"""The trained metric models as one loadable bundle (``data/models/``)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import sklearn

from replay_room.contracts.values import OnBallSignal
from replay_room.metrics.pass_value import PassModel
from replay_room.metrics.vaep import VAEPModel
from replay_room.metrics.xg import XGModel
from replay_room.metrics.xt import XTModel

MODELS_DIR = Path(__file__).resolve().parents[3] / "data" / "models"


@dataclass(frozen=True)
class MetricModels:
    xt: XTModel
    xg: XGModel
    passes: PassModel
    vaep: VAEPModel | None  # present only if it validated
    manifest: dict = field(repr=False)

    @property
    def on_ball_signal(self) -> OnBallSignal:
        return self.manifest["on_ball_signal"]

    @property
    def provenance(self) -> dict[str, str]:
        corpus = self.manifest["corpus"]
        out = {"xt": f"xt-16x12@{corpus}", "xg": f"xg-logit@{corpus}", "pass": f"pass-logit@{corpus}",
               "pitch_control": "fernandez-bornn-influence"}
        if self.vaep is not None:
            out["vaep"] = f"vaep-hgb@{corpus}"
        return out

    @classmethod
    def load(cls, path: Path) -> MetricModels:
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        vaep = None
        if manifest["on_ball_signal"] == "vaep":
            if manifest["sklearn"] != sklearn.__version__:
                raise RuntimeError(f"VAEP models were trained with scikit-learn {manifest['sklearn']} "
                                   f"but {sklearn.__version__} is installed: python -m replay_room.metrics.train")
            vaep = VAEPModel.load(path / "vaep.joblib")
        return cls(
            xt=XTModel.from_dict(json.loads((path / "xt.json").read_text(encoding="utf-8"))),
            xg=XGModel.from_dict(json.loads((path / "xg.json").read_text(encoding="utf-8"))),
            passes=PassModel.from_dict(json.loads((path / "pass.json").read_text(encoding="utf-8"))),
            vaep=vaep,
            manifest=manifest,
        )


@lru_cache(maxsize=4)
def load_models(path: str = str(MODELS_DIR)) -> MetricModels:
    """The bundle in ``data/models/`` (train with ``python -m replay_room.metrics.train``)."""
    return MetricModels.load(Path(path))
