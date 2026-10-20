"""Build 2: interpret. Possession segmentation and goal-moment detection (structural, no valuation)."""

from replay_room.detect.moments import StreamingGoalDetector, detect_goal_moments
from replay_room.detect.possessions import Possession, possession_index, segment_possessions

__all__ = [
    "Possession",
    "StreamingGoalDetector",
    "detect_goal_moments",
    "possession_index",
    "segment_possessions",
]
