import io
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from replay_room.contracts import ContextEvent, MatchMeta, Moment, Period, Team
from replay_room.contracts.moment import EXPLAINED_CLASSES, FLAGGED_CLASSES
from replay_room.detect import (
    ALL_CLASSES,
    detect_big_chances_saved,
    detect_goal_moments,
    detect_moments,
    detect_turnover_to_shot,
)
from replay_room.detect.__main__ import main
from replay_room.detect.explained import BIG_CHANCE_XG, TURNOVER_TO_SHOT_SECONDS
from replay_room.ingest import load_match
from replay_room.metrics.xg import PENALTY_XG, XGModel

SNAPSHOT = Path(__file__).resolve().parent / "snapshots" / "goal_moments_synthetic_match_01.json"


# --------------------------------------------------------------------------- goal regression


@pytest.fixture(scope="module")
def legacy_goals():
    """The goal moments as Build 2 emitted them before the class-agnostic revision."""
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def _legacy_fields(moments, legacy):
    return [{k: m.model_dump(mode="json")[k] for k in legacy[0]} for m in moments]


def test_goal_detection_unchanged(match, legacy_goals):
    moments = [c.moment for c in detect_goal_moments(match.actions, match.tracking)]
    assert len(moments) == len(legacy_goals) == 4
    assert _legacy_fields(moments, legacy_goals) == legacy_goals
    for m in moments:
        assert (m.type, m.engine_eligible, m.outcome_scored) == ("goal", True, True)
        assert m.outcome_ref == m.key_event_ref
        assert m.secondary_types == () and m.outcome_xg is None


@pytest.mark.parametrize("classes", [("goal",), EXPLAINED_CLASSES, ALL_CLASSES])
def test_dispatcher_goals_unchanged(match, legacy_goals, classes):
    found = detect_moments(match.actions, match.tracking, match.meta, classes, match.context)
    goals = [c.moment for c in found if c.moment.type == "goal"]
    assert _legacy_fields(goals, legacy_goals) == legacy_goals
    assert all(0 < m.outcome_xg < 1 for m in goals)


# --------------------------------------------------------------------------- fixture


@pytest.fixture(scope="module")
def explained(match):
    return detect_moments(match.actions, match.tracking, match.meta, EXPLAINED_CLASSES, match.context)


def test_fixture_moments_by_class(explained):
    got = [(c.moment.type, c.moment.key_event_ref.original_event_id, c.moment.secondary_types) for c in explained]
    assert got == [
        ("turnover_to_shot", "ev00026", ()),
        ("big_chance_saved", "ev00034", ("turnover_to_shot",)),
        ("goal", "ev00052", ("turnover_to_shot",)),
        ("turnover_to_shot", "ev00090", ()),
        ("turnover_to_shot", "ev00137", ()),
        ("goal", "ev00158", ()),
        ("turnover_to_shot", "ev00171", ()),
        ("goal", "ev00178", ("turnover_to_shot",)),
        ("big_chance_saved", "ev00185", ()),
        ("goal", "ev00213", ("turnover_to_shot",)),
        ("big_chance_saved", "ev00222", ()),
    ]


def test_one_shape_for_every_explained_moment(explained, match):
    by_id = match.actions.set_index("action_id")
    for ctx in explained:
        m = ctx.moment
        assert m.engine_eligible and m.chain[-1] == m.key_event_ref == m.outcome_ref
        assert ctx.chain_actions["action_id"].tolist() == list(m.chain_action_ids)
        assert sorted(ctx.frames["frame_id"].unique()) == list(range(m.window.frame_start, m.window.frame_end + 1))
        assert by_id.at[m.outcome_ref.action_id, "type_name"].startswith("shot")
        assert m.outcome_scored == (m.type == "goal")


