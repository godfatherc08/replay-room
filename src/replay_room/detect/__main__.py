"""List a match's goal moments.

    python -m replay_room.detect data/fixtures/synthetic_match_01
    python -m replay_room.detect data/fixtures/synthetic_match_01 --json
    python -m replay_room.detect data/fixtures/synthetic_match_01 --stream   # via the replay clock
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import TextIO

from replay_room.contracts.match import MatchMeta
from replay_room.contracts.moment import MomentContext
from replay_room.detect.moments import StreamingGoalDetector, detect_goal_moments
from replay_room.ingest import FileReplaySource, load_match
from replay_room.replay import ReplayClock


def detect_streaming(path: str) -> tuple[MatchMeta, list[MomentContext]]:
    """Run the detector over the replay stream (clock advanced without wall time)."""
    found: list[MomentContext] = []
    detector = StreamingGoalDetector(found.append)
    source = FileReplaySource.from_path(path)
    clock = ReplayClock(source)
    detector.attach(clock)
    clock.advance_to(clock.duration)
    detector.finish()
    return source.meta, found


def format_moment(ctx: MomentContext, names: dict[str, str]) -> str:
    m = ctx.moment
    w = m.window
    turnover = f"after {m.turnover_event_ref.original_event_id}" if m.turnover_event_ref else ""
    contested = f"  contested={list(m.contested_action_ids)}" if m.contested_action_ids else ""
    return (
        f"{m.moment_id}  [{m.period_id} {int(m.t_event // 60):02d}:{m.t_event % 60:04.1f}]  "
        f"{names.get(m.attacking_team_id, m.attacking_team_id)} v {names.get(m.defending_team_id, m.defending_team_id)}  "
        f"scorer {m.key_player_id}{' (own goal)' if m.is_own_goal else ''}  key {m.key_event_ref.original_event_id}\n"
        f"    chain: {len(m.chain)} actions #{m.chain[0].action_id}..#{m.chain[-1].action_id}  "
        f"from {m.chain_start} {turnover} at {m.chain[0].time_seconds:.1f}s{contested}\n"
        f"    window: frames {w.frame_start}..{w.frame_end} ({w.n_frames})  "
        f"t {w.t_start:.1f}..{w.t_end:.1f}s  ({m.t_event - w.t_start:.1f}s before the goal)"
    )


def main(argv: list[str] | None = None, out: TextIO = sys.stdout) -> int:
    ap = argparse.ArgumentParser(prog="detect", description="List a match's goal moments.")
    ap.add_argument("match", help="match directory (e.g. data/fixtures/synthetic_match_01)")
    ap.add_argument("--json", action="store_true", help="print the Moment contracts as JSON")
    ap.add_argument("--stream", action="store_true", help="detect from the replay-clock stream instead of batch")
    args = ap.parse_args(argv)

    if args.stream:
        meta, moments = detect_streaming(args.match)
    else:
        match = load_match(args.match)
        moments = detect_goal_moments(match.actions, match.tracking)
        meta = match.meta

    if args.json:
        print(json.dumps([ctx.moment.model_dump(mode="json") for ctx in moments], indent=2), file=out)
        return 0
    names = {t.team_id: t.name for t in (meta.home_team, meta.away_team)}
    print(f"{meta.game_id}: {len(moments)} goal moment(s)", file=out)
    for ctx in moments:
        print(format_moment(ctx, names), file=out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
