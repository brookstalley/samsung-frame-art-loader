"""The shapes the browser surface receives.

Typed rather than free dictionaries because this is the half of the FastAPI
decision that framework was chosen for: a response model is checked against what
the handler actually returns, so a field renamed in the service layer fails here
rather than becoming an empty cell in a grid.

**Field names match the MCP surface wherever both carry the same fact**
(`artwork_id`, `theme_id`, `lifespan_text`). The two surfaces format for
different readers and are allowed to differ in *shape*; they are not allowed to
differ in what a thing is *called*, because that is how an agent and a click come
to disagree about the same catalogue in a way no test would catch.

This surface carries **no stability obligation** — it ships with its only
consumer and both deploy together (`api-contract.md`). Nothing outside this
repository may bind to it.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ArtistOut(BaseModel):
    """A person a work is attributed to."""

    artist_id: str
    name: str
    nationality: str | None
    born: int | None
    died: int | None
    #: The source's own words for the lifespan, kept because "c. 1650" and a
    #: parsed year are different claims.
    lifespan_text: str | None
    biography: str | None
    #: Which part of the name is the family name — the part the e-paper label
    #: leads with. Stored rather than derived from `name`, because no rule over
    #: one string is right for both "van Gogh" and "Frank Lloyd Wright"; null on
    #: a record that is not a person, and on one nobody has said yet.
    family_name: str | None
    given_name: str | None


class FitOut(BaseModel):
    """How the held master would meet the space it is rendered into.

    Derived on every read from this deployment's panel and mat, never stored: a
    stored verdict is a judgement about one particular television.
    """

    #: `native`, `matted_small` or `below_floor`.
    verdict: str
    rendered_width: int
    rendered_height: int
    #: The number a curator can actually judge — "would show at 8.6 inches". A
    #: thumbnail cannot convey resolution, which is why this is not optional.
    rendered_long_edge_inches: float


class ImageOut(BaseModel):
    """Whether there is an image to show, and which held image it is."""

    available: bool
    #: `tv_display` when the wall's own render is current, `original` when the
    #: master stands in for it, null when there is nothing to show.
    source_kind: str | None
    #: Present exactly when `available` is false, saying what is missing.
    note: str | None


class WorkOut(BaseModel):
    """One work as a grid card shows it."""

    artwork_id: str
    title: str
    artist: ArtistOut | None
    date_created: str | None
    medium: str | None
    dimensions: str | None
    description: str | None
    #: The line written for a wall label, which is not the holding institution's
    #: paragraph — see `description` above it, and `Artwork` for why one cannot
    #: stand in for the other.
    commentary: str | None
    rights: str | None
    status: str
    fit: FitOut | None
    #: Present exactly when `fit` is null, saying why there is no verdict. A card
    #: with no size must not read like a card whose work is small.
    fit_note: str | None
    image: ImageOut


class WorkFacetOut(BaseModel):
    """One thing a work is said to be."""

    facet_id: str
    #: One of the six shared vocabulary kinds — `artist`, `movement`, `era`,
    #: `subject`, `medium`, `palette`.
    kind: str
    value: str
    #: `sourced` or `inferred`. **Inferred is the rule rather than the exception**
    #: for the wired collection, so a screen states that default once and marks
    #: only the rare `sourced` value; badging every inferred row is a label on
    #: almost everything, which is a label nobody reads.
    derivation: str
    #: Which field of which provider, or which model. Null where nobody recorded it.
    source_note: str | None


class FacetOptionOut(BaseModel):
    """One value a facet control offers."""

    value: str
    #: Works this value would select **given every other facet but not this one**.
    #: That is what lets a curator change their mind about a facet without first
    #: clearing it.
    count: int
    selected: bool
    #: True for an option that would select nothing. **Returned rather than
    #: omitted**: a vocabulary that shrank as filters were applied would read as
    #: data loss rather than as an empty intersection. A selected value is never
    #: disabled, because the control that turns it off is the option itself.
    disabled: bool


class FacetGroupOut(BaseModel):
    """One facet kind as a control renders it."""

    kind: str
    #: Commonest first, then alphabetically, capped — with every selected value
    #: kept whatever its count.
    options: list[FacetOptionOut]
    #: How many values this kind offers in total, before the cap.
    total_values: int
    #: True when the cap left some out, so a control can say how much it is not
    #: showing rather than implying the vocabulary is as long as the list.
    truncated: bool


class WorkPageOut(BaseModel):
    """A page of works that describes its own place in the set."""

    works: list[WorkOut]
    total: int
    limit: int
    offset: int
    truncated: bool
    #: The facet controls for exactly this filter, in the same response as the
    #: works they label. **Not a second route** — they answer the same question
    #: the grid answers, and two routes would give a curator two answers to it
    #: with a write free to land in between.
    facets: list[FacetGroupOut] = []


class SourceOut(BaseModel):
    """A place a work can be obtained from."""

    source_id: str
    url: str
    provider: str
    source_class: str
    acquisition_method: str
    #: Provenance and source quality. It gates nothing.
    rights_status: str
    is_primary: bool
    confidence: float | None
    selection_rationale: str | None
    last_fetch_status: str | None
    #: When that status was recorded. Present for the same reason the MCP shape
    #: carries it: "failed" with no date cannot be told from "failed months ago
    #: and since fixed", which is the question a curator asks before retrying.
    last_fetched_at: datetime | None


class OriginalOut(BaseModel):
    """The master image a work holds."""

    relative_path: str
    width: int
    height: int
    byte_size: int
    content_hash: str


class RenditionOut(BaseModel):
    """A derived image, and whether it still matches the master it was made from."""

    rendition_id: str
    kind: str
    target_width: int
    target_height: int
    relative_path: str
    #: Derived on every read rather than stored, so it cannot disagree with the
    #: original it is a statement about.
    stale: bool
    generated_at: str


class MatColorOut(BaseModel):
    """A mat colour chosen for a work, and how it was chosen."""

    hex_rgb: str
    #: `vision_model` or `dominant_color_fallback` — recorded because a
    #: mechanical fallback and a considered choice are otherwise identical.
    method: str
    is_current: bool
    reason: str | None
    chosen_at: str


class WorkDetailOut(BaseModel):
    """One work in full."""

    work: WorkOut
    original: OriginalOut | None
    sources: list[SourceOut]
    renditions: list[RenditionOut]
    mat_colors: list[MatColorOut]
    #: What this work is, in the vocabulary the collection is filtered by. On the
    #: detail rather than on `WorkOut`, because the grid shows the collection's
    #: counts and the Work screen shows one work's facts.
    facets: list[WorkFacetOut] = []


class ThemeOut(BaseModel):
    """A grouping of works, and the pace it runs at.

    **It does not say where it is hanging**, and that is the shape of the
    2026-08-12 ruling rather than an omission: a theme is global, two walls may
    hang the same one, and an `is_active` boolean here could only ever have meant
    "active on the one television". `WallOut` is what says what is where.
    """

    theme_id: str
    name: str
    description: str | None
    #: Null means "inherit the deployment default" rather than "unset", so it is
    #: reported as stored rather than resolved to a number that would read as a
    #: choice the curator made.
    rotation_interval_seconds: int | None
    shuffle: bool | None
    created_at: str


class WallRefOut(BaseModel):
    """A wall named from somewhere that is not about walls.

    Just enough to say which wall and to print its name. The full shape would
    carry the theme hanging on it, and a theme listing that carried each wall's
    theme would be answering a question nobody asked from inside the answer to
    another one.
    """

    wall_id: str
    name: str


class ThemePlacementOut(BaseModel):
    """A theme and every wall showing it.

    A list rather than a single wall, because two walls may hang the same theme
    — and a field with room for one would have re-made the single-wall
    assumption one layer above the boolean that was removed. Empty is the
    ordinary state of a theme nobody has hung.
    """

    theme: ThemeOut
    hanging_on: list[WallRefOut]


class ThemeListOut(BaseModel):
    """Every theme, and where each is hanging."""

    themes: list[ThemePlacementOut]


class WallOut(BaseModel):
    """A place where art hangs, and what is hanging there.

    The theme travels with the wall rather than being a second request, because
    every screen that shows a wall shows what is on it — and because the pair is
    read at one instant here, where two requests could report a wall and a theme
    that were never simultaneously true.

    **`theme` is null when nothing is hanging**, which is an ordinary state: an
    empty catalogue, or a curator who took everything down.
    """

    wall_id: str
    name: str
    created_at: str
    theme: ThemeOut | None
    #: What this wall was last told to do. Carried because the Walls screen shows
    #: "what is next" beside "what is hanging", and because a per-wall counter is
    #: the thing a reader has to be able to see is per-wall.
    directive_sequence: int
    pinned_work_id: str | None


class WallListOut(BaseModel):
    """Every wall, with what each is showing."""

    walls: list[WallOut]


class DirectiveOut(BaseModel):
    """What one wall was last told to do.

    **The wall is in the answer, not only in the request.** A directive is a row
    per wall rather than a singleton, and an answer that reported only a counter
    would leave a caller holding a number with nothing attached to it — which is
    exactly the state the singleton was in before the split.

    `WallOut` carries the same two facts beside the theme, and this is
    deliberately not that: stepping a wall changes what it was told to do and
    nothing about what hangs there, so an answer shaped like a wall would invite
    a reader to look for a change in the rest of it.
    """

    wall_id: str
    sequence: int
    #: Null after a step, always: moving on and standing on a pinned work are
    #: contradictory instructions, so the step clears any pin.
    pinned_work_id: str | None


class ThemeDetailOut(BaseModel):
    """A theme and the works it holds, in curated order."""

    theme: ThemeOut
    works: list[WorkOut]


class ManifestEntryOut(BaseModel):
    """One work as the display plane would receive it."""

    artwork_id: str
    title: str
    artist: str | None
    render_path: str


class ExclusionOut(BaseModel):
    """One work that is in the theme and not on the wall, and why."""

    artwork_id: str
    title: str
    #: `archived`, `no_original`, `no_rendition`, `stale_rendition` or
    #: `no_mat_color` — each a distinct thing a curator would act on differently.
    reason: str
    #: A sentence to act on, not a restatement of the reason.
    detail: str


class ManifestOut(BaseModel):
    """What a theme would put on the wall, and everything it would leave off.

    Exclusions are the half of this a list-only view drops silently, which is the
    whole reason the builder reports them.
    """

    #: Which wall this build is about. Named in the response so a confirmation
    #: can say "Hang Winter in the living room" without a second request, even
    #: while there is one wall and the answer is obvious.
    wall_id: str
    wall_name: str
    theme: ThemeOut
    entries: list[ManifestEntryOut]
    exclusions: list[ExclusionOut]
    considered: int
    rotation_interval_seconds: int
    shuffle: bool
    directive_sequence: int
    pinned_work_id: str | None
    #: One sentence saying how much of the theme reached the wall, stated even
    #: when nothing was excluded — a message that appeared only on trouble would
    #: train a reader to skim past its absence.
    summary: str


class HeartbeatOut(BaseModel):
    """What curation can observe about the display plane, stated as observation.

    Never a verdict. `absent` and `problem` are different answers on purpose:
    nothing has ever run is normal on a fresh deployment, and a file that will
    not parse is a fault.
    """

    path: str
    reported_at: str | None
    age_seconds: float | None
    absent: bool
    problem: str | None
    #: One sentence stating what was observed, never a judgement about it.
    description: str
    #: The document as the display plane wrote it, handed through untouched.
    #:
    #: **This is what gives the failure table a reader.** TV connectivity, e-paper
    #: state and the last error are all mapped onto this document by
    #: `observability-strategy.md`, and until it reached the panel those rows named
    #: a signal nothing displayed — a monitoring plan whose evidence existed only
    #: in a file no surface opened.
    #:
    #: Passed through rather than unpacked into named fields, because
    #: `reported_at` is the *only* key that artifact makes contract and the rest is
    #: explicitly the writer's to shape. Naming them here would invent a second
    #: contract the writer never agreed to, and a writer that spelled one
    #: differently would go silently unreported — the exact failure the one named
    #: key exists to prevent, reintroduced for every other field.
    reported: dict[str, Any] | None


class ArtworkBoxOut(BaseModel):
    """The space this deployment renders a work into, as resolved at startup.

    Shown because a wrong mat or floor is otherwise visible only as works being
    labelled oddly in the grid, which reads as a catalogue problem rather than a
    configuration one.
    """

    width: int
    height: int
    pixels_per_inch: float
    floor_inches: float


class BackupOut(BaseModel):
    """When the catalogue was last safely copied, or that nothing has copied it.

    The catalogue is the irreplaceable asset — the image tree is deliberately not
    backed up, because every file in it can be fetched again. A backup that
    silently stopped succeeding a month ago is the failure this reading exists to
    make visible, and it is the same silent-failure class as everything else here.
    """

    path: str
    completed_at: str | None
    age_seconds: float | None
    #: True when no backup has ever recorded itself. Held apart from `problem`
    #: for the reason the heartbeat holds them apart: never run is normal on a
    #: deployment whose backup is not yet scheduled, and a receipt that will not
    #: parse is a fault.
    absent: bool
    problem: str | None
    #: One sentence stating what was observed, never a judgement about it. There
    #: is no threshold here: six days is alarming for a nightly job and
    #: unremarkable for a destination that is usually asleep, and this surface
    #: does not know which deployment it is on.
    description: str
    #: The receipt as the backup job wrote it, past the one key this side reads.
    #: Where the copy went and how large it was are the job's to record.
    reported: dict[str, Any] | None


class WallHeartbeatOut(BaseModel):
    """One wall and what the display serving it last said about itself.

    The wall's name travels with its reading rather than being looked up by the
    client from a second call: a panel that has to join two responses to say
    *which* room is silent is a panel that will say "a wall is silent" instead.
    """

    wall_id: str
    wall_name: str
    heartbeat: HeartbeatOut


class HealthOut(BaseModel):
    """Observations about the walls, the backup, and this deployment's geometry.

    **The heartbeat is a list, one entry per wall**, since 2026-08-12. Each wall's
    display writes its own file, so "has the display plane reported" stopped being
    a question with one answer and became "which wall has not" — and a single
    reading could not have carried the name of the room that went quiet.

    **There is no budget balance here, and its absence is a decision** (operator,
    2026-08-04). The provider's `limit_remaining` was observed reporting credit
    while live calls were already being refused, so it fails by inversion rather
    than by staleness — and stating its age, which is this panel's whole remedy
    for a stale figure, would not warn anyone about the case that bites. The
    honest budget signals are recorded per-run spend and the `halted_by_budget`
    outcome, and both are on the run view.
    """

    walls: list[WallHeartbeatOut]
    #: One sentence across every wall, naming the ones that have not reported.
    #: An observation and never a verdict: no threshold is applied here, so this
    #: says how long ago rather than whether that is too long.
    description: str
    backup: BackupOut
    artwork_box: ArtworkBoxOut


class RunOut(BaseModel):
    """One discovery run as a list row shows it.

    The terminal state is carried as itself and never collapsed into a
    succeeded/failed flag, for the same reason the MCP surface refuses to: out of
    money, broke, and the process restarted underneath it call for three
    different responses from the person reading the row.
    """

    run_id: str
    #: `discovery` or `resolve`. A re-search is a run, which is what lets one
    #: screen follow either without knowing which it is looking at.
    kind: str
    status: str
    #: Whether this run has ended. Carried rather than left for the client to
    #: derive from a list of status names, because that list is the thing that
    #: goes stale: a tenth status added to the enum would leave a browser polling
    #: a finished run forever, with nothing failing to say so.
    is_terminal: bool
    initiated_by: str
    intent: str | None
    #: How the engine read the intent, in its own words. A work list is judged
    #: against the reading of the request rather than its wording, so a
    #: surprising list is explicable instead of merely wrong. Null while phase 1
    #: is still working: nothing has read the intent yet.
    strategy: str | None
    approval_required: bool
    #: Prices are strings, never floats. A tenth of a cent that cannot be
    #: represented exactly is a rounding error in the figure a curator authorised
    #: against, and then in a total nobody reconciles.
    estimated_cost_usd: str | None
    actual_cost_usd: str | None
    unresolved_work_count: int | None
    parent_run_id: str | None
    started_at: str
    completed_at: str | None


class CandidateWorkOut(BaseModel):
    """One work a run proposed or was offered, in words rather than pictures.

    Shared by the run view and the review grid, which show the same work at two
    altitudes — a row in a run's work list, and the text half of a card being
    judged. One model rather than two because it is one work: a second shape
    would let the two screens come to call the same fact by different names,
    which is the failure `models.py` exists to prevent one surface further out.
    """

    work_id: str
    title: str
    artist: str | None
    #: Why the engine named this work. Shown because a curator judging a work
    #: list is judging the reasoning as much as the titles.
    rationale: str
    #: `proposed` — the model named it — or `offered`, meaning a wired collection
    #: volunteered it on top of the list. Never merged into one count: the
    #: curator authorised a list of a stated size and the supplement adds to it.
    provenance: str
    #: For an offered work, the browse query that produced it and how many works
    #: that query matched in the collection; null on both for a proposed work.
    #:
    #: Sent as two facts rather than as a finished sentence so each surface can
    #: say them where its own grouping puts them — `product-brief.md` requires a
    #: curator to be able to tell one-of-four-hundred from one-of-one, and asks
    #: that it be said once for the query rather than on every card. A composed
    #: sentence could only ever be said per work, which is what it used to be.
    #:
    #: **`matched` is the collection's holdings, not the number offered.** The
    #: per-run bound caps what is shown; this is what it is capped from, and the
    #: two are meant to be read against each other.
    offered_for_artist: str | None
    offered_artist_matched: int | None
    verdict: str
    resolution_status: str
    #: Which kind of nothing an unresolved work came back with, or null. A bare
    #: `unresolved` cannot tell a title nobody holds from a scan too small for
    #: the wall, and those lead to opposite actions.
    unresolved_reason: str | None


class RunTallyOut(BaseModel):
    """How many works a run has, cut the ways a curator reads them.

    Proposed and offered are counted apart wherever a number is shown. With
    twelve offered works behind one unresolved proposal, a merged "12 of 13 have
    an image" reports a resolution rate the run never achieved.
    """

    total: int
    proposed: int
    offered: int
    resolved: int
    #: How many of the model's own works ended up with an image — the numerator
    #: any resolution rate is stated over. Counted directly rather than derived
    #: by subtracting offered works from resolved, which goes negative as soon as
    #: an offered work is re-searched to nothing.
    resolved_proposals: int
    unresolved: int
    pending: int


class SearchUsageOut(BaseModel):
    """What a run has used of its search allowance.

    Two numbers rather than one verdict: the usage is this run's own history and
    the allowance is the deployment's current setting, so a run read after the
    setting changed shows both instead of a boolean recomputed against a rule it
    never ran under.
    """

    used: int
    allowance: int
    exhausted: bool


class RunViewOut(BaseModel):
    """A run in full — its state, its works, and what it has spent looking."""

    run: RunOut
    tally: RunTallyOut
    #: Every work, uncapped, and **nothing bounds how many there are** — phase 1
    #: is deliberately not capped at a work count, because the approval gate
    #: exists to catch exactly the run that read an intent too broadly ("you
    #: asked for Dalí and I found 200 works, really?"), and a cap would mean the
    #: gate could never fire. So this list is as long as the run is wide.
    #:
    #: Sent whole anyway. The MCP surface stops at 100 because a model's context
    #: is the scarce thing; here the reader is a curator deciding whether to
    #: approve, and a truncated list is precisely the one they cannot answer the
    #: gate's question from. The cost is real and bounded by that same
    #: judgement: a 200-work run re-fetched while it is being deliberated over.
    works: list[CandidateWorkOut]
    searches: SearchUsageOut
    #: Whether this deployment can resolve images at all. A run sitting in
    #: `resolving_images` means work under way or work nothing will ever pick up,
    #: and there is no other way to tell those apart.
    image_resolution_available: bool


class RunListOut(BaseModel):
    """The newest runs, and how many there were before the cap.

    `total` and `truncated` are carried rather than left for the client to
    infer from `len(runs)`: a silently short list is indistinguishable from a
    complete one, which is how a curator concludes there have been fifty runs
    when there have been four hundred.
    """

    runs: list[RunOut]
    count: int
    total: int
    truncated: bool


class EstimateOut(BaseModel):
    """What something is expected to cost, and which question was answered.

    `phase` is carried rather than inferred from whether a run was named: "what
    will asking cost" and "what will resolving what I found cost" are different
    questions, and a number whose meaning depends on remembering what you sent
    gets read wrong.
    """

    phase: str
    estimated_cost_usd: str
    basis: str
    run_id: str | None


class SpendOut(BaseModel):
    """What was actually spent, over a run or over a calendar month.

    **No `run_direct_cost_usd`, unlike the MCP twin, and the absence is a
    decision.** This surface's costs panel reads "what this run alone spent" off
    the run record's `actual_cost_usd`, which is the same figure — so carrying it
    here as well would give one screen two sources for one number, and the unread
    one is where they would silently diverge. What this payload is fetched for is
    the family total, which lives nowhere else.

    Stated here rather than as a `#:` comment where the field used to be: a
    comment in that position documents the field *below* it, so an explanation of
    something absent would be read as describing `year`.
    """

    scope: str
    cost_usd: str
    run_id: str | None

    year: int | None
    month: int | None


class InstanceOut(BaseModel):
    """One image instance as a curator judging it needs to see it.

    **The size is not decoration and it is why this model is not just a URL.** A
    900 px scan and a 6000 px scan are the same picture in a review card, so a
    grid that showed only pictures would not protect against hanging a postage
    stamp. Every instance therefore carries the size it would render at on *this*
    deployment's wall, in inches — the number a curator can actually judge.
    """

    image_id: str
    work_id: str
    #: Where the scan lives at its provider. Shown because an instance with no
    #: local copy is still real and still selectable, and this is all a curator
    #: has to go on when the picture cannot travel.
    url: str
    provider: str
    confidence: float
    #: Whether this is the instance a verdict would accept on. Not the same
    #: question as whether it is the one pictured on the card — a work whose scans
    #: are all below the floor or all turned down has no selection and is still
    #: shown, which is what `shown_is_on_offer` reports one level up.
    is_selected: bool
    #: Whether the curator has turned this scan down. A rejected instance stays on
    #: the card, labelled: it is the evidence of a judgement already made, and
    #: hiding it would leave a curator wondering why a re-search returned fewer
    #: instances than before.
    rejected: bool
    rights_status: str | None
    selection_rationale: str | None
    fit: FitOut | None
    #: Present exactly when `fit` is null. An instance whose dimensions nobody
    #: recorded must not read like one known to be small: the first is a fact
    #: about our record, the second a fact about the picture.
    fit_note: str | None
    #: Whether a picture travels with this instance. Carried so a card knows
    #: before it asks, rather than requesting bytes that are not there and
    #: painting a blank box while it finds out.
    preview_available: bool
    #: Present exactly when no picture travels, saying which of the four reasons
    #: applies — never cached, reclaimed after a verdict, gone from disk, or
    #: undecodable. They send whoever asks to different places.
    preview_note: str | None


class CandidateCardOut(BaseModel):
    """One proposed work with the instance whose picture stands for it."""

    work: CandidateWorkOut
    #: The instance pictured on the card, or null when there is genuinely nothing
    #: to show — no instances at all, or every one of them rejected.
    #: `instances_held` and `instances_surviving` tell those two apart.
    shown: InstanceOut | None
    #: Whether the pictured instance is also the one a verdict would accept on. A
    #: work with no selection still arrives pictured, because a below-floor scan
    #: must be shown, labelled and selectable rather than hidden — and a card
    #: carrying no image because nothing was auto-selected would hide it.
    shown_is_on_offer: bool
    instances_held: int
    instances_surviving: int


class CandidatePageOut(BaseModel):
    """One page of a run's works, with enough context to describe itself."""

    run: RunOut
    works: list[CandidateCardOut]
    total: int
    limit: int
    offset: int
    truncated: bool