def test_turnover_to_shot_on_fixture(explained, match):
    (m,) = [c.moment for c in explained if c.moment.key_event_ref.original_event_id == "ev00026"]
    assert m.chain_start == "regain" and m.turnover_event_ref is not None
    lost = match.actions.set_index("action_id").loc[m.turnover_event_ref.action_id]
    assert lost["team_id"] == m.defending_team_id
    assert m.t_event - m.chain[0].time_seconds <= TURNOVER_TO_SHOT_SECONDS
    # every qualifying shot after a regain is listed, even a low-value one (NBR's effort, xG 0.058)
    (late,) = [c.moment for c in explained if c.moment.key_event_ref.original_event_id == "ev00137"]
    assert late.type == "turnover_to_shot" and late.outcome_xg < 0.1


def test_big_chance_saved_on_fixture(explained):
    for c in explained:
        if c.moment.type == "big_chance_saved":
            assert c.moment.outcome_xg >= BIG_CHANCE_XG and not c.moment.outcome_scored
    keys = {c.moment.key_event_ref.original_event_id for c in explained}
    assert "ev00199" not in keys  # a saved shot at xG 0.09: not a big chance (and not after a regain)


def test_dispatcher_subset_and_errors(match):
    only = detect_moments(match.actions, match.tracking, match.meta, ["big_chance_saved"])
    assert [c.moment.moment_id for c in only] == [f"SYN-0007-big_chance_saved-{i}" for i in (1, 2, 3)]
    assert all(c.moment.secondary_types == () for c in only)  # nothing else requested to share with
    turnovers = detect_moments(match.actions, match.tracking, match.meta, ["turnover_to_shot"])
    assert len(turnovers) == 8  # unclaimed by goals / big chances, every qualifying shot is listed
    with pytest.raises(ValueError, match="unknown moment classes"):
        detect_moments(match.actions, match.tracking, match.meta, ["red_card"])


def test_dispatcher_deterministic_and_pure(match, explained):
    actions, tracking = match.actions.copy(), match.tracking.copy()
    again = detect_moments(match.actions, match.tracking, match.meta, EXPLAINED_CLASSES, match.context)
    assert [c.moment for c in again] == [c.moment for c in explained]
    pd.testing.assert_frame_equal(match.actions, actions)
    pd.testing.assert_frame_equal(match.tracking, tracking)
    for ctx in explained:
        assert Moment.model_validate_json(ctx.moment.model_dump_json()) == ctx.moment


# --------------------------------------------------------------------------- hand-built cases

# Toy xG: logistic in distance only (6 m -> 0.86, 20 m -> 0.27, 25 m -> 0.12, 30 m -> 0.05).
TOY_XG = XGModel(coef=[-1.0, 0.0, 0.0], intercept=-1.0, means=[20.0, 0.0, 0.0], scales=[5.0, 1.0, 1.0])
META = MatchMeta(
    game_id="g", competition="test",
    home_team=Team(team_id="A", name="Alpha", short_name="A", players=()),
    away_team=Team(team_id="B", name="Beta", short_name="B", players=()),
    periods=(Period(period_id=1, start_seconds=0.0, end_seconds=60.0),),
    frame_rate_hz=10.0, source="test",
)


def _tracking(period_seconds=60.0):
    ts = np.round(np.arange(0, period_seconds + 1e-9, 0.1), 1)
    rows = [(fid, 1, float(t), pid, team, 50.0, 34.0, 0.0, 0.0)
            for fid, t in enumerate(ts) for pid, team in (("A-1", "A"), ("B-1", "B"), ("ball", "ball"))]
    return pd.DataFrame(rows, columns=["frame_id", "period_id", "timestamp", "player_id", "team_id",
                                       "x", "y", "vx", "vy"])


