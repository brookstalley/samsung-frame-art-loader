"""Running a discovery run: starting it, gating it, pricing it, and reporting it.

`DiscoveryService` owns the *records* — the two state machines, the verdicts, the
spend rows — and is deliberately synchronous and free of any notion of a process.
This is the concern above it: the thing that decides a run should begin, hands
phase 1 to an engine, writes what came back, and answers "where is it now". The
split is the same one the catalogue and discovery services already draw. A record
layer that also knew about worker threads and long-polls would be untestable
without both.

**Discovery must not block.** `start` returns a run handle and the work happens
behind it, because a call that ran for the length of a discovery run would be
killed by the client long before it finished — the idle abort is five minutes and
a run takes many. `status` is the other half: it holds until something changes,
so a caller polls rarely rather than in a tight loop, and it holds for less than
a minute so no single call approaches any client threshold.

**Nothing here decides whether money may be spent.** The ceiling is a
provider-side credit limit and arrives as a refusal from the engine, which this
turns into a run state an agent can act on. What *is* enforced here is the per-run
search allowance, which is a different thing: a bound on one run's fan-out, so
that the figure a curator authorised is one the run cannot freely exceed.
"""

import logging
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from time import monotonic
from typing import Final

from curation.discovery.dedup import work_dedup_key
from curation.discovery.engine import (
    BudgetExhausted,
    DiscoveryEngine,
    EngineFailure,
    EngineSpend,
    WorkList,
    WorkListRequest,
)
from curation.discovery.images import ImageQuery, ImageSearchFailure
from curation.discovery.phase_two import JudgedImage, PhaseTwoEngine
from curation.logs import run_context
from curation.persistence.discovery_records import (
    CandidateWork,
    DiscoveryRun,
    InitiatedBy,
    ResolutionStatus,
    RunKind,
    RunStatus,
)
from curation.services.discovery import DiscoveryService
from curation.services.errors import ServiceError
from curation.services.previews import PreviewCache

log = logging.getLogger(__name__)

#: How long `status` holds before answering with whatever it has. Sized to sit
#: under the 60-second tool timeout a client applies to a single call, which
#: leaves the whole surface comfortably clear of both the two-minute
#: auto-background and the five-minute idle abort.
STATUS_HOLD_SECONDS: Final[float] = 45.0

#: How often a held `status` re-checks when nothing has signalled it. The wait is
#: normally woken by the change itself; this only bounds how long a change made
#: by something outside this process could go unnoticed.
_RECHECK_SECONDS: Final[float] = 5.0


@dataclass(frozen=True, slots=True)
class DiscoverySettings:
    """What discovery is allowed to do, and what a provider charges for doing it.

    **Costs are `Decimal`, never `float`.** A tenth of a cent that cannot be
    represented exactly is a rounding error in the figure a curator is asked to
    authorise against, and then in a total nobody will reconcile against the
    provider's own.

    The two allowances are one cap in two parts, and the split is forced by what
    is knowable when: phase 1 has no work count to derive an allowance from,
    because producing the work count is what phase 1 is *for*. The estimate
    decomposes the same way, which is what lets a caller be told what asking will
    cost before anything has run.
    """

    approval_threshold: int
    phase1_search_allowance: int
    phase2_searches_per_work: int
    search_cost_usd: Decimal
    input_cost_usd_per_mtok: Decimal
    output_cost_usd_per_mtok: Decimal
    #: What one phase-1 run may consume, as bounds rather than typical figures.
    #: The two are arrived at differently: input is a measurement with headroom,
    #: output is the provider's own reservation, which a run physically cannot
    #: exceed. So they are close in size even though real consumption is
    #: input-heavy — and a model with cheap input and expensive output is priced
    #: accordingly rather than getting the pass an input-dominated basis gave it.
    phase1_input_tokens: int
    phase1_output_tokens: int

    @property
    def phase1_estimate_usd(self) -> Decimal:
        """What asking a question costs, at the allowance's ceiling.

        **Bounded rather than typical.** A figure a run may freely exceed is not
        an estimate, and this is the number a curator or an agent decides on
        before anything has been spent — so it prices the whole search allowance
        whether or not a given run uses it.
        """
        return self._model_call_usd + self.phase1_search_allowance * self.search_cost_usd

    def phase2_estimate_usd(self, work_count: int) -> Decimal:
        """What resolving a known work list costs. Nothing, on museum APIs.

        **Zero is measured, not assumed** (2026-08-02). Phase 2 asks museum APIs,
        which are open and unmetered, and establishes whether a result is the
        requested work by comparing titles and artists locally — so it makes no
        model call and no paid web search. Bandwidth is the only cost and nobody
        bills for it.

        This figure priced `phase2_searches_per_work` paid web searches until the
        providers were chosen. That allowance still bounds a run's fan-out and is
        still reported beside a run's usage, but nothing it bounds is billed
        today, and pricing it would show a curator a charge that will not appear.
        **A paid provider added later reinstates the arithmetic here**, which is
        the one place it has to change.
        """
        return Decimal(0)

    @property
    def _model_call_usd(self) -> Decimal:
        return (
            self.phase1_input_tokens * self.input_cost_usd_per_mtok + self.phase1_output_tokens * self.output_cost_usd_per_mtok
        ) / 1_000_000


