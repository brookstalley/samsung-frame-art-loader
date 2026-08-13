"""The e-paper surface, driven against a double of the driver rather than a panel.

**Everything here would otherwise only be checkable on a Pi with a panel screwed
to it**, which is why the driver is passed in rather than opened inside. What is
under test is the four corrections this surface applies at the seam: the panel is
put into sixteen greys and checked rather than asked, a driver that returns
nothing on failure is turned into one that raises, the frame is turned to match
how the panel is mounted, and nothing on the shutdown path can throw.

The one thing that genuinely needs the library — `open_panel` — is a single
function, and what it promises (a failure to open is a `SurfaceUnavailable`, not
an `ImportError` escaping into the composition root) is asserted here on a machine
where the library is deliberately absent.
"""

import logging

import pytest

from display.panel.epaper import GREYSCALE_MODE, EpaperSurface, open_panel
from display.panel.layout import Block, Geometry, Layout
from display.panel.legibility import TypeScale
from display.panel.raster import Raster, Rasterizer
from display.panel.styling import Run

GEOMETRY = Geometry(width_px=8, height_px=4, margin_px=1)

#: **Absurd on purpose, to match the eight-pixel-wide "panel" above.** Nothing in
#: this module typesets anything — the rasterizer is a double — so what these
#: sizes have to be is *carried through unchanged*, and numbers that could not
#: come off a real derivation make it obvious that this file is not the place
#: any judgement about legibility is made.
TYPE_SCALE = TypeScale(primary_px=2, floor_px=1)


class FakeEpd:
    """omni-epd's device surface: `mode` accepts what it is given and reports it back."""

    def __init__(self, *, width: int = 8, height: int = 4) -> None:
        self.mode = "bw"
        self.width = width
        self.height = height
        self.calls: list[str] = []
        self.shown: list[object] = []
        #: Armed failure: the driver raises out of `display`, as a real one does
        #: when the SPI bus or the controller is unhappy.
        self.raises: Exception | None = None

    def prepare(self) -> None:
        self.calls.append("prepare")

    def display(self, image: object) -> None:
        self.calls.append("display")
        if self.raises:
            raise self.raises
        self.shown.append(image)

    def sleep(self) -> None:
        self.calls.append("sleep")

    def close(self) -> None:
        self.calls.append("close")


class FlatRasterizer(Rasterizer):
    """Draws a recognisable gradient, so a rotation is visible in the bytes."""

    @property
    def measure(self):
        return lambda line, size_px, wrap_px: None  # never called here

    def render(self, layout: Layout) -> Raster:
        width, height = layout.surface.width_px, layout.surface.height_px
        # Row index in every byte: row 0 is all zeroes, row 1 all ones. A half turn
        # reverses the row order, which no symmetric pattern would show.
        pixels = bytes(row for row in range(height) for _ in range(width))
        return Raster(width_px=width, height_px=height, pixels=pixels)


def a_surface(**kwargs) -> EpaperSurface:
    epd = kwargs.pop("epd", None) or FakeEpd()
    return EpaperSurface(
        epd=epd,
        rasterizer=kwargs.pop("rasterizer", None) or FlatRasterizer(),
        geometry=kwargs.pop("geometry", GEOMETRY),
        type_scale=kwargs.pop("type_scale", TYPE_SCALE),
        **kwargs,
    )


def a_layout() -> Layout:
    block = Block(runs=(Run("Cat Litter"),), size_px=4, x_px=1, y_px=1, width_px=6, height_px=2, wrap_px=6)
    return Layout(surface=GEOMETRY, blocks=(block,), dropped=())


