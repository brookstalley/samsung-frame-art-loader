"""Which painter a proposed name resolves to, one rule at a time.

**The merge cases are the important ones.** A split costs a duplicate row that is
visible in the catalogue and can be merged later. A merge writes another person's
name onto a physical label and leaves nothing behind saying a choice was made. So
the cases pinned hardest here are the ones where two names must *not* come out as
one painter, including the two that reach the merge without either name
resembling the other: an unattributed work, and a name that normalises away.
"""

import pytest

from curation.persistence.records import Artist
from curation.services.attribution import resolve


def artist(name: str) -> Artist:
    return Artist(id=f"id-{name}", name=name)


def test_a_name_we_already_hold_matches_the_row_holding_it():
    held = artist("Salvador Dalí")

    result = resolve("Salvador Dalí", [held])

    assert result.matched is held
    assert result.mint is None


def test_a_name_we_do_not_hold_mints_a_row_under_the_name_a_label_renders():
    result = resolve("Salvador Dalí", [artist("Edward Hopper")])

    assert result.matched is None
    assert result.mint == "Salvador Dalí", "the accent is how the name is spelled, not cataloguing noise"


@pytest.mark.parametrize(
    ("held", "proposed"),
    [
        ("Salvador Dalí", "salvador dali"),
        ("Salvador Dalí", "  Salvador   Dalí  "),
        ("El Greco", "El Greco (Domenikos Theotokopoulos)"),
        ("El Greco (Domenikos Theotokopoulos)", "El Greco"),
    ],
)
def test_cataloguing_variation_does_not_split_a_painter(held, proposed):
    result = resolve(proposed, [artist(held)])

    assert result.matched is not None, f"{proposed!r} should have matched {held!r}"


@pytest.mark.parametrize("proposed", [None, "", "   ", "-", "???", "..."])
def test_an_unattributed_work_takes_no_artist_at_all(proposed):
    """The merge nothing has to resemble anything to reach.

    Every one of these normalises to the empty key. Matching on it would make one
    artist named nothing out of every unattributed work in the catalogue.
    """
    result = resolve(proposed, [artist("Edward Hopper")])

    assert result.is_unattributed
    assert result.matched is None
    assert result.mint is None


def test_two_unattributed_works_do_not_become_one_artist():
    first = resolve(None, [])
    second = resolve("   ", [])

    assert first.is_unattributed and second.is_unattributed
    assert first.mint is None and second.mint is None


def test_an_unattributed_work_does_not_match_a_held_artist_whose_name_normalises_away():
    """A row can hold a name that keys empty; it must still not catch everything."""
    result = resolve(None, [artist("???")])

    assert result.matched is None
    assert result.is_unattributed


def test_a_name_that_normalises_away_does_not_match_a_row_that_also_does():
    result = resolve("-", [artist("???")])

    assert result.matched is None, "two names that identify nobody are not the same painter"
    assert result.is_unattributed


# -- the split taken on purpose, and the notice that makes it visible ----------


def test_a_patronymic_splits_rather_than_merging():
    """`data-model.md` records this as inherited and deliberately not closed.

    Closing it needs a heuristic that buys the merge direction, so the duplicate
    is taken instead — and reported, which is what the next test asserts.
    """
    result = resolve("Jacob Isaacksz van Ruisdael", [artist("Jacob van Ruisdael")])

    assert result.matched is None
    assert result.mint == "Jacob Isaacksz van Ruisdael"


def test_the_probable_duplicate_is_named_rather_than_left_silent():
    held = artist("Jacob van Ruisdael")

    result = resolve("Jacob Isaacksz van Ruisdael", [held])

    assert list(result.near_misses) == [held]


def test_the_form_that_defeats_first_and_last_tokens_is_still_reported():
    """`Hans Holbein the Younger` is why no first-and-last rule ships.

    It keys apart from `Hans Holbein`, so it splits — but the shared surname is
    somebody's last token, so the curator is told.
    """
    held = artist("Hans Holbein")

    result = resolve("Hans Holbein the Younger", [held])

    assert result.matched is None
    assert list(result.near_misses) == [held]


def test_a_shared_forename_alone_does_not_report_a_duplicate():
    result = resolve("Hans Holbein", [artist("Hans Memling")])

    assert result.near_misses == (), "every painter sharing a forename would be reported"


def test_a_shared_particle_alone_does_not_report_a_duplicate():
    result = resolve("Vincent van Gogh", [artist("Jacob van Ruisdael")])

    assert result.near_misses == ()


def test_a_short_surname_is_evidence_like_any_other():
    """A minimum token length silently switches this notice off for whole
    naming traditions, while looking correct on every European name.

    `wu li` has no token of three characters at all, so a floor would return
    before comparing anything; `zhang li` would lose the surname that matches.
    """
    held = artist("Wu Li")

    result = resolve("Zhang Li", [held])

    assert list(result.near_misses) == [held]


def test_initials_are_not_evidence():
    """The last-token rule handles these without a length floor."""
    result = resolve("J. M. W. Turner", [artist("J. Smith")])

    assert result.near_misses == ()


def test_a_shared_family_name_is_reported_even_through_a_particle():
    held = artist("Theo van Gogh")

    result = resolve("Vincent van Gogh", [held])

    assert list(result.near_misses) == [held]


def test_an_unrelated_name_reports_nothing():
    result = resolve("Edward Hopper", [artist("Salvador Dalí"), artist("Claude Monet")])

    assert result.near_misses == ()


def test_a_name_contained_in_a_held_name_is_not_that_painter():
    """The merge a substring test would make, and the reason identity is equality.

    `hans holbein` is a substring of `hans holbein the younger`, and they are two
    painters — the elder and the younger. Anything looser than exact key equality
    attributes one's work to the other.
    """
    result = resolve("Hans Holbein", [artist("Hans Holbein the Younger")])

    assert result.matched is None
    assert result.mint == "Hans Holbein"


def test_a_surname_first_held_name_still_reports():
    """The catalogue's own corpus carries `Surname, Forename` records.

    The held name's surname is then not its last token — here its last token is a
    middle name the proposal never mentions — so a rule reading only the held
    side's ending would miss every record written in that convention.
    """
    held = artist("Holbein, Hans Ambrosius")

    result = resolve("Hans Holbein", [held])

    assert list(result.near_misses) == [held]


def test_a_held_artist_whose_name_normalises_away_is_skipped_not_crashed_on():
    """A row can hold a name with no tokens at all; it has no last token to read."""
    result = resolve("Salvador Dalí", [artist("???"), artist("Salvatore Dali")])

    assert result.mint == "Salvador Dalí"


def test_a_match_reports_no_near_misses():
    """A resolved attribution has nothing to warn about, even beside similar rows."""
    held = artist("Jacob van Ruisdael")

    result = resolve("Jacob van Ruisdael", [held, artist("Jacob Isaacksz van Ruisdael")])

    assert result.matched is held
    assert result.near_misses == ()


def test_a_name_that_merely_looks_similar_is_not_reported():
    """`Ruysdael` and `Ruisdael` are two painters and share no token.

    The notice is for names a curator would plausibly want merged, not for every
    name a human eye finds similar — a spelling-distance rule would report the
    two Ruysdaels, who really are different people.
    """
    plausible = artist("Jacob van Ruisdael")
    distinct = artist("Salomon van Ruysdael")

    result = resolve("Jacob Isaacksz van Ruisdael", [plausible, distinct])

    assert list(result.near_misses) == [plausible]


def test_an_empty_catalogue_mints_without_reporting():
    result = resolve("Salvador Dalí", [])

    assert result.mint == "Salvador Dalí"
    assert result.near_misses == ()
