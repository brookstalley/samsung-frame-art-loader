"""Moving a single-wall catalogue onto walls, without losing a picture.

The file this migration reads is the one every existing deployment has: a
`Theme.is_active` boolean under a partial unique index, and one directive row for
the whole installation. Every test here writes that file with raw SQL rather than
through the store, because the store no longer knows how to make one — which is
the point, and also the reason a fixture that went through it would be testing a
shape nobody has on disk.
"""

import sqlite3
from datetime import UTC, datetime

import pytest

from curation.persistence.file import open_catalogue_file
from curation.persistence.migrations import DEFAULT_WALL_NAME
from curation.persistence.sqlite import SqliteCatalogue

#: The catalogue exactly as the single-wall revision encoded it — the two tables
#: this migration reads, with the column and the singleton it takes away.
_SINGLE_WALL_DDL = """
CREATE TABLE IF NOT EXISTS artworks (
    id            TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    status        TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS themes (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL UNIQUE,
    description  TEXT,
    is_active    INTEGER NOT NULL,
    created_at   TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS themes_one_active ON themes(is_active) WHERE is_active = 1;

CREATE TABLE IF NOT EXISTS directive (
    id              INTEGER PRIMARY KEY CHECK (id = 1),
    sequence        INTEGER NOT NULL,
    pinned_work_id  TEXT REFERENCES artworks(id)
);
"""

_MOMENT = datetime(2026, 8, 11, 9, 30, tzinfo=UTC)


def _single_wall_catalogue(path, *, themes, sequence=0, pinned_work_id=None, works=()):
    """Write the pre-wall file. `themes` is (id, name, is_active) per row."""
    connection = sqlite3.connect(path)
    try:
        connection.executescript(_SINGLE_WALL_DDL)
        for work_id, title in works:
            connection.execute(
                "INSERT INTO artworks (id, title, status, created_at) VALUES (?, ?, ?, ?)",
                (work_id, title, "accepted", _MOMENT.isoformat()),
            )
        for theme_id, name, is_active in themes:
            connection.execute(
                "INSERT INTO themes (id, name, description, is_active, created_at) VALUES (?, ?, ?, ?, ?)",
                (theme_id, name, None, is_active, _MOMENT.isoformat()),
            )
        connection.execute("INSERT INTO directive (id, sequence, pinned_work_id) VALUES (1, ?, ?)", (sequence, pinned_work_id))
        connection.commit()
    finally:
        connection.close()
    return path


def _columns(path, table):
    connection = sqlite3.connect(path)
    try:
        return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
    finally:
        connection.close()


