"""The client reads what the Art Institute actually sends.

Every fixture here is a response shape **measured** against the real API
(`.prawduct/artifacts/artic-api-findings.md`), not one invented to match the
parser. That is the whole value: a fixture written from the parser's assumptions
would pass forever while the client mis-read the live collection from its first
call.

Driven through `httpx.MockTransport`, so the code under test is the real client
with its real request-building — only the socket is replaced.
"""

import json

import httpx
import pytest

from curation.discovery.artic import PROVIDER, ArticImageSearch
from curation.discovery.images import ImageQuery, ImageSearchFailure
from curation.persistence.records import AcquisitionMethod, RightsStatus, SourceClass

USER_AGENT = "samsung-frame-art-loader (test@example.org)"

#: The real record for artwork 6565, field for field as the API returned it. The
#: dimensions on `thumbnail` are the master's — verified equal to the IIIF
#: `info.json` for the same `image_id` — which is why no second request is made
#: to learn how big the picture is.
AMERICAN_GOTHIC = {
    "_score": 196.23375,
    "id": 6565,
    "api_link": "https://api.artic.edu/api/v1/artworks/6565",
    "title": "American Gothic",
    "thumbnail": {"lqip": "data:image/gif;base64,R0lGOD", "width": 6949, "height": 8400, "alt_text": "Painting of…"},
    "date_display": "1930",
    "artist_display": "Grant Wood (American, 1891–1942)",
    "artist_title": "Grant Wood",
    "image_id": "b272df73-a965-ac37-4172-be4e99483637",
    "is_public_domain": False,
}

#: The same title by a different painter, which the live collection really does
#: hold. It is the reason an artist disagreement has to disqualify rather than
#: merely deduct.
AMERICAN_GOTHIC_BY_LAYTON = {
    "_score": 87.8095,
    "id": 223426,
    "api_link": "https://api.artic.edu/api/v1/artworks/223426",
    "title": "American Gothic",
    "thumbnail": {"lqip": "data:image/gif;base64,R0lGOD", "width": 2380, "height": 3000, "alt_text": "A work made of…"},
    "date_display": "1978",
    "artist_title": "Elizabeth Layton",
    "image_id": "ce38cdf4-1c94-d143-c726-d8dc22e360ec",
    "is_public_domain": True,
}

#: What a query for a work the museum does not hold actually returns: real works,
#: real artists, comfortable scores, and not one of them the painting asked for.
NEAR_MISSES = [
    {
        "_score": 110.56,
        "id": 99790,
        "api_link": "https://api.artic.edu/api/v1/artworks/99790",
        "title": "Ann-In Memory",
        "artist_title": "Joseph Cornell",
        "thumbnail": {"width": 1949, "height": 2250},
        "image_id": "aaaaaaaa-0000-0000-0000-000000000001",
        "is_public_domain": False,
    },
    {
        "_score": 91.24,
        "id": 199002,
        "api_link": "https://api.artic.edu/api/v1/artworks/199002",
        "title": "In Memory of My Father",
        "artist_title": "Sylvia Plimack Mangold",
        "thumbnail": {"width": 6221, "height": 2595},
        "image_id": "aaaaaaaa-0000-0000-0000-000000000002",
        "is_public_domain": True,
    },
]

#: A garbage query does not return an empty list — it returns the collection at
#: score zero, with `pagination.total` reporting the collection size regardless.
ZERO_SCORED = {
    "_score": 0.0,
    "id": 11,
    "api_link": "https://api.artic.edu/api/v1/artworks/11",
    "title": "Self-Portrait",
    "artist_title": "Some Painter",
    "thumbnail": {"width": 2000, "height": 2500},
    "image_id": "aaaaaaaa-0000-0000-0000-000000000003",
    "is_public_domain": True,
}


def _body(*records):
    return {
        "preference": None,
        "pagination": {"total": 132630, "limit": 10, "offset": 0, "total_pages": 13263, "current_page": 1},
        "data": list(records),
        "info": {"license_text": "…", "license_links": ["…"], "version": "1.14"},
        "config": {"iiif_url": "https://www.artic.edu/iiif/2", "website_url": "http://www.artic.edu"},
    }


def _client(handler) -> ArticImageSearch:
    return ArticImageSearch(user_agent=USER_AGENT, client=httpx.Client(transport=httpx.MockTransport(handler)))


