"""Azure services the agents use, each behind a local fallback so the pipeline runs without them.

* ``AzureMcp``: the Azure MCP server (``npx -y @azure/mcp@latest server start``),
  consumed with the MCP client. Its namespace tools take ``{"intent", "command",
  "parameters"}``; we use ``kusto`` / ``kusto_query`` (Fabric Eventhouse is
  Kusto-compatible) and ``cosmos`` / ``cosmos_database_container_item_query``.
* ``Translator``: Azure AI Translator (``AZURE_TRANSLATOR_KEY``,
  ``AZURE_TRANSLATOR_REGION``, optional ``AZURE_TRANSLATOR_ENDPOINT``).
* ``ContentSafety``: Azure AI Content Safety text analysis
  (``CONTENT_SAFETY_ENDPOINT``, ``CONTENT_SAFETY_KEY``).

Each reports ``available`` and, when not, ``reason``: the caller records the
reason and takes its deterministic path.
"""

from __future__ import annotations

import json
import os
import shutil
from typing import Any

import httpx


class AzureUnavailable(RuntimeError):
    pass


class AzureMcp:
    """One call per method: launch the Azure MCP server, call a namespace tool, close."""

    def __init__(self, namespaces: tuple[str, ...] = ("kusto", "cosmos"), timeout_s: float = 300):
        self.namespaces = namespaces
        self.timeout = timeout_s
        self.npx = shutil.which("npx") or shutil.which("npx.cmd")

    @property
    def available(self) -> bool:
        return self.npx is not None

    async def _call(self, tool: str, command: str, parameters: dict[str, Any], intent: str) -> Any:
        from mcp import Client, StdioServerParameters

        args = ["-y", "@azure/mcp@latest", "server", "start"]
        for ns in self.namespaces:
            args += ["--namespace", ns]
        async with Client(StdioServerParameters(command=self.npx, args=args),
                          read_timeout_seconds=self.timeout) as client:
            result = await client.call_tool(tool, {"intent": intent, "command": command, "parameters": parameters})
        text = " ".join(getattr(c, "text", "") for c in result.content)
        if result.is_error:
            raise AzureUnavailable(f"azure mcp {command}: {text[:400]}")
        body = result.structured_content if result.structured_content is not None else json.loads(text)
        if isinstance(body, dict) and body.get("status", 200) >= 400:
            raise AzureUnavailable(f"azure mcp {command}: {body.get('message', body)}")
        return body.get("results", body) if isinstance(body, dict) else body

    def call(self, tool: str, command: str, parameters: dict[str, Any], intent: str) -> Any:
        if not self.available:
            raise AzureUnavailable("npx is not on PATH (Node.js is needed to run the Azure MCP server)")
        from replay_room.explain.foundry import run_sync

        return run_sync(self._call(tool, command, parameters, intent))

    def kusto_query(self, cluster_uri: str, database: str, query: str) -> Any:
        return self.call("kusto", "kusto_query", {"cluster-uri": cluster_uri, "database": database, "query": query},
                         "read match events from the Fabric Eventhouse")

    def cosmos_query(self, account: str, database: str, container: str, query: str) -> Any:
        return self.call("cosmos", "cosmos_database_container_item_query",
                         {"account": account, "database": database, "container": container, "query": query},
                         "read causal accounts from Cosmos DB")


class Translator:
    def __init__(self) -> None:
        self.key = os.environ.get("AZURE_TRANSLATOR_KEY", "").strip()
        self.region = os.environ.get("AZURE_TRANSLATOR_REGION", "").strip()
        self.endpoint = os.environ.get("AZURE_TRANSLATOR_ENDPOINT", "https://api.cognitive.microsofttranslator.com")

    @property
    def available(self) -> bool:
        return bool(self.key)

    @property
    def reason(self) -> str:
        return "set AZURE_TRANSLATOR_KEY (and AZURE_TRANSLATOR_REGION) to translate"

    def translate(self, texts: list[str], to: str) -> list[str]:
        if not self.available:
            raise AzureUnavailable(self.reason)
        headers = {"Ocp-Apim-Subscription-Key": self.key, "Content-Type": "application/json"}
        if self.region:
            headers["Ocp-Apim-Subscription-Region"] = self.region
        r = httpx.post(f"{self.endpoint.rstrip('/')}/translate", params={"api-version": "3.0", "from": "en", "to": to},
                       headers=headers, json=[{"text": t} for t in texts], timeout=30)
        r.raise_for_status()
        return [item["translations"][0]["text"] for item in r.json()]


class ContentSafety:
    SEVERITY_LIMIT = 2  # categories at or above this severity block the text

    def __init__(self) -> None:
        self.endpoint = os.environ.get("CONTENT_SAFETY_ENDPOINT", "").strip()
        self.key = os.environ.get("CONTENT_SAFETY_KEY", "").strip()

    @property
    def available(self) -> bool:
        return bool(self.endpoint and self.key)

    @property
    def reason(self) -> str:
        return "set CONTENT_SAFETY_ENDPOINT and CONTENT_SAFETY_KEY to screen narration"

    def screen(self, text: str) -> list[str]:
        """The harm categories the text trips (empty = clean)."""
        if not self.available:
            raise AzureUnavailable(self.reason)
        r = httpx.post(f"{self.endpoint.rstrip('/')}/contentsafety/text:analyze",
                       params={"api-version": "2024-09-01"}, headers={"Ocp-Apim-Subscription-Key": self.key},
                       json={"text": text[:10000]}, timeout=30)
        r.raise_for_status()
        return [c["category"] for c in r.json().get("categoriesAnalysis", [])
                if c.get("severity", 0) >= self.SEVERITY_LIMIT]
