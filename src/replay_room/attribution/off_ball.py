"""Track B, off-ball: who opened, or gave up, the space the moment came from.

**Space at the key spot.** The moment's key event (the shot, or the foul that
won a penalty) happened at a spot; the outcome's value V is the value of
having the ball *there*. So for one frame, from the attacking team's
perspective::

    space(f) = sum(control * g) / sum(g),   g = exp(-|cell - spot|^2 / (2 * SPOT_SIGMA^2))

is how much the attack controlled that spot (``control``: Build 3's
influence-model pitch control, the frame's ``PitchControlSurface``), and
``V * space`` is, to first order, the attack's P(outcome) through that space.

**A player's share.** ``share(p, f) = V * (space(f) - space(f without p))``:
the frame's control is recomputed with player p's influence removed (Build 3's
``influence`` per player; the full sum reproduces the surface exactly, which is
checked). An attacker's share is positive (he holds the spot or is arriving),
a defender's negative (he denies it). Frames where the player is on the ball
(within ``CARRIER_RADIUS``) are skipped: that is on-ball work.

**The fact.** Over the window up to the key event, a player's fact is the
largest *rise* in his share, ``share(b) - share(a)`` for frames ``a < b``, in
units of P(outcome):

* attacker: **space_creation** (``space_created``), signal ``run_in_behind``
  when the run took him past the defensive line, ``run_into_space`` when he was
  moving at ``RUN_SPEED`` or faster, otherwise ``found_space``;
* defender: **space_conceded**, and **marking_break** when he also lost the
  attacker nearest him at frame ``a`` (separation grew by at least
  ``MARK_GAIN_M``). The decisive frame is then the first frame where the two
  were separating at ``SEPARATING_SPEED`` or faster: where he stopped tracking
  his man. Signal ``stopped_tracking_runner`` when the man was running,
  ``lost_marker`` otherwise.

Goalkeepers get no off-ball facts: the influence model treats them like
outfield players, so a keeper's routine repositioning reads as space conceded
at the shot spot. Their saves are on-ball (and ``chance_denied``).

Every fact cites the measured numbers (``space_conceded`` / ``space_created``,
the shares, separations) and is bound to the frame where the rise peaked (and
the decisive frame for a marking break), naming the players.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from replay_room.attribution.outcome import Candidate
from replay_room.contracts.pitch import BALL_ID, PITCH_LENGTH
from replay_room.contracts.refs import FrameRef
from replay_room.contracts.values import ValuedMoment
from replay_room.metrics.pitch_control import _cells, influence

SPOT_SIGMA = 4.0  # m, the size of "the spot" the key event happened at
CARRIER_RADIUS = 1.5  # m, a player this close to the ball is on it
RUN_SPEED = 4.0  # m/s
MARK_GAIN_M = 2.5  # m of extra separation that counts as losing a man
SEPARATING_SPEED = 2.0  # m/s along the defender->attacker line
_EPS = 1e-6


def space_shares(vm: ValuedMoment, frames: pd.DataFrame, spot: tuple[float, float], value: float,
                 t_end: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Per frame (rows) and player (columns): ``V * (space - space without the player)``, NaN while on the ball.

    Also returns the frames' player rows (positions, velocities) indexed by (frame_id, player_id).
    """
    m = vm.moment
    surfaces = {s.frame_id: s for s in vm.surfaces if s.timestamp <= t_end + _EPS}
    if not surfaces:
        raise ValueError(f"{m.moment_id}: no valued frames before the key event")
    first = next(iter(surfaces.values()))
    cells = _cells(first.x, first.y)
    g = np.exp(-((cells - np.asarray(spot)) ** 2).sum(axis=1) / (2 * SPOT_SIGMA ** 2))
    weight = g / g.sum()
    rows = frames[frames["frame_id"].isin(surfaces.keys())].sort_values(["frame_id", "player_id"])
    shares: dict[int, dict[str, float]] = {}
    for fid, f in rows.groupby("frame_id", sort=True):
        players = f[f["player_id"] != BALL_ID]
        ball = f.loc[f["player_id"] == BALL_ID, ["x", "y"]].to_numpy()[0]
        pos, vel = players[["x", "y"]].to_numpy(float), players[["vx", "vy"]].to_numpy(float)
        own = (players["team_id"] == m.attacking_team_id).to_numpy()
        infl = influence(pos, vel, ball, cells)
        z = infl[own].sum(axis=0) - infl[~own].sum(axis=0)
        control = 1.0 / (1.0 + np.exp(-z))
        if not np.allclose(control, surfaces[fid].control.ravel(), atol=1e-9):
            raise ValueError(f"frame {fid}: recomputed control disagrees with Build 3's surface")
        z_without = z[None, :] - np.where(own, 1.0, -1.0)[:, None] * infl  # (P, C): each player removed
        share = value * (control @ weight - (1.0 / (1.0 + np.exp(-z_without))) @ weight)
        share[np.hypot(*(pos - ball).T) < CARRIER_RADIUS] = np.nan
        shares[int(fid)] = dict(zip(players["player_id"], share))
    table = pd.DataFrame.from_dict(shares, orient="index").sort_index()
    return table, rows.set_index(["frame_id", "player_id"])


def _best_rise(series: pd.Series) -> tuple[float, int, int] | None:
    """max over a < b of s[b] - s[a] (NaNs skipped), with (a, b) frame ids."""
    s = series.dropna()
    if len(s) < 2:
        return None
    vals, ids = s.to_numpy(), s.index.to_numpy()
    best, best_ab = -np.inf, None
    lo = 0
    for j in range(1, len(vals)):
        if vals[j - 1] < vals[lo]:
            lo = j - 1
        if vals[j] - vals[lo] > best:
            best, best_ab = vals[j] - vals[lo], (int(ids[lo]), int(ids[j]))
    return (float(best), *best_ab) if best_ab and best > 0 else None


