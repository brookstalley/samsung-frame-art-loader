"""What the catalogue stores: its enumerations and its records.

The records are plain frozen dataclasses. They carry no persistence behaviour —
no `save()`, no lazy relationship loading — so that a service holding one cannot
accidentally reach the database through it. Reads that need more go back through
the store, whose contract is `catalogue.py`.

**Only stored facts live here.** A value the catalogue derives rather than keeps
belongs with the function that derives it — `DisplayFit` is the worked example
and it is deliberately in `services/display_fit.py`, because a verdict about
whether an image is big enough depends on panel geometry and mat configuration,
which are deployment values this plane does not own. Storing it would make the
row a claim about one particular television that goes silently wrong the day the
television changes.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class ArtworkStatus(StrEnum):
    """The only two states a catalogued work can be in.

    An artwork exists only once it has been accepted; everything before that
    is a candidate, which is a different entity with its own lifecycle.
    """

    ACCEPTED = "accepted"
    ARCHIVED = "archived"


class SourceClass(StrEnum):
    """Which kind of place a work was obtained from.

    Load-bearing rather than descriptive: the two classes share almost nothing
    operationally. An institutional source offers gigapixel tiles, structured
    metadata, published rate limits and usually public-domain rights; a
    contemporary-web source offers one web JPEG, scraped or absent metadata,
    unknown per-site limits and usually copyright. Keeping the distinction in a
    column lets the pipeline branch once instead of scattering the difference
    through the acquisition code as conditionals on a provider string.
    """

    INSTITUTIONAL = "institutional"
    CONTEMPORARY_WEB = "contemporary_web"


class AcquisitionMethod(StrEnum):
    """How the bytes are fetched from a source."""

    DEZOOMIFY = "dezoomify"
    DIRECT_HTTP = "direct_http"
    API = "api"


class RightsStatus(StrEnum):
    """What is known about a source's rights.

    Recorded for every source, `UNKNOWN` included, because "we did not check"
    and "we checked and could not tell" are different facts and only the second
    is honest as `unknown`. The value gates nothing — it is shown in the review
    grid as a provenance and source-quality signal, since a holding
    institution's own public-domain scan is usually the authoritative file while
    unknown-rights images are more often downstream reproductions.
    """

    PUBLIC_DOMAIN = "public_domain"
    IN_COPYRIGHT = "in_copyright"
    UNKNOWN = "unknown"


class FetchStatus(StrEnum):
    """How the last fetch from a source went.

    `PARTIAL_TILES` is a normal dezoomify outcome and not an error: a tile
    server that drops a few tiles still yields a usable master image.
    """

    OK = "ok"
    PARTIAL_TILES = "partial_tiles"
    FAILED = "failed"


class RenditionKind(StrEnum):
    """What a derived image is for.

    There is no `label` kind. A label is rendered on the display plane from the
    text fields the theme manifest carries, because its geometry is the e-paper
    panel's — a device this plane does not own and must not hold facts about.
    Both kinds here are device-independent: `TV_DISPLAY` is a 4K presentation of
    the artwork with its mat composed in, which any 4K display shows, and a
    thumbnail is a thumbnail.
    """

    TV_DISPLAY = "tv_display"
    THUMBNAIL = "thumbnail"


class MatMethod(StrEnum):
    """How a mat colour was arrived at.

    Recorded because the fallback is invisible otherwise: the 2024 pipeline
    silently substituted a darkened dominant colour whenever the vision model
    failed, so a hand-quality choice and a mechanical one were indistinguishable
    in the data.
    """

    VISION_MODEL = "vision_model"
    DOMINANT_COLOR_FALLBACK = "dominant_color_fallback"
    MANUAL = "manual"


class VocabularyKind(StrEnum):
    """The one typed vocabulary, used from both sides.

    **This enum is deliberately shared rather than duplicated, and the sharing is
    the reason `WorkFacet` exists at all.** One set of terms then serves three
    purposes: what a work *is* (`WorkFacet.kind`), what the curator *likes*
    (`Affinity.kind`), and what discovery weights when it proposes. Two
    vocabularies for one idea is the drift being avoided — "Post-Impressionism"
    as a taste and "post impressionist" as a catalogue value cannot be matched,
    and nothing would report the mismatch.

    **`Affinity` binds to this type rather than declaring its own**, which is
    what makes the agreement structural. Widening one without the other would
    silently break the join that makes taste useful, and the only way to stop
    that being a promise is for there to be one enum to widen. `Affinity` itself
    lives in `discovery_records.py`, beside the conversations a judgment is
    derived from and inside the transaction its detachment has to hold.

    Closed on purpose. A free-text kind turns a typo into a new dimension, and
    nothing downstream can tell `subject` from `subjcet`; a seventh kind is a
    schema change, which is the point.
    """

    ARTIST = "artist"
    MOVEMENT = "movement"
    ERA = "era"
    SUBJECT = "subject"
    MEDIUM = "medium"
    PALETTE = "palette"


class FacetDerivation(StrEnum):
    """Where a facet's claim about a work came from.

    Never absent — an unlabelled facet is a guess wearing a citation.

    **The expected steady state is that most facets are `INFERRED`**, and that is
    a fact about the providers rather than a defect: `discovery/browse.py` records
    that for the Art Institute "style, classification and period were measured
    missing on ordinary spellings", and that collection publishes no style field
    at all. Which is exactly why every row has to say which it is — a facet the
    museum published and a facet a model guessed carry different authority, and a
    curator correcting the catalogue needs to know which one they are arguing
    with.

    Deliberately *not* `Affinity.derivation`, which is a different question with
    three answers (`stated`, `inferred`, `observed`) about where a *taste* came
    from. Only `kind` is the shared vocabulary.
    """

    SOURCED = "sourced"
    INFERRED = "inferred"


@dataclass(frozen=True, slots=True)
class Artist:
    """A person a work is attributed to.

    Separate from the work so the physical label can render nationality and
    lifespan without re-parsing a blob, and so two works by the same artist
    agree about them.

    **`name` is what a source called the artist; the two name parts are what a
    label sets them as, and neither is derived from the other.** The e-paper
    label leads with the family name and sets it apart, which needs to know which
    part of the name that is — and no rule over `name` can say. "Titian (Tiziano
    Vecellio)", "van Gogh" and "Frank Lloyd Wright" each break a different
    last-word heuristic, and the heuristic in `discovery/artic.py` documents its
    own unreliability. So the parts are stored facts, supplied by whoever knows,
    and an artist who has neither is set unstyled under `name` rather than split
    by a guess. Both parts are optional because the corpus holds records that are
    not people at all — a culture, a workshop, an anonymous master.
    """

    id: str
    name: str
    nationality: str | None = None
    born: int | None = None
    died: int | None = None
    lifespan_text: str | None = None
    biography: str | None = None
    family_name: str | None = None
    given_name: str | None = None
    #: The short form of `nationality` the e-paper label sets, when the recorded
    #: one is too long or too discursive for a wall label. Null means the label
    #: uses `nationality` unchanged. A *display* form and not a correction: the
    #: recorded string is the provenance and stays whatever the institution
    #: printed.
    display_nationality: str | None = None


@dataclass(frozen=True, slots=True)
class Artwork:
    """The canonical record of a work.

    `id` is a stable internal identity and is never derived from a source URL:
    a museum reorganising its site must not break a work's identity, and the
    same painting held by two institutions must not become two records.

    `date_created` is free text on purpose. Sources give "1931", "c. 1650",
    and "1888-89"; normalising those to a date type would destroy the
    distinction between a known year and an estimated one.

    **`description` and `commentary` are different texts and neither substitutes
    for the other.** `description` is the holding institution's own paragraph,
    arriving with the record at whatever length it was written; `commentary` is a
    line meant to be read on a wall label at standing distance. Rendering the
    first where the second belongs would put several hundred words on a 6-inch
    panel, so a label that wanted a sentence had to have one written for it.
    """

    id: str
    title: str
    created_at: datetime
    status: ArtworkStatus = ArtworkStatus.ACCEPTED
    artist_id: str | None = None
    date_created: str | None = None
    medium: str | None = None
    dimensions: str | None = None
    description: str | None = None
    rights: str | None = None
    accepted_at: datetime | None = None
    commentary: str | None = None


@dataclass(frozen=True, slots=True)
class WorkFacet:
    """What a work *is*, in the same typed vocabulary the curator's taste is expressed in.

    Many per work, unique on (`artwork_id`, `kind`, `value`): a work is Baroque
    once. The uniqueness is not decoration — the facet counts a curator reads off
    the collection are a plain `COUNT(*)` per value, and a second Baroque row on
    one work would inflate every one of them.

    **`era` sits BESIDE `Artwork.date_created`, never over it.** `date_created` is
    free text — "1931", "c. 1650", "1888-89" — because normalising would destroy
    the distinction between a known year and an estimated one, and that decision
    stands. An era facet is an additional, coarser, *lossy* reading of the same
    fact, kept here where its derivation is recorded: the free text stays the
    evidence and the facet is only the index. A surface showing "Late 19th c."
    must still be able to show "1888-89".
    """

    id: str
    artwork_id: str
    kind: VocabularyKind
    value: str
    derivation: FacetDerivation
    created_at: datetime
    #: For `SOURCED`, which field of which provider — e.g. `artic:classification_title`.
    #: For `INFERRED`, the model id. Null where nobody recorded it, which is
    #: honest rather than tidy.
    source_note: str | None = None


@dataclass(frozen=True, slots=True)
class Source:
    """A place a work can be obtained from.

    Many per work, deliberately. A work held by several institutions keeps
    working when one of them reorganises its site, which is what makes
    re-acquisition from scratch a real promise rather than a hope. The URL is an
    attribute of the attempt and never an identity.
    """

    id: str
    artwork_id: str
    url: str
    provider: str
    source_class: SourceClass
    acquisition_method: AcquisitionMethod
    rights_status: RightsStatus
    is_primary: bool = False
    confidence: float | None = None
    selection_rationale: str | None = None
    last_fetch_status: FetchStatus | None = None
    last_fetched_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class Original:
    """The acquired master image — one per work.

    Upstream and expensive: this is the half of the art tree that a sync carries
    and that nothing regenerates. `content_hash` identifies the bytes, which is
    what lets a rendition tell whether the image it was made from is still the
    image the work has.
    """

    id: str
    artwork_id: str
    source_id: str
    relative_path: str
    width: int
    height: int
    byte_size: int
    content_hash: str
    #: How the fetch that produced *these bytes* ended — `OK` or `PARTIAL_TILES`.
    #: A fact about a past event, not a verdict about a deployment, which is why
    #: it is stored where `display_fit` deliberately is not.
    #:
    #: It cannot be read off `Source.last_fetch_status` instead: that column holds
    #: the source's *most recent* attempt, and one failed re-fetch overwrites it to
    #: `FAILED` while the held original — protected by staging — is still the
    #: complete image from before. A caller comparing against it would read "held
    #: quality: failed", conclude anything is an improvement, and let a partial
    #: overwrite a complete master.
    #:
    #: `None` means the row was written before this field existed. Callers
    #: comparing quality must treat that as complete: the rows cannot be told
    #: apart, and the permissive reading loses images for exactly the oldest ones.
    #: `FAILED` is unreachable here — a failed fetch produces no bytes to record.
    fetch_status: FetchStatus | None = None


@dataclass(frozen=True, slots=True)
class Rendition:
    """A derived output, regenerated rather than transported.

    Target geometry is columns rather than a filename suffix. The 2024 design
    encoded it as `_w648_h480` in the name, which is why the recovered catalogue
    points at a panel that no longer exists — and a suffix cannot be queried, so
    "which renditions exist for this geometry" had no answer at all.
    """

    id: str
    artwork_id: str
    kind: RenditionKind
    target_width: int
    target_height: int
    relative_path: str
    source_content_hash: str
    generated_at: datetime


def is_current(rendition: Rendition, original: Original | None) -> bool:
    """Whether a derived output still stands for the image the work holds.

    **The one place this question is answered.** It decides what a review card
    badges, what a thumbnail is made from, and whether a work reaches the wall
    or is excluded as `STALE_RENDITION` — three surfaces that must not be able
    to disagree. They did: the rule was written twice, once here in substance
    and once inline in the manifest builder, so a change to what "current" means
    would have landed in one and left the other deciding manifest membership by
    the old rule. The grid would badge a work green while the wall silently
    dropped it, which is exactly the shortfall the exclusion report exists to
    make visible, arriving by the one path that did not consult the shared rule.

    **What it deliberately does not answer: whether a rendition drawn from
    another rendition is current.** This compares against the *original*, which
    is the right parent for every kind but one — a thumbnail of a work that has a
    television canvas is a copy of the canvas, and composing or recomposing that
    canvas leaves the original untouched. So this rule says "current" about a
    cached thumbnail of an image that has since been redrawn, and it is right to:
    the question it is asked is about the master. `ThumbnailService._drawn_from`
    asks the other one. Do not fold it in here — three surfaces share this rule
    precisely so they cannot disagree, and a term only one of them can evaluate
    would break that.

    A work holding no original at all has nothing that could vouch for any
    rendition, so none of them may be served on the strength of having once been
    generated. That is not the same as a mismatch and it is deliberately not
    reported differently — in both cases the render cannot be trusted to be a
    picture of what the work now holds.

    Derived on every read rather than stored, so it cannot drift from the
    original it is a statement about.
    """
    if original is None:
        return False
    return rendition.source_content_hash == original.content_hash


def tv_renditions_newest_first(renditions: Sequence[Rendition]) -> list[Rendition]:
    """Every television render for a work, in the order any consumer prefers them.

    **The one place that preference is expressed**, for the same reason
    `is_current` is: the manifest builder took the most recently generated row
    while the thumbnail service took the first current one the store happened to
    return, and the unique index is on `(artwork_id, kind, target_width,
    target_height)` — so two television renders at different geometries are
    reachable, and on that work the wall and the card would have shown different
    pictures with nothing saying which was right.

    Newest first, tie broken by id so the order is total and a rebuild cannot
    reshuffle two renders generated in the same instant. Currency is *not*
    filtered here: the manifest has to be able to tell a work rendered from an
    older acquisition (`STALE_RENDITION`, "needs regenerating") from one never
    rendered at all (`NO_RENDITION`), and a filter would collapse the two into
    the second and tell a curator the opposite of what happened.
    """
    return sorted(
        (rendition for rendition in renditions if rendition.kind is RenditionKind.TV_DISPLAY),
        key=lambda rendition: (rendition.generated_at, rendition.id),
        reverse=True,
    )


@dataclass(frozen=True, slots=True)
class MatColor:
    """A mat colour chosen for a work, and how it was chosen.

    Superseded choices are retained rather than overwritten: mat quality is this
    product's subjective quality bar, so "the new model picked a worse colour"
    has to be both answerable and reversible.
    """

    id: str
    artwork_id: str
    hex_rgb: str
    method: MatMethod
    chosen_at: datetime
    is_current: bool = True
    lab_l: float | None = None
    lab_a: float | None = None
    lab_b: float | None = None
    reason: str | None = None
    model_id: str | None = None


@dataclass(frozen=True, slots=True)
class ThemeMembership:
    """One work's place in one theme.

    An explicit join rather than an implicit set, so that order can be curated.
    A null `position` means the curator has expressed no order for this entry.
    """

    theme_id: str
    artwork_id: str
    added_at: datetime
    position: int | None = None


@dataclass(frozen=True, slots=True)
class Theme:
    """A curator's grouping of works, and the unit a wall rotates through.

    **Global, and hung rather than activated.** This record carried an
    `is_active` boolean until 2026-08-12, which could only ever mean "active on
    the one television" — the single-wall assumption written into the noun. What
    is hanging where is `ThemeAssignment`'s to say, so two walls may hang the
    same theme with nothing duplicated.

    Rotation is host-driven — the TV's own slideshow can only be scoped to a
    whole category, so timing is this product's data rather than the television's
    setting. It is per-theme so that a contemplative theme can breathe while a
    busy one moves; null on either field means "inherit the global default",
    which is why neither is required.
    """

    id: str
    name: str
    created_at: datetime
    description: str | None = None
    rotation_interval_seconds: int | None = None
    shuffle: bool | None = None


@dataclass(frozen=True, slots=True)
class Wall:
    """A place where art hangs. One display serves one wall.

    **Three fields, and the shortness is the design.** A wall is an identity and
    a name; it is not a device. Geometry, network address, panel model, TV
    content ids, upload state, reachability and last-heartbeat are all per-device
    runtime state and are permanently forbidden here — they belong to the display
    plane's own store or to the configuration both planes read. Which display
    serves which wall is display-plane configuration, exactly as `TV_ADDRESS`
    already is.

    That this record lives in the catalogue at all is a ruling against
    `data-model.md`'s "per-device runtime state never lives in the catalogue"
    rather than an oversight: a wall is a *place* and its name is a *curatorial*
    fact, and assigning a theme to it is a curatorial act, which is precisely why
    it cannot live on the display side where the curator cannot reach it.
    Replace the television and the wall persists, keeps its name and keeps its
    theme — where a design keying assignment on a device would lose the curation
    along with the device.
    """

    id: str
    name: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ThemeAssignment:
    """What is hanging on one wall — the act the interface calls *hanging*.

    **`wall_id` alone is the primary key, which is what makes "one theme per
    wall" structural.** The predecessor needed a partial unique index over
    `Theme.is_active` plus a reconciliation pass to approximate it, and this
    product has already been bitten once by reading that arrangement as an
    absolute it never enforced. Nothing here has to claim anything: a second
    theme on a wall is not a violation to detect, it is a row that cannot be
    inserted.

    **A wall with no row hangs nothing, and that is an ordinary state** — an
    empty catalogue, or a curator who took everything down.
    """

    wall_id: str
    theme_id: str
    assigned_at: datetime


@dataclass(frozen=True, slots=True)
class Directive:
    """One wall's standing instruction to the display plane, held catalogue-side.

    The display plane is reached only through the theme manifest, so an
    interactive command — "show this work now", "step to the next one" — travels
    as state rather than as a message: a monotonically increasing sequence, plus
    an optional work the sequence's advance points at. Display acts once each
    time it observes the sequence advance.

    **One row per wall, seeded when the wall is created so no caller ever has to
    make it.** This was a singleton until 2026-08-12, and a `next` aimed at the
    living room would otherwise have stepped every wall in the house: one counter
    cannot say which display an advance was meant for.

    The counter lives here, in the catalogue, because a manifest rebuild must
    carry it forward unchanged. A counter derived from the manifest would reset
    whenever the manifest was rewritten, and a reset reads to the display plane
    as an advance — firing a directive nobody issued. It stays *per wall* rather
    than per theme for the same reason: it has to survive theme switching.
    """

    wall_id: str
    sequence: int
    pinned_work_id: str | None = None


@dataclass(frozen=True, slots=True)
class ArtworkPage:
    """One page of works plus the size of the set it was drawn from.

    `total` is what lets a caller say "showing 20 of 84" instead of silently
    handing back a short list.
    """

    artworks: Sequence[Artwork]
    total: int
