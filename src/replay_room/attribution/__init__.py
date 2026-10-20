"""Build 4: causal attribution + evidence trace. Deterministic; no language model anywhere.

``attribute(valued_moment, ...)`` turns one engine-eligible moment, valued by
Build 3, into a ``CausalAccount``: a ranked list of evidence-bound facts about
what moved the attacking team's probability of realising the outcome.

Semantics:

* **Outcome value V** is the ex-ante value of the moment's ``outcome_ref`` (its
  xG; the attacking team's xT there for a non-shot such as an own goal). The
  account attributes over V, never over "goal = 1", with one path for every
  explained class.
* **Sign.** Every ``effect`` is the change in the attacking team's (the
  beneficiary's) P(outcome). A defending-team action counts with the opposite
  sign of its own value, so a lost ball or a lapse is a positive effect: a
  failure to prevent.
* **Realized vs prevented** is one flag on the outcome: prevented iff the
  terminal action did not score and V was a big chance (``BIG_CHANCE_XG``).
  Realized accounts are headlined by the largest conceding-side failure
  (``primary_cause``), else the largest creator. Prevented accounts add the
  ``chance_denied`` fact (effect ``-V``: the save, block or miss) and lead with it.
* **Evidence bar.** A fact enters iff ``|effect| >= EFFECT_THRESHOLD`` (top
  ``TOP_K``), and every fact is bound to an event id (on-ball) or an in-window
  tracking frame (off-ball).

Modules: ``on_ball`` (track A), ``off_ball`` (track B), ``fuse`` (bar, ranking,
headline), ``counterfactual`` (better options from the real positions),
``engine`` (``attribute``, ``attribute_match``), ``store`` (JSON persistence).
"""

from replay_room.attribution.engine import attribute, attribute_match
from replay_room.attribution.store import load_account, save_accounts

__all__ = ["attribute", "attribute_match", "load_account", "save_accounts"]
