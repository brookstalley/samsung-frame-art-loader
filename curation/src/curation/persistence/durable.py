"""A durable store over one SQLite file, keyed by table, primary key and row.

The catalogue's persistence is split in two. This module is the lower half: a
store addressed as tables, primary keys and rows, which holds no artwork, artist
or theme concept. `sqlite.py` is the upper half — the domain adapter that maps
records to rows and owns ordering, paging and totals.

The split is by *schema* knowledge: this module shares the package's two error
types and phrases a refusal in plain words ("it is already stored"), because the
reason a write was refused has to reach a curator intact and only this layer can
see which constraint fired.

**Those words are deliberately domain-neutral, and that is a correction.** They
said "already in the catalogue" while this store held one domain; two adapters now
sit over it, and a refused `CandidateWork` insert answered "it is already in the
catalogue" about a record that is precisely *not* in the catalogue — acceptance is
what puts one there. A layer that cannot see which table it refused must not
name one. Whichever adapter caught the refusal is the layer that knows the
subject, and it is the one that says so.

**Why this exact shape.** `fetch_one` / `upsert` / `delete` / `scan`, keyed by a
table name plus a column-to-value primary-key mapping, is the decomposition and
naming of the `DurableStore` protocol in the three-tier framework this operator
maintains (`pacepace/3tears`, `core/backends/protocol.py`). Matching it
deliberately means that adopting that framework's collection layer later is an
adapter over this class rather than a rewrite of it. Nothing here imports the
framework: the contract is matched structurally, and a dependency is not worth
taking to call no code.

**Where the signatures differ, and why each.** The match is of decomposition and
naming; the argument lists are a subset, which is worth stating precisely so that
nobody reads a promise here that the code does not carry.

- The framework's methods are `async`; these are not, because this product's
  ratified shape is async at the I/O boundary over a synchronous core. An adapter
  would delegate through `asyncio.to_thread` — which blocking `sqlite3` requires
  inside an event loop in any case, so that wrapper is work the async colour owes
  rather than work this divergence creates.
- `fetch_one`, `upsert` and `delete` take `conn` there — a backend-specific
  transaction handle, so that several writes commit together against a pooled
  connection. (`scan` does not; it is read-only and unordered.) This store has
  exactly one connection, so the handle would name the only thing it could ever
  name: `transaction()` below is the same capability with the handle left
  implicit, and it is what a rule spanning rows is applied inside.
- `upsert` also takes `cas`, an optimistic-lock fence against a row's previous
  `date_updated`. Nothing here has that column, and a single-writer process on a
  serialised connection has no concurrent modification to lose — so the parameter
  would be one that could only ever be passed `None`.
- `pk` is required here and optional there, because the framework permits a
  backend that already knows a table's key; this one takes it and then checks it
  against the key the file actually declares.

**`select_page` is deliberately outside the matched contract.** That framework's
structured contract has no ordered, paged, counted read, and its collection layer
has no query API at all, so a listing path reaches a durable store directly under
every configuration. Keeping it here, named as an addition, is what stops the
compatibility promise from being read onto a method that does not carry it.

**Identifiers are validated, never trusted.** Table and column names reach SQL as
interpolated identifiers because they cannot be bound as parameters. Every one is
checked against the schema the file actually has, read back at open time, so a
caller's typo raises `StoreMisuseError` rather than composing a malformed
statement — and no caller can widen what reaches SQL. That type is deliberately
separate from `StorageError`: a refused write is something a caller could
reasonably have attempted and its message is fit to show, whereas a bad column
name is a bug whose message names internals and must not be repeated to whoever
made the request.

**Concurrency.** One connection is opened with `check_same_thread=False` and every
statement runs under a single reentrant lock. The server accepts requests on an
event loop thread while tests and startup code touch the store from another, so
the connection genuinely crosses threads; the lock is what makes that safe rather
than usually-safe. Queries are sub-millisecond point lookups against a
household-sized catalogue, so serialising them costs nothing worth measuring — and
a transaction holds the lock for its whole body, which is what lets the one
connection carry a multi-statement group without another thread writing into the
middle of it.
"""

import logging
import sqlite3
import threading
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal, get_args

from curation.persistence.errors import StorageError, StoreMisuseError

log = logging.getLogger(__name__)

#: How `upsert` resolves a row that is already present. `raise` is a plain insert
#: and is what a catalogue addition wants — re-adding a work is a mistake, not an
#: edit. The framework's contract names all three, so all three exist here.
ConflictPolicy = Literal["raise", "ignore", "update"]

