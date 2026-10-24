"""Analyst: assembles the framing plan for an engine-eligible moment. Chooses, orders, emphasizes; never authors.

The Analyst works from two tool outputs, ``attribute`` (the causal account)
and ``match_context``, and returns a ``FramingPlan``: an ordered selection of
the facts they returned, each by id. It leads with the attacking move and
points at the defensive flaw and the context deviation as supporting beats.

* ``mode="foundry"``: a Foundry model on Microsoft Agent Framework proposes the
  plan (structured output ``PlanProposal``). With ``use_mcp`` it is handed the
  engine's MCP server as its tools and fetches the account and context itself;
  otherwise the facts are given inline. Every proposal goes to the Critic
  (``framing.check_plan``); a rejected one is re-proposed with the violations,
  up to ``MAX_ATTEMPTS``, then the rule plan is used.
* ``mode="rules"``: ``framing.rules_plan``, no model.

The model can only pick ids; a beat naming a fact no tool returned (an
invented contribution, a link the engine did not compute) does not resolve
and the Critic rejects the plan.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import Field

from replay_room.contracts.causal_account import CausalAccount
from replay_room.contracts.context import MatchContext
from replay_room.contracts.plan import BeatKind, FramingPlan
from replay_room.contracts.refs import _Model
from replay_room.explain.foundry import FoundryConfig, FoundryUnavailable, foundry_client, run_structured
from replay_room.framing import check_plan, rules_plan

MAX_ATTEMPTS = 3

ANALYST_PROMPT = """\
You are the Analyst of a football match-analysis system. A deterministic engine has computed a
moment's causal account (ranked facts, each with an id) and its match context (baselines for the
defending team and whether this moment deviates). You decide how the moment is TOLD: which facts,
in which order, with what emphasis. You never add a fact, a cause or a link.

Rules, all mandatory:
1. Use only ids the tools returned: contribution_id, link_id, context fact_id. Never make one up.
2. The account's headline is the lead (exactly one beat with emphasis "lead"); set
   lead_contribution_id to it.
3. Lead with the attacking move. In a realized moment the lead beat comes before every flaw, link
   and context beat: the story then points at the defensive flaw as a supporting beat. In a
   prevented moment the denial (the headline) comes after the build-up and the flaw.
4. A "flaw" beat must be a defending-team contribution with a positive effect (it helped the
   attack). Set flaw_contribution_id to the flaw you tell, if any. A flaw beat may carry the
   link_id of a link about that same defender.
5. A "context" beat only for a context fact that deviates.
6. Exactly one "outcome" beat (no ids), after the lead; "counterfactual" beats (contribution_id of
   the choice) after the outcome.
