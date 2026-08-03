"""Which instance represents a work, and why that order is not the store's order.

The store lists a work's instances for a review card to read — chosen first, then
by confidence. Selection is a different question with a different answer, and the
two agreeing today is a coincidence rather than a guarantee. These tests pin the
policy directly, so that changing how a listing reads cannot quietly change which
image a work is represented by.
"""

from datetime import UTC, datetime

from curation.persistence.discovery_records import CandidateImage
from curation.persistence.records import AcquisitionMethod, SourceClass
from curation.services import selection


def _image(identifier: str, *, confidence: float, quality: float | None = None, rejected: bool = False) -> CandidateImage:
    return CandidateImage(
        id=identifier,
        candidate_work_id="c1",
        url=f"https://museum.example/{identifier}",
        provider="artic",
        source_class=SourceClass.INSTITUTIONAL,
        acquisition_method=AcquisitionMethod.DEZOOMIFY,
        confidence=confidence,
        quality_score=quality,
        rejected_at=datetime(2026, 7, 27, tzinfo=UTC) if rejected else None,
    )


def test_being_the_right_painting_outranks_being_a_better_file():
    """A gorgeous scan of the wrong work is worse than a modest scan of the right one.

    `confidence` asks whether this is genuinely that work rather than a detail
    crop, a study, a poster or an "after"; `quality_score` asks how good the file
    is. Only the first is about being right.
    """
    gigapixel = _image("gigapixel", confidence=0.4, quality=0.99)
    museum_plate = _image("plate", confidence=0.95, quality=0.30)

    assert selection.best([gigapixel, museum_plate]).id == "plate"


def test_quality_breaks_a_tie_on_confidence():
    modest = _image("modest", confidence=0.9, quality=0.2)
    sharp = _image("sharp", confidence=0.9, quality=0.8)

    assert selection.best([modest, sharp]).id == "sharp"


def test_an_unscored_instance_ranks_below_every_scored_one():
    """Unscored is not zero, and it is not best either — it is simply unknown."""
    unscored = _image("unscored", confidence=0.9)
    scored = _image("scored", confidence=0.9, quality=0.05)

    assert selection.best([unscored, scored]).id == "scored"


def test_the_same_instances_never_order_two_ways():
    """Paging a review card twice must not shuffle it, so ties break on the id."""
    first = _image("aaa", confidence=0.9, quality=0.5)
    second = _image("bbb", confidence=0.9, quality=0.5)

    assert [image.id for image in selection.surviving([second, first])] == ["aaa", "bbb"]
    assert [image.id for image in selection.surviving([first, second])] == ["aaa", "bbb"]


def test_a_rejected_instance_is_not_a_candidate_for_selection():
    turned_down = _image("turned-down", confidence=0.99, quality=0.99, rejected=True)
    survivor = _image("survivor", confidence=0.1)

    assert selection.best([turned_down, survivor]).id == "survivor"
    assert [image.id for image in selection.surviving([turned_down, survivor])] == ["survivor"]


def test_a_work_whose_every_instance_was_rejected_has_no_best_one():
    """Which is what sends it back to phase 2 rather than leaving it selectionless."""
    assert selection.best([_image("only", confidence=0.9, rejected=True)]) is None


def test_a_work_with_no_instances_at_all_has_no_best_one():
    assert selection.best([]) is None
