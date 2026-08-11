"""The label and the heartbeat, driven by the real loop rather than called directly.

**These exist because everything they exercise was, briefly, unreachable.** The
panel package, the heartbeat writer and the selection fan-out each had a full
suite of their own and no production caller — which is the shape of a green suite
over a feature that does nothing. What is asserted here is only what the daemon
itself does with them.

The governing rule throughout: **nothing about a label or a heartbeat may stop
the wall.** The television is the product; both of these annotate it.
"""

import asyncio
import json
import threading
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fakes import FakeSurface

from display import daemon as daemon_module
from display.daemon import Daemon
from display.heartbeat import HEARTBEAT_FILENAME, INTERVAL_SECONDS
from display.manifest import Watcher
from display.panel import TypeScale


async def _comes_back(flag: threading.Event, *, within_seconds: float = 5.0) -> bool:
    """Wait on a worker thread's flag without blocking the loop waiting for it."""
    deadline = time.monotonic() + within_seconds
    while time.monotonic() < deadline:
        if flag.is_set():
            return True
        await asyncio.sleep(0.005)
    return False


@pytest.fixture
def surface() -> Iterator[FakeSurface]:
    made = FakeSurface()
    yield made
    # A draw runs on a worker thread now, and one armed to hang would otherwise
    # still be sitting in the panel when the session tries to exit.
    made.release.set()


@pytest.fixture
def labelled(settings, tv, state, clock, surface: FakeSurface) -> Daemon:
    """A daemon with a label surface attached — the deployment 13B provisions."""
    watcher = Watcher(
        settings.manifest_path,
        rotation_interval_fallback=settings.rotation_interval_fallback_seconds,
        shuffle_fallback=settings.rotation_shuffle_fallback,
    )
    return Daemon(
        settings=settings,
        tv=tv,
        state=state,
        watcher=watcher,
        clock=clock.as_clock(),
        surface=surface,
    )


class TestTheLabelFollowsTheWall:
    @pytest.mark.asyncio
    async def test_a_confirmed_selection_puts_a_label_on_the_surface(self, labelled, surface, publish):
        publish(["work-a"], labels={"work-a": {"title": "Cat Litter", "artist": "Ed Ruscha"}})

        await labelled.tick()

        assert surface.shown, "the wall changed and no label was drawn"
        assert surface.last_text[:2] == ["Cat Litter", "Ed Ruscha"]

    @pytest.mark.asyncio
    async def test_the_label_is_set_at_the_surface_s_own_type_scale(self, settings, tv, state, clock, publish):
        """**The seam between the device and the type, pinned on the drawn output.**

        How large the label's type has to be is a fact about this panel's
        resolution and how far away it is read, so the device supplies it and the
        daemon must set the label at what it was given. A draw path that reached
        for sizes of its own would be asserting that every surface is read from
        the same place — which is how this product came to render body type at
        half the height a letter must reach to be resolvable, undetected.

        **The fake is given a scale no derivation would produce**, because a fixture
        carrying the reference wall's own numbers cannot tell "used the surface's
        scale" apart from "hardcoded the reference wall's" — both routes would
        arrive at the same pixels and the test would pass either way.
        """
        absurd = TypeScale(primary_px=7, floor_px=3)
        surface = FakeSurface(type_scale=absurd)
        daemon = Daemon(
            settings=settings,
            tv=tv,
            state=state,
            watcher=Watcher(
                settings.manifest_path,
                rotation_interval_fallback=settings.rotation_interval_fallback_seconds,
                shuffle_fallback=settings.rotation_shuffle_fallback,
            ),
            clock=clock.as_clock(),
            surface=surface,
        )
        publish(["work-a"], labels={"work-a": {"title": "Cat Litter", "artist": "Ed Ruscha"}})

        await daemon.tick()

        surface.release.set()
        sizes = {block.size_px for block in surface.shown[-1].blocks}
        assert sizes <= {absurd.primary_px, absurd.floor_px}, f"the label was set at sizes the surface never gave it: {sizes}"
        assert absurd.primary_px in sizes, "the leading line did not get the surface's primary tier"

    @pytest.mark.asyncio
    async def test_nothing_is_captioned_when_the_wall_did_not_change(self, labelled, surface, tv, publish):
        """The label must never name a picture the set accepted and never displayed.

        A wrong label is worse than a stale one: a stale label is visibly old, and
        a wrong one is indistinguishable from a right one.
        """
        tv.displays_nothing_selected = True
        publish(["work-a"], labels={"work-a": {"title": "Cat Litter"}})

        await labelled.tick()

        assert surface.shown == []

    @pytest.mark.asyncio
    async def test_the_label_changes_with_the_wall(self, labelled, surface, publish, clock):
        publish(
            ["work-a", "work-b"],
            shuffle=False,
            labels={"work-a": {"title": "Cat Litter"}, "work-b": {"title": "Silver Sun"}},
        )

        await labelled.tick()
        clock.advance(10_000)
        await labelled.tick()

        assert [layout.blocks[0].text for layout in surface.shown] == ["Cat Litter", "Silver Sun"]

    @pytest.mark.asyncio
    async def test_a_work_with_no_label_text_still_shows(self, labelled, surface, publish):
        """A work whose institution published nothing is not an error."""
        publish(["work-a"], labels={"work-a": {}})

        await labelled.tick()

        assert surface.shown, "an empty label stopped the wall"
        assert surface.last_text == []


