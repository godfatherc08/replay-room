"""Moment contract: a talking point and the exact context later stages reason over.

A ``Moment`` is produced by Build 2 (detect) and consumed by Builds 3, 4 and 5,
and it is embedded in every ``CausalAccount``. It is serialisable and small: it
*references* actions and frames by id. ``MomentContext`` is the in-memory
bundle that carries the referenced rows themselves (the chain's SPADL actions
and the window's tracking rows).

**Explained vs flagged.** A moment class belongs to the attribution engine iff
its "why" is a question about scoring probability over space and actions:

* ``EXPLAINED_CLASSES`` (``engine_eligible=True``): goal, turnover_to_shot,
  big_chance_saved, penalty. Every one reduces to the same shape (chain +
  window + key event + ``outcome_ref``), and Build 4 attributes over the value
  of ``outcome_ref``, never over a hard-coded "goal = 1".
* ``FLAGGED_CLASSES`` (``engine_eligible=False``): offside, var_decision,
  injury, substitution. Their "why" is rules, discipline or officiating, so
  they are surfaced as talking points and get **no causal account**. They have
  no chain and no outcome; offside keeps a tracking window so it can be shown.

Red cards are not a moment class (MVP).

The unit of an explained moment is the **possession chain + tracking window**:

* ``chain``: the move, in order, from the action that started it (a regain, a
  kickoff or a set piece) to the key event. Brief opponent touches that never
  became control (e.g. an interception immediately tackled back) stay inside the
  chain and are listed in ``contested_action_ids``.
* ``turnover_event_ref``: when the move began with a regain, the opponent's
  action that lost the ball (not itself part of the chain).
* ``window``: a contiguous frame range in one period covering the run-up to the
  key event and its immediate aftermath.
* ``outcome_ref``: the terminal action whose value defines the outcome. It is
  the key event for every class except ``penalty``, whose key event is the
  foul that won it and whose outcome is the penalty kick.
* ``outcome_scored``: the realised result of the terminal action. It differs
  from the terminal value by design for ``big_chance_saved`` (high xG, no goal).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Literal

import pandas as pd
from pydantic import Field, model_validator

from replay_room.contracts.refs import ContextRef, EventRef, _Model

MomentClass = Literal[
    # explained: the attribution engine runs on these
    "goal",
    "turnover_to_shot",
    "big_chance_saved",
    "penalty",
    # flagged: detected and surfaced, never explained
    "offside",
    "var_decision",
    "injury",
    "substitution",
]
EXPLAINED_CLASSES: tuple[MomentClass, ...] = ("goal", "turnover_to_shot", "big_chance_saved", "penalty")
FLAGGED_CLASSES: tuple[MomentClass, ...] = ("offside", "var_decision", "injury", "substitution")
ChainStart = Literal["regain", "kickoff", "set_piece", "period_start", "truncated"]
KeyRef = Annotated[EventRef | ContextRef, Field(discriminator="kind")]


class TrackingWindow(_Model):
    period_id: int
    frame_start: int  # inclusive
    frame_end: int  # inclusive
    t_start: float
    t_end: float

    @model_validator(mode="after")
    def _ordered(self) -> TrackingWindow:
        if self.frame_start > self.frame_end or self.t_start > self.t_end:
            raise ValueError("window bounds out of order")
        return self

    @property
    def n_frames(self) -> int:
        return self.frame_end - self.frame_start + 1


class Moment(_Model):
    moment_id: str
    type: MomentClass
    engine_eligible: bool  # True exactly for EXPLAINED_CLASSES: Build 4 runs only on these
    game_id: str
    period_id: int
    t_event: float
    # Explained: credited with the moment (the scoring team, also for own goals) and its opponent.
    # Flagged: set only where the class has an attacking side (offside).
    attacking_team_id: str | None
    defending_team_id: str | None
    team_id: str | None = None  # flagged moments: the team concerned (offside, substitution, injury)
    key_event_ref: KeyRef  # explained: the goal / shot / penalty-winning foul; flagged: the incident
    key_player_id: str | None
    detail: str | None = None  # flagged moments: the feed's label for the incident (e.g. the VAR outcome)
    is_own_goal: bool = False
    # Explained classes only (empty / None when flagged).
    outcome_ref: EventRef | None = None
    outcome_scored: bool | None = None
    outcome_xg: float | None = None  # xG of outcome_ref at detection (None if it is not a shot)
    secondary_types: tuple[MomentClass, ...] = ()  # other explained classes this terminal action also qualified as
    possession_id: int | None = None
    chain: tuple[EventRef, ...] = ()
    chain_start: ChainStart | None = None
    turnover_event_ref: EventRef | None = None
    contested_action_ids: tuple[int, ...] = ()
    t_start: float  # earliest of chain start and window start (t_event when there is neither)
    t_end: float  # window end (t_event when there is no window)
    window: TrackingWindow | None = None

    @model_validator(mode="after")
    def _consistent(self) -> Moment:
        if self.engine_eligible != (self.type in EXPLAINED_CLASSES):
            raise ValueError("engine_eligible must be True exactly for explained classes")
        if self.window is not None and self.window.period_id != self.period_id:
            raise ValueError("window must lie in the moment's period")
        if self.key_event_ref.period_id != self.period_id:
            raise ValueError("key event must lie in the moment's period")
        if not self.t_start <= self.t_event <= self.t_end:
            raise ValueError("t_event must lie within the moment's time bounds")
        if (self.attacking_team_id is None) != (self.defending_team_id is None):
            raise ValueError("attacking and defending team are given together")
        if self.attacking_team_id is not None and self.attacking_team_id == self.defending_team_id:
            raise ValueError("attacking and defending team must differ")
        if self.engine_eligible:
            self._check_explained()
        else:
            self._check_flagged()
        return self

    def _check_explained(self) -> None:
        if self.attacking_team_id is None or self.key_player_id is None:
            raise ValueError("an explained moment has an attacking team and a key player")
        if not isinstance(self.key_event_ref, EventRef):
            raise ValueError("an explained moment's key event is an on-ball action")
        if not self.chain or self.window is None or self.possession_id is None or self.chain_start is None:
            raise ValueError("an explained moment has a chain, a window, a possession and a chain start")
        ids = [ref.action_id for ref in self.chain]
        if ids != sorted(set(ids)):
            raise ValueError("chain must be strictly ordered by action_id")
        if self.chain[-1] != self.key_event_ref:
            raise ValueError("chain must end at the key event")
        if any(ref.period_id != self.period_id for ref in self.chain):
            raise ValueError("chain must lie in the moment's period")
        if not set(self.contested_action_ids) <= set(ids):
            raise ValueError("contested actions must be part of the chain")
        if self.turnover_event_ref is not None and self.turnover_event_ref.action_id >= ids[0]:
            raise ValueError("turnover event must precede the chain")
        if (self.chain_start == "regain") != (self.turnover_event_ref is not None):
            raise ValueError("a turnover event is given exactly when the chain starts with a regain")
        out = self.outcome_ref
        if out is None or self.outcome_scored is None:
            raise ValueError("an explained moment has an outcome action and a realised outcome")
        if out.period_id != self.period_id or out.action_id < self.key_event_ref.action_id:
            raise ValueError("the outcome action is the key event or follows it in the same period")
        if out != self.key_event_ref and self.type != "penalty":
            raise ValueError("the outcome action is the key event (only a penalty's follows it: the kick after the foul)")
        if self.type == "goal" and not self.outcome_scored:
            raise ValueError("a goal moment's outcome is a goal")
        if self.type == "big_chance_saved" and self.outcome_scored:
            raise ValueError("a big chance saved did not score")
        if self.type in self.secondary_types or not set(self.secondary_types) <= set(EXPLAINED_CLASSES):
            raise ValueError("secondary types are other explained classes")

    def _check_flagged(self) -> None:
        explained_only = (self.outcome_ref, self.outcome_scored, self.outcome_xg, self.possession_id,
                          self.chain_start, self.turnover_event_ref)
        if self.chain or self.contested_action_ids or self.secondary_types or self.is_own_goal \
                or any(v is not None for v in explained_only):
            raise ValueError("a flagged moment carries no chain, outcome or attribution fields")

    @property
    def chain_action_ids(self) -> tuple[int, ...]:
        return tuple(ref.action_id for ref in self.chain)


@dataclass(frozen=True)
class MomentContext:
    """A moment plus the rows it references (not serialised)."""

    moment: Moment
    chain_actions: pd.DataFrame  # SPADL rows of the chain, in order (empty for flagged moments)
    frames: pd.DataFrame  # tracking-table rows in the window (all objects, all frames; empty without a window)
