"""Match metadata and non-SPADL context events."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict

ContextKind = Literal[
    "period_start",
    "period_end",
    "pressure",
    "possession_change",
    "ball_out_of_play",
]
CONTEXT_KINDS: tuple[str, ...] = ContextKind.__args__  # type: ignore[attr-defined]


class Player(BaseModel):
    model_config = ConfigDict(frozen=True)

    player_id: str
    name: str
    shirt_number: int
    position: str  # GK, DF, MF, FW


class Team(BaseModel):
    model_config = ConfigDict(frozen=True)

    team_id: str
    name: str
    short_name: str
    players: tuple[Player, ...]


class Period(BaseModel):
    model_config = ConfigDict(frozen=True)

    period_id: int
    start_seconds: float
    end_seconds: float


class MatchMeta(BaseModel):
    """Match metadata in canonical terms (frame/units are fixed by ``contracts.pitch``)."""

    model_config = ConfigDict(frozen=True)

    game_id: str
    competition: str
    home_team: Team
    away_team: Team
    periods: tuple[Period, ...]
    frame_rate_hz: float
    source: str  # which adapter produced this match, e.g. "synthetic-v1"

    @property
    def home_team_id(self) -> str:
        return self.home_team.team_id

    def team(self, team_id: str) -> Team:
        for team in (self.home_team, self.away_team):
            if team.team_id == team_id:
                return team
        raise KeyError(team_id)

    def player(self, player_id: str) -> Player:
        for team in (self.home_team, self.away_team):
            for p in team.players:
                if p.player_id == player_id:
                    return p
        raise KeyError(player_id)


@dataclass(frozen=True, slots=True)
class ContextEvent:
    """A feed event that is not an on-ball SPADL action (pressure, possession change, ...).

    ``player_id`` is the actor (e.g. the presser); ``target_player_id`` the player
    acted on (e.g. the pressed ball carrier), when there is one.
    """

    event_id: str
    period_id: int
    time_seconds: float
    kind: str
    team_id: str | None = None
    player_id: str | None = None
    target_player_id: str | None = None
    x: float | None = None
    y: float | None = None

    def __post_init__(self) -> None:
        if self.kind not in CONTEXT_KINDS:
            raise ValueError(f"unknown context kind {self.kind!r}")
