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
from collections.abc import Iterator

import pytest
import uvicorn

from curation.app import create_app
from curation.persistence.sqlite import SqliteCatalogue
from curation.services.catalogue import CatalogueService
from curation.services.container import Services

_SEEDED_TITLES = ("I Saw the Figure 5 in Gold", "Nighthawks", "The Persistence of Memory")


@pytest.fixture
def seeded_titles() -> tuple[str, ...]:
    """What `seeded_service` holds, for tests that assert against the set."""
    return _SEEDED_TITLES


@pytest.fixture
def store(tmp_path) -> Iterator[SqliteCatalogue]:
    """An empty catalogue on a scratch file."""
    catalogue = SqliteCatalogue(tmp_path / "catalogue.sqlite")
    yield catalogue
    catalogue.close()


@pytest.fixture
def services(store: SqliteCatalogue) -> Services:
    """Every service, wired the way the entry point wires them."""
    return Services.bind(catalogue=store)


@pytest.fixture
def service(services: Services) -> CatalogueService:
    return services.catalogue


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