@dataclass(frozen=True, slots=True)
class Estimate:
    """What something is expected to cost, and which question was answered.

    `phase` is carried rather than left for a caller to infer from whether they
    passed a run id, because the two figures answer genuinely different
    questions — "what will it cost me to ask this" and "what will it cost to
    resolve what I found" — and a number whose meaning depends on remembering
    what you sent is a number that gets read wrong.
    """

    phase: str
    cost_usd: Decimal
    basis: str
    run_id: str | None = None


@dataclass(frozen=True, slots=True)
class SpendReport:
    """What was actually spent, over a run or over a calendar month.

    A run's headline figure includes every re-search descended from it, because
    "what did asking for Dalí cost" is that number and not the narrower one. The
    narrower one is carried alongside rather than replaced: a run billed little
    itself whose re-searches cost ten times more is a fact worth being able to
    see.
    """

    scope: str
    cost_usd: Decimal
    run_id: str | None = None
    run_direct_usd: Decimal | None = None
    year: int | None = None
    month: int | None = None


@dataclass(frozen=True, slots=True)
class RunView:
    """A run, its works, and what it has spent of its search allowance.

    The allowance is *this deployment's current* setting, while the usage is the
    run's own recorded history. They are reported side by side rather than
    reduced to a verdict, so a run read after the setting changed shows both
    numbers instead of a boolean silently recomputed against a rule it never ran
    under.
    """

    run: DiscoveryRun
    resolved: int
    unresolved: int
    pending: int
    searches_used: int
    search_allowance: int
    #: Whether this deployment can resolve images at all. Carried on the view
    #: because a run sitting in `resolving_images` means two different things
    #: depending on it — work under way, or work nothing will ever pick up — and
    #: a surface describing that state has no other way to tell them apart. It
    #: was a hardcoded sentence once, and it went from true to false the day
    #: phase 2 was built; a fact read from the wiring cannot go stale that way.
    image_resolution_available: bool

    @property
    def work_count(self) -> int:
        return self.resolved + self.unresolved + self.pending

    @property
    def searches_exhausted(self) -> bool:
        """Whether this run has used every search its allowance currently permits."""
        return self.searches_used >= self.search_allowance


def _daemon_thread(work: Callable[[], None]) -> None:
    """Run a run's phase-1 work behind the handle that was already returned.

    Daemon threads on purpose: a run in flight when the process stops is a
    designed-for event, not a case to drain. The catalogue holds the run's state,
    startup reconciliation moves whatever was mid-flight to `interrupted`, and
    that WARNING is the only signal a run died — a dying process cannot report
    its own death. Draining instead would hold a deploy restart open for the
    length of a run to reach the same place.
    """
    threading.Thread(target=work, name="discovery-run", daemon=True).start()


