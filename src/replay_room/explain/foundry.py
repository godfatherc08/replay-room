"""Foundry renderer: the one place in Replay Room that calls a language model.

The model is a renderer, not a reasoner. It receives the narration brief (the
causal account, reshaped; see ``brief``) and nothing else, and must return JSON
matching ``schema.MODEL_OUTPUT_SCHEMA`` (structured outputs, strict). Its
output is untrusted until ``validate`` passes it; ``narrate`` does that.

Connection (azure-ai-projects 2.x): ``AIProjectClient(endpoint, credential)``
with Entra ID (``DefaultAzureCredential``: ``az login`` locally, a managed
identity on Azure Container Apps); ``get_openai_client()`` gives an OpenAI
client on ``{endpoint}/openai/v1`` whose bearer token is scoped to
``https://ai.azure.com/.default``; generation is a Responses API call against a
model deployment in the project.

Configuration (environment):

* ``FOUNDRY_PROJECT_ENDPOINT``: the project endpoint,
  ``https://<resource>.services.ai.azure.com/api/projects/<project>``;
* ``FOUNDRY_MODEL_DEPLOYMENT``: the deployment name of a model that supports
  structured outputs;
* ``FOUNDRY_TEMPERATURE``: default ``0.2``; ``none`` omits it (for models that
  reject a temperature).
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from replay_room.explain.schema import MODEL_OUTPUT_SCHEMA

PROMPT_VERSION = "1"
DEFAULT_TEMPERATURE = 0.2

SYSTEM_PROMPT = """\
You are the narration renderer of a football match-analysis system. You turn a causal account,
which another system has already computed, into short, clear sentences for a fan. You are a
renderer, not an analyst: the account is the only truth, and it is complete.

Rules, all mandatory:
1. Use ONLY the account you are given. Never introduce any event, player, team, place, cause,
   tactic, time, position, statistic or number that is not in it. Do not use outside knowledge
   about football, these teams or these players. If the account does not say it, do not say it.
2. Write exactly one sentence per contribution, in the order given by "order" (the headline
   first, then the rest by rank). For each, set contribution_id, copy one of that contribution's
   "refs" exactly into "ref", and copy its "role" exactly.
3. Refer to players by their "player_name" (optionally with their player_id) and to teams by the
   names given. Name no other person, team or place.
4. Numbers: you may state a number only if it appears in the account (effect, a metric, the
   outcome value, a counterfactual value or completion probability), written to at most three
   decimals or as a percentage of the same value. Put the one number a sentence relies on in
   "metric" with its name ("effect", a key of that contribution's "metrics", or "outcome_value").
   A sentence may state no number (metric null).
5. Meaning of the fields: "effect" is how much that fact changed the attacking team's chance of
   the outcome (positive helped the attack, negative hurt it). "role" says what the fact was
   (assist, build_up, space_creation, defensive_error, primary_cause, prevention, ...); "label"
   names the action or movement. Describe them in plain words; do not invent detail about how
   it happened beyond the label, role and numbers.
6. Framing: if outcome.framing is "prevented", the story is a goal that didn't happen: the
   headline is what stopped the chance. Never say or imply that it was scored. If outcome.scored
   is false, never say the shot was scored, converted or went in.
   If "realized", the headline is the main reason the defending side failed to stop it
   (or, if there is none, the main creator).
7. "headline_text" is one plain line about the headline contribution, under the same rules.
8. If a contribution has a counterfactual, you may mention the better option it lists, with its
   value, in that contribution's sentence.
Return only the JSON object required by the schema.
"""


class FoundryUnavailable(RuntimeError):
    """Foundry is not configured or not reachable; narrate falls back to the template."""


@dataclass(frozen=True)
class FoundryConfig:
    endpoint: str
    deployment: str
    temperature: float | None = DEFAULT_TEMPERATURE

    @classmethod
    def from_env(cls) -> FoundryConfig:
        endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT", "").strip()
        deployment = os.environ.get("FOUNDRY_MODEL_DEPLOYMENT", "").strip()
        if not endpoint or not deployment:
            raise FoundryUnavailable("set FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_MODEL_DEPLOYMENT to use Foundry")
        raw = os.environ.get("FOUNDRY_TEMPERATURE", str(DEFAULT_TEMPERATURE)).strip().lower()
        return cls(endpoint, deployment, None if raw in ("", "none") else float(raw))


def user_message(brief: dict[str, Any], feedback: Sequence[str] = ()) -> str:
    msg = "Narrate this causal account.\n\nACCOUNT:\n" + json.dumps(brief, indent=1, ensure_ascii=False)
    if feedback:
        msg += ("\n\nYour previous narration of this account was REJECTED by the grounding check for these "
                "reasons. Fix every one; change nothing else about the rules:\n- " + "\n- ".join(feedback))
    return msg


class FoundryRenderer:
    """Calls a Foundry model deployment. ``client`` (an OpenAI-compatible client) is injectable for tests."""

    def __init__(self, config: FoundryConfig, client: Any | None = None):
        self.config = config
        self._client = client

    @property
    def model(self) -> str:
        return self.config.deployment

    def client(self) -> Any:
        if self._client is None:
            from azure.ai.projects import AIProjectClient
            from azure.identity import DefaultAzureCredential

            project = AIProjectClient(endpoint=self.config.endpoint, credential=DefaultAzureCredential())
            self._client = project.get_openai_client()
        return self._client

    def render(self, brief: dict[str, Any], feedback: Sequence[str] = ()) -> dict[str, Any]:
        """One generation. Returns the parsed JSON object (unvalidated)."""
        kwargs: dict[str, Any] = {
            "model": self.config.deployment,
            "instructions": SYSTEM_PROMPT,
            "input": user_message(brief, feedback),
            "text": {"format": {"type": "json_schema", "name": "narration", "schema": MODEL_OUTPUT_SCHEMA,
                                "strict": True}},
            "store": False,
        }
        if self.config.temperature is not None:
            kwargs["temperature"] = self.config.temperature
        response = self.client().responses.create(**kwargs)
        text = response.output_text
        if not text:
            raise ValueError(f"empty model output (status {getattr(response, 'status', '?')})")
        return json.loads(text)
