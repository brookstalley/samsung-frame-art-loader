"""The thousands-scale corpus fixture, and proof it works.

This is preparation for Chunk 06 of `build-plan-curation-ux.md`, not Chunk 06
itself: that chunk measures search latency over a seeded thousands-scale
corpus and settles whether the answer is SQLite FTS5 or a `LIKE` scan. Nothing
here builds `WorkFacet`, a `q` parameter, or facet counts — those are that
chunk's own deliverables. What this proves is narrower: that
`build_large_catalogue` (in `conftest.py`) is deterministic, and that the
works it writes are real rows a test can find again through the query path
that exists today — `CatalogueService.list_artworks`, paged. Chunk 06 builds
search on top of that same store; this is the fixture waiting for it.
"""

from curation.services.catalogue import MAX_LIST_LIMIT


class TestDeterminism:
    """Same seed, two independent stores, identical corpus.

    A latency number is only comparable across runs if the corpus behind it
    does not silently change shape, so this is checked directly rather than
    trusted from reading `build_large_catalogue`'s source. Built small (200
    works) and through the `build_catalogue` factory rather than the
    `_LARGE_CORPUS_SIZE` session fixture, so this costs nothing beyond what it
    is actually checking.
    """

    def test_the_same_seed_writes_the_same_titles_in_the_same_order(self, build_catalogue):
        _, first = build_catalogue(size=200, seed=20260812)
        _, second = build_catalogue(size=200, seed=20260812)

        assert [work.title for work in first] == [work.title for work in second]
        assert [work.date_created for work in first] == [work.date_created for work in second]
        assert [work.description for work in first] == [work.description for work in second]

    def test_a_different_seed_writes_a_different_corpus(self, build_catalogue):
        _, first = build_catalogue(size=200, seed=20260812)
        _, second = build_catalogue(size=200, seed=1)

        assert [work.title for work in first] != [work.title for work in second]


class TestTheSeededCorpus:
    """The session-scoped 4,000-work corpus itself."""

    def test_it_holds_the_size_it_promises(self, large_catalogue_service, large_corpus_size):
        assert large_catalogue_service.list_artworks(limit=1).total == large_corpus_size

    def test_titles_are_not_all_the_same_string(self, large_catalogue_works):
        """A corpus where every title is `Work 0001` measures nothing — CLAUDE.md's own example."""
        titles = {work.title for work in large_catalogue_works}
        assert len(titles) > 100

    def test_artists_are_shared_by_some_works_and_rare_for_others(self, large_catalogue_service, large_catalogue_works):
        """Some artists hold many works, some hold one — not a flat distribution."""
        artist_ids = [work.artist_id for work in large_catalogue_works if work.artist_id is not None]
        counts: dict[str, int] = {}
        for artist_id in artist_ids:
            counts[artist_id] = counts.get(artist_id, 0) + 1

        assert max(counts.values()) >= 20, "no artist holds many works — the skew did not take"
        assert sum(1 for count in counts.values() if count == 1) >= 5, "no artist holds only one work"

    def test_a_known_work_is_reachable_through_the_listing_the_product_offers_today(
        self, large_catalogue_service, large_catalogue_works
    ):
        """Proof the corpus is queryable, using `list_artworks` — the only listing that exists before Chunk 06.

        Paged with the service's own `MAX_LIST_LIMIT`, the way a real caller is
        made to, rather than asking the store for everything at once.
        """
        target = large_catalogue_works[0]

        found = None
        offset = 0
        while True:
            page = large_catalogue_service.list_artworks(limit=MAX_LIST_LIMIT, offset=offset)
            match = next((entry for entry in page.entries if entry.artwork.id == target.id), None)
            if match is not None:
                found = match
                break
            if not page.truncated:
                break
            offset += MAX_LIST_LIMIT

        assert found is not None, "the corpus's own first work was not reachable through list_artworks"
        assert found.artwork.title == target.title
        assert found.artwork.date_created == target.date_created
