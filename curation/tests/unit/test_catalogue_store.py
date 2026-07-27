"""The catalogue file as a durable artifact, not just as a live object.

The service suite exercises the store through a service that holds it open for
the length of a test. Nothing there would notice if the catalogue stopped
surviving the process that wrote it, and survival is the whole reason this
product keeps a file rather than a cache.

The schema assertion pins the on-disk shape deliberately. `ART_ROOT`'s catalogue
outlives any single version of this code and is what the backup path copies, so a
change to the columns is a migration question — one this test forces someone to
answer on purpose rather than discover from a file that no longer loads.
"""

import sqlite3
from datetime import UTC, datetime

from curation.persistence.catalogue import Artist, Artwork, ArtworkStatus, Theme
from curation.persistence.sqlite import SqliteCatalogue

_EXPECTED_SCHEMA = {
    "artists": {"id", "name", "nationality", "born", "died", "lifespan_text", "biography"},
    "artworks": {
        "id",
        "title",
        "artist_id",
        "date_created",
        "medium",
        "dimensions",
        "description",
        "rights",
        "status",
        "accepted_at",
        "created_at",
    },
    "themes": {"id", "name", "description", "is_active", "created_at"},
}


def _seed(catalogue):
    moment = datetime(2026, 7, 27, 9, 30, tzinfo=UTC)
    catalogue.add_artist(Artist(id="a1", name="Edward Hopper", nationality="American", born=1882, died=1967))
    catalogue.add_artwork(
        Artwork(
            id="w1",
            title="Nighthawks",
            created_at=moment,
            artist_id="a1",
            date_created="1942",
            medium="Oil on canvas",
            accepted_at=moment,
        )
    )
    catalogue.add_theme(Theme(id="t1", name="Late night", created_at=moment, description="After hours"))
    return moment


def test_a_catalogue_survives_the_process_that_wrote_it(tmp_path):
    path = tmp_path / "catalogue.sqlite"
    first = SqliteCatalogue(path)
    moment = _seed(first)
    first.close()

    reopened = SqliteCatalogue(path)
    try:
        artwork = reopened.get_artwork("w1")
        assert artwork is not None
        assert artwork.title == "Nighthawks"
        assert artwork.status is ArtworkStatus.ACCEPTED
        assert artwork.created_at == moment
        assert artwork.accepted_at == moment

        artist = reopened.get_artist("a1")
        assert artist is not None
        assert (artist.name, artist.nationality, artist.born, artist.died) == ("Edward Hopper", "American", 1882, 1967)

        theme = reopened.get_theme("t1")
        assert theme is not None
        assert (theme.name, theme.description, theme.is_active) == ("Late night", "After hours", False)

        assert reopened.list_artworks(status=None, limit=10, offset=0).total == 1
        assert [entry.name for entry in reopened.list_themes()] == ["Late night"]
    finally:
        reopened.close()


def test_an_instant_round_trips_through_the_file_as_utc(tmp_path):
    """A timezone-aware instant must come back equal, not merely close.

    SQLite has no datetime type, so this is stored as text; a naive local-time
    string would read back as a different moment on a machine in another zone.
    """
    path = tmp_path / "catalogue.sqlite"
    catalogue = SqliteCatalogue(path)
    stored = datetime(2026, 3, 14, 15, 9, 26, tzinfo=UTC)
    catalogue.add_artwork(Artwork(id="w1", title="Pi", created_at=stored))
    catalogue.close()

    reopened = SqliteCatalogue(path)
    try:
        assert reopened.get_artwork("w1").created_at == stored
    finally:
        reopened.close()


