"""The questions this half of the model exists to answer.

A persisted format's requirements are its consumers' queries, so these are
written as the questions rather than as the mechanisms: each one is asked the way
a surface will ask it, and answered from stored data alone. A mechanism that
works while the question it exists for stays unanswerable is the failure this
file is here to catch.

Deliberately independent of any surface. These are service-layer calls, because
that is where the answer has to exist for an agent and a click to agree on it.
"""

from datetime import UTC, datetime
from decimal import Decimal

from curation.persistence.discovery_records import InitiatedBy, SpendCategory, Verdict
from curation.persistence.records import RightsStatus

# -- Q3: has this work already been suggested and rejected? -------------------
#
# The one most easily missed. Without persisted rejections every run re-proposes
# the works the curator has already declined, and the product feels broken in a
# way no single component is responsible for.


def test_a_declined_work_is_known_to_be_declined_in_a_later_run(discovery, resolved_work):
    work = resolved_work("Nighthawks", dedup_key="hopper::nighthawks")
    discovery.set_verdict(work.id, Verdict.REJECTED)

    later = discovery.start_discovery_run(intent_text="American realists", initiated_by=InitiatedBy.MCP_CLIENT)

    assert later.id != work.discovery_run_id
    assert discovery.is_work_suppressed("hopper::nighthawks") is True


def test_a_work_nobody_has_seen_is_not_suppressed(discovery):
    assert discovery.is_work_suppressed("hopper::automat") is False


# -- Q4: what has been spent this month, and what did this run cost? ----------


def test_what_this_run_cost_is_the_sum_of_what_it_was_billed(discovery, run):
    discovery.record_spend(category=SpendCategory.DISCOVERY_TOKENS, cost_usd=Decimal("0.13"), discovery_run_id=run.id)
    discovery.record_spend(category=SpendCategory.WEB_SEARCH, cost_usd=Decimal("0.06"), discovery_run_id=run.id, units=2)

    assert discovery.run_cost(run.id).direct == Decimal("0.19")


def test_asking_for_dali_costs_what_the_re_searches_cost_too(discovery, run, propose):
    """A re-search is its own run so it has a handle, a status and a cancel.

    The price of that is that "what did this intent cost" has to add the chain
    back up, which is what makes the second number the answer to the question a
    curator actually asks.
    """
    work = propose()
    discovery.record_spend(category=SpendCategory.DISCOVERY_TOKENS, cost_usd=Decimal("0.20"), discovery_run_id=run.id)
    resolve = discovery.start_resolve_run(candidate_work_ids=[work.id], initiated_by=InitiatedBy.WEB_UI)
    discovery.record_spend(category=SpendCategory.IMAGE_RESEARCH, cost_usd=Decimal("0.07"), discovery_run_id=resolve.id)

    cost = discovery.run_cost(run.id)

    assert cost.direct == Decimal("0.20")
    assert cost.total == Decimal("0.27")


def test_the_originating_run_never_reopens_to_absorb_a_re_search(discovery, run, propose):
    """The re-search's spend attributes to the re-search; only the total rolls up."""
    work = propose()
    discovery.finish_work_list(run.id, approval_threshold=5)
    discovery.complete_run(run.id, actual_cost_usd=Decimal("0.20"))
    resolve = discovery.start_resolve_run(candidate_work_ids=[work.id], initiated_by=InitiatedBy.WEB_UI)
    discovery.record_spend(category=SpendCategory.IMAGE_RESEARCH, cost_usd=Decimal("0.07"), discovery_run_id=resolve.id)

    assert discovery.get_run(run.id).actual_cost_usd == Decimal("0.20")
    assert discovery.run_cost(resolve.id).direct == Decimal("0.07")


