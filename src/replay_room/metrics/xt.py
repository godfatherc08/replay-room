"""Expected Threat (Karun Singh, 2018) and possession-adjusted delta-xT.

The grid is fitted on the corpus with ``socceraction.xthreat.ExpectedThreat``
(16 x 12 zones, Markov fixed point of shoot/move probabilities). Rating uses
the plain cell lookup: socceraction's interpolation depends on
``scipy.interpolate.interp2d``, which current scipy no longer ships.

socceraction rates only *successful* moves (``xT(end) - xT(start)``). To value
every action in a goal's build-up, short counter-attacks included, delta-xT is
extended, all in the acting team's left-to-right frame:

* successful move (pass, cross, dribble, set-piece pass, clearance, take-on):
  ``xT(end) - xT(start)``;
* failed move: ``-xT(start)``, the threat the team held is lost;
* regain (successful interception, tackle or keeper action): ``+xT(location)``,
  the threat the team now holds;
* shot: ``xG - xT(start)``, the shot's value over keeping the ball there
  (only when xG is supplied);
* anything else (fouls, ...): undefined (NaN).

Zones with fewer than ``MIN_ZONE_SUPPORT`` move/shot starts in the corpus
(socceraction leaves unvisited ones at 0, and a handful of samples is noise)
take the value of the nearest supported zone in the same column (same distance
from goal), so no location reads as "no threat at all" for lack of data.
"""

from __future__ import annotations

import contextlib
import io

import numpy as np
import pandas as pd
from socceraction.xthreat import ExpectedThreat

from replay_room.contracts.pitch import PITCH_LENGTH, PITCH_WIDTH
from replay_room.metrics.orientation import LtrActions, require_ltr

GRID_L = 16  # zones along the length
GRID_W = 12  # zones across the width
MIN_ZONE_SUPPORT = 10  # move/shot starts needed for a zone's own estimate

MOVE_TYPES = frozenset({
    "pass", "cross", "dribble", "take_on", "clearance", "goalkick", "throw_in",
    "freekick_short", "freekick_crossed", "corner_short", "corner_crossed",
})
REGAIN_TYPES = frozenset({"interception", "tackle", "keeper_save", "keeper_claim", "keeper_pick_up", "keeper_punch"})
SHOT_TYPES = frozenset({"shot", "shot_freekick", "shot_penalty"})


def _supported(df: pd.DataFrame) -> np.ndarray:
    """Zones with at least MIN_ZONE_SUPPORT move/shot starts, shape (GRID_W, GRID_L)."""
    df = df[df["type_name"].isin(["pass", "cross", "dribble", "shot"])]
    xi = np.clip((df["start_x"].to_numpy(float) / PITCH_LENGTH * GRID_L).astype(int), 0, GRID_L - 1)
    yj = np.clip((df["start_y"].to_numpy(float) / PITCH_WIDTH * GRID_W).astype(int), 0, GRID_W - 1)
    counts = np.zeros((GRID_W, GRID_L), dtype=int)
    np.add.at(counts, (yj, xi), 1)
    return counts >= MIN_ZONE_SUPPORT


class XTModel:
    def __init__(self, grid: np.ndarray):
        """``grid[j, i]``: zone i along the length (0 = own goal line), zone j across (0 = y near 0)."""
        self.grid = np.asarray(grid, dtype=float)
        if self.grid.shape != (GRID_W, GRID_L):
            raise ValueError(f"xT grid must be {GRID_W}x{GRID_L}, got {self.grid.shape}")

    @classmethod
    def fit(cls, actions: LtrActions) -> XTModel:
        df = require_ltr(actions)
        model = ExpectedThreat(l=GRID_L, w=GRID_W)
        with contextlib.redirect_stdout(io.StringIO()):  # socceraction prints its iteration count
            model.fit(df)
        # socceraction's row 0 is the top of the pitch (y = 68); store with row 0 at y = 0.
        grid = model.xT[::-1].copy()
        supported = _supported(df)
        for i in range(GRID_L):
            seen = np.flatnonzero(supported[:, i])
            if len(seen) == 0:
                raise ValueError(f"xT column {i} has no supported zone; corpus too small")
            for j in np.flatnonzero(~supported[:, i]):
                grid[j, i] = grid[seen[np.abs(seen - j).argmin()], i]
        return cls(grid)

    def at(self, x: np.ndarray | pd.Series, y: np.ndarray | pd.Series) -> np.ndarray:
        """xT of the zone containing each (x, y), in the attacking team's left-to-right frame."""
        xi = np.clip((np.asarray(x, float) / PITCH_LENGTH * GRID_L).astype(int), 0, GRID_L - 1)
        yj = np.clip((np.asarray(y, float) / PITCH_WIDTH * GRID_W).astype(int), 0, GRID_W - 1)
        return self.grid[yj, xi]

    def rate(self, actions: LtrActions, xg: pd.Series | None = None) -> pd.DataFrame:
        """Columns ``xt_start``, ``xt_end``, ``xt_delta`` (possession-adjusted, see module docstring)."""
        df = require_ltr(actions)
        start = self.at(df["start_x"], df["start_y"])
        end = self.at(df["end_x"], df["end_y"])
        success = (df["result_name"] == "success").to_numpy()
        typ = df["type_name"]
        move = typ.isin(MOVE_TYPES).to_numpy()
        regain = (typ.isin(REGAIN_TYPES).to_numpy()) & success
        shot = typ.isin(SHOT_TYPES).to_numpy()
        delta = np.full(len(df), np.nan)
        delta[move & success] = (end - start)[move & success]
        delta[move & ~success] = -start[move & ~success]
        delta[regain] = start[regain]
        if xg is not None:
            delta[shot] = xg.to_numpy(float)[shot] - start[shot]
        return pd.DataFrame({"xt_start": start, "xt_end": np.where(move | shot, end, np.nan), "xt_delta": delta},
                            index=df.index)

    def oriented_grid(self, attacking_home: bool, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        """xT at absolute-frame cell centres (x, y) for a team attacking +x (home) or -x (away)."""
        gx, gy = np.meshgrid(x, y)
        if not attacking_home:  # same flip as play_left_to_right
            gx, gy = PITCH_LENGTH - gx, PITCH_WIDTH - gy
        return self.at(gx, gy)

    def to_dict(self) -> dict:
        return {"l": GRID_L, "w": GRID_W, "grid": self.grid.tolist()}

    @classmethod
    def from_dict(cls, d: dict) -> XTModel:
        return cls(np.array(d["grid"]))
