"""What a run offers when the gate refuses, and what it must never do to get there.

Driven through the runner, because every rule here is about *acting* on a browse
rather than about the browse itself: which artists get asked, how many works
survive the bound, how they are spread across artists, and — the one that matters
most — that an offered work is never merged with or presented as a work phase 1
named.

Phase 2 runs on the calling thread via the `spawn` seam, as its sibling does.
"""

import pytest
from fakes import FakeCollectionBrowse, FakeImageSearch, a_collection_holding, a_work, an_image

from curation.discovery.engine import WorkList
from curation.discovery.phase_two import PhaseTwoEngine
from curation.persistence.discovery_records import (
    InitiatedBy,
    ResolutionStatus,
    RunStatus,
    Verdict,
    WorkProvenance,
)
from curation.services.previews import PreviewCache, PreviewSettings
from curation.services.runner import DiscoveryRunner


def a_list(*works: tuple[str, str]) -> WorkList:
    """A phase-1 list of (title, artist) pairs, so a run can name several artists."""
    return WorkList(works=tuple(a_work(title, artist=artist) for title, artist in works))


@pytest.fixture
def museum() -> FakeImageSearch:
    """A museum that holds nothing anyone asks for: every work comes back unresolved."""
    return FakeImageSearch()


@pytest.fixture
def collection() -> FakeCollectionBrowse:
    return FakeCollectionBrowse()


@pytest.fixture
def previews(settings, museum) -> PreviewCache:
    return PreviewCache(PreviewSettings(art_root=settings.art_root, directory=settings.previews_path), museum.fetch_preview)


@pytest.fixture
def runner(services, engine, settings, museum, previews, collection) -> DiscoveryRunner:
    return DiscoveryRunner(
        services.discovery,
        engine,
        settings.discovery_settings,
        images=PhaseTwoEngine(museum, box=settings.tv_artwork_box),
        previews=previews,
        collection=collection,
        spawn=lambda work: work(),
    )


def start(runner: DiscoveryRunner):
    return runner.start(intent_text="Hard-edge abstraction for a white room", initiated_by=InitiatedBy.MCP_CLIENT)


def works_of(services, run_id):
    return services.discovery.list_candidate_works(run_id)


def offered(services, run_id):
    return [work for work in works_of(services, run_id) if work.provenance is WorkProvenance.OFFERED]


def proposed(services, run_id):
    return [work for work in works_of(services, run_id) if work.provenance is WorkProvenance.PROPOSED]


# -- the case the requirement exists for ----------------------------------------


def test_a_run_that_resolves_nothing_still_offers_the_collections_own_answer(services, engine, runner, collection):
    """The two real runs that started all this: eight works proposed, none resolved.

    A run ending with nothing to review told the curator nothing about a
    collection that may hold a great deal for their intent. It now offers what
    the collection actually has.
    """
    engine.result = a_list(("Spectrum IV", "Ellsworth Kelly"))
    collection.holdings = a_collection_holding(**{"Ellsworth Kelly": ["Train Landscape", "Tableau Vert"]}).holdings

    run_id = start(runner).id

    assert [work.resolution_status for work in proposed(services, run_id)] == [ResolutionStatus.UNRESOLVED]
    assert sorted(work.proposed_title for work in offered(services, run_id)) == ["Tableau Vert", "Train Landscape"]


def test_an_offered_work_is_never_presented_as_the_work_the_model_named(services, engine, runner, collection):
    """The near-match this whole flow forbids, asserted rather than asserted-about.

    The proposed work stays unresolved and holds no image; the offered works are
    separate rows under the collection's own titles. If an offered image were
    ever attached to the named work, that work would be `resolved` — so the
    assertion is on the thing that would actually go wrong.
    """
    engine.result = a_list(("Spectrum IV", "Ellsworth Kelly"))
    collection.holdings = a_collection_holding(**{"Ellsworth Kelly": ["Train Landscape"]}).holdings

    run_id = start(runner).id

    (named,) = proposed(services, run_id)
    assert named.resolution_status is ResolutionStatus.UNRESOLVED
    assert services.discovery.list_candidate_images(named.id) == []
    (gift,) = offered(services, run_id)
    assert gift.proposed_title == "Train Landscape"
    assert gift.id != named.id


def test_an_offered_work_says_which_query_produced_it_and_how_many_it_matched(services, engine, runner, collection):
    """Being offered one work out of four hundred reads differently from one out of one."""
    engine.result = a_list(("Spectrum IV", "Ellsworth Kelly"))
    collection.holdings = a_collection_holding(**{"Ellsworth Kelly": ["Train Landscape"]}).holdings
    collection.matched = {"Ellsworth Kelly": 400}

    run_id = start(runner).id

    (gift,) = offered(services, run_id)
    assert "Ellsworth Kelly" in gift.rationale
    assert "400" in gift.rationale
    assert "collection" in gift.rationale.lower()


