"""Framing: how a moment is told. Deterministic: the rule plan, the plan check, and beat -> record lookup.

The Analyst agent may propose a plan with a model; ``check_plan`` decides
whether it may be told, and ``rules_plan`` is the floor it falls back to.
"""

from replay_room.framing.check import check_plan
from replay_room.framing.facts import Facts, UnresolvedBeat
from replay_room.framing.rules import flaw_of, rules_plan

__all__ = ["Facts", "UnresolvedBeat", "check_plan", "flaw_of", "rules_plan"]
