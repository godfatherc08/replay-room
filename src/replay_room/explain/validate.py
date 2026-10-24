"""The grounding gate for told stories: a story passes only if everything it says is in the tool outputs.

``validate(story, account, plan, context)`` returns the violations (empty =
pass). It is the text half of the Critic (``framing.check_plan`` is the plan
half). For the headlines and every beat, in both registers:

* **shape**: one passage per plan beat, in the plan's order;
* **players**: a passage may name only the players of *its own* beat's records
  (``framing.Facts.players``): a beat about Brandt's pass cannot pull in Novak.
  Player ids follow the same rule;
* **numbers**: every number equals a number the tools computed, at the
  precision written: account values (effects, metrics, V, counterfactual values
  and completion probabilities; ``15%`` matches 0.152, ``0.15`` matches 0.152,
  a bare ``0`` or ``0.2`` matches nothing), shirt numbers, and the metres,
  seconds and counts of links, metrics and match context, to the nearest whole
  number (``24 m`` matches a 24.3 m line);
* **entities**: every capitalised word is part of an allowed player's name, a
  team's name or id, or ``ALLOWED_TERMS``; a sentence may also start with a
  common English word (``STARTERS``). An unknown name is a violation;
* **links**: causal-link language (``LINK_WORDS``: "drags", "runs past",
  "stepped away", "opened", "because", ...) only in a beat that carries a
  computed link. Elsewhere the facts stand side by side, unconnected;
* **outcome**: if the terminal action did not score, nothing says it did
  (``SCORING_WORDS``, unless negated within a few words);
* **fan register**: no digits and no metric jargon (``JARGON``);
* **exactness** (analyst register): no vague magnitude (``VAGUE``: "about",
  "roughly", "nearly", "a big chunk"): the number and its comparison instead.
  A share of the chance ("70% of the 0.110 xG chance") must equal a
  contribution's |effect| over V; a count ("the move's 5 facts") the account's;
* **framing**: a moment that did not score is never called "the goal" (only "a
  goal that didn't happen", a goal kick, or a distance from goal);
* **teams**: a player is never put on the other team ("Northbridge's Alex
  Larsen" when the account has Alex Larsen at Eastport).
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import ValidationError

from replay_room.contracts.causal_account import CausalAccount
from replay_room.contracts.context import MatchContext
from replay_room.contracts.plan import FramingPlan
from replay_room.explain.schema import StoryOutput
from replay_room.framing.facts import Facts, UnresolvedBeat

ALLOWED_TERMS = frozenset({"xG", "xT", "VAEP", "I"})
# Ordinary words a sentence may start with. Anything else capitalised must be a name from the tool outputs.
STARTERS = frozenset("""
a an the this that these those it its his her their our your my one two three no not none
he she they we you there here what which who whom whose where when while why how
and but or so yet nor for as if then than though although because since until unless once
after before during despite through throughout with without within under over above below behind
beyond between among against across along around into onto from to of off on at by in out up down
again also even only just still already almost both each every either neither all any some many
most much more less few several such same other another own instead meanwhile however moreover
first second third next last later earlier finally eventually soon now meanwhile together
ball chance shot pass passes cross run runs space pressure movement defending defender attack
attacking attackers defence defense keeper goalkeeper save block miss header move build build-up turnover
headline overall ultimately crucially decisively key credit blame value threat effect goal
was were is are be been being had has have did do does could would should might may must can
denied prevented realized realised scored missed lost won gave got made kept left let set put rated pitch
""".split())
SCORING_WORDS = re.compile(
    r"\b(scored|scores|netted|nets|converted|converts|finish(?:ed|es)? (?:it )?off|"
    r"(?:found|finds) the (?:net|back of the net)|into the net)\b", re.IGNORECASE)
# A scoring word preceded by one of these (within a few words) is a denial, not a claim: "didn't go into the net".
NEGATION = re.compile(r"\b(not|never|no|without|failed|fails|unable)\b|n't\b", re.IGNORECASE)
LINK_WORDS = re.compile(
    r"\b(drag(?:s|ged|ging)?|pull(?:s|ed|ing)? \w+ (?:out|away|across)|dr[ae]w(?:s)? \w+ (?:out|away|across)|"
    r"takes? \w+ away|took \w+ away|(?:runs?|ran) (?:straight |right )?past|step(?:s|ped)? away|vacat\w+|"
    r"open(?:s|ed|ing)(?: up)?|left the space|because|caused?|so that|leaving)\b", re.IGNORECASE)
VAGUE = re.compile(r"\b(about|roughly|around|nearly|almost|approximately|a big chunk|a fair bit|a good deal|"
                   r"most valuable|biggest|smallest)\b", re.IGNORECASE)
# realized-goal wording; allowed in a moment that did not score only as "a goal that didn't happen", "goal kick",
# "goal line", or a distance ("from their goal")
GOAL_WORD = re.compile(r"(?<!from )(?<!from their )(?<!from the )(?<!own )\b(the|a|their|his|her|its) goal\b"
                       r"(?! that didn't happen| kick| line)|\bmakes? the goal\b|^Goal\b", re.IGNORECASE)
JARGON = re.compile(r"\b(xG|xT|VAEP|pitch control|expected threat|expected goals|probability|effect|metric)\b",
                    re.IGNORECASE)
PLAYER_ID = re.compile(r"\b[A-Z]{2,4}-\d{1,3}\b")
NUMBER = re.compile(r"(?<![\w.])\d+(?:\.\d+)?%?")
CAPITALISED = re.compile(r"(?<![A-Za-z\d])[A-Z][A-Za-zÀ-ſ'’-]*")
SENTENCE_START = re.compile(r"(^|[.!?:;—–]\s+|\(\s*|\"\s*)$")


class Grounds:
    """What a passage may draw on: the numbers and names of one moment's tool outputs."""

    def __init__(self, account: CausalAccount, context: MatchContext | None = None):
        self.account = account
        self.facts = Facts(account, context)
        a = account
        probs = [a.outcome.value]
        for c in a.contributions:
            probs.append(c.effect)
            probs.extend(c.metrics.values())
        for cf in a.counterfactuals:
            probs.append(cf.chosen_value)
            for alt in cf.alternatives:
                probs.append(alt.value)
                if alt.completion_prob is not None:
                    probs.append(alt.completion_prob)
        measured = [v for c in a.contributions for v in c.metrics.values()]
        measured += [v for link in a.links for v in link.metrics.values()]
        for f in (context.facts if context else ()):
            measured += [f.here, f.baseline, *(f.spread or ()), *f.metrics.values()]
            probs.append(f.baseline)
        self.floats = [abs(v) for v in probs + measured]
        self.integers = {p.shirt_number for p in a.participants if p.shirt_number is not None}
        self.integers |= {round(abs(v)) for v in measured if abs(v) >= 1}
        self.integers |= {len(a.contributions), sum(c.kind != "chance_denied" for c in a.contributions)}
        self.integers |= {f.sample_size for f in (context.facts if context else ())}
        # shares of the chance a text may state as a percent: |effect| / V, for every fact
        self.shares = [abs(c.effect) / a.outcome.value for c in a.contributions] if a.outcome.value > 0 else []
        self.team_words = {w for t in a.teams for w in t.name.split()} | {t.team_id for t in a.teams}
        self.names = {p.player_id: p.name for p in a.participants}
        self.team_of = {p.player_id: p.team_id for p in a.participants}
        self.team_names = {t.team_id: t.name for t in a.teams}


