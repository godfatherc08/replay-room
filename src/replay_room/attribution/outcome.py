"""The outcome an account explains, and the candidate type both tracks produce."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from replay_room.contracts.causal_account import ContributionKind, ContributionRole, Outcome
from replay_room.contracts.match import MatchMeta
from replay_room.contracts.moment import Moment
from replay_room.contracts.pitch import PITCH_LENGTH, PITCH_WIDTH
from replay_room.contracts.refs import EventRef, FrameRef
from replay_room.detect.explained import BIG_CHANCE_XG
from replay_room.metrics.xt import XTModel


@dataclass(frozen=True)
class Candidate:
    """A causal fact before thresholding and ranking (becomes a ``Contribution``)."""

    key: str  # stable, unique within a moment: becomes the contribution id
    track: str  # "on_ball" | "off_ball"
    kind: ContributionKind
    role: ContributionRole
    label: str  # the action (on-ball) or signal (off-ball)
    player_id: str
    team_id: str
    t: float
    effect: float  # change in the attacking team's P(outcome)
    evidence: tuple[EventRef | FrameRef, ...]
    metrics: dict[str, float] = field(default_factory=dict)


def threat_at(xt: XTModel, x: float, y: float, attacking_home: bool) -> float:
    """The attacking team's xT at an absolute-frame location."""
    if not attacking_home:  # same flip as play_left_to_right
        x, y = PITCH_LENGTH - x, PITCH_WIDTH - y
    return float(xt.at(np.array([x]), np.array([y]))[0])


def outcome_of(moment: Moment, actions: pd.DataFrame, action_values: pd.DataFrame, meta: MatchMeta,
               xt: XTModel) -> Outcome:
    """V and the framing. Prevented iff the terminal action did not score but was a big chance."""
    oid = moment.outcome_ref.action_id
    xg = action_values.at[oid, "xg"]
    if xg is not None and not (isinstance(xg, float) and math.isnan(xg)):
        value, source = float(xg), "xg"
    else:  # not a shot (an own goal): the threat the attacking team held at that spot
        row = actions.set_index("action_id").loc[oid]
        value = threat_at(xt, float(row["start_x"]), float(row["start_y"]), moment.attacking_team_id == meta.home_team_id)
        source = "xt"
    return Outcome(
        ref=moment.outcome_ref, value=value, value_source=source, scored=bool(moment.outcome_scored),
        realized=bool(moment.outcome_scored) or value < BIG_CHANCE_XG,
        beneficiary_team_id=moment.attacking_team_id, conceding_team_id=moment.defending_team_id,
    )
