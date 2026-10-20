"""Fusion: pool both tracks, keep what clears the evidence bar, rank, pick the headline.

* **Evidence bar.** A candidate survives iff ``|effect| >= EFFECT_THRESHOLD``;
  of those, the ``TOP_K`` largest by ``|effect|`` are kept. If nothing clears
  the bar, the single largest candidate is kept so the account is never empty.
* **Ranking** is by ``|effect|`` (ties: earlier first, then id), on one scale for
  both tracks: every effect is a change in the attacking team's P(outcome).
* **Headline** (one rule over the outcome, no per-class branches):

  - prevented outcome: the ``chance_denied`` fact (the save, block or miss);
  - realized outcome: the largest conceding-side failure (a defending-team
    fact with positive effect: a lost ball, a lapse, space conceded, a broken
    marking), which takes role ``primary_cause``; if there is none, the largest
    attacking contribution.

Shapley shares are not computed (``Contribution.shapley_share`` stays None).
"""

from __future__ import annotations

from replay_room.attribution.outcome import Candidate
from replay_room.contracts.causal_account import Contribution, Outcome

EFFECT_THRESHOLD = 0.01
TOP_K = 10


def _order(c: Candidate) -> tuple[float, float, str]:
    return (-abs(c.effect), c.t, c.key)


def select(candidates: list[Candidate]) -> list[Candidate]:
    keys = [c.key for c in candidates]
    if len(keys) != len(set(keys)):
        raise ValueError(f"duplicate candidate keys {sorted(k for k in keys if keys.count(k) > 1)}")
    ranked = sorted(candidates, key=_order)
    kept = [c for c in ranked if abs(c.effect) >= EFFECT_THRESHOLD][:TOP_K]
    return kept or ranked[:1]


def headline(kept: list[Candidate], outcome: Outcome) -> Candidate:
    if not outcome.realized:
        denied = [c for c in kept if c.kind == "chance_denied"]
        if not denied:
            raise ValueError("a prevented outcome needs its chance_denied fact")
        return denied[0]
    failures = [c for c in kept if c.team_id == outcome.conceding_team_id and c.effect > 0]
    if failures:
        return max(failures, key=lambda c: (c.effect, -c.t))
    creators = [c for c in kept if c.team_id == outcome.beneficiary_team_id and c.effect > 0]
    return max(creators or kept, key=lambda c: (abs(c.effect), -c.t))


def contributions(kept: list[Candidate], head: Candidate, outcome: Outcome) -> tuple[Contribution, ...]:
    out = []
    for rank, c in enumerate(kept, start=1):
        cause = c is head and outcome.realized and c.team_id == outcome.conceding_team_id
        out.append(Contribution(
            contribution_id=c.key, rank=rank, track=c.track, kind=c.kind,
            role="primary_cause" if cause else c.role,
            action=c.label if c.track == "on_ball" else None,
            signal=c.label if c.track == "off_ball" else None,
            player_id=c.player_id, team_id=c.team_id, t=c.t, effect=round(c.effect, 6),
            metrics=c.metrics, evidence=c.evidence,
        ))
    return tuple(out)
