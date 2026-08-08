"""What this plane says about itself, for anyone who cares to look.

**The only thing that runs display → curation**, and deliberately not a
dependency in either direction: this writes the file and never checks whether
anybody read it. Curation being absent, or present and ignoring it, changes
nothing here. That is what keeps the availability norm true — the display plane's
ability to show art never depends on the curation plane being reachable — while
still giving a health surface something real to read.

**Two names in this document are a contract rather than a preference, because the
reader was built first.** The file is `display-heartbeat.json` under `ART_ROOT`
and the instant is spelled `reported_at`. `curation/manifest/heartbeat.py` treats
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

    #: The manifest version currently loaded, or None before one has been adopted.
    manifest_version: int | None = None
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
    #: Whether the label surface accepted the last label it was given. None when
    #: this device has no label surface at all, which is a valid configuration
    #: rather than a fault.
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
            "manifest_version": self.manifest_version,
            "theme_id": self.theme_id,
            "current_work_id": self.current_work_id,
            "announced_content_id": self.announced_content_id,
            "television_reachable": self.television_reachable,
            "television_showing_art": self.television_showing_art,
            "label_surface_working": self.label_surface_working,
            "last_error": self.last_error,
        }


def path_in(art_root: Path) -> Path:
    """Where the heartbeat lives under a given art root."""
    return art_root / HEARTBEAT_FILENAME


def write(art_root: Path, health: Health, *, reported_at: datetime) -> None:
    """Put the heartbeat on disk, atomically, replacing whatever was there.

    **Temp-and-rename, the same discipline as the manifest**, and for a sharper
    reason here: curation polls this file on its own schedule, so a plain
    truncating write leaves a window in which the reader sees half a document —
    which it correctly reports as an unreadable heartbeat, i.e. as this plane
    being broken. `os.replace` is atomic within a filesystem, and the temp file is
    made in the same directory to guarantee that.

    Raises on failure rather than swallowing. The caller is the one that knows a
    heartbeat is an annotation and not the product, and it is the caller that
    holds the report-once machinery to say so at most once per episode.
    """
    destination = path_in(art_root)
    temporary = destination.with_name(f"{destination.name}.tmp")
    payload = json.dumps(health.document(reported_at=reported_at), indent=2, ensure_ascii=False)
    try:
        temporary.write_text(payload + "\n", encoding="utf-8")
        os.replace(temporary, destination)
    except OSError:
        # The partial temp file is this plane's litter, not curation's problem —
        # but it is named `.tmp` precisely so a reader never mistakes it for the
        # heartbeat, so failing to remove it costs nothing and must not mask the
        # original error.
        temporary.unlink(missing_ok=True)
        raise
