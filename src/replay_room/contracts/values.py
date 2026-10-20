"""Value-annotation contract: what Build 3 attaches and Build 4 consumes.

* ``ValuedAction``: one SPADL action plus every value the metric layer computed
  for it, and ``value``, the reading of the *authoritative* on-ball signal
  (``ValuedMoment.on_ball_signal``: ``"vaep"`` when the VAEP models validated,
  otherwise ``"xt_delta"``).
* ``PitchControlSurface``: one tracking frame's control field from the
  attacking team's perspective, in the canonical (absolute) pitch frame so it
  overlays the tracking data and the 3D scene directly.
* ``ValuedMoment``: a goal moment with every chain action valued and every
  window frame carrying a surface.

These are in-memory types (numpy arrays inside); they are not part of the
causal-account JSON. Build 4 cites the numbers, not the arrays.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from replay_room.contracts.moment import Moment
from replay_room.contracts.spadl import SpadlAction

OnBallSignal = Literal["vaep", "xt_delta"]


@dataclass(frozen=True)
class ValuedAction:
    action: SpadlAction  # canonical (absolute) coordinates, as ingested
    value: float | None  # authoritative on-ball value (see ValuedMoment.on_ball_signal); None if undefined
    xt_start: float | None = None  # xT of the start cell, acting team's perspective
    xt_end: float | None = None
    xt_delta: float | None = None  # possession-adjusted delta-xT (see metrics.xt)
    vaep: float | None = None
    vaep_offensive: float | None = None
    vaep_defensive: float | None = None
    xg: float | None = None  # shots only
    pass_completion: float | None = None  # passes and crosses only

    @property
    def pass_difficulty(self) -> float | None:
        return None if self.pass_completion is None else 1.0 - self.pass_completion


@dataclass(frozen=True)
class PitchControlSurface:
    """``control[j, i]`` = P(``team_id`` controls the cell centred at (x[i], y[j]))."""

    frame_id: int
    period_id: int
    timestamp: float
    team_id: str  # perspective: the moment's attacking team
    model: Literal["influence", "voronoi"]
    x: np.ndarray = field(repr=False)  # cell centres along the pitch length, metres
    y: np.ndarray = field(repr=False)  # cell centres along the width, metres
    control: np.ndarray = field(repr=False)  # shape (len(y), len(x)), values in [0, 1]
    control_share: float = 0.0  # mean control over the pitch
    space_value: float = 0.0  # xT-weighted control: share of the pitch's threat this team controls

    def at(self, x: float, y: float) -> float:
        """Control in the cell nearest to (x, y)."""
        i = int(np.abs(self.x - x).argmin())
        j = int(np.abs(self.y - y).argmin())
        return float(self.control[j, i])


@dataclass(frozen=True)
class ValuedMoment:
    moment: Moment
    on_ball_signal: OnBallSignal
    actions: tuple[ValuedAction, ...]  # the chain, in order
    surfaces: tuple[PitchControlSurface, ...]  # one per window frame, in order
    models: dict[str, str] = field(default_factory=dict)  # metric -> model id/version (provenance)
