"""The pipeline's write-time rules, one section per rule.

These are the constraints the data model states for everything before
acceptance, checked where the data model says they are enforced: at write time,
in the service layer. A rule applied on the way out instead of on the way in is
a rule the stored data can already violate, and by then the violation is
permanent.

Each section names the rule it covers and the failure that rule exists to
prevent, because a test that only asserts the mechanism stops explaining itself
the moment somebody wonders whether the mechanism is still wanted.
"""

import logging
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from curation.persistence.discovery_records import InitiatedBy, ResolutionStatus, RunStatus, SpendCategory, Verdict
from curation.services.errors import ServiceError

# -- 7. Suppression has two scopes and they never share a key ------------------
#
# Rejecting a *work* suppresses the work. Rejecting an *image* must suppress
# only that image and leave the work eligible — otherwise asking for a better
# scan of a painting silently blacklists the painting. Enforcing (b) through (a)
# is the failure mode, and it is invisible until a curator wonders why a work
# they asked to keep never came back.


def test_a_rejected_work_is_not_proposed_again(discovery, resolved_work, propose):
    work = resolved_work("Nighthawks")
    discovery.set_verdict(work.id, Verdict.REJECTED)

    with pytest.raises(ServiceError, match="already been proposed and rejected"):
        propose("Nighthawks")


def test_suppression_follows_the_work_identity_rather_than_the_title(discovery, resolved_work, propose):
    """The dedup key is the identity, so a re-titled proposal is still the same work."""
    work = resolved_work("Nighthawks", dedup_key="hopper::nighthawks")
    discovery.set_verdict(work.id, Verdict.REJECTED)

    with pytest.raises(ServiceError, match="already been proposed and rejected"):
        propose("Nighthawks (1942)", dedup_key="hopper::nighthawks")


def test_the_curator_may_reconsider_a_work_they_declined(discovery, resolved_work, propose):
    """The rule is 'unless the curator explicitly reconsiders it' — never by accident."""
    work = resolved_work("Nighthawks")
    discovery.set_verdict(work.id, Verdict.REJECTED)

    assert propose("Nighthawks", reconsider=True).proposed_title == "Nighthawks"


def test_a_work_still_under_review_does_not_suppress_itself(discovery, resolved_work):
    work = resolved_work("Nighthawks")

    assert discovery.is_work_suppressed(work.work_dedup_key) is False


def test_rejecting_an_image_leaves_the_work_eligible(discovery, resolved_work):
    """The trap the two scopes exist to avoid: asking for a better scan of a
    painting must never blacklist the painting."""
    work = resolved_work("Nighthawks")

    discovery.reject_image(discovery.list_candidate_images(work.id)[0].id)

    assert discovery.is_work_suppressed(work.work_dedup_key) is False


def test_rejecting_an_image_does_not_stop_the_work_being_proposed_again(discovery, resolved_work, propose):
    work = resolved_work("Nighthawks")
    discovery.reject_image(discovery.list_candidate_images(work.id)[0].id)

    assert propose("Nighthawks").work_dedup_key == work.work_dedup_key


# -- 8. Exactly one instance per work is selected, while any survives that -----
#      clears the display floor
#
# Two states hold no selection, not one, and they are different situations:
#
#   - Every instance rejected. The work re-enters phase 2 rather than sitting
#     selectionless.
#   - Every surviving instance below the floor. Selection declines them all,
#     which is what the floor is for — nothing under it is chosen without being
#     asked for. Acceptance is refused until one is chosen explicitly, because
#     promoting with no selection mints an artwork whose every source is
#     non-primary. The tests for that refusal are in section 9, with the other
#     acceptance guards.


def test_the_first_instance_found_represents_the_work(discovery, propose, add_image):
    work = propose()

    found = add_image(work)

    assert discovery.list_candidate_images(work.id) == [found]
    assert found.is_selected is True


