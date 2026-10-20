"""Possession segmentation over a SPADL action table (structural, no valuation).

A possession is a maximal run of actions during which one team keeps control.
Rules, applied in action order within each period:

1. **Control.** An action gives control to its team unless it is a non-control
   action: a foul or ``non_action``, a *failed* defensive attempt (tackle,
   interception, keeper action) since the defender never had the ball, or an
   own goal, which stays inside the attacking team's possession.
2. **Boundaries.** A new possession starts at the first action of a period
   (``period_start``), the first action after a goal (``kickoff``), any
   set-piece action, even for the same team (``set_piece``; the ball was dead),
   and any control action by the other team (``regain``).
3. **Contested touches.** A regain that never becomes control is not a change
   of possession: an opponent spell of at most ``FLEETING_MAX_ACTIONS`` actions,
   lasting at most ``FLEETING_MAX_SECONDS`` before the original team regains, and
   with no pass or shot *attempt* (attempting one means the player had the ball
   under control), is merged into the surrounding possession. Its actions are
   recorded as ``contested_action_ids``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

FLEETING_MAX_ACTIONS = 2
FLEETING_MAX_SECONDS = 3.0

SHOT_TYPES = frozenset({"shot", "shot_freekick", "shot_penalty"})
PASS_TYPES = frozenset({"pass", "cross"})
SET_PIECE_TYPES = frozenset({
    "throw_in", "freekick_crossed", "freekick_short", "corner_crossed", "corner_short",
    "goalkick", "shot_penalty", "shot_freekick",
})
NON_CONTROL_TYPES = frozenset({"foul", "non_action"})
DEFENSIVE_TYPES = frozenset({
    "tackle", "interception", "keeper_save", "keeper_claim", "keeper_punch", "keeper_pick_up",
})

StartType = Literal["period_start", "kickoff", "set_piece", "regain"]
EndType = Literal["goal", "turnover", "stoppage", "period_end"]


def is_goal(type_name: str, result_name: str) -> bool:
    """A goal is a successful shot of any kind, or any action resulting in an own goal."""
    return (type_name in SHOT_TYPES and result_name == "success") or result_name == "owngoal"


def control_team(type_name: str, result_name: str, team_id: str) -> str | None:
    """The team this action gives control to, or None if it does not change control."""
    if type_name in NON_CONTROL_TYPES or result_name == "owngoal":
        return None
    if type_name in DEFENSIVE_TYPES and result_name != "success":
        return None
    return team_id


@dataclass(frozen=True)
class Possession:
    possession_id: int
    period_id: int
    team_id: str
    action_ids: tuple[int, ...]
    start_type: StartType
    end_type: EndType
    t_start: float  # time of the first action
    t_end: float  # time of the last action
    contested_action_ids: tuple[int, ...] = ()


@dataclass
class _Seg:
    period_id: int
    team_id: str
    start_type: StartType
    ids: list[int]
    times: list[float]
    rows: list[tuple[str, str, str]]  # (team_id, type_name, result_name) per action
    contested: list[int] = field(default_factory=list)

    def absorb(self, other: _Seg, contested: bool = False) -> None:
        self.ids += other.ids
        self.times += other.times
        self.rows += other.rows
        self.contested += other.ids if contested else other.contested


def _is_fleeting(prev: _Seg, mid: _Seg, nxt: _Seg) -> bool:
    return (
        prev.period_id == mid.period_id == nxt.period_id
        and prev.team_id == nxt.team_id != mid.team_id
        and mid.start_type == "regain"
        and nxt.start_type == "regain"
        and len(mid.ids) <= FLEETING_MAX_ACTIONS
        and nxt.times[0] - mid.times[0] <= FLEETING_MAX_SECONDS
        and not any(t in PASS_TYPES or t in SHOT_TYPES or is_goal(t, r) for _, t, r in mid.rows)
    )


def segment_possessions(actions: pd.DataFrame) -> tuple[Possession, ...]:
    """Split a SPADL table into possessions. Pure: the input is not modified."""
    ordered = actions.sort_values(["period_id", "action_id"], kind="stable")
    segs: list[_Seg] = []
    prev_period: int | None = None
    after_goal = False
    for a in ordered.itertuples(index=False):
        control = control_team(a.type_name, a.result_name, a.team_id)
        start: StartType | None = None
        if a.period_id != prev_period:
            start = "period_start"
        elif after_goal:
            start = "kickoff"
        elif a.type_name in SET_PIECE_TYPES:
            start = "set_piece"
        elif control is not None and control != segs[-1].team_id:
            start = "regain"
        row = (a.team_id, a.type_name, a.result_name)
        if start is not None:
            team = control if control is not None else a.team_id
            segs.append(_Seg(int(a.period_id), team, start, [int(a.action_id)], [float(a.time_seconds)], [row]))
        else:
            seg = segs[-1]
            seg.ids.append(int(a.action_id))
            seg.times.append(float(a.time_seconds))
            seg.rows.append(row)
        after_goal = is_goal(a.type_name, a.result_name)
        prev_period = a.period_id

    i = 1
    while i < len(segs) - 1:
        if _is_fleeting(segs[i - 1], segs[i], segs[i + 1]):
            merged = segs[i - 1]
            merged.absorb(segs[i], contested=True)
            merged.absorb(segs[i + 1])
            del segs[i : i + 2]
            # stay at i: the merged possession may now precede another fleeting spell
        else:
            i += 1

    out = []
    for n, seg in enumerate(segs):
        nxt = segs[n + 1] if n + 1 < len(segs) else None
        last_team, last_type, last_result = seg.rows[-1]
        if is_goal(last_type, last_result):
            end: EndType = "goal"
        elif nxt is None or nxt.period_id != seg.period_id:
            end = "period_end"
        elif nxt.start_type == "regain":
            end = "turnover"
        else:
            end = "stoppage"
        out.append(Possession(
            possession_id=n, period_id=seg.period_id, team_id=seg.team_id,
            action_ids=tuple(seg.ids), start_type=seg.start_type, end_type=end,
            t_start=seg.times[0], t_end=seg.times[-1], contested_action_ids=tuple(seg.contested),
        ))
    return tuple(out)


def possession_index(possessions: tuple[Possession, ...]) -> pd.Series:
    """action_id -> possession_id, for joining possessions onto the SPADL table."""
    pairs = [(aid, p.possession_id) for p in possessions for aid in p.action_ids]
    return pd.Series(dict(pairs), name="possession_id").rename_axis("action_id").sort_index()
