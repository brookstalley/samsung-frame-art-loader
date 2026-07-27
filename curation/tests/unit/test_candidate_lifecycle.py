"""The CandidateWork state machine, and what acceptance does to the catalogue.

A verdict has two writers — the curator, and a resolution attempt finishing — and
only one of them is authoritative. Most of what is checked here is that boundary
holding: which transitions the curator may make, which ones a background job may
not, and what a work looks like on the far side of an acceptance.
"""

import pytest

from curation.persistence.discovery_records import ResolutionStatus, Verdict
from curation.persistence.records import ArtworkStatus, RightsStatus
from curation.services.errors import ServiceError

# -- proposal ------------------------------------------------------------------


def test_a_proposed_work_starts_undecided_and_unresolved(propose):
    work = propose()

    assert work.verdict is Verdict.PENDING
    assert work.resolution_status is ResolutionStatus.PENDING
    assert work.artwork_id is None
    assert work.decided_at is None


def test_a_proposal_carries_why_it_was_proposed(propose):
    """A review card that cannot say why asks the curator to judge a bare title."""
    assert propose().rationale.startswith("The intent asked for Surrealism")


def test_a_proposal_without_a_reason_is_refused(discovery, run):
    with pytest.raises(ServiceError, match="rationale cannot be empty"):
        discovery.propose_work(run_id=run.id, proposed_title="Nighthawks", rationale="   ", work_dedup_key="nighthawks")


# -- the curator's verdicts ----------------------------------------------------


def test_accepting_a_work_mints_the_artwork_it_becomes(discovery, resolved_work, service):
    work = resolved_work("Nighthawks")

    accepted = discovery.set_verdict(work.id, Verdict.ACCEPTED)

    assert accepted.verdict is Verdict.ACCEPTED
    assert accepted.decided_at is not None
    artwork = service.get_artwork(accepted.artwork_id).artwork
    assert artwork.title == "Nighthawks"
    assert artwork.status is ArtworkStatus.ACCEPTED


def test_rejecting_a_work_records_the_note_and_when_it_was_decided(discovery, resolved_work):
    work = resolved_work()

    rejected = discovery.set_verdict(work.id, Verdict.REJECTED, reason="Too well known.")

    assert rejected.verdict is Verdict.REJECTED
    assert rejected.rejected_reason == "Too well known."
    assert rejected.decided_at is not None


def test_a_decided_work_is_not_decided_again(discovery, resolved_work):
    work = resolved_work()
    discovery.set_verdict(work.id, Verdict.REJECTED)

    with pytest.raises(ServiceError, match="already rejected, and that is final"):
        discovery.set_verdict(work.id, Verdict.ACCEPTED)


def test_pending_is_where_a_work_starts_rather_than_something_a_curator_chooses(discovery, resolved_work):
    work = resolved_work()

    with pytest.raises(ServiceError, match="not a decision"):
        discovery.set_verdict(work.id, Verdict.PENDING)


def test_the_curator_is_never_blocked_by_a_re_search_in_flight(discovery, resolved_work, add_image):
    """`set_verdict` constrains its target value only, never the state it comes from.

    A curator who has asked for a better scan may still accept the best instance
    on offer, or give up on the work, without waiting for a background job.
    """
    work = resolved_work()
    rejected_image = discovery.list_candidate_images(work.id)[0]
    add_image(work, confidence=0.4)
    discovery.reject_image(rejected_image.id)

    accepted = discovery.set_verdict(work.id, Verdict.ACCEPTED)

    assert accepted.verdict is Verdict.ACCEPTED


# -- acceptance is a promotion -------------------------------------------------


def test_every_instance_becomes_a_source_with_the_selected_one_primary(discovery, resolved_work, add_image, service):
    """Losing instances are retained: they are what makes re-acquisition survive.

    A work held by several institutions keeps working when one of them
    reorganises its site, which is the promise **Q6** rests on.
    """
    work = resolved_work()
    first = discovery.list_candidate_images(work.id)[0]
    add_image(work, url="https://other.example/1", confidence=0.5)

    accepted = discovery.set_verdict(work.id, Verdict.ACCEPTED)

    sources = service.list_sources(accepted.artwork_id)
    assert len(sources) == 2
    assert [source.is_primary for source in sources] == [True, False]
    assert sources[0].url == first.url


def test_a_candidate_without_established_rights_promotes_as_unknown(discovery, resolved_work, service):
    """Absence is not permitted on a source: 'unknown' is the honest reading."""
    work = resolved_work()

    accepted = discovery.set_verdict(work.id, Verdict.ACCEPTED)

    assert service.list_sources(accepted.artwork_id)[0].rights_status is RightsStatus.UNKNOWN


