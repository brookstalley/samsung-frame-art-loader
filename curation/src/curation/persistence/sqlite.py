"""A `CatalogueStore` on stdlib `sqlite3`.

Chosen because it has no dependency to resolve, no server to run, and a file
that can be copied to a backup and back again — which is how this catalogue's
restore path is meant to work. It sits behind `CatalogueStore` so that
replacing it later is one module, not a sweep.

**Concurrency.** One connection is opened with `check_same_thread=False` and
every statement runs under a single lock. The server accepts requests on an
event loop thread while tests and startup code touch the store from another,
so the connection genuinely crosses threads; the lock is what makes that safe
rather than usually-safe. Queries here are sub-millisecond point lookups
against a household-sized catalogue, so serialising them costs nothing worth
measuring.
"""

import logging
import sqlite3
import threading
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from curation.persistence.catalogue import (
    Artist,
    Artwork,
    ArtworkPage,
    ArtworkStatus,
    StorageError,
    Theme,
)

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


log = logging.getLogger(__name__)


def _refusal(exc: sqlite3.IntegrityError) -> str:
    """Why the store said no, in the catalogue's terms rather than SQL's.

    Falls back to a generic phrase rather than the driver text: an unrecognised
    constraint is still not something a caller should be reading table names
    out of.
    """
    text = str(exc).lower()
    if "unique" in text or "primary key" in text:
        return "it is already in the catalogue."
    if "foreign key" in text:
        return "it refers to a record that is not in the catalogue."
    if "not null" in text:
        return "a required field was empty."
    return "the catalogue refused the write."


def _to_iso(moment: datetime | None) -> str | None:
    """Store instants as UTC ISO-8601 text.

    SQLite has no datetime type, and a naive local-time string is unreadable
    once the machine's timezone changes under it.
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
        self._lock = threading.Lock()
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        with self._lock:
            # Foreign keys are off by default in SQLite, which would let an
            # artwork keep pointing at an artist that was never written.
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.executescript(_SCHEMA)
            self._connection.commit()

    # -- artists --------------------------------------------------------------

    def add_artist(self, artist: Artist) -> None:
        self._insert(
            "INSERT INTO artists (id, name, nationality, born, died, lifespan_text, biography)" " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                artist.id,
                artist.name,
                artist.nationality,
                artist.born,
                artist.died,
                artist.lifespan_text,
                artist.biography,
            ),
            subject=f"artist {artist.id!r}",
        )

    def get_artist(self, artist_id: str) -> Artist | None:
        row = self._fetch_one("SELECT * FROM artists WHERE id = ?", (artist_id,))
        return None if row is None else self._artist(row)

    # -- artworks -------------------------------------------------------------

    def add_artwork(self, artwork: Artwork) -> None:
        self._insert(
            "INSERT INTO artworks"
            " (id, title, artist_id, date_created, medium, dimensions, description, rights,"
            "  status, accepted_at, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                artwork.id,
                artwork.title,
                artwork.artist_id,
                artwork.date_created,
                artwork.medium,
                artwork.dimensions,
                artwork.description,
                artwork.rights,
                str(artwork.status),
                _to_iso(artwork.accepted_at),
                _to_iso(artwork.created_at),
            ),
            subject=f"artwork {artwork.id!r}",
        )

    def get_artwork(self, artwork_id: str) -> Artwork | None:
        row = self._fetch_one("SELECT * FROM artworks WHERE id = ?", (artwork_id,))
        return None if row is None else self._artwork(row)

    def list_artworks(self, *, status: ArtworkStatus | None, limit: int, offset: int) -> ArtworkPage:
        where = "" if status is None else " WHERE status = :status"
        parameters: dict[str, object] = {"limit": limit, "offset": offset}
        if status is not None:
            parameters["status"] = str(status)
        with self._lock:
            total = self._connection.execute(f"SELECT COUNT(*) FROM artworks{where}", parameters).fetchone()[0]
            # Title is what a curator scans by; id breaks ties so the same page
            # request never comes back in a different order.
            rows = self._connection.execute(
                f"SELECT * FROM artworks{where} ORDER BY title COLLATE NOCASE, id LIMIT :limit OFFSET :offset",
                parameters,
            ).fetchall()
        return ArtworkPage(artworks=[self._artwork(row) for row in rows], total=total)

    # -- themes ---------------------------------------------------------------

    def add_theme(self, theme: Theme) -> None:
        self._insert(
            "INSERT INTO themes (id, name, description, is_active, created_at) VALUES (?, ?, ?, ?, ?)",
            (theme.id, theme.name, theme.description, int(theme.is_active), _to_iso(theme.created_at)),
            subject=f"theme {theme.id!r}",
        )

    def get_theme(self, theme_id: str) -> Theme | None:
        row = self._fetch_one("SELECT * FROM themes WHERE id = ?", (theme_id,))
        return None if row is None else self._theme(row)

    def list_themes(self) -> Sequence[Theme]:
        with self._lock:
            rows = self._connection.execute("SELECT * FROM themes ORDER BY name COLLATE NOCASE, id").fetchall()
        return [self._theme(row) for row in rows]

    # -- lifecycle ------------------------------------------------------------

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    # -- internals ------------------------------------------------------------

    def _insert(self, statement: str, values: tuple[object, ...], *, subject: str) -> None:
        try:
            with self._lock, self._connection:
                self._connection.execute(statement, values)
        except sqlite3.IntegrityError as exc:
            # The driver's own text names tables and columns, and the message
            # travels intact to the tool surface. Translate it to the reason in
            # the catalogue's own terms and keep the SQL detail in the journal,
            # where diagnosis happens.
            log.warning("Refused to store %s: %s", subject, exc)
            raise StorageError(f"Could not store {subject}: {_refusal(exc)}") from exc

    def _fetch_one(self, statement: str, values: tuple[object, ...]) -> sqlite3.Row | None:
        with self._lock:
            return self._connection.execute(statement, values).fetchone()

    @staticmethod
    def _artist(row: sqlite3.Row) -> Artist:
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
    def _artwork(row: sqlite3.Row) -> Artwork:
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
    def _theme(row: sqlite3.Row) -> Theme:
        return Theme(
            id=row["id"],
            name=row["name"],
            created_at=_require_datetime(row["created_at"], "created_at"),
            description=row["description"],
            is_active=bool(row["is_active"]),
        )
