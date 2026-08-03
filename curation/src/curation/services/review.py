"""What a curator sees when judging a proposed work — composed once, for both surfaces.

The counterpart to `survey.py`, on the other side of acceptance. That one composes
works already in the catalogue; this one composes works that are still proposals,
together with the image instances found for them. Both exist for the same reason:
a review surface does not want a row, it wants everything needed to judge one, and
composing it in the service layer is what stops an agent and a click disagreeing
about the same painting.

**A thumbnail cannot convey resolution, and that is why this module exists at
all.** A 900 px scan and a 6000 px scan look identical in a review grid, so a gate
that showed only pictures would not protect against hanging a postage stamp. Every
instance therefore travels with the size it would render at on *this* deployment's
wall, in inches, beside the picture — the number a curator can actually judge.

**Nothing is decided here that is decided elsewhere.** The fit verdict is
`display_fit`'s, the ordering of a work's instances is the store's — the same
order `selection.best` walks, so the instance leading a listing is the instance on
offer — and whether a preview can be shown is `previews`'. This gathers them, and
its only judgement of its own is `survey.py`'s: a missing answer is reported as a
stated reason rather than as an absent field, because a card showing no size
because nothing recorded the dimensions must not look like a card whose work is
small.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from curation.persistence.discovery_records import CandidateImage, CandidateWork, DiscoveryRun
from curation.services import selection
from curation.services.discovery import DiscoveryService
from curation.services.display_fit import ArtworkBox, FitAssessment, assess_display_fit
from curation.services.errors import ServiceError
from curation.services.previews import InlinePreview, inline_preview

#: The most one review listing will return, and **the bound is the pictures, not
#: the rows.** Every entry carries an image content block, which costs a client
#: about `width * height / 750` tokens — roughly 160 at the 400 px cap — so forty
#: entries is about 6,400 tokens of image before a word of text.
#:
#: 40 because `api-contract.md` § Token budget names that batch size as the design
#: target and sizes the 400 px cap from it. This is where it is imposed, and the
#: budget test is what stops the two drifting apart.
#:
#: Deliberately lower than the catalogue's 100. That ceiling bounds rows of short
#: text; this one bounds pictures, which cost two orders of magnitude more each.
#: One number serving both would be moved by whichever surface complained first.
MAX_REVIEW_LIMIT: Final[int] = 40

#: How many works a review listing returns when the caller does not say.
#:
#: **Lower than the ceiling, and the gap is the point.** The client has two
#: thresholds, not one: it refuses a result above 25,000 tokens and warns above
#: 10,000. Measured 2026-08-03, a full 40-work page costs about 10,200 tokens —
#: 6,400 of picture and 3,800 of text — which is far inside the limit that would
#: actually *lose* the images and barely past the one that merely complains. A
#: caller who asks for 40 has asked for it and gets it; a caller who asks for
#: nothing should not need to know a warning threshold exists, so the default
#: sits under it at about 7,700.
#:
#: The 2% overshoot at the ceiling could be closed by dropping a field from the
#: row, and deliberately is not: the candidates are `resolution_status` and
#: `instances_held`, and both carry a distinction a curator acts on — "nothing
#: was found" against "we could not look". Trading information a person needs for
#: a threshold a client merely warns at is the wrong way round.
#:
#: Both figures are measured rather than reasoned, and the budget tests assert
#: each against its own line, so a later change that pushes either across fails
#: rather than quietly costing a curator their images.
DEFAULT_REVIEW_LIMIT: Final[int] = 30

#: The most instances one work's image listing will carry, each with a picture.
#:
#: **Nothing else bounds this list.** A work's instances accumulate: phase 2
#: records what a museum offered, and every re-search adds whatever it finds that
#: the work does not already hold. Rejecting a scan does not remove it either —
#: it stays as the evidence of a judgement — so a work re-searched repeatedly
#: grows a longer card each time, and the growth is driven by a curator asking
#: for something better rather than by anything that stops.
#:
#: 12 because these rows are the wide shape, not the listing's: at roughly 160
#: tokens of picture and 120 of text each, a full card is about 3,400 tokens,
#: which leaves a caller room to read several works in one conversation. A work
#: with more than a dozen distinct scans on offer is not a review problem the
#: curator can solve by reading further down.
#:
#: **There is deliberately no paging here**, and the notice does not offer any.
#: The instances are ordered best-first by the one ranking this product has, so a
#: truncated card omits the *worst* candidates — which is the opposite of the
#: listing case, where what falls off a page is arbitrary and paging is the
#: remedy. Promising an offset that does not exist is the failure the withheld
#: action was withheld to avoid.
MAX_INSTANCES_LISTED: Final[int] = 12


@dataclass(frozen=True, slots=True)
class InstanceView:
    """One image instance as a curator judging it needs to see it.

    `fit` is None exactly when the instance's dimensions were never recorded, in
    which case `fit_note` says so. That is different from an instance known to be
    small, and the two must not read alike: one is a fact about the picture, the
    other is a fact about our record of it.

    `preview` is None whenever no picture travels with this instance — no local
    copy was ever cached, or the file will not decode. `preview_note` says which.
    An instance without a picture is still listed, still carries its source-side
    URL, and is still selectable; losing a work over a missing thumbnail would be
    the tail wagging the dog.
    """

    image: CandidateImage
    fit: FitAssessment | None
    fit_note: str | None
    preview: InlinePreview | None
    preview_note: str | None

    @property
    def rejected(self) -> bool:
        """Whether the curator has turned this scan down.

        A rejected instance stays on the card, labelled. It is excluded from
        re-selection for this work and from nothing else — which is what keeps
        "this scan is not good enough" from becoming "this painting is not
        wanted".
        """
        return self.image.rejected_at is not None


@dataclass(frozen=True, slots=True)
class CandidateView:
    """One proposed work, with the one instance whose picture travels beside it.

    **`shown` is not the same question as "what would a verdict accept this
    on".** The selected instance answers that, and a work can legitimately have
    none — every instance below the floor, or every instance turned down. Such a
    work still has to arrive with a picture: `api-contract.md` requires a
    below-floor instance to be "shown, labelled, and selectable — never hidden",
    and a listing row that carried no image because nothing was auto-selected
    would hide it one level above where that rule is written. The curator would
    see a title with no picture and no way to know a picture exists.

    So `shown` falls back to the best surviving instance, and
    `shown_is_on_offer` says which case this is. It is None only when there is
    genuinely nothing to show — no instances at all, or every one of them
    rejected. `instances_held` and `instances_surviving` tell those two apart
    without a second read.
    """

    work: CandidateWork
    shown: InstanceView | None
    instances_held: int
    instances_surviving: int

    @property
    def shown_is_on_offer(self) -> bool:
        """Whether the pictured instance is also the one a verdict would accept on."""
        return self.shown is not None and self.shown.image.is_selected


@dataclass(frozen=True, slots=True)
class CandidatePage:
    """One page of a run's proposed works, with enough context to describe itself."""

    run: DiscoveryRun
    entries: Sequence[CandidateView]
    total: int
    limit: int
    offset: int

    @property
    def truncated(self) -> bool:
        """True when the run holds works this page does not carry."""
        return self.offset + len(self.entries) < self.total