def _ltr_x(x: float, attacking_home: bool) -> float:
    return x if attacking_home else PITCH_LENGTH - x


def _last_line(at: pd.DataFrame, defending: str, goalkeepers: frozenset[str], attacking_home: bool) -> float:
    """How far up the pitch (attacking team's frame) the deepest outfield defender stands."""
    outfield = at[(at["team_id"] == defending) & ~at.index.isin(goalkeepers)]
    return max(_ltr_x(x, attacking_home) for x in outfield["x"])


def off_ball_candidates(vm: ValuedMoment, frames: pd.DataFrame, spot: tuple[float, float], value: float,
                        attacking_home: bool, goalkeepers: frozenset[str] = frozenset()) -> list[Candidate]:
    """``spot``: the key event's location (absolute frame); ``value``: the outcome's V."""
    m = vm.moment
    shares, pos = space_shares(vm, frames, spot, value, m.t_event)
    stamps = frames.drop_duplicates("frame_id").set_index("frame_id")["timestamp"]
    out: list[Candidate] = []
    for pid in shares.columns:
        if pid in goalkeepers:
            continue
        rise = _best_rise(shares[pid])
        if rise is None:
            continue
        effect, a, b = rise
        me_b = pos.loc[(b, pid)]
        team = str(me_b["team_id"])
        speed = float(np.hypot(me_b["vx"], me_b["vy"]))
        metrics = {"share_start": round(float(shares.at[a, pid]), 6), "share_end": round(float(shares.at[b, pid]), 6)}
        if team == m.attacking_team_id:
            behind_b = _ltr_x(me_b["x"], attacking_home) > _last_line(pos.loc[b], m.defending_team_id, goalkeepers,
                                                                    attacking_home)
            behind_a = _ltr_x(pos.loc[(a, pid)]["x"], attacking_home) > _last_line(pos.loc[a], m.defending_team_id,
                                                                                goalkeepers, attacking_home)
            signal = "run_in_behind" if behind_b and not behind_a else (
                "run_into_space" if speed >= RUN_SPEED else "found_space")
            out.append(Candidate(
                key=f"s{pid}", track="off_ball", kind="space_creation", role="space_creation", label=signal,
                player_id=pid, team_id=team, t=float(stamps[b]), effect=effect,
                evidence=(FrameRef(frame_id=b, timestamp=float(stamps[b]), player_ids=(pid,)),
                          FrameRef(frame_id=a, timestamp=float(stamps[a]), player_ids=(pid,))),
                metrics={"space_created": round(effect, 6), "speed": round(speed, 3), **metrics},
            ))
            continue
        out.append(_conceded(pid, team, effect, a, b, pos, stamps, m.attacking_team_id, metrics, goalkeepers))
    return out


def _conceded(pid: str, team: str, effect: float, a: int, b: int, pos: pd.DataFrame, stamps: pd.Series,
              attacking: str, metrics: dict[str, float], goalkeepers: frozenset[str]) -> Candidate:
    at_a = pos.loc[a]
    me_a = at_a.loc[pid]
    rivals = at_a[(at_a["team_id"] == attacking) & ~at_a.index.isin(goalkeepers)]
    gaps = np.hypot(rivals["x"] - me_a["x"], rivals["y"] - me_a["y"])
    man = str(gaps.idxmin())
    span = [f for f in stamps.index if a <= f <= b]
    sep, closing = [], []
    for f in span:
        d, r = pos.loc[(f, pid)], pos.loc[(f, man)]
        rel = np.array([r["x"] - d["x"], r["y"] - d["y"]])
        dist = float(np.hypot(*rel))
        sep.append(dist)
        closing.append(float((np.array([r["vx"] - d["vx"], r["vy"] - d["vy"]]) @ rel) / max(dist, _EPS)))
    gain = sep[-1] - sep[0]
    metrics = {"space_conceded": round(effect, 6), **metrics}
    if gain >= MARK_GAIN_M:
        k = next((i for i, v in enumerate(closing) if v >= SEPARATING_SPEED), len(span) - 1)
        decisive = span[k]
        r = pos.loc[(decisive, man)]
        signal = "stopped_tracking_runner" if float(np.hypot(r["vx"], r["vy"])) >= RUN_SPEED else "lost_marker"
        metrics |= {"separation_start": round(sep[0], 3), "separation_end": round(sep[-1], 3),
                    "separating_speed": round(closing[k], 3)}
        evidence = [FrameRef(frame_id=decisive, timestamp=float(stamps[decisive]), player_ids=(pid, man))]
        if decisive != b:
            evidence.append(FrameRef(frame_id=b, timestamp=float(stamps[b]), player_ids=(pid, man)))
        return Candidate(
            key=f"s{pid}", track="off_ball", kind="marking_break", role="defensive_error", label=signal,
            player_id=pid, team_id=team, t=float(stamps[decisive]), effect=effect, evidence=tuple(evidence),
            metrics=metrics,
        )
    return Candidate(
        key=f"s{pid}", track="off_ball", kind="space_conceded", role="defensive_error", label="conceded_space",
        player_id=pid, team_id=team, t=float(stamps[b]), effect=effect,
        evidence=(FrameRef(frame_id=b, timestamp=float(stamps[b]), player_ids=(pid,)),
                  FrameRef(frame_id=a, timestamp=float(stamps[a]), player_ids=(pid,))),
        metrics=metrics,
    )
