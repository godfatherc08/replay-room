"""Pass completion probability ("pass difficulty" = 1 - completion).

SPADL records where a pass *ended*, not where it was aimed: an intercepted
pass ends at the interception point, so failed passes look short. A model on
the SPADL end point learns "longer passes complete more often", which is the
leak itself. Features therefore come from the tracking frame at the moment of
the pass, i.e. from what the passer could see:

* the **intended receiver**, led by their velocity. When the feed names it
  (``Match.pass_targets``, for completed *and* failed passes) that is used.
  Otherwise it is inferred: the teammate best aligned with the direction the
  ball travelled, among those at least as far away as the ball got, else the
  observed end. ``result_name`` is never read.

  Inference is only reliable for completed passes. A failed pass's ball runs
  towards the interceptor, so the inferred target leans that way and its lane
  looks blocked: a model trained on inferred targets reads the outcome back
  (held-out AUC 0.80 on inferred features vs 0.64 when scored on true
  targets). Train only on feeds that name targets; ``metrics.train`` reports
  the source mix.
* geometry towards the intended point: length, forward progress, depth,
  distance from the centre line, cross flag;
* ``lane_gap``: nearest opponent to the passing lane at the moment of the pass;
* ``receiver_gap``: nearest opponent to the intended point;
* whether the passer was under pressure.

``pass_context`` computes the tracking-derived columns (absolute frame);
``orient`` flips the intended point with the rest of the action. The model is
a low-capacity logistic regression fitted on the corpus.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from replay_room.contracts.match import ContextEvent
from replay_room.contracts.pitch import BALL_ID, PITCH_LENGTH, PITCH_WIDTH
from replay_room.metrics.orientation import LtrActions, require_ltr

PASS_TYPES = ("pass", "cross")
PRESSURE_WINDOW = 2.0  # s: a pressure event on the passer this recently counts
LEAD_SPEED = 16.0  # m/s, typical ball speed: a receiver is led by velocity * distance / LEAD_SPEED
MAX_AIM_ANGLE = np.radians(25.0)  # widest misalignment still read as "aimed at this teammate"
END_TOLERANCE = 3.0  # m, an intended receiver may stand this much short of where the ball stopped
GAP_CAP = 10.0  # m, beyond this an opponent no longer matters to the pass
CONTEXT_COLUMNS = ("pass_frame_id", "receiver_id", "receiver_source", "intended_end_x", "intended_end_y",
                   "lane_gap", "receiver_gap")
FEATURES = ("length", "dx", "start_x", "end_x", "end_dy", "is_cross", "under_pressure",
            "lane_gap", "lane_tight", "receiver_gap", "receiver_tight")


def under_pressure(actions: pd.DataFrame, context: tuple[ContextEvent, ...]) -> pd.Series:
    """True where the actor was the target of a pressure event in the preceding ``PRESSURE_WINDOW`` s."""
    by_player: dict[tuple[int, str], list[float]] = {}
    for c in context:
        if c.kind == "pressure" and c.target_player_id:
            by_player.setdefault((c.period_id, c.target_player_id), []).append(c.time_seconds)
    flags = [
        any(t - PRESSURE_WINDOW <= p <= t for p in by_player.get((period, player), ()))
        for period, player, t in zip(actions["period_id"], actions["player_id"], actions["time_seconds"])
    ]
    return pd.Series(flags, index=actions.index, name="under_pressure")


def segment_gap(points: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Distance from each point (N, 2) to the segment a-b."""
    ab = b - a
    denom = float(ab @ ab)
    s = np.zeros(len(points)) if denom == 0 else np.clip((points - a) @ ab / denom, 0.0, 1.0)
    return np.hypot(*(points - (a + s[:, None] * ab)).T)


def frame_ids_at(tracking: pd.DataFrame, period_ids: pd.Series, times: pd.Series) -> np.ndarray:
    """The tracking frame nearest each (period, time)."""
    frames = tracking[["frame_id", "period_id", "timestamp"]].drop_duplicates("frame_id")
    out = np.empty(len(times), dtype=np.int64)
    pids, ts = period_ids.to_numpy(), times.to_numpy(float)
    for period, f in frames.groupby("period_id"):
        rows = np.flatnonzero(pids == period)
        if len(rows) == 0:
            continue
        stamps, ids = f["timestamp"].to_numpy(float), f["frame_id"].to_numpy()
        k = np.clip(np.searchsorted(stamps, ts[rows]), 1, len(stamps) - 1)
        k -= (ts[rows] - stamps[k - 1]) < (stamps[k] - ts[rows])
        out[rows] = ids[k]
    missing = set(np.unique(pids)) - set(frames["period_id"])
    if missing:
        raise ValueError(f"no tracking frames for period(s) {sorted(missing)}")
    return out


