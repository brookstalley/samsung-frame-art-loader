"""Run the curation plane: `uv run python -m curation`."""

import logging

import uvicorn

from curation.app import create_app
from curation.config import Settings
from curation.persistence.sqlite import SqliteCatalogue
from curation.services.catalogue import CatalogueService


def main() -> None:
    """Resolve configuration, open the catalogue, and serve."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = Settings.from_env()
    log = logging.getLogger(__name__)
    log.info("catalogue=%s bind=%s:%s", settings.catalogue_path, settings.host, settings.port)

    settings.art_root.mkdir(parents=True, exist_ok=True)
    store = SqliteCatalogue(settings.catalogue_path)
    try:
        service = CatalogueService(store)
        # The catalogue file outlives any single version of this code, so rules
        # added since it was written are brought to it here rather than assumed
        # of it. Before serving, because a surface must not answer from a
        # catalogue still in a state its own rules forbid.
        service.reconcile()
        uvicorn.run(create_app(service), host=settings.host, port=settings.port)
    finally:
        store.close()


if __name__ == "__main__":
    main()
