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

from display.panel import Geometry, lay_out
from display.panel.layout import (
    ARTIST_SIZE_PX,
    BODY_SIZE_PX,
    LEADING,
    MEASURE_EM,
    TITLE_SIZE_PX,
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


class TestTheHierarchy:
    def test_the_first_line_is_the_largest_and_the_second_is_next(self):
        layout = lay_out(("Chicago", "Georgia O'Keeffe", "American"), PANEL, measured)

        assert [block.size_px for block in layout.blocks] == [TITLE_SIZE_PX, ARTIST_SIZE_PX, BODY_SIZE_PX]

    def test_everything_after_the_artist_shares_the_body_size(self):
        layout = lay_out(("T", "A", "N", "D", "Y", "M", "X"), PANEL, measured)

        assert {block.size_px for block in layout.blocks[2:]} == {BODY_SIZE_PX}

    def test_the_text_is_carried_through_unchanged(self):
        layout = lay_out(("Cow's Skull with Calico Roses", "Georgia O'Keeffe"), PANEL, measured)

        assert [block.text for block in layout.blocks] == ["Cow's Skull with Calico Roses", "Georgia O'Keeffe"]


class TestPlacement:
    def test_it_starts_at_the_top_left_margin(self):
        layout = lay_out(("Silver Sun",), PANEL, measured)

        assert layout.blocks[0].x_px == PANEL.margin_px
        assert layout.blocks[0].y_px == PANEL.margin_px

    def test_every_block_sits_at_the_left_margin(self):
        layout = lay_out(("The Banquet", "Jan Steen", "Dutch"), PANEL, measured)

        assert {block.x_px for block in layout.blocks} == {PANEL.margin_px}

    def test_each_block_sits_below_the_one_before_it(self):
        layout = lay_out(("The Banquet", "Jan Steen", "Dutch"), PANEL, measured)

        tops = [block.y_px for block in layout.blocks]
        assert tops == sorted(tops)
        assert len(set(tops)) == 3, "two blocks were placed at the same height"

    def test_the_gap_between_blocks_is_proportional_to_the_upper_one(self):
        layout = lay_out(("The Banquet", "Jan Steen"), PANEL, measured)

        first, second = layout.blocks
        gap = second.y_px - (first.y_px + first.height_px)
        assert gap == round(TITLE_SIZE_PX * LEADING)

    def test_a_wrapped_line_is_given_the_room_it_actually_takes(self):
        """The next block must clear a two-row title, not a one-row one."""
        narrow = Geometry(width_px=300, height_px=1072, margin_px=20)
        long_title = "Triptych Window from the Coonley Playhouse, Riverside, Illinois"

        layout = lay_out((long_title, "Frank Lloyd Wright"), narrow, measured)

        title, artist = layout.blocks
        assert title.height_px > TITLE_SIZE_PX, "the title was not measured as wrapping"
        assert artist.y_px >= title.y_px + title.height_px


class TestWhatComesOffWhenItWillNotFit:
    def test_a_label_that_fits_drops_nothing(self):
        layout = lay_out(("The Banquet", "Jan Steen", "Dutch"), PANEL, measured)

        assert layout.dropped == ()

    @pytest.mark.parametrize(
        ("height", "kept"),
        [
            (300, ["The Banquet", "Jan Steen", "Dutch", "1626–1679", "Oil on canvas"]),
            (200, ["The Banquet", "Jan Steen", "Dutch", "1626–1679"]),
            (150, ["The Banquet", "Jan Steen"]),
            (120, ["The Banquet"]),
        ],
    )
    def test_the_least_identifying_lines_come_off_the_bottom(self, height: int, kept: list[str]):
        """Shrinking the surface peels lines off the end, never out of the middle.

        Stepped through four heights rather than asserted at one, because the
        property is the *ordering* — a rule that kept a prefix at one size and
        reordered at another would pass a single-height check.
        """
        lines = ("The Banquet", "Jan Steen", "Dutch", "1626–1679", "Oil on canvas")
        short = Geometry(width_px=1448, height_px=height, margin_px=20)

        layout = lay_out(lines, short, measured)

        assert [block.text for block in layout.blocks] == kept
        assert layout.dropped == lines[len(kept) :]

    def test_what_is_kept_stays_at_its_full_size(self):
        """The floor. Type that shrinks to fit has quietly stopped being an
        accessibility surface, and only the person who cannot read it finds out."""
        short = Geometry(width_px=1448, height_px=200, margin_px=20)

        layout = lay_out(("The Banquet", "Jan Steen", "Dutch", "Oil on canvas"), short, measured)

        assert layout.blocks[0].size_px == TITLE_SIZE_PX
        assert layout.blocks[1].size_px == ARTIST_SIZE_PX

    def test_nothing_placed_runs_past_the_bottom_margin(self):
        short = Geometry(width_px=1448, height_px=300, margin_px=20)

        layout = lay_out(("The Banquet", "Jan Steen", "Dutch", "1626–1679", "Oil on canvas"), short, measured)

        bottom = short.margin_px + short.text_height_px
        assert all(block.y_px + block.height_px <= bottom for block in layout.blocks)

    def test_the_title_is_kept_even_when_it_alone_overflows(self):
        """A surface too small for one title is a misconfigured device.

        Returning an empty label would present that as a work with no name, and
        hide a deployment error behind a blank panel.
        """
        tiny = Geometry(width_px=200, height_px=50, margin_px=5)

        layout = lay_out(("Triptych Window from the Coonley Playhouse", "Frank Lloyd Wright"), tiny, measured)

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
        layout = lay_out(("The Banquet", "Jan Steen"), surface, measured)

        assert layout.is_empty, why
        assert layout.dropped == ("The Banquet", "Jan Steen"), "what could not be placed was not reported"

    def test_a_label_with_no_lines_lays_out_to_nothing(self):
        layout = lay_out((), PANEL, measured)

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
        lay_out(("Chicago", "Georgia O'Keeffe", "American"), self.UNBOUNDED, self.recording(seen))

        body_wrap = seen[2][2]
        assert body_wrap == round(MEASURE_EM * BODY_SIZE_PX)
        assert body_wrap < self.UNBOUNDED.text_width_px, "the bound did not narrow anything"

    def test_the_measure_scales_with_the_type_size(self):
        """Ems, not pixels: a bound that did not scale would be one measure for
        the title and a different one, in characters, for everything else."""
        seen: list[tuple[str, int, int]] = []
        lay_out(("Chicago", "Georgia O'Keeffe", "American"), self.UNBOUNDED, self.recording(seen))

        title_wrap, artist_wrap, body_wrap = (line[2] for line in seen)
        assert title_wrap > artist_wrap > body_wrap

    def test_a_surface_narrower_than_the_measure_still_governs(self):
        """The bound narrows a line; it never widens one past the margins."""
        narrow = Geometry(width_px=400, height_px=1072, margin_px=40)
        seen: list[tuple[str, int, int]] = []
        lay_out(("The Bedroom", "Vincent van Gogh"), narrow, self.recording(seen))

        assert {line[2] for line in seen} == {narrow.text_width_px}

    def test_a_block_carries_the_width_it_was_measured_at(self):
        """**The seam between measuring and drawing.** A renderer that wrapped at
        the surface width would draw one row where two were measured, putting
        every block below it a row lower than the ink. The block carries the
        number so the two sides cannot disagree."""
        seen: list[tuple[str, int, int]] = []
        layout = lay_out(("Chicago", "Georgia O'Keeffe", "American"), PANEL, self.recording(seen))

        assert [block.wrap_px for block in layout.blocks] == [line[2] for line in seen]

    def test_the_bound_is_what_makes_a_long_line_wrap(self):
        """Behavioural rather than about the wrap number: the same line on the
        same surface occupies more rows with the bound than the panel alone
        would have given it."""
        long_line = "Colour woodblock print on paper, from the series Thirty-six Views of Mount Fuji"
        layout = lay_out(("T", "A", long_line), self.UNBOUNDED, measured)

        bounded = layout.blocks[2]
        unbounded = measured(long_line, BODY_SIZE_PX, self.UNBOUNDED.text_width_px)
        assert bounded.height_px > unbounded.height_px


class TestGeometryIsAParameter:
    def test_two_surfaces_of_different_size_get_different_layouts(self):
        """The norm, asserted: the deployment may hold panels of several sizes."""
        wide = Geometry(width_px=1448, height_px=1072, margin_px=40)
        narrow = Geometry(width_px=400, height_px=1072, margin_px=40)
        lines = ("Triptych Window from the Coonley Playhouse, Riverside, Illinois", "Frank Lloyd Wright")

        on_wide = lay_out(lines, wide, measured)
        on_narrow = lay_out(lines, narrow, measured)

        assert on_wide.blocks[1].y_px != on_narrow.blocks[1].y_px

    def test_the_usable_area_is_the_surface_less_its_margins(self):
        surface = Geometry(width_px=1448, height_px=1072, margin_px=40)

        assert surface.text_width_px == 1368
        assert surface.text_height_px == 992
