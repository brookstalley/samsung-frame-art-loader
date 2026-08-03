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
#: 12 because these rows are the wide shape, not the listing's. **Measured
#: 2026-08-03, not reasoned**: a full card costs about 3,600 tokens — 1,920 of
#: picture (160 each, as the published relation gives) and 1,700 of text, which
#: is about 142 per row rather than the 120 this comment first guessed. That
#: leaves a caller room to read several works in one conversation, and a work
#: with more than a dozen distinct scans on offer is not a review problem the
#: curator can solve by reading further down.
#:
#: The measurement is asserted by the truncation test rather than left here as
#: prose, for the reason the page cap exists to teach: the first version of that
#: cap was sized from its pictures alone and the rows came to nearly as much
#: again. A cap whose arithmetic nothing checks is the same mistake with a
#: smaller N.
#:
#: **There is deliberately no paging here**, and the notice does not offer any.
#: `_fill` gives the still-choosable instances first claim on the slots, so the
#: cut falls on scans already refused until those choosable ones alone outrun the
#: cap. The two states omit different things and the notice names which: refused
#: scans in the first, and in the second the *lower-ranked* choosable scans
#: together with every refused one. Only the first of those is ordered — a refused
#: scan is usually the highest-confidence one there is, since that is why it was
#: offered and turned down — so "what fell off ranks lowest" is true of a page and
#: is not true here. What holds instead is that nothing omitted is both choosable
#: and better than what is shown, which is what makes an offset not worth having,
#: unlike the listing case where what falls off a page is arbitrary and paging is
#: the remedy. Promising an offset that does not exist is the failure the withheld
#: action was withheld to avoid.
MAX_INSTANCES_LISTED: Final[int] = 12


def _fill(held: Sequence[CandidateImage]) -> Sequence[CandidateImage]:
    """Choose which of a work's instances a capped card carries.

    Selectable instances claim the slots first and rejected ones take what is
    left, so a card can never be all refused scans while the choosable ones fall
    off the end. Within that, the store's order is preserved rather than rebuilt —
    the chosen set is read back out of `held` — because a second ordering here is
    exactly how a curator's card and the automatic choice come to disagree about
    which scan is on offer.

    **Preserved, not established.** Where the work has a selection, that instance
    leads both this card and `selection.best`, since `is_selected` heads the
    store's order and a selected instance is never rejected. Where it has none —
    every instance below the floor, or every one turned down, the two cases
    `CandidateView` documents — the card leads with whatever the store ranks
    first, which may be a refused scan. That is unchanged by this function and was
    equally true of the slice it replaced; `shown_is_on_offer` is what tells a
    caller which situation they are in, and it is why that field exists rather
    than being inferred from position.

    A rejected scan is not filler: it is the evidence of a judgement already made,
    and dropping it silently would leave a curator wondering why a re-search
    returned fewer instances than before. It simply yields to an instance that can
    still be chosen, which is the only claim on a slot that outranks it.
    """
    if len(held) <= MAX_INSTANCES_LISTED:
        return held
    surviving = [image for image in held if image.rejected_at is None]
    keep = {image.id for image in surviving[:MAX_INSTANCES_LISTED]}
    for image in held:
        if len(keep) >= MAX_INSTANCES_LISTED:
            break
        keep.add(image.id)
    return [image for image in held if image.id in keep]


