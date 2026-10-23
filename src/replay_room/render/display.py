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


# ------------------------------------------------------------------------------------- bundle v3: meaning
#
# Plain-language words for a contribution, read off its kind / role / action / signal and the sign and size
# of its effect (never a new judgement: the role says who it helped, the effect says how much). Thresholds
# are on the stored metric, so the same fact always gets the same words.

DANGEROUS_VALUE = 0.05  # an on-ball action worth at least this much VAEP / delta-xT is called "dangerous"
_FAILED = ("pass_fail", "goalkick_fail", "cross_fail", "dribble_fail")
_WON = ("interception", "tackle", "clearance")

# Kits by side (display only: the feed carries no colours). Keepers wear their own colour.
KITS = {"home": {"shirt": "#d6363c", "shorts": "#f4f4f5", "keeper": "#c8e64a"},
        "away": {"shirt": "#2f7cf6", "shorts": "#0f1e3d", "keeper": "#f59e0b"}}


def icon(c: Contribution, account: CausalAccount) -> str:
    """The ribbon's role icon: pass / carry / shot / save / turnover / run / space / marking."""
    if c.kind == "space_creation":
        return "run"
    if c.kind == "space_conceded":
        return "space"
    if c.kind == "marking_break":
        return "marking"
    a = c.action or ""
    if a == "keeper_save":
        return "save"
    if a.startswith("shot"):
        return "shot"
    if a in _WON or (a in _FAILED and c.team_id == account.moment.defending_team_id):
        return "turnover"
    if a.startswith("dribble"):
        return "carry"
    return "pass"


def gloss(c: Contribution, account: CausalAccount) -> str:
    """A few plain words for what this fact did for the chance."""
    a = c.action or ""
    if c.kind == "chance_denied":
        if a == "keeper_save":
            return "the save that stopped it"
        if a.startswith("shot"):
            return "the miss that let them off"
        return "the stop that denied the goal"
    if c.kind == "space_creation":
        return {"run_in_behind": "ran in behind to open space", "run_into_space": "ran into open space",
                "found_space": "found space between the lines"}.get(c.signal or "", "opened up space")
    if c.kind == "space_conceded":
        return "left the decisive space open" if c.role == "primary_cause" else "left space open"
    if c.kind == "marking_break":
        return "lost their marker"
    defending = c.team_id == account.moment.defending_team_id
    if defending:  # a defending player's action that helped the attack
        return "lost possession here" if a in _FAILED or c.role in ("primary_cause", "defensive_error") else "slowed the attack"
    if c.role == "attacking_error":
        return "gave the ball away" if a in _FAILED or a in _WON else "cost the attack ground"
    if c.role == "primary_cause":
        return "created the chance"
    if c.role == "finish":
        return "took the shot"
    if c.role == "assist":
        return "set up the shot"
    if a in _WON:
        return "won the ball back"
    if a == "keeper_save":
        return "started the move"
    dangerous = abs(c.effect) >= DANGEROUS_VALUE
    if a.startswith("dribble"):
        return "a dangerous carry" if dangerous else "carried the ball forward"
    if a.startswith("pass") or a.startswith("cross"):
        return "a dangerous pass" if dangerous else "moved the ball forward"
    return "helped build the attack"


def chance_band(xg: float) -> str:
    """Qualitative size of a chance for Fan mode."""
    if xg >= 0.3:
        return "a big chance"
    if xg >= 0.12:
        return "a good chance"
    if xg >= 0.05:
        return "a half-chance"
    return "a long shot"


def outcome_display(account: CausalAccount) -> dict[str, Any]:
    o = account.outcome
    percent = round(100 * o.value)
    unit = "chance of scoring" if o.value_source == "xg" else "threat"
    if o.scored:
        result = "Goal"
    elif o.realized:
        result = "No goal"
    else:
        result = "A goal that didn't happen"
    return {"percent": percent, "label": f"{percent}% {unit}", "band": chance_band(o.value), "result": result}


def name_ids(text: str, account: CausalAccount) -> str:
    """Replace player ids in a stored description ("pass to EPA-09") with their shirt and name."""
    for p in sorted(account.participants, key=lambda p: -len(p.player_id)):
        if p.player_id in text:
            who = f"#{p.shirt_number} {p.name}" if p.shirt_number is not None else p.name
            text = text.replace(p.player_id, who)
    return text


def meaning(account: CausalAccount) -> list[dict[str, Any]]:
    """Per contribution: gloss, icon, signed direction and magnitude normalized within this moment."""
    peak = max((abs(c.effect) for c in account.contributions), default=0.0) or 1.0
    return [{"contribution_id": c.contribution_id, "gloss": gloss(c, account), "icon": icon(c, account),
             "positive": c.effect >= 0, "magnitude": round(abs(c.effect) / peak, 3)}
            for c in account.contributions]
