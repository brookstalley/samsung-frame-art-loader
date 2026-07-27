"""The five tools, declared once.

**All five names are registered from the start, and they never change.** A tool
name is the one part of this surface a client binds to that cannot be evolved
additively, so they are all claimed at once rather than appearing one at a time
and tempting a rename along the way. A tool whose actions have not been built
carries `unavailable_note`: it answers `action='help'` and returns an error
naming what is available for anything else. That is deliberately more useful
than an absent tool, which a client discovers only as a missing name.

**The annotations describe each tool as designed, not as currently built.**
They are part of the frozen surface: a client that auto-approves on
`readOnlyHint` would see a later action landing as a silent change in what it
had already agreed to. Declaring them against the full designed action set
means they are true on the day the last action lands and every day before it.

Nothing in this module contains logic. Each record says what an action is,
what it takes, and what a good call looks like; `bindings.py` says which
service method answers it, and the service method does the work.
"""

from typing import Final

from curation.mcp.registry import Action, Param, ToolRecord
from curation.persistence.records import ArtworkStatus
from curation.services.catalogue import MAX_LIST_LIMIT

_UNBUILT = "Not available yet: this tool answers action='help' and returns an error naming that for anything else."

_STATUS = Param(
    name="status",
    type="string",
    description="Restrict to works in this state. Omit to list the whole catalogue.",
    choices=tuple(member.value for member in ArtworkStatus),
)

_LIMIT = Param(
    name="limit",
    type="integer",
    description=f"How many works to return, 1 to {MAX_LIST_LIMIT}.",
    minimum=1,
    maximum=MAX_LIST_LIMIT,
)

_OFFSET = Param(
    name="offset",
    type="integer",
    description="How many works to skip, for paging through a large result.",
    minimum=0,
)

ART_CATALOGUE: Final = ToolRecord(
    name="art_catalogue",
    title="Art catalogue",
    summary="Read and manage the works already accepted into the collection.",
    read_only=False,
    destructive=False,
    open_world=False,
    actions=(
        Action(
            name="list",
            description="Page through catalogued works, optionally filtered by status.",
            example="art_catalogue(action='list', status='accepted', limit=20)",
            params=(_STATUS, _LIMIT, _OFFSET),
            tips=(
                "A truncated result says so and reports the total, so a short list is never mistaken for a complete one.",
                "Listings carry the fields needed to choose; use action='get' for the whole record.",
            ),
        ),
        Action(
            name="get",
            description="Return one work in full, with its artist resolved.",
            example="art_catalogue(action='get', artwork_id='<an artwork_id from action=list>')",
            params=(
                Param(
                    name="artwork_id",
                    type="string",
                    description="The work's catalogue id, as returned by action='list'.",
                    required=True,
                ),
            ),
            tips=("Ids are stable internal identities, never source URLs, so they survive a museum reorganising its site.",),
        ),
    ),
)

ART_DISCOVERY: Final = ToolRecord(
    name="art_discovery",
    title="Art discovery",
    summary="Propose and resolve new works. The only tool that spends money.",
    read_only=False,
    destructive=True,
    open_world=True,
    unavailable_note=_UNBUILT,
)

ART_REVIEW: Final = ToolRecord(
    name="art_review",
    title="Art review",
    summary="Show candidate works and images for a curator to judge, and record the verdict. Never spends.",
    read_only=False,
    destructive=True,
    open_world=False,
    unavailable_note=_UNBUILT,
)

ART_THEME: Final = ToolRecord(
    name="art_theme",
    title="Art themes",
    summary="Group works into themes and choose which one the wall is showing.",
    read_only=False,
    destructive=True,
    open_world=False,
    unavailable_note=_UNBUILT,
)

ART_DISPLAY: Final = ToolRecord(
    name="art_display",
    title="Art display",
    summary="Report what the wall is doing and ask it to change. Every action writes desired state, never a command.",
    read_only=False,
    destructive=False,
    open_world=False,
    unavailable_note=_UNBUILT,
)

#: Registration order, which is the order a client sees. Money first, then the
#: gate that money runs through, then the collection it lands in.
TOOLS: Final[tuple[ToolRecord, ...]] = (
    ART_DISCOVERY,
    ART_REVIEW,
    ART_CATALOGUE,
    ART_THEME,
    ART_DISPLAY,
)

TOOLS_BY_NAME: Final[dict[str, ToolRecord]] = {tool.name: tool for tool in TOOLS}