def _actions(rows):
    """rows: (t, team, type, result, x). A attacks +x and B attacks -x (canonical frame)."""
    return pd.DataFrame([
        {"game_id": "g", "original_event_id": f"e{i}", "action_id": i, "period_id": 1, "time_seconds": t,
         "team_id": team, "player_id": f"{team}-1", "start_x": x, "start_y": 34.0, "end_x": x, "end_y": 34.0,
         "type_name": typ, "result_name": res, "bodypart_name": "foot"}
        for i, (t, team, typ, res, x) in enumerate(rows)
    ])


def _detect(rows, classes=EXPLAINED_CLASSES, context=()):
    return [c.moment for c in detect_moments(_actions(rows), _tracking(), META, classes, context, xg_model=TOY_XG)]


def test_turnover_to_shot_fires_on_regain_then_shot():
    rows = [
        (0.0, "B", "pass", "success", 60.0),
        (10.0, "A", "interception", "success", 55.0),  # A regain
        (12.0, "A", "pass", "success", 70.0),
        (14.0, "A", "shot", "fail", 80.0),  # 25 m: xG 0.12, a chance but not a big one
    ]
    (m,) = _detect(rows)
    assert m.type == "turnover_to_shot" and m.engine_eligible
    assert m.chain_action_ids == (1, 2, 3) and m.chain_start == "regain" and m.turnover_event_ref.action_id == 0
    assert m.outcome_ref == m.key_event_ref and m.outcome_scored is False
    assert m.outcome_xg == pytest.approx(TOY_XG.predict_features(np.array([[25.0, 0, 0]]))[0])


def test_turnover_to_shot_needs_a_recent_regain():
    slow = [(0.0, "B", "pass", "success", 60.0), (10.0, "A", "interception", "success", 55.0),
            (10.0 + TURNOVER_TO_SHOT_SECONDS + 1, "A", "shot", "fail", 80.0)]
    assert _detect(slow) == []
    restart = [(0.0, "A", "throw_in", "success", 70.0), (3.0, "A", "shot", "fail", 80.0)]  # set piece, no regain
    assert _detect(restart) == []


def test_big_chance_saved_fires_on_high_xg_non_goal_only():
    rows = [
        (0.0, "A", "pass", "success", 90.0),
        (2.0, "A", "shot", "fail", 99.0),  # 6 m: xG 0.86, saved
        (4.0, "B", "keeper_save", "success", 104.0),
        (20.0, "A", "pass", "success", 70.0),
        (22.0, "A", "shot", "fail", 75.0),  # 30 m: xG 0.05, not a big chance
        (30.0, "B", "pass", "success", 30.0),
        (32.0, "B", "shot", "fail", 6.0),  # B attacks -x: 6 m from its goal, a big chance
        (40.0, "A", "pass", "success", 90.0),
        (42.0, "A", "shot", "success", 99.0),  # high xG but scored: a goal, not a big chance saved
    ]
    big = [m for m in _detect(rows, ["big_chance_saved"])]
    assert [m.key_event_ref.action_id for m in big] == [1, 6]
    assert all(m.outcome_xg >= BIG_CHANCE_XG and m.outcome_scored is False for m in big)
    assert big[1].attacking_team_id == "B"


def test_big_chance_detector_reads_the_given_xg():
    actions = _actions([(0.0, "A", "pass", "success", 90.0), (2.0, "A", "shot", "fail", 99.0),
                        (4.0, "B", "pass", "success", 50.0)])
    xg = pd.Series({1: BIG_CHANCE_XG - 0.01})
    assert detect_big_chances_saved(actions, _tracking(), xg) == []
    assert len(detect_big_chances_saved(actions, _tracking(), pd.Series({1: BIG_CHANCE_XG}))) == 1
    assert detect_turnover_to_shot(actions, _tracking(), xg) == []  # no regain before the shot


PENALTY_ROWS = [
    (0.0, "B", "pass", "success", 60.0),
    (20.0, "A", "interception", "success", 70.0),  # A regain
    (22.0, "A", "dribble", "success", 92.0),
    (24.0, "B", "foul", "fail", 95.0),  # B fouls in its own box
    (40.0, "A", "shot_penalty", "success", 94.0),
]


