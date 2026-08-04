"""A `CatalogueStore` over a SQLite file.

SQLite was chosen because it has no dependency to resolve, no server to run, and
a file that can be copied to a backup and back again — which is how this
catalogue's restore path is meant to work.

This module is one domain adapter over that file: it owns the catalogue's
tables, the mapping between its records and rows, and the ordering and paging
decisions that make a listing stable. Everything about connections, statements,
locking and constraint translation lives in `durable.py`, and what every adapter
does identically lives in `adapter.py` — so what remains here reads as the
catalogue rather than as SQL plumbing. `sqlite_discovery.py` is the other
adapter, over the same open file.

Ordering is decided here rather than below because it is a product judgement, not
a storage one: title is what a curator scans by, and id breaks ties so that the
same page request never comes back in a different order.

**The unique indexes below do not replace the service layer's rules.** Every
catalogue rule is applied in the service layer, where a refusal can be phrased for
whoever asked; a partial index here catches the case where some path forgets to,
and its message names only the table. Enforcement in two places would be a defect
if they could disagree — they cannot, because the index is strictly the weaker
statement of the same rule.
"""

from collections.abc import Mapping, Sequence
from typing import Any, Final

from curation.persistence.adapter import BY_ID, TableAdapter, from_iso, require_datetime, to_iso
from curation.persistence.catalogue import StorageError
from curation.persistence.durable import OrderBy
from curation.persistence.records import (
    AcquisitionMethod,
    Artist,
    Artwork,
    ArtworkPage,
    ArtworkStatus,
    Directive,
    FetchStatus,
    MatColor,
    MatMethod,
    Original,
    Rendition,
    RenditionKind,
    RightsStatus,
    Source,
    SourceClass,
    Theme,
    ThemeMembership,
)

