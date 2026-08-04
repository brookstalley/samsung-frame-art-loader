"""Which of a museum's results is actually the work that was asked for.

The case this exists for is the one the live API produced: asking the Art
Institute for *The Persistence of Memory* — which it does not hold, MoMA does —
returns *Ann-In Memory* by Joseph Cornell at a comfortable relevance score. Any
scheme that ranks by the provider's own number attaches that to the request and
reports success, with nothing anywhere saying a different painting was
substituted.

So the tests below are mostly about refusal: what must *not* come back, and the
`unresolved` outcome that must come back instead.
"""

import pytest

from curation.discovery.images import FoundImage, ImageQuery, ImageSearchFailure
from curation.discovery.phase_two import CONFIDENT, TITLE_ONLY, UNATTRIBUTED_RECORD, PhaseTwoEngine
from curation.persistence.records import AcquisitionMethod, RightsStatus, SourceClass
from curation.services.display_fit import ArtworkBox, DisplayFit

#: A 42" panel, as `Settings.tv_artwork_box` composes it — a fixed geometry chosen
#: so the numbers below are checkable, NOT the operator's set, which is 50". A
#: 12-inch floor sits at about 1,260 pixels on the long edge here.
BOX = ArtworkBox(width=3316, height=1597, pixels_per_inch=104.9, floor_inches=12.0)


def an_instance(title: str, *, artist: str | None = None, width: int = 6949, height: int = 8400, **kwargs) -> FoundImage:
    return FoundImage(
        url=f"https://api.artic.edu/api/v1/artworks/{abs(hash(title)) % 10000}",
        provider="artic",
        source_class=SourceClass.INSTITUTIONAL,
        acquisition_method=AcquisitionMethod.DEZOOMIFY,
        title=title,
        artist=artist,
        preview_url="https://www.artic.edu/iiif/2/x/full/843,/0/default.jpg",
        estimated_width=width,
        estimated_height=height,
        **kwargs,
    )


class StubSearch:
    """A provider that answers with what it was built to answer."""

    def __init__(self, *instances: FoundImage, fails: bool = False) -> None:
        self._instances = instances
        self._fails = fails

    def find_images(self, query: ImageQuery):
        if self._fails:
            raise ImageSearchFailure("the museum could not be reached")
        return self._instances

    def fetch_preview(self, url: str) -> bytes | None:
        return b"jpeg"


def resolve(*instances: FoundImage, title: str, artist: str | None = None):
    return PhaseTwoEngine(StubSearch(*instances), box=BOX).resolve(ImageQuery(title=title, artist=artist))


# -- the near-match, which is the whole point -----------------------------------


def test_a_real_work_by_a_real_artist_is_refused_when_it_is_not_the_work_asked_for():
    """The measured case: the museum does not hold this painting and says so by omission.

    Every candidate here scored well against the live query. None is the
    requested work, and the correct answer is nothing at all — because an empty
    result makes the work `unresolved`, which is the signal that phase 1 may have
    proposed something that does not exist, and a low-confidence near-match
    launders exactly that signal away.
    """
    judged = resolve(
        an_instance("Ann-In Memory", artist="Joseph Cornell"),
        an_instance("In Memory of My Father", artist="Sylvia Plimack Mangold"),
        an_instance("A Memory", artist="Gene Charlton"),
        title="The Persistence of Memory",
        artist="Salvador Dalí",
    )

    assert judged == []


def test_the_same_title_by_a_different_painter_is_refused_rather_than_scored_lower():
    """A deduction still selects the wrong one whenever the right one is absent.

    The collection really does hold two *American Gothic*s, so this is not a
    hypothetical: a scheme that merely ranked Grant Wood above Elizabeth Layton
    would attach hers to a request for his the moment his was missing.
    """
    judged = resolve(an_instance("American Gothic", artist="Elizabeth Layton"), title="American Gothic", artist="Grant Wood")

    assert judged == []


def test_the_right_painter_is_kept_when_both_are_offered():
    judged = resolve(
        an_instance("American Gothic", artist="Elizabeth Layton"),
        an_instance("American Gothic", artist="Grant Wood"),
        title="American Gothic",
        artist="Grant Wood",
    )

    assert [entry.found.artist for entry in judged] == ["Grant Wood"]
    assert judged[0].confidence == CONFIDENT


