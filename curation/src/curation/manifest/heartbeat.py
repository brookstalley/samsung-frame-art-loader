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

The writer is the display plane's — `display/src/display/heartbeat.py`, which
declares the same two names and is held to them by
`tests/preferences/test_heartbeat_contract.py`, since neither plane can import
the other to check. A heartbeat that has never been written is still an ordinary
answer and is reported as one: a fresh deployment has no writer running yet, and
that is a true and useful thing to say rather than a zero that reads like a
reading.

The parse is `observations.observe`'s, shared with the backup receipt — the same
document-with-an-instant, read for the same panel. Three things are this module's
own: the filename, the key, and the sentence.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Final

from curation import observations

#: Written into `ART_ROOT` by the display plane. Not configurable, for the same
#: reason the manifest's name is not: both planes must agree where it is.
HEARTBEAT_FILENAME: Final[str] = "display-heartbeat.json"

#: The key carrying the instant, and a contract rather than a preference. A writer
#: that spells it `timestamp` produces a plane that looks *down* to curation while
#: running perfectly — this product's defining failure mode manufactured by the
#: mechanism built to detect it. `observability-strategy.md` names it for the same
#: reason. Everything else in the document is the writer's to shape.
REPORTED_AT_KEY: Final[str] = "reported_at"


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
        """One sentence stating what was observed, never a verdict about it.

        The age is in the unit a person reads it in rather than in seconds. A
        display plane down since Tuesday reported "345600 seconds ago", which is
        a conversion the reader has to do on the one surface built so they would
        not have to — and `observability-strategy.md` states the target wording.
        """
        if self.absent:
            return f"No heartbeat file exists at {self.path}; the display plane has not reported yet."
        if self.problem is not None:
            return f"The heartbeat file at {self.path} could not be read: {self.problem}"
        return f"The display plane last reported {observations.ago(self.age_seconds)}."


def read(path: Path, *, now: datetime | None = None) -> HeartbeatReading:
    """Observe the heartbeat file. Absent is an answer, not a failure."""
    seen = observations.observe(path, key=REPORTED_AT_KEY, now=now)
    return HeartbeatReading(
        path=seen.path,
        reported_at=seen.at,
        age_seconds=seen.age_seconds,
        contents=seen.contents,
        problem=seen.problem,
    )