7. Tell each fact at most once. Select: leave out small touches that do not move the story.
Return only the JSON object required by the schema.
"""


class ProposedBeat(_Model):
    kind: BeatKind
    emphasis: Literal["lead", "support", "detail"]
    contribution_id: str | None
    link_id: str | None
    context_fact_id: str | None


class PlanProposal(_Model):
    lead_contribution_id: str
    flaw_contribution_id: str | None
    beats: list[ProposedBeat] = Field(min_length=2)


def analyst_brief(account: CausalAccount, context: MatchContext | None) -> dict[str, Any]:
    names = {p.player_id: p.name for p in account.participants}
    teams = {t.team_id: t.name for t in account.teams}
    out = account.outcome
    return {
        "moment": {"moment_id": account.moment.moment_id, "type": account.moment.type,
                   "framing": "realized" if out.realized else "prevented", "scored": out.scored,
                   "attacking_team": teams[out.beneficiary_team_id], "defending_team": teams[out.conceding_team_id]},
        "headline_contribution_id": account.headline_contribution_id,
        "supporting_contribution_id": account.supporting_contribution_id,
        "contributions": [{"contribution_id": c.contribution_id, "rank": c.rank, "role": c.role, "kind": c.kind,
                           "label": c.action or c.signal, "player": names.get(c.player_id),
                           "side": "attacking" if c.team_id == out.beneficiary_team_id else "defending",
                           "effect": round(c.effect, 3), "t": round(c.t, 1)} for c in account.contributions],
        "links": [{"link_id": k.link_id, "kind": k.kind, "defender_contribution_id": k.defender_contribution_id,
                   "runner": names.get(k.runner_id) if k.runner_id else None, "zone": k.zone}
                  for k in account.links],
        "context": [{"fact_id": f.fact_id, "kind": f.kind, "deviates": f.deviates, "direction": f.direction,
                     "confidence": f.confidence} for f in (context.facts if context else ())],
        "counterfactuals": [cf.contribution_id for cf in account.counterfactuals],
        "rule_plan": [b.model_dump(exclude={"beat_id"}) for b in rules_plan(account, context).beats],
    }


def to_plan(proposal: dict[str, Any] | PlanProposal, account: CausalAccount, model: str | None) -> FramingPlan:
    p = proposal if isinstance(proposal, PlanProposal) else PlanProposal.model_validate(proposal)
    beats = [{"beat_id": f"b{i + 1}", **b.model_dump()} for i, b in enumerate(p.beats)]
    return FramingPlan(account_id=account.account_id, moment_id=account.moment.moment_id, source="foundry",
                       model=model, lead_contribution_id=p.lead_contribution_id,
                       flaw_contribution_id=p.flaw_contribution_id, beats=beats)


Proposer = Callable[[CausalAccount, MatchContext | None, Sequence[str]], dict[str, Any]]


@dataclass
class AnalystReport:
    source: str
    attempts: int = 0
    rejections: list[list[str]] = field(default_factory=list)
    fallback_reason: str | None = None


def foundry_proposer(config: FoundryConfig, use_mcp: bool = True, client: Any | None = None) -> Proposer:
    """An Agent Framework agent on Foundry that proposes a plan; with ``use_mcp`` it calls the engine's MCP tools."""
    chat = client or foundry_client(config)

    def propose(account: CausalAccount, context: MatchContext | None, feedback: Sequence[str]) -> dict[str, Any]:
        if use_mcp:
            from agent_framework import MCPStdioTool

            tools = [MCPStdioTool(name="replay_room_engine", command=sys.executable,
                                  args=["-m", "replay_room.mcp_server"], allowed_tools=["attribute", "match_context"],
                                  load_prompts=False)]
            message = (f"Plan how to tell moment {account.moment.moment_id}. Call attribute and match_context for it "
                       f"first, then return the plan.")
        else:
            tools = None
            message = "Plan how to tell this moment.\n\nFACTS:\n" + json.dumps(analyst_brief(account, context), indent=1)
        if feedback:
            message += ("\n\nYour previous plan was REJECTED by the Critic for these reasons. Fix every one:\n- "
                        + "\n- ".join(feedback))
        return run_structured(chat, "Analyst", ANALYST_PROMPT, message, PlanProposal, config.temperature,
                              tools=tools)

    return propose


class Analyst:
    def __init__(self, mode: Literal["foundry", "rules"] = "foundry", proposer: Proposer | None = None,
                 use_mcp: bool = True):
        self.mode = mode
        self.proposer = proposer
        self.use_mcp = use_mcp
        self.model: str | None = None

    def plan(self, account: CausalAccount, context: MatchContext | None = None) -> tuple[FramingPlan, AnalystReport]:
        floor = rules_plan(account, context)
        if self.mode == "rules":
            return floor, AnalystReport(source="rules")
        proposer = self.proposer
        if proposer is None:
            try:
                config = FoundryConfig.from_env()
                proposer = foundry_proposer(config, self.use_mcp)
                self.model = config.deployment
            except FoundryUnavailable as e:
                return floor, AnalystReport(source="rules", fallback_reason=str(e))
        report = AnalystReport(source="foundry")
        feedback: list[str] = []
        for attempt in range(1, MAX_ATTEMPTS + 1):
            report.attempts = attempt
            try:
                plan = to_plan(proposer(account, context, feedback), account, self.model)
            except Exception as e:  # network, auth, a malformed proposal: all mean "use the floor"
                report.source, report.fallback_reason = "rules", f"Analyst model failed: {type(e).__name__}: {e}"
                return floor, report
            errors = check_plan(plan, account, context)
            if not errors:
                return plan, report
            report.rejections.append(errors)
            feedback = errors
        report.source = "rules"
        report.fallback_reason = f"no model plan passed the Critic in {MAX_ATTEMPTS} attempts"
        return floor, report
