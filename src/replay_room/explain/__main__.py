"""Narrate saved causal accounts (the rule plan, without match context; the agents add context).

    python -m replay_room.explain data/accounts/SYN-0007/SYN-0007-big_chance_saved-3.json
    python -m replay_room.explain data/accounts/SYN-0007/*[0-9].json --mode template
    python -m replay_room.explain <account.json> --json          # the full Narration
    python -m replay_room.explain <account.json> --refresh       # ignore the cache, ask Foundry again
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import TextIO

from replay_room.attribution.store import load_account
from replay_room.explain.narrate import narrate
from replay_room.explain.schema import Narration


def format_narration(n: Narration) -> str:
    source = n.source if n.source == "template" else f"foundry ({n.model}, attempt {n.attempts})"
    lines = [f"{n.moment_id}  [{n.framing}]  plan: {n.plan_source}  source: {source}"]
    if n.fallback_reason:
        lines.append(f"  fallback: {n.fallback_reason}")
    for k, errors in enumerate(n.rejections, start=1):
        lines.append(f"  rejected attempt {k}: " + "; ".join(errors))
    lines.append(f"  HEADLINE: {n.headline}")
    if n.headline_fan != n.headline:
        lines.append(f"       fan: {n.headline_fan}")
    for b in n.beats:
        refs = ", ".join(f"event #{r.action_id}" if r.kind == "event" else f"frame {r.frame_id}" for r in b.refs)
        lines.append(f"  {b.index + 1:>2}. [{b.kind}] {b.text}  [{refs} @ {b.t:.1f}s]")
        if b.fan != b.text:
            lines.append(f"      fan: {b.fan}")
    return "\n".join(lines)


def main(argv: list[str] | None = None, out: TextIO = sys.stdout) -> int:
    ap = argparse.ArgumentParser(prog="explain", description="Grounded narration of causal accounts.")
    ap.add_argument("accounts", nargs="+", help="causal account JSON file(s) (data/accounts/<game>/<moment>.json)")
    ap.add_argument("--mode", choices=["foundry", "template"], default="foundry")
    ap.add_argument("--refresh", action="store_true", help="ignore cached Foundry narrations")
    ap.add_argument("--json", action="store_true", help="print the Narration objects as JSON")
    args = ap.parse_args(argv)
    narrations = [narrate(load_account(p), args.mode, refresh=args.refresh) for p in args.accounts]
    if args.json:
        print(json.dumps([n.model_dump(mode="json") for n in narrations], indent=2, ensure_ascii=False), file=out)
    else:
        print("\n\n".join(format_narration(n) for n in narrations), file=out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