def test_penalty_key_is_the_foul_and_outcome_the_kick():
    (m,) = _detect(PENALTY_ROWS)
    assert m.type == "penalty" and m.engine_eligible
    assert m.key_event_ref.action_id == 3 and m.chain_action_ids == (1, 2, 3)  # build-up ending in the foul
    assert m.chain_start == "regain" and m.turnover_event_ref.action_id == 0
    assert m.outcome_ref.action_id == 4 and m.outcome_scored is True
    assert m.outcome_xg == PENALTY_XG
    assert m.attacking_team_id == "A" and m.key_player_id == "B-1"
    assert m.secondary_types == ("goal",)  # the scored kick is not listed again as a one-action goal
    assert m.window.t_end == pytest.approx(24.0 + 2.0)  # the run-up to the foul


def test_penalty_goal_alone_is_a_one_action_goal():
    (m,) = _detect(PENALTY_ROWS, ["goal"])
    assert m.type == "goal" and m.chain_action_ids == (4,) and m.chain_start == "set_piece"


def test_penalty_without_a_foul_in_the_feed():
    (m,) = _detect([(0.0, "A", "pass", "success", 80.0), (30.0, "A", "shot_penalty", "fail", 94.0)])
    assert m.type == "penalty" and m.key_event_ref == m.outcome_ref and m.outcome_scored is False


def test_flagged_classes_are_not_engine_eligible():
    rows = [(0.0, "A", "pass", "success", 60.0), (5.0, "A", "pass", "offside", 80.0),
            (8.0, "B", "freekick_short", "success", 80.0)]
    context = (
        ContextEvent("c1", 1, 30.0, "substitution", team_id="B", player_id="B-1", target_player_id="B-12"),
        ContextEvent("c2", 1, 20.0, "injury", team_id="A", player_id="A-1"),
        ContextEvent("c3", 1, 50.0, "var_decision", detail="goal_stands"),
        ContextEvent("c4", 1, 51.0, "pressure", team_id="B", player_id="B-1"),  # not a moment
    )
    found = _detect(rows, ALL_CLASSES, context)
    assert [(m.type, m.engine_eligible) for m in found] == [
        ("offside", False), ("injury", False), ("substitution", False), ("var_decision", False)]
    offside, injury, sub, var = found
    assert offside.window is not None and offside.key_event_ref.action_id == 1 and offside.team_id == "A"
    assert sub.key_event_ref.event_id == "c1" and (sub.team_id, sub.key_player_id) == ("B", "B-1")
    assert var.detail == "goal_stands" and var.team_id is None
    for m in found:
        assert m.chain == () and m.outcome_ref is None and m.outcome_xg is None
    assert _detect(rows, ["offside"], context) == [offside]  # selectable on their own


def test_dispatcher_returns_one_time_sorted_list():
    rows = PENALTY_ROWS + [
        (44.0, "B", "pass", "success", 20.0),
        (46.0, "B", "pass", "offside", 15.0),
        (48.0, "A", "freekick_short", "success", 15.0),
        (50.0, "A", "pass", "success", 92.0),
        (52.0, "A", "shot", "success", 99.0),
    ]
    context = (ContextEvent("c1", 1, 45.0, "substitution", team_id="A", player_id="A-1"),
               ContextEvent("c2", 1, 10.0, "injury", team_id="B", player_id="B-1"))
    found = _detect(rows, ALL_CLASSES, context)
    assert [m.type for m in found] == ["injury", "penalty", "substitution", "offside", "goal"]
    times = [(m.period_id, m.t_event) for m in found]
    assert times == sorted(times)
    assert [m.engine_eligible for m in found] == [m.type in EXPLAINED_CLASSES for m in found]
    assert {m.type for m in found if not m.engine_eligible} <= set(FLAGGED_CLASSES)