def test_an_offered_work_arrives_reviewable_rather_than_as_a_bare_title(services, engine, runner, collection):
    """It carries its instance, so the review grid has a picture to show.

    An offered work with no image would be a title a curator cannot judge — worse
    than offering nothing, because it looks like the supplement worked.
    """
    engine.result = a_list(("Spectrum IV", "Ellsworth Kelly"))
    collection.holdings = a_collection_holding(**{"Ellsworth Kelly": ["Train Landscape"]}).holdings

    run_id = start(runner).id

    (gift,) = offered(services, run_id)
    assert gift.resolution_status is ResolutionStatus.RESOLVED
    (image,) = services.discovery.list_candidate_images(gift.id)
    assert image.is_selected
    assert image.preview_path, "an offered work's preview must be cached like any other"


# -- what bounds it -------------------------------------------------------------


def test_the_offer_is_bounded_and_spread_across_the_artists_the_run_named(services, engine, runner, collection, settings):
    """One prolific artist must not fill the allowance.

    The measured case: a run's artists held 51, 12, 5 and 1 offerable works. Take
    them in the collection's order and the whole bound goes to the first — the
    supplement stops being about the intent and becomes about one painter.
    """
    engine.result = a_list(("A", "Ellsworth Kelly"), ("B", "Morris Louis"), ("C", "Frank Stella"))
    collection.holdings = a_collection_holding(
        **{
            "Ellsworth Kelly": [f"Kelly {n}" for n in range(20)],
            "Morris Louis": ["Louis 0", "Louis 1"],
            "Frank Stella": ["Stella 0"],
        }
    ).holdings

    run_id = start(runner).id

    titles = [work.proposed_title for work in offered(services, run_id)]
    assert len(titles) == settings.discovery_settings.offered_works_per_run
    assert "Louis 0" in titles and "Stella 0" in titles, "a sparse artist was crowded out by a prolific one"
    assert sum(1 for title in titles if title.startswith("Kelly")) < len(titles)


def test_only_the_artists_whose_works_went_unconfirmed_are_asked_about(services, engine, runner, collection, museum):
    """A work that resolved needs no supplement, and its artist is not a facet.

    Offering more of a successful artist would pad a run that worked rather than
    answer one that did not.
    """
    engine.result = a_list(("The Elephants", "Salvador Dalí"), ("Spectrum IV", "Ellsworth Kelly"))
    museum.holdings = {"The Elephants": (an_image("The Elephants", artist="Salvador Dalí"),)}
    collection.holdings = a_collection_holding(**{"Ellsworth Kelly": ["Train Landscape"]}).holdings

    start(runner)

    assert collection.asked == [["Ellsworth Kelly"]]


def test_a_run_that_resolved_everything_asks_the_collection_nothing(services, engine, runner, collection, museum):
    """No unconfirmed work is no supplement, and no request."""
    engine.result = a_list(("The Elephants", "Salvador Dalí"))
    museum.holdings = {"The Elephants": (an_image("The Elephants", artist="Salvador Dalí"),)}

    start(runner)

    assert collection.asked == []


def test_an_artist_is_asked_about_once_however_many_of_their_works_failed(services, engine, runner, collection):
    """Two unresolved works by one painter are one question to the collection."""
    engine.result = a_list(("A", "Ellsworth Kelly"), ("B", "Ellsworth Kelly"), ("C", "Ellsworth Kelly"))
    collection.holdings = a_collection_holding(**{"Ellsworth Kelly": ["Train Landscape"]}).holdings

    start(runner)

    assert collection.asked == [["Ellsworth Kelly"]]


def test_a_work_with_no_named_artist_produces_no_facet(services, engine, runner, collection):
    """Artist adjacency is the only facet built, so an unattributed work has none.

    It is not an error and the run is not held up — there is simply nothing to
    ask the collection about.
    """
    engine.result = a_list(("An Untitled Work", None))

    run_id = start(runner).id

    assert collection.asked == []
    assert offered(services, run_id) == []


# -- what must not happen -------------------------------------------------------


def test_a_work_the_curator_already_rejected_is_never_offered_back(services, engine, runner, collection):
    """Constraint 7 does not care which route a work came back by.

    A supplement that re-offered declined works would ask a curator to turn down
    the same painting forever, and would do it under a new label.
    """
    engine.result = a_list(("Spectrum IV", "Ellsworth Kelly"))
    collection.holdings = a_collection_holding(**{"Ellsworth Kelly": ["Train Landscape", "Tableau Vert"]}).holdings

    first = start(runner).id
    turned_down = next(work for work in offered(services, first) if work.proposed_title == "Train Landscape")
    services.discovery.set_verdict(turned_down.id, Verdict.REJECTED, reason="Not for this room.")

    second = start(runner).id

    assert [work.proposed_title for work in offered(services, second)] == ["Tableau Vert"]


