"""Reclaiming candidate previews, and the two ways doing it wrongly loses a picture.

The sweep is the only thing that deletes files a curator might still be looking
at, so its tests are mostly about restraint: what it declines to take, and what
it leaves consistent when it stops halfway. The disk it protects is an SD card
whose exhaustion `operational-spec.md` § Risks names first, which is why "it also
actually deletes things" is the shortest test here and the rest are about the
edges.
"""

import logging
import pathlib
import threading

import pytest

from curation.persistence.discovery_records import Verdict
from curation.persistence.records import AcquisitionMethod, SourceClass
from curation.services import sweep as sweep_module
from curation.services.errors import ServiceError
from curation.services.sweep import PreviewSweep, run_periodically, start_sweeping


@pytest.fixture
def preview(settings):
    """Write a file into the preview cache and return its catalogue-relative path."""

    def _write(name: str, *, contents: bytes = b"a preview's worth of bytes") -> str:
        relative = f"previews/{name}"
        target = settings.art_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(contents)
        return relative

    return _write


@pytest.fixture
def sweep(services) -> PreviewSweep:
    """The container's own sweep, so these tests exercise the wiring a plane runs."""
    return services.sweep


@pytest.fixture
def review(services):
    """The review surface, for the two tests about what a curator is told afterwards."""
    return services.review


def decide(discovery, work, verdict=Verdict.ACCEPTED):
    """Put a work into a terminal verdict without going through acceptance.

    Rejection rather than acceptance wherever the test does not care which:
    accepting mints an artwork and promotes sources, which is a great deal of
    unrelated machinery to drag into a test about deleting a file.
    """
    return discovery.set_verdict(work.id, verdict).work


# -- what it takes, and what it refuses to ------------------------------------


def test_a_decided_works_preview_is_deleted_and_its_row_stops_claiming_one(
    discovery, sweep, propose, add_image, preview, settings
):
    work = propose("The Persistence of Memory")
    add_image(work, preview_path=preview("memory.jpg"))
    decide(discovery, work, Verdict.REJECTED)

    result = sweep.run()

    assert result.deleted == 1
    assert result.forgotten == 1
    assert not (settings.art_root / "previews/memory.jpg").exists()
    # The row follows the file. A `preview_path` naming a file this process
    # deleted is what makes a review card report a routine reclamation as a
    # corrupt download.
    assert discovery.list_candidate_images(work.id)[0].preview_path is None


def test_a_work_still_under_review_keeps_the_picture_review_shows(discovery, sweep, propose, add_image, preview, settings):
    work = propose("The Persistence of Memory")
    add_image(work, preview_path=preview("memory.jpg"))

    result = sweep.run()

    assert result.deleted == 0
    assert result.retained == 1, "reported, not merely absent from the deletions"
    assert (settings.art_root / "previews/memory.jpg").exists()
    assert discovery.list_candidate_images(work.id)[0].preview_path == "previews/memory.jpg"


def test_a_work_awaiting_a_better_image_is_not_decided_and_keeps_its_previews(
    discovery, sweep, propose, add_image, preview, settings
):
    """The verdict that reads like a conclusion and is not one.

    `awaiting_better_image` is the state a curator reaches by turning a scan
    down, and the work is still wanted — a re-search is what it is waiting for.
    Sweeping it would delete the previews of the alternates they are choosing
    between, which is the state in which the pictures matter most.
    """
    work = propose("The Persistence of Memory")
    first = add_image(work, url="https://museum.example/one", preview_path=preview("one.jpg"))
    add_image(work, url="https://museum.example/two", preview_path=preview("two.jpg"))
    discovery.reject_image(first.id)
    assert discovery.get_candidate_work(work.id).verdict is Verdict.AWAITING_BETTER_IMAGE

    result = sweep.run()

    assert result.deleted == 0
    assert result.retained == 2
    assert (settings.art_root / "previews/two.jpg").exists()