# -- identity, derived from the module that already owns it ---------------------


@pytest.mark.parametrize(
    ("asked", "held"),
    [
        ("The Persistence of Memory", "The Persistence of Memory (1931)"),
        ("Coquelicots", "Coquelicots (The Poppies)"),
        ("Nighthawks", "nighthawks"),
        ("Dalí's Study", "Dali's Study"),
    ],
)
def test_cataloguing_variation_in_a_title_is_not_a_different_work(asked, held):
    """Normalisation comes from `dedup`, so this agrees with the dedup key by construction.

    A second normalisation written here would be free to drift from the one the
    persisted identity is built with, and the two disagreeing is how one painting
    becomes two rows.
    """
    judged = resolve(an_instance(held, artist="Someone"), title=asked, artist="Someone")

    assert len(judged) == 1


@pytest.mark.parametrize(
    ("asked_artist", "held_artist", "expected"),
    [
        ("Grant Wood", "Grant Wood", CONFIDENT),
        ("El Greco", "El Greco (Domenikos Theotokopoulos)", CONFIDENT),
        (None, "Grant Wood", TITLE_ONLY),
        ("Grant Wood", None, UNATTRIBUTED_RECORD),
    ],
)
def test_confidence_reflects_how_much_of_the_identity_was_confirmable(asked_artist, held_artist, expected):
    """Three tiers, because a title alone is a weaker identity than a title and a painter."""
    judged = resolve(an_instance("American Gothic", artist=held_artist), title="American Gothic", artist=asked_artist)

    assert judged[0].confidence == expected


def test_confidence_never_reaches_certainty():
    """This is a textual identity match, not an inspection of the picture.

    Reserving the top of the range leaves somewhere for a provider that can
    actually verify the image to go, and stops a strong-but-textual match from
    reading as proof.
    """
    judged = resolve(an_instance("American Gothic", artist="Grant Wood"), title="American Gothic", artist="Grant Wood")

    assert 0 < judged[0].confidence < 1.0


# -- the floor ------------------------------------------------------------------


def test_a_below_floor_instance_is_kept_and_labelled_rather_than_hidden():
    """Not a rejection: shown, sized in inches, and selectable by a curator who wants it."""
    judged = resolve(an_instance("Small Study", artist="Someone", width=600, height=400), title="Small Study", artist="Someone")

    assert len(judged) == 1
    assert judged[0].below_floor is True
    assert judged[0].fit.fit is DisplayFit.BELOW_FLOOR
    assert "below the 12-inch floor" in judged[0].rationale
    # The number, not just the verdict — a curator judging one needs the size.
    assert f"{judged[0].fit.rendered_long_edge_inches:.1f} inches" in judged[0].rationale


def test_below_floor_instances_sort_behind_every_instance_that_clears_it():
    """Ordering is what makes the first-recorded instance the one that gets selected."""
    judged = resolve(
        an_instance("Study", artist="Someone", width=600, height=400),
        an_instance("Study", artist="Someone", width=6000, height=4000),
        title="Study",
        artist="Someone",
    )

    assert [entry.below_floor for entry in judged] == [False, True]


def test_a_bigger_scan_of_the_same_work_outranks_a_smaller_one():
    """Quality breaks ties between instances that are equally, credibly the work."""
    judged = resolve(
        an_instance("Nighthawks", artist="Edward Hopper", width=1600, height=1200),
        an_instance("Nighthawks", artist="Edward Hopper", width=6000, height=4500),
        title="Nighthawks",
        artist="Edward Hopper",
    )

    assert judged[0].found.estimated_width == 6000
    assert judged[0].quality_score > judged[1].quality_score


