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

from curation.discovery.dedup import clean_name, work_dedup_key


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


def test_a_bilingual_compound_is_left_alone_on_purpose():
    """A rule for this was written, measured, and removed.

    One Vermeer did arrive twice in a single run under two original-language names
    sharing one English gloss, so the failure is real. But the form appears in
    zero of 128 realistic proposals — it showed up only when an intent asked for
    both languages — and which half to keep cannot be chosen from that. Keeping
    the first half does not even fix the case that motivated it. A rule firing on
    a form the product does not produce, in a direction nothing supports, can only
    merge works, and merging is the direction with no recovery.
    """
    assert work_dedup_key(title="Het melkmeisje / The Milkmaid", artist="Vermeer") != work_dedup_key(
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


#: The seven titles a real Dalí run stored, and the title each one is. Written
#: out rather than derived, because the point of the case is the exact string a
#: curator was shown — a fixture that re-derived it from a rule would agree with
#: whatever the rule currently does.
DAMAGED_IN_THE_CATALOGUE = [
    ("The Persistence of Memory (1931) - cited from blog.artsper.com (", "The Persistence of Memory"),
    ("Lobster Telephone (1938) - cited from tate.org.uk (", "Lobster Telephone"),
    ("Metamorphosis of Narcissus (1937) - cited from tate.org.uk (", "Metamorphosis of Narcissus"),
    ("Illumined Pleasures (1929) - cited from moma.org (", "Illumined Pleasures"),
    ("Mountain Lake (1938) - cited from tate.org.uk (", "Mountain Lake"),
    ("Portrait of my Sister (1925) - cited from salvador-dali.org (", "Portrait of my Sister"),
    ("Mae West Lips Sofa (1938) - cited from christies.com (", "Mae West Lips Sofa"),
]


@pytest.mark.parametrize(("stored", "work"), DAMAGED_IN_THE_CATALOGUE)
def test_a_citation_the_old_rule_half_removed_keys_as_the_work_it_names(stored, work):
    """The seven rows the catalogue actually held, each keyed as its painting.

    These are not hypothetical shapes: a Dalí run stored every one of them, and
    the curator judged the works from cards reading `Lobster Telephone (1938) -
    cited from tate.org.uk (`. The damage was ours — a greedy URL pattern ate the
    bracket that closed the citation and left the one that opened it — so the
    same painting proposed cleanly keyed as a different work and suppression
    would not have carried between them.
    """
    assert work_dedup_key(title=stored, artist="Salvador Dalí") == work_dedup_key(title=work, artist="Salvador Dalí")


def test_a_bare_citation_is_dropped_before_it_can_be_stored():
    """The same citation as the model writes it, which is where the fix belongs.

    Repairing the rows above without this would let the next run write seven more.
    """
    written = "The Persistence of Memory (1931) - cited from blog.artsper.com (https://blog.artsper.com/dali/)"

    assert work_dedup_key(title=written, artist="Salvador Dalí") == work_dedup_key(
        title="The Persistence of Memory", artist="Salvador Dalí"
    )


def test_the_words_introducing_a_citation_go_with_it():
    """`- cited from` is not part of a title and must not be part of an identity.

    Removing only the link left it behind in every one of the seven real rows,
    which is a visible defect on the review card and a silent one in the key.
    """
    key = work_dedup_key(title="Mountain Lake (1938) - cited from tate.org.uk (", artist="Salvador Dalí")

    assert "cited" not in key and "from" not in key and "tate" not in key


def test_a_title_ending_in_a_citation_word_keeps_it():
    """The over-merge the lead-in rule could cause, pinned.

    Ingres painted `The Source`. A rule that took a trailing `source`, `from` or
    `see` off any title would reduce it to `The` and merge it with every other
    title ending in one of those words. The words are only evidence when a
    citation was removed alongside them, and here none was.
    """
    assert work_dedup_key(title="The Source", artist="Jean-Auguste-Dominique Ingres") != work_dedup_key(
        title="The", artist="Jean-Auguste-Dominique Ingres"
    )
    assert "source" in work_dedup_key(title="The Source", artist="Jean-Auguste-Dominique Ingres")


def test_a_hostlike_word_in_a_title_is_not_a_citation_even_beside_a_url():
    """The over-merge a bracketed URL nearly bought back.

    Requiring the URL made a trailing hostname safe to drop, but the word before
    the brackets is the *title's* last word as often as the citation's:
    `Composition No.5 (https://example.com/x)` has both halves of the pattern and
    only one of them is a citation. The URL names its own host, so the two are
    told apart by asking it rather than by guessing — and where they disagree the
    URL still goes, because a URL is never part of a title.
    """
    written = "Composition No.5 (https://example.com/x)"

    assert clean_name(written) == "Composition No.5"
    assert work_dedup_key(title=written, artist="Serge Poliakoff") != work_dedup_key(
        title="Composition", artist="Serge Poliakoff"
    )


def test_a_title_word_shaped_exactly_like_a_hostname_survives_beside_a_url():
    """The host check on its own, with the shape check unable to help.

    `St.Mark` is a hostname to any pattern — dot-joined word characters ending in
    letters — so nothing about its *shape* separates it from `tate.org.uk`. Only
    the URL beside it can: it names `example.com`, which is not this word, so the
    word stays. Without that comparison the title would read `The Miracle of`.
    """
    assert clean_name("The Miracle of St.Mark (https://example.com/x)") == "The Miracle of St.Mark"


def test_a_stored_row_whose_last_word_is_numbered_is_not_repaired_as_a_citation():
    """The shape check on its own, with the host check unable to help.

    A row damaged by the old rule has no URL left in it — that is what the old
    rule removed — so nothing can be compared and the shape is the only evidence
    there is. `No.5 (` and `tate.org.uk (` are identical but for the last
    segment, and a top-level domain is letters. Leaving the row unrepaired is the
    recoverable direction; reading it as a citation would key `Composition No.5`
    as `Composition` and swallow every numbered canvas by that painter.
    """
    assert clean_name("Composition No.5 (") == "Composition No.5 ("


@pytest.mark.parametrize(
    "written",
    [
        "Mountain Lake tate.org.uk (https://tate.org.uk])",
        "Mountain Lake tate.org.uk (https://[tate.org.uk)",
        "Mountain Lake tate.org.uk (https://ex[a]mple.com/x)",
    ],
)
def test_a_url_that_will_not_parse_keeps_the_word_rather_than_raising(written):
    """Cleaning a name is not allowed to fail, and here it nearly could.

    `urlsplit` reads a `[` in the authority as the start of an IPv6 address and
    raises `ValueError` on an unbalanced one, which a model is as free to emit as
    anything else. Raising would be expensive in both callers: at the engine seam
    it fails a run already paid for, and inside `reconcile` it fails *startup*,
    every start, for as long as the row is stored — a plane that will not boot
    because of one bad title. Unparseable means the host cannot be proved, and
    unproved means the word stays.
    """
    cleaned = clean_name(written)

    assert cleaned == "Mountain Lake tate.org.uk"


def test_a_citation_names_its_own_host_however_the_site_is_spelled():
    """`tate.org.uk` beside `www.tate.org.uk` is one source, not two.

    A citation names the site and the URL names the server, so the match has to
    be by suffix — an equality test would leave the commonest real spelling of
    all seven stored rows unrecognised.
    """
    assert clean_name("Mountain Lake - tate.org.uk (https://www.tate.org.uk/art/x)") == "Mountain Lake"


def test_a_hostlike_word_in_a_title_is_not_a_citation():
    """The over-merge the citation rule could cause, pinned.

    `No.5` matches any pattern loose enough to match `tate.org.uk`, so a rule
    keying on a trailing hostname alone would leave `Composition` and merge every
    numbered canvas under that name. A hostname counts as a citation only when it
    brought a bracketed URL with it.
    """
    assert work_dedup_key(title="Composition No.5", artist="Serge Poliakoff") != work_dedup_key(
        title="Composition", artist="Serge Poliakoff"
    )


def test_the_bare_citation_rules_do_not_reach_inside_a_markdown_one():
    """Three rules share one string, and this is what keeps them out of each
    other's way.

    A rule matching the bracketed URL on its own would take it out from under the
    markdown rule and strand the `[nga.gov]` only that rule can recognise.
    Requiring a bare hostname before the bracket is what prevents it: in
    `[nga.gov](https://...)` the character there is `]`.
    """
    assert clean_name("Manhattan (1932) – [americanart.si.edu](https://americanart.si.edu/artwork/manhattan-34289)") == (
        "Manhattan (1932)"
    )
    assert clean_name("The Night Watch [rijksmuseum.nl](https://www.rijksmuseum.nl/en/collection/x)") == ("The Night Watch")


def test_a_name_that_was_nothing_but_a_citation_cleans_to_nothing():
    """The empty return every caller has to have an answer for.

    The engine seam drops such a proposal and says so; `reconcile` leaves the
    stored row alone rather than overwriting a title with nothing.
    """
    assert clean_name("tate.org.uk (https://www.tate.org.uk/art/x)") == ""
    assert clean_name("tate.org.uk (") == ""


def test_cleaning_a_name_twice_is_cleaning_it_once():
    """Applied at the engine seam and again inside the key, so it must settle.

    A citation rule that fired on its own output would keep eating words off the
    end of a title every time the value passed through.
    """
    once = clean_name("Mountain Lake (1938) - cited from tate.org.uk (https://www.tate.org.uk/art/x)")

    assert once == "Mountain Lake (1938)"
    assert clean_name(once) == once