def number_ok(token: str, floats: list[float], integers: set[int], shares: list[float] = ()) -> bool:
    percent = token.endswith("%")
    digits = token.rstrip("%")
    value = float(digits)
    decimals = len(digits.split(".")[1]) if "." in digits else 0
    half = 0.5 * 10 ** -decimals + 1e-9
    if percent:
        return any(abs(value - 100 * v) <= half for v in [*(v for v in floats if v <= 1), *shares])
    if decimals == 0 and int(value) in integers:
        return True
    if decimals == 0 or (value < 1 and decimals < 2):
        return False
    return any(abs(value - v) <= half for v in floats)


def check_text(text: str, grounds: Grounds, where: str, players: set[str], *, fan: bool = False,
               link: bool = False) -> list[str]:
    errors = []
    for pid in PLAYER_ID.findall(text):
        if pid not in players:
            errors.append(f"{where}: names player {pid}, who is not in this beat's facts")
    scrubbed = PLAYER_ID.sub(" ", text)
    for token in NUMBER.findall(scrubbed):
        if not number_ok(token, grounds.floats, grounds.integers, grounds.shares):
            errors.append(f"{where}: states {token}, which is not a number the tools computed")
    allowed = {w.strip("'’") for pid in players for w in re.split(r"[\s-]+", grounds.names.get(pid, ""))}
    allowed |= grounds.team_words | ALLOWED_TERMS
    others = {w.strip("'’") for pid, n in grounds.names.items() if pid not in players for w in re.split(r"[\s-]+", n)}
    for m in CAPITALISED.finditer(scrubbed):
        word = m.group(0).rstrip("'’").removesuffix("'s").removesuffix("’s").rstrip("'’")
        if word in allowed or (SENTENCE_START.search(scrubbed[: m.start()]) and word.lower() in STARTERS):
            continue
        if word in others:
            errors.append(f"{where}: names {word!r}, who is not in this beat's facts")
        else:
            errors.append(f"{where}: names {word!r}, which is not in the tool outputs")
    if not grounds.account.outcome.scored:
        for m in SCORING_WORDS.finditer(text):
            before = " ".join(text[: m.start()].split()[-4:])
            if not NEGATION.search(before):
                errors.append(f"{where}: says the chance was scored, but the outcome is no goal")
                break
    if not grounds.account.outcome.scored and (m := GOAL_WORD.search(text)):
        errors.append(f"{where}: {m.group(0)!r} frames it as a goal, but the outcome is no goal")
    if not fan and (m := VAGUE.search(text)):
        errors.append(f"{where}: {m.group(0)!r} is vague or asserted: state the number and its comparison")
    for pid, name in grounds.names.items():
        for tid, team in grounds.team_names.items():
            if tid == grounds.team_of.get(pid):
                continue
            for t in {team, team.split()[0]}:
                if re.search(rf"\b{re.escape(t)}'s {re.escape(name)}\b|\b{re.escape(name)} \({re.escape(team)}\)", text):
                    errors.append(f"{where}: puts {name} on {team}; the account has them at "
                                  f"{grounds.team_names[grounds.team_of[pid]]}")
    if not link and (m := LINK_WORDS.search(text)):
        errors.append(f"{where}: {m.group(0)!r} asserts a causal link, but this beat carries no computed link")
    if fan:
        if re.search(r"\d", text):
            errors.append(f"{where}: the fan register states a number")
        if m := JARGON.search(text):
            errors.append(f"{where}: the fan register uses the jargon {m.group(0)!r}")
    return errors


