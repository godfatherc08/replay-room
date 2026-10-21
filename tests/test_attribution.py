import io
import json
import shutil
import warnings
from dataclasses import replace

import pytest

from replay_room.attribution.__main__ import main
from replay_room.attribution.engine import attribute, attribute_match
from replay_room.attribution.fuse import EFFECT_THRESHOLD, RECENCY_FLOOR, TOP_K, headline, recency, select
from replay_room.attribution.outcome import Candidate
from replay_room.attribution.store import load_account, save_accounts
from replay_room.contracts import CausalAccount, EventRef
from replay_room.detect import detect_moments
from replay_room.ingest import load_match
from replay_room.metrics import load_models, rate_actions, value_moment
from replay_room.metrics.xg import PENALTY_XG


def _quiet(fn, *args, **kwargs):
    with warnings.catch_warnings():  # socceraction's VAEP feature code trips pandas FutureWarnings
        warnings.simplefilter("ignore", FutureWarning)
        return fn(*args, **kwargs)


@pytest.fixture(scope="module")
def accounts(match):
    return {a.moment.moment_id: a for a in _quiet(attribute_match, match)}


def _by_id(account):
    return {c.contribution_id: c for c in account.contributions}


def test_every_explained_fixture_moment_gets_an_account(accounts, match):
    moments = [c.moment for c in detect_moments(match.actions, match.tracking, match.meta)]
    assert list(accounts) == [m.moment_id for m in moments]
    assert {a.moment.type for a in accounts.values()} == {"goal", "turnover_to_shot", "big_chance_saved"}
    for a in accounts.values():
        assert CausalAccount.model_validate_json(a.model_dump_json()) == a
        assert a.outcome.value == pytest.approx(a.moment.outcome_xg)  # attributed over outcome_ref's value
    tracks = {c.track for a in accounts.values() for c in a.contributions}
    assert tracks == {"on_ball", "off_ball"}


def test_realized_goal(accounts):
    a = accounts["SYN-0007-goal-1"]
    assert a.outcome.realized and a.outcome.scored
    c = _by_id(a)
    assert c["a35"].role == "assist" and c["a35"].effect > EFFECT_THRESHOLD  # the key pass is a creator
    head = a.headline
    # NBR-05 conceding space just before the shot leads NBR-04's larger but earlier lost ball (recency)
    assert head.contribution_id == "sNBR-05" and head.role == "primary_cause" and head.track == "off_ball"
    assert head.team_id == a.outcome.conceding_team_id and head.effect > 0
    lost = c["a30"]
    assert lost.role == "defensive_error" and lost.effect > head.effect and lost.rank < head.rank  # ranks unchanged
    m = a.moment
    assert head.effect * recency(head.t, m.t_start, m.t_event) > lost.effect * recency(lost.t, m.t_start, m.t_event)


def test_off_ball_lapse_can_be_the_headline(accounts):
    a = accounts["SYN-0007-goal-2"]  # no lost ball: the move started at kick-off
    head = a.headline
    assert head.track == "off_ball" and head.role == "primary_cause" and head.kind == "space_conceded"
    assert head.metrics["space_conceded"] == pytest.approx(head.effect, abs=1e-6)  # the claim carries its number


def test_turnover_to_shot(accounts, match):
    a = accounts["SYN-0007-turnover_to_shot-5"]
    m = a.moment
    turnover = _by_id(a)[f"a{m.turnover_event_ref.action_id}"]
    assert turnover.team_id == m.defending_team_id and turnover.effect > 0 and turnover.metrics["lost_ball"] == 1
    assert turnover.metrics["value"] < 0  # a negative for the side that lost it
    regain = _by_id(a)[f"a{m.chain_action_ids[0]}"]
    assert regain.team_id == m.attacking_team_id and regain.effect > 0
    on_ball = {c.evidence[0].action_id for c in a.contributions if c.track == "on_ball"}
    assert on_ball <= set(m.chain_action_ids) | {m.turnover_event_ref.action_id}


