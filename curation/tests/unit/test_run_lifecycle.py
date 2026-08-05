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

from curation.discovery.dedup import work_dedup_key
from curation.persistence.discovery_records import InitiatedBy, RunKind, RunStatus, Verdict
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


# -- startup reconciliation: stored titles ------------------------------------
#
# A title is stored as the engine seam cleaned it, so improving that cleaning
# leaves earlier rows carrying markup the product now knows how to strip. These
# enter through `reconcile` rather than through the repair itself: the repair
# only matters because startup calls it, and a test on the callee passes just as
# well with the call deleted.

#: A row exactly as the catalogue held it: a citation whose closing bracket a
#: greedy URL pattern ate, leaving the opening one and the words introducing it.
DAMAGED_TITLE = "Lobster Telephone (1938) - cited from tate.org.uk ("


def test_a_stored_title_carrying_citation_markup_is_recleaned_at_startup(discovery, run, propose):
    """The defect a curator saw: seven review cards titled with a broken citation."""
    work = propose(DAMAGED_TITLE, dedup_key="dali::lobster telephone 1938 cited from tate org uk")

    discovery.reconcile()

    assert discovery.get_candidate_work(work.id).proposed_title == "Lobster Telephone (1938)"


def test_recleaning_a_stored_title_recomputes_the_identity_derived_from_it(discovery, run, propose):
    """The half of the defect nobody could see.

    The key is derived from the title, so a row storing markup keys as a
    different painting from the same work proposed cleanly — and the column is
    what suppression reads. Repairing the title without the key would leave the
    visible defect fixed and the silent one intact.
    """
    work = propose(DAMAGED_TITLE, dedup_key="dali::lobster telephone 1938 cited from tate org uk")

    discovery.reconcile()

    assert discovery.get_candidate_work(work.id).work_dedup_key == work_dedup_key(title="Lobster Telephone")


def test_a_rejection_recorded_after_the_repair_suppresses_the_clean_proposal(discovery, run, propose):
    """What the re-key is *for*, one hop past the repair itself.

    Rejecting a work whose stored key carried markup would have suppressed only
    the markup — the next run proposing the painting cleanly derives a different
    key, finds no rejection under it, and shows the curator a work they turned
    down. Asserting the column alone would not catch that; this asks the question
    suppression actually asks.
    """
    work = propose(DAMAGED_TITLE, dedup_key="dali::lobster telephone 1938 cited from tate org uk")
    discovery.reconcile()

    discovery.set_verdict(work.id, Verdict.REJECTED, reason="A studio copy.")

    assert discovery.is_work_suppressed(work_dedup_key(title="Lobster Telephone")) is True


def test_a_stored_title_the_rules_do_not_reach_is_left_exactly_as_it_is(discovery, run, propose):
    """The no-op case, which is what makes running this at every start safe.

    `The Source` ends in a word that introduces a citation, and `Composition
    No.5` ends in something any loose hostname pattern matches. Both are titles,
    neither carries a citation, and a repair that touched them would merge them
    with `The` and `Composition`.
    """
    kept = [propose(title, dedup_key=title.lower()) for title in ("The Source", "Composition No.5")]

    discovery.reconcile()

    assert [discovery.get_candidate_work(work.id).proposed_title for work in kept] == [
        "The Source",
        "Composition No.5",
    ]
    assert [discovery.get_candidate_work(work.id).work_dedup_key for work in kept] == [
        "the source",
        "composition no.5",
    ]


def test_a_stored_title_that_was_nothing_but_a_citation_is_left_to_be_read(discovery, run, propose):
    """Cleaning can empty a value, and an empty title is not an improvement.

    `require_text` refuses one on the way in, so writing one here would make the
    row unreadable by the rules that guard every other write — and it would
    destroy the evidence of a cleaning rule that reached too far, which is the
    one thing anybody diagnosing it would need.
    """
    work = propose("tate.org.uk (", dedup_key="tate.org.uk (")

    discovery.reconcile()

    assert discovery.get_candidate_work(work.id).proposed_title == "tate.org.uk ("