def pass_context(actions: pd.DataFrame, tracking: pd.DataFrame, targets: pd.Series | None = None) -> pd.DataFrame:
    """Tracking-derived context for every pass/cross (absolute frame); NaN/None for other actions.

    ``targets``: action_id -> intended receiver named by the feed (``Match.pass_targets``).
    ``receiver_source`` says where each receiver came from: ``feed``, ``inferred`` or ``none``.
    """
    targets = {} if targets is None else targets.to_dict()
    out = pd.DataFrame({"pass_frame_id": pd.Series(pd.NA, index=actions.index, dtype="Int64"),
                        "receiver_id": pd.Series(None, index=actions.index, dtype=object),
                        "receiver_source": pd.Series(None, index=actions.index, dtype=object),
                        "intended_end_x": np.nan, "intended_end_y": np.nan,
                        "lane_gap": np.nan, "receiver_gap": np.nan}, index=actions.index)
    passes = actions[actions["type_name"].isin(PASS_TYPES)]
    if passes.empty:
        return out
    fids = frame_ids_at(tracking, passes["period_id"], passes["time_seconds"])
    players = tracking[tracking["player_id"] != BALL_ID]
    by_frame = {fid: f for fid, f in players[players["frame_id"].isin(fids)].groupby("frame_id")}
    for idx, fid, row in zip(passes.index, fids, passes.itertuples(index=False)):
        f = by_frame[fid]
        start = np.array([row.start_x, row.start_y])
        observed = np.array([row.end_x, row.end_y])
        pos, vel = f[["x", "y"]].to_numpy(float), f[["vx", "vy"]].to_numpy(float)
        team, pid = f["team_id"].to_numpy(), f["player_id"].to_numpy()
        mates = np.flatnonzero((team == row.team_id) & (pid != row.player_id))
        intended, receiver, source = observed, None, "none"
        lead = pos[mates] + vel[mates] * (np.hypot(*(pos[mates] - start).T) / LEAD_SPEED)[:, None]
        lead = np.clip(lead, [0, 0], [PITCH_LENGTH, PITCH_WIDTH])
        named = np.flatnonzero(pid[mates] == targets.get(row.action_id))
        travel = observed - start
        travelled = float(np.hypot(*travel))
        if len(named):
            intended, receiver, source = lead[named[0]], str(pid[mates[named[0]]]), "feed"
        elif travelled > 0.5 and len(mates):
            rel = lead - start
            dist = np.hypot(*rel.T)
            cos = (rel @ travel) / (np.maximum(dist, 1e-9) * travelled)
            angle = np.where(dist >= travelled - END_TOLERANCE, np.arccos(np.clip(cos, -1, 1)), np.inf)
            best = int(np.argmin(angle))
            if angle[best] <= MAX_AIM_ANGLE:
                intended, receiver, source = lead[best], str(pid[mates[best]]), "inferred"
        opp = pos[team != row.team_id]
        out.at[idx, "pass_frame_id"] = int(fid)
        out.at[idx, "receiver_id"] = receiver
        out.at[idx, "receiver_source"] = source
        out.at[idx, "intended_end_x"], out.at[idx, "intended_end_y"] = float(intended[0]), float(intended[1])
        out.at[idx, "lane_gap"] = float(segment_gap(opp, start, intended).min()) if len(opp) else GAP_CAP
        out.at[idx, "receiver_gap"] = float(np.hypot(*(opp - intended).T).min()) if len(opp) else GAP_CAP
    return out


def pass_features(ltr: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in ("intended_end_x", "intended_end_y", "lane_gap", "receiver_gap") if c not in ltr]
    if missing:
        raise ValueError(f"pass completion needs tracking context {missing}: add pass_context() before orient()")
    dx = ltr["intended_end_x"] - ltr["start_x"]
    dy = ltr["intended_end_y"] - ltr["start_y"]
    pressure = ltr["under_pressure"] if "under_pressure" in ltr else pd.Series(False, index=ltr.index)
    lane = ltr["lane_gap"].clip(upper=GAP_CAP)
    space = ltr["receiver_gap"].clip(upper=GAP_CAP)
    return pd.DataFrame({
        "length": np.hypot(dx, dy),
        "dx": dx,
        "start_x": ltr["start_x"],
        "end_x": ltr["intended_end_x"],
        "end_dy": (ltr["intended_end_y"] - PITCH_WIDTH / 2).abs(),
        "is_cross": (ltr["type_name"] == "cross").astype(float),
        "under_pressure": pressure.astype(float),
        "lane_gap": lane,
        "lane_tight": np.exp(-lane / 1.5),  # a defender in the lane matters far more than one 5 m off it
        "receiver_gap": space,
        "receiver_tight": np.exp(-space / 1.5),
    }, index=ltr.index)[list(FEATURES)]


class PassModel:
    def __init__(self, coef: list[float], intercept: float, means: list[float], scales: list[float]):
        self.coef = np.asarray(coef)
        self.intercept = float(intercept)
        self.means = np.asarray(means)
        self.scales = np.asarray(scales)

    @classmethod
    def fit(cls, actions: LtrActions) -> PassModel:
        df = require_ltr(actions)
        passes = df[df["type_name"].isin(PASS_TYPES)]
        X = pass_features(passes).to_numpy(float)
        means, scales = X.mean(axis=0), X.std(axis=0) + 1e-9
        lr = LogisticRegression(C=1.0, max_iter=1000).fit((X - means) / scales, passes["result_name"] == "success")
        return cls(lr.coef_[0].tolist(), float(lr.intercept_[0]), means.tolist(), scales.tolist())

    def predict(self, actions: LtrActions) -> pd.Series:
        """Completion probability for passes/crosses; NaN for every other action."""
        df = require_ltr(actions)
        out = pd.Series(np.nan, index=df.index, name="pass_completion")
        mask = df["type_name"].isin(PASS_TYPES)
        if mask.any():
            X = (pass_features(df[mask]).to_numpy(float) - self.means) / self.scales
            out[mask] = 1.0 / (1.0 + np.exp(-(X @ self.coef + self.intercept)))
        return out

    def to_dict(self) -> dict:
        return {"features": list(FEATURES), "coef": self.coef.tolist(), "intercept": self.intercept,
                "means": self.means.tolist(), "scales": self.scales.tolist()}

    @classmethod
    def from_dict(cls, d: dict) -> PassModel:
        if tuple(d["features"]) != FEATURES:
            raise ValueError("pass model was trained with different features; retrain")
        return cls(d["coef"], d["intercept"], d["means"], d["scales"])