class TestTheGreyLevelsAreTakenRatherThanAskedFor:
    """The trap this product's legibility depends on not falling into.

    The driver's default is one bit, and `max_colors` reports 16 in both modes, so
    the obvious check cannot tell them apart. The 2024 plane shipped 1-bit type
    past every check anyone thought to run.
    """

    def test_the_panel_is_put_into_sixteen_greys(self):
        epd = FakeEpd()

        a_surface(epd=epd)

        assert epd.mode == GREYSCALE_MODE, "the panel was left in the driver's one-bit default"

    def test_a_panel_that_quietly_stays_in_one_bit_is_refused(self):
        """A read-back that disagrees is the only signal there is, so it must bite.

        Accepting it would put 1-bit type on the wall behind a surface reporting
        itself healthy — legible close up, and not at the standing distance this
        label exists to be read from. This is the *measured* behaviour being
        guarded against and not a hypothetical: the driver comes up in `bw`, and
        `max_colors` says 16 either way.
        """
        from display.panel.surface import SurfaceUnavailable

        class StaysInOneBit(FakeEpd):
            """Takes the assignment and goes on running in one bit."""

            @property
            def mode(self) -> str:
                return "bw"

            @mode.setter
            def mode(self, value: str) -> None:
                pass

        with pytest.raises(SurfaceUnavailable) as raised:
            a_surface(epd=StaysInOneBit())

        assert "bw" in str(raised.value) and GREYSCALE_MODE in str(raised.value)

    def test_a_driver_that_raises_on_the_mode_is_a_surface_that_is_unavailable(self):
        class Unsettable:
            @property
            def mode(self) -> str:
                raise OSError("the SPI bus is not there")

            @mode.setter
            def mode(self, value: str) -> None:
                raise OSError("the SPI bus is not there")

        from display.panel.surface import SurfaceUnavailable

        with pytest.raises(SurfaceUnavailable):
            a_surface(epd=Unsettable())


class TestAFailureIsRaisedBecauseTheDriverWillNotReportOne:
    def test_a_frame_that_lands_goes_prepare_display_sleep(self):
        epd = FakeEpd()
        surface = a_surface(epd=epd)

        surface.show(a_layout())

        assert epd.calls == ["prepare", "display", "sleep"]

    def test_a_driver_that_raises_becomes_a_surface_that_is_unavailable(self):
        """The caller catches one type. Anything the Cython driver throws must
        arrive as that type or the daemon's `_caption` lets it past and the panel
        takes the wall down with it."""
        from display.panel.surface import SurfaceUnavailable

        epd = FakeEpd()
        epd.raises = OSError("the controller stopped answering")
        surface = a_surface(epd=epd)

        with pytest.raises(SurfaceUnavailable) as raised:
            surface.show(a_layout())

        assert "the controller stopped answering" in str(raised.value), "the driver's own words were thrown away"

    def test_the_panel_is_not_left_awake_after_a_frame(self):
        """`sleep` is what keeps an unattended panel from drawing current all
        night between rotations three minutes apart."""
        epd = FakeEpd()

        a_surface(epd=epd).show(a_layout())

        assert epd.calls[-1] == "sleep"


class TestTheFrameIsTurnedToMatchTheMounting:
    def test_a_half_turn_reverses_the_image(self):
        epd = FakeEpd()

        a_surface(epd=epd, rotate_degrees=180).show(a_layout())

        rows = list(epd.shown[0].tobytes()[:: GEOMETRY.width_px])
        assert rows == [3, 2, 1, 0], "the label reached a panel mounted ribbon-up the right way up"

    def test_an_unturned_panel_gets_the_raster_as_drawn(self):
        epd = FakeEpd()

        a_surface(epd=epd, rotate_degrees=0).show(a_layout())

        rows = list(epd.shown[0].tobytes()[:: GEOMETRY.width_px])
        assert rows == [0, 1, 2, 3]

    def test_a_quarter_turn_is_refused_rather_than_half_supported(self):
        """It exchanges width and height, so the layout above would have been
        arranged for the wrong shape — a label laid out landscape, drawn portrait."""
        from display.panel.surface import SurfaceUnavailable

        with pytest.raises(SurfaceUnavailable) as raised:
            a_surface(rotate_degrees=90)

        assert "90" in str(raised.value)


