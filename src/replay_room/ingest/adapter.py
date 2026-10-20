"""Feed adapters: the ONLY place that knows a raw feed's format.

An adapter turns one raw match directory into canonical contracts:
``MatchMeta``, a SPADL action table, context events, and the tracking table,
all in the frame defined by ``replay_room.contracts.pitch``. When the real
Innovation Studio feed arrives, add an adapter for it here; nothing downstream
changes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import pandas as pd
from socceraction.spadl import SPADLSchema

from replay_room.contracts.match import ContextEvent, MatchMeta, Period, Player, Team
from replay_room.contracts.pitch import BALL_ID, PITCH_LENGTH, PITCH_WIDTH
from replay_room.contracts.spadl import SPADL_COLUMNS, SpadlAction
from replay_room.contracts.tracking import TRACKING_COLUMNS


@dataclass(frozen=True)
class AdaptedFeed:
    meta: MatchMeta
    actions: pd.DataFrame  # SPADL_COLUMNS, validated against socceraction's SPADLSchema
    context: tuple[ContextEvent, ...]
    tracking: pd.DataFrame  # TRACKING_COLUMNS
    # action_id -> player the feed says a pass/cross was aimed at, for every pass that names one
    # (completed or not). Not part of SPADL; empty if the feed has no such field.
    pass_targets: pd.Series = field(default_factory=lambda: pd.Series(dtype=object, name="intended_receiver_id"))


class FeedAdapter(Protocol):
    name: str

    def can_read(self, path: Path) -> bool: ...

    def read(self, path: Path) -> AdaptedFeed: ...


# --------------------------------------------------------------------------- synthetic-v1


# raw type -> (SPADL type, {raw outcome -> SPADL result}); "*" is the default result.
_SPADL_MAP: dict[str, tuple[str, dict[str, str]]] = {
    "Pass": ("pass", {"complete": "success", "incomplete": "fail"}),
    "KickOff": ("pass", {"complete": "success", "incomplete": "fail"}),
    "GoalKick": ("goalkick", {"complete": "success", "incomplete": "fail"}),
    "Carry": ("dribble", {"*": "success"}),
    "TakeOn": ("take_on", {"won": "success", "lost": "fail"}),
    "Tackle": ("tackle", {"won": "success", "lost": "fail"}),
    "Interception": ("interception", {"*": "success"}),
    "Shot": ("shot", {"goal": "success", "saved": "fail", "off_target": "fail", "blocked": "fail"}),
    "KeeperSave": ("keeper_save", {"*": "success"}),
    "Clearance": ("clearance", {"*": "success"}),
}
_CONTEXT_MAP: dict[str, str] = {
    "PeriodStart": "period_start",
    "PeriodEnd": "period_end",
    "Pressure": "pressure",
    "PossessionChange": "possession_change",
    "BallOut": "ball_out_of_play",
}
_BODYPARTS = {"right_foot": "foot_right", "left_foot": "foot_left", "head": "head", "other": "other"}


class SyntheticFeedAdapter:
    """Reads the ``synthetic-v1`` raw feed written by ``ingest.generator``.

    Raw frame: metres, origin at the centre spot, and each period's
    ``home_attacks`` says whether the home team attacks raw +x or -x.
    """

    name = "synthetic-v1"

    def can_read(self, path: Path) -> bool:
        meta = path / "meta.json"
        return meta.is_file() and json.loads(meta.read_text(encoding="utf-8")).get("feed_version") == self.name

    def read(self, path: Path) -> AdaptedFeed:
        raw_meta = json.loads((path / "meta.json").read_text(encoding="utf-8"))
        meta = self._meta(raw_meta)
        flips = {p["id"]: (1.0 if p["home_attacks"] == "+x" else -1.0) for p in raw_meta["periods"]}
        with (path / "events.jsonl").open(encoding="utf-8") as fh:
            raw_events = [json.loads(line) for line in fh if line.strip()]
        actions, context = self._events(raw_events, meta, flips)
        tracking = self._tracking(pd.read_csv(path / "tracking.csv.gz"), flips)
        return AdaptedFeed(meta=meta, actions=actions, context=context, tracking=tracking,
                           pass_targets=self._pass_targets(raw_events, actions))

    @staticmethod
    def _pass_targets(raw_events: list[dict[str, Any]], actions: pd.DataFrame) -> pd.Series:
        recipients = {ev["id"]: ev["recipient"] for ev in raw_events if ev.get("recipient")}
        passes = actions[actions["type_name"].isin(["pass", "cross"])]
        targets = passes["original_event_id"].map(recipients)
        targets.index = passes["action_id"].to_numpy()
        return targets.dropna().rename("intended_receiver_id")

    def _meta(self, raw: dict[str, Any]) -> MatchMeta:
        pitch = raw["pitch"]
        if (pitch["length_m"], pitch["width_m"]) != (PITCH_LENGTH, PITCH_WIDTH):
            # Canonical SPADL is fixed at 105 x 68; a different pitch would need rescaling here.
            raise ValueError(f"unsupported pitch size {pitch}")

        def team(t: dict[str, Any]) -> Team:
            players = tuple(
                Player(player_id=p["id"], name=p["name"], shirt_number=p["number"], position=p["position"])
                for p in t["players"]
            )
            return Team(team_id=t["id"], name=t["name"], short_name=t["id"], players=players)

        # Clocks restart at 0 each period (same convention as SPADL time_seconds).
        periods = [Period(period_id=p["id"], start_seconds=0.0, end_seconds=float(p["duration_s"]))
                   for p in raw["periods"]]
        return MatchMeta(
            game_id=raw["match_id"],
            competition=raw["competition"],
            home_team=team(raw["teams"]["home"]),
            away_team=team(raw["teams"]["away"]),
            periods=tuple(periods),
            frame_rate_hz=float(raw["frame_rate_hz"]),
            source=self.name,
        )

    @staticmethod
    def _xy(x: float, y: float, flip: float) -> tuple[float, float]:
        """Raw centre-origin -> canonical bottom-left origin, home attacking +x."""
        return flip * x + PITCH_LENGTH / 2, flip * y + PITCH_WIDTH / 2

    def _events(
        self, raw_events: list[dict[str, Any]], meta: MatchMeta, flips: dict[int, float]
    ) -> tuple[pd.DataFrame, tuple[ContextEvent, ...]]:
        actions: list[dict[str, Any]] = []
        context: list[ContextEvent] = []
        for ev in raw_events:
            kind = ev["type"]
            flip = flips[ev["period"]]
            if kind in _CONTEXT_MAP:
                x = y = None
                if "x" in ev:
                    x, y = self._xy(ev["x"], ev["y"], flip)
                context.append(ContextEvent(
                    event_id=ev["id"], period_id=ev["period"], time_seconds=float(ev["t"]),
                    kind=_CONTEXT_MAP[kind], team_id=ev.get("team"), player_id=ev.get("player"),
                    target_player_id=ev.get("target"), x=x, y=y,
                ))
                continue
            if kind not in _SPADL_MAP:
                raise ValueError(f"unmapped raw event type {kind!r} ({ev['id']})")
            type_name, results = _SPADL_MAP[kind]
            if kind == "Pass" and ev.get("cross"):
                type_name = "cross"
            outcome = ev.get("outcome")
            result = results.get(outcome, results.get("*")) if outcome is not None else results.get("*")
            if result is None:
                raise ValueError(f"unmapped outcome {outcome!r} for {kind} ({ev['id']})")
            sx, sy = self._xy(ev["x"], ev["y"], flip)
            ex, ey = self._xy(ev["end_x"], ev["end_y"], flip) if "end_x" in ev else (sx, sy)
            bodypart = _BODYPARTS[ev["body_part"]] if "body_part" in ev else "foot"
            actions.append(SpadlAction(
                game_id=meta.game_id, original_event_id=ev["id"], action_id=len(actions),
                period_id=ev["period"], time_seconds=float(ev["t"]), team_id=ev["team"],
                player_id=ev["player"], start_x=sx, start_y=sy, end_x=ex, end_y=ey,
                type_name=type_name, result_name=result, bodypart_name=bodypart,
            ).to_row())
        df = pd.DataFrame(actions, columns=list(SPADL_COLUMNS))
        # Players can stand a little off the pitch; SPADL locations are clipped to it.
        df[["start_x", "end_x"]] = df[["start_x", "end_x"]].clip(0, PITCH_LENGTH)
        df[["start_y", "end_y"]] = df[["start_y", "end_y"]].clip(0, PITCH_WIDTH)
        df = df.sort_values(["period_id", "time_seconds", "action_id"], kind="stable").reset_index(drop=True)
        df["action_id"] = np.arange(len(df))
        return SPADLSchema.validate(df), tuple(context)

    def _tracking(self, raw: pd.DataFrame, flips: dict[int, float]) -> pd.DataFrame:
        flip = raw["period"].map(flips).to_numpy()
        is_ball = (raw["object"] == "BALL").to_numpy()
        out = pd.DataFrame({
            "frame_id": raw["frame"].astype("int64"),
            "period_id": raw["period"].astype("int64"),
            "timestamp": raw["t"].astype("float64"),
            "player_id": np.where(is_ball, BALL_ID, raw["object"]),
            "team_id": np.where(is_ball, BALL_ID, raw["team"].fillna("")),
            "x": flip * raw["x"] + PITCH_LENGTH / 2,
            "y": flip * raw["y"] + PITCH_WIDTH / 2,
            "vx": flip * raw["vx"],
            "vy": flip * raw["vy"],
        })
        return out[list(TRACKING_COLUMNS)].sort_values(["frame_id", "player_id"], kind="stable").reset_index(drop=True)


ADAPTERS: tuple[FeedAdapter, ...] = (SyntheticFeedAdapter(),)


def detect_adapter(path: Path) -> FeedAdapter:
    for adapter in ADAPTERS:
        if adapter.can_read(path):
            return adapter
    raise ValueError(f"no feed adapter recognises {path}")
