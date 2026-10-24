"""Match context: per-match baselines for the defending team, and how a moment deviates from them.

``match_context(moment, ...)`` returns a ``MatchContext`` (``contracts.context``).
Deterministic; consumed by the Analyst as a supporting beat, never as a cause.
"""

from replay_room.context.baselines import match_context, match_context_for

__all__ = ["match_context", "match_context_for"]
