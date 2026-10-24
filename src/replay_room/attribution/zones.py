"""Plain names for pitch areas, from the attacking team's point of view (facing the goal it attacks)."""

from __future__ import annotations

from replay_room.contracts.pitch import PITCH_LENGTH, PITCH_WIDTH

BOX_X, EDGE_X, FINAL_THIRD_X = 88.5, 83.0, 70.0  # attacking frame, metres from the own goal line
BOX_Y = (13.84, 54.16)
SIX_X, SIX_Y = 99.5, (24.84, 43.16)


def zone_name(x: float, y: float, attacking_home: bool) -> str:
    """Plain name of a pitch area, from the attacking team's point of view (facing the goal they attack)."""
    xl = x if attacking_home else PITCH_LENGTH - x
    yl = y if attacking_home else PITCH_WIDTH - y  # facing +x, left is +y
    side = "left" if yl > SIX_Y[1] else "right" if yl < SIX_Y[0] else None
    if xl >= SIX_X and SIX_Y[0] <= yl <= SIX_Y[1]:
        return "the six-yard box"
    if xl >= BOX_X and BOX_Y[0] <= yl <= BOX_Y[1]:
        return f"the {side} side of the box" if side else "the middle of the box"
    if xl >= EDGE_X and BOX_Y[0] <= yl <= BOX_Y[1]:
        return f"the {side} edge of the box" if side else "the edge of the box"
    if xl >= FINAL_THIRD_X:
        return f"the {side} channel" if side else "the centre of the final third"
    return f"the {side} of midfield" if side else "midfield"


