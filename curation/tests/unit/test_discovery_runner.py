"""Running a discovery run: the gate, the estimate, the cap, and what is skipped.

Driven through the runner rather than the record layer, because the record layer
already has tests that pass with every one of these decisions deleted. What is
under test here is which numbers reach those methods and what happens to an
engine's answer on the way in.

Phase 1 runs on the calling thread in these tests — see the `runner` fixture. The
threaded path is exercised where its behaviour actually matters, against a real
server over real HTTP.
"""

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fakes import a_work, a_work_list, spent, works

from curation.discovery.engine import BudgetExhausted, EngineFailure, WorkList, unavailable_engine
from curation.persistence.discovery_records import InitiatedBy, RunStatus, SpendCategory, Verdict
from curation.services.errors import ServiceError
from curation.services.runner import DiscoveryRunner


def start(runner: DiscoveryRunner, intent: str = "Surrealist paintings with strong blues"):
    return runner.start(intent_text=intent, initiated_by=InitiatedBy.MCP_CLIENT)


# -- the approval gate ----------------------------------------------------------


@pytest.mark.parametrize(
    ("threshold", "found", "expected", "gated"),
    [
        (25, 26, RunStatus.AWAITING_APPROVAL, True),
        # Exactly the threshold does not stop: a limit the curator set is a
        # number they have already accepted.
        (25, 25, RunStatus.RESOLVING_IMAGES, False),
        (25, 3, RunStatus.RESOLVING_IMAGES, False),
        # Zero gates everything, which is a coherent setting for a cautious
        # deployment rather than a broken one.
        (0, 1, RunStatus.AWAITING_APPROVAL, True),
    ],
)
def test_the_gate_fires_on_the_work_count_against_the_configured_threshold(
    services, engine, settings, threshold, found, expected, gated
):
    engine.result = a_work_list(found)
    runner = DiscoveryRunner(
        services.discovery,
        engine,
        replace(settings.discovery_settings, approval_threshold=threshold),
        spawn=lambda work: work(),
    )

    run = services.discovery.get_run(start(runner).id)

    assert run.status is expected
    assert run.approval_required is gated


def test_whether_the_gate_fired_is_stored_rather_than_re_derived(services, engine, settings):
    """A run judged last month must still read as having stopped for approval.

    The threshold is configuration and configuration changes. Re-deriving would
    have a run's history silently rewritten by an unrelated edit to `.env`.
    """
    engine.result = a_work_list(4)
    gated = DiscoveryRunner(
        services.discovery, engine, replace(settings.discovery_settings, approval_threshold=2), spawn=lambda work: work()
    )
    run_id = start(gated).id
    assert services.discovery.get_run(run_id).approval_required is True

    # The deployment is re-configured to a threshold this run would clear.
    relaxed = DiscoveryRunner(
        services.discovery, engine, replace(settings.discovery_settings, approval_threshold=99), spawn=lambda work: work()
    )

    assert relaxed.run_status(run_id, wait=False).run.approval_required is True


def test_a_gated_run_waits_and_then_takes_the_curators_decision(services, engine, settings):
    """Approving and declining are both available, and only from the gate."""
    gated = DiscoveryRunner(
        services.discovery, engine, replace(settings.discovery_settings, approval_threshold=1), spawn=lambda work: work()
    )

    approved_id = start(gated).id
    assert services.discovery.get_run(approved_id).status is RunStatus.AWAITING_APPROVAL
    assert gated.approve(approved_id).run.status is RunStatus.RESOLVING_IMAGES

    declined_id = start(gated).id
    assert gated.decline(declined_id).run.status is RunStatus.DECLINED


def test_a_run_that_never_reached_the_gate_cannot_be_approved(runner, services):
    """The refusal names where the run actually is, so a caller can act on it."""
    run_id = start(runner).id
    assert services.discovery.get_run(run_id).status is RunStatus.RESOLVING_IMAGES

    with pytest.raises(ServiceError) as refusal:
        runner.approve(run_id)

    assert "resolving_images" in str(refusal.value)


# -- the estimate, at both arities ----------------------------------------------


def test_estimate_with_no_run_id_prices_asking_the_question(runner, settings):
    """Computable before anything exists, which is what makes it the number
    shown at the point of decision."""
    estimate = runner.estimate()

    assert estimate.phase == "phase_1"
    assert estimate.run_id is None
    assert estimate.cost_usd == settings.discovery_settings.phase1_estimate_usd


