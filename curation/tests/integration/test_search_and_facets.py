"""Retrieval at the scale it was made mandatory for, and over the real surfaces.

`nonfunctional-requirements.md` moved the catalogue target from hundreds of works
to thousands and made search a requirement rather than an option. What follows
runs against the seeded corpus at that scale, because the rules this chunk
implements are the ones that look correct at 41 works whatever they do.

**The acceptance criterion has its own class**: *no filter combination the control
offers can return an unexplained empty grid.* That is checked by taking the
control at its word — every option it offers as enabled, from several starting
states — rather than by reading the query that produces it.

The HTTP and MCP halves are here rather than with their neighbours because they
are the same claim arriving twice: an agent and a click must not disagree about
the same catalogue, and the filters landed on both surfaces together.
"""

import json

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from curation.persistence.records import FacetDerivation, VocabularyKind
from curation.services.catalogue import MAX_LIST_LIMIT

#: Filter states an option is added to. The empty one is the collection's first
#: screen; the others are a curator part-way through narrowing, which is where a
#: count computed against the wrong set stops being obvious.
_STARTING_POINTS = (
    {},
    {"movement": ["Impressionism"]},
    {"era": ["19th c."], "subject": ["Seascape"]},
)


def enabled(listing, kind: VocabularyKind):
    return [option for option in _group(listing, kind).options if not option.disabled]


def _group(listing, kind: VocabularyKind):
    return next(group for group in listing.facets if group.kind is kind)


class TestSearchOverTheSeededCorpus:
    """Text search against 4,000 works, through the service the surfaces call."""

    def test_a_selective_term_finds_only_the_works_that_carry_it(self, large_catalogue_service, large_catalogue_works):
        """`Ostend` is one of the corpus's places: in some titles, some descriptions, most neither."""
        expected = {work.id for work in large_catalogue_works if "ostend" in f"{work.title} {work.description}".lower()}
        assert 0 < len(expected) < len(large_catalogue_works), "the term is not selective, so this proves nothing"

        found = set()
        offset = 0
        while True:
            page = large_catalogue_service.list_artworks(q="Ostend", limit=MAX_LIST_LIMIT, offset=offset)
            found.update(entry.artwork.id for entry in page.entries)
            if not page.truncated:
                break
            offset += MAX_LIST_LIMIT

        assert found == expected

    def test_a_term_nothing_carries_finds_nothing_and_says_so(self, large_catalogue_service):
        listing = large_catalogue_service.list_artworks(q="zzzznothing")

        assert (listing.total, list(listing.entries)) == (0, [])
        # The vocabulary is still there, every option at zero — which is what
        # tells a curator the search emptied the grid rather than the catalogue.
        assert [group.kind for group in listing.facets] == list(VocabularyKind)
        assert all(option.count == 0 for option in _group(listing, VocabularyKind.MOVEMENT).options)

    def test_a_second_word_narrows(self, large_catalogue_service):
        broad = large_catalogue_service.list_artworks(q="tradition").total
        narrowed = large_catalogue_service.list_artworks(q="tradition Ostend").total

        assert broad == 4000
        assert 0 < narrowed < broad

    def test_a_search_reaches_an_artist_by_name(self, large_catalogue_service, large_catalogue_works):
        """The join the search clause carries, exercised where it costs something."""
        busiest = _group(large_catalogue_service.list_artworks(), VocabularyKind.ARTIST).options[0]

        listing = large_catalogue_service.list_artworks(q=busiest.value, limit=1)

        assert listing.total >= busiest.count


class TestFacetsOverTheSeededCorpus:
    def test_every_kind_the_corpus_carries_comes_back_with_counts(self, large_catalogue_service, large_corpus_size):
        listing = large_catalogue_service.list_artworks(limit=1)

        movements = _group(listing, VocabularyKind.MOVEMENT)
        assert movements.total_values == 17, "the corpus's own movement table is 17 long"
        assert sum(option.count for option in movements.options) == large_corpus_size
        # Every work carries exactly one of each of these, so the counts partition
        # the corpus — which is the shape that makes a wrong count visible.
        for kind in (VocabularyKind.ERA, VocabularyKind.SUBJECT, VocabularyKind.MEDIUM):
            assert sum(option.count for option in _group(listing, kind).options) == large_corpus_size

    def test_a_kind_nothing_infers_is_an_empty_group_rather_than_a_missing_one(self, large_catalogue_service):
        palette = _group(large_catalogue_service.list_artworks(limit=1), VocabularyKind.PALETTE)

        assert (palette.options, palette.total_values, palette.truncated) == ([], 0, False)

    def test_the_artist_rail_is_capped_and_says_how_much_it_is_not_showing(self, large_catalogue_service):
        """Hundreds of artists is a scroll rather than a choice, so the list is cut.

        The cut is by count, so what survives is what most of the collection
        actually is — and `total_values` is what lets the control say "50 of 393"
        instead of implying the vocabulary is fifty long.
        """
        artists = _group(large_catalogue_service.list_artworks(limit=1), VocabularyKind.ARTIST)

        assert artists.truncated is True
        assert artists.total_values > len(artists.options)
        assert [option.count for option in artists.options] == sorted((option.count for option in artists.options), reverse=True)

    def test_selecting_a_movement_narrows_era_at_scale(self, large_catalogue_service):
        """The corpus draws a movement's year from that movement's own period.

        Nothing in the query layer knows that; it falls out of the works carrying
        both facets, which is what `information-architecture.md` says it should do
        rather than needing a rule of its own.
        """
        listing = large_catalogue_service.list_artworks(facets={"movement": ["Baroque"]}, limit=1)
        eras = {option.value: option.count for option in _group(listing, VocabularyKind.ERA).options}

        assert eras["17th c."] > 0
        assert eras["18th c."] > 0
        assert eras["20th c."] == 0
        assert eras["21st c."] == 0

    def test_a_facet_count_does_not_move_when_its_own_selection_does(self, large_catalogue_service):
        """The exclusion rule, stated as the invariant a curator relies on.

        Whatever the curator picks in the movement control, every *other*
        movement's count stays what it was — because none of them is computed
        through the movement filter. Without the rule, choosing Baroque takes
        every other movement to zero and the control can only be cleared.
        """
        before = {
            option.value: option.count
            for option in _group(large_catalogue_service.list_artworks(limit=1), VocabularyKind.MOVEMENT).options
        }
        after = {
            option.value: option.count
            for option in _group(
                large_catalogue_service.list_artworks(facets={"movement": ["Baroque"]}, limit=1), VocabularyKind.MOVEMENT
            ).options
        }

        assert after == before


