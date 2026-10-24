"""Run the agentic pipeline end to end and print what every agent did.

    python -m replay_room.agents                                   # Scout menu + the hero moment, in-process
    python -m replay_room.agents --via-mcp                         # the engine over its MCP server (stdio)
    python -m replay_room.agents --moment SYN-0007-goal-1 --focus-team NBR --language fr
    python -m replay_room.agents --mode template                   # no model at all (rules plan + composer)
    python -m replay_room.agents --json                            # the full result

Foundry (Analyst + Storyteller) is used when FOUNDRY_PROJECT_ENDPOINT and
FOUNDRY_MODEL_DEPLOYMENT are set; otherwise every model step falls back to its
deterministic floor and the trace says so.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TextIO

from replay_room.agents.engine import InProcessEngine, McpEngine
from replay_room.agents.orchestrator import Orchestrator
from replay_room.agents.sources import stream_from_env
from replay_room.mcp_server.service import DEFAULT_MATCH

HERO = "SYN-0007-big_chance_saved-3"


def main(argv: list[str] | None = None, out: TextIO = sys.stdout) -> int:
    ap = argparse.ArgumentParser(prog="replay_room.agents", description="Replay Room's agents, end to end.")
    ap.add_argument("--match", default=str(DEFAULT_MATCH))
    ap.add_argument("--moment", default=HERO)
    ap.add_argument("--mode", choices=["foundry", "template"], default="foundry")
    ap.add_argument("--via-mcp", action="store_true", help="reach the engine through its MCP server")
    ap.add_argument("--language", default="en")
    ap.add_argument("--focus-team")
    ap.add_argument("--focus-player")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if hasattr(out, "reconfigure"):
        out.reconfigure(encoding="utf-8")

    engine = McpEngine(args.match) if args.via_mcp else InProcessEngine(args.match)
    try:
        picked = stream_from_env(Path(args.match))
        orch = Orchestrator(engine, picked.source, mode=args.mode)
        if picked.fallback_reason:
            orch.log("Sources", "stream: local fallback", picked.fallback_reason)
        menu = orch.scout()
        result = orch.explain(args.moment, language=args.language, focus_team_id=args.focus_team,
                              focus_player_id=args.focus_player)
    finally:
        if isinstance(engine, McpEngine):
            engine.close()

    if args.json:
        print(json.dumps({
            "menu": [m.__dict__ for m in menu],
            "trace": [s.__dict__ for s in orch.trace],
            "plan": result.plan.model_dump(mode="json") if result.plan else None,
            "narration": result.narration.model_dump(mode="json") if result.narration else None,
            "editions": {k: e.model_dump(mode="json") for k, e in result.editions.items()},
        }, indent=2, ensure_ascii=False), file=out)
        return 0
    print("SCOUT MENU", file=out)
    for m in menu:
        tag = "explain" if m.explainable else "describe only"
        print(f"  [{tag:>13}] {m.description}" + (f"  ({m.why_not_explained})" if m.why_not_explained else ""), file=out)
    print("\nTRACE", file=out)
    for s in orch.trace:
        print(f"  {s.agent:<12} {s.action}\n  {'':<12}   -> {s.detail}", file=out)
    for register, ed in result.editions.items():
        print(f"\n{register.upper()} EDITION ({ed.language}, {ed.perspective})\n  {ed.headline}", file=out)
        for b in ed.beats:
            print(f"  {'*' if b.highlighted else '-'} {b.text}", file=out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
