"""Narration contracts: what the model must return, and what leaves Build 6.

* ``ModelNarration``: the raw structured output a renderer (the Foundry model,
  or the template) produces. One sentence per contribution, headline first then
  the account's rank order, each pinned to the contribution it narrates and to a
  ref string (``event:<action_id>`` / ``frame:<frame_id>``) from that
  contribution's own evidence. ``MODEL_OUTPUT_SCHEMA`` is the strict JSON Schema
  the model is constrained to (structured outputs).
* ``Narration``: the validated result ``narrate`` returns. Every sentence
  carries its ref as a structured ``EventRef`` / ``FrameRef`` copied from the
  account (not from the model) and the time of that record; ``timed_overlay``
  is the same sentences as cues in time order, ready to drive on-screen
  graphics in sync with the replay.

Nothing here is ever built from unvalidated model output: see ``validate``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from replay_room.contracts.refs import EvidenceRef, _Model

NARRATION_VERSION = "1"
CUE_SECONDS = 3.0  # how long a cue stays up when nothing follows it


class Metric(_Model):
    name: str  # "effect" or a key of the contribution's metrics (e.g. "xg", "space_conceded")
    value: float


class ModelSentence(_Model):
    contribution_id: str
    ref: str  # "event:<action_id>" or "frame:<frame_id>", from that contribution's evidence
    role: str  # the contribution's role, as given
    text: str
    metric: Metric | None  # the one number the sentence states, if any


class ModelNarration(_Model):
    headline_text: str
    sentences: tuple[ModelSentence, ...]


MODEL_OUTPUT_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["headline_text", "sentences"],
    "properties": {
        "headline_text": {"type": "string", "description": "One line: the headline contribution, in plain words."},
        "sentences": {
            "type": "array",
            "description": "Exactly one per contribution: the headline first, then the others in rank order.",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["contribution_id", "ref", "role", "text", "metric"],
                "properties": {
                    "contribution_id": {"type": "string"},
                    "ref": {"type": "string", "description": "One of the contribution's refs, copied exactly."},
                    "role": {"type": "string"},
                    "text": {"type": "string"},
                    "metric": {
                        "anyOf": [
                            {"type": "null"},
                            {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["name", "value"],
                                "properties": {"name": {"type": "string"}, "value": {"type": "number"}},
                            },
                        ]
                    },
                },
            },
        },
    },
}


class Sentence(_Model):
    index: int = Field(ge=0)
    contribution_id: str
    role: str
    headline: bool
    text: str
    ref: EvidenceRef  # copied from the account
    metric: Metric | None = None
    period_id: int
    t: float  # seconds in the period of the cited record


class OverlayCue(_Model):
    sentence_index: int
    contribution_id: str
    period_id: int
    t_start: float
    t_end: float
    frame_id: int | None = None  # set when the cited record is a frame
    action_id: int | None = None  # set when the cited record is an event
    text: str


class Narration(_Model):
    narration_version: Literal["1"] = NARRATION_VERSION
    account_id: str
    moment_id: str
    account_hash: str  # sha256 of the account it narrates (cache key)
    framing: Literal["realized", "prevented"]
    source: Literal["foundry", "template"]
    model: str | None = None  # Foundry deployment that wrote it (foundry source only)
    fallback_reason: str | None = None  # why the template was used when Foundry was asked for
    attempts: int = 0  # model generations tried (0 for the template)
    rejections: tuple[tuple[str, ...], ...] = ()  # validator errors of each rejected attempt
    headline_text: str
    sentences: tuple[Sentence, ...]
    timed_overlay: tuple[OverlayCue, ...]
