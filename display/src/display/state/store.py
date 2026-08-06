"""`display-state.sqlite` — what this television holds, and where the wall got to.

**Per-device runtime state never lives in the catalogue.** Which image this
particular television holds under which of its own identifiers is a fact about
one device, and putting it in the catalogue is what made the 2024 tree's
`tv_content_id` column impossible to restore onto a different set. This store is
the process that norm lives in: display is its sole writer, curation never opens
it, and losing it costs a re-upload rather than a curatorial record.

Two things live here:

* **`tv_binding`** — the work-to-content-id map, modelled in `data-model.md`
  because it is the entity that carries the norm across the plane boundary.
* **`daemon_state`** — where the rotation got to, and which directive has already
  been acted on. Display-internal, never read by anything else.

**`upload_status` is explicit, and the table refuses the 2024 defect
structurally.** That version's `upload_file` caught every exception, logged, and
still reported success — recording no content id while its retry loop set
`success = True`. A row here cannot say `uploaded` without an id: the check
constraint rejects it, so the failure mode is a write that raises during
development rather than a wall that silently shows nothing.
"""

import logging
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from types import TracebackType
from typing import Final, Self

log = logging.getLogger(__name__)

#: Bumped when a migration lands. Read from `PRAGMA user_version`, which SQLite
#: carries in the file header for exactly this purpose and costs no table.
SCHEMA_VERSION: Final[int] = 1


class UploadStatus(StrEnum):
    """What is known about one work's image on this television.

    `failed` exists so that "we tried and it did not land" is a different state
    from "we have not tried" — the absence of a row. Collapsing those is the
    original defect this store was designed against.
    """

    UPLOADED = "uploaded"
    FAILED = "failed"
    #: The television no longer lists the content id this row names. The row is
    #: kept rather than deleted so the next reconciliation re-uploads rather than
    #: rediscovering the work as new, and so the journal can say what happened.
    ORPHANED = "orphaned"


class StateSchemaTooNew(RuntimeError):
    """The store on disk was written by a newer display plane than this one.

    Refused rather than opened, for the same reason a manifest major from the
    future is refused: a reader that guesses at a shape it does not know writes
    damage, and this is the one file whose loss is not free.
    """


@dataclass(frozen=True)
class Binding:
    """One work's image on this television."""

    artwork_id: str
    tv_content_id: str | None
    upload_status: UploadStatus
    uploaded_at: datetime
    tv_thumb_md5: str | None = None

    @property
    def is_on_the_television(self) -> bool:
        """Whether this row claims the set is holding the image right now."""
        return self.upload_status is UploadStatus.UPLOADED and self.tv_content_id is not None