CATALOGUE_SCHEMA = """
CREATE TABLE IF NOT EXISTS artists (
    id             TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    nationality    TEXT,
    born           INTEGER,
    died           INTEGER,
    lifespan_text  TEXT,
    biography      TEXT
);

CREATE TABLE IF NOT EXISTS artworks (
    id            TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    artist_id     TEXT REFERENCES artists(id),
    date_created  TEXT,
    medium        TEXT,
    dimensions    TEXT,
    description   TEXT,
    rights        TEXT,
    status        TEXT NOT NULL,
    accepted_at   TEXT,
    created_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS artworks_by_status ON artworks(status);

-- `rotation_interval_seconds` and `shuffle` are nullable because null means
-- "inherit the global default" rather than "unset": a theme that has never
-- expressed a pace is a normal theme, not an incomplete one.
CREATE TABLE IF NOT EXISTS themes (
    id                        TEXT PRIMARY KEY,
    name                      TEXT NOT NULL UNIQUE,
    description               TEXT,
    is_active                 INTEGER NOT NULL,
    created_at                TEXT NOT NULL,
    rotation_interval_seconds INTEGER,
    shuffle                   INTEGER
);

-- The display plane's sync target has to be unambiguous, so no two themes may
-- claim it at once.
CREATE UNIQUE INDEX IF NOT EXISTS themes_one_active ON themes(is_active) WHERE is_active = 1;

CREATE TABLE IF NOT EXISTS sources (
    id                   TEXT PRIMARY KEY,
    artwork_id           TEXT NOT NULL REFERENCES artworks(id),
    url                  TEXT NOT NULL,
    provider             TEXT NOT NULL,
    source_class         TEXT NOT NULL,
    acquisition_method   TEXT NOT NULL,
    rights_status        TEXT NOT NULL,
    is_primary           INTEGER NOT NULL,
    confidence           REAL,
    selection_rationale  TEXT,
    last_fetch_status    TEXT,
    last_fetched_at      TEXT
);

CREATE INDEX IF NOT EXISTS sources_by_artwork ON sources(artwork_id);

-- Which source produced the held original is a single fact about the work.
CREATE UNIQUE INDEX IF NOT EXISTS sources_one_primary ON sources(artwork_id) WHERE is_primary = 1;

CREATE TABLE IF NOT EXISTS originals (
    id             TEXT PRIMARY KEY,
    artwork_id     TEXT NOT NULL UNIQUE REFERENCES artworks(id),
    source_id      TEXT NOT NULL REFERENCES sources(id),
    relative_path  TEXT NOT NULL,
    width          INTEGER NOT NULL,
    height         INTEGER NOT NULL,
    -- A zero-byte file is the 2024 pipeline's known download failure. The
    -- catalogue must not be able to record one as a held original.
    byte_size      INTEGER NOT NULL CHECK (byte_size > 0),
    content_hash   TEXT NOT NULL,
    -- How the fetch that produced these bytes ended. Nullable, because the column
    -- was added to a table that already had rows on disk and the widening step
    -- can only add columns that allow NULL — a null here means "written before
    -- this was recorded", which readers treat as complete rather than as partial.
    fetch_status   TEXT
);

CREATE TABLE IF NOT EXISTS renditions (
    id                   TEXT PRIMARY KEY,
    artwork_id           TEXT NOT NULL REFERENCES artworks(id),
    kind                 TEXT NOT NULL,
    target_width         INTEGER NOT NULL,
    target_height        INTEGER NOT NULL,
    relative_path        TEXT NOT NULL,
    source_content_hash  TEXT NOT NULL,
    generated_at         TEXT NOT NULL
);

-- One rendition per work per kind per geometry: a second row for the same
-- target is two answers to "is this current", and only one of them is right.
CREATE UNIQUE INDEX IF NOT EXISTS renditions_by_geometry
    ON renditions(artwork_id, kind, target_width, target_height);

CREATE TABLE IF NOT EXISTS mat_colors (
    id          TEXT PRIMARY KEY,
    artwork_id  TEXT NOT NULL REFERENCES artworks(id),
    hex_rgb     TEXT NOT NULL,
    method      TEXT NOT NULL,
    is_current  INTEGER NOT NULL,
    lab_l       REAL,
    lab_a       REAL,
    lab_b       REAL,
    reason      TEXT,
    model_id    TEXT,
    chosen_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS mat_colors_by_artwork ON mat_colors(artwork_id);

-- Superseded choices stay; exactly one of them is the one in force.
CREATE UNIQUE INDEX IF NOT EXISTS mat_colors_one_current ON mat_colors(artwork_id) WHERE is_current = 1;

CREATE TABLE IF NOT EXISTS theme_memberships (
    theme_id    TEXT NOT NULL REFERENCES themes(id),
    artwork_id  TEXT NOT NULL REFERENCES artworks(id),
    position    INTEGER,
    added_at    TEXT NOT NULL,
    PRIMARY KEY (theme_id, artwork_id)
);

CREATE INDEX IF NOT EXISTS theme_memberships_by_artwork ON theme_memberships(artwork_id);

-- One row, always. The display plane's standing directive is a property of the
-- catalogue rather than of any theme, because the sequence has to survive every
-- manifest rebuild and every theme switch to stay monotonic.
CREATE TABLE IF NOT EXISTS directive (
    id              INTEGER PRIMARY KEY CHECK (id = 1),
    sequence        INTEGER NOT NULL,
    pinned_work_id  TEXT REFERENCES artworks(id)
);

INSERT OR IGNORE INTO directive (id, sequence, pinned_work_id) VALUES (1, 0, NULL);
"""

#: The join's own key. A work appears at most once in a theme.
_MEMBERSHIP_KEY: Final[tuple[str, ...]] = ("theme_id", "artwork_id")

#: The singleton directive row's key, which is the same value forever.
_DIRECTIVE_KEY: Final[Mapping[str, Any]] = {"id": 1}

#: What a curator scans by, then a tie-break that makes paging repeatable.
_BY_TITLE: Final[tuple[OrderBy, ...]] = (OrderBy("title", ignore_case=True), OrderBy("id"))
_BY_NAME: Final[tuple[OrderBy, ...]] = (OrderBy("name", ignore_case=True), OrderBy("id"))

#: The source that produced the held original leads; the rest are alternates.
_BY_PRIMARY: Final[tuple[OrderBy, ...]] = (
    OrderBy("is_primary", descending=True),
    OrderBy("url", ignore_case=True),
    OrderBy("id"),
)

#: Grouped by what the output is for, then by how big it is.
_BY_GEOMETRY: Final[tuple[OrderBy, ...]] = (
    OrderBy("kind"),
    OrderBy("target_width"),
    OrderBy("target_height"),
    OrderBy("id"),
)

#: Newest first, because a mat colour list is a history and the current choice
#: is the one at the top of it.
_BY_RECENCY: Final[tuple[OrderBy, ...]] = (OrderBy("chosen_at", descending=True), OrderBy("id"))

#: Curated order, with the entries nobody placed after the ones somebody did.
_BY_POSITION: Final[tuple[OrderBy, ...]] = (
    OrderBy("position", nulls_last=True),
    OrderBy("added_at"),
    OrderBy("artwork_id"),
)