def test_the_month_is_the_one_the_providers_own_cap_resets_on(discovery, run):
    """UTC, because the ceiling that can actually stop spending resets at midnight UTC.

    A report on the operator's local boundary would disagree with the only
    figure that is authoritative, and the disagreement would show up as a month
    that looks under budget while the key is already exhausted.
    """
    discovery.record_spend(
        category=SpendCategory.DISCOVERY_TOKENS,
        cost_usd=Decimal("1.00"),
        discovery_run_id=run.id,
        at=datetime(2026, 6, 30, 23, 59, 59, tzinfo=UTC),
    )
    discovery.record_spend(
        category=SpendCategory.DISCOVERY_TOKENS,
        cost_usd=Decimal("2.00"),
        discovery_run_id=run.id,
        at=datetime(2026, 7, 1, 0, 0, 0, tzinfo=UTC),
    )
    discovery.record_spend(
        category=SpendCategory.DISCOVERY_TOKENS,
        cost_usd=Decimal("4.00"),
        discovery_run_id=run.id,
        at=datetime(2026, 7, 31, 23, 59, 59, tzinfo=UTC),
    )
    discovery.record_spend(
        category=SpendCategory.MAT_COLOR_VISION,
        cost_usd=Decimal("8.00"),
        at=datetime(2026, 8, 1, 0, 0, 0, tzinfo=UTC),
    )

    assert discovery.spend_in_month(year=2026, month=7) == Decimal("6.00")


def test_december_rolls_into_the_next_year(discovery, run):
    discovery.record_spend(
        category=SpendCategory.DISCOVERY_TOKENS,
        cost_usd=Decimal("3.00"),
        discovery_run_id=run.id,
        at=datetime(2026, 12, 31, 23, 0, tzinfo=UTC),
    )
    discovery.record_spend(
        category=SpendCategory.DISCOVERY_TOKENS,
        cost_usd=Decimal("5.00"),
        discovery_run_id=run.id,
        at=datetime(2027, 1, 1, 1, 0, tzinfo=UTC),
    )

    assert discovery.spend_in_month(year=2026, month=12) == Decimal("3.00")


def test_spend_outside_any_run_is_still_this_months_spend(discovery, service):
    """Mat-colour vision has no run to attribute to and is still money."""
    artwork = service.add_artwork(title="Nighthawks")
    discovery.record_spend(
        category=SpendCategory.MAT_COLOR_VISION,
        cost_usd=Decimal("0.02"),
        artwork_id=artwork.id,
        at=datetime(2026, 7, 15, tzinfo=UTC),
    )

    assert discovery.spend_in_month(year=2026, month=7) == Decimal("0.02")


# -- Q5: where did this candidate come from, and why was it suggested? --------


def test_a_candidate_carries_the_run_that_proposed_it_and_the_reason(discovery, run, propose):
    work = propose("Nighthawks")

    stored = discovery.get_candidate_work(work.id)
    origin = discovery.get_run(stored.discovery_run_id)

    assert origin.id == run.id
    assert origin.intent_text == "Surrealist paintings"
    assert origin.initiated_by is InitiatedBy.MCP_CLIENT
    assert stored.rationale.startswith("The intent asked for Surrealism")


def test_provenance_is_not_overwritten_by_a_re_search(discovery, run, propose):
    """Which run *proposed* a work and which run is *re-searching* it are two facts.

    Overloading the first to mean the second would destroy the provenance, and
    the parent link cannot serve either, because a resolve run covers a subset.
    """
    work = propose()
    resolve = discovery.start_resolve_run(candidate_work_ids=[work.id], initiated_by=InitiatedBy.WEB_UI)

    assert discovery.get_candidate_work(work.id).discovery_run_id == run.id
    assert [covered.id for covered in discovery.covered_works(resolve.id)] == [work.id]
    assert resolve.parent_run_id == run.id


# -- Q10: which instances were found, which was selected, and on what basis? --


def test_a_work_reports_its_instances_the_chosen_one_first_with_its_reasoning(discovery, propose, add_image):
    work = propose()
    add_image(work, url="https://museum.example/plate", confidence=0.55, quality_score=0.9)
    gigapixel = add_image(work, url="https://gigapixel.example/scan", confidence=0.95, quality_score=0.4)
    discovery.select_image(gigapixel.id, rationale="The museum's own page, so canonicity is not in question.")

    images = discovery.list_candidate_images(work.id)

    assert images[0].id == gigapixel.id
    assert images[0].is_selected is True
    assert images[0].selection_rationale == "The museum's own page, so canonicity is not in question."
    assert len(images) == 2