def test_a_work_the_run_already_proposed_is_not_offered_a_second_time(services, engine, runner, collection):
    """One painting, one card — whichever route found it.

    The collection holding a work the model also named is the ordinary case, not
    an edge one: that is what makes the model's list confirmable at all.
    """
    engine.result = a_list(("Train Landscape", "Ellsworth Kelly"))
    collection.holdings = a_collection_holding(**{"Ellsworth Kelly": ["Train Landscape", "Tableau Vert"]}).holdings

    run_id = start(runner).id

    assert [work.proposed_title for work in offered(services, run_id)] == ["Tableau Vert"]
    assert len(works_of(services, run_id)) == 2


def test_a_work_too_small_for_the_wall_is_not_offered(services, engine, runner, collection):
    """A named work below the floor is still shown; a volunteered one is not.

    The difference is that there are hundreds more behind the volunteered one, so
    a work that cannot go on the wall is padding rather than the answer to what
    was asked.
    """
    engine.result = a_list(("Spectrum IV", "Ellsworth Kelly"))
    collection.holdings = {
        "Ellsworth Kelly": (
            an_image("A Postage Stamp", artist="Ellsworth Kelly", width=90, height=60),
            an_image("Train Landscape", artist="Ellsworth Kelly", width=6000, height=4500),
        )
    }

    run_id = start(runner).id

    assert [work.proposed_title for work in offered(services, run_id)] == ["Train Landscape"]


def test_the_same_work_reached_by_two_facets_is_offered_once(services, engine, runner, collection):
    """A run naming both "Rembrandt" and "Rembrandt van Rijn" gets overlapping buckets."""
    shared = an_image("Old Man with a Gold Chain", artist="Rembrandt van Rijn", width=6000, height=4500)
    engine.result = a_list(("A", "Rembrandt"), ("B", "Rembrandt van Rijn"))
    collection.holdings = {"Rembrandt": (shared,), "Rembrandt van Rijn": (shared,)}

    run_id = start(runner).id

    assert len(offered(services, run_id)) == 1


def test_a_collection_that_cannot_be_reached_does_not_fail_the_run(services, engine, runner, collection, museum):
    """A supplement is an extra. Losing it must not lose what the run resolved.

    The opposite of phase 2, where an unreachable provider is the whole answer
    for that work — and the difference is that nobody asked for the supplement.
    """
    engine.result = a_list(("The Elephants", "Salvador Dalí"), ("Spectrum IV", "Ellsworth Kelly"))
    museum.holdings = {"The Elephants": (an_image("The Elephants", artist="Salvador Dalí"),)}
    collection.unreachable = True

    run_id = start(runner).id

    assert services.discovery.get_run(run_id).status is RunStatus.COMPLETED
    assert offered(services, run_id) == []
    assert next(w for w in proposed(services, run_id) if w.proposed_title == "The Elephants").resolution_status is (
        ResolutionStatus.RESOLVED
    )


def test_a_deployment_with_no_collection_wired_simply_offers_nothing(services, engine, settings, museum, previews):
    """Phase 2 without a supplement is a coherent deployment, not a broken one."""
    runner = DiscoveryRunner(
        services.discovery,
        engine,
        settings.discovery_settings,
        images=PhaseTwoEngine(museum, box=settings.tv_artwork_box),
        previews=previews,
        spawn=lambda work: work(),
    )
    engine.result = a_list(("Spectrum IV", "Ellsworth Kelly"))

    run_id = start(runner).id

    assert offered(services, run_id) == []


def test_a_bound_of_zero_switches_the_supplement_off_without_unwiring_it(
    services, engine, settings, museum, previews, collection
):
    """A cautious deployment can take only what the model named."""
    from dataclasses import replace

    runner = DiscoveryRunner(
        services.discovery,
        engine,
        replace(settings.discovery_settings, offered_works_per_run=0),
        images=PhaseTwoEngine(museum, box=settings.tv_artwork_box),
        previews=previews,
        collection=collection,
        spawn=lambda work: work(),
    )
    engine.result = a_list(("Spectrum IV", "Ellsworth Kelly"))
    collection.holdings = a_collection_holding(**{"Ellsworth Kelly": ["Train Landscape"]}).holdings

    run_id = start(runner).id

    assert offered(services, run_id) == []
    assert collection.asked == [], "a bound of zero should not even ask"