class InstanceListingOut(BaseModel):
    """A work's instances in the order the review card offers them, capped."""

    work: CandidateWorkOut
    instances: list[InstanceOut]
    #: What the work actually holds, against `len(instances)` for what this card
    #: shows. Reported separately so a truncated card cannot be read as a
    #: complete one — the failure a count omitted alongside a list always makes.
    held: int
    #: The same distinction one level in: how many instances are still choosable,
    #: against how many of *those* fit. A card that dropped only refused scans and
    #: one that also dropped choosable ones are different things to tell a
    #: curator, and `held` counts both kinds together.
    surviving_held: int
    truncated: bool
    #: False only when the choosable instances alone outrun the cap, which is the
    #: one case where a truncated card withholds something actionable.
    shows_every_choosable_instance: bool


class VerdictOut(BaseModel):
    """A recorded verdict, and what recording it did beyond the verdict itself."""

    work: CandidateWorkOut
    #: Null on a rejection, and the id of the minted work on an acceptance — the
    #: handle every catalogue action takes, so accepting hands back the thing the
    #: next call needs rather than making the caller go looking.
    artwork_id: str | None
    decided_at: str | None
    #: Both reported on every acceptance, empty included. A key present only when
    #: an artist was minted would teach a reader to take its absence as "nothing
    #: happened", which is the silence this pair exists to break: a duplicate
    #: artist row looks exactly like a painter newly encountered.
    minted_artist: ArtistOut | None
    possible_duplicate_artists: list[ArtistOut]
    notice: str | None


