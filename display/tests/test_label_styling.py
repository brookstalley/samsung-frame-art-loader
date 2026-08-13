"""The vocabulary the three label tiers share, and the arithmetic under it.

Runs at every tier's altitude and none of them: no geometry, no manifest, no text
stack. What is under test is the one thing all three depend on being right — that
a run's characters and a run's *place* in the string a renderer sets agree.
"""

from display.panel import Case, Line, Run, Slant, Weight, plain, set_text

# **Not re-exported from the package**, unlike the rest of this vocabulary: the
# only caller is the renderer, which imports the module directly, and a package
# root that offers a name nobody reaches is a surface with no reader.
from display.panel.styling import byte_spans


class TestARunHoldsWhatWasRecorded:
    def test_an_unstyled_run_is_the_default_and_says_so(self):
        """A plain fact is `Run("Oil on canvas")`, so only the runs that depart
        from that have to say anything."""
        run = Run("Oil on canvas")

        assert (run.weight, run.slant, run.case) == (Weight.NORMAL, Slant.UPRIGHT, Case.AS_RECORDED)

    def test_a_capitalised_run_keeps_its_recorded_spelling(self):
        """The capitals belong to how a panel sets a name at 7 feet. A name that
        lost them here would be capitalised in the journal too, and permanently."""
        run = Run("Katsushika", case=Case.CAPITALS)

        assert run.text == "Katsushika"
        assert run.set_text == "KATSUSHIKA"

    def test_a_run_with_no_case_transform_sets_what_it_holds(self):
        assert Run("Hokusai").set_text == "Hokusai"


class TestWhatALineSaysAndWhatGetsSet:
    IDENTIFICATION: Line = (
        Run("Katsushika", weight=Weight.BOLD, case=Case.CAPITALS),
        Run(", "),
        Run("Hokusai"),
    )

    def test_plain_is_the_form_for_anything_that_is_not_a_panel(self):
        assert plain(self.IDENTIFICATION) == "Katsushika, Hokusai"

    def test_set_text_is_the_form_a_renderer_draws(self):
        assert set_text(self.IDENTIFICATION) == "KATSUSHIKA, Hokusai"

    def test_a_line_with_no_capitals_reads_the_same_either_way(self):
        line = (Run("The Banquet", slant=Slant.ITALIC),)

        assert plain(line) == set_text(line) == "The Banquet"


class TestWhereEachRunLands:
    """**Byte offsets, because that is what Pango's attribute indices are.**

    Counting characters is invisible on the corpus's American names and wrong on
    everything else, and what it produces is a run of the wrong length set in the
    wrong weight rather than an error anybody sees.
    """

    def test_the_spans_tile_the_string_that_will_be_set(self):
        """No gaps and no overlaps: every byte belongs to exactly one run, so a
        renderer walking these covers the line once."""
        line = (Run("Klee"), Run(", "), Run("Swiss"))

        spans = byte_spans(line)
        assert spans[0].start_byte == 0
        assert [span.end_byte for span in spans[:-1]] == [span.start_byte for span in spans[1:]]
        assert spans[-1].end_byte == len(set_text(line).encode("utf-8"))

    def test_an_ascii_line_counts_the_same_either_way_which_is_why_this_is_easy_to_miss(self):
        (span,) = byte_spans((Run("Hokusai"),))

        assert (span.start_byte, span.end_byte) == (0, 7)

    def test_a_run_after_non_ascii_text_starts_at_its_byte_offset(self):
        """`1760–1849` is nine characters and eleven bytes — an en dash spends
        three. A run following one of these, which on this corpus is every life
        date, starts two bytes later than a character count would say."""
        line = (Run("1760–1849"), Run(", "), Run("Japanese"))

        _, separator, nationality = byte_spans(line)
        assert separator.start_byte == 11, "the en dash was counted as one byte"
        assert nationality.start_byte == 13

    def test_a_capitalised_run_is_measured_at_the_length_it_is_set(self):
        """The transform happens before the offsets are taken, so a capital that
        costs a different number of bytes than the letter it replaced cannot put
        every later run out of position.

        The German sharp s is the case that makes this concrete: it uppercases to
        two characters, so a span taken from the recorded text would leave every
        run after it one byte short.
        """
        line = (Run("Weiß", case=Case.CAPITALS), Run(", "), Run("German"))

        surname, separator, _ = byte_spans(line)
        assert set_text(line).startswith("WEISS")
        assert surname.end_byte == len(b"WEISS")
        assert separator.start_byte == surname.end_byte

    def test_every_span_indexes_the_string_it_claims_to(self):
        """The property the two tests above are instances of, asserted directly:
        slicing the set string by a span's own bytes gives that run back."""
        line = (
            Run("Kandinsky", weight=Weight.BOLD, case=Case.CAPITALS),
            Run(", "),
            Run("Russian"),
            Run(", "),
            Run("1866–1944"),
        )

        encoded = set_text(line).encode("utf-8")
        for span in byte_spans(line):
            assert encoded[span.start_byte : span.end_byte].decode("utf-8") == span.run.set_text

    def test_a_line_with_no_runs_has_no_spans(self):
        assert byte_spans(()) == ()
