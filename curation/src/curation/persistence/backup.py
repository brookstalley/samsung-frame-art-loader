"""Whether the catalogue has been backed up lately, and how long ago.

The catalogue is the irreplaceable asset — the image tree is deliberately not
backed up, because every file in it can be fetched again. So "a backup that
silently stopped succeeding a month ago" is the failure this reading exists to
make visible, and `operational-spec.md` names surfacing its age on the health
panel as part of the backup's design rather than as a nicety.

**The receipt is written only on success**, which is what makes its age mean what
the panel says it means. A job that stamped every attempt would report a fresh
age for a backup that has been failing since Tuesday, and the panel would be
confidently wrong about the one asset nothing else protects.

**Nothing writes one yet.** The job is Chunk 20's; this side is built first
deliberately, and the reason is the panel's own contract: it states observations
with ages and never verdicts, so *no backup has ever been recorded* is a true and
useful observation on a deployment that has never run one. It reports real ages
the moment a writer lands, with nothing further to wire — and the alternative,
building the reader alongside the job, is what left the two entries waiting on
each other.

The parse is `observations.observe`'s, shared with the display heartbeat. Both
ends of this one are ours, so the key cannot drift the way the heartbeat's could
across planes — but the reader and the writer still belong in one module, and
this is where the writer lands.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Final

from curation import observations

#: Written beside the catalogue's own directory, under `ART_ROOT`. Beside the
#: catalogue rather than *inside* it, which is not a filing preference: the
#: backup copies the catalogue, so a receipt recorded as a row could only ever be
#: written after the copy was taken — every restored catalogue would then carry
#: the previous backup's receipt and report an age older than the file it came
#: from. A file beside it is stamped by the run that succeeded and restores as
#: whatever the destination actually holds.
BACKUP_RECEIPT_FILENAME: Final[str] = "backup-status.json"

#: The key carrying the instant the backup finished. Named for the fact the panel
#: states — when the catalogue was last safely copied — rather than for when the
#: document was written, because a writer that stamps an attempt and a writer that
#: stamps a success would otherwise both be spelling this correctly.
COMPLETED_AT_KEY: Final[str] = "completed_at"


@dataclass(frozen=True, slots=True)
class BackupReading:
    """When the catalogue was last backed up, stated as an observation.

    `absent` and `unreadable` are different answers, as they are for the
    heartbeat: nothing has ever run is the normal state of a deployment whose
    backup is not yet scheduled, and a receipt that will not parse is a fault.
    """

    path: Path
    #: None when no receipt exists at all.
    completed_at: datetime | None
    #: How long ago the backup finished, in seconds. None when there is nothing
    #: to age.
    age_seconds: float | None
    #: The receipt as the backup job wrote it, or None if absent or unreadable.
    #: Handed through untouched past `completed_at`: where the copy went, and how
    #: large it was, are the job's to record and the panel's to show.
    contents: dict[str, Any] | None
    #: Set when a receipt is present but could not be read.
    problem: str | None

    @property
    def absent(self) -> bool:
        """True when no backup has ever recorded itself here."""
        return self.contents is None and self.problem is None

    def describe(self) -> str:
        """One sentence stating what was observed, never a verdict about it.

        There is deliberately no threshold in here. "Six days" is alarming for a
        nightly job and unremarkable for a destination that is usually asleep,
        and the panel does not know which this deployment is — so it reports the
        age and the reader decides, exactly as it does for the heartbeat.
        """
        if self.absent:
            return f"No backup has been recorded at {self.path}; nothing has written one yet."
        if self.problem is not None:
            return f"The backup record at {self.path} could not be read: {self.problem}"
        return f"The catalogue was last backed up {observations.ago(self.age_seconds)}."


def read(path: Path, *, now: datetime | None = None) -> BackupReading:
    """Observe the backup receipt. Absent is an answer, not a failure."""
    seen = observations.observe(path, key=COMPLETED_AT_KEY, now=now)
    return BackupReading(
        path=seen.path,
        completed_at=seen.at,
        age_seconds=seen.age_seconds,
        contents=seen.contents,
        problem=seen.problem,
    )