def test_a_rejected_instance_of_a_decided_work_is_swept_like_any_other(discovery, sweep, propose, add_image, preview, settings):
    """Suppression is about re-selection, not about the file.

    A rejected scan stays on the card as the evidence of a judgement while the
    work is live. Once the work is decided nobody is judging it, and keeping its
    bytes would make a rejected instance the one thing on the plane that is never
    reclaimed.
    """
    work = propose("The Persistence of Memory")
    turned_down = add_image(work, url="https://museum.example/one", preview_path=preview("one.jpg"))
    add_image(work, url="https://museum.example/two", preview_path=preview("two.jpg"))
    discovery.reject_image(turned_down.id)
    decide(discovery, work, Verdict.REJECTED)

    result = sweep.run()

    assert result.deleted == 2
    assert result.forgotten == 2
    assert list((settings.art_root / "previews").iterdir()) == []


# -- one file, two works ------------------------------------------------------


def test_a_preview_two_works_share_survives_while_either_is_under_review(discovery, sweep, propose, add_image, preview, settings):
    """The failure the path-shaped unit exists to prevent.

    Preview files are named by a digest of their URL, so the same museum scan
    proposed for two candidate works is two rows over one file — which is
    ordinary when phase 1 names one painting twice. Deleting on the first
    work's verdict takes the picture out from under a work still being judged,
    and the review card then reports the file as unreadable when in fact this
    process removed it.
    """
    shared = preview("shared.jpg")
    decided = propose("The Persistence of Memory", dedup_key="memory")
    live = propose("The Persistence of Memory (again)", dedup_key="memory-again")
    add_image(decided, url="https://museum.example/shared", preview_path=shared)
    add_image(live, url="https://museum.example/shared", preview_path=shared)
    decide(discovery, decided, Verdict.ACCEPTED)

    result = sweep.run()

    assert result.deleted == 0
    assert result.retained == 1, "one path held back, not two rows"
    assert (settings.art_root / shared).exists()
    # And the decided work keeps its path too, because the file is still there:
    # a row cleared here would report no local copy for a picture on disk.
    assert discovery.list_candidate_images(decided.id)[0].preview_path == shared


def test_a_shared_preview_goes_when_the_last_work_holding_it_is_decided(discovery, sweep, propose, add_image, preview, settings):
    shared = preview("shared.jpg")
    first = propose("The Persistence of Memory", dedup_key="memory")
    second = propose("The Persistence of Memory (again)", dedup_key="memory-again")
    add_image(first, url="https://museum.example/shared", preview_path=shared)
    add_image(second, url="https://museum.example/shared", preview_path=shared)
    decide(discovery, first, Verdict.ACCEPTED)
    decide(discovery, second, Verdict.REJECTED)

    result = sweep.run()

    assert result.deleted == 1, "one file"
    assert result.forgotten == 2, "two rows pointing at it"
    assert not (settings.art_root / shared).exists()


# -- running it again ---------------------------------------------------------


def test_a_second_pass_over_the_same_catalogue_changes_nothing(discovery, sweep, propose, add_image, preview):
    work = propose("The Persistence of Memory")
    add_image(work, preview_path=preview("memory.jpg"))
    decide(discovery, work, Verdict.REJECTED)
    sweep.run()

    again = sweep.run()

    # Nothing left to consider at all: the rows no longer name a path, so the
    # second pass does not even see them. Idempotence here is the absence of a
    # second deletion *and* the absence of a retained count that would mean the
    # rows were still claiming files.
    assert (again.deleted, again.forgotten, again.retained, again.failed) == (0, 0, 0, 0)


def test_a_file_already_gone_still_clears_the_row_that_named_it(discovery, sweep, propose, add_image, preview, settings):
    """The state a crash between the unlink and the write leaves behind.

    The sweep deletes the file first so that an interruption strands a row
    rather than bytes — a stranded row is found and fixed by the next pass,
    where bytes nothing references are unreclaimable forever. That only holds
    if the next pass treats a missing file as done rather than as a problem.
    """
    work = propose("The Persistence of Memory")
    add_image(work, preview_path=preview("memory.jpg"))
    decide(discovery, work, Verdict.REJECTED)
    (settings.art_root / "previews/memory.jpg").unlink()

    result = sweep.run()

    assert result.deleted == 1
    assert result.forgotten == 1
    assert result.bytes_reclaimed == 0, "nothing was freed, and the count says so"
    assert discovery.list_candidate_images(work.id)[0].preview_path is None


