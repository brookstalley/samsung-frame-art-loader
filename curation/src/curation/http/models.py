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
