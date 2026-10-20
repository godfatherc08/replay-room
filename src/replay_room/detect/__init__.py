"""Build 2: interpret. Possession segmentation and moment detection (explained + flagged classes)."""

from replay_room.detect.dispatch import ALL_CLASSES, CLAIM_ORDER, detect_moments
from replay_room.detect.explained import detect_big_chances_saved, detect_penalties, detect_turnover_to_shot
from replay_room.detect.flagged import detect_context_moments, detect_offsides
from replay_room.detect.moments import StreamingGoalDetector, detect_goal_moments
from replay_room.detect.possessions import Possession, possession_index, segment_possessions

__all__ = [
    "ALL_CLASSES",
    "CLAIM_ORDER",
    "Possession",
    "StreamingGoalDetector",
    "detect_big_chances_saved",
    "detect_context_moments",
    "detect_goal_moments",
    "detect_moments",
    "detect_offsides",
    "detect_penalties",
    "detect_turnover_to_shot",
    "possession_index",
    "segment_possessions",
]
