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
import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from display import brightness as brightness_module
from display.config import Settings
from display.logs import work_context
from display.manifest import Entry, Manifest, Watcher
from display.state import DisplayState
from display.tv import RemovalOutcome, TvClient, TvRemovalUnconfirmed, TvUnavailable, TvUploadFailed

log = logging.getLogger(__name__)


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
        rng: random.Random | None = None,
    ) -> None:
        self._settings = settings
        self._tv = tv
        self._state = state
        self._watcher = watcher
        self._clock = clock
        self._rng = rng if rng is not None else random.Random()

        #: Positions into the current manifest's entries, in the order they will
        #: be shown. Held apart from the entries themselves so that shuffling is
        #: a property of this run rather than something written back anywhere.
        self._order: list[int] = []
        self._cursor: int = 0
        self._selected_at: float | None = None
        self._brightness_at: float | None = None
        self._brightness_value: int | None = None
        self._retry_seconds: float = settings.tv_retry_min_seconds
        self._reported_unavailable = False

    async def run(self, stop: asyncio.Event) -> None:
        """Reconcile until asked to stop."""
        log.info(
            "display plane starting against %s",
            self._settings.art_root,
            extra={"event": "daemon.started", **self._settings.startup_lines()},
        )
        while not stop.is_set():
            interval = await self.tick()
            await self._wait(stop, interval)
        await self._tv.close()
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

        manifest = self._watcher.current
        if manifest is None:
            return self._settings.poll_interval_seconds

        try:
            await self._connected()
            if adopted is not None:
                await self._reconcile_with_the_set(adopted)
            await self._apply_brightness()
            acted = await self._act_on_directive(manifest)
            if not acted:
                await self._rotate_if_due(manifest)
            await self._upload_one_pending(manifest)
        except TvUnavailable as exc:
            return self._back_off(exc)

        self._recover()
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
        self._cursor = found_at if self._selected_at is None else (found_at + 1) % len(self._order)

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
        if manifest.pinned_work_id is None:
            acted = await self._advance(manifest)
            self._state.set_last_acted_sequence(observed)
            log.info(
                "directive %d: stepping to the next work",
                observed,
                extra={"event": "directive.acted", "sequence": observed, "directive": "next"},
            )
            return acted

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

        # Rotation continues *from* the pin rather than resuming where it was, so
        # the next step is the work after the pinned one.
        self._cursor = (self._order.index(position) + 1) % len(self._order)
        shown = await self._show(manifest, manifest.entries[position])
        self._state.set_last_acted_sequence(observed)
        log.info(
            "directive %d: jumping to work %s",
            observed,
            manifest.pinned_work_id,
            extra={"event": "directive.acted", "sequence": observed, "directive": "show_now"},
        )
        return shown

    # -- rotation ----------------------------------------------------------

    async def _rotate_if_due(self, manifest: Manifest) -> None:
        due_after = manifest.rotation_interval_seconds
        if self._selected_at is not None and self._clock.monotonic() - self._selected_at < due_after:
            return
        await self._advance(manifest)

    async def _advance(self, manifest: Manifest) -> bool:
        """Show the next work that can be shown, skipping the ones that cannot.

        Bounded by the length of the list, so a theme whose every render is
        missing logs its warnings once per pass and returns, rather than spinning
        on a loop that can never succeed.
        """
        if not self._order:
            return False
        for _ in range(len(self._order)):
            position = self._order[self._cursor]
            self._cursor = (self._cursor + 1) % len(self._order)
            if self._cursor == 0 and manifest.shuffle:
                # A new order for each pass through the theme. Shuffling once and
                # keeping it would give the household the same "random" sequence
                # every day, which reads as a bug in the shuffle.
                self._rng.shuffle(self._order)
            if await self._show(manifest, manifest.entries[position]):
                return True
        return False

    async def _show(self, manifest: Manifest, entry: Entry) -> bool:
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
                return False

            content_id = await self._content_id_for(entry, render)
            if content_id is None:
                return False

            await self._tv.select_image(content_id)
            self._state.set_last_selected_work_id(entry.work_id)
            self._selected_at = self._clock.monotonic()
            log.info(
                "showing %s",
                entry.label.get("title") or entry.work_id,
                extra={
                    "event": "rotation.selected",
                    "tv_content_id": content_id,
                    "theme_id": manifest.theme_id,
                },
            )
            return True

    # -- bindings ----------------------------------------------------------

    async def _content_id_for(self, entry: Entry, render: Path) -> str | None:
        """This work's id on the television, uploading it now if it has none."""
        binding = self._state.binding_for(entry.work_id)
        if binding is not None and binding.is_on_the_television:
            return binding.tv_content_id
        return await self._upload(entry, render)

    async def _upload(self, entry: Entry, render: Path) -> str | None:
        """Send one render to the television and record what happened.

        A failure is recorded, not merely logged: the store keeps `failed` apart
        from "no row at all", so a work that fails every pass is visible in the
        device's own state rather than only in a journal that does not survive a
        reboot.
        """
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

        self._state.record_upload(entry.work_id, content_id)
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
            binding = self._state.binding_for(entry.work_id)
            if binding is not None and binding.is_on_the_television:
                continue
            render = self._settings.art_root / entry.render_path
            if not render.is_file():
                # Not a failure to record: nothing was attempted, and writing a
                # `failed` row for a file curation has not produced yet would make
                # the store report an upload problem for a preparation one.
                continue
            with work_context(entry.work_id):
                await self._upload(entry, render)
            return

    async def _reconcile_with_the_set(self, manifest: Manifest) -> None:
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

        await self._remove_orphans(listed)

    async def _remove_orphans(self, listed: frozenset[str]) -> None:
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
            return

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
            return

        log.info(
            "removed %d image(s) the binding table does not account for",
            len(outcome.removed),
            extra={
                "event": "tv.orphans_removed",
                "removed": list(outcome.removed),
                "surviving": list(outcome.surviving),
            },
        )

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

    def _back_off(self, exc: TvUnavailable) -> float:
        """Report the television going away once, then wait longer each time.

        Once, because an asleep set is the normal overnight condition and one
        WARNING a second until morning buries every other line in the journal. The
        recovery is logged too, so the pair reads as an episode with a length.
        """
        if not self._reported_unavailable:
            log.warning("%s; holding the wall where it is and retrying", exc, extra={"event": "tv.unavailable"})
            self._reported_unavailable = True
        wait = self._retry_seconds
        self._retry_seconds = min(self._retry_seconds * 2, self._settings.tv_retry_max_seconds)
        return wait

    def _recover(self) -> None:
        if self._reported_unavailable:
            log.info("the television is answering again", extra={"event": "tv.recovered"})
            self._reported_unavailable = False
        self._retry_seconds = self._settings.tv_retry_min_seconds

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
