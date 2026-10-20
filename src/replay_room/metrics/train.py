"""Train and validate every metric model on the corpus; write ``data/models/``.

    python -m replay_room.metrics.train            # 200-match corpus (cached after first build)

Games are split deterministically: first 60% train, next 20% tune, last 20%
test. The test games are scored exactly once, after every choice is made.

* xT: fitted on all games (no labels to validate against; sanity-checked in tests).
* xG, pass completion: fitted on train+tune, scored on test. The pass model
  uses only passes whose intended receiver the feed names: inferred targets
  leak the outcome (see ``metrics.pass_value``), so a corpus where fewer than
  ``PASS_MIN_FEED_TARGETS`` of passes are named is refused.
* VAEP: for each of P_score and P_concede, a small regularisation grid is fitted
  on train and the best Brier score on tune is chosen. The chosen settings are
  refitted on train+tune and scored on test. VAEP is shipped, and becomes the
  authoritative on-ball signal, only if both models pass
  ``vaep.MIN_AUC`` / ``vaep.MIN_BRIER_SKILL``. Otherwise no VAEP artifact is
  written and delta-xT is authoritative.
"""

from __future__ import annotations

import argparse
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

from replay_room.metrics import vaep as vaep_mod
from replay_room.metrics.corpus import DEFAULT_N, DEFAULT_SEED0, Corpus, build_corpus
from replay_room.metrics.models import MODELS_DIR, load_models
from replay_room.metrics.orientation import LtrActions, orient
from replay_room.metrics.pass_value import PASS_TYPES, PassModel
from replay_room.metrics.xg import OPEN_PLAY_SHOTS, XGModel
from replay_room.metrics.xt import XTModel

XG_MIN_AUC = 0.65
PASS_MIN_AUC = 0.60
PASS_MIN_FEED_TARGETS = 0.9  # share of corpus passes whose intended receiver the feed names
VAEP_GRID = [
    {"max_iter": 300, "learning_rate": 0.05, "max_leaf_nodes": 31, "min_samples_leaf": 40},
    {"max_iter": 150, "learning_rate": 0.05, "max_leaf_nodes": 15, "min_samples_leaf": 100},
    {"max_iter": 100, "learning_rate": 0.05, "max_leaf_nodes": 7, "min_samples_leaf": 200, "l2_regularization": 1.0},
]


