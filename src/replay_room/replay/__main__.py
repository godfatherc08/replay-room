"""Replay a match directory on the clock and print the stream.

    python -m replay_room.replay data/fixtures/synthetic_match_01 --speed 4
    python -m replay_room.replay data/fixtures/synthetic_match_01 --start p2:30 --instant

Keys while playing (Windows console): space pause/resume, + / - double/halve
speed, f / b seek +/-10 s, q quit.
"""

from __future__ import annotations

import argparse
import math
import sys
from collections.abc import Callable
from typing import TextIO

from replay_room.contracts.match import ContextEvent
from replay_room.contracts.spadl import SpadlAction
from replay_room.contracts.tracking import TrackingFrame
from replay_room.ingest.source import FeedItem, FileReplaySource
from replay_room.replay.clock import ReplayClock


def format_item(item: FeedItem) -> str:
    stamp = f"[{item.period_id} {int(item.t // 60):02d}:{item.t % 60:04.1f}]"
    p = item.payload
    if isinstance(p, SpadlAction):
        return (f"{stamp} ACTION  #{p.action_id:<4} {p.type_name:<12} {p.player_id:<7} "
                f"({p.start_x:5.1f},{p.start_y:4.1f})->({p.end_x:5.1f},{p.end_y:4.1f}) "
                f"{p.result_name:<7} {p.bodypart_name:<10} {p.original_event_id}")
    if isinstance(p, ContextEvent):
        who = p.player_id or ""
        if p.target_player_id:
            who += f" -> {p.target_player_id}"
        where = f"({p.x:5.1f},{p.y:4.1f})" if p.x is not None else ""
        return f"{stamp} CONTEXT {p.kind:<17} {who:<18} {where} {p.event_id}"
    if isinstance(p, TrackingFrame):
        ball = p.ball
        ball_txt = f"ball ({ball.x:5.1f},{ball.y:4.1f}) {math.hypot(ball.vx, ball.vy):4.1f} m/s" if ball else "no ball"
        return f"{stamp} FRAME   #{p.frame_id:<5} {ball_txt}  players={len(p.players)}"
    raise TypeError(type(p))


def parse_time(text: str, clock: ReplayClock) -> float:
    """'95.5' -> timeline seconds; 'p2:30' -> period 2, 30 s into it."""
    if text.lower().startswith("p"):
        period, _, t = text[1:].partition(":")
        try:
            return clock.timeline_t(int(period), float(t or 0))
        except (KeyError, ValueError):
            raise argparse.ArgumentTypeError(f"bad period time {text!r}") from None
    return float(text)


def _keyboard_controls(out: TextIO) -> Callable[[ReplayClock], bool | None] | None:
    try:
        import msvcrt  # Windows only
    except ImportError:
        return None
    if not sys.stdin.isatty():
        return None

    def on_tick(clock: ReplayClock) -> bool | None:
        while msvcrt.kbhit():
            key = msvcrt.getwch()
            if key == "q":
                return True
            if key == " ":
                clock.toggle()
                print(f"-- {'playing' if clock.playing else 'paused'}", file=out)
            elif key in "+=":
                clock.set_speed(clock.speed * 2)
                print(f"-- speed x{clock.speed:g}", file=out)
            elif key == "-":
                clock.set_speed(clock.speed / 2)
                print(f"-- speed x{clock.speed:g}", file=out)
            elif key in "fb":
                clock.seek(clock.position + (10 if key == "f" else -10))
                period, t = clock.period_t(clock.position)
                print(f"-- seek to period {period} {t:.1f}s", file=out)
        return None

    return on_tick


def main(argv: list[str] | None = None, out: TextIO = sys.stdout) -> int:
    ap = argparse.ArgumentParser(prog="replay", description="Replay a match on the clock.")
    ap.add_argument("match", help="match directory (e.g. data/fixtures/synthetic_match_01)")
    ap.add_argument("--speed", type=float, default=1.0, help="playback speed multiplier (default 1)")
    ap.add_argument("--start", default=None, help="seek before playing: timeline seconds, or pPERIOD:SECONDS (e.g. p2:30)")
    ap.add_argument("--end", default=None, help="stop at: timeline seconds, or pPERIOD:SECONDS")
    ap.add_argument("--frame-every", type=int, default=10,
                    help="print every Nth tracking frame (default 10 = 1 Hz at 10 Hz); 0 hides frames")
    ap.add_argument("--no-context", action="store_true", help="hide context events")
    ap.add_argument("--instant", action="store_true", help="ignore wall time; print the stream immediately")
    args = ap.parse_args(argv)

    source = FileReplaySource.from_path(args.match)
    clock = ReplayClock(source, speed=args.speed)
    try:
        start = parse_time(args.start, clock) if args.start else None
        end = parse_time(args.end, clock) if args.end else None
    except argparse.ArgumentTypeError as exc:
        ap.error(str(exc))
    meta = source.meta
    print(f"{meta.game_id}  {meta.home_team.name} v {meta.away_team.name}  ({meta.competition})", file=out)
    print(f"source={meta.source}  {meta.frame_rate_hz:g} Hz  duration={clock.duration:.0f}s  speed x{args.speed:g}",
          file=out)

    def printer(item: FeedItem) -> None:
        if item.kind == "frame":
            if args.frame_every <= 0 or item.payload.frame_id % args.frame_every:
                return
        elif item.kind == "context" and args.no_context:
            return
        print(format_item(item), file=out, flush=True)

    clock.subscribe(printer)
    if start is not None:
        clock.seek(start)

    if args.instant:
        clock.advance_to(end if end is not None else clock.duration)
        return 0

    keys = _keyboard_controls(out)
    if keys:
        print("keys: space pause/resume  +/- speed  f/b seek 10s  q quit", file=out)

    def on_tick(c: ReplayClock) -> bool | None:
        if end is not None and c.position >= end:
            return True
        return keys(c) if keys else None

    try:
        clock.run(on_tick=on_tick)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