def test_a_second_instance_does_not_displace_the_selection_by_arriving(discovery, propose, add_image):
    work = propose()
    first = add_image(work)
    second = add_image(work, url="https://other.example/1")

    selected = [image for image in discovery.list_candidate_images(work.id) if image.is_selected]

    assert [image.id for image in selected] == [first.id]
    assert second.is_selected is False


def test_choosing_an_instance_stands_the_previous_one_down(discovery, propose, add_image):
    work = propose()
    first = add_image(work)
    second = add_image(work, url="https://other.example/1")

    discovery.select_image(second.id, rationale="Higher resolution at the same confidence.")

    images = {image.id: image for image in discovery.list_candidate_images(work.id)}
    assert images[second.id].is_selected is True
    assert images[first.id].is_selected is False
    assert images[second.id].selection_rationale == "Higher resolution at the same confidence."


def test_rejecting_the_selected_instance_falls_through_to_the_next(discovery, propose, add_image):
    """A work is never left representing itself by an image its curator rejected."""
    work = propose()
    best = add_image(work, confidence=0.9)
    runner_up = add_image(work, url="https://other.example/1", confidence=0.6)

    discovery.reject_image(best.id)

    images = {image.id: image for image in discovery.list_candidate_images(work.id)}
    assert images[runner_up.id].is_selected is True
    assert images[best.id].is_selected is False


def test_a_work_whose_every_instance_is_rejected_holds_no_selection(discovery, propose, add_image):
    work = propose()
    only = add_image(work)

    discovery.reject_image(only.id)

    assert [image for image in discovery.list_candidate_images(work.id) if image.is_selected] == []


def test_a_rejected_instance_can_never_be_selected_again(discovery, propose, add_image):
    """What 'the curator turned this scan down' has to mean for the next re-search."""
    work = propose()
    first = add_image(work)
    add_image(work, url="https://other.example/1", confidence=0.5)
    discovery.reject_image(first.id)

    with pytest.raises(ServiceError, match="cannot be selected again"):
        discovery.select_image(first.id)


def test_a_rejected_instance_is_not_re_selected_by_a_later_resolution(discovery, propose, add_image):
    work = propose()
    first = add_image(work, confidence=0.99)
    second = add_image(work, url="https://other.example/1", confidence=0.2)
    discovery.reject_image(first.id)

    outcome = discovery.record_resolution(work.id)

    assert outcome.selected.id == second.id


def test_an_instance_cannot_be_rejected_twice(discovery, propose, add_image):
    work = propose()
    only = add_image(work)
    discovery.reject_image(only.id)

    with pytest.raises(ServiceError, match="already rejected"):
        discovery.reject_image(only.id)


# -- 9. An unresolved work is never presented as accepted-able ----------------
#
# And never silently omitted from the run's results. It is reported.


def test_a_work_nothing_was_found_for_cannot_be_accepted(discovery, propose):
    work = propose("A Work That Does Not Exist")
    discovery.record_resolution(work.id)

    with pytest.raises(ServiceError, match="no image to accept it on"):
        discovery.set_verdict(work.id, Verdict.ACCEPTED)


def test_a_work_no_attempt_has_been_made_for_cannot_be_accepted(discovery, propose):
    """Accepting one would mint an artwork with no source, and so nothing to acquire."""
    work = propose()

    with pytest.raises(ServiceError, match="no image to accept it on"):
        discovery.set_verdict(work.id, Verdict.ACCEPTED)


def test_a_work_whose_only_image_was_turned_down_cannot_be_accepted(discovery, resolved_work):
    """`resolution_status` still reads `resolved` here — only a re-search recomputes it.

    Accepting on that would mint an artwork whose sole source is the scan its
    curator turned down, with no primary source naming what produced the original,
    because the rejection stood the selection down.
    """
    work = resolved_work()
    discovery.reject_image(discovery.list_candidate_images(work.id)[0].id)

    with pytest.raises(ServiceError, match="no image to accept it on"):
        discovery.set_verdict(work.id, Verdict.ACCEPTED)


