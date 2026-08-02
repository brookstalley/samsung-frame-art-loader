"""The work identity's rules, one at a time.

Each case here is a property the derivation must hold whatever else changes.
The aggregate — how much of a curator's suppression actually survives real
renaming — is measured separately against captured output, because a derivation
can satisfy every hand-written example here and still fail most real
recurrences. It did exactly that: these tests were green while suppression held
7 of 36.

**The over-merge cases are the important ones.** Splitting one work in two asks
the curator about the same painting twice, which is visible and self-correcting.
Merging two works silently withholds a painting nobody turned down — they are
never shown it and never learn it existed — so the rules that could merge are
pinned here rather than left to the corpus, which contains no pair that would
demonstrate them.
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


# -- what the rules recover ------------------------------------------------------


@pytest.mark.parametrize(
    ("variant", "why"),
    [
        ("Abstraction Blue (1927)", "a year appended in parentheses"),
        ("Abstraction Blue (1927-28)", "a year range"),
        ("Abstraction Blue (ca. 1927)", "an approximate year"),
        ("Abstraction Blue, 1927", "a year appended after a comma"),
        ("Abstraction Blue (1927) ", "trailing space after all of it"),
    ],
)
def test_a_date_the_cataloguer_appended_does_not_split_a_work(variant, why):
    """The largest single cause of lost suppression, measured on real output.

    The same model on the same intent returned "Abstraction Blue" and
    "Abstraction Blue (1927)" minutes apart.
    """
    assert work_dedup_key(title=variant, artist="Georgia O'Keeffe") == work_dedup_key(
        title="Abstraction Blue", artist="Georgia O'Keeffe"
    ), why


def test_a_descriptive_alternate_title_does_not_split_a_work():
    """ "Coquelicots" came back as "(Poppies)", "(Poppy Field)" and "(The
    Poppies)" across four runs of one intent."""
    assert work_dedup_key(title="Coquelicots (The Poppies)", artist="Claude Monet") == work_dedup_key(
        title="Coquelicots", artist="Claude Monet"
    )


def test_a_cataloguing_clause_does_not_split_a_work():
    assert work_dedup_key(title="Yahagi Bridge, from the series Remarkable Views", artist="Hokusai") == work_dedup_key(
        title="Yahagi Bridge", artist="Hokusai"
    )


def test_a_bilingual_compound_does_not_split_a_work():
    """One Vermeer arrived twice in a single run, under two original-language names."""
    assert work_dedup_key(title="Meisje met de parel / Girl with a Pearl Earring", artist="Vermeer") != work_dedup_key(
        title="La jeune fille à la perle / Girl with a Pearl Earring", artist="Vermeer"
    ), "the two originals are different strings and are not claimed to unify"
    assert work_dedup_key(title="Het melkmeisje / The Milkmaid", artist="Vermeer") == work_dedup_key(
        title="Het melkmeisje", artist="Vermeer"
    )


def test_a_parenthesised_alias_does_not_split_an_artist():
    assert work_dedup_key(title="The Nobleman", artist="El Greco (Domenikos Theotokopoulos)") == work_dedup_key(
        title="The Nobleman", artist="El Greco"
    )


# -- what the rules must never merge ---------------------------------------------


def test_two_untitled_works_by_one_artist_keep_their_disambiguators():
    """The over-merge the corpus cannot demonstrate, pinned here instead.

    Rothko and Agnes Martin catalogued many untitled canvases, told apart by a
    number. If a rule ever reduced these to a bare "Untitled", one rejection
    would withhold every other untitled work by that painter, and the curator
    would never be shown what it swallowed.
    """
    keys = {work_dedup_key(title=title, artist="Agnes Martin") for title in ("Untitled #1", "Untitled #2", "Untitled #12")}

    assert len(keys) == 3


def test_a_generic_title_does_not_absorb_its_parenthetical():
    """The one place dropping a parenthetical is refused.

    "Untitled (Composition Studies)" reduced to "Untitled" merges with every
    other untitled work by Pollock. A distinctive base title has no such problem,
    which is why the rule is conditional rather than off.
    """
    assert work_dedup_key(title="Untitled (Composition Studies)", artist="Jackson Pollock") != work_dedup_key(
        title="Untitled", artist="Jackson Pollock"
    )


def test_a_catalogue_number_is_never_dropped():
    """Richter painted hundreds of works called "Abstraktes Bild"; the number is
    the only thing that tells them apart. A year appended after it still goes."""
    assert work_dedup_key(title="Abstraktes Bild (742-4) (1991)", artist="Gerhard Richter") == work_dedup_key(
        title="Abstraktes Bild (742-4)", artist="Gerhard Richter"
    )
    assert work_dedup_key(title="Abstraktes Bild (742-4)", artist="Gerhard Richter") != work_dedup_key(
        title="Abstraktes Bild (648-2)", artist="Gerhard Richter"
    )


def test_a_date_inside_a_title_is_not_treated_as_an_appended_one():
    """A sitter's lifespan is part of the name. Only a TRAILING date is
    cataloguing noise, and that distinction is the whole safety of the rule."""
    key = work_dedup_key(title="James Stuart (1612-1655), Duke of Richmond", artist="Anthony van Dyck")

    assert "1612" in key and "duke of richmond" in key


def test_two_painters_are_never_reduced_to_one():
    """The rejected artist rule, pinned so it cannot come back unnoticed.

    Keeping only the first and last name tokens would turn "Hans Holbein the
    Younger" into "hans younger" and merge him with anyone else so styled.
    """
    assert work_dedup_key(title="Portrait", artist="Hans Holbein the Younger") != work_dedup_key(
        title="Portrait", artist="Hans Bol the Younger"
    )


def test_a_translated_title_still_splits_a_work_and_that_is_recorded():
    """Not every rename is recovered, and this one is not.

    A full translation shares no characters with its original, so no
    normalisation reaches it — telling these two apart from two genuinely
    different works needs a catalogue, not a string rule. It splits, the curator
    sees the painting twice, and that is the recoverable direction.
    """
    assert work_dedup_key(title="Les Demoiselles d'Avignon", artist="Pablo Picasso") != work_dedup_key(
        title="The Young Ladies of Avignon", artist="Pablo Picasso"
    )
