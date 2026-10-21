"""``narrate(account, mode)``: validated narration + timed overlay. The entry point Build 7 calls.

* ``mode="foundry"``: the Foundry model writes it; every generation goes through
  ``validate``; a rejected one is regenerated with the violations fed back, up
  to ``MAX_ATTEMPTS``; if none passes, or Foundry is unavailable or errors, the
  template is used and ``fallback_reason`` says why.
* ``mode="template"``: the deterministic renderer, no model.

Validated or fallback, never raw model output: the template is validated too,
and a cached narration is re-validated before it is returned.

Cache: ``<cache_dir>/<game>/<moment>.<mode>.json``, keyed by the account's
content hash, the prompt version and the deployment, so the demo and tests
replay the same text. Fallbacks are not cached under ``foundry``, so the next
call retries the model.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from replay_room.attribution.store import ACCOUNTS_DIR
from replay_room.contracts.causal_account import CausalAccount
from replay_room.explain.assemble import account_hash, assemble
from replay_room.explain.brief import brief, ref_key
from replay_room.explain.foundry import PROMPT_VERSION, FoundryConfig, FoundryRenderer, FoundryUnavailable
from replay_room.explain.schema import ModelNarration, ModelSentence, Narration
from replay_room.explain.template import render_template
from replay_room.explain.validate import validate

MAX_ATTEMPTS = 3
CACHE_DIR = ACCOUNTS_DIR.parent / "narrations"

Mode = Literal["foundry", "template"]


class UngroundedNarration(RuntimeError):
    """A narration failed the grounding gate where that must never happen (the template)."""


def as_model_output(n: Narration) -> ModelNarration:
    return ModelNarration(headline_text=n.headline_text, sentences=tuple(
        ModelSentence(contribution_id=s.contribution_id, ref=ref_key(s.ref), role=s.role, text=s.text, metric=s.metric)
        for s in n.sentences))


def _template(account: CausalAccount, **meta) -> Narration:
    model = render_template(account)
    errors = validate(model, account)
    if errors:
        raise UngroundedNarration(f"template narration failed validation: {errors}")
    return assemble(model, account, "template", **meta)


def _cache_path(account: CausalAccount, mode: Mode, cache_dir: Path) -> Path:
    return Path(cache_dir) / account.game_id / f"{account.moment.moment_id}.{mode}.json"


def _cached(path: Path, account: CausalAccount, model: str | None) -> Narration | None:
    if not path.is_file():
        return None
    n = Narration.model_validate_json(path.read_text(encoding="utf-8"))
    if n.account_hash != account_hash(account) or n.model != model or validate(as_model_output(n), account):
        return None
    return n


def narrate(
    account: CausalAccount,
    mode: Mode = "foundry",
    *,
    renderer: FoundryRenderer | None = None,
    cache_dir: str | Path | None = CACHE_DIR,
    refresh: bool = False,
) -> Narration:
    if not account.moment.engine_eligible:
        raise ValueError("flagged moments have no account to narrate")
    if mode == "template":
        return _template(account)
    if mode != "foundry":
        raise ValueError(f"unknown mode {mode!r}")

    try:
        renderer = renderer or FoundryRenderer(FoundryConfig.from_env())
    except FoundryUnavailable as e:
        return _template(account, fallback_reason=str(e))
    path = _cache_path(account, "foundry", cache_dir) if cache_dir is not None else None
    model_tag = f"{renderer.model}@prompt-v{PROMPT_VERSION}"
    if path is not None and not refresh:
        hit = _cached(path, account, model_tag)
        if hit is not None:
            return hit

    material = brief(account)
    rejections: list[tuple[str, ...]] = []
    feedback: list[str] = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            raw = renderer.render(material, feedback)
        except Exception as e:  # network, auth, quota, bad JSON: all mean "use the floor"
            return _template(account, fallback_reason=f"Foundry call failed: {type(e).__name__}: {e}",
                             attempts=attempt, rejections=tuple(rejections))
        errors = validate(raw, account)
        if not errors:
            n = assemble(ModelNarration.model_validate(raw), account, "foundry", model=model_tag, attempts=attempt,
                         rejections=tuple(rejections))
            if path is not None:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(n.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n")
            return n
        rejections.append(tuple(errors))
        feedback = errors
    return _template(account, fallback_reason=f"no Foundry narration passed validation in {MAX_ATTEMPTS} attempts",
                     attempts=MAX_ATTEMPTS, rejections=tuple(rejections))
