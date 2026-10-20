"""Deterministic synthetic match generator (events + tracking).

A small agent simulation, not a physics engine: two teams hold a formation
shape that slides with the ball, the nearest defender presses, others mark,
attackers make forward runs, and the ball carrier carries, passes, shoots or
loses duels. Every on-ball event and every 10 Hz frame comes from the same
simulated state, so events and tracking agree with each other.

Output is a *raw provider-style feed* (see ``data/schema/DATA_CONTRACT.md``),
deliberately not in the canonical frame, so the feed adapter does real
normalisation and the generator exercises the same path a real feed will:

    <out>/meta.json          match metadata, teams, periods, generator seed
    <out>/events.jsonl       one raw event per line
    <out>/tracking.csv.gz    one row per object per frame (ball included)

Reproducibility: ``generate_match(seed)`` is a pure function of its arguments.
It simulates attempt 0, 1, 2, ... (each seeded from ``(seed, attempt)``) and
keeps the first match with at least one goal preceded by a >= 3-pass build-up.

    python -m replay_room.ingest.generator --seed 7 --out data/fixtures/synthetic_match_01
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

FEED_VERSION = "synthetic-v1"
GENERATOR_VERSION = "1"
FPS = 10
DT = 1.0 / FPS
L, W = 105.0, 68.0
CY = W / 2
GOAL_HALF_WIDTH = 3.66
MAX_ATTEMPTS = 50

# (position, depth fraction, width fraction); depth 0 = own goal line.
FORMATIONS: dict[str, list[tuple[str, float, float]]] = {
    "4-3-3": [
        ("GK", 0.0, 0.5),
        ("DF", 0.18, 0.12), ("DF", 0.15, 0.38), ("DF", 0.15, 0.62), ("DF", 0.18, 0.88),
        ("MF", 0.40, 0.25), ("MF", 0.34, 0.50), ("MF", 0.40, 0.75),
        ("FW", 0.62, 0.15), ("FW", 0.68, 0.50), ("FW", 0.62, 0.85),
    ],
    "4-4-2": [
        ("GK", 0.0, 0.5),
        ("DF", 0.18, 0.12), ("DF", 0.15, 0.38), ("DF", 0.15, 0.62), ("DF", 0.18, 0.88),
        ("MF", 0.40, 0.12), ("MF", 0.37, 0.38), ("MF", 0.37, 0.62), ("MF", 0.40, 0.88),
        ("FW", 0.66, 0.38), ("FW", 0.66, 0.62),
    ],
}
SHIRT_NUMBERS = [1, 2, 5, 6, 3, 8, 4, 10, 7, 9, 11]
TEAMS = [
    {"id": "NBR", "name": "Northbridge FC", "formation": "4-3-3"},
    {"id": "EPA", "name": "Eastport Athletic", "formation": "4-4-2"},
]
_FIRST = ["Alex", "Sam", "Jordan", "Casey", "Riley", "Morgan", "Jamie", "Taylor", "Robin", "Drew", "Quinn"]
_LAST = ["Hale", "Okafor", "Brandt", "Silva", "Novak", "Mensah", "Larsen", "Costa", "Adeyemi", "Byrne", "Ferraro"]


@dataclass
class SyntheticMatch:
    """Raw feed in memory: what ``write_fixture`` serialises."""

    meta: dict[str, Any]
    events: list[dict[str, Any]]
    tracking: pd.DataFrame


# --------------------------------------------------------------------------- helpers


def _unit(v: np.ndarray) -> np.ndarray:
    n = float(np.hypot(v[0], v[1]))
    return v / n if n > 1e-9 else np.zeros(2)


def _seg_dist(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    """Distance from p to segment ab, and the projection parameter in [0, 1]."""
    ab = b - a
    denom = float(ab @ ab)
    s = 0.0 if denom < 1e-9 else float(np.clip((p - a) @ ab / denom, 0.0, 1.0))
    return float(np.hypot(*(a + s * ab - p))), s


class _Sim:
    """One simulated match in the canonical frame (home attacks +x throughout)."""

    def __init__(self, rng: np.random.Generator, period_seconds: float, n_periods: int):
        self.rng = rng
        self.period_steps = int(round(period_seconds * FPS))
        self.n_periods = n_periods

        self.ids: list[str] = []
        self.team: list[int] = []
        self.role: list[str] = []
        slots = []
        for ti, team in enumerate(TEAMS):
            for (role, fx, fy), num in zip(FORMATIONS[team["formation"]], SHIRT_NUMBERS):
                self.ids.append(f"{team['id']}-{num:02d}")
                self.team.append(ti)
                self.role.append(role)
                slots.append((fx, fy))
        self.n = len(self.ids)
        self.team_arr = np.array(self.team)
        self.slots = np.array(slots)
        self.max_speed = np.array([6.0 if r == "GK" else 7.6 + 0.6 * rng.random() for r in self.role])
        self.phase = rng.uniform(0, 2 * math.pi, size=(self.n, 2))
        self.right_footed = rng.random(self.n) < 0.75

        self.pos = np.zeros((self.n, 2))
        self.vel = np.zeros((self.n, 2))
        self.ball = np.array([L / 2, CY])
        self.beaten_until = np.full(self.n, -1.0)
        self.run_until = np.full(self.n, -1.0)
        self.run_target = np.zeros((self.n, 2))
        self.last_pressure: dict[int, float] = {}

        self.events: list[dict[str, Any]] = []
        self.frames: list[tuple[int, int, float, np.ndarray, np.ndarray, np.ndarray]] = []
        self.frame_id = 0
        self.score = [0, 0]

    # ----------------------------------------------------------------- geometry

    @staticmethod
    def sign(team: int) -> float:
        return 1.0 if team == 0 else -1.0

    def depth(self, team: int, x: float) -> float:
        return x if team == 0 else L - x

    def x_at(self, team: int, depth: float) -> float:
        return depth if team == 0 else L - depth

    def goal(self, team: int) -> np.ndarray:
        """Centre of the goal ``team`` attacks."""
        return np.array([L if team == 0 else 0.0, CY])

    def players_of(self, team: int) -> np.ndarray:
        return np.flatnonzero(self.team_arr == team)

    def gk(self, team: int) -> int:
        return int(self.players_of(team)[0])

    def nearest(self, idxs: np.ndarray, point: np.ndarray) -> tuple[int, float]:
        d = np.hypot(*(self.pos[idxs] - point).T)
        k = int(np.argmin(d))
        return int(idxs[k]), float(d[k])

    def def_line_depth(self, team: int) -> float:
        dfs = [i for i in self.players_of(team) if self.role[i] == "DF"]
        return min(self.depth(team, self.pos[i, 0]) for i in dfs)

    # ----------------------------------------------------------------- events

    def emit(self, type_: str, player: int | None, xy: np.ndarray | None, **extra: Any) -> dict[str, Any]:
        ev: dict[str, Any] = {
            "period": self.period,
            "t": round(self.k * DT, 1),
            "seq": len(self.events),
            "type": type_,
            "team": TEAMS[self.team[player]]["id"] if player is not None else None,
            "player": self.ids[player] if player is not None else None,
        }
        if xy is not None:
            ev["x"], ev["y"] = float(xy[0]), float(xy[1])
        ev.update(extra)
        self.events.append(ev)
        return ev

    def set_possession(self, team: int, player: int) -> None:
        if team != self.poss_team:
            self.emit("PossessionChange", player, self.ball.copy())
        self.poss_team = team

    # ----------------------------------------------------------------- lifecycle

    def run(self) -> None:
        for period in range(1, self.n_periods + 1):
            self.period = period
            self.k = 0
            self.poss_team = -1
            self.emit("PeriodStart", None, None)
            self.kickoff_shape(kicking=0 if period == 1 else 1, snap=True)
            self.start_kickoff(kicking=0 if period == 1 else 1)
            while self.k <= self.period_steps:
                self.record_frame()
                if self.k == self.period_steps:
                    break
                self.decide()
                self.move()
                self.k += 1
            self.close_period()
            self.emit("PeriodEnd", None, None)

    def close_period(self) -> None:
        """Resolve an action still in flight at the whistle so every event has an outcome."""
        if self.mode == "flight":
            ev = self.flight["event"]
            ev.setdefault("outcome", "incomplete")
            ev.setdefault("end_x", float(np.clip(self.ball[0], 0, L)))
            ev.setdefault("end_y", float(np.clip(self.ball[1], 0, W)))
        elif self.mode == "owned":
            self.end_carry(self.owner)

    def record_frame(self) -> None:
        self.frames.append((self.frame_id, self.period, round(self.k * DT, 1),
                            self.pos.copy(), self.vel.copy(), self.ball.copy()))
        self.frame_id += 1

    def kickoff_shape(self, kicking: int, snap: bool = False) -> np.ndarray:
        targets = np.zeros((self.n, 2))
        for i in range(self.n):
            ti = self.team[i]
            fx, fy = self.slots[i]
            d = 4.0 if self.role[i] == "GK" else min(10 + (fx - 0.15) / 0.53 * 36, 49.0)
            targets[i] = (self.x_at(ti, d), CY + (fy - 0.5) * 50)
        striker = self.striker(kicking)
        targets[striker] = (L / 2 - self.sign(kicking) * 0.5, CY)
        if snap:
            self.pos[:] = targets
            self.vel[:] = 0
            self.ball[:] = (L / 2, CY)
        return targets

    def striker(self, team: int) -> int:
        fws = [i for i in self.players_of(team) if self.role[i] == "FW"]
        return min(fws, key=lambda i: abs(self.slots[i, 1] - 0.5))

    def start_kickoff(self, kicking: int) -> None:
        self.mode = "owned"
        kicker = self.striker(kicking)
        mfs = [i for i in self.players_of(kicking) if self.role[i] == "MF"]
        receiver = min(mfs, key=lambda i: abs(self.slots[i, 1] - 0.5))
        self.owner = kicker
        self.ball[:] = self.pos[kicker]
        self.set_possession(kicking, kicker)
        self.start_pass(kicker, receiver, kind="KickOff", force_success=True)

    # ----------------------------------------------------------------- decisions

    def decide(self) -> None:
        t = self.k * DT
        if self.mode == "flight" and self.flight["remaining"] == 0:
            self.arrive()
        elif self.mode == "dead":
            self.dead["timer"] -= 1
            if self.dead["timer"] <= 0:
                self.restart()
        elif self.mode == "owned":
            self.owned_tick(t)

    def owned_tick(self, t: float) -> None:
        o = self.owner
        opp = self.players_of(1 - self.team[o])
        dists = np.hypot(*(self.pos[opp] - self.pos[o]).T)
        for j, d in zip(opp, dists):
            j = int(j)
            if self.role[j] == "GK":
                continue
            if d < 2.5 and t - self.last_pressure.get(j, -99.0) >= 2.0:
                self.emit("Pressure", j, self.pos[j].copy(), target=self.ids[o])
                self.last_pressure[j] = t
            if d < 1.3 and self.beaten_until[j] < t and self.role[o] != "GK" and self.rng.random() < 0.12:
                if self.rng.random() < 0.5:  # tackle wins the ball
                    self.end_carry(o)
                    self.emit("Tackle", j, self.pos[o].copy(), outcome="won")
                    self.beaten_until[o] = t + 1.5
                    self.take_ball(j)
                    self.hold = self.rng.uniform(0.4, 1.2)
                else:  # carrier beats the defender
                    self.emit("TakeOn", o, self.pos[o].copy(), outcome="won")
                    self.beaten_until[j] = t + 2.0
                return
        under_pressure = float(dists.min()) < 3.0
        self.hold -= DT * (2.0 if under_pressure else 1.0)
        if self.hold > 0:
            return
        team = self.team[o]
        to_goal = float(np.hypot(*(self.goal(team) - self.pos[o])))
        depth = self.depth(team, self.pos[o, 0])
        p_shoot = 0.9 if to_goal < 14 else 0.45 if to_goal < 20 else 0.1 if to_goal < 26 else 0.0
        if depth > 75 and self.rng.random() < p_shoot:
            self.shoot(o)
        else:
            self.choose_pass(o)

    def take_ball(self, i: int) -> None:
        self.mode = "owned"
        self.owner = i
        self.carry_start = (self.k * DT, self.pos[i].copy())
        self.set_possession(self.team[i], i)

    def end_carry(self, i: int) -> None:
        t0, p0 = self.carry_start
        if float(np.hypot(*(self.pos[i] - p0))) >= 3.0 and self.k * DT - t0 > 0.15:
            ev = self.emit("Carry", i, p0, end_x=float(self.pos[i, 0]), end_y=float(self.pos[i, 1]))
            ev["t"] = round(t0, 1)

    def choose_pass(self, o: int) -> None:
        team = self.team[o]
        mates = [int(i) for i in self.players_of(team) if i != o]
        opp = self.players_of(1 - team)
        scores, cands = [], []
        for m in mates:
            if self.role[m] == "GK" and self.role[o] not in ("DF",):
                continue
            d = float(np.hypot(*(self.pos[m] - self.pos[o])))
            if not 5.0 <= d <= 45.0:
                continue
            progress = self.depth(team, self.pos[m, 0]) - self.depth(team, self.pos[o, 0])
            openness = min(float(np.hypot(*(self.pos[opp] - self.pos[m]).T).min()), 10.0)
            lane = min(min(_seg_dist(self.pos[j], self.pos[o], self.pos[m])[0] for j in opp), 8.0)
            score = 0.09 * progress + 0.3 * openness + 0.3 * lane - 0.03 * d
            if self.run_until[m] > self.k * DT:
                score += 1.0
            scores.append(score)
            cands.append(m)
        if not cands:
            self.hold = 0.5
            return
        p = np.exp(2.0 * (np.array(scores) - max(scores)))
        receiver = cands[int(self.rng.choice(len(cands), p=p / p.sum()))]
        self.start_pass(o, receiver, kind="GoalKick" if self.pending_goalkick else "Pass")

    def start_pass(self, o: int, r: int, kind: str = "Pass", force_success: bool = False) -> None:
        self.pending_goalkick = False
        team = self.team[o]
        if kind == "Pass":
            self.end_carry(o)
        d = float(np.hypot(*(self.pos[r] - self.pos[o])))
        speed = float(np.clip(13 + 0.15 * d, 13, 22))
        steps = max(4, int(round(d / speed * FPS)))
        aim = self.pos[r] + self.vel[r] * steps * DT * 0.9
        aim = np.clip(aim, [1, 1], [L - 1, W - 1])
        opp = self.players_of(1 - team)
        lane, s, j = min((*_seg_dist(self.pos[j], self.pos[o], aim), int(j)) for j in opp)
        openness = float(np.hypot(*(self.pos[opp] - aim).T).min())
        p_ok = 0.98 - 0.005 * d - 0.07 * max(0.0, 2.5 - lane) - 0.05 * max(0.0, 2.5 - openness)
        success = force_success or self.rng.random() < float(np.clip(p_ok, 0.3, 0.97))
        cross = (kind == "Pass" and self.depth(team, self.pos[o, 0]) > 78 and abs(self.pos[o, 1] - CY) > 18
                 and self.depth(team, aim[0]) > 88 and abs(aim[1] - CY) < 20)
        foot = "right_foot" if self.right_footed[o] else "left_foot"
        ev = self.emit(kind, o, self.pos[o].copy(), body_part=foot, cross=cross, recipient=self.ids[r])
        if success:
            target, meet = r, aim
        else:
            if s < 0.15:  # blocked right at the passer: intercept a little further out
                s = 0.25
            target, meet = j, self.pos[o] + s * (aim - self.pos[o])
            steps = max(3, int(round(steps * max(s, 0.3))))
        self.mode = "flight"
        self.owner = None
        self.flight = {"kind": "pass", "event": ev, "target": target, "meet": meet, "remaining": steps,
                       "success": success, "passer": o, "cross": cross}

    def shoot(self, o: int) -> None:
        self.end_carry(o)
        team = self.team[o]
        gx = self.goal(team)[0]
        dist = float(np.hypot(*(self.goal(team) - self.pos[o])))
        header = self.headed_chance
        on_target = self.rng.random() < (0.35 if header else 0.45)
        if on_target:
            y = CY + self.rng.uniform(-GOAL_HALF_WIDTH + 0.3, GOAL_HALF_WIDTH - 0.3)
            p_goal = float(np.clip(1.2 * math.exp(-0.12 * dist), 0.05, 0.6)) * (0.7 if header else 1.0)
            outcome = "goal" if self.rng.random() < p_goal else "saved"
        else:
            side = 1 if self.rng.random() < 0.5 else -1
            y = float(np.clip(CY + side * (GOAL_HALF_WIDTH + self.rng.uniform(0.4, 5.0)), 0, W))
            outcome = "off_target"
        part = "head" if header else ("right_foot" if self.right_footed[o] else "left_foot")
        ev = self.emit("Shot", o, self.pos[o].copy(), end_x=gx, end_y=float(y), outcome=outcome, body_part=part)
        beyond = gx + self.sign(team) * (1.2 if outcome == "goal" else 2.5)
        meet = np.array([gx - self.sign(team) * 0.8, y]) if outcome == "saved" else np.array([beyond, y])
        steps = max(3, int(round(float(np.hypot(*(meet - self.ball))) / 22.0 * FPS)))
        self.mode = "flight"
        self.owner = None
        keeper = self.gk(1 - team)
        self.flight = {"kind": "shot", "event": ev, "outcome": outcome, "remaining": steps, "shooter": o,
                       "target": keeper if outcome == "saved" else None, "meet": meet}

    def arrive(self) -> None:
        f = self.flight
        ev = f["event"]
        if f["kind"] == "pass":
            ev["end_x"], ev["end_y"] = float(self.ball[0]), float(self.ball[1])
            ev["outcome"] = "complete" if f["success"] else "incomplete"
            r = f["target"]
            if not f["success"]:
                self.emit("Interception", r, self.ball.copy())
            self.take_ball(r)
            self.headed_chance = f["cross"] and self.depth(self.team[r], self.pos[r, 0]) > 88
            self.hold = 0.1 if self.headed_chance else self.rng.uniform(0.6, 2.2)
            return
        team = self.team[f["shooter"]]
        outcome = f["outcome"]
        self.headed_chance = False
        if outcome == "saved":
            ev["end_x"], ev["end_y"] = float(np.clip(self.ball[0], 0, L)), float(np.clip(self.ball[1], 0, W))
            keeper = f["target"]
            self.emit("KeeperSave", keeper, self.ball.copy())
            self.take_ball(keeper)
            self.hold = self.rng.uniform(1.5, 3.0)
            return
        self.mode = "dead"
        if outcome == "goal":
            self.score[team] += 1
            self.dead = {"kind": "kickoff", "team": 1 - team, "timer": 7 * FPS, "dest": np.array([L / 2, CY])}
        else:
            self.emit("BallOut", None, self.ball.copy())
            keeper = self.gk(1 - team)
            spot = np.array([self.x_at(1 - team, 5.5), CY + (1 if self.ball[1] > CY else -1) * 9.0])
            self.dead = {"kind": "goalkick", "team": 1 - team, "timer": 5 * FPS, "dest": spot, "keeper": keeper}

    def restart(self) -> None:
        dead = self.dead
        if dead["kind"] == "kickoff":
            self.start_kickoff(dead["team"])
            return
        keeper = dead["keeper"]
        self.ball[:] = self.pos[keeper]
        self.take_ball(keeper)
        self.pending_goalkick = True
        self.choose_pass(keeper)
        if self.mode == "owned":  # nobody in range: just keep it, try again shortly
            self.hold = 0.5

    # ----------------------------------------------------------------- movement

    def targets(self) -> tuple[np.ndarray, np.ndarray]:
        t = self.k * DT
        tgt = np.zeros((self.n, 2))
        cap = self.max_speed.copy()
        if self.mode == "dead" and self.dead["kind"] == "kickoff":
            tgt[:] = self.kickoff_shape(self.dead["team"])
            return tgt, cap * 0.6
        attacking = self.poss_team
        ball = self.ball
        for ti in (0, 1):
            idx = self.players_of(ti)
            in_poss = ti == attacking
            bd = self.depth(ti, ball[0])
            if in_poss:
                line, block, width, shift = float(np.clip(bd - 32, 10, 52)), 44.0, 58.0, 0.2
            else:
                line, block, width, shift = float(np.clip(bd * 0.5 - 2, 8, 38)), 32.0, 44.0, 0.35
            for i in idx:
                fx, fy = self.slots[i]
                if self.role[i] == "GK":
                    d = float(np.clip(3 + 0.08 * bd, 3, 14))
                    y = CY + 0.15 * (ball[1] - CY)
                else:
                    d = line + (fx - 0.15) / 0.53 * block
                    y = CY + (fy - 0.5) * width + shift * (ball[1] - CY)
                noise = 1.5 * np.sin(self.phase[i] + t * np.array([0.3, 0.25]))
                tgt[i] = (self.x_at(ti, d), y) + noise
            if in_poss:
                self.attack_targets(ti, idx, tgt, cap, t)
            else:
                self.defend_targets(ti, idx, tgt, cap)
        if self.mode == "dead" and self.dead["kind"] == "goalkick":
            k = self.dead["keeper"]
            tgt[k] = self.dead["dest"]
        if self.mode == "flight":
            f = self.flight
            if f["target"] is not None:
                tgt[f["target"]] = f["meet"]
                cap[f["target"]] = self.max_speed[f["target"]]
        return tgt, cap

    def attack_targets(self, ti: int, idx: np.ndarray, tgt: np.ndarray, cap: np.ndarray, t: float) -> None:
        opp_line = L - self.def_line_depth(1 - ti)  # opponents' last line, in our depth
        ball_depth = self.depth(ti, self.ball[0])
        for i in idx:
            if self.role[i] == "GK":
                continue
            if self.mode == "owned" and i == self.owner:
                continue
            if self.run_until[i] > t:
                tgt[i] = self.run_target[i]
                continue
            hazard = {"FW": 0.25, "MF": 0.07}.get(self.role[i], 0.0)
            if ball_depth > 35 and self.rng.random() < hazard * DT:
                d = min(opp_line + 9.0, 99.0)
                y = float(np.clip(self.pos[i, 1] + self.rng.normal(0, 6) + 0.3 * (CY - self.pos[i, 1]), 6, W - 6))
                self.run_target[i] = (self.x_at(ti, d), y)
                self.run_until[i] = t + 2.5
                tgt[i] = self.run_target[i]
                continue
            d = self.depth(ti, tgt[i, 0])
            if d > opp_line + 0.5:  # hold the line rather than stand offside
                tgt[i, 0] = self.x_at(ti, opp_line + 0.5)
        if self.mode == "owned" and self.team[self.owner] == ti:
            o = self.owner
            if self.role[o] == "GK":
                tgt[o] = self.pos[o]
            else:
                opp = self.players_of(1 - ti)
                j, dj = self.nearest(opp, self.pos[o])
                away = _unit(self.pos[o] - self.pos[j]) * (3.0 / max(dj, 1.0))
                direction = _unit(_unit(self.goal(ti) - self.pos[o]) + away)
                carry_to = self.pos[o] + 5.0 * direction
                carry_to[0] = self.x_at(ti, min(self.depth(ti, carry_to[0]), L - 4.0))
                tgt[o] = np.clip(carry_to, [1.0, 1.0], [L - 1.0, W - 1.0])
                cap[o] = 5.5

    def defend_targets(self, ti: int, idx: np.ndarray, tgt: np.ndarray, cap: np.ndarray) -> None:
        outfield = np.array([i for i in idx if self.role[i] != "GK"])
        ball = self.ball
        dists = np.hypot(*(self.pos[outfield] - ball).T)
        order = outfield[np.argsort(dists)]
        own_goal = self.goal(1 - ti)
        presser, cover = int(order[0]), int(order[1])
        tgt[presser] = ball + _unit(own_goal - ball) * 1.0
        tgt[cover] = ball + _unit(own_goal - ball) * 8.0
        attackers = [a for a in self.players_of(1 - ti) if self.role[a] != "GK"]
        for i in order[2:]:
            i = int(i)
            a, da = self.nearest(np.array(attackers), tgt[i])
            if da < 15.0:
                mark = self.pos[a] + _unit(own_goal - self.pos[a]) * 1.5
                tgt[i] = 0.65 * tgt[i] + 0.35 * mark
            cap[i] *= 0.9

    def move(self) -> None:
        tgt, cap = self.targets()
        delta = tgt - self.pos
        dist = np.hypot(delta[:, 0], delta[:, 1])
        speed = np.minimum(cap, dist * 1.2)
        desired = delta / np.maximum(dist, 1e-9)[:, None] * speed[:, None]
        acc = (desired - self.vel) / DT
        acc_n = np.hypot(acc[:, 0], acc[:, 1])
        acc *= np.minimum(1.0, 5.0 / np.maximum(acc_n, 1e-9))[:, None]
        self.vel += acc * DT
        self.pos += self.vel * DT
        self.pos[:] = np.clip(self.pos, [-1.0, -1.0], [L + 1.0, W + 1.0])
        self.move_ball()

    def move_ball(self) -> None:
        if self.mode == "owned":
            o = self.owner
            facing = _unit(self.vel[o]) if np.hypot(*self.vel[o]) > 0.5 else np.array([self.sign(self.team[o]), 0.0])
            self.ball[:] = self.pos[o] + 0.5 * facing
        elif self.mode == "flight":
            f = self.flight
            dest = self.pos[f["target"]] if f["target"] is not None else f["meet"]
            self.ball += (dest - self.ball) / f["remaining"]
            f["remaining"] -= 1
        else:  # dead ball being returned to the restart spot
            step = self.dead["dest"] - self.ball
            n = float(np.hypot(*step))
            if n > 1e-9:
                self.ball += step * min(1.0, 10.0 * DT / n)

    headed_chance = False
    pending_goalkick = False


# --------------------------------------------------------------------------- feed output


def _has_goal_with_buildup(events: list[dict[str, Any]], min_passes: int = 3) -> bool:
    passes, team = 0, None
    for ev in sorted(events, key=lambda e: (e["period"], e["t"])):  # stable: ties keep feed order
        if ev["type"] in ("Pressure", "PeriodStart", "PeriodEnd", "BallOut", "PossessionChange"):
            continue
        if ev.get("team") != team:
            passes, team = 0, ev.get("team")
        if ev["type"] in ("Pass", "KickOff", "GoalKick") and ev.get("outcome") == "complete":
            passes += 1
        if ev["type"] == "Shot" and ev["outcome"] == "goal" and passes >= min_passes:
            return True
    return False


def _to_raw(x: float, y: float, home_attacks: str) -> tuple[float, float]:
    """Canonical (bottom-left origin, home -> +x) to the raw feed's centre-origin frame."""
    s = 1.0 if home_attacks == "+x" else -1.0
    return round(s * (x - L / 2), 2), round(s * (y - CY), 2)