#: The DDL and inserts an earlier revision of this package wrote, frozen verbatim.
#:
#: Deliberately NOT imported from `curation.persistence.sqlite`: a copy that
#: tracked the code could never detect the code drifting away from files already
#: on disk, which is the only thing these are here to catch. `ART_ROOT`'s
#: catalogue outlives any single version of this code, so when a change makes
#: these fail, the answer is a migration — not an edit to the literals below.
_LEGACY_DDL = """
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

_LEGACY_ARTIST_INSERT = (
    "INSERT INTO artists (id, name, nationality, born, died, lifespan_text, biography) VALUES (?, ?, ?, ?, ?, ?, ?)"
)
_LEGACY_ARTWORK_INSERT = (
    "INSERT INTO artworks (id, title, artist_id, date_created, medium, dimensions,"
    " description, rights, status, accepted_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)
_LEGACY_THEME_INSERT = "INSERT INTO themes (id, name, description, is_active, created_at) VALUES (?, ?, ?, ?, ?)"


def _write_legacy_catalogue(path):
    """Produce a catalogue file exactly as the earlier revision encoded one.

    Instants as UTC ISO-8601 text, status as its bare string value, and
    `is_active` as an integer — the three places a record stops being a Python
    object and becomes bytes, and so the three that can silently change meaning.
    """
    moment = datetime(2026, 7, 27, 9, 30, tzinfo=UTC).astimezone(UTC).isoformat()
    connection = sqlite3.connect(path)
    try:
        connection.executescript(_LEGACY_DDL)
        connection.execute(
            _LEGACY_ARTIST_INSERT, ("a1", "Edward Hopper", "American", 1882, 1967, "1882–1967", "American realist.")
        )
        # A second artist with every optional column NULL — the sparse row shape.
        connection.execute(_LEGACY_ARTIST_INSERT, ("a2", "Unknown", None, None, None, None, None))
        connection.execute(
            _LEGACY_ARTWORK_INSERT,
            ("w1", "Nighthawks", "a1", "1942", "Oil on canvas", "84x152cm", "A diner.", "PD", "accepted", moment, moment),
        )
        # Lowercase leader and a NULL accepted_at: pins the case-insensitive sort
        # and the nullable instant at once.
        connection.execute(
            _LEGACY_ARTWORK_INSERT,
            ("w2", "chop suey", "a2", None, None, None, None, None, "archived", None, moment),
        )
        connection.execute(_LEGACY_THEME_INSERT, ("t1", "Late night", "After hours", 1, moment))
        connection.execute(_LEGACY_THEME_INSERT, ("t2", "daylight", None, 0, moment))
        connection.commit()
    finally:
        connection.close()
    return datetime(2026, 7, 27, 9, 30, tzinfo=UTC)


def test_a_catalogue_written_by_an_earlier_revision_still_reads(tmp_path):
    """A file on disk outlives the code that wrote it, so reads must stay compatible.

    Every field is asserted rather than a sampled few, because a mapping change
    shows up one column at a time; the listings are included because ordering and
    totals are read paths too, and a silent reordering is the kind of regression a
    per-record check cannot see.
    """
    path = tmp_path / "catalogue.sqlite"
    moment = _write_legacy_catalogue(path)

    catalogue = SqliteCatalogue(path)
    try:
        hopper = catalogue.get_artist("a1")
        assert (hopper.id, hopper.name, hopper.nationality) == ("a1", "Edward Hopper", "American")
        assert (hopper.born, hopper.died, hopper.lifespan_text) == (1882, 1967, "1882–1967")
        assert hopper.biography == "American realist."

        sparse = catalogue.get_artist("a2")
        assert (sparse.nationality, sparse.born, sparse.died, sparse.lifespan_text, sparse.biography) == (
            None,
            None,
            None,
            None,
            None,
        )

        nighthawks = catalogue.get_artwork("w1")
        assert (nighthawks.id, nighthawks.title, nighthawks.artist_id) == ("w1", "Nighthawks", "a1")
        assert (nighthawks.date_created, nighthawks.medium, nighthawks.dimensions) == ("1942", "Oil on canvas", "84x152cm")
        assert (nighthawks.description, nighthawks.rights) == ("A diner.", "PD")
        assert nighthawks.status is ArtworkStatus.ACCEPTED
        assert nighthawks.created_at == moment
        assert nighthawks.accepted_at == moment

        archived = catalogue.get_artwork("w2")
        assert archived.status is ArtworkStatus.ARCHIVED
        assert archived.accepted_at is None

        theme = catalogue.get_theme("t1")
        assert (theme.name, theme.description, theme.is_active, theme.created_at) == ("Late night", "After hours", True, moment)
        assert catalogue.get_theme("t2").is_active is False

        # Ordering is case-insensitive by title, so the lowercase entry leads.
        listed = catalogue.list_artworks(status=None, limit=10, offset=0)
        assert [work.id for work in listed.artworks] == ["w2", "w1"]
        assert listed.total == 2
        assert [work.id for work in catalogue.list_artworks(status=ArtworkStatus.ACCEPTED, limit=10, offset=0).artworks] == ["w1"]
        assert [entry.id for entry in catalogue.list_themes()] == ["t2", "t1"]
    finally:
        catalogue.close()


def test_the_file_carries_the_schema_the_backup_path_expects(tmp_path):
    path = tmp_path / "catalogue.sqlite"
    catalogue = SqliteCatalogue(path)
    catalogue.close()

    connection = sqlite3.connect(path)
    try:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert _EXPECTED_SCHEMA.keys() <= tables
        for table, columns in _EXPECTED_SCHEMA.items():
            assert {row[1] for row in connection.execute(f"PRAGMA table_info({table})")} == columns
    finally:
        connection.close()
