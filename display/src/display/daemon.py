"""The reconciliation loop: make the wall match the manifest, and keep it matching.

**Nothing here is a command handler.** Curation writes desired state and this
converges on it; the directive block is the one place where that framing is
strained, and even there what arrives is a number that went up, not an
instruction that must be delivered exactly once by the sender. If curation dies,
this keeps rotating the last manifest forever — which is the availability norm
working, not degradation.

Four behaviours are worth reading before changing anything here, because each was
chosen against an alternative that looks more obvious:

**Uploads are spread across ticks rather than done in a batch on adoption.** A
fresh install has an empty binding table and a theme of forty works, and each
upload costs the set the better part of ten seconds. Doing them all before the
first `select_image` leaves the wall on yesterday's picture for five minutes and,
worse, leaves a curator pressing "next" with nothing happening for five minutes —
against a poll interval that is one second precisely because that wait is the one
the product may not have. So the loop shows what it can as soon as it can, and
carries one pending upload per pass until the theme is complete.

**A directive is acted on when the sequence advances, and adopted silently when
it moves any other way.** A first start has never acted on anything, so it takes
whatever it finds as its baseline: acting instead would execute, at install time,
a `show_now` somebody issued last week. A sequence that goes *backwards* is a
restored catalogue, not a directive, and replaying a stale pin because a backup
came back is the failure that rule exists to prevent.

**Anything that cannot be shown is skipped, never fatal.** A missing render file,
a work whose upload failed, a pin naming a work the active theme does not carry —
each is one WARNING and the rotation continues. The wall going black is always
worse than the wall being incomplete.

**The television going away is an expected operating condition.** The set is
asleep most of the time; a connection failure is a backoff, not an incident, and
the picture stays up regardless because the television holds it.
"""

import asyncio
import enum
import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from display import brightness as brightness_module
from display import heartbeat as heartbeat_module
from display.config import Settings
from display.episodes import Backoff, ReportOnce
from display.logs import work_context
from display.manifest import Entry, Manifest, Watcher
from display.panel import LabelSurface, Layout, lay_out, read_label
from display.state import Binding, DisplayState, UploadStatus
from display.tv import RemovalOutcome, SelectionAnnouncement, TvClient, TvRemovalUnconfirmed, TvUnavailable, TvUploadFailed

log = logging.getLogger(__name__)

#: How long a label may spend being drawn before this loop stops waiting for it.
#:
#: **The whole of the product's label budget rather than a fraction of it.** The
#: label must match what the television is showing within 15 s of the picture
#: changing (`nonfunctional-requirements.md` § Performance), and the panel's own
#: refresh is most of that — so this is the loosest bound that still honours the
#: requirement, and a draw that has passed it has already missed the thing it was
#: for. A healthy 16-level frame measures 1.5–1.9 s and comes nowhere near it;
#: what this catches is an SPI transaction that is never coming back, which is the
#: one way a panel could stop the wall that no `except` clause can reach.
LABEL_DRAW_BUDGET_SECONDS: Final[float] = 15.0


def _forget(draw: "asyncio.Future[Layout]") -> None:
    """Collect an abandoned draw's outcome, so nothing warns about it later.

    A draw left running past its budget is one nobody is waiting for any more, and
    a future whose exception is never read prints a warning when it is collected —
    on the one code path where the journal is already saying something truer.
    """
    if not draw.cancelled():
        draw.exception()


class Shown(enum.Enum):
    """What came of trying to put one work on the wall.

    **Three outcomes rather than a boolean, because two failures want opposite
    responses.** A work that cannot be shown — no render, no binding — means try
    the next one, which is what makes a theme with a pruned image tree degrade to
    the works that survive. A wall that is not accepting selections at all means
    try *nothing* else: every remaining work would fail identically, and a pass
    that walked forty of them would cost eighty round trips and consume the whole
    rotation order against a television that displayed none of it.
    """

    YES = "yes"
    #: This work could not be shown; another might.
    SKIP = "skip"
    #: The television took the request and displayed nothing. No work will fare
    #: better until that changes, so the pass ends here.
    WALL_UNCHANGED = "wall_unchanged"


@dataclass(frozen=True)
class Clock:
    """Wall time and elapsed time, injected so the loop is testable at any hour.

    Two readings rather than one, because they answer different questions and one
    of them lies. `now()` is for the sun, which genuinely cares what time it is.
    `monotonic()` is for every interval, so an NTP correction — routine on a Pi
    with no RTC, which comes up believing it is 1970 — cannot stall the rotation
    for the length of the jump or fire every timer at once.
    """

    now: Callable[[], datetime]
    monotonic: Callable[[], float]

    @staticmethod
    def system() -> "Clock":
        return Clock(now=lambda: datetime.now(UTC).astimezone(), monotonic=time.monotonic)