def test_a_work_whose_every_scan_is_below_the_floor_cannot_be_accepted(discovery, propose, add_image, service):
    """The second selectionless state, and the one that reached the catalogue.

    Constraint 8 named only the all-rejected case, and the all-below-floor case
    was reachable the whole time: nothing is rejected, so the rejection guard
    passes, and `selection.best` has declined every instance — so promotion ran
    with nothing to make primary and minted an artwork whose every source carried
    `is_primary=False`. No record of which scan produced the original, and a scan
    on the wall that the floor exists precisely to stop anyone choosing by
    accident.
    """
    work = propose("A work only ever found small", dedup_key="small-only")
    for index in range(2):
        add_image(work, url=f"https://museum.example/small-{index}", estimated_width=600, estimated_height=450)
    work = discovery.record_resolution(work.id).work
    held = discovery.list_candidate_images(work.id)
    assert held and not any(image.is_selected for image in held), "the floor declined every one of them"
    assert all(image.rejected_at is None for image in held), "and none was rejected, so that guard does not fire"

    with pytest.raises(ServiceError, match="every scan found for it is below") as refused:
        discovery.set_verdict(work.id, Verdict.ACCEPTED)
    assert "already rejected" not in str(refused.value), "nothing here was rejected; the floor is the whole cause"

    assert discovery.get_candidate_work(work.id).artwork_id is None
    assert list(service.list_artworks(limit=10).entries) == [], "no artwork was minted on the way to the refusal"


def test_the_refusal_does_not_blame_the_floor_for_a_scan_the_curator_rejected(discovery, propose, add_image):
    """The same refusal, reached the other way, saying something different.

    A big scan was found and the curator turned it down; what survives is only the
    small one, so there is no selection and acceptance is still refused. But
    "every scan found for it is below the size this deployment will show" is
    *false* here — the big one was found, and rejecting it is what they just did.
    Accepting from `awaiting_better_image` is deliberately permitted, so this is an
    ordinary path rather than a corner, and a message that contradicts the
    curator's own last action is worse than no message.

    The cause is derived from the instances rather than asserted, which is the
    thing this test pins: the first guard in `_accept` already worked that way and
    the second one did not.
    """
    work = propose("A work found big and small", dedup_key="big-and-small")
    big = add_image(work, url="https://museum.example/big", estimated_width=6000, estimated_height=4500)
    add_image(work, url="https://museum.example/small", estimated_width=600, estimated_height=450)
    work = discovery.record_resolution(work.id).work
    discovery.reject_image(big.id)
    assert not any(image.is_selected for image in discovery.list_candidate_images(work.id))

    with pytest.raises(ServiceError, match="already rejected"):
        discovery.set_verdict(work.id, Verdict.ACCEPTED)


def test_a_below_floor_work_is_acceptable_once_an_instance_is_chosen(discovery, propose, add_image, service):
    """The floor forces a decision; it does not forbid the work.

    `api-contract.md` requires a below-floor instance to be shown, labelled and
    *selectable* — never hidden. Refusing acceptance outright would make the floor
    a veto instead of a prompt, so the refusal has to lift the moment a curator
    chooses one.
    """
    work = propose("A work only ever found small", dedup_key="small-only")
    small = add_image(work, url="https://museum.example/small", estimated_width=600, estimated_height=450)
    work = discovery.record_resolution(work.id).work
    discovery.select_image(small.id, rationale="Small, and I want it anyway.")

    accepted = discovery.set_verdict(work.id, Verdict.ACCEPTED).work

    assert accepted.artwork_id is not None
    sources = service.list_sources(accepted.artwork_id)
    assert [source.is_primary for source in sources] == [True], "the chosen scan is the work's primary source"
    assert sources[0].url == small.url


def test_a_work_with_one_surviving_image_can_still_be_accepted(discovery, resolved_work, add_image):
    """The guard is about there being something left, not about nothing having been rejected."""
    work = resolved_work()
    add_image(work)
    discovery.reject_image(discovery.list_candidate_images(work.id)[0].id)

    assert discovery.set_verdict(work.id, Verdict.ACCEPTED).work.verdict is Verdict.ACCEPTED


