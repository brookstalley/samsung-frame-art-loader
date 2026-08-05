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
    rights: str | None
    status: str
    fit: FitOut | None
    #: Present exactly when `fit` is null, saying why there is no verdict. A card
    #: with no size must not read like a card whose work is small.
    fit_note: str | None
    image: ImageOut


class WorkPageOut(BaseModel):
    """A page of works that describes its own place in the set."""

    works: list[WorkOut]
    total: int
    limit: int
    offset: int
    truncated: bool


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


class ThemeOut(BaseModel):
    """A grouping of works, and the pace it runs at."""

    theme_id: str
    name: str
    description: str | None
    is_active: bool
    #: Null means "inherit the deployment default" rather than "unset", so it is
    #: reported as stored rather than resolved to a number that would read as a
    #: choice the curator made.
    rotation_interval_seconds: int | None
    shuffle: bool | None
    created_at: str


class ThemeListOut(BaseModel):
    """Every theme."""

    themes: list[ThemeOut]


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


class HealthOut(BaseModel):
    """Observations about the wall and this deployment's own geometry."""

    heartbeat: HeartbeatOut
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
    """One work a run proposed or was offered, in the fields the run view shows."""

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
    """Every run, newest first."""

    runs: list[RunOut]
    count: int


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
    """What was actually spent, over a run or over a calendar month."""

    scope: str
    cost_usd: str
    run_id: str | None
    #: What this run alone was billed, beside what asking altogether cost. A run
    #: billed little whose re-searches cost ten times more is worth being able to
    #: see rather than totalled away.
    run_direct_cost_usd: str | None
    year: int | None
    month: int | None


class StartRun(BaseModel):
    """An intent to search for, in the curator's own words."""

    intent: str


class CreateTheme(BaseModel):
    """Everything needed to record a theme."""

    name: str
    description: str | None = None


class AddWork(BaseModel):
    """A work to place in a theme, optionally at a chosen position."""

    artwork_id: str
    position: int | None = None


class MoveWork(BaseModel):
    """Where a work should sit in a theme's order."""

    #: Null moves it behind everything a curator has placed deliberately.
    position: int | None = Field(default=None)
