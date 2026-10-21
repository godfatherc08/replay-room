"""The grounding gate: a narration passes only if everything it says is in the account.

``validate(narration, account)`` returns the list of violations (empty = pass).
It checks, for the headline line and every sentence:

* **shape**: one sentence per contribution, in ``brief.narration_order`` (headline
  first, then rank order), each with that contribution's role;
* **refs**: every sentence's ``ref`` is one of *its own contribution's*
  evidence refs (so it exists in the account and points at the right fact);
* **numbers**: every number in the text equals a number in the account at the
  precision written (``0.15`` matches 0.152; ``15%`` matches 0.152; ``0`` does
  not match 0.152; a probability-sized value needs two decimals, since ``0.2``
  would match almost anything): effects, metrics, V, counterfactual values and completion
  probabilities, plus shirt numbers; the structured ``metric`` must name one of
  the contribution's own numbers (``effect`` or a metric key, or the moment's
  ``outcome_value``) and match it to ``METRIC_TOLERANCE``;
* **entities**: every player id named is a participant; every capitalised word
  is part of a participant's name, a team's name or id, or ``ALLOWED_TERMS``,
  except a word starting a sentence, which may also be a common English word
  (``STARTERS``): an unknown name (a player, team or place the account does
  not mention) is a violation wherever it stands;
* **outcome**: if the terminal action did not score, no sentence may say that it
  did (``SCORING_WORDS``).
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import ValidationError

from replay_room.contracts.causal_account import CausalAccount
from replay_room.explain.brief import narration_order, ref_key
from replay_room.explain.schema import ModelNarration

METRIC_TOLERANCE = 6e-4
ALLOWED_TERMS = frozenset({"xG", "xT", "VAEP", "I"})
# Ordinary words a sentence may start with. Anything else capitalised must be a name from the account.
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
attacking defence defense keeper goalkeeper save block miss header move build build-up turnover
headline overall ultimately crucially decisively key credit blame value threat effect
was were is are be been being had has have did do does could would should might may must can
denied prevented realized realised scored missed lost won gave got made kept left let set put
""".split())
SCORING_WORDS = re.compile(
    r"\b(scored|scores|scoring|netted|nets|converted|converts|finish(?:ed|es)? (?:it )?off|"
    r"(?:found|finds) the (?:net|back of the net)|into the net)\b", re.IGNORECASE)
PLAYER_ID = re.compile(r"\b[A-Z]{2,4}-\d{1,3}\b")
NUMBER = re.compile(r"(?<![\w.])\d+(?:\.\d+)?%?")
CAPITALISED = re.compile(r"(?<![A-Za-z\d])[A-Z][A-Za-zÀ-ſ'’-]*")
SENTENCE_START = re.compile(r"(^|[.!?:;—–]\s+|\(\s*|\"\s*)$")


def _floats(account: CausalAccount) -> list[float]:
    vals = [account.outcome.value]
    for c in account.contributions:
        vals.append(c.effect)
        vals.extend(c.metrics.values())
    for cf in account.counterfactuals:
        vals.append(cf.chosen_value)
        for a in cf.alternatives:
            vals.append(a.value)
            if a.completion_prob is not None:
                vals.append(a.completion_prob)
    return [abs(v) for v in vals]


def _vocabulary(account: CausalAccount) -> set[str]:
    words = set(ALLOWED_TERMS)
    for p in account.participants:
        words.update(re.split(r"[\s-]+", p.name))
    for t in account.teams:
        words.update(t.name.split())
        words.add(t.team_id)
    return {w.strip("'’") for w in words if w}


def number_ok(token: str, floats: list[float], integers: set[int]) -> bool:
    percent = token.endswith("%")
    digits = token.rstrip("%")
    value = float(digits)
    decimals = len(digits.split(".")[1]) if "." in digits else 0
    half = 0.5 * 10 ** -decimals + 1e-9
    if percent:
        return any(abs(value - 100 * v) <= half for v in floats)
    if decimals == 0 and int(value) in integers:
        return True
    if decimals == 0 or (value < 1 and decimals < 2):
        return False
    return any(abs(value - v) <= half for v in floats)


def check_text(text: str, account: CausalAccount, where: str) -> list[str]:
    errors = []
    participants = {p.player_id for p in account.participants}
    for pid in PLAYER_ID.findall(text):
        if pid not in participants:
            errors.append(f"{where}: names player {pid}, who is not in the account")
    scrubbed = PLAYER_ID.sub(" ", text)
    floats = _floats(account)
    integers = {p.shirt_number for p in account.participants if p.shirt_number is not None}
    for token in NUMBER.findall(scrubbed):
        if not number_ok(token, floats, integers):
            errors.append(f"{where}: states {token}, which is not a number in the account")
    vocab = _vocabulary(account)
    for m in CAPITALISED.finditer(scrubbed):
        word = m.group(0).rstrip("'’").removesuffix("'s").removesuffix("’s")
        if word in vocab or (SENTENCE_START.search(scrubbed[: m.start()]) and word.lower() in STARTERS):
            continue
        errors.append(f"{where}: names {word!r}, which is not in the account")
    if not account.outcome.scored and SCORING_WORDS.search(text):
        errors.append(f"{where}: says the chance was scored, but the outcome is no goal")
    return errors


def validate(narration: ModelNarration | dict[str, Any], account: CausalAccount) -> list[str]:
    if not isinstance(narration, ModelNarration):
        try:
            narration = ModelNarration.model_validate(narration)
        except ValidationError as e:
            return [f"does not match the narration schema: {e.errors()[0]['msg']} at {e.errors()[0]['loc']}"]
    errors = check_text(narration.headline_text, account, "headline")
    order = narration_order(account)
    got = [s.contribution_id for s in narration.sentences]
    if got != order:
        errors.append(f"sentences must narrate {order} in that order, got {got}")
    by_id = {c.contribution_id: c for c in account.contributions}
    for i, s in enumerate(narration.sentences):
        where = f"sentence {i} ({s.contribution_id})"
        c = by_id.get(s.contribution_id)
        if c is None:
            errors.append(f"{where}: no such contribution in the account")
            continue
        refs = {ref_key(r) for r in c.evidence}
        if s.ref not in refs:
            errors.append(f"{where}: cites {s.ref!r}; its evidence is {sorted(refs)}")
        if s.role != c.role:
            errors.append(f"{where}: role {s.role!r}, the account says {c.role!r}")
        if s.metric is not None:
            known = {"effect": c.effect, "outcome_value": account.outcome.value, **c.metrics}
            if s.metric.name not in known:
                errors.append(f"{where}: metric {s.metric.name!r} is not one of {sorted(known)}")
            elif abs(abs(s.metric.value) - abs(known[s.metric.name])) > METRIC_TOLERANCE:
                errors.append(f"{where}: {s.metric.name}={s.metric.value}, the account says {known[s.metric.name]:.4f}")
        errors += check_text(s.text, account, where)
    return errors
