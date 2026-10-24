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


def test_positional_facts_for_the_story(match, moments, all_accounts):
    a = all_accounts["SYN-0007-big_chance_saved-3"]
    ctx = match_context_for(match, a.moment, a)
    novak = next(p for p in ctx.positions if p.player_id == "NBR-05" and p.frame_id == 2419)
    assert novak.phase == "defending" and novak.confidence == "medium" and novak.sample_spells == 12
    assert novak.forward_m == pytest.approx(16.8, abs=0.05)  # stepped up, far from where he usually stands
    assert novak.deviation_m >= abs(novak.forward_m) and novak.nearest_opponent_id == "EPA-11"
    swing = next(s for s in ctx.swings if s.label == "LNBR-05")
    assert (swing.frame_from, swing.frame_to, swing.control_from, swing.control_to) == (2354, 2419, 0.33, 0.41)
    for p in ctx.positions:  # every average rests on enough possessions, or there is none
        assert (p.average is None) == (p.confidence is None)
        if p.confidence is not None:
            assert p.sample_spells >= MIN_SAMPLES
    for m in ctx.markings:  # a marking is only someone within marking range
        assert m.separation_from <= 10.0


def test_a_marking_that_breaks(match, all_accounts):
    a = all_accounts["SYN-0007-turnover_to_shot-1"]  # Sam Brandt loses Sam Adeyemi
    ctx = match_context_for(match, a.moment, a)
    m = next(m for m in ctx.markings if m.defender_id == "NBR-02")
    assert m.man_id == "EPA-09" and not m.held and m.separation_to - m.separation_from >= 2.5