class TestNoOfferedFilterCanEmptyTheGrid:
    """The chunk's acceptance criterion, taken at the control's word.

    For each starting state, every option the control offers as *enabled* is
    added to the filter and the result must be non-empty. This is the criterion
    itself rather than a proxy for it: it fails if the counts are computed over
    the wrong set, if a zero option is left enabled, or if adding a value to a
    kind that already has one narrowed instead of widening.

    Run over a smaller corpus built by the same builder, so every option of every
    kind can be tried rather than a sample of them — 300 works still hold values
    with counts of one, which is where an off-by-one in the counting shows.
    """

    @pytest.fixture
    def small_corpus(self, build_catalogue):
        """300 works from the same builder as the session corpus, same seed.

        Built here rather than reusing `large_catalogue_service` because this
        walks *every* option of every kind: at 4,000 works the artist rail alone
        offers fifty, and a sampled walk is exactly the shape that reports a
        criterion met against the combinations that happen to work.
        """
        service, _ = build_catalogue(size=300, seed=20260812)
        return service

    @pytest.mark.parametrize("starting_point", _STARTING_POINTS, ids=["nothing chosen", "one movement", "era and subject"])
    def test_every_enabled_option_selects_at_least_one_work(self, small_corpus, starting_point):
        listing = small_corpus.list_artworks(facets=starting_point, limit=1)
        tried = 0

        for kind in VocabularyKind:
            for option in enabled(listing, kind):
                chosen = dict(starting_point)
                # Added to whatever that kind already holds, which is what a
                # control does: several values in one kind mean *either*.
                chosen[str(kind)] = [*chosen.get(str(kind), []), option.value]
                result = small_corpus.list_artworks(facets=chosen, limit=1)
                tried += 1
                assert result.total > 0, f"{kind}={option.value!r} was offered at {option.count} and selected nothing"

        assert tried > 20, f"only {tried} options were tried — the corpus offers too little to prove anything"

    def test_a_disabled_option_really_would_have_emptied_the_grid(self, small_corpus):
        """The other half: the ones it greys out are greyed out for a reason.

        Without this, a control that disabled everything would pass the test
        above by offering nothing — which is the trivially safe answer and the one
        that makes the collection unfilterable.
        """
        listing = small_corpus.list_artworks(facets={"movement": ["Colour Field"]}, limit=1)
        blocked = [option for option in _group(listing, VocabularyKind.ERA).options if option.disabled]

        assert blocked, "no era is impossible under Colour Field, so this proves nothing"
        for option in blocked:
            assert small_corpus.list_artworks(facets={"movement": ["Colour Field"], "era": [option.value]}).total == 0


