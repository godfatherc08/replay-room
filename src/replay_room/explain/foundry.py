"""Foundry Storyteller: the model that tells a framing plan, on Microsoft Agent Framework.

The model is a writer, not a reasoner. It receives the story brief (the plan
with its records resolved; see ``brief``) and must return JSON matching
``schema.StoryOutput`` (structured outputs). Its output is untrusted until the
Critic (``validate``) passes it; ``narrate`` does that.

Connection: an Agent Framework ``Agent`` on a ``FoundryChatClient`` (the
Responses API of a Foundry project) with Entra ID (``DefaultAzureCredential``:
``az login`` locally, a managed identity on Azure Container Apps).

Configuration (environment):

* ``FOUNDRY_PROJECT_ENDPOINT``: the project endpoint,
  ``https://<resource>.services.ai.azure.com/api/projects/<project>``;
* ``FOUNDRY_MODEL_DEPLOYMENT``: a deployment that supports structured outputs;
* ``FOUNDRY_TEMPERATURE``: default ``0.4``; ``none`` omits it.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

PROMPT_VERSION = "4"
DEFAULT_TEMPERATURE = 0.4

SYSTEM_PROMPT = """\
You are the Storyteller of a football match-analysis system. Another system has already computed
what happened and why, and an Analyst has chosen how to tell it: an ordered list of beats. You
write each beat as connected, natural English a fan follows, like a sharp TV analyst talking over
the replay. You are a writer, not an analyst: the brief is the only truth, and it is complete.

Rules, all mandatory:
1. Tell exactly the beats given, in order, one passage per beat (one or two sentences), copying
   each beat_id. Also write a one-line headline.
2. Every beat has two registers. "text" (analyst) may weave in at most one number from that
   beat's own record, as meaning ("well above their usual 9 m"), never as the point of the
   sentence. "fan" has no numbers and no jargon (no xG, xT, VAEP, pitch control, probability,
   effect) and must still explain.
3. Name only the players in that beat's "may_name", and the two teams. No other person, team,
   place, tactic, body part, direction or detail that is not in the beat's record.
4. Never connect two players' actions causally ("dragged", "ran past", "opened", "because",
   "left the space") unless the beat carries_a_computed_link; then say exactly what the link says.
5. Keep the story connected: each beat follows from the one before. Do not repeat the same idea
   as a title, then a subtitle, then a gloss; say it once, well.
6. If outcome.scored is false, never say or imply the shot went in.
7. The "draft" of each beat is a correct telling. Improve its language; do not add to its facts.
8. Exact, not vague (analyst register): give the number and its comparison exactly as the draft does
   ("VAEP +0.077: the largest of the 5 facts that built the chance, 70% of the 0.110 xG chance").
   Never "about", "roughly", "nearly", "most valuable", "biggest": show the ranked values instead.
9. Frame by the outcome: if outcome.scored is false, never write "the goal" or "a goal" (except
   "a goal that didn't happen"); say "the chance".
10. Names and teams verbatim: every player belongs to the team the brief gives; never move a player
   to the other team and never merge two players' names.
11. "deep" (and "deep_fan") is the going-deeper passage of a beat: two to four connected sentences
   built on that beat's "positional" facts: where its players were against their average in this
   phase (say the confidence), how close the nearest opponent was, how the attacking team's
   control of the shooting spot moved, whether a marking held, and how it fits the move. Use only
   those figures; never restate the beat's own number as the depth. Leave it empty when the beat
   has no positional facts (the draft shows which).
Return only the JSON object required by the schema.
"""


class FoundryUnavailable(RuntimeError):
    """Foundry is not configured or not reachable; narrate falls back to the composer."""


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


def foundry_client(config: FoundryConfig) -> Any:
    """An Agent Framework chat client on the Foundry project (imported lazily: the composer needs none of it)."""
    try:
        from agent_framework.foundry import FoundryChatClient
        from azure.identity import DefaultAzureCredential
    except ImportError as e:  # pragma: no cover - depends on the optional extra
        raise FoundryUnavailable(f"install the agents extra (pip install -e .[agents]): {e}") from e
    return FoundryChatClient(project_endpoint=config.endpoint, model=config.deployment,
                             credential=DefaultAzureCredential())


_LOOP: asyncio.AbstractEventLoop | None = None
_LOOP_LOCK = threading.Lock()


def _model_loop() -> asyncio.AbstractEventLoop:
    """One long-lived event loop for every model call: the Foundry client keeps connections bound to the loop it
    first ran on, so a fresh loop per call breaks the retry ("Event loop is closed")."""
    global _LOOP
    with _LOOP_LOCK:
        if _LOOP is None or _LOOP.is_closed():
            _LOOP = asyncio.new_event_loop()
            threading.Thread(target=_LOOP.run_forever, name="model-calls", daemon=True).start()
        return _LOOP


def run_sync(coro: Any) -> Any:
    """Await ``coro`` from sync code (also from inside a running event loop, e.g. an MCP server's tool call)."""
    return asyncio.run_coroutine_threadsafe(coro, _model_loop()).result()


def run_structured(client: Any, name: str, instructions: str, message: str, schema: type,
                   temperature: float | None, tools: list[Any] | None = None) -> dict[str, Any]:
    """One Agent Framework agent turn constrained to ``schema`` (a pydantic model); returns the parsed JSON.

    ``tools``: Agent Framework tools for the turn (e.g. an ``MCPStdioTool``), connected for its duration.
    """
    from contextlib import AsyncExitStack

    from agent_framework import Agent

    options: dict[str, Any] = {"response_format": schema}
    if temperature is not None:
        options["temperature"] = temperature

    async def turn() -> Any:
        async with AsyncExitStack() as stack:
            for tool in tools or ():
                if hasattr(tool, "__aenter__"):
                    await stack.enter_async_context(tool)
            agent = Agent(client=client, instructions=instructions, name=name, tools=tools or None)
            return await agent.run(message, options=options)

    response = run_sync(turn())
    text = response.text
    if not text:
        raise ValueError(f"{name}: empty model output")
    return json.loads(text)


def user_message(brief: dict[str, Any], feedback: Sequence[str] = ()) -> str:
    msg = "Tell this story.\n\nBRIEF:\n" + json.dumps(brief, indent=1, ensure_ascii=False)
    if feedback:
        msg += ("\n\nYour previous telling was REJECTED by the Critic for these reasons. Fix every one; "
                "change nothing else about the rules:\n- " + "\n- ".join(feedback))
    return msg


class FoundryStoryteller:
    """Tells a brief with a Foundry model. ``client`` (an Agent Framework chat client) is injectable for tests."""

    def __init__(self, config: FoundryConfig, client: Any | None = None):
        self.config = config
        self._client = client

    @property
    def model(self) -> str:
        return self.config.deployment

    def client(self) -> Any:
        if self._client is None:
            self._client = foundry_client(self.config)
        return self._client

    def render(self, brief: dict[str, Any], feedback: Sequence[str] = ()) -> dict[str, Any]:
        """One generation. Returns the parsed JSON object (unvalidated)."""
        from replay_room.explain.schema import StoryOutput

        return run_structured(self.client(), "Storyteller", SYSTEM_PROMPT, user_message(brief, feedback),
                              StoryOutput, self.config.temperature)
