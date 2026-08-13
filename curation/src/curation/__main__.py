"""Run the curation plane: `uv run python -m curation`."""

import argparse
import logging
import shutil
import sys
from collections.abc import Sequence

import uvicorn

from curation import art_root, logs
from curation.acquisition.mat import MatEngine
from curation.acquisition.preparation import PreparationSettings
from curation.acquisition.service import AcquisitionSettings
from curation.acquisition.transport import http_stream
from curation.app import create_app
from curation.config import Settings
from curation.discovery.artic import build_collection_browse, build_image_search
from curation.discovery.browse import CollectionBrowse
from curation.discovery.conversation import (
    NO_CONVERSATION_KEY,
    ConversationEngine,
    UnavailableConversation,
    build_conversation_engine,
)
from curation.discovery.engine import DiscoveryEngine, unavailable_engine
from curation.discovery.images import ImageSearch
from curation.discovery.openrouter import OpenRouterClient
from curation.discovery.phase_one import build_engine
from curation.persistence.file import open_catalogue_file
from curation.persistence.sqlite import SqliteCatalogue
from curation.persistence.sqlite_discovery import SqliteDiscovery
from curation.services.container import Services
from curation.services.display import DisplaySettings
from curation.services.previews import PreviewSettings
from curation.services.thumbnails import ThumbnailSettings

#: What a deployment with no key is told when it tries to discover. Written for
#: the curator or agent who reads it back off a refusal, and it names the one
#: thing that fixes it rather than describing the internals that noticed.
NO_KEY: str = (
    "Discovery cannot start: this deployment has no OPENROUTER_API_KEY set, and phase 1 needs a model "
    "to turn an intent into a list of works. Set it in .env — the spend ceiling is that key's own credit "
    "limit. Every other art_discovery action works on runs that already exist."
)


def _engine(settings: Settings) -> DiscoveryEngine:
    """The real engine when a key is configured, and an honest refusal when not.

    Deliberately not a stand-in. A convincing double reachable from a deployment
    is one somebody eventually wires up, and the result would be invented works
    written into a real catalogue with nothing to distinguish them from found
    ones — the curator's evidence that discovery worked would be the product
    fabricating it.
    """
    if not settings.openrouter_api_key:
        return unavailable_engine(NO_KEY)
    return build_engine(
        settings.openrouter_api_key,
        model=settings.discovery_model,
        max_output_tokens=settings.discovery_max_output_tokens,
        search_results=settings.discovery_search_results,
        search_engine=settings.discovery_search_engine,
    )


def _mat_engine(settings: Settings) -> MatEngine:
    """The mat engine, asking a vision model when there is a key to ask with.

    **Unlike `_engine` above, no key is not a refusal here.** Discovery with no
    key must refuse, because a stand-in would write invented works into a real
    catalogue. A mat has an honest mechanical producer — the work's own dominant
    colour, darkened — and `MatColor.method` records which one chose it, so the
    keyless deployment gets real mats that say what they are rather than works
    that cannot be rendered.
    """
    client = None
    if settings.openrouter_api_key:
        client = OpenRouterClient(
            settings.openrouter_api_key,
            model=settings.mat_model,
            max_output_tokens=settings.mat_max_output_tokens,
        )
    return MatEngine(client, image_max_edge=settings.mat_image_max_edge)


def _conversation_engine(settings: Settings) -> ConversationEngine:
    """The engine intent-forming asks, or one that refuses and says why.

    **Refuses like `_engine`, rather than falling back like `_mat_engine`.** A mat
    has an honest mechanical producer; a reply to "what would suit a calm wall"
    has none, and anything written here that tried would put an invented sentence
    in a transcript beside real ones with nothing to tell them apart.
    """
    if not settings.openrouter_api_key:
        return UnavailableConversation(NO_CONVERSATION_KEY)
    return build_conversation_engine(
        settings.openrouter_api_key,
        model=settings.conversation_model,
        max_output_tokens=settings.conversation_max_output_tokens,
    )


def _image_search(settings: Settings) -> ImageSearch | None:
    """The museum provider phase 2 asks, or nothing when none is configured.

    `None` rather than a refusing stand-in, because the two say different things
    at different times. Phase 1 refuses at `start`, where a run does not yet
    exist and refusing creates no record. Phase 2 has a run in hand by the time
    it would refuse, and failing it would record a run that broke when in fact a
    capability is simply not configured — so the honest arrangement is to leave
    the run where it is and let `status` say so in words.
    """
    if not settings.artic_user_agent:
        return None
    return build_image_search(
        user_agent=settings.artic_user_agent,
        preview_max_bytes=settings.preview_max_bytes,
    )


def _collection(settings: Settings) -> CollectionBrowse | None:
    """The collection a run supplements from, or nothing when none is configured.

    Gated on the same identifier as phase 2 and for the same reason: it is the
    same museum, asked a second kind of question, and that museum asks callers to
    say who they are. A deployment that has not said so browses nothing rather
    than browsing anonymously.
    """
    if not settings.artic_user_agent:
        return None
    return build_collection_browse(user_agent=settings.artic_user_agent)


