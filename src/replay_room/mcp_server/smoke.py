"""MCP smoke test: launch the engine server over stdio, list its tools and call each one.

    python -m replay_room.mcp_server.smoke [--moment SYN-0007-goal-1]

Prints one line per tool with the shape of what came back; exits non-zero if
a tool is missing or a call fails.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from mcp import Client, StdioServerParameters

TOOLS = ("detect_moments", "attribute", "match_context", "narrate")


def payload(result: Any) -> dict[str, Any]:
    """A tool result's JSON: the structured content, else the text content parsed."""
    if result.is_error:
        raise RuntimeError(" ".join(getattr(c, "text", "") for c in result.content))
    if result.structured_content is not None:
        return result.structured_content
    return json.loads(result.content[0].text)


async def smoke(moment_id: str) -> dict[str, Any]:
    params = StdioServerParameters(command=sys.executable, args=["-m", "replay_room.mcp_server"])
    async with Client(params, read_timeout_seconds=600) as client:
        listed = sorted(t.name for t in (await client.list_tools()).tools)
        missing = sorted(set(TOOLS) - set(listed))
        if missing:
            raise RuntimeError(f"server does not list {missing}")
        out: dict[str, Any] = {"tools": listed}
        menu = payload(await client.call_tool("detect_moments", {"classes": "all"}))
        out["detect_moments"] = menu
        out["attribute"] = payload(await client.call_tool("attribute", {"moment_id": moment_id}))
        out["match_context"] = payload(await client.call_tool("match_context", {"moment_id": moment_id}))
        out["narrate"] = payload(await client.call_tool("narrate", {"moment_id": moment_id, "mode": "template"}))
        return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="replay_room.mcp_server.smoke")
    ap.add_argument("--moment", default="SYN-0007-goal-1")
    args = ap.parse_args(argv)
    out = asyncio.run(smoke(args.moment))
    print(f"tools: {', '.join(out['tools'])}")
    moments = out["detect_moments"]["moments"]
    print(f"detect_moments: {len(moments)} moments "
          f"({sum(m['engine_eligible'] for m in moments)} explained, {sum(not m['engine_eligible'] for m in moments)} flagged)")
    a = out["attribute"]
    print(f"attribute: {a['account_id']}  headline {a['headline_contribution_id']}  "
          f"supporting {a['supporting_contribution_id']}  {len(a['contributions'])} contributions, {len(a['links'])} links")
    c = out["match_context"]
    print(f"match_context: {len(c['facts'])} facts ({', '.join(f['kind'] for f in c['facts'])}), "
          f"{len(c['insufficient'])} insufficient")
    n = out["narrate"]
    print(f"narrate: source {n['source']}, {len(n['beats'])} beats; headline: {n['headline']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
