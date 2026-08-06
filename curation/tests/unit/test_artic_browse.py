"""Browsing a collection by artist, against the shapes the live API really sends.

Every fixture here mirrors a response **measured** against the Art Institute
(`.prawduct/artifacts/artic-api-findings.md` § Browsing by artist), including the
detail that makes the safety rule non-obvious: the aggregation that prices a
surname's ambiguity answers differently depending on whether it inherits the
browse's own filters. The transport below reproduces that difference rather than
asserting the request looks right, so an implementation that scoped the check
wrongly fails on the work it offers rather than on a request body.

Driven through `httpx.MockTransport`: the real client, its real request-building
and its real parsing, with only the socket replaced.
"""

import json

import httpx
import pytest

from curation.discovery.artic import PROVIDER, ArticCollectionBrowse
from curation.discovery.browse import BrowseQuery, CollectionBrowseFailure
from curation.persistence.records import AcquisitionMethod, RightsStatus, SourceClass

USER_AGENT = "samsung-frame-art-loader (test@example.org)"

CONFIG = {"iiif_url": "https://www.artic.edu/iiif/2", "website_url": "http://www.artic.edu"}


def a_hit(title: str, artist: str, *, work_id: int, width: int = 6000, height: int = 4500, public_domain: bool = True):
    """One `top_hits` entry, shaped as the live aggregation returns it.

    Note the `_source` nesting and the absence of `_score`: a browse hit is
    selected by a filter, so there is no relevance number on it to read.
    """
    return {
        "_id": str(work_id),
        "_source": {
            "id": work_id,
            "api_link": f"https://api.artic.edu/api/v1/artworks/{work_id}",
            "title": title,
            "artist_title": artist,
            "image_id": f"image-{work_id}",
            "is_public_domain": public_domain,
            "thumbnail": {"width": width, "height": height, "alt_text": "A work made of oil on canvas."},
        },
    }


def a_facet_bucket(*hits, matched: int):
    return {"doc_count": matched, "top": {"hits": {"total": {"value": matched}, "hits": list(hits)}}}


def a_response(buckets: dict, *, agg: str = "by_facet"):
    return {
        "preference": None,
        "pagination": {"total": sum(b["doc_count"] for b in buckets.values()), "limit": 0},
        "data": [],
        "aggregations": {agg: {"buckets": buckets}},
        "config": CONFIG,
    }


def a_vocabulary_response(names_by_artist: dict[str, list[str]]):
    """The unfiltered check: which artists each surname reaches."""
    return {
        "pagination": {"total": 0, "limit": 0},
        "data": [],
        "aggregations": {
            "by_surname": {
                "buckets": {
                    artist: {"doc_count": len(names), "who": {"buckets": [{"key": n, "doc_count": 1} for n in names]}}
                    for artist, names in names_by_artist.items()
                }
            }
        },
        "config": CONFIG,
    }


