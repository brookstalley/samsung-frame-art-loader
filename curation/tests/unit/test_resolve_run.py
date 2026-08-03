"""The re-search: a run whose whole life is phase 2, over works a curator named.

Driven through the runner rather than the record layer, because what the record
layer already holds — coverage, the double-spend guard, the parent link — is
tested against `DiscoveryService` in `test_discovery_constraints.py`. What is
under test here is the half that *runs*: which works get asked about, whether a
`status` call can see the work happening, whose verdict wins when the curator
decides while it is running, and where the money lands.

Everything runs on the calling thread via the `spawn` seam, except where a test
is specifically about a run being observable while it is in flight.
"""

import threading
from decimal import Decimal

import pytest
from fakes import FakeImageSearch, a_work, an_image

from curation.discovery.engine import WorkList
from curation.discovery.phase_two import PhaseTwoEngine
from curation.persistence.discovery_records import (
    InitiatedBy,
    ResolutionStatus,
    RunKind,
    RunStatus,
    SpendCategory,
    Verdict,
)
from curation.services.errors import ServiceError
from curation.services.previews import PreviewCache, PreviewSettings
from curation.services.runner import DiscoveryRunner


@pytest.fixture
def museum() -> FakeImageSearch:
    return FakeImageSearch()


@pytest.fixture
def previews(settings, museum) -> PreviewCache:
    return PreviewCache(PreviewSettings(art_root=settings.art_root, directory=settings.previews_path), museum.fetch_preview)


@pytest.fixture
def runner(services, engine, settings, museum, previews) -> DiscoveryRunner:
    return DiscoveryRunner(
        services.discovery,
        engine,
        settings.discovery_settings,
        images=PhaseTwoEngine(museum, box=settings.tv_artwork_box),
        previews=previews,
        spawn=lambda work: work(),
    )


@pytest.fixture
def reviewed(services, engine, runner, museum):
    """A completed run whose works hold an image, ready for a curator to judge.

    The re-search only has a subject once a first pass has produced one, so
    every test here starts from a run that finished rather than from hand-built
    rows — which is also what makes the works' `resolution_status` the value a
    real run left behind rather than one a fixture asserted.

    Works come back keyed by title. Nothing promises the order a run's works are
    stored in, and a test that unpacked them positionally would assert against
    whichever one the store happened to hand back first.
    """

    def _reviewed(*titles: str, holdings: dict[str, tuple] | None = None):
        engine.result = WorkList(works=tuple(a_work(title) for title in titles))
        museum.holdings = holdings if holdings is not None else {title: (an_image(title),) for title in titles}
        run = runner.start(intent_text="Surrealist paintings with strong blues", initiated_by=InitiatedBy.MCP_CLIENT)
        assert services.discovery.get_run(run.id).status is RunStatus.COMPLETED
        return run, {work.proposed_title: work for work in services.discovery.list_candidate_works(run.id)}

    return _reviewed


def re_search(runner, *works, initiated_by=InitiatedBy.MCP_CLIENT):
    return runner.resolve_images(candidate_work_ids=[work.id for work in works], initiated_by=initiated_by)


def _two_scans(title: str) -> tuple:
    """One work a museum holds twice, so rejecting the better leaves a worse one standing.

    The size gap is what makes which is which deterministic rather than a
    coincidence of ordering: quality ranking prefers the larger, so the first
    instance listed is always the one a curator would be turning down.
    """
    return (
        an_image(title, url=f"https://artic.edu/{title}-best", width=6949, height=8400),
        an_image(title, url=f"https://artic.edu/{title}-fallback", width=3000, height=3600),
    )


# -- what a re-search is ---------------------------------------------------------


def test_a_re_search_is_a_run_hung_on_the_intent_that_proposed_the_works(services, runner, reviewed):
    """The parent link is what keeps a re-search's cost attributable to an intent."""
    parent, works = reviewed("The Elephants")
    work = works["The Elephants"]

    resolve = re_search(runner, work)

    assert resolve.kind is RunKind.RESOLVE
    assert resolve.parent_run_id == parent.id
    assert resolve.id != parent.id
    assert [covered.id for covered in services.discovery.covered_works(resolve.id)] == [work.id]


def test_a_re_search_finds_the_curator_a_replacement_and_returns_the_work_to_review(services, runner, reviewed, museum):
    """The state that was a dead end is one a work now comes back out of."""
    _, works = reviewed("The Elephants")
    work = works["The Elephants"]
    rejected = services.discovery.list_candidate_images(work.id)[0]
    services.discovery.reject_image(rejected.id)
    museum.holdings = {"The Elephants": (an_image("The Elephants", url="https://artic.edu/better-scan"),)}

    re_search(runner, work)

    settled = services.discovery.get_candidate_work(work.id)
    assert settled.verdict is Verdict.PENDING, "the work is back in front of the curator"
    assert settled.resolution_status is ResolutionStatus.RESOLVED
    selected = [image for image in services.discovery.list_candidate_images(work.id) if image.is_selected]
    assert [image.url for image in selected] == ["https://artic.edu/better-scan"]


