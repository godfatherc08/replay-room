"""The replay clock: emits a match's feed items "as they happen".

Periods are laid end to end on one continuous *timeline* (seconds): period 2
starts where period 1's duration ends. The clock maps wall time to timeline
time through ``speed`` and supports pause, seek and speed changes at any
moment. Consumers either subscribe callbacks (``subscribe``) and drive it with
``run``/``poll``, or iterate ``stream()`` from async code. Neither cares
whether the items came from a fixture, an in-memory replay or (later) a live
Eventstream: the clock only sees an ``IngestSource``.

Time is injectable (``time_fn``) so the clock is deterministic under test.
"""

from __future__ import annotations

import asyncio
import bisect
import time
from collections.abc import AsyncIterator, Callable, Iterable
from dataclasses import dataclass

from replay_room.ingest.source import FeedItem, IngestSource, ItemKind

Callback = Callable[[FeedItem], None]
SeekCallback = Callable[[float], None]

# Items due within this many timeline seconds are emitted now. Without it, sleeping
# exactly ``time_to_next`` can land a rounding error short of the item, and the
# remaining wait is below the wall clock's resolution, so the loop never advances.
_EPS = 1e-6


@dataclass
class _Subscription:
    callback: Callback
    kinds: frozenset[str] | None
    on_seek: SeekCallback | None


class ReplayClock:
    def __init__(self, source: IngestSource, speed: float = 1.0, time_fn: Callable[[], float] = time.monotonic):
        if speed <= 0:
            raise ValueError("speed must be > 0")
        self.source = source
        self._time = time_fn
        self._offsets: dict[int, float] = {}
        offset = 0.0
        for period in source.meta.periods:
            self._offsets[period.period_id] = offset
            offset += period.end_seconds - period.start_seconds
        self.duration = offset
        self._items = source.items()
        self._item_t = [self.timeline_t(i.period_id, i.t) for i in self._items]
        self._cursor = 0
        self._speed = float(speed)
        self._playing = False
        self._anchor_pos = 0.0  # timeline position at the anchor
        self._anchor_wall = self._time()
        self._subs: list[_Subscription] = []

    # ------------------------------------------------------------------ time mapping

    def timeline_t(self, period_id: int, t: float) -> float:
        return self._offsets[period_id] + t

    def period_t(self, timeline: float) -> tuple[int, float]:
        """Inverse of ``timeline_t`` (clamped to the match)."""
        timeline = min(max(timeline, 0.0), self.duration)
        period_id = max((p for p, off in self._offsets.items() if off <= timeline), key=self._offsets.get)
        return period_id, timeline - self._offsets[period_id]

    @property
    def position(self) -> float:
        """Current timeline position in seconds."""
        pos = self._anchor_pos
        if self._playing:
            pos += (self._time() - self._anchor_wall) * self._speed
        return min(pos, self.duration)

    def _reanchor(self, pos: float) -> None:
        self._anchor_pos = min(max(pos, 0.0), self.duration)
        self._anchor_wall = self._time()

    # ------------------------------------------------------------------ controls

    @property
    def playing(self) -> bool:
        return self._playing

    @property
    def speed(self) -> float:
        return self._speed

    @property
    def finished(self) -> bool:
        return self._cursor >= len(self._items)

    def play(self) -> None:
        if not self._playing:
            self._reanchor(self._anchor_pos)
            self._playing = True

    def pause(self) -> None:
        if self._playing:
            self._reanchor(self.position)
            self._playing = False

    def toggle(self) -> None:
        self.pause() if self._playing else self.play()

    def set_speed(self, speed: float) -> None:
        if speed <= 0:
            raise ValueError("speed must be > 0")
        self._reanchor(self.position)
        self._speed = float(speed)

    def seek(self, timeline: float) -> None:
        """Jump to ``timeline`` seconds without emitting what is skipped; items at or
        after the target are pending. Subscribers' ``on_seek`` hooks are told."""
        self._reanchor(timeline)
        self._cursor = bisect.bisect_left(self._item_t, self._anchor_pos)
        for sub in list(self._subs):
            if sub.on_seek is not None:
                sub.on_seek(self._anchor_pos)

    def seek_period(self, period_id: int, t: float) -> None:
        self.seek(self.timeline_t(period_id, t))

    # ------------------------------------------------------------------ emission

    def subscribe(
        self,
        callback: Callback,
        kinds: Iterable[ItemKind] | None = None,
        on_seek: SeekCallback | None = None,
    ) -> Callable[[], None]:
        """Register ``callback`` for items (optionally only some kinds). Returns an unsubscribe function."""
        sub = _Subscription(callback, frozenset(kinds) if kinds is not None else None, on_seek)
        self._subs.append(sub)
        return lambda: self._subs.remove(sub) if sub in self._subs else None

    def _emit(self, item: FeedItem) -> None:
        for sub in list(self._subs):
            if sub.kinds is None or item.kind in sub.kinds:
                sub.callback(item)

    def poll(self) -> list[FeedItem]:
        """Emit every pending item whose time has come; return them in order."""
        now = self.position + _EPS
        due = []
        while self._cursor < len(self._items) and self._item_t[self._cursor] <= now:
            item = self._items[self._cursor]
            self._cursor += 1
            due.append(item)
            self._emit(item)
        return due

    def advance_to(self, timeline: float) -> list[FeedItem]:
        """Move the clock forward to ``timeline`` emitting everything in between,
        independent of wall time (batch processing, tests). Keeps play/pause state."""
        self._reanchor(max(timeline, self.position))
        return self.poll()

    def time_to_next(self) -> float | None:
        """Wall seconds until the next item is due (0 if overdue, None if finished or paused)."""
        if self.finished or not self._playing:
            return None
        return max(0.0, (self._item_t[self._cursor] - self.position) / self._speed)

    def run(
        self,
        sleep: Callable[[float], None] = time.sleep,
        on_tick: Callable[[ReplayClock], bool | None] | None = None,
        max_idle: float = 0.05,
    ) -> None:
        """Blocking loop until the stream is exhausted. ``on_tick`` runs every
        iteration (e.g. keyboard controls) and may return True to stop early."""
        self.play()
        while not self.finished:
            self.poll()
            if on_tick is not None and on_tick(self):
                return
            wait = self.time_to_next()
            sleep(max_idle if wait is None else min(wait, max_idle))

    async def stream(self, max_idle: float = 0.05) -> AsyncIterator[FeedItem]:
        """Async generator of items as they happen. Pause/seek/speed take effect live."""
        self.play()
        while not self.finished:
            for item in self.poll():
                yield item
            wait = self.time_to_next()
            await asyncio.sleep(max_idle if wait is None else min(wait, max_idle))
