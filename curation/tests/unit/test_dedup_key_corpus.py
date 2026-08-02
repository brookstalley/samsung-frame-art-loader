"""The derivation measured against real phase-1 output, as a standing check.

The corpus is 128 proposals captured from 22 real runs, with ground truth
assigned by reading. Its value is that the rewrites in it were not imagined: the
same intent asked twice returns the same painting under a different name, and
these are the shapes that actually took.

**Why this is a test and not a note in a commit.** The figure it guards is the
share of a curator's rejections that keep working, and nothing else in the suite
can notice that falling. Every other dedup test compares two strings a person
chose, which is exactly how the derivation came to hold only a fifth of real
recurrences together while the suite stayed green.
"""

import json
from collections import defaultdict
from pathlib import Path

import pytest

from curation.discovery.dedup import work_dedup_key

CORPUS = json.loads((Path(__file__).parent.parent / "fixtures" / "phase_one_proposals.json").read_text())
ROWS = CORPUS["rows"]

#: Works held together when this derivation was adopted, out of 36 that recur.
#: A count over a rate: the corpus is fixed, so the count is the exact thing
#: measured, and a rounded percentage would make the floor argue with itself at
#: the boundary. A floor rather than an equality, so an improvement is not a
#: failure — but quietly giving ground is.
ADOPTED_UNITED_WORKS = 29


def keys_by_work() -> dict[str, set[str]]:
    grouped: dict[str, set[str]] = defaultdict(set)
    for row in ROWS:
        grouped[row["work"]].add(work_dedup_key(title=row["title"], artist=row["artist"]))
    return grouped


def works_by_key() -> dict[str, set[str]]:
    grouped: dict[str, set[str]] = defaultdict(set)
    for row in ROWS:
        grouped[work_dedup_key(title=row["title"], artist=row["artist"])].add(row["work"])
    return grouped


def recurring_works() -> set[str]:
    counts: dict[str, int] = defaultdict(int)
    for row in ROWS:
        counts[row["work"]] += 1
    return {work for work, count in counts.items() if count > 1}


def test_the_corpus_still_contains_the_recurrences_it_is_for():
    """A guard on the evidence rather than on the code.

    If the fixture were ever trimmed to rows that only appear once, every
    assertion below would pass by having nothing left to measure.
    """
    recurring = recurring_works()

    assert len(ROWS) == 128
    assert len(recurring) >= 30, f"only {len(recurring)} works recur; the coverage figure would mean little"


def test_no_two_works_share_an_identity():
    """The failure the curator never sees, and so the one that must not happen.

    A merge means a rejection withholds a painting nobody turned down: it is
    skipped silently, and nothing ever tells them it existed. A split merely asks
    them about the same painting twice.
    """
    merged = {key: works for key, works in works_by_key().items() if len(works) > 1}

    assert not merged, f"these identities each cover more than one real work: {merged}"


def test_most_recurrences_survive_being_renamed():
    """The number that is the point: how much suppression actually holds.

    Normalised artist and title alone held 7 of these together. Anything that
    drops back toward that has undone the measurement this derivation came from.
    """
    grouped = keys_by_work()
    recurring = recurring_works()
    united = sum(1 for work in recurring if len(grouped[work]) == 1)

    assert united >= ADOPTED_UNITED_WORKS, (
        f"suppression now holds {united} of {len(recurring)} real recurrences together, below the "
        f"{ADOPTED_UNITED_WORKS} this derivation was adopted at — normalised artist and title alone held 7"
    )


@pytest.mark.parametrize(
    ("work", "why"),
    [
        ("abstraction_blue", "an appended year: 'Abstraction Blue' and 'Abstraction Blue (1927)'"),
        ("vir_heroicus", "an appended year range"),
        ("richter_742_4", "a year appended after a catalogue number that must survive"),
        ("coquelicots", "three different English glosses of one French title"),
        ("large_dort", "a descriptive alternate title in parentheses"),
        ("great_wave", "a 'from the series ...' clause"),
        ("early_sunday", "a markdown citation and a year, together"),
        ("pollock_one_31", "a canonical title that already ends in a year"),
    ],
)
def test_the_named_rewrites_each_resolve_to_one_identity(work, why):
    """Each rule's own case, so a regression names which rewrite stopped working
    rather than only moving the aggregate."""
    assert len(keys_by_work()[work]) == 1, f"{work} split across identities: {why}"


def test_a_parenthesised_alias_on_the_artist_does_not_split_a_work():
    """'El Greco (Domenikos Theotokopoulos)' and 'El Greco' are one painter.

    Asserted on the pair the rule governs rather than on the whole work, which
    also carries a provenance tail on one of its three rows — that residual is
    recorded in the derivation and is not this rule's to fix.
    """
    rows = {row["id"]: row for row in ROWS if row["work"] == "nobleman_hand_chest"}
    aliased = rows["r089"]
    plain = rows["r103"]

    assert aliased["artist"] != plain["artist"], "the corpus rows differ in the way this is about"
    assert work_dedup_key(title=aliased["title"], artist=aliased["artist"]) == work_dedup_key(
        title=plain["title"], artist=plain["artist"]
    )


def test_the_residual_is_the_shape_the_derivation_says_it_is():
    """The works still splitting are the provenance-tail cases, and no others.

    Recorded as a test because "the remainder is one known pattern" is a claim
    that decays silently: a new cause appearing would otherwise look identical to
    the old one, and the coverage floor alone would not notice a swap.
    """
    grouped = keys_by_work()
    still_split = {work for work in recurring_works() if len(grouped[work]) > 1}

    provenance_tail = {
        "barbarigo",
        "henrietta_with_hudson",
        "james_stuart",
        "mr_mrs_andrews",
        "nobleman_hand_chest",
        "thomas_more",
    }
    # "Jacob Isaacksz van Ruisdael" and "Jacob van Ruisdael". Left split on
    # purpose: the rule that would join them drops name tokens, and on "Hans
    # Holbein the Younger" it discards the surname.
    artist_patronymic = {"windmill_wijk"}

    assert (
        still_split == provenance_tail | artist_patronymic
    ), "the residual changed shape; the derivation's recorded account of it is now wrong"


def test_the_two_van_dyck_portraits_of_one_sitter_stay_apart():
    """The over-merge the corpus can actually catch.

    'Queen Henrietta Maria with Sir Jeffrey Hudson' and 'Queen Henrietta Maria'
    are different paintings in different collections. A rule reaching far enough
    to unite the naming variants must not reach far enough to unite these.
    """
    grouped = keys_by_work()

    assert not (grouped["henrietta_with_hudson"] & grouped["henrietta_alone"])