def _serving(*records, capture: list | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if capture is not None:
            capture.append(request)
        return httpx.Response(200, json=_body(*records))

    return handler


def test_a_search_result_becomes_an_instance_carrying_the_masters_dimensions():
    """The size the wall gets is read from the search response, not a second call."""
    found = _client(_serving(AMERICAN_GOTHIC)).find_images(ImageQuery(title="American Gothic", artist="Grant Wood"))

    assert len(found) == 1
    instance = found[0]
    assert instance.title == "American Gothic"
    assert instance.artist == "Grant Wood"
    assert instance.provider == PROVIDER
    assert instance.source_class is SourceClass.INSTITUTIONAL
    # Tiles, because every simple size request is capped at 843 pixels wide.
    assert instance.acquisition_method is AcquisitionMethod.DEZOOMIFY
    assert (instance.estimated_width, instance.estimated_height) == (6949, 8400)
    assert instance.url == "https://api.artic.edu/api/v1/artworks/6565"


def test_the_preview_url_is_built_at_the_only_size_the_service_serves():
    """843 is not a tuning knob: every other size redirects here and returns identical bytes."""
    found = _client(_serving(AMERICAN_GOTHIC)).find_images(ImageQuery(title="American Gothic"))

    assert found[0].preview_url == ("https://www.artic.edu/iiif/2/b272df73-a965-ac37-4172-be4e99483637/full/843,/0/default.jpg")


def test_the_iiif_path_is_read_from_the_response_rather_than_hardcoded():
    """Every measured response carries `config.iiif_url`, so a path move needs no release here."""
    moved = _body(AMERICAN_GOTHIC)
    moved["config"]["iiif_url"] = "https://www.artic.edu/iiif/3"

    found = _client(lambda request: httpx.Response(200, json=moved)).find_images(ImageQuery(title="American Gothic"))

    assert found[0].preview_url.startswith("https://www.artic.edu/iiif/3/")


@pytest.mark.parametrize(
    "advertised",
    [
        "https://images.example.org/iiif/3",
        "http://www.artic.edu/iiif/2",
        "https://www.artic.edu.evil.test/iiif/2",
        "file:///etc",
    ],
)
def test_an_unexpected_iiif_host_is_ignored_in_favour_of_the_known_one(advertised):
    """This value builds a URL the process then fetches and writes to disk.

    Read from the response so a path move needs no release; checked so a
    malformed or tampered response cannot point the fetcher somewhere else. The
    plain-HTTP case is refused for the same reason as the foreign hosts — it is
    not the endpoint this client was measured against.
    """
    redirected = _body(AMERICAN_GOTHIC)
    redirected["config"]["iiif_url"] = advertised

    found = _client(lambda request: httpx.Response(200, json=redirected)).find_images(ImageQuery(title="American Gothic"))

    assert found[0].preview_url.startswith("https://www.artic.edu/iiif/2/")


def test_a_response_with_no_config_block_still_yields_a_preview_url():
    """The fallback is for the field going absent, which is not a failure."""
    bare = _body(AMERICAN_GOTHIC)
    del bare["config"]

    found = _client(lambda request: httpx.Response(200, json=bare)).find_images(ImageQuery(title="American Gothic"))

    assert found[0].preview_url.startswith("https://www.artic.edu/iiif/2/")


def test_the_public_domain_flag_becomes_a_rights_status_that_distinguishes_false_from_absent():
    """`false` is `in_copyright`; a missing field is `unknown`. Different facts."""
    absent = {key: value for key, value in AMERICAN_GOTHIC.items() if key != "is_public_domain"}

    in_copyright = _client(_serving(AMERICAN_GOTHIC)).find_images(ImageQuery(title="American Gothic"))
    public = _client(_serving(AMERICAN_GOTHIC_BY_LAYTON)).find_images(ImageQuery(title="American Gothic"))
    unchecked = _client(_serving(absent)).find_images(ImageQuery(title="American Gothic"))

    assert in_copyright[0].rights_status is RightsStatus.IN_COPYRIGHT
    assert public[0].rights_status is RightsStatus.PUBLIC_DOMAIN
    assert unchecked[0].rights_status is RightsStatus.UNKNOWN


def test_a_zero_scored_result_is_dropped_because_a_garbage_query_returns_the_collection():
    """`pagination.total` is the collection size whatever was asked, so presence proves nothing."""
    found = _client(_serving(ZERO_SCORED, AMERICAN_GOTHIC)).find_images(ImageQuery(title="American Gothic"))

    assert [instance.title for instance in found] == ["American Gothic"]


@pytest.mark.parametrize(
    ("missing", "why"),
    [
        ("image_id", "the museum holds the object but publishes no image of it"),
        ("thumbnail", "nothing says how big the picture is"),
    ],
)
def test_a_record_that_cannot_become_an_instance_is_dropped(missing, why):
    """Each disqualification is a fact about the record, not a judgement about the work."""
    incomplete = {key: value for key, value in AMERICAN_GOTHIC.items() if key != missing}

    assert _client(_serving(incomplete)).find_images(ImageQuery(title="American Gothic")) == [], why


def test_a_thumbnail_without_dimensions_is_dropped_rather_than_sized_at_zero():
    """An instance recorded without dimensions is indistinguishable from one that clears the floor."""
    sizeless = {**AMERICAN_GOTHIC, "thumbnail": {"lqip": "data:image/gif;base64,R0lGOD", "alt_text": "…"}}

    assert _client(_serving(sizeless)).find_images(ImageQuery(title="American Gothic")) == []


def test_the_artist_narrows_the_query_text_rather_than_filtering_on_a_field():
    """A field filter returns nothing for a name the museum spells its own way."""
    sent: list[httpx.Request] = []
    _client(_serving(AMERICAN_GOTHIC, capture=sent)).find_images(ImageQuery(title="American Gothic", artist="Grant Wood"))

    assert len(sent) == 1
    assert "American%20Gothic%20Grant%20Wood" in str(sent[0].url)
    # Explicit rather than the default projection, which omits both of the fields
    # an instance cannot be recorded without.
    assert "image_id" in str(sent[0].url)
    assert "thumbnail" in str(sent[0].url)


def test_the_museum_is_told_who_is_calling():
    """The API is open but asks callers to identify themselves, and this deployment does."""
    sent: list[httpx.Request] = []
    _client(_serving(AMERICAN_GOTHIC, capture=sent)).find_images(ImageQuery(title="American Gothic"))

    assert sent[0].headers["AIC-User-Agent"] == USER_AGENT


def test_a_client_cannot_be_built_without_an_identifier():
    """No default, because a default would misrepresent whoever runs this to a third party."""
    with pytest.raises(ValueError, match="ARTIC_USER_AGENT"):
        ArticImageSearch(user_agent="")


@pytest.mark.parametrize(
    ("respond", "why"),
    [
        (lambda request: httpx.Response(404, json={"status": 404, "error": "Not found", "detail": "…"}), "a 404 body"),
        (lambda request: httpx.Response(500, text="upstream is unwell"), "a server error"),
        (lambda request: httpx.Response(200, text="<html>not json</html>"), "a non-JSON body"),
        (lambda request: httpx.Response(200, json=[1, 2, 3]), "a JSON array where an object was due"),
        (lambda request: httpx.Response(200, json={"config": {}}), "an object with no data array"),
    ],
)
def test_a_provider_that_cannot_be_understood_raises_rather_than_reporting_nothing_found(respond, why):
    """ "Asked, and there is nothing there" and "could not ask" lead to opposite actions.

    Reporting the second as the first would tell a curator their painting is not
    in the collection because a server was briefly down.
    """
    with pytest.raises(ImageSearchFailure):
        _client(respond).find_images(ImageQuery(title="American Gothic"))


def test_a_preview_that_will_not_download_reports_absence_rather_than_raising():
    """A missing thumbnail degrades a review card; it does not invalidate an instance."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="try later")

    assert _client(handler).fetch_preview("https://www.artic.edu/iiif/2/x/full/843,/0/default.jpg") is None


def test_a_preview_that_downloads_comes_back_as_bytes():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"\xff\xd8\xff\xe0 jpeg bytes")

    assert (
        _client(handler).fetch_preview("https://www.artic.edu/iiif/2/x/full/843,/0/default.jpg") == b"\xff\xd8\xff\xe0 jpeg bytes"
    )


def test_the_response_the_findings_recorded_parses_field_for_field():
    """A whole recorded body, so the parser is exercised against the real envelope.

    The envelope matters as much as the records: `data`, `config` and
    `pagination` are read from it, and a fixture holding only a bare list would
    not notice the client reaching for a key that moved.
    """
    recorded = json.loads(json.dumps(_body(AMERICAN_GOTHIC, AMERICAN_GOTHIC_BY_LAYTON, *NEAR_MISSES)))

    found = _client(lambda request: httpx.Response(200, json=recorded)).find_images(ImageQuery(title="American Gothic"))

    # Every one of the four is a usable instance at this level: the client
    # reports what the collection holds, and which of them is the requested work
    # is decided above the seam.
    assert [instance.title for instance in found] == [
        "American Gothic",
        "American Gothic",
        "Ann-In Memory",
        "In Memory of My Father",
    ]


#: The single-object response, as `GET /artworks/91194?fields=id,image_id` really
#: returns it — `data` is one object rather than a list, and `config` carries the
#: IIIF base the same way the search envelope does. Measured 2026-08-04 against
#: the live API for Brancusi's *Golden Bird*.
GOLDEN_BIRD_OBJECT = {
    "data": {"id": 91194, "title": "Golden Bird", "image_id": "c8024369-fa0a-6438-0072-f9b9929a800b"},
    "info": {"license_text": "…", "license_links": ["…"], "version": "1.14"},
    "config": {"iiif_url": "https://www.artic.edu/iiif/2", "website_url": "http://www.artic.edu"},
}


class TestResolvingAnObjectsImageService:
    """The step whose absence meant no artic work could ever be fetched.

    A source records where a curator goes to check provenance; the tile fetcher
    needs where the pixels are served. These are the tests that the client can
    get from the first to the second.
    """

    def test_an_api_link_resolves_to_the_iiif_base_for_its_image(self):
        """The shape discovery records on every instance it accepts."""
        client = _client(lambda request: httpx.Response(200, json=GOLDEN_BIRD_OBJECT))

        target = client.tile_url("https://api.artic.edu/api/v1/artworks/91194")

        assert target == "https://www.artic.edu/iiif/2/c8024369-fa0a-6438-0072-f9b9929a800b"

    def test_a_museum_page_url_resolves_to_the_same_place(self):
        """The shape the 2024 index carries, which seeding wrote onto 32 sources."""
        client = _client(lambda request: httpx.Response(200, json=GOLDEN_BIRD_OBJECT))

        target = client.tile_url("https://www.artic.edu/artworks/91194/golden-bird")

        assert target == "https://www.artic.edu/iiif/2/c8024369-fa0a-6438-0072-f9b9929a800b"

    def test_the_object_is_asked_for_by_id_and_only_for_what_is_needed(self):
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, json=GOLDEN_BIRD_OBJECT)

        _client(handler).tile_url("https://www.artic.edu/artworks/91194/golden-bird")

        assert captured[0].url.path == "/api/v1/artworks/91194"
        assert captured[0].url.params["fields"] == "id,image_id"

    def test_the_museum_identifies_the_caller_on_this_call_too(self):
        """The API asks callers to say who they are; a new call must not forget."""
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, json=GOLDEN_BIRD_OBJECT)

        _client(handler).tile_url("https://api.artic.edu/api/v1/artworks/91194")

        assert captured[0].headers["AIC-User-Agent"] == USER_AGENT

    def test_an_advertised_iiif_base_is_used_when_the_museum_moves_its_path(self):
        """Reading the base from the response is why a service move needs no release."""
        moved = {**GOLDEN_BIRD_OBJECT, "config": {"iiif_url": "https://www.artic.edu/iiif/3"}}

        target = _client(lambda request: httpx.Response(200, json=moved)).tile_url("https://api.artic.edu/api/v1/artworks/91194")

        assert target == "https://www.artic.edu/iiif/3/c8024369-fa0a-6438-0072-f9b9929a800b"

    def test_an_advertised_base_on_another_host_is_refused(self):
        """The response builds a URL this process fetches and writes to disk."""
        hijacked = {**GOLDEN_BIRD_OBJECT, "config": {"iiif_url": "https://evil.example.com/iiif/2"}}

        target = _client(lambda request: httpx.Response(200, json=hijacked)).tile_url(
            "https://api.artic.edu/api/v1/artworks/91194"
        )

        assert target.startswith("https://www.artic.edu/iiif/2/")

    def test_a_url_that_names_no_object_is_refused_without_asking_the_museum(self):
        asked: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            asked.append(request)
            return httpx.Response(200, json=GOLDEN_BIRD_OBJECT)

        with pytest.raises(ImageSearchFailure, match="does not name an Art Institute object"):
            _client(handler).tile_url("https://artsandculture.google.com/asset/golden-bird/abc")

        assert asked == []

    def test_a_number_outside_the_object_path_is_not_read_as_an_id(self):
        """`/artworks/<id>` is a path segment, not any digits in the URL."""
        with pytest.raises(ImageSearchFailure):
            _client(lambda request: httpx.Response(200, json=GOLDEN_BIRD_OBJECT)).tile_url(
                "https://www.artic.edu/collection?page=91194"
            )

    def test_an_object_the_museum_publishes_no_image_of_is_named_as_that(self):
        """Distinct from a failed lookup: the record is real and carries no picture."""
        imageless = {**GOLDEN_BIRD_OBJECT, "data": {"id": 91194, "title": "Golden Bird", "image_id": None}}

        with pytest.raises(ImageSearchFailure, match="publishes no image"):
            _client(lambda request: httpx.Response(200, json=imageless)).tile_url("https://api.artic.edu/api/v1/artworks/91194")

    def test_a_museum_that_cannot_be_reached_is_a_failure_not_a_guess(self):
        with pytest.raises(ImageSearchFailure):
            _client(lambda request: httpx.Response(503)).tile_url("https://api.artic.edu/api/v1/artworks/91194")

    def test_the_client_reports_the_provider_its_instances_are_recorded_under(self):
        """Wiring keys resolvers by this rather than repeating the name."""
        assert _client(lambda request: httpx.Response(200, json=GOLDEN_BIRD_OBJECT)).provider == PROVIDER
