"""The services a surface is handed, and how they relate to each other.

Operation logic is split by concern rather than gathered into one class: the
catalogue owns works already accepted, discovery owns everything before
acceptance. A surface takes this container rather than any single service, so
adding a concern changes the wiring here and nothing in `create_app` or in an MCP
binding — which is what keeps a surface from quietly binding to one service and
becoming the reason a second one is awkward to add.

How the services relate is decided here, once. Discovery holds the catalogue
because acceptance is a promotion, and that direction is a fact about the
pipeline rather than a convenience of one call site.
"""

from dataclasses import dataclass

from curation.persistence.catalogue import CatalogueStore
from curation.services.catalogue import CatalogueService
from curation.services.discovery import DiscoveryService


@dataclass(frozen=True, slots=True)
class Services:
    """Every service the curation plane offers, assembled over one open file."""

    catalogue: CatalogueService
    discovery: DiscoveryService

    @classmethod
    def bind(cls, *, catalogue: CatalogueStore) -> Services:
        """Assemble the services over an already-open store."""
        catalogue_service = CatalogueService(catalogue)
        return cls(catalogue=catalogue_service, discovery=DiscoveryService(catalogue_service))

    def reconcile(self) -> None:
        """Repair whatever the file on disk may predate. Run once, as the plane starts.

        A catalogue file outlives any single version of this code, so a rule
        added after a file was written has to be brought to that file rather than
        assumed of it. Each service owns the repairs for its own records; this is
        the one call a process start has to remember, so a service gaining a
        repair does not mean an entry point gaining a line.
        """
        self.catalogue.reconcile()
