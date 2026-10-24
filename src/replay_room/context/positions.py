"""Positional facts for the deep telling (evidence treatise, L3). Deterministic, from the tracking.

For the frames the story shows (each fact's frame, each link's end, the
terminal action's frame) and the players those facts name:

* **position** at the frame, and the **average position** over the match's
  other frames in the same phase: the moment's attacking team on the ball,
  the ball in the same third of the pitch (from the attack's point of view).
  The sample is graded like the match context (``baselines.confidence`` on the
  number of possessions the frames come from); too few, and no average is
  given. The **deviation** from it, split into ``forward_m`` (towards the goal
  the player's team attacks) and ``lateral_m`` (towards their left);
* **distances**: to the ball, to the nearest opponent (who), and to the centre
  of the goal under attack;
* **marking**: for each link with a man, and each defensive off-ball fact, the
  defender's nearest attacker at the start of the span (within ``MARK_RADIUS``;
  further away he was marking no one), the separation at both ends, and
  whether it held (grew by less than ``MARK_GAIN_M``);
* **control swing**: the attacking team's pitch control (Build 3's influence
  model) at the shooting spot over each fact's span: an off-ball fact's or a
  link's measured span; an on-ball action's next ``SWING_S`` seconds (the
  ``SWING_S`` before it when the key event comes sooner).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from replay_room.attribution.links import MARK_RADIUS
from replay_room.attribution.off_ball import MARK_GAIN_M
from replay_room.attribution.zones import zone_name
from replay_room.context.baselines import _possession_at, confidence
from replay_room.contracts.causal_account import CausalAccount
from replay_room.contracts.context import ControlSwing, Marking, PlayerPosition
from replay_room.contracts.pitch import BALL_ID, PITCH_LENGTH, PITCH_WIDTH
from replay_room.detect.possessions import Possession
from replay_room.metrics.pitch_control import influence_control

SWING_S = 1.2


class Positions:
    def __init__(self, account: CausalAccount, actions: pd.DataFrame, tracking: pd.DataFrame, home_team_id: str,
                 possessions: tuple[Possession, ...]):
        self.a = account
        m = account.moment
        self.m = m
        self.home = home_team_id
        self.attacking_home = m.attacking_team_id == home_team_id
        w = m.window
        self.window = tracking[(tracking["frame_id"] >= w.frame_start) & (tracking["frame_id"] <= w.frame_end)]
        self.rows = self.window.set_index(["frame_id", "player_id"]).sort_index()
        self.stamps = self.window.drop_duplicates("frame_id").set_index("frame_id")["timestamp"]
        self.by_id = actions.set_index("action_id")
        key = self.by_id.loc[m.key_event_ref.action_id]
        self.spot = np.array([float(key["start_x"]), float(key["start_y"])])
        self.goal = np.array([PITCH_LENGTH if self.attacking_home else 0.0, PITCH_WIDTH / 2])
        self.key_frame = self._frame_of(m.key_event_ref.action_id)
        # the phase frames: the attacking team on the ball, outside this moment, with the ball's third
        frames = tracking.drop_duplicates("frame_id")[["frame_id", "period_id", "timestamp"]].reset_index(drop=True)
        owner = _possession_at(possessions, frames["period_id"].to_numpy(), frames["timestamp"].to_numpy())
        frames["spell"] = owner
        frames["ours"] = [o >= 0 and possessions[o].team_id == m.attacking_team_id for o in owner]
        ball = tracking[tracking["player_id"] == BALL_ID].set_index("frame_id")["x"]
        bx = frames["frame_id"].map(ball).to_numpy(float)
        frames["third"] = self._third(bx)
        outside = (frames["frame_id"] < w.frame_start) | (frames["frame_id"] > w.frame_end)
        self.phase = frames[frames["ours"] & outside]
        self.tracking = tracking

    def _third(self, x: np.ndarray) -> np.ndarray:
        ltr = x if self.attacking_home else PITCH_LENGTH - x
        return np.digitize(ltr, [PITCH_LENGTH / 3, 2 * PITCH_LENGTH / 3])

    def _frame_of(self, action_id: int) -> int:
        """The window frame nearest an event's time (the window lies in the event's period)."""
        t = float(self.by_id.at[action_id, "time_seconds"])
        return int((self.stamps - t).abs().idxmin())

    def at(self, frame_id: int, pid: str) -> np.ndarray:
        r = self.rows.loc[(frame_id, pid)]
        return np.array([float(r["x"]), float(r["y"])])

    def position(self, pid: str, frame_id: int) -> PlayerPosition | None:
        if (frame_id, pid) not in self.rows.index:
            return None
        here = self.at(frame_id, pid)
        f = self.rows.loc[frame_id]
        team = str(f.loc[pid, "team_id"])
        ball = f.loc[BALL_ID, ["x", "y"]].to_numpy(float) if BALL_ID in f.index else here
        rivals = f[(f["team_id"] != team) & (f.index != BALL_ID)]
        gaps = np.hypot(rivals["x"] - here[0], rivals["y"] - here[1])
        third = int(self._third(np.array([ball[0]]))[0])
        sample = self.phase[self.phase["third"] == third]
        mine = self.tracking[(self.tracking["player_id"] == pid) & self.tracking["frame_id"].isin(sample["frame_id"])]
        spells = int(sample[sample["frame_id"].isin(mine["frame_id"])]["spell"].nunique())
        grade = confidence(spells)
        out = dict(player_id=pid, team_id=team, frame_id=frame_id, timestamp=round(float(self.stamps[frame_id]), 2),
                   x=round(float(here[0]), 2), y=round(float(here[1]), 2),
                   phase="attacking" if team == self.m.attacking_team_id else "defending",
                   sample_frames=len(mine), sample_spells=spells, confidence=grade,
                   to_ball_m=round(float(np.hypot(*(ball - here))), 1), to_opponent_m=round(float(gaps.min()), 1),
                   nearest_opponent_id=str(gaps.idxmin()), to_goal_m=round(float(np.hypot(*(self.goal - here))), 1))
        if grade is not None:
            avg = mine[["x", "y"]].to_numpy(float).mean(axis=0)
            d = here - avg
            sign = 1.0 if team == self.home else -1.0  # the home team attacks +x
            out |= dict(average=(round(float(avg[0]), 1), round(float(avg[1]), 1)),
                        deviation_m=round(float(np.hypot(*d)), 1), forward_m=round(float(sign * d[0]), 1),
                        lateral_m=round(float(sign * d[1]), 1))
        return PlayerPosition(**out)

    def control(self, frame_id: int) -> float:
        rows = self.window[self.window["frame_id"] == frame_id]
        return float(influence_control(rows, self.m.attacking_team_id, self.spot[:1], self.spot[1:])[0, 0])

    def swing(self, label: str, a: int, b: int) -> ControlSwing:
        a, b = sorted((a, b))
        return ControlSwing(label=label, team_id=self.m.attacking_team_id,
                            zone=zone_name(*self.spot, self.attacking_home), frame_from=a, frame_to=b,
                            seconds=round(float(self.stamps[b] - self.stamps[a]), 1),
                            control_from=round(self.control(a), 2), control_to=round(self.control(b), 2))

    def marking(self, defender: str, a: int, b: int, man: str | None = None) -> Marking | None:
        if (a, defender) not in self.rows.index:
            return None
        if man is None:
            f = self.rows.loc[a]
            rivals = f[(f["team_id"] == self.m.attacking_team_id) & (f.index != BALL_ID)]
            d = self.at(a, defender)
            man = str(np.hypot(rivals["x"] - d[0], rivals["y"] - d[1]).idxmin())
        s0 = float(np.hypot(*(self.at(a, man) - self.at(a, defender))))
        if s0 > MARK_RADIUS:  # nobody that close: he was marking no one
            return None
        s1 = float(np.hypot(*(self.at(b, man) - self.at(b, defender))))
        return Marking(defender_id=defender, man_id=man, frame_from=a, frame_to=b, separation_from=round(s0, 1),
                       separation_to=round(s1, 1), held=s1 - s0 < MARK_GAIN_M)


def positional_facts(account: CausalAccount, actions: pd.DataFrame, tracking: pd.DataFrame, home_team_id: str,
                     possessions: tuple[Possession, ...]) -> tuple[tuple[PlayerPosition, ...], tuple[ControlSwing, ...],
                                                                    tuple[Marking, ...]]:
    p = Positions(account, actions, tracking, home_team_id, possessions)
    w = account.moment.window
    fps_frames = max(1, round(SWING_S * (len(p.stamps) - 1) / max(float(p.stamps.iloc[-1] - p.stamps.iloc[0]), 1e-6)))
    wanted: dict[tuple[str, int], None] = {}
    swings, markings = [], []
    for c in account.contributions:
        frames = [r.frame_id for r in c.evidence if r.kind == "frame"]
        named = [c.player_id, *(pid for r in c.evidence if r.kind == "frame" for pid in r.player_ids)]
        if frames:
            f, a, b = frames[0], min(frames), max(frames)
        else:
            f = p._frame_of(c.evidence[0].action_id)
            a, b = (f, f + fps_frames) if f + fps_frames <= p.key_frame else (max(f - fps_frames, w.frame_start), f)
        for pid in dict.fromkeys(named):
            wanted[(pid, f)] = None
        if a != b and c.kind != "chance_denied":
            swings.append(p.swing(c.contribution_id, a, min(b, w.frame_end)))
        if c.track == "off_ball" and c.team_id == account.moment.defending_team_id and a != b:
            man = next((pid for pid in named if pid != c.player_id), None)
            if (mk := p.marking(c.player_id, a, b, man)) is not None:
                markings.append(mk)
    for k in account.links:
        a, b = k.evidence[0].frame_id, k.evidence[-1].frame_id
        for pid in (k.defender_id, k.runner_id, k.marked_player_id):
            if pid:
                wanted[(pid, b)] = None
        swings.append(p.swing(k.link_id, a, b))
        if k.marked_player_id and (mk := p.marking(k.defender_id, a, b, k.marked_player_id)) is not None:
            markings.append(mk)
    shooter = str(p.by_id.loc[account.outcome.ref.action_id, "player_id"])
    wanted[(shooter, p.key_frame)] = None
    positions = tuple(pos for (pid, f) in wanted if (pos := p.position(pid, f)) is not None)
    unique = {(mk.defender_id, mk.man_id, mk.frame_from, mk.frame_to): mk for mk in markings}
    return positions, tuple(swings), tuple(unique.values())
