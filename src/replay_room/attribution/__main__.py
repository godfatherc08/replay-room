"""Print the causal account of every engine-eligible moment of a match.

    python -m replay_room.attribution data/fixtures/synthetic_match_01
    python -m replay_room.attribution data/fixtures/synthetic_match_01 --classes big_chance_saved
    python -m replay_room.attribution data/fixtures/synthetic_match_01 --json
    python -m replay_room.attribution data/fixtures/synthetic_match_01 --save   # data/accounts/<game>/<moment>.json
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from typing import TextIO

from replay_room.attribution.engine import attribute_match
from replay_room.attribution.store import ACCOUNTS_DIR, save_accounts
from replay_room.contracts.causal_account import CausalAccount
from replay_room.contracts.moment import EXPLAINED_CLASSES
from replay_room.detect.__main__ import parse_classes
from replay_room.ingest import load_match


def _ref(c) -> str:
    r = c.evidence[0]
    return f"event #{r.action_id}" if r.kind == "event" else f"frame {r.frame_id}"


def _metrics(c) -> str:
    return " ".join(f"{k}={v:.3f}" for k, v in c.metrics.items())


def format_account(a: CausalAccount) -> str:
    m, o = a.moment, a.outcome
    names = {t.team_id: t.name for t in a.teams}
    framing = "realized" if o.realized else "PREVENTED (a goal that didn't happen)"
    lines = [
        f"{m.moment_id}  {m.type}  [{m.period_id} {int(m.t_event // 60):02d}:{m.t_event % 60:04.1f}]  "
        f"{names[o.beneficiary_team_id]} v {names[o.conceding_team_id]}",
        f"  outcome: #{o.ref.action_id} V={o.value:.3f} ({o.value_source})  "
        f"{'scored' if o.scored else 'no goal'}  {framing}",
    ]
    h = a.headline
    lines.append(f"  headline: {h.contribution_id}  {h.role}  {h.player_id} {h.action or h.signal}  "
                 f"effect {h.effect:+.3f}  ({_ref(h)})")
    for c in a.contributions:
        lines.append(f"    {c.rank:>2}. {c.contribution_id:<10} {c.track:<8} {c.role:<16} "
                     f"{(c.action or c.signal):<24} {c.player_id:<7} {c.effect:+.3f}  {_ref(c):<13} {_metrics(c)}")
    for cf in a.counterfactuals:
        best = cf.best
        comp = f", completion {best.completion_prob:.2f}" if best.completion_prob is not None else ""
        lines.append(f"  counterfactual ({cf.contribution_id} @ frame {cf.decision_frame.frame_id}): chose "
                     f"{cf.chosen} worth {cf.chosen_value:.3f}; {best.description} was worth {best.value:.3f}{comp}")
    lines.append(f"  evidence: events {list(a.evidence.events)}  frames {list(a.evidence.frames)}")
    return "\n".join(lines)


def main(argv: list[str] | None = None, out: TextIO = sys.stdout) -> int:
    ap = argparse.ArgumentParser(prog="attribution", description="Causal accounts for a match's moments.")
    ap.add_argument("match", help="match directory (e.g. data/fixtures/synthetic_match_01)")
    ap.add_argument("--classes", type=parse_classes, default=EXPLAINED_CLASSES,
                    help="comma-separated explained classes (default: all explained classes)")
    ap.add_argument("--json", action="store_true", help="print the accounts as JSON")
    ap.add_argument("--save", nargs="?", const=str(ACCOUNTS_DIR), metavar="DIR",
                    help=f"write <DIR>/<game>/<moment>.json (default DIR: {ACCOUNTS_DIR})")
    args = ap.parse_args(argv)

    with warnings.catch_warnings():  # socceraction's VAEP feature code trips pandas FutureWarnings
        warnings.simplefilter("ignore", FutureWarning)
        accounts = attribute_match(load_match(args.match), args.classes)
    if args.save:
        for path in save_accounts(accounts, args.save):
            print(f"wrote {path}", file=sys.stderr)
    if args.json:
        print(json.dumps([a.model_dump(mode="json") for a in accounts], indent=2), file=out)
        return 0
    print(f"{len(accounts)} causal account(s)", file=out)
    for a in accounts:
        print(format_account(a), file=out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
