"""Build 6: grounded explanation renderer. The only stage that calls a language model.

``narrate(account, mode)`` returns a validated ``Narration`` (headline + one cited
sentence per contribution + a timed overlay). The Foundry model writes it; the
grounding gate (``validate``) decides whether it may leave; the deterministic
template is the floor.
"""

from replay_room.explain.narrate import narrate
from replay_room.explain.schema import ModelNarration, Narration
from replay_room.explain.validate import validate

__all__ = ["ModelNarration", "Narration", "narrate", "validate"]
