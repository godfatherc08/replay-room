"""The engine behind the MCP tools: one loaded match, its moments, accounts, contexts and tellings, cached.

A protocol surface only: every method calls the deterministic pipeline as it
is (``detect_moments``, ``value_moment`` + ``attribute``, ``match_context``,
``narrate``); nothing here ranks, attributes or writes prose.
"""

from __future__ import annotations

import warnings
from functools import cached_property
from pathlib import Path
from typing import Any

from replay_room.attribution.engine import attribute
from replay_room.context import match_context_for
from replay_room.contracts.causal_account import CausalAccount
from replay_room.contracts.context import MatchContext
from replay_room.contracts.moment import EXPLAINED_CLASSES, FLAGGED_CLASSES, MomentContext
from replay_room.contracts.plan import FramingPlan
from replay_room.detect.dispatch import detect_moments
from replay_room.explain.narrate import Mode, narrate
from replay_room.explain.schema import Narration
from replay_room.ingest import load_match
from replay_room.ingest.loader import Match
from replay_room.metrics.models import MetricModels, load_models
from replay_room.metrics.valuation import rate_actions, value_moment
from replay_room.render.display import match_clock

DEFAULT_MATCH = Path(__file__).resolve().parents[3] / "data" / "fixtures" / "synthetic_match_01"
ALL = (*EXPLAINED_CLASSES, *FLAGGED_CLASSES)


class UnknownMoment(KeyError):
    pass


class EngineService:
    def __init__(self, match_dir: str | Path = DEFAULT_MATCH, match: Match | None = None):
        self.match_dir = Path(match_dir)
        if match is not None:
            self.__dict__["match"] = match
        self._accounts: dict[str, CausalAccount] = {}
        self._contexts: dict[str, MatchContext] = {}

    @cached_property
    def match(self) -> Match:
        return load_match(self.match_dir)

    @cached_property
    def models(self) -> MetricModels:
        return load_models()

    @cached_property
    def action_values(self):
        m = self.match
        with warnings.catch_warnings():  # socceraction's VAEP feature code trips pandas FutureWarnings
            warnings.simplefilter("ignore", FutureWarning)
            return rate_actions(m.actions, m.tracking, m.meta, m.context, self.models, m.pass_targets)

    @cached_property
    def detected(self) -> dict[str, MomentContext]:
        m = self.match
        found = detect_moments(m.actions, m.tracking, m.meta, ALL, m.context, self.models.xg)
        return {c.moment.moment_id: c for c in found}

    def _moment(self, moment_id: str) -> MomentContext:
        if moment_id not in self.detected:
            raise UnknownMoment(f"no moment {moment_id!r} in {self.match.meta.game_id}")
        return self.detected[moment_id]

    def menu(self, classes: tuple[str, ...] = ALL) -> list[dict[str, Any]]:
        """Every detected moment of the requested classes: what it is, and whether the engine explains it."""
        meta = self.match.meta
        names = {p.player_id: p.name for t in (meta.home_team, meta.away_team) for p in t.players}
        teams = {t.team_id: t.name for t in (meta.home_team, meta.away_team)}
        out = []
        for mid, ctx in self.detected.items():
            m = ctx.moment
            if m.type not in classes:
                continue
            out.append({
                "moment_id": mid, "type": m.type, "engine_eligible": m.engine_eligible, "period_id": m.period_id,
                "t_event": round(m.t_event, 2), "match_clock": match_clock(meta, m.period_id, m.t_event),
                "team": teams.get(m.team_id or m.attacking_team_id or ""),
                "player": names.get(m.key_player_id or ""), "scored": m.outcome_scored,
                "detail": m.detail,
            })
        return out

    def account(self, moment_id: str) -> CausalAccount:
        if moment_id not in self._accounts:
            ctx = self._moment(moment_id)
            if not ctx.moment.engine_eligible:
                raise ValueError(f"{moment_id}: {ctx.moment.type} moments are flagged, not explained")
            m = self.match
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", FutureWarning)
                vm = value_moment(ctx.moment, m.actions, ctx.frames, m.meta, m.context, self.models,
                                  self.action_values)
                self._accounts[moment_id] = attribute(vm, ctx.frames, m.actions, self.action_values, m.meta,
                                                      m.tracking, m.context, self.models)
        return self._accounts[moment_id]

    def context(self, moment_id: str) -> MatchContext:
        if moment_id not in self._contexts:
            ctx = self._moment(moment_id)
            if not ctx.moment.engine_eligible:
                raise ValueError(f"{moment_id}: {ctx.moment.type} moments are flagged, not explained")
            self._contexts[moment_id] = match_context_for(self.match, ctx.moment, self.account(moment_id))
        return self._contexts[moment_id]

    def narration(self, moment_id: str, mode: Mode = "template", plan: FramingPlan | None = None) -> Narration:
        return narrate(self.account(moment_id), mode, context=self.context(moment_id), plan=plan)


_SERVICES: dict[Path, EngineService] = {}


def service(match_dir: str | Path | None = None) -> EngineService:
    """The process-wide service for a match directory (loaded once)."""
    key = Path(match_dir or DEFAULT_MATCH).resolve()
    if key not in _SERVICES:
        _SERVICES[key] = EngineService(key)
    return _SERVICES[key]
