"""Discovery operations — everything a work goes through before it is accepted.

The counterpart to `catalogue.py`, and the split is the pipeline's own: the
catalogue holds works that are already in the collection, discovery holds runs,
proposed works, the image instances found for them, what each run spent, and the
curator's verdicts. Both are reached the same way — a surface unpacks arguments,
calls one method here, and formats the result — so the rules live in exactly one
place regardless of which concern they belong to.

**This is where the pipeline's rules are enforced, at write time.** Two state
machines are closed here rather than described: a run cannot leave a terminal
state, a resolve run cannot reach the phase-1 states it skipped, and the verdict
`awaiting_better_image` has exactly one entry — the path that also suppresses the
instance the curator turned down. A rule applied on the way out is a rule the
data can already violate.

**Discovery depends on the catalogue and never the other way round.** Acceptance
is a promotion: a candidate work becomes an Artwork and its image instances
become that work's Sources. The dependency runs in the direction the pipeline
does, so nothing in the catalogue has to know that candidates exist.

Methods are synchronous, for the same reason the catalogue's are: the store is a
local file answering point lookups in well under a millisecond, and a synchronous
core keeps this logic testable without an event loop.
"""

import logging
import uuid
from collections.abc import Callable, Iterable, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal

from curation.persistence.discovery import DiscoveryStore
from curation.persistence.discovery_records import (
    CandidateImage,
    CandidateWork,
    DiscoveryRun,
    InitiatedBy,
    ResolutionStatus,
    ResolveRunWork,
    RunKind,
    RunStatus,
    SpendCategory,
    SpendRecord,
    Verdict,
)
from curation.persistence.records import AcquisitionMethod, Artist, RightsStatus, SourceClass
from curation.services import attribution, selection
from curation.services.catalogue import CatalogueService
from curation.services.display_fit import ArtworkBox
from curation.services.errors import ServiceError
from curation.services.fields import relative_path, require_member, require_text
from curation.services.store import store_write

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class VerdictOutcome:
    """A recorded verdict, and what recording it did beyond the verdict itself.

    Acceptance mints an artwork and may mint an artist, and the artist is the one
    part a curator can neither see nor undo from the work alone: a new `Artist`
    row that duplicates a painter already held looks, in the catalogue, exactly
    like a painter newly encountered. `minted_artist` and `duplicate_candidates`
    are how that reaches them at the moment it happens.

    Both are empty for a rejection, and for an acceptance that matched an artist
    already held or named none — the three cases where nothing was decided that a
    reader could not work out from the work.
    """

    work: CandidateWork
    minted_artist: Artist | None = None
    duplicate_candidates: Sequence[Artist] = ()


@dataclass(frozen=True, slots=True)
class RunResults:
    """A run's proposed works, split by whether an image was found for them.

    `unresolved` is a bucket rather than an omission. A work phase 2 could not
    resolve is evidence that phase 1 may have invented it, so a run that quietly
    returned a shorter list would be discarding its own most useful signal.
    """

    run: DiscoveryRun
    #: Named for the `resolution_status` values they hold, rather than for
    #: near-synonyms: a bucket called something the model does not say is a
    #: second vocabulary for the same three facts.
    resolved: Sequence[CandidateWork]
    unresolved: Sequence[CandidateWork]
    pending: Sequence[CandidateWork]

    @property
    def works(self) -> Sequence[CandidateWork]:
        """Every work this run is responsible for, whatever came of it.

        The buckets partition the works, so callers that want the whole set get
        it from here rather than re-adding three lengths in their own arithmetic
        — which is how two surfaces come to disagree about how big a run was.
        """
        return [*self.resolved, *self.unresolved, *self.pending]


@dataclass(frozen=True, slots=True)
class ResolutionOutcome:
    """What a resolution attempt concluded about one work, and whether it stuck.

    `applied` is false when the curator reached a terminal verdict while the
    attempt was running. The result is then reported rather than written: only
    the curator's verdict is authoritative, and a background job overwriting an
    acceptance would leave a work holding an `artwork_id` and a non-accepted
    verdict — a combination nothing else in this model can produce or repair.
    """

    work: CandidateWork
    resolution_status: ResolutionStatus
    selected: CandidateImage | None
    applied: bool


@dataclass(frozen=True, slots=True)
class RunCost:
    """What a run spent on its own, and what asking for it cost altogether.

    The two differ because a re-search is its own run: `direct` is what this run
    was billed, and `total` adds every resolve run descended from it. "What did
    asking for Dalí cost" is the second number.
    """

    direct: Decimal
    total: Decimal


