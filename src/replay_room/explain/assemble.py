"""Turn a *validated* renderer output into the outgoing ``Narration`` and its timed overlay.

Refs and times are copied from the account (the model's ref string only selects
which of the contribution's records it cites), so the overlay is timed by the
data, never by the model.
"""

from __future__ import annotations

import hashlib

from replay_room.contracts.causal_account import CausalAccount
from replay_room.explain.brief import ref_key
from replay_room.explain.schema import CUE_SECONDS, ModelNarration, Narration, OverlayCue, Sentence


def account_hash(account: CausalAccount) -> str:
    """Content hash of the account, ignoring when it was persisted."""
    stable = account.model_copy(update={"provenance": account.provenance.model_copy(update={"generated_at": None})})
    return hashlib.sha256(stable.model_dump_json().encode("utf-8")).hexdigest()


def assemble(output: ModelNarration, account: CausalAccount, source: str, **meta) -> Narration:
    by_id = {c.contribution_id: c for c in account.contributions}
    sentences = []
    for i, s in enumerate(output.sentences):
        c = by_id[s.contribution_id]
        ref = next(r for r in c.evidence if ref_key(r) == s.ref)
        t = ref.time_seconds if ref.kind == "event" else ref.timestamp
        sentences.append(Sentence(
            index=i, contribution_id=c.contribution_id, role=c.role,
            headline=c.contribution_id == account.headline_contribution_id, text=s.text, ref=ref,
            metric=s.metric, period_id=account.moment.period_id, t=t,
        ))
    timeline = sorted(sentences, key=lambda s: (s.t, s.index))
    cues = []
    for k, s in enumerate(timeline):
        nxt = timeline[k + 1].t if k + 1 < len(timeline) else None
        end = s.t + CUE_SECONDS if nxt is None or nxt <= s.t else min(nxt, s.t + CUE_SECONDS)
        cues.append(OverlayCue(
            sentence_index=s.index, contribution_id=s.contribution_id, period_id=s.period_id,
            t_start=s.t, t_end=end, text=s.text,
            frame_id=s.ref.frame_id if s.ref.kind == "frame" else None,
            action_id=s.ref.action_id if s.ref.kind == "event" else None,
        ))
    return Narration(
        account_id=account.account_id, moment_id=account.moment.moment_id, account_hash=account_hash(account),
        framing="realized" if account.outcome.realized else "prevented", source=source,
        headline_text=output.headline_text, sentences=tuple(sentences), timed_overlay=tuple(cues), **meta,
    )
