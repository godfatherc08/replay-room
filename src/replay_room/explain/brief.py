"""The story brief: a framing plan with every beat's records resolved, for a model Storyteller to read.

Nothing is added: each beat carries the fields of the records it points at
(names from the account's participants and teams), the players it may name,
and the numbers it may weave in. The deterministic composer's telling is
included as a reference draft the model may improve on but not go beyond.
"""

from __future__ import annotations

from typing import Any

from replay_room.contracts.causal_account import CausalAccount, Contribution
from replay_room.contracts.context import MatchContext
from replay_room.contracts.plan import FramingPlan
from replay_room.contracts.refs import EventRef, FrameRef
from replay_room.explain.compose import beat_positions, chance_band, compose
from replay_room.framing.facts import Facts


def ref_key(ref: EventRef | FrameRef) -> str:
    return f"event:{ref.action_id}" if ref.kind == "event" else f"frame:{ref.frame_id}"


def _contribution(c: Contribution, names: dict[str, str], teams: dict[str, str]) -> dict[str, Any]:
    return {"contribution_id": c.contribution_id, "role": c.role, "kind": c.kind, "label": c.action or c.signal,
            "player": names.get(c.player_id, c.player_id), "team": teams[c.team_id],
            "effect": round(c.effect, 3), "metrics": {k: round(v, 3) for k, v in c.metrics.items()},
            "named_players": sorted({names.get(p, p) for r in c.evidence if r.kind == "frame"
                                     for p in r.player_ids} - {names.get(c.player_id)})}


def brief(account: CausalAccount, plan: FramingPlan, context: MatchContext | None = None) -> dict[str, Any]:
    facts = Facts(account, context)
    names = {p.player_id: p.name for p in account.participants}
    teams = {t.team_id: t.name for t in account.teams}
    out = account.outcome
    draft = compose(account, plan, context)
    beats = []
    for b, told in zip(plan.beats, draft.beats):
        item: dict[str, Any] = {"beat_id": b.beat_id, "kind": b.kind, "emphasis": b.emphasis,
                                "may_name": sorted(names[p] for p in facts.players(b, plan.lead_contribution_id,
                                                                                    plan.flaw_contribution_id)),
                                "carries_a_computed_link": b.link_id is not None,
                                "draft": {"text": told.text, "fan": told.fan, "deep": told.deep,
                                          "deep_fan": told.deep_fan}}
        if b.kind not in ("outcome", "counterfactual", "context"):
            positions, swing, marking = beat_positions(
                facts, context, b, facts.players(b, plan.lead_contribution_id, plan.flaw_contribution_id))
            item["positional"] = {
                "players": [{"player": names.get(p.player_id, p.player_id), "frame": p.frame_id, "phase": p.phase,
                             "forward_of_average_m": p.forward_m, "lateral_of_average_m": p.lateral_m,
                             "average_confidence": p.confidence, "average_possessions": p.sample_spells,
                             "to_ball_m": p.to_ball_m, "to_nearest_opponent_m": p.to_opponent_m,
                             "nearest_opponent": names.get(p.nearest_opponent_id), "to_goal_m": p.to_goal_m}
                            for p in positions],
                "control_swing": None if swing is None else {
                    "zone": swing.zone, "from": swing.control_from, "to": swing.control_to, "seconds": swing.seconds},
                "marking": None if marking is None else {
                    "defender": names.get(marking.defender_id), "man": names.get(marking.man_id),
                    "separation_from_m": marking.separation_from, "separation_to_m": marking.separation_to,
                    "held": marking.held}}
        if b.contribution_id and b.kind != "counterfactual":
            item["fact"] = _contribution(facts.contribution(b.contribution_id), names, teams)
        if b.link_id:
            k = facts.link(b.link_id)
            item["link"] = {"kind": k.kind, "defender": names[k.defender_id],
                            "marked": names.get(k.marked_player_id) if k.marked_player_id else None,
                            "runner": names.get(k.runner_id) if k.runner_id else None, "zone": k.zone,
                            "used_by": _contribution(used, names, teams) if (used := facts.enabled_by(k)) else None,
                            "metrics": {key: round(v, 1) for key, v in k.metrics.items()}}
        if b.context_fact_id:
            f = facts.context_fact(b.context_fact_id)
            item["context"] = {"kind": f.kind, "team": teams[f.team_id], "unit": f.unit, "baseline": f.baseline,
                               "here": f.here, "spread": f.spread, "direction": f.direction,
                               "sample_size": f.sample_size, "confidence": f.confidence, "metrics": f.metrics}
        if b.kind == "counterfactual":
            cf = facts.counterfactual(b.contribution_id)
            item["counterfactual"] = {
                "chooser": names[facts.contribution(cf.contribution_id).player_id], "chosen": cf.chosen,
                "chosen_value": round(cf.chosen_value, 3),
                "better_options": [{"description": a.description, "value": round(a.value, 3),
                                    "target": names.get(a.target_player_id) if a.target_player_id else None,
                                    "completion_prob": None if a.completion_prob is None else round(a.completion_prob, 2)}
                                   for a in cf.alternatives]}
        beats.append(item)
    return {
        "moment": {"type": account.moment.type, "attacking_team": teams[out.beneficiary_team_id],
                   "defending_team": teams[out.conceding_team_id]},
        "outcome": {"framing": "realized" if out.realized else "prevented", "scored": out.scored,
                    "value": round(out.value, 3), "band": chance_band(out.value), "zone": out.zone,
                    "shooter": names.get(facts.scorer_id)},
        "headline_draft": {"text": draft.headline, "fan": draft.headline_fan},
        "beats": beats,
    }
