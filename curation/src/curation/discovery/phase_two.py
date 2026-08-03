"""Phase 2: one work, a provider's instances, and which of them is the work.

This is the judgement the seam deliberately keeps out of a provider. A museum
reports what its collection holds; whether any of it is the painting a curator
asked for is decided here, once, in terms that do not vary by provider.

**Confidence is an identity comparison, never a relevance score.** The Art
Institute's search was measured returning a real work by a real artist, at a
comfortable score, for a painting it does not hold: asking for *The Persistence
of Memory* surfaces *Ann-In Memory* by Joseph Cornell. Ranking by the provider's
own number attaches that to the request and reports success. So the test is
whether the title the provider returned *is* the requested title, and whether the
artists agree — derived from `dedup`, which is where this product's answer to
"are these the same work" already lives and was measured. Reimplementing the
normalisation here would be a second answer free to drift from the one the dedup
key is built with.

**An artist disagreement is disqualifying, not a deduction.** The same collection
holds *American Gothic* by Grant Wood and *American Gothic* by Elizabeth Layton.
A scheme that scored the wrong one slightly lower would still select it whenever
the right one was absent, which is precisely the case that matters.

**Quality is whether the render is a downscale or a native-size paste**, graded
by how much of the artwork box the master covers — deliberately *not* the size
the instance renders at. Aspect-ratio mismatch dominates rendered size, so a tall
master with resolution to spare comes out shorter on a wide box than a small one
that suits the shape. The verdict comes from the same function the review grid
and the renderer use, so phase 2 does not grow a resolution policy of its own.

Quality breaks ties; it never overturns confidence, because a gorgeous scan of
the wrong painting is worse than a modest scan of the right one.

**The ordering is unconditional, and the `source_class`-dependent dominance the
data model describes is deliberately not built.** Nothing produces a
`contemporary_web` candidate — every instance phase 2 records comes from a museum
API and is `institutional` — so a switch on it would have one reachable branch and
one branch no deployment could exercise. What stands in its place is stronger
where it matters: confidence is not a weight but a gate, so an instance that is
not the requested work is refused rather than ranked lower, which for a work with
a single candidate image is the whole of the `contemporary_web` concern. The
unbuilt half is canonicity among many institutional copies, and it becomes real
when a second provider can offer copies of one work. `data-model.md` carries the
deferral and the trigger to reopen it.

**Below the floor is not a rejection.** Such an instance is recorded, offered,
and labelled with the size it would appear at — it is simply not selected without
a curator saying so. A work whose every instance is below the floor holds no
selection and is reported `unresolved`, which is a first-class outcome rather
than an absent row.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from curation.discovery.dedup import artist_key, title_key
from curation.discovery.images import FoundImage, ImageQuery, ImageSearch
from curation.persistence.records import RightsStatus
from curation.services.display_fit import ArtworkBox, DisplayFit, FitAssessment, assess_display_fit

log = logging.getLogger(__name__)

#: Confidence when the provider's title and artist both match what was asked for.
#: Not 1.0: this is a strong textual identity match, not an inspection of the
#: picture, and a number reserved for certainty leaves somewhere for a provider
#: that can actually verify the image to go.
CONFIDENT: Final[float] = 0.95

#: Confidence when the titles match and the *request* named no artist. Lower
#: because a title alone is a weaker identity — the collection holds two
#: different *American Gothic*s — and phase 1 not naming an artist is exactly
#: when that ambiguity is unresolvable here.
TITLE_ONLY: Final[float] = 0.75

#: Confidence when the titles match and the *provider* names no artist. Lower
#: still: the request was specific and the record cannot confirm the half that
#: would have settled it.
UNATTRIBUTED_RECORD: Final[float] = 0.6

#: How much of `quality_score` is resolution rather than rights. Rights are a
#: component of quality in the data model and a genuine provenance signal — an
#: institution's own public-domain scan is usually the authoritative file — but
#: they are weighted to break a tie and never to overturn a resolution
#: difference. **This is not a rights gate** (constraint 13): nothing is
#: excluded, filtered or refused on rights, and an in-copyright instance with
#: better resolution still wins.
_RESOLUTION_WEIGHT: Final[float] = 0.85

_RIGHTS_TERM: Final[dict[RightsStatus | None, float]] = {
    RightsStatus.PUBLIC_DOMAIN: 1.0,
    RightsStatus.IN_COPYRIGHT: 0.5,
    RightsStatus.UNKNOWN: 0.5,
    None: 0.5,
}

#: Where each fit verdict's band starts. Ordered and evenly spaced so that the
#: verdict dominates and coverage grades within it — a downscaled instance always
#: outranks one pasted at native size, whatever their rendered sizes work out to.
_BAND_BASE: Final[dict[DisplayFit, float]] = {
    DisplayFit.BELOW_FLOOR: 0.0,
    DisplayFit.MATTED_SMALL: 1 / 3,
    DisplayFit.NATIVE: 2 / 3,
}

_BAND_WIDTH: Final[float] = 1 / 3

#: How many times the artwork box a master must cover before extra resolution
#: stops counting. Not a cliff — it is where the top band saturates, so a
#: gigapixel scan and a merely generous one are distinguished but a scan ten
#: times larger than the wall can show gains nothing further for it.
_NATIVE_SATURATION: Final[float] = 4.0


@dataclass(frozen=True, slots=True)
class JudgedImage:
    """One instance, judged against the work it was found for.

    The `FitAssessment` travels with the judgement rather than being recomputed
    by a caller, because the rendered size is what the review card labels a
    below-floor instance with — and computing it twice is how the label and the
    decision come to disagree.
    """

    found: FoundImage
    confidence: float
    quality_score: float
    rationale: str
    fit: FitAssessment

    @property
    def below_floor(self) -> bool:
        """Whether this would render smaller on the wall than the floor allows."""
        return self.fit.fit is DisplayFit.BELOW_FLOOR


class PhaseTwoEngine:
    """Turn one work into the instances that are credibly it, best first."""

    def __init__(self, search: ImageSearch, *, box: ArtworkBox) -> None:
        self._search = search
        self._box = box

    def resolve(self, query: ImageQuery) -> Sequence[JudgedImage]:
        """Every credible instance for this work, most confident first.

        An empty result is a real answer and the caller must record it as one:
        it means nothing this provider holds is the work that was asked for,
        which is the signal that phase 1 may have proposed something that does
        not exist. Raises `ImageSearchFailure` when the provider could not be
        asked at all — a different fact, and one that says nothing about the work.
        """
        judged = [judgement for found in self._search.find_images(query) if (judgement := self._judge(query, found))]
        judged.sort(key=lambda entry: (entry.below_floor, -entry.confidence, -entry.quality_score, entry.found.url))
        log.info(
            "judged a work's instances",
            extra={
                "event": "phase_two.judged",
                "work_title": query.title,
                "instances_credible": len(judged),
                "instances_below_floor": sum(1 for entry in judged if entry.below_floor),
            },
        )
        return judged

    def fetch_preview(self, url: str) -> bytes | None:
        """The preview bytes for an instance, or `None` when they could not be got."""
        return self._search.fetch_preview(url)

    def _judge(self, query: ImageQuery, found: FoundImage) -> JudgedImage | None:
        """Score one instance, or reject it as not being the work at all."""
        confidence = _confidence(query, found)
        if confidence is None:
            log.info(
                "discarding a result that is not the work that was asked for",
                extra={
                    "event": "phase_two.not_the_work",
                    "work_title": query.title,
                    "found_title": found.title,
                    "found_artist": found.artist,
                },
            )
            return None
        if found.estimated_width is None or found.estimated_height is None:
            # An instance whose rendered size cannot be computed cannot be judged
            # against the floor, and one recorded anyway is indistinguishable
            # from one that clears it — which is the single thing the floor
            # exists to make visible. Dropped rather than recorded unassessable,
            # and logged so a provider that stops reporting dimensions shows up
            # as a run finding nothing rather than as a run finding everything.
            log.info(
                "discarding an instance whose size the provider did not report",
                extra={"event": "phase_two.size_unknown", "work_title": query.title, "found_title": found.title},
            )
            return None
        fit = assess_display_fit(width=found.estimated_width, height=found.estimated_height, box=self._box)
        quality = _quality(
            fit,
            found.rights_status,
            width=found.estimated_width,
            height=found.estimated_height,
            box=self._box,
        )
        return JudgedImage(
            found=found,
            confidence=confidence,
            quality_score=quality,
            rationale=_rationale(found, confidence=confidence, fit=fit, box=self._box),
            fit=fit,
        )


def _confidence(query: ImageQuery, found: FoundImage) -> float | None:
    """How sure we are this is that work, or `None` when it is not that work.

    `None` is deliberately not a low score. A near-match kept at low confidence
    is still selected the moment nothing better exists, which is exactly the
    situation a work the museum does not hold produces — so the only safe
    representation of "this is a different painting" is absence.
    """
    if title_key(query.title) != title_key(found.title):
        return None
    asked = artist_key(query.artist) if query.artist else ""
    holds = artist_key(found.artist) if found.artist else ""
    if asked and holds:
        return CONFIDENT if asked == holds else None
    if not asked:
        return TITLE_ONLY
    return UNATTRIBUTED_RECORD


def _quality(fit: FitAssessment, rights: RightsStatus | None, *, width: int, height: int, box: ArtworkBox) -> float:
    """How good this file is, as one number in 0..1.

    **The resolution metric is the fit verdict, not the rendered size**, and the
    difference is not academic. A 6949x8400 master rendered into a wide artwork
    box is limited by the box's height and comes out shorter on the wall than a
    2000x1500 one that happens to suit the shape — while having four times the
    resolution to spare. Ranking on rendered inches prefers the smaller file, and
    the requirement says so in as many words: canvas occupancy is dominated by
    aspect-ratio mismatch, and what isolates resolution is whether the render is a
    downscale or a native-size paste.

    So the verdict picks the band and coverage grades within it. Crossing from
    "pasted at native size" to "downscaled to fit" is a genuine step up rather
    than a continuous one, because it is the point where the file stops being the
    limiting factor.
    """
    resolution = _BAND_BASE.get(fit.fit, 0.0) + _BAND_WIDTH * _within_band(fit, width=width, height=height, box=box)
    # `.get` with the neutral term rather than indexing: a rights value added to
    # the enum later is an unranked one, not a crash in a worker thread that
    # would end the run.
    return _RESOLUTION_WEIGHT * resolution + (1 - _RESOLUTION_WEIGHT) * _RIGHTS_TERM.get(rights, 0.5)


def _within_band(fit: FitAssessment, *, width: int, height: int, box: ArtworkBox) -> float:
    """Where in its band this instance sits, in 0..1.

    Below the floor, how close it came to reaching it — the only band where the
    rendered size is the right measure, because the floor is itself a rendered
    size. Otherwise how much of the artwork box the master covers at its own
    resolution, saturating once it has several times more than the box can use:
    beyond that the extra pixels are not usable on this wall, and the losing
    instances are retained anyway.
    """
    if fit.fit is DisplayFit.BELOW_FLOOR:
        return min(1.0, fit.rendered_long_edge_inches / box.floor_inches) if box.floor_inches > 0 else 0.0
    coverage = min(width / box.width, height / box.height)
    if fit.fit is DisplayFit.MATTED_SMALL:
        return min(1.0, coverage)
    return min(1.0, coverage / _NATIVE_SATURATION)


def _rationale(found: FoundImage, *, confidence: float, fit: FitAssessment, box: ArtworkBox) -> str:
    """Why this instance was chosen, in the words a curator asking gets back.

    Written for the review card rather than for a log: it names what the museum
    calls the work, how the identity was established, and the size it would
    appear at — the last because a curator judging a below-floor instance needs
    the number, not the verdict.
    """
    holder = f"{found.provider} holds this as {found.title!r}"
    holder += f" by {found.artist}" if found.artist else ", with no artist recorded"
    if confidence >= CONFIDENT:
        identity = "matching the requested title and artist"
    elif confidence >= TITLE_ONLY:
        identity = "matching the requested title; the request named no artist"
    else:
        identity = "matching the requested title; the record names no artist to confirm it"
    size = (
        f"At {found.estimated_width}x{found.estimated_height} it would render "
        f"{fit.rendered_long_edge_inches:.1f} inches on the long edge"
    )
    if fit.fit is DisplayFit.BELOW_FLOOR:
        size += f", below the {box.floor_inches:g}-inch floor, so it is offered but not selected automatically"
    elif fit.fit is DisplayFit.MATTED_SMALL:
        size += ", smaller than the artwork box, so it is matted wider rather than downscaled"
    else:
        size += ", filling the artwork box"
    return f"{holder}, {identity}. {size}."
