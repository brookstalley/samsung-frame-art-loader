"""The narrow reverse channel: what the display plane says about itself.

The manifest runs curation → display. This is the only thing that runs the other
way, and it is deliberately not a dependency: display writes this file and never
checks whether anyone read it, so curation being absent changes nothing about the
wall. Curation reading a stale one, or none at all, is likewise not an error — it
is an observation, and this module's job is to report it as one.

**Nothing here decides whether the display plane is healthy.** It reports what was
found and how old it is, in absolute terms. A green dot is a verdict, and a
verdict computed from a file that may simply be young is how a health surface
starts lying: the reader is told the age and decides.

The writer is the display plane's, and does not exist yet. Until it does, this
reports honestly that no heartbeat has ever been written — which is a true and
useful answer, and a better one than a zero that reads like a reading.
"""

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

log = logging.getLogger(__name__)

#: Written into `ART_ROOT` by the display plane. Not configurable, for the same
#: reason the manifest's name is not: both planes must agree where it is.
HEARTBEAT_FILENAME: Final[str] = "display-heartbeat.json"


@dataclass(frozen=True, slots=True)
class HeartbeatReading:
    """What curation can observe about the display plane, stated as observation.

    `absent` and `unreadable` are different answers on purpose. Nothing has ever
    run is a normal state on a fresh deployment; a file that exists and will not
    parse is a fault, and collapsing the two would hide it.
    """

    path: Path
    #: None when no heartbeat file exists at all.
    reported_at: datetime | None
    #: How long ago it was written, in seconds. None when there is nothing to age.
    age_seconds: float | None
    #: The document as display wrote it, or None if absent or unreadable.
    contents: dict[str, Any] | None
    #: Set when a file is present but could not be read as a heartbeat.
    problem: str | None

    @property
    def absent(self) -> bool:
        """True when the display plane has never written a heartbeat here."""
        return self.contents is None and self.problem is None

    def describe(self) -> str:
        """One sentence stating what was observed, never a verdict about it."""
        if self.absent:
            return f"No heartbeat file exists at {self.path}; the display plane has not reported yet."
        if self.problem is not None:
            return f"The heartbeat file at {self.path} could not be read: {self.problem}"
        return f"The display plane last reported {self.age_seconds:.0f} seconds ago."


def read(path: Path, *, now: datetime | None = None) -> HeartbeatReading:
    """Observe the heartbeat file. Absent is an answer, not a failure."""
    moment = now or datetime.now(UTC)
    if not path.exists():
        return HeartbeatReading(path=path, reported_at=None, age_seconds=None, contents=None, problem=None)

    try:
        contents = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("The heartbeat file at %s exists but could not be read: %s", path, exc)
        return HeartbeatReading(path=path, reported_at=None, age_seconds=None, contents=None, problem=str(exc))

    if not isinstance(contents, dict):
        return HeartbeatReading(
            path=path,
            reported_at=None,
            age_seconds=None,
            contents=None,
            problem="it does not hold a JSON object.",
        )

    reported_at = _instant(contents.get("reported_at"))
    if reported_at is None:
        return HeartbeatReading(
            path=path,
            reported_at=None,
            age_seconds=None,
            contents=contents,
            problem="it carries no readable 'reported_at' timestamp, so its age is unknown.",
        )
    return HeartbeatReading(
        path=path,
        reported_at=reported_at,
        age_seconds=(moment - reported_at).total_seconds(),
        contents=contents,
        problem=None,
    )


def _instant(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    # A naive timestamp is read as UTC rather than as local time: the alternative
    # makes the reported age wrong by the machine's offset, and wrong quietly.
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
