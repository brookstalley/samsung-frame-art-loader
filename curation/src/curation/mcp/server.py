"""The MCP server: generated tool definitions and one generic dispatcher.

There is no per-tool code here. `list_tools` renders every registry record
through the same generator, and `dispatch` resolves the action, validates the
arguments, and calls whatever `bindings.py` bound to it. A branch on a tool
name in this module would be the first crack in the guarantee that the wire
schema, the validation, `help`, and the error messages all come from one
record.
"""

import asyncio
import logging
from collections.abc import Mapping
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Final

import mcp.types as types
from mcp.server.lowlevel import Server

from curation.mcp import registry
from curation.mcp.bindings import BINDINGS
from curation.mcp.envelope import failure, ok, to_call_tool_result
from curation.mcp.registry import HELP_ACTION, ArgumentError
from curation.mcp.tools import TOOLS, TOOLS_BY_NAME
from curation.services.container import Services
from curation.services.errors import ServiceError

log = logging.getLogger(__name__)

SERVER_NAME: Final[str] = "samsung-frame-art-loader"


def _server_version() -> str:
    """This server's version, not the SDK's.

    Left unset, the SDK reports its own version as the server's, so a client
    asking what it is talking to is told which protocol library is installed.
    """
    try:
        return version("curation")
    except PackageNotFoundError:  # running from a source tree with nothing installed
        return "0.0.0+unknown"


#: Shown to a client once, alongside the tool list. Kept short deliberately:
#: the client truncates server instructions at the same 2 KB it truncates a
#: tool description, and the depth belongs behind each tool's `help`.
INSTRUCTIONS: Final[str] = (
    "Curate a Samsung Frame TV's art collection. Five tools, each a noun taking a required "
    "'action' string. Every tool answers action='help' with its full action menu, parameters, "
    "a worked example, and tips — start there. art_discovery is the only tool that spends money. "
    "Adding a work to the wall always passes through a human review step, so an agent stages "
    "changes rather than completing them."
)


def tool_definitions() -> list[types.Tool]:
    """Every tool, generated from its record."""
    return [
        types.Tool(
            name=tool.name,
            title=tool.title,
            description=registry.description(tool),
            inputSchema=registry.input_schema(tool),
            annotations=types.ToolAnnotations(
                title=tool.title,
                readOnlyHint=tool.read_only,
                destructiveHint=tool.destructive,
                openWorldHint=tool.open_world,
            ),
        )
        for tool in TOOLS
    ]


def dispatch(services: Services, tool_name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Resolve one tool call to a result payload.

    Returns a payload rather than a wire result so that the envelope's
    `isError` is derived from it in exactly one place.
    """
    tool = TOOLS_BY_NAME.get(tool_name)
    if tool is None:
        # The contract calls for a protocol error here, on the reasoning that
        # the client addressed something that does not exist. The SDK cannot
        # carry one: its `call_tool` request handler catches every exception
        # unconditionally and converts it to a normal error result, so no
        # exception survives that boundary. The substitute enumerates the real
        # tool names, which is what a caller needs either way.
        return failure(
            f"Unknown tool: {tool_name!r}",
            tool=SERVER_NAME,
            enumeration={"valid_tools": [known.name for known in TOOLS]},
            # No tool was identified, so the default hint would name the
            # server — which is not callable. Point at the enumerated names
            # instead, so following the hint reaches a tool that exists.
            hint="Call one of the names in valid_tools with action='help' to see what it does.",
        )

    try:
        action = registry.resolve_action(tool, arguments)
        validated = registry.validate(tool, action, arguments)
    except ArgumentError as exc:
        return failure(exc.message, tool=tool.name, example=exc.example, enumeration=exc.enumeration)

    if action.name == HELP_ACTION:
        return ok(**registry.help_payload(tool))

    binding = BINDINGS.get((tool.name, action.name))
    if binding is None:
        # Unreachable today, and kept deliberately. `bindings.py` refuses at
        # import to let a declared action go unbound, so a mismatch stops the
        # process before it serves anything — which is the right failure for a
        # defect the whole surface shares. This branch is what stands behind that
        # check if the registry ever becomes something assembled at runtime, and
        # it fails the one call rather than the process. Untested on purpose:
        # a test would have to defeat the import check to reach it.
        log.error("No binding for %s(action=%r); the registry and bindings disagree.", tool.name, action.name)
        return failure(
            f"{tool.name}(action={action.name!r}) is declared but not wired up. This is a defect, not a usage error.",
            tool=tool.name,
            example=action.example,
            enumeration={"valid_actions": sorted(name for known, name in BINDINGS if known == tool.name)},
        )

    try:
        return binding(services, validated)
    except ServiceError as exc:
        return failure(str(exc), tool=tool.name, example=action.example)
    except Exception:  # prawduct:allow prawduct/broad-except -- tool boundary: a fault must surface as failure, never success
        # The trace goes to the journal; the caller gets a message it can act
        # on. Shipping the exception text would leak internals and tell a model
        # nothing useful.
        log.exception("%s(action=%r) failed unexpectedly.", tool.name, action.name)
        return failure(
            f"{tool.name}(action={action.name!r}) failed unexpectedly. The server log has the details.",
            tool=tool.name,
            example=action.example,
        )


def build_server(services: Services) -> Server:
    """Wire the registry and the services onto an MCP server."""
    server: Server = Server(SERVER_NAME, version=_server_version(), instructions=INSTRUCTIONS)

    @server.list_tools()
    async def _list_tools() -> list[types.Tool]:
        return tool_definitions()

    # Input validation is the registry's, not the SDK's. The SDK would check
    # the flattened schema and report a bare jsonschema message, which names
    # neither the valid set nor a correct call — two validators, one of which
    # does not teach.
    @server.call_tool(validate_input=False)
    async def _call_tool(name: str, arguments: dict[str, Any]) -> types.CallToolResult:
        # Dispatched on a worker thread, never on the event loop. The service
        # layer is synchronous by design, and one of its calls deliberately
        # holds for up to 45 seconds waiting for a run to change — on the loop
        # that would stop every other request in the process, the browser
        # surface included, for the length of the hold. The browser surface
        # already reaches the same services this way, because Starlette runs a
        # synchronous endpoint in a worker thread; the catalogue is built for
        # it, holding one connection behind a reentrant lock.
        return to_call_tool_result(await asyncio.to_thread(dispatch, services, name, arguments))

    return server