class TestAPanelFailureNeverStopsTheWall:
    @pytest.mark.asyncio
    async def test_a_failure_that_is_not_the_declared_one_still_leaves_the_wall_rotating(self, labelled, surface, tv, publish):
        """**The half a declared exception type cannot cover.**

        `show` converts its own failures, but the caller reads `geometry` and
        `measure` outside it — and `measure` on the real surface reaches Pango
        through C bindings, which raise GLib errors related to nothing this
        codebase can name. A catch listing only the exceptions somebody thought of
        would let one of those past, and the promise that nothing about a label
        may stop the wall would be false in exactly the case nobody rehearsed: a
        Pi with a font cache it cannot build.
        """
        surface.measurement_explodes = True
        publish(["work-a"], labels={"work-a": {"title": "Cat Litter"}})

        await labelled.tick()

        assert tv.displaying is not None, "a text stack that could not measure took the wall down with it"
        assert surface.shown == []

    @pytest.mark.asyncio
    async def test_that_failure_is_reported_rather_than_swallowed(self, labelled, surface, publish, caplog):
        """Caught broadly is not the same as caught silently: this is a real fault
        and the journal is where this plane says so."""
        surface.measurement_explodes = True
        publish(["work-a"], labels={"work-a": {"title": "Cat Litter"}})

        with caplog.at_level("WARNING"):
            await labelled.tick()

        assert [r for r in caplog.records if getattr(r, "event", None) == "label.failed"]

    @pytest.mark.asyncio
    async def test_a_refusing_surface_leaves_the_picture_selected(self, labelled, surface, tv, publish):
        surface.refuses = True
        publish(["work-a"], labels={"work-a": {"title": "Cat Litter"}})

        await labelled.tick()

        assert tv.displaying is not None
        assert len(tv.selected) == 1, "the wall did not change because the label failed"

    @pytest.mark.asyncio
    async def test_rotation_carries_on_across_repeated_panel_failures(self, labelled, surface, tv, publish, clock):
        surface.refuses = True
        publish(["work-a", "work-b"], shuffle=False, labels={"work-a": {}, "work-b": {}})

        await labelled.tick()
        clock.advance(10_000)
        await labelled.tick()

        assert len(tv.selected) == 2

    @pytest.mark.asyncio
    async def test_the_failure_is_reported_once_not_once_a_rotation(self, labelled, surface, publish, clock, caplog):
        """A panel with a loose ribbon fails every rotation, all night."""
        surface.refuses = True
        publish(["work-a", "work-b"], shuffle=False, labels={"work-a": {}, "work-b": {}})

        with caplog.at_level("WARNING"):
            await labelled.tick()
            clock.advance(10_000)
            await labelled.tick()

        failures = [r for r in caplog.records if getattr(r, "event", None) == "label.failed"]
        assert len(failures) == 1

    @pytest.mark.asyncio
    async def test_a_refusing_surface_is_not_re_asked_on_every_poll(self, labelled, surface, publish):
        """The poll is a second and a real draw is seconds. That ratio is the fault.

        The label follows what the set says is on the wall, and a refusing panel
        leaves that unreconciled — so a rule that re-drew until it succeeded would
        put a fresh two-second frame into the panel every second, for as long as
        the ribbon stays loose. A panel gets its next chance when the wall next
        changes, which is also the first moment its label would be wrong.
        """
        surface.refuses = True
        publish(["work-a"], labels={"work-a": {"title": "Cat Litter"}})

        await labelled.tick()
        await labelled.tick()
        await labelled.tick()

        assert surface.draws_begun == 1

    @pytest.mark.asyncio
    async def test_a_recovered_surface_says_so(self, labelled, surface, publish, clock, caplog):
        surface.refuses = True
        publish(["work-a", "work-b"], shuffle=False, labels={"work-a": {}, "work-b": {}})
        await labelled.tick()

        surface.refuses = False
        clock.advance(10_000)
        with caplog.at_level("INFO"):
            await labelled.tick()

        assert [r for r in caplog.records if getattr(r, "event", None) == "label.recovered"]

    @pytest.mark.asyncio
    async def test_a_panel_that_fails_after_working_is_reported_as_failing(
        self, labelled, surface, tv, publish, clock, caplog, art_root: Path
    ):
        """**The third failure point, and the only one with an edge in it.**

        A panel that is broken from the outset never has to change its mind. This
        one draws, and then stops — a ribbon that works cold and fails warm, which
        is the failure an e-paper panel on a wall actually has. Everything the
        other tests here assert is a latch away from being wrong: a `ReportOnce`
        that stayed ended after a good draw would say nothing, and a
        `label_surface_working` that stayed True would tell curation the panel is
        fine while nobody in the room can read a label.
        """
        publish(["work-a", "work-b"], shuffle=False, labels={"work-a": {}, "work-b": {}})
        await labelled.tick()
        assert surface.shown, "the panel never worked, so this is not the mid-run case"
        first = json.loads((art_root / HEARTBEAT_FILENAME).read_text())
        assert first["label_surface_working"] is True

        surface.refuses = True
        clock.advance(10_000)
        with caplog.at_level("WARNING"):
            await labelled.tick()

        assert len(tv.selected) == 2, "the wall stopped when the panel did"
        assert len([r for r in caplog.records if getattr(r, "event", None) == "label.failed"]) == 1
        document = json.loads((art_root / HEARTBEAT_FILENAME).read_text())
        assert document["label_surface_working"] is False


