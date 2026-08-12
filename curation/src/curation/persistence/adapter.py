"""What a domain adapter over the durable store does the same way every time.

`sqlite.py` and `sqlite_discovery.py` are two adapters over one open file. Each
owns its own tables, its own record-to-row mapping, and its own ordering
decisions — those are product judgements and belong with the records they order.
What they share is mechanical: how an insert refuses a record already stored, how
an update refuses to create one that is not, and how the file's text columns
carry instants and money. Sharing it here is what keeps the two adapters from
answering the same question differently as they drift apart.
"""

import logging
from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Final

from curation.persistence.durable import OrderBy, SqliteDurableStore
from curation.persistence.errors import StorageError

log = logging.getLogger(__name__)

#: Most tables in this file are keyed by a single `id`. Named once so the durable
#: store is addressed the same way everywhere.
BY_ID: Final[tuple[str, ...]] = ("id",)


def to_iso(moment: datetime | None) -> str | None:
    """Store instants as UTC ISO-8601 text.

    SQLite has no datetime type, and a naive local-time string is unreadable once
    the machine's timezone changes under it.
    """
    if moment is None:
        return None
    return moment.astimezone(UTC).isoformat()


def from_iso(text: str | None) -> datetime | None:
    if text is None:
        return None
    return datetime.fromisoformat(text)


def require_datetime(text: str | None, column: str) -> datetime:
    moment = from_iso(text)
    if moment is None:
        raise StorageError(f"Row is missing its required {column} timestamp.")
    return moment


def to_money(amount: Decimal | None) -> str | None:
    """Store money as its decimal text, never as a float.

    SQLite's only numeric types are integers and IEEE doubles, and a tenth of a
    cent that cannot be represented exactly is a rounding error in a total nobody
    will ever reconcile against the provider's own figure.
    """
    if amount is None:
        return None
    return str(amount)


def from_money(text: str | None) -> Decimal | None:
    if text is None:
        return None
    return Decimal(text)


def require_money(text: str | None, column: str) -> Decimal:
    amount = from_money(text)
    if amount is None:
        raise StorageError(f"Row is missing its required {column} amount.")
    return amount


class TableAdapter:
    """A domain adapter's shared way of reaching the durable store."""

    def __init__(self, store: SqliteDurableStore) -> None:
        self._store = store

    def transaction(self) -> AbstractContextManager[None]:
        """Group several writes so they commit together or not at all.

        Delegated rather than reimplemented: both adapters run against the same
        connection, so a transaction opened through either covers writes made
        through the other. That is what lets acceptance promote a candidate's
        instances into a work's sources as one commit.
        """
        return self._store.transaction()

    def reading(self) -> AbstractContextManager[None]:
        """Group several reads so they answer about one instant of the file.

        Delegated for the same reason as `transaction` above, and it reaches the
        same lock — so a composite read spanning both adapters is as consistent
        as one inside either.
        """
        return self._store.reading()

    def close(self) -> None:
        """Release the file. Every adapter over the same file is closed with it.

        There is one connection behind both adapters, so this is one resource
        with one lifetime — closing "the catalogue" and closing "the pipeline"
        are the same act, and neither view is left usable by the other.
        """
        self._store.close()

    def _add(self, table: str, row: Mapping[str, Any], *, subject: str, key: tuple[str, ...] = BY_ID) -> None:
        """Insert a record, refusing rather than overwriting one already there.

        Adding something already stored is a mistake to report, not an edit to
        apply — so this is the conflict policy every addition takes, and revising
        a record is a different operation with its own name.
        """
        try:
            self._store.upsert(table, row, pk=key, on_conflict="raise")
        except StorageError as exc:
            # Which record was refused is knowable only here, and only this line
            # puts it in the journal: the driver's own text for a foreign-key
            # violation carries no id, and the message raised from here is
            # written for whoever asked rather than for whoever is diagnosing.
            log.warning("Refused to store %s: %s", subject, exc.reason)
            raise StorageError(f"Could not store {subject}: {exc.reason}", reason=exc.reason) from exc

    def _update(self, table: str, key: tuple[str, ...], row: Mapping[str, Any], *, subject: str) -> None:
        """Overwrite a record that is already there, refusing to create one that is not.

        The existence check and the write share a transaction so that the answer
        cannot change between them. An update that silently inserted would turn a
        typo'd id into a second record nobody meant to make.
        """
        pk = {column: row[column] for column in key}
        with self._store.transaction():
            if self._store.fetch_one(table, pk) is None:
                reason = "it is not stored."
                log.warning("Refused to update %s: %s", subject, reason)
                raise StorageError(f"Could not update {subject}: {reason}", reason=reason)
            try:
                self._store.upsert(table, row, pk=key, on_conflict="update")
            except StorageError as exc:
                log.warning("Refused to update %s: %s", subject, exc.reason)
                raise StorageError(f"Could not update {subject}: {exc.reason}", reason=exc.reason) from exc

    def _get[R](self, table: str, pk: Mapping[str, Any], build: Callable[[Mapping[str, Any]], R]) -> R | None:
        row = self._store.fetch_one(table, pk)
        return None if row is None else build(row)

    def _list[R](
        self,
        table: str,
        filters: Mapping[str, Any] | None,
        order_by: Sequence[OrderBy],
        build: Callable[[Mapping[str, Any]], R],
    ) -> list[R]:
        rows, _ = self._store.select_page(table, order_by=order_by, filters=filters)
        return [build(row) for row in rows]
