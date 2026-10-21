"""Attribute a match and export one viewer bundle per moment.

    python -m replay_room.render data/fixtures/synthetic_match_01
    python -m replay_room.render data/fixtures/synthetic_match_01 --out viewer/public/bundles

Writes ``<out>/<game>/<moment>.json`` (the account), ``<moment>.bundle.json``
(account + window tracking + pitch meta) and ``<out>/index.json``.
"""

from __future__ import annotations

import argparse
import sys
import warnings

from replay_room.attribution.engine import attribute_match
from replay_room.attribution.store import ACCOUNTS_DIR, save_accounts
from replay_room.contracts.moment import EXPLAINED_CLASSES
from replay_room.detect.__main__ import parse_classes
from replay_room.ingest import load_match
from replay_room.render.export import write_bundles


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="render", description="Export viewer bundles for a match's moments.")
    ap.add_argument("match", help="match directory (e.g. data/fixtures/synthetic_match_01)")
    ap.add_argument("--classes", type=parse_classes, default=EXPLAINED_CLASSES)
    ap.add_argument("--out", default=str(ACCOUNTS_DIR), help=f"output root (default {ACCOUNTS_DIR})")
    args = ap.parse_args(argv)
    match = load_match(args.match)
    with warnings.catch_warnings():  # socceraction's VAEP feature code trips pandas FutureWarnings
        warnings.simplefilter("ignore", FutureWarning)
        accounts = attribute_match(match, args.classes)
    save_accounts(accounts, args.out)
    for path in write_bundles(accounts, match, args.out):
        print(f"wrote {path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
