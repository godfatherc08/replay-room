"""The rule-based framing plan: the Analyst's deterministic floor (and what a model plan is checked against).

From the account and its match context:

* **lead**: the account's headline;
* **flaw**: the conceding side's failure the story points at: the headline
  itself when it is the defensive cause (role ``primary_cause``; then the
  account's supporting act is the ``punish`` beat), else the account's
  supporting contribution when it is a conceding-side failure;
* **links**: every computed link (at most ``MAX_LINKS``, the flaw defender's
  first). The flaw defender's link is told *with* the flaw (one beat carrying
  both ids); the others get their own beats. The runner's run and the
  defender's fact that a link tells are not told again as build-up;
* **context**: match-context facts that deviate, most confident first (at most
  ``MAX_CONTEXT``);
* **build-up**: the remaining contributions, the ``MAX_BUILD_UP`` largest by
  ``|effect|``, told in time order. The finish is told by the outcome beat;
  an attacking setback smaller than ``SETBACK`` is left out (it does not move
  the story);
* **outcome**, then one **counterfactual** beat per counterfactual.

Order: a realized story is told in time order up to the outcome and then
points back at the flaw (build-up and lead by time, then punish, flaw, links,
context, outcome); a prevented story builds the chance, shows what let it
happen, then the denial (build-up, flaw, links, context, lead, outcome);
counterfactuals close both.
"""

from __future__ import annotations

from replay_room.contracts.causal_account import CausalAccount, Contribution
from replay_room.contracts.context import MatchContext
from replay_room.contracts.plan import Beat, FramingPlan

MAX_BUILD_UP = 5
MAX_LINKS = 2
MAX_CONTEXT = 2
SETBACK = 0.1  # an attacking action that cost less than this is not told
_CONFIDENCE = {"high": 0, "medium": 1, "low": 2}


def flaw_of(account: CausalAccount) -> tuple[Contribution | None, Contribution | None]:
    """(flaw, punish): the conceding side's failure the story points at, and the act that punished it."""
    out, head, support = account.outcome, account.headline, account.supporting
    if head.role == "primary_cause":
        return head, support
    if support is not None and support.team_id == out.conceding_team_id and support.effect > 0:
        return support, None
    return None, None


def _when(c: Contribution) -> tuple[float, int, int]:
    r = c.evidence[0]
    return (r.time_seconds, r.action_id, c.rank) if r.kind == "event" else (r.timestamp, 0, c.rank)


def rules_plan(account: CausalAccount, context: MatchContext | None = None) -> FramingPlan:
    head = account.headline
    flaw, punish = flaw_of(account)
    links = sorted(account.links, key=lambda k: (flaw is None or k.defender_contribution_id != flaw.contribution_id,
                                                 k.link_id))[:MAX_LINKS]
    facts = sorted((f for f in (context.facts if context else ()) if f.deviates),
                   key=lambda f: (_CONFIDENCE[f.confidence], f.fact_id))[:MAX_CONTEXT]

    told = {head.contribution_id} | {c.contribution_id for c in (flaw, punish) if c is not None}
    told |= {k.runner_contribution_id for k in links if k.runner_contribution_id}
    told |= {k.defender_contribution_id for k in links}
    oid = account.outcome.ref.action_id
    rest = [c for c in account.contributions if c.contribution_id not in told and c.kind != "chance_denied"
            and not (c.track == "on_ball" and c.evidence[0].action_id == oid)
            and not (c.team_id == account.outcome.beneficiary_team_id and -SETBACK < c.effect < 0)]
    build = sorted(sorted(rest, key=lambda c: (-abs(c.effect), c.rank))[:MAX_BUILD_UP], key=_when)

    lead = Beat(beat_id="", kind="lead", emphasis="lead", contribution_id=head.contribution_id)
    pointing = []
    if punish is not None:
        pointing.append(Beat(beat_id="", kind="punish", emphasis="support", contribution_id=punish.contribution_id))
    own = next((k for k in links if flaw is not None and k.defender_contribution_id == flaw.contribution_id), None)
    if flaw is not None and flaw is not head:
        pointing.append(Beat(beat_id="", kind="flaw", emphasis="support", contribution_id=flaw.contribution_id,
                             link_id=own.link_id if own else None))
    pointing += [Beat(beat_id="", kind="link", emphasis="support", link_id=k.link_id) for k in links if k is not own]
    pointing += [Beat(beat_id="", kind="context", emphasis="support", context_fact_id=f.fact_id) for f in facts]
    if head.role == "primary_cause":  # the defensive cause leads: it is the flaw
        lead = Beat(beat_id="", kind="flaw", emphasis="lead", contribution_id=head.contribution_id,
                    link_id=own.link_id if own else None)
    if account.outcome.realized:
        story = sorted([*build, head], key=_when)
        beats = [lead if c is head else Beat(beat_id="", kind="build_up", contribution_id=c.contribution_id)
                 for c in story] + pointing
    else:
        beats = [Beat(beat_id="", kind="build_up", contribution_id=c.contribution_id) for c in build]
        beats += [*pointing, lead]
    beats.append(Beat(beat_id="", kind="outcome", emphasis="support"))
    beats += [Beat(beat_id="", kind="counterfactual", emphasis="support", contribution_id=cf.contribution_id)
              for cf in account.counterfactuals]
    beats = [b.model_copy(update={"beat_id": f"b{i + 1}"}) for i, b in enumerate(beats)]
    return FramingPlan(account_id=account.account_id, moment_id=account.moment.moment_id, source="rules",
                       lead_contribution_id=head.contribution_id,
                       flaw_contribution_id=flaw.contribution_id if flaw is not None else None, beats=tuple(beats))
