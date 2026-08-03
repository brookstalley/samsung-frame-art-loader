"""The curation plane's scaffold holds together.

Thin by design: this asserts the toolchain and the pinned surfaces, not product
behaviour. It exists so `uv run pytest` is meaningful from the day the project
is created rather than from the day the first feature lands.
"""

import sys


def test_runs_on_the_pinned_interpreter():
    """3.14 is the declared floor; this asserts we are actually on it.

    What *holds* that floor has been re-based twice and is deliberately not
    restated here — `project-preferences.md` § Language & Runtime is its one
    canonical home. This docstring named `3tears` core, then `3tears-models`
    "which the discovery work calls", and was still saying the second after that
    package became a test-only dependency, which is how a docstring in the suite
    ends up teaching a retired claim to everyone who reads it.

    The assertion below is worth keeping regardless of the rationale: it fails
    loudly if the interpreter is the system 3.13 rather than the uv-managed
    standalone build, which is a real and easy misconfiguration on the Pi.
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


def test_the_mcp_sdk_exposes_the_server_surface_the_app_drives_itself():
    """The curation app mounts a streamable-HTTP MCP server inside FastAPI.

    The known hazard is that Starlette does not run a mounted sub-app's
    lifespan, so the host app must drive `session_manager.run()` itself. That
    only works if these names exist — pinned here so an SDK bump that moves
    them fails on this line rather than on every request.
    """
    from mcp.server.lowlevel import Server
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

    assert hasattr(Server, "list_tools")
    assert hasattr(Server, "call_tool")
    assert hasattr(StreamableHTTPSessionManager, "run")
    assert hasattr(StreamableHTTPSessionManager, "handle_request")