class SelectedImageOut(BaseModel):
    """Which instance a work now stands on.

    No `is_on_offer` flag: `select_image` either makes this the instance on offer
    or refuses, and a refusal returns no payload — so the field could only ever
    read true, and would restate the fact that the call succeeded.
    """

    image_id: str
    work_id: str
    url: str
    selection_rationale: str | None


class StartRun(BaseModel):
    """An intent to search for, in the curator's own words."""

    intent: str


class StartResolve(BaseModel):
    """The works to look again for images of."""

    work_ids: list[str]


class SetVerdict(BaseModel):
    """A curator's decision about a proposed work.

    `awaiting_better_image` is deliberately not settable here: that verdict is
    what rejecting an *image* means, and it is set by that call so the verdict and
    the instance's suppression can never come apart. The service refuses it, and
    the refusal says which call does set it.
    """

    verdict: str
    #: Why, in the curator's words. Optional, and worth having: "rejected" and
    #: "rejected because it is a studio copy" are the same row to the pipeline and
    #: different evidence to whoever reads it later.
    reason: str | None = None


class SelectImage(BaseModel):
    """Why this scan rather than the one the pipeline picked."""

    rationale: str | None = None


class CreateTheme(BaseModel):
    """Everything needed to record a theme."""

    name: str
    description: str | None = None