def test_bytes_are_measured_before_the_file_goes(discovery, sweep, propose, add_image, preview):
    work = propose("The Persistence of Memory")
    add_image(work, preview_path=preview("memory.jpg", contents=b"x" * 4096))
    decide(discovery, work, Verdict.REJECTED)

    assert sweep.run().bytes_reclaimed == 4096


def test_a_preview_that_cannot_be_deleted_leaves_its_row_pointing_at_it(
    discovery, sweep, propose, add_image, preview, monkeypatch
):
    """A read-only mount must cost one file, not the sweep and not the record.

    The row keeps its `preview_path` on purpose: the file is still there, so a
    card that showed it would be right, and the next pass will try again. A row
    cleared here would claim no local copy of a picture sitting on disk.
    """
    work = propose("The Persistence of Memory")
    add_image(work, preview_path=preview("memory.jpg"))
    decide(discovery, work, Verdict.REJECTED)
    monkeypatch.setattr(
        "pathlib.Path.unlink",
        lambda *args, **kwargs: (_ for _ in ()).throw(PermissionError("read-only file system")),
    )

    result = sweep.run()

    assert (result.deleted, result.forgotten, result.failed) == (0, 0, 1)
    assert discovery.list_candidate_images(work.id)[0].preview_path == "previews/memory.jpg"


def test_one_unreclaimable_file_does_not_stop_the_others(discovery, sweep, propose, add_image, preview, monkeypatch):
    stubborn = preview("stubborn.jpg")
    work = propose("The Persistence of Memory")
    add_image(work, url="https://museum.example/one", preview_path=stubborn)
    add_image(work, url="https://museum.example/two", preview_path=preview("ordinary.jpg"))
    decide(discovery, work, Verdict.REJECTED)
    real_unlink = pathlib.Path.unlink

    def refuse_one(self, *args, **kwargs):
        if self.name == "stubborn.jpg":
            raise PermissionError("read-only file system")
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr("pathlib.Path.unlink", refuse_one)

    result = sweep.run()

    assert (result.deleted, result.failed) == (1, 1)


# -- works with no previews at all --------------------------------------------


def test_a_catalogue_with_nothing_cached_sweeps_to_a_clean_no_op(discovery, sweep, propose, add_image):
    work = propose("The Persistence of Memory")
    add_image(work)
    decide(discovery, work, Verdict.REJECTED)

    result = sweep.run()

    assert (result.deleted, result.forgotten, result.retained, result.failed) == (0, 0, 0, 0)


def test_an_empty_catalogue_sweeps_without_reaching_for_anything(sweep):
    assert sweep.run().deleted == 0


# -- what the curator is told afterwards ---------------------------------------


def test_a_swept_works_card_says_the_copy_was_reclaimed_not_that_none_existed(
    discovery, sweep, review, propose, add_image, preview
):
    """A decided work stays on the review surface, so its card outlives its previews.

    `run_results` splits by `resolution_status`, not by verdict, so `list_works`
    and `get_work` keep returning accepted and rejected works. Saying "no local
    copy was cached" about a preview this plane deleted on purpose is a false
    statement of history, and it points whoever asks at phase 2's caching —
    `ARTIC_USER_AGENT` unset, no preview URL, a failed fetch — rather than at the
    sweep that did it.
    """
    work = propose("The Persistence of Memory")
    add_image(work, preview_path=preview("memory.jpg"))
    decide(discovery, work, Verdict.ACCEPTED)
    sweep.run()

    note = review.list_images(work.id).instances[0].preview_note

    assert "reclaimed" in note
    assert "accepted" in note, "the verdict that reclaimed it, so the reason is not merely asserted"
    assert "was cached" not in note, "the never-cached message would send diagnosis to phase 2"


def test_a_live_work_with_no_cached_copy_still_says_none_was_cached(discovery, review, propose, add_image):
    """The other branch, which the one above must not have swallowed."""
    work = propose("The Persistence of Memory")
    add_image(work)

    note = review.list_images(work.id).instances[0].preview_note

    assert "No local copy of this image was cached" in note


