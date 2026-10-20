"""VAEP (Decroos et al., KDD 2019): P_score / P_concede models over SPADL game states.

Features, labels and the value formula are socceraction's own
(``VAEP.compute_features``, ``VAEP.compute_labels``, ``vaep.formula.value``);
only the two classifiers are trained here, as scikit-learn gradient-boosted
trees (``HistGradientBoostingClassifier``). That is the same model family as the
paper's XGBoost, but deterministic and with no extra dependency.

Orientation: socceraction orients each game state itself (towards the goal of
the team performing the state's action), so this module takes the ABSOLUTE
actions and refuses ``LtrActions`` (see ``metrics.orientation``).

VAEP is only used if it validates on held-out games (see ``validate`` and
``metrics.train``). Otherwise delta-xT is the authoritative on-ball signal.
"""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import brier_score_loss, roc_auc_score
from socceraction.vaep import formula
from socceraction.vaep.base import VAEP

from replay_room.metrics.orientation import require_absolute

MIN_AUC = 0.70  # both models must reach this on held-out games...
MIN_BRIER_SKILL = 0.0  # ...and beat the base-rate Brier score
GBM_PARAMS = {"max_iter": 300, "learning_rate": 0.05, "max_leaf_nodes": 31, "min_samples_leaf": 40,
              "early_stopping": False, "random_state": 0}
_VAEP = VAEP()  # socceraction's feature/label definitions only


def _game(game_id: str, home_team_id: str) -> pd.Series:
    return pd.Series({"game_id": game_id, "home_team_id": home_team_id})


def features_and_labels(actions: pd.DataFrame, games: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Socceraction features and (scores, concedes) labels for every action of every game."""
    actions = require_absolute(actions)
    Xs, ys = [], []
    for game in games.itertuples(index=False):
        ga = actions[actions["game_id"] == game.game_id].reset_index(drop=True)
        g = _game(game.game_id, game.home_team_id)
        Xs.append(_VAEP.compute_features(g, ga))
        ys.append(_VAEP.compute_labels(g, ga))
    return pd.concat(Xs, ignore_index=True), pd.concat(ys, ignore_index=True)


def score(model: HistGradientBoostingClassifier, X: pd.DataFrame, y: pd.Series) -> dict[str, float]:
    p = model.predict_proba(X)[:, 1]
    base = np.full(len(y), y.mean())
    brier, brier_base = brier_score_loss(y, p), brier_score_loss(y, base)
    return {"auc": float(roc_auc_score(y, p)), "brier": float(brier), "brier_base": float(brier_base),
            "brier_skill": float(1 - brier / brier_base), "positive_rate": float(y.mean())}


class VAEPModel:
    def __init__(self, scores: HistGradientBoostingClassifier, concedes: HistGradientBoostingClassifier,
                 columns: list[str]):
        self.scores = scores
        self.concedes = concedes
        self.columns = columns

    @classmethod
    def fit(cls, X: pd.DataFrame, y: pd.DataFrame) -> VAEPModel:
        scores = HistGradientBoostingClassifier(**GBM_PARAMS).fit(X, y["scores"])
        concedes = HistGradientBoostingClassifier(**GBM_PARAMS).fit(X, y["concedes"])
        return cls(scores, concedes, list(X.columns))

    def validate(self, X: pd.DataFrame, y: pd.DataFrame) -> dict:
        report = {"scores": score(self.scores, X[self.columns], y["scores"]),
                  "concedes": score(self.concedes, X[self.columns], y["concedes"])}
        report["passed"] = all(r["auc"] >= MIN_AUC and r["brier_skill"] > MIN_BRIER_SKILL
                               for r in (report["scores"], report["concedes"]))
        return report

    def rate(self, actions: pd.DataFrame, home_team_id: str) -> pd.DataFrame:
        """``offensive_value``, ``defensive_value``, ``vaep_value`` for every action of one game."""
        actions = require_absolute(actions).reset_index(drop=True)
        g = _game(str(actions["game_id"].iloc[0]), home_team_id)
        X = _VAEP.compute_features(g, actions)[self.columns]
        p_scores = pd.Series(self.scores.predict_proba(X)[:, 1], index=actions.index)
        p_concedes = pd.Series(self.concedes.predict_proba(X)[:, 1], index=actions.index)
        values = formula.value(_VAEP._spadlcfg.add_names(actions), p_scores, p_concedes)
        values.index = actions["action_id"].to_numpy()
        return values

    def save(self, path: Path) -> None:
        joblib.dump({"scores": self.scores, "concedes": self.concedes, "columns": self.columns}, path)

    @classmethod
    def load(cls, path: Path) -> VAEPModel:
        d = joblib.load(path)
        return cls(d["scores"], d["concedes"], d["columns"])