def test_big_chance_saved_is_framed_prevented(accounts):
    a = accounts["SYN-0007-big_chance_saved-1"]
    assert not a.outcome.realized and not a.outcome.scored and a.outcome.value >= 0.15
    head = a.headline
    assert (head.kind, head.role, head.action, head.player_id) == ("chance_denied", "prevention", "keeper_save",
                                                                    "NBR-01")
    assert head.effect == pytest.approx(-a.outcome.value, abs=1e-6) and head.team_id == a.outcome.conceding_team_id
    creators = [c for c in a.contributions if c.team_id == a.outcome.beneficiary_team_id and c.effect > 0]
    assert creators and {"finish", "space_creation"} <= {c.role for c in creators}


def test_a_miss_denies_itself(accounts):
    a = accounts["SYN-0007-big_chance_saved-2"]  # off target: no defender touched it
    assert a.headline.action == "shot_missed" and a.headline.player_id == a.moment.key_player_id


def test_threshold_filters_incidental_touches(accounts):
    a = accounts["SYN-0007-goal-1"]
    cited = {c.evidence[0].action_id for c in a.contributions if c.track == "on_ball"}
    assert {32, 33, 34} & cited == set()  # passes and a dribble worth < 0.003
    for acc in accounts.values():
        assert len(acc.contributions) <= TOP_K + 1
        assert all(abs(c.effect) >= EFFECT_THRESHOLD for c in acc.contributions)


def _cand(key, effect, team="A"):
    return Candidate(key=key, track="on_ball", kind="action_value", role="build_up", label="pass", player_id="A-1",
                     team_id=team, t=1.0, effect=effect,
                     evidence=(EventRef(action_id=1, original_event_id="e", period_id=1, time_seconds=1.0),))


def test_select_ranks_and_filters():
    kept = select([_cand("small", 0.004), _cand("big", -0.2), _cand("mid", 0.05)])
    assert [c.key for c in kept] == ["big", "mid"]
    assert [c.key for c in select([_cand("x", 0.001), _cand("y", 0.002)])] == ["y"]  # never empty
    assert len(select([_cand(f"c{i}", 0.02 + i / 1000) for i in range(TOP_K + 5)])) == TOP_K
    with pytest.raises(ValueError, match="duplicate"):
        select([_cand("a", 0.1), _cand("a", 0.2)])


def test_headline_weighs_effect_by_recency():
    from replay_room.contracts.causal_account import Outcome

    ref = EventRef(action_id=9, original_event_id="e9", period_id=1, time_seconds=20.0)
    outcome = Outcome(ref=ref, value=0.2, value_source="xg", scored=True, realized=True,
                      beneficiary_team_id="A", conceding_team_id="B")
    early = replace(_cand("early", 0.08, team="B"), t=11.0)
    late = replace(_cand("late", 0.03, team="B"), t=19.0)
    creator = _cand("creator", 0.2)
    assert recency(5.0, 10.0, 20.0) == RECENCY_FLOOR and recency(20.0, 10.0, 20.0) == 1.0
    assert headline([early, late, creator], outcome, 10.0, 20.0).key == "late"  # 0.03 x 0.9 > 0.08 x 0.1
    assert headline([early, creator], outcome, 10.0, 20.0).key == "early"  # a conceding failure still leads
    assert headline([creator], outcome, 10.0, 20.0).key == "creator"


def test_every_contribution_is_bound(accounts, match):
    events = match.actions.set_index("action_id")["original_event_id"]
    frame_ids = set(match.tracking["frame_id"])
    for a in accounts.values():
        w = a.moment.window
        for c in a.contributions:
            assert c.evidence
            for r in c.evidence:
                if r.kind == "event":
                    assert events[r.action_id] == r.original_event_id
                else:
                    assert w.frame_start <= r.frame_id <= w.frame_end and r.frame_id in frame_ids
                    assert c.player_id in r.player_ids
        for cf in a.counterfactuals:
            assert w.frame_start <= cf.decision_frame.frame_id <= w.frame_end


def test_counterfactual_is_grounded(accounts):
    cfs = [(a, cf) for a in accounts.values() for cf in a.counterfactuals]
    assert cfs  # at least one fixture decision had a clearly better option
    for a, cf in cfs:
        assert cf.best_gap >= a.provenance.counterfactual_margin
        target = _by_id(a)[cf.contribution_id]
        assert target.track == "on_ball" and target.role in ("assist", "finish")
        players = {p.player_id for p in a.participants}
        assert all(alt.target_player_id in players for alt in cf.alternatives if alt.target_player_id)


