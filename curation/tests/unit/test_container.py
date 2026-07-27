"""What a surface is handed, and what one call to it reaches.

The container exists so that a surface binds to the service layer rather than to
one service in it. Two things are worth pinning: that it actually carries every
concern, and that the single repair call an entry point makes reaches each
service that has one. The second is the wiring, and wiring is where a fully
tested behaviour still ends up doing nothing.
"""

from datetime import UTC, datetime

from curation.persistence.discovery_records import InitiatedBy, RunStatus
from curation.persistence.records import Theme
from curation.services.catalogue import CatalogueService
from curation.services.discovery import DiscoveryService

_A_MOMENT = datetime(2026, 7, 20, 9, 30, tzinfo=UTC)


def test_the_container_carries_every_concern_a_surface_may_need(services):
    """A surface takes this, so a concern missing from it is a concern no surface can reach."""
    assert isinstance(services.catalogue, CatalogueService)
    assert isinstance(services.discovery, DiscoveryService)


def test_one_reconcile_call_reaches_the_catalogue_repair(store, services):
    """An entry point calls the container once; each service's repair must run.

    Seeded through the store rather than the service, because the state being
    repaired — themes with none active — is one the service's own rules forbid it
    to create, and only a file written by an earlier revision holds it.
    """
    store.add_theme(Theme(id="t1", name="Late night", created_at=_A_MOMENT))
    store.add_theme(Theme(id="t2", name="Daylight", created_at=_A_MOMENT))

    services.reconcile()

    assert services.catalogue.active_theme().name == "Late night"


def test_one_reconcile_call_reaches_the_discovery_repair(discovery, services):
    """The second repair, asserted through the same single call an entry point makes.

    Its own tests enter through `DiscoveryService.reconcile`, and every one of
    them passes with the container's call to it deleted — which is the shape of
    defect this file exists for: the behaviour is fine and nothing invokes it.
    """
    run = discovery.start_discovery_run(intent_text="Surrealist paintings", initiated_by=InitiatedBy.MCP_CLIENT)

    services.reconcile()

    assert discovery.get_run(run.id).status is RunStatus.INTERRUPTED
