"""The recorded ARTIC findings, as a test rather than as prose.

`artic-api-findings.md` is a snapshot of a live probe, and three of its
measurements are load-bearing in the client: that the search response carries the
*master's* dimensions, that every IIIF response is 843 pixels wide, and that a
query matching nothing still returns the whole collection rather than an empty
page. A document nobody re-runs quietly stops describing the API, so the durable
form of those measurements is a test that fails when one stops holding.

**The third one has already earned its keep.** It was recorded as "the whole
collection, *at score zero*", and that is no longer true: the scores are ordinary
relevance scores now, so the client's zero-score pre-filter no longer empties a
garbage query and the identity comparison is the sole defence. This suite is
where that arrived, in the form of a red test rather than of a wrong belief.

**Deselected by default**, like its OpenRouter sibling — but for a different
reason, and the difference is why it carries a **different marker**. That suite
is deselected because it *costs money*. This one costs nothing: the Art
Institute's API is open and unmetered. It is deselected because it needs the
**network**, and a suite whose job is to be green cannot depend on a third party
being up. Run deliberately:

    uv run pytest -m live_museum

**Not `-m live_api`** — that selector also runs both OpenRouter suites, so a file
arguing at length that it is free would have been instructing the reader to spend
real credit.

Each test names the client behaviour that would break if its fact changed, so a
failure reads as "the museum moved, and here is what now mis-parses" rather than
as an unexplained red.
"""

import struct

import pytest

from curation.discovery.artic import PROVIDER, build_image_search
from curation.discovery.images import ImageQuery
from curation.discovery.phase_two import CONFIDENT, PhaseTwoEngine
from curation.persistence.records import AcquisitionMethod, SourceClass
from curation.services.display_fit import ArtworkBox

pytestmark = pytest.mark.live_museum

#: A real identifier, as the API asks for. The suite identifies itself honestly
#: rather than borrowing a string, which is the same reason there is no default.
USER_AGENT = "samsung-frame-art-loader test suite (brooks@noun.band)"

#: A work the Art Institute genuinely holds, and one it genuinely does not — *The
#: Persistence of Memory* is MoMA's. The second is the whole reason the identity
#: comparison exists, so it belongs in the live suite rather than only in fixtures.
HELD = ("American Gothic", "Grant Wood")
NOT_HELD = ("The Persistence of Memory", "Salvador Dalí")


@pytest.fixture
def museum():
    return build_image_search(user_agent=USER_AGENT)


@pytest.fixture
def engine(museum):
    # A fixed 42" geometry, so the fit verdicts mean something against a known
    # panel. NOT the operator's set, which is 50" — this is a reference the
    # numbers are checkable against, and pinning it keeps the test stable when a
    # deployment value changes.
    return PhaseTwoEngine(museum, box=ArtworkBox(width=3316, height=1597, pixels_per_inch=104.9, floor_inches=12.0))


def _jpeg_size(blob: bytes) -> tuple[int, int]:
    """Width and height off the JPEG's own frame header, not off the URL."""
    index = 2
    while index < len(blob):
        if blob[index] != 0xFF:
            index += 1
            continue
        marker = blob[index + 1]
        if marker in (0xC0, 0xC1, 0xC2):
            height, width = struct.unpack(">HH", blob[index + 5 : index + 9])
            return width, height
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            index += 2
            continue
        index += 2 + struct.unpack(">H", blob[index + 2 : index + 4])[0]
    raise AssertionError("no JPEG frame header found")


def test_a_held_work_still_comes_back_with_the_fields_an_instance_needs(museum):
    """If any of these went absent the client would record nothing at all."""
    found = museum.find_images(ImageQuery(title=HELD[0], artist=HELD[1]))

    assert found, "the collection no longer returns a usable instance for a work it holds"
    instance = next(image for image in found if image.title == HELD[0])
    assert instance.provider == PROVIDER
    assert instance.source_class is SourceClass.INSTITUTIONAL
    assert instance.acquisition_method is AcquisitionMethod.DEZOOMIFY
    assert instance.artist == HELD[1]
    assert instance.preview_url and instance.preview_url.startswith("https://www.artic.edu/iiif/")
    assert instance.rights_status is not None


def test_the_search_response_still_carries_the_masters_dimensions_not_the_previews(museum):
    """The client sizes an instance from the search response and makes no IIIF call.

    If `thumbnail.width`/`height` ever started describing the *preview*, every
    instance would suddenly measure 843 pixels and land below the floor — a
    silent collapse to "nothing is good enough", which is the failure shape this
    product is built around.
    """
    instance = next(image for image in museum.find_images(ImageQuery(title=HELD[0], artist=HELD[1])) if image.title == HELD[0])

    assert instance.estimated_width and instance.estimated_height
    assert instance.estimated_width > 2000, "these are the master's dimensions, not a preview's"

    preview = museum.fetch_preview(instance.preview_url)
    assert preview is not None
    width, _height = _jpeg_size(preview)
    assert width < instance.estimated_width, "the preview is a derivative of the master these dimensions describe"


