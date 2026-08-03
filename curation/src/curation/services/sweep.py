"""Reclaiming the previews of works nobody is judging any more.

Candidate previews are the one class of file under `ART_ROOT` that nothing else
reclaims. Originals are permanent, renditions and thumbnails are regenerated
against whatever they were derived from, and both have a writer that owns their
staleness. A preview has neither: it is written once when phase 2 finds an
instance, and it stays until something deletes it. The plane runs on an SD card
whose exhaustion is the top operational risk, and one preview lands per image
instance per work, growing with every run and every re-search.

**A sweep rather than an on-verdict hook, decided at build.** Both reclaim the
same files. A hook does it sooner and loses everything it was mid-way through
when the process stops — and a leaked preview is invisible, because nothing
afterwards is looking for one. A sweep is idempotent by construction: it derives
what to delete from the catalogue's current state rather than from an event it
had to catch, so a crashed sweep costs a delay and nothing else, and the next one
picks up exactly what the last one missed.

**A preview file is named by its URL's digest, so two works can share one.** The
same scan proposed for two candidate works — which is ordinary when phase 1 names
one painting twice and phase 2 resolves both to the same museum image — is two
rows pointing at one file. Deleting on the first work's verdict would take the
picture out from under a work still being reviewed, and the review card would
then report the file as unreadable when in fact this process removed it. So the
unit of deletion is the *path*, and a path survives while any work still under
review references it.

**The pass runs inside one store transaction, and what that closes is worth
stating exactly, because it is not everything.** Reading the references and
unlinking are two steps, and holding the store's lock across both stops a writer
landing *between them* — `record_image` takes the same lock, so no row can appear
against a path this pass has already judged reclaimable while the pass is running.

**What it does not close is the writer's own straddle, and that is recorded rather
than claimed away.** `PreviewCache.store` returns a digest-named file it finds on
disk without re-fetching, and it holds no lock while doing so; `record_image` takes
the lock afterwards. So a resolve run can read "the file is there", have a whole
sweep pass run and delete it, and then write a row naming it. That row is permanent,
because `record_image` never rewrites `preview_path` for a URL its work already
holds. Closing it means the row write verifying the file inside the lock it takes,
which is a change to what the record layer depends on and is filed rather than
smuggled in here. The consequence is bounded and is reported honestly: `review.py`
treats a `preview_path` whose file is missing as an absent copy, so such an instance
loses its picture and says so, rather than reading as a corrupt download.

**The record follows the file, in that order.** A row still naming a file this
sweep deleted has nothing to show and should not claim otherwise, so clearing the
column is part of reclaiming rather than a tidy-up. It happens *after* the unlink,
so a crash in between leaves a row pointing at a missing file — which the next
pass finds and finishes. The other order strands bytes with nothing referencing
them, and nothing would ever reclaim those.

Deleting a preview never touches the catalogue proper. An accepted work's imagery
comes from acquisition against the source URL the catalogue holds; the preview
only ever helped someone decide.
"""

import logging
import threading
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from curation.persistence.discovery_records import CandidateImage
from curation.services.discovery import DiscoveryService
from curation.services.errors import ServiceError

log = logging.getLogger(__name__)

#: How long a shutdown waits for an in-flight sweep to notice it should stop.
#: Short because a sweep of a household catalogue is milliseconds of work, and a
#: pass that is somehow wedged must not hold a restart open.
_SHUTDOWN_JOIN_SECONDS: Final[float] = 5.0

#: What the sweep's thread is called, in `journalctl` and in a stack dump.
#:
#: A constant rather than a literal at the one place it is set, because the only
#: way to observe that this thread does not outlive the application is to look for
#: it by name — and a test written against a literal is disarmed by a rename,
#: silently and while staying green.
SWEEP_THREAD_NAME: Final[str] = "preview-sweep"


@dataclass(frozen=True, slots=True)
class SweepResult:
    """What one pass reclaimed, and what it deliberately left alone.

    `retained` is reported rather than inferred from the difference between two
    other counts: a path held back because a work is still being reviewed is the
    normal, correct outcome, and a sweep that only ever reported deletions would
    make it indistinguishable from a sweep that found nothing to consider.
    """

    #: Preview files removed from disk. Counts paths, not rows: a file two works
    #: shared is one deletion.
    deleted: int
    #: Rows whose `preview_path` was cleared. At least `deleted`, and more
    #: wherever a shared file's last references settled together.
    forgotten: int
    #: Bytes returned to the filesystem, as measured before each unlink. Zero for
    #: a file already gone, which a re-run is full of.
    bytes_reclaimed: int
    #: Paths left in place because a work still under review points at them.
    retained: int
    #: Paths whose file could not be removed. The rows keep their `preview_path`,
    #: so the next pass tries again rather than leaving a row claiming a picture
    #: that is not coming back.
    failed: int