def _home_attacks(period: int) -> str:
    return "+x" if period % 2 == 1 else "-x"  # sides switch at half time


def _build_feed(sim: _Sim, seed: int, attempt: int, period_seconds: float) -> SyntheticMatch:
    teams = {}
    for side, ti in (("home", 0), ("away", 1)):
        team = TEAMS[ti]
        players = []
        for k, i in enumerate(sim.players_of(ti)):
            players.append({
                "id": sim.ids[i],
                "name": f"{_FIRST[(k + 3 * ti) % 11]} {_LAST[(2 * k + ti) % 11]}",
                "number": int(sim.ids[i].split("-")[1]),
                "position": sim.role[i],
            })
        teams[side] = {"id": team["id"], "name": team["name"], "formation": team["formation"], "players": players}
    meta = {
        "feed_version": FEED_VERSION,
        "match_id": f"SYN-{seed:04d}",
        "competition": "Replay Room Synthetic League",
        "pitch": {"length_m": L, "width_m": W},
        "coordinates": {"origin": "centre", "units": "m", "y_axis": "towards the left touchline of a team attacking +x"},
        "frame_rate_hz": FPS,
        "periods": [{"id": p, "duration_s": period_seconds, "home_attacks": _home_attacks(p)}
                    for p in range(1, sim.n_periods + 1)],
        "teams": teams,
        "final_score": {"home": sim.score[0], "away": sim.score[1]},
        "generator": {"version": GENERATOR_VERSION, "seed": seed, "attempt": attempt},
    }

    events = []
    ordered = sorted(sim.events, key=lambda e: (e["period"], e["t"], e["seq"]))
    for n, ev in enumerate(ordered, start=1):
        dirn = _home_attacks(ev["period"])
        out = {"id": f"ev{n:05d}", "period": ev["period"], "t": ev["t"], "type": ev["type"]}
        for key in ("team", "player"):
            if ev[key] is not None:
                out[key] = ev[key]
        if "x" in ev:
            out["x"], out["y"] = _to_raw(ev["x"], ev["y"], dirn)
        if "end_x" in ev:
            out["end_x"], out["end_y"] = _to_raw(ev["end_x"], ev["end_y"], dirn)
        for key in ("outcome", "body_part", "recipient", "target"):
            if key in ev:
                out[key] = ev[key]
        if ev.get("cross"):
            out["cross"] = True
        events.append(out)

    rows = []
    obj_ids = sim.ids + ["BALL"]
    obj_teams = [TEAMS[t]["id"] for t in sim.team] + [""]
    frames = sim.frames
    for period in range(1, sim.n_periods + 1):
        pf = [f for f in frames if f[1] == period]
        balls = np.array([f[5] for f in pf])
        ball_v = np.gradient(balls, DT, axis=0) if len(pf) > 1 else np.zeros_like(balls)
        s = 1.0 if _home_attacks(period) == "+x" else -1.0
        for (fid, _, t, pos, vel, _ball), bv, bp in zip(pf, ball_v, balls):
            allpos = np.vstack([pos, bp])
            allvel = np.vstack([vel, bv])
            rx = s * (allpos[:, 0] - L / 2)
            ry = s * (allpos[:, 1] - CY)
            for k in range(len(obj_ids)):
                rows.append((fid, period, t, obj_ids[k], obj_teams[k],
                             rx[k], ry[k], s * allvel[k, 0], s * allvel[k, 1]))
    tracking = pd.DataFrame(rows, columns=["frame", "period", "t", "object", "team", "x", "y", "vx", "vy"])
    tracking[["x", "y", "vx", "vy"]] = tracking[["x", "y", "vx", "vy"]].round(2)
    return SyntheticMatch(meta=meta, events=events, tracking=tracking)


