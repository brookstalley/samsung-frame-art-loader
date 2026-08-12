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
from curation.persistence.durable import OrderBy
from curation.persistence.errors import StorageError
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
    ThemeAssignment,
    ThemeMembership,
    Wall,
)

CATALOGUE_SCHEMA = """
-- `family_name` and `given_name` are nullable because a record that is not a
-- person — a culture, a workshop, an anonymous master — has neither, and
-- because a file written before they existed has neither either. Both cases
-- read the same way downstream and are meant to: the label falls back to `name`
-- rather than splitting one by a rule that is wrong for "van Gogh".
CREATE TABLE IF NOT EXISTS artists (
    id             TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    nationality    TEXT,
    born           INTEGER,
    died           INTEGER,
    lifespan_text  TEXT,
    biography      TEXT,
    family_name    TEXT,
    given_name     TEXT
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
    created_at    TEXT NOT NULL,
    commentary    TEXT
);

CREATE INDEX IF NOT EXISTS artworks_by_status ON artworks(status);

-- `rotation_interval_seconds` and `shuffle` are nullable because null means
-- "inherit the global default" rather than "unset": a theme that has never
-- expressed a pace is a normal theme, not an incomplete one.
--
-- A theme is global: nothing here says where it is hanging. `is_active` and its
-- `themes_one_active` partial index were dropped on 2026-08-12, when hanging
-- became an act against a named wall; `migrations.py` carries the file that
-- still has them.
CREATE TABLE IF NOT EXISTS themes (
    id                        TEXT PRIMARY KEY,
    name                      TEXT NOT NULL UNIQUE,
    description               TEXT,
    created_at                TEXT NOT NULL,
    rotation_interval_seconds INTEGER,
    shuffle                   INTEGER
);

-- A place where art hangs, and nothing about the device that serves it. The
-- forbidden columns are listed on the `Wall` record; the rule is that this table
-- must survive its television being replaced.
CREATE TABLE IF NOT EXISTS walls (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL
);

-- What is hanging on one wall. `wall_id` alone is the key, so "at most one theme
-- per wall" is the key rather than a rule anything has to check: a second theme
-- on a wall is a row that cannot be inserted. A wall with no row hangs nothing,
-- which is an ordinary state.
CREATE TABLE IF NOT EXISTS theme_assignments (
    wall_id      TEXT PRIMARY KEY REFERENCES walls(id),
    theme_id     TEXT NOT NULL REFERENCES themes(id),
    assigned_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS theme_assignments_by_theme ON theme_assignments(theme_id);

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

-- One row per wall, seeded when the wall is created so no caller ever has to
-- make one. The standing directive is a property of the *wall* rather than of
-- any theme, because the sequence has to survive every manifest rebuild and
-- every theme switch to stay monotonic — and a singleton, which is what this
-- was until 2026-08-12, cannot say which display an advance was meant for.
CREATE TABLE IF NOT EXISTS directives (
    wall_id         TEXT PRIMARY KEY REFERENCES walls(id),
    sequence        INTEGER NOT NULL,
    pinned_work_id  TEXT REFERENCES artworks(id)
);

CREATE INDEX IF NOT EXISTS directives_by_pin ON directives(pinned_work_id);
"""

#: The join's own key. A work appears at most once in a theme.
_MEMBERSHIP_KEY: Final[tuple[str, ...]] = ("theme_id", "artwork_id")

#: Both tables that hang off a wall are keyed by it alone, which is what makes
#: "one theme per wall" and "one directive per wall" keys rather than claims.
_BY_WALL: Final[tuple[str, ...]] = ("wall_id",)

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

