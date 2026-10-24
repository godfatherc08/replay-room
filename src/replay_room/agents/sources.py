"""Where the agents read the live match and the stored accounts: Azure (via Azure MCP) or local, one interface.

* **Stream** (what the Scout consumes): ``EventhouseStream`` reads the match's
  feed events from a Fabric Eventhouse (KQL) through the Azure MCP ``kusto``
  tool; ``FixtureStream`` reads the same feed from the fixture's
  ``events.jsonl``. Both yield the raw feed events in order.
* **Account store**: ``CosmosAccountStore`` reads a moment's causal account
  from Cosmos DB through the Azure MCP ``cosmos`` tool; ``LocalAccountStore``
  reads ``data/accounts/<game>/<moment>.json``.

``stream_from_env`` / ``store_from_env`` pick the Azure source when it is
configured and fall back to the local one (recording why) when it is not, or
when it fails, so the pipeline runs with or without Azure provisioned.

Configuration: ``EVENTHOUSE_CLUSTER_URI``, ``EVENTHOUSE_DATABASE``,
``EVENTHOUSE_TABLE`` (default ``MatchEvents``); ``COSMOS_ACCOUNT``,
``COSMOS_DATABASE`` (default ``replayroom``), ``COSMOS_CONTAINER`` (default
``accounts``).
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from replay_room.agents.azure import AzureMcp, AzureUnavailable
from replay_room.attribution.store import ACCOUNTS_DIR, load_account
from replay_room.contracts.causal_account import CausalAccount


class Stream(Protocol):
    name: str

    def events(self) -> Iterator[dict[str, Any]]: ...


class AccountStore(Protocol):
    name: str

    def get(self, game_id: str, moment_id: str) -> CausalAccount | None: ...


@dataclass
class FixtureStream:
    match_dir: Path
    name: str = "fixture feed (events.jsonl)"

    def events(self) -> Iterator[dict[str, Any]]:
        with (Path(self.match_dir) / "events.jsonl").open(encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    yield json.loads(line)


@dataclass
class EventhouseStream:
    cluster_uri: str
    database: str
    table: str = "MatchEvents"
    game_id: str | None = None
    mcp: AzureMcp = field(default_factory=AzureMcp)
    name: str = "Fabric Eventhouse (Azure MCP kusto)"

    def events(self) -> Iterator[dict[str, Any]]:
        where = f" | where game_id == '{self.game_id}'" if self.game_id else ""
        rows = self.mcp.kusto_query(self.cluster_uri, self.database,
                                    f"{self.table}{where} | order by period asc, t asc, id asc")
        for row in rows if isinstance(rows, list) else rows.get("items", []):
            yield row if isinstance(row, dict) else json.loads(row)


@dataclass
class LocalAccountStore:
    root: Path = ACCOUNTS_DIR
    name: str = "local files (data/accounts)"

    def get(self, game_id: str, moment_id: str) -> CausalAccount | None:
        path = Path(self.root) / game_id / f"{moment_id}.json"
        return load_account(path) if path.is_file() else None


@dataclass
class CosmosAccountStore:
    account: str
    database: str = "replayroom"
    container: str = "accounts"
    mcp: AzureMcp = field(default_factory=AzureMcp)
    name: str = "Cosmos DB (Azure MCP cosmos)"

    def get(self, game_id: str, moment_id: str) -> CausalAccount | None:
        items = self.mcp.cosmos_query(self.account, self.database, self.container,
                                      f"SELECT * FROM c WHERE c.account_id = 'acc-{moment_id}'")
        items = items if isinstance(items, list) else items.get("items", [])
        if not items:
            return None
        doc = {k: v for k, v in items[0].items() if not k.startswith("_") and k != "id"}
        return CausalAccount.model_validate(doc)


@dataclass
class Picked:
    source: Any
    fallback_reason: str | None = None


def stream_from_env(match_dir: Path, game_id: str | None = None) -> Picked:
    uri, db = os.environ.get("EVENTHOUSE_CLUSTER_URI", ""), os.environ.get("EVENTHOUSE_DATABASE", "")
    if not uri or not db:
        return Picked(FixtureStream(match_dir), "set EVENTHOUSE_CLUSTER_URI and EVENTHOUSE_DATABASE to stream from Fabric")
    stream = EventhouseStream(uri, db, os.environ.get("EVENTHOUSE_TABLE", "MatchEvents"), game_id)
    try:
        first = next(iter(stream.events()), None)
    except (AzureUnavailable, OSError, ValueError) as e:
        return Picked(FixtureStream(match_dir), f"Eventhouse via Azure MCP failed: {e}")
    if first is None:
        return Picked(FixtureStream(match_dir), "the Eventhouse table has no events for this match")
    return Picked(stream)


def store_from_env(root: Path = ACCOUNTS_DIR) -> Picked:
    account = os.environ.get("COSMOS_ACCOUNT", "")
    if not account:
        return Picked(LocalAccountStore(root), "set COSMOS_ACCOUNT to read accounts from Cosmos DB")
    return Picked(CosmosAccountStore(account, os.environ.get("COSMOS_DATABASE", "replayroom"),
                                     os.environ.get("COSMOS_CONTAINER", "accounts")))
