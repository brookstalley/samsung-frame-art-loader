"""What a work is, and the retrieval that stands on it.

The rules under test are `information-architecture.md` § Retrieval's three, and
they are rules about a *control* rather than about a query: each facet's counts
are computed over the results filtered by every other facet and never its own, a
zero option is disabled rather than hidden, and the counts are shown. The last is
a rendering concern; the first two are decided here and are what make the
acceptance criterion — no filter combination the control offers can return an
unexplained empty grid — a property rather than a hope.

**All of them are invisible at 41 works and ruinous at 4,000.** At the size the
catalogue is today every option has a count either way and every intersection is
non-empty, so a suite that only ever saw the real corpus would pass against a
control that had none of this. The catalogues built here are small and
*deliberately sparse*: each has combinations that do not exist.
"""

from dataclasses import replace

import pytest

from curation.persistence.catalogue import StorageError, WorkQuery
from curation.persistence.durable import SqliteDurableStore
from curation.persistence.file import open_catalogue_file
from curation.persistence.records import FacetDerivation, VocabularyKind
from curation.persistence.sqlite import CATALOGUE_SCHEMA, SqliteCatalogue
from curation.persistence.sqlite_discovery import DISCOVERY_SCHEMA
from curation.services.catalogue import MAX_FACET_VALUES, MAX_SEARCH_TERMS, CatalogueService
from curation.services.errors import ServiceError

#: A tiny corpus with a hole in it: no Baroque work is from the 20th century and
#: no Colour Field work is from the 17th, so "movement=Colour Field, era=17th c."
#: is exactly the dead end the first prototype offered and got an empty grid for.
_CORPUS = (
    ("Interior with Four Windows", "Baroque", "17th c.", "Interior"),
    ("The Weight of Salt", "Baroque", "17th c.", "Still life"),
    ("Nocturne in Blue Hour", "Impressionism", "19th c.", "Seascape"),
    ("Approach to the Quarry", "Impressionism", "19th c.", "Landscape"),
    ("Ground and Iron", "Colour Field", "20th c.", "Non-objective"),
)


@pytest.fixture
def faceted(service: CatalogueService) -> CatalogueService:
    """`_CORPUS`, written as works with movement, era and subject facets."""
    for title, movement, era, subject in _CORPUS:
        work = service.add_artwork(title=title)
        for kind, value in (
            (VocabularyKind.MOVEMENT, movement),
            (VocabularyKind.ERA, era),
            (VocabularyKind.SUBJECT, subject),
        ):
            service.record_facet(artwork_id=work.id, kind=kind, value=value, derivation=FacetDerivation.INFERRED)
    return service


def options(listing, kind: VocabularyKind) -> dict[str, int]:
    """One group's values and counts, by value."""
    group = next(group for group in listing.facets if group.kind is kind)
    return {option.value: option.count for option in group.options}


def group(listing, kind: VocabularyKind):
    return next(entry for entry in listing.facets if entry.kind is kind)


# -- the counting rule ---------------------------------------------------------