def test_the_phase_one_estimate_prices_the_whole_allowance_not_a_typical_run(services, engine, settings):
    """Bounded, not typical: a figure a run may freely exceed is not an estimate."""
    generous = replace(settings.discovery_settings, phase1_search_allowance=100)
    runner = DiscoveryRunner(services.discovery, engine, generous, spawn=lambda work: work())

    priced = runner.estimate().cost_usd

    # The allowance is ten times the default, and only the search half of the
    # figure moves — which is the decomposition the two-part cap rests on.
    assert priced > settings.discovery_settings.phase1_estimate_usd
    assert priced == generous.phase1_estimate_usd


def test_estimate_with_a_run_id_returns_that_runs_stored_phase_two_figure(services, engine, settings):
    engine.result = a_work_list(4)
    runner = DiscoveryRunner(services.discovery, engine, settings.discovery_settings, spawn=lambda work: work())
    run_id = start(runner).id
    stored = services.discovery.get_run(run_id).estimated_cost_usd

    estimate = runner.estimate(run_id)

    assert estimate.phase == "phase_2"
    assert estimate.run_id == run_id
    assert estimate.cost_usd == stored
    # Four works, not the three a default fake would give, so an estimate built
    # from anything but this run's own count would show.
    assert stored == settings.discovery_settings.phase2_estimate_usd(4)


def test_the_stored_estimate_is_not_recomputed_under_later_prices(services, engine, settings):
    """A run reviewed later reports what it was actually authorised against."""
    runner = DiscoveryRunner(services.discovery, engine, settings.discovery_settings, spawn=lambda work: work())
    run_id = start(runner).id
    authorised = runner.estimate(run_id).cost_usd

    dearer = DiscoveryRunner(
        services.discovery,
        engine,
        replace(settings.discovery_settings, search_cost_usd=Decimal("5.00")),
        spawn=lambda work: work(),
    )

    assert dearer.estimate(run_id).cost_usd == authorised


def test_estimate_refuses_a_run_that_has_no_phase_two_figure_yet_and_says_what_to_do(services, engine, settings):
    """A run still in phase 1 has no work count, so there is nothing to price."""
    # Phase 1 is never run at all, which is what leaves the run in the state a
    # caller would find it in while the work is still going on.
    runner = DiscoveryRunner(services.discovery, engine, settings.discovery_settings, spawn=lambda work: None)
    run_id = start(runner).id

    with pytest.raises(ServiceError) as refusal:
        runner.estimate(run_id)

    assert "resolving_works" in str(refusal.value)
    assert "estimate with no run_id" in str(refusal.value)


def test_estimating_never_spends(runner, services):
    runner.estimate()
    run_id = start(runner).id
    before = services.discovery.run_cost(run_id).total

    runner.estimate()
    runner.estimate(run_id)

    assert services.discovery.run_cost(run_id).total == before


# -- the search cap -------------------------------------------------------------


def test_the_allowance_is_handed_to_the_engine(runner, engine, settings):
    """The engine cannot respect a bound it was never told."""
    start(runner)

    assert engine.searched == [settings.discovery_settings.phase1_search_allowance]


def test_a_run_that_used_its_whole_allowance_says_so_rather_than_looking_complete(services, engine, settings):
    tight = replace(settings.discovery_settings, phase1_search_allowance=3, phase2_searches_per_work=0)
    engine.result = WorkList(works=works(2), spend=spent(searches=3))
    runner = DiscoveryRunner(services.discovery, engine, tight, spawn=lambda work: work())

    view = runner.run_status(start(runner).id, wait=False)

    assert view.searches_used == 3
    assert view.search_allowance == 3
    assert view.searches_exhausted is True


def test_a_run_well_inside_its_allowance_is_not_reported_as_exhausted(runner):
    view = runner.run_status(start(runner).id, wait=False)

    assert view.searches_used == 1
    assert view.searches_exhausted is False