def test_every_iiif_response_is_still_843_pixels_wide(museum):
    """The preview URL is built at exactly this size because nothing else is served.

    A service that began honouring size requests would not break the client — it
    would just mean the preview could be a better size, and this test is where
    that news arrives.
    """
    instance = next(image for image in museum.find_images(ImageQuery(title=HELD[0], artist=HELD[1])) if image.title == HELD[0])

    width, _height = _jpeg_size(museum.fetch_preview(instance.preview_url))

    assert width == 843


def test_a_nonsense_query_returns_real_paintings_and_the_identity_gate_refuses_them_all(museum, engine):
    """Emptiness is not how this API says no, and the score no longer says it either.

    **This test previously asserted the opposite half and the API moved under it**
    (measured 2026-08-04). A nonsense query used to come back at `_score` 0.0, so
    the client's zero-score pre-filter emptied the result and the recorded
    behaviour was "garbage in, nothing out". It now comes back with ten real works
    scoring in the fifties and sixties — *Nighthawks* among them — while
    `pagination.total` still reports the whole collection. The pre-filter fires on
    none of them.

    So the recorded measurement was rewritten to what the API does, and this test
    was re-aimed at the defence that actually holds: the identity comparison. Both
    halves are asserted because they fail for different reasons and both are worth
    hearing about — the client returning nothing again would mean the API changed
    back, and the engine keeping something would mean the only remaining guard
    between a garbage query and a real painting had stopped discriminating.
    """
    query = ImageQuery(title="zzzqqx nonexistent painting", artist="nobody at all")

    assert museum.find_images(query), "the collection came back empty; the API's way of saying no has changed again"
    assert engine.resolve(query).instances == []


def test_a_work_the_collection_does_not_hold_still_resolves_to_nothing(engine):
    """The measured near-match, live: real works, real artists, none of them the painting.

    This is the finding the whole judgement was designed around. If it ever
    returns an instance, either the museum acquired the painting or the identity
    comparison has stopped discriminating — and the two need telling apart by
    hand, which is why this fails loudly rather than being asserted away.
    """
    judged = engine.resolve(ImageQuery(title=NOT_HELD[0], artist=NOT_HELD[1])).instances

    assert judged == [], f"expected no credible instance, got {[entry.found.title for entry in judged]}"


def test_a_held_work_still_resolves_confidently_end_to_end(engine):
    """The other half: the judgement must not be so strict that nothing survives it."""
    judged = engine.resolve(ImageQuery(title=HELD[0], artist=HELD[1])).instances

    assert judged, "a work the collection holds resolved to nothing — the comparison is too strict"
    assert judged[0].confidence == CONFIDENT
    assert judged[0].below_floor is False
    assert HELD[0] in judged[0].rationale


#: The object endpoint the fetch path resolves through, and a work whose page URL
#: shape matches what the 2024 index recorded on 32 seeded sources.
GOLDEN_BIRD_PAGE = "https://www.artic.edu/artworks/91194/golden-bird"
GOLDEN_BIRD_API = "https://api.artic.edu/api/v1/artworks/91194"


def test_the_object_endpoint_still_answers_with_an_image_id(museum):
    """Acquisition cannot fetch an artic work without this call succeeding.

    It is a *different* endpoint from the search every other test here uses —
    `/artworks/{id}` rather than `/artworks/search` — and the fetch path depends
    on it entirely. Nothing else in the suite would notice it moving.
    """
    target = museum.tile_url(GOLDEN_BIRD_API)

    assert target.startswith("https://www.artic.edu/iiif/2/")
    # An image_id after the base, not a bare base with nothing on the end.
    assert len(target.rsplit("/", 1)[1]) > 8


def test_both_recorded_url_shapes_still_resolve_to_the_same_image_service(museum):
    """The seeded corpus carries page URLs; discovery records api_links.

    Both are real shapes held in this product's catalogue right now, and a change
    to the museum's URL scheme that broke either would strand a third of the
    works with no signal until someone tried to fetch one.
    """
    assert museum.tile_url(GOLDEN_BIRD_PAGE) == museum.tile_url(GOLDEN_BIRD_API)


def test_the_resolved_image_service_is_really_a_iiif_endpoint(museum):
    """Proves the resolution lands somewhere dezoomify can read, not merely
    somewhere well-formed. `info.json` under the base is the contract the tile
    fetcher relies on, and it is checked against the live service rather than
    assumed from the URL's shape."""
    import httpx

    target = museum.tile_url(GOLDEN_BIRD_API)

    response = httpx.get(f"{target}/info.json", timeout=20.0, follow_redirects=True)
    response.raise_for_status()
    payload = response.json()
    assert int(payload["width"]) > 0 and int(payload["height"]) > 0
