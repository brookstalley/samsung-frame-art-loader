"""The label's invariants, over every shape a work and a surface can take.

**These are the accessibility norm, not examples of it.** A work has nine
independently optional fields, which is 512 content shapes before any surface size
is crossed with them, and the rules that matter are universal: no fact that
identifies the work is ever dropped, no optional fact is ever set below the
legibility floor, everything that came off is reported, and nothing runs past the
margin. An example suite covers the shapes somebody thought of — and the two
defects this engine replaced (a title that dropped instead of shrinking, a
nationality that could never drop at all) both survived every example anybody
wrote, because they were about combinations rather than about lines.

**The examples still earn their place and are in `test_label_layout.py`.** These
say a rule always holds; those say what the rule *is*, in a form somebody can read
and argue with. A property suite alone would pass against an engine that drew
nothing at all.

Run derandomized — see `conftest.py` for why, and for what that gives up.
"""

import math
from collections import Counter

import pytest
from hypothesis import given
from hypothesis import strategies as st

from display.panel import Geometry, Line, Tier, lay_out, plain, read_label, set_text, type_scale_for
from display.panel.corpus import CORPUS
from display.panel.layout import Extent
from display.panel.metadata import SEPARATOR

#: The reference wall: a 6-inch 1448×1072 panel read from 7 feet. Derived rather
#: than written down, for the reason `test_label_layout.py` gives.
SCALE = type_scale_for(width_px=1448, height_px=1072, diagonal_inches=6.0, viewing_distance_inches=84.0)


