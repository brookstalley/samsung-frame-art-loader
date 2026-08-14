"""What a label says, read off a manifest entry.

The tier that knows nothing about geometry or pixels, so these run anywhere.

**Two kinds of assertion, and the split is deliberate.** `plain` reduces a line to
what it says, which is what most of these are about and what they asserted when a
line was a string; the styling is asserted separately, on the runs, because it is
a different claim and conflating the two would let a change to either look like a
change to the other. Nothing here asserts what a renderer *does* with a weight —
that is `tests/raster/test_pango.py`, against real type.
"""

from display.panel import Case, LabelText, Run, Slant, Tier, Weight, plain, read_label


def said(label: LabelText) -> list[str]:
    """What each fact the label offers says, in reading order, styling aside.

    **Facts rather than lines, and that is the contract change.** This tier used
    to hand down composed lines, so the identification block arrived here as one
    string; it now hands down the facts and their tiers, and *which* of them share
    a line is decided by whatever knows how much room there is. Which facts end up
    sharing a line, and where one breaks, is asserted in `test_label_layout.py`,
    where the composing happens.
    """
    return [candidate.text for candidate in label.candidates()]


def name_runs(label: LabelText) -> tuple[Run, ...]:
    """The artist's name as styled runs, composed the way the layout composes it.

    **A test convenience, and it lives here for a reason.** `LabelText` carried an
    `identification` property that did this until 2026-08-13, when it lost its
    last production reader: `candidates()` hands the layout the name as one or two
    facts, and the joining is the layout's. A property nothing ships is one nobody
    maintains — its docstring had already gone false about where the nationality
    sits — so the composition moved to the only place that wanted it.
    """
    runs: list[Run] = []
    for candidate in label._name_candidates():
        if runs:
            runs.extend(candidate.continues_line)
        runs.extend(candidate.runs)
    return tuple(runs)


def ranked(label: LabelText) -> list[tuple[str, Tier]]:
    """What each fact says and whether the label may drop it."""
    return [(candidate.text, candidate.tier) for candidate in label.candidates()]


class TestReadingTheManifestBlock:
    def test_the_fields_it_knows_are_taken(self):
        label = read_label(
            {
                "title": "Cow's Skull with Calico Roses",
                "artist": "Georgia O'Keeffe",
                "artist_family_name": "O'Keeffe",
                "artist_given_name": "Georgia",
                "artist_nationality": "American",
                "artist_dates": "1887–1986",
                "date_created": "1931",
                "medium": "Oil on canvas",
                "dimensions": "91.4 × 61 cm",
                "commentary": "The skull was carried back from the desert.",
            }
        )

        assert label.title == "Cow's Skull with Calico Roses"
        assert label.artist == "Georgia O'Keeffe"
        assert (label.artist_family_name, label.artist_given_name) == ("O'Keeffe", "Georgia")
        assert label.dimensions == "91.4 × 61 cm"
        assert label.commentary == "The skull was carried back from the desert."

    def test_a_manifest_written_before_the_name_was_split_still_labels_the_work(self):
        """The deployed catalogue publishes one of these until it is re-seeded, and a
        wall that went blank over an additive change would be the worse failure."""
        label = read_label({"title": "Improvisation No. 30", "artist": "Vasily Kandinsky"})

        assert said(label) == ["Vasily Kandinsky", "Improvisation No. 30"]
        assert all(tier is Tier.MANDATORY for _, tier in ranked(label)), "an unsplit name is still the artist's name"

    def test_a_field_curation_does_not_publish_is_simply_absent(self):
        """The corpus is full of these — a print with no dimensions, an anonymous work."""
        label = read_label({"title": "Untitled"})

        assert label.title == "Untitled"
        assert label.artist is None
        assert said(label) == ["Untitled"]

    def test_a_key_this_version_does_not_know_is_dropped_rather_than_refused(self):
        """A display plane that refused a manifest over an additive change takes the wall down."""
        label = read_label({"title": "Chicago", "accession_number": "1970.1"})

        assert label.title == "Chicago"

    def test_a_value_that_is_not_text_is_dropped(self):
        """Curation's bug; rendering `17` onto a wall label would be this plane repeating it."""
        label = read_label({"title": "Silver Sun", "date_created": 1930})

        assert label.title == "Silver Sun"
        assert label.date_created is None

    def test_no_label_block_at_all_is_an_empty_label(self):
        assert read_label(None).is_empty
        assert read_label({}).is_empty

    def test_something_that_is_not_a_mapping_is_an_empty_label(self):
        assert read_label("a title").is_empty  # type: ignore[arg-type]