class RenameTheme(BaseModel):
    """The new name, and deliberately nothing else.

    `update_theme` can also change a description and a theme's pace, and this
    body cannot reach either. That is the route's scope rather than an oversight:
    the service distinguishes "leave this alone" from "clear it" with a sentinel,
    and a request model whose optional fields default to `None` would erase a
    theme's rotation settings every time a curator corrected a typo in its name.
    A body that can only say one thing cannot say that one by accident.
    """

    name: str


class CreateWall(BaseModel):
    """Everything needed to record a wall: a name, and nothing device-shaped."""

    name: str


class HangTheme(BaseModel):
    """Which wall a theme is being hung on.

    **Required, even while there is one wall and the answer is obvious.** A
    request that omitted it would produce a confirmation that reads correctly
    today and silently becomes wrong the day a second display arrives.
    """

    wall_id: str


class StepDisplay(BaseModel):
    """Which wall is being told to move on to the next work.

    **Required, for the reason `HangTheme` states.** A `next` aimed at the living
    room that stepped the study is one counter being asked a question it cannot
    answer, and a request that guessed would be indistinguishable from one that
    meant it.
    """

    wall_id: str


class AddWork(BaseModel):
    """A work to place in a theme, at a chosen index or at the end of the order."""

    artwork_id: str
    #: An index into the order the theme is displayed in, not a number stored on
    #: the work. Null puts it last — the screens send nothing, and a work nobody
    #: has placed belongs at the end rather than outside the order.
    position: int | None = None


