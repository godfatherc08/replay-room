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

With the moment's account, it also carries the positional facts the deep
telling draws on (``context.positions``): each story player's position at the
story's frame against their average in that phase (confidence-graded, absent
when the sample is too thin), their distances to the ball, the nearest
opponent and the goal; the attacking team's pitch-control swing at the
shooting spot; and the marking assignments, held or broken.
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


class PlayerPosition(_Model):
    """Where a player was at a frame the story shows, against where they usually are in that phase of play."""

    player_id: str
    team_id: str
    frame_id: int
    timestamp: float
    x: float
    y: float
    phase: Literal["attacking", "defending"]  # the player's team in / out of possession in this moment
    average: tuple[float, float] | None = None  # mean position over the match frames in the same phase and third
    sample_frames: int = 0
    sample_spells: int = 0  # possessions those frames come from (frames are not independent)
    confidence: Literal["low", "medium", "high"] | None = None  # None: too few spells, no average given
    deviation_m: float | None = None  # distance from the average
    forward_m: float | None = None  # + = further up the pitch (towards the goal the player's team attacks)
    lateral_m: float | None = None  # + = towards the player's left
    to_ball_m: float
    to_opponent_m: float  # to the nearest opponent
    nearest_opponent_id: str
    to_goal_m: float  # to the centre of the goal under attack in this moment


class ControlSwing(_Model):
    """The attacking team's pitch control at the shooting spot, from one frame to another."""

    label: str  # what the span is: the beat it belongs to
    team_id: str
    zone: str | None = None
    frame_from: int
    frame_to: int
    seconds: float
    control_from: float  # 0..1
    control_to: float


class Marking(_Model):
    """A marking assignment over a span: the nearest-attacker rule at its start, and whether it held."""

    defender_id: str
    man_id: str
    frame_from: int
    frame_to: int
    separation_from: float
    separation_to: float
    held: bool  # False: the separation grew by MARK_GAIN_M or more


class MatchContext(_Model):
    context_version: Literal["1"] = CONTEXT_VERSION
    game_id: str
    moment_id: str
    team_id: str  # the defending team
    facts: tuple[ContextFact, ...] = ()
    insufficient: tuple[tuple[str, str], ...] = ()  # (kind, why no baseline was computed)
    positions: tuple[PlayerPosition, ...] = ()  # the story's players at the story's frames
    swings: tuple[ControlSwing, ...] = ()
    markings: tuple[Marking, ...] = ()