def test_a_re_search_that_finds_nothing_new_leaves_the_work_asking(services, runner, reviewed, museum):
    """A dead end has to stay visible as one rather than reading as un-started."""
    _, works = reviewed("The Elephants")
    work = works["The Elephants"]
    services.discovery.reject_image(services.discovery.list_candidate_images(work.id)[0].id)
    museum.holdings = {}

    resolve = re_search(runner, work)

    assert services.discovery.get_run(resolve.id).status is RunStatus.COMPLETED
    settled = services.discovery.get_candidate_work(work.id)
    assert settled.verdict is Verdict.AWAITING_BETTER_IMAGE
    assert settled.resolution_status is ResolutionStatus.UNRESOLVED


def test_a_re_search_asks_about_every_work_it_covers(services, runner, reviewed, museum):
    """Coverage is the scope, and nothing narrows it after the curator has named it.

    A covered work quietly skipped would be a silent no-op that still held the
    work against a second re-search until this run ended. Every work a re-search
    covers has already been resolved once — that is what is being asked again —
    so a filter on "not yet resolved" would skip the whole request.
    """
    _, works = reviewed("The Elephants", "Swans Reflecting Elephants")
    museum.asked.clear()

    re_search(runner, *works.values())

    assert sorted(museum.asked) == ["Swans Reflecting Elephants", "The Elephants"]


def test_a_re_search_covers_a_subset_and_leaves_the_rest_alone(services, runner, reviewed, museum):
    _, works = reviewed("The Elephants", "Swans Reflecting Elephants")
    museum.asked.clear()

    re_search(runner, works["The Elephants"])

    assert museum.asked == ["The Elephants"]
    assert services.discovery.get_candidate_work(works["Swans Reflecting Elephants"].id).verdict is Verdict.PENDING


# -- the money -------------------------------------------------------------------


def test_what_a_re_search_spends_rolls_up_to_the_run_that_proposed_the_works(services, runner, reviewed):
    """ "What did asking for Dalí cost" is the total, and a re-search is part of it."""
    parent, works = reviewed("The Elephants")
    work = works["The Elephants"]
    before = services.discovery.run_cost(parent.id)

    resolve = re_search(runner, work)
    services.discovery.record_spend(category=SpendCategory.IMAGE_RESEARCH, cost_usd=Decimal("0.40"), discovery_run_id=resolve.id)

    parent_cost = services.discovery.run_cost(parent.id)
    assert parent_cost.total == before.total + Decimal("0.40")
    assert parent_cost.direct == before.direct, "the re-search's own bill is not the parent's"
    assert services.discovery.run_cost(resolve.id).direct == Decimal("0.40")


def test_the_parent_stays_completed_while_a_re_search_runs_under_it(services, runner, reviewed):
    """A run that ended never reopens; the re-search is a separate handle for that reason."""
    parent, works = reviewed("The Elephants")
    work = works["The Elephants"]

    re_search(runner, work)

    assert services.discovery.get_run(parent.id).status is RunStatus.COMPLETED


def test_a_re_search_is_priced_on_the_works_it_covers_not_the_ids_it_was_sent(services, runner, reviewed):
    """The estimate prices the deduplicated scope, so naming a work twice is not billed twice."""
    _, works = reviewed("The Elephants")
    work = works["The Elephants"]

    resolve = runner.resolve_images(candidate_work_ids=[work.id, work.id], initiated_by=InitiatedBy.WEB_UI)

    estimate = runner.estimate(resolve.id)
    assert estimate.cost_usd == Decimal(0), "phase 2 asks museum APIs, which are free"
    assert "1 works this run covers" in estimate.basis
    assert "proposed" not in estimate.basis, "a re-search proposed nothing; that sentence belongs to its parent"


# -- the curator outranks the job ------------------------------------------------


