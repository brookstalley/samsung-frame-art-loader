"""The provisional work identity, and the two ways it is known to be wrong.

The failure modes are tested as much as the successes, because this derivation
ships ahead of the measurement that will choose the real one — and a replacement
argued for later needs the current behaviour written down rather than
remembered. A test that only showed the cases it gets right would leave the
argument for changing it resting on nobody's notes.
"""

import pytest

from curation.discovery.dedup import work_dedup_key


def test_the_same_work_named_the_same_way_keys_the_same():
    first = work_dedup_key(title="The Persistence of Memory", artist="Salvador Dalí")
    second = work_dedup_key(title="The Persistence of Memory", artist="Salvador Dalí")

    assert first == second


@pytest.mark.parametrize(
    "title",
    [
        "the persistence of memory",
        "The Persistence of Memory.",
        "The  Persistence   of Memory",
        "  The Persistence of Memory  ",
        "The Persistence of Memory!",
    ],
)
def test_cataloguing_variation_does_not_split_a_work(title):
    """Case, punctuation and whitespace vary with the cataloguer, not the work."""
    assert work_dedup_key(title=title, artist="Salvador Dalí") == work_dedup_key(
        title="The Persistence of Memory", artist="Salvador Dalí"
    )


def test_an_accent_does_not_split_an_artist():
    """A model writing "Dali" and a museum recording "Dalí" mean one person.

    Keys that separated them would suppress neither, which is the failure the
    curator notices: a work they rejected coming back.
    """
    assert work_dedup_key(title="The Elephants", artist="Salvador Dali") == work_dedup_key(
        title="The Elephants", artist="Salvador Dalí"
    )


def test_different_works_by_one_artist_do_not_collide():
    assert work_dedup_key(title="The Elephants", artist="Salvador Dalí") != work_dedup_key(
        title="Swans Reflecting Elephants", artist="Salvador Dalí"
    )


def test_the_same_title_by_different_artists_does_not_collide():
    """The artist is part of the identity, not decoration.

    Without it, one curator's rejection of an anonymous "Composition" would
    suppress every other painting of that name in the world.
    """
    assert work_dedup_key(title="Composition", artist="Piet Mondrian") != work_dedup_key(
        title="Composition", artist="Wassily Kandinsky"
    )


def test_a_work_with_no_artist_is_keyed_under_a_name_no_artist_can_have():
    """The key never begins with its own separator, and says what it is.

    A missing artist rendering as an empty half would read as a malformed key
    rather than as a work whose artist phase 1 could not name.
    """
    key = work_dedup_key(title="Nighthawks")

    assert key.startswith("(unattributed)")
    assert not key.startswith("::")


@pytest.mark.parametrize("name", ["Unattributed", "unattributed", "(Unattributed)", "Unattributed::"])
def test_an_unattributed_work_does_not_collide_with_an_artist_of_that_name(name):
    """Nobody's real name can normalise onto the no-artist sentinel.

    Improbable and cheap to hold, and the cost of getting it wrong is not: one
    rejected work by an artist so named would suppress every work in the
    catalogue whose artist was never established.
    """
    assert work_dedup_key(title="Nighthawks") != work_dedup_key(title="Nighthawks", artist=name)


# -- the known failure modes, recorded rather than hidden ------------------------


def test_uninformative_titles_collide_and_that_is_the_known_hazard():
    """Two different paintings both called "Untitled" become one identity here.

    This is a false positive: rejecting one suppresses a work nobody turned
    down. It is recorded rather than fixed because fixing it needs evidence
    about which of these two failures actually bites — real phase-1 output is
    what settles that, and this key ships before that output exists.
    """
    assert work_dedup_key(title="Untitled", artist="Mark Rothko") == work_dedup_key(title="Untitled", artist="Mark Rothko")


def test_a_translated_title_splits_one_work_and_that_is_the_other_hazard():
    """One painting under two names becomes two identities here.

    The mirror failure: suppression silently stops working, and the curator
    declines the same painting under each name. Pulling in the opposite
    direction from the collision above is exactly why neither can be fixed by
    guessing.
    """
    assert work_dedup_key(title="Les Demoiselles d'Avignon", artist="Pablo Picasso") != work_dedup_key(
        title="The Young Ladies of Avignon", artist="Pablo Picasso"
    )
