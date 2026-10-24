"""``match_context``: per-match baselines for the defending team, and how this moment deviates from them.

Deterministic, from the match's own events and tracking. Three facts:

* **counter_press** (only when the moment began with the defending team losing
  the ball): over the match's other losses by that team (a possession of theirs
  that ended in a turnover), the share they won back in open play within
  ``COUNTER_PRESS_S``; here, how long the attack kept the ball before the shot
  without them winning it back. It deviates when they usually win it back
  (share >= 0.5) and here they did not.
* **line_height**: while the attacking team has the ball in the defending
  team's defensive third (``DEFENSIVE_THIRD_M`` from its goal line), metres
  from the defending team's goal line to its deepest outfield player. Baseline:
  the median (and IQR) over the match's frames outside this moment; here: the
  median over the ``HERE_S`` seconds before the key event.
* **marking_distance**: the same frames; the mean distance from each attacker
  in that third to the nearest outfield defender.

A frame-based fact deviates when the value here is outside the match's IQR by
at least ``MIN_GAP_M``. Frames are not independent, so sample size counts the
*defending spells* (possessions of the attacking team that contributed frames),
and the lost balls for the counter-press. Below ``MIN_SAMPLES`` there is no
baseline: the kind is listed as insufficient. Confidence: ``low`` from
``MIN_SAMPLES``, ``medium`` from ``MEDIUM_SAMPLES``, ``high`` from ``HIGH_SAMPLES``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from replay_room.contracts.causal_account import CausalAccount
from replay_room.contracts.context import ContextFact, MatchContext
from replay_room.contracts.moment import Moment
from replay_room.contracts.pitch import BALL_ID, PITCH_LENGTH
from replay_room.contracts.refs import FrameRef
from replay_room.detect.possessions import Possession, segment_possessions

COUNTER_PRESS_S = 5.0
DEFENSIVE_THIRD_M = 35.0
HERE_S = 2.0
MIN_GAP_M = 1.0
MIN_SAMPLES = 5
MEDIUM_SAMPLES = 8
HIGH_SAMPLES = 15


def confidence(n: int) -> str | None:
    if n >= HIGH_SAMPLES:
        return "high"
    if n >= MEDIUM_SAMPLES:
        return "medium"
    return "low" if n >= MIN_SAMPLES else None


def _counter_press(m: Moment, possessions: tuple[Possession, ...], actions: pd.DataFrame
                   ) -> ContextFact | tuple[str, str] | None:
    loss = m.turnover_event_ref
    if loss is None:
        return None
    team = m.defending_team_id
    by_id = actions.set_index("action_id")
    if str(by_id.at[loss.action_id, "team_id"]) != team:
        return None
    won_back, n = 0, 0
    for i, p in enumerate(possessions):
        if p.team_id != team or p.end_type != "turnover" or loss.action_id in p.action_ids:
            continue
        n += 1
        nxt = next((q for q in possessions[i + 1:] if q.team_id == team or q.period_id != p.period_id), None)
        if nxt is not None and nxt.team_id == team and nxt.period_id == p.period_id and nxt.start_type == "regain" \
                and nxt.t_start - p.t_end <= COUNTER_PRESS_S:
            won_back += 1
    grade = confidence(n)
    if grade is None:
        return ("counter_press", f"only {n} other lost balls by {team} in the match (need {MIN_SAMPLES})")
    share = won_back / n
    kept = m.t_event - loss.time_seconds  # the attack kept it this long, to the shot: no regain
    return ContextFact(
        fact_id="ctx-counter_press", kind="counter_press", team_id=team, unit="share", baseline=round(share, 3),
        here=0.0, deviates=share >= 0.5 and kept > COUNTER_PRESS_S, direction="lower" if share > 0 else "same",
        sample_size=n, confidence=grade,
        metrics={"won_back": float(won_back), "losses": float(n), "window_s": COUNTER_PRESS_S,
                 "seconds_to_shot": round(kept, 1)},
        evidence=(loss,),
    )


def _possession_at(possessions: tuple[Possession, ...], period: np.ndarray, t: np.ndarray) -> np.ndarray:
    """Index of the possession in play at each (period, time): the last one started at or before it."""
    out = np.full(len(t), -1)
    for pid in np.unique(period):
        own = [i for i, p in enumerate(possessions) if p.period_id == pid]
        if not own:
            continue
        starts = np.array([possessions[i].t_start for i in own])
        mask = period == pid
        k = np.searchsorted(starts, t[mask], side="right") - 1
        out[mask] = np.where(k >= 0, np.array(own)[np.clip(k, 0, None)], -1)
    return out


def _frame_series(m: Moment, tracking: pd.DataFrame, possessions: tuple[Possession, ...],
                  home_team_id: str) -> pd.DataFrame:
    """Per frame with the attacking team on the ball in the defending team's defensive third:
    line height, marking distance, the spell (possession) it belongs to."""
    team, rival = m.defending_team_id, m.attacking_team_id
    defending_home = team == home_team_id
    t = tracking.sort_values(["frame_id", "player_id"])
    frames = t.drop_duplicates("frame_id")[["frame_id", "period_id", "timestamp"]].reset_index(drop=True)
    owner = _possession_at(possessions, frames["period_id"].to_numpy(), frames["timestamp"].to_numpy())
    frames["spell"] = owner
    frames["attacking"] = [owner[k] >= 0 and possessions[owner[k]].team_id == rival for k in range(len(frames))]
    ball = t[t["player_id"] == BALL_ID].set_index("frame_id")["x"]
    own_goal = (lambda x: x) if defending_home else (lambda x: PITCH_LENGTH - x)  # metres from its goal line
    frames["ball_depth"] = own_goal(frames["frame_id"].map(ball).to_numpy(float))
    frames = frames[frames["attacking"] & (frames["ball_depth"] <= DEFENSIVE_THIRD_M)]
    players = t[t["frame_id"].isin(frames["frame_id"]) & (t["player_id"] != BALL_ID)].copy()
    players["depth"] = own_goal(players["x"].to_numpy(float))
    rows = []
    for fid, f in players.groupby("frame_id", sort=True):
        d = f[(f["team_id"] == team) & ~f["is_keeper"]]
        a = f[(f["team_id"] == rival) & ~f["is_keeper"]]
        if d.empty:
            continue
        line = float(d["depth"].min())
        near = a[a["depth"] <= DEFENSIVE_THIRD_M]
        if len(near):
            gaps = np.hypot(near["x"].to_numpy()[:, None] - d["x"].to_numpy()[None, :],
                            near["y"].to_numpy()[:, None] - d["y"].to_numpy()[None, :]).min(axis=1)
            marking = float(gaps.mean())
        else:
            marking = np.nan
        rows.append((int(fid), line, marking))
    series = pd.DataFrame(rows, columns=["frame_id", "line_height", "marking_distance"])
    return frames.merge(series, on="frame_id")


def _frame_fact(kind: str, values: pd.DataFrame, m: Moment, team: str) -> ContextFact | tuple[str, str]:
    w = m.window
    inside = (values["frame_id"] >= w.frame_start) & (values["frame_id"] <= w.frame_end)
    base = values[~inside].dropna(subset=[kind])
    here_rows = values[inside & (values["timestamp"] >= m.t_event - HERE_S) & (values["timestamp"] <= m.t_event)
                       ].dropna(subset=[kind])
    spells = int(base["spell"].nunique())
    grade = confidence(spells)
    if grade is None:
        return (kind, f"only {spells} defending spells in the match (need {MIN_SAMPLES})")
    if here_rows.empty:
        return (kind, "the ball was not in their defensive third just before the key event")
    q25, med, q75 = (float(v) for v in np.percentile(base[kind], [25, 50, 75]))
    here = float(here_rows[kind].median())
    gap = max(q25 - here, here - q75, 0.0)
    direction = "higher" if here > med else "lower" if here < med else "same"
    first, last = here_rows.iloc[0], here_rows.iloc[-1]
    return ContextFact(
        fact_id=f"ctx-{kind}", kind=kind, team_id=team, unit="m", baseline=round(med, 1), here=round(here, 1),
        spread=(round(q25, 1), round(q75, 1)), deviates=gap >= MIN_GAP_M, direction=direction,
        sample_size=spells, confidence=grade,
        metrics={"frames": float(len(base)), "here_frames": float(len(here_rows))},
        evidence=(FrameRef(frame_id=int(first["frame_id"]), timestamp=float(first["timestamp"])),
                  FrameRef(frame_id=int(last["frame_id"]), timestamp=float(last["timestamp"]))),
    )


def match_context(m: Moment, actions: pd.DataFrame, tracking: pd.DataFrame, home_team_id: str,
                  goalkeepers: frozenset[str], account: CausalAccount | None = None) -> MatchContext:
    """The baselines; with the moment's ``account``, also the positional facts of the story's players."""
    possessions = segment_possessions(actions)
    facts, missing = [], []
    press = _counter_press(m, possessions, actions)
    if isinstance(press, ContextFact):
        facts.append(press)
    elif press is not None:
        missing.append(press)
    values = _frame_series(m, tracking.assign(is_keeper=tracking["player_id"].isin(goalkeepers)), possessions,
                           home_team_id)
    for kind in ("line_height", "marking_distance"):
        fact = _frame_fact(kind, values, m, m.defending_team_id)
        (facts if isinstance(fact, ContextFact) else missing).append(fact)
    positions, swings, markings = (positional_facts(account, actions, tracking, home_team_id, possessions)
                                   if account is not None else ((), (), ()))
    return MatchContext(game_id=m.game_id, moment_id=m.moment_id, team_id=m.defending_team_id, facts=tuple(facts),
                        insufficient=tuple(missing), positions=positions, swings=swings, markings=markings)


def match_context_for(match, m: Moment, account: CausalAccount | None = None) -> MatchContext:
    """``match_context`` for a loaded ``Match`` (with the account: its positional facts too)."""
    keepers = frozenset(p.player_id for t in (match.meta.home_team, match.meta.away_team) for p in t.players
                        if p.position == "GK")
    return match_context(m, match.actions, match.tracking, match.meta.home_team_id, keepers, account)


from replay_room.context.positions import positional_facts  # noqa: E402  (positions builds on this module)
