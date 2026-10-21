"""Narrate saved causal accounts.

    python -m replay_room.explain data/accounts/SYN-0007/SYN-0007-big_chance_saved-3.json
    python -m replay_room.explain data/accounts/SYN-0007/*[0-9].json --mode template
    python -m replay_room.explain <account.json> --json          # the full Narration (sentences + timed overlay)
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
    lines = [f"{n.moment_id}  [{n.framing}]  source: {source}"]
    if n.fallback_reason:
        lines.append(f"  fallback: {n.fallback_reason}")
    for k, errors in enumerate(n.rejections, start=1):
        lines.append(f"  rejected attempt {k}: " + "; ".join(errors))
    lines.append(f"  HEADLINE: {n.headline_text}")
    for s in n.sentences:
        ref = f"event #{s.ref.action_id}" if s.ref.kind == "event" else f"frame {s.ref.frame_id}"
        lines.append(f"  {s.index + 1:>2}. {s.text}  [{s.contribution_id} -> {ref} @ {s.t:.1f}s]")
    lines.append("  timed overlay:")
    for c in n.timed_overlay:
        lines.append(f"    P{c.period_id} {c.t_start:6.1f}-{c.t_end:6.1f}s  sentence {c.sentence_index + 1}  "
                     f"{'frame ' + str(c.frame_id) if c.frame_id is not None else 'event #' + str(c.action_id)}")
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