def test_an_offered_work_can_be_accepted_like_any_other(services, engine, runner, collection):
    """The supplement is a real candidate, not a display-only row.

    A work a curator cannot act on would be a worse answer than no work at all.
    """
    engine.result = a_list(("Spectrum IV", "Ellsworth Kelly"))
    collection.holdings = a_collection_holding(**{"Ellsworth Kelly": ["Train Landscape"]}).holdings

    run_id = start(runner).id
    (gift,) = offered(services, run_id)

    outcome = services.discovery.set_verdict(gift.id, Verdict.ACCEPTED)

    assert outcome.work.verdict is Verdict.ACCEPTED
    assert outcome.work.artwork_id, "accepting an offered work must mint an artwork like any other"


# -- what the surfaces report ---------------------------------------------------


def test_the_two_kinds_are_counted_apart_wherever_a_number_is_shown(services, engine, runner, collection):
    """The curator approved a list of a stated size; the supplement adds to it.

    A single total would report the run as having found more of what was asked
    for than it did, which is the one thing the offered/proposed split exists to
    prevent.
    """
    engine.result = a_list(("Spectrum IV", "Ellsworth Kelly"))
    collection.holdings = a_collection_holding(**{"Ellsworth Kelly": ["Train Landscape", "Tableau Vert"]}).holdings

    run_id = start(runner).id
    view = runner.run_status(run_id)

    assert view.proposed_count == 1
    assert view.offered_count == 2
    assert view.work_count == 3, "the total is still available; it is simply not the only number"


def test_the_approval_gate_is_sized_by_the_models_list_alone(services, engine, settings, museum, previews, collection):
    """An offer can never push a run over the gate, because it happens after it.

    Asserted on a run whose proposed list sits under a tight threshold and whose
    supplement would carry it well past: the gate has already been decided by the
    time a single work is offered.
    """
    from dataclasses import replace

    tight = replace(settings.discovery_settings, approval_threshold=3)
    runner = DiscoveryRunner(
        services.discovery,
        engine,
        tight,
        images=PhaseTwoEngine(museum, box=settings.tv_artwork_box),
        previews=previews,
        collection=collection,
        spawn=lambda work: work(),
    )
    engine.result = a_list(("A", "Ellsworth Kelly"), ("B", "Ellsworth Kelly"))
    collection.holdings = a_collection_holding(**{"Ellsworth Kelly": [f"Kelly {n}" for n in range(10)]}).holdings

    run_id = start(runner).id

    assert services.discovery.get_run(run_id).approval_required is False
    assert runner.run_status(run_id).offered_count > 0
    assert services.discovery.get_run(run_id).status is RunStatus.COMPLETED


def test_an_offered_work_does_not_inflate_the_runs_unresolved_tally(services, engine, runner, collection):
    """The run's own report of what it could not do stays about what it was asked."""
    engine.result = a_list(("Spectrum IV", "Ellsworth Kelly"))
    collection.holdings = a_collection_holding(**{"Ellsworth Kelly": ["Train Landscape"]}).holdings

    run_id = start(runner).id

    assert services.discovery.get_run(run_id).unresolved_work_count == 1


def test_the_spread_yields_each_work_once_and_takes_the_facets_in_turn():
    """The round robin's own contract, apart from what the store later refuses.

    Tested directly because the service layer independently declines a work the
    run already carries, which hides this from every end-to-end assertion: the
    records come out right whether or not the spread repeats itself. What only
    shows here is the order, and the order is the whole reason it exists.
    """
    from curation.discovery.browse import BrowseQuery, OfferedGroup
    from curation.services.runner import _round_robin

    shared = an_image("Shared", artist="A", url="https://artic.edu/shared")
    groups = [
        OfferedGroup(
            query=BrowseQuery(artist="A"),
            matched=3,
            works=(an_image("A1", artist="A", url="https://artic.edu/a1"), shared),
        ),
        OfferedGroup(
            query=BrowseQuery(artist="B"),
            matched=2,
            works=(an_image("B1", artist="B", url="https://artic.edu/b1"), shared),
        ),
    ]

    taken = [(found.title, group.query.artist) for found, group in _round_robin(groups)]

    assert taken == [("A1", "A"), ("B1", "B"), ("Shared", "A")], "expected one per facet per pass, each work once"


def test_a_record_whose_size_is_unknown_does_not_clear_the_floor(services):
    """ "We do not know how big it is" is not "it is big enough".

    Reached directly because the browse client refuses an unsized record before
    this is ever asked — so nothing end to end can distinguish the two answers,
    and a caller added later would inherit whichever this happens to give.
    """
    assert services.discovery.clears_display_floor(width=None, height=4500) is False
    assert services.discovery.clears_display_floor(width=6000, height=None) is False
    assert services.discovery.clears_display_floor(width=6000, height=4500) is True
