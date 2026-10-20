"""Draft causal-account contract (schema v0.1).

The causal account is the single contract between the deterministic core
(stage 4 produces it) and everything downstream (stages 5, 6 and 7 consume it).
Only the types live here; nothing in Build 1 produces accounts.

Invariants enforced on construction:

* every contribution carries at least one evidence reference, and that
  reference matches its track (``on_ball`` -> event, ``off_ball`` -> frame);
* contributions are ranked 1..n with no gaps, ordered by rank;
* the headline names an existing contribution;
* every counterfactual points at an existing on-ball contribution.

The JSON Schema export lives at ``data/schema/causal_account.schema.json`` and
is regenerated with ``python -m replay_room.contracts``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "0.1"


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class EventRef(_Model):
    """Points at one on-ball SPADL action."""

    kind: Literal["event"] = "event"
    action_id: int
    original_event_id: str
    time_seconds: float


class FrameRef(_Model):
    """Points at one tracking frame, optionally naming the players that matter in it."""

    kind: Literal["frame"] = "frame"
    frame_id: int
    timestamp: float
    player_ids: tuple[str, ...] = ()


EvidenceRef = Annotated[EventRef | FrameRef, Field(discriminator="kind")]


class TrackingWindow(_Model):
    frame_start: int
    frame_end: int
    t_start: float
    t_end: float


class Moment(_Model):
    moment_id: str
    moment_type: Literal["goal"]  # MVP: goals only
    period_id: int
    t_event: float
    team_id: str  # the team credited with the moment (scoring team for a goal)
    key_action_id: int  # the shot (or own-goal action) that defines the moment
    key_player_id: str
    chain_action_ids: tuple[int, ...]  # the possession chain, in order, ending at key_action_id
    window: TrackingWindow


ContributionKind = Literal[
    # on-ball track
    "action_value",  # VAEP / delta-xT of an action
    # off-ball track
    "space_creation",  # pitch-control / space-value gained by a movement
    "space_conceded",  # pitch-control / space-value given up by a defender
    "marking_break",  # a marking assignment that was lost
]


class Contribution(_Model):
    """One evidence-bound causal fact, kept because its effect cleared the threshold."""

    contribution_id: str
    rank: int = Field(ge=1)
    track: Literal["on_ball", "off_ball"]
    kind: ContributionKind
    player_id: str
    team_id: str
    t: float
    effect: float  # marginal change in P(goal) for the moment's team; signed
    metrics: dict[str, float] = Field(default_factory=dict)  # e.g. vaep, delta_xt, pitch_control_delta
    shapley_share: float | None = None
    evidence: tuple[EvidenceRef, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _evidence_matches_track(self) -> Contribution:
        wanted = "event" if self.track == "on_ball" else "frame"
        if not any(ref.kind == wanted for ref in self.evidence):
            raise ValueError(f"{self.track} contribution {self.contribution_id} needs a {wanted} reference")
        return self


class Alternative(_Model):
    """An option that was actually available, valued from the real positions."""

    description: str  # machine-generated label, e.g. "pass to HOM-07"
    target_player_id: str | None = None
    value: float
    evidence: tuple[EvidenceRef, ...] = Field(min_length=1)


class Counterfactual(_Model):
    contribution_id: str  # the on-ball contribution whose choice is being compared
    chosen_value: float
    alternatives: tuple[Alternative, ...] = Field(min_length=1)

    @property
    def best_gap(self) -> float:
        return max(a.value for a in self.alternatives) - self.chosen_value


class Provenance(_Model):
    pipeline_version: str
    source: str  # adapter that produced the input match
    models: dict[str, str] = Field(default_factory=dict)  # metric -> model/version
    effect_threshold: float
    generated_at: str  # ISO-8601


class CausalAccount(_Model):
    schema_version: Literal["0.1"] = SCHEMA_VERSION
    account_id: str
    game_id: str
    moment: Moment
    headline_contribution_id: str
    contributions: tuple[Contribution, ...] = Field(min_length=1)
    counterfactuals: tuple[Counterfactual, ...] = ()
    provenance: Provenance

    @model_validator(mode="after")
    def _check_integrity(self) -> CausalAccount:
        ranks = [c.rank for c in self.contributions]
        if ranks != list(range(1, len(ranks) + 1)):
            raise ValueError(f"contributions must be ordered by rank 1..n, got {ranks}")
        ids = {c.contribution_id for c in self.contributions}
        if len(ids) != len(self.contributions):
            raise ValueError("duplicate contribution_id")
        if self.headline_contribution_id not in ids:
            raise ValueError(f"headline {self.headline_contribution_id!r} is not a contribution")
        on_ball = {c.contribution_id for c in self.contributions if c.track == "on_ball"}
        for cf in self.counterfactuals:
            if cf.contribution_id not in on_ball:
                raise ValueError(f"counterfactual targets unknown on-ball contribution {cf.contribution_id!r}")
        return self

    @property
    def headline(self) -> Contribution:
        return next(c for c in self.contributions if c.contribution_id == self.headline_contribution_id)


SCHEMA_PATH = Path(__file__).resolve().parents[3] / "data" / "schema" / "causal_account.schema.json"


def json_schema_text() -> str:
    return json.dumps(CausalAccount.model_json_schema(), indent=2, sort_keys=True) + "\n"