def test_a_row_naming_a_file_that_is_gone_reads_as_absent_not_corrupt(discovery, review, propose, add_image, preview, settings):
    """The residual of the race the transaction narrows without closing.

    `PreviewCache.store` checks the file with no lock and `record_image` takes one
    afterwards, so a row can be written naming a file a sweep pass removed in
    between — for a work still under review, which is the case the sweep itself
    never produces. Reporting that as unreadable is the corruption message for a
    file this plane deleted on purpose, and it sends whoever asks looking for a
    bad download instead of at the sweep.
    """
    work = propose("The Persistence of Memory")
    add_image(work, preview_path=preview("memory.jpg"))
    (settings.art_root / "previews/memory.jpg").unlink()

    note = review.list_images(work.id).instances[0].preview_note

    assert "reclaimed" in note
    assert "could not be read" not in note, "the corruption message would misdirect the diagnosis"


# -- the guard on the write itself --------------------------------------------


def test_forgetting_the_preview_of_a_live_work_is_refused(discovery, propose, add_image, preview):
    """The rule enforced where it can be broken, not only where it is applied.

    The sweep decides what is reclaimable by walking works; this is the one
    write that can clear a `preview_path`, and a second caller written later
    would otherwise have to remember the rule rather than be held to it.
    """
    work = propose("The Persistence of Memory")
    image = add_image(work, preview_path=preview("memory.jpg"))

    with pytest.raises(ServiceError, match="still under review"):
        discovery.forget_preview(image.id)


def test_forgetting_a_preview_that_is_already_forgotten_is_not_an_error(discovery, propose, add_image, preview):
    work = propose("The Persistence of Memory")
    image = add_image(work, preview_path=preview("memory.jpg"))
    decide(discovery, work, Verdict.REJECTED)
    discovery.forget_preview(image.id)

    assert discovery.forget_preview(image.id).preview_path is None


def test_a_record_that_refuses_to_be_cleared_costs_one_row_and_not_the_pass(
    discovery, sweep, propose, add_image, preview, monkeypatch, settings
):
    """The error posture that held for the unlink half and not the record half.

    A read-only mount cost one file and the pass continued; a refused *write*
    escaped `run` and cost every path after it, with no `SweepResult` to say how
    far it got. A record layer that refuses one row is exactly as survivable as a
    filesystem that refuses one unlink.
    """
    stubborn = propose("The Persistence of Memory", dedup_key="memory")
    ordinary = propose("Swans Reflecting Elephants", dedup_key="swans")
    # Named so the paths sort in a known order: the pass walks them sorted, so
    # the refusal lands on the first and the assertion below is about what
    # happened *after* it.
    refused = add_image(stubborn, url="https://museum.example/one", preview_path=preview("aaa.jpg"))
    add_image(ordinary, url="https://museum.example/two", preview_path=preview("zzz.jpg"))
    decide(discovery, stubborn, Verdict.REJECTED)
    decide(discovery, ordinary, Verdict.REJECTED)
    real_forget = type(discovery).forget_preview

    def refuse_the_first(self, image_id):
        if image_id == refused.id:
            raise ServiceError("the row is held by something else")
        return real_forget(self, image_id)

    monkeypatch.setattr(type(discovery), "forget_preview", refuse_the_first)

    result = sweep.run()

    # Both files went; only the second row could be cleared. The pass reports
    # what it managed rather than dying between the two.
    assert result.deleted == 2
    assert result.forgotten == 1
    assert not (settings.art_root / "previews/zzz.jpg").exists()