class TestTheDrawIsNotOnTheEventLoop:
    """A full frame is seconds, and the television client's reader shares this loop.

    Moving the draw off the library's callback did not move it off the loop they
    both run on: a coroutine that rasterises and clocks bytes out over SPI delays
    every message on that socket — including the selection confirmations the
    rotation is waiting on — exactly as much as doing it in the callback would.
    """

    @pytest.mark.asyncio
    async def test_the_loop_keeps_running_while_the_panel_draws(self, labelled, surface, publish):
        surface.draw_takes_seconds = 0.2
        publish(["work-a"], labels={"work-a": {"title": "Cat Litter"}})

        ticking = asyncio.create_task(labelled.tick())
        turns_taken_mid_draw = 0
        while not ticking.done():
            if surface.entered.is_set() and not surface.left.is_set():
                turns_taken_mid_draw += 1
            await asyncio.sleep(0.001)
        await ticking

        assert surface.shown, "the label never drew, so this proves nothing"
        # A draw on the loop enters and leaves inside one uninterrupted stretch,
        # so this counter cannot come off zero however long the panel takes.
        assert turns_taken_mid_draw > 0, "nothing else on the loop got a turn while the panel drew"

    @pytest.mark.asyncio
    async def test_a_panel_that_never_comes_back_does_not_take_the_wall_with_it(
        self, labelled, surface, tv, publish, clock, caplog, monkeypatch
    ):
        """**The one way a panel can stop the wall that no `except` clause reaches.**

        A driver wedged in a bad SPI transaction does not raise; it simply never
        returns. Off the loop that is a parked thread, which is survivable. Waited
        on without a bound it is the rotation, the poll timer and the SIGTERM path
        all stopped behind an annotation of the wall.
        """
        monkeypatch.setattr(daemon_module, "LABEL_DRAW_BUDGET_SECONDS", 0.05)
        surface.blocks = True
        publish(["work-a", "work-b"], shuffle=False, labels={"work-a": {}, "work-b": {}})

        try:
            with caplog.at_level("WARNING"):
                await asyncio.wait_for(labelled.tick(), timeout=10)
                clock.advance(10_000)
                await asyncio.wait_for(labelled.tick(), timeout=10)

            assert len(tv.selected) == 2, "a panel that never answered stopped the rotation"
            assert [r for r in caplog.records if getattr(r, "event", None) == "label.failed"]
            # **The second rotation dispatched nothing, and that gate is not
            # decoration.** The executor a draw goes to is the one the television
            # client's own blocking calls use, so a hung draw left behind per
            # rotation would end with the *set* waiting behind the panel — a panel
            # stopping the wall by the back door, after being moved off it by the
            # front.
            assert surface.draws_begun == 1
        finally:
            # In a `finally` because the loop joins its executor on the way out and
            # waits five minutes to do it — so a thread this test failed before
            # releasing would cost every run after it, not just this one.
            surface.release.set()
            assert await _comes_back(surface.left), "the draw thread never came back"

    @pytest.mark.asyncio
    async def test_a_draw_that_never_got_a_thread_does_not_close_the_gate_for_ever(
        self, labelled, surface, publish, clock, monkeypatch
    ):
        """**The budget can expire before the work starts, not only while it runs.**

        A draw is handed to a shared pool, and the television's own blocking calls
        use that pool too — so a draw can still be sitting in the queue when its
        budget runs out, never having touched the panel. Anything that releases the
        gate from *inside* the draw is then never reached, and every label after it
        is turned away by a gate guarding work that never happened: a device with a
        working panel goes blank until the process restarts, reporting itself
        broken the whole time. The pool is squeezed to one worker here and that
        worker is occupied, which is that queue with the timing made certain.
        """
        monkeypatch.setattr(daemon_module, "LABEL_DRAW_BUDGET_SECONDS", 0.05)
        publish(["work-a", "work-b"], shuffle=False, labels={"work-a": {}, "work-b": {}})
        occupied, let_go = threading.Event(), threading.Event()

        with ThreadPoolExecutor(max_workers=1) as only_one_thread:
            asyncio.get_running_loop().set_default_executor(only_one_thread)
            only_one_thread.submit(lambda: (occupied.set(), let_go.wait(30)))
            assert await _comes_back(occupied), "the pool's one worker was never taken"

            await asyncio.wait_for(labelled.tick(), timeout=10)
            assert surface.draws_begun == 0, "the draw ran, so this is not the queued case"

            # **The loop is let settle before the worker is freed**, because the
            # two are unrelated in life: what occupies that pool is a television
            # call taking seconds, and it finishes when it finishes. Freeing the
            # worker in the same event-loop step that gave up waiting models a
            # coincidence, and it hides anything the loop would have done to the
            # queued draw in between — a cancellation, say, which is the one thing
            # that must not happen to it.
            await asyncio.sleep(0.05)
            let_go.set()
            assert await _comes_back(surface.left), "the queued draw never ran once a thread was free"

            clock.advance(10_000)
            await asyncio.wait_for(labelled.tick(), timeout=10)

        assert surface.draws_begun == 2, "the panel was never drawn to again"

    @pytest.mark.asyncio
    async def test_a_panel_that_comes_back_is_drawn_to_again(self, labelled, surface, publish, clock, monkeypatch):
        """**The gate has to open again, and only its own draw can open it.**

        Whatever holds this closed is released by a draw nobody is waiting for any
        more — so it cannot be a flag the waiting side clears, and it cannot be a
        cancellation, which would mark the work finished while the panel was still
        being written to. A gate that stayed shut would leave a working panel
        permanently blank and reported broken, which is the failure this whole
        subsystem is arranged to make impossible.
        """
        monkeypatch.setattr(daemon_module, "LABEL_DRAW_BUDGET_SECONDS", 0.05)
        surface.blocks = True
        publish(["work-a", "work-b"], shuffle=False, labels={"work-a": {}, "work-b": {}})
        await asyncio.wait_for(labelled.tick(), timeout=10)

        surface.release.set()
        assert await _comes_back(surface.left), "the draw thread never came back"
        surface.blocks = False
        clock.advance(10_000)
        await asyncio.wait_for(labelled.tick(), timeout=10)

        assert surface.shown, "the panel recovered and was never drawn to again"


