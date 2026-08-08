"""The typesetter, run against a real text stack.

**Its own directory because it is the one part of this suite that needs something
a default install does not provide.** Pango arrives through PyGObject in the
`raster` dependency group; the rest of this plane installs and tests without it,
so these are collected only where that group is present — the Pi, and the CI leg
that installs it. `tests/test_default_suite_ci_scope.py` at the repo root is what
keeps the workflow and this directory agreeing about that.

**Nothing here compares pixels to a stored image.** The available faces differ
between a Raspberry Pi and a GitHub runner, so a golden image would assert which
fonts the machine has rather than what this code does, and would go red on a
machine where the label is perfectly legible. What is asserted instead is the set
of properties the label's legibility actually rests on: the buffer is the shape it
claims, the ground is white and the type is dark, the greys that make antialiased
type readable are really there, size and wrap width change the extents in the
directions they must, and museum text is set literally rather than parsed as
markup.
"""

import pytest

pytest.importorskip("gi", reason="the typesetter needs the `raster` group: uv sync --group raster")

from display.panel.layout import Block, Layout, Surface  # noqa: E402 -- after the group check above
from display.panel.pango import PangoRasterizer  # noqa: E402 -- importing it is what needs the group

#: **Deliberately not a multiple of four.** Cairo pads each row of an A8 surface
#: out to a four-byte boundary, so a width of 1448 — the reference panel's, and
#: divisible by four — hides a stride bug completely. This one does not.
AWKWARD = Surface(width_px=101, height_px=60, margin_px=5)


@pytest.fixture
def rasterizer() -> PangoRasterizer:
    return PangoRasterizer()


def a_layout(text: str = "Cat Litter", *, size_px: int = 12, y_px: int = 5, surface: Surface = AWKWARD) -> Layout:
    return Layout(
        surface=surface,
        blocks=(Block(text=text, size_px=size_px, x_px=surface.margin_px, y_px=y_px, width_px=0, height_px=0),),
        dropped=(),
    )


class TestTheBufferIsTheShapeItClaims:
    def test_a_width_that_is_not_a_multiple_of_four_still_comes_back_flat(self, rasterizer):
        """The stride correction, asserted at the width that can catch it.

        A padded buffer handed through unchanged puts every row after the first a
        few pixels late, and the label arrives sheared — invisible at the
        reference panel's own 1448 pixels, where the padding is zero.
        """
        raster = rasterizer.render(a_layout())

        assert (raster.width_px, raster.height_px) == (AWKWARD.width_px, AWKWARD.height_px)
        assert len(raster.pixels) == AWKWARD.width_px * AWKWARD.height_px

    def test_an_empty_label_is_a_white_surface_rather_than_a_black_one(self, rasterizer):
        """A work whose institution published no label text gets a blank panel,
        not an inverted one — and the inversion is easy to get backwards."""
        raster = rasterizer.render(Layout(surface=AWKWARD, blocks=(), dropped=()))

        assert set(raster.pixels) == {255}


class TestTheTypeIsDarkAndTheGreysAreReal:
    def test_drawing_text_puts_dark_pixels_on_the_surface(self, rasterizer):
        raster = rasterizer.render(a_layout())

        assert min(raster.pixels) < 64, "the type came out no darker than mid-grey"

    def test_the_antialiased_greys_are_there_which_is_what_gray16_is_for(self, rasterizer):
        """The panel is driven in sixteen greys rather than one bit precisely so
        these exist. A rasterizer producing only black and white would make that
        whole decision — and the legibility claim resting on it — worthless."""
        raster = rasterizer.render(a_layout())

        assert any(0 < value < 255 for value in raster.pixels), "the type is hard-edged; nothing would be gained by gray16"

    def test_nothing_is_drawn_below_a_block_that_sits_at_the_top(self, rasterizer):
        """Placement is honoured, not ignored — a rasterizer that drew every block
        at the origin would pass every extent-based test above."""
        raster = rasterizer.render(a_layout(y_px=0, size_px=10))

        bottom = raster.pixels[AWKWARD.width_px * 40 :]
        assert set(bottom) == {255}, "ink appeared far below a block placed at the top"

    def test_nothing_is_drawn_above_a_block_that_sits_lower_down(self, rasterizer):
        """The other direction, and the one that actually catches the mistake.

        A rasterizer that ignored placement entirely and drew everything at the
        origin passes the test above — the ink is at the top either way. Only a
        block placed *down* the surface tells the two apart, which is why both
        halves are here: the layout tier's whole output is a set of coordinates,
        and a renderer that discarded them would stack every line of a label on
        top of the first.
        """
        raster = rasterizer.render(a_layout(y_px=30, size_px=10))

        above = raster.pixels[: AWKWARD.width_px * 25]
        below = raster.pixels[AWKWARD.width_px * 30 :]
        assert set(above) == {255}, "ink appeared above a block placed thirty pixels down"
        assert min(below) < 64, "the block was placed thirty pixels down and drawn nowhere"


