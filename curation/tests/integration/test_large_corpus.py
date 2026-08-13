"""The thousands-scale corpus fixture, and proof it works.

The fixture exists so that whether text search needs SQLite FTS5 or whether a
`LIKE` scan suffices can be *measured* rather than guessed — a question the real
collection is far too small to answer. This module does not build search and
does not measure it. What it proves is narrower, and is what a measurement would
otherwise silently assume: that `build_large_catalogue` (in `conftest.py`) is
deterministic, so two latency numbers are comparable, and that the works it
writes are real rows findable again through the query path that exists today,
`CatalogueService.list_artworks`, paged. A corpus that seeded differently each
run, or wrote rows nothing could read back, would produce numbers that looked
fine and meant nothing.
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

    **Read back through the store rather than off the builder's return value.**
    What a measurement queries is the rows, so the rows are what has to be
    reproducible; asserting over what `build_large_catalogue` handed back would
    pass just as happily if nothing it built ever reached the database.
    Compared as multisets, because stored order is not reproducible and nothing
    here depends on it — `_BY_TITLE` tiebreaks on a `uuid4` id, and works share
    a title often enough for that tiebreak to bite.
    """

    @staticmethod
    def _stored(service):
        rows = []
        offset = 0
        while True:
            page = service.list_artworks(limit=MAX_LIST_LIMIT, offset=offset)
            rows.extend((entry.artwork.title, entry.artwork.date_created, entry.artwork.description) for entry in page.entries)
            if not page.truncated:
                return sorted(rows)
            offset += MAX_LIST_LIMIT

    def test_the_same_seed_writes_the_same_rows(self, build_catalogue):
        first_service, _ = build_catalogue(size=200, seed=20260812)
        second_service, _ = build_catalogue(size=200, seed=20260812)

        assert self._stored(first_service) == self._stored(second_service)

    def test_a_different_seed_writes_a_different_corpus(self, build_catalogue):
        first_service, _ = build_catalogue(size=200, seed=20260812)
        second_service, _ = build_catalogue(size=200, seed=1)

        assert self._stored(first_service) != self._stored(second_service)


class TestTheSeededCorpus:
    """The session-scoped 4,000-work corpus itself."""

    def test_it_holds_the_size_it_promises(self, large_catalogue_service, large_corpus_size):
        assert large_catalogue_service.list_artworks(limit=1).total == large_corpus_size

    def test_titles_are_not_all_the_same_string(self, large_catalogue_works):
        """A corpus where every title is `Work 0001` measures nothing — CLAUDE.md's own example."""
        titles = {work.title for work in large_catalogue_works}
        assert len(titles) > 100

    def test_the_corpus_offers_selective_terms_to_search_for(self, large_catalogue_works, large_corpus_size):
        """Selectivity, which is the property the whole fixture exists to provide.

        A full scan pays for every row whatever it is asked; an index pays in
        proportion to what matches. They therefore only diverge where something
        selective can be *asked for*, and a corpus that offers no selective term
        cannot distinguish the two strategies however carefully the latency
        around it is measured — it would look like evidence and be none. An
        earlier version of this fixture crossed 18 openers with 18 closers and
        nothing else, so 4,000 works carried 324 distinct titles: every title
        was shared with about a dozen others and there was nothing selective to
        ask for.

        **What is pinned here is distinctness, not word frequency.** Individual
        common words staying common is correct — "Untitled" and "Study" really
        do recur across a real collection, and a search for one really does
        match a lot of it. Bars are loose and set from measurement (63.6%
        distinct titles, commonest title 11 rows, at the defaults on
        2026-08-12); they guard the failure mode rather than fixing a number.
        """
        titles = [work.title for work in large_catalogue_works]
        distinct = len(set(titles)) / large_corpus_size
        assert distinct > 0.5, f"only {distinct:.1%} of titles are distinct — nothing selective to search for"

        counts: dict[str, int] = {}
        for title in titles:
            counts[title] = counts.get(title, 0) + 1
        commonest, hits = max(counts.items(), key=lambda pair: pair[1])
        share = hits / large_corpus_size
        assert share < 0.01, f"{commonest!r} is {share:.1%} of the corpus — titles collapse too far"

        # Descriptions carry the movement, subject, place and provenance text a
        # curator would search across, so they are a searchable field in their
        # own right and collapse the same way titles did if left uncrossed.
        descriptions = [work.description for work in large_catalogue_works]
        distinct_descriptions = len(set(descriptions)) / large_corpus_size
        assert distinct_descriptions > 0.5, f"only {distinct_descriptions:.1%} of descriptions are distinct"

    def test_artists_are_shared_by_some_works_and_rare_for_others(self, large_catalogue_works):
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
        """Proof the corpus is queryable through the listing that exists today.

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
