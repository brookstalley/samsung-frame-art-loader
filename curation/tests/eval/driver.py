"""The tool loop: a model on one end, the real MCP surface on the other.

Nothing here is a mock. The tools the model is offered are the ones
`list_tools` renders from the registry — the same descriptions, the same
schemas, byte for byte — and every call it makes goes over HTTP to a running
server and through the real service layer. That is the whole point: a harness
that reconstructed the tool definitions would be measuring its own copy, and a
description edit, which is the drift this is most needed for, would not reach
it.

Execution goes through the contract suite's `Caller`, so a model-driven run and
a scripted one produce the same `Transcript` and the same envelope invariant
checks. The reference route the scripted flow takes is the yardstick a model's
route is compared against.
"""

import json
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from mcp.shared.exceptions import McpError

# The contract suite's runner. Its directory is on `sys.path` under pytest's
# default import mode, but only once something in it has been collected, and
# collection order is not something to rest on.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "contract"))

from scenarios import REFERENCE_ROUTE, Call, Transcript, connect  # noqa: E402

#: What the scripted flow takes to put a work on the wall, derived from the one
#: place that route is written rather than counted here. If the flow ever needs
#: another round trip the model's allowance follows it, instead of silently
#: tightening while both numbers stay individually true.
REFERENCE_CALLS = len(REFERENCE_ROUTE)

#: Deliberately thin. The surface is supposed to explain itself — the server's
#: own instructions tell a client to start at `help`, and every error teaches.
#: A system prompt that coached the model through the five tools would be
#: measuring the prompt instead of the surface.
SYSTEM = (
    "You are helping a curator manage the art shown on a Samsung Frame television. "
    "Use the available tools to accomplish what is asked, then state plainly what you did "
    "or what you found. If a tool call fails, read the error — it lists what is valid."
)


@dataclass
class Outcome:
    """What a driven run produced, and what it cost to get there."""

    transcript: Transcript
    answer: str
    stopped_on_budget: bool

    @property
    def answered(self) -> bool:
        return bool(self.answer.strip())

    def __str__(self) -> str:
        parts = [
            f"{len(self.transcript.calls)} calls ({len(self.transcript.failures)} failed)",
            f"route: {self.transcript}",
        ]
        if self.stopped_on_budget:
            parts.append("STOPPED: exhausted the call budget")
        if self.answered:
            parts.append(f"answer: {self.answer[:400]}")
        return "\n  ".join(["", *parts])


def _as_openai_tool(tool: Any) -> dict[str, Any]:
    """One MCP tool definition in the shape `bind_tools` accepts.

    A translation of the envelope only — name, description and schema are
    passed through untouched, so what the model reads is what the registry
    rendered.
    """
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.inputSchema,
        },
    }


async def drive(server_url: str, model: Any, *, goal: str, budget: int) -> Outcome:
    """Give a model the live tool surface and a goal; run until it stops.

    `budget` caps tool calls, not turns. A model that loops — the failure this
    guards against, and one a confusing surface provokes — stops at the cap and
    the run is reported as budget-exhausted rather than hanging.
    """
    async with connect(server_url) as caller:
        bound = model.bind_tools([_as_openai_tool(tool) for tool in await caller.list_tools()])

        messages: list[Any] = [SystemMessage(SYSTEM), HumanMessage(goal)]
        stopped_on_budget = False

        while True:
            reply: AIMessage = await bound.ainvoke(messages)
            messages.append(reply)

            if not reply.tool_calls:
                break

            if len(caller.transcript.calls) + len(reply.tool_calls) > budget:
                stopped_on_budget = True
                break

            for request in reply.tool_calls:
                payload = await _execute(caller, request)
                messages.append(
                    ToolMessage(
                        content=json.dumps(payload, default=str),
                        tool_call_id=request["id"],
                    )
                )

        return Outcome(
            transcript=caller.transcript,
            answer=_text_of(reply),
            stopped_on_budget=stopped_on_budget,
        )


async def _execute(caller: Any, request: Mapping[str, Any]) -> dict[str, Any]:
    """Run one requested call, turning a rejected tool name into a readable result.

    A model naming a tool that does not exist is a navigation failure worth
    measuring, not an exception worth raising — and the surface already answers
    an unknown *action* with a teaching error, so the unknown-*tool* case is
    given the same shape rather than crashing the run.
    """
    arguments = request.get("args") or {}
    try:
        return await caller.invoke(request["name"], arguments)
    except McpError as exc:
        # Narrow on purpose. `invoke` asserts the envelope invariants, and a
        # broad catch here would turn a real contract violation into "the model
        # made a bad call" — hiding the finding inside the measurement.
        payload = {"success": False, "error": f"{type(exc).__name__}: {exc}"}
        caller.transcript.calls.append(Call(request["name"], "<rejected>", False, payload))
        return payload


def _text_of(reply: AIMessage) -> str:
    """The model's final text, across the shapes providers return it in."""
    content = reply.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(block.get("text", "") for block in content if isinstance(block, dict))
    return str(content)
