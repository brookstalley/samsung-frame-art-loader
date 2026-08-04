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


@dataclass(frozen=True, slots=True)
class Artist:
    """A person a work is attributed to.

    Separate from the work so the physical label can render nationality and
    lifespan without re-parsing a blob, and so two works by the same artist
    agree about them.
    """

    id: str
    name: str
    nationality: str | None = None
    born: int | None = None
    died: int | None = None
    lifespan_text: str | None = None
    biography: str | None = None


@dataclass(frozen=True, slots=True)
class Artwork:
    """The canonical record of a work.

    `id` is a stable internal identity and is never derived from a source URL:
    a museum reorganising its site must not break a work's identity, and the
    same painting held by two institutions must not become two records.

    `date_created` is free text on purpose. Sources give "1931", "c. 1650",
    and "1888-89"; normalising those to a date type would destroy the
    distinction between a known year and an estimated one.
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
    """A curator's grouping of works, and the unit the wall rotates through.

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
    is_active: bool = False
    rotation_interval_seconds: int | None = None
    shuffle: bool | None = None


@dataclass(frozen=True, slots=True)
class Directive:
    """The standing instruction the display plane acts on, held catalogue-side.

    The display plane is reached only through the theme manifest, so an
    interactive command — "show this work now", "step to the next one" — travels
    as state rather than as a message: a monotonically increasing sequence, plus
    an optional work the sequence's advance points at. Display acts once each
    time it observes the sequence advance.

    The counter lives here, in the catalogue, because a manifest rebuild must
    carry it forward unchanged. A counter derived from the manifest would reset
    whenever the manifest was rewritten, and a reset reads to the display plane
    as an advance — firing a directive nobody issued.
    """

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
