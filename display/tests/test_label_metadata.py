"""What a label says, read off a manifest entry.

The tier that knows nothing about geometry or pixels, so these run anywhere.

**Two kinds of assertion, and the split is deliberate.** `plain` reduces a line to
what it says, which is what most of these are about and what they asserted when a
line was a string; the styling is asserted separately, on the runs, because it is
a different claim and conflating the two would let a change to either look like a
change to the other. Nothing here asserts what a renderer *does* with a weight —
that is `tests/raster/test_pango.py`, against real type.
"""

from display.panel import Case, LabelText, Run, Slant, Weight, plain, read_label


def said(label: LabelText) -> list[str]:
    """What each of the label's lines says, styling aside."""
    return [plain(line) for line in label.lines()]


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

        assert plain(label.identification) == "Vasily Kandinsky"
        assert said(label) == ["Vasily Kandinsky", "Improvisation No. 30"]

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


class TestTheLinesALabelOffers:
    def test_they_come_in_wall_label_order(self):
        """Least droppable first — the layout tier drops from the end.

        The artist leads: on a 6-inch panel read from 7 feet a long title
        consumed over half the usable height and drove the year, the medium and
        the dimensions off the bottom, while the family name is a few characters.
        Identification, nationality and dates arrive as **one** line, which is
        what a museum prints and is worth ~260 px of the panel's ~66 px of slack.
        """
        label = LabelText(
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

        assert said(label) == [
            "Steen, Jan, Dutch, 1626–1679",
            "The Banquet",
            "1660",
            "Oil on canvas",
            "100 × 80 cm",
            "Painted for a civic guild.",
        ]

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

        assert plain(label.identification) == "Kandinsky, Vasily"

    def test_the_whole_name_is_used_when_neither_part_is_known(self):
        """An artist with no recorded parts is a fact about the record — a culture, a
        workshop, an anonymous master — and not a licence to guess which word is which."""
        label = LabelText(artist="Moche", artist_nationality="Peruvian")

        assert plain(label.identification) == "Moche, Peruvian"

    def test_the_stored_name_is_never_split_here_to_manufacture_parts(self):
        """The split is a stored fact because no rule over one string gets both
        "van Gogh" and "Frank Lloyd Wright" right. A display plane inventing one
        would be asserting something about a person it has no way to know."""
        label = LabelText(artist="Frank Lloyd Wright")

        assert plain(label.identification) == "Frank Lloyd Wright"

    def test_one_known_part_stands_alone_rather_than_being_padded_from_the_whole_name(self):
        """ "Rembrandt" is a correct label; "Rembrandt, Rembrandt Harmenszoon van Rijn" is not."""
        label = LabelText(artist="Rembrandt Harmenszoon van Rijn", artist_family_name="Rembrandt")

        assert plain(label.identification) == "Rembrandt"

    def test_an_anonymous_work_has_no_identification_line_at_all(self):
        """Not an empty line and not the word "unknown" — the label opens with the title."""
        label = LabelText(title="Untitled")

        assert label.identification is None
        assert said(label) == ["Untitled"]

    def test_nationality_and_dates_ride_the_name_rather_than_taking_lines_of_their_own(self):
        label = LabelText(artist_family_name="Hokusai", artist_nationality="Japanese", artist_dates="1760–1849")

        assert plain(label.identification) == "Hokusai, Japanese, 1760–1849"

    def test_a_whitespace_only_part_does_not_become_a_stray_comma(self):
        """Museum records carry these; an empty fragment here reads as a punctuation bug."""
        label = LabelText(artist_family_name="Klee", artist_given_name="  ", artist_nationality="Swiss")

        assert plain(label.identification) == "Klee, Swiss"

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
        surname = self.HOKUSAI.identification[0]

        assert surname.text == "Katsushika"
        assert (surname.weight, surname.case) == (Weight.BOLD, Case.CAPITALS)

    def test_nothing_else_on_that_line_is(self):
        """The weight means "this is the family name"; a second bold run would say
        the same thing about a nationality."""
        rest = self.HOKUSAI.identification[1:]

        assert all(run.weight is Weight.NORMAL for run in rest)
        assert all(run.case is Case.AS_RECORDED for run in rest)

    def test_the_capitals_are_not_written_into_the_name(self):
        """A person's name keeps its spelling here. The capitals belong to how a
        panel sets it at 7 feet, and `plain` is what everything that is not a
        panel — a journal line, this assertion — reads."""
        assert plain(self.HOKUSAI.identification) == "Katsushika, Hokusai, Japanese, 1760–1849"

    def test_the_separator_is_a_run_of_its_own(self):
        """So that a tier deciding what to drop, or how large to set a fact, is
        never handed a nationality with a comma stuck to its front."""
        assert Run(", ") in self.HOKUSAI.identification

    def test_the_title_is_set_in_italic(self):
        """Museum convention rather than a decision this product took."""
        (title,) = LabelText(title="The Banquet").lines()

        assert title == (Run("The Banquet", slant=Slant.ITALIC),)

    def test_a_name_with_no_recorded_parts_is_set_as_recorded(self):
        """Bold capitals assert "this is the family name". A whole name nobody has
        split is exactly the case where that is not known."""
        label = LabelText(artist="Frank Lloyd Wright")

        assert label.identification == (Run("Frank Lloyd Wright"),)

    def test_a_given_name_standing_alone_is_not_set_as_a_family_name(self):
        """The degenerate record — one part, and it is the wrong one. Setting it
        bold would be this plane claiming which part of a name it is."""
        label = LabelText(artist_given_name="Rembrandt")

        assert label.identification == (Run("Rembrandt"),)

    def test_the_facts_below_the_name_carry_no_styling_at_all(self):
        """They are facts about the object, and the label sets them as recorded."""
        label = LabelText(date_created="1660", medium="Oil on canvas", dimensions="100 × 80 cm")

        assert label.lines() == ((Run("1660"),), (Run("Oil on canvas"),), (Run("100 × 80 cm"),))


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