class TestTheRemoteIsACuratorToo:
    """A selection this plane did not make still changes what the wall is showing.

    Somebody picks a different work with the remote in art mode. Nothing in the
    rotation path runs, so a label driven only from that path goes on naming the
    previous picture for the rest of the interval — up to three minutes of a
    confident, wrong label on the one surface the person in the room can read.
    """

    @pytest.mark.asyncio
    async def test_a_work_chosen_from_the_remote_gets_its_own_label(self, labelled, surface, tv, state, publish):
        publish(
            ["work-a", "work-b"],
            shuffle=False,
            labels={"work-a": {"title": "Cat Litter"}, "work-b": {"title": "Silver Sun"}},
        )
        await labelled.tick()
        assert surface.last_text[:1] == ["Cat Litter"]

        binding = state.binding_for("work-b")
        assert binding is not None and binding.tv_content_id, "work-b never reached the set to be chosen"
        tv.announce(binding.tv_content_id, is_shown=True)
        await labelled.tick()

        assert surface.last_text[:1] == ["Silver Sun"]

    @pytest.mark.asyncio
    async def test_a_picture_this_device_cannot_name_gets_an_empty_label(self, labelled, surface, tv, publish):
        """Choosing one of the set's own art-store images is a supported thing to do.

        No label text for it exists anywhere on this device. Blank says "nothing is
        known about what you are looking at"; leaving the last work's label up says
        something false, and nobody standing in front of it can tell which.
        """
        publish(["work-a"], labels={"work-a": {"title": "Cat Litter"}})
        await labelled.tick()

        tv.announce("SAM-F0222", is_shown=True)
        await labelled.tick()

        assert surface.last_text == []

    @pytest.mark.asyncio
    async def test_this_planes_own_selection_is_not_drawn_twice(self, labelled, surface, publish):
        """The set announces our own selections too — that is how they are confirmed.

        A redraw rule that read the announcement without knowing what it had
        already drawn would put every rotation on the panel twice, at seconds a
        frame.
        """
        publish(["work-a"], labels={"work-a": {"title": "Cat Litter"}})

        await labelled.tick()

        assert len(surface.shown) == 1


