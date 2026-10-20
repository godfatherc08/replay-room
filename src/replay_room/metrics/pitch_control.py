"""Pitch control: closed-form geometry over observed positions and velocities.

Two models, both evaluated on a regular grid in the canonical (absolute) frame:

* ``voronoi_control``: baseline. Each cell belongs to the team of the nearest
  player (control is 0 or 1).
* ``influence_control``: player-influence model after Fernandez & Bornn,
  "Wide Open Spaces" (MIT Sloan 2018), parameterised as in the common open
  implementations. Each player projects a bivariate normal centred half a
  second ahead along their velocity, stretched along the direction of travel
  (more with speed) and wider the further the player is from the ball. The
  influence is normalised to 1 at the player's own position. Control for a team
  is ``sigmoid(sum(own influence) - sum(opponent influence))``, so the two
  teams' controls sum to 1 in every cell.

No training; no data beyond one frame. Every frame is computed independently,
so windows of any length (or a single frame) work.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from replay_room.contracts.pitch import BALL_ID, PITCH_LENGTH, PITCH_WIDTH

GRID_NX = 53  # ~2 m cells
GRID_NY = 34
MAX_PLAYER_SPEED = 13.0  # m/s, scales the velocity stretch
RADIUS_MIN = 4.0  # m, influence radius next to the ball
RADIUS_MAX = 10.0  # m, influence radius far from the ball
RADIUS_DIST_SCALE = 18.0 ** 3 / 10.0  # radius = min(MIN + d_ball^3 / SCALE, MAX)
LOOKAHEAD = 0.5  # s, the influence centre leads the player by velocity * LOOKAHEAD
MAX_SPEED_RATIO = 0.99  # keeps the cross-axis spread strictly positive


def grid(nx: int = GRID_NX, ny: int = GRID_NY) -> tuple[np.ndarray, np.ndarray]:
    """Cell centres (x, y) covering the pitch."""
    x = (np.arange(nx) + 0.5) * PITCH_LENGTH / nx
    y = (np.arange(ny) + 0.5) * PITCH_WIDTH / ny
    return x, y


def _cells(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    gx, gy = np.meshgrid(x, y)  # shape (ny, nx)
    return np.stack([gx.ravel(), gy.ravel()], axis=1)  # (ny*nx, 2)


def influence(pos: np.ndarray, vel: np.ndarray, ball: np.ndarray, cells: np.ndarray) -> np.ndarray:
    """Influence of each player on each cell. pos/vel: (P, 2); ball: (2,); cells: (C, 2) -> (P, C)."""
    d_ball = np.hypot(*(pos - ball).T)
    radius = np.minimum(RADIUS_MIN + d_ball ** 3 / RADIUS_DIST_SCALE, RADIUS_MAX)
    speed = np.hypot(*vel.T)
    ratio = np.minimum(speed ** 2 / MAX_PLAYER_SPEED ** 2, MAX_SPEED_RATIO)
    theta = np.arctan2(vel[:, 1], vel[:, 0])
    c, s = np.cos(theta), np.sin(theta)
    sx = (radius + radius * ratio) / 2  # spread along the direction of travel
    sy = (radius - radius * ratio) / 2  # spread across it
    mu = pos + LOOKAHEAD * vel
    # Mahalanobis distance in the player's rotated frame: project onto (along, across) axes.
    d = cells[None, :, :] - mu[:, None, :]  # (P, C, 2)
    along = d[..., 0] * c[:, None] + d[..., 1] * s[:, None]
    across = -d[..., 0] * s[:, None] + d[..., 1] * c[:, None]
    m = (along / sx[:, None]) ** 2 + (across / sy[:, None]) ** 2
    d0 = pos - mu  # the player's own position, for normalisation
    a0 = d0[:, 0] * c + d0[:, 1] * s
    b0 = -d0[:, 0] * s + d0[:, 1] * c
    m0 = (a0 / sx) ** 2 + (b0 / sy) ** 2
    return np.exp(-0.5 * (m - m0[:, None]))


def influence_control(frame: pd.DataFrame, team_id: str, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """P(team_id controls each cell) for one frame of the tracking table -> (len(y), len(x))."""
    players = frame[frame["player_id"] != BALL_ID]
    ball_rows = frame[frame["player_id"] == BALL_ID]
    if ball_rows.empty:
        raise ValueError("frame has no ball row")
    ball = ball_rows[["x", "y"]].to_numpy()[0]
    cells = _cells(x, y)
    own = players["team_id"].to_numpy() == team_id
    infl = influence(players[["x", "y"]].to_numpy(), players[["vx", "vy"]].to_numpy(), ball, cells)
    z = infl[own].sum(axis=0) - infl[~own].sum(axis=0)
    return (1.0 / (1.0 + np.exp(-z))).reshape(len(y), len(x))


def voronoi_control(frame: pd.DataFrame, team_id: str, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """1 where the nearest player is on ``team_id``, else 0 -> (len(y), len(x))."""
    players = frame[frame["player_id"] != BALL_ID]
    cells = _cells(x, y)
    pos = players[["x", "y"]].to_numpy()
    nearest = np.argmin(((cells[None, :, :] - pos[:, None, :]) ** 2).sum(axis=2), axis=0)
    own = players["team_id"].to_numpy() == team_id
    return own[nearest].astype(float).reshape(len(y), len(x))