def test_established_rights_survive_the_promotion(discovery, propose, add_image, service):
    work = propose()
    add_image(work, rights_status=RightsStatus.PUBLIC_DOMAIN)
    discovery.record_resolution(work.id)

    accepted = discovery.set_verdict(work.id, Verdict.ACCEPTED)

    assert service.list_sources(accepted.artwork_id)[0].rights_status is RightsStatus.PUBLIC_DOMAIN


def test_how_to_fetch_the_bytes_travels_with_the_instance(discovery, resolved_work, service):
    """The one field of a source that a promotion could otherwise only guess.

    A wrong guess surfaces as a re-acquisition that fails at exactly the moment
    every derived file has already been lost.
    """
    work = resolved_work()
    found = discovery.list_candidate_images(work.id)[0]

    accepted = discovery.set_verdict(work.id, Verdict.ACCEPTED)

    assert service.list_sources(accepted.artwork_id)[0].acquisition_method is found.acquisition_method


def test_a_rejected_work_never_becomes_an_artwork(discovery, resolved_work, service):
    work = resolved_work()

    rejected = discovery.set_verdict(work.id, Verdict.REJECTED)

    assert rejected.artwork_id is None
    assert service.list_artworks().total == 0


# -- resolution attempts -------------------------------------------------------


def test_finding_an_instance_resolves_the_work_and_selects_it(discovery, propose, add_image):
    work = propose()
    found = add_image(work)

    outcome = discovery.record_resolution(work.id)

    assert outcome.resolution_status is ResolutionStatus.RESOLVED
    assert outcome.selected.id == found.id
    assert outcome.applied is True


def test_finding_nothing_is_an_outcome_rather_than_an_absent_row(discovery, propose):
    """Phase 2 finding no credible instance is the signal phase 1 invented the work."""
    work = propose("A Work That Does Not Exist")

    outcome = discovery.record_resolution(work.id)

    assert outcome.resolution_status is ResolutionStatus.UNRESOLVED
    assert outcome.selected is None
    assert discovery.get_candidate_work(work.id).resolution_status is ResolutionStatus.UNRESOLVED


def test_a_work_awaiting_a_better_image_returns_to_review_once_one_is_on_offer(discovery, resolved_work, add_image):
    work = resolved_work()
    discovery.reject_image(discovery.list_candidate_images(work.id)[0].id)
    add_image(work, url="https://better.example/1", confidence=0.95)

    outcome = discovery.record_resolution(work.id)

    assert outcome.work.verdict is Verdict.PENDING
    assert outcome.resolution_status is ResolutionStatus.RESOLVED


def test_a_re_search_that_finds_nothing_leaves_the_work_where_the_curator_put_it(discovery, resolved_work):
    """The dead end has to report itself rather than read as a silent no-op."""
    work = resolved_work()
    discovery.reject_image(discovery.list_candidate_images(work.id)[0].id)

    outcome = discovery.record_resolution(work.id)

    assert outcome.work.verdict is Verdict.AWAITING_BETTER_IMAGE
    assert outcome.resolution_status is ResolutionStatus.UNRESOLVED


def test_a_re_search_finishing_after_an_acceptance_reports_but_does_not_apply(discovery, resolved_work, add_image):
    """Only the curator's verdict is authoritative, and this is the guard that keeps it so.

    Without it a resolve run completing after an accept writes `pending` over
    `accepted`, leaving a work with an `artwork_id` and a non-accepted verdict —
    a combination nothing else in this model can produce or repair.
    """
    work = resolved_work()
    accepted = discovery.set_verdict(work.id, Verdict.ACCEPTED)
    add_image(work, url="https://later.example/1", confidence=0.99)

    outcome = discovery.record_resolution(work.id)

    assert outcome.applied is False
    assert outcome.resolution_status is ResolutionStatus.RESOLVED
    stored = discovery.get_candidate_work(work.id)
    assert stored.verdict is Verdict.ACCEPTED
    assert stored.artwork_id == accepted.artwork_id


def test_a_re_search_finishing_after_a_rejection_leaves_the_rejection_standing(discovery, resolved_work, add_image):
    work = resolved_work()
    discovery.set_verdict(work.id, Verdict.REJECTED)
    add_image(work, url="https://later.example/1", confidence=0.99)

    outcome = discovery.record_resolution(work.id)

    assert outcome.applied is False
    assert discovery.get_candidate_work(work.id).verdict is Verdict.REJECTED


def test_no_path_yields_a_work_holding_an_artwork_with_a_non_accepted_verdict(discovery, resolved_work, add_image):
    """The one combination the model cannot represent, checked after the sequence that used to produce it."""
    work = resolved_work()
    discovery.set_verdict(work.id, Verdict.ACCEPTED)
    add_image(work, url="https://later.example/1", confidence=0.99)
    discovery.record_resolution(work.id)

    stored = discovery.get_candidate_work(work.id)
    assert (stored.artwork_id is None) == (stored.verdict is not Verdict.ACCEPTED)
