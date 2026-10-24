"""Off-ball causal links: why a defender's space went, measured on the tracking (never inferred).

For each kept off-ball fact of a *defending* player D (``space_conceded`` or
``marking_break``), over the span ``a..b`` its rise in share was measured on:

* **marking assignment**: D's man M is the outfield attacker nearest him at
  frame ``a`` (the nearest-defender rule, read from his side), if within
  ``MARK_RADIUS``; further away, D was marking no one;
* **the runner**: an outfield attacker R that D moved *with*: both moved at
  least ``RUN_M`` / ``DRAG_M`` over the span, in directions within
  ``FOLLOW_COS`` of each other, and D stayed within ``FOLLOW_M`` of R on
  average. R is the attacker who took him somewhere;
* **the zone**: where the key event happened (the spot D's share was measured
  at), named by pitch area (``zone_name``); D *vacated* it when his distance to
  the spot grew by ``VACATE_M`` or more;
* **what used it**: the first attacking action of the chain from frame ``a`` on
  that arrived within ``ZONE_RADIUS`` of the spot (a pass or carry by its end,
  a shot by its start).

A link is emitted only when one of these patterns holds, in this order:

* ``decoy_run``: R is not M, and D's separation from M grew by at least
  ``MARK_GAIN_M``: R's run took D away from his man;
* ``dragged_out``: D followed R (his man or another) and vacated the zone;
* ``run_past``: D vacated the zone while an outfield attacker ran towards it,
  closing on the spot by ``RUN_M`` or more and passing within ``PASS_M`` of D
  on the way: the runner went past him into the space he left (the nearest
  such pass names the runner);
* ``lost_man``: no runner, D's separation from M grew by ``MARK_GAIN_M`` and M
  ended nearer the spot than he started.

Otherwise there is no link, and downstream may show the facts side by side but
never assert a connection between them.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from replay_room.attribution.off_ball import MARK_GAIN_M, SPOT_SIGMA
from replay_room.attribution.outcome import Candidate
from replay_room.attribution.zones import zone_name
from replay_room.contracts.causal_account import Link
from replay_room.contracts.moment import Moment
from replay_room.contracts.pitch import BALL_ID
from replay_room.contracts.refs import EventRef, FrameRef
from replay_room.detect.possessions import SHOT_TYPES

RUN_M = 4.0  # m the runner covers over the span
DRAG_M = 3.0  # m the defender covers with him
FOLLOW_COS = 0.7  # cos of the angle between their movements
FOLLOW_M = 6.0  # m, mean distance while he went with him
VACATE_M = 2.0  # m further from the spot at the end of the span
MARK_RADIUS = 10.0  # m, a nearest attacker further away than this is not his man
PASS_M = 6.0  # m, a runner this close to the defender on his way to the spot went past him
ZONE_RADIUS = 2 * SPOT_SIGMA  # m, an action arriving this close to the spot used the zone

def _arrival(row: pd.Series) -> tuple[float, float]:
    if row["type_name"] in SHOT_TYPES:
        return float(row["start_x"]), float(row["start_y"])
    return float(row["end_x"]), float(row["end_y"])


def _enabled(m: Moment, actions: pd.DataFrame, t_from: float, spot: np.ndarray) -> pd.Series | None:
    chain = actions[actions["action_id"].isin(m.chain_action_ids) & (actions["team_id"] == m.attacking_team_id)
                    & (actions["time_seconds"] >= t_from - 1e-6)].sort_values("action_id")
    for _, row in chain.iterrows():
        if np.hypot(*(np.asarray(_arrival(row)) - spot)) <= ZONE_RADIUS:
            return row
    return None


def _ran_past(pos: pd.DataFrame, span: list[int], defender: str, attackers: pd.Index,
              target: np.ndarray) -> tuple[str, float] | None:
    """The attacker who closed on the spot by ``RUN_M`` and came nearest the defender on the way (if within ``PASS_M``)."""
    me = pos.xs(defender, level=1).loc[span, ["x", "y"]].to_numpy(float)
    best = None
    for rid in attackers:
        path = pos.xs(rid, level=1).loc[span, ["x", "y"]].to_numpy(float)
        if np.hypot(*(path[0] - target)) - np.hypot(*(path[-1] - target)) < RUN_M:
            continue
        closest = float(np.hypot(*(path - me).T).min())
        if closest <= PASS_M and (best is None or closest < best[1]):
            best = (str(rid), closest)
    return best


def links_for(m: Moment, kept: list[Candidate], frames: pd.DataFrame, actions: pd.DataFrame,
              spot: tuple[float, float], attacking_home: bool,
              goalkeepers: frozenset[str] = frozenset()) -> tuple[Link, ...]:
    pos = frames[frames["player_id"] != BALL_ID].set_index(["frame_id", "player_id"]).sort_index()
    stamps = frames.drop_duplicates("frame_id").set_index("frame_id")["timestamp"]
    keys = {c.key for c in kept}
    contribution_of_event = {c.evidence[0].action_id: c.key for c in kept if c.track == "on_ball"}
    target = np.asarray(spot, float)
    out = []
    for c in kept:
        if c.track != "off_ball" or c.team_id != m.defending_team_id or c.span is None:
            continue
        a, b = c.span
        at_a, at_b = pos.loc[a], pos.loc[b]
        d_a, d_b = at_a.loc[c.player_id, ["x", "y"]].to_numpy(float), at_b.loc[c.player_id, ["x", "y"]].to_numpy(float)
        rivals = at_a[(at_a["team_id"] == m.attacking_team_id) & ~at_a.index.isin(goalkeepers)]
        gaps = np.hypot(rivals["x"] - d_a[0], rivals["y"] - d_a[1])
        man = str(gaps.idxmin()) if float(gaps.min()) <= MARK_RADIUS else None
        nearest = str(gaps.idxmin())
        sep_a = float(gaps.min())
        sep_b = float(np.hypot(*(at_b.loc[nearest, ["x", "y"]].to_numpy(float) - d_b)))
        d_move = d_b - d_a
        span = [f for f in stamps.index if a <= f <= b]

        runner, follow = None, np.inf
        if np.hypot(*d_move) >= DRAG_M:
            for rid in rivals.index:
                r_a, r_b = at_a.loc[rid, ["x", "y"]].to_numpy(float), at_b.loc[rid, ["x", "y"]].to_numpy(float)
                r_move = r_b - r_a
                if np.hypot(*r_move) < RUN_M:
                    continue
                cos = float(d_move @ r_move / (np.hypot(*d_move) * np.hypot(*r_move)))
                mean = float(np.mean([np.hypot(*(pos.loc[(f, rid), ["x", "y"]].to_numpy(float)
                                                  - pos.loc[(f, c.player_id), ["x", "y"]].to_numpy(float)))
                                      for f in span]))
                if cos >= FOLLOW_COS and mean <= FOLLOW_M and mean < follow:
                    runner, follow = str(rid), mean

        away_a, away_b = float(np.hypot(*(d_a - target))), float(np.hypot(*(d_b - target)))
        man_a = float(np.hypot(*(at_a.loc[nearest, ["x", "y"]].to_numpy(float) - target)))
        man_b = float(np.hypot(*(at_b.loc[nearest, ["x", "y"]].to_numpy(float) - target)))
        vacated = away_b - away_a >= VACATE_M
        if runner is not None and man is not None and runner != man and sep_b - sep_a >= MARK_GAIN_M:
            kind = "decoy_run"
        elif runner is not None and vacated:
            kind = "dragged_out"
        elif vacated and (past := _ran_past(pos, span, c.player_id, rivals.index, target)) is not None:
            kind, runner, follow = "run_past", past[0], past[1]
        elif runner is None and man is not None and sep_b - sep_a >= MARK_GAIN_M and man_b < man_a:
            kind = "lost_man"
        else:
            continue

        used = _enabled(m, actions, float(stamps[a]), target)
        enabled = None if used is None else EventRef(
            action_id=int(used["action_id"]), original_event_id=str(used["original_event_id"]),
            period_id=int(used["period_id"]), time_seconds=float(used["time_seconds"]))
        named = tuple(p for p in (c.player_id, man, runner) if p is not None)
        metrics = {"defender_moved": round(float(np.hypot(*d_move)), 3),
                   "spot_distance_start": round(away_a, 3), "spot_distance_end": round(away_b, 3)}
        if man is not None:
            metrics |= {"separation_start": round(sep_a, 3), "separation_end": round(sep_b, 3)}
        if runner is not None:
            metrics["closest_approach" if kind == "run_past" else "follow_distance"] = round(follow, 3)
        out.append(Link(
            link_id=f"L{c.player_id}", kind=kind, defender_contribution_id=c.key, defender_id=c.player_id,
            marked_player_id=man, runner_id=runner,
            runner_contribution_id=f"s{runner}" if runner is not None and f"s{runner}" in keys else None,
            zone=zone_name(*spot, attacking_home), enabled=enabled,
            enabled_contribution_id=None if enabled is None else contribution_of_event.get(enabled.action_id),
            metrics=metrics,
            evidence=(FrameRef(frame_id=a, timestamp=float(stamps[a]), player_ids=named),
                      FrameRef(frame_id=b, timestamp=float(stamps[b]), player_ids=named)),
        ))
    return tuple(out)
