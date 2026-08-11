"""Where the label's text lands, and what comes off when it will not fit.

**Measurement is injected, so these test policy rather than a font.** The
measurer here is arithmetic the test chooses: a line is as wide as its character
count times the size, and as tall as the size times however many wrapped rows
that implies. That is not what Pango does, and it does not need to be — what is
under test is the ordering, the hierarchy, the drop rule and the floor, all of
which are this module's own decisions. The real measurer's job is to be right
about pixels, and it is exercised where it can actually run.
"""

import math

import pytest

from display.panel import Geometry, lay_out, type_scale_for
from display.panel.layout import (
    LEADING,
    MEASURE_EM,
    Extent,
)


def measured(text: str, size_px: int, wrap_px: int) -> Extent:
    """A predictable stand-in for a rasterizer's metrics.

    Each glyph is half its point size wide, lines wrap at the surface width, and
    a wrapped line is as tall as its rows. Deliberately not a real font: a test
    that depended on DejaVu's metrics would be testing DejaVu.
    """
    glyph = max(1, size_px // 2)
    per_row = max(1, wrap_px // glyph)
    rows = max(1, math.ceil(len(text) / per_row))
    return Extent(width_px=min(len(text) * glyph, wrap_px), height_px=rows * size_px)


PANEL = Geometry(width_px=1448, height_px=1072, margin_px=40)

#: The reference wall's sizes — a 6-inch 1448×1072 panel read from 7 feet, giving
#: a 130 px primary tier over a 92 px floor. **Derived here rather than written
#: down**, because a literal pair would be this file quietly re-asserting a
#: judgement that belongs to `legibility.py`; what these tests are about is what
#: the layout does with a scale, not what the scale is.
SCALE = type_scale_for(width_px=1448, height_px=1072, diagonal_inches=6.0, viewing_distance_inches=84.0)


class TestTheHierarchy:
    """**Two tiers, where there were three judged numbers.**

    The sizes used to be title / artist / everything-else, three constants with no
    stated relationship to each other or to any reader. They now come off a scale
    derived from how far away the panel is read, and that calibration settled
    exactly two readings worth setting type at — the rung between them was
    reported as the size that takes effort, so a middle tier would be aiming at a
    boundary somebody recorded as one to avoid.
    """

    def test_the_leading_line_gets_the_primary_tier(self):
        layout = lay_out(("Chicago", "Georgia O'Keeffe", "American"), PANEL, measured, SCALE)

        assert layout.blocks[0].size_px == SCALE.primary_px

    def test_everything_after_the_leading_line_sits_at_the_floor(self):
        layout = lay_out(("T", "A", "N", "D", "Y", "M", "X"), PANEL, measured, SCALE)

        assert {block.size_px for block in layout.blocks[1:]} == {SCALE.floor_px}

    def test_nothing_is_ever_set_below_the_floor(self):
        """The norm, asserted directly rather than inferred from the sizes above.

        This is the claim the whole label rests on — type that shrinks to fit has
        quietly converted an accessibility surface into a decorative one — and it
        must hold over the awkward shapes as well as the tidy one.
        """
        for surface in (PANEL, Geometry(width_px=400, height_px=300, margin_px=10)):
            layout = lay_out(("The Banquet", "Jan Steen", "Dutch", "Oil on canvas"), surface, measured, SCALE)

            assert all(block.size_px >= SCALE.floor_px for block in layout.blocks), surface

    def test_a_device_read_from_further_away_sets_larger_type(self):
        """The scale is a parameter, like the geometry: a second device with a
        different panel at a different distance gets its own answer, with nobody
        visiting it."""
        far = type_scale_for(width_px=1448, height_px=1072, diagonal_inches=6.0, viewing_distance_inches=168.0)

        near_layout = lay_out(("Chicago", "Georgia O'Keeffe"), PANEL, measured, SCALE)
        far_layout = lay_out(("Chicago", "Georgia O'Keeffe"), PANEL, measured, far)

        assert far_layout.blocks[0].size_px > near_layout.blocks[0].size_px

    def test_the_text_is_carried_through_unchanged(self):
        layout = lay_out(("Cow's Skull with Calico Roses", "Georgia O'Keeffe"), PANEL, measured, SCALE)

        assert [block.text for block in layout.blocks] == ["Cow's Skull with Calico Roses", "Georgia O'Keeffe"]


class TestPlacement:
    def test_it_starts_at_the_top_left_margin(self):
        layout = lay_out(("Silver Sun",), PANEL, measured, SCALE)

        assert layout.blocks[0].x_px == PANEL.margin_px
        assert layout.blocks[0].y_px == PANEL.margin_px

    def test_every_block_sits_at_the_left_margin(self):
        layout = lay_out(("The Banquet", "Jan Steen", "Dutch"), PANEL, measured, SCALE)

        assert {block.x_px for block in layout.blocks} == {PANEL.margin_px}

    def test_each_block_sits_below_the_one_before_it(self):
        layout = lay_out(("The Banquet", "Jan Steen", "Dutch"), PANEL, measured, SCALE)

        tops = [block.y_px for block in layout.blocks]
        assert tops == sorted(tops)
        assert len(set(tops)) == 3, "two blocks were placed at the same height"

    def test_the_gap_between_blocks_is_proportional_to_the_upper_one(self):
        layout = lay_out(("The Banquet", "Jan Steen"), PANEL, measured, SCALE)

        first, second = layout.blocks
        gap = second.y_px - (first.y_px + first.height_px)
        assert gap == round(SCALE.primary_px * LEADING)

    def test_a_wrapped_line_is_given_the_room_it_actually_takes(self):
        """The next block must clear a multi-row title, not a one-row one.

        On the reference panel rather than an artificially narrow one: at type
        derived from a 7-foot viewing distance a long title wraps three ways
        across the full panel, where the retired placeholder sizes needed a 300 px
        surface to wrap at all — and that surface now drops the second line
        instead of placing it, which would have tested the drop rule by accident.
        """
        long_title = "Triptych Window from the Coonley Playhouse, Riverside, Illinois"

        layout = lay_out((long_title, "Frank Lloyd Wright"), PANEL, measured, SCALE)

        title, artist = layout.blocks
        assert title.height_px > SCALE.primary_px, "the title was not measured as wrapping"
        assert artist.y_px >= title.y_px + title.height_px


class TestWhatComesOffWhenItWillNotFit:
    def test_a_label_that_fits_drops_nothing(self):
        layout = lay_out(("The Banquet", "Jan Steen", "Dutch"), PANEL, measured, SCALE)

        assert layout.dropped == ()

    LINES = ("The Banquet", "Jan Steen", "Dutch", "1626–1679", "Oil on canvas")

    @staticmethod
    def tall_enough_for(count: int, *, margin_px: int = 20) -> Geometry:
        """A surface exactly tall enough to hold the first `count` of `LINES`.

        **Taken from where the blocks actually land, not recomputed here.** These
        heights used to be four literals — 300, 200, 150, 120 — chosen against
        type sizes that were provisional placeholders, so every one of them was
        pinning a coincidence of constants nobody had measured. Now that the sizes
        derive from a viewing distance the operator can recalibrate, a literal
        height would break on the commit that changes a number it never named. A
        test that re-derived the stack arithmetic instead would agree with a
        broken implementation about where the bottom is, so the surface is sized
        from an unbounded layout's own answer.
        """
        unbounded = Geometry(width_px=1448, height_px=100_000, margin_px=margin_px)
        last = lay_out(TestWhatComesOffWhenItWillNotFit.LINES, unbounded, measured, SCALE).blocks[count - 1]
        return Geometry(width_px=1448, height_px=last.y_px + last.height_px + margin_px, margin_px=margin_px)

    @pytest.mark.parametrize("count", [5, 4, 3, 2, 1])
    def test_the_least_identifying_lines_come_off_the_bottom(self, count: int):
        """Shrinking the surface peels lines off the end, never out of the middle.

        Stepped through every count rather than asserted at one, because the
        property is the *ordering* — a rule that kept a prefix at one size and
        reordered at another would pass a single-height check.
        """
        layout = lay_out(self.LINES, self.tall_enough_for(count), measured, SCALE)

        assert [block.text for block in layout.blocks] == list(self.LINES[:count])
        assert layout.dropped == self.LINES[count:]

    def test_what_is_kept_stays_at_its_full_size(self):
        """The floor. Type that shrinks to fit has quietly stopped being an
        accessibility surface, and only the person who cannot read it finds out."""
        layout = lay_out(self.LINES, self.tall_enough_for(2), measured, SCALE)

        assert [block.size_px for block in layout.blocks] == [SCALE.primary_px, SCALE.floor_px]

    def test_nothing_placed_runs_past_the_bottom_margin(self):
        short = Geometry(width_px=1448, height_px=300, margin_px=20)

        layout = lay_out(("The Banquet", "Jan Steen", "Dutch", "1626–1679", "Oil on canvas"), short, measured, SCALE)

        bottom = short.margin_px + short.text_height_px
        assert all(block.y_px + block.height_px <= bottom for block in layout.blocks)

    def test_the_title_is_kept_even_when_it_alone_overflows(self):
        """A surface too small for one title is a misconfigured device.

        Returning an empty label would present that as a work with no name, and
        hide a deployment error behind a blank panel.
        """
        tiny = Geometry(width_px=200, height_px=50, margin_px=5)

        layout = lay_out(("Triptych Window from the Coonley Playhouse", "Frank Lloyd Wright"), tiny, measured, SCALE)

        assert [block.text for block in layout.blocks] == ["Triptych Window from the Coonley Playhouse"]
        assert layout.dropped == ("Frank Lloyd Wright",)


class TestDegenerateSurfaces:
    @pytest.mark.parametrize(
        ("surface", "why"),
        [
            (Geometry(width_px=40, height_px=1072, margin_px=40), "margins consume the whole width"),
            (Geometry(width_px=1448, height_px=80, margin_px=40), "margins consume the whole height"),
            (Geometry(width_px=0, height_px=0, margin_px=0), "no surface at all"),
        ],
    )
    def test_there_is_nowhere_to_put_anything_and_it_says_so(self, surface: Geometry, why: str):
        layout = lay_out(("The Banquet", "Jan Steen"), surface, measured, SCALE)

        assert layout.is_empty, why
        assert layout.dropped == ("The Banquet", "Jan Steen"), "what could not be placed was not reported"

    def test_a_label_with_no_lines_lays_out_to_nothing(self):
        layout = lay_out((), PANEL, measured, SCALE)

        assert layout.is_empty
        assert layout.dropped == ()


class TestTheMeasure:
    """The bound on how far a line runs before it wraps.

    A 1448px panel is far wider than continuous text stays comfortable to read
    across, so the wrap width handed to the measurer is the *narrower* of the
    surface and the measure — which is the only thing this tier can decide,
    since how many characters that turns out to be depends on the face.
    """

    #: A surface far wider than any measure, so the bound is always the narrower of
    #: the two. **Deliberately not `PANEL`**: whether the bound bites on the
    #: reference panel depends on the type sizes, and those are about to be derived
    #: from a viewing distance rather than fixed here. A test that asserted "the
    #: bound bites at 1448px" would pass today and fail on the commit that raises
    #: the sizes — pinning a coincidence of the current constants instead of the
    #: rule. What is under test is that a measure exists and narrows; where it
    #: happens to land on one device is that device's arithmetic.
    UNBOUNDED = Geometry(width_px=100_000, height_px=100_000, margin_px=40)

    @staticmethod
    def recording(seen: list[tuple[str, int, int]]):
        """A measurer that records the wrap width it was asked for."""

        def measure(text: str, size_px: int, wrap_px: int) -> Extent:
            seen.append((text, size_px, wrap_px))
            return measured(text, size_px, wrap_px)

        return measure

    def test_a_line_wraps_at_the_measure_rather_than_at_the_surface_edge(self):
        seen: list[tuple[str, int, int]] = []
        lay_out(("Chicago", "Georgia O'Keeffe", "American"), self.UNBOUNDED, self.recording(seen), SCALE)

        body_wrap = seen[2][2]
        assert body_wrap == round(MEASURE_EM * SCALE.floor_px)
        assert body_wrap < self.UNBOUNDED.text_width_px, "the bound did not narrow anything"

    def test_the_measure_scales_with_the_type_size(self):
        """Ems, not pixels: a bound that did not scale would be one measure for
        the leading line and a different one, in characters, for everything else.

        Asserted between the two tiers rather than across three lines, because the
        supporting lines now share a size — the middle tier the old assertion
        stepped through was one of the provisional constants this replaced.
        """
        seen: list[tuple[str, int, int]] = []
        lay_out(("Chicago", "Georgia O'Keeffe", "American"), self.UNBOUNDED, self.recording(seen), SCALE)

        leading_wrap, *supporting_wraps = (line[2] for line in seen)
        assert leading_wrap > supporting_wraps[0]
        assert len(set(supporting_wraps)) == 1, "lines at one size were bounded at two widths"

    def test_a_surface_narrower_than_the_measure_still_governs(self):
        """The bound narrows a line; it never widens one past the margins."""
        narrow = Geometry(width_px=400, height_px=1072, margin_px=40)
        seen: list[tuple[str, int, int]] = []
        lay_out(("The Bedroom", "Vincent van Gogh"), narrow, self.recording(seen), SCALE)

        assert {line[2] for line in seen} == {narrow.text_width_px}

    def test_a_block_carries_the_width_it_was_measured_at(self):
        """**The seam between measuring and drawing.** A renderer that wrapped at
        the surface width would draw one row where two were measured, putting
        every block below it a row lower than the ink. The block carries the
        number so the two sides cannot disagree."""
        seen: list[tuple[str, int, int]] = []
        layout = lay_out(("Chicago", "Georgia O'Keeffe", "American"), PANEL, self.recording(seen), SCALE)

        assert [block.wrap_px for block in layout.blocks] == [line[2] for line in seen]

    def test_the_bound_is_what_makes_a_long_line_wrap(self):
        """Behavioural rather than about the wrap number: the same line on the
        same surface occupies more rows with the bound than the panel alone
        would have given it."""
        long_line = "Colour woodblock print on paper, from the series Thirty-six Views of Mount Fuji"
        layout = lay_out(("T", "A", long_line), self.UNBOUNDED, measured, SCALE)

        bounded = layout.blocks[2]
        unbounded = measured(long_line, SCALE.floor_px, self.UNBOUNDED.text_width_px)
        assert bounded.height_px > unbounded.height_px


class TestGeometryIsAParameter:
    def test_two_surfaces_of_different_size_get_different_layouts(self):
        """The norm, asserted: the deployment may hold panels of several sizes."""
        wide = Geometry(width_px=1448, height_px=1072, margin_px=40)
        narrow = Geometry(width_px=400, height_px=1072, margin_px=40)
        lines = ("Triptych Window from the Coonley Playhouse, Riverside, Illinois", "Frank Lloyd Wright")

        on_wide = lay_out(lines, wide, measured, SCALE)
        on_narrow = lay_out(lines, narrow, measured, SCALE)

        # The first block rather than the second, because the second may not exist:
        # a narrow surface can wrap the title far enough to drop everything under
        # it, and this test is about geometry reaching the layout at all — not
        # about which lines survive, which is the drop rule's own test above.
        assert on_wide.blocks[0].height_px < on_narrow.blocks[0].height_px

    def test_the_usable_area_is_the_surface_less_its_margins(self):
        surface = Geometry(width_px=1448, height_px=1072, margin_px=40)

        assert surface.text_width_px == 1368
        assert surface.text_height_px == 992
