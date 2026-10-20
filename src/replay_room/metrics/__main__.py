"""Print each goal moment's valued chain and a per-frame pitch-control summary.

    python -m replay_room.metrics data/fixtures/synthetic_match_01
    python -m replay_room.metrics data/fixtures/synthetic_match_01 --frame-every 5

Models come from data/models/ (train with ``python -m replay_room.metrics.train``).
"""

from __future__ import annotations

import argparse
import sys
from typing import TextIO

from replay_room.contracts.values import ValuedMoment
from replay_room.detect import detect_goal_moments
from replay_room.ingest import load_match
from replay_room.metrics.models import load_models
from replay_room.metrics.valuation import rate_actions, value_moment


def _num(v: float | None, fmt: str = "+.3f") -> str:
    return "     -" if v is None else format(v, fmt).rjust(6)


def format_valued(vm: ValuedMoment, frame_every: int) -> str:
    m = vm.moment
    lines = [f"{m.moment_id}  [{m.period_id} {m.t_event:.1f}s]  {m.attacking_team_id} scorer {m.key_player_id}  "
             f"on-ball signal: {vm.on_ball_signal}",
             f"  {'action':<30} {'value':>6} {'dxT':>6} {'vaep':>6} {'xG':>6} {'pass%':>6}"]
    for va in vm.actions:
        a = va.action
        label = f"#{a.action_id} {a.player_id} {a.type_name} {'' if a.result_name == 'success' else a.result_name}"
        lines.append(f"  {label:<30} {_num(va.value)} {_num(va.xt_delta)} {_num(va.vaep)} {_num(va.xg, '.3f')} "
                     f"{_num(va.pass_completion, '.2f')}")
    s = vm.surfaces
    lines.append(f"  pitch control ({len(s)} frames, {s[0].timestamp:.1f}-{s[-1].timestamp:.1f}s, "
                 f"{m.attacking_team_id} perspective):  t  share  box  space")
    for i, surf in enumerate(s):
        if frame_every > 0 and (i % frame_every == 0 or i == len(s) - 1):
            lines.append(f"    #{surf.frame_id:<5} {surf.timestamp:6.1f}  {surf.control_share:.2f}  "
                         f"{surf.box_control:.2f}  {surf.space_value:.3f}")
    return "\n".join(lines)


def main(argv: list[str] | None = None, out: TextIO = sys.stdout) -> int:
    ap = argparse.ArgumentParser(prog="metrics", description="Value a match's goal moments.")
    ap.add_argument("match", help="match directory (e.g. data/fixtures/synthetic_match_01)")
    ap.add_argument("--frame-every", type=int, default=10, help="print every Nth frame summary (0 = none)")
    args = ap.parse_args(argv)

    match = load_match(args.match)
    models = load_models()
    action_values = rate_actions(match.actions, match.tracking, match.meta, match.context, models,
                                 match.pass_targets)
    moments = detect_goal_moments(match.actions, match.tracking)
    print(f"{match.meta.game_id}: {len(moments)} goal moment(s); models: corpus {models.manifest['corpus']}, "
          f"authoritative on-ball signal = {models.on_ball_signal}", file=out)
    for ctx in moments:
        vm = value_moment(ctx.moment, match.actions, ctx.frames, match.meta, match.context, models, action_values)
        print(format_valued(vm, args.frame_every), file=out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
