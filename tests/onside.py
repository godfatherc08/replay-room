"""The practical offside rule of the onside-correct corpus, read off a loaded match (test helper; no pipeline code).

At the instant a pass is played, a receiver is **offside** when, in the opponents' half, they are nearer the
opponents' goal line than both the ball and the second-to-last opponent (usually the keeper is the last).
Positions come from the tracking frame nearest the pass's time.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from replay_room.contracts.pitch import BALL_ID, PITCH_LENGTH


def _frame(tracking: pd.DataFrame, period: int, t: float) -> pd.DataFrame:
    rows = tracking[tracking["period_id"] == period]
    stamps = rows.drop_duplicates("frame_id")
    fid = int(stamps.iloc[(stamps["timestamp"] - t).abs().argsort().iloc[0]]["frame_id"])
    return rows[rows["frame_id"] == fid].set_index("player_id")


def is_offside(tracking: pd.DataFrame, period: int, t: float, receiver: str, team: str, attacking_home: bool) -> bool:
    """Was ``receiver`` (of ``team``) offside at the instant of a pass played at ``t``?"""
    f = _frame(tracking, period, t)
    depth = (lambda x: x) if attacking_home else (lambda x: PITCH_LENGTH - x)  # towards the goal attacked
    r = float(depth(f.at[receiver, "x"]))
    ball = float(depth(f.at[BALL_ID, "x"]))
    opponents = f[(f["team_id"] != team) & (f.index != BALL_ID)]
    second_last = float(np.sort(depth(opponents["x"].to_numpy(float)))[-2])
    return r > PITCH_LENGTH / 2 and r > ball + 1e-6 and r > second_last + 1e-6


def decisive_passes(match, moment) -> list[tuple[int, float, str]]:
    """(period, time, receiver) of the passes that set up the moment's key event: the attacking team's last
    successful pass before it in the chain, received by the player who then has the ball."""
    a = match.actions.set_index("action_id")
    chain = [aid for aid in moment.chain_action_ids if aid in a.index]
    key = moment.key_event_ref.action_id
    out = []
    for i, aid in enumerate(chain):
        row = a.loc[aid]
        if aid >= key or row["team_id"] != moment.attacking_team_id or row["type_name"] not in ("pass", "cross"):
            continue
        if row["result_name"] != "success":
            continue
        later = [x for x in chain[i + 1:] if x <= key and a.loc[x, "team_id"] == moment.attacking_team_id]
        if later:
            out.append((int(row["period_id"]), float(row["time_seconds"]), str(a.loc[later[0], "player_id"])))
    return out[-1:]  # the decisive one