class TestAFacetIsNotCountedByItsOwnSelection:
    """The rule the collection stands on, and the one nothing else can substitute for."""

    def test_choosing_one_movement_leaves_the_others_countable(self, faceted):
        """A curator can change their mind about Baroque without first clearing Baroque.

        Counting movement by its own selection would leave exactly one non-zero
        option in the movement control — the value already chosen — so every other
        movement would be disabled and the only way out of the filter would be to
        clear it. That is a control you escape rather than adjust.
        """
        listing = faceted.list_artworks(facets={"movement": ["Baroque"]})

        assert listing.total == 2
        assert options(listing, VocabularyKind.MOVEMENT) == {"Baroque": 2, "Colour Field": 1, "Impressionism": 2}

    def test_another_facet_still_narrows_the_counts(self, faceted):
        """Excluded from its own selection only — everything else still applies.

        The failure this pins is the over-correction: dropping *all* the filters
        when counting a facet would make every option's count the whole
        catalogue's, and an option showing a count would then be able to select
        nothing.
        """
        listing = faceted.list_artworks(facets={"era": ["17th c."]})

        # Movement is counted over the 17th-century works, which are both Baroque.
        assert options(listing, VocabularyKind.MOVEMENT) == {"Baroque": 2, "Colour Field": 0, "Impressionism": 0}
        # Era is counted over everything, because era is the facet doing the filtering.
        assert options(listing, VocabularyKind.ERA) == {"17th c.": 2, "19th c.": 2, "20th c.": 1}

    def test_two_facets_each_ignore_only_themselves(self, faceted):
        listing = faceted.list_artworks(facets={"movement": ["Impressionism"], "subject": ["Seascape"]})

        assert listing.total == 1
        # Movement counted over the Seascapes: one, and it is Impressionist.
        assert options(listing, VocabularyKind.MOVEMENT) == {"Baroque": 0, "Colour Field": 0, "Impressionism": 1}
        # Subject counted over the Impressionist works: a seascape and a landscape.
        assert options(listing, VocabularyKind.SUBJECT) == {
            "Interior": 0,
            "Landscape": 1,
            "Non-objective": 0,
            "Seascape": 1,
            "Still life": 0,
        }

    def test_free_text_narrows_every_facet_including_a_chosen_one(self, faceted):
        """`q` is not a facet, so no facet is exempt from it.

        The exclusion rule is about a control ignoring *itself*. A search term
        belongs to none of the six controls, so dropping it while counting one of
        them would offer an option whose count no filter could reproduce.
        """
        listing = faceted.list_artworks(q="Nocturne", facets={"movement": ["Impressionism"]})

        assert listing.total == 1
        assert options(listing, VocabularyKind.MOVEMENT) == {"Baroque": 0, "Colour Field": 0, "Impressionism": 1}

    def test_without_drops_one_kind_and_keeps_the_rest(self):
        query = WorkQuery(facets={VocabularyKind.MOVEMENT: ("Baroque",), VocabularyKind.ERA: ("17th c.",)})

        narrowed = query.without(VocabularyKind.MOVEMENT)

        assert VocabularyKind.MOVEMENT not in narrowed.facets
        assert narrowed.facets[VocabularyKind.ERA] == ("17th c.",)
        # The original is untouched, which is what lets one query be counted six
        # different ways in one request.
        assert query.facets[VocabularyKind.MOVEMENT] == ("Baroque",)


# -- what the control is offered ----------------------------------------------


class TestAZeroOptionIsDisabledAndNotHidden:
    def test_an_impossible_combination_is_offered_greyed_out(self, faceted):
        """Colour Field is 20th century, so it has no 17th-century work at all.

        Hiding it would make the movement vocabulary shrink from three entries to
        one as the era was chosen, which reads as the catalogue having lost works
        rather than as an empty intersection.
        """
        listing = faceted.list_artworks(facets={"era": ["17th c."]})
        movement = group(listing, VocabularyKind.MOVEMENT)

        assert [option.value for option in movement.options] == ["Baroque", "Colour Field", "Impressionism"]
        assert {option.value: option.disabled for option in movement.options} == {
            "Baroque": False,
            "Colour Field": True,
            "Impressionism": True,
        }

    def test_a_chosen_value_stays_enabled_even_at_zero(self, faceted):
        """The one state an empty grid has to be escapable from.

        `movement=Colour Field` with `era=17th c.` selects nothing, and a shared
        link can arrive in exactly that state. If the chosen option were disabled
        along with every other zero, the control that turns the filter off would
        be the greyed-out one.
        """
        listing = faceted.list_artworks(facets={"movement": ["Colour Field"], "era": ["17th c."]})
        chosen = next(option for option in group(listing, VocabularyKind.MOVEMENT).options if option.value == "Colour Field")

        assert listing.total == 0
        assert (chosen.selected, chosen.count, chosen.disabled) == (True, 0, False)

    def test_a_value_the_catalogue_no_longer_holds_is_still_offered(self, faceted):
        """A filter naming nothing must still have a control that removes it."""
        listing = faceted.list_artworks(facets={"movement": ["Vorticism"]})
        offered = next(option for option in group(listing, VocabularyKind.MOVEMENT).options if option.value == "Vorticism")

        assert (offered.selected, offered.count, offered.disabled) == (True, 0, False)

    def test_a_kind_the_catalogue_holds_nothing_of_is_still_a_group(self, faceted):
        """Every kind comes back, so a rail does not appear and disappear."""
        assert [entry.kind for entry in faceted.list_artworks().facets] == list(VocabularyKind)
        assert group(faceted.list_artworks(), VocabularyKind.PALETTE).options == []