def test_a_writer_cannot_land_between_the_pass_reading_rows_and_deleting_files(
    discovery, sweep, propose, add_image, preview, monkeypatch
):
    """Reading the references and unlinking are two steps, and phase 2 writes between them.

    `PreviewCache.store` hands back a digest-named file it finds on disk without
    re-fetching, so a resolve run can attach a work still under review to a path
    the pass has already judged reclaimable — and `record_image` never rewrites
    `preview_path` for a URL its work already holds, so that row would name a
    deleted file for the rest of its review life. Holding the store's lock across
    both halves is what makes the rule hold against a writer rather than only
    against the moment the sweep looked.

    Driven from inside the unlink, which is the exact instant the gap would be
    open. The negative assertion is the load-bearing one and it cannot flake into
    a false pass: a writer can only land there if the lock is *not* held. The
    positive one afterwards is what stops the test passing because the writer was
    simply broken.
    """
    shared = preview("shared.jpg")
    decided = propose("The Persistence of Memory", dedup_key="memory")
    live = propose("Swans Reflecting Elephants", dedup_key="swans")
    add_image(decided, url="https://museum.example/shared", preview_path=shared)
    decide(discovery, decided, Verdict.REJECTED)

    landed = threading.Event()
    real_unlink = pathlib.Path.unlink

    def race_the_unlink(self, *args, **kwargs):
        writer = threading.Thread(
            target=lambda: (
                discovery.record_image(
                    candidate_work_id=live.id,
                    url="https://museum.example/shared",
                    provider="artic",
                    source_class=SourceClass.INSTITUTIONAL,
                    acquisition_method=AcquisitionMethod.DEZOOMIFY,
                    confidence=0.9,
                    preview_path=shared,
                ),
                landed.set(),
            ),
            daemon=True,
        )
        writer.start()
        assert not landed.wait(timeout=0.5), "a writer attached a live work to a path being deleted"
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "unlink", race_the_unlink)

    sweep.run()

    assert landed.wait(timeout=5), "the writer was blocked rather than serialised, which is a different defect"


# -- the loop that drives it ---------------------------------------------------


class _CountingSweep:
    """Stands in for the real sweep so the loop can be tested without files."""

    def __init__(self, *, fail_on: int | None = None) -> None:
        self.passes = 0
        self._fail_on = fail_on

    def run(self):
        self.passes += 1
        if self.passes == self._fail_on:
            raise RuntimeError("the catalogue went away")
        return None


def test_the_loop_sweeps_before_it_waits():
    """A process restarting more often than the interval must still reclaim.

    The plane is on an SD card and restarts are what it does when something goes
    wrong; a loop that slept first would mean the deployments most in need of
    reclamation are the ones that never get it.
    """
    counting = _CountingSweep()
    stop = threading.Event()

    run_periodically(counting, interval_seconds=0, stop=stop, after_pass=stop.set)

    assert counting.passes == 1


def test_the_loop_keeps_going_after_a_pass_raises():
    """A background thread that dies stops reclaiming, silently and forever."""
    counting = _CountingSweep(fail_on=1)
    stop = threading.Event()

    def stop_after_two() -> None:
        if counting.passes >= 2:
            stop.set()

    run_periodically(counting, interval_seconds=0, stop=stop, after_pass=stop_after_two)

    assert counting.passes == 2, "the failure did not end the loop"


def test_shutdown_says_so_when_the_sweep_will_not_stop(monkeypatch, caplog):
    """The join's own answer, which shutdown previously discarded.

    A pass that outlasts the bound is holding the store lock the next generation
    of services will want, and the two log lines around it claim the sweep was
    started and stopped. Saying nothing here makes a wedged sweep look like a
    clean shutdown, which is the wrong diagnosis for the one fault this thread
    has that the process survives.

    The bound is monkeypatched rather than parameterised: a shutdown budget is
    not a deployment knob, and a parameter whose only caller is a test is the
    thing this repo removes when it finds one.
    """
    monkeypatch.setattr(sweep_module, "_SHUTDOWN_JOIN_SECONDS", 0.05)
    wedged = threading.Event()

    class _WedgedSweep:
        def run(self) -> None:
            wedged.wait(timeout=10)

    halt = start_sweeping(_WedgedSweep(), interval_seconds=3600)
    try:
        with caplog.at_level(logging.WARNING):
            halt()
    finally:
        wedged.set()

    assert any(record.__dict__.get("event") == "preview.sweep_wedged" for record in caplog.records)


def test_the_loop_returns_as_soon_as_it_is_asked_to_stop():
    """`stop.wait` rather than `sleep`, so a shutdown is not held for an interval."""
    counting = _CountingSweep()
    stop = threading.Event()
    stop.set()

    run_periodically(counting, interval_seconds=3600, stop=stop)

    assert counting.passes == 1, "the pass it had already started, and no wait"
