import pytest

from replay_room.contracts.plan import Beat
from replay_room.framing import Facts, UnresolvedBeat, check_plan, flaw_of, rules_plan

HERO = "SYN-0007-big_chance_saved-3"


def _kinds(plan):
    return [b.kind for b in plan.beats]


def test_every_rule_plan_passes_the_critic(all_accounts, all_contexts):
    for mid, a in all_accounts.items():
        plan = rules_plan(a, all_contexts[mid])
        assert check_plan(plan, a, all_contexts[mid]) == [], mid
        assert plan.lead_contribution_id == a.headline_contribution_id
        assert _kinds(plan).count("outcome") == 1


def test_a_realized_story_leads_with_the_attack_then_points_at_the_flaw(all_accounts, all_contexts):
    a = all_accounts["SYN-0007-goal-1"]
    plan = rules_plan(a, all_contexts["SYN-0007-goal-1"])
    kinds = _kinds(plan)
    assert kinds.index("lead") < kinds.index("flaw") < kinds.index("context") < kinds.index("outcome")
    flaw = next(b for b in plan.beats if b.kind == "flaw")
    assert (flaw.contribution_id, flaw.link_id) == ("sNBR-05", "LNBR-05")  # the flaw is told through its link
    assert "sEPA-09" not in {b.contribution_id for b in plan.beats}  # the runner's run is told by the link


def test_a_prevented_story_builds_the_chance_then_the_denial(all_accounts, all_contexts):
    a = all_accounts[HERO]
    kinds = _kinds(rules_plan(a, all_contexts[HERO]))
    assert kinds.index("flaw") < kinds.index("lead") < kinds.index("outcome") < kinds.index("counterfactual")


def test_context_only_where_it_deviates(all_accounts, all_contexts):
    for mid, a in all_accounts.items():
        ctx = all_contexts[mid]
        told = {b.context_fact_id for b in rules_plan(a, ctx).beats if b.kind == "context"}
        assert told == {f.fact_id for f in ctx.facts if f.deviates} or len(told) == 2


def test_flaw_of_follows_the_account(all_accounts):
    for a in all_accounts.values():
        flaw, punish = flaw_of(a)
        if flaw is not None:
            assert flaw.team_id == a.outcome.conceding_team_id and flaw.effect > 0
        assert punish is None or a.headline.role == "primary_cause"


def test_a_planted_fact_is_rejected(all_accounts, all_contexts):
    a, ctx = all_accounts[HERO], all_contexts[HERO]
    plan = rules_plan(a, ctx)
    planted = {
        "an invented contribution": Beat(beat_id="x1", kind="build_up", contribution_id="a999"),
        "an invented link": Beat(beat_id="x1", kind="link", link_id="LNBR-02"),
        "an invented context fact": Beat(beat_id="x1", kind="context", context_fact_id="ctx-pressing_intensity"),
        "a typical context fact told as a deviation": Beat(beat_id="x1", kind="context",
                                                           context_fact_id="ctx-marking_distance"),
        "an attacking act told as a flaw": Beat(beat_id="x1", kind="flaw", contribution_id="a157"),
        "a fact told twice": Beat(beat_id="x1", kind="build_up", contribution_id="a159"),
        "a link pinned to the wrong defender": Beat(beat_id="x1", kind="flaw", contribution_id="sNBR-05",
                                                    link_id="LNBR-99"),
    }
    for name, beat in planted.items():
        bad = plan.model_copy(update={"beats": (beat, *plan.beats)})
        assert check_plan(bad, a, ctx), name


def test_the_framing_rules_are_enforced(all_accounts, all_contexts):
    a, ctx = all_accounts["SYN-0007-goal-1"], all_contexts["SYN-0007-goal-1"]
    plan = rules_plan(a, ctx)
    beats = list(plan.beats)
    lead = next(i for i, b in enumerate(beats) if b.kind == "lead")
    flaw = next(i for i, b in enumerate(beats) if b.kind == "flaw")
    beats[lead], beats[flaw] = beats[flaw], beats[lead]  # the flaw before the attack in a realized story
    assert any("attack leads" in e for e in check_plan(plan.model_copy(update={"beats": tuple(beats)}), a, ctx))
    demoted = tuple(b.model_copy(update={"emphasis": "support"}) if b.kind == "lead" else b for b in plan.beats)
    assert any("must lead" in e for e in check_plan(plan.model_copy(update={"beats": demoted}), a, ctx))
    no_outcome = tuple(b for b in plan.beats if b.kind != "outcome")
    assert any("outcome" in e for e in check_plan(plan.model_copy(update={"beats": no_outcome}), a, ctx))


def test_facts_resolve_refs_and_players(all_accounts, all_contexts):
    a, ctx = all_accounts[HERO], all_contexts[HERO]
    facts = Facts(a, ctx)
    plan = rules_plan(a, ctx)
    flaw = next(b for b in plan.beats if b.kind == "flaw")
    assert facts.players(flaw) == {"NBR-05", "EPA-11", "EPA-08"}  # Novak, the runner Ferraro, Robin Hale (the pass)
    assert all(r.kind in ("event", "frame") for r in facts.refs(flaw))
    with pytest.raises(UnresolvedBeat):
        facts.refs(Beat(beat_id="z", kind="link", link_id="nope"))


def test_a_plan_that_drops_the_computed_counterfactual_is_rejected(all_accounts, all_contexts):
    a, ctx = all_accounts[HERO], all_contexts[HERO]
    assert a.counterfactuals  # the hero's better option
    plan = rules_plan(a, ctx)
    dropped = plan.model_copy(update={"beats": [b for b in plan.beats if b.kind != "counterfactual"]})
    errors = check_plan(dropped, a, ctx)
    assert errors and "must be told" in errors[-1]
