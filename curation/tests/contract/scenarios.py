"""Driving the tool surface the way a caller does, and measuring the trip.

The contract tests beside this file assert the surface's *shape* — names,
schemas, descriptions, annotations, tips. This module is for the other half of
the question: whether the five consolidated tools actually compose into the
flows the product exists for. Shape can be perfect while the flow is broken,
because two tools can each be correct and still disagree about the name of the
thing they hand each other.

**Steps thread values out of one envelope into the next, deliberately.** A flow
whose every argument is a literal proves each tool works alone, which the unit
suite already proves. Passing an id the *previous call actually returned* is
what fails when `create` names it one thing and `add` expects another — and
that defect is invisible from inside either tool's own tests.

The measurement is shared on purpose. A scenario driven by `Caller` and the
same goal pursued by a model produce the same `Transcript`, so the scripted run
is the reference a model is measured against rather than a separate exercise.
What a transcript records — how many calls a goal took and how many failed — is
exactly what says whether a noun-shaped surface with an `action` parameter is
navigable.

**Every call checks two envelope invariants**, so scenario coverage doubles as
coverage of them across the whole surface rather than at the one or two call
sites a unit test happened to look at:

1. The protocol's `isError` agrees with the payload's `success`. `envelope.py`
   derives one from the other precisely so they cannot drift; nothing asserted
   that they hadn't.
2. The JSON text and the `structuredContent` carry the same body. The envelope
   sends the payload out twice so any client can read it, which is only true
   while the two agree.
"""

import json
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

#: The route a competent caller takes to put one work on the wall, and the only
#: place it is written down. The scripted scenario asserts it took exactly this
#: path; the model-driven evaluation sizes its call budget from its length. Two
#: copies of this would drift the moment the flow needs another round trip — and
#: they would drift silently, because each would still be true of its own half.
REFERENCE_ROUTE = (
    "art_catalogue(action='list')",
    "art_theme(action='create')",
    "art_theme(action='add')",
    # Added 2026-08-12, when hanging became an act against a named wall. It is a
    # real extra round trip and it is recorded as one rather than hidden: the
    # wall is a required argument, so a caller that cannot obtain a wall id
    # cannot hang anything, and the surface has to hand it one. That is the cost
    # of the confirmation naming the room, paid once per flow.
    "art_display(action='walls')",
    "art_theme(action='activate')",
)

#: The route a caller takes to spend money responsibly: price the question,
#: commit to it, watch it, then decide. Written down for the same reason the
#: route above is — an extra required round trip is a regression in navigability,
#: and on this tool it is also a regression in how easy it is to spend without
#: looking. `estimate` leads deliberately: an agent has no wallet and no instinct
#: for what is expensive, so the surface has to make pricing the cheap first move
#: rather than a thing a careful caller remembers to do.
DISCOVERY_ROUTE = (
    "art_discovery(action='estimate')",
    "art_discovery(action='start')",
    "art_discovery(action='status')",
    "art_discovery(action='approve')",
)


#: The route a curator takes to see what a run found and judge it. The last two
#: steps are the ones the product's only safety control lives in: `security-model.md`
#: § Content Appropriateness makes "the reviewing surface shows the image" the
#: whole of that control, so a route that reached a verdict without a step
#: returning pictures would be a navigable path to accepting a work sight-unseen.
#: Written down here for the same reason the other routes are — a change that adds
#: a required round trip, or removes the step that carries the images, is a
#: regression this file is what notices.
REVIEW_ROUTE = (
    "art_discovery(action='start')",
    "art_discovery(action='status')",
    "art_review(action='list_works', 2 image(s))",
    "art_review(action='list_images', 1 image(s))",
)


#: The whole of the product's first flow: an intent becomes a work on the
#: catalogue, judged by someone who saw it. It extends `REVIEW_ROUTE` rather
#: than restating it, because the claim that matters is that **acceptance costs
#: one call past the pictures** — a route that reached a verdict by some other
#: path would satisfy a copy of these steps while breaking the one property the
#: review gate has.
#:
#: The last step is the catalogue's, deliberately. Acceptance returns an
#: `artwork_id`, and a flow that ended at the verdict would prove the tool
#: answered rather than that a work arrived where the rest of the product looks
#: for it — which is the difference between a recorded decision and a promotion.
#:
#: One `status` here, because this is the *route* and not the call log: watching
#: a run takes as many polls as it takes. Assert it against `Transcript.route`,
#: which collapses adjacent repeats; against `steps` it is a flake.
ACCEPTANCE_ROUTE = (
    *REVIEW_ROUTE,
    "art_review(action='set_verdict')",
    "art_catalogue(action='get')",
)


@dataclass(frozen=True)
class Call:
    """One tool call and how it landed.

    `images` is the count of image content blocks the result carried, and it is
    recorded rather than discarded because on the review surface it is the whole
    point of the call. A harness that kept only the payload would let a scenario
    assert everything about a review result *except* whether the curator was
    shown anything — and a result with the pictures silently missing is exactly
    what defeats the review gate while looking correct. The count rather than the
    bytes: a transcript is read in failure messages, and forty base64 blobs in one
    would make it unreadable.
    """

    tool: str
    action: str
    succeeded: bool
    payload: dict[str, Any]
    images: int = 0

    def __str__(self) -> str:
        pictures = f", {self.images} image(s)" if self.images else ""
        return f"{self.tool}(action={self.action!r}{pictures})"