class TestADeviceWithNoLabelSurface:
    """A supported deployment, not a degraded one."""

    @pytest.mark.asyncio
    async def test_the_wall_rotates_normally(self, daemon, tv, publish):
        publish(["work-a"], labels={"work-a": {"title": "Cat Litter"}})

        await daemon.tick()

        assert tv.displaying is not None

    @pytest.mark.asyncio
    async def test_its_absence_is_never_reported_as_a_fault(self, daemon, publish, caplog):
        publish(["work-a"], labels={"work-a": {"title": "Cat Litter"}})

        with caplog.at_level("WARNING"):
            await daemon.tick()

        assert not [r for r in caplog.records if getattr(r, "event", None) == "label.failed"]

    @pytest.mark.asyncio
    async def test_the_heartbeat_says_null_rather_than_false(self, daemon, publish, art_root: Path):
        """`false` would read as a broken panel on a device that has none."""
        publish(["work-a"])

        await daemon.tick()

        document = json.loads((art_root / HEARTBEAT_FILENAME).read_text())
        assert document["label_surface_working"] is None
        assert document["has_label_surface"] is False

    @pytest.mark.asyncio
    async def test_it_is_told_apart_from_a_panel_that_has_not_drawn_yet(self, labelled, publish, art_root: Path):
        """Two different deployments that once reported identically.

        `label_surface_working` is null both on a device with no panel and on one
        whose panel is fine but has not been asked to draw. Read alone it made a
        freshly started plane look like a device with no panel at all.
        """
        await labelled.tick()  # no manifest yet, so nothing has been captioned

        document = json.loads((art_root / HEARTBEAT_FILENAME).read_text())
        assert document["has_label_surface"] is True
        assert document["label_surface_working"] is None


