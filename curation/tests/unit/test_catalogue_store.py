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
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from curation.persistence.catalogue import StorageError, StoreMisuseError, WorkQuery
from curation.persistence.durable import SqliteDurableStore
from curation.persistence.file import open_catalogue_file
from curation.persistence.records import (
    AcquisitionMethod,
    Artist,
    Artwork,
    ArtworkStatus,
    Directive,
    FetchStatus,
    MatColor,
    MatMethod,
    Original,
    RightsStatus,
    Source,
    SourceClass,
    Theme,
    ThemeAssignment,
    Wall,
)
from curation.persistence.sqlite import SqliteCatalogue

_EXPECTED_SCHEMA = {
    # Widened with `family_name` and `given_name` when the e-paper label began
    # leading with the family part — which needs to know which part that is, and
    # no rule over `name` can say for "van Gogh".
    "artists": {"id", "name", "nationality", "born", "died", "lifespan_text", "biography", "family_name", "given_name"},
    # `commentary` is the line written for a wall label, which is not
    # `description` — that is the holding institution's paragraph.
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
        "commentary",
    },
    # Widened 2026-07-31 with the per-theme rotation settings. This was the first
    # change to a table files already on disk carried, so it is also what the
    # store's column-widening step exists for.
    # `is_active` was here until 2026-08-12, when hanging became an act against a
    # named wall. It is the first column this schema has *removed*, which the
    # widening step cannot do — `migrations.py` does, and the test below watches
    # a legacy file lose it.
    "themes": {"id", "name", "description", "created_at", "rotation_interval_seconds", "shuffle"},
    "walls": {"id", "name", "created_at"},
    "theme_assignments": {"wall_id", "theme_id", "assigned_at"},
    "directives": {"wall_id", "sequence", "pinned_work_id"},
    "sources": {
        "id",
        "artwork_id",
        "url",
        "provider",
        "source_class",
        "acquisition_method",
        "rights_status",
        "is_primary",
        "confidence",
        "selection_rationale",
        "last_fetch_status",
        "last_fetched_at",
    },
    "originals": {
        "id",
        "artwork_id",
        "source_id",
        "relative_path",
        "width",
        "height",
        "byte_size",
        "content_hash",
        # Added after files existed on disk, so it is nullable and arrives through
        # the widening step rather than through a rewritten file. A null means the
        # row predates it, which readers treat as a complete fetch.
        "fetch_status",
    },
    "renditions": {
        "id",
        "artwork_id",
        "kind",
        "target_width",
        "target_height",
        "relative_path",
        "source_content_hash",
        "generated_at",
    },
    "mat_colors": {
        "id",
        "artwork_id",
        "hex_rgb",
        "method",
        "is_current",
        "lab_l",
        "lab_a",
        "lab_b",
        "reason",
        "model_id",
        "chosen_at",
    },
    "theme_memberships": {"theme_id", "artwork_id", "position", "added_at"},
}

#: Columns no table may grow. `display_fit` was one once, computed at acquisition
#: and stored on the original; it became wrong the moment panel geometry turned
#: into a deployment value, because a stored verdict is a claim about one
#: particular television. It is derived now, and nothing reports the drift if a
#: later change quietly puts it back.
_FORBIDDEN_COLUMNS = {"display_fit"}


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
    first = SqliteCatalogue(open_catalogue_file(path))
    moment = _seed(first)
    first.close()

    reopened = SqliteCatalogue(open_catalogue_file(path))
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
        assert (theme.name, theme.description) == ("Late night", "After hours")

        assert reopened.list_artworks(WorkQuery(), limit=10, offset=0).total == 1
        assert [entry.name for entry in reopened.list_themes()] == ["Late night"]
    finally:
        reopened.close()