def test_a_tall_master_with_resolution_to_spare_outranks_a_smaller_one_that_suits_the_shape():
    """Aspect ratio must not be read as resolution — the requirement says so outright.

    The artwork box is much wider than it is tall, so a 6949x8400 portrait is
    limited by the box's height and renders *shorter* on the wall than a
    2000x1500 landscape that happens to fit the shape. It nonetheless has four
    times the resolution to spare, and it is the better file: canvas occupancy is
    dominated by aspect-ratio mismatch, and what isolates resolution is whether
    the render is a downscale or a native-size paste.

    An earlier ranking here used rendered inches and preferred the smaller file.
    """
    portrait = an_instance("Study", artist="Someone", width=6949, height=8400)
    landscape = an_instance("Study", artist="Someone", width=2000, height=1500)

    judged = resolve(landscape, portrait, title="Study", artist="Someone")

    assert judged[0].found is portrait
    # And the reason is visible in the verdict, not only in the ordering.
    assert judged[0].fit.fit is DisplayFit.NATIVE
    assert judged[1].fit.fit is DisplayFit.MATTED_SMALL
    assert judged[1].fit.rendered_long_edge_inches > judged[0].fit.rendered_long_edge_inches


def test_quality_never_overturns_confidence():
    """A gorgeous scan of the wrong painting is worse than a modest scan of the right one.

    Both survive the identity check here — the request names no artist, so a
    record naming one and a record naming none are both credible — and the
    weaker identity must still lose despite being the larger file.
    """
    judged = resolve(
        an_instance("Nighthawks", artist=None, width=9000, height=7000),
        an_instance("Nighthawks", artist="Edward Hopper", width=1400, height=1100),
        title="Nighthawks",
        artist="Edward Hopper",
    )

    assert judged[0].found.artist == "Edward Hopper"
    assert judged[0].quality_score < judged[1].quality_score


def test_an_instance_the_provider_could_not_size_is_dropped():
    """One recorded without dimensions is indistinguishable from one that clears the floor."""
    judged = resolve(
        FoundImage(
            url="https://example.org/1",
            provider="somewhere",
            source_class=SourceClass.CONTEMPORARY_WEB,
            acquisition_method=AcquisitionMethod.DIRECT_HTTP,
            title="Nighthawks",
            artist="Edward Hopper",
        ),
        title="Nighthawks",
        artist="Edward Hopper",
    )

    assert judged == []


# -- rights, which inform quality without gating anything -----------------------


def test_rights_break_a_tie_between_otherwise_identical_instances():
    """An institution's own public-domain scan is usually the authoritative file."""
    judged = resolve(
        an_instance("Nighthawks", artist="Edward Hopper", rights_status=RightsStatus.IN_COPYRIGHT),
        an_instance("Nighthawks", artist="Edward Hopper", rights_status=RightsStatus.PUBLIC_DOMAIN),
        title="Nighthawks",
        artist="Edward Hopper",
    )

    assert judged[0].found.rights_status is RightsStatus.PUBLIC_DOMAIN


def test_rights_never_exclude_an_instance_and_never_beat_resolution():
    """Constraint 13: rights gate nothing. An in-copyright larger scan still wins."""
    judged = resolve(
        an_instance("Nighthawks", artist="Edward Hopper", width=1400, height=1100, rights_status=RightsStatus.PUBLIC_DOMAIN),
        an_instance("Nighthawks", artist="Edward Hopper", width=8000, height=6000, rights_status=RightsStatus.IN_COPYRIGHT),
        title="Nighthawks",
        artist="Edward Hopper",
    )

    assert len(judged) == 2, "nothing is excluded on rights"
    assert judged[0].found.rights_status is RightsStatus.IN_COPYRIGHT


# -- failure is not the same as finding nothing ---------------------------------


def test_a_provider_that_cannot_be_reached_raises_rather_than_answering_empty():
    """Empty means "your painting is not in this collection"; that is a different claim."""
    engine = PhaseTwoEngine(StubSearch(fails=True), box=BOX)

    with pytest.raises(ImageSearchFailure):
        engine.resolve(ImageQuery(title="Nighthawks"))


def test_a_rationale_names_the_museums_own_title_so_a_substitution_would_be_visible():
    """The card says what the provider calls it, which is how a curator catches a wrong match."""
    judged = resolve(
        an_instance("American Gothic (1930)", artist="Grant Wood"),
        title="American Gothic",
        artist="Grant Wood",
    )

    assert "American Gothic (1930)" in judged[0].rationale
    assert "Grant Wood" in judged[0].rationale
