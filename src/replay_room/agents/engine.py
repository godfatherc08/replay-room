"""How the agents reach the engine: the four tools, in-process or over MCP. Same answers either way.

* ``InProcessEngine``: calls ``mcp_server.service`` directly (fast; tests, render);
* ``McpEngine``: launches ``python -m replay_room.mcp_server`` and calls its
  tools over stdio with the MCP client, keeping one session open on a
  background event loop. This is the path the demo shows: the agents consume
  the engine as an MCP server.

Both return the contract objects (``CausalAccount``, ``MatchContext``,
``Narration``), validated on arrival, so a tool answer that does not parse is
refused rather than passed on.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
from pathlib import Path
from typing import Any, Protocol

from replay_room.contracts.causal_account import CausalAccount
from replay_room.contracts.context import MatchContext
from replay_room.explain.schema import Narration


class Engine(Protocol):
    name: str

    def detect_moments(self, classes: str = "all") -> dict[str, Any]: ...

    def attribute(self, moment_id: str) -> CausalAccount: ...

    def match_context(self, moment_id: str) -> MatchContext: ...

    def narrate(self, moment_id: str, mode: str = "template") -> Narration: ...


class InProcessEngine:
    name = "in-process"

    def __init__(self, match_dir: str | Path | None = None, svc: Any | None = None):
        from replay_room.mcp_server.service import service

        self.svc = svc or service(match_dir)

    def detect_moments(self, classes: str = "all") -> dict[str, Any]:
        from replay_room.detect.__main__ import parse_classes
        from replay_room.mcp_server.service import ALL

        wanted = ALL if classes == "all" else parse_classes(classes)
        return {"game_id": self.svc.match.meta.game_id, "moments": self.svc.menu(wanted)}

    def attribute(self, moment_id: str) -> CausalAccount:
        return self.svc.account(moment_id)

    def match_context(self, moment_id: str) -> MatchContext:
        return self.svc.context(moment_id)

    def narrate(self, moment_id: str, mode: str = "template") -> Narration:
        return self.svc.narration(moment_id, mode)


class McpEngine:
    """The engine over MCP (stdio). Use as a context manager, or call ``close()``."""

    name = "mcp (stdio)"

    def __init__(self, match_dir: str | Path | None = None, timeout_s: float = 600):
        from mcp import Client, StdioServerParameters

        env = {**os.environ, **({"REPLAY_ROOM_MATCH": str(match_dir)} if match_dir else {})}
        self._params = StdioServerParameters(command=sys.executable, args=["-m", "replay_room.mcp_server"], env=env)
        self._client_cls = Client
        self._timeout = timeout_s
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()
        self._client = None
        self._run(self._open())
        self.tools = sorted(t.name for t in self._run(self._client.list_tools()).tools)

    async def _open(self) -> None:
        self._client = self._client_cls(self._params, read_timeout_seconds=self._timeout)
        await self._client.__aenter__()

    def _run(self, coro: Any) -> Any:
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result()

    def call(self, tool: str, **arguments: Any) -> dict[str, Any]:
        result = self._run(self._client.call_tool(tool, arguments))
        if result.is_error:
            raise RuntimeError(f"{tool}: " + " ".join(getattr(c, "text", "") for c in result.content))
        if result.structured_content is not None:
            return result.structured_content
        return json.loads(result.content[0].text)

    def detect_moments(self, classes: str = "all") -> dict[str, Any]:
        return self.call("detect_moments", classes=classes)

    def attribute(self, moment_id: str) -> CausalAccount:
        return CausalAccount.model_validate(self.call("attribute", moment_id=moment_id))

    def match_context(self, moment_id: str) -> MatchContext:
        return MatchContext.model_validate(self.call("match_context", moment_id=moment_id))

    def narrate(self, moment_id: str, mode: str = "template") -> Narration:
        return Narration.model_validate(self.call("narrate", moment_id=moment_id, mode=mode))

    def close(self) -> None:
        if self._client is not None:
            try:
                self._run(self._client.__aexit__(None, None, None))
            finally:
                self._client = None
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=10)

    def __enter__(self) -> McpEngine:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()
