"""Framing-plan contract: the Analyst's ordered selection of computed facts.

A ``FramingPlan`` decides how a moment is *told*: which facts appear, in what
order, and with what emphasis. It never says anything new: every beat points
at a record that a tool returned (a contribution or link of the
``CausalAccount``, a fact of the ``MatchContext``, the account's outcome or a
counterfactual), by id. ``agents.critic.check_plan`` rejects any beat that does
not resolve, or a plan that breaks the framing rules (the account's headline
leads; a realized story leads with the attack and only then points at the
defensive flaw; context only where it deviates).

Beat kinds:

* ``build_up``: a contribution on the way to the chance;
* ``lead``: the account's headline contribution;
* ``flaw``: the conceding side's failure the story points at (the account's
  supporting contribution, or its headline when that is the defensive cause);
* ``punish``: the attacking act that punished a defensive-cause headline;
* ``link``: a computed off-ball link (``CausalAccount.links``);
* ``context``: a match-context fact that deviates (``MatchContext.facts``);
* ``outcome``: the terminal action and why it was a chance;
* ``counterfactual``: the better option that existed.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from replay_room.contracts.refs import _Model

PLAN_VERSION = "1"

BeatKind = Literal["build_up", "lead", "flaw", "punish", "link", "context", "outcome", "counterfactual"]


class Beat(_Model):
    beat_id: str
    kind: BeatKind
    emphasis: Literal["lead", "support", "detail"] = "detail"
    contribution_id: str | None = None  # build_up / lead / flaw / punish / counterfactual (the choice compared)
    link_id: str | None = None  # link; or a flaw told through its own link
    context_fact_id: str | None = None  # context


class FramingPlan(_Model):
    plan_version: Literal["1"] = PLAN_VERSION
    account_id: str
    moment_id: str
    source: Literal["rules", "foundry"]
    model: str | None = None  # the deployment that planned it (foundry source only)
    lead_contribution_id: str  # the account's headline
    flaw_contribution_id: str | None = None  # the defensive flaw the story points at
    beats: tuple[Beat, ...] = Field(min_length=2)
