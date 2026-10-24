"""Attribute a match, run the agents over every explainable moment, and export one viewer bundle per moment.

    python -m replay_room.render data/fixtures/synthetic_match_01
    python -m replay_room.render data/fixtures/synthetic_match_01 --narration template   # no model at all
    python -m replay_room.render data/fixtures/synthetic_match_01 --out viewer/public/bundles

Writes ``<out>/<game>/<moment>.json`` (the account), ``<moment>.bundle.json``
(account + plan + context + narration + editions + window tracking) and
``<out>/index.json``. ``--narration foundry`` (the default) uses the Foundry
Analyst and Storyteller when configured and falls back to the rule plan and the
composer when not; every telling passes the Critic either way.
"""

from __future__ import annotations

import argparse
import sys

from replay_room.agents.engine import InProcessEngine
from replay_room.agents.orchestrator import Orchestrator
from replay_room.agents.sources import FixtureStream
from replay_room.attribution.store import ACCOUNTS_DIR, save_accounts
from replay_room.contracts.moment import EXPLAINED_CLASSES
from replay_room.detect.__main__ import parse_classes
from replay_room.ingest import load_match
from replay_room.mcp_server.service import EngineService
from replay_room.render.export import write_bundles


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="render", description="Export viewer bundles for a match's moments.")
    ap.add_argument("match", help="match directory (e.g. data/fixtures/synthetic_match_01)")
    ap.add_argument("--classes", type=parse_classes, default=EXPLAINED_CLASSES)
    ap.add_argument("--out", default=str(ACCOUNTS_DIR), help=f"output root (default {ACCOUNTS_DIR})")
    ap.add_argument("--narration", choices=["foundry", "template"], default="foundry",
                    help="foundry: the model agents when configured, else their deterministic floors; "
                         "template: no model (default foundry)")
    args = ap.parse_args(argv)
    match = load_match(args.match)
    svc = EngineService(args.match, match=match)
    orch = Orchestrator(InProcessEngine(svc=svc), FixtureStream(args.match), mode=args.narration)
    menu = [m for m in orch.scout() if m.explainable and m.type in args.classes]
    told, accounts = {}, []
    for item in menu:
        result = orch.explain(item.moment_id)
        accounts.append(result.account)
        told[item.moment_id] = {"narration": result.narration, "plan": result.plan, "context": result.context,
                                "editions": result.editions}
        print(f"told {item.moment_id}: plan {result.plan.source}, narration {result.narration.source}",
              file=sys.stderr)
    save_accounts(accounts, args.out)
    for path in write_bundles(accounts, match, told, args.out):
        print(f"wrote {path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