def test_deterministic(match, accounts):
    models = load_models()
    av = _quiet(rate_actions, match.actions, match.tracking, match.meta, match.context, models, match.pass_targets)
    ctx = next(c for c in detect_moments(match.actions, match.tracking, match.meta)
               if c.moment.moment_id == "SYN-0007-goal-4")
    vm = value_moment(ctx.moment, match.actions, ctx.frames, match.meta, match.context, models, av)
    again = attribute(vm, ctx.frames, match.actions, av, match.meta, match.tracking, match.context, models)
    assert again == accounts["SYN-0007-goal-4"]
    assert again.provenance.generated_at is None


def test_flagged_moments_are_refused(match):
    from replay_room.contracts.values import ValuedMoment

    offside = next(iter(detect_moments(match.actions, match.tracking, match.meta, ["goal"]))).moment.model_copy(
        update={"type": "offside", "engine_eligible": False})
    with pytest.raises(ValueError, match="flagged"):
        attribute(ValuedMoment(offside, "vaep", (), ()), match.tracking.iloc[0:0], match.actions,
                  None, match.meta, match.tracking)


# --------------------------------------------------------------------------- penalty, through the full pipeline


@pytest.fixture(scope="module")
def penalty_account(fixture_dir, tmp_path_factory):
    match_dir = tmp_path_factory.mktemp("penalty") / "match"
    shutil.copytree(fixture_dir, match_dir)
    extra = [  # raw frame: in period 2 the home team (NBR) attacks raw -x; EPA fouls in its own box
        {"id": "ev90001", "period": 2, "t": 149.9, "type": "Foul", "team": "EPA", "player": "EPA-05",
         "x": -43.5, "y": 4.0},
        {"id": "ev90002", "period": 2, "t": 149.9, "type": "Penalty", "team": "NBR", "player": "NBR-09",
         "x": -41.5, "y": 0.0, "end_x": -52.5, "end_y": 1.0, "outcome": "goal", "body_part": "right_foot"},
    ]
    with (match_dir / "events.jsonl").open("a", encoding="utf-8") as fh:
        fh.writelines(json.dumps(ev) + "\n" for ev in extra)
    (account,) = _quiet(attribute_match, load_match(match_dir), ["penalty"])
    return account


def test_penalty_headline_is_the_foul(penalty_account):
    a = penalty_account
    assert a.moment.type == "penalty" and a.outcome.realized and a.outcome.scored
    assert a.outcome.value == PENALTY_XG and a.outcome.ref.original_event_id == "ev90002"
    head = a.headline
    assert head.evidence[0] == a.moment.key_event_ref and head.evidence[0].original_event_id == "ev90001"
    assert (head.role, head.player_id, head.team_id) == ("primary_cause", "EPA-05", "EPA")
    assert head.metrics["outcome_value"] == PENALTY_XG
    assert head.effect == pytest.approx(PENALTY_XG - head.metrics["xt_attacking"], abs=1e-6)


# --------------------------------------------------------------------------- persistence + CLI


def test_store_roundtrip(accounts, tmp_path):
    from datetime import datetime, timezone

    a = accounts["SYN-0007-goal-1"]
    (path,) = save_accounts([a], tmp_path, now=datetime(2026, 10, 21, tzinfo=timezone.utc))
    assert path == tmp_path / "SYN-0007" / "SYN-0007-goal-1.json"
    loaded = load_account(path)
    assert loaded.provenance.generated_at == "2026-10-21T00:00:00+00:00"
    assert loaded.model_copy(update={"provenance": a.provenance}) == a


def test_cli(fixture_dir):
    out = io.StringIO()
    assert main([str(fixture_dir), "--classes", "big_chance_saved"], out=out) == 0
    text = out.getvalue()
    assert text.startswith("3 causal account(s)\n")
    assert "PREVENTED (a goal that didn't happen)" in text
    assert "headline: d23  prevention  NBR-01 keeper_save  effect -0.174  (event #23)" in text
    out = io.StringIO()
    main([str(fixture_dir), "--classes", "goal", "--json"], out=out)
    assert [CausalAccount.model_validate(d).moment.type for d in json.loads(out.getvalue())] == ["goal"] * 4
