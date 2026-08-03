"""What a surface is handed, and what one call to it reaches.

The container exists so that a surface binds to the service layer rather than to
one service in it. Two things are worth pinning: that it actually carries every
concern, and that the single repair call an entry point makes reaches each
service that has one. The second is the wiring, and wiring is where a fully
tested behaviour still ends up doing nothing.
"""

import threading
from dataclasses import replace
from datetime import UTC, datetime

from curation.app import MCP_PATH, MCP_SESSION_IDLE_TIMEOUT_SECONDS, create_app
from curation.persistence.discovery_records import InitiatedBy, RunStatus, Verdict
from curation.persistence.records import Theme
from curation.services.catalogue import CatalogueService
from curation.services.discovery import DiscoveryService
from curation.services.display import DisplayService
from curation.services.sweep import SWEEP_THREAD_NAME, PreviewSweep

_A_MOMENT = datetime(2026, 7, 20, 9, 30, tzinfo=UTC)


class _SweepSpy:
    """Counts passes and lets a test wait for the first one.

    An event rather than a sleep: the sweep runs on its own thread, so a test
    that polled a counter would either be slow or flake on a loaded machine.
    """

    def __init__(self) -> None:
        self.passes = 0
        self.swept = threading.Event()

    def run(self) -> None:
        self.passes += 1
        self.swept.set()


def _sweep_threads() -> list[threading.Thread]:
    """Live threads the sweep started, found the way an operator would: by name."""
    return [thread for thread in threading.enumerate() if thread.name == SWEEP_THREAD_NAME and thread.is_alive()]


def test_the_container_carries_every_concern_a_surface_may_need(services):
    """A surface takes this, so a concern missing from it is a concern no surface can reach."""
    assert isinstance(services.catalogue, CatalogueService)
    assert isinstance(services.discovery, DiscoveryService)
    assert isinstance(services.display, DisplayService)
    assert isinstance(services.sweep, PreviewSweep)


def test_one_reconcile_call_reaches_the_display_repair(store, services):
    """An entry point calls the container once; each service's repair must run.

    Seeded through the store rather than the service, because the state being
    repaired — themes with none active — is one the service's own rules forbid it
    to create, and only a file written by an earlier revision holds it.
    """
    store.add_theme(Theme(id="t1", name="Late night", created_at=_A_MOMENT))
    store.add_theme(Theme(id="t2", name="Daylight", created_at=_A_MOMENT))

    services.reconcile()

    assert services.display.active_theme().name == "Late night"


def test_one_reconcile_call_reaches_the_discovery_repair(discovery, services):
    """The second repair, asserted through the same single call an entry point makes.

    Its own tests enter through `DiscoveryService.reconcile`, and every one of
    them passes with the container's call to it deleted — which is the shape of
    defect this file exists for: the behaviour is fine and nothing invokes it.
    """
    run = discovery.start_discovery_run(intent_text="Surrealist paintings", initiated_by=InitiatedBy.MCP_CLIENT)

    services.reconcile()

    assert discovery.get_run(run.id).status is RunStatus.INTERRUPTED


def test_the_mcp_surface_reaps_sessions_it_stops_hearing_from(services):
    """Sessions with no expiry are a growing collection with no lifecycle.

    Each holds an instance and a live task for the life of the process, on an
    always-on plane whose unit sets `MemoryMax` — so the failure mode is an
    OOM-killed unit, not a slow leak. Asserted through `create_app` because the
    value only does anything if the application actually passes it.
    """
    app = create_app(services)

    managers = [
        route.app.__closure__[0].cell_contents
        for route in app.routes
        if getattr(route, "path", None) == MCP_PATH and getattr(route, "app", None) is not None
    ]
    assert managers, "the MCP mount was not found, so this assertion would pass vacuously"
    assert managers[0].session_idle_timeout == MCP_SESSION_IDLE_TIMEOUT_SECONDS


def test_the_containers_sweep_reads_the_same_art_tree_everything_else_writes(services, discovery, propose, add_image, settings):
    """`isinstance` says the concern is present; only a real file says it is wired.

    The sweep resolves every `preview_path` against an `art_root` the container
    hands it, and a wrong one is invisible: the walk finds the rows, the unlink
    finds nothing, and the pass reports a tidy zero. Deleting a real preview
    through the container is what distinguishes wired from merely constructed.
    """
    work = propose("The Persistence of Memory")
    add_image(work, preview_path="previews/memory.jpg")
    cached = settings.art_root / "previews/memory.jpg"
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_bytes(b"a preview's worth of bytes")
    discovery.set_verdict(work.id, Verdict.REJECTED)

    assert services.sweep.run().deleted == 1
    assert not cached.exists()


async def test_the_application_sweeps_previews_while_it_is_serving(services):
    """The sweep does nothing at all unless the lifespan starts it.

    Every test of the sweep itself calls `run` directly and passes with the
    lifespan's call deleted — which is the defect this file exists for, one
    directory further along: the reclamation works perfectly and nothing ever
    invokes it, so an SD card fills with no failing test anywhere.
    """
    spy = _SweepSpy()
    app = create_app(replace(services, sweep=spy), preview_sweep_interval_seconds=3600)

    async with app.router.lifespan_context(app):
        assert spy.swept.wait(timeout=5), "the application served without ever sweeping"

    assert spy.passes >= 1


async def test_the_application_stops_sweeping_when_it_stops_serving(services):
    """A daemon thread that outlives the lifespan holds the catalogue it reads.

    The thread is a daemon, so the process can still exit — but a sweep running
    after shutdown reads a store the application is finished with, and on a
    restart-in-place it would be the *previous* generation's store.
    """
    spy = _SweepSpy()
    app = create_app(replace(services, sweep=spy), preview_sweep_interval_seconds=3600)

    async with app.router.lifespan_context(app):
        assert spy.swept.wait(timeout=5)
        # Pinned from both sides, because the assertion after the block is a
        # `not any(...)` over a name nothing else in the suite fixes: rename the
        # thread and the predicate matches nothing, `not any` is True, and the
        # test reports success while a live sweep outlives the application.
        assert _sweep_threads(), "no thread by that name was running, so the assertion below would pass vacuously"

    assert not _sweep_threads()


async def test_an_application_given_no_interval_never_sweeps(services):
    """The default is off, so constructing the app does not acquire a file-deleting thread.

    A harness that got one by default would race a reclamation it never opted
    into — a suite that accepted a work and then read its review card would fail
    intermittently, in a test about something else entirely.
    """
    spy = _SweepSpy()
    app = create_app(replace(services, sweep=spy))

    async with app.router.lifespan_context(app):
        pass

    assert spy.passes == 0
