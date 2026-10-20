"""Ingest sources: where the replay clock gets its time-ordered stream from.

``IngestSource`` is the seam for later transports. Build 1 ships
``FileReplaySource`` (local, in-memory, from a fixture directory); a Fabric
Eventstream source would implement the same interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Union

from replay_room.contracts.match import ContextEvent, MatchMeta
from replay_room.contracts.spadl import SpadlAction
from replay_room.contracts.tracking import TrackingFrame
from replay_room.ingest.loader import Match, load_match

ItemKind = Literal["action", "context", "frame"]
Payload = Union[SpadlAction, ContextEvent, TrackingFrame]

# Within one timestamp: frame first (the state at t), then context, then actions.
_KIND_ORDER = {"frame": 0, "context": 1, "action": 2}


@dataclass(frozen=True, slots=True)
class FeedItem:
    """One thing that happens at match time (``period_id``, ``t``)."""

    period_id: int
    t: float
    kind: ItemKind
    payload: Payload

    @property
    def sort_key(self) -> tuple[int, float, int]:
        return (self.period_id, self.t, _KIND_ORDER[self.kind])


class IngestSource(ABC):
    """A match as a time-ordered stream of feed items."""

    @property
    @abstractmethod
    def meta(self) -> MatchMeta: ...

    @abstractmethod
    def items(self) -> list[FeedItem]:
        """All items, ordered by ``sort_key``. Bounded sources only (replay); a live
        source will expose an async iterator instead when it is added."""


class FileReplaySource(IngestSource):
    """Replays a match loaded from disk, entirely in memory."""

    def __init__(self, match: Match):
        self.match = match
        self._items: list[FeedItem] | None = None

    @classmethod
    def from_path(cls, path: str | Path) -> FileReplaySource:
        return cls(load_match(path))

    @property
    def meta(self) -> MatchMeta:
        return self.match.meta

    def items(self) -> list[FeedItem]:
        if self._items is None:
            items = [FeedItem(f.period_id, f.timestamp, "frame", f) for f in self.match.iter_frames()]
            items += [FeedItem(c.period_id, c.time_seconds, "context", c) for c in self.match.context]
            items += [FeedItem(a.period_id, a.time_seconds, "action", a) for a in self.match.iter_actions()]
            items.sort(key=lambda i: i.sort_key)  # stable: ties keep feed order
            self._items = items
        return self._items
