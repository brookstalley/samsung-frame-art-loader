"""The curation plane's scaffold holds together.

Thin by design: this asserts the toolchain and the pinned surfaces, not product
behaviour. It exists so `uv run pytest` is meaningful from the day the project
is created rather than from the day the first feature lands.
"""

import sys


def test_runs_on_the_pinned_interpreter():
    """3.14 is a hard floor, and the reason is no longer the one it was.

    It was `3tears` core, which this plane no longer depends on at all. What
    holds the floor now is `3tears-models` — the operator's own model adapters,
    which the discovery work calls and which declare the same floor — together
    with the verification that the whole curation dependency set resolves and
    imports on CPython 3.14.4. The interpreter is a uv-managed standalone build,
    deliberately not the system 3.13.
    """
    assert sys.version_info >= (3, 14)


def test_the_package_layout_imports():
    import curation
    from curation import acquisition, discovery, http, manifest, mcp, persistence, services

    assert curation.__all__ == []
    # The module boundaries the architecture makes load-bearing exist as real
    # packages from the start, so nothing later has to invent them mid-chunk.
    for module in (services, persistence, mcp, http, discovery, acquisition, manifest):
        assert module.__doc__


def test_the_mcp_sdk_exposes_the_server_surface_the_plan_assumes():
    """Chunk 07 mounts a streamable-HTTP MCP server inside the FastAPI app.

    The known hazard is that Starlette does not run a mounted sub-app's
    lifespan, so the host app must drive `session_manager.run()` itself. That
    only works if these names exist — pin them now so an SDK bump that moves
    them fails here rather than at request time.
    """
    from mcp.server.lowlevel import Server
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

    assert hasattr(Server, "list_tools")
    assert hasattr(Server, "call_tool")
    assert hasattr(StreamableHTTPSessionManager, "run")
    assert hasattr(StreamableHTTPSessionManager, "handle_request")