class PreviewSweep:
    """Delete the cached previews of works that have reached a terminal verdict."""

    def __init__(self, discovery: DiscoveryService, *, art_root: Path) -> None:
        self._discovery = discovery
        #: Every `preview_path` is relative to this, as every catalogue path is.
        self._art_root = art_root

    def run(self) -> SweepResult:
        """Reclaim what is reclaimable now. Safe to call at any time, any number of times.

        Derived entirely from current state, so two passes in a row are a pass
        and a no-op rather than a pass and a mistake.
        """
        # A pass is announced before it starts as well as after it ends, so a
        # wedged one is visible. With only the closing line, a pass that never
        # returns and a plane that stopped sweeping look identical in the
        # journal — silence — and they are different faults with different fixes.
        log.debug("sweeping candidate previews", extra={"event": "preview.sweep_started"})
        deleted = forgotten = reclaimed = retained = failed = 0
        # The whole pass runs inside one transaction, so no row can appear
        # against a path *while* the pass is deciding about it: `record_image`
        # takes the same lock. That is what this closes, and it is not the whole
        # race — a writer whose file check ran before the pass started can still
        # write afterwards. The module docstring has the surviving interleaving.
        #
        # The cost is bounded by what is inside: a walk of a household's rows and
        # a handful of unlinks, single-digit milliseconds, against a plane whose
        # writers are a curator's own runs. Nothing slow is done in here — no
        # fetch, no encode — and nothing may be added.
        with self._discovery.transaction():
            referenced, decided = self._references()
            for path, images in sorted(referenced.items()):
                if any(image.candidate_work_id not in decided for image in images):
                    retained += 1
                    continue
                removed, freed = self._unlink(path)
                if not removed:
                    failed += 1
                    continue
                deleted += 1
                reclaimed += freed
                for image in images:
                    if self._forget(image):
                        forgotten += 1
        result = SweepResult(
            deleted=deleted,
            forgotten=forgotten,
            bytes_reclaimed=reclaimed,
            retained=retained,
            failed=failed,
        )
        # At INFO even when nothing was reclaimed. The interesting operational
        # question about a periodic job is whether it is running at all, and a
        # job that logs only when it acts is indistinguishable from one that
        # died — which on this plane means the SD card filling with nobody
        # having been told a sweep stopped happening.
        log.info(
            "swept candidate previews",
            extra={
                "event": "preview.swept",
                "deleted": deleted,
                "forgotten": forgotten,
                "bytes_reclaimed": reclaimed,
                "retained": retained,
                "failed": failed,
            },
        )
        return result

    def _references(self) -> tuple[dict[str, list[CandidateImage]], set[str]]:
        """Every cached preview on record, the instances pointing at it, and which
        of their works the curator has finished with.

        Walked through the service's own listings rather than a query of its own,
        because the durable store's contract is equality filters and a
        deterministic order — a join or a `WHERE preview_path IS NOT NULL` would
        widen that contract for a job that runs on a timer over a household's
        worth of rows.

        Iterating runs reaches every work exactly once: a work belongs to the
        discovery run that proposed it and keeps that id for life, so a resolve
        run — which covers works through `ResolveRunWork` rather than owning them
        — contributes an empty list rather than a second sighting.

        The verdicts come back with the walk rather than being asked for again
        per instance. The walk already holds each work, and re-reading it once
        per image would be a query per preview to answer a question already in
        hand — on the pass where nothing is reclaimable, which is most of them.
        """
        references: dict[str, list[CandidateImage]] = defaultdict(list)
        decided: set[str] = set()
        for run in self._discovery.list_runs():
            for work in self._discovery.list_candidate_works(run.id):
                if work.verdict.is_terminal:
                    decided.add(work.id)
                for image in self._discovery.list_candidate_images(work.id):
                    if image.preview_path is not None:
                        references[image.preview_path].append(image)
        return references, decided

    def _forget(self, image: CandidateImage) -> bool:
        """Clear one row's `preview_path`, reporting whether it went.

        Guarded for the reason `_unlink` is, and the asymmetry was worth closing:
        the file half tolerated a read-only mount and carried on, while a refused
        *write* would have escaped `run` and cost every path after it — with no
        `SweepResult` to say how far the pass got. A record layer that refuses one
        row is exactly as survivable as a filesystem that refuses one unlink, and
        the next pass finds the row still naming a file that is now gone.
        """
        try:
            self._discovery.forget_preview(image.id)
        except ServiceError as exc:
            log.warning(
                "a candidate preview was deleted but its record still names it",
                extra={"event": "preview.forget_failed", "candidate_image_id": image.id, "reason": str(exc)},
            )
            return False
        return True

    def _unlink(self, path: str) -> tuple[bool, int]:
        """Remove one preview, reporting whether it went and what it freed.

        A file already gone counts as removed: the state this converges on is
        "no file and no row pointing at one", and a missing file is half of it
        already. Refusing to clear the rows in that case would leave them
        claiming a picture forever.
        """
        target = self._art_root / path
        try:
            freed = target.stat().st_size
        except OSError:
            # Missing, or unreadable for the same reason the unlink below may
            # fail. The size is only ever a report, so a failure to measure must
            # not stop the reclamation it is reporting on.
            freed = 0
        try:
            target.unlink(missing_ok=True)
        except OSError as exc:
            # A read-only mount or a permissions problem. Left for the next pass
            # rather than raised: one unreclaimable file must not stop the sweep
            # reclaiming the rest, and the count says it happened.
            log.warning(
                "a candidate preview could not be deleted; its record still points at it",
                extra={"event": "preview.sweep_failed", "path": path, "reason": str(exc)},
            )
            return False, 0
        return True, freed


