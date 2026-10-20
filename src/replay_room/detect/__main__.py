"""List a match's moments.

    python -m replay_room.detect data/fixtures/synthetic_match_01                 # explained classes
    python -m replay_room.detect data/fixtures/synthetic_match_01 --classes goal,penalty
    python -m replay_room.detect data/fixtures/synthetic_match_01 --classes all   # + flagged classes
    python -m replay_room.detect data/fixtures/synthetic_match_01 --json
    python -m replay_room.detect data/fixtures/synthetic_match_01 --stream        # goals, via the replay clock
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from typing import TextIO

from replay_room.contracts.match import MatchMeta
from replay_room.contracts.moment import EXPLAINED_CLASSES, FLAGGED_CLASSES, MomentContext
from replay_room.detect.dispatch import ALL_CLASSES, detect_moments
from replay_room.detect.moments import StreamingGoalDetector
from replay_room.ingest import FileReplaySource, load_match
from replay_room.replay import ReplayClock

CLASS_GROUPS = {"all": ALL_CLASSES, "explained": EXPLAINED_CLASSES, "flagged": FLAGGED_CLASSES}


def detect_streaming(path: str) -> tuple[MatchMeta, list[MomentContext]]:
    """Run the goal detector over the replay stream (clock advanced without wall time)."""
    found: list[MomentContext] = []
    detector = StreamingGoalDetector(found.append)
    source = FileReplaySource.from_path(path)
    clock = ReplayClock(source)
    detector.attach(clock)
    clock.advance_to(clock.duration)
    detector.finish()
    return source.meta, found


def parse_classes(text: str) -> tuple[str, ...]:
    out: list[str] = []
    for name in (s.strip() for s in text.split(",") if s.strip()):
        out += CLASS_GROUPS.get(name, (name,))
    unknown = [c for c in out if c not in ALL_CLASSES]
    if unknown:
        raise argparse.ArgumentTypeError(
            f"unknown class {', '.join(unknown)} (choose from {', '.join(ALL_CLASSES)}, or all/explained/flagged)")
    return tuple(dict.fromkeys(out))


def format_moment(ctx: MomentContext, names: dict[str, str]) -> str:
    m = ctx.moment
    clock = f"[{m.period_id} {int(m.t_event // 60):02d}:{m.t_event % 60:04.1f}]"
    key = m.key_event_ref.original_event_id if m.key_event_ref.kind == "event" else m.key_event_ref.event_id
    if m.attacking_team_id is not None:
        teams = f"{names.get(m.attacking_team_id, m.attacking_team_id)} v " \
                f"{names.get(m.defending_team_id, m.defending_team_id)}"
    else:
        teams = names.get(m.team_id, m.team_id) if m.team_id else "-"
    player = f"  player {m.key_player_id}{' (own goal)' if m.is_own_goal else ''}" if m.key_player_id else ""
    detail = f"  ({m.detail})" if m.detail else ""
    eligible = "engine_eligible" if m.engine_eligible else "flagged: not explained"
    lines = [f"{m.moment_id}  {m.type}  {clock}  {teams}{player}  key {key}{detail}  {eligible}"]
    if m.chain:
        turnover = f"after {m.turnover_event_ref.original_event_id}" if m.turnover_event_ref else ""
        contested = f"  contested={list(m.contested_action_ids)}" if m.contested_action_ids else ""
        lines.append(f"    chain: {len(m.chain)} actions #{m.chain[0].action_id}..#{m.chain[-1].action_id}  "
                     f"from {m.chain_start} {turnover} at {m.chain[0].time_seconds:.1f}s{contested}")
    if m.window is not None:
        w = m.window
        lines.append(f"    window: frames {w.frame_start}..{w.frame_end} ({w.n_frames})  "
                     f"t {w.t_start:.1f}..{w.t_end:.1f}s  ({m.t_event - w.t_start:.1f}s before the key event)")
    if m.outcome_ref is not None:
        xg = f"  xG {m.outcome_xg:.3f}" if m.outcome_xg is not None else ""
        also = f"  also {', '.join(m.secondary_types)}" if m.secondary_types else ""
        lines.append(f"    outcome: {m.outcome_ref.original_event_id} "
                     f"{'scored' if m.outcome_scored else 'no goal'}{xg}{also}")
    return "\n".join(lines)


def main(argv: list[str] | None = None, out: TextIO = sys.stdout) -> int:
    ap = argparse.ArgumentParser(prog="detect", description="List a match's moments.")
    ap.add_argument("match", help="match directory (e.g. data/fixtures/synthetic_match_01)")
    ap.add_argument("--classes", type=parse_classes, default=None,
                    help="comma-separated moment classes, or all / explained / flagged (default: explained)")
    ap.add_argument("--json", action="store_true", help="print the Moment contracts as JSON")
    ap.add_argument("--stream", action="store_true",
                    help="detect goals from the replay-clock stream instead of batch (goal class only)")
    args = ap.parse_args(argv)

    if args.stream:
        if args.classes not in (None, ("goal",)):
            ap.error("--stream detects goals only; drop --classes or use --classes goal")
        meta, moments = detect_streaming(args.match)
    else:
        match = load_match(args.match)
        moments = detect_moments(match.actions, match.tracking, match.meta,
                                 args.classes or EXPLAINED_CLASSES, match.context)
        meta = match.meta

    if args.json:
        print(json.dumps([ctx.moment.model_dump(mode="json") for ctx in moments], indent=2), file=out)
        return 0
    names = {t.team_id: t.name for t in (meta.home_team, meta.away_team)}
    counts = Counter(ctx.moment.type for ctx in moments)
    summary = ", ".join(f"{c} {counts[c]}" for c in ALL_CLASSES if counts[c])
    print(f"{meta.game_id}: {len(moments)} moment(s){'  ' + summary if summary else ''}", file=out)
    for ctx in moments:
        print(format_moment(ctx, names), file=out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
