"""Training corpus: many reproducible synthetic matches, through the real adapter.

Value models (xT, xG, VAEP, pass completion) cannot be trained on one fixture's
four goals. ``build_corpus`` generates ``n`` matches with Build 1's generator
(seeds ``seed0 .. seed0+n-1``, no "must contain a goal" retry so the data is
unbiased), writes each as a raw feed, loads it back through the feed adapter
(the same path real data takes), and keeps the SPADL actions plus the
``under_pressure`` flag and the tracking-derived pass context
(``pass_value.pass_context``). The result is cached on disk under a key that includes
the corpus/generator versions, ``n`` and ``seed0``.

Caveat: everything learned from this corpus reflects the simulator's football.
Retrain on a corpus of real matches when the real feed lands.
"""

from __future__ import annotations

import json
import tempfile
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from replay_room.ingest import load_match
from replay_room.ingest.generator import GENERATOR_VERSION, generate_match, write_fixture
from replay_room.metrics.pass_value import pass_context, under_pressure

CORPUS_VERSION = "3"
DEFAULT_N = 200
DEFAULT_SEED0 = 1000
DEFAULT_ROOT = Path(__file__).resolve().parents[3] / "data" / "corpus"
_STR_COLS = {"game_id": str, "original_event_id": str, "team_id": str, "player_id": str, "receiver_id": str, "receiver_source": str}


@dataclass(frozen=True)
class Corpus:
    key: str
    actions: pd.DataFrame  # SPADL (absolute frame) for all games, plus `under_pressure` and pass context
    games: pd.DataFrame  # game_id, home_team_id

    @property
    def n_games(self) -> int:
        return len(self.games)


def corpus_key(n: int, seed0: int) -> str:
    return f"c{CORPUS_VERSION}-g{GENERATOR_VERSION}-n{n}-s{seed0}"


def _one_match(seed: int) -> tuple[pd.DataFrame, str]:
    match = generate_match(seed, require_goal_buildup=False)
    with tempfile.TemporaryDirectory() as tmp:
        loaded = load_match(write_fixture(match, Path(tmp) / "m"))
    actions = loaded.actions.copy()
    actions["under_pressure"] = under_pressure(loaded.actions, loaded.context)
    actions = actions.join(pass_context(loaded.actions, loaded.tracking, loaded.pass_targets))
    return actions, loaded.meta.home_team_id


def build_corpus(
    n: int = DEFAULT_N, seed0: int = DEFAULT_SEED0, root: Path = DEFAULT_ROOT, workers: int | None = None
) -> Corpus:
    """Load the cached corpus, or generate it (in parallel) and cache it."""
    key = corpus_key(n, seed0)
    path = Path(root) / key
    if (path / "manifest.json").is_file():
        actions = pd.read_csv(path / "actions.csv.gz", dtype=_STR_COLS)
        actions["pass_frame_id"] = actions["pass_frame_id"].astype("Int64")
        games = pd.read_csv(path / "games.csv", dtype=str)
        return Corpus(key, actions, games)

    seeds = list(range(seed0, seed0 + n))
    if workers == 1:
        results = [_one_match(s) for s in seeds]
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(_one_match, seeds))  # map keeps seed order: deterministic
    actions = pd.concat([a for a, _ in results], ignore_index=True)
    games = pd.DataFrame({"game_id": [a["game_id"].iloc[0] for a, _ in results],
                          "home_team_id": [h for _, h in results]})

    path.mkdir(parents=True, exist_ok=True)
    actions.to_csv(path / "actions.csv.gz", index=False)
    games.to_csv(path / "games.csv", index=False)
    manifest = {"key": key, "n_games": n, "seed0": seed0, "n_actions": len(actions),
                "n_shots": int((actions["type_name"] == "shot").sum()),
                "n_goals": int(((actions["type_name"] == "shot") & (actions["result_name"] == "success")).sum())}
    (path / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return build_corpus(n, seed0, root)  # reload from disk so fresh and cached corpora are identical