def _names(path, kind):
    connection = sqlite3.connect(path)
    try:
        return {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = ?", (kind,))}
    finally:
        connection.close()


def test_the_active_theme_ends_up_hanging_on_the_one_wall(tmp_path):
    """The assumption the whole chunk rests on: no deployment loses its picture.

    A curator whose wall was showing Late night before the upgrade has to find it
    showing Late night after, without hanging anything.
    """
    path = _single_wall_catalogue(
        tmp_path / "catalogue.sqlite",
        themes=[("t1", "Late night", 1), ("t2", "Daylight", 0)],
    )

    catalogue = SqliteCatalogue(open_catalogue_file(path, wall_name="Living room"))
    try:
        walls = catalogue.list_walls()
        assert [wall.name for wall in walls] == ["Living room"]
        assert catalogue.get_assignment(walls[0].id).theme_id == "t1"
        # And nothing was hung anywhere else: the other theme keeps existing and
        # hangs nowhere, which is the ordinary state of a theme.
        assert [assignment.theme_id for assignment in catalogue.list_assignments()] == ["t1"]
    finally:
        catalogue.close()


def test_exactly_one_wall_is_created(tmp_path):
    path = _single_wall_catalogue(tmp_path / "catalogue.sqlite", themes=[("t1", "Late night", 1)])

    catalogue = SqliteCatalogue(open_catalogue_file(path))
    try:
        assert len(catalogue.list_walls()) == 1
    finally:
        catalogue.close()


def test_the_wall_is_named_from_configuration(tmp_path):
    path = _single_wall_catalogue(tmp_path / "catalogue.sqlite", themes=[])

    catalogue = SqliteCatalogue(open_catalogue_file(path, wall_name="The study"))
    try:
        assert [wall.name for wall in catalogue.list_walls()] == ["The study"]
    finally:
        catalogue.close()


def test_a_deployment_that_configured_no_name_still_gets_a_named_wall(tmp_path):
    """The name is the noun every confirmation about that wall is built around,
    so there is no such thing as an unnamed one."""
    path = _single_wall_catalogue(tmp_path / "catalogue.sqlite", themes=[])

    catalogue = SqliteCatalogue(open_catalogue_file(path))
    try:
        assert [wall.name for wall in catalogue.list_walls()] == [DEFAULT_WALL_NAME]
    finally:
        catalogue.close()


def test_the_wall_keeps_the_name_it_has_when_configuration_changes(tmp_path):
    """Once a wall exists the name is the curator's, not the deployment's.

    A configuration value that overwrote it on every restart would undo a rename
    silently, which is worse than not offering a rename at all.
    """
    path = _single_wall_catalogue(tmp_path / "catalogue.sqlite", themes=[])
    open_catalogue_file(path, wall_name="Living room").close()

    catalogue = SqliteCatalogue(open_catalogue_file(path, wall_name="Somewhere else"))
    try:
        assert [wall.name for wall in catalogue.list_walls()] == ["Living room"]
    finally:
        catalogue.close()


def test_the_singleton_directive_becomes_the_walls_own_counter(tmp_path):
    """Carried rather than restarted.

    The display plane acts once each time it sees the number go up. A counter
    that dropped to zero here would make the next ordinary advance look like a
    step already taken, and the wall would sit still while the curator pressed.
    """
    path = _single_wall_catalogue(
        tmp_path / "catalogue.sqlite",
        themes=[("t1", "Late night", 1)],
        works=[("w1", "Nighthawks")],
        sequence=41,
        pinned_work_id="w1",
    )

    catalogue = SqliteCatalogue(open_catalogue_file(path))
    try:
        wall = catalogue.list_walls()[0]
        directive = catalogue.get_directive(wall.id)
        assert (directive.sequence, directive.pinned_work_id) == (41, "w1")
    finally:
        catalogue.close()


def test_the_migration_itself_does_not_advance_the_sequence(tmp_path):
    """An upgrade is not an instruction to the display plane.

    An advance here would fire a directive nobody issued, stepping the wall to an
    unrelated work the first time the plane restarted.
    """
    path = _single_wall_catalogue(tmp_path / "catalogue.sqlite", themes=[("t1", "Late night", 1)], sequence=7)

    catalogue = SqliteCatalogue(open_catalogue_file(path))
    try:
        assert catalogue.get_directive(catalogue.list_walls()[0].id).sequence == 7
    finally:
        catalogue.close()


def test_a_catalogue_with_no_active_theme_hangs_nothing_rather_than_promoting_one(tmp_path):
    """The promotion is dropped, not made per-wall.

    `reconcile` used to activate the oldest theme when none was active. With more
    than one wall that rule hangs the same theme in every room unbidden, and the
    honest empty state is already designed — so the migration leaves the wall
    empty and says nothing was hanging.
    """
    path = _single_wall_catalogue(
        tmp_path / "catalogue.sqlite",
        themes=[("t1", "Late night", 0), ("t2", "Daylight", 0)],
    )

    catalogue = SqliteCatalogue(open_catalogue_file(path))
    try:
        assert catalogue.list_assignments() == []
        assert len(catalogue.list_themes()) == 2
    finally:
        catalogue.close()


def test_the_single_wall_shape_is_taken_away_rather_than_left_beside_the_new_one(tmp_path):
    """Two places to read "what is on the wall" is one too many.

    The column and the singleton table both go, so no later code can read a
    boolean nothing writes and reach a different answer from the assignment rows.
    """
    path = _single_wall_catalogue(tmp_path / "catalogue.sqlite", themes=[("t1", "Late night", 1)])

    open_catalogue_file(path).close()

    assert "is_active" not in _columns(path, "themes")
    assert "themes_one_active" not in _names(path, "index")
    assert "directive" not in _names(path, "table")


def test_reopening_a_migrated_file_changes_nothing(tmp_path):
    """It runs on every open, so it has to be safe on a file it already moved.

    The failure this refuses is a second wall per restart, which would look like
    a hardware inventory growing on its own.
    """
    path = _single_wall_catalogue(tmp_path / "catalogue.sqlite", themes=[("t1", "Late night", 1)], sequence=3)
    open_catalogue_file(path, wall_name="Living room").close()

    first = SqliteCatalogue(open_catalogue_file(path, wall_name="Living room"))
    wall_id = first.list_walls()[0].id
    first.close()

    reopened = SqliteCatalogue(open_catalogue_file(path, wall_name="Living room"))
    try:
        assert [wall.id for wall in reopened.list_walls()] == [wall_id]
        assert reopened.get_directive(wall_id).sequence == 3
        assert reopened.get_assignment(wall_id).theme_id == "t1"
    finally:
        reopened.close()


def test_an_interrupted_migration_is_finished_by_the_next_open(tmp_path):
    """The rows are carried and committed before anything is dropped.

    So a file caught between the two halves holds both shapes, and the next open
    reads that as "already migrated, still to tidy" rather than as a fresh file
    it should establish a second wall in.
    """
    path = _single_wall_catalogue(tmp_path / "catalogue.sqlite", themes=[("t1", "Late night", 1)], sequence=9)
    open_catalogue_file(path).close()

    # Put the old shape back beside the new, which is exactly the state an open
    # interrupted between the carry and the drops leaves behind.
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            "ALTER TABLE themes ADD COLUMN is_active INTEGER NOT NULL DEFAULT 0;"
            "CREATE UNIQUE INDEX IF NOT EXISTS themes_one_active ON themes(is_active) WHERE is_active = 1;"
            "CREATE TABLE directive (id INTEGER PRIMARY KEY CHECK (id = 1), sequence INTEGER NOT NULL,"
            " pinned_work_id TEXT REFERENCES artworks(id));"
            "INSERT INTO directive (id, sequence, pinned_work_id) VALUES (1, 0, NULL);"
        )
        connection.commit()
    finally:
        connection.close()

    catalogue = SqliteCatalogue(open_catalogue_file(path))
    try:
        wall_ids = [wall.id for wall in catalogue.list_walls()]
        assert len(wall_ids) == 1, "a half-migrated file must not acquire a second wall"
        # The carried counter stands: the zero in the resurrected singleton is
        # not read, because a file with a wall has already been carried.
        assert catalogue.get_directive(wall_ids[0]).sequence == 9
    finally:
        catalogue.close()

    assert "is_active" not in _columns(path, "themes")
    assert "directive" not in _names(path, "table")


