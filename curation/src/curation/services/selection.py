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
from curation.services.display_fit import ArtworkBox, DisplayFit, assess_display_fit


def surviving(images: Iterable[CandidateImage]) -> list[CandidateImage]:
    """The instances still eligible, best first.

    A rejected instance is excluded from re-selection for its work — and only
    from that. The work itself stays eligible, which is the whole point of
    keeping instance suppression on a different key from work suppression:
    asking for a better scan must never blacklist the painting.

    **Below-floor instances are included here.** They are the alternates a review
    card offers, labelled with the size they would appear at, and a curator may
    choose one. What they are excluded from is being chosen *for* the curator —
    see `best`.
    """
    return sorted((image for image in images if image.rejected_at is None), key=_rank)


def below_floor(image: CandidateImage, box: ArtworkBox) -> bool:
    """Whether this instance would render smaller on the wall than the floor allows.

    An instance whose dimensions were never recorded is **not** below floor:
    "we do not know how big it is" and "we know it is too small" are different
    facts, and only the second justifies withholding it from selection. The
    engine that records instances refuses ones it cannot size, so this is the
    rule for rows that predate it rather than a path phase 2 produces.
    """
    if image.estimated_width is None or image.estimated_height is None:
        return False
    fit = assess_display_fit(width=image.estimated_width, height=image.estimated_height, box=box)
    return fit.fit is DisplayFit.BELOW_FLOOR


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


def best(images: Iterable[CandidateImage], *, box: ArtworkBox | None = None) -> CandidateImage | None:
    """The instance that should represent the work, or None if none may be chosen.

    **A below-floor instance is never chosen automatically**, which is why the
    artwork box comes in: the floor is a rendered size on the wall, so it cannot
    be read off a row without the panel geometry that turns pixels into inches.
    Passing no box means "no floor applies" and is what a caller with no
    deployment geometry to hand gets — the ranking, and nothing withheld.

    Returning `None` when every survivor is below floor is the specified
    outcome, not a gap: such a work holds no selection and is reported
    `unresolved`, which keeps a wall of postage stamps from being assembled
    silently while leaving every instance on the card for a curator who wants one
    anyway.
    """
    ranked = surviving(images)
    eligible = [image for image in ranked if not below_floor(image, box)] if box is not None else ranked
    return eligible[0] if eligible else None
