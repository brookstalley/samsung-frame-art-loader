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
from dataclasses import replace

import pytest

from display.panel import (
    Candidate,
    Case,
    Geometry,
    Line,
    Run,
    Tier,
    TypeScale,
    Weight,
    lay_out,
    plain,
    set_text,
    type_scale_for,
)
from display.panel.layout import (
    LEADING,
    MEASURE_EM,
    Extent,
    _compose,
)


def measured(line: Line, size_px: int, wrap_px: int) -> Extent:
    """A predictable stand-in for a rasterizer's metrics.

    Each glyph is half its point size wide, lines wrap at the surface width, and
    a wrapped line is as tall as its rows. Deliberately not a real font: a test
    that depended on DejaVu's metrics would be testing DejaVu.

    **Measures `set_text`, which is what a real rasterizer sets** — not the
    recorded text. The two differ wherever a run is capitalised, and a fake that
    reached past the transform would let the tier under test look right while the
    panel measured something else.
    """
    text = set_text(line)
    glyph = max(1, size_px // 2)
    per_row = max(1, wrap_px // glyph)
    rows = max(1, math.ceil(len(text) / per_row))
    return Extent(width_px=min(len(text) * glyph, wrap_px), height_px=rows * size_px, rows=rows)


def droppable(*texts: str) -> tuple[Candidate, ...]:
    """These strings as facts the label may drop, each on a line of its own.

    **Unstyled on purpose.** Every decision this module makes — the ordering, the
    two tiers, the drop rule, the measure — is about a line's *extent*, and asks
    nothing about how it is set; the styling reaches the measurer and stops there.
    Writing the styling into these fixtures would decorate them without testing
    anything, so the one test that is about styling reaching the measurer states
    it explicitly and the rest read as the text they are about.

    **Optional on purpose too.** These are the fixtures for everything the engine
    does that is *not* about the tier — placement, the measure, the geometry — and
    the optional tier is the one with no special powers, so a test using them is
    reading the plain behaviour rather than the exception to it.
    """
    return tuple(Candidate(runs=(Run(text),), tier=Tier.OPTIONAL) for text in texts)


def identifying(*texts: str) -> tuple[Candidate, ...]:
    """These strings as facts the label may not drop, each on a line of its own."""
    return tuple(Candidate(runs=(Run(text),), tier=Tier.MANDATORY) for text in texts)


def a_label(*texts: str) -> tuple[Candidate, ...]:
    """The shape every real record has: something identifying, then facts about it.

    **Used wherever the leading line's *size* is part of the assertion.** The
    identification tier is withheld from a leading line that identifies nothing
    (`_sizes_for`), so a fixture of nothing but optional facts is set entirely at
    the floor — correct, and not the label a test about placement, leading or the
    measure means to be reading.
    """
    first, *rest = texts
    return (*identifying(first), *droppable(*rest))


PANEL = Geometry(width_px=1448, height_px=1072, margin_px=40)

#: The reference wall's sizes — a 6-inch 1448×1072 panel read from 7 feet, giving
#: a 130 px primary tier over a 92 px floor. **Derived here rather than written
#: down**, because a literal pair would be this file quietly re-asserting a
#: judgement that belongs to `legibility.py`; what these tests are about is what
#: the layout does with a scale, not what the scale is.
SCALE = type_scale_for(width_px=1448, height_px=1072, diagonal_inches=6.0, viewing_distance_inches=84.0)


def exactly_holding(facts: tuple[Candidate, ...], count: int, *, width_px: int = 1448, margin_px: int = 40) -> Geometry:
    """A surface exactly tall enough for the first `count` lines these facts make.

    **Taken from where the blocks actually land, not computed here.** A literal
    height would pin a coincidence of the current type sizes — which derive from a
    viewing distance the operator can recalibrate — and a test that re-derived the
    stack arithmetic instead would agree with a broken implementation about where
    the bottom is. So the surface is sized from an unbounded layout's own answer.

    **Unbounded in height, so nothing is dropped and nothing shrinks — and every
    fact below the leading line is measured as optional, so nothing grows
    either.** Without that the surface would be sized for a label that had already
    spent its slack on type, and a caller asserting "the slack went to content"
    would be handed a surface where it could not have gone anywhere else.
    """
    unbounded = Geometry(width_px=width_px, height_px=1_000_000, margin_px=margin_px)
    ungrown = (facts[0], *(replace(fact, tier=Tier.OPTIONAL) for fact in facts[1:]))
    last = lay_out(ungrown, unbounded, measured, SCALE).blocks[count - 1]
    return Geometry(width_px=width_px, height_px=last.y_px + last.height_px + margin_px, margin_px=margin_px)


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
        layout = lay_out(a_label("Chicago", "Georgia O'Keeffe", "American"), PANEL, measured, SCALE)

        assert layout.blocks[0].size_px == SCALE.primary_px

    def test_everything_after_the_leading_line_sits_at_the_floor(self):
        layout = lay_out(droppable("T", "A", "N", "D", "Y", "M", "X"), PANEL, measured, SCALE)

        assert {block.size_px for block in layout.blocks[1:]} == {SCALE.floor_px}

    def test_nothing_is_ever_set_between_the_two_tiers(self):
        """**The squint boundary, guarded behaviourally.**

        The operator's ladder settled two readings worth setting type at, and the
        rung between them — 110 px, 10.5′ — was reported as the size that can be
        *made out with effort*. It is recorded in `accessibility-spec.md` as a
        boundary precisely so that nothing aims at it, so a hierarchy that grew a
        middle tier would be putting type at the one size somebody measured and
        rejected.

        **Asserted on the sizes the layout actually emits, not on `TypeScale`'s
        field list.** A structural check on the dataclass guards the shape rather
        than the decision, and it would fail when the mandatory tier adds its
        size — which is a *smaller* size, below the floor, not a middle one. This
        assertion stays true through that change and false through the one it
        exists to catch.
        """
        lines = droppable("The Banquet", "Jan Steen", "Dutch", "1626–1679", "Oil on canvas", "25 × 37 cm")
        for surface in (PANEL, Geometry(width_px=900, height_px=800, margin_px=30)):
            layout = lay_out(lines, surface, measured, SCALE)

            between = [b.size_px for b in layout.blocks if SCALE.floor_px < b.size_px < SCALE.primary_px]
            assert not between, f"type was set at the squint boundary on {surface}: {between}"

    def test_no_optional_fact_is_ever_set_below_the_floor(self):
        """The norm, asserted directly rather than inferred from the sizes above.

        This is the claim the whole label rests on — type that shrinks to fit has
        quietly converted an accessibility surface into a decorative one — and it
        must hold over the awkward shapes as well as the tidy one.

        **Narrowed from "nothing" to "nothing optional" by the operator's ruling
        of 2026-08-11, and that is a contract change rather than a weakened
        test.** The flat rule collided with itself: a long title at the floor can
        overflow a surface, and nothing said whether "the title is never dropped"
        or "nothing is set below the floor" yielded. The ruling split the content
        instead of picking a winner, so this half is asserted here and the other
        half — the facts that identify the work, which shrink and are reported for
        it — is asserted in `TestTheFactsThatIdentifyTheWorkShrinkInstead`. Every
        fact here is optional, which is what makes the assertion unconditional.
        """
        for surface in (PANEL, Geometry(width_px=400, height_px=300, margin_px=10)):
            layout = lay_out(droppable("The Banquet", "Jan Steen", "Dutch", "Oil on canvas"), surface, measured, SCALE)

            assert all(block.size_px >= SCALE.floor_px for block in layout.blocks), surface
            assert layout.shrunk == (), "an optional fact was squeezed where it should have been dropped"

    def test_a_device_read_from_further_away_sets_larger_type(self):
        """The scale is a parameter, like the geometry: a second device with a
        different panel at a different distance gets its own answer, with nobody
        visiting it."""
        far = type_scale_for(width_px=1448, height_px=1072, diagonal_inches=6.0, viewing_distance_inches=168.0)

        near_layout = lay_out(droppable("Chicago", "Georgia O'Keeffe"), PANEL, measured, SCALE)
        far_layout = lay_out(droppable("Chicago", "Georgia O'Keeffe"), PANEL, measured, far)

        assert far_layout.blocks[0].size_px > near_layout.blocks[0].size_px

    def test_the_text_is_carried_through_unchanged(self):
        layout = lay_out(droppable("Cow's Skull with Calico Roses", "Georgia O'Keeffe"), PANEL, measured, SCALE)

        assert [block.text for block in layout.blocks] == ["Cow's Skull with Calico Roses", "Georgia O'Keeffe"]


class TestPlacement:
    def test_it_starts_at_the_top_left_margin(self):
        layout = lay_out(droppable("Silver Sun"), PANEL, measured, SCALE)

        assert layout.blocks[0].x_px == PANEL.margin_px
        assert layout.blocks[0].y_px == PANEL.margin_px

    def test_every_block_sits_at_the_left_margin(self):
        layout = lay_out(droppable("The Banquet", "Jan Steen", "Dutch"), PANEL, measured, SCALE)

        assert {block.x_px for block in layout.blocks} == {PANEL.margin_px}

    def test_each_block_sits_below_the_one_before_it(self):
        layout = lay_out(droppable("The Banquet", "Jan Steen", "Dutch"), PANEL, measured, SCALE)

        tops = [block.y_px for block in layout.blocks]
        assert tops == sorted(tops)
        assert len(set(tops)) == 3, "two blocks were placed at the same height"

    def test_the_gap_between_blocks_is_proportional_to_the_upper_one(self):
        layout = lay_out(a_label("The Banquet", "Jan Steen"), PANEL, measured, SCALE)

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

        layout = lay_out(droppable(long_title, "Frank Lloyd Wright"), PANEL, measured, SCALE)

        # Named for position rather than for field: this tier is handed strings
        # and never a record, and the label's own ordering has since put the
        # artist first — which would make `title, artist` here describe a label
        # the product no longer produces while testing something else entirely.
        leading, following = layout.blocks
        assert leading.height_px > SCALE.primary_px, "the leading line was not measured as wrapping"
        assert following.y_px >= leading.y_px + leading.height_px


class TestWhatComesOffWhenItWillNotFit:
    def test_a_label_that_fits_drops_nothing(self):
        layout = lay_out(droppable("The Banquet", "Jan Steen", "Dutch"), PANEL, measured, SCALE)

        assert layout.dropped == ()

    LINES = ("The Banquet", "Jan Steen", "Dutch", "1626–1679", "Oil on canvas")

    #: The same lines with the leading one identifying the work, which is the shape
    #: a real record has — needed wherever the assertion names a tier.
    @staticmethod
    def as_a_label() -> tuple[Candidate, ...]:
        return a_label(*TestWhatComesOffWhenItWillNotFit.LINES)

    @staticmethod
    def tall_enough_for(count: int, *, margin_px: int = 20, facts: tuple[Candidate, ...] | None = None) -> Geometry:
        """A surface exactly tall enough to hold the first `count` of `LINES`.

        `facts` is the set being sized for, and defaults to the all-optional one
        most of these tests use. **A caller whose label leads with an identifying
        fact must pass it**, because that line is set at the identification tier
        and a surface measured against the floor-height version is a different
        surface — which is not a subtlety worth rediscovering from a failure two
        assertions later.

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
        chosen = facts if facts is not None else droppable(*TestWhatComesOffWhenItWillNotFit.LINES)
        last = lay_out(chosen, unbounded, measured, SCALE).blocks[count - 1]
        return Geometry(width_px=1448, height_px=last.y_px + last.height_px + margin_px, margin_px=margin_px)

    @pytest.mark.parametrize("count", [5, 4, 3, 2, 1])
    def test_the_least_identifying_lines_come_off_the_bottom(self, count: int):
        """Shrinking the surface peels lines off the end, never out of the middle.

        Stepped through every count rather than asserted at one, because the
        property is the *ordering* — a rule that kept a prefix at one size and
        reordered at another would pass a single-height check.
        """
        layout = lay_out(droppable(*self.LINES), self.tall_enough_for(count), measured, SCALE)

        assert [block.text for block in layout.blocks] == list(self.LINES[:count])
        assert layout.dropped == self.LINES[count:]

    def test_what_is_kept_stays_at_its_full_size(self):
        """The floor. Type that shrinks to fit has quietly stopped being an
        accessibility surface, and only the person who cannot read it finds out."""
        facts = self.as_a_label()
        layout = lay_out(facts, self.tall_enough_for(2, facts=facts), measured, SCALE)

        assert [block.size_px for block in layout.blocks] == [SCALE.primary_px, SCALE.floor_px]

    def test_a_dropped_line_is_reported_as_it_was_recorded(self):
        """**The one place a styled line becomes text again**, and it goes to a
        journal rather than to a panel.

        `label.truncated` is the only signal that a device's surface is too small
        for the corpus, and it is read by a person looking at a log — so a family
        name arrives there spelled as the catalogue holds it. A journal shouting
        `KATSUSHIKA` would be carrying a decision about type at 7 feet into a file
        where it means nothing, and the same conversion is what keeps the line
        greppable against the catalogue it came from.
        """
        tiny = Geometry(width_px=200, height_px=50, margin_px=5)
        surname = Candidate(
            runs=(Run("Katsushika", weight=Weight.BOLD, case=Case.CAPITALS), Run(", "), Run("Hokusai")),
            tier=Tier.OPTIONAL,
        )

        layout = lay_out((*droppable("Silver Sun"), surname), tiny, measured, SCALE)

        assert layout.dropped == ("Silver Sun", "Katsushika, Hokusai")

    def test_nothing_placed_runs_past_the_bottom_margin(self):
        short = Geometry(width_px=1448, height_px=300, margin_px=20)

        layout = lay_out(droppable("The Banquet", "Jan Steen", "Dutch", "1626–1679", "Oil on canvas"), short, measured, SCALE)

        bottom = short.margin_px + short.text_height_px
        assert all(block.y_px + block.height_px <= bottom for block in layout.blocks)

    def test_the_title_shrinks_rather_than_coming_off_when_it_alone_overflows(self):
        """**The half of the ruling that had no guard at all until now.**

        A surface too small for one title used to drop it, because the engine
        dropped from the end at a fixed size and nothing knew the title was
        different from a medium. The operator's ruling reversed that for the facts
        that identify the work: an unreadably small title is still a title
        somebody can walk closer to read, and a picture beside a label that does
        not name it is the failure worth avoiding.

        Returning an empty label would present a misconfigured device as a work
        with no name, and hide a deployment error behind a blank panel.
        """
        tiny = Geometry(width_px=200, height_px=50, margin_px=5)
        title = "Triptych Window from the Coonley Playhouse"

        layout = lay_out((*identifying(title), *droppable("Frank Lloyd Wright")), tiny, measured, SCALE)

        assert [block.text for block in layout.blocks] == [title]
        assert layout.dropped == ("Frank Lloyd Wright",)
        assert layout.blocks[0].size_px < SCALE.floor_px, "the title kept its size on a surface that cannot hold it"
        assert layout.shrunk == (title,), "type went below the floor and nothing said so"


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
        layout = lay_out(droppable("The Banquet", "Jan Steen"), surface, measured, SCALE)

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

        def measure(line: Line, size_px: int, wrap_px: int) -> Extent:
            seen.append((plain(line), size_px, wrap_px))
            return measured(line, size_px, wrap_px)

        return measure

    def test_a_line_wraps_at_the_measure_rather_than_at_the_surface_edge(self):
        layout = lay_out(droppable("Chicago", "Georgia O'Keeffe", "American"), self.UNBOUNDED, measured, SCALE)

        body_wrap = layout.blocks[2].wrap_px
        assert body_wrap == round(MEASURE_EM * SCALE.floor_px)
        assert body_wrap < self.UNBOUNDED.text_width_px, "the bound did not narrow anything"

    def test_the_measure_scales_with_the_type_size(self):
        """Ems, not pixels: a bound that did not scale would be one measure for
        the leading line and a different one, in characters, for everything else.

        Asserted between the two tiers rather than across three lines, because the
        supporting lines now share a size — the middle tier the old assertion
        stepped through was one of the provisional constants this replaced.
        """
        layout = lay_out(a_label("Chicago", "Georgia O'Keeffe", "American"), self.UNBOUNDED, measured, SCALE)

        leading_wrap, *supporting_wraps = (block.wrap_px for block in layout.blocks)
        assert leading_wrap > supporting_wraps[0]
        assert len(set(supporting_wraps)) == 1, "lines at one size were bounded at two widths"

    def test_a_surface_narrower_than_the_measure_still_governs(self):
        """The bound narrows a line; it never widens one past the margins."""
        narrow = Geometry(width_px=400, height_px=1072, margin_px=40)
        seen: list[tuple[str, int, int]] = []
        lay_out(droppable("The Bedroom", "Vincent van Gogh"), narrow, self.recording(seen), SCALE)

        assert {line[2] for line in seen} == {narrow.text_width_px}

    def test_the_measurer_is_given_the_runs_and_not_their_text(self):
        """**The half of the seam that only styling can break.**

        Bold capitals are wider than the letters they replace, so a tier that
        measured a line's plain text while the renderer set its runs would
        under-report the one line the label leads with — and the drop rule, which
        is driven entirely by measured height, would keep a line that runs off the
        bottom of the panel. Nothing catches that except somebody standing in
        front of it.

        Asserted by handing in a line whose styled and recorded forms differ, and
        checking which one the measurer saw.
        """
        seen: list[Line] = []

        def measure(line: Line, size_px: int, wrap_px: int) -> Extent:
            seen.append(line)
            return measured(line, size_px, wrap_px)

        surname = Candidate(runs=(Run("Hokusai", case=Case.CAPITALS),), tier=Tier.MANDATORY)
        lay_out((surname,), PANEL, measure, SCALE)

        assert set(seen) == {(Run("Hokusai", case=Case.CAPITALS),)}
        assert set_text(seen[0]) == "HOKUSAI", "the measurer was handed the recorded text, not what will be set"

    def test_a_block_carries_the_width_it_was_measured_at(self):
        """**The seam between measuring and drawing.** A renderer that wrapped at
        the surface width would draw one row where two were measured, putting
        every block below it a row lower than the ink. The block carries the
        number so the two sides cannot disagree.

        **Asserted against every width the measurer was asked for, not against the
        order it was asked in.** The fill model measures a trial arrangement per
        fact it considers admitting, so the recording is far longer than the
        label; what has to hold is that no block carries a width nothing was ever
        measured at.
        """
        seen: list[tuple[str, int, int]] = []
        layout = lay_out(droppable("Chicago", "Georgia O'Keeffe", "American"), PANEL, self.recording(seen), SCALE)

        asked = {(text, wrap) for text, _, wrap in seen}
        assert {(block.text, block.wrap_px) for block in layout.blocks} <= asked

    def test_the_bound_is_what_makes_a_long_line_wrap(self):
        """Behavioural rather than about the wrap number: the same line on the
        same surface occupies more rows with the bound than the panel alone
        would have given it."""
        long_line = "Colour woodblock print on paper, from the series Thirty-six Views of Mount Fuji"
        layout = lay_out(droppable("T", "A", long_line), self.UNBOUNDED, measured, SCALE)

        bounded = layout.blocks[2]
        unbounded = measured((Run(long_line),), SCALE.floor_px, self.UNBOUNDED.text_width_px)
        assert bounded.height_px > unbounded.height_px


class TestGeometryIsAParameter:
    def test_two_surfaces_of_different_size_get_different_layouts(self):
        """The norm, asserted: the deployment may hold panels of several sizes."""
        wide = Geometry(width_px=1448, height_px=1072, margin_px=40)
        narrow = Geometry(width_px=400, height_px=1072, margin_px=40)
        lines = a_label("Triptych Window from the Coonley Playhouse, Riverside, Illinois", "Frank Lloyd Wright")

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


class TestTheFactsThatIdentifyTheWorkShrinkInstead:
    """The other half of the 2026-08-11 ruling, and the half that had no guard.

    The flat rule — nothing shrinks, content drops — collided with itself on a
    title too long for its surface, and the operator split the content rather than
    picking a winner. What a label is *for* is saying who made the work and what
    it is called; a name too small to read at 7 feet can still be read by somebody
    who steps closer, and a name that is not there cannot.

    **The reporting is the condition the ruling rests on, not a nicety.** The
    reason the flat rule existed is that illegible type fails invisibly, so every
    test here that asserts a shrink also asserts that something said so.
    """

    #: Tall enough for one line of the identification tier and nothing more.
    CRAMPED = Geometry(width_px=600, height_px=200, margin_px=10)

    def test_a_mandatory_fact_is_never_dropped_however_small_the_surface(self):
        for height in (30, 60, 120, 300):
            surface = Geometry(width_px=300, height_px=height, margin_px=5)

            layout = lay_out(identifying("Katsushika", "Under the Well of the Great Wave"), surface, measured, SCALE)

            assert [b.text for b in layout.blocks] == ["Katsushika", "Under the Well of the Great Wave"], height
            assert layout.dropped == (), f"an identifying fact came off a {height} px surface"

    def test_it_shrinks_only_as_far_as_it_has_to(self):
        """**The step matters, and this is what pins it.** An engine that halved
        the type on the first attempt would fit the label and set it far smaller
        than the surface required — which looks like the rule working and is the
        failure the rule exists to prevent, one size down."""
        roomier = Geometry(width_px=600, height_px=260, margin_px=10)
        facts = identifying("Kandinsky", "Painting with Green Center", "Improvisation No. 30")

        tight = lay_out(facts, self.CRAMPED, measured, SCALE)
        loose = lay_out(facts, roomier, measured, SCALE)

        assert loose.blocks[0].size_px > tight.blocks[0].size_px
        assert all(b.size_px <= SCALE.primary_px for b in loose.blocks), "it grew past the tier it started at"

    def test_every_line_shrinks_by_the_same_factor_so_the_hierarchy_survives(self):
        """A label whose leading line kept its size while its title collapsed
        would be saying one of the two identifies the work and the other does not.

        **Asserted against the tiers rather than against an unbounded layout**,
        because an unbounded surface has slack and spends it: the baseline would
        be a label that had *grown*, and the ratios measured against it would be
        about growth rather than about the shrink.
        """
        facts = identifying("Kandinsky", "Painting with Green Center", "Improvisation No. 30")

        layout = lay_out(facts, self.CRAMPED, measured, SCALE)

        assert layout.shrunk, "this surface was meant to force a shrink"
        leading, *supporting = (block.size_px for block in layout.blocks)
        assert len(set(supporting)) == 1, f"lines sharing a tier shrank differently: {supporting}"
        assert abs(leading / supporting[0] - SCALE.primary_px / SCALE.floor_px) < 0.05, "the hierarchy did not survive"

    def test_the_shrink_is_reported_exactly_like_a_drop(self):
        """The condition the whole exception rests on. A panel routinely setting
        names below the floor is a misconfigured device, and nobody discovers that
        by eye at 7 feet."""
        layout = lay_out(identifying("Kandinsky", "Painting with Green Center"), self.CRAMPED, measured, SCALE)

        below = [block.text for block in layout.blocks if block.size_px < SCALE.floor_px]
        assert below, "nothing went below the floor, so this test is not exercising the report"
        assert list(layout.shrunk) == below

    def test_a_label_that_fits_reports_no_shrink(self):
        layout = lay_out((*identifying("Steen", "The Banquet"), *droppable("Dutch")), PANEL, measured, SCALE)

        assert layout.shrunk == ()

    def test_a_shrunk_name_is_reported_as_the_catalogue_spells_it(self):
        """`label.shrunk` is read by a person looking at a log, like `dropped` —
        so the capitals that belong to type at 7 feet stay on the panel."""
        surname = Candidate(
            runs=(Run("Katsushika", weight=Weight.BOLD, case=Case.CAPITALS),),
            tier=Tier.MANDATORY,
        )
        tiny = Geometry(width_px=120, height_px=40, margin_px=2)

        layout = lay_out((surname,), tiny, measured, SCALE)

        assert layout.shrunk == ("Katsushika",)

    def test_nothing_optional_is_admitted_onto_a_label_that_had_to_shrink(self):
        """A surface with no room for the artist's name at the floor has none to
        offer a medium — and admitting one *at* the floor would set an optional
        fact larger than the mandatory one it is subordinate to."""
        facts = (*identifying("Kandinsky", "Painting with Green Center"), *droppable("Oil on canvas"))

        layout = lay_out(facts, self.CRAMPED, measured, SCALE)

        assert layout.shrunk, "this surface was meant to force a shrink"
        assert "Oil on canvas" in layout.dropped
        assert all(block.size_px < SCALE.floor_px for block in layout.blocks)


class TestTheNameLadder:
    """One line, then two, then smaller — each step only when the one before fails.

    The name block gives up its line before it gives up its size, and gives up its
    size last of all. Stated as a preference with fallbacks rather than as a number
    of lines: an engine told "two lines" would break `ANDERS, Joseph` for every
    short name on the wall, and one told "one line" would shrink a long one to fit
    a break it could have taken for free.
    """

    @staticmethod
    def name(family: str, given: str, *rest: str) -> tuple[Candidate, ...]:
        """A tombstone: the name on the leading line, the biography beneath it.

        **`rest` is one candidate, not one each**, because that is what
        `LabelText` composes: nationality and dates are a single clause and they
        take a line of their own, so a fixture that left them joinable to the name
        would exercise an arrangement the product stopped producing on 2026-08-13.

        **Only the two name parts set `names_the_maker`**, which is what makes
        this a name fixture rather than a pair of undroppable strings — the
        ladder, and the report that fires when it runs out of rungs, are about
        names and not about undroppability.
        """
        return (
            Candidate(runs=(Run(family),), tier=Tier.MANDATORY, names_the_maker=True),
            Candidate(runs=(Run(given),), tier=Tier.MANDATORY, continues_line=(Run(", "),), names_the_maker=True),
            *((Candidate(runs=(Run(", ".join(rest)),), tier=Tier.OPTIONAL),) if rest else ()),
        )

    def test_a_short_name_keeps_its_one_line(self):
        """Rung one, and the reason the ladder is a preference: `ANDERS, Joseph`
        fits, so breaking it would spend a line box on nothing."""
        layout = lay_out(self.name("Anders", "Joseph"), PANEL, measured, SCALE)

        assert [block.text for block in layout.blocks] == ["Anders, Joseph"]

    #: The record whose nationality is a birthplace clause rather than a demonym —
    #: 48 characters, the longest on the wall, and the reason this line is the one
    #: that will not hold. Real, and recorded in `accessibility-spec.md` as one of
    #: the two records where the tombstone convention does not hold.
    KANDINSKY = ("Kandinsky", "Vasily", "Born Moscow (formerly Russian Empire, now Russia)", "1866–1944")

    def test_a_name_that_will_not_hold_takes_a_second_line_before_it_shrinks(self):
        """Rung two, taken because the *name* will not hold on one line.

        **The surface is narrow rather than short, and that is the change of
        2026-08-13.** The biography left the name's line, so what decides the rung
        is now the width the name itself needs: on this wall's own panel
        `Kandinsky, Vasily` fits, and only a narrower device breaks it. A short
        surface no longer reaches rung two at all — it drops optional facts
        instead, which is the fill rule doing its job one layer up.

        Both parts of the name keep the identification tier: the given name is
        part of the name, and setting it at the floor would present it as
        biography.
        """
        narrow = Geometry(width_px=1000, height_px=900, margin_px=40)

        layout = lay_out(self.name(*self.KANDINSKY), narrow, measured, SCALE)

        assert [block.text for block in layout.blocks] == [
            "Kandinsky",
            "Vasily",
            "Born Moscow (formerly Russian Empire, now Russia), 1866–1944",
        ]
        assert layout.blocks[0].size_px == SCALE.primary_px
        assert layout.blocks[1].size_px == SCALE.primary_px, "the given name is name, not biography"
        assert layout.blocks[2].size_px == SCALE.floor_px
        assert layout.shrunk == (), "it gave up its size before it had given up its line"

    def test_the_biography_is_not_grown_to_the_identification_tier_but_the_given_name_is(self):
        """**Where "may not be dropped" and "identifies the work" come apart.**

        **This test's expectation inverted on 2026-08-13, and the principle under
        it did not.** It used to assert that rung two's tail stayed at the floor,
        because that tail was `Given, Nationality, dates` — a line carrying
        optional facts, which at the identification tier would claim a work is
        identified by when its maker died. The biography now takes its own line,
        so rung two's tail is the given name and nothing else: purely identifying,
        and demoting it would present a person's name as biography.

        So the line that must not be grown is the biography, and the line that
        must be is the given name. Growth asks `wholly_identifying` rather than
        `mandatory`, which is exactly the distinction that gets both right — and
        it is still the one place the two questions differ, which is why this is a
        named test rather than a property.

        **A narrow, tall surface is what makes it reachable, and it is not a
        contrivance.** The break is chosen because the *name* will not hold at this
        width, and the height is what leaves slack to grow into; a cramped surface
        reaches rung two with nothing left. Such a surface is the mat strip beside
        an artwork rather than this wall's panel, and `architecture.md`
        § Direction names that device.
        """
        narrow_and_tall = Geometry(width_px=1000, height_px=1300, margin_px=40)

        layout = lay_out(self.name(*self.KANDINSKY), narrow_and_tall, measured, SCALE)

        assert [block.text for block in layout.blocks] == [
            "Kandinsky",
            "Vasily",
            "Born Moscow (formerly Russian Empire, now Russia), 1866–1944",
        ]
        assert layout.blocks[0].size_px == SCALE.primary_px
        assert layout.blocks[1].size_px == SCALE.primary_px, "the given name was set as biography"
        assert layout.blocks[2].size_px == SCALE.floor_px, "an optional fact was set at the identification tier"

    def test_nothing_shrinks_on_a_surface_where_the_break_alone_would_have_done(self):
        """**The ladder's ordering, asserted as an ordering rather than at one
        surface.** Rung three is only reached when rung two has failed, so across
        every height in the range there must be no case where the engine gave up
        size while a two-line arrangement at the proper tiers would have fitted.

        The two-line arrangement is computed here with the same measurer the
        engine was handed, so this compares the engine's decision against the
        alternative it had rather than against a remembered number.

        **The name alone, with no optional tail**, so that what is being compared
        is the ladder rather than the fill: a cramped surface drops the nationality
        and the dates long before it shrinks anything, and a tail still in the
        comparison would be measuring an arrangement the engine had already
        stopped considering.
        """
        facts = self.name("Toulouse-Lautrec", "Henri")

        shrank_somewhere = False
        for height in range(120, 620, 20):
            surface = Geometry(width_px=1448, height_px=height, margin_px=40)
            layout = lay_out(facts, surface, measured, SCALE)
            if not layout.shrunk:
                continue
            shrank_somewhere = True
            assert (
                self.broken_height("Toulouse-Lautrec", "Henri", surface) > surface.margin_px + surface.text_height_px
            ), f"it shrank at {height} px although two lines at full size would have fitted"
        assert shrank_somewhere, "no height in this range forced a shrink, so the ordering was never exercised"

    @staticmethod
    def broken_height(family: str, given: str, surface: Geometry) -> int:
        """Where rung two's last line would end: the family name alone, then the rest."""
        head = measured((Run(family),), SCALE.primary_px, min(surface.text_width_px, round(MEASURE_EM * SCALE.primary_px)))
        tail = measured((Run(given),), SCALE.floor_px, min(surface.text_width_px, round(MEASURE_EM * SCALE.floor_px)))
        return surface.margin_px + head.height_px + round(SCALE.primary_px * LEADING) + tail.height_px

    def test_once_a_shrink_is_unavoidable_the_arrangement_that_stays_largest_wins(self):
        """**Rung two exists to avoid a reduction; once one is unavoidable it has
        failed at its job**, and the question reverts to which arrangement stays
        most legible. Giving up size last of all is the ordering the whole ladder
        is, so the engine shrinks both and keeps the larger answer rather than
        shrinking whichever was shorter at full size.

        **Narrow rather than short, because that is where the two diverge.** On a
        wide surface the name wraps to two rows at most and breaking it costs a
        line box for nothing; on a narrow one — a device drawing its label into a
        strip beside the artwork, which `architecture.md` § Direction names — the
        joined line wraps far enough that the break wins by several sizes.

        Compared against the same name handed in pre-joined, which is the
        arrangement with no break available: the ladder must do at least as well
        as the thing it has more options than.
        """
        narrow = Geometry(width_px=300, height_px=700, margin_px=10)
        family, given = "Toulouse-Lautrec", "Henri Marie Raymond"

        laddered = lay_out(self.name(family, given), narrow, measured, SCALE)
        no_break_available = lay_out(
            (Candidate(runs=(Run(f"{family}, {given}"),), tier=Tier.MANDATORY),), narrow, measured, SCALE
        )

        assert laddered.shrunk, "this surface was meant to force a shrink"
        assert no_break_available.shrunk
        assert laddered.blocks[0].size_px > no_break_available.blocks[0].size_px

    def test_a_name_the_breaker_split_is_reported_rather_than_drawn_in_silence(self):
        """**The fault a person found by eye, given the channel it never had.**

        The ladder prevents this and normally does, but it cannot always win: on a
        surface where no rung fits, a wrapped name still beats giving up the
        family name's size, and `_arrange` takes that trade deliberately. What
        made the trade invisible is that nothing said so — the type is at its
        tier, so `shrunk` is empty; every fact is placed, so `dropped` is empty;
        and the daemon logs that the label was drawn.

        A wrapped name is a fact about the *device* — too narrow a panel, or type
        calibrated for a reader further away than this one — so it belongs beside
        the shrink report, which exists for exactly that reason.
        """
        no_rung_fits = Geometry(width_px=300, height_px=250, margin_px=10)

        layout = lay_out(self.name("Toulouse-Lautrec", "Henri Marie Raymond"), no_rung_fits, measured, SCALE)

        assert layout.blocks[0].rows > 1, "this surface was meant to force a wrap"
        assert layout.wrapped == (layout.blocks[0].text,), "a name broken across rows was reported by nothing"

    def test_an_ordinary_title_wrapping_is_not_reported_as_a_broken_name(self):
        """The measure exists so that long lines wrap; only the leading line
        wrapping is the name broken where nothing chose to break it. A report that
        fired on every title would be one nobody reads."""
        layout = lay_out(
            (*self.name("Anders", "Joseph"), *droppable("A title long enough that it certainly has to wrap somewhere")),
            PANEL,
            measured,
            SCALE,
        )

        assert any(block.rows > 1 for block in layout.blocks[1:]), "no line below the leading one wrapped"
        assert layout.wrapped == ()

    def test_a_wrapping_title_leading_a_makerless_record_is_not_a_broken_name(self):
        """**The same claim as the test above, at the position that defeated its
        first implementation.** That one puts the long title *below* a name, so a
        gate reading "the leading line may not be dropped" passes it for the wrong
        reason. Here nothing names a maker, so the title itself leads — and it is
        mandatory, which is precisely what the old gate asked about.

        A record like this is one the product should not be able to create: a
        museum with no individual maker records the culture in the maker slot
        (`museum-label-findings.md`), so the label leads with that. It is
        reachable anyway — the Met leaves both its maker fields empty — and a
        WARNING channel this plane's observability calls load-bearing may not be
        diluted by the case that gets there.
        """
        layout = lay_out(
            identifying("A descriptive object name long enough that it certainly has to wrap somewhere"),
            PANEL,
            measured,
            SCALE,
        )

        assert layout.blocks[0].rows > 1, "this surface was meant to wrap the leading line"
        assert layout.wrapped == (), "an ordinary title was reported as a name the surface could not hold"

    def test_a_line_carries_the_name_when_any_part_of_it_does(self):
        """**The quantifier, pinned at the unit rather than through a label**,
        because no record the product composes can reach it: the name parts are
        the only joinable facts there are, and they are all names, so `or` and
        `and` agree on every label the engine can build today.

        It is asserted anyway because `_compose` is general machinery and the
        quantifier is a stated contract — the same `or` that `mandatory` uses, for
        the same reason. The next joinable fact declared after the name would
        otherwise silently take the ladder's report away from it, and the failure
        would be a warning that stopped firing rather than anything visible.
        """
        name = Candidate(runs=(Run("Katsushika"),), tier=Tier.MANDATORY, names_the_maker=True)
        tail = Candidate(runs=(Run("Japanese"),), tier=Tier.OPTIONAL, continues_line=(Run(", "),))

        lines, _ = _compose((name, tail), (0, 1), break_first_join=False)

        assert plain(lines[0].runs) == "Katsushika, Japanese", "the fixture was meant to compose one joined line"
        assert lines[0].carries_the_name, "a line holding the name stopped being the name's when a fact joined it"

    def test_an_optional_fact_is_never_bought_by_breaking_the_name(self):
        """**`_arrange` returning a wrapped-but-fitting arrangement means opposite
        things to its two callers.**

        For the mandatory pass, a wrapped name beats giving up the family name's
        size, so it is preferred to returning nothing. For the optional-admission
        loop, `None` means "leave this fact off" — so accepting the same
        arrangement says a medium is worth breaking a name for, which inverts the
        ratified ordering.

        **Set at a scale where the branch is reachable, deliberately, because at
        this wall's it is not.** Rung three costs `1.35*(primary+floor)` against
        the joined-wrapped `2.35*primary`, so rung three wins whenever `floor <
        0.74*primary`; the calibrated 8.8′/12.4′ gives 0.710, a 3% margin. The
        queue's own question asks the operator whether 12.4′ can come down, and
        below about 11.9′ the branch flips. A test written at the wall's numbers
        would assert the coincidence and pass whatever this loop did.
        """
        # A floor close to the primary tier — ratio 0.85, over the 0.74 threshold —
        # so the joined-wrapped arrangement is genuinely the shorter one and the
        # loop has to refuse it on the rule rather than on the arithmetic.
        crowded = TypeScale(primary_px=130, floor_px=110)
        surface = Geometry(width_px=1200, height_px=500, margin_px=40)
        name = self.name("Toulouse-Lautrec", "Henri")

        without = lay_out(name, surface, measured, crowded)
        with_optional = lay_out((*name, *droppable("Oil on canvas")), surface, measured, crowded)

        assert without.wrapped == (), "the name already wrapped without the optional fact, so nothing is being tested"
        assert with_optional.wrapped == (), "an optional fact was admitted at the price of breaking the name"

    def test_the_given_name_gives_up_its_tier_before_anything_shrinks(self):
        """**Rung three, and the ordering the operator stated: the family name
        gives up nothing until the given name has given up everything.**

        Rung two sets both parts of a broken name at the identification tier,
        which costs a second full-size line box. A surface too short to pay for
        that has one thing left to try before type starts shrinking — dropping the
        given name to the floor — and it must try it, because a shrink puts the
        *family* name below the size the operator calibrated, and that is the last
        thing on this label anybody agreed to spend.

        The family name keeps the identification tier throughout, which is what
        makes this a rung rather than a retreat.
        """
        short_and_narrow = Geometry(width_px=1600, height_px=360, margin_px=40)

        layout = lay_out(self.name("Toulouse-Lautrec", "Henri Marie Raymond"), short_and_narrow, measured, SCALE)

        assert [block.text for block in layout.blocks] == ["Toulouse-Lautrec", "Henri Marie Raymond"]
        assert layout.blocks[0].size_px == SCALE.primary_px, "the family name gave up its size first"
        assert layout.blocks[1].size_px == SCALE.floor_px
        assert layout.shrunk == (), "it shrank while the given name still had a tier to give up"

    def test_the_break_is_not_taken_when_the_name_fits_without_it(self):
        """Rung one, at a height where the break would also have fitted. An engine
        told "two lines" would break `ANDERS, Joseph` for every short name on the
        wall.

        The biography sits beneath the name rather than on it, so what this asserts
        is that the *name* kept its single line — which is the thing the rung is
        about.
        """
        layout = lay_out(self.name("Anders", "Joseph", "Danish", "1901–1974"), PANEL, measured, SCALE)

        assert [block.text for block in layout.blocks] == ["Anders, Joseph", "Danish, 1901–1974"]

    def test_a_nationality_that_will_not_fit_is_dropped_rather_than_taking_the_name_with_it(self):
        """The biography is optional and the name is not, so the label gives up
        where the artist was from before the name gives up anything at all.

        **It goes as one clause**, because it is one fact: nationality and dates
        were joined on 2026-08-13 when they took a line of their own, and half a
        clause on the panel reads as a fault rather than as an abbreviation.
        """
        cramped = Geometry(width_px=560, height_px=200, margin_px=10)
        facts = self.name("Kandinsky", "Vasily", "Born Moscow (formerly Russian Empire, now Russia)", "1866–1944")

        layout = lay_out(facts, cramped, measured, SCALE)

        assert "Kandinsky" in layout.blocks[0].text
        assert layout.dropped == ("Born Moscow (formerly Russian Empire, now Russia), 1866–1944",)

    def test_a_fact_that_would_open_the_line_never_carries_its_separator(self):
        """The stray comma, which is what an anonymous work's label would open with
        if the separator rode the fact before the one that needs it."""
        nationality = Candidate(runs=(Run("Japanese"),), tier=Tier.OPTIONAL, continues_line=(Run(", "),))

        layout = lay_out((nationality, *identifying("Water Jar")), PANEL, measured, SCALE)

        assert [block.text for block in layout.blocks] == ["Japanese", "Water Jar"]


class TestTheFillModel:
    """Everything above the floor, in priority order, and slack spent on content.

    A fixed hierarchy handles this corpus badly at both ends: an anonymous
    untitled work leaves most of the panel empty while a long-titled attributed
    one overflows. So the engine is given facts with a tier and a position, admits
    every identifying one, and then walks the rest from the top.
    """

    def test_the_mandatory_facts_are_admitted_before_the_fill_rule_runs(self):
        """They are the room the rest competes for what is left of, rather than
        candidates competing for room — which is what makes "nothing else is
        mandatory" affordable."""
        surface = Geometry(width_px=800, height_px=420, margin_px=10)
        facts = (*droppable("Dutch", "1626–1679"), *identifying("The Banquet"))

        layout = lay_out(facts, surface, measured, SCALE)

        assert "The Banquet" in [block.text for block in layout.blocks]

    def test_an_optional_fact_that_will_not_fit_at_the_floor_is_dropped(self):
        surface = Geometry(width_px=800, height_px=300, margin_px=10)

        layout = lay_out(
            (*identifying("The Banquet"), *droppable("Dutch", "1626–1679", "Oil on canvas")), surface, measured, SCALE
        )

        assert layout.dropped, "this surface was meant to be too small for everything"
        assert all(block.size_px >= SCALE.floor_px for block in layout.blocks)

    def test_a_later_fact_is_still_tried_after_an_earlier_one_would_not_fit(self):
        """**Greedy rather than stop-at-the-first-refusal**, and the facts differ
        in size as well as in rank: a one-row date should not be lost to a
        three-row medium that merely came before it. Everything that came off is
        reported either way, so nothing goes missing silently."""
        long_medium = "Colour woodblock print on paper, from the series Thirty-six Views of Mount Fuji, and more besides"
        surface = Geometry(width_px=700, height_px=430, margin_px=10)
        facts = (*identifying("Hokusai"), *droppable(long_medium, "1831"))

        layout = lay_out(facts, surface, measured, SCALE)

        assert "1831" in [block.text for block in layout.blocks]
        assert long_medium in layout.dropped

    def test_commentary_is_the_first_thing_to_go(self):
        """It is the only line that identifies nothing, so it is last in reading
        order and therefore the last admitted and the first refused."""
        commentary = "One of thirty-six views, and the one that outran the series."
        facts = (*identifying("Hokusai"), *droppable("Japanese", "1831", "Colour woodblock print", commentary))

        layout = lay_out(facts, exactly_holding(facts, len(facts) - 1), measured, SCALE)

        assert layout.dropped == (commentary,)

    def test_a_bigger_surface_never_holds_less(self):
        """Monotonicity, which a greedy fill could plausibly break: growing the
        surface must never cost the label a fact it had before.

        Stated here on the reference record so a failure names something a person
        recognises; the same property over every content shape and surface is in
        `test_label_properties.py`.
        """
        facts = (
            *identifying("Hokusai", "Under the Well of the Great Wave off Kanagawa"),
            *droppable("Japanese", "1760–1849", "1831", "Colour woodblock print on paper"),
        )

        dropped = [
            len(lay_out(facts, Geometry(width_px=900, height_px=height, margin_px=10), measured, SCALE).dropped)
            for height in range(300, 1100, 50)
        ]

        assert dropped == sorted(dropped, reverse=True), f"a taller surface dropped more: {dropped}"


class TestSlackIsSpentOnContentBeforeType:
    """Growth toward a preferred size happens only once no further fact can be
    admitted. A label set enormous with three of its six facts dropped is worse
    than one set comfortably with all six.

    **Growth is a promotion between the two tiers rather than a search.** The
    calibration settled exactly two readings worth setting type at, and the rung
    between them is the size reported as taking effort to read — so there is
    nowhere for a growing line to land except the tier above.
    """

    def test_an_almost_empty_label_grows_its_identifying_lines(self):
        """The anonymous untitled work at the other end of the corpus: two facts
        on a panel sized for six leaves most of the surface empty otherwise."""
        layout = lay_out(identifying("Moche", "Stirrup Spout Vessel"), PANEL, measured, SCALE)

        assert [block.size_px for block in layout.blocks] == [SCALE.primary_px, SCALE.primary_px]

    def test_optional_facts_stay_at_the_floor_however_much_room_there_is(self):
        """The two-distance label museum practice sets: the identification block is
        for the approach and everything else is for whoever walks up. A medium set
        at the identification tier would be claiming it identifies the work."""
        layout = lay_out((*identifying("Moche"), *droppable("Ceramic and pigment")), PANEL, measured, SCALE)

        assert [block.size_px for block in layout.blocks] == [SCALE.primary_px, SCALE.floor_px]

    def test_content_is_admitted_before_anything_grows(self):
        """The ordering, asserted where it bites: on a surface exactly big enough
        for all three lines at their proper tiers, the room goes to the medium
        rather than to a larger title."""
        facts = (*identifying("Moche", "Stirrup Spout Vessel"), *droppable("Ceramic and pigment"))

        layout = lay_out(facts, exactly_holding(facts, 3), measured, SCALE)

        assert "Ceramic and pigment" in [block.text for block in layout.blocks]
        assert layout.blocks[1].size_px == SCALE.floor_px, "it grew the title instead of admitting the medium"

    def test_growth_never_lands_between_the_two_tiers(self):
        """The squint boundary again, over the range where growth actually fires.

        **Layouts that had to shrink are exempt, and that is the ruling rather
        than a hole.** A shrink scales the whole label by whatever factor makes it
        fit, so it necessarily passes through every size between the tiers on its
        way down; the boundary is a rule about where the *hierarchy* aims, not a
        floor the exception is bound by.
        """
        for height in range(300, 1100, 25):
            surface = Geometry(width_px=900, height_px=height, margin_px=10)
            layout = lay_out(identifying("Moche", "Stirrup Spout Vessel"), surface, measured, SCALE)
            if layout.shrunk:
                continue

            between = [b.size_px for b in layout.blocks if SCALE.floor_px < b.size_px < SCALE.primary_px]
            assert not between, f"type was set at the squint boundary at {height} px: {between}"


class TestALeadingLineThatIdentifiesNothing:
    """A record with no artist name at all, which the corpus really contains.

    `metadata.py` composes the identification block whether or not a name reached
    it, so a work whose only artist fact is a nationality opens with that
    nationality and sets its title beneath. **Sizing by position alone set the
    demonym at the identification tier and demoted the title to the floor** — an
    optional fact claiming to identify the work, which is the two-distance label
    read backwards, and it is what `_sizes_for` now withholds the tier to prevent.
    """

    #: Room for a leading line at the identification tier and a second at the
    #: floor, and not for two at the identification tier — which is the band where
    #: the demotion was visible rather than repaired by growth.
    BAND = Geometry(width_px=1448, height_px=340, margin_px=20)

    @staticmethod
    def nationality_then_title() -> tuple[Candidate, ...]:
        return (
            Candidate(runs=(Run("Japanese"),), tier=Tier.OPTIONAL, continues_line=(Run(", "),)),
            Candidate(runs=(Run("Water Jar"),), tier=Tier.MANDATORY),
        )

    def test_no_optional_fact_is_ever_set_above_a_mandatory_one(self):
        layout = lay_out(self.nationality_then_title(), self.BAND, measured, SCALE)

        by_text = {block.text: block.size_px for block in layout.blocks}
        assert by_text["Japanese"] <= by_text["Water Jar"], "a demonym was set larger than the work's title"

    def test_the_identification_tier_is_withheld_from_the_whole_label(self):
        """Not handed to the title instead, which would set a smaller line above a
        larger one — a hierarchy nobody chose. The label is simply set small."""
        layout = lay_out(self.nationality_then_title(), self.BAND, measured, SCALE)

        assert {block.size_px for block in layout.blocks} == {SCALE.floor_px}

    def test_growth_does_not_promote_underneath_it_either(self):
        """Room to spare must not reintroduce the inversion from the other end."""
        layout = lay_out(self.nationality_then_title(), PANEL, measured, SCALE)

        sizes = [block.size_px for block in layout.blocks]
        assert sizes == sorted(sizes, reverse=True), sizes
        assert sizes[0] == SCALE.floor_px, "an optional leading line took the identification tier"

    def test_admitting_it_makes_the_label_shorter_rather_than_taller(self):
        """**Which is why there is no `if not placed.shrunk` guard on the fill.**

        The guard that was briefly here rested on "adding a fact can only make an
        arrangement taller", and this is the configuration that falsifies it: the
        nationality takes the identification tier away from the title's line, and
        a title set at the floor can occupy fewer rows *and* fewer pixels than the
        same title at 12.4′. So a trial admission can genuinely succeed where the
        mandatory facts alone did not, and the result is more content at a legible
        size — which a guard would have refused on a rule about slack.
        """
        narrow = Geometry(width_px=300, height_px=1_000_000, margin_px=10)
        title = "Water Jar with Pine Motif"
        title_only = (Candidate(runs=(Run(title),), tier=Tier.MANDATORY),)

        alone = lay_out(title_only, narrow, measured, SCALE)
        with_nationality = lay_out(
            (Candidate(runs=(Run("Japanese"),), tier=Tier.OPTIONAL, continues_line=(Run(", "),)), *title_only),
            narrow,
            measured,
            SCALE,
        )

        def bottom(layout):
            return layout.blocks[-1].y_px + layout.blocks[-1].height_px

        assert bottom(with_nationality) < bottom(alone), "the extra fact did not shorten the label"
        assert "Japanese" in [block.text for block in with_nationality.blocks]