@dataclass(frozen=True, slots=True)
class InstanceListing:
    """A work's instances, best first, capped at what one card can carry.

    Carries the work as well as the instances, because a caller that had to ask
    twice — once for the pictures and once for the title they belong to — is the
    composite read this layer exists to prevent.

    It does **not** carry the run. That was here, cost a `get_run` on every call,
    and reached the payload as a `run_id` nothing needed: a caller arrives at this
    action holding a work id they got from a run-scoped listing, so they already
    know the run. Removed rather than pinned by a test — a field whose only
    defence would be a test written to defend it is a field to delete.

    `held` is what the work actually has, against `len(instances)` for what this
    card shows. The two are reported separately so a truncated card cannot be read
    as a complete one — the failure a count omitted alongside a list always
    produces.
    """

    work: CandidateWork
    instances: Sequence[InstanceView]
    held: int

    @property
    def truncated(self) -> bool:
        """True when the work holds instances this card does not show."""
        return len(self.instances) < self.held


class ReviewService:
    """Read proposed works the way a surface that shows them to a human needs them."""

    def __init__(self, discovery: DiscoveryService, *, box: ArtworkBox, art_root: Path) -> None:
        self._discovery = discovery
        #: The space a work is rendered into on this deployment. Required rather
        #: than optional: a review surface whose whole justification is showing
        #: how large a work would appear cannot be assembled without it, and a
        #: caller with none should fail at wiring rather than serve cards with
        #: every size reported as unknown.
        self._box = box
        #: Where preview files live. Every catalogue path is relative to it.
        self._art_root = art_root

    def list_works(self, run_id: str, *, limit: int | None = None, offset: int = 0) -> CandidatePage:
        """A page of the works a run is responsible for, each with the image on offer.

        Scoped to a run because that is the id a caller can actually obtain:
        `art_discovery(action='list_runs')` returns run ids, and nothing on any
        built surface enumerates candidate works across runs. An action whose
        argument has no reachable source is an action nobody can call.

        Paging is real here, which is what lets the truncation notice name a
        remedy. A run's own status view caps its work list at a hundred and can
        only say the rest are omitted — this is the paged listing it points at.
        """
        resolved_limit = DEFAULT_REVIEW_LIMIT if limit is None else limit
        if not 1 <= resolved_limit <= MAX_REVIEW_LIMIT:
            raise ServiceError(f"limit must be between 1 and {MAX_REVIEW_LIMIT}, got {resolved_limit}.")
        if offset < 0:
            raise ServiceError(f"offset cannot be negative, got {offset}.")

        # Read whole and sliced here rather than paged in the store, because the
        # relation differs by run kind — a discovery run's works are the ones it
        # proposed, a re-search's are the ones it covers — and that branch already
        # lives behind `run_results`. Bounded by phase 1's output, which is
        # already held in memory to compute the approval gate.
        #
        # **The page order is resolved works, then unresolved, then pending**,
        # each group in the store's title order. That falls out of `run_results`
        # rather than being imposed here, and it is the right way round for this
        # surface: the works a curator can actually judge lead, and the ones
        # nothing was found for — which they can do nothing about except
        # re-search — sort behind them. It is a total order, so a page boundary
        # lands in the same place on every call.
        results = self._discovery.run_results(run_id)
        works = results.works
        page = works[offset : offset + resolved_limit]
        return CandidatePage(
            run=results.run,
            entries=[self._view(work) for work in page],
            total=len(works),
            limit=resolved_limit,
            offset=offset,
        )

    def get_work(self, candidate_work_id: str) -> CandidateView:
        """One proposed work with the instance standing for it.

        The alternates are `list_images`' answer, not this one's. Returning every
        instance here would make the two actions differ only in what a caller
        ignores, and would put a work's whole picture set inside a call a caller
        makes to read one title.

        Returns the view itself rather than a wrapper carrying the run beside it.
        The wrapper existed to supply a top-level `run_id`, which was the same
        value the work already carries as `discovery_run_id` — one fact under two
        names in one payload, and a `get_run` per call to produce the duplicate.
        """
        return self._view(self._discovery.get_candidate_work(candidate_work_id))

    def list_images(self, candidate_work_id: str) -> InstanceListing:
        """Every instance found for a work, in the order the review card offers them.

        The order is the store's — selected first, then by confidence, then by id
        — which is the same order `selection.best` walks. Re-sorting here would be
        a second ordering of the same set, and the whole point of there being one
        is that a curator and the automatic choice cannot come to disagree about
        which instance leads.

        A rejected instance is included and labelled rather than dropped. It is
        the evidence of a judgement already made, and hiding it would leave a
        curator wondering why a re-search returned fewer instances than before.

        Capped at `MAX_INSTANCES_LISTED`, because nothing else bounds this list:
        a work accumulates instances across every re-search, rejected ones stay,
        and the growth is driven by a curator asking for something better. The
        cut takes the *worst* candidates, since the order is best-first — which is
        why there is no paging to offer and none is promised.
        """
        work = self._discovery.get_candidate_work(candidate_work_id)
        held = self._discovery.list_candidate_images(work.id)
        return InstanceListing(
            work=work,
            instances=[self._instance(image) for image in held[:MAX_INSTANCES_LISTED]],
            held=len(held),
        )

    def _view(self, work: CandidateWork) -> CandidateView:
        images = self._discovery.list_candidate_images(work.id)
        # Asked of `is_selected` rather than taken from position zero: the store
        # sorts the selected instance first, but a work with no selection would
        # then be represented by whichever instance happened to sort next —
        # including one the curator had already rejected.
        chosen = next((image for image in images if image.is_selected), None)
        # Falling back through `selection.surviving` rather than a local sort, so
        # the instance a listing pictures is the one the review card leads with
        # and the one `best` would choose if the floor were lifted. A second
        # ordering here is how a curator's card and the automatic choice come to
        # disagree about which scan is the best of a bad set.
        if chosen is None:
            chosen = next(iter(selection.surviving(images)), None)
        return CandidateView(
            work=work,
            shown=None if chosen is None else self._instance(chosen),
            instances_held=len(images),
            instances_surviving=sum(1 for image in images if image.rejected_at is None),
        )

    def _instance(self, image: CandidateImage) -> InstanceView:
        fit, fit_note = self._fit(image)
        preview, preview_note = self._preview(image)
        return InstanceView(image=image, fit=fit, fit_note=fit_note, preview=preview, preview_note=preview_note)

    def _fit(self, image: CandidateImage) -> tuple[FitAssessment | None, str | None]:
        """How large this instance would render, or why that is not knowable."""
        if image.estimated_width is None or image.estimated_height is None:
            return None, (
                "The provider did not report this image's dimensions, so how large it would appear on "
                "the wall is unknown — which is not the same as knowing it is small."
            )
        return assess_display_fit(width=image.estimated_width, height=image.estimated_height, box=self._box), None

    def _preview(self, image: CandidateImage) -> tuple[InlinePreview | None, str | None]:
        """The picture this instance travels with, or why it travels without one."""
        if image.preview_path is None:
            return None, (
                "No local copy of this image was cached, so it cannot be shown here. Its source URL is " "reported beside it."
            )
        rendered = inline_preview(self._art_root / image.preview_path)
        if rendered is None:
            return None, (
                "The cached copy of this image could not be read, so it cannot be shown here. Its source "
                "URL is reported beside it."
            )
        return rendered, None