def test_an_engine_that_overruns_the_allowance_fails_the_run_rather_than_keeping_its_results(services, engine, settings):
    """Results bought outside the bound are not accepted quietly.

    The cap is what makes the pre-run estimate a bound rather than a guess, so an
    overrun reported as a successful run with a footnote would be the estimate
    silently ceasing to mean anything.
    """
    tight = replace(settings.discovery_settings, phase1_search_allowance=2)
    engine.result = WorkList(works=works(3), spend=spent(searches=5))
    runner = DiscoveryRunner(services.discovery, engine, tight, spawn=lambda work: work())

    run_id = start(runner).id

    run = services.discovery.get_run(run_id)
    assert run.status is RunStatus.FAILED
    assert services.discovery.list_candidate_works(run_id) == []
    # The spend still lands: the searches were made and billed whether or not
    # their results were kept.
    assert services.discovery.searches_in_run(run_id) == 5


def test_the_search_count_comes_from_the_records_that_price_it(services, engine, settings):
    """One number, not two. A separate tally could disagree with the bill."""
    engine.result = WorkList(works=works(2), spend=spent(searches=4))
    runner = DiscoveryRunner(services.discovery, engine, settings.discovery_settings, spawn=lambda work: work())

    run_id = start(runner).id

    priced = [
        record
        for record in services.discovery._store.list_spend_records(run_id=run_id)
        if record.category is SpendCategory.WEB_SEARCH
    ]
    assert [record.units for record in priced] == [4]
    assert services.discovery.searches_in_run(run_id) == 4


# -- what an engine's answer becomes ---------------------------------------------


def test_a_work_the_curator_already_rejected_is_not_proposed_again(services, engine, settings, propose):
    """Suppression is the dedup key's whole purpose, and it is silent to the run.

    Refusing the whole run would be wrong — the other works are fine — and
    proposing it again would ask the curator to decline the same painting
    forever.
    """
    already = propose("The Elephants", dedup_key="salvador dali::the elephants")
    services.discovery.set_verdict(already.id, Verdict.REJECTED)

    engine.result = WorkList(works=(a_work("The Elephants"), a_work("Galatea of the Spheres")), spend=spent())
    runner = DiscoveryRunner(services.discovery, engine, settings.discovery_settings, spawn=lambda work: work())

    run_id = start(runner).id

    proposed = [work.proposed_title for work in services.discovery.list_candidate_works(run_id)]
    assert proposed == ["Galatea of the Spheres"]


def test_a_work_the_engine_names_twice_is_recorded_once(services, engine, settings):
    """A run proposes each work exactly once, whatever the engine returned."""
    engine.result = WorkList(
        works=(a_work("The Elephants"), a_work("the  elephants."), a_work("Galatea of the Spheres")),
        spend=spent(),
    )
    runner = DiscoveryRunner(services.discovery, engine, settings.discovery_settings, spawn=lambda work: work())

    run_id = start(runner).id

    assert len(services.discovery.list_candidate_works(run_id)) == 2


def test_the_stored_estimate_counts_the_works_actually_proposed(services, engine, settings, propose):
    """Not what the engine said. A skipped work costs nothing to resolve."""
    already = propose("The Elephants", dedup_key="salvador dali::the elephants")
    services.discovery.set_verdict(already.id, Verdict.REJECTED)
    engine.result = WorkList(works=(a_work("The Elephants"), a_work("Galatea of the Spheres")), spend=spent())
    runner = DiscoveryRunner(services.discovery, engine, settings.discovery_settings, spawn=lambda work: work())

    run_id = start(runner).id

    assert services.discovery.get_run(run_id).estimated_cost_usd == settings.discovery_settings.phase2_estimate_usd(1)


def test_each_proposed_work_carries_the_engines_reason_for_it(runner, services):
    run_id = start(runner).id

    for work in services.discovery.list_candidate_works(run_id):
        assert work.rationale
        assert work.proposed_artist == "Salvador Dalí"


# -- how a run can end -----------------------------------------------------------


def test_a_provider_refusing_to_spend_halts_the_run_rather_than_failing_it(services, engine, settings):
    """Out of money and broken are different, and the right response differs."""
    engine.error = BudgetExhausted("The provider returned 402.", spend=spent(tokens_usd="0.04"))
    runner = DiscoveryRunner(services.discovery, engine, settings.discovery_settings, spawn=lambda work: work())

    run_id = start(runner).id

    assert services.discovery.get_run(run_id).status is RunStatus.HALTED_BY_BUDGET