def browse_client(handler) -> tuple[ArticCollectionBrowse, list[dict]]:
    """The real client over a recorded transport, plus every body it sent."""
    sent: list[dict] = []

    def record(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        sent.append(body)
        return handler(body)

    client = httpx.Client(transport=httpx.MockTransport(record))
    return ArticCollectionBrowse(user_agent=USER_AGENT, client=client), sent


def type_filtered(body: dict) -> bool:
    """Whether this request restricts to the wall-appropriate artwork types."""
    clauses = body.get("query", {}).get("bool", {}).get("filter", [])
    return any("terms" in clause and "artwork_type_title.keyword" in clause["terms"] for clause in clauses)


def asked_for(body: dict) -> set[str]:
    """The artist strings this request actually searches on.

    Read out of the `should` clause rather than by looking for a name anywhere in
    the body: on the retry path the bucket is *labelled* with the run's spelling
    while the query carries the surname, so both strings are present and only one
    of them is what was asked.
    """
    clauses = body.get("query", {}).get("bool", {}).get("filter", [])
    return {
        should["match"]["artist_title"]["query"]
        for clause in clauses
        for should in clause.get("bool", {}).get("should", [])
        if "match" in should
    }


def test_one_run_is_one_request_when_every_artist_is_held():
    """The whole run's facets travel in one POST, not one per artist.

    Asserted on the count rather than described, because the per-facet
    aggregation exists precisely so the request does not multiply with the work
    list — and nothing else would notice if it started to.
    """
    client, sent = browse_client(
        lambda body: httpx.Response(
            200,
            json=a_response(
                {
                    "Ellsworth Kelly": a_facet_bucket(a_hit("Train Landscape", "Ellsworth Kelly", work_id=1), matched=56),
                    "Morris Louis": a_facet_bucket(a_hit("Earth", "Morris Louis", work_id=2), matched=2),
                }
            ),
        )
    )

    groups = client.browse([BrowseQuery(artist="Ellsworth Kelly"), BrowseQuery(artist="Morris Louis")], per_query=3)

    assert len(sent) == 1, "a browse asked the collection more than once for a run that had no misses"
    assert [group.query.artist for group in groups] == ["Ellsworth Kelly", "Morris Louis"]
    assert [group.matched for group in groups] == [56, 2]


def test_a_work_carries_the_collections_own_title_and_attribution():
    """What comes back is the collection's record, not an echo of the query."""
    client, _ = browse_client(
        lambda body: httpx.Response(
            200,
            json=a_response(
                {
                    "Claude Monet": a_facet_bucket(
                        a_hit("Stacks of Wheat (End of Day, Autumn)", "Claude Monet", work_id=64818, public_domain=True),
                        matched=46,
                    )
                }
            ),
        )
    )

    (group,) = client.browse([BrowseQuery(artist="Claude Monet")], per_query=3)
    (work,) = group.works

    assert work.title == "Stacks of Wheat (End of Day, Autumn)"
    assert work.artist == "Claude Monet"
    assert work.provider == PROVIDER
    assert work.url == "https://api.artic.edu/api/v1/artworks/64818"
    assert work.preview_url == "https://www.artic.edu/iiif/2/image-64818/full/843,/0/default.jpg"
    assert work.estimated_width == 6000 and work.estimated_height == 4500
    assert work.rights_status is RightsStatus.PUBLIC_DOMAIN
    assert work.source_class is SourceClass.INSTITUTIONAL
    assert work.acquisition_method is AcquisitionMethod.DEZOOMIFY


def test_matched_is_the_collections_total_and_not_what_came_back():
    """The count a rationale quotes is the collection's, before any cap.

    "Offered one work by this artist" reads differently when the collection holds
    one and when it holds four hundred, which is why the brief requires the
    figure and why it cannot be `len(works)`.
    """
    client, _ = browse_client(
        lambda body: httpx.Response(
            200,
            json=a_response(
                {
                    "Ellsworth Kelly": a_facet_bucket(
                        a_hit("Train Landscape", "Ellsworth Kelly", work_id=1),
                        a_hit("Tableau Vert", "Ellsworth Kelly", work_id=2),
                        matched=56,
                    )
                }
            ),
        )
    )

    (group,) = client.browse([BrowseQuery(artist="Ellsworth Kelly")], per_query=2)

    assert group.matched == 56
    assert len(group.works) == 2


def test_an_artist_the_collection_does_not_hold_yields_a_group_with_no_works():
    """Asked and empty is reported, never dropped.

    A dropped facet is indistinguishable from one nobody asked about, and the
    difference is exactly what tells a curator the collection was consulted.
    """
    client, _ = browse_client(
        lambda body: httpx.Response(
            200,
            json=(
                a_response({"Johannes Vermeer": a_facet_bucket(matched=0)})
                if type_filtered(body)
                # The surname retry's check: the collection knows no Vermeer at all.
                else a_vocabulary_response({"Johannes Vermeer": []})
            ),
        )
    )

    (group,) = client.browse([BrowseQuery(artist="Johannes Vermeer")], per_query=3)

    assert group.query.artist == "Johannes Vermeer"
    assert group.matched == 0
    assert group.works == ()


def test_a_name_the_museum_spells_differently_is_recovered_by_surname():
    """ "Wassily Kandinsky" finds the twenty-four filed under "Vasily Kandinsky".

    And it comes back under the spelling the *run* used, because that is the
    facet a curator asked about; the work itself still carries the collection's
    own attribution.
    """

    def handler(body):
        if not type_filtered(body):
            return httpx.Response(200, json=a_vocabulary_response({"Wassily Kandinsky": ["vasily kandinsky"]}))
        if asked_for(body) == {"Kandinsky"}:
            return httpx.Response(
                200,
                json=a_response(
                    {
                        "Wassily Kandinsky": a_facet_bucket(
                            a_hit("Improvisation No. 30", "Vasily Kandinsky", work_id=8991), matched=21
                        )
                    }
                ),
            )
        return httpx.Response(200, json=a_response({"Wassily Kandinsky": a_facet_bucket(matched=0)}))

    client, sent = browse_client(handler)

    (group,) = client.browse([BrowseQuery(artist="Wassily Kandinsky")], per_query=3)

    assert group.query.artist == "Wassily Kandinsky", "the group must answer under the spelling the run used"
    assert group.matched == 21
    (work,) = group.works
    assert work.artist == "Vasily Kandinsky", "the work keeps the collection's own attribution"
    assert len(sent) == 3, "expected the miss, the ambiguity check, and the retry"


def test_a_surname_two_artists_share_is_never_retried():
    """The Martorell case, and the reason the ambiguity check must be unfiltered.

    The collection holds one Antonio Martorell — a `Graphic Design` that the
    wall-type filter removes — and one Bernat Martorell painting. **A check that
    inherited the browse's own filters would see only Bernat, call the surname
    unambiguous, and offer his painting to a run that named Antonio.** The
    transport reproduces exactly that asymmetry, so an implementation that scopes
    the check wrongly fails here by offering a work rather than by looking wrong.
    """

    def handler(body):
        if type_filtered(body):
            if asked_for(body) == {"Martorell"}:
                # The retry, if the implementation wrongly got this far.
                return httpx.Response(
                    200,
                    json=a_response(
                        {"Antonio Martorell": a_facet_bucket(a_hit("Saint George", "Bernat Martorell", work_id=3), matched=1)}
                    ),
                )
            return httpx.Response(200, json=a_response({"Antonio Martorell": a_facet_bucket(matched=0)}))
        # Unfiltered, the collection names both. Filtered, it would name one.
        return httpx.Response(200, json=a_vocabulary_response({"Antonio Martorell": ["antonio martorell", "bernat martorell"]}))

    client, sent = browse_client(handler)

    (group,) = client.browse([BrowseQuery(artist="Antonio Martorell")], per_query=3)

    assert group.works == (), "a surname two artists share was retried, offering the wrong artist's work"
    assert group.matched == 0
    assert len(sent) == 2, "expected the miss and the ambiguity check, and no retry"


def test_a_single_word_name_is_not_retried_against_itself():
    """Nothing is gained by asking the same question twice.

    A one-word name has no surname to fall back to, so the retry would repeat the
    query that just returned nothing — a request whose answer is already known.
    """
    client, sent = browse_client(lambda body: httpx.Response(200, json=a_response({"Banksy": a_facet_bucket(matched=0)})))

    (group,) = client.browse([BrowseQuery(artist="Banksy")], per_query=3)

    assert group.works == ()
    assert len(sent) == 1, "a one-word name has no surname to retry, so nothing should follow the miss"


def test_the_collection_being_unreachable_is_its_own_failure():
    """Not an empty collection — a different fact, and the caller must tell them apart."""
    client, _ = browse_client(lambda body: httpx.Response(503, json={"error": "unavailable"}))

    with pytest.raises(CollectionBrowseFailure):
        client.browse([BrowseQuery(artist="Claude Monet")], per_query=3)


def test_a_response_carrying_no_aggregation_is_an_empty_browse():
    """The collection answered; what it answered holds nothing.

    A missing aggregation is a shape failure the run should survive: a browse is
    a supplement, and losing it must not take the run down with it.
    """
    client, _ = browse_client(lambda body: httpx.Response(200, json={"data": [], "config": CONFIG}))

    (group,) = client.browse([BrowseQuery(artist="Claude Monet")], per_query=3)

    assert group.matched == 0 and group.works == ()


def test_asking_for_nothing_asks_the_collection_nothing():
    """A run with no artists to supplement from spends no request."""
    client, sent = browse_client(lambda body: httpx.Response(500, json={}))

    assert client.browse([], per_query=3) == ()
    assert client.browse([BrowseQuery(artist="  ")], per_query=3)[0].works == ()
    assert client.browse([BrowseQuery(artist="Monet")], per_query=0)[0].works == ()
    assert sent == []


def test_a_record_without_dimensions_cannot_be_offered():
    """The floor is applied above this seam, and needs a size to apply.

    A record kept without dimensions would be indistinguishable from one that
    clears the floor, which is the single thing the floor exists to make visible.
    """
    hit = a_hit("Untitled", "Claude Monet", work_id=9)
    del hit["_source"]["thumbnail"]
    client, _ = browse_client(lambda body: httpx.Response(200, json=a_response({"Claude Monet": a_facet_bucket(hit, matched=1)})))

    (group,) = client.browse([BrowseQuery(artist="Claude Monet")], per_query=3)

    assert group.works == ()
    assert group.matched == 1, "the collection still matched it; it is simply not offerable"


def test_a_browse_hit_is_kept_even_if_it_arrives_with_a_zero_score():
    """A filter chose it, so there is no ranking to disqualify it.

    The per-work search drops a zero-scored record because a record matching no
    query term cannot be the work that was asked for. A browse asks nothing to
    match — the record is in the answer because it passed a filter — so the same
    rule applied here would silently discard real holdings the day this API
    starts including `_score` in an aggregation's `_source`.
    """
    hit = a_hit("Train Landscape", "Ellsworth Kelly", work_id=1)
    hit["_source"]["_score"] = 0.0
    client, _ = browse_client(
        lambda body: httpx.Response(200, json=a_response({"Ellsworth Kelly": a_facet_bucket(hit, matched=56)}))
    )

    (group,) = client.browse([BrowseQuery(artist="Ellsworth Kelly")], per_query=3)

    assert [work.title for work in group.works] == ["Train Landscape"]


def test_a_name_with_a_parenthesised_alias_retries_on_the_name_itself():
    """ "Titian (Tiziano Vecellio)" retries as "Titian", not as "Vecellio)".

    The model supplies these constantly. Stripping the aside leaves a single word,
    which is still a retry worth making — it differs from the name that failed —
    and taking the last word of the raw string instead would ask the collection
    about a fragment with a bracket on it.

    Whether the retry then *recovers* anything is the ambiguity check's decision,
    so this uses a name it lets through; the real Titian is refused, and correctly.
    """

    def handler(body):
        if not type_filtered(body):
            return httpx.Response(200, json=a_vocabulary_response({"Kandinsky (Wassily)": ["vasily kandinsky"]}))
        if asked_for(body) == {"Kandinsky"}:
            return httpx.Response(
                200,
                json=a_response(
                    {"Kandinsky (Wassily)": a_facet_bucket(a_hit("Improvisation", "Vasily Kandinsky", work_id=2), matched=21)}
                ),
            )
        return httpx.Response(200, json=a_response({"Kandinsky (Wassily)": a_facet_bucket(matched=0)}))

    client, sent = browse_client(handler)

    (group,) = client.browse([BrowseQuery(artist="Kandinsky (Wassily)")], per_query=3)

    assert group.matched == 21, "the parenthesised name was not retried on the name itself"
    assert asked_for(sent[-1]) == {"Kandinsky"}


def test_a_bucket_whose_top_hits_are_null_is_an_empty_facet_rather_than_a_crash():
    """The museum sending `null` where an object was expected must not fail a run.

    A chained unwrap raises `AttributeError` here, which escapes a caller that
    catches only a browse failure and ends an otherwise successful run as an
    unexplained fault — the opposite of a supplement that must not take a run
    down with it. Distinct from a *missing* aggregation, which the chained form
    already survived, so that test could not have caught this.
    """
    for bucket in (
        {"doc_count": 5, "top": None},
        {"doc_count": 5, "top": {"hits": None}},
        {"doc_count": 5, "top": {"hits": {"hits": None}}},
        {"doc_count": 5},
    ):
        client, _ = browse_client(lambda body, b=bucket: httpx.Response(200, json=a_response({"Claude Monet": b})))

        (group,) = client.browse([BrowseQuery(artist="Claude Monet")], per_query=3)

        assert group.works == ()
        assert group.matched == 5, "the facet still matched; it simply carried no readable hits"
