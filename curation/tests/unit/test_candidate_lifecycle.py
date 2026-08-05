"""The CandidateWork state machine, and what acceptance does to the catalogue.

A verdict has two writers — the curator, and a resolution attempt finishing — and
only one of them is authoritative. Most of what is checked here is that boundary
holding: which transitions the curator may make, which ones a background job may
not, and what a work looks like on the far side of an acceptance.
"""

import pytest

from curation.persistence.discovery_records import ResolutionStatus, UnresolvedReason, Verdict
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

    accepted = discovery.set_verdict(work.id, Verdict.ACCEPTED).work

    assert accepted.verdict is Verdict.ACCEPTED
    assert accepted.decided_at is not None
    artwork = service.get_artwork(accepted.artwork_id).artwork
    assert artwork.title == "Nighthawks"
    assert artwork.status is ArtworkStatus.ACCEPTED


# -- the artist an accepted work is attributed to -------------------------------
#
# Q9 — who is the artist, for the physical label — has no answer for a discovered
# work until acceptance resolves one. The label renders what is stored here, and
# nothing downstream re-checks it, so the cases that matter are the ones where two
# names must not become one painter.


def test_an_accepted_work_carries_the_artist_that_was_proposed_for_it(discovery, resolved_work, service):
    """Q9, answerable for a discovered work — which it is not before acceptance."""
    work = resolved_work("Nighthawks", proposed_artist="Edward Hopper")

    accepted = discovery.set_verdict(work.id, Verdict.ACCEPTED).work

    detail = service.get_artwork(accepted.artwork_id)
    assert detail.artist is not None, "an accepted work with no artist cannot be labelled"
    assert detail.artist.name == "Edward Hopper"


def test_two_works_by_one_painter_share_one_artist_row(discovery, resolved_work, service):
    """The reason Artist is a row and not a string on the work."""
    first = resolved_work("Nighthawks", dedup_key="nighthawks", proposed_artist="Edward Hopper")
    second = resolved_work("Chop Suey", dedup_key="chop-suey", proposed_artist="Edward Hopper")

    one = discovery.set_verdict(first.id, Verdict.ACCEPTED).work
    two = discovery.set_verdict(second.id, Verdict.ACCEPTED).work

    assert service.get_artwork(one.artwork_id).artist.id == service.get_artwork(two.artwork_id).artist.id


def test_a_painter_named_a_second_way_still_lands_on_one_row(discovery, resolved_work, service):
    """`El Greco` and its parenthesised alias are one painter, decided in `dedup`."""
    first = resolved_work("View of Toledo", dedup_key="toledo", proposed_artist="El Greco")
    second = resolved_work(
        "The Disrobing of Christ", dedup_key="disrobing", proposed_artist="El Greco (Domenikos Theotokopoulos)"
    )

    one = discovery.set_verdict(first.id, Verdict.ACCEPTED).work
    two = discovery.set_verdict(second.id, Verdict.ACCEPTED).work

    assert service.get_artwork(one.artwork_id).artist.id == service.get_artwork(two.artwork_id).artist.id


def test_a_work_naming_no_artist_is_accepted_and_attributed_to_nobody(discovery, resolved_work, service):
    """An anonymous work is a real thing, not a failure to match."""
    work = resolved_work("Untitled")

    accepted = discovery.set_verdict(work.id, Verdict.ACCEPTED).work

    detail = service.get_artwork(accepted.artwork_id)
    assert detail.artwork.artist_id is None
    assert detail.artist is None


def test_two_unattributed_works_do_not_become_one_painter(discovery, resolved_work, service):
    """The merge that needs no two names to resemble each other.

    Both proposals normalise to the empty key. Treating that as an identity would
    attribute every anonymous work in the catalogue to one artist named nothing.
    """
    first = resolved_work("Untitled", dedup_key="untitled-1")
    second = resolved_work("Study", dedup_key="study", proposed_artist="   ")

    one = discovery.set_verdict(first.id, Verdict.ACCEPTED).work
    two = discovery.set_verdict(second.id, Verdict.ACCEPTED).work

    assert service.get_artwork(one.artwork_id).artwork.artist_id is None
    assert service.get_artwork(two.artwork_id).artwork.artist_id is None
    assert list(service.list_artists()) == []