def test_an_engine_error_fails_the_run(services, engine, settings):
    engine.error = EngineFailure("The model returned something unparseable.")
    runner = DiscoveryRunner(services.discovery, engine, settings.discovery_settings, spawn=lambda work: work())

    assert services.discovery.get_run(start(runner).id).status is RunStatus.FAILED


def test_an_unexpected_error_ends_the_run_instead_of_leaving_it_looking_alive(services, engine, settings):
    """A worker that died with an exception would leave a phantom hang.

    The run would sit in a process-held state looking as though something were
    still working on it, until the next restart reconciled it — turning every
    engine bug into a run that never answers.
    """
    engine.error = ZeroDivisionError("something no engine was supposed to raise")
    runner = DiscoveryRunner(services.discovery, engine, settings.discovery_settings, spawn=lambda work: work())

    assert services.discovery.get_run(start(runner).id).status is RunStatus.FAILED


def test_spend_incurred_before_a_failure_is_still_recorded(services, engine, settings):
    """A run that broke halfway still incurred what it incurred.

    Dropping it on the failure path would under-report the month by exactly what
    the failures cost, which is the spend nobody is watching.
    """
    engine.error = BudgetExhausted("Out of credit.", spend=spent(tokens_usd="0.04", searches=2))
    runner = DiscoveryRunner(services.discovery, engine, settings.discovery_settings, spawn=lambda work: work())

    run_id = start(runner).id

    assert services.discovery.run_cost(run_id).direct == Decimal("0.05")
    assert services.discovery.searches_in_run(run_id) == 2


def test_a_run_cancelled_while_phase_one_worked_keeps_its_spend_and_discards_its_results(services, engine, settings):
    """Only the curator's decision is authoritative once they have made one.

    Writing the work list onto a run somebody stopped would resurrect the thing
    they stopped, and it must not raise out of the worker either — there is
    nobody to raise to.
    """
    held: list = []
    runner = DiscoveryRunner(services.discovery, engine, settings.discovery_settings, spawn=held.append)
    run_id = start(runner).id
    runner.cancel(run_id)

    # Phase 1 comes back after the cancel, exactly as it would on the worker.
    held[0]()

    run = services.discovery.get_run(run_id)
    assert run.status is RunStatus.CANCELLED
    assert services.discovery.list_candidate_works(run_id) == []


# -- refusals --------------------------------------------------------------------


def test_an_unwired_engine_refuses_to_start_rather_than_recording_a_failed_run(services, settings):
    """Nothing was attempted, so nothing should be recorded as having been."""
    runner = DiscoveryRunner(services.discovery, unavailable_engine(), settings.discovery_settings)

    with pytest.raises(ServiceError) as refusal:
        start(runner)

    assert "not wired up" in str(refusal.value)
    assert services.discovery.list_runs() == []


def test_spend_refuses_a_run_and_a_month_together_rather_than_silently_picking_one(runner):
    run_id = start(runner).id

    with pytest.raises(ServiceError) as refusal:
        runner.spend_report(run_id=run_id, year=2026, month=8)

    assert "one run or about one month" in str(refusal.value)


def test_spend_refuses_half_a_month(runner):
    with pytest.raises(ServiceError) as refusal:
        runner.spend_report(year=2026)

    assert "both year and month" in str(refusal.value)


def test_spend_over_a_run_includes_what_its_re_searches_cost(runner, services):
    """ "What did asking for this cost" is the total, not the narrower figure."""
    run_id = start(runner).id
    work = services.discovery.list_candidate_works(run_id)[0]
    child = services.discovery.start_resolve_run(candidate_work_ids=[work.id], initiated_by=InitiatedBy.WEB_UI)
    services.discovery.record_spend(category=SpendCategory.IMAGE_RESEARCH, cost_usd=Decimal("0.30"), discovery_run_id=child.id)

    report = runner.spend_report(run_id=run_id)

    assert report.scope == "run"
    assert report.run_direct_usd == Decimal("0.085")
    assert report.cost_usd == Decimal("0.385")


def test_spend_with_nothing_named_reports_the_current_utc_month(runner):
    """UTC, matching the boundary the provider's own credit limit resets on."""
    now = datetime.now(UTC)

    report = runner.spend_report()

    assert report.scope == "month"
    assert (report.year, report.month) == (now.year, now.month)