def measured(line: Line, size_px: int, wrap_px: int) -> Extent:
    """The same arithmetic stand-in the example suite uses.

    Shared by copy rather than by import because these two files are about
    different things and a change made for one would silently retune the other —
    and because what a property needs from a measurer is only that it be
    monotonic and consistent, which this is by construction.
    """
    text = set_text(line)
    glyph = max(1, size_px // 2)
    per_row = max(1, wrap_px // glyph)
    rows = max(1, math.ceil(len(text) / per_row))
    return Extent(width_px=min(len(text) * glyph, wrap_px), height_px=rows * size_px, rows=rows)


#: Text a museum record actually contains, at the lengths that decide layouts.
#: **Not `st.text()`**, which spends its budget on control characters and lone
#: surrogates — none of which this engine treats differently from a letter, since
#: it never inspects a character. What varies the outcome is *length*, and the
#: non-ASCII this corpus really carries is exercised by the corpus tests below.
VALUES = st.one_of(
    st.sampled_from(
        [
            "Moche",
            "O'Keeffe",
            "Toulouse-Lautrec",
            "Georgia",
            "Japanese",
            "1760–1849",
            "Oil on canvas",
            "25.7 × 37.9 cm (10 1/8 × 14 15/16 in.)",
            "Under the Well of the Great Wave off Kanagawa",
            "One of thirty-six views, and the one that outran the series.",
        ]
    ),
    st.text(alphabet=st.characters(categories=("Lu", "Ll", "Nd", "Zs")), min_size=1, max_size=120),
)

FIELDS = (
    "title",
    "artist",
    "artist_family_name",
    "artist_given_name",
    "artist_nationality",
    "artist_dates",
    "date_created",
    "medium",
    "dimensions",
    "commentary",
)


@st.composite
def labels(draw: st.DrawFn) -> dict[str, str]:
    """A manifest label block with any subset of the fields present.

    Every field independently present or absent is the point: the two defects this
    engine replaced were both about *which* fields a record happened to have.
    """
    return {field: draw(VALUES) for field in FIELDS if draw(st.booleans())}


@st.composite
def surfaces(draw: st.DrawFn) -> Geometry:
    """A device's label surface, from a postage stamp to something roomy.

    **The small end is not a curiosity.** A panel whose margins nearly consume it
    is what a misconfigured deployment looks like, and it is exactly where the
    shrink rule and the drop rule have to keep agreeing with each other.
    """
    width = draw(st.integers(min_value=1, max_value=2000))
    height = draw(st.integers(min_value=1, max_value=2000))
    return Geometry(width_px=width, height_px=height, margin_px=draw(st.integers(min_value=0, max_value=120)))


def laid(label: dict[str, str], surface: Geometry):
    return lay_out(read_label(label).candidates(), surface, measured, SCALE)


class TestWhatTheLabelPromises:
    @given(labels(), surfaces())
    def test_no_fact_that_identifies_the_work_is_ever_dropped(self, label: dict[str, str], surface: Geometry):
        """**The half of the ruling this engine was built for.** A label that
        cannot say who made the work and what it is called identifies nothing, and
        an unreadably small name is still a name somebody can walk closer to read.

        A surface with no usable area at all is the one exception, and it is not a
        drop rule acting — there is nowhere to put anything, so everything is
        reported and the operator learns the device is misconfigured.

        **Counted rather than compared as sets**, because two facts on one label
        can say the same words — a work whose artist is recorded as `Moche` in
        both the whole-name field and the given-name one, or a one-word
        commentary that repeats the title. A set would report the optional fact's
        drop as the mandatory fact's, which is a failure in this test rather than
        in the engine, and it took a generated example to notice.
        """
        if surface.text_width_px <= 0 or surface.text_height_px <= 0:
            return
        droppable = Counter(c.text for c in read_label(label).candidates() if c.tier is Tier.OPTIONAL)

        for text, dropped in Counter(laid(label, surface).dropped).items():
            assert dropped <= droppable[text], f"{text!r} came off more often than the label could spare it"

    @given(labels(), surfaces())
    def test_no_optional_fact_is_ever_set_below_the_floor(self, label: dict[str, str], surface: Geometry):
        """The other half. Optional content drops at full size rather than being
        squeezed — type that shrank to fit has quietly converted an accessibility
        surface into a decorative one, and only the person who cannot read it
        finds out.

        Asserted through the shrink report rather than by inspecting sizes,
        because a line may carry a mandatory fact *and* an optional one — the
        nationality riding the family name — and it is the mandatory fact that
        earns the whole line its exception.
        """
        layout = laid(label, surface)
        if not layout.shrunk:
            assert all(block.size_px >= SCALE.floor_px for block in layout.blocks)
            return
        mandatory = {c.text for c in read_label(label).candidates() if c.tier is Tier.MANDATORY}

        for block in layout.blocks:
            if block.size_px < SCALE.floor_px:
                assert any(fact and fact in block.text for fact in mandatory), block.text

    @given(labels(), surfaces())
    def test_no_line_is_set_above_the_floor_unless_it_identifies_the_work(self, label: dict[str, str], surface: Geometry):
        """**The universal form of the rule the examples pin one shape of.**

        An optional fact set at the identification tier is claiming to identify
        the work, which is the two-distance label read backwards — and it shipped
        exactly once, for records with no artist name, where the leading line is a
        bare nationality. Sizing followed position while everything else followed
        the tier; three hand-rolled examples now cover that shape, and this covers
        the ones nobody thought to write.

        A line carrying *any* mandatory fact earns the tier for the whole line —
        that is what lets the nationality ride the family name — so the question
        is only whether some mandatory fact is on it. **That is the rule for the
        leading line, and only for it**; the property below is the stricter one
        that governs every line under it.
        """
        mandatory = [c.text for c in read_label(label).candidates() if c.tier is Tier.MANDATORY]

        for block in laid(label, surface).blocks:
            if block.size_px > SCALE.floor_px:
                assert any(fact in block.text for fact in mandatory), f"{block.text!r} was set above the floor"

    @given(labels(), surfaces())
    def test_no_line_below_the_leading_one_is_grown_unless_all_of_it_identifies_the_work(
        self, label: dict[str, str], surface: Geometry
    ):
        """**Where the two quantifiers come apart, and the ladder is what pulls
        them apart.**

        The leading line earns the identification tier if *any* fact on it
        identifies the work — that is what lets a nationality ride a family name,
        and it is the property above. Every line beneath it starts at the floor
        and can only rise by growth, and there the question has to be whether
        *every* fact on it identifies the work: at that size a line claims the
        work is identified by what is on it, so a medium or a life date set there
        is the two-distance label read backwards.

        The name ladder's second rung is exactly the line that separates the two.
        `Hokusai, Japanese, 1760–1849` may not be dropped, because the given name
        is on it — and it is not the name. Asking whether the line was droppable
        would promote the nationality and the dates with it, which is the gap
        `accessibility-spec.md` records as closed by the ladder.

        **Facts whose words are also some mandatory fact's words are left out of
        the question**, for the reason the drop property counts rather than
        comparing sets: a generated record can record `Moche` as its title, its
        given name and its medium at once, and a line reading `Moche` cannot then
        be asked which of the three is on it. The ambiguity is in the record and
        not in the engine, and an assertion that cannot tell two facts apart
        reports the wrong one.
        """
        candidates = read_label(label).candidates()
        identifying = {c.text for c in candidates if c.tier is Tier.MANDATORY}
        optional = [c.text for c in candidates if c.tier is Tier.OPTIONAL and c.text not in identifying]

        for block in laid(label, surface).blocks[1:]:
            if block.size_px > SCALE.floor_px:
                riding = [fact for fact in optional if fact and fact in block.text]
                assert not riding, f"{block.text!r} was grown while carrying optional facts {riding}"

    @given(labels(), surfaces())
    def test_every_fact_is_either_set_or_reported(self, label: dict[str, str], surface: Geometry):
        """**Nothing vanishes silently**, which is the property the journal rests
        on: an engine that adapts silently is one whose omissions nobody can
        audit. A fact is either somewhere in the placed text or named in the drop
        report, and never neither."""
        layout = laid(label, surface)
        placed = "\n".join(block.text for block in layout.blocks)
        reported = set(layout.dropped)

        for candidate in read_label(label).candidates():
            assert candidate.text in placed or candidate.text in reported, candidate.text

    @given(labels(), surfaces())
    def test_a_shrink_is_always_reported(self, label: dict[str, str], surface: Geometry):
        """The condition the exception to the type floor rests on. Illegible type
        fails invisibly, so admitting a shrink re-opens that hole unless something
        names it."""
        layout = laid(label, surface)
        below = [block.text for block in layout.blocks if block.size_px < SCALE.floor_px]

        assert below == list(layout.shrunk)

    @given(labels(), surfaces())
    def test_nothing_is_placed_outside_the_margins(self, label: dict[str, str], surface: Geometry):
        """Horizontally always, and vertically whenever the label did not have to
        shrink — a surface too small even for one-pixel type is a misconfigured
        device, and the label is placed anyway rather than hidden behind a blank
        panel."""
        layout = laid(label, surface)

        for block in layout.blocks:
            assert block.x_px == surface.margin_px
            assert block.width_px <= surface.text_width_px
        if not layout.shrunk and layout.blocks:
            last = layout.blocks[-1]
            assert last.y_px + last.height_px <= surface.margin_px + surface.text_height_px

    @given(labels(), surfaces())
    def test_no_line_is_ever_empty(self, label: dict[str, str], surface: Geometry):
        """A fact the label does not have produces no line rather than a blank one:
        an empty line mid-label reads as a rendering bug and a missing value does
        not."""
        for block in laid(label, surface).blocks:
            assert block.text.strip(), "a blank line reached the surface"

    @given(labels(), surfaces())
    def test_the_leading_line_is_never_smaller_than_the_ones_under_it(self, label: dict[str, str], surface: Geometry):
        """The hierarchy, through growth and through shrink alike. A label whose
        medium was set larger than its artist's name would be saying the medium
        identifies the work."""
        sizes = [block.size_px for block in laid(label, surface).blocks]

        assert sizes == sorted(sizes, reverse=True), sizes

    @given(labels())
    def test_the_tombstone_reads_the_same_however_it_was_composed(self, label: dict[str, str]):
        """**Two things compose the identification line and this is what stops
        them drifting.** `LabelText.identification` joins the name, the
        nationality and the dates for a report or a test; the layout tier joins
        the same facts from the same candidates when it decides how many lines
        they get. Nothing in production reads the first, so a change to the
        second could diverge from it in silence — and the divergence would be a
        stray comma or a missing demonym on the panel while every metadata test
        stayed green.

        Asserted where the ladder cannot interfere: a surface with room for
        everything takes no rung, so the block spans as few lines as the content
        model allows.

        **That is two lines rather than one since 2026-08-13**, when the biography
        left the name's line — so the comparison spans the name and the biography
        beneath it rather than reading one block. The drift this guards against is
        unchanged, and so is the reason it would be invisible: nothing in
        production reads `identification`, so the two can only be held together by
        something that checks.
        """
        described = read_label(label)
        text = described.identification
        if text is None:
            return
        roomy = Geometry(width_px=4000, height_px=10_000, margin_px=10)
        blocks = laid(label, roomy).blocks

        biography = described._biography_candidate()
        spans = 2 if biography is not None and described._name_runs() else 1
        assert SEPARATOR.join(block.text for block in blocks[:spans]) == plain(text)

    @given(labels(), st.integers(min_value=100, max_value=1400))
    def test_a_taller_surface_never_holds_less(self, label: dict[str, str], height: int):
        """**Monotonicity, which a greedy fill could plausibly break.** Growing the
        surface must never cost the label a fact it already had — an engine whose
        answer got worse with more room would be one nobody could reason about
        from a panel measurement."""
        shorter = Geometry(width_px=1000, height_px=height, margin_px=20)
        taller = Geometry(width_px=1000, height_px=height + 200, margin_px=20)

        assert len(laid(label, taller).dropped) <= len(laid(label, shorter).dropped)


class TestTheCorpusItActuallyServes:
    """The specific records, laid out on the wall's own panel.

    The properties above say the rules hold everywhere; these say the wall works —
    and they are the ones that would catch a change that satisfied every invariant
    while making the reference record unreadable.
    """

    PANEL = Geometry(width_px=1448, height_px=1072, margin_px=65)

    @pytest.mark.parametrize(("name", "record"), CORPUS)
    def test_every_record_keeps_what_identifies_it(self, name: str, record: dict[str, str]):
        layout = lay_out(read_label(record).candidates(), self.PANEL, measured, SCALE)

        droppable = Counter(c.text for c in read_label(record).candidates() if c.tier is Tier.OPTIONAL)
        for text, dropped in Counter(layout.dropped).items():
            assert dropped <= droppable[text], f"{name}: {text!r} came off"

    @pytest.mark.parametrize(("name", "record"), CORPUS)
    def test_no_record_on_this_panel_needs_a_shrink(self, name: str, record: dict[str, str]):
        """**The claim the operator's panel visit is for**, asserted here against
        the modelled measurer so a regression is caught before the visit: this
        panel, at this viewing distance, holds every record in the corpus at a
        legible size. A record appearing here means the wall has outgrown its
        panel, which is a finding rather than a test failure to route around.
        """
        layout = lay_out(read_label(record).candidates(), self.PANEL, measured, SCALE)

        assert layout.shrunk == (), name

    @pytest.mark.parametrize(("name", "record"), CORPUS)
    def test_the_artist_leads_and_the_work_follows(self, name: str, record: dict[str, str]):
        """The ordering the operator asked for and the ordering the panel can hold
        turned out to be the same one — seven characters where there were
        forty-four."""
        layout = lay_out(read_label(record).candidates(), self.PANEL, measured, SCALE)
        label = read_label(record)
        if label.identification is None or not label.title:
            return

        texts = [block.text for block in layout.blocks]
        assert texts.index(label.title) > 0, name

    def test_the_record_with_no_name_parts_falls_back_to_the_whole_name(self):
        """A culture rather than a person. The seed table says nothing about it,
        which is the behaviour a heuristic could not have had."""
        moche = dict(CORPUS)["moche"]

        layout = lay_out(read_label(moche).candidates(), self.PANEL, measured, SCALE)

        assert layout.blocks[0].text.startswith("Moche")

    def test_a_record_with_no_artist_name_does_not_shout_its_demonym(self):
        """`NATIONALITY_ONLY` is a real shape and it is what caught the defect: the
        identification block composes from whatever of the three facts it has, so
        a record with no name opens with a bare nationality. The tier is withheld
        from the whole label rather than handed to the demonym."""
        record = dict(CORPUS)["nationality-only"]

        layout = lay_out(read_label(record).candidates(), self.PANEL, measured, SCALE)

        assert {block.size_px for block in layout.blocks} == {SCALE.floor_px}
        assert layout.blocks[0].text == "Japanese"

    def test_the_almost_empty_record_keeps_both_its_facts_and_stays_at_the_floor(self):
        """The other end of the corpus, and the case where the withheld tier and
        the fill model meet.

        **This record cannot grow, and the name says so.** Its only facts are a
        medium and a date — both optional — so nothing on the leading line
        identifies the work, the identification tier is withheld from the whole
        label, and growth stops at the first line it looks at. A name promising
        growth here would be describing a branch this record cannot reach.
        What is worth pinning is the outcome that leaves: two facts,
        neither dropped, all of it at the floor, and most of the panel white.
        That is the arrangement § The fill model calls deliberate and the queued
        panel entry warns will look most like a bug.

        Growth firing is covered by `TestSlackIsSpentOnContentBeforeType` and by
        the records that carry a mandatory fact.
        """
        anonymous = dict(CORPUS)["anonymous"]

        layout = lay_out(read_label(anonymous).candidates(), self.PANEL, measured, SCALE)

        assert layout.blocks, "the label was blank"
        assert layout.dropped == ()
        assert {block.size_px for block in layout.blocks} == {SCALE.floor_px}