#: Derived from the type rather than restated, so the runtime check and the
#: annotation cannot drift apart.
_POLICIES: Final[frozenset[str]] = frozenset(get_args(ConflictPolicy))

#: One schema change this store cannot infer, applied to the open file. Opaque
#: on purpose: this module holds no artwork, theme or wall concept, and a
#: migration that named one here would put domain knowledge in the tier whose
#: whole reason to exist is not having any. `migrations.py` writes them.
type Migration = Callable[[sqlite3.Connection], None]


@dataclass(frozen=True, slots=True)
class _TableInfo:
    """What one table in the open file looks like."""

    columns: frozenset[str]
    #: The primary-key columns in key order, empty for a table declaring none.
    key: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OrderBy:
    """One sort term for `select_page`.

    A column and a flag, rather than a SQL fragment, so that ordering cannot
    become a second channel for arbitrary SQL into a store whose whole identifier
    discipline is validate-then-interpolate.
    """

    column: str
    #: Compare case-insensitively. What a person scanning a list of titles expects;
    #: SQLite's NOCASE folds ASCII only, which is the collation the catalogue file
    #: already carries.
    ignore_case: bool = False
    #: Sort rows whose value is unset after the rest. SQLite puts them first by
    #: default, which is wrong wherever the column means "the curator said where
    #: this goes": the entries nobody ordered would lead the ones somebody did.
    nulls_last: bool = False
    #: Largest or truest first. What "newest first" and "the primary one first"
    #: both need, and neither is expressible by choosing a different column.
    descending: bool = False


def _refusal(exc: sqlite3.IntegrityError) -> str:
    """Why the store said no, in plain terms rather than SQL's.

    Falls back to a generic phrase rather than the driver text: an unrecognised
    constraint is still not something a caller should be reading table names out
    of.
    """
    text = str(exc).lower()
    if "unique" in text or "primary key" in text:
        return "it is already stored."
    if "foreign key" in text:
        return "it refers to a record that is not stored."
    if "not null" in text:
        return "a required field was empty."
    if "check" in text:
        return "a field held a value the store does not allow."
    return "the store refused the write."


def _describe(connection: sqlite3.Connection) -> dict[str, dict[str, sqlite3.Row]]:
    """Every table's columns, as the database itself reports them."""
    tables = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    described: dict[str, dict[str, sqlite3.Row]] = {}
    for table in tables:
        info = connection.execute(f'PRAGMA table_info("{table["name"]}")').fetchall()
        described[table["name"]] = {column["name"]: column for column in info}
    return described


def _column_declaration(column: sqlite3.Row) -> str:
    """Rebuild one column's DDL from what `PRAGMA table_info` reports of it.

    Enough of a declaration for `ADD COLUMN` and no more: type, nullability and
    default. A primary key, a foreign key or a check cannot be added to an
    existing column by this route in SQLite, so reconstructing them here would
    write a promise the statement does not keep.
    """
    parts = [f'"{column["name"]}"']
    if column["type"]:
        parts.append(column["type"])
    if column["notnull"]:
        parts.append("NOT NULL")
    if column["dflt_value"] is not None:
        parts.append(f"DEFAULT {column['dflt_value']}")
    return " ".join(parts)


