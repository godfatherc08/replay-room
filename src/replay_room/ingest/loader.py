"""Format-agnostic match loading: path -> canonical ``Match``."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from replay_room.contracts.match import ContextEvent, MatchMeta
from replay_room.contracts.spadl import SpadlAction
from replay_room.contracts.tracking import TrackingFrame, TrackingRow
from replay_room.ingest.adapter import FeedAdapter, detect_adapter


@dataclass(frozen=True)
class Match:
    """One match in canonical form. Tables are the bulk form; iterators give contract objects."""

    meta: MatchMeta
    actions: pd.DataFrame
    context: tuple[ContextEvent, ...]
    tracking: pd.DataFrame

    def iter_actions(self) -> Iterator[SpadlAction]:
        for row in self.actions.itertuples(index=False):
            yield SpadlAction.from_row(row)

    def iter_frames(self) -> Iterator[TrackingFrame]:
        cols = self.tracking
        frame_ids = cols["frame_id"].to_numpy()
        period_ids = cols["period_id"].to_numpy()
        timestamps = cols["timestamp"].to_numpy()
        records = list(zip(cols["player_id"], cols["team_id"], cols["x"], cols["y"], cols["vx"], cols["vy"]))
        start = 0
        n = len(cols)
        while start < n:
            end = start
            while end < n and frame_ids[end] == frame_ids[start]:
                end += 1
            yield TrackingFrame(
                frame_id=int(frame_ids[start]),
                period_id=int(period_ids[start]),
                timestamp=float(timestamps[start]),
                objects=tuple(
                    TrackingRow(str(p), str(t), float(x), float(y), float(vx), float(vy))
                    for p, t, x, y, vx, vy in records[start:end]
                ),
            )
            start = end


def load_match(path: str | Path, adapter: FeedAdapter | None = None) -> Match:
    path = Path(path)
    adapter = adapter or detect_adapter(path)
    feed = adapter.read(path)
    return Match(meta=feed.meta, actions=feed.actions, context=feed.context, tracking=feed.tracking)