def test_a_repaired_row_and_a_clean_one_become_the_same_work(discovery, run, propose):
    """The split the corruption caused, closed — and closed without deleting a row.

    A curator who saw the painting twice, once titled with a citation and once
    without, was looking at one work under two identities. After the repair they
    share one, so a verdict on either answers for both. Both rows stay: the key
    is an index rather than a unique constraint, and suppression asks whether
    *any* row sharing a key was rejected, so merging rows would only risk losing a
    decision that this keeps.
    """
    damaged = propose(DAMAGED_TITLE, dedup_key="dali::lobster telephone 1938 cited from tate org uk")
    clean = propose("Lobster Telephone", dedup_key=work_dedup_key(title="Lobster Telephone"))

    discovery.reconcile()

    repaired = discovery.get_candidate_work(damaged.id)
    assert repaired.work_dedup_key == discovery.get_candidate_work(clean.id).work_dedup_key
    discovery.set_verdict(clean.id, Verdict.REJECTED, reason="A studio copy.")
    assert discovery.is_work_suppressed(repaired.work_dedup_key) is True


def test_an_artist_the_cleaning_removes_entirely_becomes_unattributed_not_empty(discovery, run, propose):
    """The write path spells "no artist" `None`, and so must the repair.

    Storing `""` would put a value in the column that no proposal could produce —
    `_read_works` writes `artist or None` — leaving one path in the product able
    to mint a third state out of a two-state field.
    """
    work = propose(
        DAMAGED_TITLE,
        dedup_key="dali::lobster telephone 1938 cited from tate org uk",
        proposed_artist="tate.org.uk (",
    )

    discovery.reconcile()

    assert discovery.get_candidate_work(work.id).proposed_artist is None


def test_recleaning_stored_titles_says_how_many_a_curator_was_shown(discovery, run, propose, caplog):
    """A repair firing long after the rule changed means rows sat in front of
    someone carrying markup, and the count is the size of what they were shown."""
    propose(DAMAGED_TITLE, dedup_key="dali::lobster telephone 1938 cited from tate org uk")

    with caplog.at_level(logging.WARNING):
        discovery.reconcile()

    recleaned = [record for record in caplog.records if getattr(record, "event", None) == "works.recleaned"]
    assert len(recleaned) == 1
    assert recleaned[0].works_recleaned == 1


def test_recleaning_a_stored_title_is_done_after_the_first_start(discovery, run, propose, caplog):
    """Idempotent, because it runs at every start rather than once.

    A repair that kept finding work to do would rewrite the same rows forever and
    report a fresh repair on a catalogue that had none.
    """
    propose(DAMAGED_TITLE, dedup_key="dali::lobster telephone 1938 cited from tate org uk")
    discovery.reconcile()
    # Cleared because `caplog` accumulates across the whole test: without this the
    # first start's own repair line would satisfy the assertion below and the test
    # would pass whatever the second start did.
    caplog.clear()

    with caplog.at_level(logging.WARNING):
        discovery.reconcile()

    assert [record for record in caplog.records if getattr(record, "event", None) == "works.recleaned"] == []


@pytest.mark.parametrize("ending", ["fail_run", "halt_run_for_budget"])
def test_a_run_waiting_for_the_curator_cannot_break_or_be_halted(discovery, run, propose, ending):
    """Nothing is executing there, so neither ending describes something that happened.

    Both are things that happen to a run *while it works*. Leaving them reachable
    from `awaiting_approval` would put two edges in the machine that the model
    does not draw — the state the artifact already had to correct once for
    `awaiting_better_image`.
    """
    propose()
    discovery.finish_work_list(run.id, approval_threshold=0)

    with pytest.raises(ServiceError, match="nothing is running"):
        getattr(discovery, ending)(run.id)


@pytest.mark.parametrize(
    ("ending", "expected"), [("fail_run", RunStatus.FAILED), ("halt_run_for_budget", RunStatus.HALTED_BY_BUDGET)]
)
def test_phase_one_can_break_and_can_be_refused_by_the_provider(discovery, run, ending, expected):
    """Phase 1 makes model calls and can search the web, so it spends and it can fail.

    Drawing these only from phase 2 would leave the run that actually broke with
    no ending that says so, which is the absorption the six terminal states exist
    to prevent.
    """
    ended = getattr(discovery, ending)(run.id)

    assert ended.status is expected
    assert ended.completed_at is not None
