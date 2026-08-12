"""Shared fixtures.

The server fixture starts a real uvicorn process-in-a-thread rather than
driving the ASGI app in-process. That is the point: an in-process transport
does not run the application's lifespan, and the lifespan is exactly what makes
the mounted MCP server work. A test that skipped it would pass against an
application that fails every request in production.
"""

import struct
import threading
import time
import uuid
from collections.abc import Iterator
from decimal import Decimal

import pytest
import uvicorn
from fakes import FakeEngine
from PIL import Image

from curation.acquisition.preparation import PreparationSettings
from curation.app import create_app
from curation.config import (
    CATALOGUE_FILENAME,
    DEFAULT_ACQUISITION_USER_AGENT,
    DEFAULT_DISCOVERY_APPROVAL_THRESHOLD,
    DEFAULT_DISCOVERY_MAX_OUTPUT_TOKENS,
    DEFAULT_DISCOVERY_MODEL,
    DEFAULT_DISCOVERY_SEARCH_RESULTS,
    DEFAULT_HOST,
    DEFAULT_INPUT_COST_USD_PER_MTOK,
    DEFAULT_MAT_BOTTOM_WEIGHT,
    DEFAULT_MAT_WIDTH_INCHES,
    DEFAULT_MAX_IMAGE_BYTES,
    DEFAULT_MIN_FREE_BYTES,
    DEFAULT_OFFERED_WORKS_PER_RUN,
    DEFAULT_OUTPUT_COST_USD_PER_MTOK,
    DEFAULT_PHASE1_INPUT_TOKENS,
    DEFAULT_PHASE1_OUTPUT_TOKENS,
    DEFAULT_PHASE1_SEARCH_ALLOWANCE,
    DEFAULT_PHASE2_SEARCHES_PER_WORK,
    DEFAULT_PORT,
    DEFAULT_PREVIEW_MAX_BYTES,
    DEFAULT_PREVIEW_SWEEP_INTERVAL_SECONDS,
    DEFAULT_RESOLUTION_FLOOR_INCHES,
    DEFAULT_ROTATION_INTERVAL_SECONDS,
    DEFAULT_ROTATION_SHUFFLE,
    DEFAULT_SEARCH_COST_USD,
    DEFAULT_TILE_BINARY,
    DEFAULT_TILE_MAX_PIXELS,
    DEFAULT_TILE_TIMEOUT_SECONDS,
    DEFAULT_TV_PANEL_DIAGONAL_INCHES,
    DEFAULT_TV_PANEL_HEIGHT_PX,
    DEFAULT_TV_PANEL_WIDTH_PX,
    Settings,
)
from curation.manifest.builder import MANIFEST_FILENAME
from curation.manifest.heartbeat import HEARTBEAT_FILENAME
from curation.persistence.discovery_records import DiscoveryRun, InitiatedBy
from curation.persistence.durable import SqliteDurableStore
from curation.persistence.file import open_catalogue_file
from curation.persistence.records import (
    AcquisitionMethod,
    FetchStatus,
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
from curation.services.runner import DiscoveryRunner
from curation.services.thumbnails import ThumbnailService, ThumbnailSettings

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
def settings(tmp_path) -> Settings:
    """The deployment values a test runs against, over a scratch art tree.

    Constructed rather than read from the environment: `Settings.from_env`
    resolves a real `.env` from the config module's own directory upward, so a
    test that went through it would run against whatever the developer's machine
    happens to hold — and would pass or fail depending on it. (That is true of
    every name the environment does not already carry, and stayed true when the
    2026-08-05 precedence fix stopped the file beating names it does.) Every
    value here is the shipped default, so a test's geometry is the geometry a
    fresh deployment gets.
    """
    return Settings(
        art_root=tmp_path,
        catalogue_path=tmp_path / CATALOGUE_FILENAME,
        manifest_path=tmp_path / MANIFEST_FILENAME,
        heartbeat_path=tmp_path / HEARTBEAT_FILENAME,
        host=DEFAULT_HOST,
        port=DEFAULT_PORT,
        acquisition_user_agent=DEFAULT_ACQUISITION_USER_AGENT,
        tile_binary=DEFAULT_TILE_BINARY,
        tile_max_pixels=DEFAULT_TILE_MAX_PIXELS,
        tile_timeout_seconds=DEFAULT_TILE_TIMEOUT_SECONDS,
        max_image_bytes=DEFAULT_MAX_IMAGE_BYTES,
        min_free_bytes=DEFAULT_MIN_FREE_BYTES,
        preview_max_bytes=DEFAULT_PREVIEW_MAX_BYTES,
        rotation_interval_seconds=DEFAULT_ROTATION_INTERVAL_SECONDS,
        rotation_shuffle=DEFAULT_ROTATION_SHUFFLE,
        preview_sweep_interval_seconds=DEFAULT_PREVIEW_SWEEP_INTERVAL_SECONDS,
        tv_panel_width_px=DEFAULT_TV_PANEL_WIDTH_PX,
        tv_panel_height_px=DEFAULT_TV_PANEL_HEIGHT_PX,
        tv_panel_diagonal_inches=DEFAULT_TV_PANEL_DIAGONAL_INCHES,
        mat_width_inches=DEFAULT_MAT_WIDTH_INCHES,
        mat_bottom_weight=DEFAULT_MAT_BOTTOM_WEIGHT,
        resolution_floor_inches=DEFAULT_RESOLUTION_FLOOR_INCHES,
        approval_threshold=DEFAULT_DISCOVERY_APPROVAL_THRESHOLD,
        phase1_search_allowance=DEFAULT_PHASE1_SEARCH_ALLOWANCE,
        phase2_searches_per_work=DEFAULT_PHASE2_SEARCHES_PER_WORK,
        offered_works_per_run=DEFAULT_OFFERED_WORKS_PER_RUN,
        search_cost_usd=Decimal(DEFAULT_SEARCH_COST_USD),
        input_cost_usd_per_mtok=Decimal(DEFAULT_INPUT_COST_USD_PER_MTOK),
        output_cost_usd_per_mtok=Decimal(DEFAULT_OUTPUT_COST_USD_PER_MTOK),
        phase1_input_tokens=DEFAULT_PHASE1_INPUT_TOKENS,
        phase1_output_tokens=DEFAULT_PHASE1_OUTPUT_TOKENS,
        discovery_model=DEFAULT_DISCOVERY_MODEL,
        discovery_max_output_tokens=DEFAULT_DISCOVERY_MAX_OUTPUT_TOKENS,
        discovery_search_results=DEFAULT_DISCOVERY_SEARCH_RESULTS,
        # No key, which is the shipped default and the only safe one here: a
        # fixture holding a real one would let a test reach the paid API by
        # accident, and the suite is meant to be free.
        openrouter_api_key=None,
    )


@pytest.fixture
def wall(settings: Settings) -> WallSettings:
    """A manifest destination of this test's own, and the shipped rotation defaults."""
    return WallSettings(
        manifest_path=settings.manifest_path,
        heartbeat_path=settings.heartbeat_path,
        rotation_interval_seconds=settings.rotation_interval_seconds,
        shuffle=settings.rotation_shuffle,
    )


@pytest.fixture
def thumbnail_settings(settings: Settings) -> ThumbnailSettings:
    """A thumbnail cache inside this test's own art tree."""
    return ThumbnailSettings(art_root=settings.art_root, directory=settings.thumbnails_path)


@pytest.fixture
def engine() -> FakeEngine:
    """The discovery engine every test runs against, in its default mood.

    Overridable by a test that needs a different answer: reassigning its fields
    before the run starts is what selects a failure, a refusal, or a work list of
    a particular size.
    """
    return FakeEngine()


@pytest.fixture
def services(
    store: SqliteCatalogue,
    discovery_store: SqliteDiscovery,
    wall: WallSettings,
    thumbnail_settings: ThumbnailSettings,
    settings: Settings,
    engine: FakeEngine,
) -> Services:
    """Every service, wired the way the entry point wires them."""
    bound = Services.bind(
        catalogue=store,
        discovery=discovery_store,
        wall=wall,
        thumbnails=thumbnail_settings,
        # Derived by the same property the entry point calls, so a test never
        # asserts against a box a real deployment would not produce.
        artwork_box=settings.tv_artwork_box,
        engine=engine,
        discovery_settings=settings.discovery_settings,
        # Panel and box from the same resolved settings, as the entry point does
        # it. Letting the panel default while passing a box derived from these
        # settings is the one way the canvas and the mat can disagree about where
        # the mat ends, and a test wired that way would assert against geometry no
        # deployment produces.
        preparation=PreparationSettings(
            art_root=settings.art_root,
            ready_path=settings.ready_path,
            panel_width=settings.tv_panel_width_px,
            panel_height=settings.tv_panel_height_px,
            box=settings.tv_artwork_box,
        ),
        # A museum source records the object's page; the tile fetcher needs the
        # image service, and only the provider can say where that is. Wired here
        # even though these tests configure no image *search*, because a catalogue
        # holding artic works and a deployment able to fetch them is a real
        # arrangement — and without it every such fetch refuses before reaching
        # the code the test is about.
        tile_targets={"artic": lambda url: f"https://www.artic.edu/iiif/2/{abs(hash(url)) % 100000}"},
        # Stated rather than looked up, for every test that reaches acquisition. A
        # suite whose job is to be green cannot depend on the network — pyproject
        # says so and deselects the tests that deliberately do. Without this the
        # fetch policy resolves real hostnames, so a machine with no DNS fails tests
        # about wiring, and one with hostile DNS could pass them for the wrong reason.
        #
        # Passed through the container rather than assigned onto the built service.
        # It was `bound.acquisition._resolve = …` until 2026-08-04, and a private
        # attribute written from outside is a guard that disarms in silence: rename
        # it and every acquisition test starts resolving real hostnames again with
        # nothing failing to say so.
        resolve=lambda _host: ["93.184.216.34"],
    )
    return bound


@pytest.fixture
def thumbnails(services: Services) -> ThumbnailService:
    return services.thumbnails


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
def runner(services: Services, engine: FakeEngine, settings: Settings) -> DiscoveryRunner:
    """A runner that does phase 1 on the calling thread.

    The shipped runner hands phase 1 to a worker so that `start` can return a
    handle at once. That is the right behaviour and the wrong one to unit-test
    against: a test asserting on what phase 1 wrote would have to wait for it,
    and "wait for a thread" is how a suite acquires flakes. The threaded path is
    exercised where it matters, through a real server over real HTTP.
    """
    return DiscoveryRunner(services.discovery, engine, settings.discovery_settings, spawn=lambda work: work())


@pytest.fixture
def ready_work(service: CatalogueService):
    """A work with everything catalogue readiness asks for, and nothing more.

    A factory rather than a fixture row: the readiness tests each remove exactly
    one of the four requirements, and the missing one is the point. It lives here
    rather than beside them because anything that puts a work on the wall — a
    manifest entry, a directive pin — needs a work that can actually be shown.
    """

    def _ready(
        title="Nighthawks", *, artist_id=None, original=True, rendition=True, mat=True, content_hash="hash-1", commentary=None
    ):
        work = service.add_artwork(
            title=title, artist_id=artist_id, date_created="1942", medium="Oil on canvas", commentary=commentary
        )
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
                fetch_status=FetchStatus.OK,
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
    """A real HTTP server on an ephemeral port, serving the real application.

    **uvicorn is asked for port 0 and the port is read back from the socket it
    actually bound.** The obvious alternative — claim a port from the OS, close
    it, and hand uvicorn the number — has a window between the close and
    uvicorn's bind in which anything else on the machine can take it. That window
    is nearly harmless when one suite runs alone and is a live race the moment
    tests run in parallel, because every worker boots servers continuously and
    they draw from the same ephemeral range. Reading the port back is a little
    more to know about uvicorn and has no window at all.
    """
    app = create_app(services)
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + 20
    while not server.started:
        if time.monotonic() > deadline:
            server.should_exit = True
            pytest.fail("the curation server did not start within 20 seconds")
        time.sleep(0.02)

    # Only valid once `started` is set — that is what puts the bound sockets on
    # the server — which is why this reads after the wait rather than beside the
    # config above.
    port = server.servers[0].sockets[0].getsockname()[1]

    try:
        yield f"http://{config.host}:{port}"
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


@pytest.fixture
def decodable_jpeg():
    """Write a JPEG that can actually be opened and resized.

    Distinct from `jpeg`, which writes valid segment headers around no image
    data. That is the right fixture for a reader that only measures, and the
    wrong one for anything that decodes: a thumbnail made from it would fail, and
    the failure would be the fixture's rather than the code's.
    """

    def _write(path, *, width=1600, height=1200, color=(88, 72, 140)):
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (width, height), color).save(path, format="JPEG", quality=90)
        return path

    return _write


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