@pytest.mark.parametrize("verdict", [Verdict.ACCEPTED, Verdict.REJECTED])
def test_a_verdict_reached_while_the_re_search_ran_is_reported_and_not_applied(
    services, engine, settings, museum, previews, reviewed, runner, verdict
):
    """Only the curator's verdict is authoritative, and the guard is at the write.

    The curator is never blocked on a background job, so they can decide a work
    the moment they lose patience with a re-search of it. Whichever lands second
    must not be the one that wins: a resolution writing `pending` over an
    acceptance would leave a work holding an `artwork_id` and a non-accepted
    verdict, which nothing else in this model can produce or repair.
    """
    _, works = reviewed("The Elephants", holdings={"The Elephants": _two_scans("The Elephants")})
    work = works["The Elephants"]
    # Rejecting the instance on offer is what puts a work in a re-search's way;
    # the alternate underneath it is what leaves the curator something they can
    # still decide on, which is the whole point of not blocking them.
    services.discovery.reject_image(services.discovery.list_candidate_images(work.id)[0].id)

    def decide_mid_flight(query):
        services.discovery.set_verdict(work.id, verdict)
        return (an_image("The Elephants", url="https://artic.edu/found-late"),)

    museum.find_images = decide_mid_flight

    resolve = re_search(runner, work)

    assert services.discovery.get_run(resolve.id).status is RunStatus.COMPLETED
    settled = services.discovery.get_candidate_work(work.id)
    assert settled.verdict is verdict, "the curator's decision stands"
    assert settled.resolution_status is ResolutionStatus.RESOLVED, "and the re-search's result is still reported"


def test_no_re_search_ever_leaves_a_work_holding_an_artwork_id_and_a_non_accepted_verdict(services, museum, reviewed, runner):
    """The combination the guard exists to prevent — nothing in this model can repair it.

    Both orderings are exercised: a work already accepted when the re-search is
    asked for, and one accepted while it runs. Coverage does not consult the
    verdict, so a curator can name either.
    """
    _, works = reviewed("The Elephants", "Swans Reflecting Elephants")
    decided = works["The Elephants"]
    racing = works["Swans Reflecting Elephants"]
    services.discovery.set_verdict(decided.id, Verdict.ACCEPTED)

    def accept_mid_flight(query):
        if query.title == racing.proposed_title:
            services.discovery.set_verdict(racing.id, Verdict.ACCEPTED)
        return (an_image(query.title, url=f"https://artic.edu/{query.title}-again"),)

    museum.find_images = accept_mid_flight

    re_search(runner, decided, racing)

    for work in (decided, racing):
        settled = services.discovery.get_candidate_work(work.id)
        assert settled.verdict is Verdict.ACCEPTED
        assert settled.artwork_id is not None
        assert not (settled.artwork_id is not None and settled.verdict is not Verdict.ACCEPTED)


def test_a_curator_who_rejected_a_scan_is_never_handed_it_back(services, runner, reviewed, museum):
    """Instance suppression has to survive the re-search, which is the only thing it defends against.

    A rejection is a fact about the scan at that URL, not about the row that
    happened to hold it. A provider re-offering the same URL — which is the
    normal case, since museums do not move their images between two searches a
    minute apart — would otherwise produce a second, unrejected row and select
    it, handing the curator back exactly what they turned down.
    """
    _, works = reviewed("The Elephants")
    work = works["The Elephants"]
    turned_down = services.discovery.list_candidate_images(work.id)[0]
    services.discovery.reject_image(turned_down.id)

    re_search(runner, work)

    offered = [image for image in services.discovery.list_candidate_images(work.id) if image.rejected_at is None]
    assert [image.url for image in offered] == [], "the only instance on offer was the rejected one"
    settled = services.discovery.get_candidate_work(work.id)
    assert settled.verdict is Verdict.AWAITING_BETTER_IMAGE
    assert settled.resolution_status is ResolutionStatus.UNRESOLVED


# -- a re-search is a run, and every run-shaped action takes it ------------------


def test_a_re_search_can_be_cancelled_and_stops_where_it_was(services, runner, reviewed, museum):
    """`cancel` takes a re-search id, which the action's own tips promise a caller.

    Driven rather than asserted from the wording: a run stopped partway must
    actually stop, or the promise is that the call returns rather than that it
    does anything. The works not yet reached are left alone, and what was spent
    before the decision stays recorded.
    """
    _, works = reviewed("The Elephants", "Swans Reflecting Elephants")
    museum.asked.clear()
    resolve_id: dict[str, str] = {}
    ask = museum.find_images

    def cancel_after_the_first(query):
        result = ask(query)
        if len(museum.asked) == 1:
            services.discovery.cancel_run(resolve_id["id"])
        return result

    original = services.discovery.start_resolve_run

    def remember(**kwargs):
        run = original(**kwargs)
        resolve_id["id"] = run.id
        return run

    services.discovery.start_resolve_run = remember
    museum.find_images = cancel_after_the_first

    resolve = re_search(runner, *works.values())

    assert services.discovery.get_run(resolve.id).status is RunStatus.CANCELLED
    assert len(museum.asked) == 1, "it stopped rather than working through the rest"
    # And cancelling is terminal, which is what releases the coverage — a curator
    # who stopped a re-search must be able to start another over the same works.
    services.discovery.start_resolve_run = original
    assert re_search(runner, *works.values()).id