def test_an_unresolved_work_can_still_be_rejected(discovery, propose):
    """It is unacceptable, not undecidable — a curator may close it out."""
    work = propose("A Work That Does Not Exist")
    discovery.record_resolution(work.id)

    assert discovery.set_verdict(work.id, Verdict.REJECTED).work.verdict is Verdict.REJECTED


def test_an_unresolved_work_is_reported_rather_than_dropped(discovery, run, propose, add_image):
    found = propose("Nighthawks")
    add_image(found)
    discovery.record_resolution(found.id)
    lost = propose("A Work That Does Not Exist")
    discovery.record_resolution(lost.id)

    results = discovery.run_results(run.id)

    assert [work.id for work in results.resolved] == [found.id]
    assert [work.id for work in results.unresolved] == [lost.id]


# -- 11. `halted_by_budget` comes from the provider, never a local sum ---------
#
# A local tally that fails open is indistinguishable from one that works: no
# error, no alert, just a bill. The ceiling is a provider-side credit limit, and
# the spend table is attribution only.


def test_recording_spend_never_moves_a_run(discovery, run):
    """No amount of recorded cost decides anything, because nothing consults it."""
    for _ in range(50):
        discovery.record_spend(category=SpendCategory.DISCOVERY_TOKENS, cost_usd=Decimal("100.00"), discovery_run_id=run.id)

    assert discovery.get_run(run.id).status is RunStatus.RESOLVING_WORKS


def test_a_run_halts_only_when_the_caller_says_the_provider_refused(discovery, run):
    assert discovery.halt_run_for_budget(run.id).status is RunStatus.HALTED_BY_BUDGET


def test_spend_is_still_attributed_after_the_cap_fires(discovery, run):
    """The cap failing closed is not a reason to lose the record of what was spent."""
    discovery.record_spend(category=SpendCategory.WEB_SEARCH, cost_usd=Decimal("0.25"), discovery_run_id=run.id, units=5)
    discovery.halt_run_for_budget(run.id)

    assert discovery.run_cost(run.id).direct == Decimal("0.25")


# -- 14. A work is covered by at most one live resolve run --------------------
#
# Double-submitting the same ids would spend twice for one result, on the only
# operation that spends at all. The refusal names the ids rather than silently
# deduplicating: a curator who double-submitted should find out.


def test_a_second_re_search_over_the_same_work_is_refused_by_name(discovery, propose):
    work = propose("Nighthawks")
    discovery.start_resolve_run(candidate_work_ids=[work.id], initiated_by=InitiatedBy.WEB_UI)

    with pytest.raises(ServiceError) as refusal:
        discovery.start_resolve_run(candidate_work_ids=[work.id], initiated_by=InitiatedBy.MCP_CLIENT)

    assert "Nighthawks" in str(refusal.value)
    assert work.id in str(refusal.value)


def test_a_work_is_re_searchable_again_once_the_run_covering_it_ends(discovery, propose):
    work = propose()
    first = discovery.start_resolve_run(candidate_work_ids=[work.id], initiated_by=InitiatedBy.WEB_UI)
    discovery.complete_run(first.id)

    assert discovery.start_resolve_run(candidate_work_ids=[work.id], initiated_by=InitiatedBy.WEB_UI).parent_run_id


def test_a_crashed_re_search_does_not_block_its_works_forever(discovery, propose):
    """The guard against double-spend must not become a permanent block.

    'Non-terminal' is only safe to key on because startup reconciliation writes
    the one terminal state a dead process cannot write for itself. Without it a
    crash leaves these ids refused for the life of the catalogue.
    """
    work = propose()
    discovery.start_resolve_run(candidate_work_ids=[work.id], initiated_by=InitiatedBy.WEB_UI)

    discovery.reconcile()

    assert discovery.start_resolve_run(candidate_work_ids=[work.id], initiated_by=InitiatedBy.WEB_UI).id