class TestMeasuringMovesInTheDirectionsTheLayoutTierRelieson:
    def test_a_size_in_pixels_is_a_size_in_pixels(self, rasterizer):
        """**The units, which nothing else here would catch.**

        Every size this product reasons about is in pixels: the layout tier's
        constants, the panel's geometry, and the mid-20s-to-low-40s range the
        operator's look at the real panel established. Pango's ordinary
        `set_size` takes *points* and resolves them through an ambient
        resolution — 96 dpi by default — so the same number comes out a third
        larger, silently. Every relative assertion below passes either way, since
        both scale monotonically; only measuring against the requested number
        tells them apart.

        The bound is loose on purpose. A single line is one em plus the face's
        ascent and descent, which is about 1.15–1.25× the size for the sans faces
        this resolves to; going through points would put it near 1.55×.
        """
        measured = rasterizer.measure("Hg", 40, 400)

        assert 40 <= measured.height_px < 56, (
            f"a line asked for at 40 px measured {measured.height_px} px — outside what a face's "
            "ascent and descent explain, which is what asking in points and getting 96 dpi looks like"
        )

    def test_bigger_type_measures_taller(self, rasterizer):
        small = rasterizer.measure("Cat Litter", 12, 400)
        large = rasterizer.measure("Cat Litter", 40, 400)

        assert large.height_px > small.height_px
        assert large.width_px > small.width_px

    def test_a_narrower_wrap_measures_taller(self, rasterizer):
        """The layout tier's drop rule is driven entirely by measured height, so a
        measurer that ignored the wrap width would report every label as fitting
        and the last lines would run off the panel."""
        wide = rasterizer.measure("A rather long museum title that has to wrap somewhere", 12, 400)
        narrow = rasterizer.measure("A rather long museum title that has to wrap somewhere", 12, 80)

        assert narrow.height_px > wide.height_px

    def test_an_unbreakable_run_wraps_rather_than_running_off_the_edge(self, rasterizer):
        """A museum record carries accession strings and URLs with no space in
        them. Under Pango's word wrapping those are drawn straight past the right
        margin; the label has to break mid-word instead, because ugly beats
        unreadable."""
        measured = rasterizer.measure("A" * 200, 12, 80)

        assert measured.width_px <= 80


class TestMuseumTextIsSetLiterallyAndNeverAsMarkup:
    def test_angle_brackets_are_drawn_rather_than_parsed(self, rasterizer):
        """The 2024 label interpolated description text into a markup string, so a
        title containing `<` produced mangled type or a parse failure. Set
        literally, the tags are characters and take room — which is exactly what
        distinguishes the two here."""
        plain = rasterizer.measure("Untitled", 12, 400)
        tagged = rasterizer.measure("<i>Untitled</i>", 12, 400)

        assert tagged.width_px > plain.width_px, "the markup was parsed away instead of being drawn"

    def test_an_unclosed_tag_is_text_rather_than_an_error(self, rasterizer):
        """Under `set_markup` this raises and takes the label with it."""
        assert rasterizer.render(a_layout("Piece <3 of 5")).pixels