class MoveWork(BaseModel):
    """Where a work should sit in a theme's order."""

    #: Null moves it behind everything a curator has placed deliberately.
    position: int | None = Field(default=None)


class SampleOut(BaseModel):
    """One picture shown beside a name a reply gave, to make the name concrete.

    **Not a candidate and not on its way to becoming one.** Nothing here has been
    proposed, judged, or acquired — it is a work the wired collection holds by an
    artist the model named. `image_url` is the collection's own preview address,
    loaded by the browser directly, because a conversation caches no files: a
    picture nobody chose is not a preview of anything, and storing one would need
    a sweep for files that were never candidates.
    """

    title: str
    artist: str | None
    #: Null when the deployment browses no collection, or when the collection's
    #: record carries no preview. The name is still shown; a sample without a
    #: picture is a fact stated plainly rather than a blank box.
    image_url: str | None


class SuggestionOut(BaseModel):
    """One thing a turn named, and whatever pictures were found for it.

    `kind` is drawn from the same closed set an affinity is recorded against —
    artist, movement, era, subject, medium, palette — because a suggestion is
    what an affinity would later be recorded *about*, and two vocabularies would
    leave the thing said and the thing remembered unable to be matched up.
    """

    kind: str
    value: str
    #: Frozen at the moment the turn was written, never looked up on read. The
    #: transcript is a record of what was said, so a thread re-read next month
    #: shows the pictures it showed at the time rather than whatever the
    #: collection would answer today. Empty for a kind the collection cannot be
    #: browsed by, which today is everything but `artist`.
    samples: list[SampleOut]