def test_the_line_announcing_a_dead_run_can_be_found_by_that_runs_id(discovery, propose, caplog):
    """The only signal a run died has to be reachable by the documented query.

    A dying process cannot report its own death, so this WARNING is the whole
    record of it — and the way an operator reconstructs a run is to select on the
    `run_id` field. An id readable only inside the message text is invisible to
    that filter, so they would get every line of the run except the one saying it
    ended, and the observability spec tells them to read that silence as a
    *second*, non-existent defect.
    """
    work = propose()
    resolve = discovery.start_resolve_run(candidate_work_ids=[work.id], initiated_by=InitiatedBy.WEB_UI)

    with caplog.at_level(logging.WARNING):
        caplog.clear()
        discovery.reconcile()

    selected = [record for record in caplog.records if getattr(record, "run_id", None) == resolve.id]
    assert len(selected) == 1, "the dead run is not findable by its own id"
    assert selected[0].event == "run.interrupted"
    assert "interrupted" in selected[0].getMessage()


def test_coverage_survives_the_run_that_recorded_it(discovery, propose):
    """The join records the run's scope, which stays true after the run has ended."""
    work = propose()
    resolve = discovery.start_resolve_run(candidate_work_ids=[work.id], initiated_by=InitiatedBy.WEB_UI)
    discovery.complete_run(resolve.id)

    assert [covered.id for covered in discovery.covered_works(resolve.id)] == [work.id]


def test_the_same_work_named_twice_in_one_request_is_covered_once(discovery, propose):
    work = propose()

    resolve = discovery.start_resolve_run(candidate_work_ids=[work.id, work.id], initiated_by=InitiatedBy.WEB_UI)

    assert [covered.id for covered in discovery.covered_works(resolve.id)] == [work.id]


# -- 15. `awaiting_better_image` is reachable only through rejecting an image --
#
# The path that sets the instance's suppression and the path that sets the
# verdict are the same path, so the suppression can never be skipped. Both used
# to reach that state and only one set `rejected_at`, so a re-search could
# legitimately return the image the curator had just turned down.


def test_set_verdict_refuses_the_value_and_names_the_way_in(discovery, resolved_work):
    work = resolved_work()

    with pytest.raises(ServiceError, match="reject_image"):
        discovery.set_verdict(work.id, Verdict.AWAITING_BETTER_IMAGE)


def test_the_one_path_in_always_suppresses_the_instance_it_turned_down(discovery, resolved_work):
    work = resolved_work()
    image = discovery.list_candidate_images(work.id)[0]

    awaiting = discovery.reject_image(image.id)

    assert awaiting.verdict is Verdict.AWAITING_BETTER_IMAGE
    assert discovery.list_candidate_images(work.id)[0].rejected_at is not None


def test_a_work_already_decided_has_no_images_left_under_review(discovery, resolved_work):
    work = resolved_work()
    image = discovery.list_candidate_images(work.id)[0]
    discovery.set_verdict(work.id, Verdict.REJECTED)

    with pytest.raises(ServiceError, match="no longer under review"):
        discovery.reject_image(image.id)


# -- 6. Stored paths are relative to ART_ROOT ---------------------------------
#
# The rule the catalogue already obeys, applied to the one path this half of the
# model stores. A cached preview named absolutely would break the promise that
# the whole tree can be copied to a backup and restored anywhere.


def test_a_cached_preview_is_stored_relative_to_the_art_root(discovery, propose, add_image):
    work = propose()

    image = add_image(work, preview_path="api-cache/previews/nighthawks.jpg")

    assert image.preview_path == "api-cache/previews/nighthawks.jpg"


def test_an_absolute_preview_path_is_refused(discovery, propose, add_image):
    work = propose()

    with pytest.raises(ServiceError, match="must be relative to ART_ROOT"):
        add_image(work, preview_path="/mnt/photos/previews/nighthawks.jpg")


