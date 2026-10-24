"""The proof behind every claim the viewer shows: who, which frame, what was measured, which records.

For each contribution of the account, and for each told beat of the story, a
proof binds the claim to:

* ``players``: everyone its records name, with a role (``actor``, ``man``,
  ``runner``, ``won the ball``, ``used the space``, ``shooter``, ...);
* ``frames``: the tracking frames it cites (id, timestamp, match clock, and
  what the frame is: "where the run ended", "the decision");
* ``events``: the on-ball events it cites (action id, the feed's event id,
  type, player, time);
* ``measured``: the number the engine computed for it, the metric it is in,
  a ``statement`` that says the number with its meaning, and ``plain``, the
  same meaning without a number (Fan);
* ``focus_frame``: the frame the viewer seeks to when the proof is opened.

Everything is read off the ``CausalAccount`` and the ``MatchContext`` (and the
feed's event ids from the match's actions): nothing is derived beyond
formatting, so a missing field is simply absent. Deterministic.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from replay_room.contracts.causal_account import CausalAccount, Contribution, Link
from replay_room.contracts.context import ContextFact, MatchContext
from replay_room.contracts.match import MatchMeta
from replay_room.contracts.refs import EventRef, FrameRef
from replay_room.explain.compose import base_action, chance_band, noun
from replay_room.render.display import match_clock, value_unit


class Prover:
    def __init__(self, account: CausalAccount, actions: pd.DataFrame, meta: MatchMeta,
                 context: MatchContext | None = None):
        self.a = account
        self.meta = meta
        self.context = context
        self.by_id = actions.set_index("action_id")
        self.people = {p.player_id: p for p in account.participants}
        self.teams = {t.team_id: t.name for t in account.teams}
        self.T = self.teams[account.outcome.beneficiary_team_id]
        self.contribs = {c.contribution_id: c for c in account.contributions}
        self.V = account.outcome.value

    # ------------------------------------------------------------------ pieces

    def name(self, pid: str | None) -> str:
        p = self.people.get(pid or "")
        return p.name if p else (pid or "")

    def player(self, pid: str, role: str) -> dict[str, Any]:
        p = self.people.get(pid)
        return {"player_id": pid, "name": p.name if p else pid, "shirt_number": p.shirt_number if p else None,
                "team_id": p.team_id if p else None, "role": role}

    def frame(self, r: FrameRef, what: str) -> dict[str, Any]:
        return {"frame_id": r.frame_id, "timestamp": round(r.timestamp, 2),
                "match_clock": match_clock(self.meta, self.a.moment.period_id, r.timestamp), "what": what}

    def event(self, r: EventRef) -> dict[str, Any]:
        row = self.by_id.loc[r.action_id]
        return {"action_id": r.action_id, "original_event_id": r.original_event_id, "type": str(row["type_name"]),
                "result": str(row["result_name"]), "player_id": str(row["player_id"]),
                "player": self.name(str(row["player_id"])), "t": round(r.time_seconds, 2),
                "match_clock": match_clock(self.meta, r.period_id, r.time_seconds)}

    @staticmethod
    def _merge(*parts: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {"players": [], "frames": [], "events": [], "measured": [], "focus_frame": None}
        for p in parts:
            for key in ("players", "frames", "events"):
                seen = {(x.get("player_id"), x.get("frame_id"), x.get("action_id")) for x in out[key]}
                for x in p.get(key, []):
                    k = (x.get("player_id"), x.get("frame_id"), x.get("action_id"))
                    if k not in seen:
                        out[key].append(x)
                        seen.add(k)
            out["measured"] += p.get("measured", [])
            out["focus_frame"] = out["focus_frame"] or p.get("focus_frame")
        return out

    def _boost(self, c: Contribution) -> str:
        share = abs(c.effect) / self.V if self.V > 0 else 0
        if c.effect < 0:
            return f"it set {self.T} back"
        if share >= 0.45:
            return f"it gave {self.T}'s chance a huge boost"
        if share >= 0.2:
            return f"it gave {self.T}'s chance a big boost"
        return f"it gave {self.T}'s chance a small boost"

    # ------------------------------------------------------------------ claims

    def contribution(self, c: Contribution) -> dict[str, Any]:
        """The proof of one fact of the account."""
        who = self.name(c.player_id)
        players = [self.player(c.player_id, "actor")]
        frames, events = [], []
        for r in c.evidence:
            if r.kind == "event":
                events.append(self.event(r))
            else:
                frames.append(self.frame(r, "the decisive frame" if not frames else "where it started"))
                players += [self.player(p, "named") for p in r.player_ids if p != c.player_id]
        if c.kind == "marking_break" and len(players) > 1:
            players[1]["role"] = "man"
        unit = value_unit(c)
        if c.kind == "chance_denied":
            what = "save" if base_action(c.action) == "keeper_save" else "miss" if c.team_id == \
                self.a.outcome.beneficiary_team_id else noun(c.action)
            statement = f"{who}'s {what} took away a chance worth {self.V:.3f} (xG): {round(100 * self.V)}% to score."
            plain = f"It was {chance_band(self.V)}, and {who}'s {what} ended it."
        elif c.track == "off_ball":
            m = c.metrics
            if c.kind == "space_creation":
                statement = (f"{who}'s run added control worth {c.effect:+.3f} of a scoring chance at the shot spot "
                             f"(pitch control), running at {m.get('speed', 0):.1f} m/s.")
                plain = f"{who}'s run made the spot the shot came from more dangerous."
            elif c.kind == "marking_break" and "separation_end" in m:
                man = players[1]["name"] if len(players) > 1 else "the runner"
                statement = (f"{who} let {man} get from {m['separation_start']:.1f} m to {m['separation_end']:.1f} m "
                             f"away, giving up space worth {c.effect:+.3f} of a scoring chance (pitch control).")
                plain = f"{who} lost {man}, and {self.T} got space where it mattered."
            else:
                statement = (f"{who}'s position gave up space worth {c.effect:+.3f} of a scoring chance at the shot "
                             f"spot (pitch control).")
                plain = f"{who} gave up the space the shot came from."
        else:
            action = noun(c.action)
            if "xt_start" in c.metrics and "xg" in c.metrics:
                statement = (f"Shooting from there turned {c.metrics['xt_start']:.3f} of threat into a "
                             f"{c.metrics['xg']:.3f} chance ({unit} {c.effect:+.3f}).")
                plain = f"Shooting from there made it {chance_band(c.metrics['xg'])}."
            elif "outcome_value" in c.metrics:
                statement = (f"{who}'s {action} turned the threat {self.T} held there into a "
                             f"{c.metrics['outcome_value']:.3f} chance ({unit} {c.effect:+.3f}).")
                plain = f"{who}'s {action} gave {self.T} a big chance."
            else:
                verb = "raised" if c.effect >= 0 else "lowered"
                statement = (f"{who}'s {action} {verb} {self.T}'s chance of scoring by {abs(c.effect):.3f} "
                             f"({unit}).")
                plain = f"{who}'s {action}: {self._boost(c)}."
        measured = {"metric": unit, "value": round(c.effect, 6), "statement": statement, "plain": plain,
                    "magnitude": round(abs(c.effect) / max(abs(x.effect) for x in self.a.contributions), 3)}
        return {"players": players, "frames": frames, "events": events, "measured": [measured],
                "focus_frame": frames[0]["frame_id"] if frames else None}

    def link(self, k: Link) -> dict[str, Any]:
        m = k.metrics
        D, R = self.name(k.defender_id), self.name(k.runner_id)
        players = [self.player(k.defender_id, "defender")]
        if k.runner_id:
            players.append(self.player(k.runner_id, "runner"))
        if k.marked_player_id:
            players.append(self.player(k.marked_player_id, "man"))
        frames = [self.frame(k.evidence[0], "where the run began"), self.frame(k.evidence[-1], "where the run ended")]
        events = []
        used = ""
        if k.enabled is not None:
            ev = self.event(k.enabled)
            events.append(ev)
            if ev["player_id"] in self.people:
                players.append(self.player(ev["player_id"], "used the space"))
            used = f" {ev['player']}'s {noun(ev['type'])} ({ev['original_event_id']}) then went into that zone."
        moved = (f"{D} ended {m['spot_distance_end']:.1f} m from the shot spot, having started "
                 f"{m['spot_distance_start']:.1f} m from it")
        how = {"run_past": f"; {R} passed within {m.get('closest_approach', 0):.1f} m of {D} on the way in",
               "dragged_out": f"; {D} moved with {R}, {m.get('follow_distance', 0):.1f} m apart on average",
               "decoy_run": f"; {R}'s run took {D} along, {m.get('follow_distance', 0):.1f} m apart on average",
               "lost_man": ""}[k.kind]
        statement = f"{moved}{how} ({k.zone}).{used}"
        plain = {"run_past": f"{R} ran past {D}, who had stepped away from {k.zone}.",
                 "dragged_out": f"{R}'s run pulled {D} out of {k.zone}.",
                 "decoy_run": f"{R}'s run took {D} away from {self.name(k.marked_player_id)}.",
                 "lost_man": f"{D} lost {self.name(k.marked_player_id)}, who moved towards {k.zone}."}[k.kind]
        return {"players": players, "frames": frames, "events": events, "focus_frame": k.evidence[-1].frame_id,
                "measured": [{"metric": "tracking", "value": m.get("spot_distance_end"), "statement": statement,
                              "plain": plain, "magnitude": None}]}

    def context_fact(self, f: ContextFact) -> dict[str, Any]:
        team = self.teams[f.team_id]
        frames = [self.frame(r, "this moment") for r in f.evidence if r.kind == "frame"]
        events = [self.event(r) for r in f.evidence if r.kind == "event"]
        spread = f" (usually {f.spread[0]:.1f}–{f.spread[1]:.1f} m)" if f.spread else ""
        basis = f"over {f.sample_size} {'lost balls' if f.kind == 'counter_press' else 'defending spells'} " \
                f"in this match, {f.confidence} confidence"
        if f.kind == "line_height":
            statement = (f"{team}'s back line was {f.here:.1f} m from their goal here; the match median is "
                         f"{f.baseline:.1f} m{spread}, {basis}.")
            plain = f"{team}'s back line was standing {'higher' if f.direction == 'higher' else 'deeper'} than usual."
        elif f.kind == "marking_distance":
            statement = (f"Attackers in {team}'s third had {f.here:.1f} m to the nearest defender here; the match "
                         f"median is {f.baseline:.1f} m{spread}, {basis}.")
            plain = (f"{self.T}'s attackers had more room than usual." if f.direction == "higher"
                     else f"{team} were marking tighter than usual.")
        else:
            statement = (f"{team} won the ball back within {f.metrics['window_s']:.0f} s after "
                         f"{f.metrics['won_back']:.0f} of {f.metrics['losses']:.0f} other losses, {basis}; "
                         f"here they did not.")
            plain = f"{team} usually win the ball straight back; here they did not."
        return {"players": [], "frames": frames, "events": events,
                "focus_frame": frames[-1]["frame_id"] if frames else None,
                "measured": [{"metric": f.kind.replace("_", " "), "value": f.here, "statement": statement,
                              "plain": plain, "magnitude": None}]}

    def outcome(self) -> dict[str, Any]:
        o = self.a.outcome
        ev = self.event(o.ref)
        result = "scored" if o.scored else "did not score"
        statement = (f"{ev['player']}'s {noun(ev['type'])} ({ev['original_event_id']}) was worth {o.value:.3f} "
                     f"({'xG' if o.value_source == 'xg' else 'xT'}), {round(100 * o.value)}% to score, and {result}.")
        plain = f"It was {chance_band(o.value)}, and it {'went in' if o.scored else 'did not go in'}."
        players = [self.player(ev["player_id"], "shooter")] if ev["player_id"] in self.people else []
        return {"players": players, "frames": [], "events": [ev], "focus_frame": None,
                "measured": [{"metric": "xG" if o.value_source == "xg" else "xT", "value": round(o.value, 6),
                              "statement": statement, "plain": plain, "magnitude": None}]}

    def counterfactual(self, cid: str) -> dict[str, Any]:
        cf = next(x for x in self.a.counterfactuals if x.contribution_id == cid)
        c = self.contribs[cid]
        best = cf.best
        fix = lambda text: " ".join(self.name(w) if w in self.people else w for w in text.split())  # noqa: E731
        players = [self.player(c.player_id, "chose")]
        players += [self.player(a.target_player_id, "better option" if i == 0 else "other option")
                    for i, a in enumerate(cf.alternatives[:1]) if a.target_player_id]
        arrive = f", {round(100 * best.completion_prob)}% likely to arrive" if best.completion_prob is not None else ""
        statement = (f"Chosen: {fix(cf.chosen)}, worth {cf.chosen_value:.3f}. Better: {fix(best.description)}, worth "
                     f"{best.value:.3f}{arrive} (the pass model, from the positions at the decision frame).")
        option = fix(best.description)
        plain = f"{option[:1].upper()}{option[1:]} was the better option."
        return {"players": players, "frames": [self.frame(cf.decision_frame, "the decision")],
                "events": [self.event(r) for r in c.evidence if r.kind == "event"],
                "focus_frame": cf.decision_frame.frame_id,
                "measured": [{"metric": "pass model", "value": round(best.value - cf.chosen_value, 6),
                              "statement": statement, "plain": plain, "magnitude": None}]}

    def beat(self, b: dict[str, Any]) -> dict[str, Any]:
        """The proof of one told beat: its fact, and its link when it is told through one."""
        links = {k.link_id: k for k in self.a.links}
        facts = {f.fact_id: f for f in (self.context.facts if self.context else ())}
        if b["kind"] == "outcome":
            return self.outcome()
        if b["kind"] == "counterfactual":
            return self.counterfactual(b["contribution_id"])
        if b["kind"] == "context":
            return self.context_fact(facts[b["context_fact_id"]])
        parts = []
        if b.get("link_id"):
            parts.append(self.link(links[b["link_id"]]))
        if b.get("contribution_id"):
            parts.append(self.contribution(self.contribs[b["contribution_id"]]))
        return self._merge(*parts)


def proofs(account: CausalAccount, actions: pd.DataFrame, meta: MatchMeta, context: MatchContext | None,
           beats: list[dict[str, Any]]) -> dict[str, Any]:
    p = Prover(account, actions, meta, context)
    return {"contributions": {c.contribution_id: p._merge(p.contribution(c)) for c in account.contributions},
            "beats": {b["beat_id"]: p.beat(b) for b in beats}}
