"""Reading a document a job wrote to say it ran, and reporting it as an observation.

Two jobs in this product write one: the display plane writes a heartbeat, and the
backup writes a receipt. Neither is a health check — nothing here decides whether
anything is *well*. A file that is absent, a file that will not parse, and a file
written eight days ago are three observations, and the reader states which one it
found and how old it is. A verdict computed from a document that may simply be
young is how a health surface starts lying.

**One parser for both, because two would drift.** The two readings differ in the
filename, in the key carrying the instant, and in the sentence a person reads —
and in nothing else. Kept apart, they would be two implementations of the same
decode, which in this repository has already produced a real defect: one copy
caught a Pillow `ValueError` its sibling did not, and the difference was
invisible until someone read them side by side.

**Absent and unreadable are held apart on purpose.** Nothing has ever run is a
normal state on a fresh deployment; a file that exists and will not parse is a
fault. Collapsing them hides the second behind the first.
"""

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Observation:
    """What was found at a path, and how old it is. Never whether that is good."""

    path: Path
    #: The instant the document carries, or None when there is nothing to age.
    at: datetime | None
    #: How long ago that was, in seconds. Negative when the document is stamped
    #: ahead of this machine's clock, which `in_words` reports as itself.
    age_seconds: float | None
    #: The document as its writer wrote it, or None if absent or unreadable. Handed
    #: through untouched: past the one key below, its shape is the writer's.
    contents: dict[str, Any] | None
    #: Set when a file is present but could not be read.
    problem: str | None

    @property
    def absent(self) -> bool:
        """True when nothing has ever written here."""
        return self.contents is None and self.problem is None


def observe(path: Path, *, key: str, now: datetime | None = None) -> Observation:
    """Read the document at `path`, aging it by the instant under `key`.

    Absent is an answer rather than a failure, and so is unreadable. Nothing
    raises: a surface that showed a stack trace where a heartbeat's age belongs
    would have replaced an observation with an outage of its own.
    """
    moment = now or datetime.now(UTC)
    if not path.exists():
        return Observation(path=path, at=None, age_seconds=None, contents=None, problem=None)

    try:
        contents = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("The document at %s exists but could not be read: %s", path, exc)
        return Observation(path=path, at=None, age_seconds=None, contents=None, problem=str(exc))

    if not isinstance(contents, dict):
        return Observation(
            path=path,
            at=None,
            age_seconds=None,
            contents=None,
            problem="it does not hold a JSON object.",
        )

    at = _instant(contents.get(key))
    if at is None:
        return Observation(
            path=path,
            at=None,
            age_seconds=None,
            # Carried even though the timestamp is missing: the document is real
            # and what it does say is worth showing, and a reader that dropped it
            # would report a written file as though nothing had written one.
            contents=contents,
            problem=f"it carries no readable {key!r} timestamp, so its age is unknown.",
        )
    return Observation(
        path=path,
        at=at,
        age_seconds=(moment - at).total_seconds(),
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


#: Where each unit gives way to the next, and what to divide by once it does. Read
#: in order, so the first threshold an age clears names it. 90 rather than 60 at
#: each step because "90 seconds" reads better than "2 minutes" for the same
#: instant, and the boundary is arbitrary either way.
_UNITS: tuple[tuple[float, float, str], ...] = (
    (90, 1, "second"),
    (90 * 60, 60, "minute"),
    (48 * 3600, 3600, "hour"),
    (float("inf"), 86400, "day"),
)


def in_words(seconds: float) -> str:
    """An age in the unit a person reads it in, with its direction.

    One unit cannot serve both readers here: a heartbeat is a minute old and a
    backup is a week old, and "604800 seconds ago" is a figure nobody converts —
    on the panel whose entire job is making staleness legible.
    `observability-strategy.md` writes the target itself, as "last heartbeat: 4
    days ago", and this is what produces it.

    **A negative age is reported as itself rather than folded into zero.** The
    planes can run on different machines, and two clocks disagreeing is precisely
    the quiet fault this surface exists to state out loud — "0 seconds ago" for a
    document stamped tomorrow would state the opposite.
    """
    magnitude = abs(seconds)
    _, divisor, unit = next(entry for entry in _UNITS if magnitude < entry[0])
    count = round(magnitude / divisor)
    phrase = f"{count} {unit}{'' if count == 1 else 's'}"
    return phrase if seconds >= 0 else f"{phrase} in the future"


def ago(seconds: float) -> str:
    """`in_words`, as the tail of a sentence about when something happened.

    The direction is asked of the number rather than read back off the phrase:
    a sentence that decided by looking for "in the future" in its own output
    would start saying "ago" the day that wording is reworded.
    """
    return f"{in_words(seconds)} ago" if seconds >= 0 else in_words(seconds)
