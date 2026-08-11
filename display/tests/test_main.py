"""What the composition root refuses to start for, and what it starts anyway.

**Two refusals.** A missing deployment value, and a store written by a newer plane
than this one. Both are read by a person who has just run the command at a
terminal, so both owe the same three things: a non-zero exit so systemd and a
shell agree something failed, a sentence on stderr rather than only a JSON log
line, and no traceback, because a stack through `load()` points at this codebase,
which is the one place the problem is not. Those are driven through `main`, since
what is under test is the handling rather than the work.

**And one thing that is emphatically not a refusal**: a label panel that will not
open. The television is the product and the label annotates it, so that costs the
label, says so in the journal, and reports itself on the heartbeat — driven
through `_run`, because the claim is about the wiring between a raise and a
constructor argument, and a test of either end alone leaves the line between them
undefended.
"""

import asyncio

import pytest

from display import __main__ as entry
from display.config import ConfigError
from display.panel import SurfaceUnavailable
from display.state import StateSchemaTooNew


@pytest.fixture(autouse=True)
def _quiet_logging(monkeypatch):
    """`main` configures logging as its first act; leave the suite's alone."""
    monkeypatch.setattr(entry.logs, "configure", lambda: None)


def _raising(exc: Exception):
    async def _run() -> int:
        raise exc

    return _run


@pytest.mark.parametrize(
    ("exc", "what"),
    [
        pytest.param(
            ConfigError("ART_ROOT is not set. Copy .env.example to .env and fill it in."),
            "ART_ROOT",
            id="a missing deployment value",
        ),
        pytest.param(
            StateSchemaTooNew("display-state.sqlite was written by a display plane at schema 9; this one understands 8."),
            "schema 9",
            id="a store from a newer plane",
        ),
    ],
)
def test_a_deployment_fault_refuses_to_start_and_says_so_at_the_terminal(monkeypatch, capsys, exc: Exception, what: str):
    monkeypatch.setattr(entry, "_run", _raising(exc))

    code = entry.main()

    assert code == 2, "a refusal to start exited zero, so systemd would treat it as a clean stop"
    printed = capsys.readouterr().err
    assert "display plane cannot start" in printed
    assert what in printed, "the operator is told it cannot start but not which value is wrong"


def test_an_unexpected_failure_is_not_swallowed_into_a_tidy_exit(monkeypatch):
    """Only the two deployment faults are handled. Anything else must keep its
    traceback: those two are 'the fix is in `.env`', and a bug wearing the same
    two-line exit would send whoever reads it to the wrong file."""
    monkeypatch.setattr(entry, "_run", _raising(RuntimeError("something nobody anticipated")))

    with pytest.raises(RuntimeError):
        entry.main()


