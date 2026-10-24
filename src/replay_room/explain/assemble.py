"""Turn a *validated* Storyteller output into the outgoing ``Narration``.

Refs and times are copied from the tool outputs (``framing.Facts.refs``), so
each beat is timed and grounded by the data, never by the model.
"""

from __future__ import annotations

import hashlib

from replay_room.contracts.causal_account import CausalAccount
from replay_room.contracts.context import MatchContext
from replay_room.contracts.plan import FramingPlan
from replay_room.explain.schema import Narration, NarratedBeat, StoryOutput
from replay_room.framing.facts import Facts


def account_hash(account: CausalAccount) -> str:
    """Content hash of the account, ignoring when it was persisted."""
    stable = account.model_copy(update={"provenance": account.provenance.model_copy(update={"generated_at": None})})
    return hashlib.sha256(stable.model_dump_json().encode("utf-8")).hexdigest()


def plan_hash(plan: FramingPlan, context: MatchContext | None) -> str:
    body = plan.model_dump_json() + (context.model_dump_json() if context is not None else "")
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def assemble(output: StoryOutput, account: CausalAccount, plan: FramingPlan, context: MatchContext | None,
             source: str, **meta) -> Narration:
    facts = Facts(account, context)
    beats = []
    for i, (b, told) in enumerate(zip(plan.beats, output.beats)):
        refs = facts.refs(b)
        first = refs[0]
        beats.append(NarratedBeat(
            index=i, beat_id=b.beat_id, kind=b.kind, emphasis=b.emphasis, contribution_id=b.contribution_id,
            link_id=b.link_id, context_fact_id=b.context_fact_id, text=told.text, fan=told.fan, deep=told.deep,
            deep_fan=told.deep_fan, refs=refs,
            period_id=account.moment.period_id,
            t=first.time_seconds if first.kind == "event" else first.timestamp,
        ))
    return Narration(
        account_id=account.account_id, moment_id=account.moment.moment_id, account_hash=account_hash(account),
        plan_hash=plan_hash(plan, context), plan_source=plan.source,
        framing="realized" if account.outcome.realized else "prevented", source=source,
        headline=output.headline, headline_fan=output.headline_fan, beats=tuple(beats), **meta,
    )
