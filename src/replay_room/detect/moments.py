"""Goal-moment detection, and the chain + window builder every explained class shares.

``detect_goal_moments(actions, tracking)`` is a pure function of the SPADL table
and the tracking table, so it behaves identically on a fixture and on a real
feed. ``StreamingGoalDetector`` wraps it for the replay clock: it buffers what
the stream has delivered and runs the same function once a goal's window has
fully arrived, so streaming and batch produce identical moments.

The chain is the scoring possession (see ``possessions``), which already runs
back to the regain or restart that started the move, capped at
``CHAIN_MAX_ACTIONS`` / ``CHAIN_MAX_SECONDS``. The window covers the run-up:
it starts ``WINDOW_LEAD`` before the chain, clamped to between
``WINDOW_BEFORE_MIN`` and ``WINDOW_BEFORE_MAX`` before the goal and to the
period start, and ends ``WINDOW_AFTER`` after the goal so the ball's flight
into the net is included. The other explained classes (``detect.explained``)
build their moments with the same ``chain_moment``, keyed on their own action.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd

from replay_room.contracts.moment import Moment, MomentClass, MomentContext, TrackingWindow
from replay_room.contracts.pitch import BALL_ID
from replay_room.contracts.refs import EventRef
from replay_room.contracts.spadl import SPADL_COLUMNS
from replay_room.contracts.tracking import TRACKING_COLUMNS, TrackingFrame
from replay_room.detect.possessions import Possession, is_goal, segment_possessions

CHAIN_MAX_ACTIONS = 25
CHAIN_MAX_SECONDS = 30.0
WINDOW_BEFORE_MIN = 10.0
WINDOW_BEFORE_MAX = 15.0
WINDOW_LEAD = 1.0
WINDOW_AFTER = 2.0
_EPS = 1e-6


def _ref(row: Any) -> EventRef:
    return EventRef(
        action_id=int(row.action_id),
        original_event_id=str(row.original_event_id),
        period_id=int(row.period_id),
        time_seconds=float(row.time_seconds),
    )


def _teams(actions: pd.DataFrame, tracking: pd.DataFrame) -> set[str]:
    teams = set(actions["team_id"].astype(str)) | set(tracking.loc[tracking["team_id"] != BALL_ID, "team_id"])
    if len(teams) != 2:
        raise ValueError(f"expected exactly two teams, found {sorted(teams)}")
    return teams


def _window(tracking: pd.DataFrame, period_id: int, t_key: float, chain_t0: float) -> TrackingWindow:
    frames = (tracking.loc[tracking["period_id"] == period_id, ["frame_id", "timestamp"]]
              .drop_duplicates("frame_id").sort_values("frame_id"))
    if frames.empty:
        raise ValueError(f"no tracking frames for period {period_id}")
    ts = frames["timestamp"].to_numpy()
    fids = frames["frame_id"].to_numpy()
    want_start = float(np.clip(chain_t0 - WINDOW_LEAD, t_key - WINDOW_BEFORE_MAX, t_key - WINDOW_BEFORE_MIN))
    want_end = t_key + WINDOW_AFTER
    i0 = int(np.searchsorted(ts, want_start - _EPS, side="left"))
    i1 = int(np.searchsorted(ts, want_end + _EPS, side="right")) - 1
    i0, i1 = min(i0, len(ts) - 1), max(i1, 0)
    if fids[i1] - fids[i0] != i1 - i0:
        raise ValueError(f"tracking frames are not contiguous in period {period_id} window")
    return TrackingWindow(period_id=period_id, frame_start=int(fids[i0]), frame_end=int(fids[i1]),
                          t_start=float(ts[i0]), t_end=float(ts[i1]))


def window_frames(tracking: pd.DataFrame, window: TrackingWindow | None) -> pd.DataFrame:
    if window is None:
        return tracking.iloc[0:0].reset_index(drop=True)
    rows = tracking[(tracking["frame_id"] >= window.frame_start) & (tracking["frame_id"] <= window.frame_end)]
    return rows.reset_index(drop=True)


def possession_of(possessions: tuple[Possession, ...]) -> dict[int, int]:
    """action_id -> index into ``possessions``."""
    return {aid: n for n, p in enumerate(possessions) for aid in p.action_ids}


def chain_moment(
    moment_class: MomentClass,
    seq: int,
    key: Any,
    possessions: tuple[Possession, ...],
    n: int,
    by_id: pd.DataFrame,
    tracking: pd.DataFrame,
    attacking: str,
    defending: str,
    outcome: Any | None = None,
    outcome_xg: float | None = None,
    is_own_goal: bool = False,
) -> MomentContext:
    """An explained moment keyed on SPADL row ``key``, in ``possessions[n]``.

    The chain is that possession up to and including the key action, capped at
    ``CHAIN_MAX_ACTIONS`` / ``CHAIN_MAX_SECONDS``; ``outcome`` (default: the key
    action) is the terminal action whose value Build 4 attributes over.
    """
    poss = possessions[n]
    key_id = int(key.action_id)
    outcome = key if outcome is None else outcome
    t_key = float(key.time_seconds)
    upto = [aid for aid in poss.action_ids if aid <= key_id]
    chain_ids = [aid for aid in upto if t_key - float(by_id.at[aid, "time_seconds"]) <= CHAIN_MAX_SECONDS + _EPS]
    chain_ids = chain_ids[-CHAIN_MAX_ACTIONS:]
    truncated = len(chain_ids) < len(upto)
    chain_start = "truncated" if truncated else poss.start_type
    turnover = None
    if chain_start == "regain":
        prev = possessions[n - 1]
        lost = [aid for aid in prev.action_ids if by_id.at[aid, "team_id"] == prev.team_id]
        turnover = _ref(by_id.loc[lost[-1] if lost else prev.action_ids[-1]])

    chain_rows = by_id.loc[chain_ids]
    chain_t0 = float(chain_rows["time_seconds"].iloc[0])
    window = _window(tracking, poss.period_id, t_key, chain_t0)
    game_id = str(key.game_id)
    moment = Moment(
        moment_id=f"{game_id}-{moment_class}-{seq}",
        type=moment_class,
        engine_eligible=True,
        game_id=game_id,
        period_id=poss.period_id,
        t_event=t_key,
        attacking_team_id=attacking,
        defending_team_id=defending,
        key_event_ref=_ref(key),
        key_player_id=str(key.player_id),
        is_own_goal=is_own_goal,
        outcome_ref=_ref(outcome),
        outcome_scored=is_goal(outcome.type_name, outcome.result_name),
        outcome_xg=outcome_xg,
        possession_id=poss.possession_id,
        chain=tuple(_ref(r) for r in chain_rows.itertuples(index=False)),
        chain_start=chain_start,
        turnover_event_ref=turnover,
        contested_action_ids=tuple(a for a in poss.contested_action_ids if a in set(chain_ids)),
        t_start=min(chain_t0, window.t_start),
        t_end=window.t_end,
        window=window,
    )
    return MomentContext(moment=moment, chain_actions=chain_rows.reset_index(drop=True),
                         frames=window_frames(tracking, window))


def detect_goal_moments(
    actions: pd.DataFrame,
    tracking: pd.DataFrame,
    possessions: tuple[Possession, ...] | None = None,
) -> list[MomentContext]:
    """One ``MomentContext`` per goal, in match order. Pure: inputs are not modified."""
    if possessions is None:
        possessions = segment_possessions(actions)
    by_id = actions.set_index("action_id", drop=False)
    teams = _teams(actions, tracking)
    out: list[MomentContext] = []
    for n, poss in enumerate(possessions):
        if poss.end_type != "goal":
            continue
        key = by_id.loc[poss.action_ids[-1]]
        own_goal = key.result_name == "owngoal"
        attacking = next(t for t in teams if t != key.team_id) if own_goal else str(key.team_id)
        defending = next(t for t in teams if t != attacking)
        out.append(chain_moment("goal", len(out) + 1, key, possessions, n, by_id, tracking,
                                attacking, defending, is_own_goal=own_goal))
    return out


class StreamingGoalDetector:
    """Detects goal moments from a ``ReplayClock`` stream, as they complete.

    Call ``attach(clock)``; ``on_moment`` fires once a goal's tracking window has
    fully arrived (``WINDOW_AFTER`` after the goal, or at the end of the period).
    A seek resets the buffers: the detector only knows what it has been fed.
    """

    def __init__(self, on_moment: Callable[[MomentContext], None]):
        self.on_moment = on_moment
        self.reset()

    def reset(self, _position: float | None = None) -> None:
        self._actions: list[dict[str, Any]] = []
        self._frames: list[tuple] = []
        self._pending: list[tuple[int, float, int]] = []  # (period_id, due_t, goal action_id)
        self._period: int | None = None

    def attach(self, clock: Any) -> Callable[[], None]:
        return clock.subscribe(self.feed, kinds=["action", "frame"], on_seek=self.reset)

    def feed(self, item: Any) -> None:
        if item.kind == "action":
            a = item.payload
            self._actions.append(a.to_row())
            if is_goal(a.type_name, a.result_name):
                self._pending.append((a.period_id, a.time_seconds + WINDOW_AFTER, a.action_id))
            return
        frame: TrackingFrame = item.payload
        new_period = self._period is not None and frame.period_id != self._period
        if new_period:
            self._flush(lambda p, due: p != frame.period_id)  # period ended: windows are complete
        self._period = frame.period_id
        self._frames.extend(
            (frame.frame_id, frame.period_id, frame.timestamp, o.player_id, o.team_id, o.x, o.y, o.vx, o.vy)
            for o in frame.objects
        )
        self._flush(lambda p, due: p == frame.period_id and frame.timestamp >= due - _EPS)

    def finish(self) -> None:
        """Flush goals whose window was cut short by the end of the stream."""
        self._flush(lambda p, due: True)

    def _flush(self, ready: Callable[[int, float], bool]) -> None:
        done = [g for g in self._pending if ready(g[0], g[1])]
        if not done:
            return
        self._pending = [g for g in self._pending if g not in done]
        actions = pd.DataFrame(self._actions, columns=list(SPADL_COLUMNS))
        tracking = pd.DataFrame(self._frames, columns=list(TRACKING_COLUMNS))
        wanted = {g[2] for g in done}
        for ctx in detect_goal_moments(actions, tracking):
            if ctx.moment.key_event_ref.action_id in wanted:
                self.on_moment(ctx)
