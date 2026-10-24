"""``attribute``: one valued moment in, one ``CausalAccount`` out. Deterministic; no model calls."""

from __future__ import annotations

from collections.abc import Iterable
from importlib.metadata import PackageNotFoundError, version

import pandas as pd

from replay_room.attribution.counterfactual import COUNTERFACTUAL_MARGIN, counterfactual_for
from replay_room.attribution.fuse import EFFECT_THRESHOLD, contributions, headline, select
from replay_room.attribution.links import links_for
from replay_room.attribution.off_ball import off_ball_candidates
from replay_room.attribution.on_ball import on_ball_candidates
from replay_room.attribution.outcome import outcome_of
from replay_room.contracts.causal_account import CausalAccount, EvidenceIndex, Participant, Provenance, TeamInfo
from replay_room.contracts.match import ContextEvent, MatchMeta
from replay_room.contracts.moment import EXPLAINED_CLASSES, MomentClass
from replay_room.contracts.values import ValuedMoment
from replay_room.detect.dispatch import detect_moments
from replay_room.metrics.models import MetricModels, load_models
from replay_room.metrics.pass_value import PASS_TYPES, under_pressure
from replay_room.metrics.valuation import rate_actions, value_moment

try:
    PIPELINE_VERSION = version("replay-room")
except PackageNotFoundError:  # running from a source tree that is not installed
    PIPELINE_VERSION = "0.0.0"


def goalkeepers(meta: MatchMeta) -> frozenset[str]:
    return frozenset(p.player_id for t in (meta.home_team, meta.away_team) for p in t.players if p.position == "GK")


def attribute(
    vm: ValuedMoment,
    frames: pd.DataFrame,
    actions: pd.DataFrame,
    action_values: pd.DataFrame,
    meta: MatchMeta,
    tracking: pd.DataFrame,
    context: tuple[ContextEvent, ...] = (),
    models: MetricModels | None = None,
) -> CausalAccount:
    """The causal account of an engine-eligible moment.

    ``vm``/``frames``: the moment valued by ``value_moment`` and its window's tracking rows;
    ``actions``/``action_values``/``tracking``: the whole match's SPADL table, ``rate_actions``
    output and tracking table (the turnover and the denial sit outside the chain; the
    counterfactual reads the decision frame).
    """
    m = vm.moment
    if not m.engine_eligible:
        raise ValueError(f"{m.moment_id}: {m.type} moments are flagged, not explained")
    models = models or load_models()
    keepers = goalkeepers(meta)
    by_id = actions.set_index("action_id", drop=False)
    outcome = outcome_of(m, actions, action_values, meta, models.xt)
    key = by_id.loc[m.key_event_ref.action_id]
    candidates = on_ball_candidates(vm, actions, action_values, outcome, meta, models.xt)
    spot = (float(key["start_x"]), float(key["start_y"]))
    attacking_home = m.attacking_team_id == meta.home_team_id
    candidates += off_ball_candidates(vm, frames, spot, outcome.value, attacking_home, keepers)
    kept = select(candidates, outcome, m.t_start, m.t_event)
    head, support = headline(kept, outcome, m.t_start, m.t_event)
    contribs = contributions(kept, head, outcome)
    links = links_for(m, kept, frames, actions, spot, attacking_home, keepers)

    pressure = under_pressure(by_id, context)
    counterfactuals = []
    for c in contribs:
        if c.track != "on_ball" or c.kind != "action_value" or c.team_id != m.attacking_team_id:
            continue
        if c.role not in ("finish", "assist") or c.action not in (*PASS_TYPES, "shot"):
            continue
        aid = c.evidence[0].action_id
        cf = counterfactual_for(c.contribution_id, by_id.loc[aid], action_values.loc[aid], tracking,
                                (m.window.frame_start, m.window.frame_end), bool(pressure.loc[aid]), meta,
                                models, keepers)
        if cf is not None:
            counterfactuals.append(cf)

    mentioned = {c.player_id for c in contribs} | {m.key_player_id}
    mentioned |= {p for c in contribs for r in c.evidence if r.kind == "frame" for p in r.player_ids}
    mentioned |= {a.target_player_id for cf in counterfactuals for a in cf.alternatives if a.target_player_id}
    mentioned |= {p for link in links for p in link.player_ids}
    participants = []
    for team in (meta.home_team, meta.away_team):
        participants += [Participant(player_id=p.player_id, name=p.name, team_id=team.team_id,
                                     shirt_number=p.shirt_number, position=p.position)
                         for p in team.players if p.player_id in mentioned]
    teams = {t.team_id: TeamInfo(team_id=t.team_id, name=t.name) for t in (meta.home_team, meta.away_team)}

    draft = dict(
        account_id=f"acc-{m.moment_id}", game_id=m.game_id, moment=m, outcome=outcome,
        teams=(teams[m.attacking_team_id], teams[m.defending_team_id]), participants=tuple(participants),
        headline_contribution_id=head.key, supporting_contribution_id=support.key if support else None,
        contributions=contribs, counterfactuals=tuple(counterfactuals), links=links,
        provenance=Provenance(pipeline_version=PIPELINE_VERSION, source=meta.source, models=vm.models,
                              effect_threshold=EFFECT_THRESHOLD, counterfactual_margin=COUNTERFACTUAL_MARGIN),
    )
    refs = [r for c in contribs for r in c.evidence]
    refs += [cf.decision_frame for cf in counterfactuals] + [r for cf in counterfactuals for a in cf.alternatives
                                                              for r in a.evidence]
    refs += [r for link in links for r in (*link.evidence, *([link.enabled] if link.enabled else []))]
    evidence = EvidenceIndex(events=tuple(sorted({r.action_id for r in refs if r.kind == "event"})),
                             frames=tuple(sorted({r.frame_id for r in refs if r.kind == "frame"})))
    return CausalAccount(**draft, evidence=evidence)


def attribute_match(match, classes: Iterable[MomentClass] = EXPLAINED_CLASSES,
                    models: MetricModels | None = None) -> list[CausalAccount]:
    """Detect, value and attribute every engine-eligible moment of a loaded ``Match``."""
    models = models or load_models()
    action_values = rate_actions(match.actions, match.tracking, match.meta, match.context, models,
                                 match.pass_targets)
    accounts = []
    for ctx in detect_moments(match.actions, match.tracking, match.meta, classes, match.context, models.xg):
        if not ctx.moment.engine_eligible:
            continue
        vm = value_moment(ctx.moment, match.actions, ctx.frames, match.meta, match.context, models, action_values)
        accounts.append(attribute(vm, ctx.frames, match.actions, action_values, match.meta, match.tracking,
                                  match.context, models))
    return accounts
