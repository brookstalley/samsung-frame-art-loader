"""What a label says, read off a manifest entry.

The tier that knows nothing about geometry or pixels, so these run anywhere.
"""

from display.panel import LabelText, read_label


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

        assert label.identification == "Vasily Kandinsky"
        assert label.lines() == ("Vasily Kandinsky", "Improvisation No. 30")

    def test_a_field_curation_does_not_publish_is_simply_absent(self):
        """The corpus is full of these — a print with no dimensions, an anonymous work."""
        label = read_label({"title": "Untitled"})

        assert label.title == "Untitled"
        assert label.artist is None
        assert label.lines() == ("Untitled",)

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

        assert label.lines() == (
            "Steen, Jan, Dutch, 1626–1679",
            "The Banquet",
            "1660",
            "Oil on canvas",
            "100 × 80 cm",
            "Painted for a civic guild.",
        )

    def test_missing_fields_close_up_rather_than_leaving_gaps(self):
        label = LabelText(title="Golden Bird", medium="Bronze")

        assert label.lines() == ("Golden Bird", "Bronze")

    def test_a_whitespace_only_value_counts_as_absent(self):
        """Museum records carry these, and a blank line mid-label is worse than none."""
        label = LabelText(title="ION 11", medium="   ", dimensions="50 × 50 cm")

        assert label.lines() == ("ION 11", "50 × 50 cm")

    def test_values_are_stripped(self):
        assert LabelText(title="  Cat Litter\n").lines() == ("Cat Litter",)

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

        assert label.identification == "Kandinsky, Vasily"

    def test_the_whole_name_is_used_when_neither_part_is_known(self):
        """An artist with no recorded parts is a fact about the record — a culture, a
        workshop, an anonymous master — and not a licence to guess which word is which."""
        label = LabelText(artist="Moche", artist_nationality="Peruvian")

        assert label.identification == "Moche, Peruvian"

    def test_the_stored_name_is_never_split_here_to_manufacture_parts(self):
        """The split is a stored fact because no rule over one string gets both
        "van Gogh" and "Frank Lloyd Wright" right. A display plane inventing one
        would be asserting something about a person it has no way to know."""
        label = LabelText(artist="Frank Lloyd Wright")

        assert label.identification == "Frank Lloyd Wright"

    def test_one_known_part_stands_alone_rather_than_being_padded_from_the_whole_name(self):
        """ "Rembrandt" is a correct label; "Rembrandt, Rembrandt Harmenszoon van Rijn" is not."""
        label = LabelText(artist="Rembrandt Harmenszoon van Rijn", artist_family_name="Rembrandt")

        assert label.identification == "Rembrandt"

    def test_an_anonymous_work_has_no_identification_line_at_all(self):
        """Not an empty line and not the word "unknown" — the label opens with the title."""
        label = LabelText(title="Untitled")

        assert label.identification is None
        assert label.lines() == ("Untitled",)

    def test_nationality_and_dates_ride_the_name_rather_than_taking_lines_of_their_own(self):
        label = LabelText(artist_family_name="Hokusai", artist_nationality="Japanese", artist_dates="1760–1849")

        assert label.identification == "Hokusai, Japanese, 1760–1849"

    def test_a_whitespace_only_part_does_not_become_a_stray_comma(self):
        """Museum records carry these; an empty fragment here reads as a punctuation bug."""
        label = LabelText(artist_family_name="Klee", artist_given_name="  ", artist_nationality="Swiss")

        assert label.identification == "Klee, Swiss"

    def test_nationality_and_dates_alone_still_say_something(self):
        """A work whose artist is unrecorded but whose period is not."""
        label = LabelText(title="Bowl", artist_dates="c. 1450–1516")

        assert label.lines() == ("c. 1450–1516", "Bowl")


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
