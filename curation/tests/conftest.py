"""Shared fixtures.

The server fixture starts a real uvicorn process-in-a-thread rather than
driving the ASGI app in-process. That is the point: an in-process transport
does not run the application's lifespan, and the lifespan is exactly what makes
the mounted MCP server work. A test that skipped it would pass against an
application that fails every request in production.
"""

import socket
import struct
import threading
import time
import uuid
from collections.abc import Iterator

import pytest
import uvicorn

from curation.app import create_app
from curation.config import DEFAULT_ROTATION_INTERVAL_SECONDS, DEFAULT_ROTATION_SHUFFLE
from curation.manifest.builder import MANIFEST_FILENAME
from curation.manifest.heartbeat import HEARTBEAT_FILENAME
from curation.persistence.discovery_records import DiscoveryRun, InitiatedBy
from curation.persistence.durable import SqliteDurableStore
from curation.persistence.file import open_catalogue_file
from curation.persistence.records import (
    AcquisitionMethod,
    MatMethod,
    RenditionKind,
    RightsStatus,
    SourceClass,
)
from curation.persistence.sqlite import SqliteCatalogue
from curation.persistence.sqlite_discovery import SqliteDiscovery
from curation.services.catalogue import CatalogueService
from curation.services.container import Services
from curation.services.discovery import DiscoveryService
from curation.services.display import DisplayService, WallSettings

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
def wall(tmp_path) -> WallSettings:
    """A manifest destination of this test's own, and the shipped rotation defaults."""
    return WallSettings(
        manifest_path=tmp_path / MANIFEST_FILENAME,
        heartbeat_path=tmp_path / HEARTBEAT_FILENAME,
        rotation_interval_seconds=DEFAULT_ROTATION_INTERVAL_SECONDS,
        shuffle=DEFAULT_ROTATION_SHUFFLE,
    )


@pytest.fixture
def services(store: SqliteCatalogue, discovery_store: SqliteDiscovery, wall: WallSettings) -> Services:
    """Every service, wired the way the entry point wires them."""
    return Services.bind(catalogue=store, discovery=discovery_store, wall=wall)


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
def ready_work(service: CatalogueService):
    """A work with everything catalogue readiness asks for, and nothing more.

    A factory rather than a fixture row: the readiness tests each remove exactly
    one of the four requirements, and the missing one is the point. It lives here
    rather than beside them because anything that puts a work on the wall — a
    manifest entry, a directive pin — needs a work that can actually be shown.
    """

    def _ready(title="Nighthawks", *, artist_id=None, original=True, rendition=True, mat=True, content_hash="hash-1"):
        work = service.add_artwork(title=title, artist_id=artist_id, date_created="1942", medium="Oil on canvas")
        source = service.add_source(
            artwork_id=work.id,
            url=f"https://museum.example/{work.id}",
            provider="artic",
            source_class=SourceClass.INSTITUTIONAL,
            acquisition_method=AcquisitionMethod.DEZOOMIFY,
            rights_status=RightsStatus.PUBLIC_DOMAIN,
            is_primary=True,
        )
        if original:
            service.record_original(
                artwork_id=work.id,
                source_id=source.id,
                path=f"raw/{work.id}.tif",
                width=6000,
                height=4000,
                byte_size=90_000_000,
                content_hash=content_hash,
            )
        if mat:
            service.record_mat_color(artwork_id=work.id, hex_rgb="#27285b", method=MatMethod.VISION_MODEL)
        if rendition and original:
            service.record_rendition(
                artwork_id=work.id,
                kind=RenditionKind.TV_DISPLAY,
                target_width=3840,
                target_height=2160,
                path=f"ready/{work.id}.jpg",
            )
        return work

    return _ready


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


def jpeg_bytes(width: int = 6000, height: int = 4000) -> bytes:
    """A JPEG segment stream stating `width` x `height`, valid as far as it goes.

    Deliberately not a decodable image. The seeder reads segment headers and
    never decodes one, so a real frame header behind the segments that normally
    precede it exercises the whole of what it does — in particular the
    length-skipping, which a reader can get wrong by a byte and still appear to
    work.

    The reader was separately checked against the 41 masters of the real corpus
    on 2026-08-01: every one of its measurements matched the size the 2024 index
    recorded for that file.
    """
    identification = b"JFIF\x00\x01\x02\x00\x00\x01\x00\x01\x00\x00"
    quantisation = bytes([0]) + bytes(range(1, 65))
    frame = bytes([8]) + struct.pack(">HH", height, width) + bytes([1, 1, 0x11, 0])
    return b"".join(
        [
            b"\xff\xd8",
            b"\xff\xe0",
            struct.pack(">H", len(identification) + 2),
            identification,
            b"\xff\xdb",
            struct.pack(">H", len(quantisation) + 2),
            quantisation,
            b"\xff\xc0",
            struct.pack(">H", len(frame) + 2),
            frame,
            b"\xff\xd9",
        ]
    )


@pytest.fixture
def jpeg():
    """Write a JPEG of a given size to a path, making its directory as needed."""

    def _write(path, *, width=6000, height=4000):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(jpeg_bytes(width, height))
        return path

    return _write


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
