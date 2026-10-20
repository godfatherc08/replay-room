"""Track A, on-ball: each action's value delta, signed towards the attacking team.

Values are Build 3's, read as they are:

* every chain action carries ``value``, the authoritative on-ball signal (VAEP
  when it validated, otherwise delta-xT), from the acting team's perspective.
  A defending-team action counts with the opposite sign: losing the ball is a
  positive effect for the attack;
* the **terminal action** (``outcome_ref``) is valued *ex ante* with delta-xT
  (xG minus the threat already held there). Its VAEP reads the realised result
  (about +0.8 for a scored shot, negative for a miss), which would leak the
  outcome into its own explanation;
* a key event that is not the terminal action (the foul that won a penalty) is
  worth ``V - xT`` at its location from the attacking team's perspective: it
  turned the threat the attack held there into the outcome's value;
* the **turnover** (the defending team's action that lost the ball before a
  regain) is valued like a chain action. A shot that ended the other team's
  possession is not a turnover: it is a finish, not a lapse;
* a **prevented** outcome adds ``chance_denied`` with effect ``-V``, credited to
  the first defending action within ``DENIAL_SECONDS`` of the shot (save,
  block, interception, clearance, tackle), or to the shooter for a miss.
"""

from __future__ import annotations

import math

import pandas as pd

from replay_room.attribution.outcome import Candidate, threat_at
from replay_room.contracts.causal_account import Outcome
from replay_room.contracts.match import MatchMeta
from replay_room.contracts.refs import EventRef
from replay_room.contracts.values import ValuedMoment
from replay_room.detect.moments import _ref
from replay_room.detect.possessions import PASS_TYPES, SHOT_TYPES
from replay_room.metrics.xt import XTModel

DENIAL_SECONDS = 3.0
DENIAL_TYPES = frozenset({"keeper_save", "keeper_claim", "keeper_punch", "keeper_pick_up",
                          "interception", "clearance", "tackle"})


def _num(v: float | None) -> float | None:
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else float(v)


def _metrics(**values: float | None) -> dict[str, float]:
    return {k: round(float(v), 6) for k, v in values.items() if _num(v) is not None}


def _role(attacking: bool, effect: float, is_finish: bool, is_assist: bool) -> str:
    if is_finish:
        return "finish"
    if attacking:
        if effect < 0:
            return "attacking_error"
        return "assist" if is_assist else "build_up"
    return "defensive_error" if effect > 0 else "defending"


def on_ball_candidates(
    vm: ValuedMoment,
    actions: pd.DataFrame,
    action_values: pd.DataFrame,
    outcome: Outcome,
    meta: MatchMeta,
    xt: XTModel,
) -> list[Candidate]:
    m = vm.moment
    att = m.attacking_team_id
    oid, kid = m.outcome_ref.action_id, m.key_event_ref.action_id
    by_id = actions.set_index("action_id", drop=False)
    attacking_passes = [va.action.action_id for va in vm.actions
                        if va.action.team_id == att and va.action.type_name in PASS_TYPES
                        and va.action.result_name == "success" and va.action.action_id < oid]
    assist_id = attacking_passes[-1] if attacking_passes else None

    out: list[Candidate] = []
    for va in vm.actions:
        a = va.action
        attacking = a.team_id == att
        if a.action_id == oid:
            value, label = _num(va.xt_delta), a.type_name
            metrics = _metrics(xg=va.xg, xt_start=va.xt_start, delta_xt=va.xt_delta)
        elif a.action_id == kid:  # wins the outcome without being it (a penalty foul)
            held = threat_at(xt, a.start_x, a.start_y, att == meta.home_team_id)
            value = -(outcome.value - held) if not attacking else outcome.value - held
            label = a.type_name
            metrics = _metrics(outcome_value=outcome.value, xt_attacking=held)
        else:
            value, label = va.value, a.type_name
            metrics = _metrics(value=va.value, vaep=va.vaep, delta_xt=va.xt_delta, pass_completion=va.pass_completion)
        if value is None:  # undefined for this action (e.g. a foul with no outcome attached)
            continue
        effect = value if attacking else -value
        out.append(Candidate(
            key=f"a{a.action_id}", track="on_ball", kind="action_value",
            role=_role(attacking, effect, a.action_id == oid, a.action_id == assist_id),
            label=label if a.result_name in ("success", "owngoal") else f"{label}_{a.result_name}",
            player_id=a.player_id, team_id=a.team_id, t=a.time_seconds, effect=effect,
            evidence=(EventRef(action_id=a.action_id, original_event_id=a.original_event_id,
                               period_id=a.period_id, time_seconds=a.time_seconds),),
            metrics=metrics,
        ))

    turnover = m.turnover_event_ref
    if turnover is not None:
        row = by_id.loc[turnover.action_id]
        value = _num(action_values.at[turnover.action_id, "value"])
        if value is not None and row["type_name"] not in SHOT_TYPES:
            effect = -value if row["team_id"] != att else value
            v = action_values.loc[turnover.action_id]
            out.append(Candidate(
                key=f"a{turnover.action_id}", track="on_ball", kind="action_value",
                role="defensive_error" if effect > 0 else "defending",
                label=f"{row['type_name']}_{row['result_name']}" if row["result_name"] != "success" else row["type_name"],
                player_id=str(row["player_id"]), team_id=str(row["team_id"]), t=float(row["time_seconds"]),
                effect=effect, evidence=(turnover,),
                metrics=_metrics(value=value, vaep=v["vaep"], delta_xt=v["xt_delta"], lost_ball=1.0),
            ))

    if not outcome.realized:
        out.append(_denial(by_id.loc[oid], by_id, att, outcome))
    return out


def _denial(shot: pd.Series, by_id: pd.DataFrame, att: str, outcome: Outcome) -> Candidate:
    after = by_id[(by_id["period_id"] == shot["period_id"]) & (by_id["action_id"] > shot["action_id"])
                  & (by_id["time_seconds"] <= shot["time_seconds"] + DENIAL_SECONDS)]
    stoppers = after[(after["team_id"] != att) & after["type_name"].isin(DENIAL_TYPES)]
    if len(stoppers):
        row, label = stoppers.iloc[0], str(stoppers.iloc[0]["type_name"])
    else:
        row, label = shot, f"{shot['type_name']}_missed"
    return Candidate(
        key=f"d{int(row['action_id'])}", track="on_ball", kind="chance_denied", role="prevention", label=label,
        player_id=str(row["player_id"]), team_id=str(row["team_id"]), t=float(row["time_seconds"]),
        effect=-outcome.value, evidence=(_ref(row),), metrics=_metrics(xg_denied=outcome.value),
    )
