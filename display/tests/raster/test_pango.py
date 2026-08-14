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
directions they must, the styled runs really change the type they name, and museum
text is set literally rather than parsed as markup.

**The one exception to "no stored image" is a computed one.** Proving that a style
covers a whole non-ASCII run needs something to compare against, and the reference
is rendered here from the same characters with the slant asked for on the *font*
rather than over a byte range — an independent road to the same picture, computed
on whatever machine is running, so it says nothing about which fonts are installed.
"""

import pytest

pytest.importorskip("gi", reason="the typesetter needs the `raster` group: uv sync --group raster")

import gi  # noqa: E402 -- after the group check above

# The oracle below reaches Pango directly, so this file pins the versions itself
# rather than relying on `display.panel.pango` having been imported first — which
# is an ordering the import block does not guarantee and the linter may reshuffle.
gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")

import cairo  # noqa: E402 -- same
from gi.repository import Pango, PangoCairo  # noqa: E402 -- same

from display.panel.layout import Block, Geometry, Layout  # noqa: E402 -- same
from display.panel.pango import PangoRasterizer  # noqa: E402 -- importing it is what needs the group
from display.panel.styling import Case, Line, Run, Slant, Weight  # noqa: E402 -- same

#: **Deliberately not a multiple of four.** Cairo pads each row of an A8 surface
#: out to a four-byte boundary, so a width of 1448 — the reference panel's, and
#: divisible by four — hides a stride bug completely. This one does not.
AWKWARD = Geometry(width_px=101, height_px=60, margin_px=5)


@pytest.fixture
def rasterizer() -> PangoRasterizer:
    return PangoRasterizer()


def a_layout(
    text: str | Line = "Cat Litter",
    *,
    size_px: int = 12,
    y_px: int = 5,
    surface: Geometry = AWKWARD,
    wrap_px: int | None = None,
) -> Layout:
    return Layout(
        surface=surface,
        blocks=(
            Block(
                runs=(Run(text),) if isinstance(text, str) else text,
                size_px=size_px,
                x_px=surface.margin_px,
                y_px=y_px,
                width_px=0,
                height_px=0,
                wrap_px=surface.text_width_px if wrap_px is None else wrap_px,
            ),
        ),
        dropped=(),
    )


def one(text: str) -> Line:
    """One unstyled run — what most of these tests are measuring."""
    return (Run(text),)


def _columns_with_ink(raster) -> set[int]:
    """Which x positions carry any dark pixel."""
    return {x for y in range(raster.height_px) for x in range(raster.width_px) if raster.pixels[y * raster.width_px + x] < 200}


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


class TestTheBlockIsDrawnAtTheWidthItWasMeasuredAt:
    """**The seam between the two tiers, pinned where only ink can pin it.**

    The layout tier narrows a line to the measure bound and records that width on
    the block; this tier must wrap to the same number. They disagreed once — layout
    measured at the bound while the renderer went on wrapping at the surface width
    — and every suite stayed green, because the layout-tier test can only prove the
    number was *stored* and the fake surface records layouts without drawing. A
    line measured as two rows and drawn as one runs past its bound, leaves every
    block below it a row lower than the ink, and lets the drop rule shed a line the
    panel would have held.

    A fixture whose `wrap_px` equals `surface.text_width_px` cannot tell the two
    expressions apart — they are the same number — so these pass a bound that is
    strictly narrower, which is the only arrangement where the mistake is visible.
    """

    #: Comfortably inside AWKWARD's 91px of text width, so the two expressions
    #: differ; wide enough that several characters still fit per row.
    NARROW = 30

    def test_no_ink_lands_right_of_the_blocks_own_wrap_width(self, rasterizer):
        raster = rasterizer.render(
            a_layout("wrapping at the bound rather than the panel", size_px=8, y_px=2, wrap_px=self.NARROW)
        )

        rightmost = max(_columns_with_ink(raster))
        assert rightmost <= AWKWARD.margin_px + self.NARROW, (
            f"ink reached x={rightmost}, past the {self.NARROW}px bound this block was measured at — "
            "the renderer is wrapping at the surface width instead"
        )

    def test_the_same_text_at_the_surface_width_does_reach_further(self, rasterizer):
        """The other half, and the one that keeps the test above honest: a
        renderer that drew nothing at all, or wrapped everything to a sliver,
        would satisfy it. This proves the bound is what moved the ink."""
        text, size = "wrapping at the bound rather than the panel", 8

        bounded = rasterizer.render(a_layout(text, size_px=size, y_px=2, wrap_px=self.NARROW))
        full = rasterizer.render(a_layout(text, size_px=size, y_px=2))

        assert max(_columns_with_ink(full)) > max(_columns_with_ink(bounded))


class TestMeasuringMovesInTheDirectionsTheLayoutTierRelieson:
    def test_a_size_in_pixels_is_a_size_in_pixels(self, rasterizer):
        """**The units, which nothing else here would catch.**

        Every size this product reasons about is in pixels: the panel's geometry,
        and the type sizes the layout tier is handed — which are themselves derived
        from a viewing distance in `panel/legibility.py`, so a units error here
        would silently undo an arithmetic chain built to be right about exactly
        this. Pango's ordinary
        `set_size` takes *points* and resolves them through an ambient
        resolution — 96 dpi by default — so the same number comes out a third
        larger, silently. Every relative assertion below passes either way, since
        both scale monotonically; only measuring against the requested number
        tells them apart.

        The bound is loose on purpose. A single line is one em plus the face's
        ascent and descent, which is about 1.15–1.25× the size for the sans faces
        this resolves to; going through points would put it near 1.55×.
        """
        measured = rasterizer.measure(one("Hg"), 40, 400)

        assert 40 <= measured.height_px < 56, (
            f"a line asked for at 40 px measured {measured.height_px} px — outside what a face's "
            "ascent and descent explain, which is what asking in points and getting 96 dpi looks like"
        )

    def test_bigger_type_measures_taller(self, rasterizer):
        small = rasterizer.measure(one("Cat Litter"), 12, 400)
        large = rasterizer.measure(one("Cat Litter"), 40, 400)

        assert large.height_px > small.height_px
        assert large.width_px > small.width_px

    def test_a_narrower_wrap_measures_taller(self, rasterizer):
        """The layout tier's drop rule is driven entirely by measured height, so a
        measurer that ignored the wrap width would report every label as fitting
        and the last lines would run off the panel."""
        wide = rasterizer.measure(one("A rather long museum title that has to wrap somewhere"), 12, 400)
        narrow = rasterizer.measure(one("A rather long museum title that has to wrap somewhere"), 12, 80)

        assert narrow.height_px > wide.height_px

    def test_a_line_that_fits_measures_as_one_row(self, rasterizer):
        """**`rows` is the only number in `Extent` that no fake can settle**, and
        three behaviours hang off it: the name ladder's wrap rung, `Layout.wrapped`,
        and the daemon's `label.name_wrapped` WARNING. Every other suite synthesises
        it arithmetically, so a `measure` that returned a constant 1 would leave all
        three silent with every test green — and the fault that produces is the one
        the 2026-08-13 sitting read off the wall: a name broken mid-phrase, drawn,
        and journalled as fine.
        """
        measured = rasterizer.measure(one("Katsushika"), 40, 4000)

        assert measured.rows == 1

    def test_a_line_that_wraps_measures_as_more_than_one_row(self, rasterizer):
        """The other half, and the direction that matters: the ladder is *taken*
        on this answer. The same text at a wrap width it cannot hold must come
        back as more rows than one, from Pango's own line count rather than from
        arithmetic over a nominal glyph width."""
        wide = rasterizer.measure(one("A rather long museum title that has to wrap somewhere"), 12, 400)
        narrow = rasterizer.measure(one("A rather long museum title that has to wrap somewhere"), 12, 80)

        assert wide.rows == 1
        assert narrow.rows > wide.rows

    def test_an_unbreakable_run_wraps_rather_than_running_off_the_edge(self, rasterizer):
        """A museum record carries accession strings and URLs with no space in
        them. Under Pango's word wrapping those are drawn straight past the right
        margin; the label has to break mid-word instead, because ugly beats
        unreadable."""
        measured = rasterizer.measure(one("A" * 200), 12, 80)

        assert measured.width_px <= 80


class TestTheStylingReachesTheType:
    """**The runs, asserted where only real type can settle them.**

    The tiers above can say a run carries `Weight.BOLD`; nothing there can say
    that anything got heavier. These are the tests that fail if the attribute
    list is built wrong, attached to the wrong layout, or silently dropped.
    """

    def test_a_bold_run_is_wider_than_the_same_characters_unstyled(self):
        rasterizer = PangoRasterizer()

        plain_run = rasterizer.measure(one("Katsushika"), 40, 4000)
        bold_run = rasterizer.measure((Run("Katsushika", weight=Weight.BOLD),), 40, 4000)

        assert bold_run.width_px > plain_run.width_px, "the weight attribute never reached the type"

    def test_an_italic_run_is_set_differently_from_an_upright_one(self, rasterizer):
        """Width is not the test here — an italic face need not be wider — so this
        asks whether the ink moved at all."""
        upright = rasterizer.render(a_layout(one("The Banquet"), size_px=20, y_px=2))
        italic = rasterizer.render(a_layout((Run("The Banquet", slant=Slant.ITALIC),), size_px=20, y_px=2))

        assert upright.pixels != italic.pixels, "the slant attribute never reached the type"

    def test_only_the_styled_run_is_affected(self, rasterizer):
        """**The claim the identification line rests on.** `KATSUSHIKA, Hokusai`
        is one line with one bold stretch; an attribute applied to the whole
        layout would look identical in every width assertion above and would set
        the given name bold too, which is the thing the weight exists to deny.

        **Both ends of the range are pinned, and the `both` comparison is what
        pins them.** Without it a renderer that ignored `start_index` and began
        every attribute at byte 0 passes: the leading case is unchanged, and the
        trailing case still differs from the unstyled one — it just differs by
        being *entirely* bold. The mutation sweep found exactly that gap, so the
        two one-run cases are each asserted to differ from the all-bold line as
        well as from the plain one.
        """

        def bold(*flags: bool):
            runs = (
                Run("AAAA", weight=Weight.BOLD if flags[0] else Weight.NORMAL),
                Run(" BBBB", weight=Weight.BOLD if flags[1] else Weight.NORMAL),
            )
            return rasterizer.render(a_layout(runs, size_px=20, y_px=2)).pixels

        leading, trailing, neither, both = bold(True, False), bold(False, True), bold(False, False), bold(True, True)

        assert leading != neither
        assert trailing != neither
        assert leading != trailing, "the weight landed on the whole line rather than on one run"
        assert leading != both, "the weight ran past the end of its run"
        assert trailing != both, "the weight began before the start of its run"

    def test_capitals_are_set_rather_than_merely_declared(self, rasterizer):
        upper = rasterizer.render(a_layout((Run("hokusai", case=Case.CAPITALS),), size_px=20, y_px=2))
        as_recorded = rasterizer.render(a_layout(one("hokusai"), size_px=20, y_px=2))

        assert upper.pixels != as_recorded.pixels
        assert upper.pixels == rasterizer.render(a_layout(one("HOKUSAI"), size_px=20, y_px=2)).pixels

    def test_a_style_over_text_that_is_not_ascii_covers_all_of_it(self):
        """**The byte-offset decision, and the only test that can catch it.**

        Pango's attribute indices are byte offsets into the UTF-8 the layout was
        set with. Counting characters instead is invisible on `O'Keeffe` and
        wrong on everything else — an en dash spends three bytes, a Japanese
        title three per glyph — and what it produces is a run of the wrong length
        set in the wrong style rather than an error anybody sees.

        Asserted against a reference that uses **no indices at all**: the same
        characters set italic through the font description, which is a wholly
        independent road to "all of this is italic". A character-counted end index
        italicises the first half of these accented letters and the two renders
        part company.
        """
        text = "ÉÉÉÉÉÉÉÉ"
        assert len(text.encode("utf-8")) == 2 * len(text), "this case stopped being one where bytes differ from characters"

        ours = PangoRasterizer().render(a_layout((Run(text, slant=Slant.ITALIC),), size_px=20, y_px=2))

        assert ours.pixels == _wholly_italic(text, size_px=20, y_px=2), "the style did not cover the whole run"


def _wholly_italic(text: str, *, size_px: int, y_px: int) -> bytes:
    """The same drawing, with the slant asked for on the font rather than a range.

    An oracle rather than a second implementation: it exists to answer "all of it
    is italic" without going anywhere near a byte index, which is the thing under
    test on the other side.
    """
    surface = cairo.ImageSurface(cairo.FORMAT_A8, AWKWARD.width_px, AWKWARD.height_px)
    context = cairo.Context(surface)
    layout = PangoCairo.create_layout(context)
    layout.set_text(text, -1)

    font = Pango.FontDescription()
    font.set_family("Sans")
    font.set_style(Pango.Style.ITALIC)
    font.set_absolute_size(size_px * Pango.SCALE)
    layout.set_font_description(font)
    layout.set_width(AWKWARD.text_width_px * Pango.SCALE)
    layout.set_wrap(Pango.WrapMode.WORD_CHAR)

    context.move_to(AWKWARD.margin_px, y_px)
    context.set_source_rgba(0, 0, 0, 1)
    PangoCairo.show_layout(context, layout)
    surface.flush()

    stride, width = surface.get_stride(), surface.get_width()
    data = bytes(surface.get_data())
    rows = (data[row * stride : row * stride + width] for row in range(surface.get_height()))
    return bytes(255 - coverage for row in rows for coverage in row)


class TestMuseumTextIsSetLiterallyAndNeverAsMarkup:
    def test_angle_brackets_are_drawn_rather_than_parsed(self, rasterizer):
        """The 2024 label interpolated description text into a markup string, so a
        title containing `<` produced mangled type or a parse failure. Set
        literally, the tags are characters and take room — which is exactly what
        distinguishes the two here."""
        plain = rasterizer.measure(one("Untitled"), 12, 400)
        tagged = rasterizer.measure(one("<i>Untitled</i>"), 12, 400)

        assert tagged.width_px > plain.width_px, "the markup was parsed away instead of being drawn"

    def test_an_unclosed_tag_is_text_rather_than_an_error(self, rasterizer):
        """Under `set_markup` this raises and takes the label with it."""
        assert rasterizer.render(a_layout("Piece <3 of 5")).pixels
