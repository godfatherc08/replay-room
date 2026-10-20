import io
import json

import numpy as np
import pandas as pd
import pytest

from replay_room.contracts import Moment
from replay_room.detect import detect_goal_moments
from replay_room.detect.__main__ import detect_streaming, main
from replay_room.detect.moments import (
    CHAIN_MAX_ACTIONS,
    WINDOW_AFTER,
    WINDOW_BEFORE_MAX,
    WINDOW_BEFORE_MIN,
)


@pytest.fixture(scope="module")
def moments(match):
    return detect_goal_moments(match.actions, match.tracking)


# Hand-checked against the fixture's event log (see tests/test_possessions.py for the boundaries).
EXPECTED = [
    # key event, team, scorer, chain action ids, chain start, turnover action id, contested
    ("ev00052", "EPA", "EPA-09", tuple(range(31, 37)), "regain", 30, ()),
    ("ev00158", "EPA", "EPA-09", tuple(range(111, 116)), "period_start", None, ()),
    ("ev00178", "EPA", "EPA-07", (127, 128, 129), "regain", 126, ()),
    ("ev00213", "NBR", "NBR-09", tuple(range(147, 157)), "regain", 146, (154,)),
]


def test_one_moment_per_goal(match, moments, fixture_dir):
    goals = match.actions[(match.actions["type_name"] == "shot") & (match.actions["result_name"] == "success")]
    assert len(moments) == len(goals) == 4
    score = json.loads((fixture_dir / "meta.json").read_text(encoding="utf-8"))["final_score"]
    assert sum(m.moment.attacking_team_id == "NBR" for m in moments) == score["home"]
    assert sum(m.moment.attacking_team_id == "EPA" for m in moments) == score["away"]


@pytest.mark.parametrize("i", range(len(EXPECTED)))
def test_chain_assembly(moments, match, i):
    key, team, scorer, chain, start, turnover, contested = EXPECTED[i]
    m = moments[i].moment
    assert m.key_event_ref.original_event_id == key
    assert (m.attacking_team_id, m.key_player_id, m.type) == (team, scorer, "goal")
    assert m.defending_team_id == ({"NBR", "EPA"} - {team}).pop()
    assert m.chain_action_ids == chain
    assert m.chain_action_ids[-1] == m.key_event_ref.action_id  # ends at the goal
    assert m.chain_start == start
    assert (m.turnover_event_ref.action_id if m.turnover_event_ref else None) == turnover
    assert m.contested_action_ids == contested
    rows = moments[i].chain_actions
    assert rows["action_id"].tolist() == list(chain)
    if start == "regain":  # starts at the regain: the attacking team's first touch after the defending team's
        assert rows["team_id"].iloc[0] == team
        lost = match.actions.set_index("action_id").loc[turnover]
        assert lost["team_id"] == m.defending_team_id


@pytest.mark.parametrize("i", range(len(EXPECTED)))
def test_window_bounds(moments, match, i):
    ctx = moments[i]
    m, w = ctx.moment, ctx.moment.window
    period_frames = match.tracking[match.tracking["period_id"] == m.period_id]
    period_start, period_end = period_frames["timestamp"].min(), period_frames["timestamp"].max()
    assert w.t_end == pytest.approx(min(m.t_event + WINDOW_AFTER, period_end))
    before = m.t_event - w.t_start
    if w.t_start > period_start:
        assert WINDOW_BEFORE_MIN - 1e-9 <= before <= WINDOW_BEFORE_MAX + 1e-9
    else:
        assert before < WINDOW_BEFORE_MIN  # clipped at the start of the period
    # correct frames, correct length
    assert w.n_frames == round((w.t_end - w.t_start) * 10) + 1
    assert sorted(ctx.frames["frame_id"].unique()) == list(range(w.frame_start, w.frame_end + 1))
    assert (ctx.frames["period_id"] == m.period_id).all()
    assert (ctx.frames.groupby("frame_id").size() == 23).all()
    ts = ctx.frames.drop_duplicates("frame_id")["timestamp"]
    assert ts.min() == w.t_start and ts.max() == w.t_end