class TestWhetherThisDeviceHasALabelSurface:
    """Two roads to no label, and only one of them is a fault.

    `architecture.md` § Direction: a device with no label surface is a supported
    configuration, not a broken deployment. A device whose configured panel will
    not open is broken — and still rotates the wall, because the label is an
    annotation of the product and never a precondition for it.
    """

    def test_a_device_with_no_panel_configured_gets_no_surface_and_no_complaint(self, settings, caplog):
        import logging

        with caplog.at_level(logging.WARNING):
            assert entry.label_surface(settings) is None

        assert caplog.records == [], "a supported deployment was reported as a fault"

    def test_a_configured_panel_that_will_not_open_is_a_raise_and_not_a_second_none(self, settings):
        """The panel is absent on every machine this suite runs on, which is what
        makes this the real path rather than a simulated one.

        A raise rather than `None` because the caller has to tell the two apart:
        `None` is a deployment with no panel, and this is a deployment whose panel
        is broken. Collapsing them is how a broken panel became invisible on the
        health surface.
        """
        import dataclasses

        configured = dataclasses.replace(settings, epd_device="no_such_vendor.no_such_panel")

        with pytest.raises(SurfaceUnavailable) as raised:
            entry.label_surface(configured)

        # **Two roads and one type, which is the point.** A laptop has no text
        # stack and stops at the import; a Pi has one and stops at the device. The
        # caller must not have to tell them apart — but the operator must, so
        # whichever road was taken has to name what is missing.
        assert any(
            named in str(raised.value) for named in ("no_such_vendor.no_such_panel", "--group raster")
        ), f"the failure names neither the device nor the missing install: {raised.value}"

    @pytest.mark.parametrize(
        ("unstated", "named"),
        [
            ("epd_panel_diagonal_inches", "EPD_PANEL_DIAGONAL_INCHES"),
            ("epd_viewing_distance_inches", "EPD_VIEWING_DISTANCE_INCHES"),
        ],
    )
    def test_a_panel_whose_viewing_conditions_are_unstated_loses_the_label_and_not_the_wall(
        self, settings, unstated: str, named: str
    ):
        """**The third road to no label, and it is a fault of the same shape.**

        A device with a panel and no stated viewing distance cannot be told how
        large its type has to be, and the one thing that must not happen is
        guessing: a wrong distance gives silently illegible type, which looks like
        success from every direction except standing in front of the panel.

        But it is `SurfaceUnavailable` rather than `ConfigError` — the label
        surface goes, the daemon does not. Refusing to start would break two rules
        this plane holds: nothing about the label may stop the television, and a
        device with no usable label surface is a configuration rather than a
        fault. That distinction is the whole reason this raises the type the
        caller already catches.
        """
        import dataclasses

        configured = dataclasses.replace(settings, epd_device="omni_epd.mock", **{unstated: None})

        with pytest.raises(SurfaceUnavailable) as raised:
            entry.label_surface(configured)

        assert named in str(raised.value), f"the operator is not told which key to set: {raised.value}"

    def test_the_unstated_distance_is_reported_before_the_driver_is_even_looked_for(self, settings):
        """Both are reasons this device draws no label; only one is a value
        somebody typed. A deployment that has not stated its viewing distance must
        be told *that* — not told its text stack is missing, which on a machine
        with no panel it also is, and which names a fix that would not help.
        """
        import dataclasses

        configured = dataclasses.replace(settings, epd_device="no_such_vendor.no_such_panel", epd_viewing_distance_inches=None)

        with pytest.raises(SurfaceUnavailable) as raised:
            entry.label_surface(configured)

        assert "EPD_VIEWING_DISTANCE_INCHES" in str(raised.value)
        assert "--group raster" not in str(raised.value), "the reader was sent to fix the wrong thing"

    def test_the_border_derives_from_the_type_when_the_deployment_states_none(self, settings):
        """**The shipped path**, and the one the old 40 px default occupied.

        A border trades directly against how many lines survive the drop rule, so
        it cannot be picked independently of the floor that decides how many lines
        there are — which is now derived per device from the viewing distance.
        Asserted against `margin_for` rather than against a number, because a
        literal here would be this test re-stating the ratio instead of checking
        that the ratio is what got used.
        """
        from display.panel.legibility import margin_for, type_scale_for

        scale = type_scale_for(
            width_px=settings.epd_panel_width_px,
            height_px=settings.epd_panel_height_px,
            diagonal_inches=settings.epd_panel_diagonal_inches,
            viewing_distance_inches=settings.epd_viewing_distance_inches,
        )

        geometry = entry.label_geometry(settings, scale)

        assert geometry.margin_px == margin_for(scale)
        assert geometry.margin_px > 0, "the label was given no border at all"

    def test_a_deployment_that_states_a_border_keeps_it(self, settings):
        """The override, for the surface whose border is a physical fact: a device
        drawing its label into the mat around an artwork does not choose where the
        picture ends."""
        import dataclasses

        from display.panel.legibility import margin_for, type_scale_for

        scale = type_scale_for(width_px=1448, height_px=1072, diagonal_inches=6.0, viewing_distance_inches=84.0)
        stated = dataclasses.replace(settings, epd_margin_px=17)

        assert entry.label_geometry(stated, scale).margin_px == 17
        assert margin_for(scale) != 17, "the override happens to equal the derived value, so this proves nothing"

    async def test_a_broken_panel_does_not_stop_the_daemon_starting(self, monkeypatch, settings, tv, caplog):
        """**Driven through `_run` rather than around it**, because the claim is
        about the wiring and not about either end of it.

        `label_surface` raising and the daemon reporting `surface_error` were both
        tested while the line joining them — the `except` in the composition root —
        was covered by nothing; a mutation sweep changed it to catch
        `ZeroDivisionError` and every test still passed. That mutation is a daemon
        that refuses to start because a panel is unplugged, which inverts this
        product's whole posture: the television is the product and the label
        annotates it.
        """
        import dataclasses
        import logging

        from display import daemon as daemon_module

        built: dict[str, object] = {}

        class Recorder(daemon_module.Daemon):
            def __init__(self, **kwargs) -> None:
                built.update(kwargs)
                super().__init__(**kwargs)

            async def run(self, stop) -> None:
                return None

        def _no_panel(_settings):
            # Stubbed rather than provoked, so the message is the same on a laptop
            # with no text stack and on a Pi with one — this test is about the line
            # that joins the two ends, not about either end.
            raise SurfaceUnavailable("could not open the e-paper device 'waveshare_epd.it8951' (no SPI device)")

        monkeypatch.setattr(entry, "load", lambda: dataclasses.replace(settings, epd_device="waveshare_epd.it8951"))
        monkeypatch.setattr(entry, "SamsungTv", lambda **kwargs: tv)
        monkeypatch.setattr(entry, "Daemon", Recorder)
        monkeypatch.setattr(entry, "label_surface", _no_panel)

        with caplog.at_level(logging.WARNING):
            assert await entry._run() == 0, "a panel that would not open stopped a daemon whose television was fine"

        assert built["surface"] is None
        assert "no SPI device" in str(built["surface_error"]), "the reason was dropped on the way in"
        assert any(record.__dict__.get("event") == "panel.unavailable" for record in caplog.records)
        assert "waveshare_epd.it8951" in caplog.text, "the journal does not name which device could not be opened"