class TestTheSurfaceSaysWhatItKnowsAndNeverStopsTheWall:
    def test_the_geometry_is_the_configured_one(self):
        """Configuration wins because the layout is arranged before anything is
        drawn, and `operational-spec.md` § Configuration makes the panel a
        deployment value."""
        assert a_surface().geometry == GEOMETRY

    def test_a_panel_that_reports_a_different_size_is_named_rather_than_refused(self, caplog):
        """Warned about, not refused — a slightly wrong label beats no label, and
        this surface may never be a reason the wall stops."""
        with caplog.at_level(logging.WARNING):
            a_surface(epd=FakeEpd(width=800, height=600))

        assert any(record.__dict__.get("event") == "panel.size_disagrees" for record in caplog.records)
        assert "800x600" in caplog.text and "8x4" in caplog.text

    def test_a_panel_that_agrees_about_its_size_says_nothing(self, caplog):
        with caplog.at_level(logging.WARNING):
            a_surface(epd=FakeEpd(width=8, height=4))

        assert caplog.records == []

    def test_a_driver_that_does_not_report_a_size_is_not_a_disagreement(self, caplog):
        """omni-epd's mock and any future device may simply not carry one, and a
        warning about a comparison nobody made is how a warning stops being read."""

        class Sizeless(FakeEpd):
            def __init__(self) -> None:
                super().__init__()
                del self.width
                del self.height

        with caplog.at_level(logging.WARNING):
            a_surface(epd=Sizeless())

        assert caplog.records == []

    def test_closing_a_panel_that_will_not_close_does_not_raise(self, caplog):
        """This runs on the way out. Raising here would cost the television its
        clean disconnect, and the set holds an abandoned art channel for minutes."""

        class Stuck(FakeEpd):
            def close(self) -> None:
                raise OSError("the device is gone")

        with caplog.at_level(logging.WARNING):
            a_surface(epd=Stuck()).close()

        assert any(record.__dict__.get("event") == "panel.close_failed" for record in caplog.records)

    def test_closing_releases_the_device(self):
        epd = FakeEpd()

        a_surface(epd=epd).close()

        assert "close" in epd.calls


class TestOpeningAPanelThatIsNotThere:
    def test_a_panel_that_cannot_be_opened_is_a_surface_that_is_unavailable(self):
        """One answer from both roads, which is what makes this test portable.

        On a laptop the library is absent and this is an `ImportError`; on the Pi
        it is installed and this is the driver's own "no such device". The
        composition root catches `SurfaceUnavailable`, so either one escaping past
        it would stop a daemon whose television is working perfectly.
        """
        from display.panel.surface import SurfaceUnavailable

        with pytest.raises(SurfaceUnavailable) as raised:
            open_panel("no_such_vendor.no_such_panel")

        assert "no_such_vendor.no_such_panel" in str(raised.value), "the operator is not told which device could not be opened"


class TestTypesettingFailsInsideTheGuardRatherThanBeforeIt:
    """`show` promises one exception type, and it has to be true of all of its work.

    The rasterizer is a text stack reached through C bindings; a font map that
    cannot be built raises something unrelated to anything the driver throws.
    Typesetting outside the guard would make the promise true only of the half
    that touches hardware — and the caller catches by type.
    """

    def test_a_rasterizer_that_raises_is_a_surface_that_is_unavailable(self):
        from display.panel.surface import SurfaceUnavailable

        class Broken(FlatRasterizer):
            def render(self, layout):
                raise RuntimeError("the text stack could not build a font map")

        surface = a_surface(rasterizer=Broken())

        with pytest.raises(SurfaceUnavailable) as raised:
            surface.show(a_layout())

        assert "could not build a font map" in str(raised.value)

    def test_the_panel_is_not_touched_when_typesetting_failed(self):
        """A frame that was never drawn must not cost a `prepare`/`sleep` cycle,
        which on e-paper is real current and real seconds."""

        class Broken(FlatRasterizer):
            def render(self, layout):
                raise RuntimeError("the text stack could not build a font map")

        from display.panel.surface import SurfaceUnavailable

        epd = FakeEpd()

        with pytest.raises(SurfaceUnavailable):
            a_surface(epd=epd, rasterizer=Broken()).show(a_layout())

        assert epd.calls == [], "the panel was woken for a frame that did not exist"