def generate_match(seed: int = 7, period_seconds: float = 150.0, n_periods: int = 2) -> SyntheticMatch:
    """Simulate a match; deterministic in ``(seed, period_seconds, n_periods)``."""
    for attempt in range(MAX_ATTEMPTS):
        rng = np.random.default_rng([seed, attempt])
        sim = _Sim(rng, period_seconds, n_periods)
        sim.run()
        if _has_goal_with_buildup(sim.events):
            return _build_feed(sim, seed, attempt, period_seconds)
    raise RuntimeError(f"no goal with build-up in {MAX_ATTEMPTS} attempts for seed {seed}")


def write_fixture(match: SyntheticMatch, out_dir: str | Path) -> Path:
    """Write the raw feed. Byte-identical for identical matches (gzip mtime pinned)."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "meta.json").write_text(json.dumps(match.meta, indent=2) + "\n", encoding="utf-8", newline="\n")
    lines = "".join(json.dumps(ev, separators=(",", ":")) + "\n" for ev in match.events)
    (out / "events.jsonl").write_text(lines, encoding="utf-8", newline="\n")
    csv = match.tracking.to_csv(index=False, float_format="%.2f", lineterminator="\n")
    buf = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buf, mtime=0) as gz:
        gz.write(csv.encode("utf-8"))
    (out / "tracking.csv.gz").write_bytes(buf.getvalue())
    return out


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Generate a deterministic synthetic match fixture.")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--period-seconds", type=float, default=150.0)
    ap.add_argument("--periods", type=int, default=2)
    ap.add_argument("--out", default="data/fixtures/synthetic_match_01")
    args = ap.parse_args(argv)
    match = generate_match(args.seed, args.period_seconds, args.periods)
    out = write_fixture(match, args.out)
    score = match.meta["final_score"]
    print(f"wrote {out}  attempt={match.meta['generator']['attempt']}  "
          f"events={len(match.events)}  tracking_rows={len(match.tracking)}  "
          f"score {score['home']}-{score['away']}")


if __name__ == "__main__":
    main()