async def test_a_crash_still_closes_the_art_channel_on_the_way_out(settings, tv, state, clock):
    """`Restart=always` makes the exit path load-bearing.

    The set has been observed refusing new art-channel connections for minutes
    after a client vanished without closing, apparently holding the slot until it
    times out. So a daemon that skipped its close on the unexpected exit would
    come back up unable to reach the television it just crashed away from.
    """
    from display.daemon import Daemon
    from display.manifest import Watcher

    watcher = Watcher(settings.manifest_path, rotation_interval_fallback=180, shuffle_fallback=False)
    daemon = Daemon(settings=settings, tv=tv, state=state, watcher=watcher, clock=clock.as_clock())

    async def explode() -> float:
        raise RuntimeError("something nobody predicted")

    daemon.tick = explode  # type: ignore[method-assign]

    with pytest.raises(RuntimeError):
        await daemon.run(asyncio.Event())

    assert tv.closed, "the art channel was left open at the set"


async def test_a_crash_is_distinguishable_from_a_clean_stop_in_the_log(settings, tv, state, clock, caplog):
    """The journal is this plane's only failure channel.

    A crash used to write `daemon.stopped` at INFO — the identical line a clean
    shutdown writes — so an operator reading the log could not tell a wall
    somebody switched off from one falling over in a `Restart=always` loop.
    """
    import logging

    from display.daemon import Daemon
    from display.manifest import Watcher

    watcher = Watcher(settings.manifest_path, rotation_interval_fallback=180, shuffle_fallback=False)
    daemon = Daemon(settings=settings, tv=tv, state=state, watcher=watcher, clock=clock.as_clock())

    async def explode() -> float:
        raise RuntimeError("something nobody predicted")

    daemon.tick = explode  # type: ignore[method-assign]

    with caplog.at_level(logging.INFO), pytest.raises(RuntimeError):
        await daemon.run(asyncio.Event())

    events = [r.__dict__.get("event") for r in caplog.records]
    assert "daemon.crashed" in events, "a crash left no ERROR behind"
    assert "daemon.stopped" not in events, "a crash reported itself as a clean shutdown"
    assert any(r.levelno >= logging.ERROR for r in caplog.records)
