"""The DiscoveryRun state machine, including the edges that must not exist.

A run's status is what a curator polls, what a re-search is refused against, and
what tells an operator whether to re-run something or investigate it. Every one
of those depends on the machine being closed rather than described: a transition
the code merely never makes is one the next caller can still make.

The reconciliation tests are here because startup repair is a transition too —
the only one the run's own process cannot write, which is exactly why it exists.
"""

import logging
from decimal import Decimal

import pytest

from curation.persistence.discovery_records import InitiatedBy, RunKind, RunStatus
from curation.services.errors import ServiceError


def _resolve_run(discovery, propose):
    """A re-search over one work, which is the only way a resolve run is made."""
    work = propose()
    return discovery.start_resolve_run(candidate_work_ids=[work.id], initiated_by=InitiatedBy.WEB_UI)


# -- phase 1 ------------------------------------------------------------------


def test_a_discovery_run_starts_in_phase_one_with_the_intent_recorded_verbatim(discovery):
    run = discovery.start_discovery_run(intent_text="  Surrealist paintings  ", initiated_by=InitiatedBy.MCP_CLIENT)

    assert run.status is RunStatus.RESOLVING_WORKS
    assert run.kind is RunKind.DISCOVERY
    assert run.intent_text == "Surrealist paintings"
    assert run.initiated_by is InitiatedBy.MCP_CLIENT
    assert run.parent_run_id is None


def test_a_short_work_list_goes_straight_to_phase_two(discovery, run, propose):
    propose("Nighthawks")

    advanced = discovery.finish_work_list(run.id, approval_threshold=5)

    assert advanced.status is RunStatus.RESOLVING_IMAGES
    assert advanced.approval_required is False


def test_more_works_than_the_threshold_stops_for_the_curator(discovery, run, propose):
    """The gate is on scope: 'you asked for Dalí and I found 200 works — really?'"""
    for index in range(3):
        propose(f"Work {index}")

    advanced = discovery.finish_work_list(run.id, approval_threshold=2)

    assert advanced.status is RunStatus.AWAITING_APPROVAL
    assert advanced.approval_required is True


def test_whether_the_gate_fired_is_stored_rather_than_re_derived(discovery, run, propose):
    """The threshold is configuration, and configuration changes.

    A run that stopped for approval last month must still read that way under
    today's setting, so the answer is a stored fact about the run rather than a
    comparison redone at read time.
    """
    for index in range(3):
        propose(f"Work {index}")
    discovery.finish_work_list(run.id, approval_threshold=2)

    assert discovery.get_run(run.id).approval_required is True


def test_the_estimate_is_recorded_when_the_work_list_closes(discovery, run, propose):
    propose()

    advanced = discovery.finish_work_list(run.id, approval_threshold=5, estimated_cost_usd=Decimal("0.42"))

    assert advanced.estimated_cost_usd == Decimal("0.42")


def test_approving_releases_phase_two(discovery, run, propose):
    propose()
    discovery.finish_work_list(run.id, approval_threshold=0)

    assert discovery.approve_run(run.id).status is RunStatus.RESOLVING_IMAGES


def test_declining_ends_the_run_without_phase_two_ever_spending(discovery, run, propose):
    propose()
    discovery.finish_work_list(run.id, approval_threshold=0)

    declined = discovery.decline_run(run.id)

    assert declined.status is RunStatus.DECLINED
    assert declined.completed_at is not None


# -- the endings, which are six different things ------------------------------


def test_a_run_completes_even_when_some_works_resolved_and_others_did_not(discovery, run, propose, add_image):
    """A run that resolved 1 of 2 works succeeded partially; it did not fail."""
    found = propose("Nighthawks")
    add_image(found)
    discovery.record_resolution(found.id)
    lost = propose("A Work That Does Not Exist")
    discovery.record_resolution(lost.id)
    discovery.finish_work_list(run.id, approval_threshold=5)

    completed = discovery.complete_run(run.id, actual_cost_usd=Decimal("0.31"))

    assert completed.status is RunStatus.COMPLETED
    assert completed.unresolved_work_count == 1
    assert completed.actual_cost_usd == Decimal("0.31")


