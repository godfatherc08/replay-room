"""Build 6: the Storyteller. The only stage that calls a language model to write.

``narrate(account, mode, context=, plan=)`` returns a validated ``Narration``
(a headline and one cited passage per beat of a framing plan, in an analyst
and a fan register). The Foundry model writes it; the Critic (``validate``)
decides whether it may leave; the deterministic composer is the floor.
"""

from replay_room.explain.narrate import narrate
from replay_room.explain.schema import Narration, StoryOutput
from replay_room.explain.validate import validate

__all__ = ["Narration", "StoryOutput", "narrate", "validate"]