class TestSelectingAMovementNarrowsEraWithNoRuleSayingSo:
    """A movement implies its period, and that is a fact about the world.

    `information-architecture.md` records it as something that should fall out of
    derived facets rather than needing its own rule — but only if the underlying
    data carries both. This is what proves it falls out: nothing in the query
    layer knows that Baroque is 17th century.
    """

    def test_baroque_leaves_only_its_own_centuries_countable(self, faceted):
        listing = faceted.list_artworks(facets={"movement": ["Baroque"]})

        assert options(listing, VocabularyKind.ERA) == {"17th c.": 2, "19th c.": 0, "20th c.": 0}

    def test_the_same_holds_the_other_way_round(self, faceted):
        listing = faceted.list_artworks(facets={"era": ["20th c."]})

        assert options(listing, VocabularyKind.MOVEMENT) == {"Baroque": 0, "Colour Field": 1, "Impressionism": 0}


class TestTheOptionsAreOrderedAndBounded:
    def test_commonest_first_then_alphabetically(self, faceted):
        subjects = [option.value for option in group(faceted.list_artworks(), VocabularyKind.SUBJECT).options]

        # All five subjects hold one work each, so the tie-break is what shows.
        assert subjects == ["Interior", "Landscape", "Non-objective", "Seascape", "Still life"]

    def test_a_long_vocabulary_is_cut_and_says_it_was(self, service):
        for index in range(MAX_FACET_VALUES + 5):
            work = service.add_artwork(title=f"Work {index}")
            service.record_facet(
                artwork_id=work.id,
                kind=VocabularyKind.PALETTE,
                value=f"palette-{index:03d}",
                derivation=FacetDerivation.INFERRED,
            )

        palette = group(service.list_artworks(), VocabularyKind.PALETTE)

        assert len(palette.options) == MAX_FACET_VALUES
        assert palette.total_values == MAX_FACET_VALUES + 5
        assert palette.truncated is True

    def test_a_chosen_value_survives_the_cut(self, service):
        """Ordered by count, so a rare chosen value falls off the end — and must not.

        Every value here holds one work except the chosen one, which holds none:
        it sorts last by count and then by value, so nothing but the rule keeps it
        in the list. Without it the filter in force would have no control to
        remove it.
        """
        for index in range(MAX_FACET_VALUES + 5):
            work = service.add_artwork(title=f"Work {index}")
            service.record_facet(
                artwork_id=work.id,
                kind=VocabularyKind.PALETTE,
                value=f"palette-{index:03d}",
                derivation=FacetDerivation.INFERRED,
            )
        rare = service.add_artwork(title="The odd one")
        service.record_facet(
            artwork_id=rare.id, kind=VocabularyKind.PALETTE, value="zzz-rare", derivation=FacetDerivation.INFERRED
        )
        service.archive_artwork(rare.id)

        palette = group(service.list_artworks(status="accepted", facets={"palette": ["zzz-rare"]}), VocabularyKind.PALETTE)

        assert palette.options[-1].value == "zzz-rare"
        assert (palette.options[-1].selected, palette.options[-1].count) == (True, 0)
        assert len(palette.options) == MAX_FACET_VALUES + 1


# -- text search ---------------------------------------------------------------