class TestTheFactsALabelOffers:
    FULL = LabelText(
        title="The Banquet",
        artist="Jan Steen",
        artist_family_name="Steen",
        artist_given_name="Jan",
        artist_nationality="Dutch",
        artist_dates="1626–1679",
        date_created="1660",
        medium="Oil on canvas",
        dimensions="100 × 80 cm",
        commentary="Painted for a civic guild.",
    )

    def test_they_come_in_reading_order(self):
        """Top of the label to the bottom, not most-important first.

        The artist leads the work: on a 6-inch panel read from 7 feet a long title
        consumed over half the usable height and drove the year, the medium and
        the dimensions off the bottom, while the family name is a few characters.
        The two name parts come first because they share the leading line; the
        biography follows on a line of its own, and the title below that.

        **The biography is one fact, not two.** Where the artist was from and when
        they lived are a single clause in the practice this label follows, and
        they were joined here on 2026-08-13 when they left the name's line — two
        joinable facts would have attached themselves to whatever line was under
        construction, which with the nationality absent is the name's.
        """
        assert said(self.FULL) == [
            "Steen",
            "Jan",
            "Dutch, 1626–1679",
            "The Banquet",
            "1660",
            "Oil on canvas",
            "100 × 80 cm",
            "Painted for a civic guild.",
        ]

    def test_reading_order_is_not_priority_order(self):
        """**The change that made a tier necessary.** The title is set *below* the
        nationality and admitted *before* it, because a label that cannot say what
        the work is called identifies nothing while one missing a demonym is a
        label with a demonym missing. Position alone cannot express that, and the
        rule it replaced — drop from the end — made two droppable facts permanent
        the moment the tombstone collapsed onto the leading line.
        """
        assert ranked(self.FULL) == [
            ("Steen", Tier.MANDATORY),
            ("Jan", Tier.MANDATORY),
            ("Dutch, 1626–1679", Tier.OPTIONAL),
            ("The Banquet", Tier.MANDATORY),
            ("1660", Tier.OPTIONAL),
            ("Oil on canvas", Tier.OPTIONAL),
            ("100 × 80 cm", Tier.OPTIONAL),
            ("Painted for a civic guild.", Tier.OPTIONAL),
        ]

    def test_the_name_is_two_facts_so_the_ladder_has_somewhere_to_break(self):
        """A single candidate could only be wrapped or shrunk. Two lets the family
        name take a line of its own and the given name follow at the floor, which
        is what makes a long family name cost only itself."""
        family, given = self.FULL.candidates()[:2]

        assert (family.text, given.text) == ("Steen", "Jan")
        assert family.continues_line == (), "the family name opens the line"
        assert given.continues_line == (Run(", "),), "the given name continues it, or opens one of its own"

    def test_missing_fields_close_up_rather_than_leaving_gaps(self):
        label = LabelText(title="Golden Bird", medium="Bronze")

        assert said(label) == ["Golden Bird", "Bronze"]

    def test_a_whitespace_only_value_counts_as_absent(self):
        """Museum records carry these, and a blank line mid-label is worse than none."""
        label = LabelText(title="ION 11", medium="   ", dimensions="50 × 50 cm")

        assert said(label) == ["ION 11", "50 × 50 cm"]

    def test_values_are_stripped(self):
        assert said(LabelText(title="  Cat Litter\n")) == ["Cat Litter"]

    def test_a_label_with_nothing_in_it_is_empty(self):
        assert LabelText().is_empty
        assert LabelText(title="  ").is_empty

    def test_a_label_with_anything_in_it_is_not(self):
        assert not LabelText(dimensions="30 × 40 cm").is_empty


class TestWhoMadeIt:
    """The identification line — the one the panel leads with, and never drops."""

    def test_the_family_name_comes_first_and_the_given_name_follows_it(self):
        """An index convention rather than a wall-label one, taken deliberately:
        on a rotating display the family name is what a passer-by scans at 7 feet."""
        label = LabelText(artist="Vasily Kandinsky", artist_family_name="Kandinsky", artist_given_name="Vasily")

        assert said(label) == ["Kandinsky", "Vasily"]

    def test_the_whole_name_is_used_when_neither_part_is_known(self):
        """An artist with no recorded parts is a fact about the record — a culture, a
        workshop, an anonymous master — and not a licence to guess which word is which."""
        label = LabelText(artist="Moche", artist_nationality="Peruvian")

        assert said(label) == ["Moche", "Peruvian"]

    def test_the_stored_name_is_never_split_here_to_manufacture_parts(self):
        """The split is a stored fact because no rule over one string gets both
        "van Gogh" and "Frank Lloyd Wright" right. A display plane inventing one
        would be asserting something about a person it has no way to know."""
        label = LabelText(artist="Frank Lloyd Wright")

        assert said(label) == ["Frank Lloyd Wright"]

    def test_one_known_part_stands_alone_rather_than_being_padded_from_the_whole_name(self):
        """ "Rembrandt" is a correct label; "Rembrandt, Rembrandt Harmenszoon van Rijn" is not."""
        label = LabelText(artist="Rembrandt Harmenszoon van Rijn", artist_family_name="Rembrandt")

        assert said(label) == ["Rembrandt"]

    def test_an_anonymous_work_has_no_identification_line_at_all(self):
        """Not an empty line and not the word "unknown" — the label opens with the title."""
        label = LabelText(title="Untitled")

        assert said(label) == ["Untitled"]

    def test_nationality_and_dates_are_one_fact_on_a_line_below_the_name(self):
        """**This test asserted the opposite until 2026-08-13**, and it stayed green
        for three commits after the product stopped doing it — because it read
        `identification`, a property nothing shipped, rather than the facts the
        tier hands down. Read at the panel, riding the name's line is what set a
        demonym as large as the name."""
        label = LabelText(artist_family_name="Hokusai", artist_nationality="Japanese", artist_dates="1760–1849")

        assert said(label) == ["Hokusai", "Japanese, 1760–1849"]

    def test_a_whitespace_only_part_does_not_become_a_stray_comma(self):
        """Museum records carry these; an empty fragment here reads as a punctuation bug."""
        label = LabelText(artist_family_name="Klee", artist_given_name="  ", artist_nationality="Swiss")

        assert plain(name_runs(label)) == "Klee"

    def test_nationality_and_dates_alone_still_say_something(self):
        """A work whose artist is unrecorded but whose period is not."""
        label = LabelText(title="Bowl", artist_dates="c. 1450–1516")

        assert said(label) == ["c. 1450–1516", "Bowl"]