class SqliteDurableStore:
    """One SQLite file, addressed as tables of rows."""

    def __init__(self, path: Path | str, schema: str, migrations: Sequence[Migration] = ()) -> None:
        # Reentrant because `transaction()` holds it across a body that calls
        # back into the store's own methods, each of which takes it again.
        self._lock = threading.RLock()
        #: How many `transaction()` blocks are open. Non-zero means a write must
        #: leave committing to the outermost one.
        self._depth = 0
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        with self._lock:
            # Foreign keys are off by default in SQLite, which would let a row
            # keep pointing at a parent that was never written.
            self._connection.execute("PRAGMA foreign_keys = ON")
            # **Widened before the script runs, not after, and the order is the
            # whole point.** The script declares indexes as well as tables, and an
            # index may name a column that only widening adds to a file older than
            # it — `CREATE INDEX IF NOT EXISTS x ON t(c)` raises `no such column`
            # rather than skipping, so a widening that ran afterwards never ran at
            # all. Running it first costs nothing on a new file, where there is no
            # existing table to widen.
            self._widen_existing_tables(schema)
            self._connection.executescript(schema)
            self._connection.commit()
            # After the schema, because a migration carries rows into tables the
            # schema has just created; before `_read_schema`, because one may
            # take a column away and this store validates every identifier
            # against what the file actually holds.
            for migration in migrations:
                migration(self._connection)
            self._connection.commit()
            self._columns = self._read_schema()

    # -- atomicity ------------------------------------------------------------

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Commit every write in the body together, or none of them.

        A rule that spans rows — exactly one mat colour current, at most one
        source primary — is applied as a clear-then-set pair, and a pair interrupted
        between its halves leaves the catalogue in the state the rule forbids.
        Wrapping the pair here is what makes "it cannot be observed half-applied"
        true rather than likely.

        The lock is held for the whole body. That is deliberate: one connection
        cannot carry two interleaved statement groups, so another thread writing
        into the middle would silently join this transaction and be rolled back
        with it. Serialising costs nothing at this catalogue's size, and the
        alternative is a wrong answer rather than a slow one.

        Nesting joins the outer group, so a service operation assembled from
        other service operations still commits exactly once.
        """
        with self._lock:
            if self._depth:
                self._depth += 1
                try:
                    yield
                finally:
                    self._depth -= 1
                return
            self._depth = 1
            try:
                yield
            except BaseException:  # prawduct:allow prawduct/broad-except -- cleanup-and-reraise; rollback must run on any exit
                # Deliberately wider than `Exception`, and it swallows nothing:
                # the group is abandoned and the same exception continues. A
                # `KeyboardInterrupt` or a generator being closed early leaves
                # the body just as surely as an error does, and leaving half a
                # rule applied is the one outcome this block exists to prevent.
                self._connection.rollback()
                raise
            else:
                self._connection.commit()
            finally:
                self._depth = 0

    # -- the matched contract -------------------------------------------------

    def fetch_one(self, table: str, pk: Mapping[str, Any]) -> dict[str, Any] | None:
        """Return the row whose primary key equals `pk`, or None on a miss."""
        where, values = self._equality(table, pk, as_key=True)
        with self._lock:
            row = self._connection.execute(f'SELECT * FROM "{table}" WHERE {where}', values).fetchone()
        return None if row is None else dict(row)

    def upsert(
        self,
        table: str,
        row: Mapping[str, Any],
        *,
        pk: Sequence[str],
        on_conflict: ConflictPolicy = "update",
    ) -> int:
        """Write `row`, resolving an existing primary key per `on_conflict`.

        Returns the number of rows the statement affected: 1 when it wrote, and 0
        when it deliberately did not — `ignore` meeting a row that is already
        there, or `update` meeting one in a table whose columns are all key, where
        there is nothing an update could change.
        """
        if on_conflict not in _POLICIES:
            raise StoreMisuseError(f"Unknown conflict policy {on_conflict!r}; expected one of {', '.join(sorted(_POLICIES))}.")
        columns = self._validate(table, row.keys())
        self._validate(table, pk)
        placeholders = ", ".join("?" for _ in columns)
        quoted = ", ".join(f'"{column}"' for column in columns)
        statement = f'INSERT INTO "{table}" ({quoted}) VALUES ({placeholders})'
        if on_conflict != "raise":
            # Only a conflict clause names the key. A target that is not the
            # table's real key resolves nothing, so `update` would quietly start
            # inserting duplicates instead of updating; a plain insert reaches no
            # key at all and needs no such promise.
            self._require_whole_key(table, pk)
            statement += self._conflict_clause(columns, pk, on_conflict)
        return self._write(statement, tuple(row[column] for column in columns), table=table)

    def delete(self, table: str, pk: Mapping[str, Any]) -> None:
        """Delete the row whose primary key equals `pk`. A missing row is not an error."""
        where, values = self._equality(table, pk, as_key=True)
        self._write(f'DELETE FROM "{table}" WHERE {where}', values, table=table)

    def scan(self, table: str, filters: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
        """Return every row matching the equality `filters`, or every row when there are none.

        Unordered, by the contract this matches. Callers that need an order say so
        through `select_page`.
        """
        where, values = self._equality(table, filters or {}, as_key=False)
        clause = "" if not where else f" WHERE {where}"
        with self._lock:
            rows = self._connection.execute(f'SELECT * FROM "{table}"{clause}', values).fetchall()
        return [dict(row) for row in rows]

    # -- outside the matched contract -----------------------------------------

    def select_page(
        self,
        table: str,
        *,
        order_by: Sequence[OrderBy],
        filters: Mapping[str, Any] | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """Return one ordered page and the size of the unpaged set it came from.

        The total is what lets a caller say "showing 20 of 84" instead of silently
        handing back a short list, and it is counted in the same statement pair as
        the page so the two cannot disagree about the filter.
        """
        if not order_by:
            raise StoreMisuseError("A page must declare its order, or two requests for the same page can differ.")
        where, values = self._equality(table, filters or {}, as_key=False)
        clause = "" if not where else f" WHERE {where}"
        self._validate(table, [term.column for term in order_by])
        ordering = ", ".join(self._order_term(term) for term in order_by)
        # SQLite will not take OFFSET without LIMIT, and -1 is its "no limit".
        # Spelling that out beats letting a caller's offset fall on the floor.
        if limit is None and not offset:
            window, page_values = "", values
        elif limit is None:
            window, page_values = " LIMIT -1 OFFSET ?", (*values, offset)
        else:
            window, page_values = " LIMIT ? OFFSET ?", (*values, limit, offset)
        with self._lock:
            total = self._connection.execute(f'SELECT COUNT(*) FROM "{table}"{clause}', values).fetchone()[0]
            rows = self._connection.execute(
                f'SELECT * FROM "{table}"{clause} ORDER BY {ordering}{window}', page_values
            ).fetchall()
        return [dict(row) for row in rows], total

    @contextmanager
    def reading(self) -> Iterator[None]:
        """Hold the file still for several reads that must agree with each other.

        `select_page` takes its COUNT and its page under one lock by its own
        design, because a total that disagrees with the rows beneath it is a
        wrong answer rather than a stale one. A composite read assembled from
        *several* calls needs the same guarantee and cannot get it from the
        individual locks: handlers are synchronous `def`, so Starlette runs them
        in a worker thread and a write can land between any two of them.

        The lock is the same re-entrant one `transaction` takes, so a read scope
        inside a transaction — or nested inside another read scope — joins rather
        than deadlocks.

        **Reads only, and it is not a snapshot.** Nothing here begins a SQLite
        transaction: it excludes this process's own writers, which is what the
        one-connection design makes sufficient, and it says nothing about a
        second process. There is no second process by design — `catalogue.sqlite`
        has one writer and it is this plane.
        """
        with self._lock:
            yield

    def select_rows(self, statement: str, values: Sequence[Any] = ()) -> list[dict[str, Any]]:
        """Run one adapter-authored `SELECT` and return its rows.

        **The escape hatch for a read this store's own vocabulary cannot express**,
        and it is deliberately narrow: a text search across three tables, and a
        facet count grouped over one of them, are joins with a `GROUP BY` — there
        is no decomposition of `fetch_one`/`scan`/`select_page` that reaches them,
        and a general query builder here would be a second SQL dialect to maintain
        for the sake of not writing SQL.

        **It does not weaken the identifier discipline, and the reason is who
        writes the statement.** Every other method interpolates table and column
        names supplied by a *caller*, which is why they are validated against the
        file's own schema first. A statement passed here is written in this
        package by the adapter that declares the schema — the same module, the
        same commit — and every value a caller ever supplied is bound as a
        parameter. `_validate` would have nothing to check: there is no caller
        identifier in the statement to check.

        The layering is unchanged by it. This module still holds no artwork, theme
        or wall concept: it owns the connection, the lock and the row shape, and
        the SQL arrives from above the way a table name does.

        Read-only by contract — it neither commits nor rolls back, so a write sent
        through it would leave an implicit transaction open for the next commit to
        publish. `SELECT` only.
        """
        with self._lock:
            rows = self._connection.execute(statement, tuple(values)).fetchall()
        return [dict(row) for row in rows]

    def close(self) -> None:
        """Release the underlying resources."""
        with self._lock:
            self._connection.close()

    # -- internals ------------------------------------------------------------

    def _widen_existing_tables(self, schema: str) -> None:
        """Add columns the declared schema has and the file on disk does not.

        `CREATE TABLE IF NOT EXISTS` does nothing whatsoever to a table that
        already exists, so a column added to the DDL never reaches a file written
        before it. What that produces is not a loud failure: the adapter writes
        the new column, `_validate` refuses it by name, and the refusal reads as a
        code defect rather than as a file predating the column. A file outlives
        any single version of this code, so closing that gap is this layer's job.

        The intended shape is learned by running the same DDL against an empty
        in-memory database and reading it back — SQLite parses the schema, not
        this module, so the two can never disagree about what the DDL meant.

        **Only additions.** `ALTER TABLE ADD COLUMN` is the one schema change
        SQLite applies in place and the only one that cannot lose data. A column
        that changed type is reported and left alone, because SQLite's types are
        affinities and a rename-copy-swap is a migration to write deliberately
        rather than to infer here. A `NOT NULL` addition with no default is
        refused outright: SQLite cannot add one to a table with rows, so applying
        it would half-migrate the file.

        **A third case is neither applied nor reported, and it is silent: a
        `CHECK` or `UNIQUE` clause added to a column of a table that already
        exists.** The comparison below is built from `PRAGMA table_info`, which
        states a column's name, type, nullability and default and says nothing
        about its constraints — so a constraint added later binds new files and
        not old ones, with nothing to read back. Standing invariants are
        deliberately carried by partial unique *indexes* instead, because
        `CREATE UNIQUE INDEX IF NOT EXISTS` does reach an existing file; a
        constraint that has to hold on every file belongs there rather than in a
        column clause, and one added to a column needs a written migration.

        **Everything this cannot do is what `migrations.py` is for**, and the
        `migrations` argument to this class is where one is handed in. A column
        that goes away, a table replaced by a differently-keyed one, rows carried
        from the first shape to the second: none of it is inferable from a
        comparison of two schemas, because the comparison cannot see intent.
        """
        intended = sqlite3.connect(":memory:")
        try:
            intended.row_factory = sqlite3.Row
            intended.executescript(schema)
            wanted = _describe(intended)
        finally:
            intended.close()

        actual = _describe(self._connection)
        for table, columns in wanted.items():
            present = actual.get(table)
            if present is None:
                # Not in the file yet — the script that runs after this creates
                # it whole, so there is nothing to widen.
                continue
            for name, column in columns.items():
                if name in present:
                    if column["type"].strip().upper() != present[name]["type"].strip().upper():
                        log.warning(
                            "Table %r column %r is %s in this file and %s in the declared schema; leaving it as it is.",
                            table,
                            name,
                            present[name]["type"] or "untyped",
                            column["type"] or "untyped",
                        )
                    continue
                if column["notnull"] and column["dflt_value"] is None:
                    raise StoreMisuseError(
                        f"Cannot add column {name!r} to existing table {table!r}: it is NOT NULL with no default, "
                        "which SQLite cannot add to a table that already has rows. This needs a written migration."
                    )
                self._connection.execute(f'ALTER TABLE "{table}" ADD COLUMN {_column_declaration(column)}')
                log.info("Added column %r to table %r, which this catalogue file predated.", name, table)

    def _read_schema(self) -> dict[str, _TableInfo]:
        """What each table actually has, read from the open file.

        Read back rather than parsed out of the DDL that was just executed: the
        file is the authority, and a file opened from disk carries a schema this
        process never wrote.
        """
        tables = self._connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        schema: dict[str, _TableInfo] = {}
        for table in tables:
            info = self._connection.execute(f'PRAGMA table_info("{table["name"]}")').fetchall()
            # `pk` is 0 for an ordinary column and otherwise the column's 1-based
            # position within the key, which is what orders a composite one.
            key = sorted((column["pk"], column["name"]) for column in info if column["pk"])
            schema[table["name"]] = _TableInfo(
                columns=frozenset(column["name"] for column in info),
                key=tuple(name for _, name in key),
            )
        return schema

    def _validate(self, table: str, columns: Iterable[str]) -> tuple[str, ...]:
        """Check a table and its columns against the real schema; return the columns in order."""
        known = self._columns.get(table)
        if known is None:
            raise StoreMisuseError(f"No table named {table!r} in this store.")
        named = tuple(columns)
        unknown = [column for column in named if column not in known.columns]
        if unknown:
            raise StoreMisuseError(f"Table {table!r} has no column named {', '.join(repr(column) for column in unknown)}.")
        return named

    def _require_whole_key(self, table: str, columns: Iterable[str]) -> None:
        """Refuse a key that is not exactly the table's own.

        Half of a composite key is a valid `WHERE` clause that matches several
        rows, so without this a caller asking for one row would be handed
        whichever the file happened to return first — a wrong answer that looks
        like a right one. The join rows arriving with the rest of the schema are
        exactly the shape that would hit it.
        """
        key = self._columns[table].key
        if not key:
            raise StoreMisuseError(f"Table {table!r} has no primary key, so a single row cannot be addressed by one.")
        given = set(columns)
        if given != set(key):
            expected = ", ".join(repr(column) for column in key)
            raise StoreMisuseError(f"Addressing a row in {table!r} needs its whole primary key ({expected}).")

    def _equality(self, table: str, terms: Mapping[str, Any], *, as_key: bool) -> tuple[str, tuple[Any, ...]]:
        """Render the match terms joined by AND, with the values left to bind.

        In a filter, a `None` means "this column is unset" and renders `IS NULL`,
        because SQL's `= NULL` is never true: binding it would report no matching
        rows for a column that has them. That is the same silent-wrong-answer
        failure the whole-key rule above refuses, and most of the schema arriving
        next is nullable, so it is worth being right about here rather than in
        each caller.

        In a **key** (`as_key`), a `None` is refused instead. SQLite does not
        enforce NOT NULL on a `TEXT PRIMARY KEY`, so `IS NULL` on a key column can
        match several rows — which would put the wrong answer back on the one path
        that promises a single one. A null is a legitimate filter value and never a
        legitimate key value.
        """
        columns = self._validate(table, terms.keys())
        if as_key:
            self._require_whole_key(table, columns)
        clauses: list[str] = []
        values: list[Any] = []
        for column in columns:
            value = terms[column]
            if value is None and as_key:
                # Reason in the docstring above.
                raise StoreMisuseError(f"Column {column!r} of {table!r}'s primary key cannot be null when addressing a row.")
            if value is None:
                clauses.append(f'"{column}" IS NULL')
            else:
                clauses.append(f'"{column}" = ?')
                values.append(value)
        return " AND ".join(clauses), tuple(values)

    @staticmethod
    def _order_term(term: OrderBy) -> str:
        """Render one sort term.

        Unset values sort last as `"col" IS NULL, "col"` rather than as SQLite's
        own `NULLS LAST`, which arrived in 3.30 (2019). The expression is
        equivalent, is composed here from an already-validated column name rather
        than from anything a caller wrote, and cannot make the ordering depend on
        which SQLite the host happens to ship.
        """
        rendered = f'"{term.column}"' + (" COLLATE NOCASE" if term.ignore_case else "") + (" DESC" if term.descending else "")
        # The null test stays ascending whichever way the values run: false sorts
        # before true, so the rows that have a value come first either way.
        return f'"{term.column}" IS NULL, {rendered}' if term.nulls_last else rendered

    @staticmethod
    def _conflict_clause(columns: Sequence[str], pk: Sequence[str], on_conflict: ConflictPolicy) -> str:
        """The ON CONFLICT tail for `ignore` and `update`."""
        target = ", ".join(f'"{column}"' for column in pk)
        if on_conflict == "ignore":
            return f" ON CONFLICT ({target}) DO NOTHING"
        assignments = [f'"{column}" = excluded."{column}"' for column in columns if column not in set(pk)]
        if not assignments:
            # Every column is part of the key, so there is nothing an update could
            # change and DO UPDATE SET would not parse.
            return f" ON CONFLICT ({target}) DO NOTHING"
        return f" ON CONFLICT ({target}) DO UPDATE SET {', '.join(assignments)}"

    def _write(self, statement: str, values: tuple[Any, ...], *, table: str) -> int:
        """Run one statement, committing it unless a transaction owns that decision.

        Inside `transaction()` the commit and the rollback both belong to the
        outermost block — committing here would publish half of a rule that spans
        rows, and rolling back here would discard writes the caller made before
        this one and still believes in.
        """
        with self._lock:
            try:
                rowcount = int(self._connection.execute(statement, values).rowcount)
            except sqlite3.IntegrityError as exc:
                if not self._depth:
                    # A failed statement writes nothing, but sqlite3 has already
                    # opened an implicit transaction around it; leaving that open
                    # would hold the file's write lock until the next commit.
                    self._connection.rollback()
                # The driver's own text names tables and columns, and a message
                # raised here travels to the tool surface intact. Translate it to
                # the reason into plain terms and keep the SQL detail
                # in the journal, where diagnosis happens. The table has to be
                # logged explicitly: sqlite3's text for a foreign-key violation is
                # exactly "FOREIGN KEY constraint failed", naming neither table nor
                # column nor value.
                reason = _refusal(exc)
                log.warning("Refused a write to %s: %s", table, exc)
                raise StorageError(reason, reason=reason) from exc
            if not self._depth:
                self._connection.commit()
            return rowcount
