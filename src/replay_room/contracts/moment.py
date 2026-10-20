"""Moment contract: a talking point and the exact context later stages reason over.

A ``Moment`` is produced by Build 2 (detect) and consumed by Builds 3, 4 and 5,
and it is embedded in every ``CausalAccount``. It is serialisable and small: it
*references* actions and frames by id. ``MomentContext`` is the in-memory
bundle that carries the referenced rows themselves (the chain's SPADL actions
and the window's tracking rows).

The unit is the **possession chain + tracking window**, not the goal event:

* ``chain``: the move, in order, from the action that started it (a regain, a
  kickoff or a set piece) to the key event. Brief opponent touches that never
  became control (e.g. an interception immediately tackled back) stay inside the
  chain and are listed in ``contested_action_ids``.
* ``turnover_event_ref``: when the move began with a regain, the opponent's
  action that lost the ball (not itself part of the chain).
* ``window``: a contiguous frame range in one period covering the run-up to the
  key event and the ball reaching the goal.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd
from pydantic import Field, model_validator

from replay_room.contracts.refs import EventRef, _Model

MomentType = Literal["goal"]  # MVP: goals only; widen this Literal to add moment classes
ChainStart = Literal["regain", "kickoff", "set_piece", "period_start", "truncated"]


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
    type: MomentType
    game_id: str
    period_id: int
    t_event: float
    attacking_team_id: str  # credited with the moment (the scoring team, also for own goals)
    defending_team_id: str
    key_event_ref: EventRef  # the goal action (shot, or the own-goal action)
    key_player_id: str
    is_own_goal: bool = False
    possession_id: int
    chain: tuple[EventRef, ...] = Field(min_length=1)
    chain_start: ChainStart
    turnover_event_ref: EventRef | None = None
    contested_action_ids: tuple[int, ...] = ()
    t_start: float  # earliest of chain start and window start
    t_end: float  # window end
    window: TrackingWindow

    @model_validator(mode="after")
    def _consistent(self) -> Moment:
        ids = [ref.action_id for ref in self.chain]
        if ids != sorted(set(ids)):
            raise ValueError("chain must be strictly ordered by action_id")
        if self.chain[-1] != self.key_event_ref:
            raise ValueError("chain must end at the key event")
        if any(ref.period_id != self.period_id for ref in self.chain) or self.window.period_id != self.period_id:
            raise ValueError("chain and window must lie in the moment's period")
        if not set(self.contested_action_ids) <= set(ids):
            raise ValueError("contested actions must be part of the chain")
        if self.turnover_event_ref is not None and self.turnover_event_ref.action_id >= ids[0]:
            raise ValueError("turnover event must precede the chain")
        if (self.chain_start == "regain") != (self.turnover_event_ref is not None):
            raise ValueError("a turnover event is given exactly when the chain starts with a regain")
        if not self.t_start <= self.t_event <= self.t_end:
            raise ValueError("t_event must lie within the moment's time bounds")
        if self.attacking_team_id == self.defending_team_id:
            raise ValueError("attacking and defending team must differ")
        return self

    @property
    def chain_action_ids(self) -> tuple[int, ...]:
        return tuple(ref.action_id for ref in self.chain)


@dataclass(frozen=True)
class MomentContext:
    """A moment plus the rows it references (not serialised)."""

    moment: Moment
    chain_actions: pd.DataFrame  # SPADL rows of the chain, in order
    frames: pd.DataFrame  # tracking-table rows in the window (all objects, all frames)
