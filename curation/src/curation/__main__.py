"""Run the curation plane: `uv run python -m curation`."""

import logging

import uvicorn

from curation import logs
from curation.app import create_app
from curation.config import Settings
from curation.discovery.engine import unavailable_engine
from curation.persistence.file import open_catalogue_file
from curation.persistence.sqlite import SqliteCatalogue
from curation.persistence.sqlite_discovery import SqliteDiscovery
from curation.services.container import Services
from curation.services.display import WallSettings
from curation.services.thumbnails import ThumbnailSettings


def main() -> None:
    """Resolve configuration, open the catalogue, and serve."""
    logs.configure(level=logging.INFO)
    settings = Settings.from_env()
    log = logging.getLogger(__name__)
    log.info("catalogue=%s bind=%s:%s", settings.catalogue_path, settings.host, settings.port)
    # The resolved root and this plane's own panel, on one line, so a
    # misconfiguration is a journal read rather than a mystery. The television's
    # panel — never the e-paper one, which belongs to the display plane.
    box = settings.tv_artwork_box
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
    # The derived geometry as well as its inputs: whether a work is judged large
    # enough for the wall depends on this box, and a wrong mat or floor is
    # otherwise only visible as works being labelled oddly in the grid.
    log.info(
        'artwork_box=%dx%dpx mat=%.2f" (bottom x%.2f) floor=%.1f"',
        box.width,
        box.height,
        settings.mat_width_inches,
        settings.mat_bottom_weight,
        settings.resolution_floor_inches,
    )
    # What discovery may spend and what it is priced at, on one line, because a
    # bounded estimate a curator authorises against is only as good as the
    # numbers behind it — and those are the ones most likely to be stale.
    discovery = settings.discovery_settings
    log.info(
        "discovery gate=%d works phase1_searches=%d phase2_searches_per_work=%d phase1_estimate=$%s",
        discovery.approval_threshold,
        discovery.phase1_search_allowance,
        discovery.phase2_searches_per_work,
        discovery.phase1_estimate_usd,
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
            thumbnails=ThumbnailSettings(art_root=settings.art_root, directory=settings.thumbnails_path),
            artwork_box=box,
            # No model client is configured in this build, so discovery refuses
            # to start a run rather than being handed a stand-in that would
            # write invented works into a real catalogue. Every other discovery
            # action works on runs that already exist.
            engine=unavailable_engine(),
            discovery_settings=settings.discovery_settings,
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
