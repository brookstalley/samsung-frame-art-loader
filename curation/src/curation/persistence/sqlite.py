"""A `CatalogueStore` over a SQLite file.

SQLite was chosen because it has no dependency to resolve, no server to run, and
a file that can be copied to a backup and back again — which is how this
catalogue's restore path is meant to work.

This module is the domain half of the split: it owns the schema, the mapping
between records and rows, and the ordering and paging decisions that make a
listing stable. Everything about connections, statements, locking and constraint
translation lives in `durable.py`, so what remains here reads as the catalogue
rather than as SQL plumbing.

Ordering is decided here rather than below because it is a product judgement, not
a storage one: title is what a curator scans by, and id breaks ties so that the
same page request never comes back in a different order.
"""

import logging
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from curation.persistence.catalogue import (
    Artist,
    Artwork,
    ArtworkPage,
    ArtworkStatus,
    StorageError,
    Theme,
)
from curation.persistence.durable import OrderBy, SqliteDurableStore

log = logging.getLogger(__name__)

_SCHEMA = """
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

CREATE TABLE IF NOT EXISTS themes (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL UNIQUE,
    description  TEXT,
    is_active    INTEGER NOT NULL,
    created_at   TEXT NOT NULL
);
"""

#: Every table in this catalogue is keyed by a single `id`. Named once so the
#: durable store is addressed the same way everywhere.
_BY_ID: Final[tuple[str, ...]] = ("id",)

#: What a curator scans by, then a tie-break that makes paging repeatable.
_BY_TITLE: Final[tuple[OrderBy, ...]] = (OrderBy("title", ignore_case=True), OrderBy("id"))
_BY_NAME: Final[tuple[OrderBy, ...]] = (OrderBy("name", ignore_case=True), OrderBy("id"))


def _to_iso(moment: datetime | None) -> str | None:
    """Store instants as UTC ISO-8601 text.

    SQLite has no datetime type, and a naive local-time string is unreadable once
    the machine's timezone changes under it.
    """
    if moment is None:
        return None
    return moment.astimezone(UTC).isoformat()


def _from_iso(text: str | None) -> datetime | None:
    if text is None:
        return None
    return datetime.fromisoformat(text)


def _require_datetime(text: str | None, column: str) -> datetime:
    moment = _from_iso(text)
    if moment is None:
        raise StorageError(f"Row is missing its required {column} timestamp.")
    return moment


class SqliteCatalogue:
    """The catalogue, persisted to one SQLite file."""

    def __init__(self, path: Path | str) -> None:
        self._store = SqliteDurableStore(path, _SCHEMA)

    # -- artists --------------------------------------------------------------

    def add_artist(self, artist: Artist) -> None:
        self._add(
            "artists",
            {
                "id": artist.id,
                "name": artist.name,
                "nationality": artist.nationality,
                "born": artist.born,
                "died": artist.died,
                "lifespan_text": artist.lifespan_text,
                "biography": artist.biography,
            },
            subject=f"artist {artist.id!r}",
        )

    def get_artist(self, artist_id: str) -> Artist | None:
        row = self._store.fetch_one("artists", {"id": artist_id})
        return None if row is None else self._artist(row)

    # -- artworks -------------------------------------------------------------

    def add_artwork(self, artwork: Artwork) -> None:
        self._add(
            "artworks",
            {
                "id": artwork.id,
                "title": artwork.title,
                "artist_id": artwork.artist_id,
                "date_created": artwork.date_created,
                "medium": artwork.medium,
                "dimensions": artwork.dimensions,
                "description": artwork.description,
                "rights": artwork.rights,
                "status": str(artwork.status),
                "accepted_at": _to_iso(artwork.accepted_at),
                "created_at": _to_iso(artwork.created_at),
            },
            subject=f"artwork {artwork.id!r}",
        )

    def get_artwork(self, artwork_id: str) -> Artwork | None:
        row = self._store.fetch_one("artworks", {"id": artwork_id})
        return None if row is None else self._artwork(row)

    def list_artworks(self, *, status: ArtworkStatus | None, limit: int, offset: int) -> ArtworkPage:
        rows, total = self._store.select_page(
            "artworks",
            order_by=_BY_TITLE,
            filters=None if status is None else {"status": str(status)},
            limit=limit,
            offset=offset,
        )
        return ArtworkPage(artworks=[self._artwork(row) for row in rows], total=total)

    # -- themes ---------------------------------------------------------------

    def add_theme(self, theme: Theme) -> None:
        self._add(
            "themes",
            {
                "id": theme.id,
                "name": theme.name,
                "description": theme.description,
                "is_active": int(theme.is_active),
                "created_at": _to_iso(theme.created_at),
            },
            subject=f"theme {theme.id!r}",
        )

    def get_theme(self, theme_id: str) -> Theme | None:
        row = self._store.fetch_one("themes", {"id": theme_id})
        return None if row is None else self._theme(row)

    def list_themes(self) -> Sequence[Theme]:
        rows, _ = self._store.select_page("themes", order_by=_BY_NAME)
        return [self._theme(row) for row in rows]

    # -- lifecycle ------------------------------------------------------------

    def close(self) -> None:
        self._store.close()

    # -- internals ------------------------------------------------------------

    def _add(self, table: str, row: Mapping[str, Any], *, subject: str) -> None:
        """Insert a record, refusing rather than overwriting one already there.

        Adding a work that is already catalogued is a mistake to report, not an
        edit to apply — so this is the conflict policy the catalogue's additions
        take, and revising a record is a different operation with its own name.
        """
        try:
            self._store.upsert(table, row, pk=_BY_ID, on_conflict="raise")
        except StorageError as exc:
            # Which record was refused is knowable only here, and only this line
            # puts it in the journal: the driver's own text for a foreign-key
            # violation carries no id, and the message raised from here is
            # written for whoever asked rather than for whoever is diagnosing.
            log.warning("Refused to store %s: %s", subject, exc.reason)
            raise StorageError(f"Could not store {subject}: {exc.reason}", reason=exc.reason) from exc

    @staticmethod
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

    @staticmethod
    def _artwork(row: Mapping[str, Any]) -> Artwork:
        return Artwork(
            id=row["id"],
            title=row["title"],
            created_at=_require_datetime(row["created_at"], "created_at"),
            status=ArtworkStatus(row["status"]),
            artist_id=row["artist_id"],
            date_created=row["date_created"],
            medium=row["medium"],
            dimensions=row["dimensions"],
            description=row["description"],
            rights=row["rights"],
            accepted_at=_from_iso(row["accepted_at"]),
        )

    @staticmethod
    def _theme(row: Mapping[str, Any]) -> Theme:
        return Theme(
            id=row["id"],
            name=row["name"],
            created_at=_require_datetime(row["created_at"], "created_at"),
            description=row["description"],
            is_active=bool(row["is_active"]),
        )
