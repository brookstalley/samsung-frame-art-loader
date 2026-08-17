"""A count, and the words around it agreeing with it.

The helper, and the one caller that can be reached without a store:
`ManifestBuild.summarise` is a pure function of two sequence lengths, so it is
exercised here at exactly one — the count every one of these sentences was wrong
at, and the count a test at two would have passed throughout the defect's life.

**The other four callers are pinned where each can actually be driven**, and this
docstring names them because it once claimed to cover them itself, which is a
worse gap than an uncovered sentence: a reader trusting it would believe the
check was here. `mcp/bindings.py`'s notices are in `tests/unit/test_offered_works.py`,
`services/runner.py`'s phase-2 basis in `tests/unit/test_resolve_run.py`, and
`screens/run.js` and `screens/conversation.js` in the browser suite, which is the
only thing that runs them.

**The verb is asserted separately from the noun everywhere below.** A fix that
reaches for a plural noun and stops leaves "1 work ... are reported" behind, and
that is not hypothetical: the client already had one correct inline `=== 1`
ternary for a noun, on the same screen, six lines from sentences that got the
verb wrong.
"""

from datetime import UTC, datetime

import pytest

from curation.counting import agree, agree_partitive, counted, noun
from curation.manifest.builder import Exclusion, ExclusionReason, ManifestBuild, ManifestEntry
from curation.persistence.records import Theme, Wall


@pytest.fixture
def one_work_build():
    """A `ManifestBuild` carrying a chosen number of entries and exclusions.

    Built directly rather than driven through a publish, because `summarise` is
    a pure function of two sequence lengths and driving a real build to reach it
    would put a store, a theme and a rendition between the assertion and the
    sentence it is about.
    """

    def _build(*, excluded: int, entries: int = 0) -> ManifestBuild:
        stamp = datetime(2026, 8, 17, tzinfo=UTC)
        return ManifestBuild(
            wall=Wall(id="wall-1", name="The living room", created_at=stamp),
            theme=Theme(id="theme-1", name="Winter", created_at=stamp),
            entries=[ManifestEntry(work_id=f"work-{index}", render_path=f"r/{index}.jpg", label={}) for index in range(entries)],
            exclusions=[
                Exclusion(
                    work_id=f"out-{index}",
                    title=f"Excluded {index}",
                    reason=ExclusionReason.NO_RENDITION,
                    detail="nothing has been rendered for the television yet",
                )
                for index in range(excluded)
            ],
            rotation_interval_seconds=180,
            shuffle=True,
            directive_sequence=1,
            pinned_work_id=None,
        )

    return _build


class TestTheHelper:
    @pytest.mark.parametrize(("count", "expected"), [(0, "works"), (1, "work"), (2, "works")])
    def test_the_noun_agrees(self, count: int, expected: str):
        """Zero takes the plural, which is English rather than an off-by-one."""
        assert noun(count, "work") == expected

    def test_an_irregular_plural_is_named_at_the_call_site(self):
        assert noun(1, "entry", "entries") == "entry"
        assert noun(2, "entry", "entries") == "entries"

    @pytest.mark.parametrize(("count", "expected"), [(0, "0 works"), (1, "1 work"), (2, "2 works")])
    def test_counted_says_the_number_and_the_noun(self, count: int, expected: str):
        assert counted(count, "work") == expected

    @pytest.mark.parametrize(("count", "expected"), [(0, "are"), (1, "is"), (2, "are")])
    def test_the_verb_agrees(self, count: int, expected: str):
        assert agree(count, "is", "are") == expected

    def test_agree_carries_pronouns_too(self):
        """ "unreachable for them" over a count of one is the same defect as "1 works"."""
        assert agree(1, "it", "them") == "it"
        assert agree(2, "it", "them") == "them"

    def test_agree_has_no_default_plural(self):
        """Because `is`/`are` is not suffixation, so a default could only be wrong."""
        with pytest.raises(TypeError):
            agree(1, "is")  # type: ignore[call-arg]


class TestThePartitive:
    """A sentence of the shape "N of M works …", where the count nearest the verb is the wrong one.

    This is the shape the first pass at the plural fix got wrong on every one of
    its five sites: it corrected each trailing noun and left `agree` keyed on the
    denominator, so "1 of 3 works in this theme are on the wall" shipped. The
    disagreement did not survive the fix; it moved.
    """

    @pytest.mark.parametrize(("part", "whole", "expected"), [(1, 3, "is"), (2, 3, "are"), (1, 1, "is"), (3, 3, "are")])
    def test_the_verb_agrees_with_the_numerator(self, part: int, whole: int, expected: str):
        assert agree_partitive(part, whole, "is", "are") == expected

    @pytest.mark.parametrize(("whole", "expected"), [(1, "is"), (3, "are")])
    def test_at_zero_the_denominator_governs(self, whole: int, expected: str):
        """Zero has no number of its own: "none of the three **are**", "none of the one **is**".

        This is the case that makes this a function rather than advice to pass
        the numerator: doing that gives "0 of 1 work are on the wall", which is
        the fix over-applied, and it is a real state — a theme holding one work
        that cannot be displayed.
        """
        assert agree_partitive(0, whole, "is", "are") == expected


class TestTheManifestSummary:
    """`ManifestBuild.summarise` — **both** branches, which is the pair a partial fix splits.

    The no-exclusions branch is three lines above the other and says the same
    thing about the same number. Fixing one and leaving the other makes this
    method correct when a theme has exclusions and wrong when it does not, which
    is the harder of the two for anyone to notice.
    """

    def test_one_work_all_of_it_on_the_wall(self, one_work_build):
        assert one_work_build(excluded=0, entries=1).summarise() == "All 1 work in this theme is on the wall."

    def test_one_work_and_it_is_not_displayable(self, one_work_build):
        assert (
            one_work_build(excluded=1).summarise() == "0 of 1 work in this theme is on the wall; 1 is not currently displayable."
        )

    def test_two_works_are_unchanged(self, one_work_build):
        """The plural path is the one that was always right, and it stays right."""
        assert one_work_build(excluded=0, entries=2).summarise() == "All 2 works in this theme are on the wall."

    def test_one_of_several_takes_the_singular_verb(self, one_work_build):
        """The partitive, at the count where the two candidate numbers disagree.

        Every other case here has the numerator and the denominator agreeing
        about the verb, which is why keying it on the wrong one survived: only
        "one of several" tells them apart, and it is the ordinary state of a
        theme most of whose works are not yet rendered.
        """
        assert (
            one_work_build(excluded=2, entries=1).summarise()
            == "1 of 3 works in this theme is on the wall; 2 are not currently displayable."
        )
