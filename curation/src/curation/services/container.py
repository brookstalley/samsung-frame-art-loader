"""The services a surface is handed, and how they relate to each other.

Operation logic is split by concern rather than gathered into one class: the
catalogue owns works already accepted, discovery owns everything before
acceptance, and display owns what reaches the wall — themes, the standing
directive, and the manifest built from them. A surface takes this container
rather than any single service, so adding a concern changes the wiring here and
nothing in `create_app` or in an MCP binding — which is what keeps a surface from
quietly binding to one service and becoming the reason a second one is awkward to
add.

How the services relate is decided here, once. Both discovery and display hold
the catalogue, and neither is held by it: acceptance is a promotion *into* the
catalogue, and a theme is a grouping *of* catalogue works. Both directions are
facts about the product rather than conveniences of one call site, which is why
they are settled in one place instead of per constructor.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from curation.acquisition.direct import StreamOpener
from curation.acquisition.mat import MatEngine
from curation.acquisition.preparation import PreparationService, PreparationSettings
from curation.acquisition.service import AcquisitionService, AcquisitionSettings
from curation.acquisition.tiles import TileTargetResolver
from curation.acquisition.transport import no_transport
from curation.acquisition.urls import Resolver

# Module scope, and the three `_default_*` helpers below used to import this at
# function scope instead, explained as breaking a cycle: "config reads this
# package to compose its settings objects". It does not. `curation.config`
# imports `manifest.builder`, `manifest.heartbeat`, `services.display_fit` and
# `services.runner`, and none of those reaches this module — `services/__init__`
# is a docstring. The deferral hid container→config from anything reading the
# import graph while teaching a pattern on a premise that was never true. If a
# real cycle ever appears, the fix is to move the constants, not to hide the edge.
from curation.config import (
    DEFAULT_ACQUISITION_USER_AGENT,
    DEFAULT_MAT_IMAGE_MAX_EDGE,
    DEFAULT_MAX_IMAGE_BYTES,
    DEFAULT_MIN_FREE_BYTES,
    DEFAULT_TILE_BINARY,
    DEFAULT_TILE_MAX_PIXELS,
    DEFAULT_TILE_TIMEOUT_SECONDS,
    DEFAULT_TV_PANEL_HEIGHT_PX,
    DEFAULT_TV_PANEL_WIDTH_PX,
    ORIGINALS_DIRNAME,
    READY_DIRNAME,
    TILE_CACHE_DIRNAME,
)
from curation.discovery.browse import CollectionBrowse
from curation.discovery.engine import DiscoveryEngine
from curation.discovery.images import ImageSearch
from curation.discovery.phase_two import PhaseTwoEngine
from curation.persistence.backup import BACKUP_RECEIPT_FILENAME
from curation.persistence.catalogue import CatalogueStore
from curation.persistence.discovery import DiscoveryStore
from curation.services.catalogue import CatalogueService
from curation.services.discovery import DiscoveryService
from curation.services.display import DisplayService, WallSettings
from curation.services.display_fit import ArtworkBox
from curation.services.errors import ServiceError
from curation.services.health import HealthService
from curation.services.previews import PreviewCache, PreviewSettings
from curation.services.review import ReviewService
from curation.services.runner import DiscoveryRunner, DiscoverySettings
from curation.services.survey import SurveyService
from curation.services.sweep import PreviewSweep
from curation.services.thumbnails import ThumbnailService, ThumbnailSettings


@dataclass(frozen=True, slots=True)
class Services:
    """Every service the curation plane offers, assembled over one open file."""

    catalogue: CatalogueService
    discovery: DiscoveryService
    display: DisplayService
    thumbnails: ThumbnailService
    #: Works composed the way a surface showing them to a human needs them. It is
    #: its own concern rather than a method on the catalogue because it spans
    #: three of them, and because both surfaces need the identical composition —
    #: which is the same reason the service layer exists at all.
    survey: SurveyService
    #: The same composition on the other side of acceptance: proposed works and
    #: the instances found for them, each with the size it would render at and a
    #: picture small enough to travel. Separate from `survey` because they read
    #: different entities entirely — one the catalogue, one the pipeline — and a
    #: single service spanning both would hold the catalogue and discovery stores
    #: at once for no shared logic.
    review: ReviewService
    #: Everything the health panel states, gathered in one call. Its own concern
    #: rather than a composite the handler assembles, because the panel is the
    #: product's only alerting surface and "which signals does it make" is a
    #: product rule — one that belongs where it can be tested without HTTP, and
    #: where the next signal is added in one place rather than two.
    health: HealthService
    #: Running a discovery run, as distinct from recording one. It sits above
    #: `discovery` rather than inside it because the record layer is deliberately
    #: synchronous and knows nothing of processes, and everything about starting
    #: work behind a handle does.
    runner: DiscoveryRunner
    #: Reclaiming the previews of works the curator has decided. Built
    #: unconditionally, unlike the phase-2 pair it cleans up after: a deployment
    #: that never cached a preview has nothing to sweep, and the pass costs one
    #: walk of a household's rows to find that out. An optional here would mean
    #: a deployment could disable phase 2, keep the files it already wrote, and
    #: lose the only thing that reclaims them.
    sweep: PreviewSweep
    #: Acquiring the master image a work was accepted for. Held beside the
    #: catalogue rather than inside it because it is the one service that reaches
    #: outside the machine to do its job — a subprocess and an HTTP transport —
    #: and the record layer is deliberately free of both.
    acquisition: AcquisitionService
    #: Turning a held original into a mat and a television canvas. Its own service
    #: rather than the tail of acquisition: a work is prepared repeatedly over its
    #: life — whenever the panel changes, the mat is re-chosen, or a rendition
    #: goes stale — while it is acquired once. Folding the two together would make
    #: every re-render look like a re-fetch to whatever reads the journal.
    preparation: PreparationService

    @classmethod
    def bind(
        cls,
        *,
        catalogue: CatalogueStore,
        discovery: DiscoveryStore,
        wall: WallSettings,
        thumbnails: ThumbnailSettings,
        artwork_box: ArtworkBox,
        engine: DiscoveryEngine,
        discovery_settings: DiscoverySettings,
        image_search: ImageSearch | None = None,
        collection: CollectionBrowse | None = None,
        previews: PreviewSettings | None = None,
        acquisition: AcquisitionSettings | None = None,
        open_stream: StreamOpener | None = None,
        tile_targets: Mapping[str, TileTargetResolver] | None = None,
        #: How a hostname becomes addresses for the fetch policy. Defaults to the
        #: system resolver, which is what a deployment wants and what a test suite
        #: must not have — a suite whose job is to be green cannot depend on DNS.
        #: Exposed here rather than left to whoever knows the attribute name: a
        #: caller reaching past this to write `acquisition._resolve` gets no error
        #: when the attribute is renamed, it just silently resolves for real again.
        resolve: Resolver | None = None,
        preparation: PreparationSettings | None = None,
        mat_engine: MatEngine | None = None,
    ) -> Services:
        """Assemble the services over an already-open file.

        The engines are injected rather than constructed here for the reason
        every foreign dependency is: a container that built its own model client
        or museum client would make "run the service layer without touching a
        foreign API" impossible to arrange, and that is the arrangement most of
        this product's tests need.

        `image_search` and `previews` are optional together. Without them the
        plane runs phase 1 and stops, which is a coherent deployment — and the
        one every test that has no business reaching a museum uses.
        """
        catalogue_service = CatalogueService(catalogue)
        display_service = DisplayService(catalogue, catalogue_service, wall)
        thumbnail_service = ThumbnailService(catalogue_service, thumbnails)
        # The artwork box reaches discovery for one reason: automatic selection
        # must withhold an instance that would render below the floor, and the
        # floor is a size on the wall rather than a pixel count — so the rule
        # cannot be evaluated without the panel geometry that converts one to the
        # other.
        discovery_service = DiscoveryService(discovery, catalogue_service, artwork_box)
        if (image_search is None) != (previews is None):
            # Refused here rather than defaulted, because either half alone is a
            # misconfiguration that would otherwise disable phase 2 silently —
            # and a deployment that meant to enable it would see runs stop at
            # `resolving_images` with nothing saying why.
            raise ServiceError(
                "Phase 2 needs both an image provider and a preview directory, or neither. A deployment "
                "selects both with ARTIC_USER_AGENT — the preview directory is derived from ART_ROOT, so "
                "passing one of these without the other is a wiring mistake rather than a configuration one."
            )
        return cls(
            catalogue=catalogue_service,
            discovery=discovery_service,
            display=display_service,
            thumbnails=thumbnail_service,
            survey=SurveyService(catalogue_service, display_service, thumbnail_service, artwork_box),
            # `art_root` is read off the thumbnail settings rather than taken as
            # an argument of its own. It is the same deployment value — every
            # catalogue path is relative to it — and it is already required and
            # validated there. A third copy would be a third chance for the
            # copies to disagree, and nothing would notice which was right.
            review=ReviewService(discovery_service, box=artwork_box, art_root=thumbnails.art_root),
            # The receipt is located the same way, and for the same reason. It is
            # not a `WallSettings` field beside the heartbeat's path: that
            # settings object carries what the *wall's* operations need, and the
            # backup is this plane's own business rather than the display plane's.
            health=HealthService(
                display_service,
                backup_receipt_path=thumbnails.art_root / BACKUP_RECEIPT_FILENAME,
                box=artwork_box,
            ),
            runner=DiscoveryRunner(
                discovery_service,
                engine,
                discovery_settings,
                images=None if image_search is None else PhaseTwoEngine(image_search, box=artwork_box),
                previews=None if image_search is None or previews is None else PreviewCache(previews, image_search.fetch_preview),
                # Independent of the phase-2 pair: a deployment may resolve
                # images without supplementing, and a run with no collection
                # simply offers nothing.
                collection=collection,
            ),
            # `art_root` off the thumbnail settings for the same reason `review`
            # takes it from there: it is one deployment value, already validated,
            # and a second copy is a second chance for the two to disagree.
            sweep=PreviewSweep(discovery_service, art_root=thumbnails.art_root),
            acquisition=AcquisitionService(
                catalogue_service,
                acquisition or _default_acquisition(thumbnails.art_root),
                # Defaults to a transport that refuses rather than to a live one.
                # A plane assembled without wiring one has a wiring mistake, and
                # a real client here would let that mistake reach a museum from a
                # test suite instead of failing where it was made.
                open_stream=open_stream or no_transport,
                # Only a provider whose recorded URL is an identity needs one, and
                # the museum client is the thing that can answer — so by default
                # this is exactly the configured image provider. A deployment with
                # none configured therefore has no resolver either, and an artic
                # fetch refuses by name rather than handing the tile fetcher a URL
                # it cannot read: without credentials to ask the collection for an
                # object's image service, there is genuinely no way to reach it.
                #
                # Overridable because resolving one object and searching a whole
                # collection are separate capabilities that today's one provider
                # happens to serve both of.
                tile_targets=(
                    tile_targets
                    if tile_targets is not None
                    else ({} if image_search is None else {image_search.provider: image_search.tile_url})
                ),
                **({} if resolve is None else {"resolve": resolve}),
            ),
            preparation=PreparationService(
                catalogue_service,
                # Defaults to an engine with no client, which is not a stub: it is
                # exactly the keyless deployment, and it produces recorded
                # dominant-colour mats. A real client here would let a wiring
                # mistake spend money from a test suite rather than failing where
                # it was made — the same reason `open_stream` defaults to refusing.
                mat_engine or _default_mat_engine(),
                preparation or _default_preparation(thumbnails.art_root, artwork_box),
            ),
        )

    def reconcile(self) -> None:
        """Repair whatever the file on disk may predate. Run once, as the plane starts.

        A catalogue file outlives any single version of this code, so a rule
        added after a file was written has to be brought to that file rather than
        assumed of it. Each service owns the repairs for its own records; this is
        the one call a process start has to remember, so a service gaining a
        repair does not mean an entry point gaining a line.

        **The display service had the other one until 2026-08-12**, and it was
        dropped rather than made per-wall: it promoted the oldest theme when none
        was active, which with more than one wall would hang the same theme in
        every room unbidden. What the file may predate about hanging is a *shape*
        rather than a rule now — the single-wall columns — and a shape is moved by
        `persistence/migrations.py` when the file is opened, before any service
        can read it.
        """
        self.discovery.reconcile()


def _default_acquisition(art_root: Path) -> AcquisitionSettings:
    """Acquisition settings for a caller that expressed no preference.

    Every value here is a library default rather than a deployment value, which
    is right for a test and wrong for the Pi — so the entry point passes its own,
    resolved from the environment like everything else it configures.
    """
    return AcquisitionSettings(
        art_root=art_root,
        originals_path=art_root / ORIGINALS_DIRNAME,
        tile_cache_path=art_root / TILE_CACHE_DIRNAME,
        user_agent=DEFAULT_ACQUISITION_USER_AGENT,
        tile_binary=DEFAULT_TILE_BINARY,
        tile_max_pixels=DEFAULT_TILE_MAX_PIXELS,
        tile_timeout_seconds=DEFAULT_TILE_TIMEOUT_SECONDS,
        max_image_bytes=DEFAULT_MAX_IMAGE_BYTES,
        min_free_bytes=DEFAULT_MIN_FREE_BYTES,
    )


def _default_mat_engine() -> MatEngine:
    """A mat engine for a caller that wired no model client.

    **No client is a real deployment, not a stub.** A plane with no
    `OPENROUTER_API_KEY` serves its whole catalogue and pays for nothing; works
    acquired there get dominant-colour mats recorded as such. So the default is
    that deployment rather than something that would fail if used.
    """
    return MatEngine(None, image_max_edge=DEFAULT_MAT_IMAGE_MAX_EDGE)


def _default_preparation(art_root: Path, artwork_box: ArtworkBox) -> PreparationSettings:
    """Preparation settings for a caller that expressed no preference.

    The panel comes from the reference defaults, as every other value in this
    file's defaults does. **A caller passing its own `artwork_box` and letting
    the panel default would get a mismatched pair**, which is why the entry point
    passes both from one resolved `Settings` — the box is *derived from* the
    panel there, so the two cannot disagree.
    """
    return PreparationSettings(
        art_root=art_root,
        ready_path=art_root / READY_DIRNAME,
        panel_width=DEFAULT_TV_PANEL_WIDTH_PX,
        panel_height=DEFAULT_TV_PANEL_HEIGHT_PX,
        box=artwork_box,
    )
