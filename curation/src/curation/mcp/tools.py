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
from curation.services.review import MAX_REVIEW_LIMIT

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

#: One description for `artwork_id`, because every action's parameters flatten
#: onto a single wire schema and only the first description survives.
_ARTWORK_ID = Param(
    name="artwork_id",
    type="string",
    description="The work's catalogue id, as returned by action='list'.",
    required=True,
)

_SOURCE_ID = Param(
    name="source_id",
    type="string",
    description="Which source to fetch from, as returned by action='sources'. Omit to use the work's primary source.",
)

#: Optional, and its absence is what asks the model. Stated in the description
#: because the parameter's presence changes what the action *costs*, and a caller
#: reading only the schema would have no way to know that omitting it spends
#: money — the one thing on this tool that does.
_HEX_RGB = Param(
    name="hex_rgb",
    type="string",
    description=(
        "The mat colour as a hex triplet, e.g. '#27285b'. Omit it to have the vision model choose one, which "
        "spends a fraction of a cent. (action='regenerate' also chooses one, and pays, for a work that has "
        "never had a mat; both actions report cost_usd.)"
    ),
)

_FORCE = Param(
    name="force",
    type="boolean",
    description="Re-render even if the work's canvas is already current. Defaults to false.",
)

ART_CATALOGUE: Final = ToolRecord(
    name="art_catalogue",
    title="Art catalogue",
    summary=(
        "Read and manage the works already accepted into the collection. Two actions reach outside the machine: "
        "retry_acquisition fetches from a museum, and set_mat_color asks a vision model when given no colour."
    ),
    read_only=False,
    destructive=False,
    #: **True, and it was wrong before.** This is published to clients as
    #: `openWorldHint`, which is how a client decides whether a call warrants
    #: confirmation. Two actions here reach the internet — `retry_acquisition`
    #: fetches a museum URL, and `set_mat_color` without a colour calls a vision
    #: model — so declaring a closed world understated both to every client that
    #: reads the hint. The flag is per *tool*, not per action, so a tool holding
    #: one open-world action is an open-world tool; the alternative is splitting
    #: them out, which `api-contract.md` weighs and rejects for the surface size
    #: this product has.
    open_world=True,
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
            params=(_ARTWORK_ID,),
            tips=("Ids are stable internal identities, never source URLs, so they survive a museum reorganising its site.",),
        ),
        Action(
            name="sources",
            description="List where a work can be obtained from, with rights, primacy and the last fetch's outcome.",
            example="art_catalogue(action='sources', artwork_id='<an artwork_id from action=list>')",
            params=(_ARTWORK_ID,),
            tips=(
                "The primary source is the one that produced the image the work holds.",
                "rights_status is provenance, not permission: it gates nothing and is recorded as the source stated it.",
                "last_fetch_status='partial_tiles' is a normal outcome, not an error — the image exists and has gaps.",
            ),
        ),
        Action(
            name="archive",
            description="Take a work out of circulation, keeping its record, its sources and its mat history.",
            example="art_catalogue(action='archive', artwork_id='<an artwork_id from action=list>')",
            params=(_ARTWORK_ID,),
            tips=(
                "Nothing is deleted and action='restore' reverses it exactly.",
                "A standing pin naming the work is withdrawn, because the wall could never carry it out.",
            ),
        ),
        Action(
            name="restore",
            description="Return an archived work to circulation.",
            example="art_catalogue(action='restore', artwork_id='<an artwork_id from action=list, status=archived>')",
            params=(_ARTWORK_ID,),
            tips=("Renditions made before it was archived are checked against the held image and regenerated if stale.",),
        ),
        Action(
            name="retry_acquisition",
            description="Fetch the work's master image again from one of its sources.",
            example="art_catalogue(action='retry_acquisition', artwork_id='<an artwork_id from action=list>')",
            params=(_ARTWORK_ID, _SOURCE_ID),
            tips=(
                "Use it after a failed or partial fetch; action='sources' shows which, and what went wrong last time.",
                "Omitting source_id uses the work's primary source.",
                "Retrying cannot cost the work its image: an attempt that fails replaces nothing, and one that "
                "comes back with missing tiles is refused outright when the work already holds a complete image.",
            ),
        ),
        Action(
            name="set_mat_color",
            description="Set the mat colour a work is shown against, or ask the vision model to choose one again.",
            example="art_catalogue(action='set_mat_color', artwork_id='<an artwork_id from action=list>', hex_rgb='#27285b')",
            params=(_ARTWORK_ID, _HEX_RGB),
            tips=(
                "Give hex_rgb to set a colour yourself; omit it to have the vision model choose, which spends "
                "a fraction of a cent.",
                "Nothing is overwritten: the previous colour is kept, so a worse choice can be read back and reversed "
                "by setting the old one again.",
                "The work is re-rendered in the new colour immediately — there is no separate regenerate to remember.",
                "A colour recorded as method='dominant_color_fallback' was derived mechanically because the model "
                "could not be asked or could not be read, not chosen for this work.",
            ),
        ),
        Action(
            name="regenerate",
            description="Re-render a work's television canvas from the image it holds, in the mat colour already in force.",
            example="art_catalogue(action='regenerate', artwork_id='<an artwork_id from action=list>')",
            params=(_ARTWORK_ID, _FORCE),
            tips=(
                "Free for a work that already has a mat colour: the recorded one is reused and no model is asked. "
                "A work that has never had one gets a mat chosen here, which costs a fraction of a cent — every "
                "answer reports cost_usd, so a call that spent nothing says so.",
                "Ordinarily it does only what is needed — a work whose canvas is already current is reported "
                "unchanged rather than re-rendered.",
                "Use force=true after changing the panel geometry or clearing the rendered tree.",
                "A work whose master image is missing from disk is refused rather than rendered blank; "
                "action='retry_acquisition' fetches it again.",
            ),
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
    #: No longer "the only tool that spends money" — `art_catalogue`'s
    #: `set_mat_color` asks a vision model when given no colour. The distinction
    #: that survives is scale, and it is the one a curator needs: a discovery run
    #: is the operation with a budget, an approval gate and a ceiling behind it,
    #: while a mat call is a fraction of a cent against one work.
    summary="Propose and resolve new works. The only tool that spends money in amounts worth authorising.",
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

#: The work a review action is about. Required wherever it appears, so one
#: description governs every use of it and there is no optional-vs-required split
#: to write around, as there is for `run_id` on art_discovery.
_WORK_ID = Param(
    name="work_id",
    type="string",
    description="A proposed work's id, as returned by action='list_works'.",
    required=True,
)

#: The one scan an action is about, for the two that judge scans rather than
#: works. Deliberately the *only* id those actions take: an instance already
#: knows its work, and accepting a `work_id` beside it would invent a way for the
#: two to disagree and a rule about which wins.
_IMAGE_ID = Param(
    name="image_id",
    type="string",
    description="One scan's id, as returned by action='list_images'. It carries its own work.",
    required=True,
)

#: The tip every action returning pictures carries, verbatim. The protocol gives
#: an image content block no identity, so position is the only correlation there
#: is — and a caller that does not know the rule will pair the wrong picture with
#: the wrong painting on the first result where one instance had no local copy.
#: One constant rather than three near-identical sentences, because three would
#: drift and the drift would be invisible until a curator accepted the wrong work.
_BLOCK_ORDER_TIP = (
    "Images arrive as image blocks after the text, in the order the rows list them. Each row carries "
    "image_block_index saying which block is its own; a row whose index is null has no picture and "
    "contributes no block."
)

ART_REVIEW: Final = ToolRecord(
    name="art_review",
    title="Art review",
    summary=(
        "Show candidate works and images with the size each would appear at, and record what the curator "
        "decides about them. Never spends."
    ),
    read_only=False,
    destructive=True,
    open_world=False,
    actions=(
        Action(
            name="list_works",
            description="Page through a run's works, each with the image standing for it.",
            example="art_review(action='list_works', run_id='<a run_id from art_discovery(action=list_runs)>')",
            params=(
                Param(
                    name="run_id",
                    type="string",
                    description="Which run's works to review, as returned by art_discovery(action='list_runs').",
                    required=True,
                ),
                Param(
                    name="limit",
                    type="integer",
                    description=f"How many works to return, 1 to {MAX_REVIEW_LIMIT}.",
                    minimum=1,
                    maximum=MAX_REVIEW_LIMIT,
                ),
                Param(
                    name="offset",
                    type="integer",
                    description="How many works to skip, for paging through a large run.",
                    minimum=0,
                ),
            ),
            tips=(
                _BLOCK_ORDER_TIP,
                "Works with an image found for them come first, then ones nothing was found for. A work "
                "reported unresolved is not a defect; read `unresolved_reason` for which kind of nothing. "
                "Only `not_held` suggests the work may not exist.",
                "Read `provenance` on every row. `proposed` is a work the model named for this intent; "
                "`offered` is one the collection volunteered by an artist the run named but could not "
                "confirm a work for. An offered row carries the collection's own title and attribution "
                "verbatim and is never the work that was asked for — its `rationale` says which artist "
                "produced it and how many works that artist has there.",
                f"The page is capped at {MAX_REVIEW_LIMIT} works because each one carries a picture, and pictures "
                "dominate the result's size. A truncated page says so and how many remain; page with offset.",
                "Every image is shown at 400px on its long edge, which is enough to judge whether this is the "
                "right painting and whether it belongs in a living room. It is not enough to judge mat colour.",
            ),
        ),
        Action(
            name="get_work",
            description="Return one proposed work with the image standing for it, and why it was proposed.",
            example="art_review(action='get_work', work_id='<a work_id from action=list_works>')",
            params=(_WORK_ID,),
            tips=(
                _BLOCK_ORDER_TIP,
                "This carries one image, and is_on_offer says whether it is the one a verdict would accept "
                "on. It is false for a work whose scans are all below the floor or all turned down — the "
                "picture is still shown, because a work with no picture and a work nothing was found for "
                "must not look alike. Use action='list_images' to see the alternates found for the work.",
                "rationale is the engine's account of why this work matched the intent. A work is judged "
                "against that reading of the request rather than against its wording.",
            ),
        ),
        Action(
            name="list_images",
            description="Return the image instances found for one work, ranked, each with its size on the wall.",
            example="art_review(action='list_images', work_id='<a work_id from action=list_works>')",
            params=(_WORK_ID,),
            tips=(
                _BLOCK_ORDER_TIP,
                "Where a work has an instance on offer it leads; a work whose scans are all below the floor "
                "or all turned down has none, and then the first row is simply the highest-ranked. Read "
                "is_on_offer rather than position. The rest are alternates, kept rather than discarded so "
                "an over-eager match stays inspectable.",
                "A card you can still act on may hold rows you cannot: rejected scans stay on it as the "
                "record of a judgement, and they keep their rank rather than sorting last. Read "
                "rejected_for_this_work on each row.",
                "display_fit says how an instance would meet the wall: 'native', 'matted_small', or "
                "'below_floor'. A below_floor instance is shown and may be chosen — it is labelled with the "
                "size it would appear at, never hidden.",
                "renders_at_inches is the number a thumbnail cannot convey. A 900-pixel scan and a "
                "6000-pixel scan look identical here and are not the same thing on a wall.",
            ),
        ),
        Action(
            name="set_canonical",
            description="Choose which of a work's scans represents it, overriding the automatic choice.",
            example="art_review(action='set_canonical', image_id='<an image_id from action=list_images>')",
            params=(
                _IMAGE_ID,
                Param(
                    name="rationale",
                    type="string",
                    description="Why this scan was chosen. Kept on the source after acceptance, so the choice stays readable.",
                ),
            ),
            tips=(
                "This is how a below_floor scan gets onto the wall: automatic selection withholds one, and "
                "choosing it explicitly is the decision the floor exists to force. Nothing else overrides it.",
                "A scan already turned down cannot be chosen again — that is what rejecting one means. Use "
                "art_discovery(action='resolve_images') to go looking for a better one.",
            ),
        ),
        Action(
            name="set_verdict",
            description="Accept or reject one proposed work. Accepting puts it in the catalogue.",
            example="art_review(action='set_verdict', work_id='<a work_id from action=list_works>', verdict='accepted')",
            params=(
                _WORK_ID,
                Param(
                    name="verdict",
                    type="string",
                    description="'accepted' puts the work in the catalogue; 'rejected' closes it. Both are final.",
                    required=True,
                    choices=("accepted", "rejected"),
                    # `api-contract.md` § set_verdict cannot set
                    # `awaiting_better_image` requires the refusal to name
                    # `reject_image`, and it is the schema that refuses it — the
                    # service's own teaching error is unreachable from here,
                    # because validation runs first by design. A caller asking
                    # for that verdict has not mistyped; they want the thing a
                    # different action does, and an enumeration alone would send
                    # them away without it.
                    refused_hint=(
                        "To ask for a better scan instead, use action='reject_image' with the image_id — that is "
                        "the only way to awaiting_better_image, and it also suppresses the scan so a re-search "
                        "cannot return it."
                    ),
                ),
                Param(
                    name="reason",
                    type="string",
                    description="Why the work was turned down. Recorded on a rejection; ignored on an acceptance.",
                ),
            ),
            tips=(
                "One work per call, named by id, and there is no accept-everything: the works being accepted "
                "have to appear in the conversation, because a curator seeing what they accepted is the whole "
                "of the review gate. Look at the picture before calling this.",
                "Accepting mints the artwork, promotes every scan found into a source with the chosen one "
                "primary, and attributes it to an artist. A work with no scan selected is refused rather than "
                "recorded with no primary source — choose one with action='set_canonical' first.",
                "minted_artist says a new artist row was created. Where it arrives with "
                "possible_duplicate_artists, the catalogue may now hold the same painter twice under different "
                "spellings — visible and mergeable, which a wrong merge would not be.",
                "'awaiting_better_image' is not settable here. Turning down a scan is "
                "action='reject_image', which is also what suppresses it.",
                "Both verdicts are final: a work already accepted or rejected cannot be re-judged.",
            ),
        ),
        Action(
            name="reject_image",
            description="Turn down one scan and ask for a better one. The work stays wanted.",
            example="art_review(action='reject_image', image_id='<an image_id from action=list_images>')",
            params=(_IMAGE_ID,),
            tips=(
                "This does not go looking for a replacement — art_discovery(action='resolve_images') does, and "
                "it is the call that spends money. Reject the scans you want re-searched, then re-search them "
                "in one batch.",
                "The work moves to awaiting_better_image and the scan is suppressed, so a later search cannot "
                "hand back the one just turned down. The suppression is the reason this is the only way into "
                "that state.",
                "Rejecting the scan on offer falls the selection through to the next survivor; rejecting an "
                "alternate leaves the standing choice alone.",
                "You are never blocked on a re-search: action='set_verdict' works from awaiting_better_image "
                "too, so a curator can accept the best scan on offer or give up on the work at any point.",
            ),
        ),
    ),
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

#: One description across both tools, because every action's parameters flatten
#: onto a single wire schema and only the first description survives. Required
#: wherever it appears: an action that guessed the wall would be worse here than
#: on the web surface, where at least a confirmation dialog could catch it.
_WALL_ID = Param(
    name="wall_id",
    type="string",
    description="Which wall to act on, as returned by art_display(action='walls'). Required even when there is one.",
    required=True,
)

ART_THEME: Final = ToolRecord(
    name="art_theme",
    title="Art themes",
    summary="Group works into themes, and hang a theme on a named wall.",
    read_only=False,
    destructive=True,
    open_world=False,
    actions=(
        Action(
            name="list",
            description="Return every theme, with the walls each is hanging on.",
            example="art_theme(action='list')",
            tips=(
                "A theme is global and hangs nowhere until action='activate' puts it on a named wall. "
                "The same theme may hang on several walls at once, and a theme hanging on none is normal.",
            ),
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
            description="Create a theme. It hangs nowhere until action='activate' puts it on a wall.",
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
                "A theme hanging on any wall is refused, and the refusal names those walls. Hang something else "
                "there with action='activate', or take it down with action='unhang', and then delete. This holds "
                "even when it is the only theme: a wall losing its picture has to be a choice.",
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
            description="Hang this theme on a named wall, replacing whatever was hanging there.",
            example="art_theme(action='activate', theme_id='<a theme_id>', wall_id='<a wall_id>')",
            params=(_THEME_ID, _WALL_ID),
            tips=(
                "The wall is required even when there is only one, so the confirmation you report names it. "
                "Get wall ids from art_display(action='walls').",
                "This publishes the theme: it rewrites the manifest, so the wall converges on it "
                "within about a second. No separate sync is needed.",
                "The result names every member that will NOT be on the wall and why, exactly as "
                "art_display(action='sync') does — a theme can be half-displayable.",
                "Switching costs no television writes: the whole library stays on the TV and rotation is driven from here.",
            ),
        ),
        Action(
            name="unhang",
            description="Take down whatever is hanging on a wall, leaving it holding nothing.",
            example="art_theme(action='unhang', wall_id='<a wall_id>')",
            params=(_WALL_ID,),
            tips=(
                "Refused when nothing is hanging on that wall — there is nothing to take down.",
                "The wall goes on showing what it was showing until something else is hung: no manifest is "
                "rewritten, because publishing an empty one would blank the wall as a side effect of tidying up.",
                "This is how a theme that is refused by action='delete' becomes deletable.",
            ),
        ),
    ),
)

_SYNC_THEME_ID = Param(
    name="theme_id",
    type="string",
    description="Which theme to publish. Omit to publish the one already hanging on that wall, which is the usual case.",
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
            name="walls",
            description="Return every wall, with the theme hanging on each and that wall's directive.",
            example="art_display(action='walls')",
            tips=(
                "Start here: every other action on this tool and art_theme(action='activate') needs a wall_id, "
                "and this is where they come from.",
                "A wall with no theme hanging on it is an ordinary state, not a fault.",
            ),
        ),
        Action(
            name="add_wall",
            description="Record a wall — a place where art hangs. It arrives with nothing on it.",
            example="art_display(action='add_wall', name='Living room')",
            params=(Param(name="name", type="string", description="What to call the wall. Must be unique.", required=True),),
            tips=(
                "A wall is a place and a name, never a device: which display serves it is that display's own "
                "configuration, and nothing about a television is recorded here.",
                "Refuses a name that is empty or already taken.",
                "A new wall shows nothing until a display device is configured with the wall_id this "
                "returns — each wall has its own manifest file, and a display serves the one wall it is "
                "pointed at. Hanging a theme on a new wall disturbs no other wall.",
            ),
        ),
        Action(
            name="status",
            description="Report what the display serving each wall last said about itself, and how long ago.",
            example="art_display(action='status')",
            tips=(
                "This reports an observation and its age in seconds, never a verdict about health. "
                "If no display has ever run for a wall, it says so plainly rather than reporting a zero.",
                "It takes no wall and reports every one of them: each wall's display writes its own "
                "heartbeat, so the answerable question is which wall has gone quiet — and an answer about "
                "one room could be given while another was dark.",
            ),
        ),
        Action(
            name="sync",
            description="Rebuild the theme manifest so a named wall converges on what is hanging there.",
            example="art_display(action='sync', wall_id='<a wall_id>')",
            params=(_WALL_ID, _SYNC_THEME_ID),
            tips=(
                "Refused when nothing is hanging on that wall and no theme_id is given — there is nothing "
                "to put on it. Hang one with art_theme(action='activate') first.",
                "The result names every theme member that will NOT be on the wall and why. "
                "A theme can be half-displayable, and this is the only place that says so.",
                "Switching themes costs no television writes: the whole library stays on the TV "
                "and rotation is driven from here.",
            ),
        ),
        Action(
            name="show_now",
            description="Ask a named wall to jump to one work and carry on rotating from there.",
            example="art_display(action='show_now', wall_id='<a wall_id>', artwork_id='<an artwork_id>')",
            params=(_WALL_ID, Param(name="artwork_id", type="string", description="The work to jump to.", required=True)),
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
            description="Ask a named wall to step to the next work in the theme hanging on it.",
            example="art_display(action='next', wall_id='<a wall_id>')",
            params=(_WALL_ID,),
            tips=(
                "It steps that wall and no other: each wall carries its own counter, so a step in the living "
                "room leaves the study where it was.",
                "Repeated calls inside one poll interval coalesce into a single step — latest wins.",
            ),
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
