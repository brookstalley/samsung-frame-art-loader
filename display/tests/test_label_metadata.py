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
                "artist_nationality": "American",
                "artist_dates": "1887–1986",
                "date_created": "1931",
                "medium": "Oil on canvas",
                "dimensions": "91.4 × 61 cm",
            }
        )

        assert label.title == "Cow's Skull with Calico Roses"
        assert label.artist == "Georgia O'Keeffe"
        assert label.dimensions == "91.4 × 61 cm"

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
        """Least droppable first — the layout tier drops from the end."""
        label = LabelText(
            title="The Banquet",
            artist="Jan Steen",
            artist_nationality="Dutch",
            artist_dates="1626–1679",
            date_created="1660",
            medium="Oil on canvas",
            dimensions="100 × 80 cm",
        )

        assert label.lines() == (
            "The Banquet",
            "Jan Steen",
            "Dutch",
            "1626–1679",
            "1660",
            "Oil on canvas",
            "100 × 80 cm",
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