class SqliteCatalogue(TableAdapter):
    """The catalogue's own tables, mapped to its records."""

    # -- artists --------------------------------------------------------------

    def add_artist(self, artist: Artist) -> None:
        self._add("artists", _artist_row(artist), subject=f"artist {artist.id!r}")

    def get_artist(self, artist_id: str) -> Artist | None:
        return self._get("artists", {"id": artist_id}, _artist)

    def list_artists(self) -> Sequence[Artist]:
        return self._list("artists", None, _BY_NAME, _artist)

    # -- artworks -------------------------------------------------------------

    def add_artwork(self, artwork: Artwork) -> None:
        self._add("artworks", _artwork_row(artwork), subject=f"artwork {artwork.id!r}")

    def get_artwork(self, artwork_id: str) -> Artwork | None:
        return self._get("artworks", {"id": artwork_id}, _artwork)

    def update_artwork(self, artwork: Artwork) -> None:
        self._update("artworks", BY_ID, _artwork_row(artwork), subject=f"artwork {artwork.id!r}")

    def list_artworks(self, *, status: ArtworkStatus | None, limit: int, offset: int) -> ArtworkPage:
        rows, total = self._store.select_page(
            "artworks",
            order_by=_BY_TITLE,
            filters=None if status is None else {"status": str(status)},
            limit=limit,
            offset=offset,
        )
        return ArtworkPage(artworks=[_artwork(row) for row in rows], total=total)

    # -- sources --------------------------------------------------------------

    def add_source(self, source: Source) -> None:
        self._add("sources", _source_row(source), subject=f"source {source.id!r}")

    def get_source(self, source_id: str) -> Source | None:
        return self._get("sources", {"id": source_id}, _source)

    def update_source(self, source: Source) -> None:
        self._update("sources", BY_ID, _source_row(source), subject=f"source {source.id!r}")

    def list_sources(self, artwork_id: str) -> Sequence[Source]:
        return self._list("sources", {"artwork_id": artwork_id}, _BY_PRIMARY, _source)

    # -- originals ------------------------------------------------------------

    def add_original(self, original: Original) -> None:
        self._add("originals", _original_row(original), subject=f"original for artwork {original.artwork_id!r}")

    def get_original(self, artwork_id: str) -> Original | None:
        # Addressed by the work rather than by its own id: one work holds at most
        # one original, and every caller arrives holding the work.
        rows = self._store.scan("originals", {"artwork_id": artwork_id})
        return _original(rows[0]) if rows else None

    def update_original(self, original: Original) -> None:
        self._update("originals", BY_ID, _original_row(original), subject=f"original for artwork {original.artwork_id!r}")

    # -- renditions -----------------------------------------------------------

    def add_rendition(self, rendition: Rendition) -> None:
        self._add("renditions", _rendition_row(rendition), subject=f"rendition {rendition.id!r}")

    def update_rendition(self, rendition: Rendition) -> None:
        self._update("renditions", BY_ID, _rendition_row(rendition), subject=f"rendition {rendition.id!r}")

    def list_renditions(self, artwork_id: str) -> Sequence[Rendition]:
        return self._list("renditions", {"artwork_id": artwork_id}, _BY_GEOMETRY, _rendition)

    # -- mat colours ----------------------------------------------------------

    def add_mat_color(self, mat_color: MatColor) -> None:
        self._add("mat_colors", _mat_color_row(mat_color), subject=f"mat colour {mat_color.id!r}")

    def update_mat_color(self, mat_color: MatColor) -> None:
        self._update("mat_colors", BY_ID, _mat_color_row(mat_color), subject=f"mat colour {mat_color.id!r}")

    def list_mat_colors(self, artwork_id: str) -> Sequence[MatColor]:
        return self._list("mat_colors", {"artwork_id": artwork_id}, _BY_RECENCY, _mat_color)

    # -- themes ---------------------------------------------------------------

    def add_theme(self, theme: Theme) -> None:
        self._add("themes", _theme_row(theme), subject=f"theme {theme.id!r}")

    def get_theme(self, theme_id: str) -> Theme | None:
        return self._get("themes", {"id": theme_id}, _theme)

    def update_theme(self, theme: Theme) -> None:
        self._update("themes", BY_ID, _theme_row(theme), subject=f"theme {theme.id!r}")

    def list_themes(self) -> Sequence[Theme]:
        return self._list("themes", None, _BY_NAME, _theme)

    def remove_theme(self, theme_id: str) -> None:
        self._store.delete("themes", {"id": theme_id})

    # -- theme membership -----------------------------------------------------

    def add_membership(self, membership: ThemeMembership) -> None:
        self._add(
            "theme_memberships",
            _membership_row(membership),
            subject=f"artwork {membership.artwork_id!r} in theme {membership.theme_id!r}",
            key=_MEMBERSHIP_KEY,
        )

    def get_membership(self, theme_id: str, artwork_id: str) -> ThemeMembership | None:
        return self._get("theme_memberships", {"theme_id": theme_id, "artwork_id": artwork_id}, _membership)

    def update_membership(self, membership: ThemeMembership) -> None:
        self._update(
            "theme_memberships",
            _MEMBERSHIP_KEY,
            _membership_row(membership),
            subject=f"artwork {membership.artwork_id!r} in theme {membership.theme_id!r}",
        )

    def remove_membership(self, theme_id: str, artwork_id: str) -> None:
        self._store.delete("theme_memberships", {"theme_id": theme_id, "artwork_id": artwork_id})

    def list_memberships(self, theme_id: str) -> Sequence[ThemeMembership]:
        return self._list("theme_memberships", {"theme_id": theme_id}, _BY_POSITION, _membership)

    # -- the display directive ------------------------------------------------

    def get_directive(self) -> Directive:
        row = self._store.fetch_one("directive", _DIRECTIVE_KEY)
        if row is None:
            # The schema seeds this row when the file is created, so its absence
            # means the file was edited by something other than this code.
            raise StorageError("The catalogue has no display directive row.")
        return Directive(sequence=row["sequence"], pinned_work_id=row["pinned_work_id"])

    def set_directive(self, directive: Directive) -> None:
        self._update(
            "directive",
            BY_ID,
            {**_DIRECTIVE_KEY, "sequence": directive.sequence, "pinned_work_id": directive.pinned_work_id},
            subject="the display directive",
        )


