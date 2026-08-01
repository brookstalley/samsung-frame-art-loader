"""Shared fixtures.

The server fixture starts a real uvicorn process-in-a-thread rather than
driving the ASGI app in-process. That is the point: an in-process transport
does not run the application's lifespan, and the lifespan is exactly what makes
the mounted MCP server work. A test that skipped it would pass against an
application that fails every request in production.
"""

import socket
import threading
import time
import uuid
from collections.abc import Iterator

import pytest
import uvicorn

from curation.app import create_app
from curation.persistence.discovery_records import DiscoveryRun, InitiatedBy
from curation.persistence.durable import SqliteDurableStore
from curation.persistence.file import open_catalogue_file
from curation.persistence.records import AcquisitionMethod, SourceClass
from curation.persistence.sqlite import SqliteCatalogue
from curation.persistence.sqlite_discovery import SqliteDiscovery
from curation.services.catalogue import CatalogueService
from curation.services.container import Services
from curation.services.discovery import DiscoveryService
from curation.services.display import DisplayService

_SEEDED_TITLES = ("I Saw the Figure 5 in Gold", "Nighthawks", "The Persistence of Memory")


@pytest.fixture
def seeded_titles() -> tuple[str, ...]:
    """What `seeded_service` holds, for tests that assert against the set."""
    return _SEEDED_TITLES


@pytest.fixture
def catalogue_file(tmp_path) -> Iterator[SqliteDurableStore]:
    """An empty catalogue file, with every table both adapters read."""
    opened = open_catalogue_file(tmp_path / "catalogue.sqlite")
    yield opened
    opened.close()


@pytest.fixture
def store(catalogue_file: SqliteDurableStore) -> SqliteCatalogue:
    return SqliteCatalogue(catalogue_file)


@pytest.fixture
def discovery_store(catalogue_file: SqliteDurableStore) -> SqliteDiscovery:
    return SqliteDiscovery(catalogue_file)


@pytest.fixture
def services(store: SqliteCatalogue, discovery_store: SqliteDiscovery) -> Services:
    """Every service, wired the way the entry point wires them."""
    return Services.bind(catalogue=store, discovery=discovery_store)


@pytest.fixture
def service(services: Services) -> CatalogueService:
    return services.catalogue


@pytest.fixture
def discovery(services: Services) -> DiscoveryService:
    return services.discovery


@pytest.fixture
def display(services: Services) -> DisplayService:
    return services.display


@pytest.fixture
def seeded_service(service: CatalogueService) -> CatalogueService:
    """Three works by two artists, plus one unattributed."""
    demuth = service.add_artist(name="Charles Demuth", nationality="American", born=1883, died=1935)
    dali = service.add_artist(name="Salvador Dalí", nationality="Spanish", born=1904, died=1989)
    service.add_artwork(
        title="I Saw the Figure 5 in Gold",
        artist_id=demuth.id,
        date_created="1928",
        medium="Oil, graphite, ink and gold leaf on paperboard",
    )
    service.add_artwork(title="The Persistence of Memory", artist_id=dali.id, date_created="1931")
    service.add_artwork(title="Nighthawks", date_created="1942")
    return service


@pytest.fixture
def server_url(services: Services, seeded_service: CatalogueService) -> Iterator[str]:
    """A real HTTP server on an ephemeral port, serving the real application."""
    app = create_app(services)
    config = uvicorn.Config(app, host="127.0.0.1", port=_free_port(), log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + 20
    while not server.started:
        if time.monotonic() > deadline:
            server.should_exit = True
            pytest.fail("the curation server did not start within 20 seconds")
        time.sleep(0.02)

    try:
        yield f"http://{config.host}:{config.port}"
    finally:
        server.should_exit = True
        thread.join(timeout=20)


def _free_port() -> int:
    """Claim a port from the OS and hand it straight to uvicorn.

    uvicorn can bind port 0 itself, but then the chosen port is only readable
    through its internal socket list. Asking first is less to know about.
    """
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture
def run(discovery: DiscoveryService) -> DiscoveryRun:
    """A discovery run at phase 1, which is where every proposal is made."""
    return discovery.start_discovery_run(intent_text="Surrealist paintings", initiated_by=InitiatedBy.MCP_CLIENT)


@pytest.fixture
def propose(discovery: DiscoveryService, run: DiscoveryRun):
    """Propose a work with everything the pipeline requires and nothing more.

    A factory rather than a fixed row: almost every test needs one work in a
    particular state, and threading four required arguments through each of them
    buries the one field the test is actually about.
    """

    def _propose(title="The Persistence of Memory", *, run_id=None, dedup_key=None, **fields):
        return discovery.propose_work(
            run_id=run_id or run.id,
            proposed_title=title,
            rationale="The intent asked for Surrealism and this is its best-known example.",
            work_dedup_key=dedup_key or title.lower(),
            **fields,
        )

    return _propose


@pytest.fixture
def add_image(discovery: DiscoveryService):
    """Record one image instance for a work, defaulting everything the test does not name."""

    def _add(work, *, url=None, confidence=0.9, **fields):
        return discovery.record_image(
            candidate_work_id=work.id,
            url=url or f"https://museum.example/{uuid.uuid4()}",
            provider="artic",
            source_class=SourceClass.INSTITUTIONAL,
            acquisition_method=AcquisitionMethod.DEZOOMIFY,
            confidence=confidence,
            **fields,
        )

    return _add


@pytest.fixture
def resolved_work(discovery: DiscoveryService, propose, add_image):
    """A proposed work with one image found for it — the state review starts from."""

    def _resolved(title="The Persistence of Memory", **fields):
        work = propose(title, **fields)
        add_image(work)
        return discovery.record_resolution(work.id).work

    return _resolved