def test_a_re_search_appears_in_a_listing_narrowed_to_re_searches(services, runner, reviewed):
    """`list_runs(kind=...)` is how a curator finds the re-searches under an intent."""
    parent, works = reviewed("The Elephants")

    resolve = re_search(runner, works["The Elephants"])

    assert [run.id for run in runner.list_runs(kind=RunKind.RESOLVE)] == [resolve.id]
    assert parent.id in [run.id for run in runner.list_runs(kind=RunKind.DISCOVERY)]


# -- being watched while it works ------------------------------------------------


def test_status_on_a_re_search_holds_while_the_work_is_actually_happening(services, engine, settings, museum, previews):
    """The hold is keyed on this process having the run in hand, and a re-search is a third way in.

    Registering the run late — or not at all — is invisible in every test that
    runs phase 2 on the calling thread, and shows up in production as every
    `status` call on a re-search returning instantly while the run is plainly
    working.
    """
    engine.result = WorkList(works=(a_work("The Elephants"),))
    museum.holdings = {"The Elephants": (an_image("The Elephants"),)}
    threaded = DiscoveryRunner(
        services.discovery,
        engine,
        settings.discovery_settings,
        images=PhaseTwoEngine(museum, box=settings.tv_artwork_box),
        previews=previews,
    )
    run = threaded.start(intent_text="Surrealist paintings", initiated_by=InitiatedBy.MCP_CLIENT)
    while services.discovery.get_run(run.id).status is not RunStatus.COMPLETED:
        pass
    work = services.discovery.list_candidate_works(run.id)[0]
    services.discovery.reject_image(services.discovery.list_candidate_images(work.id)[0].id)

    searching = threading.Event()
    release = threading.Event()

    def hold(query):
        searching.set()
        release.wait(5)
        return ()

    museum.find_images = hold
    resolve = threaded.resolve_images(candidate_work_ids=[work.id], initiated_by=InitiatedBy.WEB_UI)
    try:
        assert searching.wait(5), "the re-search never reached the provider"
        held = threading.Event()

        def watch():
            threaded.run_status(resolve.id)
            held.set()

        threading.Thread(target=watch, daemon=True).start()
        assert not held.wait(0.5), "status answered at once on a run that was still being worked on"
    finally:
        release.set()
    assert held.wait(5), "status did not answer once the re-search finished"


def test_a_re_search_releases_its_registration_however_it_ends(services, runner, reviewed, museum):
    """A run left registered holds every later `status` call on it for the full poll."""
    _, works = reviewed("The Elephants")
    work = works["The Elephants"]
    museum.unreachable = True

    resolve = re_search(runner, work)

    assert services.discovery.get_run(resolve.id).status is RunStatus.FAILED
    # Answers rather than holding: nothing is working on it any more.
    assert runner.run_status(resolve.id).run.status is RunStatus.FAILED


# -- refusals --------------------------------------------------------------------


def test_a_re_search_over_a_work_a_live_one_covers_is_refused_and_names_it(services, runner, reviewed):
    """The refusal names the offending work rather than silently deduplicating."""
    _, works = reviewed("The Elephants")
    work = works["The Elephants"]
    services.discovery.start_resolve_run(candidate_work_ids=[work.id], initiated_by=InitiatedBy.WEB_UI)

    with pytest.raises(ServiceError) as refusal:
        re_search(runner, work)

    assert "The Elephants" in str(refusal.value)
    assert work.id in str(refusal.value)
    assert "pay twice" in str(refusal.value)


def test_works_from_two_different_runs_cannot_share_one_re_search(services, runner, reviewed):
    """A re-search hangs its cost on one intent, and two runs have no single one."""
    _, first = reviewed("The Elephants")
    _, second = reviewed("Nighthawks")

    with pytest.raises(ServiceError, match="one discovery run"):
        re_search(runner, first["The Elephants"], second["Nighthawks"])


def test_a_re_search_with_no_works_is_refused(services, runner):
    with pytest.raises(ServiceError, match="at least one candidate work"):
        runner.resolve_images(candidate_work_ids=[], initiated_by=InitiatedBy.WEB_UI)


def test_a_deployment_with_no_image_provider_refuses_a_re_search_rather_than_minting_one(services, engine, settings, reviewed):
    """A run nothing will ever pick up is worse than a refusal: it reports itself as under way.

    `approve` tolerates the same deployment because a discovery run's work list
    is real and was worth producing whatever happens next. A re-search has
    nothing else in it.
    """
    _, works = reviewed("The Elephants")
    work = works["The Elephants"]
    blind = DiscoveryRunner(services.discovery, engine, settings.discovery_settings, spawn=lambda job: job())

    with pytest.raises(ServiceError, match="no image provider"):
        blind.resolve_images(candidate_work_ids=[work.id], initiated_by=InitiatedBy.WEB_UI)

    assert [run for run in services.discovery.list_runs(kind=RunKind.RESOLVE)] == []