def run_periodically(
    sweep: PreviewSweep,
    *,
    interval_seconds: float,
    stop: threading.Event,
    after_pass: Callable[[], None] = lambda: None,
) -> None:
    """Sweep once, then every `interval_seconds`, until `stop` is set.

    Sweeping immediately rather than after the first interval, because a process
    that restarts more often than the interval would otherwise never sweep at
    all — and restarts are exactly what an SD-card-bound plane does when
    something goes wrong.

    `stop.wait` rather than `sleep`, so a shutdown does not hold the process open
    for the rest of an interval. `after_pass` is called once per completed pass,
    which is the seam a test uses to count passes and stop the loop without
    waiting out an interval.
    """
    while True:
        try:
            sweep.run()
        except Exception:  # prawduct:allow prawduct/broad-except -- a background loop that dies stops reclaiming forever
            # Logged with its traceback and the loop continues. This thread has
            # no caller to propagate to, and the failure mode of letting it die
            # is silent: the disk fills weeks later with nothing connecting the
            # two events.
            log.exception("a preview sweep failed; the next one will try again", extra={"event": "preview.sweep_error"})
        after_pass()
        if stop.wait(interval_seconds):
            return


def start_sweeping(sweep: PreviewSweep, *, interval_seconds: float) -> Callable[[], None]:
    """Run the sweep on a daemon thread, returning the call that stops it.

    A daemon thread for the reason discovery's runs use one: work in flight when
    the process stops is a designed-for event here, since the next start sweeps
    immediately and reclaims whatever this pass did not.
    """
    stop = threading.Event()
    thread = threading.Thread(
        target=run_periodically,
        args=(sweep,),
        kwargs={"interval_seconds": interval_seconds, "stop": stop},
        name=SWEEP_THREAD_NAME,
        daemon=True,
    )
    thread.start()

    def halt() -> None:
        stop.set()
        # Joined with a bound rather than indefinitely: the sweep holds no lock
        # a shutdown needs back.
        thread.join(timeout=_SHUTDOWN_JOIN_SECONDS)
        if thread.is_alive():
            # The join's own answer, which was previously discarded — leaving
            # shutdown to log that it had stopped the sweep while the sweep was
            # still running. A pass that outlasts the bound is holding the store
            # lock the next generation of services will want, so it is the one
            # thing here worth waking someone for.
            log.warning(
                "a preview sweep did not stop when asked and is still running",
                extra={"event": "preview.sweep_wedged", "waited_seconds": _SHUTDOWN_JOIN_SECONDS},
            )

    return halt