@pytest.mark.parametrize(
    ("ending", "expected"),
    [
        ("fail_run", RunStatus.FAILED),
        ("halt_run_for_budget", RunStatus.HALTED_BY_BUDGET),
        ("cancel_run", RunStatus.CANCELLED),
    ],
)
def test_each_ending_records_the_thing_that_actually_happened(discovery, run, ending, expected):
    """None of the terminal states may absorb another.

    An interrupted run is re-run and a failed one is investigated; a curator who
    declined is not a cap that fired. Folding any two together would need a
    free-text reason field to tell them apart again.
    """
    ended = getattr(discovery, ending)(run.id)

    assert ended.status is expected
    assert ended.completed_at is not None


def test_a_cancelled_run_keeps_what_it_already_spent(discovery, run):
    """The spend happened, whatever the curator decided afterwards."""
    discovery.fail_run(run.id, actual_cost_usd=Decimal("0.19"))

    assert discovery.get_run(run.id).actual_cost_usd == Decimal("0.19")


def test_a_run_can_be_cancelled_while_it_waits_for_the_curator(discovery, run, propose):
    propose()
    discovery.finish_work_list(run.id, approval_threshold=0)

    assert discovery.cancel_run(run.id).status is RunStatus.CANCELLED


# -- the edges that must not exist --------------------------------------------


def test_a_finished_run_cannot_be_finished_again(discovery, run):
    discovery.cancel_run(run.id)

    with pytest.raises(ServiceError, match="already ended as cancelled"):
        discovery.fail_run(run.id)


def test_a_finished_run_cannot_be_reopened_for_approval(discovery, run, propose):
    """A completed run never reopens, however a later re-search turns out."""
    propose()
    discovery.finish_work_list(run.id, approval_threshold=0)
    discovery.decline_run(run.id)

    with pytest.raises(ServiceError, match="is declined"):
        discovery.approve_run(run.id)


def test_phase_one_cannot_be_closed_twice(discovery, run, propose):
    propose()
    discovery.finish_work_list(run.id, approval_threshold=5)

    with pytest.raises(ServiceError, match="is resolving_images"):
        discovery.finish_work_list(run.id, approval_threshold=5)


def test_a_run_still_in_phase_one_cannot_complete(discovery, run):
    with pytest.raises(ServiceError, match="is resolving_works"):
        discovery.complete_run(run.id)


def test_a_run_awaiting_the_curator_cannot_complete_behind_their_back(discovery, run, propose):
    propose()
    discovery.finish_work_list(run.id, approval_threshold=0)

    with pytest.raises(ServiceError, match="is awaiting_approval"):
        discovery.complete_run(run.id)


# -- the re-search is the same entity, entering later -------------------------


def test_a_resolve_run_enters_at_phase_two_carrying_its_parent(discovery, propose):
    work = propose()

    resolve = discovery.start_resolve_run(candidate_work_ids=[work.id], initiated_by=InitiatedBy.WEB_UI)

    assert resolve.kind is RunKind.RESOLVE
    assert resolve.status is RunStatus.RESOLVING_IMAGES
    assert resolve.parent_run_id == work.discovery_run_id
    assert resolve.intent_text is None


def test_a_resolve_run_can_never_reach_the_phase_one_states_it_skipped(discovery, propose):
    """Phase 1 already happened on the parent, so there is no work list to approve."""
    resolve = _resolve_run(discovery, propose)

    with pytest.raises(ServiceError, match="is resolving_images"):
        discovery.finish_work_list(resolve.id, approval_threshold=5)
    with pytest.raises(ServiceError, match="is resolving_images"):
        discovery.approve_run(resolve.id)
    with pytest.raises(ServiceError, match="is resolving_images"):
        discovery.decline_run(resolve.id)


def test_a_resolve_run_never_proposes_new_works(discovery, propose):
    resolve = _resolve_run(discovery, propose)

    with pytest.raises(ServiceError, match="resolve run"):
        discovery.propose_work(
            run_id=resolve.id,
            proposed_title="Something New",
            rationale="Nothing asked for this.",
            work_dedup_key="something-new",
        )


