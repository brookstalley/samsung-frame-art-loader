"""What a run offers when the gate refuses, and what it must never do to get there.

Driven through the runner, because every rule here is about *acting* on a browse
rather than about the browse itself: which artists get asked, how many works
survive the bound, how they are spread across artists, and — the one that matters
most — that an offered work is never merged with or presented as a work phase 1
named.

Phase 2 runs on the calling thread via the `spawn` seam, as its sibling does.
"""

from dataclasses import replace

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


def test_a_re_search_offers_nothing_and_does_not_fail_trying(services, engine, runner, collection):
    """A resolve run re-searches works a curator named; it does not supplement them.

    The supplement runs at the end of phase 2, and a re-search is phase 2 — so
    this path is reached by both kinds of run. Offering is refused for a resolve
    run at the record layer, and a refusal that travelled as an exception would
    surface as the whole re-search *failing*: the curator asks for a better image
    and is told the run broke.
    """
    engine.result = a_list(("Spectrum IV", "Ellsworth Kelly"))
    collection.holdings = a_collection_holding(**{"Ellsworth Kelly": ["Train Landscape"]}).holdings

    run_id = start(runner).id
    named = next(work for work in proposed(services, run_id) if work.resolution_status is ResolutionStatus.UNRESOLVED)
    collection.asked.clear()

    resolve = runner.resolve_images(candidate_work_ids=[named.id], initiated_by=InitiatedBy.MCP_CLIENT)

    assert services.discovery.get_run(resolve.id).status is RunStatus.COMPLETED, "the re-search failed instead of finishing"
    assert offered(services, resolve.id) == []
    assert collection.asked == [], "a re-search should not browse the collection at all"


def test_the_run_notice_rates_resolution_over_proposed_works_only(services, engine, runner, collection):
    """The sentence a curator reads must not claim a rate the run did not achieve.

    Offered works arrive carrying their images, so folding them into the
    numerator turns "one of one proposed work found nothing" into "twelve of
    thirteen have an image" — the resolution figure this product made
    load-bearing, reported as its own opposite.
    """
    from curation.mcp.bindings import _run_notice

    engine.result = a_list(("Spectrum IV", "Ellsworth Kelly"))
    collection.holdings = a_collection_holding(**{"Ellsworth Kelly": ["Kelly 1", "Kelly 2", "Kelly 3"]}).holdings

    run_id = start(runner).id
    notice = _run_notice(runner.run_status(run_id, wait=False))

    assert "0 of 1 proposed works have an image" in notice
    assert "offered 3 more works" in notice
    assert "12 of 13" not in notice and "3 of 4" not in notice


def test_the_run_payload_reports_the_two_kinds_apart(services, engine, runner, collection):
    """The counts have to reach the wire, not just exist on the view."""
    from curation.mcp.bindings import _run_view

    engine.result = a_list(("Spectrum IV", "Ellsworth Kelly"))
    collection.holdings = a_collection_holding(**{"Ellsworth Kelly": ["Kelly 1", "Kelly 2"]}).holdings

    run_id = start(runner).id
    payload = _run_view(runner.run_status(run_id, wait=False))

    assert payload["works"]["proposed"] == 1
    assert payload["works"]["offered"] == 2
    assert payload["works"]["total"] == 3


def test_the_search_allowance_is_sized_on_the_works_phase_two_searched(services, engine, runner, collection, settings):
    """An offered work reached the run through the collection, not through a search.

    Counting it in the allowance reports a bound larger than anything the run
    could have spent, on the figure that exists to make the estimate meaningful.
    """
    engine.result = a_list(("Spectrum IV", "Ellsworth Kelly"))
    collection.holdings = a_collection_holding(**{"Ellsworth Kelly": ["Kelly 1", "Kelly 2", "Kelly 3"]}).holdings

    run_id = start(runner).id
    view = runner.run_status(run_id, wait=False)

    expected = settings.discovery_settings.phase1_search_allowance + 1 * settings.discovery_settings.phase2_searches_per_work
    assert view.search_allowance == expected


