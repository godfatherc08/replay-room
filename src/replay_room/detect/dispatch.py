"""One entry point over every moment class: ``detect_moments``.

It runs the requested detectors and returns one time-sorted list. Explained
moments all have the same shape (chain, window, key event, ``outcome_ref``),
so nothing downstream branches on the class.

**One moment per terminal action.** A shot can qualify for several explained
classes (a goal straight from a regain is also a turnover-to-shot). Among the
requested classes, the one earliest in ``CLAIM_ORDER`` keeps the moment and the
others are listed in its ``secondary_types``. ``penalty`` comes first so a
scored penalty is explained through the foul that won it, not as a one-action
goal chain. Moment ids come from the per-class detectors and do not depend on
which classes were requested (a match's third goal is always ``...-goal-3``).

Every explained moment gets ``outcome_xg`` from Build 3's xG model, so the
model is loaded (``metrics.models.load_xg_model``) unless one is passed or only
flagged classes are requested.
"""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from replay_room.contracts.match import ContextEvent, MatchMeta
from replay_room.contracts.moment import EXPLAINED_CLASSES, FLAGGED_CLASSES, MomentClass, MomentContext
from replay_room.detect.explained import detect_big_chances_saved, detect_penalties, detect_turnover_to_shot
from replay_room.detect.flagged import CONTEXT_CLASSES, detect_context_moments, detect_offsides
from replay_room.detect.moments import detect_goal_moments
from replay_room.detect.possessions import segment_possessions
from replay_room.metrics.models import load_xg_model
from replay_room.metrics.orientation import orient
from replay_room.metrics.xg import XGModel

ALL_CLASSES: tuple[MomentClass, ...] = EXPLAINED_CLASSES + FLAGGED_CLASSES
CLAIM_ORDER: tuple[MomentClass, ...] = ("penalty", "goal", "big_chance_saved", "turnover_to_shot")


def shot_xg(actions: pd.DataFrame, meta: MatchMeta, model: XGModel) -> pd.Series:
    """action_id -> xG (NaN for non-shots), from Build 3's model."""
    xg = model.predict(orient(actions, meta.home_team_id))
    return pd.Series(xg.to_numpy(), index=actions["action_id"].to_numpy(), name="xg")


def detect_moments(
    actions: pd.DataFrame,
    tracking: pd.DataFrame,
    meta: MatchMeta,
    classes: Iterable[MomentClass] = EXPLAINED_CLASSES,
    context: tuple[ContextEvent, ...] = (),
    xg_model: XGModel | None = None,
) -> list[MomentContext]:
    """Moments of the requested classes, sorted by period, time, then class. Pure."""
    wanted = tuple(dict.fromkeys(classes))
    unknown = set(wanted) - set(ALL_CLASSES)
    if unknown:
        raise ValueError(f"unknown moment classes {sorted(unknown)}; known: {', '.join(ALL_CLASSES)}")

    out: list[MomentContext] = []
    explained = [c for c in CLAIM_ORDER if c in wanted]
    if explained:
        xg = shot_xg(actions, meta, xg_model or load_xg_model())
        possessions = segment_possessions(actions)
        detectors = {
            "goal": lambda: [_with_xg(c, xg) for c in detect_goal_moments(actions, tracking, possessions)],
            "turnover_to_shot": lambda: detect_turnover_to_shot(actions, tracking, xg, possessions),
            "big_chance_saved": lambda: detect_big_chances_saved(actions, tracking, xg, possessions),
            "penalty": lambda: detect_penalties(actions, tracking, xg, possessions),
        }
        claimed: dict[int, tuple[MomentContext, list[MomentClass]]] = {}
        for cls in explained:
            for ctx in detectors[cls]():
                oid = ctx.moment.outcome_ref.action_id
                if oid in claimed:
                    claimed[oid][1].append(cls)
                else:
                    claimed[oid] = (ctx, [])
        for ctx, also in claimed.values():
            if also:
                ctx = MomentContext(moment=ctx.moment.model_copy(update={"secondary_types": tuple(also)}),
                                    chain_actions=ctx.chain_actions, frames=ctx.frames)
            out.append(ctx)

    if "offside" in wanted:
        out += detect_offsides(actions, tracking)
    out += detect_context_moments(context, meta.game_id, actions, tracking,
                                  tuple(c for c in CONTEXT_CLASSES if c in wanted))

    rank = {c: i for i, c in enumerate(ALL_CLASSES)}
    out.sort(key=lambda c: (c.moment.period_id, c.moment.t_event, rank[c.moment.type], c.moment.moment_id))
    return out


def _with_xg(ctx: MomentContext, xg: pd.Series) -> MomentContext:
    v = xg.get(ctx.moment.outcome_ref.action_id)
    value = None if v is None or pd.isna(v) else float(v)
    return MomentContext(moment=ctx.moment.model_copy(update={"outcome_xg": value}),
                         chain_actions=ctx.chain_actions, frames=ctx.frames)
