"""Off-ball contract: tracking rows and per-timestamp frames.

The bulk form is the *tracking table*, a long DataFrame with
``TRACKING_COLUMNS`` (one row per object per frame, the ball included with
``player_id == team_id == BALL_ID``). ``TrackingFrame`` is one timestamp's
snapshot, which is what the replay clock emits.
"""

from __future__ import annotations

from dataclasses import dataclass

from replay_room.contracts.pitch import BALL_ID

TRACKING_COLUMNS: tuple[str, ...] = (
    "frame_id",
    "period_id",
    "timestamp",
    "player_id",
    "team_id",
    "x",
    "y",
    "vx",
    "vy",
)


@dataclass(frozen=True, slots=True)
class TrackingRow:
    """One object's observed position and velocity at one timestamp."""

    player_id: str
    team_id: str
    x: float
    y: float
    vx: float
    vy: float

    @property
    def is_ball(self) -> bool:
        return self.player_id == BALL_ID


@dataclass(frozen=True, slots=True)
class TrackingFrame:
    """All tracked objects at one timestamp. ``frame_id`` is the off-ball evidence key."""

    frame_id: int
    period_id: int
    timestamp: float
    objects: tuple[TrackingRow, ...]

    @property
    def ball(self) -> TrackingRow | None:
        return next((o for o in self.objects if o.is_ball), None)

    @property
    def players(self) -> tuple[TrackingRow, ...]:
        return tuple(o for o in self.objects if not o.is_ball)
