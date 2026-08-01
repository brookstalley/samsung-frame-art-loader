"""Run the curation plane: `uv run python -m curation`."""

import logging

import uvicorn

from curation.app import create_app
from curation.config import Settings
from curation.persistence.file import open_catalogue_file
from curation.persistence.sqlite import SqliteCatalogue
from curation.persistence.sqlite_discovery import SqliteDiscovery
from curation.services.container import Services
from curation.services.display import WallSettings


def main() -> None:
    """Resolve configuration, open the catalogue, and serve."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = Settings.from_env()
    log = logging.getLogger(__name__)
    log.info("catalogue=%s bind=%s:%s", settings.catalogue_path, settings.host, settings.port)
    # The resolved root and this plane's own panel, on one line, so a
    # misconfiguration is a journal read rather than a mystery. The television's
    # panel — never the e-paper one, which belongs to the display plane.
    log.info(
        'art_root=%s manifest=%s tv_panel=%dx%dpx/%.1f" (%.1f px per inch) rotation=%ds shuffle=%s',
        settings.art_root,
        settings.manifest_path,
        settings.tv_panel_width_px,
        settings.tv_panel_height_px,
        settings.tv_panel_diagonal_inches,
        settings.tv_pixels_per_inch,
        settings.rotation_interval_seconds,
        settings.rotation_shuffle,
    )

    settings.art_root.mkdir(parents=True, exist_ok=True)
    # One connection behind both halves of the model: acceptance promotes a
    # candidate's image instances into a work's sources, and that has to commit
    # once or not at all.
    catalogue_file = open_catalogue_file(settings.catalogue_path)
    try:
        services = Services.bind(
            catalogue=SqliteCatalogue(catalogue_file),
            discovery=SqliteDiscovery(catalogue_file),
            wall=WallSettings(
                manifest_path=settings.manifest_path,
                heartbeat_path=settings.heartbeat_path,
                rotation_interval_seconds=settings.rotation_interval_seconds,
                shuffle=settings.rotation_shuffle,
            ),
        )
        # The catalogue file outlives any single version of this code, so rules
        # added since it was written are brought to it here rather than assumed
        # of it. Before serving, because a surface must not answer from a
        # catalogue still in a state its own rules forbid.
        services.reconcile()
        uvicorn.run(create_app(services), host=settings.host, port=settings.port)
    finally:
        catalogue_file.close()


if __name__ == "__main__":
    main()