class TestHowTheLabelIsSet:
    """The styling, which is a claim about runs rather than about what a line says.

    **The family name's weight is what makes the collapsed tombstone readable.**
    `O'KEEFFE, Georgia, American, 1887–1986` spends three commas, and the first
    one means something different from the other two — it marks an inverted name,
    they separate a list. Nothing distinguishes them but the weight, so a change
    that quietly dropped it would leave the line four equal parts and no test
    would notice from the text alone.
    """

    HOKUSAI = LabelText(
        artist="Katsushika Hokusai",
        artist_family_name="Katsushika",
        artist_given_name="Hokusai",
        artist_nationality="Japanese",
        artist_dates="1760–1849",
    )

    def test_the_family_name_is_set_bold_and_in_capitals(self):
        surname = name_runs(self.HOKUSAI)[0]

        assert surname.text == "Katsushika"
        assert (surname.weight, surname.case) == (Weight.BOLD, Case.CAPITALS)

    def test_nothing_else_on_that_line_is(self):
        """The weight means "this is the family name"; a second bold run would say
        the same thing about a nationality."""
        rest = name_runs(self.HOKUSAI)[1:]

        assert all(run.weight is Weight.NORMAL for run in rest)
        assert all(run.case is Case.AS_RECORDED for run in rest)

    def test_the_capitals_are_not_written_into_the_name(self):
        """A person's name keeps its spelling here. The capitals belong to how a
        panel sets it at 7 feet, and `plain` is what everything that is not a
        panel — a journal line, this assertion — reads."""
        assert plain(name_runs(self.HOKUSAI)) == "Katsushika, Hokusai"

    def test_the_separator_is_a_run_of_its_own(self):
        """So that a tier deciding what to drop, or how large to set a fact, is
        never handed a nationality with a comma stuck to its front."""
        assert Run(", ") in name_runs(self.HOKUSAI)

    def test_the_title_is_set_in_italic(self):
        """Museum convention rather than a decision this product took."""
        (title,) = LabelText(title="The Banquet").candidates()

        assert title.runs == (Run("The Banquet", slant=Slant.ITALIC),)

    def test_a_name_with_no_recorded_parts_is_set_as_recorded(self):
        """Bold capitals assert "this is the family name". A whole name nobody has
        split is exactly the case where that is not known."""
        label = LabelText(artist="Frank Lloyd Wright")

        assert name_runs(label) == (Run("Frank Lloyd Wright"),)

    def test_a_given_name_standing_alone_is_not_set_as_a_family_name(self):
        """The degenerate record — one part, and it is the wrong one. Setting it
        bold would be this plane claiming which part of a name it is."""
        label = LabelText(artist_given_name="Rembrandt")

        assert name_runs(label) == (Run("Rembrandt"),)

    def test_the_facts_below_the_name_carry_no_styling_at_all(self):
        """They are facts about the object, and the label sets them as recorded."""
        label = LabelText(date_created="1660", medium="Oil on canvas", dimensions="100 × 80 cm")

        assert [c.runs for c in label.candidates()] == [(Run("1660"),), (Run("Oil on canvas"),), (Run("100 × 80 cm"),)]


class TestMarkupIsNotThisTiersProblem:
    def test_angle_brackets_survive_untouched(self):
        """Escaping belongs to whichever renderer has a markup language, not here.

        The 2024 label passed description text to Pango markup and mangled or
        failed on exactly this. The fix is that the renderer is told to treat
        text as literal — pushing an escape into this tier would put one
        renderer's syntax inside the renderer-agnostic one.
        """
        label = read_label({"title": "<Untitled>", "medium": "Ink & wash"})

        assert label.title == "<Untitled>"
        assert label.medium == "Ink & wash"
