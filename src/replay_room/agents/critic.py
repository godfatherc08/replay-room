"""Critic: the anti-hallucination guarantee. Nothing reaches the screen without passing it.

* ``review_plan``: every beat of the Analyst's plan resolves to a fact a tool
  returned, and the plan keeps the framing rules (``framing.check_plan``);
* ``review_story``: every passage names only its beat's players, states only
  computed numbers, asserts links only where the engine computed one, and the
  fan register is number- and jargon-free (``explain.validate``);
* ``review_edition``: an edited (personalized, possibly translated) telling
  still carries exactly the numbers and names of the telling it came from;
* ``screen``: Azure AI Content Safety over the final text, when configured.

Deterministic, no model: the Critic is code, so it cannot be talked round.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from replay_room.agents.azure import AzureUnavailable, ContentSafety
from replay_room.contracts.causal_account import CausalAccount
from replay_room.contracts.context import MatchContext
from replay_room.contracts.plan import FramingPlan
from replay_room.explain.schema import StoryOutput
from replay_room.explain.validate import validate
from replay_room.framing import check_plan

_NUMBER = re.compile(r"\d+(?:[.,]\d+)?%?")


@dataclass
class Critic:
    safety: ContentSafety = field(default_factory=ContentSafety)

    def review_plan(self, plan: FramingPlan, account: CausalAccount, context: MatchContext | None) -> list[str]:
        return check_plan(plan, account, context)

    def review_story(self, story: StoryOutput | dict, account: CausalAccount, plan: FramingPlan,
                     context: MatchContext | None) -> list[str]:
        return validate(story, account, plan, context)

    def review_edition(self, source: list[str], edited: list[str], names: set[str]) -> list[str]:
        """Each edited passage keeps its source's numbers and player names (a translation may move them)."""
        errors = []
        for i, (a, b) in enumerate(zip(source, edited)):
            if sorted(n.replace(",", ".") for n in _NUMBER.findall(a)) != \
                    sorted(n.replace(",", ".") for n in _NUMBER.findall(b)):
                errors.append(f"passage {i}: the numbers changed in editing")
            for name in names:
                if name in a and name not in b:
                    errors.append(f"passage {i}: {name!r} was lost in editing")
        if len(source) != len(edited):
            errors.append("the edition does not have one passage per beat")
        return errors

    def screen(self, texts: list[str]) -> tuple[list[str], str | None]:
        """(flagged categories, reason it was not screened)."""
        if not self.safety.available:
            return [], self.safety.reason
        try:
            return sorted({cat for t in texts for cat in self.safety.screen(t)}), None
        except (AzureUnavailable, OSError, ValueError) as e:
            return [], f"Content Safety call failed: {e}"