def test_an_offered_work_re_searched_to_nothing_does_not_make_the_count_negative(services, engine, runner, collection):
    """The state a subtraction cannot survive, and it is reachable by the documented route.

    An offered work arrives resolved. A curator who turns down its instance is
    told to re-search; a re-search that finds nothing derives `unresolved` on it.
    The run stays completed, so `resolved` falls while `offered` does not — and a
    numerator computed as `resolved - offered` goes negative, printing
    "-1 of 1 proposed works have an image".
    """
    from curation.mcp.bindings import _run_notice

    engine.result = a_list(("Spectrum IV", "Ellsworth Kelly"))
    collection.holdings = a_collection_holding(**{"Ellsworth Kelly": ["Kelly 1", "Kelly 2"]}).holdings

    run_id = start(runner).id
    for gift in offered(services, run_id):
        (image,) = services.discovery.list_candidate_images(gift.id)
        services.discovery.reject_image(image.id)
        services.discovery.record_resolution(gift.id)

    view = runner.run_status(run_id, wait=False)

    assert view.resolved_proposals == 0
    assert "0 of 1 proposed works have an image" in _run_notice(view)
    assert "-1" not in _run_notice(view)


def test_a_re_search_of_an_offered_work_is_allowed_its_searches(services, engine, runner, collection, settings):
    """A re-search covers works owned by its parent, carrying the parent's provenance.

    Sizing its allowance by `proposed` therefore counts zero for a re-search of
    offered works, and the surface publishes `exhausted: true` for a run that has
    not spent a search yet — on the operation a curator may repeat freely.
    """
    engine.result = a_list(("Spectrum IV", "Ellsworth Kelly"))
    collection.holdings = a_collection_holding(**{"Ellsworth Kelly": ["Kelly 1"]}).holdings

    run_id = start(runner).id
    (gift,) = offered(services, run_id)

    resolve = runner.resolve_images(candidate_work_ids=[gift.id], initiated_by=InitiatedBy.MCP_CLIENT)
    view = runner.run_status(resolve.id, wait=False)

    assert view.search_allowance == settings.discovery_settings.phase2_searches_per_work
    assert view.searches_exhausted is False


def test_a_re_search_reports_what_it_covers_rather_than_a_proposed_rate(services, engine, runner, collection):
    """A re-search's works belong to its parent and carry the parent's provenance.

    So "N of M proposed works" answers about a phase this run never performed,
    and on a re-search covering offered works the denominator is not even theirs:
    one proposed and one offered, both unresolved, reads "0 of 1 proposed works
    have an image. 2 could not be matched" — two failures against a denominator
    of one, with nothing accounting for the second.

    **Asserted on the sentence produced, not the one omitted.** An earlier version
    of this test checked only that "collection offered" was absent, which passes
    in every branch including the broken one and pins nothing at all.
    """
    from curation.mcp.bindings import _run_notice

    engine.result = a_list(("Spectrum IV", "Ellsworth Kelly"))
    collection.holdings = a_collection_holding(**{"Ellsworth Kelly": ["Kelly 1"]}).holdings

    run_id = start(runner).id
    (gift,) = offered(services, run_id)
    named = next(work for work in proposed(services, run_id))
    resolve = runner.resolve_images(candidate_work_ids=[gift.id, named.id], initiated_by=InitiatedBy.MCP_CLIENT)

    notice = _run_notice(runner.run_status(resolve.id, wait=False))

    assert "This re-search finished:" in notice
    assert "of the 2 works it covers" in notice, "a re-search must count what it covers, not a proposed list"
    assert "proposed works have an image" not in notice
    assert "collection offered" not in notice


def test_a_run_still_in_flight_describes_the_work_list_it_is_resolving(services, engine, runner, collection):
    """The supplement writes during this window, so a merged total climbs mid-run.

    Built as a view rather than driven, because the state is transient by
    construction: the supplement's writes and `_close_phase_two` are consecutive
    statements, so a run read from the outside is already finished. `_run_notice`
    is a pure function of the view, which is how the other notice tests reach it.
    """
    from curation.mcp.bindings import _run_notice
    from curation.services.runner import RunView

    engine.result = a_list(("Spectrum IV", "Ellsworth Kelly"))
    collection.holdings = a_collection_holding(**{"Ellsworth Kelly": ["Kelly 1", "Kelly 2"]}).holdings
    run_id = start(runner).id

    in_flight = RunView(
        run=replace(services.discovery.get_run(run_id), status=RunStatus.RESOLVING_IMAGES),
        works=works_of(services, run_id),
        searches_used=1,
        search_allowance=10,
        image_resolution_available=True,
    )

    notice = _run_notice(in_flight)

    assert "work list of 1 works is settled" in notice, "the sentence counted works the collection had just added"
