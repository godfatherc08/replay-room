"""Detectors for the explained classes beyond goals.

Each emits the same shape as a goal moment (``moments.chain_moment``): the
possession chain up to the key action, the run-up tracking window, and the
terminal ``outcome_ref`` that Build 4 attributes over. Inputs are the SPADL
table, the tracking table and ``xg`` (action_id -> xG from Build 3's model,
NaN for non-shots); all three are pure functions of them.

* ``turnover_to_shot``: an open-play shot at most ``TURNOVER_TO_SHOT_SECONDS``
  after the shooting team regained the ball, with xG of at least
  ``TURNOVER_SHOT_MIN_XG`` (a hopeful punt after a regain is not a moment).
* ``big_chance_saved``: a non-penalty shot with xG of at least ``BIG_CHANCE_XG``
  that did not score (saved, blocked or off target). The terminal value is high
  but the realised outcome is no goal: Build 4 frames it around what created the
  chance and what denied it.
* ``penalty``: a penalty kick. The key event is the opponent's foul that won it
  (the chain is the build-up into the box ending in that foul); the outcome is
  the kick itself (xG ``metrics.xg.PENALTY_XG``). If the feed has no foul right
  before the kick, the kick is its own key event.
"""

from __future__ import annotations

import math

import pandas as pd

from replay_room.contracts.moment import MomentContext
from replay_room.detect.moments import _teams, chain_moment, possession_of
from replay_room.detect.possessions import SHOT_TYPES, Possession, segment_possessions

TURNOVER_TO_SHOT_SECONDS = 15.0  # regain -> shot; the usual "shot from a turnover" horizon
TURNOVER_SHOT_MIN_XG = 0.05
# Conventional big-chance cutoffs sit near 0.3, but the synthetic feed's geometric xG model tops
# out around 0.25 per shot, so 0.15 marks its top tier. Re-tune when the real feed arrives.
BIG_CHANCE_XG = 0.15
OPEN_PLAY_SHOTS = SHOT_TYPES - {"shot_penalty"}


def _xg(xg: pd.Series, action_id: int) -> float | None:
    v = xg.get(action_id, math.nan)
    return None if pd.isna(v) else float(v)


def _setup(actions: pd.DataFrame, tracking: pd.DataFrame, possessions: tuple[Possession, ...] | None):
    possessions = segment_possessions(actions) if possessions is None else possessions
    return possessions, possession_of(possessions), actions.set_index("action_id", drop=False), \
        _teams(actions, tracking)


def detect_turnover_to_shot(
    actions: pd.DataFrame, tracking: pd.DataFrame, xg: pd.Series,
    possessions: tuple[Possession, ...] | None = None,
) -> list[MomentContext]:
    possessions, poss_of, by_id, teams = _setup(actions, tracking, possessions)
    out: list[MomentContext] = []
    for shot in by_id[by_id["type_name"].isin(OPEN_PLAY_SHOTS)].itertuples(index=False):
        n = poss_of[int(shot.action_id)]
        poss = possessions[n]
        value = _xg(xg, int(shot.action_id))
        if (poss.start_type != "regain" or poss.team_id != shot.team_id
                or float(shot.time_seconds) - poss.t_start > TURNOVER_TO_SHOT_SECONDS
                or value is None or value < TURNOVER_SHOT_MIN_XG):
            continue
        defending = next(t for t in teams if t != shot.team_id)
        out.append(chain_moment("turnover_to_shot", len(out) + 1, shot, possessions, n, by_id, tracking,
                                str(shot.team_id), defending, outcome_xg=value))
    return out


def detect_big_chances_saved(
    actions: pd.DataFrame, tracking: pd.DataFrame, xg: pd.Series,
    possessions: tuple[Possession, ...] | None = None,
) -> list[MomentContext]:
    possessions, poss_of, by_id, teams = _setup(actions, tracking, possessions)
    out: list[MomentContext] = []
    shots = by_id[by_id["type_name"].isin(OPEN_PLAY_SHOTS) & ~by_id["result_name"].isin(["success", "owngoal"])]
    for shot in shots.itertuples(index=False):
        value = _xg(xg, int(shot.action_id))
        if value is None or value < BIG_CHANCE_XG:
            continue
        defending = next(t for t in teams if t != shot.team_id)
        out.append(chain_moment("big_chance_saved", len(out) + 1, shot, possessions,
                                poss_of[int(shot.action_id)], by_id, tracking, str(shot.team_id), defending,
                                outcome_xg=value))
    return out


def detect_penalties(
    actions: pd.DataFrame, tracking: pd.DataFrame, xg: pd.Series,
    possessions: tuple[Possession, ...] | None = None,
) -> list[MomentContext]:
    possessions, poss_of, by_id, teams = _setup(actions, tracking, possessions)
    ordered = actions.sort_values(["period_id", "action_id"], kind="stable")
    ordered = ordered[ordered["type_name"] != "non_action"]
    prev_id = dict(zip(ordered["action_id"].iloc[1:], ordered["action_id"].iloc[:-1]))
    out: list[MomentContext] = []
    for kick in by_id[by_id["type_name"] == "shot_penalty"].itertuples(index=False):
        key = kick
        before = prev_id.get(int(kick.action_id))
        if before is not None:
            foul = by_id.loc[before]
            if (foul.type_name == "foul" and foul.team_id != kick.team_id
                    and foul.period_id == kick.period_id):
                key = foul
        defending = next(t for t in teams if t != kick.team_id)
        out.append(chain_moment("penalty", len(out) + 1, key, possessions, poss_of[int(key.action_id)], by_id,
                                tracking, str(kick.team_id), defending, outcome=kick,
                                outcome_xg=_xg(xg, int(kick.action_id))))
    return out