def main(argv: Sequence[str] = ()) -> None:
    """Resolve configuration, open the catalogue, and serve.

    **Arguments are passed in rather than read off `sys.argv`.** The default is
    "no arguments", so calling `main()` from a test parses nothing instead of
    parsing pytest's own command line — which is what it did for one commit, and
    it turned seven startup tests into `SystemExit: 2`. The process entry point
    below supplies the real ones.
    """
    parser = argparse.ArgumentParser(
        prog="python -m curation",
        description="Run the curation plane.",
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help=(
            "Create ART_ROOT as a new, empty art root if it is not one already. "
            "Needed once per deployment; without it a directory that is not an art root is refused, "
            "so a mistyped ART_ROOT reports an error instead of quietly becoming a second collection."
        ),
    )
    arguments = parser.parse_args(argv)

    logs.configure(level=logging.INFO)
    settings = Settings.from_env()
    log = logging.getLogger(__name__)
    log.info("catalogue=%s bind=%s:%s", settings.catalogue_path, settings.host, settings.port)
    # The resolved root and this plane's own panel, on one line, so a
    # misconfiguration is a journal read rather than a mystery. The television's
    # panel — never the e-paper one, which belongs to the display plane.
    box = settings.tv_artwork_box
    log.info(
        'art_root=%s manifests=%s tv_panel=%dx%dpx/%.1f" (%.1f px per inch) rotation=%ds shuffle=%s',
        settings.art_root,
        settings.manifest_pattern,
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
    # The engine and its per-request price on the same line as the estimate they
    # produce. They are one decision — parallel bills $0.001 and the other
    # back-ends $0.005 — and a deployment that pins the price without the engine
    # puts a five-fold error into the only figure a curator authorises against.
    # Nothing refuses to boot over it: two optional settings disagreeing is not
    # worth failing a household product to start. But it is not silent either,
    # because the test that reads as the guard here deliberately cannot see a
    # deployment's own `.env` — see `test_the_search_price_matches_the_engine_that_is_pinned`.
    log.info(
        "discovery gate=%d works phase1_searches=%d phase2_searches_per_work=%d offered_works_per_run=%s "
        "search_engine=%s search_price=$%s phase1_estimate=$%s",
        discovery.approval_threshold,
        discovery.phase1_search_allowance,
        discovery.phase2_searches_per_work,
        # Named rather than left at 0, because this is the setting whose "off" is
        # otherwise invisible: a run that offers nothing because the supplement is
        # disabled looks exactly like one whose collection held nothing.
        "disabled" if discovery.offered_works_per_run <= 0 else discovery.offered_works_per_run,
        settings.discovery_search_engine,
        discovery.search_cost_usd,
        discovery.phase1_estimate_usd,
    )
    # Which model spends the money and whether there is a key to spend it with —
    # the key's *presence*, never its value. "Is the key even set" is the first
    # question a discovery misconfiguration raises, and answering it costs
    # nothing; the repository is public and journals are read over shoulders.
    log.info(
        "discovery model=%s max_output_tokens=%d search_results=%d openrouter_key=%s",
        settings.discovery_model,
        settings.discovery_max_output_tokens,
        settings.discovery_search_results,
        settings.redacted()["openrouter_api_key"],
    )

    # Which museum phase 2 asks, and whether it can be asked at all. Logged for
    # the same reason the key's presence is: "is it even configured" is the first
    # question a run stuck at `resolving_images` raises.
    image_search = _image_search(settings)
    log.info(
        "phase2 image_provider=%s previews=%s preview_sweep=%s",
        "artic" if image_search is not None else "none (ARTIC_USER_AGENT unset)",
        settings.previews_path if image_search is not None else "disabled",
        # On this line rather than its own: the directory and the only thing
        # that reclaims it are one operational fact, and a deployment reading
        # `previews=<path>` with no sweep beside it is the state § Risks names.
        f"every {settings.preview_sweep_interval_seconds}s" if settings.preview_sweep_interval_seconds else "disabled",
    )

    # Whether tiled acquisition can run at all, and where the master images go.
    # Logged for the same reason the key's presence and the image provider are: the
    # binary is the one dependency this plane does not install, it is resolved off
    # PATH at call time, and a deployment missing it fails every tiled fetch at
    # once — a state worth reading at startup rather than discovering per work.
    tile_binary = shutil.which(settings.tile_binary)
    log.info(
        "acquisition originals=%s tile_cache=%s tile_binary=%s min_free=%.1fGiB",
        settings.originals_path,
        settings.tile_cache_path,
        tile_binary or f"MISSING ({settings.tile_binary} is not on PATH; tiled acquisition will refuse)",
        settings.min_free_bytes / (1024**3),
    )

    # Which model chooses mat colours, and where the composed canvases go. Worth
    # its own line for the reason the discovery model's is: a deployment with no
    # key still renders, using the mechanical fallback, and "every mat on this
    # machine says dominant_color_fallback" is a question best answered at
    # startup rather than by reading forty rows.
    log.info(
        "mat model=%s max_output_tokens=%d image_max_edge=%d ready=%s",
        settings.mat_model if settings.openrouter_api_key else "none (no key; every mat comes from the dominant colour)",
        settings.mat_max_output_tokens,
        settings.mat_image_max_edge,
        settings.ready_path,
    )

    # Which model answers a conversational turn, on its own line for the reason
    # the mat model's is: it is a third model with a third reservation, and a
    # deployment whose threads all refuse is a question best answered at startup.
    log.info(
        "conversation model=%s max_output_tokens=%d samples=%s",
        settings.conversation_model if settings.openrouter_api_key else "none (no key; every turn refuses)",
        settings.conversation_max_output_tokens,
        # The sample pictures are the collection's, over the same free seam the
        # run's supplement uses — so a deployment that has not named itself to
        # the museum gets names without pictures, and says so here.
        "artic" if settings.artic_user_agent else "none (ARTIC_USER_AGENT unset; names carry no pictures)",
    )

    # Before anything is created, and before the catalogue is opened. The two
    # steps this replaces were individually reasonable and silent together: a
    # `mkdir(exist_ok=True)` followed by `CREATE TABLE IF NOT EXISTS` turned a
    # typo in ART_ROOT into a fresh empty collection that started cleanly.
    art_root.prepare(settings.art_root, settings.catalogue_path, initialise=arguments.init)
    # One connection behind both halves of the model: acceptance promotes a
    # candidate's image instances into a work's sources, and that has to commit
    # once or not at all.
    catalogue_file = open_catalogue_file(settings.catalogue_path, wall_name=settings.wall_name)
    try:
        services = Services.bind(
            catalogue=SqliteCatalogue(catalogue_file),
            discovery=SqliteDiscovery(catalogue_file),
            display_settings=DisplaySettings(
                art_root=settings.art_root,
                rotation_interval_seconds=settings.rotation_interval_seconds,
                shuffle=settings.rotation_shuffle,
            ),
            thumbnails=ThumbnailSettings(art_root=settings.art_root, directory=settings.thumbnails_path),
            artwork_box=box,
            engine=_engine(settings),
            discovery_settings=settings.discovery_settings,
            image_search=image_search,
            collection=_collection(settings),
            previews=(
                None if image_search is None else PreviewSettings(art_root=settings.art_root, directory=settings.previews_path)
            ),
            acquisition=AcquisitionSettings(
                art_root=settings.art_root,
                originals_path=settings.originals_path,
                tile_cache_path=settings.tile_cache_path,
                user_agent=settings.acquisition_user_agent,
                tile_binary=settings.tile_binary,
                tile_max_pixels=settings.tile_max_pixels,
                tile_timeout_seconds=settings.tile_timeout_seconds,
                max_image_bytes=settings.max_image_bytes,
                min_free_bytes=settings.min_free_bytes,
            ),
            # The one place a live transport is wired. Everything below the seam
            # takes it as an argument, so this line is what separates a process
            # that can fetch from a suite that cannot.
            open_stream=http_stream(settings.acquisition_user_agent),
            preparation=PreparationSettings(
                art_root=settings.art_root,
                ready_path=settings.ready_path,
                panel_width=settings.tv_panel_width_px,
                panel_height=settings.tv_panel_height_px,
                # The same object passed as `artwork_box` above, and passed twice
                # on purpose rather than derived twice: it is *computed from* the
                # panel dimensions on the line above it, so a second derivation
                # here is the only way the canvas and the box could disagree
                # about where the mat ends.
                box=box,
            ),
            mat_engine=_mat_engine(settings),
            conversation_engine=_conversation_engine(settings),
        )
        # The catalogue file outlives any single version of this code, so rules
        # added since it was written are brought to it here rather than assumed
        # of it. Before serving, because a surface must not answer from a
        # catalogue still in a state its own rules forbid.
        services.reconcile()
        # `log_config=None` so uvicorn installs nothing of its own. Its default
        # config attaches plain-text handlers to `uvicorn` and `uvicorn.access`
        # with `propagate: False`, which would put the startup banner, every
        # access line and every unhandled ASGI traceback into the journal as
        # multi-line text — beside this plane's JSON. One non-JSON line aborts
        # `journalctl | jq 'select(.run_id == …)'`, which is the whole reason the
        # log shape exists, so the failure would be the documented way of
        # reconstructing a run quietly not working. With no config of its own,
        # uvicorn's loggers propagate to the root handler installed above.
        uvicorn.run(
            create_app(services, preview_sweep_interval_seconds=settings.preview_sweep_interval_seconds),
            host=settings.host,
            port=settings.port,
            log_config=None,
        )
    finally:
        catalogue_file.close()


if __name__ == "__main__":
    main(sys.argv[1:])
