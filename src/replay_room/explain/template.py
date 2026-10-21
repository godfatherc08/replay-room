"""Deterministic fallback renderer: one sentence per contribution, straight from the account.

Insurance, not the product: no model, grounded by construction (it passes the
same validator as the model). Headline first, then rank order; prevented
outcomes are framed as a goal that didn't happen.
"""

from __future__ import annotations

from replay_room.contracts.causal_account import CausalAccount, Contribution
from replay_room.explain.brief import narration_order, ref_key
from replay_room.explain.schema import Metric, ModelNarration, ModelSentence


def _words(label: str | None) -> str:
    return (label or "").replace("_", " ")


def _sentence(c: Contribution, names: dict[str, str], teams: dict[str, str]) -> str:
    who = f"{names.get(c.player_id, c.player_id)} ({teams[c.team_id]})"
    what = _words(c.action or c.signal)
    return f"{who}: {what}, {_words(c.role)}, effect {c.effect:+.3f}."


def render_template(account: CausalAccount) -> ModelNarration:
    names = {p.player_id: p.name for p in account.participants}
    teams = {t.team_id: t.name for t in account.teams}
    by_id = {c.contribution_id: c for c in account.contributions}
    head = by_id[account.headline_contribution_id]
    out = account.outcome
    value = f"{'xG' if out.value_source == 'xg' else 'xT'} {out.value:.3f}"
    head_who = f"{names.get(head.player_id, head.player_id)} ({teams[head.team_id]})"
    if not out.realized:
        stopped = (f"denied by {head_who}, {_words(head.action or head.signal)}"
                   if head.team_id == out.conceding_team_id else f"and {head_who} missed it")
        headline = (f"A goal that didn't happen: {teams[out.beneficiary_team_id]} built a chance worth {value}, "
                    f"{stopped}.")
    else:
        result = "a goal" if out.scored else "a shot"
        headline = (f"{teams[out.beneficiary_team_id]} turned this move into {result} worth {value}; "
                    f"the headline is {head_who}, {_words(head.action or head.signal)}.")
    sentences = tuple(
        ModelSentence(contribution_id=cid, ref=ref_key(by_id[cid].evidence[0]), role=by_id[cid].role,
                      text=_sentence(by_id[cid], names, teams), metric=Metric(name="effect", value=by_id[cid].effect))
        for cid in narration_order(account)
    )
    return ModelNarration(headline_text=headline, sentences=sentences)
