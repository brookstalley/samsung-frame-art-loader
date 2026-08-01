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

_THEME_ID = Param(
    name="theme_id",
    type="string",
    description="The theme's id, as returned by action='list'.",
    required=True,
)

_POSITION = Param(
    name="position",
    type="integer",
    description="Where the work sits in the theme's order. Omit to leave it unplaced, which sorts after placed works.",
    minimum=0,
)

ART_THEME: Final = ToolRecord(
    name="art_theme",
    title="Art themes",
    summary="Group works into themes and choose which one the wall is showing.",
    read_only=False,
    destructive=True,
    open_world=False,
    actions=(
        Action(
            name="list",
            description="Return every theme, with which one is active.",
            example="art_theme(action='list')",
            tips=("Exactly one theme is active whenever any theme exists; that is the one the wall syncs from.",),
        ),
        Action(
            name="get",
            description="Return one theme and the works in it, in curated order.",
            example="art_theme(action='get', theme_id='<a theme_id from action=list>')",
            params=(_THEME_ID,),
            tips=(
                "Membership is curatorial, not technical: a work can be in a theme and still not be displayable. "
                "Use art_display(action='sync') to see which members would actually reach the wall, and why not.",
            ),
        ),
        Action(
            name="create",
            description="Create a theme. It becomes active if no other theme currently is.",
            example="art_theme(action='create', name='American Modernists')",
            params=(
                Param(name="name", type="string", description="What to call the theme. Must be unique.", required=True),
                Param(name="description", type="string", description="Optional note about what the theme is for."),
            ),
        ),
        Action(
            name="update",
            description="Change a theme's name, description, or rotation settings. Omitted fields are left alone.",
            example="art_theme(action='update', theme_id='<a theme_id>', rotation_interval_seconds=600)",
            params=(
                _THEME_ID,
                Param(name="name", type="string", description="A new name for the theme."),
                Param(name="description", type="string", description="A new description."),
                Param(
                    name="rotation_interval_seconds",
                    type="integer",
                    description="How long each work is shown in this theme. Omit to leave unchanged.",
                    minimum=1,
                ),
                Param(
                    name="shuffle",
                    type="boolean",
                    description="Show this theme in random order rather than curated order.",
                ),
            ),
            tips=(
                "A theme that has never set an interval or shuffle inherits the deployment default, "
                "which is what art_display(action='sync') reports.",
            ),
        ),
        Action(
            name="delete",
            description="Delete a theme. The works in it are untouched.",
            example="art_theme(action='delete', theme_id='<a theme_id>')",
            params=(_THEME_ID,),
            tips=(
                "The active theme is refused while another exists — activate the one that should replace it first, "
                "so what lands on the wall is a choice.",
            ),
        ),
        Action(
            name="add",
            description="Put a work into a theme.",
            example="art_theme(action='add', theme_id='<a theme_id>', artwork_id='<an artwork_id>', position=0)",
            params=(
                _THEME_ID,
                Param(
                    name="artwork_id",
                    type="string",
                    description="The work to add, as returned by art_catalogue(action='list').",
                    required=True,
                ),
                _POSITION,
            ),
        ),
        Action(
            name="remove",
            description="Take a work out of a theme. The work itself is untouched.",
            example="art_theme(action='remove', theme_id='<a theme_id>', artwork_id='<an artwork_id>')",
            params=(
                _THEME_ID,
                Param(name="artwork_id", type="string", description="The work to remove.", required=True),
            ),
        ),
        Action(
            name="reorder",
            description="Move a work within a theme, or return it to unplaced.",
            example="art_theme(action='reorder', theme_id='<a theme_id>', artwork_id='<an artwork_id>', position=3)",
            params=(
                _THEME_ID,
                Param(name="artwork_id", type="string", description="The work to move.", required=True),
                _POSITION,
            ),
        ),
        Action(
            name="activate",
            description="Make this the theme the wall shows, and the only one.",
            example="art_theme(action='activate', theme_id='<a theme_id>')",
            params=(_THEME_ID,),
            tips=(
                "This changes which theme is active. It does not itself rewrite the manifest — "
                "call art_display(action='sync') to publish it to the wall.",
            ),
        ),
    ),
)

_SYNC_THEME_ID = Param(
    name="theme_id",
    type="string",
    description="Which theme to publish. Omit to publish the active one, which is the usual case.",
)

ART_DISPLAY: Final = ToolRecord(
    name="art_display",
    title="Art display",
    summary="Report what the wall is doing and ask it to change. Every action writes desired state, never a command.",
    read_only=False,
    destructive=False,
    open_world=False,
    actions=(
        Action(
            name="status",
            description="Report what the display plane last said about itself, and how long ago.",
            example="art_display(action='status')",
            tips=(
                "This reports an observation and its age in seconds, never a verdict about health. "
                "If the display plane has never run, it says so plainly rather than reporting a zero.",
            ),
        ),
        Action(
            name="sync",
            description="Rebuild the theme manifest so the wall converges on the active theme.",
            example="art_display(action='sync')",
            params=(_SYNC_THEME_ID,),
            tips=(
                "The result names every theme member that will NOT be on the wall and why. "
                "A theme can be half-displayable, and this is the only place that says so.",
                "Switching themes costs no television writes: the whole library stays on the TV "
                "and rotation is driven from here.",
            ),
        ),
        Action(
            name="show_now",
            description="Ask the wall to jump to one work and carry on rotating from there.",
            example="art_display(action='show_now', artwork_id='<an artwork_id>')",
            params=(Param(name="artwork_id", type="string", description="The work to jump to.", required=True),),
            tips=(
                "An archived work is refused rather than pinned, because it is out of circulation.",
                "This writes the directive; it does not confirm the television changed.",
            ),
        ),
        Action(
            name="next",
            description="Ask the wall to step to the next work in the current theme.",
            example="art_display(action='next')",
            tips=("Repeated calls inside one poll interval coalesce into a single step — latest wins.",),
        ),
    ),
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