# -- record to row ------------------------------------------------------------


def _artist_row(artist: Artist) -> dict[str, Any]:
    return {
        "id": artist.id,
        "name": artist.name,
        "nationality": artist.nationality,
        "born": artist.born,
        "died": artist.died,
        "lifespan_text": artist.lifespan_text,
        "biography": artist.biography,
    }


def _artwork_row(artwork: Artwork) -> dict[str, Any]:
    return {
        "id": artwork.id,
        "title": artwork.title,
        "artist_id": artwork.artist_id,
        "date_created": artwork.date_created,
        "medium": artwork.medium,
        "dimensions": artwork.dimensions,
        "description": artwork.description,
        "rights": artwork.rights,
        "status": str(artwork.status),
        "accepted_at": to_iso(artwork.accepted_at),
        "created_at": to_iso(artwork.created_at),
    }


def _source_row(source: Source) -> dict[str, Any]:
    return {
        "id": source.id,
        "artwork_id": source.artwork_id,
        "url": source.url,
        "provider": source.provider,
        "source_class": str(source.source_class),
        "acquisition_method": str(source.acquisition_method),
        "rights_status": str(source.rights_status),
        "is_primary": int(source.is_primary),
        "confidence": source.confidence,
        "selection_rationale": source.selection_rationale,
        "last_fetch_status": None if source.last_fetch_status is None else str(source.last_fetch_status),
        "last_fetched_at": to_iso(source.last_fetched_at),
    }


def _original_row(original: Original) -> dict[str, Any]:
    return {
        "id": original.id,
        "artwork_id": original.artwork_id,
        "source_id": original.source_id,
        "relative_path": original.relative_path,
        "width": original.width,
        "height": original.height,
        "byte_size": original.byte_size,
        "content_hash": original.content_hash,
        "fetch_status": None if original.fetch_status is None else original.fetch_status.value,
    }


def _rendition_row(rendition: Rendition) -> dict[str, Any]:
    return {
        "id": rendition.id,
        "artwork_id": rendition.artwork_id,
        "kind": str(rendition.kind),
        "target_width": rendition.target_width,
        "target_height": rendition.target_height,
        "relative_path": rendition.relative_path,
        "source_content_hash": rendition.source_content_hash,
        "generated_at": to_iso(rendition.generated_at),
    }


def _mat_color_row(mat_color: MatColor) -> dict[str, Any]:
    return {
        "id": mat_color.id,
        "artwork_id": mat_color.artwork_id,
        "hex_rgb": mat_color.hex_rgb,
        "method": str(mat_color.method),
        "is_current": int(mat_color.is_current),
        "lab_l": mat_color.lab_l,
        "lab_a": mat_color.lab_a,
        "lab_b": mat_color.lab_b,
        "reason": mat_color.reason,
        "model_id": mat_color.model_id,
        "chosen_at": to_iso(mat_color.chosen_at),
    }


