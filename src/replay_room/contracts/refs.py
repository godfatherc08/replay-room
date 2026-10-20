"""Evidence references: the two ways any later claim points back at the data."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class EventRef(_Model):
    """Points at one on-ball SPADL action (``action_id`` is unique within a game)."""

    kind: Literal["event"] = "event"
    action_id: int
    original_event_id: str
    period_id: int
    time_seconds: float


class FrameRef(_Model):
    """Points at one tracking frame (``frame_id`` is unique within a game), optionally
    naming the players that matter in it."""

    kind: Literal["frame"] = "frame"
    frame_id: int
    timestamp: float
    player_ids: tuple[str, ...] = ()


class ContextRef(_Model):
    """Points at one non-SPADL context event (``ContextEvent.event_id``), e.g. a
    substitution. Moment keys only: never evidence for a causal claim."""

    kind: Literal["context"] = "context"
    event_id: str
    period_id: int
    time_seconds: float


EvidenceRef = Annotated[EventRef | FrameRef, Field(discriminator="kind")]
