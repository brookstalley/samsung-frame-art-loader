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
from pathlib import Path

import pytest
from fakes import FakeSurface

from display.daemon import Daemon
from display.heartbeat import HEARTBEAT_FILENAME, INTERVAL_SECONDS
from display.manifest import Watcher


@pytest.fixture
def surface() -> FakeSurface:
    return FakeSurface()


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
    async def test_a_recovered_surface_says_so(self, labelled, surface, publish, clock, caplog):
        surface.refuses = True
        publish(["work-a", "work-b"], shuffle=False, labels={"work-a": {}, "work-b": {}})
        await labelled.tick()

        surface.refuses = False
        clock.advance(10_000)
        with caplog.at_level("INFO"):
            await labelled.tick()

        assert [r for r in caplog.records if getattr(r, "event", None) == "label.recovered"]


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
