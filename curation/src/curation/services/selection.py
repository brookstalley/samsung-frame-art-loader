"""Which image instance represents a candidate work, decided in one place.

A work usually has several instances and exactly one of them stands for it while
any unrejected instance exists. That ordering is asked for from more than one
direction — a resolution attempt choosing the instance to present, and a curator
rejecting the one on offer, which has to fall through to the next — so it lives
here rather than being decided twice and differently.

**Confidence leads, because the two axes conflict and only one of them is about
being right.** `confidence` asks whether this is genuinely that work rather than
a detail crop, a study, a poster, or an "after"; `quality_score` asks how good
the file is. A gorgeous scan of the wrong painting is worse than a modest scan of
the right one, so quality only breaks ties. Which axis should dominate varies by
`source_class` — for a contemporary web image there is usually one instance and
the whole risk is that it is the wrong one — and that weighting arrives with the
engine that ranks instances at discovery time. What is fixed here is that there
is exactly one ordering, and that a caller never invents its own.
"""

from collections.abc import Iterable

from curation.persistence.discovery_records import CandidateImage


def surviving(images: Iterable[CandidateImage]) -> list[CandidateImage]:
    """The instances still eligible, best first.

    A rejected instance is excluded from re-selection for its work — and only
    from that. The work itself stays eligible, which is the whole point of
    keeping instance suppression on a different key from work suppression:
    asking for a better scan must never blacklist the painting.
    """
    return sorted((image for image in images if image.rejected_at is None), key=_rank)


def _rank(image: CandidateImage) -> tuple[float, int, float, str]:
    """Sort key: confidence first, then quality, unscored last, id to break ties.

    Unscored is a separate term rather than a stand-in number, so the ordering
    does not quietly depend on what range quality scores happen to use. The id
    is last so the same set never comes back in two different orders.
    """
    return (
        -image.confidence,
        0 if image.quality_score is not None else 1,
        -(image.quality_score or 0.0),
        image.id,
    )


def best(images: Iterable[CandidateImage]) -> CandidateImage | None:
    """The instance that should represent the work, or None if none survives."""
    ranked = surviving(images)
    return ranked[0] if ranked else None