def test_a_probable_duplicate_artist_is_reported_at_the_moment_it_is_minted(discovery, resolved_work):
    """The split is deliberate; leaving it silent is what would not be.

    A duplicate row is the reversible failure and is taken on purpose, because
    every rule that would merge these two also merges painters who are genuinely
    different. What must not happen is that it passes unremarked.
    """
    first = resolved_work("The Mill", dedup_key="mill", proposed_artist="Jacob van Ruisdael")
    discovery.set_verdict(first.id, Verdict.ACCEPTED)
    second = resolved_work("Wheatfields", dedup_key="wheatfields", proposed_artist="Jacob Isaacksz van Ruisdael")

    outcome = discovery.set_verdict(second.id, Verdict.ACCEPTED)

    assert outcome.minted_artist is not None
    assert [artist.name for artist in outcome.duplicate_candidates] == ["Jacob van Ruisdael"]


def test_matching_a_held_artist_reports_no_duplicate(discovery, resolved_work):
    first = resolved_work("Nighthawks", dedup_key="nighthawks", proposed_artist="Edward Hopper")
    discovery.set_verdict(first.id, Verdict.ACCEPTED)
    second = resolved_work("Chop Suey", dedup_key="chop-suey", proposed_artist="Edward Hopper")

    outcome = discovery.set_verdict(second.id, Verdict.ACCEPTED)

    assert outcome.minted_artist is None
    assert outcome.duplicate_candidates == ()


def test_a_rejection_mints_no_artist(discovery, resolved_work, service):
    """Attribution is a consequence of entering the catalogue, not of being judged."""
    work = resolved_work("Nighthawks", proposed_artist="Edward Hopper")

    outcome = discovery.set_verdict(work.id, Verdict.REJECTED)

    assert outcome.minted_artist is None
    assert list(service.list_artists()) == []


def test_rejecting_a_work_records_the_note_and_when_it_was_decided(discovery, resolved_work):
    work = resolved_work()

    rejected = discovery.set_verdict(work.id, Verdict.REJECTED, reason="Too well known.").work

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

    accepted = discovery.set_verdict(work.id, Verdict.ACCEPTED).work

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

    accepted = discovery.set_verdict(work.id, Verdict.ACCEPTED).work

    sources = service.list_sources(accepted.artwork_id)
    assert len(sources) == 2
    assert [source.is_primary for source in sources] == [True, False]
    assert sources[0].url == first.url


def test_a_candidate_without_established_rights_promotes_as_unknown(discovery, resolved_work, service):
    """Absence is not permitted on a source: 'unknown' is the honest reading."""
    work = resolved_work()

    accepted = discovery.set_verdict(work.id, Verdict.ACCEPTED).work

    assert service.list_sources(accepted.artwork_id)[0].rights_status is RightsStatus.UNKNOWN


def test_established_rights_survive_the_promotion(discovery, propose, add_image, service):
    work = propose()
    add_image(work, rights_status=RightsStatus.PUBLIC_DOMAIN)
    discovery.record_resolution(work.id)

    accepted = discovery.set_verdict(work.id, Verdict.ACCEPTED).work

    assert service.list_sources(accepted.artwork_id)[0].rights_status is RightsStatus.PUBLIC_DOMAIN


def test_how_to_fetch_the_bytes_travels_with_the_instance(discovery, resolved_work, service):
    """The one field of a source that a promotion could otherwise only guess.

    A wrong guess surfaces as a re-acquisition that fails at exactly the moment
    every derived file has already been lost.
    """
    work = resolved_work()
    found = discovery.list_candidate_images(work.id)[0]

    accepted = discovery.set_verdict(work.id, Verdict.ACCEPTED).work

    assert service.list_sources(accepted.artwork_id)[0].acquisition_method is found.acquisition_method


def test_a_rejected_work_never_becomes_an_artwork(discovery, resolved_work, service):
    work = resolved_work()

    rejected = discovery.set_verdict(work.id, Verdict.REJECTED).work

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
    """A work nothing was found for is reported, not dropped — with which kind of nothing it was."""
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


# -- which kind of nothing -----------------------------------------------------
#
# `unresolved` is reached by routes that are not interchangeable, and a curator
# reading a bare one cannot tell an invented title from a scan too small for the
# wall. Two of the reasons are read from the rows the work already holds; the rest
# travel in from the search, because a result it discarded never became a row.


def test_a_resolved_work_carries_no_reason(resolved_work):
    """The column answers a question a resolved work is not asking."""
    work = resolved_work()

    assert work.resolution_status is ResolutionStatus.RESOLVED
    assert work.unresolved_reason is None


