"""Grounded counterfactual: was a better option actually available?

At the frame of a decision (the assist and the finish), every option the
player had is valued from the real positions with Build 3's models:

* **pass to a teammate**: Build 3's pass-completion model on that pass (the
  teammate led by their velocity, as ``metrics.pass_value`` aims passes; lane
  and receiver gaps from the opponents in that frame; the passer's pressure
  flag) times the attacking team's xT at the receiving point;
* **shoot**: Build 3's xG at the player's location.

The chosen action is valued the same way (a pass by its intended receiver
when known, else at its end point), so chosen and alternatives are directly
comparable. A counterfactual is emitted only when the best alternative beats
the chosen value by ``COUNTERFACTUAL_MARGIN``; the alternatives listed are those
that beat the choice, best first (at most ``MAX_ALTERNATIVES``).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from replay_room.attribution.outcome import threat_at
from replay_room.contracts.causal_account import Alternative, Counterfactual
from replay_room.contracts.match import MatchMeta
from replay_room.contracts.pitch import BALL_ID, PITCH_LENGTH, PITCH_WIDTH
from replay_room.contracts.refs import FrameRef
from replay_room.contracts.tracking import TRACKING_COLUMNS
from replay_room.metrics.models import MetricModels
from replay_room.metrics.orientation import orient
from replay_room.metrics.pass_value import GAP_CAP, LEAD_SPEED, PASS_TYPES, frame_ids_at, segment_gap

COUNTERFACTUAL_MARGIN = 0.05
MAX_ALTERNATIVES = 3
_OPTION_COLUMNS = ("game_id", "team_id", "player_id", "type_name", "result_name", "bodypart_name",
                   "start_x", "start_y", "end_x", "end_y", "intended_end_x", "intended_end_y",
                   "lane_gap", "receiver_gap", "under_pressure")


def _options(action: pd.Series, frame: pd.DataFrame, pressured: bool, goalkeepers: frozenset[str]) -> pd.DataFrame:
    """One row per pass the actor could have played in this frame (absolute frame), plus a shot."""
    players = frame[frame["player_id"] != BALL_ID]
    me = players[players["player_id"] == action["player_id"]]
    start = me[["x", "y"]].to_numpy(float)[0] if len(me) else np.array([action["start_x"], action["start_y"]])
    mates = players[(players["team_id"] == action["team_id"]) & (players["player_id"] != action["player_id"])
                    & ~players["player_id"].isin(goalkeepers)]
    opp = players[players["team_id"] != action["team_id"]][["x", "y"]].to_numpy(float)
    rows = []
    for mate in mates.itertuples(index=False):
        pos, vel = np.array([mate.x, mate.y]), np.array([mate.vx, mate.vy])
        aim = np.clip(pos + vel * (np.hypot(*(pos - start)) / LEAD_SPEED), [0, 0], [PITCH_LENGTH, PITCH_WIDTH])
        rows.append({"player_id": action["player_id"], "target": mate.player_id, "type_name": "pass",
                     "end_x": aim[0], "end_y": aim[1], "intended_end_x": aim[0], "intended_end_y": aim[1],
                     "lane_gap": float(segment_gap(opp, start, aim).min()) if len(opp) else GAP_CAP,
                     "receiver_gap": float(np.hypot(*(opp - aim).T).min()) if len(opp) else GAP_CAP})
    rows.append({"player_id": action["player_id"], "target": None, "type_name": "shot",
                 "end_x": start[0], "end_y": start[1], "intended_end_x": np.nan, "intended_end_y": np.nan,
                 "lane_gap": np.nan, "receiver_gap": np.nan})
    df = pd.DataFrame(rows)
    df["game_id"], df["team_id"], df["result_name"], df["bodypart_name"] = (
        action["game_id"], action["team_id"], "success", "foot")
    df["start_x"], df["start_y"], df["under_pressure"] = start[0], start[1], pressured
    return df


def value_options(action: pd.Series, frame: pd.DataFrame, pressured: bool, meta: MatchMeta, models: MetricModels,
                  goalkeepers: frozenset[str] = frozenset()) -> pd.DataFrame:
    """Every option at this frame with ``completion`` (passes) and ``value``, best first."""
    opts = _options(action, frame, pressured, goalkeepers)
    attacking_home = action["team_id"] == meta.home_team_id
    ltr = orient(opts[list(_OPTION_COLUMNS)], meta.home_team_id, check_home=False)
    completion = models.passes.predict(ltr)
    xg = models.xg.predict(ltr)
    threat = [threat_at(models.xt, x, y, attacking_home) for x, y in zip(opts["end_x"], opts["end_y"])]
    is_pass = (opts["type_name"] == "pass").to_numpy()
    opts["completion"] = np.where(is_pass, completion.to_numpy(), np.nan)
    opts["value"] = np.where(is_pass, opts["completion"] * np.asarray(threat), xg.to_numpy())
    return opts.sort_values(["value", "target"], ascending=[False, True], na_position="last").reset_index(drop=True)


def counterfactual_for(
    contribution_id: str,
    action: pd.Series,
    action_value: pd.Series,
    tracking: pd.DataFrame,
    window: tuple[int, int],
    pressured: bool,
    meta: MatchMeta,
    models: MetricModels,
    goalkeepers: frozenset[str] = frozenset(),
) -> Counterfactual | None:
    """The counterfactual for one pass or shot, or None if nothing available beat it by the margin."""
    fid = int(frame_ids_at(tracking, pd.Series([action["period_id"]]), pd.Series([action["time_seconds"]]))[0])
    if not window[0] <= fid <= window[1]:
        return None
    frame = tracking[tracking["frame_id"] == fid][list(TRACKING_COLUMNS)]
    opts = value_options(action, frame, pressured, meta, models, goalkeepers)
    if action["type_name"] in PASS_TYPES:
        receiver = action_value.get("pass_receiver_id")
        mine = opts[(opts["type_name"] == "pass") & (opts["target"] == receiver)] if receiver else opts.iloc[0:0]
        if len(mine):
            chosen_value, chosen, others = float(mine["value"].iloc[0]), f"pass to {receiver}", opts.drop(mine.index)
        else:  # receiver unknown: value the pass at the point it reached
            chosen_value = float(action_value["pass_completion"]) * threat_at(
                models.xt, float(action["end_x"]), float(action["end_y"]), action["team_id"] == meta.home_team_id)
            chosen, others = "pass", opts
    else:
        chosen_value, chosen, others = float(action_value["xg"]), "shot", opts[opts["type_name"] == "pass"]
    better = others[others["value"] >= chosen_value + 1e-12].head(MAX_ALTERNATIVES)
    if better.empty or float(better["value"].iloc[0]) - chosen_value < COUNTERFACTUAL_MARGIN:
        return None
    ts = float(frame["timestamp"].iloc[0])
    alternatives = tuple(
        Alternative(
            description=f"pass to {o.target}" if o.type_name == "pass" else "shot",
            target_player_id=o.target if o.type_name == "pass" else None,
            completion_prob=None if np.isnan(o.completion) else round(float(o.completion), 4),
            value=float(o.value),
            evidence=(FrameRef(frame_id=fid, timestamp=ts,
                               player_ids=tuple(p for p in (str(action["player_id"]), o.target) if p)),),
        )
        for o in better.itertuples(index=False)
    )
    return Counterfactual(
        contribution_id=contribution_id,
        decision_frame=FrameRef(frame_id=fid, timestamp=ts, player_ids=(str(action["player_id"]),)),
        chosen=chosen, chosen_value=chosen_value, alternatives=alternatives,
    )
