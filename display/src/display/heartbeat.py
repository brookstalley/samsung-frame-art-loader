"""What this plane says about itself, for anyone who cares to look.

**The only thing that runs display → curation**, and deliberately not a
dependency in either direction: this writes the file and never checks whether
anybody read it. Curation being absent, or present and ignoring it, changes
nothing here. That is what keeps the availability norm true — the display plane's
ability to show art never depends on the curation plane being reachable — while
still giving a health surface something real to read.

**Two names in this document are a contract rather than a preference, because the
reader was built first.** The file is `display-heartbeat.json` under `ART_ROOT`
and the instant is spelled `reported_at`. `curation/src/curation/manifest/heartbeat.py` treats
any other spelling as an unreadable heartbeat and says so — so a writer that
called the field `timestamp` would produce a plane that looks *down* to curation
while running perfectly. That is this product's defining failure mode
manufactured by the mechanism built to detect it, which is why both names are
imported from nowhere and written here as constants with this note attached.
Everything else in the document is this writer's to shape: the reader hands the
whole object through untouched.

**Written every 60 seconds, and that number is a wear budget as much as a
freshness one.** This file is rewritten forever on the same SD card the
catalogue lives on, and the storage risk in `operational-spec.md` rests on this
product having no unbounded small-write source. Borrowing the manifest poll's
one-second cadence by symmetry would commit ~86,400 write-and-rename cycles a
day to that medium in perpetuity. The ceiling on the other side is the rotation
interval: this names the work *currently* displayed, so a heartbeat slower than
the wall would report works the wall had already left. Sixty seconds sits under
the 180 s rotation default with margin.

**Nothing here judges anything.** No "healthy", no green, no threshold. The
document states what is so and how long ago; the reader decides what that means.
A verdict computed here from a file that may simply be young is how a health
surface starts lying.
"""

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Final

log = logging.getLogger(__name__)

#: Where curation looks. Not configurable, for the same reason the manifest's name
#: is not: both planes have to agree, and a setting is a way for them to disagree.
HEARTBEAT_FILENAME: Final[str] = "display-heartbeat.json"

#: The key carrying the instant. Contract — see this module's docstring.
REPORTED_AT_KEY: Final[str] = "reported_at"

#: How often it is rewritten. See the docstring: bounded below by SD-card wear,
#: above by the rotation interval.
INTERVAL_SECONDS: Final[float] = 60.0


@dataclass(frozen=True, slots=True)
class Health:
    """This plane's own account of itself, as facts rather than a verdict.

    **`last_error` is a string rather than an exception**, and it is whatever the
    daemon last found worth recording — it is not cleared by a good pass. A
    heartbeat that dropped the error the moment anything succeeded would report a
    plane that is fine while it fails every other minute, which is the shape of
    failure this deployment is most likely to have.
    """

    #: The schema version of the manifest currently loaded, as `major.minor`, or
    #: None before one has been adopted. **The schema rather than a generation
    #: counter**, because that is the version display acts on: it refuses a major
    #: it does not know, so this is the number that explains a plane sitting on an
    #: old manifest.
    manifest_schema: str | None = None
    #: The theme whose manifest is loaded.
    theme_id: str | None = None
    #: The work the wall is showing, as this plane last confirmed it.
    current_work_id: str | None = None
    #: What the set last announced, which is the set's own word rather than ours.
    announced_content_id: str | None = None
    #: Whether the television answered the last time it was asked.
    television_reachable: bool | None = None
    #: Whether the set is in art mode, as far as this plane last saw.
    television_showing_art: bool | None = None
    #: Whether this device has a label surface at all. **A separate fact from the
    #: one below, because `null` there was carrying two meanings**: a device with
    #: no panel, and a device whose panel is fine but has not been asked to draw
    #: yet. A freshly started plane read on curation's panel as a device with no
    #: panel, which is a different deployment.
    has_label_surface: bool = False
    #: Whether the label surface accepted the last label it was given. None until
    #: it has been given one — including on a device that has no surface, which is
    #: a valid configuration rather than a fault.
    label_surface_working: bool | None = None
    #: The last thing that went wrong, in the words the journal got.
    last_error: str | None = None

    def document(self, *, reported_at: datetime) -> dict[str, Any]:
        """The whole document, as it goes on disk.

        The instant is stamped by the caller rather than read here, so the writer
        holds no clock of its own and a test can place a heartbeat at any moment
        without patching one.
        """
        return {
            REPORTED_AT_KEY: reported_at.isoformat(),
            "manifest_schema": self.manifest_schema,
            "theme_id": self.theme_id,
            "current_work_id": self.current_work_id,
            "announced_content_id": self.announced_content_id,
            "television_reachable": self.television_reachable,
            "television_showing_art": self.television_showing_art,
            "has_label_surface": self.has_label_surface,
            "label_surface_working": self.label_surface_working,
            "last_error": self.last_error,
        }


def path_in(art_root: Path) -> Path:
    """Where the heartbeat lives under a given art root."""
    return art_root / HEARTBEAT_FILENAME


def write(art_root: Path, health: Health, *, reported_at: datetime) -> None:
    """Put the heartbeat on disk, atomically, replacing whatever was there.

    **Temp-and-rename, and the same discipline as the manifest builder's
    `write_atomically` down to the `fsync`.** Two different failures are being
    closed and only one of them is the obvious one.

    The obvious one is the reader: curation polls this file on its own schedule,
    so a plain truncating write leaves a window in which it sees half a document
    — which it correctly reports as an unreadable heartbeat, i.e. as this plane
    being broken. `os.replace` is atomic within a filesystem, and the temp file is
    made in the same directory to guarantee that.

    The other is power. This runs on a Pi with an SD card and no UPS, and a
    rename can reach the disk before the bytes it renames do — so a cut at the
    wrong moment leaves a heartbeat that exists, is the right size, and contains
    nothing. `flush` plus `os.fsync` before the rename is what orders them, and
    leaving it out is the defect that only ever appears after an outage, which is
    exactly when somebody is reading this file to find out what happened.

    Raises on failure rather than swallowing. The caller is the one that knows a
    heartbeat is an annotation and not the product, and it is the caller that
    holds the report-once machinery to say so at most once per episode.
    """
    destination = path_in(art_root)
    temporary = destination.with_name(f"{destination.name}.tmp")
    payload = json.dumps(health.document(reported_at=reported_at), indent=2, ensure_ascii=False)
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            handle.write(payload + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except BaseException:  # prawduct:allow prawduct/broad-except -- cleanup-and-reraise; nothing is swallowed
        # **`BaseException`, matching the manifest builder**: a `KeyboardInterrupt`
        # or a cancelled task between the write and the rename would otherwise
        # leave the temp file behind for ever. It is named `.tmp` so a reader can
        # never mistake it for the heartbeat, so this is tidiness rather than
        # correctness — but it is tidiness on a device nobody visits.
        #
        # Nothing is swallowed: the cleanup is best-effort and the original
        # exception goes straight back out.
        temporary.unlink(missing_ok=True)
        raise
