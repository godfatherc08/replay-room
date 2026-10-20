"""Orientation guard for the metric layer.

Ingested actions are in the canonical *absolute* frame (home attacks +x).
Directional metrics need each action expressed as if its team attacked +x:

* xT, xG and pass value accept only ``LtrActions``, which can only be made by
  ``orient()`` (``socceraction.spadl.play_left_to_right`` applied exactly once).
* VAEP must NOT get pre-oriented actions: socceraction orients every game state
  itself, from the perspective of the team performing the state's action, so a
  pre-flipped table would flip away-team actions twice. ``require_absolute``
  refuses an ``LtrActions``.

The wrapper is a distinct type (not a DataFrame), so passing the wrong
orientation is an immediate TypeError rather than silently wrong numbers.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from socceraction.spadl import play_left_to_right

from replay_room.contracts.pitch import PITCH_LENGTH, PITCH_WIDTH

# Extra (x, y) columns that orient() flips like start/end (see metrics.pass_value).
EXTRA_POINTS = (("intended_end_x", "intended_end_y"),)


@dataclass(frozen=True)
class LtrActions:
    """SPADL actions where every action's team attacks +x. Build with ``orient``."""

    df: pd.DataFrame
    home_team_id: str


def orient(actions: pd.DataFrame, home_team_id: str) -> LtrActions:
    if isinstance(actions, LtrActions):
        raise TypeError("actions are already oriented left-to-right")
    if not isinstance(actions, pd.DataFrame):
        raise TypeError(f"expected a SPADL DataFrame, got {type(actions).__name__}")
    if home_team_id not in set(actions["team_id"]):
        raise ValueError(f"home team {home_team_id!r} has no actions; wrong home_team_id?")
    ltr = play_left_to_right(actions.copy(), home_team_id)
    away = actions["team_id"] != home_team_id
    for x, y in EXTRA_POINTS:  # metric-layer locations ride along with the action
        if x in ltr:
            ltr.loc[away, x] = PITCH_LENGTH - actions.loc[away, x]
            ltr.loc[away, y] = PITCH_WIDTH - actions.loc[away, y]
    return LtrActions(ltr, home_team_id)


def require_ltr(actions: object) -> pd.DataFrame:
    if not isinstance(actions, LtrActions):
        raise TypeError("this metric needs left-to-right actions: call metrics.orientation.orient() first")
    return actions.df


def require_absolute(actions: object) -> pd.DataFrame:
    if isinstance(actions, LtrActions):
        raise TypeError("VAEP orients game states itself; pass the absolute (ingested) actions")
    if not isinstance(actions, pd.DataFrame):
        raise TypeError(f"expected a SPADL DataFrame, got {type(actions).__name__}")
    return actions
