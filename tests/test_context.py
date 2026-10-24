import pytest

from replay_room.context import match_context, match_context_for
from replay_room.context.baselines import MIN_SAMPLES, confidence
from replay_room.detect import detect_moments


@pytest.fixture(scope="module")
def moments(match):
    return {c.moment.moment_id: c.moment for c in detect_moments(match.actions, match.tracking, match.meta)}


@pytest.fixture(scope="module")
def contexts(match, moments):
    return {mid: match_context_for(match, m) for mid, m in moments.items() if m.engine_eligible}


def test_baselines_describe_the_defending_team_and_cite_the_moment(contexts, moments):
    for mid, ctx in contexts.items():
        m = moments[mid]
        assert ctx.team_id == m.defending_team_id
        assert {f.kind for f in ctx.facts} | {k for k, _ in ctx.insufficient} >= {"line_height", "marking_distance"}
        for f in ctx.facts:
            assert f.sample_size >= MIN_SAMPLES and f.confidence == confidence(f.sample_size)
            for r in f.evidence:
                if r.kind == "frame":
                    assert m.window.frame_start <= r.frame_id <= m.window.frame_end  # "here" is this moment


def test_a_high_line_is_flagged(contexts):
    facts = {f.kind: f for f in contexts["SYN-0007-goal-2"].facts}
    line = facts["line_height"]  # the kick-off move caught Northbridge's line far from its goal
    assert line.deviates and line.direction == "higher" and line.here > line.spread[1] + 1.0
    assert line.baseline == pytest.approx(9.0, abs=1.0) and line.unit == "m"


def test_counter_press_only_after_their_own_lost_ball(contexts, moments):
    for mid, ctx in contexts.items():
        press = [f for f in ctx.facts if f.kind == "counter_press"]
        if moments[mid].turnover_event_ref is None:
            assert not press
        for f in press:
            assert f.metrics["won_back"] <= f.metrics["losses"] == f.sample_size
            assert f.evidence == (moments[mid].turnover_event_ref,)
            # they rarely win it back in this match, so a ball not won back is not a deviation
            assert not f.deviates and f.baseline < 0.5


def test_no_baseline_without_the_data(match, moments):
    m = moments["SYN-0007-goal-2"]
    early = match.tracking[match.tracking["frame_id"] <= m.window.frame_end]  # a match cut short at the moment
    actions = match.actions[match.actions["period_id"] == m.period_id].head(30)
    keepers = frozenset(p.player_id for t in (match.meta.home_team, match.meta.away_team) for p in t.players
                        if p.position == "GK")
    ctx = match_context(m, actions, early, match.meta.home_team_id, keepers)
    assert {k for k, _ in ctx.insufficient} >= {"line_height", "marking_distance"}
    assert all("need" in why or "not in their defensive third" in why for _, why in ctx.insufficient)


def test_deterministic(match, moments, contexts):
    m = moments["SYN-0007-goal-1"]
    assert match_context_for(match, m) == contexts["SYN-0007-goal-1"]
