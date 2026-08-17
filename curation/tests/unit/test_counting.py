"""A count, and the words around it agreeing with it.

The helper, and then the four modules whose sentences were written without it —
each exercised at exactly one, because every one of them is correct at two and
was wrong at one, and a test at two would have passed throughout the defect's
life.

**The verb is asserted separately from the noun everywhere below.** A fix that
reaches for a plural noun and stops leaves "1 work ... are reported" behind, and
that is not hypothetical: the client already had one correct inline `=== 1`
ternary for a noun, on the same screen, six lines from sentences that got the
verb wrong.
"""

from datetime import UTC, datetime

import pytest

from curation.counting import agree, counted, noun
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