def test_a_fresh_file_needs_no_carrying_and_still_gets_its_wall(tmp_path):
    """The seed and the migration are one step, because a catalogue with no wall
    is unusable either way — nothing can be hung on it and no request can name one.

    Unparametrised, deliberately. This was a `parametrize` over a pin that the
    body then discarded — there is no directive on a fresh file for a pin to be
    carried *from*, so the two cases ran the identical assertions and the report
    claimed a coverage that did not exist. Carrying a pin is tested where a pin
    can exist, on a file that already holds one.
    """
    catalogue = SqliteCatalogue(open_catalogue_file(tmp_path / "catalogue.sqlite"))
    try:
        wall = catalogue.list_walls()[0]
        assert catalogue.get_directive(wall.id).sequence == 0
        assert catalogue.get_assignment(wall.id) is None
    finally:
        catalogue.close()


def test_a_hand_edited_file_with_two_active_themes_hangs_the_older_one(tmp_path):
    """The tie-break the partial index made unreachable, and the reason it is there.

    `themes_one_active` stopped two active themes reaching a file this product
    wrote — it did not stop a curator opening the file with `sqlite3` and setting
    a flag, which is the one way this state arrives. The migration has to resolve
    it the same way on every machine that opens the file, or two Pis reading one
    restored backup hang different pictures. Written with the index dropped,
    because that is the only shape this row can exist in.
    """
    path = tmp_path / "catalogue.sqlite"
    connection = sqlite3.connect(path)
    try:
        connection.executescript(_SINGLE_WALL_DDL)
        connection.execute("DROP INDEX themes_one_active")
        for theme_id, name, created_at in (
            ("t-late", "Daylight", datetime(2026, 8, 2, tzinfo=UTC)),
            ("t-early", "Late night", datetime(2026, 8, 1, tzinfo=UTC)),
        ):
            connection.execute(
                "INSERT INTO themes (id, name, description, is_active, created_at) VALUES (?, ?, ?, 1, ?)",
                (theme_id, name, None, created_at.isoformat()),
            )
        connection.execute("INSERT INTO directive (id, sequence, pinned_work_id) VALUES (1, 0, NULL)")
        connection.commit()
    finally:
        connection.close()

    catalogue = SqliteCatalogue(open_catalogue_file(path))
    try:
        wall = catalogue.list_walls()[0]
        # The older theme, not the one the rows happen to be ordered by.
        assert catalogue.get_assignment(wall.id).theme_id == "t-early"
    finally:
        catalogue.close()


def test_an_interpreter_too_old_to_drop_a_column_says_so_rather_than_failing_on_syntax(tmp_path, monkeypatch):
    """`ALTER TABLE ... DROP COLUMN` arrived in SQLite 3.35, and the machine that
    lacks it is the one nobody is sitting at.

    Without the check the failure is a syntax error naming neither the version
    nor the remedy, on the deployment least able to interpret it.
    """
    path = _single_wall_catalogue(tmp_path / "catalogue.sqlite", themes=[("t1", "Late night", 1)])
    monkeypatch.setattr(sqlite3, "sqlite_version", "3.34.1")

    with pytest.raises(RuntimeError) as refused:
        open_catalogue_file(path).close()

    assert "3.35.0" in str(refused.value)
    assert "3.34.1" in str(refused.value)
