"""The narration brief: the account, reshaped for a renderer to read. Nothing is added.

Everything in the brief is a field of the ``CausalAccount`` (names come from its
``participants`` and ``teams``). Refs are flattened to strings
(``event:<action_id>`` / ``frame:<frame_id>``) so a renderer can copy one into
each sentence; ``order`` is the sentence order every narration must follow:
the headline first, then the remaining contributions in rank order.
"""

from __future__ import annotations

from typing import Any

from replay_room.contracts.causal_account import CausalAccount
from replay_room.contracts.refs import EventRef, FrameRef


def ref_key(ref: EventRef | FrameRef) -> str:
    return f"event:{ref.action_id}" if ref.kind == "event" else f"frame:{ref.frame_id}"


def narration_order(account: CausalAccount) -> list[str]:
    head = account.headline_contribution_id
    return [head] + [c.contribution_id for c in account.contributions if c.contribution_id != head]


def brief(account: CausalAccount) -> dict[str, Any]:
    names = {p.player_id: p.name for p in account.participants}
    teams = {t.team_id: t.name for t in account.teams}
    out, m = account.outcome, account.moment
    by_id = {c.contribution_id: c for c in account.contributions}
    return {
        "moment": {"type": m.type, "period": m.period_id,
                   "attacking_team": teams[out.beneficiary_team_id], "defending_team": teams[out.conceding_team_id]},
        "outcome": {
            "framing": "realized" if out.realized else "prevented",
            "scored": out.scored,
            "value": round(out.value, 3),
            "value_name": out.value_source,
            "ref": ref_key(out.ref),
        },
        "headline_contribution_id": account.headline_contribution_id,
        "order": narration_order(account),
        "contributions": [
            {
                "contribution_id": c.contribution_id,
                "rank": c.rank,
                "headline": c.contribution_id == account.headline_contribution_id,
                "track": c.track,
                "kind": c.kind,
                "role": c.role,
                "label": c.action or c.signal,
                "player_id": c.player_id,
                "player_name": names.get(c.player_id, c.player_id),
                "team": teams[c.team_id],
                "effect": round(c.effect, 3),
                "metrics": {k: round(v, 3) for k, v in c.metrics.items()},
                "refs": [ref_key(r) for r in c.evidence],
                "named_players": sorted({p for r in c.evidence if r.kind == "frame" for p in r.player_ids}
                                        - {c.player_id}),
            }
            for c in (by_id[i] for i in narration_order(account))
        ],
        "counterfactuals": [
            {
                "contribution_id": cf.contribution_id,
                "chosen": cf.chosen,
                "chosen_value": round(cf.chosen_value, 3),
                "better_options": [
                    {"description": a.description,
                     "target_player_name": names.get(a.target_player_id) if a.target_player_id else None,
                     "value": round(a.value, 3),
                     "completion_prob": None if a.completion_prob is None else round(a.completion_prob, 2)}
                    for a in cf.alternatives
                ],
            }
            for cf in account.counterfactuals
        ],
        "participants": [{"player_id": p.player_id, "name": p.name, "team": teams[p.team_id]}
                         for p in account.participants],
    }