@dataclass(frozen=True, slots=True)
class InstanceView:
    """One image instance as a curator judging it needs to see it.

    `fit` is None exactly when the instance's dimensions were never recorded, in
    which case `fit_note` says so. That is different from an instance known to be
    small, and the two must not read alike: one is a fact about the picture, the
    other is a fact about our record of it.

    `preview` is None whenever no picture travels with this instance — no local
    copy was ever cached, the copy was reclaimed after the work was decided, or
    the file will not decode. `preview_note` says which, and the three are kept
    apart because they send whoever asks to three different places: phase 2's
    caching, a sweep working as designed, and a corrupt file. An instance without
    a picture is still listed, still carries its source-side URL, and is still
    selectable; losing a work over a missing thumbnail would be the tail wagging
    the dog.
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
    """A work's instances in the store's ranking, capped at what one card carries.

    Not "best first": the ranking is `is_selected`, then confidence, and a
    rejected scan keeps its place in it — usually near the top, since being the
    best on offer is why it was offered and turned down. Which rows are still
    choosable is a per-row fact, and `_fill` is what stops the cap from spending
    every slot on refused ones.

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

    `surviving_held` is the same distinction one level in: how many of the work's
    instances are still choosable, against how many of *those* fit. A card that
    dropped only refused scans and one that also dropped choosable ones are
    different things to tell a curator, and nothing else in the payload separates
    them — `held` counts both kinds together.
    """

    work: CandidateWork
    instances: Sequence[InstanceView]
    held: int
    surviving_held: int

    @property
    def truncated(self) -> bool:
        """True when the work holds instances this card does not show."""
        return len(self.instances) < self.held

    @property
    def shows_every_choosable_instance(self) -> bool:
        """Whether every instance still open to the curator is on this card.

        False only when the choosable instances alone outrun the cap, which is
        the one case where a truncated card withholds something actionable.
        """
        return sum(1 for instance in self.instances if not instance.rejected) == self.surviving_held


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
        """A page of the works a run is responsible for, each with a picture.

        Not "the image on offer": a work whose scans are all below the floor or
        all turned down has no selection, and still arrives pictured — see
        `CandidateView`, which spells out why. `shown_is_on_offer` separates the
        two cases.

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
        """A work's instances in the order the review card offers them, capped.

        Not *every* instance: the card carries at most `MAX_INSTANCES_LISTED`, and
        `held` beside the rows is what says so.

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
        and the growth is driven by a curator asking for something better.

        **The cut falls on the rejected scans before any selectable one**, which
        is what makes "no paging" honest rather than merely convenient. Slicing
        the store's order instead would drop the wrong end: rejections gather at
        the *top* of a confidence ranking, because the scan a curator turns down
        is the best one on offer and turning it down does not change how good the
        picture is, while each re-search appends its finds below. Past a cardful
        of rejections a sliced card would show only scans already refused, and the
        only instances still choosable would be the ones it omitted — with no
        second way to reach their ids, since this is the sole enumerator of a
        work's instances. `api-contract.md` states the requirement.
        """
        work = self._discovery.get_candidate_work(candidate_work_id)
        held = self._discovery.list_candidate_images(work.id)
        return InstanceListing(
            work=work,
            instances=[self._instance(image, work) for image in _fill(held)],
            held=len(held),
            surviving_held=sum(1 for image in held if image.rejected_at is None),
        )

    def _view(self, work: CandidateWork) -> CandidateView:
        images = self._discovery.list_candidate_images(work.id)
        # Asked of `is_selected` rather than taken from position zero: the store
        # sorts the selected instance first, but a work with no selection would
        # then be represented by whichever instance happened to sort next —
        # including one the curator had already rejected.
        chosen = next((image for image in images if image.is_selected), None)
        # Falling back through `selection.surviving` rather than a local sort, so
        # this picture is the one `best` would choose if the floor were lifted. A
        # second ordering here is how a curator's card and the automatic choice
        # come to disagree about which scan is the best of a bad set.
        #
        # It is *not* a claim about which row leads `list_images`: that card is
        # capped and includes rejected instances, so its first row is whatever the
        # store ranks first among those kept, which in a selectionless state can
        # be a scan already turned down. The two answers coincide wherever a
        # selection exists and are different questions everywhere else.
        if chosen is None:
            chosen = next(iter(selection.surviving(images)), None)
        return CandidateView(
            work=work,
            shown=None if chosen is None else self._instance(chosen, work),
            instances_held=len(images),
            instances_surviving=sum(1 for image in images if image.rejected_at is None),
        )

    def _instance(self, image: CandidateImage, work: CandidateWork) -> InstanceView:
        fit, fit_note = self._fit(image)
        preview, preview_note = self._preview(image, work)
        return InstanceView(image=image, fit=fit, fit_note=fit_note, preview=preview, preview_note=preview_note)

    def _fit(self, image: CandidateImage) -> tuple[FitAssessment | None, str | None]:
        """How large this instance would render, or why that is not knowable."""
        if image.estimated_width is None or image.estimated_height is None:
            return None, (
                "The provider did not report this image's dimensions, so how large it would appear on "
                "the wall is unknown — which is not the same as knowing it is small."
            )
        return assess_display_fit(width=image.estimated_width, height=image.estimated_height, box=self._box), None

    def _preview(self, image: CandidateImage, work: CandidateWork) -> tuple[InlinePreview | None, str | None]:
        """The picture this instance travels with, or why it travels without one."""
        if image.preview_path is None:
            # A decided work's previews are reclaimed on a timer, so the common
            # reason a picture is absent here is not that one was never cached —
            # it is that this plane deleted it, on purpose, after the curator was
            # finished with the work. Saying otherwise sends whoever asks to
            # phase 2's caching, which is the wrong place and the one they would
            # look first.
            if work.verdict.is_terminal:
                return None, (
                    f"This work was {work.verdict}, so its cached copy was reclaimed — previews are kept only "
                    "while a work is under review. Its source URL is reported beside it."
                )
            return None, (
                "No local copy of this image was cached, so it cannot be shown here. Its source URL is reported beside it."
            )
        cached = self._art_root / image.preview_path
        # **Absent and unreadable are different answers, and a row can name a
        # file that is simply gone.** The reclaiming sweep clears the column it
        # deletes, so the ordinary swept case never reaches here — but the sweep
        # and the write that records a `preview_path` are not a single critical
        # section, so a row can be written naming a file a pass removed a moment
        # earlier. Reporting that as unreadable would be the corruption message
        # for a file this plane deleted on purpose, which is the exact wrong
        # diagnosis: it sends whoever asks looking for a bad download.
        if not cached.exists():
            return None, (
                "No local copy of this image is on disk, so it cannot be shown here — it was either never "
                "cached or has since been reclaimed. Its source URL is reported beside it."
            )
        rendered = inline_preview(cached)
        if rendered is None:
            return None, (
                "The cached copy of this image could not be read, so it cannot be shown here. Its source "
                "URL is reported beside it."
            )
        return rendered, None
