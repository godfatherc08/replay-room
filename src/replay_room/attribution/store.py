"""Local persistence for causal accounts (JSON on disk now; Cosmos DB later).

Layout: ``<root>/<game_id>/<moment_id>.json``. ``generated_at`` is stamped
here, at write time, so the computed account itself stays reproducible.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path

from replay_room.contracts.causal_account import CausalAccount

ACCOUNTS_DIR = Path(__file__).resolve().parents[3] / "data" / "accounts"


def save_accounts(accounts: Iterable[CausalAccount], root: str | Path = ACCOUNTS_DIR,
                  now: datetime | None = None) -> list[Path]:
    stamp = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    paths = []
    for account in accounts:
        stamped = account.model_copy(update={"provenance": account.provenance.model_copy(
            update={"generated_at": stamp})})
        path = Path(root) / account.game_id / f"{account.moment.moment_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(stamped.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n")
        paths.append(path)
    return paths


def load_account(path: str | Path) -> CausalAccount:
    return CausalAccount.model_validate_json(Path(path).read_text(encoding="utf-8"))