class TestSearch:
    def test_a_term_matches_a_title_case_insensitively(self, faceted):
        assert [entry.artwork.title for entry in faceted.list_artworks(q="NOCTURNE").entries] == ["Nocturne in Blue Hour"]

    def test_a_term_matches_part_of_a_word(self, faceted):
        """A contains-match, not a whole-token one — which is why this is `LIKE`.

        FTS5 measured two orders of magnitude faster on the 4,000-work corpus and
        cannot answer this at all without the curator knowing to type a prefix
        operator. `tools/search_latency.py` carries the numbers.
        """
        assert [entry.artwork.title for entry in faceted.list_artworks(q="uarr").entries] == ["Approach to the Quarry"]

    def test_a_second_word_narrows_rather_than_widens(self, faceted):
        assert faceted.list_artworks(q="the").total == 2
        assert faceted.list_artworks(q="the Quarry").total == 1
        assert faceted.list_artworks(q="Quarry Windows").total == 0

    def test_a_facet_value_is_not_searched_as_text(self, faceted):
        """Chosen from a control that counts it, never typed at.

        Every work here carries a subject facet, and one of them is "Interior" —
        which is also a word in another work's title. A search finds the title and
        not the facet, so the two ways of narrowing stay distinguishable: one is
        exact and carries a count, the other is fuzzy and does not, and a result
        that mixed them could not say which had been used.
        """
        assert [entry.artwork.title for entry in faceted.list_artworks(q="Interior").entries] == ["Interior with Four Windows"]
        assert faceted.list_artworks(facets={"subject": ["Interior"]}).total == 1

    def test_a_term_reaches_the_artist_name(self, seeded_service):
        assert [entry.artwork.title for entry in seeded_service.list_artworks(q="Dalí").entries] == ["The Persistence of Memory"]

    def test_a_term_reaches_the_description_and_the_medium(self, service):
        work = service.add_artwork(title="Untitled", medium="Gouache on paper", description="A folded map, from the estate.")

        assert [entry.artwork.id for entry in service.list_artworks(q="gouache").entries] == [work.id]
        assert [entry.artwork.id for entry in service.list_artworks(q="folded").entries] == [work.id]

    def test_a_wildcard_a_curator_typed_is_a_wildcard_no_longer(self, service):
        """`%` and `_` are `LIKE`'s, not the curator's.

        Unescaped, a search for `%` matches every work in the catalogue and `_`
        matches every work with a character in the searched column — which reads
        as the filter having done nothing rather than as having matched
        everything, and is the shape that turns a search box into a way to lose
        your place. Escaped, each matches only a work whose text really holds that
        character, which is the second and rarer half: a curator searching for a
        work called "50% study" has to be able to find it.
        """
        literal = service.add_artwork(title="Discount 50% study")
        service.add_artwork(title="Nothing of the sort")

        assert [entry.artwork.id for entry in service.list_artworks(q="50%").entries] == [literal.id]
        assert [entry.artwork.id for entry in service.list_artworks(q="%").entries] == [literal.id]
        assert service.list_artworks(q="_").total == 0

    def test_a_blank_search_narrows_nothing(self, faceted):
        assert faceted.list_artworks(q="   ").total == len(_CORPUS)

    def test_a_pasted_paragraph_is_refused_rather_than_trimmed(self, faceted):
        """Terms narrow, so dropping the surplus would silently *broaden* the answer."""
        with pytest.raises(ServiceError, match=f"at most {MAX_SEARCH_TERMS} words"):
            faceted.list_artworks(q=" ".join(str(index) for index in range(MAX_SEARCH_TERMS + 1)))

    def test_status_and_search_apply_together(self, faceted):
        archived = next(entry for entry in faceted.list_artworks(q="Nocturne").entries)
        faceted.archive_artwork(archived.artwork.id)

        assert faceted.list_artworks(q="Nocturne", status="accepted").total == 0
        assert faceted.list_artworks(q="Nocturne", status="archived").total == 1

    def test_the_facet_vocabulary_follows_the_status_filter(self, faceted):
        """Status is the one axis applied to the vocabulary itself, not only the counts.

        An archived-only view offering the whole catalogue's movements would list
        options that cannot be reached from where the curator is standing.
        """
        colour_field = next(entry for entry in faceted.list_artworks(facets={"movement": ["Colour Field"]}).entries)
        faceted.archive_artwork(colour_field.artwork.id)

        archived = group(faceted.list_artworks(status="archived"), VocabularyKind.MOVEMENT)

        assert [option.value for option in archived.options] == ["Colour Field"]


