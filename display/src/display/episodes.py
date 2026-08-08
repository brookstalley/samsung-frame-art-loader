"""Two shapes this plane kept rewriting: saying a thing once, and waiting longer.

Both exist because **this plane's only failure channel is the journal, and the
journal has a rate limiter.** A television is asleep most of the night and
somebody watches a programme for three hours; a condition reported once per poll
would be ten thousand identical lines, and the lines journald drops to make room
are the ERRORs that are the whole point of writing any of it down.

**Reported at the edges, never in between.** A condition that persists is
announced when it starts and again when it ends, so the pair reads as an episode
with a length — which is the form an operator can actually act on. "The
television is not answering" with no closing line leaves a reader unable to tell
a wall that recovered at 03:00 from one that is still down.

**A wait that doubles is a separate concern from a line that is said once**, and
they are separate classes here even though every present caller uses them
together. They come apart in both directions: the panel is reported without any
wait at all, since a redraw is attempted on the next selection whenever that
comes, and reconciliation waits without reporting anything.

Neither class reads a clock it owns. `Backoff` is handed the same monotonic
source the daemon uses, because an NTP correction — routine on a Pi with no RTC,
which boots believing it is 1970 — must not be able to stall a retry for the
length of the jump or fire every pending wait at once.
"""

from collections.abc import Callable


class ReportOnce:
    """A condition that persists, announced at each edge and never in between.

    Holds no message and no log level: the four conditions using it report at
    WARNING, at INFO, and one of them has to ask the television a question before
    it can write its line. What is common is the *bookkeeping* — has this been
    said, and is this the moment it stops being true — and that is all this is.

    Both methods answer "is this an edge?" rather than mutating and staying
    silent, so a caller cannot report without transitioning or transition without
    the option to report. Written the other way round — a `reported` flag the
    caller sets — is what produced four hand-maintained copies of it.
    """

    __slots__ = ("_reported",)

    def __init__(self) -> None:
        self._reported = False

    @property
    def reported(self) -> bool:
        """Whether this condition is currently being lived through."""
        return self._reported

    def begin(self) -> bool:
        """True the first time the condition is seen; False while it persists."""
        if self._reported:
            return False
        self._reported = True
        return True

    def end(self) -> bool:
        """True when this closes an episode that was reported; False if none was.

        The False case is the ordinary one and is not a failure: most passes end
        an episode that never started, and a caller that logged a recovery
        unconditionally would announce the television coming back every second
        that it had never been away.
        """
        if not self._reported:
            return False
        self._reported = False
        return True


class Backoff:
    """A doubling wait with a ceiling, forgotten as soon as the thing works.

    **The ceiling is what makes it safe to forget nothing else.** Without one, a
    set left off overnight reaches a wait measured in hours and the wall would
    stay blank well into the next morning; with one, recovery is bounded by the
    ceiling regardless of how long the outage ran.

    Two ways of consuming the same ladder, because this plane needs both and they
    were written separately before they were seen to be one thing. A caller that
    controls its own sleep reads the return of `hold`; a caller on a fixed poll
    asks `is_due` and skips the pass. `hold` serves both, so a caller can switch
    without the ladder changing shape.
    """

    __slots__ = ("_maximum", "_minimum", "_monotonic", "_not_before", "_seconds")

    def __init__(self, *, minimum: float, maximum: float, monotonic: Callable[[], float]) -> None:
        self._minimum = minimum
        self._maximum = maximum
        self._monotonic = monotonic
        self._seconds = minimum
        self._not_before: float | None = None

    @property
    def seconds(self) -> float:
        """The wait the next `hold` will apply. Exposed for the journal, not for logic."""
        return self._seconds

    def is_due(self) -> bool:
        """Whether the guarded thing may be attempted again yet.

        True when no wait is in force, which is the normal condition — nothing
        here delays anything until something has actually failed.
        """
        return self._not_before is None or self._monotonic() >= self._not_before

    def hold(self) -> float:
        """Wait before trying again, and wait longer next time. Returns this wait.

        **The current wait is applied and then the ladder is advanced**, so the
        first failure after a recovery waits the minimum rather than skipping
        straight to double it. Getting that order wrong costs a set that blinks
        out for one poll a wait it did not earn.
        """
        waiting = self._seconds
        self._not_before = self._monotonic() + waiting
        self._seconds = min(self._seconds * 2, self._maximum)
        return waiting

    def clear(self) -> None:
        """Forget the wait entirely, because the guarded thing is working again."""
        self._not_before = None
        self._seconds = self._minimum