@dataclass
class Transcript:
    """Every call a scenario made, in the order it made them."""

    calls: list[Call] = field(default_factory=list)

    @property
    def failures(self) -> list[Call]:
        return [call for call in self.calls if not call.succeeded]

    @property
    def steps(self) -> list[str]:
        """Every call in order — the exact log, polls and all.

        This is what a whole-route assertion should use **whenever the scenario's
        call count is deterministic**, which is most of them: it is the stricter
        check, and it catches a repeated call as readily as an extra distinct
        one. `REFERENCE_ROUTE` and `DISCOVERY_ROUTE` are compared against it for
        that reason and should stay that way.

        Reach for `route` only where a scenario *polls* — waiting on a run makes
        the count a property of the machine rather than of the surface.
        """
        return [str(call) for call in self.calls]

    @property
    def route(self) -> list[str]:
        """The steps with consecutive repeats collapsed — the path, not the log.

        **For scenarios that poll, and only those.** Watching a run until it
        finishes takes as many `status` calls as the machine needs, so a fixed
        route compared against `steps` fails on whichever run is slower. What the
        routes in this module claim is that a goal takes these calls *in this
        order*, and asking the same question twice while waiting is not a change
        to that.

        **What this gives up, stated plainly: a flow that genuinely requires the
        same call twice in a row is indistinguishable from one that requires it
        once.** Folding cannot tell a poll from a needed repetition — nothing in a
        transcript can. So a scenario whose route legitimately contains an
        adjacent duplicate must assert against `steps` and accept that it cannot
        also poll, or assert the duplicate separately. Only *adjacent* repeats
        fold, so a call re-entered after something else is still a second visit.

        The fold is over the rendered step, which carries the image count — so
        two `list_images` calls that returned different numbers of pictures do
        **not** collapse. That is deliberate: the review gate lives in those
        counts, and a fold that ignored them would let a route keep claiming
        pictures arrived after they stopped.
        """
        collapsed: list[str] = []
        for step in self.steps:
            if not collapsed or collapsed[-1] != step:
                collapsed.append(step)
        return collapsed

    def __str__(self) -> str:
        return " -> ".join(self.steps) or "(no calls)"


class ScenarioError(AssertionError):
    """A step failed that the scenario required to succeed.

    An `AssertionError` because that is what a failing step means to the test
    reading it, and it carries the envelope's own error text — which is written
    to teach a caller what to do instead, and reads better than anything this
    module could paraphrase.
    """


class Caller:
    """An MCP client session that records what it did."""

    def __init__(self, session: ClientSession, transcript: Transcript) -> None:
        self._session = session
        self.transcript = transcript

    async def list_tools(self) -> list[Any]:
        """The tool definitions exactly as the server renders them.

        Exposed so a caller that offers this surface to a model hands over what
        `list_tools` actually returns. A harness that rebuilt the definitions
        would measure its own copy, and a description edit — the drift the
        evaluation exists to catch — would never reach it.
        """
        listed = await self._session.list_tools()
        return list(listed.tools)

    async def call(self, tool: str, action: str, **arguments: Any) -> dict[str, Any]:
        """Call one action and record it. A failed call is returned, not raised.

        Failures come back so a scenario can assert *about* one — that a bad
        action teaches, that an unbuilt tool says so. Use `ok` for the steps a
        scenario needs to have worked.
        """
        return await self.invoke(tool, {"action": action, **arguments})

    async def invoke(self, tool: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        """Call a tool with an argument mapping exactly as given.

        The entry point for arguments this module did not compose — a model's,
        in the evaluation suite, which may omit `action` entirely or send it
        with the wrong type. Those are results worth measuring rather than
        errors worth raising, and they reach the server unaltered.
        """
        result = await self._session.call_tool(tool, dict(arguments))
        action = arguments.get("action")
        action = action if isinstance(action, str) else f"<{'missing' if action is None else 'not-a-string'}>"

        structured = result.structuredContent
        assert structured is not None, f"{tool}(action={action!r}) returned no structuredContent"

        # The same body goes out as JSON text for clients that do not read
        # structured content. It is only two representations of one payload
        # while they agree.
        text = json.loads("".join(block.text for block in result.content if block.type == "text"))
        assert text == structured, f"{tool}(action={action!r}) sent different text and structured bodies"

        succeeded = structured.get("success") is True
        assert result.isError is not succeeded, (
            f"{tool}(action={action!r}) reported isError={result.isError} "
            f"with success={structured.get('success')!r}; the envelope derives one from the other"
        )

        pictures = sum(1 for block in result.content if block.type == "image")
        self.transcript.calls.append(Call(tool, action, succeeded, structured, images=pictures))
        return structured

    async def ok(self, tool: str, action: str, **arguments: Any) -> dict[str, Any]:
        """Call one action that the scenario requires to succeed."""
        payload = await self.call(tool, action, **arguments)
        if payload.get("success") is not True:
            raise ScenarioError(
                f"{tool}(action={action!r}) failed: {payload.get('error')}\n"
                f"  hint: {payload.get('hint')}\n"
                f"  after: {self.transcript}"
            )
        return payload


@asynccontextmanager
async def connect(server_url: str) -> AsyncIterator[Caller]:
    """A real MCP client against a real server, with a fresh transcript."""
    async with streamable_http_client(f"{server_url}/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield Caller(session, Transcript())