def test_a_re_search_needs_something_to_re_search(discovery):
    with pytest.raises(ServiceError, match="at least one candidate work"):
        discovery.start_resolve_run(candidate_work_ids=[], initiated_by=InitiatedBy.WEB_UI)


def test_a_re_search_covers_one_originating_run_because_that_is_what_its_cost_attributes_to(discovery, propose):
    first = propose("Nighthawks")
    other_run = discovery.start_discovery_run(intent_text="American realists", initiated_by=InitiatedBy.WEB_UI)
    second = propose("Automat", run_id=other_run.id, dedup_key="automat")

    with pytest.raises(ServiceError, match="one discovery run"):
        discovery.start_resolve_run(candidate_work_ids=[first.id, second.id], initiated_by=InitiatedBy.WEB_UI)


def test_a_resolve_run_reports_which_works_it_is_re_searching(discovery, propose):
    """Scope, not provenance: `status` on a resolve run has to say what it covers."""
    work = propose()
    resolve = discovery.start_resolve_run(candidate_work_ids=[work.id], initiated_by=InitiatedBy.WEB_UI)

    assert [covered.id for covered in discovery.covered_works(resolve.id)] == [work.id]


# -- startup reconciliation ---------------------------------------------------


def test_a_run_left_running_by_a_dead_process_is_marked_interrupted(discovery, run):
    """The state machine otherwise has no edge for process death.

    Every other terminal state is written by the run's own process, which a
    crashed process by definition cannot do.
    """
    discovery.reconcile()

    repaired = discovery.get_run(run.id)
    assert repaired.status is RunStatus.INTERRUPTED
    assert repaired.completed_at is not None


def test_reconciliation_moves_a_run_stopped_during_phase_two(discovery, run, propose):
    propose()
    discovery.finish_work_list(run.id, approval_threshold=5)

    discovery.reconcile()

    assert discovery.get_run(run.id).status is RunStatus.INTERRUPTED


def test_a_run_waiting_for_the_curator_survives_a_restart(discovery, run, propose):
    """`awaiting_approval` is human-held state, and curation restarts constantly.

    Reconciling it would let the documented deploy step destroy a pending
    decision along with the phase-1 spend already incurred to produce it.
    """
    propose()
    discovery.finish_work_list(run.id, approval_threshold=0)

    discovery.reconcile()

    assert discovery.get_run(run.id).status is RunStatus.AWAITING_APPROVAL


def test_reconciliation_leaves_finished_runs_exactly_as_they_finished(discovery, run):
    discovery.fail_run(run.id)

    discovery.reconcile()

    assert discovery.get_run(run.id).status is RunStatus.FAILED


def test_reconciliation_says_so_because_nothing_else_ever_will(discovery, run, caplog):
    """This line is the only signal a run died — the dying process cannot report it.

    Silence here is not the absence of a problem; it is the absence of the
    repair, and the operator's next clue would be a re-search refusing work ids.
    """
    with caplog.at_level(logging.WARNING):
        discovery.reconcile()

    warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == 1
    emitted = warnings[0].getMessage()
    assert run.id in emitted
    assert "resolving_works" in emitted


def test_reconciliation_reports_every_run_it_moves_and_not_one_line_for_all_of_them(discovery, run, caplog):
    second = discovery.start_discovery_run(intent_text="American realists", initiated_by=InitiatedBy.WEB_UI)

    with caplog.at_level(logging.WARNING):
        discovery.reconcile()

    moved = {record.getMessage() for record in caplog.records if record.levelno == logging.WARNING}
    assert len(moved) == 2
    assert any(run.id in message for message in moved)
    assert any(second.id in message for message in moved)


def test_a_catalogue_with_nothing_to_repair_is_repaired_silently(discovery, caplog):
    with caplog.at_level(logging.WARNING):
        discovery.reconcile()

    assert [record for record in caplog.records if record.levelno == logging.WARNING] == []
