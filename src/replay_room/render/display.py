"""Display fields for the viewer, read mechanically off the account, the match metadata and the actions.

Nothing here judges or computes a metric: it formats what is already there
(labels, roles, refs, times) and counts the goals already in the event data.

* ``match_clock``: elapsed match time ``MM:SS`` (earlier periods' lengths plus
  the time in the period), the clock a broadcast shows;
* ``score_before``: the score when the moment began, from the match's goals
  before it (own goals count for the other team);
* ``contribution_display``: per contribution, a title (the account's label),
  a subtitle (its role, and its kind for off-ball facts), the unit its number is
  in, and the time of its first cited record;
* ``value_unit``: which metric a contribution's number is: ``xG`` for a denied
  chance or a penalty-winning foul (both are the outcome's xG), ``ΔxT`` for the
  terminal action and for actions valued by delta-xT, ``VAEP`` for actions
  valued by VAEP, ``P(goal)`` for off-ball space.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from replay_room.contracts.causal_account import CausalAccount, Contribution
from replay_room.contracts.match import MatchMeta
from replay_room.detect.possessions import is_goal


def match_clock(meta: MatchMeta, period_id: int, t: float) -> str:
    before = sum(p.end_seconds - p.start_seconds for p in meta.periods if p.period_id < period_id)
    total = max(before + t, 0.0)
    return f"{int(total // 60):02d}:{int(total % 60):02d}"


def score_before(actions: pd.DataFrame, meta: MatchMeta, period_id: int, t: float) -> dict[str, int]:
    score = {"home": 0, "away": 0}
    earlier = actions[(actions["period_id"] < period_id)
                      | ((actions["period_id"] == period_id) & (actions["time_seconds"] < t))]
    for a in earlier.itertuples(index=False):
        if not is_goal(a.type_name, a.result_name):
            continue
        scorer = a.team_id
        if a.result_name == "owngoal":
            scorer = meta.away_team.team_id if scorer == meta.home_team.team_id else meta.home_team.team_id
        score["home" if scorer == meta.home_team.team_id else "away"] += 1
    return score


def value_unit(c: Contribution) -> str:
    if c.kind == "chance_denied" or "outcome_value" in c.metrics:
        return "xG"
    if c.track == "off_ball":
        return "P(goal)"
    if "vaep" in c.metrics and c.metrics.get("value") == c.metrics["vaep"]:
        return "VAEP"
    return "ΔxT"


def _words(s: str | None) -> str:
    return (s or "").replace("_", " ")


def contribution_display(account: CausalAccount, meta: MatchMeta) -> list[dict[str, Any]]:
    names = {p.player_id: (p.shirt_number, p.name) for p in account.participants}
    out = []
    for c in account.contributions:
        ref = c.evidence[0]
        t = ref.time_seconds if ref.kind == "event" else ref.timestamp
        number, name = names.get(c.player_id, (None, c.player_id))
        label = c.action or c.signal
        subtitle = _words(c.role)
        if c.track == "off_ball" and c.kind != c.role:  # e.g. "defensive error · marking break"
            subtitle = f"{subtitle} · {_words(c.kind)}"
        out.append({
            "contribution_id": c.contribution_id,
            "title": _words(label).capitalize(),
            "subtitle": subtitle.capitalize(),
            "player": f"#{number} {name}" if number is not None else name,
            "unit": value_unit(c),
            "t": round(t, 2),
            "match_clock": match_clock(meta, account.moment.period_id, t),
        })
    return out