def validate(story: StoryOutput | dict[str, Any], account: CausalAccount, plan: FramingPlan,
             context: MatchContext | None = None) -> list[str]:
    if not isinstance(story, StoryOutput):
        try:
            story = StoryOutput.model_validate(story)
        except ValidationError as e:
            return [f"does not match the story schema: {e.errors()[0]['msg']} at {e.errors()[0]['loc']}"]
    grounds = Grounds(account, context)
    facts = grounds.facts
    want = [b.beat_id for b in plan.beats]
    got = [b.beat_id for b in story.beats]
    if got != want:
        return [f"beats must tell {want} in that order, got {got}"]
    lead, flaw = plan.lead_contribution_id, plan.flaw_contribution_id
    errors: list[str] = []
    headline_players: set[str] = set()
    for b in plan.beats:
        if b.kind in ("lead", "flaw", "punish", "outcome") or b.emphasis == "lead":
            try:
                headline_players |= facts.players(b, lead, flaw)
            except UnresolvedBeat as e:
                return [f"plan: {e}"]
    errors += check_text(story.headline, grounds, "headline", headline_players)
    errors += check_text(story.headline_fan, grounds, "fan headline", headline_players, fan=True)
    for b, told in zip(plan.beats, story.beats):
        try:
            players = facts.players(b, lead, flaw)
        except UnresolvedBeat as e:
            errors.append(f"beat {b.beat_id}: {e}")
            continue
        link = b.link_id is not None
        errors += check_text(told.text, grounds, f"beat {b.beat_id} ({b.kind})", players, link=link)
        errors += check_text(told.fan, grounds, f"beat {b.beat_id} ({b.kind}, fan)", players, fan=True, link=link)
    return errors
