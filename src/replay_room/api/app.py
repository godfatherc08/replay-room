"""The live backend: one moment told by the agents now, returned as the bundle the viewer already loads.

    GET /healthz                  -> {"ok": true, "moments": [...]}
    GET /api/bundle/{moment_id}   -> the moment's bundle (same shape as ``render`` writes), plus ``live``

Each request runs the orchestrator exactly as ``python -m replay_room.render`` does
(``attribute`` + ``match_context`` -> Analyst -> Critic -> Storyteller <-> Critic ->
Editor) and exports the bundle with ``render.export``. Nothing here computes a
fact: the engine does, and the Critic gates every telling. With Foundry configured
(``FOUNDRY_*``; Entra ID through ``DefaultAzureCredential``, a managed identity on
Azure Container Apps) the model agents tell it; otherwise their deterministic floors.

``ALLOWED_ORIGINS`` (comma-separated) is the CORS allow-list, e.g. the Static Web
Apps origin. ``REPLAY_ROOM_MATCH`` names the match (default: the demo fixture).
Requests are served one at a time: model calls share one event loop.
"""

from __future__ import annotations

import os
import threading
import time
from functools import cached_property
from typing import Any

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from replay_room.agents.engine import InProcessEngine
from replay_room.agents.orchestrator import Orchestrator
from replay_room.agents.sources import FixtureStream
from replay_room.mcp_server.service import service
from replay_room.render.export import export_moment


class Studio:
    """The engine and the agents for one match, built once and reused across requests."""

    def __init__(self, match_dir: str | None = None):
        self.svc = service(match_dir)
        self.lock = threading.Lock()

    @cached_property
    def orchestrator(self) -> Orchestrator:
        orch = Orchestrator(InProcessEngine(svc=self.svc), FixtureStream(self.svc.match_dir), mode="foundry")
        orch.scout()
        return orch

    @cached_property
    def accounts(self) -> list:
        """Every explainable moment's account: the bundle's timeline lists them all."""
        return [self.svc.account(m.moment_id) for m in self.orchestrator.menu if m.explainable]

    def moments(self) -> list[str]:
        return [m.moment_id for m in self.orchestrator.menu if m.explainable]

    def bundle(self, moment_id: str) -> dict[str, Any]:
        with self.lock:
            orch = self.orchestrator
            if moment_id not in self.moments():
                raise KeyError(moment_id)
            started, first = time.monotonic(), len(orch.trace)
            told = orch.explain(moment_id)
            bundle = export_moment(told.account, self.svc.match, told.narration, told.plan, self.accounts,
                                   told.context, told.editions)
            bundle["live"] = {"seconds": round(time.monotonic() - started, 1),
                              "trace": [s.__dict__ for s in orch.trace[first:]]}
            return bundle


_studio: Studio | None = None


def studio() -> Studio:
    global _studio
    if _studio is None:
        _studio = Studio(os.environ.get("REPLAY_ROOM_MATCH") or None)
    return _studio


async def healthz(_: Request) -> JSONResponse:
    return JSONResponse({"ok": True, "moments": await run_in_threadpool(studio().moments)})


async def bundle(request: Request) -> JSONResponse:
    moment_id = request.path_params["moment_id"]
    try:
        return JSONResponse(await run_in_threadpool(studio().bundle, moment_id))
    except KeyError:
        return JSONResponse({"error": f"{moment_id} is not an explainable moment of this match"}, status_code=404)


def create_app() -> Starlette:
    origins = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]
    return Starlette(
        routes=[Route("/healthz", healthz), Route("/api/bundle/{moment_id}", bundle)],
        middleware=[Middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET"])],
    )


app = create_app()