def test_an_instant_round_trips_through_the_file_as_utc(tmp_path):
    """A timezone-aware instant must come back equal, not merely close.

    SQLite has no datetime type, so this is stored as text; a naive local-time
    string would read back as a different moment on a machine in another zone.
    """
    path = tmp_path / "catalogue.sqlite"
    catalogue = SqliteCatalogue(open_catalogue_file(path))
    stored = datetime(2026, 3, 14, 15, 9, 26, tzinfo=UTC)
    catalogue.add_artwork(Artwork(id="w1", title="Pi", created_at=stored))
    catalogue.close()

    reopened = SqliteCatalogue(open_catalogue_file(path))
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
        # Both inactive, because that is the only shape the earlier revision could
        # produce: its `add_theme` took no `is_active` argument and it shipped no
        # way to activate one. A fixture writing an active theme here would be
        # testing a file that never existed, and would hide the one real
        # consequence — a catalogue that upgrades with no active theme at all.
        connection.execute(_LEGACY_THEME_INSERT, ("t1", "Late night", "After hours", 0, moment))
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

    catalogue = SqliteCatalogue(open_catalogue_file(path))
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

        # The columns the file predates read as absent rather than failing, which
        # is the whole of what the deployed catalogue does on the restart after
        # the label gained a family name: the panel falls back to the whole name
        # until something says which part is which.
        assert (hopper.family_name, hopper.given_name) == (None, None)
        assert catalogue.get_artwork("w1").commentary is None

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
        assert (theme.name, theme.description, theme.created_at) == ("Late night", "After hours", moment)

        # Ordering is case-insensitive by title, so the lowercase entry leads.
        listed = catalogue.list_artworks(WorkQuery(), limit=10, offset=0)
        assert [work.id for work in listed.artworks] == ["w2", "w1"]
        assert listed.total == 2
        assert [
            work.id for work in catalogue.list_artworks(WorkQuery(status=ArtworkStatus.ACCEPTED), limit=10, offset=0).artworks
        ] == ["w1"]
        assert [entry.id for entry in catalogue.list_themes()] == ["t2", "t1"]
    finally:
        catalogue.close()


def test_the_file_carries_the_schema_the_backup_path_expects(tmp_path):
    path = tmp_path / "catalogue.sqlite"
    catalogue = SqliteCatalogue(open_catalogue_file(path))
    catalogue.close()

    connection = sqlite3.connect(path)
    try:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert _EXPECTED_SCHEMA.keys() <= tables
        for table, columns in _EXPECTED_SCHEMA.items():
            assert {row[1] for row in connection.execute(f"PRAGMA table_info({table})")} == columns
    finally:
        connection.close()


