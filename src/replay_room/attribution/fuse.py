"""Fusion: pool both tracks, keep what clears the evidence bar, rank, pick the headline.

* **Evidence bar.** A candidate survives iff ``|effect| >= EFFECT_THRESHOLD``;
  of those, the ``TOP_K`` largest by ``|effect|`` are kept. If nothing clears
  the bar, the single largest candidate is kept so the account is never empty.
* **Ranking** is by ``|effect|`` (ties: earlier first, then id), on one scale for
  both tracks: every effect is a change in the attacking team's P(outcome).
* **Headline** (one rule over the outcome, no per-class branches):

  - prevented outcome: the ``chance_denied`` fact (the save, block or miss);
  - realized outcome: the conceding-side failure (a defending-team fact with
    positive effect: a lost ball, a lapse, space conceded, a broken marking)
    with the largest ``|effect| x recency``, which takes role ``primary_cause``;
    if there is none, the attacking contribution with the largest
    ``|effect| x recency``. Recency is the fact's position in the moment, from
    its start (``RECENCY_FLOOR``) to the key event (1.0), so a small touch long
    before the end (a goal kick, a ball won straight back) does not lead the
    story over a lapse right before it. Only the headline uses recency: the
    contributions keep their ranks by ``|effect|``.

Shapley shares are not computed (``Contribution.shapley_share`` stays None).
"""

from __future__ import annotations

from replay_room.attribution.outcome import Candidate
from replay_room.contracts.causal_account import Contribution, Outcome

EFFECT_THRESHOLD = 0.01
TOP_K = 10
RECENCY_FLOOR = 0.1


def _order(c: Candidate) -> tuple[float, float, str]:
    return (-abs(c.effect), c.t, c.key)


def select(candidates: list[Candidate]) -> list[Candidate]:
    keys = [c.key for c in candidates]
    if len(keys) != len(set(keys)):
        raise ValueError(f"duplicate candidate keys {sorted(k for k in keys if keys.count(k) > 1)}")
    ranked = sorted(candidates, key=_order)
    kept = [c for c in ranked if abs(c.effect) >= EFFECT_THRESHOLD][:TOP_K]
    return kept or ranked[:1]


def recency(t: float, t_start: float, t_key: float) -> float:
    """Position of time ``t`` in the moment: ``RECENCY_FLOOR`` at its start (or before), 1.0 at the key event."""
    if t_key <= t_start:
        return 1.0
    return min(max((t - t_start) / (t_key - t_start), RECENCY_FLOOR), 1.0)


def headline(kept: list[Candidate], outcome: Outcome, t_start: float, t_key: float) -> Candidate:
    if not outcome.realized:
        denied = [c for c in kept if c.kind == "chance_denied"]
        if not denied:
            raise ValueError("a prevented outcome needs its chance_denied fact")
        return denied[0]

    def score(c: Candidate) -> tuple[float, float]:
        return (abs(c.effect) * recency(c.t, t_start, t_key), c.t)

    failures = [c for c in kept if c.team_id == outcome.conceding_team_id and c.effect > 0]
    if failures:
        return max(failures, key=score)
    creators = [c for c in kept if c.team_id == outcome.beneficiary_team_id and c.effect > 0]
    return max(creators or kept, key=score)


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