class DiscoveryRunner:
    """Start discovery runs, drive phase 1, and answer where a run has got to."""

    def __init__(
        self,
        discovery: DiscoveryService,
        engine: DiscoveryEngine,
        settings: DiscoverySettings,
        *,
        images: PhaseTwoEngine | None = None,
        previews: PreviewCache | None = None,
        spawn: Callable[[Callable[[], None]], None] = _daemon_thread,
    ) -> None:
        self._discovery = discovery
        self._engine = engine
        self._settings = settings
        #: Phase 2, and the cache its previews land in. Optional together: a
        #: deployment without an image provider runs phase 1 and stops, which is
        #: a coherent configuration and the one every phase-1 test uses. What is
        #: not coherent is one without the other, so the pair is checked rather
        #: than each being defaulted independently.
        if (images is None) != (previews is None):
            raise ServiceError(
                "Phase 2 needs both an image engine and a preview cache, or neither. One without the other "
                "would either find instances it cannot show or cache previews for instances nothing finds."
            )
        self._images = images
        self._previews = previews
        self._spawn = spawn
        #: Woken whenever any run's state changes, so a held `status` answers as
        #: soon as there is something to say. The counter is what closes the gap
        #: between reading a run and starting to wait: a change landing in
        #: between moves it, and the waiter re-reads instead of sleeping through
        #: the news it was waiting for.
        self._changed = threading.Condition()
        self._generation = 0
        #: Runs this process is actively working on, which is what `status`
        #: decides to hold on. Guarded by the same condition as the counter, so
        #: a waiter cannot read it between a run being registered and the wake
        #: that follows.
        self._in_flight: set[str] = set()

    # -- reads ----------------------------------------------------------------

    def estimate(self, run_id: str | None = None) -> Estimate:
        """Price a question, or price resolving what a run already found.

        Free and read-only, on the one tool that otherwise exists to spend: an
        agent has no wallet and no instinct for what is expensive, so it must be
        able to price an intent without committing to it.

        With no run id this is the phase-1 figure, computable before anything
        exists. With one it is that run's *stored* phase-2 figure — stored rather
        than recomputed because prices and allowances are configuration, and a
        run reviewed later must still report the estimate it was authorised
        against rather than what today's settings would imply.
        """
        if run_id is None:
            return Estimate(
                phase="phase_1",
                cost_usd=self._settings.phase1_estimate_usd,
                basis=(
                    f"One model call plus up to {self._settings.phase1_search_allowance} web searches, "
                    "which is the most phase 1 may use. Bounded, not typical."
                ),
            )
        run = self._discovery.get_run(run_id)
        if run.estimated_cost_usd is None:
            raise ServiceError(
                f"Run {run_id!r} has no phase-2 estimate yet: it is {run.status}, and the figure is computed "
                "when phase 1 finishes and the work count is known. Call estimate with no run_id for the "
                "phase-1 figure, or status to see where this run has got to."
            )
        return Estimate(
            phase="phase_2",
            cost_usd=run.estimated_cost_usd,
            basis=(
                f"Resolving the {len(self._discovery.list_candidate_works(run_id))} works this run proposed. "
                "Phase 2 asks museum APIs, which are free, and identifies works locally — so approving this "
                "run spends nothing further. The gate is on the work count, not the price."
            ),
            run_id=run_id,
        )

    def spend_report(self, *, run_id: str | None = None, year: int | None = None, month: int | None = None) -> SpendReport:
        """What a run cost, or what a calendar month cost.

        Which question is answered is decided here rather than at a surface, so
        the browser and an agent cannot come to differ about what `spend` with no
        arguments means.
        """
        if run_id is not None:
            if year is not None or month is not None:
                raise ServiceError(
                    "spend answers about one run or about one month, not both. Pass run_id on its own for a "
                    "run's cost, or year and month on their own for a month's."
                )
            cost = self._discovery.run_cost(run_id)
            return SpendReport(scope="run", cost_usd=cost.total, run_id=run_id, run_direct_usd=cost.direct)
        if (year is None) != (month is None):
            raise ServiceError("A month needs both year and month, or neither — omitting both reports the current month.")
        now = datetime.now(UTC)
        # The **UTC** month, matching the boundary the provider's own credit
        # limit resets on. A report on the operator's local month would disagree
        # with the only figure that can actually stop spending.
        year, month = (year, month) if year is not None and month is not None else (now.year, now.month)
        return SpendReport(
            scope="month",
            cost_usd=self._discovery.spend_in_month(year=year, month=month),
            year=year,
            month=month,
        )

    def list_runs(self, *, status: RunStatus | None = None, kind: RunKind | None = None) -> Sequence[DiscoveryRun]:
        """Every run, newest first, optionally narrowed."""
        return self._discovery.list_runs(status=status, kind=kind)

    def run_status(self, run_id: str, *, wait: bool = True) -> RunView:
        """Where a run is, holding until that changes if work is actually under way.

        **The hold is keyed on this process having the run in hand, not on the
        run's state.** The two are not the same, and the difference is not
        academic: a run's status can name a phase that nothing in this build
        advances, and holding there would make every caller wait out the full
        poll to be told something that was already true and was never going to
        change. Asking what is in flight is also the one formulation that cannot
        go stale — a phase this process does not run is a phase it does not
        register, without anyone having to remember to say so.

        A run waiting for a curator, or one that has ended, therefore answers at
        once, as does one whose worker died with the process that owned it.
        """
        deadline = monotonic() + STATUS_HOLD_SECONDS
        with self._changed:
            seen = self._generation
        while True:
            view = self._view(run_id)
            remaining = deadline - monotonic()
            with self._changed:
                working = run_id in self._in_flight
            if not wait or not working or remaining <= 0:
                return view
            with self._changed:
                if self._generation == seen:
                    self._changed.wait(min(remaining, _RECHECK_SECONDS))
                seen = self._generation

    # -- writes ---------------------------------------------------------------

    def start(self, *, intent_text: str, initiated_by: InitiatedBy) -> DiscoveryRun:
        """Begin a run and return its handle at once; phase 1 proceeds behind it.

        An engine that cannot run is refused here rather than by creating a run
        that immediately fails. The two would be indistinguishable to a caller
        reading the catalogue afterwards, and only one of them is true: nothing
        was attempted, so nothing should be recorded as having been.
        """
        unavailable = self._engine.unavailable_reason
        if unavailable is not None:
            raise ServiceError(unavailable)
        run = self._discovery.start_discovery_run(intent_text=intent_text, initiated_by=initiated_by)
        # Registered before the work is handed off, so a `status` arriving in
        # the gap between the handle being returned and the worker starting
        # still sees a run in flight and holds for it.
        with self._changed:
            self._in_flight.add(run.id)
        self._bump()
        with run_context(run.id):
            log.info(
                "discovery run started",
                extra={
                    "event": "run.started",
                    "initiated_by": str(run.initiated_by),
                    "intent_text": run.intent_text,
                    "search_allowance": self._settings.phase1_search_allowance,
                    "estimated_cost_usd": str(self._settings.phase1_estimate_usd),
                },
            )
        self._spawn(lambda: self._enumerate(run.id, intent_text))
        return run

    def approve(self, run_id: str) -> RunView:
        """Accept the work list and its price, and let phase 2 begin behind it.

        Returns as soon as the decision is recorded, exactly as `start` does and
        for the same reason: resolving a work list takes minutes, and a call held
        open for it would be abandoned by the client long before it finished.
        """
        view = self._transition(self._discovery.approve_run, run_id, event="run.approved")
        self._begin_phase_two(run_id)
        return view

    def decline(self, run_id: str) -> RunView:
        """Refuse the work list. The run ends without phase 2 ever spending."""
        return self._transition(self._discovery.decline_run, run_id, event="run.declined")

    def cancel(self, run_id: str) -> RunView:
        """Stop a run from wherever it is. Money already spent stays recorded."""
        return self._transition(self._discovery.cancel_run, run_id, event="run.cancelled")

    # -- phase 1 --------------------------------------------------------------

    def _enumerate(self, run_id: str, intent_text: str) -> None:
        """Ask the engine for a work list and write down whatever came back.

        Runs on the worker, behind the handle `start` already returned, so it
        never raises to a caller — everything that can go wrong has to end as a
        run state instead. A worker that died with an exception would leave the
        run process-held and looking alive until the next restart reconciled it,
        turning every engine bug into a phantom hang.
        """
        try:
            with run_context(run_id):
                self._attempt_phase_one(run_id, intent_text)
        finally:
            # Released however this ended, including on a path that raised past
            # every handler inside. A run left registered would hold every later
            # `status` call on it for the full poll, which is the failure the
            # register exists to prevent.
            with self._changed:
                self._in_flight.discard(run_id)
            self._bump()

    def _attempt_phase_one(self, run_id: str, intent_text: str) -> None:
        """Call the engine and turn whatever it did into a run state."""
        request = WorkListRequest(intent_text=intent_text, search_allowance=self._settings.phase1_search_allowance)
        try:
            # Recording and settling are inside the guard, not in an `else`.
            # `_settle` expects only `ServiceError`, so any other refusal from
            # the record layer at settling time would otherwise escape and leave
            # the run in `resolving_works` with nothing working on it — the same
            # hang the engine's own half is guarded against, one exception class
            # over.
            #
            # **A sustained record-layer outage is not covered here, and cannot
            # be.** Ending a run is itself a write, so if the catalogue is down
            # the handler below fails too. That case is answered by the trace it
            # logs first and by startup reconciliation, which moves every
            # process-held run to `interrupted` — no in-process handler can
            # write a failure record when the thing that records is what failed.
            produced = self._engine.enumerate_works(request)
            self._record_spend(run_id, produced.spend)
            self._settle(run_id, produced)
        except BudgetExhausted as exc:
            self._record_spend(run_id, exc.spend)
            self._end(run_id, self._discovery.halt_run_for_budget, "run.halted_by_budget", str(exc))
        except EngineFailure as exc:
            self._record_spend(run_id, exc.spend)
            self._end(run_id, self._discovery.fail_run, "run.failed", str(exc))
        except Exception:  # prawduct:allow prawduct/broad-except -- worker boundary: a fault must end the run, not hang it
            log.exception("phase 1 raised an unexpected error", extra={"event": "run.failed"})
            self._end(run_id, self._discovery.fail_run, "run.failed", "Phase 1 failed unexpectedly.")

    def _settle(self, run_id: str, produced: WorkList) -> None:
        """Turn an engine's answer into proposed works and close phase 1."""
        allowance = self._settings.phase1_search_allowance
        if produced.searches_used > allowance:
            # Failed rather than accepted and reported. An engine that overran
            # the bound spent money the estimate did not cover, so the run's
            # results were bought outside what anyone authorised — reporting it
            # as a successful run with a note would make the breach a footnote on
            # a bill somebody already paid.
            self._end(
                run_id,
                self._discovery.fail_run,
                "run.failed",
                f"Phase 1 used {produced.searches_used} web searches against an allowance of {allowance}. "
                "The run's results are not accepted: the search cap is what makes the pre-run estimate a bound.",
            )
            return
        try:
            proposed, suppressed, duplicates = self._propose(run_id, produced)
            estimate = self._settings.phase2_estimate_usd(proposed)
            run = self._discovery.finish_work_list(
                run_id,
                approval_threshold=self._settings.approval_threshold,
                estimated_cost_usd=estimate,
                strategy=produced.strategy,
            )
        except ServiceError as exc:
            self._could_not_settle(run_id, exc)
            return
        self._bump()
        log.info(
            "phase 1 finished",
            extra={
                "event": "run.work_list_ready",
                "works_proposed": proposed,
                "works_suppressed": suppressed,
                "works_duplicate": duplicates,
                "searches_used": produced.searches_used,
                "search_allowance": allowance,
                "approval_required": run.approval_required,
                "approval_threshold": self._settings.approval_threshold,
                "estimated_cost_usd": str(estimate),
            },
        )
        if run.status is RunStatus.RESOLVING_IMAGES:
            # Inline on this worker rather than spawned onto another. This thread
            # is already registered as working on the run, and handing off would
            # let `_enumerate`'s release run first — leaving a run whose phase 2
            # is under way looking idle to every `status` call, which is the one
            # thing the registration exists to prevent.
            self._attempt_phase_two(run_id)

    def _could_not_settle(self, run_id: str, exc: ServiceError) -> None:
        """Decide what a refusal during settling actually was, rather than assuming.

        Two very different things raise here and the run's own state is what
        tells them apart. If it has ended, a curator cancelled it while the
        engine was working: its spend stands, its results are discarded, and
        that is an ordinary outcome — writing works onto a run somebody stopped
        would resurrect the thing they stopped.

        **Anything else is a fault, and must end the run.** An engine returning
        a work with no title or no rationale is refused by the record layer with
        the same exception type, and treating that as a cancellation would leave
        the run sitting in a phase nothing is working on, with nothing recorded
        as wrong — the silent hang this whole worker is arranged to prevent.
        """
        if self._discovery.get_run(run_id).status.is_terminal:
            log.info(
                "phase 1 finished on a run that had already ended; discarding its results: %s",
                exc,
                extra={"event": "run.discarded"},
            )
            return
        self._end(
            run_id, self._discovery.fail_run, "run.failed", f"Phase 1 produced a work list that could not be recorded: {exc}"
        )

    def _propose(self, run_id: str, produced: WorkList) -> tuple[int, int, int]:
        """Record each work once, skipping what the curator already turned down.

        Two kinds of skip, counted separately because they mean different things.
        A *suppressed* work is one a curator rejected in an earlier run, and
        skipping it is the whole point of the dedup key — proposing it again
        would ask them to decline the same painting forever. A *duplicate* is the
        engine naming one work twice inside a single answer, which is the engine
        being imprecise rather than the curator having decided anything.

        Both are logged rather than silently dropped: a run that proposed twelve
        works from an engine that named twenty is a run whose count needs an
        explanation.
        """
        proposed = 0
        suppressed = 0
        duplicates = 0
        seen: set[str] = set()
        for work in produced.works:
            key = work_dedup_key(title=work.title, artist=work.artist)
            if key in seen:
                duplicates += 1
                log.info("skipping a work the engine named twice", extra={"event": "work.duplicate", "work_title": work.title})
                continue
            seen.add(key)
            if self._discovery.is_work_suppressed(key):
                suppressed += 1
                log.info(
                    "skipping a work the curator has already rejected",
                    extra={"event": "work.suppressed", "work_title": work.title},
                )
                continue
            self._discovery.propose_work(
                run_id=run_id,
                proposed_title=work.title,
                rationale=work.rationale,
                work_dedup_key=key,
                proposed_artist=work.artist,
            )
            proposed += 1
        return proposed, suppressed, duplicates

    # -- phase 2 --------------------------------------------------------------

    def _begin_phase_two(self, run_id: str) -> None:
        """Put phase 2 on a worker, if this deployment has one to run.

        A deployment with no image provider simply leaves the run where it is,
        which `status` reports in words. Nothing is created and nothing fails:
        the run's work list is real and was worth producing, and a run that
        failed because a capability is absent would be indistinguishable from
        one that failed because something broke.
        """
        if self._images is None:
            return
        # Registered before the hand-off, so a `status` arriving in the gap
        # between approval returning and the worker starting still sees a run in
        # flight and holds for it.
        with self._changed:
            self._in_flight.add(run_id)
        self._bump()
        self._spawn(lambda: self._resolve_run(run_id))

    def _resolve_run(self, run_id: str) -> None:
        """Phase 2 on its own worker, releasing the run however it ends."""
        try:
            with run_context(run_id):
                self._attempt_phase_two(run_id)
        finally:
            with self._changed:
                self._in_flight.discard(run_id)
            self._bump()

    def _attempt_phase_two(self, run_id: str) -> None:
        """Resolve every pending work, then close the run.

        Runs on a worker with nobody to raise to, so everything that can go wrong
        ends as a run state. A worker dying with an exception would leave the run
        process-held and looking alive until the next restart reconciled it,
        turning every provider bug into a phantom hang.

        The engine and the cache are read once here and passed down, so the
        deployment that has neither returns before anything else looks — and no
        method below has to defend against a `None` it cannot do anything about.
        """
        images, previews = self._images, self._previews
        if images is None or previews is None:
            return
        try:
            self._resolve_pending(run_id, images, previews)
        except ServiceError as exc:
            # The record layer refusing. Distinguished from a fault the same way
            # phase 1 does it — by the run's own state — because a curator
            # cancelling mid-resolve is an ordinary outcome and not a failure.
            if self._discovery.get_run(run_id).status.is_terminal:
                log.info("phase 2 finished on a run that had already ended: %s", exc, extra={"event": "run.discarded"})
                return
            self._end(run_id, self._discovery.fail_run, "run.failed", f"Phase 2 could not record what it found: {exc}")
        except Exception:  # prawduct:allow prawduct/broad-except -- worker boundary: a fault must end the run, not hang it
            log.exception("phase 2 raised an unexpected error", extra={"event": "run.failed"})
            self._end(run_id, self._discovery.fail_run, "run.failed", "Phase 2 failed unexpectedly.")

    def _resolve_pending(self, run_id: str, images: PhaseTwoEngine, previews: PreviewCache) -> None:
        """Ask the provider about each work that has not been resolved yet."""
        works = [
            work for work in self._discovery.list_candidate_works(run_id) if work.resolution_status is ResolutionStatus.PENDING
        ]
        resolved = unresolved = unreachable = 0
        for work in works:
            # Re-read each time round rather than once before the loop: a curator
            # cancelling partway through must stop the run there, and a decision
            # read before the first work would honour it only if it arrived
            # before any of them.
            if self._discovery.get_run(run_id).status.is_terminal:
                log.info(
                    "phase 2 stopping: the run ended underneath it",
                    extra={"event": "run.discarded", "works_remaining": len(works) - resolved - unresolved - unreachable},
                )
                return
            outcome = self._resolve_work(work, images, previews)
            if outcome is None:
                unreachable += 1
            elif outcome:
                resolved += 1
            else:
                unresolved += 1
        self._close_phase_two(run_id, resolved=resolved, unresolved=unresolved, unreachable=unreachable, works=len(works))

    def _resolve_work(self, work: CandidateWork, images: PhaseTwoEngine, previews: PreviewCache) -> bool | None:
        """Find and record one work's instances.

        Three outcomes, and they are genuinely different. `True` — an instance
        was found and selected. `False` — the provider was asked and holds
        nothing credible, which makes the work `unresolved` and is the signal
        that phase 1 may have proposed something that does not exist. `None` —
        the provider could not be asked at all, which says nothing about the work
        and so must not be recorded as a verdict on it.
        """
        try:
            judged = images.resolve(ImageQuery(title=work.proposed_title, artist=work.proposed_artist))
        except ImageSearchFailure as exc:
            log.warning(
                "could not search for a work's images; it stays pending rather than being called unresolved: %s",
                exc,
                extra={"event": "phase_two.unreachable", "work_title": work.proposed_title},
            )
            return None
        for entry in judged:
            self._record_instance(work, entry, previews)
        outcome = self._discovery.record_resolution(work.id)
        if not outcome.applied:
            log.info(
                "a resolution finished against a work the curator had already decided; reporting, not applying",
                extra={"event": "phase_two.verdict_stands", "work_title": work.proposed_title},
            )
        return outcome.resolution_status is ResolutionStatus.RESOLVED

    def _record_instance(self, work: CandidateWork, entry: JudgedImage, previews: PreviewCache) -> None:
        """Write down one judged instance, caching its preview on the way in.

        The preview is fetched before the row is written so the path is recorded
        with it rather than by a second update — a row written first and patched
        after is a row that is briefly wrong, and on a crash permanently so.
        """
        found = entry.found
        self._discovery.record_image(
            candidate_work_id=work.id,
            url=found.url,
            provider=found.provider,
            source_class=found.source_class,
            acquisition_method=found.acquisition_method,
            confidence=entry.confidence,
            preview_url=found.preview_url,
            preview_path=previews.store(found.preview_url) if found.preview_url else None,
            estimated_width=found.estimated_width,
            estimated_height=found.estimated_height,
            rights_status=found.rights_status,
            quality_score=entry.quality_score,
            selection_rationale=entry.rationale,
        )

    def _close_phase_two(self, run_id: str, *, resolved: int, unresolved: int, unreachable: int, works: int) -> None:
        """End the run on what phase 2 actually managed.

        **A run whose every work was unreachable failed**, and saying otherwise
        is the difference that matters here: "we looked and your paintings are
        not in the collection" and "we could not reach the collection" lead to
        opposite actions, and only the first is a fact about the works. A run
        that reached the provider for some of them completed, with the rest left
        pending and visible as such rather than silently called unresolved.
        """
        if works and unreachable == works:
            self._end(
                run_id,
                self._discovery.fail_run,
                "run.failed",
                f"Phase 2 could not reach an image provider for any of this run's {works} works. "
                "Nothing is known about whether they exist; the works are unchanged and can be re-searched.",
            )
            return
        try:
            self._discovery.complete_run(run_id, actual_cost_usd=self._discovery.run_cost(run_id).direct)
        except ServiceError as exc:
            log.info("could not complete the run; it had already ended: %s", exc, extra={"event": "run.already_ended"})
            return
        self._bump()
        log.info(
            "phase 2 finished",
            extra={
                "event": "run.completed",
                "works_resolved": resolved,
                "works_unresolved": unresolved,
                "works_unreachable": unreachable,
            },
        )

    # -- internals ------------------------------------------------------------

    def _view(self, run_id: str) -> RunView:
        results = self._discovery.run_results(run_id)
        works = len(results.resolved) + len(results.unresolved) + len(results.pending)
        return RunView(
            run=results.run,
            resolved=len(results.resolved),
            unresolved=len(results.unresolved),
            pending=len(results.pending),
            searches_used=self._discovery.searches_in_run(run_id),
            search_allowance=self._allowance_for(results.run, works),
            image_resolution_available=self._images is not None,
        )

    def _allowance_for(self, run: DiscoveryRun, works: int) -> int:
        """The two-part cap as one number, for the phases this run actually performs.

        A discovery run gets the flat phase-1 allowance plus a per-work component
        that only exists once phase 1 has said how many works there are. **A
        re-search gets only the per-work component**, because phase 1 already
        happened on its parent: granting it the flat allowance as well would
        report a bound larger than anything it could legitimately use, on the
        operation a curator can repeat as often as they like.
        """
        per_work = works * self._settings.phase2_searches_per_work
        if run.kind is RunKind.RESOLVE:
            return per_work
        return self._settings.phase1_search_allowance + per_work

    def _record_spend(self, run_id: str, spend: Sequence[EngineSpend]) -> None:
        """Write down what the engine spent, whether or not the run succeeded.

        Before any state change, and on every path out of the engine including
        the failing ones: a run that broke halfway still incurred what it
        incurred, and a failure path that skipped this would under-report the
        month by exactly what the failures cost.
        """
        for entry in spend:
            self._discovery.record_spend(
                category=entry.category,
                cost_usd=entry.cost_usd,
                discovery_run_id=run_id,
                model_id=entry.model_id,
                input_tokens=entry.input_tokens,
                output_tokens=entry.output_tokens,
                units=entry.units,
            )

    def _end(self, run_id: str, ending: Callable[..., DiscoveryRun], event: str, reason: str) -> None:
        """Move a run to a terminal state from the worker, tolerating a race.

        A curator cancelling while phase 1 was working leaves nothing to end, and
        that is an ordinary outcome rather than a second failure — so it is
        logged and dropped rather than raised into a worker that has nobody to
        raise to.
        """
        try:
            ending(run_id, actual_cost_usd=self._discovery.run_cost(run_id).direct)
        except ServiceError as exc:
            log.info("could not end the run; it had already ended: %s", exc, extra={"event": "run.already_ended"})
            return
        self._bump()
        log.warning(reason, extra={"event": event})

    def _transition(self, change: Callable[[str], DiscoveryRun], run_id: str, *, event: str) -> RunView:
        """Apply a curator's decision and wake anything holding on this run.

        Answers with the whole view rather than the bare record, so every action
        that acts on a run replies in the same shape `status` does. A caller that
        approved a run should not have to make a second call to learn what it
        approved, and two shapes for one entity is how a client comes to parse
        one of them wrongly.
        """
        run = change(run_id)
        self._bump()
        with run_context(run_id):
            log.info("run %s", run.status, extra={"event": event, "status": str(run.status)})
        return self._view(run_id)

    def _bump(self) -> None:
        """Announce that some run's state changed, waking every held `status`.

        Called after the write rather than inside it, and never while the
        catalogue's own lock is held: a waiter woken here goes straight to the
        store to re-read, and waking it from inside a transaction would have it
        block on the lock the waker is still holding.
        """
        with self._changed:
            self._generation += 1
            self._changed.notify_all()
