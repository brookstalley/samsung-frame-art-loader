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

from dataclasses import dataclass

from curation.discovery.engine import DiscoveryEngine
from curation.persistence.catalogue import CatalogueStore
from curation.persistence.discovery import DiscoveryStore
from curation.services.catalogue import CatalogueService
from curation.services.discovery import DiscoveryService
from curation.services.display import DisplayService, WallSettings
from curation.services.display_fit import ArtworkBox
from curation.services.runner import DiscoveryRunner, DiscoverySettings
from curation.services.survey import SurveyService
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
    #: Running a discovery run, as distinct from recording one. It sits above
    #: `discovery` rather than inside it because the record layer is deliberately
    #: synchronous and knows nothing of processes, and everything about starting
    #: work behind a handle does.
    runner: DiscoveryRunner

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
    ) -> Services:
        """Assemble the services over an already-open file.

        The engine is injected rather than constructed here for the reason every
        foreign dependency is: a container that built its own model client would
        make "run the service layer without touching a paid API" impossible to
        arrange, and that is the arrangement most of this product's tests need.
        """
        catalogue_service = CatalogueService(catalogue)
        display_service = DisplayService(catalogue, catalogue_service, wall)
        thumbnail_service = ThumbnailService(catalogue_service, thumbnails)
        discovery_service = DiscoveryService(discovery, catalogue_service)
        return cls(
            catalogue=catalogue_service,
            discovery=discovery_service,
            display=display_service,
            thumbnails=thumbnail_service,
            survey=SurveyService(catalogue_service, display_service, thumbnail_service, artwork_box),
            runner=DiscoveryRunner(discovery_service, engine, discovery_settings),
        )

    def reconcile(self) -> None:
        """Repair whatever the file on disk may predate. Run once, as the plane starts.

        A catalogue file outlives any single version of this code, so a rule
        added after a file was written has to be brought to that file rather than
        assumed of it. Each service owns the repairs for its own records; this is
        the one call a process start has to remember, so a service gaining a
        repair does not mean an entry point gaining a line.
        """
        self.display.reconcile()
        self.discovery.reconcile()