_SCHEMA: Final[str] = """
CREATE TABLE IF NOT EXISTS tv_binding (
    id             TEXT PRIMARY KEY,
    artwork_id     TEXT NOT NULL UNIQUE,
    tv_content_id  TEXT,
    tv_thumb_md5   TEXT,
    uploaded_at    TEXT NOT NULL,
    upload_status  TEXT NOT NULL
        CHECK (upload_status IN ('uploaded', 'failed', 'orphaned')),
    -- The 2024 defect, made unwritable: a row may not claim the image is on the
    -- television without naming the identifier the television gave it back.
    CHECK (upload_status <> 'uploaded' OR tv_content_id IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS daemon_state (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

#: Keys in `daemon_state`. Named rather than spelled at each call site, because a
#: typo in a key string is a silent read of nothing — which for the sequence key
#: means re-executing the last directive on every restart.
_LAST_ACTED_SEQUENCE: Final[str] = "last_acted_sequence"
_LAST_SELECTED_WORK_ID: Final[str] = "last_selected_work_id"
_SLIDESHOW_DISABLED: Final[str] = "native_slideshow_disabled"


class DisplayState:
    """The device's store, opened once and held for the life of the process."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._connection = sqlite3.connect(path)
        self._connection.row_factory = sqlite3.Row
        # Foreign keys are not used here — the one cross-plane reference is by id
        # and by design has no constraint behind it — but the checks above are,
        # and they are on by default. What is switched on is WAL, so a reader
        # (nothing today; the heartbeat writer tomorrow) never blocks the loop.
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._prepare()

    def _prepare(self) -> None:
        version = self._connection.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise StateSchemaTooNew(
                f"{self._path} was written by a display plane at schema {version}; this one understands "
                f"{SCHEMA_VERSION}. Roll the deployment forward rather than letting an older reader write to it."
            )
        self._connection.executescript(_SCHEMA)
        if version < SCHEMA_VERSION:
            # No widening step exists yet, and the assignment is deliberate
            # rather than vestigial: it stamps a store created by this version so
            # that the *first* migration has a floor to migrate from. A file with
            # user_version 0 and a full schema is indistinguishable from an empty
            # one that a future migration would try to build again.
            self._connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    # -- bindings ---------------------------------------------------------

    def binding_for(self, artwork_id: str) -> Binding | None:
        """What this device knows about one work's image, if anything."""
        row = self._connection.execute(
            "SELECT artwork_id, tv_content_id, tv_thumb_md5, uploaded_at, upload_status FROM tv_binding WHERE artwork_id = ?",
            (artwork_id,),
        ).fetchone()
        return _binding(row) if row is not None else None

    def bindings(self) -> tuple[Binding, ...]:
        """Every work this device has a record for, in no meaningful order."""
        rows = self._connection.execute(
            "SELECT artwork_id, tv_content_id, tv_thumb_md5, uploaded_at, upload_status FROM tv_binding"
        ).fetchall()
        return tuple(_binding(row) for row in rows)

    def accounted_content_ids(self) -> frozenset[str]:
        """Every content id this device believes it put on the television.

        **Includes orphaned rows deliberately.** An orphan is a row whose id the
        set stopped listing; if the set later lists it again — the case
        `tv_thumb_md5` exists to help with — treating it as unaccounted-for would
        delete an image this device uploaded and is about to re-upload.
        """
        rows = self._connection.execute("SELECT tv_content_id FROM tv_binding WHERE tv_content_id IS NOT NULL").fetchall()
        return frozenset(row["tv_content_id"] for row in rows)

    def record_upload(self, artwork_id: str, tv_content_id: str, *, tv_thumb_md5: str | None = None) -> Binding:
        """Record that the television is holding this work's image, under this id."""
        return self._write_binding(artwork_id, tv_content_id, UploadStatus.UPLOADED, tv_thumb_md5)

    def record_upload_failure(self, artwork_id: str) -> Binding:
        """Record that an upload was attempted and did not land.

        Keeps the row rather than deleting it, so the next pass can tell a work
        that failed from one nobody has tried — and so a work that fails every
        pass is visible in the store rather than only in the journal.
        """
        return self._write_binding(artwork_id, None, UploadStatus.FAILED, None)

    def mark_orphaned(self, artwork_id: str) -> Binding:
        """Record that the television no longer lists this work's content id."""
        return self._write_binding(artwork_id, None, UploadStatus.ORPHANED, None)

    def _write_binding(
        self,
        artwork_id: str,
        tv_content_id: str | None,
        status: UploadStatus,
        tv_thumb_md5: str | None,
    ) -> Binding:
        uploaded_at = datetime.now(UTC)
        self._connection.execute(
            """
            INSERT INTO tv_binding (id, artwork_id, tv_content_id, tv_thumb_md5, uploaded_at, upload_status)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(artwork_id) DO UPDATE SET
                tv_content_id = excluded.tv_content_id,
                tv_thumb_md5  = excluded.tv_thumb_md5,
                uploaded_at   = excluded.uploaded_at,
                upload_status = excluded.upload_status
            """,
            (str(uuid.uuid4()), artwork_id, tv_content_id, tv_thumb_md5, uploaded_at.isoformat(), str(status)),
        )
        self._connection.commit()
        return Binding(
            artwork_id=artwork_id,
            tv_content_id=tv_content_id,
            upload_status=status,
            uploaded_at=uploaded_at,
            tv_thumb_md5=tv_thumb_md5,
        )

    # -- where the wall got to --------------------------------------------

    @property
    def last_acted_sequence(self) -> int | None:
        """The directive sequence already executed, or None if none ever has been.

        None is what makes a first start different from a restart, and the
        difference is load-bearing: a fresh store adopts whatever sequence it
        first sees as its baseline **without acting**, because acting would
        execute a directive issued before this process existed.
        """
        raw = self._get(_LAST_ACTED_SEQUENCE)
        return int(raw) if raw is not None else None

    def set_last_acted_sequence(self, sequence: int) -> None:
        self._set(_LAST_ACTED_SEQUENCE, str(sequence))

    @property
    def last_selected_work_id(self) -> str | None:
        """The work last put on the wall, so a restart resumes rather than restarts."""
        return self._get(_LAST_SELECTED_WORK_ID)

    def set_last_selected_work_id(self, work_id: str) -> None:
        self._set(_LAST_SELECTED_WORK_ID, work_id)

    @property
    def native_slideshow_disabled(self) -> bool:
        """Whether this device has already been told to stop its own slideshow.

        Persisted rather than held in memory, because `Restart=always` makes
        restarts routine and the call is only correct to make once — the
        television's own slideshow fighting host-driven `select_image` is the
        failure this switch prevents, and it does not come back on by itself.
        """
        return self._get(_SLIDESHOW_DISABLED) == "1"

    def mark_native_slideshow_disabled(self) -> None:
        self._set(_SLIDESHOW_DISABLED, "1")

    def _get(self, key: str) -> str | None:
        row = self._connection.execute("SELECT value FROM daemon_state WHERE key = ?", (key,)).fetchone()
        return row["value"] if row is not None else None

    def _set(self, key: str, value: str) -> None:
        self._connection.execute(
            "INSERT INTO daemon_state (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self._connection.commit()


def _binding(row: sqlite3.Row) -> Binding:
    return Binding(
        artwork_id=row["artwork_id"],
        tv_content_id=row["tv_content_id"],
        upload_status=UploadStatus(row["upload_status"]),
        uploaded_at=datetime.fromisoformat(row["uploaded_at"]),
        tv_thumb_md5=row["tv_thumb_md5"],
    )
