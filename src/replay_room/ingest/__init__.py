"""Build 1: ingest. Raw feed -> canonical contracts (SPADL actions, context events, tracking)."""

from replay_room.ingest.adapter import AdaptedFeed, FeedAdapter, SyntheticFeedAdapter, detect_adapter
from replay_room.ingest.loader import Match, load_match
from replay_room.ingest.source import FeedItem, FileReplaySource, IngestSource

__all__ = [
    "AdaptedFeed",
    "FeedAdapter",
    "FeedItem",
    "FileReplaySource",
    "IngestSource",
    "Match",
    "SyntheticFeedAdapter",
    "detect_adapter",
    "load_match",
]
