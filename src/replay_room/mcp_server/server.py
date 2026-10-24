"""The Replay Room engine as an MCP server (stdio or Streamable HTTP).

    python -m replay_room.mcp_server                      # stdio (what an MCP client launches)
    python -m replay_room.mcp_server --http --port 8765    # Streamable HTTP, e.g. on Azure Container Apps

Tools (all deterministic; the engine's outputs as JSON, unchanged):

* ``detect_moments(classes)``: the match's moments, explained and flagged;
* ``attribute(moment_id)``: the moment's ``CausalAccount``;
* ``match_context(moment_id)``: its ``MatchContext`` (baselines + deviation);
* ``narrate(moment_id, mode)``: the validated telling of its rule plan
  (``template``: the composer; ``foundry``: the model, Critic-gated).

``REPLAY_ROOM_MATCH`` (environment) names the match directory; the default is
the synthetic fixture.
"""

from __future__ import annotations

import os
from typing import Any

from mcp.server import MCPServer

from replay_room.mcp_server.service import ALL, service

INSTRUCTIONS = """\
Replay Room's deterministic football analysis engine. Causality is computed here, never by a
language model: detect_moments lists a match's talking points, attribute returns a moment's causal
account (every fact bound to an event id or a tracking frame), match_context returns per-match
baselines for the defending team and how this moment deviates, and narrate returns a telling that
has passed the grounding check. Use only what these tools return."""

server = MCPServer("replay-room-engine", title="Replay Room engine", instructions=INSTRUCTIONS, version="1")


def _svc():
    return service(os.environ.get("REPLAY_ROOM_MATCH") or None)


@server.tool(description="List the match's moments (explained and flagged) with what each one is.")
def detect_moments(classes: str = "all") -> dict[str, Any]:
    """``classes``: comma-separated moment classes, or all / explained / flagged."""
    from replay_room.detect.__main__ import parse_classes

    wanted = ALL if classes == "all" else parse_classes(classes)
    return {"game_id": _svc().match.meta.game_id, "moments": _svc().menu(wanted)}


@server.tool(description="The causal account of an engine-eligible moment: ranked, evidence-bound facts.")
def attribute(moment_id: str) -> dict[str, Any]:
    return _svc().account(moment_id).model_dump(mode="json")


@server.tool(description="Per-match baselines for the moment's defending team, and how this moment deviates.")
def match_context(moment_id: str) -> dict[str, Any]:
    return _svc().context(moment_id).model_dump(mode="json")


@server.tool(description="A grounded telling of the moment (rule plan); mode 'template' (no model) or 'foundry'.")
def narrate(moment_id: str, mode: str = "template") -> dict[str, Any]:
    if mode not in ("template", "foundry"):
        raise ValueError("mode is 'template' or 'foundry'")
    return _svc().narration(moment_id, mode).model_dump(mode="json")