class Daemon:
    """One television, one manifest, one loop."""

    def __init__(
        self,
        *,
        settings: Settings,
        tv: TvClient,
        state: DisplayState,
        watcher: Watcher,
        clock: Clock,
        surface: LabelSurface | None = None,
        surface_error: str | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self._settings = settings
        self._tv = tv
        self._state = state
        self._watcher = watcher
        self._clock = clock
        self._rng = rng if rng is not None else random.Random()

        #: Where this device draws its label, or None if it has none. **A device
        #: with no label surface is a supported deployment, not a fault** — the
        #: wall is a television, and the label is an annotation of it
        #: (`architecture.md` § Direction). Nothing below may report its absence
        #: as a problem. The heartbeat therefore reports such a device with
        #: `has_label_surface` false and `label_surface_working` null — "there is
        #: nothing here to ask", as against the `false` that means a panel is
        #: broken. The two fields were one nullable field until that collapse made
        #: a device with no panel indistinguishable from a panel that would not
        #: open.
        self._surface = surface
        self._label_failed = ReportOnce()
        #: The draw handed to a worker thread, kept until it finishes. **A
        #: one-at-a-time gate rather than a queue**: the budget stops the loop
        #: waiting on a hung panel, but it cannot stop the thread, and dispatching
        #: another every rotation would fill the shared executor with threads
        #: parked in a driver — at which point the television's own blocking calls,
        #: which use that same executor, would start waiting behind a panel. That
        #: is a panel stopping the wall by the back door.
        self._label_draw: asyncio.Future[Layout] | None = None
        #: What the panel was last asked to name, as the television's own id for
        #: it. **Recorded on the attempt rather than the success**, which is what
        #: keeps a refusing panel from being re-asked on every one-second poll: a
        #: surface that failed gets its next chance when the wall next changes,
        #: which is also when a stale label would start being wrong.
        #:
        #: The cost of that rule, stated so nobody has to rediscover it: a draw the
        #: one-at-a-time gate turns away counts as an attempt too, so the panel
        #: keeps the older label until the wall next changes. That is reachable
        #: only once a panel has already run past the label budget and been
        #: reported broken, which is a state where one stale label is not the
        #: problem.
        self._captioned_content_id: str | None = None
        #: Why this device has no surface, when it was configured to have one.
        #: **The third state, and the reason it is carried rather than logged and
        #: dropped at the composition root**: without it a panel that failed to
        #: open is a `surface` of None, which on the health surface is
        #: indistinguishable from a device that never had a panel — the same
        #: two-meanings-in-one-value fault `has_label_surface` was split out to
        #: fix, arriving one level up.
        self._surface_error = surface_error
        #: Whether the surface accepted the last label it was given. Stays None
        #: on a device with no surface, so "never tried" and "tried and failed"
        #: cannot be confused — but **False from the outset on a device whose
        #: panel would not open**, because that one has already failed.
        self._label_working: bool | None = False if surface is None and surface_error else None

        #: What the set last announced about its own wall, which is the only
        #: honest account of it this product has. Written from the television's
        #: reader task, read here — a plain assignment either way, so no lock:
        #: it is one reference, and a reader that catches the previous value gets
        #: a stale id rather than a torn one.
        self._announced_content_id: str | None = None
        tv.observe_selections(self._note_announcement)

        #: Whether the set was showing art the last time it was actually asked.
        #: **None until it has been**, rather than defaulting to either answer: the
        #: gate is only consulted when something is about to happen, so a fresh
        #: process genuinely does not know, and a heartbeat that guessed would be
        #: reporting a read nobody performed.
        self._showing_art: bool | None = None

        self._heartbeat_at: float | None = None
        #: Seeded with the panel's failure when there was one, because at startup
        #: that *is* the last thing that went wrong. Anything later overwrites it,
        #: which is right — a television that has since gone away is the more
        #: urgent of the two.
        self._last_error: str | None = surface_error
        self._heartbeat_failed = ReportOnce()

        #: Positions into the current manifest's entries, in the order they will
        #: be shown. Held apart from the entries themselves so that shuffling is
        #: a property of this run rather than something written back anywhere.
        self._order: list[int] = []
        self._cursor: int = 0

        #: **Two facts that were one field until they were told apart.** When the
        #: last rotation was *attempted* governs the timer; whether anything has
        #: ever reached the wall governs whether a restart re-shows or steps past.
        #: Sharing one nullable float made a pass that showed nothing look like a
        #: process that had just started, so the timer never armed and a theme with
        #: no renders walked its whole list once a second, for ever.
        self._attempted_at: float | None = None
        self._has_shown = False

        #: The wall is taking selections and displaying none of them. A television
        #: whose panel is dark stays dark for hours, and a line per rotation would
        #: be a hundred a night saying the one thing that has not changed.
        self._wall_unchanged = ReportOnce()

        #: Somebody is watching their own television. Reported at INFO rather than
        #: WARNING because that is not a fault — but still reported, because "the
        #: wall stopped" otherwise has no explanation in the journal at all.
        self._not_our_wall = ReportOnce()

        #: When the wall may next be asked to change, once it has been found not
        #: changing. **Rotation has a timer and the directive path does not**, so
        #: without this a `show_now` left unconsumed — which is the right thing to
        #: do with a jump that never happened — would be re-asked on every poll: a
        #: selection a second, each waiting out the confirmation window, all night
        #: at a set that will ignore every one. It backs off on the same ladder as an unreachable
        #: television, because "the set is not doing what it is told" is that same
        #: situation arriving by a route that raises nothing.
        self._wall_retry = Backoff(
            minimum=settings.tv_retry_min_seconds,
            maximum=settings.tv_retry_max_seconds,
            monotonic=clock.monotonic,
        )

        #: Reconciling the binding table against the set is **owed until it is
        #: done**, not attempted once when a manifest lands. A new manifest is
        #: reported by the watcher on exactly one tick; if the set is asleep on
        #: that tick — which this module's own note says is most of them — the
        #: tick aborts, and tying the work to that one flag drops orphan removal
        #: entirely rather than deferring it.
        self._reconciliation_owed = False
        #: When reconciliation may next be attempted. It stays *owed* through a
        #: television that cannot say what it removed, and without this it would
        #: then be retried at the poll rate — one listing, one removal request and
        #: one INFO line a second, which is the same unbounded cadence as the two
        #: this loop already guards against.
        #:
        #: **The same `Backoff` the connection and the upload retry use**, at a
        #: fixed wait rather than a doubling one — equal bounds make `hold`'s
        #: ladder a constant. It was a hand-rolled pair of a nullable float and a
        #: comparison until the shape it rhymed with was extracted; keeping the
        #: last copy would have left one due-time gate whose reset, its
        #: "immediately the first time" rule and its arithmetic all had to be read
        #: rather than recognised.
        self._reconcile_wait = Backoff(
            minimum=settings.tv_retry_max_seconds,
            maximum=settings.tv_retry_max_seconds,
            monotonic=clock.monotonic,
        )
        self._brightness_at: float | None = None
        self._brightness_value: int | None = None

        #: The set could not be reached at all. Its own ladder, separate from the
        #: wall's: a television that is asleep and one that is awake and ignoring
        #: selections are different conditions, and recovering from one says
        #: nothing about the other.
        self._connection_retry = Backoff(
            minimum=settings.tv_retry_min_seconds,
            maximum=settings.tv_retry_max_seconds,
            monotonic=clock.monotonic,
        )
        self._unavailable = ReportOnce()

    async def run(self, stop: asyncio.Event) -> None:
        """Reconcile until asked to stop."""
        log.info(
            "display plane starting against %s",
            self._settings.art_root,
            extra={"event": "daemon.started", **self._settings.startup_lines()},
        )
        crashed = False
        try:
            while not stop.is_set():
                interval = await self.tick()
                await self._wait(stop, interval)
        except Exception:  # prawduct:allow prawduct/broad-except -- top-level supervisor; records and re-raises unchanged
            # **`Exception`, not `BaseException`, and the difference is a wrong
            # log line.** `CancelledError` and `KeyboardInterrupt` are shutdowns,
            # not crashes; reporting one as `daemon.crashed` at ERROR would be the
            # inverse of the defect this exists to fix. They still reach the
            # `finally`, so the art channel is closed either way.
            #
            # **Nothing is swallowed and nothing is handled** — the exception goes
            # straight back out, so systemd still sees a failed unit and
            # `Restart=always` still restarts. What this buys is the only record
            # that will exist: this plane's failure channel is the journal, and
            # without an ERROR here a crash left `daemon.stopped` at INFO, which is
            # the identical line a clean shutdown writes. An operator reading the
            # log could not tell a wall that was switched off from one that fell
            # over in a loop.
            crashed = True
            log.exception("the display plane is stopping on an error", extra={"event": "daemon.crashed"})
            raise
        finally:
            # **Closed on every way out, including the unexpected one.** An
            # exception escaping the loop used to skip this entirely, leaving the
            # art websocket open at the set — and the set has been observed
            # refusing new art-channel connections for minutes after a client went
            # away without closing, apparently holding the slot until it times
            # out. Under `Restart=always` that turns one crash into a daemon that
            # cannot reach its own television on the way back up.
            await self._tv.close()
            # **The panel is released too, and on e-paper that is not bookkeeping**
            # — `close()` is the sleep/power-down, and a panel left driven holds
            # its rails energised. Closed after the television because the set is
            # the one holding a network slot somebody else may want.
            if self._surface is not None:
                self._surface.close()
            if not crashed:
                log.info("display plane stopped", extra={"event": "daemon.stopped"})

    async def tick(self) -> float:
        """One pass. Returns how long to wait before the next one.

        Public because it is the unit the tests drive: a loop that could only be
        exercised by starting it and stopping it would be tested through a timer,
        and timing tests are the ones that go flaky on a loaded machine.
        """
        # The manifest is read first and unconditionally, because it is local file
        # I/O that cannot fail on account of the television. A set that is asleep
        # must not stop this plane from *knowing* what it will show when the set
        # comes back.
        adopted = self._watcher.poll()
        if adopted is not None:
            self._adopt(adopted)
            self._reconciliation_owed = True
            # A new manifest clears any wait: it is new information, and it is
            # usually what arrives after somebody has fixed whatever the set was
            # unhappy about. The wait exists to stop a *retry* loop, not to make
            # the plane ignore news.
            self._reconcile_wait.clear()

        manifest = self._watcher.current
        if manifest is None:
            # **Still beats.** A plane with no manifest is the state a fresh
            # install sits in, and it is exactly when somebody wants to know this
            # process is alive — returning here without a heartbeat would let
            # curation's panel report a running plane as one that has never
            # spoken.
            self._beat(manifest=None)
            return self._settings.poll_interval_seconds

        try:
            await self._connected()
            if self._reconciliation_owed and self._reconcile_wait.is_due():
                # Cleared only when the work actually settled: a set that goes
                # away halfway through raises, and one that cannot say what it
                # removed reports so — both leave the work owed for a later pass
                # rather than recorded as done.
                self._reconciliation_owed = not await self._reconcile_with_the_set(manifest)
                if self._reconciliation_owed:
                    self._reconcile_wait.hold()
                else:
                    self._reconcile_wait.clear()
            await self._apply_brightness()
            acted = await self._act_on_directive(manifest)
            if not acted:
                await self._rotate_if_due(manifest)
            await self._upload_one_pending(manifest)
            # Last, because it reconciles the label against whatever the pass
            # above left on the wall — including the case where the pass did
            # nothing and the wall changed anyway.
            await self._caption_the_wall_the_set_reports(manifest)
        except TvUnavailable as exc:
            # **The heartbeat is written on this path too, and that is the whole
            # point of it.** A television that has gone away is the condition an
            # operator most wants reported, and a plane that only beat on good
            # passes would fall silent exactly when it had something to say —
            # leaving curation to report "has not reported" for a process that is
            # running perfectly and telling the truth about a set that is not.
            self._record_error(str(exc))
            self._beat(manifest=manifest, television_reachable=False)
            return self._back_off(exc)

        self._recover()
        self._beat(manifest=manifest, television_reachable=True)
        return self._settings.poll_interval_seconds

    # -- the manifest ------------------------------------------------------

    def _adopt(self, manifest: Manifest) -> None:
        """Take a new manifest's entry list as the rotation, keeping our place.

        Keeping the place matters more than it looks: `sync` rewrites the manifest
        on every catalogue edit, and a rotation that restarted at the first work
        each time would show the same handful of pictures forever on a busy day.
        """
        self._order = list(range(len(manifest.entries)))
        if manifest.shuffle:
            self._rng.shuffle(self._order)

        # **Only when the wall is empty.** A wall with nothing on it should try
        # again the moment a new manifest lands — renders appearing normally comes
        # with curation republishing, and the alternative is a blank wall sitting
        # out three minutes it has no reason to. A wall that *is* showing
        # something must not have its timer restarted by a rewrite: `sync` fires
        # on every catalogue edit, and resetting here would step the wall on each
        # one, which is the same defect as the cursor rule below in a different
        # coat.
        if not self._has_shown:
            self._attempted_at = None

        self._cursor = 0
        resumed_from = self._state.last_selected_work_id
        if resumed_from is None:
            return
        position = manifest.index_of(resumed_from)
        if position is None:
            return
        found_at = self._order.index(position)

        # **A restarted process points at the work already on the wall; a running
        # one points past it.** The two cases share this method and want opposite
        # things, and getting it wrong is visible either way.
        #
        # A restart that advanced would change the picture every time the unit
        # bounced — and under `Restart=always` a crash loop would strobe the wall
        # rather than freeze it, which is the worse of the two failures by a long
        # way. Re-selecting what is already showing costs one idempotent call and
        # nobody in the room sees anything happen.
        #
        # A `sync` mid-interval, on the other hand, rewrites the manifest while
        # this process is running and holding its place in memory; pointing back
        # at the current work there would hand it a second full interval on every
        # catalogue edit, which on a busy afternoon is a wall that stops moving.
        self._cursor = found_at if not self._has_shown else (found_at + 1) % len(self._order)

    # -- directives --------------------------------------------------------

    async def _act_on_directive(self, manifest: Manifest) -> bool:
        """Execute at most one directive, and report whether the wall moved."""
        observed = manifest.directive_sequence
        acted_on = self._state.last_acted_sequence

        if acted_on is None:
            self._state.set_last_acted_sequence(observed)
            log.info(
                "adopting directive sequence %d as this device's baseline without acting on it",
                observed,
                extra={"event": "directive.baselined", "sequence": observed},
            )
            return False

        if observed == acted_on:
            return False

        if observed < acted_on:
            # The counter lives in the catalogue, and a restore can bring back an
            # older one. That is not a directive, and treating it as one would
            # replay whatever pin was current when the backup was taken.
            self._state.set_last_acted_sequence(observed)
            log.warning(
                "the manifest's directive sequence went backwards (%d after %d); re-baselining without acting, "
                "which is what a catalogue restore looks like from here",
                observed,
                acted_on,
                extra={"event": "directive.regressed", "sequence": observed, "previous": acted_on},
            )
            return False

        # Latest-wins coalescing needs no code: two `next` calls inside one poll
        # interval advance the counter twice and are observed once, which is one
        # step. That is the intended behaviour and not an approximation of it.
        #
        # **The sequence is consumed after the attempt, never before.** Every path
        # below can raise `TvUnavailable`, and a directive marked acted-on while
        # the set was asleep is a `show_now` the curator never gets: the manifest
        # does not change, so nothing would ever present it again. Recording it
        # afterwards means an outage delays the jump instead of eating it.
        #
        # An attempt that *completes* and shows nothing — a pin whose render is
        # missing — is still an attempt, and is consumed. Retrying that one every
        # second would fill the journal with a failure that will not change until
        # a file appears.
        #
        # **A jump onto a television somebody is watching is not attempted at
        # all**, and is therefore not consumed: the curator gets their picture
        # when the set comes back to art mode, by the same rule that makes an
        # outage delay a jump rather than eat it. Checked here rather than in
        # `_advance`, so the baselining and regression arms above still keep this
        # device's sequence honest while the wall is somebody else's.
        #
        # **The wait is read before the set is asked, and that order is the whole
        # point.** This path has no timer of its own: an unconsumed directive is
        # still unconsumed on the next poll, so anything downstream of a question
        # put to the television is asked again a second later, all evening. Asking
        # whether the wall is ours costs a real request, so putting that question
        # in front of the wait would spend thousands of them across one programme
        # — the same shape as the selection flood the backoff was introduced to
        # stop, arriving by a cheaper-looking route.
        if not self._wall_attempt_is_due():
            return False
        if not await self._the_wall_is_ours_to_change():
            return False

        if manifest.pinned_work_id is None:
            outcome = await self._advance(manifest)
            if outcome is Shown.WALL_UNCHANGED:
                # Left unconsumed, exactly as the pinned branch below leaves a
                # jump the wall never made. A `next` the television took and did
                # not act on has not stepped anything, and the manifest does not
                # change when a directive fails — so consuming it here would
                # evaporate the curator's press and log a step that never
                # happened.
                return False
            self._state.set_last_acted_sequence(observed)
            log.info(
                "directive %d: stepping to the next work",
                observed,
                extra={"event": "directive.acted", "sequence": observed, "directive": "next"},
            )
            return outcome is Shown.YES

        position = manifest.index_of(manifest.pinned_work_id)
        if position is None:
            self._state.set_last_acted_sequence(observed)
            # `show_now` refuses a work that could not reach the wall, but it does
            # not check theme membership — only this plane can know what to do
            # with a pin it cannot resolve. Carrying on rotating is the same
            # posture as a missing render file: say so once, never stall the wall.
            log.warning(
                "directive %d pins work %s, which the active theme does not carry; continuing to rotate",
                observed,
                manifest.pinned_work_id,
                extra={
                    "event": "directive.pin_unresolvable",
                    "sequence": observed,
                    "pinned_work_id": manifest.pinned_work_id,
                },
            )
            return False

        if not self._wall_attempt_is_due():
            # The set has already been found taking selections and displaying
            # none of them. The pin stays unconsumed and is tried again when the
            # backoff is up; asking now would be the same call at the same
            # television, once per poll, for as long as the panel stays dark.
            return False

        # Rotation continues *from* the pin rather than resuming where it was, so
        # the next step is the work after the pinned one.
        self._cursor = (self._order.index(position) + 1) % len(self._order)
        outcome = await self._show(manifest, manifest.entries[position])
        if outcome is Shown.WALL_UNCHANGED:
            # Left unconsumed, by the same rule that leaves it unconsumed through
            # an outage: the jump is delayed rather than eaten. A television that
            # took the request and displayed nothing has not performed the jump,
            # and recording it here would mean the curator's pin evaporated while
            # the panel was dark and the wall came back on some other picture.
            return False
        self._state.set_last_acted_sequence(observed)
        log.info(
            "directive %d: jumping to work %s",
            observed,
            manifest.pinned_work_id,
            extra={"event": "directive.acted", "sequence": observed, "directive": "show_now"},
        )
        return outcome is Shown.YES

    # -- rotation ----------------------------------------------------------

    async def _rotate_if_due(self, manifest: Manifest) -> None:
        """Step the wall on when the interval is up — and only then.

        **The clock is stamped before the attempt, not after a success**, which is
        what bounds a theme nothing can be shown from. Every entry logs one
        WARNING as it is skipped, so a forty-work theme with a pruned image tree
        costs forty lines *per interval* rather than forty lines per second. The
        second cadence is not a tidiness problem: journald rate-limits, and the
        lines it drops are the ERRORs this plane's only failure channel exists to
        carry.
        """
        due_after = manifest.rotation_interval_seconds
        if self._attempted_at is not None and self._clock.monotonic() - self._attempted_at < due_after:
            return
        if not self._wall_attempt_is_due():
            # Gated by the same wait as a jump. The rotation interval is normally
            # the longer of the two, so this only bites where the backoff has
            # grown past it — a set left dark for hours.
            return
        if not await self._the_wall_is_ours_to_change():
            # **The clock is deliberately not stamped.** An interval the wall was
            # never allowed to use has not been spent, so when the set comes back
            # to art mode the picture should change at once rather than sit out
            # the remainder of a rotation nobody could see.
            return
        self._attempted_at = self._clock.monotonic()
        await self._advance(manifest)

    async def _advance(self, manifest: Manifest) -> Shown:
        """Show the next work that can be shown, skipping the ones that cannot.

        Bounded by the length of the list, so a theme whose every render is
        missing logs its warnings once per pass and returns, rather than spinning
        on a loop that can never succeed.

        **Returns the outcome rather than a boolean, and the distinction is load
        bearing.** "Nothing here could be shown" and "the wall would not change"
        are both failures to move the picture and they want opposite answers from
        a caller holding a directive: the first is the curator's own theme having
        no usable render, which is consumed and reported, while the second is the
        jump never having been attempted, which must be left for the wall coming
        back. Collapsed into one `False`, a bare `next` at a set that takes
        selections and displays none of them was eaten and logged as performed —
        the false-success class this plane exists to make impossible.
        """
        if not self._order:
            return Shown.SKIP
        for _ in range(len(self._order)):
            resume_at = self._cursor
            position = self._order[self._cursor]
            self._cursor = (self._cursor + 1) % len(self._order)
            if self._cursor == 0 and manifest.shuffle:
                # A new order for each pass through the theme. Shuffling once and
                # keeping it would give the household the same "random" sequence
                # every day, which reads as a bug in the shuffle.
                self._rng.shuffle(self._order)
            outcome = await self._show(manifest, manifest.entries[position])
            if outcome is Shown.YES:
                return Shown.YES
            if outcome is Shown.WALL_UNCHANGED:
                # The place is given back rather than consumed. A television that
                # displayed nothing has not shown this work, so the wall coming
                # back should show it — not the one after it. Without this, an
                # evening with the panel dark would walk the whole theme and the
                # first picture of the morning would be wherever that landed.
                self._cursor = resume_at
                return Shown.WALL_UNCHANGED
        return Shown.SKIP

    async def _show(self, manifest: Manifest, entry: Entry) -> Shown:
        """Put one work on the wall, or say why it could not be."""
        with work_context(entry.work_id):
            render = self._settings.art_root / entry.render_path
            if not render.is_file():
                log.warning(
                    "skipping %s: its render is not at %s",
                    entry.work_id,
                    render,
                    extra={"event": "rotation.render_missing", "render_path": str(render)},
                )
                return Shown.SKIP

            content_id = await self._content_id_for(entry, render)
            if content_id is None:
                return Shown.SKIP

            try:
                shown = await self._tv.show(content_id)
            except TvUnavailable:
                content_id = await self._rebind_or_reraise(entry, render, content_id)
                if content_id is None:
                    return Shown.SKIP
                shown = await self._tv.show(content_id)

            if not shown:
                await self._report_wall_unchanged(content_id)
                self._hold_off_the_wall()
                return Shown.WALL_UNCHANGED
            self._wall_is_answering()

            # Recorded only once the set is displaying it. A work written here on
            # the strength of the request alone would make a restart re-show
            # something that was never on the wall, and would tell the plane that
            # renders the label to caption a picture nobody can see.
            self._state.set_last_selected_work_id(entry.work_id)
            self._attempted_at = self._clock.monotonic()
            self._has_shown = True
            if self._wall_unchanged.end():
                log.info(
                    "the television is changing what it displays again",
                    extra={"event": "rotation.wall_recovered"},
                )
            log.info(
                "showing %s",
                entry.label.get("title") or entry.work_id,
                extra={
                    "event": "rotation.selected",
                    "tv_content_id": content_id,
                    "theme_id": manifest.theme_id,
                },
            )
            await self._caption(entry, content_id)
            return Shown.YES

    async def _caption(self, entry: Entry | None, content_id: str) -> None:
        """Put a work's label on the device's own surface, if it has one.

        **Driven from the daemon's own task rather than from the set's callback**,
        though the announcement is what says the wall changed. The two are the same
        event; the difference is which task does the work. An e-paper redraw is a
        full frame — 1.5–1.9 s measured, with no partial refresh — and doing that
        inside the television client's callback would run it on the websocket's
        reader task, delaying every message on that socket including the
        confirmations the rotation is waiting for. So the reader task records an id
        and this, later, draws.

        **And not on the event loop either, which is the same argument one level
        down.** Moving the draw off the reader task does not move it off the loop
        they share: seconds spent rasterising and clocking bytes out over SPI in a
        coroutine delay that socket's messages exactly as much as doing it in the
        callback would. It goes to a worker thread, as the television client's own
        blocking construction does, and it is bounded — because a driver wedged in
        a bad transaction never raises, and an unbounded wait is the one way a
        panel can stop the wall that no `except` clause reaches.

        **Called only for a picture the set says is up**, which is what keeps the
        label honest: captioning on the strength of a request would name a picture
        the set accepted and never displayed, and a wrong label is worse than a
        stale one because nobody can tell it is wrong.

        `entry` is None when the wall is showing something this manifest cannot
        name — see `_caption_the_wall_the_set_reports`. That draws an empty label
        rather than leaving the previous one up, for the same reason.

        **Nothing in here may stop the wall.** A surface that is broken, missing
        or slow leaves the television rotating; that is the whole posture of this
        loop applied to an annotation of it.
        """
        surface = self._surface
        if surface is None:
            return
        self._captioned_content_id = content_id
        if self._label_draw is not None and not self._label_draw.done():
            self._label_would_not_take_it("the previous label is still being drawn")
            return

        # **The gate is the draw's own state, not a flag somebody remembers to
        # clear.** A boolean set here and cleared inside `_draw` is wrong in a case
        # that leaves the panel dark for the life of the process: if the budget
        # runs out while the work item is still *queued* rather than running, the
        # thread never starts, so nothing in `_draw` ever executes to clear it —
        # and every later label is turned away by a gate guarding a draw that
        # happened. Asking the task whether it is finished is right for both the
        # queued case and the running one.
        draw = asyncio.ensure_future(asyncio.to_thread(self._draw, surface, entry))
        self._label_draw = draw
        finished, _ = await asyncio.wait({draw}, timeout=LABEL_DRAW_BUDGET_SECONDS)
        if not finished:
            # **Not cancelled, deliberately.** Cancelling would mark it done while
            # the thread carried on — the gate would open onto a panel still being
            # written to, which is what the gate exists to prevent. Left running,
            # it opens the gate when the panel actually comes back, and its outcome
            # is collected so nothing warns about an exception nobody read.
            draw.add_done_callback(_forget)
            self._label_would_not_take_it(f"the draw ran past the {LABEL_DRAW_BUDGET_SECONDS:g}s label budget")
            return
        try:
            layout = draw.result()
        # **Widened from `SurfaceUnavailable` alone once a real surface existed,
        # and the docstring above is why.** `show` converts its own failures, but
        # `geometry` and `measure` are read outside it — and `measure` on the
        # e-paper surface reaches a text stack through C bindings, which raises
        # GLib errors related to nothing this module can name. A promise that
        # nothing in here may stop the wall cannot be kept by a catch that lists
        # the exceptions somebody thought of.
        except Exception as exc:  # prawduct:allow prawduct/broad-except -- see above
            self._label_would_not_take_it(str(exc))
            return

        self._label_working = True
        if self._label_failed.end():
            log.info("the label surface is taking labels again", extra={"event": "label.recovered"})
        if layout.dropped:
            # Not a failure — the drop rule working — but it is the only place
            # anyone would learn that this device's surface is too small for the
            # corpus, so it is said rather than left to be noticed by eye.
            log.info(
                "the label surface had no room for %d line(s) of this label",
                len(layout.dropped),
                extra={"event": "label.truncated", "dropped": list(layout.dropped)},
            )

    def _label_would_not_take_it(self, why: str) -> None:
        """One place for every way a label fails to reach the surface.

        They differ only in the sentence: the response is the same to all of them
        — say so once, keep rotating — for the reason `SurfaceUnavailable` is one
        type rather than a family.
        """
        self._label_working = False
        self._record_error(f"the label surface refused a label ({why})")
        if self._label_failed.begin():
            # Once per episode, like every other persistent condition here: a
            # panel with a loose ribbon fails on every rotation, all night.
            log.warning(
                "could not put the label on this device's surface (%s); the wall keeps rotating",
                why,
                extra={"event": "label.failed"},
            )

    def _draw(self, surface: LabelSurface, entry: Entry | None) -> Layout:
        """Lay a label out and put it on the surface. **Runs on a worker thread.**

        The measuring and the drawing are one unit of work here rather than two
        because both are the same kind of expensive — `measure` reaches the same
        text stack the drawing does, and splitting them would put half the cost
        back on the loop for no gain.

        Nothing here touches this object's state, which is what makes it safe to
        run off the loop: the caller reads the outcome through the task it holds,
        and that task finishing is also what opens the gate on the next draw.
        """
        lines = read_label(entry.label).lines() if entry is not None else ()
        layout = lay_out(lines, surface.geometry, surface.measure)
        surface.show(layout)
        return layout

    def _note_announcement(self, announcement: SelectionAnnouncement) -> None:
        """Remember what the set says is on its wall. Runs on the client's reader task.

        Deliberately the cheapest thing that could work: one assignment, no I/O,
        no lock, nothing that can raise. Everything expensive this could trigger
        happens on the daemon's own task instead — see `_caption`.

        **It records announcements this plane did not cause**, which is the point
        of subscribing at all: somebody using the remote changes the wall, and
        both the heartbeat and the label should follow what is actually up rather
        than what we last put there.
        """
        self._announced_content_id = announcement.content_id

    async def _caption_the_wall_the_set_reports(self, manifest: Manifest) -> None:
        """Re-label when the wall changed without this plane changing it.

        **The remote is a curator too.** Somebody in the room picks a different
        work in art mode, and nothing in the rotation path runs: the panel would go
        on naming the previous picture until the interval came round, up to a full
        rotation later. That is not a stale label, which is at least visibly old —
        it is a confident one that is wrong, on the only surface the person
        standing in front of the wall can read, and there is no way for them to
        tell. The same rule that keeps this plane from captioning a selection the
        set never displayed requires captioning one it displayed without being
        asked.

        **A picture this manifest cannot name gets an empty label, not the last
        one.** Choosing an image out of the set's own art store is a supported
        thing to do with a remote, and no label text exists for it anywhere on this
        device. Blank says "nothing is known about what you are looking at"; the
        previous work's label says something false.

        Cheap on the ordinary pass: two references compared, and the binding table
        is only read when they differ — which is once per rotation, plus once per
        time somebody actually touches the remote.
        """
        # The surface is checked here as well as inside `_caption`, which is not
        # belt-and-braces: the lookup below is a read of the binding table, and a
        # device with no panel would otherwise pay for one on every poll — a query
        # a second, for ever, to decide what to draw on nothing.
        if self._surface is None:
            return
        announced = self._announced_content_id
        if announced is None or announced == self._captioned_content_id:
            return
        await self._caption(self._entry_showing(announced, manifest), announced)

    def _entry_showing(self, content_id: str, manifest: Manifest) -> Entry | None:
        """The manifest entry for what the set says it is showing, if it carries one."""
        for binding in self._state.bindings():
            if binding.tv_content_id != content_id:
                continue
            position = manifest.index_of(binding.artwork_id)
            return manifest.entries[position] if position is not None else None
        return None

    async def _the_wall_is_ours_to_change(self) -> bool:
        """Whether the set is showing art, and may therefore be asked to change it.

        **The television belongs to whoever is using it**
        (`nonfunctional-requirements.md`). Selecting an image on a set showing a
        programme does not fail politely: it switches the set into art mode and
        takes the screen off the person watching. So nothing reaches the wall
        without asking first, and a no freezes everything — no selection, no
        advance through the theme, no directive consumed — exactly as a wall that
        would not change does.

        **Asked only when something is about to happen**, which is what keeps a
        one-second poll from becoming a request per second: rotation consults this
        when its interval is up, and the directive path only when a sequence has
        actually moved. A no then backs off on the shared ladder, so a whole
        evening of television costs a handful of reads rather than thousands.
        """
        showing = await self._tv.showing_art()
        self._showing_art = showing
        if showing:
            if self._not_our_wall.end():
                log.info(
                    "the television is showing art again; resuming the rotation",
                    extra={"event": "rotation.wall_returned"},
                )
            return True

        if self._not_our_wall.begin():
            # Said once for the same reason a dark wall is: somebody watches
            # television for hours, and a line per attempt would bury the ERRORs
            # that are this plane's only failure channel.
            log.info(
                "the television is not in art mode; leaving the wall alone until it is",
                extra={"event": "rotation.wall_not_ours"},
            )
        self._hold_off_the_wall()
        return False

    def _wall_attempt_is_due(self) -> bool:
        """Whether the wall may be asked to change again yet.

        False after an attempt the television took and did not act on, and after
        finding somebody else using the set. A television behaving normally in art
        mode has no wait, so nothing here delays a rotation or a jump in normal
        operation.

        **An announcement from the set clears the wait**, because it is news
        rather than a retry — the same rule a new manifest gets. Without it,
        somebody switching from a programme back to art mode would watch a blank
        wall for the remainder of a backoff that had grown to five minutes; with
        it, the next poll asks again and the picture comes back in about a second.
        """
        if self._tv.art_mode_announcement_pending():
            self._wall_is_answering()
        return self._wall_retry.is_due()

    def _hold_off_the_wall(self) -> None:
        """Back off before asking again, and lengthen the wait each time.

        Bounded by the same ceiling as a reconnection, so a night with the panel
        off costs a handful of attempts rather than one a second — and the wall
        resumes within that ceiling of somebody switching the set back on.
        """
        self._wall_retry.hold()

    def _wall_is_answering(self) -> None:
        """Forget the backoff, because the set is acting on what it is told."""
        self._wall_retry.clear()

    async def _report_wall_unchanged(self, content_id: str) -> None:
        """Say once that the set is taking selections and displaying none of them.

        **The flag is read here for the operator, and separately before every
        selection for the wall's own safety.** The two readings answer different
        questions and neither replaces the other: the gate asks *may this
        television be touched at all*, and this line answers *why is it not
        changing* for somebody reading the journal. This one costs a call on a
        rotation that has already failed, so it is free in the ordinary case.
        """
        if not self._wall_unchanged.begin():
            return
        mode = await self._tv.reported_art_mode()
        log.warning(
            "the television accepted %s and is not displaying it; "
            "it reports art mode %s. Rotation is deferred until the wall changes",
            content_id,
            mode if mode is not None else "nothing at all",
            extra={
                "event": "rotation.wall_unchanged",
                "tv_content_id": content_id,
                "art_mode": mode,
            },
        )

    # -- bindings ----------------------------------------------------------

    async def _content_id_for(self, entry: Entry, render: Path) -> str | None:
        """This work's id on the television, uploading it now if it has none."""
        binding = self._state.binding_for(entry.work_id)
        if binding is not None and _is_current(binding, render):
            return binding.tv_content_id
        if self._too_soon_to_retry(binding):
            return None
        return await self._upload(entry, render)

    def _too_soon_to_retry(self, binding: Binding | None) -> bool:
        """Whether a work that failed to upload should be left alone this pass.

        **A set that is reachable and refuses one image does not back off with the
        connection**, which is the other failure and has its own retry. Without
        this, one bad render is a round trip, a WARNING and a rewritten row every
        second for as long as it stays in the theme — an unbounded small-write
        source on the SD card that `observability-strategy.md` says not to build,
        and a journal in which the rate limiter starts dropping the lines that
        matter.

        Measured against wall time, because the failure is recorded in the store
        and must outlive the process: under `Restart=always` an elapsed-time wait
        would reset on every restart, so a crash loop would become a retry loop.
        """
        if binding is None or binding.upload_status is not UploadStatus.FAILED:
            return False
        waited = (self._clock.now() - binding.uploaded_at).total_seconds()
        return waited < self._settings.upload_retry_seconds

    async def _rebind_or_reraise(self, entry: Entry, render: Path, refused: str) -> str | None:
        """Work out whether the set is gone or the *binding* is, and fix the second.

        **A refused selection is ambiguous and the library cannot disambiguate
        it** — a dead websocket and an id the set has never heard of arrive as the
        same failure. Guessing "outage" is the expensive mistake: somebody
        removing one image from the phone app would freeze the wall on a backoff
        that retries the same doomed id forever, because the manifest never
        changes and nothing else would ever re-check that binding.

        So the question is put to the television, which is this codebase's
        standing answer to a client whose return values cannot be trusted in
        either direction: if the set still lists the id, the fault is not the
        binding and the original failure stands. If the listing itself fails,
        that is a real outage and it propagates from here.

        **The connection is re-established first, and without that this whole
        method is unreachable.** The failure that sends us here arrives from the
        television client, which drops and closes its connection on *any* failure
        — it holds a websocket whose state after an error is not knowable, so it
        refuses to reason on it. The very next request would therefore raise "not
        connected" rather than reaching the set, the outage arm would swallow it,
        and every branch below would be dead code. Reconnecting costs nothing when
        the set is there and raises the real outage when it is not, which is
        exactly the distinction being drawn.
        """
        await self._connected()
        listed = await self._tv.listed_content_ids()
        if refused in listed:
            raise TvUnavailable(f"the television refused to select {refused}, which it says it is holding")

        self._state.mark_orphaned(entry.work_id)
        log.warning(
            "the television refused %s and does not list it; re-uploading %s",
            refused,
            entry.work_id,
            extra={"event": "binding.orphaned", "tv_content_id": refused},
        )
        return await self._upload(entry, render)

    async def _upload(self, entry: Entry, render: Path) -> str | None:
        """Send one render to the television and record what happened.

        A failure is recorded, not merely logged: the store keeps `failed` apart
        from "no row at all", so a work that fails every pass is visible in the
        device's own state rather than only in a journal that does not survive a
        reboot.
        """
        fingerprint = _fingerprint(render)
        try:
            content_id = await self._tv.upload(render)
        except TvUploadFailed as exc:
            self._state.record_upload_failure(entry.work_id)
            log.warning(
                "could not put %s on the television (%s)",
                entry.work_id,
                exc,
                extra={"event": "binding.upload_failed"},
            )
            return None

        self._state.record_upload(entry.work_id, content_id, render_fingerprint=fingerprint)
        log.info(
            "uploaded %s to the television as %s",
            entry.work_id,
            content_id,
            extra={"event": "binding.uploaded", "tv_content_id": content_id},
        )
        return content_id

    async def _upload_one_pending(self, manifest: Manifest) -> None:
        """Carry one not-yet-uploaded work per pass, so the theme fills in behind us.

        Deliberately one, not all: see this module's opening note. A pass that
        uploaded the whole theme would hold the loop — and every directive — for
        as long as the theme is long.
        """
        for entry in manifest.entries:
            render = self._settings.art_root / entry.render_path
            binding = self._state.binding_for(entry.work_id)
            if _is_current(binding, render):
                continue
            if self._too_soon_to_retry(binding):
                continue
            if not render.is_file():
                # Not a failure to record: nothing was attempted, and writing a
                # `failed` row for a file curation has not produced yet would make
                # the store report an upload problem for a preparation one.
                continue
            with work_context(entry.work_id):
                await self._upload(entry, render)
            return

    async def _reconcile_with_the_set(self, manifest: Manifest) -> bool:
        """Compare what this device believes against what the television lists.

        Runs when a manifest is adopted, not every pass. The comparison costs a
        real request to the set, and at a one-second poll that would be a call per
        second forever — traffic that buys nothing, since nothing changes what the
        television holds except this process.
        """
        listed = await self._tv.listed_content_ids()

        for entry in manifest.entries:
            binding = self._state.binding_for(entry.work_id)
            if binding is None or not binding.is_on_the_television:
                continue
            if binding.tv_content_id in listed:
                continue
            # The set stopped listing an image this device uploaded — removed from
            # the phone app, or forgotten across a factory reset. Recorded as
            # orphaned so the row cannot be mistaken for a live binding, which
            # would otherwise send `select_image` at an id the set does not know.
            self._state.mark_orphaned(entry.work_id)
            log.warning(
                "the television no longer lists %s for work %s; it will be uploaded again",
                binding.tv_content_id,
                entry.work_id,
                extra={"event": "binding.orphaned", "tv_content_id": binding.tv_content_id, "work_id": entry.work_id},
            )

        return await self._remove_orphans(listed)

    async def _remove_orphans(self, listed: frozenset[str]) -> bool:
        """Take off the television everything this device cannot account for.

        **The binding table is the whole authority**, which is why a fresh install
        clears the set: images uploaded by a previous generation of this product
        are not assets to adopt, because nothing joins them to a work — the 2024
        tree addressed images by source URL and by a resized filename, and a
        manifest entry names an artwork id and a UUID render. Adopting one would
        bind a work to a picture that is not the render its entry names, and the
        wall would show one composition while the catalogue recorded another.

        The television has exactly one user-upload category, so the alternative to
        removing them is two generations of the same corpus accumulating in it.
        """
        accounted = self._state.accounted_content_ids()
        orphans = sorted(listed - accounted)
        if not orphans:
            return True

        try:
            outcome: RemovalOutcome = await self._tv.remove(orphans)
        except TvRemovalUnconfirmed as exc:
            # Unknown is reported as unknown. The images stay listed and the next
            # pass tries again; claiming either outcome here would be a guess, and
            # this is the verb whose reply the library discards.
            log.warning(
                "could not establish whether %d unaccounted-for images were removed (%s)",
                len(orphans),
                exc,
                extra={"event": "tv.orphan_removal_unconfirmed", "requested": orphans},
            )
            return False

        log.info(
            "removed %d image(s) the binding table does not account for",
            len(outcome.removed),
            extra={
                "event": "tv.orphans_removed",
                "removed": list(outcome.removed),
                "surviving": list(outcome.surviving),
            },
        )
        # **Settled even when some survived.** An incomplete removal is a *known*
        # outcome — the set was asked, answered, and is keeping them — and it is
        # already reported at WARNING by the client. Asking again immediately
        # learns nothing; the next manifest re-arms the work. Only an outcome
        # nobody could establish stays owed.
        return True

    # -- the television ----------------------------------------------------

    async def _connected(self) -> None:
        """Ensure there is a live connection, and that the set's own slideshow is off."""
        await self._tv.connect()
        if not self._state.native_slideshow_disabled:
            await self._tv.disable_native_slideshow()
            self._state.mark_native_slideshow_disabled()
            log.info(
                "disabled the television's own slideshow, which would otherwise change the picture underneath us",
                extra={"event": "tv.native_slideshow_disabled"},
            )

    async def _apply_brightness(self) -> None:
        """Follow the sun, and write to the set only when the value actually changes."""
        elapsed = self._clock.monotonic()
        if self._brightness_at is not None and elapsed - self._brightness_at < self._settings.brightness_interval_seconds:
            return
        self._brightness_at = elapsed

        state = brightness_module.sun_state(
            self._clock.now(),
            latitude=self._settings.latitude,
            longitude=self._settings.longitude,
            location_name=self._settings.location_name,
            location_region=self._settings.location_region,
        )
        value = brightness_module.television_brightness(
            state.relative_brightness,
            minimum=self._settings.tv_min_brightness,
            maximum=self._settings.tv_max_brightness,
        )
        if value == self._brightness_value:
            return

        await self._tv.set_brightness(value)
        self._brightness_value = value
        log.info(
            "set panel brightness to %d",
            value,
            extra={
                "event": "brightness.set",
                "brightness": value,
                "solar_angle": round(state.solar_angle_degrees, 2),
            },
        )

    # -- the heartbeat -----------------------------------------------------

    def _beat(self, *, manifest: Manifest | None, television_reachable: bool | None = None) -> None:
        """Write the heartbeat if it is due, and never let that stop the wall.

        **Rate-limited here rather than by the caller**, so every path through
        `tick` can call it unconditionally — including the two that return early.
        A heartbeat gated behind the good path is one that goes quiet precisely
        when it matters.

        Its own failure is an episode like any other. The disk being full or
        read-only is worth an operator's attention, and it is worth exactly one
        line per episode rather than one a minute.
        """
        elapsed = self._clock.monotonic()
        if self._heartbeat_at is not None and elapsed - self._heartbeat_at < heartbeat_module.INTERVAL_SECONDS:
            return
        self._heartbeat_at = elapsed

        health = heartbeat_module.Health(
            manifest_schema=f"{manifest.schema_major}.{manifest.schema_minor}" if manifest is not None else None,
            theme_id=manifest.theme_id if manifest is not None else None,
            current_work_id=self._state.last_selected_work_id,
            announced_content_id=self._announced_content_id,
            television_reachable=television_reachable,
            television_showing_art=self._showing_art,
            # **Whether this device is meant to draw a label**, which is not the
            # same question as whether it currently can. A panel that failed to
            # open leaves no surface and is still a device with one, so reporting
            # `false` here would tell curation this deployment has no panel — the
            # one reading that makes a broken panel invisible.
            has_label_surface=self._surface is not None or self._surface_error is not None,
            label_surface_working=self._label_working,
            last_error=self._last_error,
        )
        try:
            heartbeat_module.write(self._settings.art_root, health, reported_at=self._clock.now())
        except OSError as exc:
            if self._heartbeat_failed.begin():
                log.warning(
                    "could not write the heartbeat to %s (%s); the wall is unaffected",
                    heartbeat_module.path_in(self._settings.art_root),
                    exc,
                    extra={"event": "heartbeat.failed"},
                )
            return
        if self._heartbeat_failed.end():
            log.info("the heartbeat is being written again", extra={"event": "heartbeat.recovered"})

    def _record_error(self, message: str) -> None:
        """Keep the last thing that went wrong, for the heartbeat to carry.

        **Not cleared by a good pass.** A plane that dropped its error the moment
        anything succeeded would report itself fine while failing every other
        minute, which is the shape of failure this deployment is most likely to
        have. It is overwritten by the next failure, so it is always the latest
        rather than the first.
        """
        self._last_error = message

    def _back_off(self, exc: TvUnavailable) -> float:
        """Report the television going away once, then wait longer each time.

        Once, because an asleep set is the normal overnight condition and one
        WARNING a second until morning buries every other line in the journal. The
        recovery is logged too, so the pair reads as an episode with a length.
        """
        if self._unavailable.begin():
            log.warning("%s; holding the wall where it is and retrying", exc, extra={"event": "tv.unavailable"})
        return self._connection_retry.hold()

    def _recover(self) -> None:
        if self._unavailable.end():
            log.info("the television is answering again", extra={"event": "tv.recovered"})
        self._connection_retry.clear()

    async def _wait(self, stop: asyncio.Event, seconds: float) -> None:
        """Sleep, but wake immediately when asked to stop.

        systemd's stop timeout is finite, and a daemon that slept through a
        SIGTERM for the length of a backoff would be killed rather than closed —
        leaving the websocket to time out on the set's side.
        """
        try:
            await asyncio.wait_for(stop.wait(), timeout=seconds)
        except TimeoutError:
            return


def _fingerprint(render: Path) -> str | None:
    """What this render file looks like right now, cheaply.

    **Modification time and size rather than a hash.** The rotation reads this on
    every pass over every entry; hashing forty 2 MB composites a second would be
    real I/O on an SD card, to answer a question a `stat` answers. The pipeline
    that writes these files always rewrites them wholesale, so a change that keeps
    both the size and the nanosecond timestamp is not a case this deployment can
    produce.

    None when the file cannot be read, which is treated as "unknown" and never as
    "unchanged" — see `_render_changed`.
    """
    try:
        stat = render.stat()
    except OSError:
        return None
    return f"{stat.st_mtime_ns}:{stat.st_size}"


def _is_current(binding: Binding | None, render: Path) -> bool:
    """Whether this work's picture is already on the television, and still right.

    **One question with two callers**, which is why it is a function rather than
    a condition written twice: one caller decides whether a content id can be
    reused, the other whether an upload still needs carrying, and they are the
    same question asked from opposite ends. Written out twice they drifted once
    already — the fingerprint half was added because the first reading was
    incomplete, and had it been added to only one of the two the wall would show
    a stale composition for exactly as long as nobody looked.
    """
    return binding is not None and binding.is_on_the_television and not _render_changed(binding, render)


def _render_changed(binding: Binding, render: Path) -> bool:
    """Whether the file on disk is no longer the one the television was given.

    **The defect this closes is invisible from the wall.** `render_path` is
    `ready/{artwork_id}.jpg` and stable across re-renders, so a curator changing a
    mat colour rewrites the bytes under an unchanged name; the binding still reads
    `uploaded`, and the television goes on showing the old composition for ever.
    Both `set_mat_color` and `regenerate` are live actions, so this is reachable
    by ordinary use rather than by mishap.

    A binding with no recorded fingerprint — every row written before the column
    existed — counts as changed. That costs one re-upload per work on the first
    pass after an upgrade, which is the honest price of never having looked.
    """
    return binding.render_fingerprint != _fingerprint(render)