class DiscoveryService:
    """Read and write the pre-acceptance pipeline."""

    def __init__(self, store: DiscoveryStore, catalogue: CatalogueService, artwork_box: ArtworkBox | None = None) -> None:
        self._store = store
        self._catalogue = catalogue
        #: The space a work is rendered into, which is what turns an instance's
        #: pixels into a size on the wall. Held because automatic selection has
        #: to withhold an instance that would render below the floor, and the
        #: floor is physical — so the rule cannot be evaluated from a row alone.
        #: Optional so a caller with no deployment geometry gets the ranking
        #: without a floor rather than a constructor it cannot satisfy.
        self._artwork_box = artwork_box

    def transaction(self) -> AbstractContextManager[None]:
        """Apply a rule that spans several of this service's operations, atomically.

        Exposed for the one caller whose correctness needs it: reclaiming
        previews decides what to delete by reading rows and then deletes files,
        and a writer landing between those two halves would attach a work still
        under review to a file already gone. Holding the store's lock across both
        is what makes "a file survives while any work still under review
        references it" true against a concurrent writer rather than only against
        the moment the reader looked.

        Nesting joins the outer group, so the operations composed inside still
        commit exactly once. Every other caller should use the service method
        that already wraps what it needs — this is not a general escape hatch,
        and holding it across slow work would serialise the plane behind it.
        """
        return self._store.transaction()

    # -- reads: runs ----------------------------------------------------------

    def get_run(self, run_id: str) -> DiscoveryRun:
        """Return one run, or refuse if there is no such id."""
        run = self._store.get_run(run_id)
        if run is None:
            raise ServiceError(f"No discovery run with id {run_id!r} exists.")
        return run

    def list_runs(self, *, status: RunStatus | None = None, kind: RunKind | None = None) -> Sequence[DiscoveryRun]:
        """Every run, newest first, optionally narrowed to one status or kind."""
        resolved_status = None if status is None else require_member(status, enum=RunStatus, field="status")
        resolved_kind = None if kind is None else require_member(kind, enum=RunKind, field="kind")
        return self._store.list_runs(status=resolved_status, kind=resolved_kind)

    def run_results(self, run_id: str) -> RunResults:
        """The run's works, with the ones nothing could be found for reported separately."""
        run = self.get_run(run_id)
        works = self._works_of(run)
        return RunResults(
            run=run,
            resolved=[work for work in works if work.resolution_status is ResolutionStatus.RESOLVED],
            unresolved=[work for work in works if work.resolution_status is ResolutionStatus.UNRESOLVED],
            pending=[work for work in works if work.resolution_status is ResolutionStatus.PENDING],
        )

    # -- writes: a discovery run's life ---------------------------------------

    def start_discovery_run(self, *, intent_text: str, initiated_by: InitiatedBy) -> DiscoveryRun:
        """Begin phase 1: the curator's intent becomes a run enumerating works.

        No `strategy` here, deliberately. It is how the intent was *interpreted*,
        which nothing knows until the model has read it — so it is written when
        the work list arrives, and a run in flight honestly has none.
        """
        run = DiscoveryRun(
            id=str(uuid.uuid4()),
            kind=RunKind.DISCOVERY,
            initiated_by=require_member(initiated_by, enum=InitiatedBy, field="initiated_by"),
            status=RunStatus.RESOLVING_WORKS,
            approval_required=False,
            started_at=datetime.now(UTC),
            intent_text=require_text(intent_text, field="intent_text"),
        )
        store_write(self._store.add_run, run)
        return run

    def finish_work_list(
        self,
        run_id: str,
        *,
        approval_threshold: int,
        estimated_cost_usd: Decimal | None = None,
        strategy: str | None = None,
    ) -> DiscoveryRun:
        """Close phase 1 and either stop for approval or go straight to phase 2.

        The gate is on the **work count**, not on the estimate. A dollar
        threshold gates on the axis that does not discriminate — real runs cost
        well under a dollar — while the judgement the gate exists to invite is
        scope: "you asked for Dalí and I found 200 works — really?". More works
        than the threshold stops for approval; exactly the threshold does not,
        because a limit a curator set is a number they already accepted.

        Whether the gate fired is stored rather than left to be re-derived: the
        threshold is configuration, and a run that stopped for approval last
        month must still read that way under today's setting.

        `strategy` lands here because this is the moment it becomes known — it is
        the engine's account of how the intent was read, and it explains the very
        list this transition closes. This is its only writer: the transition runs
        once per run, out of `resolving_works`, so there is no earlier value to
        preserve and no second chance to overwrite one.
        """
        if approval_threshold < 0:
            raise ServiceError(f"An approval threshold cannot be negative, got {approval_threshold}.")
        with self._store.transaction():
            run = self._require_status(run_id, RunStatus.RESOLVING_WORKS, doing="finish its work list")
            required = len(self._store.list_candidate_works(run_id)) > approval_threshold
            advanced = replace(
                run,
                status=RunStatus.AWAITING_APPROVAL if required else RunStatus.RESOLVING_IMAGES,
                approval_required=required,
                estimated_cost_usd=estimated_cost_usd,
                strategy=strategy,
            )
            store_write(self._store.update_run, advanced)
        return advanced

    def approve_run(self, run_id: str) -> DiscoveryRun:
        """Accept the work list and its price; phase 2 may proceed."""
        with self._store.transaction():
            run = self._require_status(run_id, RunStatus.AWAITING_APPROVAL, doing="be approved")
            approved = replace(run, status=RunStatus.RESOLVING_IMAGES)
            store_write(self._store.update_run, approved)
        return approved

    def decline_run(self, run_id: str) -> DiscoveryRun:
        """Refuse the work list. The run ends without phase 2 ever spending."""
        with self._store.transaction():
            run = self._require_status(run_id, RunStatus.AWAITING_APPROVAL, doing="be declined")
            declined = self._ended(run, RunStatus.DECLINED)
            store_write(self._store.update_run, declined)
        return declined

    def complete_run(self, run_id: str, *, actual_cost_usd: Decimal | None = None) -> DiscoveryRun:
        """Finish phase 2. A run that resolved some works and not others still succeeded.

        The unresolved count is written here rather than derived on every read,
        because it is the run's own report of what it could not do and must not
        change afterwards.
        """
        with self._store.transaction():
            run = self._require_status(run_id, RunStatus.RESOLVING_IMAGES, doing="complete")
            unresolved = [work for work in self._works_of(run) if work.resolution_status is ResolutionStatus.UNRESOLVED]
            completed = self._ended(
                run,
                RunStatus.COMPLETED,
                actual_cost_usd=actual_cost_usd,
                unresolved_work_count=len(unresolved),
            )
            store_write(self._store.update_run, completed)
        return completed

    def fail_run(self, run_id: str, *, actual_cost_usd: Decimal | None = None) -> DiscoveryRun:
        """End a run because something broke. Distinct from every other ending.

        Only a run whose process is working on it can break, which is why this is
        refused from `awaiting_approval`: nothing is executing there, and a run
        that "failed" while waiting for a curator would be describing something
        that did not happen.
        """
        return self._end_active(run_id, RunStatus.FAILED, doing="fail", actual_cost_usd=actual_cost_usd, from_working=True)

    def halt_run_for_budget(self, run_id: str, *, actual_cost_usd: Decimal | None = None) -> DiscoveryRun:
        """End a run because the provider refused to spend more.

        **The caller reaches this from the provider refusing to spend, and from
        nothing else.**
        The ceiling is a provider-side credit limit; there is deliberately no
        local sum standing between the product and an unbounded bill, because a
        local tally that fails open is indistinguishable from one that works —
        no error, no alert, just a bill. Recording spend therefore never moves a
        run into this state, and nothing here reads `SpendRecord` to decide it.

        Refused from `awaiting_approval` for the same reason failure is: a run
        parked for the curator is not spending, so it cannot be the one the
        provider refused. Phase 1 *can* be — it makes model calls and can search
        the web — so this is reachable from both working states, not only phase 2.
        """
        return self._end_active(
            run_id, RunStatus.HALTED_BY_BUDGET, doing="halt", actual_cost_usd=actual_cost_usd, from_working=True
        )

    def cancel_run(self, run_id: str, *, actual_cost_usd: Decimal | None = None) -> DiscoveryRun:
        """Stop a run on request, from wherever it is. Money already spent stays recorded.

        Available from every active state, including `awaiting_approval` — a
        curator looking at a work list may simply want the run gone, and that is
        a different thing from declining it.
        """
        return self._end_active(run_id, RunStatus.CANCELLED, doing="cancel", actual_cost_usd=actual_cost_usd)

    # -- writes: the re-search ------------------------------------------------

    def start_resolve_run(
        self,
        *,
        candidate_work_ids: Sequence[str],
        initiated_by: InitiatedBy,
        price: Callable[[int], Decimal] | None = None,
    ) -> DiscoveryRun:
        """Begin a re-search over works an earlier run proposed.

        A resolve run enters at phase 2 and can never reach `resolving_works`,
        `awaiting_approval` or `declined`: phase 1 already happened on the
        parent, so there is no work list to approve or decline.

        **It refuses work ids already covered by a live resolve run, and names
        them.** Double-submitting the same ids would spend twice for one result
        on the only operation that spends at all, and a curator who did it by
        accident should find out rather than be quietly corrected.

        `price` is asked for the estimate rather than handed one, because the
        count it prices is the *deduplicated* one this method works out, and a
        caller pricing the ids it sent would over-charge every request that
        named a work twice. Pricing itself stays out of here: what a search
        costs is configuration, and this layer holds no configuration.
        """
        if not candidate_work_ids:
            raise ServiceError("A resolve run needs at least one candidate work to re-search.")
        with self._store.transaction():
            works = [self.get_candidate_work(work_id) for work_id in dict.fromkeys(candidate_work_ids)]
            self._refuse_covered(works)
            parent_ids = {work.discovery_run_id for work in works}
            if len(parent_ids) > 1:
                # A resolve run covers a subset of one run's works, and its parent
                # is what keeps its spend attributable to the intent that caused
                # it. Works from several runs have no single such intent.
                raise ServiceError(
                    "A resolve run covers works from one discovery run, and these come from "
                    f"{len(parent_ids)}. Start one per originating run."
                )
            run = DiscoveryRun(
                id=str(uuid.uuid4()),
                kind=RunKind.RESOLVE,
                initiated_by=require_member(initiated_by, enum=InitiatedBy, field="initiated_by"),
                status=RunStatus.RESOLVING_IMAGES,
                approval_required=False,
                started_at=datetime.now(UTC),
                parent_run_id=parent_ids.pop(),
                estimated_cost_usd=None if price is None else price(len(works)),
            )
            store_write(self._store.add_run, run)
            for work in works:
                store_write(self._store.add_coverage, ResolveRunWork(resolve_run_id=run.id, candidate_work_id=work.id))
        return run

    def covered_works(self, resolve_run_id: str) -> Sequence[CandidateWork]:
        """Which works a resolve run is re-searching — its scope, not its provenance."""
        run = self.get_run(resolve_run_id)
        if run.kind is not RunKind.RESOLVE:
            raise ServiceError(f"Run {resolve_run_id!r} is a {run.kind} run, and only a resolve run covers works.")
        return self._works_of(run)

    # -- repair ---------------------------------------------------------------

    def reconcile(self) -> None:
        """Move runs whose process died to `interrupted`. Run once, as the plane starts.

        Without this the state machine has no edge for process death: every one
        of its other terminal states is written by the run's own process, which a
        crashed process by definition cannot do. Combined with the double-spend
        guard, a crash would leave the covered works permanently
        un-re-searchable, silently, on the only operation that spends money.

        A run in a process-held state only advances while the curation process
        that owns it is alive, and there is exactly one such process. So if
        curation is starting, no previously-recorded run is running: the
        inference is total rather than heuristic, which is why this is startup
        reconciliation and not a timeout to tune or a liveness field to keep
        fresh.

        One line per run, at WARNING, carrying the id and the state it was left
        in. That line is the *only* signal a run died — silence here is not the
        absence of a problem, it is the absence of this repair.
        """
        with self._store.transaction():
            for status in (held for held in RunStatus if held.is_process_held):
                for run in self._store.list_runs(status=status):
                    # The id goes in `extra`, not only in the message. This is
                    # the one line that says a run died, and the documented way
                    # to reconstruct a run is to select on the `run_id` field —
                    # an id readable only inside the text is invisible to that
                    # filter, so an operator would get every line of the run
                    # except the one explaining its silence, and the artifact
                    # tells them to read that silence as a second defect.
                    log.warning(
                        "Discovery run %s was left in %s by a process that did not survive; marking it interrupted. "
                        "Re-run it; do not investigate it as a failure.",
                        run.id,
                        status,
                        extra={"event": "run.interrupted", "run_id": run.id, "status": str(status)},
                    )
                    # Coverage is released by the run becoming terminal, not by
                    # deleting its rows: the join records what the run's scope
                    # was, and that stays true after the run has ended.
                    store_write(self._store.update_run, self._ended(run, RunStatus.INTERRUPTED))

    # -- reads: proposed works ------------------------------------------------

    def get_candidate_work(self, candidate_work_id: str) -> CandidateWork:
        """Return one proposed work, or refuse if there is no such id."""
        work = self._store.get_candidate_work(candidate_work_id)
        if work is None:
            raise ServiceError(f"No candidate work with id {candidate_work_id!r} exists.")
        return work

    def list_candidate_works(self, run_id: str) -> Sequence[CandidateWork]:
        """The works a run proposed."""
        self.get_run(run_id)
        return self._store.list_candidate_works(run_id)

    def is_work_suppressed(self, work_dedup_key: str) -> bool:
        """Whether this work has already been proposed and declined.

        Work-scoped suppression, and only work-scoped: rejecting an *image* uses
        a different key entirely, so asking for a better scan of a painting
        leaves the painting eligible.
        """
        return any(
            work.verdict is Verdict.REJECTED
            for work in self._store.list_candidate_works_by_dedup_key(require_text(work_dedup_key, field="work_dedup_key"))
        )

    # -- writes: proposed works -----------------------------------------------

    def propose_work(
        self,
        *,
        run_id: str,
        proposed_title: str,
        rationale: str,
        work_dedup_key: str,
        proposed_artist: str | None = None,
        reconsider: bool = False,
    ) -> CandidateWork:
        """Record a work phase 1 proposed, unless the curator has already declined it.

        `rationale` is required because a review card that cannot say *why* this
        work matched the intent asks the curator to judge a bare title.

        Suppression is refused rather than silently skipped, and `reconsider`
        exists because the rule is "unless the curator explicitly reconsiders it"
        — a decision they are allowed to revisit, but never by accident.
        """
        key = require_text(work_dedup_key, field="work_dedup_key")
        with self._store.transaction():
            # Kind before status: a resolve run is never in `resolving_works`, so
            # the status refusal would reach it first and answer a question it did
            # not ask — and this guard would be a branch nothing could enter.
            if self.get_run(run_id).kind is not RunKind.DISCOVERY:
                raise ServiceError(
                    f"Run {run_id!r} is a resolve run, which re-searches works an earlier run proposed "
                    "rather than proposing new ones."
                )
            self._require_status(run_id, RunStatus.RESOLVING_WORKS, doing="propose works")
            if not reconsider and self.is_work_suppressed(key):
                raise ServiceError(
                    f"{proposed_title!r} has already been proposed and rejected. "
                    "Pass reconsider=True to propose it again deliberately."
                )
            work = CandidateWork(
                id=str(uuid.uuid4()),
                discovery_run_id=run_id,
                proposed_title=require_text(proposed_title, field="proposed_title"),
                rationale=require_text(rationale, field="rationale"),
                work_dedup_key=key,
                proposed_artist=proposed_artist,
            )
            store_write(self._store.add_candidate_work, work)
        return work

    def set_verdict(self, candidate_work_id: str, verdict: Verdict, *, reason: str | None = None) -> VerdictOutcome:
        """Record the curator's decision about a work: accepted or rejected.

        **`awaiting_better_image` is refused here on purpose.** That verdict is a
        judgement about an *instance*, and the path that sets it is the same path
        that suppresses the instance being turned down — so the suppression can
        never be skipped. Reaching it from here would let a re-search hand back
        the very image the curator had just rejected.

        The constraint is on the target value only, never on the source state:
        this is available from `awaiting_better_image` too, because a curator must
        never be blocked waiting for a background job to finish.
        """
        target = require_member(verdict, enum=Verdict, field="verdict")
        if target is Verdict.AWAITING_BETTER_IMAGE:
            raise ServiceError(
                "A verdict of 'awaiting_better_image' is set by rejecting an image, not by set_verdict. "
                "Use reject_image, which also suppresses the instance so a re-search cannot return it."
            )
        if target is Verdict.PENDING:
            raise ServiceError("'pending' is where a work starts, not a decision. Valid verdicts are: accepted, rejected.")

        with self._store.transaction():
            work = self.get_candidate_work(candidate_work_id)
            if work.verdict.is_terminal:
                raise ServiceError(f"Candidate work {candidate_work_id!r} was already {work.verdict}, and that is final.")
            if target is Verdict.ACCEPTED:
                return self._accept(work)
            rejected = replace(work, verdict=target, rejected_reason=reason, decided_at=datetime.now(UTC))
            store_write(self._store.update_candidate_work, rejected)
        return VerdictOutcome(work=rejected)

    # -- reads and writes: image instances ------------------------------------

    def list_candidate_images(self, candidate_work_id: str) -> Sequence[CandidateImage]:
        """Every instance found for this work, in the store's ranking.

        *Every* one, unlike the review card built from it, which is capped —
        callers that show these to a person are responsible for saying what they
        left out.

        The selected instance leads where one exists. A work whose scans are all
        below the floor or all turned down has no selection, and then the leading
        row is simply the highest-ranked, which may be a scan already refused.
        `is_selected` is what distinguishes them; position is not.

        Losing instances are kept rather than deleted: they are the alternates a
        review card offers, they make an over-eager merge inspectable, and on
        acceptance they become the work's non-primary sources.
        """
        self.get_candidate_work(candidate_work_id)
        return self._store.list_candidate_images(candidate_work_id)

    def record_image(
        self,
        *,
        candidate_work_id: str,
        url: str,
        provider: str,
        source_class: SourceClass,
        acquisition_method: AcquisitionMethod,
        confidence: float,
        preview_url: str | None = None,
        preview_path: str | None = None,
        estimated_width: int | None = None,
        estimated_height: int | None = None,
        rights_status: RightsStatus | None = None,
        quality_score: float | None = None,
        selection_rationale: str | None = None,
    ) -> CandidateImage | None:
        """Record one image instance found for a work, or decline to.

        `None` means nothing was written and nothing is wrong: the work's
        curator has already decided it, so its instances are closed. Every other
        path returns the instance the work now holds for that URL.

        The first surviving instance a work has becomes its selection, so a work
        with instances is never selectionless; a later choice moves the selection
        rather than adding a second one.

        **Unless it would render below the floor**, which is never selected
        without a curator asking for it by name. Such an instance is still
        recorded, still offered as an alternate, and still carries the size it
        would appear at — a work whose every instance is below floor simply holds
        no selection, and is reported `unresolved` rather than putting a postage
        stamp on the wall on nobody's authority.

        **A URL the work already holds returns the instance already held**, and
        writes nothing. A rejection is a fact about the scan at that address, not
        about the row that happens to carry it, so a second row for the same URL
        would come back with a null `rejected_at` and be handed straight back to
        the curator who turned it down — suppression lasting only until something
        searched again. Searching again is exactly what a re-search does, and a
        provider re-offering the same URL is the normal case rather than the
        exotic one.
        """
        with self._store.transaction():
            work = self.get_candidate_work(candidate_work_id)
            found_at = require_text(url, field="url")
            if work.verdict.is_terminal:
                # A decided work's images are no longer under review — the same
                # ground `reject_image` refuses on. On an accepted work they
                # became catalogue `Source`s at acceptance, and nothing promotes
                # a row added afterwards, so it would be reachable from no
                # surface at all. Declined rather than raised, because the caller
                # that reaches this is a re-search whose subject the curator
                # decided while it was searching — an ordinary race, not a fault,
                # and this is the write that makes losing it harmless.
                log.info(
                    "not recording an instance for %r: the curator decided it while the search was running",
                    work.proposed_title,
                    extra={"event": "image.work_decided", "verdict": str(work.verdict)},
                )
                return None
            held = self._store.list_candidate_images(work.id)
            already = next((instance for instance in held if instance.url == found_at), None)
            if already is not None:
                log.info(
                    "an instance of %r was offered again at a URL the work already holds; keeping the one on record",
                    work.proposed_title,
                    extra={"event": "image.already_held", "rejected": already.rejected_at is not None},
                )
                return already
            image = CandidateImage(
                id=str(uuid.uuid4()),
                candidate_work_id=work.id,
                url=found_at,
                provider=require_text(provider, field="provider"),
                source_class=require_member(source_class, enum=SourceClass, field="source_class"),
                acquisition_method=require_member(acquisition_method, enum=AcquisitionMethod, field="acquisition_method"),
                confidence=confidence,
                is_selected=False,
                preview_url=preview_url,
                preview_path=None if preview_path is None else relative_path(preview_path, field="preview_path"),
                estimated_width=estimated_width,
                estimated_height=estimated_height,
                rights_status=(
                    None if rights_status is None else require_member(rights_status, enum=RightsStatus, field="rights_status")
                ),
                quality_score=quality_score,
                selection_rationale=selection_rationale,
            )
            # Decided from the built row rather than from the arguments, so the
            # floor is evaluated against exactly the dimensions being stored.
            claimed = not any(other.is_selected for other in held) and not self._below_floor(image)
            image = replace(image, is_selected=claimed)
            store_write(self._store.add_candidate_image, image)
        return image

    def select_image(self, candidate_image_id: str, *, rationale: str | None = None) -> CandidateImage:
        """Make this instance the one that represents its work, and the only one.

        A rejected instance is refused: it is excluded from re-selection for this
        work, which is what "the curator turned this scan down" has to mean for
        the rejection to survive the next re-search.
        """
        with self._store.transaction():
            image = self._require_image(candidate_image_id)
            if image.rejected_at is not None:
                raise ServiceError(f"Image {candidate_image_id!r} was rejected for this work, so it cannot be selected again.")
            chosen = self._select(image, rationale=rationale)
        return chosen

    def forget_preview(self, candidate_image_id: str) -> CandidateImage:
        """Record that this instance no longer has a local copy of its picture.

        The record half of reclaiming a preview. Deleting the file belongs to
        whoever owns the directory; this is what stops the row from claiming a
        picture that is not there, which a review card would otherwise report as
        a file it could not read — a corruption message for a routine
        reclamation.

        **Refused while the work is still under review**, because a preview is
        the picture that review shows and a work not yet decided may still be
        looked at. The rule that only a decided work loses its previews is
        enforced here rather than only in the caller that walks them: this is the
        one write that can break it, and a second caller written later would
        otherwise have to remember.

        Already-forgotten is not an error. The state being converged on is "no
        file, and no row pointing at one", and a caller re-running after a crash
        must find the second half done rather than a refusal.
        """
        with self._store.transaction():
            image = self._require_image(candidate_image_id)
            work = self.get_candidate_work(image.candidate_work_id)
            if not work.verdict.is_terminal:
                raise ServiceError(
                    f"Candidate work {work.id!r} is {work.verdict}, so it is still under review and its "
                    "previews are what review shows. A preview is reclaimable once its work is accepted or rejected."
                )
            if image.preview_path is None:
                return image
            forgotten = replace(image, preview_path=None)
            store_write(self._store.update_candidate_image, forgotten)
        return forgotten

    def reject_image(self, candidate_image_id: str) -> CandidateWork:
        """Turn down an instance and ask for a better one. The work stays wanted.

        This is the only way into the `awaiting_better_image` verdict, and it is
        the same call that sets the instance's suppression — one path, so the two
        can never come apart. The work keeps its dedup key unsuppressed, because
        the curator asked to keep the painting and only turned down the scan.

        If the instance rejected was the one representing the work, the selection
        falls through to the next survivor, so a work is never left representing
        itself by an image its curator turned down. If it was an alternate, the
        standing selection is left exactly where it was. If nothing survives, the
        work holds no selection and re-enters phase 2 rather than sitting there.
        """
        with self._store.transaction():
            image = self._require_image(candidate_image_id)
            if image.rejected_at is not None:
                raise ServiceError(f"Image {candidate_image_id!r} was already rejected for this work.")
            work = self.get_candidate_work(image.candidate_work_id)
            if work.verdict.is_terminal:
                raise ServiceError(
                    f"Candidate work {work.id!r} was already {work.verdict}, so its images are no longer under review."
                )
            store_write(
                self._store.update_candidate_image,
                replace(image, is_selected=False, rejected_at=datetime.now(UTC)),
            )
            # Only a vacancy is filled. Rejecting an alternate while the instance
            # actually on offer still stands must not move the selection —
            # a curator who chose the canonical instance did not ask for that,
            # and the move would be silent.
            survivors = self._store.list_candidate_images(work.id)
            if not any(other.is_selected for other in survivors):
                replacement = selection.best(survivors, box=self._artwork_box)
                if replacement is not None:
                    self._select(replacement, rationale=None)
            awaiting = replace(work, verdict=Verdict.AWAITING_BETTER_IMAGE)
            store_write(self._store.update_candidate_work, awaiting)
        return awaiting

    def record_resolution(self, candidate_work_id: str) -> ResolutionOutcome:
        """Close a resolution attempt for one work, from the instances it now holds.

        The outcome is read from the work's instances rather than asserted by the
        caller, so "resolved" cannot disagree with whether anything is actually
        there. A work with any surviving instance is resolved and returns to
        review; a work whose instances are all rejected — or which never had any
        — is `unresolved`, which is a reportable outcome and not an absent row.

        A terminal verdict is never overwritten. The curator may have accepted or
        rejected the work while the attempt was running, and only their verdict
        is authoritative; the result is then reported and not applied.
        """
        with self._store.transaction():
            work = self.get_candidate_work(candidate_work_id)
            chosen = selection.best(self._store.list_candidate_images(work.id), box=self._artwork_box)
            status = ResolutionStatus.RESOLVED if chosen is not None else ResolutionStatus.UNRESOLVED
            if work.verdict.is_terminal:
                return ResolutionOutcome(work=work, resolution_status=status, selected=chosen, applied=False)
            if chosen is not None and not chosen.is_selected:
                self._select(chosen, rationale=None)
            settled = replace(
                work,
                resolution_status=status,
                # A work the curator asked a better image for returns to review
                # once one is on offer. It stays where it is when nothing was
                # found, which is what makes a dead end visible rather than a
                # silent no-op.
                verdict=Verdict.PENDING if chosen is not None else work.verdict,
            )
            store_write(self._store.update_candidate_work, settled)
        return ResolutionOutcome(work=settled, resolution_status=status, selected=chosen, applied=True)

    # -- spend ----------------------------------------------------------------

    def record_spend(
        self,
        *,
        category: SpendCategory,
        cost_usd: Decimal,
        discovery_run_id: str | None = None,
        artwork_id: str | None = None,
        model_id: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        units: int | None = None,
        at: datetime | None = None,
    ) -> SpendRecord:
        """Record what something cost. Attribution and history — never a ceiling.

        Nothing here reads the running total, and no state changes as a result of
        writing one. The cap is a provider-side credit limit that refuses calls
        once exhausted, and a run reaching `halted_by_budget` does so because the
        provider said so, not because a local sum crossed a number.
        """
        if cost_usd < 0:
            raise ServiceError(f"A cost cannot be negative, got {cost_usd}.")
        # Both references are checked here rather than left to the file's foreign
        # keys: a caller gets "no discovery run with id ..." instead of a refusal
        # phrased about a constraint they cannot see.
        if discovery_run_id is not None:
            self.get_run(discovery_run_id)
        if artwork_id is not None:
            self._catalogue.get_artwork(artwork_id)
        record = SpendRecord(
            id=str(uuid.uuid4()),
            category=require_member(category, enum=SpendCategory, field="category"),
            cost_usd=cost_usd,
            occurred_at=at if at is not None else datetime.now(UTC),
            discovery_run_id=discovery_run_id,
            artwork_id=artwork_id,
            model_id=model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            units=units,
        )
        store_write(self._store.add_spend_record, record)
        return record

    def run_cost(self, run_id: str) -> RunCost:
        """What this run was billed, and what it cost including every re-search under it.

        A re-search is its own run so that it has a handle, a status and a cancel
        of its own; the price of that is that "what did this intent cost" has to
        add the chain back up, which is what `total` is.
        """
        self.get_run(run_id)
        direct = self._spend_total(run_id)
        return RunCost(direct=direct, total=direct + sum(self._spend_total(child) for child in self._descendants(run_id)))

    def searches_in_run(self, run_id: str) -> int:
        """How many web searches this run has made.

        Read from the records that *price* the searches rather than counted
        separately, because a per-run search cap and the bill for that run must
        not be able to disagree about how much searching happened. Web search
        bills per call rather than per token, which is why it is its own category
        carrying a unit count at all.
        """
        self.get_run(run_id)
        return sum(
            record.units or 0
            for record in self._store.list_spend_records(run_id=run_id)
            if record.category is SpendCategory.WEB_SEARCH
        )

    def spend_in_month(self, *, year: int, month: int) -> Decimal:
        """Everything spent in one calendar month, UTC.

        The month is the **UTC** calendar month rather than the operator's local
        one, because the provider's own credit limit resets at midnight UTC — a
        report on a different boundary would disagree with the only figure that
        can actually stop spending.
        """
        if not 1 <= month <= 12:
            raise ServiceError(f"A month is 1 to 12, got {month}.")
        # The year is bounded too, so that the only input this method cannot
        # phrase a refusal for stops being the one that reaches a caller as a bare
        # stdlib ValueError through a tool boundary's "failed unexpectedly".
        if not datetime.min.year <= year < datetime.max.year:
            raise ServiceError(f"A year is {datetime.min.year} to {datetime.max.year - 1}, got {year}.")
        since = datetime(year, month, 1, tzinfo=UTC)
        until = datetime(year + (month == 12), month % 12 + 1, 1, tzinfo=UTC)
        return sum((record.cost_usd for record in self._store.list_spend_records(since=since, until=until)), Decimal(0))

    # -- internals ------------------------------------------------------------

    def _accept(self, work: CandidateWork) -> VerdictOutcome:
        """Mint the artwork this candidate becomes, and promote its instances.

        Acceptance is the only way into the catalogue, and it is a promotion
        rather than a transformation: every instance becomes a source, the
        selected one primary and the rest retained as alternates. Keeping the
        losers is what makes re-acquisition survive an institution reorganising
        its site.

        A work nothing could be found for is refused. Constraint on presentation
        alone would not be enough — a work with no credible instance would mint an
        artwork with no source, and so nothing to acquire and no way to answer
        "can this be re-acquired from scratch".

        **A work with instances but no selection is refused too, and that is the
        floor doing its job.** There are two ways to hold none: every instance
        rejected, and every instance below the display floor — `selection.best`
        declines the second, so nothing under the floor is ever chosen without
        being asked for. Promoting anyway would mint an artwork whose sources are
        every one `is_primary=False`: no record of which scan produced the
        original, and a postage stamp on the wall chosen by nobody. The remedy is
        for the curator to choose an instance explicitly, which is exactly the
        decision the floor exists to force.
        """
        # Asked of the images rather than of `resolution_status`, which answers a
        # different question: only a resolution attempt recomputes that column, so
        # turning down the last surviving instance leaves it reading `resolved`
        # until the next re-search. Accepting on it would mint a work whose sole
        # source is the scan its curator turned down — and with no primary source
        # naming which one produced the original, because the rejection stood the
        # selection down.
        images = self._store.list_candidate_images(work.id)
        if not [image for image in images if image.rejected_at is None]:
            cause = "every instance found for it has been rejected" if images else f"it is {work.resolution_status}"
            raise ServiceError(
                f"Candidate work {work.id!r}: {cause}, so there is no image to accept it on. "
                "Re-search it with resolve_images, or reject it."
            )
        # The second selectionless state, which the guard above does not cover:
        # instances survive, and every one of them is below the display floor, so
        # `selection.best` declined them all. Constraint 8 in `data-model.md` names
        # both exceptions; this is the one that reaches acceptance with sources to
        # promote and nothing to make primary.
        if not any(image.is_selected for image in images):
            # Derived from the data rather than asserted, exactly as the guard
            # above derives its own. The two situations reach this line and read
            # very differently to a curator: a work only ever found small, and one
            # whose good scan they turned down themselves — which is reachable
            # because `set_verdict` is deliberately allowed from
            # `awaiting_better_image`. Telling the second that every scan found
            # was too small contradicts what they just did.
            cause = (
                "every scan found for it is below the size this deployment will show without being asked"
                if all(self._below_floor(image) for image in images)
                else "the scans you have not turned down are all below that size, and the ones that cleared "
                "it you have already rejected"
            )
            raise ServiceError(
                f"Candidate work {work.id!r}: no instance is selected, because {cause}. Accepting now "
                "would record the work with no primary source and hang a scan nobody chose. Choose an "
                "instance explicitly, or reject the work."
            )
        # Resolved before the artwork is minted, because `add_artwork` refuses an
        # `artist_id` the catalogue does not hold — so the row has to exist first,
        # and both writes have to land inside the transaction this runs in.
        attributed = attribution.resolve(work.proposed_artist, self._catalogue.list_artists())
        minted: Artist | None = None
        if attributed.mint is not None:
            minted = self._catalogue.add_artist(name=attributed.mint)
        artist = attributed.matched if minted is None else minted
        artwork = self._catalogue.add_artwork(title=work.proposed_title, artist_id=None if artist is None else artist.id)
        for image in images:
            self._catalogue.add_source(
                artwork_id=artwork.id,
                url=image.url,
                provider=image.provider,
                source_class=image.source_class,
                acquisition_method=image.acquisition_method,
                # "We did not check" is not a value a source may carry: absence is
                # refused catalogue-side, and `unknown` is the honest reading of a
                # candidate that never established one.
                rights_status=image.rights_status if image.rights_status is not None else RightsStatus.UNKNOWN,
                is_primary=image.is_selected,
                confidence=image.confidence,
                selection_rationale=image.selection_rationale,
            )
        accepted = replace(work, verdict=Verdict.ACCEPTED, artwork_id=artwork.id, decided_at=datetime.now(UTC))
        store_write(self._store.update_candidate_work, accepted)
        return VerdictOutcome(
            work=accepted,
            minted_artist=minted,
            # Only alongside a mint: a matched artist raised none by construction,
            # and reporting them on every acceptance would train a reader to skip
            # the sentence that matters.
            duplicate_candidates=attributed.near_misses if minted is not None else (),
        )

    def _below_floor(self, image: CandidateImage) -> bool:
        """Whether this instance is too small to be selected without being asked for.

        Answers `False` when no artwork box was configured, which is the same
        thing `selection.best` does with no box: a deployment that has not said
        how big its wall is has not stated a floor either, and inventing one here
        would withhold instances against a rule nobody wrote.
        """
        return self._artwork_box is not None and selection.below_floor(image, self._artwork_box)

    def _select(self, image: CandidateImage, *, rationale: str | None) -> CandidateImage:
        """Make one instance the selected one, standing every other one down."""
        for other in self._store.list_candidate_images(image.candidate_work_id):
            if other.is_selected and other.id != image.id:
                store_write(self._store.update_candidate_image, replace(other, is_selected=False))
        chosen = replace(image, is_selected=True, selection_rationale=rationale or image.selection_rationale)
        store_write(self._store.update_candidate_image, chosen)
        return chosen

    def _refuse_covered(self, works: Iterable[CandidateWork]) -> None:
        """Refuse works a live resolve run is already re-searching, naming them.

        Keying on "not terminal" is only safe because a crashed run is reconciled
        to `interrupted` at startup. Every other terminal state is written by the
        run's own process, so without that repair a crash would leave these ids
        refused forever — turning a double-spend guard into a permanent block.
        """
        busy = [work for work in works if self._live_coverage(work.id) is not None]
        if busy:
            titles = ", ".join(f"{work.proposed_title!r} ({work.id})" for work in busy)
            raise ServiceError(
                f"A re-search is already running for {titles}. Wait for it to finish, or cancel it — "
                "re-submitting would pay twice for one result."
            )

    def _live_coverage(self, candidate_work_id: str) -> str | None:
        """The id of a resolve run still re-searching this work, if there is one."""
        for coverage in self._store.list_coverage_by_work(candidate_work_id):
            run = self._store.get_run(coverage.resolve_run_id)
            if run is not None and not run.status.is_terminal:
                return run.id
        return None

    def _works_of(self, run: DiscoveryRun) -> Sequence[CandidateWork]:
        """A run's works: what it proposed, or for a re-search, what it covers.

        The two relations are deliberately different. A work's
        `discovery_run_id` is its provenance and never changes; coverage records
        which run is re-searching it, which changes every time one does.
        """
        if run.kind is RunKind.DISCOVERY:
            return self._store.list_candidate_works(run.id)
        return [self.get_candidate_work(coverage.candidate_work_id) for coverage in self._store.list_coverage_by_run(run.id)]

    def _descendants(self, run_id: str) -> list[str]:
        """Every resolve run below this one, however deep the chain goes."""
        found: list[str] = []
        frontier = [run_id]
        while frontier:
            parent = frontier.pop()
            children = [run.id for run in self._store.list_runs(kind=RunKind.RESOLVE) if run.parent_run_id == parent]
            found.extend(children)
            frontier.extend(children)
        return found

    def _spend_total(self, run_id: str) -> Decimal:
        return sum((record.cost_usd for record in self._store.list_spend_records(run_id=run_id)), Decimal(0))

    def _require_image(self, candidate_image_id: str) -> CandidateImage:
        image = self._store.get_candidate_image(candidate_image_id)
        if image is None:
            raise ServiceError(f"No candidate image with id {candidate_image_id!r} exists.")
        return image

    def _require_status(self, run_id: str, expected: RunStatus, *, doing: str) -> DiscoveryRun:
        """Refuse a transition the run is not standing on the edge of."""
        run = self.get_run(run_id)
        if run.status is not expected:
            raise ServiceError(f"Run {run_id!r} is {run.status}, so it cannot {doing}; that needs a run in {expected}.")
        return run

    def _end_active(
        self,
        run_id: str,
        ending: RunStatus,
        *,
        doing: str,
        actual_cost_usd: Decimal | None,
        from_working: bool = False,
    ) -> DiscoveryRun:
        """End a run that is still running. A finished run stays as it finished.

        `from_working` narrows the ending to the states a process actually holds.
        Breaking and being refused by the provider are both things that happen to
        a run *while it works*; offering them from `awaiting_approval` would leave
        two edges reachable that the state machine does not draw, and a state
        machine with edges nobody modelled is one nobody can reason about.
        """
        with self._store.transaction():
            run = self.get_run(run_id)
            if run.status.is_terminal:
                raise ServiceError(f"Run {run_id!r} already ended as {run.status}, so it cannot {doing}.")
            if from_working and not run.status.is_process_held:
                raise ServiceError(
                    f"Run {run_id!r} is {run.status}, so nothing is running that could {doing}; "
                    "approve, decline, or cancel it instead."
                )
            ended = self._ended(run, ending, actual_cost_usd=actual_cost_usd)
            store_write(self._store.update_run, ended)
        return ended

    @staticmethod
    def _ended(
        run: DiscoveryRun,
        status: RunStatus,
        *,
        actual_cost_usd: Decimal | None = None,
        unresolved_work_count: int | None = None,
    ) -> DiscoveryRun:
        """The run as it will be stored once it has ended.

        A cost already recorded is kept when the caller supplies none: a run that
        spent money before being cancelled still spent it.
        """
        return replace(
            run,
            status=status,
            completed_at=datetime.now(UTC),
            actual_cost_usd=actual_cost_usd if actual_cost_usd is not None else run.actual_cost_usd,
            unresolved_work_count=(unresolved_work_count if unresolved_work_count is not None else run.unresolved_work_count),
        )