def test_expected_windows(moments):
    got = [(c.moment.window.frame_start, c.moment.window.frame_end) for c in moments]
    assert got == [(294, 414), (1501, 1595), (1731, 1851), (2170, 2301)]


def test_moments_roundtrip_json(moments):
    for ctx in moments:
        assert Moment.model_validate_json(ctx.moment.model_dump_json()) == ctx.moment


def test_pure_and_deterministic(match, moments):
    actions, tracking = match.actions.copy(), match.tracking.copy()
    again = detect_goal_moments(match.actions, match.tracking)
    assert [c.moment for c in again] == [c.moment for c in moments]
    pd.testing.assert_frame_equal(match.actions, actions)
    pd.testing.assert_frame_equal(match.tracking, tracking)


def test_streaming_matches_batch(fixture_dir, moments):
    _, streamed = detect_streaming(str(fixture_dir))
    assert [c.moment for c in streamed] == [c.moment for c in moments]


# --------------------------------------------------------------------------- hand-built cases


def _tracking(period_seconds=60.0):
    ts = np.round(np.arange(0, period_seconds + 1e-9, 0.1), 1)
    rows = []
    for fid, t in enumerate(ts):
        for pid, team in (("A-1", "A"), ("B-1", "B"), ("ball", "ball")):
            rows.append((fid, 1, float(t), pid, team, 50.0, 34.0, 0.0, 0.0))
    return pd.DataFrame(rows, columns=["frame_id", "period_id", "timestamp", "player_id", "team_id",
                                       "x", "y", "vx", "vy"])


def _actions(rows):
    return pd.DataFrame([
        {"game_id": "g", "original_event_id": f"e{i}", "action_id": i, "period_id": 1, "time_seconds": t,
         "team_id": team, "player_id": f"{team}-1", "type_name": typ, "result_name": res}
        for i, (t, team, typ, res) in enumerate(rows)
    ])


def test_own_goal_credited_to_attacking_team():
    actions = _actions([
        (0.0, "B", "pass", "success"),
        (20.0, "A", "interception", "success"),  # A regain
        (22.0, "A", "cross", "success"),
        (24.0, "B", "clearance", "owngoal"),     # B turns it into their own net
    ])
    (ctx,) = detect_goal_moments(actions, _tracking())
    m = ctx.moment
    assert m.is_own_goal and (m.attacking_team_id, m.defending_team_id) == ("A", "B")
    assert m.key_player_id == "B-1"
    assert m.chain_action_ids == (1, 2, 3) and m.chain_start == "regain"
    assert m.turnover_event_ref.action_id == 0


def test_long_possession_chain_is_capped():
    n = CHAIN_MAX_ACTIONS + 10
    rows = [(0.5 * i, "A", "pass", "success") for i in range(n)] + [(0.5 * n, "A", "shot", "success")]
    (ctx,) = detect_goal_moments(_actions(rows), _tracking())
    m = ctx.moment
    assert len(m.chain) == CHAIN_MAX_ACTIONS and m.chain_start == "truncated"
    assert m.turnover_event_ref is None
    assert m.chain_action_ids[-1] == n
    assert m.t_start == m.window.t_start  # the window reaches further back than the capped chain


def test_goal_near_period_end_window_is_clipped():
    rows = [(0.0, "A", "pass", "success"), (59.5, "A", "shot", "success")]
    (ctx,) = detect_goal_moments(_actions(rows), _tracking(60.0))
    assert ctx.moment.window.t_end == 60.0


# --------------------------------------------------------------------------- CLI


def test_cli_lists_moments(fixture_dir):
    out = io.StringIO()
    assert main([str(fixture_dir)], out=out) == 0
    text = out.getvalue()
    assert text.startswith("SYN-0007: 4 goal moment(s)")
    assert "chain: 10 actions #147..#156  from regain after ev00199" in text
    assert "window: frames 294..414 (121)" in text


def test_cli_json(fixture_dir):
    out = io.StringIO()
    main([str(fixture_dir), "--json"], out=out)
    data = json.loads(out.getvalue())
    assert [Moment.model_validate(d).moment_id for d in data] == [f"SYN-0007-goal-{i}" for i in range(1, 5)]