def test_the_two_axes_are_kept_apart_because_they_conflict(discovery, propose, add_image):
    """A museum's own page is maximum confidence and may be lower resolution.

    Collapsing them into one number would make the trade invisible and the
    choice unexplainable — which is exactly what the review card has to explain.
    """
    work = propose()
    canonical = add_image(work, url="https://museum.example/1", confidence=0.99, quality_score=0.3)

    stored = discovery.list_candidate_images(work.id)[0]

    assert (stored.confidence, stored.quality_score) == (0.99, 0.3)
    assert stored.id == canonical.id


def test_an_instance_records_where_it_came_from_and_what_is_known_about_its_rights(discovery, propose, add_image):
    work = propose()
    add_image(
        work,
        url="https://artic.edu/artworks/111628",
        rights_status=RightsStatus.PUBLIC_DOMAIN,
        estimated_width=6000,
        estimated_height=4000,
    )

    stored = discovery.list_candidate_images(work.id)[0]

    assert stored.provider == "artic"
    assert stored.rights_status is RightsStatus.PUBLIC_DOMAIN
    assert (stored.estimated_width, stored.estimated_height) == (6000, 4000)


# -- Q11: has this image been rejected for a work the curator still wants? ----


def test_a_rejected_instance_stays_rejected_while_its_work_stays_wanted(discovery, resolved_work, add_image):
    """Q3's trap. One suppression key for both scopes is the bug, and it is
    invisible until a curator wonders why a work they asked to keep never came back."""
    work = resolved_work("Nighthawks")
    turned_down = discovery.list_candidate_images(work.id)[0]
    add_image(work, url="https://better.example/1", confidence=0.4)

    discovery.reject_image(turned_down.id)

    images = {image.id: image for image in discovery.list_candidate_images(work.id)}
    assert images[turned_down.id].rejected_at is not None
    assert images[turned_down.id].is_selected is False
    assert discovery.is_work_suppressed(work.work_dedup_key) is False
    assert discovery.get_candidate_work(work.id).verdict is Verdict.AWAITING_BETTER_IMAGE


def test_a_re_search_never_hands_back_the_instance_that_was_turned_down(discovery, resolved_work, add_image):
    work = resolved_work("Nighthawks")
    turned_down = discovery.list_candidate_images(work.id)[0]
    discovery.reject_image(turned_down.id)
    fresh = add_image(work, url="https://better.example/1", confidence=0.99)

    outcome = discovery.record_resolution(work.id)

    assert outcome.selected.id == fresh.id


# -- Q12: which works could not be resolved, and which kind of nothing was it? --
#
# A model asked for an artist's famous works will occasionally invent a
# plausible title. A work no credible instance can be found for is evidence of
# exactly that, so the run must be able to say "these N could not be resolved"
# rather than quietly returning a shorter list.


def test_a_run_reports_how_many_works_it_could_not_resolve(discovery, run, propose, add_image):
    for title in ("Nighthawks", "Automat"):
        found = propose(title)
        add_image(found)
        discovery.record_resolution(found.id)
    for title in ("An Invented Title", "Another Invented Title"):
        discovery.record_resolution(propose(title).id)
    discovery.finish_work_list(run.id, approval_threshold=10)

    completed = discovery.complete_run(run.id)

    assert completed.unresolved_work_count == 2
    assert {work.proposed_title for work in discovery.run_results(run.id).unresolved} == {
        "An Invented Title",
        "Another Invented Title",
    }


def test_the_count_a_run_reported_is_not_rewritten_by_later_work(discovery, run, propose, add_image):
    """It is the run's own report of what it could not do, and must not drift."""
    lost = propose("An Invented Title")
    discovery.record_resolution(lost.id)
    discovery.finish_work_list(run.id, approval_threshold=10)
    discovery.complete_run(run.id)

    resolve = discovery.start_resolve_run(candidate_work_ids=[lost.id], initiated_by=InitiatedBy.WEB_UI)
    add_image(lost, url="https://found-at-last.example/1")
    discovery.record_resolution(lost.id)
    discovery.complete_run(resolve.id)

    assert discovery.get_run(run.id).unresolved_work_count == 1
    assert discovery.get_run(resolve.id).unresolved_work_count == 0