class TestADeviceWhosePanelWouldNotOpen:
    """The third deployment, and the one that used to be invisible.

    A panel configured in `.env` that will not open leaves the daemon holding no
    surface — which, reported as `has_label_surface: false`, is exactly what a
    device with no panel reports. So curation's health surface showed a supported
    deployment where there was a broken one, and the only account of it was a
    warning in a journal on a Pi nobody was reading.
    """

    @pytest.fixture
    def broken(self, settings, tv, state, clock) -> Daemon:
        watcher = Watcher(settings.manifest_path, rotation_interval_fallback=180, shuffle_fallback=False)
        return Daemon(
            settings=settings,
            tv=tv,
            state=state,
            watcher=watcher,
            clock=clock.as_clock(),
            surface=None,
            surface_error="could not open the e-paper device 'waveshare_epd.it8951' (no SPI device)",
        )

    @pytest.mark.asyncio
    async def test_the_heartbeat_says_this_device_has_a_panel_and_it_is_not_working(self, broken, publish, art_root: Path):
        publish(["work-a"])

        await broken.tick()

        document = json.loads((art_root / HEARTBEAT_FILENAME).read_text())
        assert document["has_label_surface"] is True, "a broken panel reported as a device that has none"
        assert document["label_surface_working"] is False, "a panel that never opened reported as one that has not been asked yet"

    @pytest.mark.asyncio
    async def test_curation_is_told_why(self, broken, publish, art_root: Path):
        """The journal is on the Pi; the heartbeat is what crosses to curation."""
        publish(["work-a"])

        await broken.tick()

        document = json.loads((art_root / HEARTBEAT_FILENAME).read_text())
        assert "no SPI device" in (document["last_error"] or "")

    @pytest.mark.asyncio
    async def test_the_wall_rotates_anyway(self, broken, tv, publish):
        """The whole posture in one assertion: a panel is never a precondition."""
        publish(["work-a"], labels={"work-a": {"title": "Cat Litter"}})

        await broken.tick()

        assert tv.displaying is not None


class TestShuttingDown:
    @pytest.mark.asyncio
    async def test_the_label_surface_is_released(self, labelled, surface):
        """On e-paper `close()` is the power-down, not bookkeeping."""
        stop = asyncio.Event()
        stop.set()

        await labelled.run(stop)

        assert surface.closed == 1

    @pytest.mark.asyncio
    async def test_a_device_with_no_surface_shuts_down_cleanly(self, daemon, tv):
        stop = asyncio.Event()
        stop.set()

        await daemon.run(stop)

        assert tv.closed == 1