# -- money is money, not a float ----------------------------------------------


def test_a_cost_survives_the_file_exactly(discovery, run):
    """A tenth of a cent that cannot be represented is a rounding error in a
    total nobody will ever reconcile against the provider's own figure."""
    for _ in range(10):
        discovery.record_spend(category=SpendCategory.DISCOVERY_TOKENS, cost_usd=Decimal("0.01"), discovery_run_id=run.id)

    assert discovery.run_cost(run.id).direct == Decimal("0.10")


def test_a_negative_cost_is_refused(discovery, run):
    with pytest.raises(ServiceError, match="cannot be negative"):
        discovery.record_spend(category=SpendCategory.DISCOVERY_TOKENS, cost_usd=Decimal("-1.00"), discovery_run_id=run.id)


def test_spend_against_a_run_that_does_not_exist_is_refused(discovery):
    with pytest.raises(ServiceError, match="No discovery run"):
        discovery.record_spend(
            category=SpendCategory.DISCOVERY_TOKENS,
            cost_usd=Decimal("0.01"),
            discovery_run_id="not-a-run",
            at=datetime(2026, 7, 27, tzinfo=UTC),
        )


def test_an_unattempted_work_is_neither_resolved_nor_unresolved(discovery, run, propose):
    """Three buckets, because 'not yet tried' and 'tried and found nothing' are
    different facts, and only the second says anything at all about the work."""
    work = propose()

    results = discovery.run_results(run.id)

    assert [entry.id for entry in results.pending] == [work.id]
    assert results.resolved == [] and results.unresolved == []
    assert work.resolution_status is ResolutionStatus.PENDING


def test_spend_against_an_artwork_that_does_not_exist_is_refused(discovery):
    with pytest.raises(ServiceError, match="No artwork"):
        discovery.record_spend(
            category=SpendCategory.MAT_COLOR_VISION,
            cost_usd=Decimal("0.01"),
            artwork_id="not-an-artwork",
            at=datetime(2026, 7, 27, tzinfo=UTC),
        )


def test_rejecting_an_alternate_leaves_the_standing_selection_alone(discovery, propose, add_image):
    """Constraint 8 asks for exactly one selection, not for the highest-ranked one.

    A curator who chose the canonical instance and then pruned an alternate did
    not ask for their choice to be revisited, and the revision would be silent —
    the rejected image is not the one that changed.
    """
    work = propose()
    modest = add_image(work, url="https://museum.example/plate", confidence=0.4)
    # A survivor that outranks the choice, so re-ranking would visibly move the
    # selection rather than land back on it.
    add_image(work, url="https://gigapixel.example/scan", confidence=0.99)
    pruned = add_image(work, url="https://poster.example/print", confidence=0.7)
    discovery.select_image(modest.id, rationale="The holding museum's own plate.")

    discovery.reject_image(pruned.id)

    images = {image.id: image for image in discovery.list_candidate_images(work.id)}
    assert images[modest.id].is_selected is True
    assert images[modest.id].selection_rationale == "The holding museum's own plate."
    assert [image.id for image in images.values() if image.is_selected] == [modest.id]


def test_a_run_waiting_for_the_curator_holds_no_coverage_to_release(discovery, run, propose):
    """Only a resolve run covers works, and a resolve run never awaits approval.

    So "the ids are held by a run awaiting approval" describes a state this model
    cannot reach — which matters because it was written down as an operator
    remedy, and a remedy for an impossible state is a wrong instruction to a human
    trying to unstick something real.
    """
    work = propose()
    discovery.finish_work_list(run.id, approval_threshold=0)
    assert discovery.get_run(run.id).status is RunStatus.AWAITING_APPROVAL

    resolve = discovery.start_resolve_run(candidate_work_ids=[work.id], initiated_by=InitiatedBy.WEB_UI)

    assert resolve.status is RunStatus.RESOLVING_IMAGES