class TestARefusalNamesWhatWouldHaveWorked:
    def test_an_unknown_facet_kind_is_refused_rather_than_ignored(self, faceted):
        """Ignoring it returns a *wider* answer than was asked for, which reads as applied."""
        with pytest.raises(ServiceError, match="Unknown facet 'genre'"):
            faceted.list_artworks(facets={"genre": ["Landscape"]})

    def test_an_empty_selection_narrows_nothing(self, faceted):
        """What a control sends when the curator has cleared it."""
        assert faceted.list_artworks(facets={"movement": []}).total == len(_CORPUS)
        assert faceted.list_artworks(facets={"movement": ["  "]}).total == len(_CORPUS)


# -- writing what a work is ----------------------------------------------------


class TestRecordingAFacet:
    def test_a_facet_comes_back_on_the_work(self, service):
        work = service.add_artwork(title="Ground and Iron")

        service.record_facet(
            artwork_id=work.id,
            kind=VocabularyKind.MOVEMENT,
            value="Colour Field",
            derivation=FacetDerivation.INFERRED,
            source_note="anthropic/claude-opus-4",
        )
        (facet,) = service.facets_for(work.id)

        assert (facet.kind, facet.value, facet.derivation) == (
            VocabularyKind.MOVEMENT,
            "Colour Field",
            FacetDerivation.INFERRED,
        )
        assert facet.source_note == "anthropic/claude-opus-4"

    def test_recording_the_same_claim_twice_is_one_row(self, service):
        """A work is Baroque once, and asserting it again is the same statement.

        It also has to stay one row for the counts to mean anything: they are a
        plain `COUNT(*)`, so a second row would inflate the number beside a value
        while the grid it labels still showed the work once.
        """
        work = service.add_artwork(title="Interior with Four Windows")

        first = service.record_facet(
            artwork_id=work.id, kind=VocabularyKind.MOVEMENT, value="Baroque", derivation=FacetDerivation.INFERRED
        )
        again = service.record_facet(
            artwork_id=work.id, kind=VocabularyKind.MOVEMENT, value="Baroque", derivation=FacetDerivation.INFERRED
        )

        assert again.id == first.id
        assert len(service.facets_for(work.id)) == 1

    def test_re_recording_does_not_relabel_where_the_claim_came_from(self, service):
        """The first recording's provenance survives, and that is the point of the column.

        A later inference pass sweeping the catalogue must not be able to quietly
        restate a museum's own value as something a model guessed — which is the
        one failure `derivation` exists to prevent.
        """
        work = service.add_artwork(title="Nighthawks")
        service.record_facet(
            artwork_id=work.id,
            kind=VocabularyKind.MEDIUM,
            value="Oil on canvas",
            derivation=FacetDerivation.SOURCED,
            source_note="artic:medium_display",
        )

        service.record_facet(
            artwork_id=work.id, kind=VocabularyKind.MEDIUM, value="Oil on canvas", derivation=FacetDerivation.INFERRED
        )
        (facet,) = service.facets_for(work.id)

        assert facet.derivation is FacetDerivation.SOURCED
        assert facet.source_note == "artic:medium_display"

    def test_the_same_value_under_a_different_kind_is_a_different_claim(self, service):
        work = service.add_artwork(title="Untitled")

        service.record_facet(
            artwork_id=work.id, kind=VocabularyKind.SUBJECT, value="Architecture", derivation=FacetDerivation.INFERRED
        )
        service.record_facet(
            artwork_id=work.id, kind=VocabularyKind.MOVEMENT, value="Architecture", derivation=FacetDerivation.INFERRED
        )

        assert len(service.facets_for(work.id)) == 2

    @pytest.mark.parametrize(
        ("field", "arguments"),
        [
            ("kind", {"kind": "genre", "derivation": "inferred"}),
            ("derivation", {"kind": "movement", "derivation": "guessed"}),
        ],
    )
    def test_a_value_outside_the_vocabulary_is_refused(self, service, field, arguments):
        work = service.add_artwork(title="Untitled")

        with pytest.raises(ServiceError, match=f"Unknown {field}"):
            service.record_facet(artwork_id=work.id, value="Baroque", **arguments)

    def test_a_facet_on_a_work_that_is_not_there_is_refused(self, service):
        with pytest.raises(ServiceError, match="No artwork with id"):
            service.record_facet(artwork_id="nope", kind=VocabularyKind.ERA, value="17th c.", derivation=FacetDerivation.INFERRED)

    def test_removing_a_facet_takes_it_off_the_work_and_out_of_the_counts(self, faceted):
        work = next(entry for entry in faceted.list_artworks(facets={"movement": ["Colour Field"]}).entries).artwork
        (movement,) = [facet for facet in faceted.facets_for(work.id) if facet.kind is VocabularyKind.MOVEMENT]

        faceted.remove_facet(work.id, facet_id=movement.id)

        assert "Colour Field" not in options(faceted.list_artworks(), VocabularyKind.MOVEMENT)
        assert faceted.list_artworks(facets={"movement": ["Colour Field"]}).total == 0

    def test_a_facet_belonging_to_another_work_cannot_be_removed_through_this_one(self, faceted):
        """The id alone is not authority over a row, the same rule an original is recorded under."""
        works = [entry.artwork for entry in faceted.list_artworks().entries]
        (borrowed,) = [facet for facet in faceted.facets_for(works[0].id) if facet.kind is VocabularyKind.MOVEMENT]

        with pytest.raises(ServiceError, match="has no facet with id"):
            faceted.remove_facet(works[1].id, facet_id=borrowed.id)

        assert len(faceted.facets_for(works[0].id)) == 3