class ConversationTurnOut(BaseModel):
    """One thing said in a conversation.

    `role` is `curator` or `system` — the product's own words, deliberately not
    the provider's `user`/`assistant`. The transcript a curator reads back is in
    the product's terms, and the translation to a chat API's happens once, far
    below this surface.
    """

    turn_id: str
    ordinal: int
    role: str
    #: Verbatim, and never null. A model turn that was cut off arrives from the
    #: provider with no content at all; storing that null is what would make the
    #: *next* turn fail over a missing content field rather than over anything
    #: that went wrong, so a turn with nothing in it carries the empty string.
    text: str
    suggested: list[SuggestionOut]
    #: The seam. Set on the turn where the curator committed a direction, and the
    #: only edge from a conversation to a run. A run started from the Discover
    #: box has none, and neither does any turn before the commit.
    committed_run_id: str | None
    created_at: str


class ConversationOut(BaseModel):
    """One conversation as a list row shows it."""

    conversation_id: str
    started_at: str
    #: What the list is ordered by. Distinct from `started_at` because the thread
    #: a curator is looking for is the one they last said something in, and the
    #: day it began says nothing about that.
    last_turn_at: str
    #: A short account of where the conversation got to, for the list. **Never
    #: read back as taste** — an affinity is the only thing the product consults
    #: for that, and a summary consulted as one would be a second, prose-shaped
    #: opinion free to drift from the recorded one.
    summary: str | None


