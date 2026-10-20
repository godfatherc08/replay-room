"""The metric layer's entry point: value a goal moment.

``value_moment(moment, actions, frames, meta, ...)`` returns a ``ValuedMoment``:
every chain action carries delta-xT, VAEP (when it validated), xG (shots) and
pass completion (passes), plus ``value`` from the authoritative signal; every
frame supplied gets a pitch-control surface from the attacking team's
perspective. Frames are processed one by one, so a short window (or any subset
of frames) is valued exactly as given.

Action values need the whole match (VAEP game states look at previous actions;
orientation needs the home team; pass completion reads the tracking frame at
each pass), so ``rate_actions`` takes the full SPADL and tracking tables. It
computes them once per match; pass its result to ``value_moment`` to value
several moments without recomputing (or pass ``tracking`` and let it call
``rate_actions``).
"""

from __future__ import annotations

import math
import warnings

import numpy as np
import pandas as pd

from replay_room.contracts.match import ContextEvent, MatchMeta
from replay_room.contracts.pitch import PITCH_LENGTH, PITCH_WIDTH
from replay_room.contracts.moment import Moment
from replay_room.contracts.spadl import SpadlAction
from replay_room.contracts.values import PitchControlSurface, ValuedAction, ValuedMoment
from replay_room.metrics.models import MetricModels, load_models
from replay_room.metrics.orientation import orient
from replay_room.metrics.pass_value import pass_context, under_pressure
from replay_room.metrics.pitch_control import grid, influence_control


BOX_DEPTH = 16.5  # m, penalty area
BOX_HALF_WIDTH = 20.16  # m


def rate_actions(
    actions: pd.DataFrame,
    tracking: pd.DataFrame,
    meta: MatchMeta,
    context: tuple[ContextEvent, ...] = (),
    models: MetricModels | None = None,
    pass_targets: pd.Series | None = None,
) -> pd.DataFrame:
    """Every value for every action of a match, indexed by ``action_id``.

    ``pass_targets``: ``Match.pass_targets``; without it every pass receiver is inferred.
    """
    models = models or load_models()
    enriched = actions.assign(under_pressure=under_pressure(actions, context)).join(pass_context(actions, tracking, pass_targets))
    ltr = orient(enriched, meta.home_team_id)
    xg = models.xg.predict(ltr)
    out = models.xt.rate(ltr, xg)
    out["xg"] = xg
    out["pass_completion"] = models.passes.predict(ltr)
    out["pass_receiver_id"] = enriched["receiver_id"].to_numpy()  # intended receiver (passes only)
    out["pass_receiver_source"] = enriched["receiver_source"].to_numpy()
    out.index = actions["action_id"].to_numpy()
    if models.vaep is not None:
        with warnings.catch_warnings():  # socceraction's feature code trips pandas FutureWarnings
            warnings.simplefilter("ignore", FutureWarning)
            v = models.vaep.rate(actions, meta.home_team_id)
        out["vaep"] = v["vaep_value"]
        out["vaep_offensive"] = v["offensive_value"]
        out["vaep_defensive"] = v["defensive_value"]
    else:
        out["vaep"] = out["vaep_offensive"] = out["vaep_defensive"] = np.nan
    out["value"] = out["vaep"] if models.on_ball_signal == "vaep" else out["xt_delta"]
    return out


def _opt(x: float) -> float | None:
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else float(x)


def surfaces(frames: pd.DataFrame, moment: Moment, meta: MatchMeta, models: MetricModels
             ) -> tuple[PitchControlSurface, ...]:
    """One pitch-control surface per frame present in ``frames``, in frame order."""
    w = moment.window
    ids = frames["frame_id"].unique()
    if len(ids) and (ids.min() < w.frame_start or ids.max() > w.frame_end):
        raise ValueError(f"frames outside the moment window {w.frame_start}..{w.frame_end}")
    x, y = grid()
    attacking_home = moment.attacking_team_id == meta.home_team_id
    threat = models.xt.oriented_grid(attacking_home, x, y)
    in_box_x = x > PITCH_LENGTH - BOX_DEPTH if attacking_home else x < BOX_DEPTH
    box = np.outer(np.abs(y - PITCH_WIDTH / 2) <= BOX_HALF_WIDTH, in_box_x)
    out = []
    for fid, frame in frames.groupby("frame_id", sort=True):
        control = influence_control(frame, moment.attacking_team_id, x, y)
        out.append(PitchControlSurface(
            frame_id=int(fid), period_id=int(frame["period_id"].iloc[0]),
            timestamp=float(frame["timestamp"].iloc[0]), team_id=moment.attacking_team_id,
            model="influence", x=x, y=y, control=control,
            control_share=float(control.mean()),
            box_control=float(control[box].mean()),
            space_value=float((control * threat).sum() / threat.sum()),
        ))
    return tuple(out)


def value_moment(
    moment: Moment,
    actions: pd.DataFrame,
    frames: pd.DataFrame,
    meta: MatchMeta,
    context: tuple[ContextEvent, ...] = (),
    models: MetricModels | None = None,
    action_values: pd.DataFrame | None = None,
    tracking: pd.DataFrame | None = None,
    pass_targets: pd.Series | None = None,
) -> ValuedMoment:
    """``action_values`` from ``rate_actions``, or else the full match ``tracking`` to compute them."""
    models = models or load_models()
    if action_values is None:
        if tracking is None:
            raise ValueError("pass action_values (rate_actions) or the full match tracking")
        action_values = rate_actions(actions, tracking, meta, context, models, pass_targets)
    by_id = actions.set_index("action_id", drop=False)
    valued = []
    for aid in moment.chain_action_ids:
        v = action_values.loc[aid]
        valued.append(ValuedAction(
            action=SpadlAction.from_row(by_id.loc[aid]),
            value=_opt(v["value"]),
            xt_start=_opt(v["xt_start"]), xt_end=_opt(v["xt_end"]), xt_delta=_opt(v["xt_delta"]),
            vaep=_opt(v["vaep"]), vaep_offensive=_opt(v["vaep_offensive"]), vaep_defensive=_opt(v["vaep_defensive"]),
            xg=_opt(v["xg"]), pass_completion=_opt(v["pass_completion"]),
        ))
    return ValuedMoment(
        moment=moment, on_ball_signal=models.on_ball_signal, actions=tuple(valued),
        surfaces=surfaces(frames, moment, meta, models), models=models.provenance,
    )