def _theme_row(theme: Theme) -> dict[str, Any]:
    return {
        "id": theme.id,
        "name": theme.name,
        "description": theme.description,
        "is_active": int(theme.is_active),
        "created_at": to_iso(theme.created_at),
        "rotation_interval_seconds": theme.rotation_interval_seconds,
        # None survives as null — "inherit the global default" — where int(None)
        # would raise and bool(None) would silently write a decision the curator
        # never made.
        "shuffle": None if theme.shuffle is None else int(theme.shuffle),
    }


def _membership_row(membership: ThemeMembership) -> dict[str, Any]:
    return {
        "theme_id": membership.theme_id,
        "artwork_id": membership.artwork_id,
        "position": membership.position,
        "added_at": to_iso(membership.added_at),
    }


# -- row to record ------------------------------------------------------------


def _artist(row: Mapping[str, Any]) -> Artist:
    return Artist(
        id=row["id"],
        name=row["name"],
        nationality=row["nationality"],
        born=row["born"],
        died=row["died"],
        lifespan_text=row["lifespan_text"],
        biography=row["biography"],
    )


def _artwork(row: Mapping[str, Any]) -> Artwork:
    return Artwork(
        id=row["id"],
        title=row["title"],
        created_at=require_datetime(row["created_at"], "created_at"),
        status=ArtworkStatus(row["status"]),
        artist_id=row["artist_id"],
        date_created=row["date_created"],
        medium=row["medium"],
        dimensions=row["dimensions"],
        description=row["description"],
        rights=row["rights"],
        accepted_at=from_iso(row["accepted_at"]),
    )


def _source(row: Mapping[str, Any]) -> Source:
    return Source(
        id=row["id"],
        artwork_id=row["artwork_id"],
        url=row["url"],
        provider=row["provider"],
        source_class=SourceClass(row["source_class"]),
        acquisition_method=AcquisitionMethod(row["acquisition_method"]),
        rights_status=RightsStatus(row["rights_status"]),
        is_primary=bool(row["is_primary"]),
        confidence=row["confidence"],
        selection_rationale=row["selection_rationale"],
        last_fetch_status=None if row["last_fetch_status"] is None else FetchStatus(row["last_fetch_status"]),
        last_fetched_at=from_iso(row["last_fetched_at"]),
    )


def _original(row: Mapping[str, Any]) -> Original:
    return Original(
        id=row["id"],
        artwork_id=row["artwork_id"],
        source_id=row["source_id"],
        relative_path=row["relative_path"],
        width=row["width"],
        height=row["height"],
        byte_size=row["byte_size"],
        content_hash=row["content_hash"],
        # `.get`, not `[...]`: a catalogue file written before this column existed
        # is widened on open, but a row read through a mapping built from an older
        # file's columns would raise KeyError where the contract is "unrecorded".
        fetch_status=None if row.get("fetch_status") is None else FetchStatus(row["fetch_status"]),
    )


def _rendition(row: Mapping[str, Any]) -> Rendition:
    return Rendition(
        id=row["id"],
        artwork_id=row["artwork_id"],
        kind=RenditionKind(row["kind"]),
        target_width=row["target_width"],
        target_height=row["target_height"],
        relative_path=row["relative_path"],
        source_content_hash=row["source_content_hash"],
        generated_at=require_datetime(row["generated_at"], "generated_at"),
    )


def _mat_color(row: Mapping[str, Any]) -> MatColor:
    return MatColor(
        id=row["id"],
        artwork_id=row["artwork_id"],
        hex_rgb=row["hex_rgb"],
        method=MatMethod(row["method"]),
        chosen_at=require_datetime(row["chosen_at"], "chosen_at"),
        is_current=bool(row["is_current"]),
        lab_l=row["lab_l"],
        lab_a=row["lab_a"],
        lab_b=row["lab_b"],
        reason=row["reason"],
        model_id=row["model_id"],
    )


def _theme(row: Mapping[str, Any]) -> Theme:
    return Theme(
        id=row["id"],
        name=row["name"],
        created_at=require_datetime(row["created_at"], "created_at"),
        description=row["description"],
        is_active=bool(row["is_active"]),
        rotation_interval_seconds=row["rotation_interval_seconds"],
        shuffle=None if row["shuffle"] is None else bool(row["shuffle"]),
    )


def _membership(row: Mapping[str, Any]) -> ThemeMembership:
    return ThemeMembership(
        theme_id=row["theme_id"],
        artwork_id=row["artwork_id"],
        added_at=require_datetime(row["added_at"], "added_at"),
        position=row["position"],
    )