class TestTheHttpSurface:
    @pytest.fixture
    def faceted_http(self, server_url, seeded_service):
        """The booted server, with facets recorded on the works it already serves."""
        for title, movement, era in (
            ("Nighthawks", "Realism", "20th c."),
            ("The Persistence of Memory", "Surrealism", "20th c."),
            ("I Saw the Figure 5 in Gold", "Precisionism", "20th c."),
        ):
            work = next(entry.artwork for entry in seeded_service.list_artworks().entries if entry.artwork.title == title)
            seeded_service.record_facet(
                artwork_id=work.id, kind=VocabularyKind.MOVEMENT, value=movement, derivation=FacetDerivation.INFERRED
            )
            seeded_service.record_facet(
                artwork_id=work.id, kind=VocabularyKind.ERA, value=era, derivation=FacetDerivation.INFERRED
            )
        with httpx.Client(base_url=server_url, timeout=30.0) as client:
            yield client

    def test_a_page_carries_its_facet_controls(self, faceted_http):
        payload = faceted_http.get("/api/works").raise_for_status().json()

        assert [group["kind"] for group in payload["facets"]] == [str(kind) for kind in VocabularyKind]
        movement = next(group for group in payload["facets"] if group["kind"] == "movement")
        assert {option["value"]: option["count"] for option in movement["options"]} == {
            "Precisionism": 1,
            "Realism": 1,
            "Surrealism": 1,
        }

    def test_a_repeated_parameter_means_either(self, faceted_http):
        payload = (
            faceted_http.get("/api/works", params=[("movement", "Realism"), ("movement", "Surrealism")]).raise_for_status().json()
        )

        assert payload["total"] == 2
        assert {work["title"] for work in payload["works"]} == {"Nighthawks", "The Persistence of Memory"}

    def test_two_kinds_mean_both_and_an_impossible_pair_comes_back_disabled(self, faceted_http):
        payload = faceted_http.get("/api/works", params={"movement": "Realism"}).raise_for_status().json()
        era = next(group for group in payload["facets"] if group["kind"] == "era")

        # One era in this catalogue and every work is in it, so nothing is
        # disabled here — the disabled case is pinned in the unit suite. What
        # this holds is that the flag travels at all.
        assert [option["disabled"] for option in era["options"]] == [False]
        assert payload["total"] == 1

    def test_free_text_reaches_the_route(self, faceted_http):
        payload = faceted_http.get("/api/works", params={"q": "nighthawks"}).raise_for_status().json()

        assert [work["title"] for work in payload["works"]] == ["Nighthawks"]

    def test_a_work_states_its_own_facets(self, faceted_http):
        listed = faceted_http.get("/api/works", params={"q": "nighthawks"}).raise_for_status().json()
        detail = faceted_http.get(f"/api/works/{listed['works'][0]['artwork_id']}").raise_for_status().json()

        assert {(facet["kind"], facet["value"], facet["derivation"]) for facet in detail["facets"]} == {
            ("era", "20th c.", "inferred"),
            ("movement", "Realism", "inferred"),
        }

    def test_an_unknown_facet_kind_is_refused_rather_than_ignored(self, faceted_http):
        """FastAPI drops an unknown query parameter, so this asks the service's own way in.

        `?genre=Landscape` is simply not a parameter of this route and is ignored
        by the framework before any of this product's code sees it; what must not
        happen is the six named ones silently widening. This drives the refusal
        through the MCP surface's spelling of the same filter set below, and holds
        here only that a *known* kind with an unknown value is an empty result and
        not an error.
        """
        payload = faceted_http.get("/api/works", params={"movement": "Vorticism"}).raise_for_status().json()

        assert payload["total"] == 0
        chosen = next(
            option
            for group in payload["facets"]
            if group["kind"] == "movement"
            for option in group["options"]
            if option["value"] == "Vorticism"
        )
        assert (chosen["selected"], chosen["count"], chosen["disabled"]) == (True, 0, False)


class TestTheToolSurface:
    """`art_catalogue(action='list')` takes the same filters and answers with the same counts."""

    @staticmethod
    async def call(server_url: str, **arguments) -> tuple[dict, bool]:
        async with streamable_http_client(f"{server_url}/mcp") as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("art_catalogue", arguments)
        return json.loads(result.content[0].text), bool(result.isError)

    @pytest.fixture
    def faceted_server(self, server_url, seeded_service):
        for title, movement in (("Nighthawks", "Realism"), ("The Persistence of Memory", "Surrealism")):
            work = next(entry.artwork for entry in seeded_service.list_artworks().entries if entry.artwork.title == title)
            seeded_service.record_facet(
                artwork_id=work.id, kind=VocabularyKind.MOVEMENT, value=movement, derivation=FacetDerivation.INFERRED
            )
        return server_url

    async def test_a_model_can_search(self, faceted_server):
        payload, errored = await self.call(faceted_server, action="list", q="memory")

        assert errored is False
        assert [work["title"] for work in payload["artworks"]] == ["The Persistence of Memory"]

    async def test_a_model_can_filter_by_facet_and_reads_the_counts_back(self, faceted_server):
        payload, errored = await self.call(faceted_server, action="list", movement=["Realism"])

        assert errored is False
        assert payload["total"] == 1
        movement = next(group for group in payload["facets"] if group["kind"] == "movement")
        # Counted with movement's own selection ignored, exactly as the browser
        # gets it — the surfaces answer the same question the same way.
        assert {option["value"]: option["count"] for option in movement["values"]} == {"Realism": 1, "Surrealism": 1}
        assert [option["selected"] for option in movement["values"]] == [True, False]

    async def test_a_facet_value_that_is_not_a_string_is_refused_by_name(self, faceted_server):
        payload, errored = await self.call(faceted_server, action="list", movement=[7])

        assert errored is True
        assert "array of string" in payload["error"]

    async def test_an_unlisted_kind_is_not_a_parameter_of_this_action(self, faceted_server):
        payload, errored = await self.call(faceted_server, action="list", genre=["Landscape"])

        assert errored is True
        assert "does not take 'genre'" in payload["error"]
