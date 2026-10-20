"""Causal-account contract (schema v0.3), per REPLAY_ROOM_TECHNICAL_SPEC.md section 4.

The causal account is the single contract between the deterministic core
(stage 4 produces it) and everything downstream (stages 5, 6 and 7 consume it).
Only the types live here; nothing produces accounts until Build 4.

The account is **self-contained**: stage 6 may narrate only what is in it, so
every fact carries its own words (``role``, plus ``action`` for on-ball or
``signal`` for off-ball), and every player it mentions is in ``participants``.

Sign convention: ``effect`` is the marginal change in the *attacking* (scoring)
team's goal probability. A creator's pass and a defender's lapse both have a
positive effect; a defending player with a positive effect is a debit to the
defending team (the spec's "top negative for the conceding team"). Club-focus
views flip the sign; the account does not.

Invariants enforced on construction:

* every contribution carries an evidence reference matching its track
  (``on_ball`` -> event, ``off_ball`` -> frame) and its label
  (``action`` for on-ball, ``signal`` for off-ball);
* contributions are ranked 1..n with no gaps, by non-increasing ``|effect|``;
* the headline names an existing contribution and is the only one that may
  have role ``primary_cause``;
* every counterfactual points at an on-ball contribution, cites its decision
  frame, ranks alternatives best first, and beats the chosen option by at
  least ``provenance.counterfactual_margin``;
* every player referenced is a participant, on one of the moment's two teams.

Versions: v0.2 embedded the shared ``contracts.moment.Moment`` (Build 2) and
added ``period_id`` to event refs. v0.3 aligns with spec section 4: ``role``,
``action``/``signal``, absolute-effect ranking, a grounded counterfactual
(decision frame + margin), and ``teams``/``participants``.

The JSON Schema export lives at ``data/schema/causal_account.schema.json`` and
is regenerated with ``python -m replay_room.contracts``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from replay_room.contracts.moment import Moment
from replay_room.contracts.refs import EvidenceRef, FrameRef, _Model

SCHEMA_VERSION = "0.3"


ContributionKind = Literal[
    # on-ball track (spec 4, track A)
    "action_value",  # VAEP / delta-xT of an action
    # off-ball track (spec 4, track B)
    "space_creation",  # pitch-control / space-value gained by a movement
    "space_conceded",  # pitch-control / space-value given up by a defender
    "marking_break",  # a marking assignment that was lost
]
ContributionRole = Literal[
    "primary_cause",  # the headline cause
    "finish",  # the goal action itself
    "assist",  # the action that set up the finish
    "build_up",  # other positive on-ball contributions by the attacking team
    "space_creation",  # off-ball movement that opened valuable space
    "defensive_error",  # a defending player's action or positioning that helped the goal
]


class TeamInfo(_Model):
    team_id: str
    name: str


class Participant(_Model):
    player_id: str
    name: str
    team_id: str
    shirt_number: int | None = None
    position: str | None = None


class Contribution(_Model):
    """One evidence-bound causal fact, kept because its effect cleared the threshold.

    ``metrics`` holds the cited numbers, keyed by metric name: ``vaep``,
    ``delta_xt``, ``xg``, ``space_created``, ``space_conceded``,
    ``pitch_control_delta``, ...
    """

    contribution_id: str
    rank: int = Field(ge=1)
    track: Literal["on_ball", "off_ball"]
    kind: ContributionKind
    role: ContributionRole
    action: str | None = None  # on-ball: SPADL type or a refinement, e.g. "through_ball"
    signal: str | None = None  # off-ball: detected pattern, e.g. "run_in_behind", "stopped_tracking_runner"
    player_id: str
    team_id: str
    t: float
    effect: float  # marginal change in the attacking team's P(goal); see module docstring
    metrics: dict[str, float] = Field(default_factory=dict)
    shapley_share: float | None = None
    evidence: tuple[EvidenceRef, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _track_consistent(self) -> Contribution:
        wanted = "event" if self.track == "on_ball" else "frame"
        if not any(ref.kind == wanted for ref in self.evidence):
            raise ValueError(f"{self.track} contribution {self.contribution_id} needs a {wanted} reference")
        label, name = (self.action, "action") if self.track == "on_ball" else (self.signal, "signal")
        if not label:
            raise ValueError(f"{self.track} contribution {self.contribution_id} needs a {name} label")
        return self


class Alternative(_Model):
    """An option that was actually available at the decision frame, valued from the real positions."""

    description: str  # machine-generated label, e.g. "pass to HOM-07"
    target_player_id: str | None = None
    completion_prob: float | None = None  # e.g. physics-based pass model
    value: float  # expected value of taking this option (e.g. completion x receiving-location value)
    evidence: tuple[EvidenceRef, ...] = Field(min_length=1)


class Counterfactual(_Model):
    """'A better option existed'. Surfaced only when it beats the chosen action by the margin."""

    contribution_id: str  # the on-ball contribution whose choice is being compared
    decision_frame: FrameRef
    chosen: str  # label of the chosen action, e.g. "shot"
    chosen_value: float
    alternatives: tuple[Alternative, ...] = Field(min_length=1)  # ranked, best first

    @model_validator(mode="after")
    def _ranked(self) -> Counterfactual:
        values = [a.value for a in self.alternatives]
        if values != sorted(values, reverse=True):
            raise ValueError("alternatives must be ranked best first")
        return self

    @property
    def best(self) -> Alternative:
        return self.alternatives[0]

    @property
    def best_gap(self) -> float:
        return self.best.value - self.chosen_value


class Provenance(_Model):
    pipeline_version: str
    source: str  # adapter that produced the input match
    models: dict[str, str] = Field(default_factory=dict)  # metric -> model/version
    effect_threshold: float
    counterfactual_margin: float
    generated_at: str  # ISO-8601


class CausalAccount(_Model):
    schema_version: Literal["0.3"] = SCHEMA_VERSION
    account_id: str
    game_id: str
    moment: Moment
    teams: tuple[TeamInfo, TeamInfo]
    participants: tuple[Participant, ...] = Field(min_length=1)
    headline_contribution_id: str
    contributions: tuple[Contribution, ...] = Field(min_length=1)
    counterfactuals: tuple[Counterfactual, ...] = ()
    provenance: Provenance

    @model_validator(mode="after")
    def _check_integrity(self) -> CausalAccount:
        ranks = [c.rank for c in self.contributions]
        if ranks != list(range(1, len(ranks) + 1)):
            raise ValueError(f"contributions must be ordered by rank 1..n, got {ranks}")
        effects = [abs(c.effect) for c in self.contributions]
        if effects != sorted(effects, reverse=True):
            raise ValueError("contributions must be ranked by non-increasing |effect|")
        ids = {c.contribution_id for c in self.contributions}
        if len(ids) != len(self.contributions):
            raise ValueError("duplicate contribution_id")
        if self.headline_contribution_id not in ids:
            raise ValueError(f"headline {self.headline_contribution_id!r} is not a contribution")
        primary = [c.contribution_id for c in self.contributions if c.role == "primary_cause"]
        if primary and primary != [self.headline_contribution_id]:
            raise ValueError("only the headline contribution may have role primary_cause")
        on_ball = {c.contribution_id for c in self.contributions if c.track == "on_ball"}
        for cf in self.counterfactuals:
            if cf.contribution_id not in on_ball:
                raise ValueError(f"counterfactual targets unknown on-ball contribution {cf.contribution_id!r}")
            if cf.best_gap < self.provenance.counterfactual_margin:
                raise ValueError(f"counterfactual for {cf.contribution_id} is below the margin")
        team_ids = {t.team_id for t in self.teams}
        if team_ids != {self.moment.attacking_team_id, self.moment.defending_team_id}:
            raise ValueError("teams must be the moment's attacking and defending teams")
        players = {p.player_id for p in self.participants}
        mentioned = {c.player_id for c in self.contributions} | {self.moment.key_player_id}
        mentioned |= {a.target_player_id for cf in self.counterfactuals for a in cf.alternatives
                      if a.target_player_id}
        if not mentioned <= players:
            raise ValueError(f"players not in participants: {sorted(mentioned - players)}")
        if not {p.team_id for p in self.participants} <= team_ids:
            raise ValueError("participant on an unknown team")
        return self

    @property
    def headline(self) -> Contribution:
        return next(c for c in self.contributions if c.contribution_id == self.headline_contribution_id)

    def evidence_index(self) -> dict[str, list[int]]:
        """Every cited record (the spec's ``evidence`` block): action ids and frame ids, sorted."""
        refs = [r for c in self.contributions for r in c.evidence]
        for cf in self.counterfactuals:
            refs.append(cf.decision_frame)
            refs += [r for a in cf.alternatives for r in a.evidence]
        return {
            "events": sorted({r.action_id for r in refs if r.kind == "event"}),
            "frames": sorted({r.frame_id for r in refs if r.kind == "frame"}),
        }


SCHEMA_PATH = Path(__file__).resolve().parents[3] / "data" / "schema" / "causal_account.schema.json"


def json_schema_text() -> str:
    return json.dumps(CausalAccount.model_json_schema(), indent=2, sort_keys=True) + "\n"