#: The only order a set of rows keyed by a wall has. Stated rather than left to
#: the file, because a listing with no ORDER BY is a different order on a
#: different day and every caller here is comparing sets.
_BY_WALL_ID: Final[tuple[OrderBy, ...]] = (OrderBy("wall_id"),)

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

    def update_artist(self, artist: Artist) -> None:
        self._update("artists", BY_ID, _artist_row(artist), subject=f"artist {artist.id!r}")

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

    # -- walls ----------------------------------------------------------------

    def add_wall(self, wall: Wall) -> None:
        # Named rather than identified, unlike every neighbour here. The id is a
        # fresh uuid4 and can never be the thing already stored, so the only way
        # this insert refuses is the UNIQUE on `name` — and "could not store wall
        # '<uuid>'" would report a collision on a value nobody has ever seen, to
        # a curator who typed a room's name. The refusal has to name what
        # collided.
        self._add("walls", _wall_row(wall), subject=f"wall {wall.name!r}")

    def get_wall(self, wall_id: str) -> Wall | None:
        return self._get("walls", {"id": wall_id}, _wall)

    def list_walls(self) -> Sequence[Wall]:
        return self._list("walls", None, _BY_NAME, _wall)

    # -- what is hanging ------------------------------------------------------

    def get_assignment(self, wall_id: str) -> ThemeAssignment | None:
        return self._get("theme_assignments", {"wall_id": wall_id}, _assignment)

    def set_assignment(self, assignment: ThemeAssignment) -> None:
        # `update` rather than `raise`, because hanging a theme on a wall that
        # already holds one replaces it. That is the whole operation — there is
        # no take-down-then-hang pair a reader could be caught between.
        self._store.upsert("theme_assignments", _assignment_row(assignment), pk=_BY_WALL, on_conflict="update")

    def remove_assignment(self, wall_id: str) -> None:
        self._store.delete("theme_assignments", {"wall_id": wall_id})

    def list_assignments(self) -> Sequence[ThemeAssignment]:
        return self._list("theme_assignments", None, _BY_WALL_ID, _assignment)

    # -- the display directives -----------------------------------------------

    def add_directive(self, directive: Directive) -> None:
        self._add("directives", _directive_row(directive), subject=f"directive for wall {directive.wall_id!r}", key=_BY_WALL)

    def get_directive(self, wall_id: str) -> Directive:
        row = self._store.fetch_one("directives", {"wall_id": wall_id})
        if row is None:
            # Seeded when the wall is created, so its absence means either an
            # unknown wall or a file edited by something other than this code.
            raise StorageError(f"Wall {wall_id!r} has no display directive row.")
        return _directive(row)

    def set_directive(self, directive: Directive) -> None:
        self._update(
            "directives",
            _BY_WALL,
            _directive_row(directive),
            subject=f"the display directive for wall {directive.wall_id!r}",
        )

    def list_directives(self) -> Sequence[Directive]:
        return self._list("directives", None, _BY_WALL_ID, _directive)


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
        "family_name": artist.family_name,
        "given_name": artist.given_name,
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
        "commentary": artwork.commentary,
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


def _wall_row(wall: Wall) -> dict[str, Any]:
    return {"id": wall.id, "name": wall.name, "created_at": to_iso(wall.created_at)}


def _assignment_row(assignment: ThemeAssignment) -> dict[str, Any]:
    return {
        "wall_id": assignment.wall_id,
        "theme_id": assignment.theme_id,
        "assigned_at": to_iso(assignment.assigned_at),
    }


def _directive_row(directive: Directive) -> dict[str, Any]:
    return {
        "wall_id": directive.wall_id,
        "sequence": directive.sequence,
        "pinned_work_id": directive.pinned_work_id,
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
        family_name=row["family_name"],
        given_name=row["given_name"],
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
        commentary=row["commentary"],
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
        rotation_interval_seconds=row["rotation_interval_seconds"],
        shuffle=None if row["shuffle"] is None else bool(row["shuffle"]),
    )


def _wall(row: Mapping[str, Any]) -> Wall:
    return Wall(id=row["id"], name=row["name"], created_at=require_datetime(row["created_at"], "created_at"))


def _assignment(row: Mapping[str, Any]) -> ThemeAssignment:
    return ThemeAssignment(
        wall_id=row["wall_id"],
        theme_id=row["theme_id"],
        assigned_at=require_datetime(row["assigned_at"], "assigned_at"),
    )


def _directive(row: Mapping[str, Any]) -> Directive:
    return Directive(wall_id=row["wall_id"], sequence=row["sequence"], pinned_work_id=row["pinned_work_id"])


def _membership(row: Mapping[str, Any]) -> ThemeMembership:
    return ThemeMembership(
        theme_id=row["theme_id"],
        artwork_id=row["artwork_id"],
        added_at=require_datetime(row["added_at"], "added_at"),
        position=row["position"],
    )
