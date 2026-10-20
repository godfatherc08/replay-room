"""The canonical pitch frame every stage after ingest works in.

It is socceraction's SPADL convention, applied to events *and* tracking so the
two line up without any per-stage conversion:

* units: metres (positions), metres/second (velocities), seconds (time)
* pitch: 105 x 68, origin at the bottom-left corner, x in [0, 105], y in [0, 68]
* direction: the home team attacks +x (towards x = 105) in every period; away
  team coordinates are absolute (not flipped). Metric code that wants "every
  team plays left to right" calls ``socceraction.spadl.play_left_to_right``.
"""

from socceraction.spadl import config as _spadl

PITCH_LENGTH: float = float(_spadl.field_length)  # 105.0
PITCH_WIDTH: float = float(_spadl.field_width)  # 68.0

BALL_ID: str = "ball"
"""``player_id`` and ``team_id`` used for the ball in tracking data."""
