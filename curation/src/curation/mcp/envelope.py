"""The result envelope, and the one rule that keeps it honest.

**`isError` is derived from the payload, never set by hand.** A result is an
error **unless** its `success` field is boolean `true` — the negative, matching
`is_error()` below. The two readings differ on exactly one payload, the one with
no `success` key at all, and only the negative fails closed on it. A flag set
separately at each call site drifts from the body it is supposed to describe,
and the drift is invisible: the payload says the operation failed and the
protocol says it succeeded, so a model believes the wrong one. Deriving it
makes the two unable to disagree.

Errors are returned as tool results rather than protocol errors, because a
known tool failing is information a model can act on — the specification is
explicit that execution errors should carry feedback a model can self-correct
from, and clients feed them back to the model.

Every error carries four things: what was wrong, the enumerated valid set, a
correct example, and a pointer to `help`. There are no nearest-match
suggestions; enumerating the whole valid set is more useful to a model than one
guess, and it cannot mislead.
"""

import json
from collections.abc import Mapping
from typing import Any

import mcp.types as types


def ok(**fields: object) -> dict[str, Any]:
    """A successful result. `success` leads so the envelope reads at a glance."""
    return {"success": True, **fields}


def failure(
    error: str,
    *,
    tool: str,
    example: str | None = None,
    enumeration: Mapping[str, Any] | None = None,
    hint: str | None = None,
) -> dict[str, Any]:
    """A failed result that teaches.

    `example` is a correct call, not a correction of the caller's — there is
    no guess at what they meant.

    `hint` overrides the default pointer at this tool's `help`. It exists for
    the one error raised before any tool is identified: there, the default
    would name the server, and a model following it would call a tool that
    does not exist — turning the teaching element into a second failure.
    """
    payload: dict[str, Any] = {"success": False, "error": error}
    payload.update(enumeration or {})
    if example is not None:
        payload["example"] = example
    payload["hint"] = hint or f"Use {tool}(action='help') to see all actions with their parameters."
    return payload


def is_error(payload: Mapping[str, Any]) -> bool:
    """True unless the payload reports success.

    Phrased as the negative on purpose. For any payload this surface produces
    the two readings agree — `ok()` and `failure()` always set a boolean — so
    the difference only shows on a malformed one, and there it fails closed. A
    payload with no `success` field at all is a defect, and reporting a defect
    as a success is this codebase's existing failure shape: `upload_file`
    catches every exception, records a null content id, and returns having set
    success to true.
    """
    return payload.get("success") is not True


def to_call_tool_result(payload: Mapping[str, Any]) -> types.CallToolResult:
    """Wrap a payload for the wire, with `isError` derived from it.

    The payload goes out twice on purpose: as JSON text, which every client
    can read, and as `structuredContent`, which clients that understand it can
    consume without parsing.
    """
    body = dict(payload)
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=json.dumps(body, indent=2, default=str))],
        structuredContent=body,
        isError=is_error(body),
    )
