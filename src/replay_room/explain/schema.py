"""Narration contracts (v2): what a Storyteller returns, and what leaves the explain stage.

The Storyteller tells a **framing plan** (``contracts.plan``): one passage per
beat, in the plan's order, in two registers:

* ``text``: the analyst register. It may weave in a number the tools computed,
  as meaning ("well above their usual 9 m"), never as the payload of the
  sentence;
* ``fan``: the fan register: no numbers and no metric jargon, still explaining.

* ``StoryOutput``: the raw output of a Storyteller (the Foundry model, or the
  deterministic composer). ``MODEL_OUTPUT_SCHEMA`` is the strict JSON Schema
  the model is constrained to (structured outputs).
* ``Narration``: the validated result ``narrate`` returns. Each beat carries
  the refs of the records it tells, copied from the tool outputs (never from
  the model), and the time of its first ref, for the viewer.

Nothing here is ever built from unvalidated model output: see ``validate``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from replay_room.contracts.plan import BeatKind
from replay_room.contracts.refs import EvidenceRef, _Model

NARRATION_VERSION = "2"


class BeatText(_Model):
    beat_id: str
    text: str  # analyst register
    fan: str  # fan register: no numbers, no metric jargon


class StoryOutput(_Model):
    headline: str  # one line, analyst register
    headline_fan: str  # one line, fan register
    beats: tuple[BeatText, ...]


def _strict(schema: dict) -> dict:
    """Pydantic's schema, made strict for structured outputs (every property required, no extras)."""
    defs = schema.pop("$defs", {})
    for node in (schema, *defs.values()):
        node["additionalProperties"] = False
        node["required"] = list(node.get("properties", {}))
        for prop in node.get("properties", {}).values():
            prop.pop("title", None)
        node.pop("title", None)
    if defs:
        schema["$defs"] = defs
    return schema


MODEL_OUTPUT_SCHEMA: dict = _strict(StoryOutput.model_json_schema())


class NarratedBeat(_Model):
    index: int = Field(ge=0)
    beat_id: str
    kind: BeatKind
    emphasis: str
    contribution_id: str | None = None
    link_id: str | None = None
    context_fact_id: str | None = None
    text: str
    fan: str
    refs: tuple[EvidenceRef, ...]  # copied from the tool outputs
    period_id: int
    t: float  # seconds in the period of the first ref


class Narration(_Model):
    narration_version: Literal["2"] = NARRATION_VERSION
    account_id: str
    moment_id: str
    account_hash: str  # sha256 of the account it tells (cache key)
    plan_hash: str  # sha256 of the plan (and context) it tells
    plan_source: Literal["rules", "foundry"]
    framing: Literal["realized", "prevented"]
    source: Literal["foundry", "template"]
    model: str | None = None  # Foundry deployment that wrote it (foundry source only)
    fallback_reason: str | None = None  # why the composer was used when Foundry was asked for
    attempts: int = 0  # model generations tried (0 for the composer)
    rejections: tuple[tuple[str, ...], ...] = ()  # Critic violations of each rejected attempt
    headline: str
    headline_fan: str
    beats: tuple[NarratedBeat, ...]
