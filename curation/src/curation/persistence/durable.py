"""A durable store over one SQLite file, keyed by table, primary key and row.

The catalogue's persistence is split in two. This module is the lower half: a
store addressed as tables, primary keys and rows, which holds no artwork, artist
or theme concept. `sqlite.py` is the upper half — the domain adapter that maps
records to rows and owns ordering, paging and totals.

The split is by *schema* knowledge, not by vocabulary: this module shares the
package's two error types and phrases a refusal in the catalogue's words ("it is
already in the catalogue"), because the reason a write was refused has to reach a
curator intact and only this layer can see which constraint fired. So it is
reusable across tables, not across products — worth knowing before lifting it
somewhere else.

**Why this exact shape.** `fetch_one` / `upsert` / `delete` / `scan`, keyed by a
table name plus a column-to-value primary-key mapping, is the decomposition,
naming and argument shape of the `DurableStore` protocol in the three-tier
framework this operator maintains (`pacepace/3tears`, `core/backends/protocol.py`).
Matching it deliberately means that adopting that framework's collection layer
later is an adapter over this class rather than a rewrite of it. Nothing here
imports the framework: the contract is matched structurally, and a dependency is
not worth taking to call no code.

**One knowing divergence.** The framework's methods are `async`; these are not,
because this product's ratified shape is async at the I/O boundary over a
synchronous core. An adapter would delegate through `asyncio.to_thread` — which
blocking `sqlite3` requires inside an event loop in any case, so that wrapper is
work the async colour owes rather than work this divergence creates.

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
statement runs under a single lock. The server accepts requests on an event loop
thread while tests and startup code touch the store from another, so the connection
genuinely crosses threads; the lock is what makes that safe rather than
usually-safe. Queries are sub-millisecond point lookups against a household-sized
catalogue, so serialising them costs nothing worth measuring.
"""

import logging
import sqlite3
import threading
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal, get_args

from curation.persistence.catalogue import StorageError, StoreMisuseError

log = logging.getLogger(__name__)

#: How `upsert` resolves a row that is already present. `raise` is a plain insert
#: and is what a catalogue addition wants — re-adding a work is a mistake, not an
#: edit. The framework's contract names all three, so all three exist here.
ConflictPolicy = Literal["raise", "ignore", "update"]

#: Derived from the type rather than restated, so the runtime check and the
#: annotation cannot drift apart.
_POLICIES: Final[frozenset[str]] = frozenset(get_args(ConflictPolicy))


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


def _refusal(exc: sqlite3.IntegrityError) -> str:
    """Why the store said no, in the catalogue's terms rather than SQL's.

    Falls back to a generic phrase rather than the driver text: an unrecognised
    constraint is still not something a caller should be reading table names out
    of.
    """
    text = str(exc).lower()
    if "unique" in text or "primary key" in text:
        return "it is already in the catalogue."
    if "foreign key" in text:
        return "it refers to a record that is not in the catalogue."
    if "not null" in text:
        return "a required field was empty."
    return "the catalogue refused the write."


class SqliteDurableStore:
    """One SQLite file, addressed as tables of rows."""

    def __init__(self, path: Path | str, schema: str) -> None:
        self._lock = threading.Lock()
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        with self._lock:
            # Foreign keys are off by default in SQLite, which would let a row
            # keep pointing at a parent that was never written.
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.executescript(schema)
            self._connection.commit()
            self._columns = self._read_schema()

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
        ordering = ", ".join(f'"{term.column}"' + (" COLLATE NOCASE" if term.ignore_case else "") for term in order_by)
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

    def close(self) -> None:
        """Release the underlying resources."""
        with self._lock:
            self._connection.close()

    # -- internals ------------------------------------------------------------

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

        A `None` means "this column is unset" and renders `IS NULL`, because SQL's
        `= NULL` is never true: binding it would report no matching rows for a
        column that has them. That is the same silent-wrong-answer failure the
        whole-key rule above refuses, and most of the schema arriving next is
        nullable, so it is worth being right about here rather than in each
        caller.
        """
        columns = self._validate(table, terms.keys())
        if as_key:
            self._require_whole_key(table, columns)
        clauses: list[str] = []
        values: list[Any] = []
        for column in columns:
            value = terms[column]
            if value is None and as_key:
                # `IS NULL` is right for a filter and wrong for a key. SQLite does
                # not enforce NOT NULL on a TEXT primary key, so a null key
                # component can match several rows, and addressing "one row" would
                # return an arbitrary one — what the whole-key rule above refuses.
                raise StoreMisuseError(f"Column {column!r} of {table!r}'s primary key cannot be null when addressing a row.")
            if value is None:
                clauses.append(f'"{column}" IS NULL')
            else:
                clauses.append(f'"{column}" = ?')
                values.append(value)
        return " AND ".join(clauses), tuple(values)

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
        try:
            with self._lock, self._connection:
                return int(self._connection.execute(statement, values).rowcount)
        except sqlite3.IntegrityError as exc:
            # The driver's own text names tables and columns, and a message raised
            # here travels to the tool surface intact. Translate it to the reason
            # in the catalogue's own terms and keep the SQL detail in the journal,
            # where diagnosis happens. The table has to be logged explicitly:
            # sqlite3's text for a foreign-key violation is exactly "FOREIGN KEY
            # constraint failed", naming neither table nor column nor value.
            reason = _refusal(exc)
            log.warning("Refused a write to %s: %s", table, exc)
            raise StorageError(reason, reason=reason) from exc
