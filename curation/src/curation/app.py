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

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.types import Receive, Scope, Send

from curation.mcp.server import build_server
from curation.services.catalogue import CatalogueService

log = logging.getLogger(__name__)

#: Where MCP clients connect. Frozen with the tool names — a client's server
#: config carries this URL.
MCP_PATH: Final[str] = "/mcp"

_PLACEHOLDER_PAGE: Final[str] = """<!doctype html>
<title>Curation</title>
<style>
  body { font: 16px/1.6 system-ui, sans-serif; margin: 4rem auto; max-width: 34rem; padding: 0 1rem; }
  code { background: #eee; padding: 0.1rem 0.3rem; border-radius: 3px; }
</style>
<h1>Curation</h1>
<p>The curation plane is running. The browser interface is not built yet.</p>
<p>The MCP server is live at <code>/mcp</code>; point a client there.</p>
"""


def create_app(service: CatalogueService) -> FastAPI:
    """Build the application around an already-constructed service.

    The service is injected rather than assembled here so that a test can run
    the real application against a scratch catalogue, and so that nothing at
    import time touches the filesystem.
    """
    mcp_server = build_server(service)
    session_manager = StreamableHTTPSessionManager(app=mcp_server)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        async with session_manager.run():
            log.info("curation plane ready; MCP server mounted at %s", MCP_PATH)
            yield

    app = FastAPI(
        title="Curation",
        description="Curation plane for the Samsung Frame art loader.",
        lifespan=lifespan,
    )

    async def handle_mcp(scope: Scope, receive: Receive, send: Send) -> None:
        await session_manager.handle_request(scope, receive, send)

    app.mount(MCP_PATH, handle_mcp)

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return _PLACEHOLDER_PAGE

    return app
