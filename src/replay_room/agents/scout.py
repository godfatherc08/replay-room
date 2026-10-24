"""Scout: watches the match stream and keeps the described replay menu. It never explains.

The Scout reads the feed in order (``sources.Stream``) and, as the stream
clock passes each moment the engine detected (``detect_moments``), adds it
to the menu with a one-line description built from the moment's own fields.
Engine-eligible moments are marked explainable; flagged ones (offside, VAR,
injury, substitution) and red cards seen in the feed are described only, with
the reason the engine does not explain them. Deterministic: no model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from replay_room.agents.engine import Engine
from replay_room.agents.sources import Stream

_FLAGGED_WHY = {
    "offside": "an offside is a rules call, not a scoring probability",
    "var_decision": "a VAR decision is officiating, not a scoring probability",
    "injury": "an injury stops play; there is no chance to explain",
    "substitution": "a substitution is a team decision, not a passage of play",
    "red_card": "a red card is discipline, not a scoring probability",
}


@dataclass(frozen=True)
class MenuItem:
    moment_id: str | None  # None for a red card seen in the feed (no moment class)
    type: str
    match_clock: str
    period_id: int
    t: float
    explainable: bool
    description: str
    why_not_explained: str | None = None


def describe(m: dict[str, Any]) -> str:
    team, player, clock = m.get("team") or "", m.get("player") or "", m["match_clock"]
    by = f" ({player})" if player else ""
    return {
        "goal": f"{clock} · Goal for {team}: {player} scores.",
        "big_chance_saved": f"{clock} · Big chance for {team}: {player} is denied.",
        "turnover_to_shot": f"{clock} · Turnover to shot: {team} win it back and {player} shoots.",
        "penalty": f"{clock} · Penalty to {team}{by}.",
        "offside": f"{clock} · Offside against {team}{by}.",
        "var_decision": f"{clock} · VAR decision{': ' + m['detail'] if m.get('detail') else ''}.",
        "injury": f"{clock} · Injury stoppage{' for ' + player if player else ''}.",
        "substitution": f"{clock} · Substitution for {team}{by}.",
    }.get(m["type"], f"{clock} · {m['type'].replace('_', ' ').capitalize()}{by}.")


@dataclass
class Scout:
    engine: Engine
    stream: Stream
    menu: list[MenuItem] = field(default_factory=list)
    events_seen: int = 0

    def watch(self) -> list[MenuItem]:
        """Consume the whole stream; returns the menu in match order."""
        found = self.engine.detect_moments("all")
        pending = sorted(found["moments"], key=lambda m: (m["period_id"], m["t_event"], m["moment_id"]))
        self.menu = []
        for ev in self.stream.events():
            self.events_seen += 1
            period, t = int(ev.get("period", 0)), float(ev.get("t", 0.0))
            while pending and (pending[0]["period_id"], pending[0]["t_event"]) <= (period, t):
                self._add(pending.pop(0))
            if _red_card(ev):
                self.menu.append(MenuItem(
                    moment_id=None, type="red_card", match_clock=f"P{period} {t:.0f}s", period_id=period, t=t,
                    explainable=False, description=f"P{period} {t:.0f}s · Red card for {ev.get('team', '')}"
                                                   f"{' (' + ev['player'] + ')' if ev.get('player') else ''}.",
                    why_not_explained=_FLAGGED_WHY["red_card"]))
        for m in pending:  # anything detected after the last streamed event
            self._add(m)
        return self.menu

    def _add(self, m: dict[str, Any]) -> None:
        self.menu.append(MenuItem(
            moment_id=m["moment_id"], type=m["type"], match_clock=m["match_clock"], period_id=m["period_id"],
            t=m["t_event"], explainable=m["engine_eligible"], description=describe(m),
            why_not_explained=None if m["engine_eligible"] else _FLAGGED_WHY.get(m["type"], "flagged, not explained")))


def _red_card(ev: dict[str, Any]) -> bool:
    kind = str(ev.get("type", "")).lower().replace(" ", "")
    card = str(ev.get("card", "")).lower()
    return kind in ("redcard", "secondyellow") or card in ("red", "second_yellow", "red_card")
