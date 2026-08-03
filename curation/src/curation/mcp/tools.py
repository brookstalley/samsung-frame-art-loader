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
from curation.persistence.discovery_records import RunKind, RunStatus
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

#: One description for `run_id`, because every action's parameters are flattened
#: onto a single wire schema and only the first description survives. This is the
#: surface's first parameter that is required by some actions and optional to
#: others, so a description written for either case would be published as though
#: it governed both — telling a model that omitting `run_id` prices a new question
#: on the four actions where omitting it is simply an error. What each action does
#: with it belongs in that action's own description and tips, which `help` shows.
_RUN_ID_DESCRIPTION = "A discovery run's id, as returned by action='start' or action='list_runs'."

_RUN_ID = Param(name="run_id", type="string", description=_RUN_ID_DESCRIPTION, required=True)

#: The same parameter where it is optional, and its absence asks a wider question.
_OPTIONAL_RUN_ID = Param(name="run_id", type="string", description=_RUN_ID_DESCRIPTION)

ART_DISCOVERY: Final = ToolRecord(
    name="art_discovery",
    title="Art discovery",
    summary="Propose and resolve new works. The only tool that spends money.",
    read_only=False,
    destructive=True,
    open_world=True,
    actions=(
        Action(
            name="estimate",
            description="Price a discovery run before starting it, or price resolving one that has already found works.",
            example="art_discovery(action='estimate')",
            params=(_OPTIONAL_RUN_ID,),
            tips=(
                "This is the one action on this tool that spends nothing, so an intent can always be priced "
                "before it is committed to.",
                "With no run_id the answer covers phase 1 — one model call and its search allowance. With a "
                "run_id it is that run's stored phase-2 figure, which is what its approval gate authorises against.",
                "Both figures are bounded rather than typical: they price the whole search allowance, because a "
                "number a run may freely exceed is not an estimate.",
            ),
        ),
        Action(
            name="start",
            description="Begin a discovery run from an intent. Returns a handle at once; the work happens behind it.",
            example="art_discovery(action='start', intent='Surrealist paintings with strong blues')",
            params=(
                Param(
                    name="intent",
                    type="string",
                    description="What to look for, in the curator's own words.",
                    required=True,
                ),
            ),
            tips=(
                "This returns immediately with a run_id and does not wait for the run. Poll action='status' "
                "with that id, which holds until something changes rather than answering straight away.",
                "A run that proposes more works than the configured threshold stops and waits for "
                "action='approve' before spending anything on phase 2.",
                "Works the curator has already rejected are skipped rather than proposed again, so a run may "
                "return fewer works than the intent would suggest.",
            ),
        ),
        Action(
            name="status",
            description="Report where a run has got to, holding until that changes if it is still being worked on.",
            example="art_discovery(action='status', run_id='<a run_id from action=start>')",
            params=(_RUN_ID,),
            tips=(
                "The call holds for up to 45 seconds while a run is being worked on, and answers immediately "
                "when it is waiting for you or has ended. Call it again to keep watching.",
                "The state itself says how a run ended: 'completed', 'failed', 'halted_by_budget' (out of "
                "money — stop, do not retry), 'declined', 'cancelled', or 'interrupted' (the process was "
                "restarted underneath it — simply run it again).",
            ),
        ),
        Action(
            name="approve",
            description="Accept a run's work list and its price, letting it proceed to finding images.",
            example="art_discovery(action='approve', run_id='<a run_id awaiting approval>')",
            params=(_RUN_ID,),
            tips=("Only a run in 'awaiting_approval' can be approved; check action='status' first.",),
        ),
        Action(
            name="decline",
            description="Refuse a run's work list. The run ends and phase 2 never spends.",
            example="art_discovery(action='decline', run_id='<a run_id awaiting approval>')",
            params=(_RUN_ID,),
            tips=(
                "Declining is not the same as cancelling: it is a judgement on the work list, and it is "
                "available only while the run is waiting for one.",
            ),
        ),
        Action(
            name="cancel",
            description="Stop a run wherever it has got to. Money already spent stays recorded.",
            example="art_discovery(action='cancel', run_id='<a run_id from action=list_runs>')",
            params=(_RUN_ID,),
            tips=(
                "Available from every state a run can still leave, including while it waits for approval — "
                "wanting a run gone is a different thing from declining what it found.",
                "A run that has already ended cannot be cancelled; the refusal names how it ended.",
            ),
        ),
        Action(
            name="resolve_images",
            description="Look again for images of works whose instances the curator turned down. Returns a handle at once.",
            example="art_discovery(action='resolve_images', work_ids=['<a work_id awaiting a better image>'])",
            params=(
                Param(
                    name="work_ids",
                    type="array",
                    items="string",
                    description="The candidate works to re-search, by id. They must all come from the same discovery run.",
                    required=True,
                ),
            ),
            tips=(
                "This is a run like any other: it returns a run_id, and action='status', action='cancel' and "
                "action='spend' all take it.",
                "A work already being re-searched by a running re-search is refused, and the refusal names it — "
                "submitting the same ids twice would pay twice for one result.",
                "The works must all come from one discovery run, because a re-search hangs its cost on the "
                "intent that proposed them. Start one re-search per originating run.",
                "What this costs rolls up into the originating run's figure, so action='spend' on that run "
                "still answers what asking for it cost altogether.",
                "A verdict you reach while this is running wins: a re-search finishing against a work you have "
                "since accepted or rejected reports what it found and leaves your decision alone.",
            ),
        ),
        Action(
            name="list_runs",
            description="List discovery runs, newest first, optionally narrowed to one state or kind.",
            example="art_discovery(action='list_runs', status='awaiting_approval')",
            params=(
                Param(
                    name="status",
                    type="string",
                    description="Restrict to runs in this state. Omit to list every run.",
                    choices=tuple(member.value for member in RunStatus),
                ),
                Param(
                    name="kind",
                    type="string",
                    description="Restrict to first-time discovery runs or to re-searches. Omit for both.",
                    choices=tuple(member.value for member in RunKind),
                ),
            ),
            tips=("Listings carry the fields needed to choose; use action='status' for one run in full.",),
        ),
        Action(
            name="spend",
            description="Report what one run cost, or what a whole calendar month cost.",
            example="art_discovery(action='spend', run_id='<a run_id>')",
            params=(
                _OPTIONAL_RUN_ID,
                Param(
                    name="year",
                    type="integer",
                    description="Calendar year to report, with month. Omit both for the current month.",
                    minimum=1,
                ),
                Param(
                    name="month",
                    type="integer",
                    description="Calendar month to report, with year. Omit both for the current month.",
                    minimum=1,
                    maximum=12,
                ),
            ),
            tips=(
                "A run's figure includes every re-search descended from it, which is what 'what did asking "
                "for this cost' means once spend is spread across a chain of runs.",
                "Months are UTC calendar months, matching the boundary the provider's own credit limit "
                "resets on. A report on any other boundary would disagree with the figure that can actually "
                "stop spending.",
            ),
        ),
    ),
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
                "This publishes the theme: it rewrites the manifest, so the wall converges on it "
                "within about a second. No separate sync is needed.",
                "The result names every member that will NOT be on the wall and why, exactly as "
                "art_display(action='sync') does — a theme can be half-displayable.",
                "Switching costs no television writes: the whole library stays on the TV and " "rotation is driven from here.",
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
                "Any work that could not reach the wall is refused rather than pinned — archived, "
                "missing its master image, mat colour or television render, or carrying a render "
                "made from an earlier acquisition. The refusal names which, in the same words "
                "art_display(action='sync') uses for an excluded work.",
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