class TestTheCollectionIsNotAskedTheSameQuestionSixTimes:
    """Two branches whose whole job is the measured latency, pinned structurally.

    Neither changes an answer — a mutation sweep proved that by breaking both and
    watching every other test here stay green. They exist because recomputing the
    facet counts naively cost **57 ms unfiltered and 101 ms with a search term** on
    the 4,000-work corpus, against 6 ms and 31 ms after
    (`tools/search_latency.py`, 2026-08-12, medians of 50). On the Pi this is
    deployed to that is the difference between a screen that opens and one that
    hesitates, and nothing else in this suite would notice it coming back.

    **Asserted as statements issued rather than as elapsed time, deliberately.**
    A latency bar in the default suite is a flake the moment the workers contend
    for cores — which they do, `-n auto` being in this plane's `addopts` — and one
    loose enough not to flake would not catch a fivefold regression. The count of
    statements is exact, deterministic, and is the thing that actually changed.
    """

    @pytest.fixture
    def statements(self, catalogue_file, monkeypatch) -> list[str]:
        """Every SQL statement the listing sends, in order."""
        seen: list[str] = []
        issued = catalogue_file.select_rows

        def recording(statement: str, values=()):
            seen.append(" ".join(statement.split()))
            return issued(statement, values)

        monkeypatch.setattr(catalogue_file, "select_rows", recording)
        return seen

    def test_the_kinds_nobody_filtered_on_are_counted_together(self, faceted, statements):
        """One count statement for all six, because `without` leaves them all the same query.

        Not an exception to the exclusion rule — a consequence of it. A kind with
        nothing chosen has nothing to drop, so its count is the same count as every
        other such kind's, and asking six times asks one question six times.
        """
        faceted.list_artworks(limit=5)

        assert len([statement for statement in statements if "COUNT(*) AS tally" in statement]) == 1

    def test_a_filtered_kind_gets_a_query_of_its_own_and_the_rest_still_share_one(self, faceted, statements):
        faceted.list_artworks(facets={"movement": ["Baroque"]}, limit=5)
        counting = [statement for statement in statements if "COUNT(*) AS tally" in statement]

        assert len(counting) == 2

    def test_an_unnarrowed_query_does_not_restrict_the_facet_tables_to_every_work(self, faceted, statements):
        """ "Which works? All of them" is not a subquery worth writing.

        Left in, SQLite builds an ephemeral index of every work and probes it once
        per facet row to arrive at the set it started with — measured at 7.0 ms
        against 0.5 ms for one kind on the 4,000-work corpus. The collection's
        first screen is exactly this case.
        """
        faceted.list_artworks(limit=5)
        over_facets = [statement for statement in statements if "FROM work_facets" in statement]

        assert over_facets, "no facet statement was issued at all, so this proves nothing"
        for statement in over_facets:
            assert "artworks" not in statement, f"an unnarrowed read still went through the works table: {statement}"

    def test_a_narrowed_query_does_restrict_them(self, faceted, statements):
        """The other side of the branch: when something narrows, the restriction is there."""
        faceted.list_artworks(facets={"era": ["17th c."]}, limit=5)
        over_facets = [statement for statement in statements if "FROM work_facets" in statement]

        assert any("FROM artworks" in statement for statement in over_facets)