# --------------------------------------------------------------------------- ingest -> detect


def test_new_raw_types_flow_through_ingest(fixture_dir, tmp_path):
    match_dir = tmp_path / "match"
    shutil.copytree(fixture_dir, match_dir)
    extra = [  # raw frame: in period 2 the home team (NBR) attacks raw -x
        {"id": "ev90001", "period": 1, "t": 60.0, "type": "Injury", "team": "EPA", "player": "EPA-04"},
        {"id": "ev90002", "period": 2, "t": 78.5, "type": "VarDecision", "decision": "goal_stands"},
        {"id": "ev90003", "period": 2, "t": 100.0, "type": "Substitution", "team": "EPA", "player": "EPA-09",
         "target": "EPA-12"},
        {"id": "ev90004", "period": 2, "t": 149.9, "type": "Pass", "team": "NBR", "player": "NBR-11", "x": -30.0,
         "y": -14.0, "end_x": -38.0, "end_y": -5.0, "outcome": "offside", "body_part": "right_foot"},
        {"id": "ev90005", "period": 2, "t": 149.9, "type": "Foul", "team": "EPA", "player": "EPA-05",
         "x": -43.5, "y": 4.0},
        {"id": "ev90006", "period": 2, "t": 149.9, "type": "Penalty", "team": "NBR", "player": "NBR-09",
         "x": -41.5, "y": 0.0, "end_x": -52.5, "end_y": 1.0, "outcome": "saved", "body_part": "right_foot"},
    ]
    with (match_dir / "events.jsonl").open("a", encoding="utf-8") as fh:
        fh.writelines(json.dumps(ev) + "\n" for ev in extra)
    m = load_match(match_dir)
    by_event = m.actions.set_index("original_event_id")
    assert by_event.loc["ev90004", "result_name"] == "offside"
    assert by_event.loc["ev90005", "type_name"] == "foul"
    assert tuple(by_event.loc["ev90006", ["type_name", "start_x", "start_y"]]) == ("shot_penalty", 94.0, 34.0)
    var = next(c for c in m.context if c.event_id == "ev90002")
    assert (var.kind, var.detail) == ("var_decision", "goal_stands")

    found = {c.moment.type: c.moment for c in detect_moments(m.actions, m.tracking, m.meta, ALL_CLASSES, m.context)}
    assert set(found) == set(ALL_CLASSES)
    pen = found["penalty"]
    assert pen.key_event_ref.original_event_id == "ev90005" and pen.outcome_ref.original_event_id == "ev90006"
    assert (pen.outcome_scored, pen.outcome_xg, pen.attacking_team_id) == (False, PENALTY_XG, "NBR")
    assert found["substitution"].key_event_ref.event_id == "ev90003"


# --------------------------------------------------------------------------- CLI


def test_cli_lists_all_explained_classes(fixture_dir):
    out = io.StringIO()
    assert main([str(fixture_dir), "--classes", "goal,turnover_to_shot,big_chance_saved,penalty"], out=out) == 0
    text = out.getvalue()
    assert text.startswith("SYN-0007: 11 moment(s)  goal 4, turnover_to_shot 4, big_chance_saved 3\n")
    assert "SYN-0007-big_chance_saved-1  big_chance_saved  [1 00:20.9]" in text
    assert "outcome: ev00034 no goal  xG 0.175  also turnover_to_shot" in text
    assert text.count("engine_eligible") == 11
    default = io.StringIO()
    main([str(fixture_dir)], out=default)
    assert default.getvalue() == text  # the default is the explained classes


def test_cli_rejects_unknown_class_and_streamed_non_goals(fixture_dir, capsys):
    with pytest.raises(SystemExit):
        main([str(fixture_dir), "--classes", "red_card"])
    with pytest.raises(SystemExit):
        main([str(fixture_dir), "--stream", "--classes", "penalty"])
    assert "goals only" in capsys.readouterr().err