def test_a_work_whose_surviving_scans_are_all_below_the_floor_says_so(discovery, propose, add_image):
    """The collection has it. It would render as a postage stamp."""
    work = propose()
    add_image(work, estimated_width=600, estimated_height=450)

    outcome = discovery.record_resolution(work.id)

    assert outcome.resolution_status is ResolutionStatus.UNRESOLVED
    assert outcome.work.unresolved_reason is UnresolvedReason.BELOW_FLOOR


def test_a_work_whose_every_scan_the_curator_turned_down_says_so(discovery, resolved_work):
    """The route that is reached from the re-search rather than from the rejection.

    Rejecting an instance sets the *verdict*; it is the attempt afterwards that
    finds nothing to add and writes `unresolved`. Judging this value unreachable
    by reading the rejection path is exactly the mistake that nearly left it out
    — reachability is a property of the paths that arrive, not of the site that
    looks most likely to set it.
    """
    work = resolved_work()
    discovery.reject_image(discovery.list_candidate_images(work.id)[0].id)

    outcome = discovery.record_resolution(work.id)

    assert outcome.resolution_status is ResolutionStatus.UNRESOLVED
    assert outcome.work.unresolved_reason is UnresolvedReason.ALL_REJECTED


def test_a_work_holding_no_rows_reports_the_deepest_gate_its_results_reached(discovery, propose):
    """Deeper beats shallower: the museum having it under another name is the news.

    A search that turned away a different painting *and* the right title under
    the wrong painter has learned that the collection holds something. Reporting
    the shallower refusal would say the opposite.
    """
    work = propose()

    outcome = discovery.record_resolution(
        work.id, refusals=frozenset({UnresolvedReason.NOT_HELD, UnresolvedReason.IDENTITY_REFUSED})
    )

    assert outcome.work.unresolved_reason is UnresolvedReason.IDENTITY_REFUSED


def test_a_work_whose_search_refused_nothing_reports_not_held(discovery, propose):
    """A provider that returned nothing refused nothing, and that is a fact about the collection."""
    outcome = discovery.record_resolution(propose().id)

    assert outcome.work.unresolved_reason is UnresolvedReason.NOT_HELD


def test_a_reason_derived_from_rows_outranks_anything_the_search_refused(discovery, propose, add_image):
    """A row on the card is further than a result that never became one.

    Without this the below-floor scan a curator can see on the card would be
    reported as a title the collection does not hold, because the same search
    also turned away a different painting.
    """
    work = propose()
    add_image(work, estimated_width=600, estimated_height=450)

    outcome = discovery.record_resolution(work.id, refusals=frozenset({UnresolvedReason.NOT_HELD}))

    assert outcome.work.unresolved_reason is UnresolvedReason.BELOW_FLOOR


def test_every_unresolved_reason_is_ranked(discovery, propose):
    """Derived from the enum, so a sixth member fails here rather than tying silently.

    A hardcoded list of today's members is correct and useless in the one
    direction this exists to guard: the member added without a depth.
    """
    for reason in UnresolvedReason:
        assert isinstance(reason.depth, int)


def test_the_reason_survives_the_round_trip_to_the_store(discovery, propose):
    """Asserting on the returned record alone would pass with the column unmapped."""
    work = propose()
    discovery.record_resolution(work.id, refusals=frozenset({UnresolvedReason.SIZE_UNKNOWN}))

    assert discovery.get_candidate_work(work.id).unresolved_reason is UnresolvedReason.SIZE_UNKNOWN


def test_a_work_that_resolves_after_being_unresolved_drops_its_reason(discovery, propose, add_image):
    """A stale reason beside a resolved work is worse than none: it reads as current."""
    work = propose()
    discovery.record_resolution(work.id)
    add_image(work)

    outcome = discovery.record_resolution(work.id)

    assert outcome.resolution_status is ResolutionStatus.RESOLVED
    assert discovery.get_candidate_work(work.id).unresolved_reason is None


def test_a_re_search_finishing_after_an_acceptance_reports_but_does_not_apply(discovery, resolved_work, add_image):
    """Only the curator's verdict is authoritative, and this is the guard that keeps it so.

    Without it a resolve run completing after an accept writes `pending` over
    `accepted`, leaving a work with an `artwork_id` and a non-accepted verdict —
    a combination nothing else in this model can produce or repair.
    """
    work = resolved_work()
    accepted = discovery.set_verdict(work.id, Verdict.ACCEPTED).work
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