class TestTheHeartbeat:
    @pytest.mark.asyncio
    async def test_a_running_plane_writes_one(self, daemon, publish, art_root: Path):
        publish(["work-a"])

        await daemon.tick()

        assert (art_root / HEARTBEAT_FILENAME).is_file()

    @pytest.mark.asyncio
    async def test_it_carries_what_the_wall_is_showing(self, daemon, publish, art_root: Path):
        publish(["work-a"])

        await daemon.tick()

        document = json.loads((art_root / HEARTBEAT_FILENAME).read_text())
        assert document["current_work_id"] == "work-a"
        assert document["television_reachable"] is True
        assert document["television_showing_art"] is True

    @pytest.mark.asyncio
    async def test_it_carries_the_sets_own_announcement_not_only_our_belief(self, daemon, tv, publish, art_root: Path, clock):
        """Somebody used the remote. The heartbeat should say what is actually up."""
        publish(["work-a"])
        await daemon.tick()

        tv.announce("SAM-F0222", is_shown=True)
        clock.advance(INTERVAL_SECONDS * 1.5)
        await daemon.tick()

        document = json.loads((art_root / HEARTBEAT_FILENAME).read_text())
        assert document["announced_content_id"] == "SAM-F0222"

    @pytest.mark.asyncio
    async def test_it_is_written_while_the_television_is_unreachable(self, daemon, tv, publish, art_root: Path):
        """The condition an operator most wants reported.

        A plane that only beat on good passes would fall silent exactly when it
        had something to say, and curation would report a healthy process as one
        that has never spoken.
        """
        publish(["work-a"])
        tv.unavailable = True

        await daemon.tick()

        document = json.loads((art_root / HEARTBEAT_FILENAME).read_text())
        assert document["television_reachable"] is False
        assert document["last_error"]

    @pytest.mark.asyncio
    async def test_it_is_written_before_any_manifest_exists(self, daemon, art_root: Path):
        """The state a fresh install sits in, and when 'is it alive' is asked most."""
        await daemon.tick()

        document = json.loads((art_root / HEARTBEAT_FILENAME).read_text())
        assert document["manifest_schema"] is None

    @pytest.mark.asyncio
    async def test_it_is_not_rewritten_on_every_pass(self, daemon, publish, art_root: Path, clock):
        """At the one-second poll this would be ~86,400 writes a day, forever."""
        publish(["work-a"])
        await daemon.tick()
        first = (art_root / HEARTBEAT_FILENAME).read_text()

        clock.advance(INTERVAL_SECONDS / 4)
        await daemon.tick()

        assert (art_root / HEARTBEAT_FILENAME).read_text() == first

    @pytest.mark.asyncio
    async def test_it_is_rewritten_once_the_interval_has_run(self, daemon, publish, art_root: Path, clock):
        publish(["work-a"])
        await daemon.tick()
        first = json.loads((art_root / HEARTBEAT_FILENAME).read_text())

        # Deliberately not a whole multiple of the interval: a clock stepped by
        # exactly the wait cannot tell `>=` from `>`.
        clock.advance(INTERVAL_SECONDS * 1.5)
        await daemon.tick()

        second = json.loads((art_root / HEARTBEAT_FILENAME).read_text())
        assert second["reported_at"] != first["reported_at"]

    @pytest.mark.asyncio
    async def test_an_unwritable_heartbeat_does_not_stop_the_wall(self, daemon, tv, publish, art_root: Path):
        """The disk is full or read-only. The television is unaffected."""
        (art_root / HEARTBEAT_FILENAME).mkdir()
        publish(["work-a"])

        await daemon.tick()

        assert tv.displaying is not None
