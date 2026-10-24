"""``narrate(account, mode, context=, plan=)``: a validated telling of a framing plan.

* ``mode="foundry"``: the Foundry Storyteller writes it; every generation goes
  through the Critic (``validate``); a rejected one is regenerated with the
  violations fed back, up to ``MAX_ATTEMPTS``; if none passes, or Foundry is
  unavailable or errors, the composer is used and ``fallback_reason`` says why.
* ``mode="template"``: the deterministic composer, no model.

``plan`` defaults to the rule plan (``framing.rules_plan``) of the account and
context. A plan that fails ``framing.check_plan`` is refused: only a checked
plan is ever told.

Validated or fallback, never raw model output: the composer is validated too,
and a cached telling is re-validated before it is returned.

Cache: ``<cache_dir>/<game>/<moment>.<mode>.json``, keyed by the account's and
the plan's content hashes, the prompt version and the deployment, so the demo
and tests replay the same text. Fallbacks are not cached under ``foundry``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from replay_room.attribution.store import ACCOUNTS_DIR
from replay_room.contracts.causal_account import CausalAccount
from replay_room.contracts.context import MatchContext
from replay_room.contracts.plan import FramingPlan
from replay_room.explain.assemble import account_hash, assemble, plan_hash
from replay_room.explain.brief import brief
from replay_room.explain.compose import compose
from replay_room.explain.foundry import PROMPT_VERSION, FoundryConfig, FoundryStoryteller, FoundryUnavailable
from replay_room.explain.schema import BeatText, Narration, StoryOutput
from replay_room.explain.validate import validate
from replay_room.framing import check_plan, rules_plan

MAX_ATTEMPTS = 3
CACHE_DIR = ACCOUNTS_DIR.parent / "narrations"

Mode = Literal["foundry", "template"]


class UngroundedNarration(RuntimeError):
    """A telling failed the grounding gate where that must never happen (the composer), or the plan was refused."""


def as_story(n: Narration) -> StoryOutput:
    return StoryOutput(headline=n.headline, headline_fan=n.headline_fan,
                       beats=tuple(BeatText(beat_id=b.beat_id, text=b.text, fan=b.fan) for b in n.beats))


def _composed(account: CausalAccount, plan: FramingPlan, context: MatchContext | None, **meta) -> Narration:
    story = compose(account, plan, context)
    errors = validate(story, account, plan, context)
    if errors:
        raise UngroundedNarration(f"composed story failed validation: {errors}")
    return assemble(story, account, plan, context, "template", **meta)


def _cache_path(account: CausalAccount, mode: Mode, cache_dir: Path) -> Path:
    return Path(cache_dir) / account.game_id / f"{account.moment.moment_id}.{mode}.json"


def _cached(path: Path, account: CausalAccount, plan: FramingPlan, context: MatchContext | None,
            model: str | None) -> Narration | None:
    if not path.is_file():
        return None
    try:
        n = Narration.model_validate_json(path.read_text(encoding="utf-8"))
    except ValueError:  # an older narration version
        return None
    if n.account_hash != account_hash(account) or n.plan_hash != plan_hash(plan, context) or n.model != model \
            or validate(as_story(n), account, plan, context):
        return None
    return n


def narrate(
    account: CausalAccount,
    mode: Mode = "foundry",
    *,
    context: MatchContext | None = None,
    plan: FramingPlan | None = None,
    renderer: FoundryStoryteller | None = None,
    cache_dir: str | Path | None = CACHE_DIR,
    refresh: bool = False,
) -> Narration:
    if not account.moment.engine_eligible:
        raise ValueError("flagged moments have no account to narrate")
    plan = plan or rules_plan(account, context)
    refused = check_plan(plan, account, context)
    if refused:
        raise UngroundedNarration(f"the Critic refused the plan: {refused}")
    if mode == "template":
        return _composed(account, plan, context)
    if mode != "foundry":
        raise ValueError(f"unknown mode {mode!r}")

    try:
        renderer = renderer or FoundryStoryteller(FoundryConfig.from_env())
    except FoundryUnavailable as e:
        return _composed(account, plan, context, fallback_reason=str(e))
    path = _cache_path(account, "foundry", cache_dir) if cache_dir is not None else None
    model_tag = f"{renderer.model}@prompt-v{PROMPT_VERSION}"
    if path is not None and not refresh:
        hit = _cached(path, account, plan, context, model_tag)
        if hit is not None:
            return hit

    material = brief(account, plan, context)
    rejections: list[tuple[str, ...]] = []
    feedback: list[str] = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            raw = renderer.render(material, feedback)
        except Exception as e:  # network, auth, quota, bad JSON: all mean "use the floor"
            return _composed(account, plan, context, fallback_reason=f"Foundry call failed: {type(e).__name__}: {e}",
                             attempts=attempt, rejections=tuple(rejections))
        errors = validate(raw, account, plan, context)
        if not errors:
            n = assemble(StoryOutput.model_validate(raw), account, plan, context, "foundry", model=model_tag,
                         attempts=attempt, rejections=tuple(rejections))
            if path is not None:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(n.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n")
            return n
        rejections.append(tuple(errors))
        feedback = errors
    return _composed(account, plan, context,
                     fallback_reason=f"no Foundry telling passed the Critic in {MAX_ATTEMPTS} attempts",
                     attempts=MAX_ATTEMPTS, rejections=tuple(rejections))
