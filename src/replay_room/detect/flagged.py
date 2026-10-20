"""Detectors for the flagged classes: surfaced as talking points, never explained.

Their "why" is about rules, discipline or officiating, not scoring probability,
so the moments carry no chain, no outcome and ``engine_eligible=False``; Build 4
never sees them. They exist so the timeline is complete and the product can be
seen *declining* to fake-explain them.

* ``offside``: a SPADL action whose result is ``offside`` (a pass played to an
  offside player). It keeps a tracking window, sized like an explained moment's
  run-up, so the viewer can show the line.
* ``substitution``, ``injury``, ``var_decision``: one moment per context event
  of that kind, keyed by a ``ContextRef``; no window.

Red cards are not detected (MVP).
"""

from __future__ import annotations

import pandas as pd

from replay_room.contracts.match import ContextEvent
from replay_room.contracts.moment import Moment, MomentContext
from replay_room.contracts.refs import ContextRef
from replay_room.detect.moments import _ref, _teams, _window, window_frames

CONTEXT_CLASSES = ("substitution", "injury", "var_decision")  # flagged classes keyed on a context event


def detect_offsides(actions: pd.DataFrame, tracking: pd.DataFrame) -> list[MomentContext]:
    teams = _teams(actions, tracking)
    out: list[MomentContext] = []
    for a in actions[actions["result_name"] == "offside"].itertuples(index=False):
        t = float(a.time_seconds)
        window = _window(tracking, int(a.period_id), t, t)
        moment = Moment(
            moment_id=f"{a.game_id}-offside-{len(out) + 1}", type="offside", engine_eligible=False,
            game_id=str(a.game_id), period_id=int(a.period_id), t_event=t,
            attacking_team_id=str(a.team_id), defending_team_id=next(x for x in teams if x != a.team_id),
            team_id=str(a.team_id), key_event_ref=_ref(a), key_player_id=str(a.player_id),
            t_start=window.t_start, t_end=window.t_end, window=window,
        )
        out.append(MomentContext(moment=moment, chain_actions=actions.iloc[0:0].reset_index(drop=True),
                                 frames=window_frames(tracking, window)))
    return out


def detect_context_moments(
    context: tuple[ContextEvent, ...], game_id: str, actions: pd.DataFrame, tracking: pd.DataFrame,
    classes: tuple[str, ...] = CONTEXT_CLASSES,
) -> list[MomentContext]:
    """One moment per substitution / injury / VAR-decision context event, in feed order per class."""
    out: list[MomentContext] = []
    for kind in CONTEXT_CLASSES:
        if kind not in classes:
            continue
        for n, ev in enumerate((e for e in context if e.kind == kind), start=1):
            t = float(ev.time_seconds)
            moment = Moment(
                moment_id=f"{game_id}-{kind}-{n}", type=kind, engine_eligible=False,
                game_id=game_id, period_id=ev.period_id, t_event=t,
                attacking_team_id=None, defending_team_id=None, team_id=ev.team_id,
                key_event_ref=ContextRef(event_id=ev.event_id, period_id=ev.period_id, time_seconds=t),
                key_player_id=ev.player_id, detail=ev.detail, t_start=t, t_end=t,
            )
            out.append(MomentContext(moment=moment, chain_actions=actions.iloc[0:0].reset_index(drop=True),
                                     frames=window_frames(tracking, None)))
    return out
