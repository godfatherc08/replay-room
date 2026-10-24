"""Match-context contract: how this moment compares with the rest of the match.

``MatchContext`` is the output of ``replay_room.context.match_context`` (the
``match_context`` tool): a few per-match **baselines** for the defending team,
each with the value **here** (in this moment), whether it deviates, and how
much data the baseline rests on. It is computed, never inferred, and it is a
separate contract from the ``CausalAccount``: context is a supporting beat,
not a cause the engine attributed.

* A fact exists only when the match holds enough data for its baseline
  (``sample_size`` at least the fact's minimum); otherwise the kind is listed
  in ``insufficient`` with the reason, and no baseline is given.
* ``confidence`` grades the sample size (``low`` / ``medium`` / ``high``).
* Every fact cites the records its "here" value was read from (frames of the
  moment window; the lost ball's event for the counter-press).
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from replay_room.contracts.refs import EvidenceRef, _Model

CONTEXT_VERSION = "1"

ContextKind = Literal[
    "counter_press",  # share of lost balls the team won back within the window, vs this loss
    "line_height",  # metres from its own goal line to its deepest outfield player, ball in its defensive third
    "marking_distance",  # mean metres from each attacker in its defensive third to the nearest defender
]


class ContextFact(_Model):
    fact_id: str  # "ctx-<kind>"
    kind: ContextKind
    team_id: str  # the team the baseline describes (the moment's defending team)
    unit: Literal["m", "s", "share"]
    baseline: float  # the match's typical value (median; a share for counter_press)
    here: float  # the value in this moment
    spread: tuple[float, float] | None = None  # the match's interquartile range, when a spread applies
    deviates: bool
    direction: Literal["higher", "lower", "same"]  # here vs the baseline
    sample_size: int  # independent samples behind the baseline (lost balls, defending spells)
    confidence: Literal["low", "medium", "high"]
    metrics: dict[str, float] = Field(default_factory=dict)
    evidence: tuple[EvidenceRef, ...] = Field(min_length=1)


class MatchContext(_Model):
    context_version: Literal["1"] = CONTEXT_VERSION
    game_id: str
    moment_id: str
    team_id: str  # the defending team
    facts: tuple[ContextFact, ...] = ()
    insufficient: tuple[tuple[str, str], ...] = ()  # (kind, why no baseline was computed)
