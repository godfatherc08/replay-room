"""Expected goals: a geometric baseline.

Logistic regression on three features of the shot location, in the shooting
team's left-to-right frame (goal at x = 105): distance to the goal centre,
the angle the goal mouth subtends, and a header flag. Three coefficients are
robustly estimated from a few thousand corpus shots; the model is validated on
held-out games before it is used (see ``metrics.train``). Penalties get a fixed
conversion rate.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from replay_room.contracts.pitch import PITCH_LENGTH, PITCH_WIDTH
from replay_room.metrics.orientation import LtrActions, require_ltr

GOAL_HALF_WIDTH = 7.32 / 2
PENALTY_XG = 0.76  # approximate long-run penalty conversion rate
OPEN_PLAY_SHOTS = ("shot", "shot_freekick")
FEATURES = ("distance", "angle", "header")


def shot_features(ltr: pd.DataFrame) -> pd.DataFrame:
    dx = PITCH_LENGTH - ltr["start_x"].to_numpy(float)
    dy = ltr["start_y"].to_numpy(float) - PITCH_WIDTH / 2
    distance = np.hypot(dx, dy)
    # Angle between the lines to the two posts.
    a1 = np.arctan2(dy - GOAL_HALF_WIDTH, dx)
    a2 = np.arctan2(dy + GOAL_HALF_WIDTH, dx)
    angle = np.abs(a2 - a1)
    header = ltr["bodypart_name"].isin(["head", "head/other"]).to_numpy(float)
    return pd.DataFrame({"distance": distance, "angle": angle, "header": header}, index=ltr.index)


class XGModel:
    def __init__(self, coef: list[float], intercept: float, means: list[float], scales: list[float]):
        self.coef = np.asarray(coef)
        self.intercept = float(intercept)
        self.means = np.asarray(means)
        self.scales = np.asarray(scales)

    @classmethod
    def fit(cls, actions: LtrActions) -> XGModel:
        df = require_ltr(actions)
        shots = df[df["type_name"].isin(OPEN_PLAY_SHOTS)]
        X = shot_features(shots).to_numpy(float)
        means, scales = X.mean(axis=0), X.std(axis=0) + 1e-9
        lr = LogisticRegression(C=1.0, max_iter=1000).fit((X - means) / scales, shots["result_name"] == "success")
        return cls(lr.coef_[0].tolist(), float(lr.intercept_[0]), means.tolist(), scales.tolist())

    def predict_features(self, X: np.ndarray) -> np.ndarray:
        z = ((X - self.means) / self.scales) @ self.coef + self.intercept
        return 1.0 / (1.0 + np.exp(-z))

    def predict(self, actions: LtrActions) -> pd.Series:
        """xG for shots; NaN for every other action."""
        df = require_ltr(actions)
        out = pd.Series(np.nan, index=df.index, name="xg")
        open_play = df["type_name"].isin(OPEN_PLAY_SHOTS)
        if open_play.any():
            out[open_play] = self.predict_features(shot_features(df[open_play]).to_numpy(float))
        out[df["type_name"] == "shot_penalty"] = PENALTY_XG
        return out

    def to_dict(self) -> dict:
        return {"features": list(FEATURES), "coef": self.coef.tolist(), "intercept": self.intercept,
                "means": self.means.tolist(), "scales": self.scales.tolist()}

    @classmethod
    def from_dict(cls, d: dict) -> XGModel:
        if tuple(d["features"]) != FEATURES:
            raise ValueError("xG model was trained with different features; retrain")
        return cls(d["coef"], d["intercept"], d["means"], d["scales"])