def split_games(games: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    n = len(games)
    a, b = int(n * 0.6), int(n * 0.8)
    return games.iloc[:a], games.iloc[a:b], games.iloc[b:]


def _ltr(corpus: Corpus, games: pd.DataFrame) -> LtrActions:
    """Orient each game separately (home team differs per game), then stack."""
    parts = []
    for g in games.itertuples(index=False):
        parts.append(orient(corpus.actions[corpus.actions["game_id"] == g.game_id], g.home_team_id).df)
    return LtrActions(pd.concat(parts), home_team_id="<per-game>")


def _binary_report(y: np.ndarray, p: np.ndarray) -> dict[str, float]:
    base = np.full(len(y), y.mean())
    return {"n": int(len(y)), "auc": float(roc_auc_score(y, p)), "log_loss": float(log_loss(y, p)),
            "log_loss_base": float(log_loss(y, base)), "brier": float(brier_score_loss(y, p)),
            "brier_base": float(brier_score_loss(y, base))}


def _fit_vaep_head(X_tr, y_tr, X_tu, y_tu, label: str) -> tuple[dict, list[dict]]:
    trials = []
    for params in VAEP_GRID:
        clf = HistGradientBoostingClassifier(**params, early_stopping=False, random_state=0).fit(X_tr, y_tr[label])
        trials.append({"params": params, "tune_brier": float(brier_score_loss(y_tu[label],
                                                                              clf.predict_proba(X_tu)[:, 1]))})
    best = min(trials, key=lambda t: t["tune_brier"])
    return best["params"], trials


def train(corpus: Corpus, out: Path = MODELS_DIR) -> dict:
    tr, tu, te = split_games(corpus.games)
    fit_games = pd.concat([tr, tu])
    report: dict = {"corpus": corpus.key, "n_games": corpus.n_games,
                    "split": {"train": len(tr), "tune": len(tu), "test": len(te)},
                    "sklearn": sklearn.__version__}

    xt = XTModel.fit(_ltr(corpus, corpus.games))

    ltr_fit, ltr_test = _ltr(corpus, fit_games), _ltr(corpus, te)
    xg = XGModel.fit(ltr_fit)
    shots = ltr_test.df[ltr_test.df["type_name"].isin(OPEN_PLAY_SHOTS)]
    xg_rep = _binary_report((shots["result_name"] == "success").to_numpy(),
                            xg.predict(LtrActions(shots, "<per-game>")).to_numpy())
    xg_rep["passed"] = xg_rep["auc"] >= XG_MIN_AUC and xg_rep["log_loss"] < xg_rep["log_loss_base"]
    report["xg"] = xg_rep

    all_passes = corpus.actions[corpus.actions["type_name"].isin(PASS_TYPES)]
    sources = all_passes["receiver_source"].value_counts().to_dict()
    if sources.get("feed", 0) < PASS_MIN_FEED_TARGETS * len(all_passes):
        raise ValueError(f"only {sources.get('feed', 0)} of {len(all_passes)} corpus passes name their intended "
                         "receiver; a pass model on inferred targets would learn the outcome")

    def named(ltr: LtrActions) -> LtrActions:
        df = ltr.df
        return LtrActions(df[df["type_name"].isin(PASS_TYPES) & (df["receiver_source"] == "feed")], ltr.home_team_id)

    passes_model = PassModel.fit(named(ltr_fit))
    passes = named(ltr_test).df
    pass_rep = _binary_report((passes["result_name"] == "success").to_numpy(),
                              passes_model.predict(LtrActions(passes, "<per-game>")).to_numpy())
    pass_rep["passed"] = pass_rep["auc"] >= PASS_MIN_AUC and pass_rep["log_loss"] < pass_rep["log_loss_base"]
    pass_rep["receiver_source"] = {k: int(v) for k, v in sorted(sources.items())}
    report["pass"] = pass_rep

    with warnings.catch_warnings():  # socceraction's feature code trips pandas FutureWarnings
        warnings.simplefilter("ignore", FutureWarning)
        X_tr, y_tr = vaep_mod.features_and_labels(corpus.actions, tr)
        X_tu, y_tu = vaep_mod.features_and_labels(corpus.actions, tu)
        X_te, y_te = vaep_mod.features_and_labels(corpus.actions, te)
    X_fit, y_fit = pd.concat([X_tr, X_tu], ignore_index=True), pd.concat([y_tr, y_tu], ignore_index=True)
    chosen, vaep_trials = {}, {}
    for label in ("scores", "concedes"):
        chosen[label], vaep_trials[label] = _fit_vaep_head(X_tr, y_tr, X_tu, y_tu, label)
    model = vaep_mod.VAEPModel(
        HistGradientBoostingClassifier(**chosen["scores"], early_stopping=False, random_state=0)
        .fit(X_fit, y_fit["scores"]),
        HistGradientBoostingClassifier(**chosen["concedes"], early_stopping=False, random_state=0)
        .fit(X_fit, y_fit["concedes"]),
        list(X_fit.columns),
    )
    vaep_rep = model.validate(X_te, y_te)
    vaep_rep.update({"chosen_params": chosen, "tuning": vaep_trials,
                     "criteria": {"min_auc": vaep_mod.MIN_AUC, "min_brier_skill": vaep_mod.MIN_BRIER_SKILL}})
    report["vaep"] = vaep_rep
    report["on_ball_signal"] = "vaep" if vaep_rep["passed"] else "xt_delta"

    out.mkdir(parents=True, exist_ok=True)
    (out / "xt.json").write_text(json.dumps(xt.to_dict()) + "\n", encoding="utf-8")
    (out / "xg.json").write_text(json.dumps(xg.to_dict(), indent=2) + "\n", encoding="utf-8")
    (out / "pass.json").write_text(json.dumps(passes_model.to_dict(), indent=2) + "\n", encoding="utf-8")
    vaep_path = out / "vaep.joblib"
    if vaep_rep["passed"]:
        model.save(vaep_path)
    elif vaep_path.exists():
        vaep_path.unlink()  # never leave a stale, unvalidated model behind
    (out / "manifest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    load_models.cache_clear()
    return report


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Build/load the corpus and train the metric models.")
    ap.add_argument("--n", type=int, default=DEFAULT_N)
    ap.add_argument("--seed0", type=int, default=DEFAULT_SEED0)
    ap.add_argument("--out", type=Path, default=MODELS_DIR)
    args = ap.parse_args(argv)
    report = train(build_corpus(args.n, args.seed0), args.out)
    v = report["vaep"]
    print(f"corpus {report['corpus']}  xG auc={report['xg']['auc']:.3f} passed={report['xg']['passed']}  "
          f"pass auc={report['pass']['auc']:.3f} passed={report['pass']['passed']}")
    print(f"VAEP scores auc={v['scores']['auc']:.3f} bss={v['scores']['brier_skill']:.3f}  "
          f"concedes auc={v['concedes']['auc']:.3f} bss={v['concedes']['brier_skill']:.3f}  passed={v['passed']}")
    print(f"authoritative on-ball signal: {report['on_ball_signal']}")


if __name__ == "__main__":
    main()
