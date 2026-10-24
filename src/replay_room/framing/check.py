"""``check_plan``: the Critic's rules for a framing plan. Returns the violations (empty = the plan may be told).

* **grounding**: every beat resolves to a record a tool returned (a
  contribution, link or counterfactual of the account; a fact of the match
  context); no record is told twice; beat ids are unique;
* **the lead**: exactly one beat carries the lead emphasis, and it is the
  account's headline; ``lead_contribution_id`` names it;
* **the flaw**: a ``flaw`` beat is a conceding-side failure the engine
  computed (defending team, positive effect); ``flaw_contribution_id`` names a
  told flaw; a ``punish`` beat is an attacking act with positive effect, and
  only follows a defensive-cause headline;
* **framing**: in a realized story the attack leads: the lead beat comes before
  every flaw, link and context beat; context is told only where it deviates;
* **shape**: exactly one outcome beat, after the lead; counterfactuals after it.
"""

from __future__ import annotations

from replay_room.contracts.causal_account import CausalAccount
from replay_room.contracts.context import MatchContext
from replay_room.contracts.plan import FramingPlan
from replay_room.framing.facts import Facts, UnresolvedBeat


def check_plan(plan: FramingPlan, account: CausalAccount, context: MatchContext | None = None) -> list[str]:
    facts = Facts(account, context)
    errors: list[str] = []
    if (plan.account_id, plan.moment_id) != (account.account_id, account.moment.moment_id):
        errors.append("the plan is for another account")
    ids = [b.beat_id for b in plan.beats]
    if len(ids) != len(set(ids)):
        errors.append("beat ids must be unique")
    told: dict[str, str] = {}
    for b in plan.beats:
        try:
            facts.check(b)
        except UnresolvedBeat as e:
            errors.append(f"beat {b.beat_id} ({b.kind}): {e}")
            continue
        keys = [k for k in (b.link_id, b.context_fact_id) if k]
        if b.contribution_id is not None:
            keys.append(f"{'choice' if b.kind == 'counterfactual' else 'fact'}:{b.contribution_id}")
        for key in keys:
            if key in told:
                errors.append(f"beat {b.beat_id} tells what beat {told[key]} already told")
            told[key] = b.beat_id
    if errors:
        return errors

    head = account.headline
    out = account.outcome
    leads = [b for b in plan.beats if b.emphasis == "lead"]
    if len(leads) != 1 or leads[0].contribution_id != head.contribution_id:
        errors.append(f"exactly one beat must lead, and it must be the headline {head.contribution_id}")
    if plan.lead_contribution_id != head.contribution_id:
        errors.append(f"lead_contribution_id must be the headline {head.contribution_id}")
    flaws = [b for b in plan.beats if b.kind == "flaw"]
    for b in flaws:
        c = facts.contribution(b.contribution_id)
        if c.team_id != out.conceding_team_id or c.effect <= 0:
            errors.append(f"beat {b.beat_id}: {c.contribution_id} is not a conceding-side failure")
    if plan.flaw_contribution_id is not None and plan.flaw_contribution_id not in {b.contribution_id for b in flaws}:
        errors.append(f"flaw_contribution_id {plan.flaw_contribution_id} is not told as a flaw")
    for b in plan.beats:
        if b.kind == "punish":
            c = facts.contribution(b.contribution_id)
            if head.role != "primary_cause" or c.team_id != out.beneficiary_team_id or c.effect <= 0:
                errors.append(f"beat {b.beat_id}: a punish beat follows a defensive-cause headline with an attacking act")
        if b.kind == "lead" and b.contribution_id != head.contribution_id:
            errors.append(f"beat {b.beat_id}: only the headline is told as the lead")
        if b.kind == "context" and not facts.context_fact(b.context_fact_id).deviates:
            errors.append(f"beat {b.beat_id}: context is told only where the moment deviates")

    order = {b.beat_id: i for i, b in enumerate(plan.beats)}
    lead_at = order[leads[0].beat_id] if leads else 0
    if out.realized and head.role != "primary_cause":
        late = [b.beat_id for b in plan.beats if b.kind in ("flaw", "link", "context") and order[b.beat_id] < lead_at]
        if late:
            errors.append(f"the attack leads a realized story: beats {late} come before the lead")
    outcomes = [b for b in plan.beats if b.kind == "outcome"]
    if len(outcomes) != 1:
        errors.append("exactly one outcome beat")
    elif order[outcomes[0].beat_id] < lead_at:
        errors.append("the outcome comes after the lead")
    else:
        early = [b.beat_id for b in plan.beats if b.kind == "counterfactual" and order[b.beat_id] < order[outcomes[0].beat_id]]
        if early:
            errors.append(f"counterfactual beats {early} come after the outcome")
    return errors