class ConversationViewOut(BaseModel):
    """A whole thread, and whatever is outstanding on it.

    `failure` and `unanswered_turn_id` are the retryable failed turn, and they
    are deliberately different kinds of fact. `unanswered_turn_id` is derived
    from the transcript — a thread whose last turn is the curator's is one whose
    question was not answered — so it survives a reload and cannot disagree with
    what the thread says. `failure` is the account of why *this* attempt did not
    answer, and it lives only on the response to that attempt: it is a fact about
    a call rather than about the conversation, and a transcript that kept it
    would report a provider's transient complaint as part of what was said.

    **Every write returns this whole view rather than the turn it wrote.** A
    failed turn must stay in the thread and be retryable, which a client cannot
    render from an error body — so a turn that could not be answered is a 200
    carrying the thread and the reason, and only a refusal that recorded nothing
    at all is a 400.
    """

    conversation: ConversationOut
    turns: list[ConversationTurnOut]
    #: The run this conversation seeded, if it has seeded one — the most recent,
    #: because a curator may commit a second direction from the same thread and
    #: the card at the bottom is about the last thing they did. This is what the
    #: commit card polls, and it is why committing never has to navigate.
    committed_run_id: str | None
    failure: str | None
    unanswered_turn_id: str | None


class ConversationListOut(BaseModel):
    """Every conversation, the most recently spoken in first."""

    conversations: list[ConversationOut]
    count: int


class Speak(BaseModel):
    """Something to say, or nothing — which asks again for the last answer.

    **Omitting the text is how a failed turn is retried, and that is what keeps a
    spend-triggering POST safe to press twice.** Retrying asks for the answer to
    the question already standing at the end of the thread rather than re-sending
    the question, so a thread whose last turn *was* answered has nothing to retry
    and is told so — which is exactly the case where the model was billed and the
    response was lost on the way back to the browser. The transcript closes the
    double-spend window, in place of an idempotency key a client would have to
    remember to send.
    """

    text: str | None = None


class CommitDirection(BaseModel):
    """The direction to search for, in the words the curator is committing to.

    Sent rather than derived on the server from the last turn's suggestions, for
    the reason the direct-intent box exists at all: what gets searched for is the
    curator's decision, and a commit button that sent something they had not read
    would be the wizard this flow is arranged to avoid.
    """

    intent: str
