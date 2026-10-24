"""The deterministic Storyteller: tells a framing plan in plain, connected English. No model.

It is the floor under the Foundry Storyteller and passes the same Critic.
Every sentence is assembled from the records the beat points at: the player
names, the action and signal labels, the computed link (who ran past whom,
which zone), the context fact, the outcome's band and zone. The analyst register is exact and shows its
comparison, never a rounded fraction or a bare "most valuable": a fact's value
with its rank among the move's facts and its share of the chance ("VAEP
+0.077: the largest of the move's 5 facts, 70% of the 0.110 xG chance; next
+0.075"), the counterfactual's two values, the context's median. The fan
register says the same thing in words, without numbers or jargon.

Players are named in full at their first mention in the story, then by
surname when no other participant shares it. Present tense throughout.
"""

from __future__ import annotations

from replay_room.contracts.causal_account import CausalAccount, Contribution, Link
from replay_room.contracts.context import ContextFact, MatchContext
from replay_room.contracts.plan import Beat, FramingPlan
from replay_room.explain.schema import BeatText, StoryOutput
from replay_room.framing.facts import Facts

DANGEROUS_VALUE = 0.05  # a build-up action worth this much makes the attack "far more dangerous"
_SUFFIXES = ("_fail", "_missed", "_offside", "_owngoal", "_success")
_NOUNS = {
    "pass": "pass", "cross": "cross", "dribble": "run with the ball", "interception": "interception",
    "tackle": "tackle", "clearance": "clearance", "goalkick": "goal kick", "keeper_save": "save",
    "keeper_claim": "catch", "keeper_punch": "punch", "keeper_pick_up": "pick-up", "shot": "shot",
    "shot_freekick": "free kick", "shot_penalty": "penalty", "foul": "foul", "throw_in": "throw-in",
    "freekick_crossed": "free kick", "freekick_short": "free kick", "corner_crossed": "corner",
    "corner_short": "corner", "take_on": "take-on", "bad_touch": "touch",
}
_WON = ("interception", "tackle", "clearance")
_ORDINALS = ("", "", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth", "eleventh")


def base_action(label: str | None) -> str:
    label = label or ""
    for suffix in _SUFFIXES:
        if label.endswith(suffix):
            return label[: -len(suffix)]
    return label


def noun(label: str | None) -> str:
    base = base_action(label)
    return _NOUNS.get(base, base.replace("_", " "))


def chance_band(value: float) -> str:
    if value >= 0.3:
        return "a big chance"
    if value >= 0.12:
        return "a good chance"
    if value >= 0.05:
        return "a half-chance"
    return "a long shot"


def ranked_phrase(a: CausalAccount, c: Contribution, with_value: bool = True) -> str:
    """A fact's exact value, its rank by size among the facts that built the chance (the denial, which is -V by
    definition, is not one of them), its share of the chance, and the comparison that shows the rank:
    'VAEP +0.077: the largest of the 5 facts that built the chance, 70% of the 0.110 xG chance (next: +0.075).'"""
    facts = sorted((x for x in a.contributions if x.kind != "chance_denied"), key=lambda x: (-abs(x.effect), x.rank))
    n, v = len(facts), a.outcome.value
    k = next(i for i, x in enumerate(facts) if x.contribution_id == c.contribution_id) + 1
    place = "the largest" if k == 1 else f"the {_ORDINALS[k]} largest" if k < len(_ORDINALS) else f"number {k}"
    share = f", {round(100 * abs(c.effect) / v)}% of the {v:.3f} {'xG' if a.outcome.value_source == 'xg' else 'xT'} "             f"chance" if v > 0 else ""
    other = facts[1] if k == 1 and n > 1 else facts[0] if k > 1 else None
    versus = "" if other is None else f" ({'next' if k == 1 else 'largest'}: {other.effect:+.3f})"
    tail = f"{place} of the {n} facts that built the chance{share}{versus}."
    return f"{metric_name(c)} {c.effect:+.3f}: {tail}" if with_value else tail


def metric_name(c: Contribution) -> str:
    """The metric a fact's value is in, as the analyst register names it."""
    if c.kind == "chance_denied" or "outcome_value" in c.metrics:
        return "xG"
    if c.track == "off_ball":
        return "Pitch control"
    if "vaep" in c.metrics and c.metrics.get("value") == c.metrics["vaep"]:
        return "VAEP"
    return "ΔxT"


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def _poss(name: str) -> str:
    return f"{name}'" if name.endswith("s") else f"{name}'s"


class Teller:
    """Tells one plan. Tracks first mentions so names shorten as the story goes on."""

    def __init__(self, account: CausalAccount, plan: FramingPlan, context: MatchContext | None = None):
        self.a = account
        self.plan = plan
        self.facts = Facts(account, context)
        self.full = {p.player_id: p.name for p in account.participants}
        surnames = [p.name.split()[-1] for p in account.participants]
        self.short = {p.player_id: p.name.split()[-1] if surnames.count(p.name.split()[-1]) == 1 else p.name
                      for p in account.participants}
        firsts = [t.name.split()[0] for t in account.teams]
        self.team = {t.team_id: t.name.split()[0] if len(set(firsts)) == 2 else t.name for t in account.teams}
        self.T = self.team[account.outcome.beneficiary_team_id]
        self.Opp = self.team[account.outcome.conceding_team_id]
        self.seen: set[str] = set()
        self.said: list[str] = []  # signals and links already told, to vary repeated patterns
        self.goal = "goal" if account.outcome.scored else "chance"

    # ------------------------------------------------------------------ names

    def name(self, pid: str) -> str:
        if pid in self.seen:
            return self.short.get(pid, pid)
        self.seen.add(pid)
        return self.full.get(pid, pid)

    def peek(self, pid: str) -> str:
        """A name without counting it as a mention (for the headline)."""
        return self.short.get(pid, pid)

    def described(self, text: str) -> str:
        """A stored description with player ids replaced by names ("pass to EPA-11" -> "pass to Jordan Ferraro")."""
        for pid in sorted(self.full, key=len, reverse=True):
            if pid in text:
                text = text.replace(pid, self.name(pid))
        return text

    # ------------------------------------------------------------------ facts in words

    def ranked(self, c: Contribution) -> str:
        return " " + ranked_phrase(self.a, c)

    def attacking(self, c: Contribution, lead: bool) -> tuple[str, str]:
        A, T = self.name(c.player_id), self.T
        base, n = base_action(c.action), noun(c.action)
        comes = f", and that is where the {self.goal} comes from."
        if c.track == "off_ball":
            again = self.said.count(c.signal or "")
            self.said.append(c.signal or "")
            if lead:
                fan = f"{_poss(A)} run is where the {self.goal} comes from."
            elif again:
                fan = {"run_in_behind": f"{A} gets in behind as well.", "run_into_space": f"{A} also attacks the space.",
                       "found_space": f"{A} finds room too."}.get(c.signal or "", f"{A} finds space too.")
            else:
                fan = {"run_in_behind": f"{A} runs in behind the {self.Opp} defence.",
                       "run_into_space": f"{A} makes a run into open space.",
                       "found_space": f"{A} finds a pocket of space."}.get(c.signal or "", f"{A} finds space.")
            where = self.a.outcome.zone or "the spot the shot comes from"
            text = f"{fan[:-1]}, giving {T} more control of {where}." if not again or lead else fan
        elif c.effect < 0:
            fan = (f"{_poss(A)} {n} goes astray." if base in ("pass", "cross", "dribble")
                   else f"{_poss(A)} {n} costs {T} some of their threat.")
            text = fan + self.ranked(c)
        elif lead and base in _WON:
            fan = text = f"{A} wins the ball back for {T}{comes}"
        elif lead and base in ("pass", "cross") and c.role != "assist":
            fan = text = f"{A} plays the {n} the {self.goal} comes from."
        elif lead and base == "dribble":
            fan = text = f"{A} drives forward with the ball{comes}"
        elif base in _WON:
            fan = f"{A} wins the ball back for {T}."
            text = fan
        elif base == "keeper_save":
            fan = text = f"{A} gathers the ball, and {T} go from there."
        elif base in ("pass", "cross"):
            if c.role == "assist":
                fan = f"{A} plays the {n} that sets up the shot."
            elif c.effect >= DANGEROUS_VALUE:
                fan = f"{_poss(A)} {n} makes {T} far more dangerous."
            else:
                fan = f"{A} keeps the move going with a {n}."
            text = fan
        elif base == "dribble":
            fan = (f"{A} drives forward with the ball, and {T} grow more dangerous." if c.effect >= DANGEROUS_VALUE
                   else f"{A} carries the ball on.")
            text = fan
        elif base.startswith("shot"):
            fan = text = f"{A} gets the shot away."
        else:
            fan = text = f"{_poss(A)} {n} keeps {T} going."
        if lead and c.role == "assist":
            fan, text = fan[:-1] + comes, text[:-1] + comes
        text += self.ranked(c)
        return text, fan

    def denial(self, c: Contribution) -> tuple[str, str]:
        A, T = self.name(c.player_id), self.T
        base = base_action(c.action)
        if base == "keeper_save":
            fan = f"{A} makes the save, and {T} are denied."
        elif c.team_id == self.a.outcome.beneficiary_team_id:
            fan = f"{A} misses it, and {T} are left with nothing."
        elif base == "interception":
            fan = f"{A} cuts it out, and {T} are denied."
        elif base == "clearance":
            fan = f"{A} clears it, and {T} are denied."
        else:
            fan = f"{_poss(A)} {noun(c.action)} stops it, and {T} are denied."
        return fan, fan

    def lapse(self, c: Contribution) -> tuple[str, str]:
        """A conceding-side failure in plain words (no framing prefix)."""
        D = self.name(c.player_id)
        if c.track == "on_ball":
            base, n = base_action(c.action), noun(c.action)
            if base == "foul":
                what = "the penalty" if self.a.moment.type == "penalty" else "the free kick"
                fan = f"{D} gives away the foul, and {self.T} have {what}."
            elif (won := self.facts.regain_after(c)) is not None:
                W = self.name(won.player_id)
                how = {"interception": f"is cut out by {W}", "tackle": f"is won by {W}",
                       "clearance": f"is cleared to {W}"}.get(base_action(won.action), f"ends with {W}")
                fan = f"{_poss(D)} {n} {how}."
            elif base in _WON or base == "keeper_save":
                fan = f"{_poss(D)} {n} doesn't end the danger."
            else:
                fan = f"{_poss(D)} {n} goes astray."
            text = fan
        elif c.kind == "marking_break":
            others = [p for r in c.evidence if r.kind == "frame" for p in r.player_ids if p != c.player_id]
            M = self.name(others[0]) if others else None
            if M is None:
                fan = f"{D} loses the runner."
            elif c.signal == "stopped_tracking_runner":
                fan = f"{D} stops tracking {_poss(M)} run."
            else:
                fan = f"{D} loses {M}."
            text = fan
            if M is not None and "separation_end" in c.metrics:  # the separation, exactly
                text = (f"{fan[:-1]}: {self.peek(others[0])} ends up {c.metrics['separation_end']:.1f} m clear of "
                        f"{self.peek(c.player_id)}.")
        else:
            where = self.a.outcome.zone
            fan = (f"{D} gives up the space in {where}, where the shot comes from." if where
                   else f"{D} gives up the space the shot comes from.")
            text = fan
        text += self.ranked(c)
        return text, fan

    def link(self, link: Link) -> tuple[str, str]:
        D = self.name(link.defender_id)
        R = self.name(link.runner_id) if link.runner_id else None
        M = self.name(link.marked_player_id) if link.marked_player_id else None
        z = link.zone
        again = f"{link.kind}:{z}" in self.said
        self.said.append(f"{link.kind}:{z}")
        if link.kind == "run_past" and again:
            core = f"{R} does the same to {D}, who has also stepped away from {z}"
        elif link.kind == "run_past":
            core = f"{R} runs straight past {D}, who has stepped away from {z}"
        elif link.kind == "dragged_out":
            core = f"{_poss(R)} run drags {D} out of {z}"
        elif link.kind == "decoy_run":
            core = f"{_poss(R)} run takes {D} away from {M}"
        else:
            core = f"{D} loses {M}, who moves towards {z}"
        used = self.facts.enabled_by(link)
        if used is not None and used.track == "on_ball" and not again:
            E, base = self.name(used.player_id), base_action(used.action)
            if base in ("pass", "cross"):
                core += f", and {_poss(E)} {noun(used.action)} goes straight into that space"
            elif base == "dribble":
                core += f", and {E} carries the ball into that space"
            elif base.startswith("shot"):
                core += ", and that is where the shot comes from"
        fan = core + "."
        text = fan
        if "spot_distance_end" in link.metrics:
            text += (f" {self.peek(link.defender_id)} ends up {link.metrics['spot_distance_end']:.1f} m from where "
                     f"the shot is taken, having started {link.metrics['spot_distance_start']:.1f} m from it.")
        return text, fan

    def context(self, f: ContextFact) -> tuple[str, str]:
        Opp, T = self.Opp, self.T
        small = " (a small sample)" if f.confidence == "low" else ""
        if f.kind == "line_height":
            way = "higher" if f.direction == "higher" else "deeper"
            fan = f"{_poss(Opp)} back line is standing much {way} than usual."
            text = (f"With the ball in their third, {_poss(Opp)} back line is {f.here:.1f} m from their own goal line "
                    f"here, against a match median of {f.baseline:.1f} m over {f.sample_size} defending spells{small}.")
        elif f.kind == "marking_distance":
            fan = (f"{_poss(T)} attackers have far more room than usual." if f.direction == "higher"
                   else f"{Opp} are marking much tighter than usual.")
            text = (f"Attackers in {_poss(Opp)} third have {f.here:.1f} m to the nearest defender here, against a "
                    f"match median of {f.baseline:.1f} m over {f.sample_size} defending spells{small}.")
        else:
            fan = f"{Opp} usually win the ball straight back, but not this time."
            text = (f"{Opp} won the ball back within {f.metrics['window_s']:.0f} seconds after "
                    f"{f.metrics['won_back']:.0f} of their {f.metrics['losses']:.0f} other losses in this match; "
                    f"this time they don't{small}.")
        return text, fan

    def noun_phrase(self, cid: str | None, own: str | None = None) -> str | None:
        """'Larsen's pass', 'the space Novak gave up': who made the chance, for the outcome and headline.
        ``own``: a player already named in the sentence ("the interception", not "Brandt's interception")."""
        if cid is None or cid not in self.facts.contributions:
            return None
        c = self.facts.contributions[cid]
        P = self.peek(c.player_id)
        if c.player_id == own and c.team_id == self.a.outcome.beneficiary_team_id:
            return f"the {'run' if c.track == 'off_ball' else noun(c.action)}"
        if c.team_id == self.a.outcome.conceding_team_id:
            if c.kind == "space_conceded":
                return f"the space {P} gave up"
            if c.kind == "marking_break":
                return f"{_poss(P)} lapse"
            return f"{_poss(P)} {noun(c.action)}" if base_action(c.action) == "foul" else f"{_poss(P)} mistake"
        if c.track == "off_ball":
            return f"{_poss(P)} run"
        return f"{_poss(P)} {noun(c.action)}"

    def outcome(self) -> tuple[str, str]:
        o = self.a.outcome
        S = self.name(self.facts.scorer_id)
        band = chance_band(o.value)
        zone = f" from {o.zone}" if o.zone else ""
        lead = self.plan.lead_contribution_id if self.a.headline.kind != "chance_denied" else None
        shooter = self.facts.scorer_id
        why = [p for p in (self.noun_phrase(lead, shooter), self.noun_phrase(self.plan.flaw_contribution_id, shooter))
               if p]
        came = f", and it came from {' and '.join(why)}" if why else ""
        rated = f", rated {round(100 * o.value)}% before the shot ({'xG' if o.value_source == 'xg' else 'xT'} " \
                f"{o.value:.3f})"
        if o.scored:
            fan = f"Goal! {S} scores{zone}: {band}{came}."
            text = f"Goal: {S} scores{zone}: {band}{rated}{came}."
        elif o.realized:
            fan = f"{_poss(S)} shot{zone} doesn't go in: {band}{came}."
            text = f"{_poss(S)} shot{zone} doesn't go in: {band}{rated}{came}."
        else:
            fan = f"A goal that didn't happen: {S} had {band}{zone}{came}."
            text = f"A goal that didn't happen: {S} had {band}{zone}{rated}{came}."
        return text, fan

    def counterfactual(self, cid: str) -> tuple[str, str]:
        cf = self.facts.counterfactual(cid)
        C = self.name(self.facts.contribution(cid).player_id)
        chosen = self.described(cf.chosen)
        best = cf.best
        option = self.described(best.description)
        fan = f"Instead of the {chosen}, {C} had a better option: a {option}."
        if best.completion_prob is not None and best.completion_prob >= 0.85:
            fan = fan[:-1] + ", and it was very likely to arrive."
        text = f"Instead of the {chosen}, {C} had a better option: a {option}."
        text += f" By the pass model it was worth {best.value:.3f} against {cf.chosen_value:.3f} for the {chosen}"
        if best.completion_prob is not None:
            text += f", with a {round(100 * best.completion_prob)}% chance of arriving"
        text += "."
        return text, fan

    def headline(self) -> tuple[str, str]:
        a, o = self.a, self.a.outcome
        head = a.headline
        flaw = self.noun_phrase(self.plan.flaw_contribution_id) if self.plan.flaw_contribution_id != head.contribution_id \
            else None
        if head.kind == "chance_denied":
            K = self.peek(head.player_id)
            fc = self.facts.contributions.get(self.plan.flaw_contribution_id or "")
            after = f", after {flaw}" if flaw and fc is not None and fc.track == "on_ball" else ""
            if head.team_id == o.beneficiary_team_id:
                line = f"A goal that didn't happen: {K} misses {chance_band(o.value)} for {self.T}."
            elif fc is not None and fc.player_id == head.player_id:
                line = f"A goal that didn't happen: {K} makes up for an earlier mistake and denies {self.T}."
            else:
                line = f"A goal that didn't happen: {K} denies {self.T}{after}."
        elif head.role == "primary_cause":
            D = self.peek(head.player_id)
            if base_action(head.action) == "foul":
                line = f"{self.T} punish {_poss(D)} foul."
            elif head.track == "on_ball":
                line = f"{self.T} punish a {self.Opp} mistake: {_poss(D)} {noun(head.action)}."
            else:
                line = f"{self.T} punish {self.noun_phrase(head.contribution_id)}."
        else:
            lead = self.noun_phrase(head.contribution_id) or self.peek(head.player_id)
            fc = self.facts.contributions.get(self.plan.flaw_contribution_id or "")
            tail = ""
            if flaw and fc is not None:
                tail = f", through {flaw}" if fc.kind == "space_conceded" else f", after {flaw}"
            line = f"{_cap(lead)} makes the {self.goal} for {self.T}{tail}."
        return line, line

    # ------------------------------------------------------------------ beats

    def beat(self, b: Beat) -> tuple[str, str]:
        if b.kind == "outcome":
            return self.outcome()
        if b.kind == "counterfactual":
            return self.counterfactual(b.contribution_id)
        if b.kind == "context":
            return self.context(self.facts.context_fact(b.context_fact_id))
        if b.kind == "link":
            return self.link(self.facts.link(b.link_id))
        c = self.facts.contribution(b.contribution_id)
        if c.kind == "chance_denied":
            return self.denial(c)
        if c.team_id == self.a.outcome.conceding_team_id and c.effect > 0:
            if b.link_id is not None:
                text, fan = self.link(self.facts.link(b.link_id))
            else:
                text, fan = self.lapse(c)
            if b.kind == "flaw":
                if b.emphasis == "lead":
                    prefix = f"It starts with a {self.Opp} mistake: "
                elif self.a.outcome.realized:
                    prefix = f"Where {self.Opp} go wrong: "
                else:
                    prefix = f"How {self.T} got the chance: "
                text, fan = prefix + text[0].lower() + text[1:] if not text[0].isupper() or text.split()[0] in ("It",) \
                    else prefix + text, prefix + fan
            return text, fan
        if c.team_id == self.a.outcome.conceding_team_id:  # a defending action that hurt the attack
            D = self.name(c.player_id)
            fan = f"{_poss(D)} {noun(c.action)} slows {self.T} down."
            return fan, fan
        text, fan = self.attacking(c, lead=b.emphasis == "lead")
        if b.kind == "punish":
            text, fan = f"{self.T} make them pay: {text}", f"{self.T} make them pay: {fan}"
        return text, fan


def compose(account: CausalAccount, plan: FramingPlan, context: MatchContext | None = None) -> StoryOutput:
    teller = Teller(account, plan, context)
    headline, headline_fan = teller.headline()
    beats = []
    for b in plan.beats:
        text, fan = teller.beat(b)
        deep, deep_fan = Deep(teller).beat(b)
        beats.append(BeatText(beat_id=b.beat_id, text=text, fan=fan, deep=deep, deep_fan=deep_fan))
    return StoryOutput(headline=headline, headline_fan=headline_fan, beats=tuple(beats))


def beat_positions(facts: Facts, context: MatchContext | None, b: Beat, players: set[str]):
    """The positional facts of a beat: each of its players at the frame nearest the beat's first record, the
    control swing over its span (the link's, else the fact's), and the marking it involves."""
    if context is None:
        return [], None, None
    refs = facts.refs(b)
    t = refs[0].time_seconds if refs[0].kind == "event" else refs[0].timestamp
    if b.link_id is not None:
        t = facts.link(b.link_id).evidence[-1].timestamp
    best: dict[str, object] = {}
    for p in context.positions:
        if p.player_id in players and (p.player_id not in best or abs(p.timestamp - t) < abs(best[p.player_id].timestamp - t)):
            best[p.player_id] = p
    label = b.link_id or b.contribution_id
    swing = next((s for s in context.swings if s.label == label), None)
    marking = next((m for m in context.markings if m.defender_id in players), None)
    return list(best.values()), swing, marking


class Deep:
    """The deep passage of a beat (evidence treatise L3): where the players were against their averages, how close
    the nearest opponent was, how the attacking team's control of the shooting spot moved over the beat's span,
    whether a marking held, and how it fits the move. Every figure is a computed one; a low-confidence average is
    said to be one, a missing one is not mentioned."""

    def __init__(self, teller: Teller):
        self.t = teller
        self.a = teller.a
        self.ctx = teller.facts.context

    def who(self, pid: str) -> str:
        return self.t.peek(pid) if pid in self.t.full else ""

    def position(self, p, fan: bool) -> str:
        P = self.who(p.player_id)
        if p.average is not None and p.forward_m is not None and abs(p.forward_m) >= 2:
            way = "higher up the pitch" if p.forward_m > 0 else "deeper"
            if fan:
                if p.confidence == "low":
                    return ""
                size = "much " if abs(p.forward_m) >= 8 else ""
                where = f"{P} is {size}{way} than usual in this phase of play"
            else:
                where = (f"{P} is {abs(p.forward_m):.1f} m {way} than their average in this phase of play "
                         f"({p.confidence} confidence, {p.sample_spells} possessions)")
        else:
            where = "" if fan else f"{P} is {p.to_goal_m:.1f} m from goal"
        opp = self.who(p.nearest_opponent_id)
        if fan:
            near = ("an opponent tight to them" if p.to_opponent_m < 3 else
                    "room around them" if p.to_opponent_m > 8 else "")
            if not near:
                return f"{where}." if where else ""
            return f"{where}, with {near}." if where else f"{P} has {near}."
        else:
            near = f"{p.to_opponent_m:.1f} m from the nearest opponent" + (f", {opp}" if opp else "")
        parts = [x for x in (where, near) if x]
        if not parts:
            return ""
        if not where:
            return f"{P} is {near}."
        return f"{where}, {near}." if near else f"{where}."

    def swing(self, s, fan: bool) -> str:
        T = self.t.T
        zone = s.zone or "the shooting spot"
        if fan:
            if abs(s.control_to - s.control_from) < 0.03:
                return f"{_poss(T)} hold on {zone} barely changes."
            return f"{_poss(T)} hold on {zone} {'grows' if s.control_to > s.control_from else 'slips'}."
        span = f"{s.seconds:.1f}" if s.seconds >= 1 else f"{s.seconds:.2f}"  # a value under 1 is written exactly
        return (f"{_poss(T)} pitch control of {zone} goes from {s.control_from:.2f} to {s.control_to:.2f} "
                f"over {span} s.")

    def marking(self, m, fan: bool) -> str:
        D, M = self.who(m.defender_id), self.who(m.man_id)
        if not D or not M:
            return ""
        if fan:
            return f"{D} {'stays with' if m.held else 'loses'} {M}."
        return (f"{D} is {m.separation_from:.1f} m from {M} at the start and {m.separation_to:.1f} m at the end: "
                f"the marking {'holds' if m.held else 'breaks'}.")

    def fit(self, fan: bool) -> str:
        o = self.a.outcome
        v = f"{o.value:.3f} {'xG' if o.value_source == 'xg' else 'xT'}"
        if o.scored:
            return "It all ends in the goal." if fan else f"It all leads to the goal, from a {v} chance."
        if o.realized:
            return "The shot that follows does not go in." if fan else f"The shot that follows, worth {v}, does not go in."
        return "The chance it all builds is denied." if fan else f"The chance it all builds, worth {v}, is denied."

    def beat(self, b: Beat) -> tuple[str, str]:
        if b.kind in ("outcome", "counterfactual"):
            return "", ""
        players = self.t.facts.players(b, self.t.plan.lead_contribution_id, self.t.plan.flaw_contribution_id)
        if b.kind == "context":
            f = self.t.facts.context_fact(b.context_fact_id)
            text, fan = self.t.context(f)
            spread = f" The middle half of the match lies between {f.spread[0]:.1f} m and {f.spread[1]:.1f} m." \
                if f.spread else ""
            return (f"{text}{spread} {self.fit(False)}", f"{fan} {self.fit(True)}")
        positions, swing, marking = beat_positions(self.t.facts, self.ctx, b, players)
        order = {pid: i for i, pid in enumerate(sorted(players, key=lambda p: p not in self.t.full))}
        positions.sort(key=lambda p: order.get(p.player_id, 99))
        out = {False: [], True: []}
        for fan in (False, True):
            for p in positions[:3]:
                if (s := self.position(p, fan)):
                    out[fan].append(s)
            if marking is not None and (s := self.marking(marking, fan)):
                out[fan].append(s)
            if swing is not None:
                out[fan].append(self.swing(swing, fan))
            if out[fan]:
                out[fan].append(self.fit(fan))
        return " ".join(out[False]), " ".join(out[True])


def perspective_headline(account: CausalAccount, plan: FramingPlan, context: MatchContext | None,
                         team_id: str) -> str:
    """The headline seen from one club (club focus). The same facts; only whose side the line stands on."""
    teller = Teller(account, plan, context)
    line, _ = teller.headline()
    o, head = account.outcome, account.headline
    if team_id != o.conceding_team_id:
        return line
    Opp = teller.Opp
    if head.kind == "chance_denied":
        if head.team_id == o.conceding_team_id:
            return f"How {Opp} survived: {_poss(teller.peek(head.player_id))} {noun(head.action)}."
        return f"How {Opp} survived: {teller.peek(head.player_id)} missed {chance_band(o.value)}."
    flaw = teller.noun_phrase(plan.flaw_contribution_id)
    if flaw is None:
        return f"What went wrong for {Opp}: they could not stop {teller.noun_phrase(head.contribution_id)}."
    return f"What went wrong for {Opp}: {flaw}."
