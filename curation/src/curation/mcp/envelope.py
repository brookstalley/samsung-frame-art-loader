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
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

import mcp.types as types

#: Where a binding leaves the pictures its result carries. **Private, and
#: stripped before anything is serialised** — base64 image data must reach the
#: wire as image content blocks and nowhere else. In the JSON text it would be
#: unreadable to a model and would cost the payload's whole token budget twice
#: over; in `structuredContent` it would do the same to clients that parse it.
#:
#: A reserved key rather than a second return type, because every binding is a
#: `Mapping -> dict` and widening that signature for the three actions that
#: return pictures would change all twenty-seven. The leading underscore marks
#: it as not-for-callers, and `to_call_tool_result` is the single place that
#: knows the name.
IMAGE_BLOCKS: Final[str] = "_image_blocks"


@dataclass(frozen=True, slots=True)
class ImageBlock:
    """One picture travelling beside a result.

    Deliberately not a service type. The wire layer knowing about
    `InlinePreview` would make the envelope depend on the preview cache, and the
    envelope is the one module in this package that has no business knowing what
    the product stores.
    """

    data: str
    media_type: str


def ok(**fields: object) -> dict[str, Any]:
    """A successful result. `success` leads so the envelope reads at a glance."""
    return {"success": True, **fields}


def with_images(payload: dict[str, Any], images: Sequence[ImageBlock]) -> dict[str, Any]:
    """Attach pictures to a result, to be emitted as image content blocks.

    **Nothing correlates a block with a row except its position**, because the
    protocol gives an image block no identity to key on. So a payload using this
    owes its caller the mapping in words: the rows it describes must be listed in
    the same order as the blocks, and must say so. `bindings.py` states it in
    every notice that carries pictures.
    """
    return {**payload, IMAGE_BLOCKS: list(images)}


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

    Pictures go out once, as image content blocks after the text. They are
    removed from the body first, so neither copy of the payload carries base64 —
    this is the only place that name is known, which is what makes "the data
    never reaches the JSON" a property of one function rather than a rule every
    binding has to remember.

    The text block leads. A model reads the rows and then the pictures they
    describe, in the same order, which is the only correlation the protocol
    offers.
    """
    body = dict(payload)
    images: Sequence[ImageBlock] = body.pop(IMAGE_BLOCKS, ())
    return types.CallToolResult(
        content=[
            types.TextContent(type="text", text=json.dumps(body, indent=2, default=str)),
            *(types.ImageContent(type="image", data=image.data, mimeType=image.media_type) for image in images),
        ],
        structuredContent=body,
        isError=is_error(body),
    )
