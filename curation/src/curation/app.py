"""The curation plane's ASGI application: the UI and the MCP server, one process.

Both surfaces bind the same in-memory service layer, which is what makes the
thin-binding norm structurally easy rather than a rule someone has to remember.
A separate MCP process would need its own path to the catalogue and would
reintroduce exactly the divergence that norm exists to prevent. The cost
accepted is that the MCP surface goes down when the UI process does — tolerable
because both live on the curation plane, whose downtime is invisible to the
household.

**The lifespan wiring below is load-bearing and its failure mode is total.**
Starlette does not run a mounted sub-app's lifespan, so a session manager
mounted without the host entering `run()` raises `RuntimeError: Task group is
not initialized` on *every* request. The SDK's own `streamable_http_app()` sets
that lifespan on the app it returns — which is precisely why mounting that app
under a host is silent: the correct lifespan exists, mounted where nothing runs
it. Driving the session manager from this application's own lifespan is what
makes the mount work.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Final

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.types import Receive, Scope, Send

from curation.http import api, pages
from curation.mcp.server import build_server
from curation.services.container import Services
from curation.services.errors import ServiceError
from curation.services.sweep import start_sweeping

log = logging.getLogger(__name__)

#: Where MCP clients connect. Frozen with the tool names — a client's server
#: config carries this URL.
MCP_PATH: Final[str] = "/mcp"

#: How long an MCP session may sit idle before the server reaps it.
#:
#: Without a value here sessions never expire, and each one holds an instance and
#: a live task for the life of the process. That is a growing collection with no
#: lifecycle on an always-on plane whose systemd unit sets `MemoryMax`, so the
#: failure is an OOM-killed unit rather than a gradual slowdown — and the unit
#: restarting is exactly the event startup reconciliation exists to clean up
#: after. Half an hour is generous for a human-paced review session (the longest
#: designed wait is a 45-second long-poll) and short enough that a client which
#: simply went away does not hold anything until the next restart.
MCP_SESSION_IDLE_TIMEOUT_SECONDS: Final[float] = 1800.0

#: Where the client's stylesheet and script are served from.
STATIC_PATH: Final[str] = "/static"


def create_app(services: Services, *, preview_sweep_interval_seconds: int = 0) -> FastAPI:
    """Build the application around already-constructed services.

    They are injected rather than assembled here so that a test can run the real
    application against a scratch catalogue, and so that nothing at import time
    touches the filesystem.

    **Sweeping is off unless a caller asks for it**, and the deployment entry
    point is what asks. A background thread that deletes files is not something a
    test harness should acquire by constructing the application: a suite that
    accepted a work and then read its review card would be racing a reclamation
    it never opted into, and the failure would be intermittent.
    """
    mcp_server = build_server(services)
    session_manager = StreamableHTTPSessionManager(
        app=mcp_server,
        session_idle_timeout=MCP_SESSION_IDLE_TIMEOUT_SECONDS,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # Started before the surface is served and stopped after it is not, so
        # the sweep's whole life is inside the application's. Nothing it does is
        # request-scoped; it simply must not outlive the process that owns the
        # catalogue it reads.
        halt = (
            None
            if preview_sweep_interval_seconds <= 0
            else start_sweeping(services.sweep, interval_seconds=preview_sweep_interval_seconds)
        )
        if halt is None:
            log.info("candidate previews will not be swept; PREVIEW_SWEEP_INTERVAL_SECONDS is 0")
        else:
            log.info("sweeping candidate previews every %ds", preview_sweep_interval_seconds)
        try:
            async with session_manager.run():
                log.info("curation plane ready; MCP server mounted at %s", MCP_PATH)
                yield
        finally:
            if halt is not None:
                halt()

    app = FastAPI(
        title="Curation",
        description="Curation plane for the Samsung Frame art loader.",
        lifespan=lifespan,
    )
    # Read by the HTTP handlers off application state. The services are built
    # once, at startup, over one open catalogue file — a per-request dependency
    # would advertise a lifetime they do not have.
    app.state.services = services

    async def handle_mcp(scope: Scope, receive: Receive, send: Send) -> None:
        await session_manager.handle_request(scope, receive, send)

    app.mount(MCP_PATH, handle_mcp)

    @app.exception_handler(ServiceError)
    async def refused(_: Request, error: ServiceError) -> JSONResponse:
        """Turn a refused operation into the one error shape this surface returns.

        Registered here rather than caught per handler, which is what keeps every
        handler to unpack-call-format. The service layer raises a single type by
        design, so a per-error status table would be this surface inventing a
        taxonomy the layer below it does not have — and the message is already
        written to be shown to whoever asked.
        """
        log.info("refused: %s", error)
        return api.service_error_response(str(error))

    app.include_router(api.router)
    app.include_router(pages.router)
    app.mount(STATIC_PATH, StaticFiles(directory=pages.STATIC_DIR), name="static")

    return app
