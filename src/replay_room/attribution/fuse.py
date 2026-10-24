"""Fusion: pool both tracks, keep what clears the evidence bar, rank, pick the headline.

* **Evidence bar.** A candidate survives iff ``|effect| >= EFFECT_THRESHOLD``;
  of those, the ``TOP_K`` largest by ``|effect|`` are kept, plus the
  conceding side's best failure (by ``|effect| x recency``) if the cut dropped
  it: a real defensive flaw is never buried beneath small on-ball touches. If
  nothing clears the bar, the single largest candidate is kept so the account
  is never empty.
* **Ranking** is by ``|effect|`` (ties: earlier first, then id), on one scale for
  both tracks: every effect is a change in the attacking team's P(outcome).
* **Headline and supporting beat** (one rule over the outcome, no per-class
  branches). Facts are scored by ``|effect| x recency``, where recency is the
  fact's position in the moment, from its start (``RECENCY_FLOOR``) to the key
  event (1.0), so a small touch long before the end (a goal kick, a ball won
  straight back) does not lead the story over the act right before it. Only the
  headline uses recency: the contributions keep their ranks by ``|effect|``.

  - prevented outcome: the headline is the ``chance_denied`` fact (the save,
    block or miss); the supporting beat is the conceding side's best failure
    (what let the chance happen), if any;
  - realized outcome: the headline is the attacking team's best positive act
    (the finish, the key pass, the run). The conceding side's best failure (a
    lost ball, a lapse, space conceded, a broken marking) is the supporting
    beat; it takes the headline itself, with role ``primary_cause``, only when
    it outscores the best attacking act by ``DEFENSIVE_LEAD`` (a foul that won
    a penalty), and then the attacking act that punished it supports it. A
    goal is told from the side that scored it.

Shapley shares are not computed (``Contribution.shapley_share`` stays None).
"""

from __future__ import annotations

from replay_room.attribution.outcome import Candidate
from replay_room.contracts.causal_account import Contribution, Outcome

EFFECT_THRESHOLD = 0.01
TOP_K = 10
RECENCY_FLOOR = 0.1
DEFENSIVE_LEAD = 2.0  # a conceding failure leads only when it outscores the best attacking act this many times


def _order(c: Candidate) -> tuple[float, float, str]:
    return (-abs(c.effect), c.t, c.key)


def select(candidates: list[Candidate], outcome: Outcome | None = None, t_start: float = 0.0,
           t_key: float = 0.0) -> list[Candidate]:
    keys = [c.key for c in candidates]
    if len(keys) != len(set(keys)):
        raise ValueError(f"duplicate candidate keys {sorted(k for k in keys if keys.count(k) > 1)}")
    ranked = sorted(candidates, key=_order)
    clear = [c for c in ranked if abs(c.effect) >= EFFECT_THRESHOLD]
    kept = clear[:TOP_K]
    if outcome is not None:
        flaw = _best(_failures(clear, outcome), t_start, t_key)
        if flaw is not None and flaw not in kept:
            kept = sorted([*kept, flaw], key=_order)
    return kept or ranked[:1]


def recency(t: float, t_start: float, t_key: float) -> float:
    """Position of time ``t`` in the moment: ``RECENCY_FLOOR`` at its start (or before), 1.0 at the key event."""
    if t_key <= t_start:
        return 1.0
    return min(max((t - t_start) / (t_key - t_start), RECENCY_FLOOR), 1.0)


def _score(c: Candidate, t_start: float, t_key: float) -> tuple[float, float]:
    return (abs(c.effect) * recency(c.t, t_start, t_key), c.t)


def _best(cands: list[Candidate], t_start: float, t_key: float) -> Candidate | None:
    return max(cands, key=lambda c: _score(c, t_start, t_key)) if cands else None


def _failures(cands: list[Candidate], outcome: Outcome) -> list[Candidate]:
    """The conceding side's facts that helped the attack (a positive effect)."""
    return [c for c in cands if c.team_id == outcome.conceding_team_id and c.effect > 0 and c.kind != "chance_denied"]


def headline(kept: list[Candidate], outcome: Outcome, t_start: float, t_key: float) -> tuple[Candidate, Candidate | None]:
    """The headline and the supporting beat (None when there is no second side to the story)."""
    flaw = _best(_failures(kept, outcome), t_start, t_key)
    if not outcome.realized:
        denied = [c for c in kept if c.kind == "chance_denied"]
        if not denied:
            raise ValueError("a prevented outcome needs its chance_denied fact")
        return denied[0], flaw
    act = _best([c for c in kept if c.team_id == outcome.beneficiary_team_id and c.effect > 0], t_start, t_key)
    if flaw is not None and (act is None or
                             _score(flaw, t_start, t_key)[0] >= DEFENSIVE_LEAD * _score(act, t_start, t_key)[0]):
        return flaw, act
    if act is not None:
        return act, flaw
    return _best(kept, t_start, t_key), None


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