def test_no_table_stores_the_resolution_verdict(tmp_path):
    """Constraint 12, checked against the file rather than against the code.

    The verdict depends on panel geometry and mat configuration, both deployment
    values this plane does not own. A column would be a stored judgement about
    one specific television, and it would go silently wrong the day the
    television changed — which is precisely how it went wrong the first time.
    """
    path = tmp_path / "catalogue.sqlite"
    SqliteCatalogue(open_catalogue_file(path)).close()

    connection = sqlite3.connect(path)
    try:
        for table in (row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")):
            columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
            assert not columns & _FORBIDDEN_COLUMNS, f"{table} stores a value that must be derived"
    finally:
        connection.close()


def test_a_fresh_catalogue_carries_one_wall_and_one_directive_for_it(tmp_path):
    """Both are established when the file is opened, so no caller ever makes either.

    A directive that had to be created on first use would have a window in which
    reading it fails, and the read happens on every manifest build. A wall that
    had to be created on first use would leave a fresh deployment with nowhere to
    hang anything and no operation able to name a wall.
    """
    path = tmp_path / "catalogue.sqlite"
    catalogue = SqliteCatalogue(open_catalogue_file(path, wall_name="Living room"))
    try:
        walls = catalogue.list_walls()
        assert [wall.name for wall in walls] == ["Living room"]
        assert catalogue.get_directive(walls[0].id) == Directive(wall_id=walls[0].id, sequence=0, pinned_work_id=None)
        # Nothing is hanging on it: a theme is created globally and hung
        # deliberately, and there are no themes here to hang.
        assert catalogue.get_assignment(walls[0].id) is None
    finally:
        catalogue.close()

    connection = sqlite3.connect(path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM directives").fetchone()[0] == 1
        # The singleton it replaced is gone rather than left beside it, so
        # nothing can read a counter no code writes.
        assert connection.execute("SELECT COUNT(*) FROM sqlite_master WHERE name = 'directive'").fetchone()[0] == 0
    finally:
        connection.close()


def test_a_second_theme_on_a_wall_is_a_row_that_cannot_be_inserted(tmp_path):
    """One theme per wall is the primary key, not a rule anything checks.

    Asserted against the file rather than the service, because the claim is about
    the *key*: there is nothing here to detect or reconcile, which is the whole
    difference from the partial index this replaced.
    """
    path = tmp_path / "catalogue.sqlite"
    catalogue = SqliteCatalogue(open_catalogue_file(path))
    try:
        moment = datetime(2026, 8, 12, 9, 30, tzinfo=UTC)
        wall = catalogue.list_walls()[0]
        catalogue.add_theme(Theme(id="t1", name="Late night", created_at=moment))
        catalogue.add_theme(Theme(id="t2", name="Daylight", created_at=moment))
        catalogue.set_assignment(ThemeAssignment(wall_id=wall.id, theme_id="t1", assigned_at=moment))
    finally:
        catalogue.close()

    connection = sqlite3.connect(path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO theme_assignments (wall_id, theme_id, assigned_at) VALUES (?, ?, ?)",
                (wall.id, "t2", moment.isoformat()),
            )
    finally:
        connection.close()


def test_hanging_a_second_theme_replaces_the_first_rather_than_refusing(tmp_path):
    """The store's own write is an update, because that is what hanging means.

    A curator hanging something else is not making a mistake to report; there is
    no take-down-then-hang pair a reader could be caught between.
    """
    catalogue = SqliteCatalogue(open_catalogue_file(tmp_path / "catalogue.sqlite"))
    try:
        moment = datetime(2026, 8, 12, 9, 30, tzinfo=UTC)
        wall = catalogue.list_walls()[0]
        catalogue.add_theme(Theme(id="t1", name="Late night", created_at=moment))
        catalogue.add_theme(Theme(id="t2", name="Daylight", created_at=moment))

        catalogue.set_assignment(ThemeAssignment(wall_id=wall.id, theme_id="t1", assigned_at=moment))
        catalogue.set_assignment(ThemeAssignment(wall_id=wall.id, theme_id="t2", assigned_at=moment))

        assert catalogue.get_assignment(wall.id).theme_id == "t2"
        assert [assignment.wall_id for assignment in catalogue.list_assignments()] == [wall.id]
    finally:
        catalogue.close()


def test_two_walls_may_hang_the_same_theme_with_nothing_duplicated(tmp_path):
    """The property the removed boolean could not have.

    A column on the theme can say "on the wall" exactly once; a row per wall says
    it once per wall, over the same theme row.
    """
    catalogue = SqliteCatalogue(open_catalogue_file(tmp_path / "catalogue.sqlite"))
    try:
        moment = datetime(2026, 8, 12, 9, 30, tzinfo=UTC)
        first = catalogue.list_walls()[0]
        catalogue.add_wall(Wall(id="w-study", name="Study", created_at=moment))
        catalogue.add_directive(Directive(wall_id="w-study", sequence=0))
        catalogue.add_theme(Theme(id="t1", name="Late night", created_at=moment))

        catalogue.set_assignment(ThemeAssignment(wall_id=first.id, theme_id="t1", assigned_at=moment))
        catalogue.set_assignment(ThemeAssignment(wall_id="w-study", theme_id="t1", assigned_at=moment))

        assert {assignment.wall_id for assignment in catalogue.list_assignments()} == {first.id, "w-study"}
        assert {assignment.theme_id for assignment in catalogue.list_assignments()} == {"t1"}
        assert len(catalogue.list_themes()) == 1
    finally:
        catalogue.close()


def test_an_earlier_catalogue_gains_the_tables_it_did_not_have(tmp_path):
    """Opening an older file adds the new tables without disturbing its rows.

    Every entity added up to that point lived in a table of its own, so the file
    grew rather than changing shape. The rotation settings below were the first
    change that did not have that luxury.
    """
    path = tmp_path / "catalogue.sqlite"
    _write_legacy_catalogue(path)

    catalogue = SqliteCatalogue(open_catalogue_file(path))
    try:
        # The rows the older revision wrote are untouched.
        assert catalogue.get_artwork("w1").title == "Nighthawks"
        assert catalogue.get_theme("t1").name == "Late night"
        # And the entities it never knew about are addressable.
        assert catalogue.get_directive(catalogue.list_walls()[0].id).sequence == 0
        assert catalogue.list_sources("w1") == []
        assert catalogue.get_original("w1") is None
        assert catalogue.list_renditions("w1") == []
        assert catalogue.list_mat_colors("w1") == []
        assert catalogue.list_memberships("t1") == []
    finally:
        catalogue.close()


def test_an_earlier_catalogue_gains_columns_added_to_a_table_it_already_had(tmp_path):
    """The rotation settings widened `themes`, which the frozen DDL above created.

    `CREATE TABLE IF NOT EXISTS` does nothing at all to a table that exists, so
    without a widening step the new columns would never reach this file. The
    failure that causes is quiet in the worst way: reads keep working, and the
    first *write* of a theme is refused for naming a column the file lacks —
    which reads as a code defect rather than as a file predating the column.
    """
    path = tmp_path / "catalogue.sqlite"
    _write_legacy_catalogue(path)

    catalogue = SqliteCatalogue(open_catalogue_file(path))
    try:
        # The theme the older revision wrote reads back, and its rotation
        # settings are null — "inherit the global default", which is the correct
        # answer for a theme written before the fields existed.
        stored = catalogue.get_theme("t1")
        assert stored.rotation_interval_seconds is None
        assert stored.shuffle is None

        # And the file now accepts a write that names them. Values no default
        # could produce, so a column silently dropped on the way down would show.
        catalogue.update_theme(replace(stored, rotation_interval_seconds=930, shuffle=True))
        reread = catalogue.get_theme("t1")
        assert reread.rotation_interval_seconds == 930
        assert reread.shuffle is True
    finally:
        catalogue.close()


def test_an_original_written_before_fetch_status_reads_back_as_unrecorded(tmp_path):
    """The second column added to a table that already held rows, and the first
    whose null means something a reader acts on.

    `originals` predates `fetch_status`, so every row a real deployment already
    holds — the whole seeded 2024 corpus among them — arrives with no value. That
    has to read back as `None` rather than as a default, because acquisition treats
    unrecorded as *complete* and so declines to overwrite it with a gappy re-fetch.
    A widening that quietly filled the column with `partial_tiles`, or a reader that
    substituted a default on the way up, would surrender exactly those images.
    """
    path = tmp_path / "catalogue.sqlite"
    connection = sqlite3.connect(path)
    try:
        # The `originals` table as it stood before the column, written out rather
        # than derived from the current DDL: a fixture that built itself from the
        # shipped schema would gain the column and assert nothing.
        connection.executescript("""
            CREATE TABLE artworks (id TEXT PRIMARY KEY, title TEXT NOT NULL, artist_id TEXT,
                date_created TEXT, medium TEXT, dimensions TEXT, description TEXT, rights TEXT,
                status TEXT NOT NULL, accepted_at TEXT, created_at TEXT NOT NULL);
            CREATE TABLE sources (id TEXT PRIMARY KEY, artwork_id TEXT NOT NULL, url TEXT NOT NULL,
                provider TEXT NOT NULL, source_class TEXT NOT NULL, acquisition_method TEXT NOT NULL,
                rights_status TEXT NOT NULL, is_primary INTEGER NOT NULL DEFAULT 0, confidence REAL,
                selection_rationale TEXT, last_fetch_status TEXT, last_fetched_at TEXT);
            CREATE TABLE originals (id TEXT PRIMARY KEY, artwork_id TEXT NOT NULL UNIQUE,
                source_id TEXT NOT NULL, relative_path TEXT NOT NULL, width INTEGER NOT NULL,
                height INTEGER NOT NULL, byte_size INTEGER NOT NULL CHECK (byte_size > 0),
                content_hash TEXT NOT NULL);
            """)
        moment = datetime(2026, 7, 27, 9, 30, tzinfo=UTC).astimezone(UTC).isoformat()
        connection.execute(
            "INSERT INTO artworks (id, title, status, created_at) VALUES (?, ?, ?, ?)",
            ("w1", "Nighthawks", "accepted", moment),
        )
        connection.execute(
            "INSERT INTO sources (id, artwork_id, url, provider, source_class, acquisition_method, rights_status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("s1", "w1", "https://museum.example/1", "artic", "institutional", "dezoomify", "public_domain"),
        )
        connection.execute(
            "INSERT INTO originals (id, artwork_id, source_id, relative_path, width, height, byte_size, content_hash) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("o1", "w1", "s1", "raw/w1.tif", 6000, 4000, 90_000_000, "sha256:aaa"),
        )
        connection.commit()
    finally:
        connection.close()

    catalogue = SqliteCatalogue(open_catalogue_file(path))
    try:
        held = catalogue.get_original("w1")
        assert held.fetch_status is None, "a pre-column row must not acquire a value nobody recorded"
        assert (held.width, held.content_hash) == (6000, "sha256:aaa")

        # And the widened file accepts a write that names the column.
        catalogue.update_original(replace(held, fetch_status=FetchStatus.PARTIAL_TILES))
        assert catalogue.get_original("w1").fetch_status is FetchStatus.PARTIAL_TILES
    finally:
        catalogue.close()


def test_widening_survives_the_process_that_did_it(tmp_path):
    """A migration held only in the connection that ran it would repeat forever."""
    path = tmp_path / "catalogue.sqlite"
    _write_legacy_catalogue(path)

    first = SqliteCatalogue(open_catalogue_file(path))
    first.update_theme(replace(first.get_theme("t1"), rotation_interval_seconds=930))
    first.close()

    reopened = SqliteCatalogue(open_catalogue_file(path))
    try:
        assert reopened.get_theme("t1").rotation_interval_seconds == 930
    finally:
        reopened.close()


def test_a_not_null_column_with_no_default_is_refused_rather_than_half_applied(tmp_path):
    """SQLite cannot add one to a table with rows, so the honest answer is to say so.

    Guarding the boundary of what this widening can do. Applying the additions it
    can and falling over on the one it cannot would leave a half-migrated file,
    which is worse than an open that refuses and names the reason.
    """
    path = tmp_path / "catalogue.sqlite"
    connection = sqlite3.connect(path)
    try:
        connection.executescript("CREATE TABLE IF NOT EXISTS notes (id TEXT PRIMARY KEY);")
        connection.execute("INSERT INTO notes (id) VALUES ('n1')")
        connection.commit()
    finally:
        connection.close()

    widened = "CREATE TABLE IF NOT EXISTS notes (id TEXT PRIMARY KEY, body TEXT NOT NULL);"
    with pytest.raises(StoreMisuseError, match="NOT NULL with no default"):
        SqliteDurableStore(path, widened)


def test_a_file_predating_a_column_opens_when_the_schema_indexes_that_column(tmp_path):
    """The schema declares indexes as well as tables, and one may name a new column.

    **`CREATE INDEX IF NOT EXISTS ... ON t(c)` does not skip when `c` is absent —
    it raises `no such column`.** So the widening step has to run *before* the
    script rather than after it: run afterwards, it never runs at all on the one
    file that needed it, and the open fails for every catalogue written before the
    column existed. Every other widening test here adds a column and then writes
    to it, which is why none of them saw this — the failure needs an index in the
    schema, not just a column.

    Found against the wall's own catalogue, where `spend_records` gained
    `conversation_turn_id` together with an index over it, and the curation plane
    then refused to start on a deployment that had been running for months.
    """
    path = tmp_path / "catalogue.sqlite"
    connection = sqlite3.connect(path)
    try:
        connection.executescript("CREATE TABLE IF NOT EXISTS notes (id TEXT PRIMARY KEY);")
        connection.execute("INSERT INTO notes (id) VALUES ('n1')")
        connection.commit()
    finally:
        connection.close()

    widened = (
        "CREATE TABLE IF NOT EXISTS notes (id TEXT PRIMARY KEY, turn_id TEXT);"
        "CREATE INDEX IF NOT EXISTS notes_by_turn ON notes(turn_id);"
    )
    store = SqliteDurableStore(path, widened)
    try:
        # The row written before the column exists reads back with it null, and
        # the column then takes a value — so the widening reached the file rather
        # than merely letting the open succeed.
        assert store.fetch_one("notes", {"id": "n1"}) == {"id": "n1", "turn_id": None}
        store.upsert("notes", {"id": "n1", "turn_id": "t1"}, pk=("id",))
        assert store.fetch_one("notes", {"id": "n1"})["turn_id"] == "t1"
    finally:
        store.close()


def test_the_file_itself_refuses_a_second_wall_of_the_same_name(tmp_path):
    """A wall's name is how every confirmation identifies it, so two cannot share one.

    The one rule about walls that is a uniqueness constraint rather than a key:
    the id is the identity, and the name is what a curator reads.
    """
    catalogue = SqliteCatalogue(open_catalogue_file(tmp_path / "catalogue.sqlite", wall_name="Living room"))
    try:
        moment = datetime(2026, 8, 12, 9, 30, tzinfo=UTC)

        with pytest.raises(StorageError, match="already stored"):
            catalogue.add_wall(Wall(id="w-second", name="Living room", created_at=moment))
    finally:
        catalogue.close()


def test_the_file_itself_refuses_a_zero_byte_original(tmp_path):
    """A zero-length file is the 2024 pipeline's known download failure."""
    catalogue = SqliteCatalogue(open_catalogue_file(tmp_path / "catalogue.sqlite"))
    try:
        moment = datetime(2026, 7, 27, 9, 30, tzinfo=UTC)
        catalogue.add_artwork(Artwork(id="w1", title="Nighthawks", created_at=moment))
        catalogue.add_source(
            Source(
                id="s1",
                artwork_id="w1",
                url="https://museum.example/1",
                provider="artic",
                source_class=SourceClass.INSTITUTIONAL,
                acquisition_method=AcquisitionMethod.DEZOOMIFY,
                rights_status=RightsStatus.PUBLIC_DOMAIN,
            )
        )

        with pytest.raises(StorageError, match="does not allow"):
            catalogue.add_original(
                Original(
                    id="o1",
                    artwork_id="w1",
                    source_id="s1",
                    relative_path="originals/w1.tif",
                    width=100,
                    height=100,
                    byte_size=0,
                    content_hash="sha256:aaa",
                )
            )
    finally:
        catalogue.close()


def test_the_file_itself_refuses_a_second_current_mat_colour(tmp_path):
    catalogue = SqliteCatalogue(open_catalogue_file(tmp_path / "catalogue.sqlite"))
    try:
        moment = datetime(2026, 7, 27, 9, 30, tzinfo=UTC)
        catalogue.add_artwork(Artwork(id="w1", title="Nighthawks", created_at=moment))
        catalogue.add_mat_color(MatColor(id="m1", artwork_id="w1", hex_rgb="#27285b", method=MatMethod.MANUAL, chosen_at=moment))

        with pytest.raises(StorageError, match="already stored"):
            catalogue.add_mat_color(
                MatColor(id="m2", artwork_id="w1", hex_rgb="#1a1a1a", method=MatMethod.MANUAL, chosen_at=moment)
            )
    finally:
        catalogue.close()