class TestTheFileCarriesFacetsWithoutAWrittenMigration:
    """A catalogue that predates the table gains it on the next open, and nothing else does.

    `durable.py` widens a file by adding *columns* the schema has and the file
    does not, and `migrations.py` exists for everything that cannot be inferred
    from comparing two schemas. A new table is neither: `CREATE TABLE IF NOT
    EXISTS` and `CREATE UNIQUE INDEX IF NOT EXISTS` both reach an existing file
    unchanged. That is the claim under which this chunk wrote no migration, so it
    is checked rather than assumed.
    """

    @staticmethod
    def _without_facets() -> str:
        """The catalogue schema as a file written before `work_facets` existed holds it."""
        kept = [statement for statement in CATALOGUE_SCHEMA.split(";") if "work_facets" not in statement and statement.strip()]
        return ";".join(kept) + ";"

    def test_an_older_file_gains_the_table_and_its_uniqueness(self, tmp_path):
        path = tmp_path / "catalogue.sqlite"
        older = SqliteDurableStore(path, self._without_facets() + DISCOVERY_SCHEMA)
        older_catalogue = SqliteCatalogue(older)
        work = CatalogueService(older_catalogue).add_artwork(title="Written before facets existed")
        assert older.select_rows("SELECT name FROM sqlite_master WHERE name = 'work_facets'") == []
        older.close()

        reopened = open_catalogue_file(path)
        try:
            service = CatalogueService(SqliteCatalogue(reopened))
            service.record_facet(
                artwork_id=work.id, kind=VocabularyKind.ERA, value="20th c.", derivation=FacetDerivation.INFERRED
            )

            assert [facet.value for facet in service.facets_for(work.id)] == ["20th c."]
            assert service.list_artworks(facets={"era": ["20th c."]}).total == 1
            # The index came with the table, so the uniqueness the counts rest on
            # holds on a migrated file too rather than only on a fresh one.
            assert (
                reopened.select_rows("SELECT name FROM sqlite_master WHERE type = 'index' AND name = 'work_facets_once_per_work'")
                != []
            )
        finally:
            reopened.close()

    def test_the_store_refuses_a_second_row_for_the_same_claim(self, store, service):
        """Below the service's no-op, the file will not hold two.

        The service returns the row it already has rather than writing a second,
        so nothing reaching it can produce a duplicate — this is the index behind
        that, which is what protects a catalogue written by anything else.
        """
        work = service.add_artwork(title="Untitled")
        service.record_facet(
            artwork_id=work.id, kind=VocabularyKind.MOVEMENT, value="Baroque", derivation=FacetDerivation.INFERRED
        )
        (held,) = store.list_facets(work.id)

        with pytest.raises(StorageError, match="already stored"):
            store.add_facet(replace(held, id="a-different-id", derivation=FacetDerivation.SOURCED))
