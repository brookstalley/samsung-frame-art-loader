"""Start the display plane: `uv run python -m display`.

The composition root, and the only module that knows a real television exists —
everything above the seam is written against `TvClient`, so this is where the
`samsungtvws` fork is named and where it stays.

**Shutdown is deliberate rather than abrupt.** systemd sends SIGTERM and then
waits a bounded time before SIGKILL; a daemon that ignored the first would be
killed with its websocket open, and the set holds a half-closed art channel until
it times out on its own. The stop event unblocks the loop's own wait, so the
process closes in about as long as whatever call is in flight.
"""

import asyncio
import logging
import signal
import sys

from display import logs
from display.config import ConfigError, Settings, load
from display.daemon import Clock, Daemon
from display.manifest import Watcher
from display.panel import Geometry, LabelSurface, SurfaceUnavailable
from display.panel.legibility import TypeScale, ViewingConditionsUnknown, margin_for, type_scale_for
from display.state import DisplayState, StateSchemaTooNew
from display.tv.samsung import SamsungTv

log = logging.getLogger(__name__)


def label_surface(settings: Settings) -> LabelSurface | None:
    """This device's label surface, None when it has none, raising when it has a broken one.

    **The three outcomes are three different things and the daemon reports them
    differently.** No `EPD_DEVICE` means this device draws no label, which
    `architecture.md` § Direction makes a supported deployment rather than a
    fault — `None`, and nothing said. A configured panel that will not open is a
    device that is *meant* to have a label and does not, which is worth saying
    out loud — hence a raise rather than a second `None`, because two roads to
    the same return value is how a broken panel came to look identical to a
    deployment that never had one.

    **The rasterizer is imported here rather than at the top of this module.** It
    pulls in Pango through PyGObject, which is installed only where a label is
    actually drawn, and importing it unconditionally would make a text stack a
    requirement for every device including the ones with no panel at all.

    **The type scale is derived here** because this is where `.env` is read and
    where a device is decided to have a panel; everything below the seam takes its
    physical facts as arguments, which is what lets the next device be a
    configuration rather than a rewrite.
    """
    if not settings.epd_device:
        return None

    # **Before the driver import, deliberately.** Both are reasons this device
    # gets no label, but only one of them is a value somebody typed: a deployment
    # that has not stated its viewing distance should be told that, not told its
    # text stack is missing — which on a dev machine it also is.
    try:
        scale = type_scale_for(
            width_px=settings.epd_panel_width_px,
            height_px=settings.epd_panel_height_px,
            diagonal_inches=settings.epd_panel_diagonal_inches,
            viewing_distance_inches=settings.epd_viewing_distance_inches,
        )
    except ViewingConditionsUnknown as exc:
        # Converted rather than propagated, the same move the text stack's
        # ImportError gets below: this function's promise to its caller is that a
        # device without a usable label surface raises one type, and the caller
        # answers all of them by saying so once and rotating the wall anyway.
        raise SurfaceUnavailable(str(exc)) from exc

    try:
        from display.panel.epaper import EpaperSurface, open_panel  # noqa: PLC0415 -- see the docstring
        from display.panel.pango import PangoRasterizer  # noqa: PLC0415 -- see the docstring
    except ImportError as exc:
        # The text stack being absent lands in the same place as the panel being
        # absent, and it is a provisioning mistake somebody can fix while the wall
        # keeps working — so it is converted rather than allowed to crash a daemon
        # whose television is perfectly healthy.
        raise SurfaceUnavailable(f"the label's text stack is not installed ({exc}); try `uv sync --group raster`") from exc

    return EpaperSurface(
        epd=open_panel(settings.epd_device),
        rasterizer=PangoRasterizer(),
        geometry=label_geometry(settings, scale),
        type_scale=scale,
        rotate_degrees=settings.epd_rotate_degrees,
    )


def label_geometry(settings: Settings, scale: TypeScale) -> Geometry:
    """This panel's usable area, with a border derived from the type on it.

    **Separate from `label_surface` because it is the only part of that function
    reachable without hardware.** Everything else there needs a driver and a text
    stack; this is a decision, and a decision covered by no test is one a
    refactor can invert silently — which for this one means a label that quietly
    goes back to a border chosen against type sizes nobody had measured.

    The margin derives unless the deployment states one. It cannot be picked
    independently: a border trades directly against how many lines survive the
    drop rule, so choosing it apart from the floor that decides how many lines
    there are leaves two numbers in tension that nobody compared. The override is
    for the surface whose border is a physical fact rather than a typographic
    choice — a device drawing its label into the mat area around an artwork does
    not get to choose where the picture ends.
    """
    return Geometry(
        width_px=settings.epd_panel_width_px,
        height_px=settings.epd_panel_height_px,
        margin_px=settings.epd_margin_px if settings.epd_margin_px is not None else margin_for(scale),
    )


async def _run() -> int:
    settings = load()
    watcher = Watcher(
        settings.manifest_path,
        rotation_interval_fallback=settings.rotation_interval_fallback_seconds,
        shuffle_fallback=settings.rotation_shuffle_fallback,
    )
    tv = SamsungTv(
        host=settings.tv_address,
        port=settings.tv_port,
        token_file=settings.tv_token_file,
        client_name=settings.tv_client_name,
        connect_timeout_seconds=settings.tv_connect_timeout_seconds,
        upload_timeout_seconds=settings.upload_timeout_seconds,
        select_confirm_seconds=settings.select_confirm_seconds,
    )

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for received in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(received, stop.set)

    # One clock for both, because the daemon measures an upload's retry wait
    # against a timestamp the store wrote. Two sources here would be two answers
    # to the same question, and the store's is the one that has to survive a
    # restart.
    # **A panel that will not open is reported, not fatal.** The television is the
    # product and the label annotates it, so a broken panel costs the label and
    # nothing else — but it is carried into the daemon rather than logged and
    # dropped, because the journal is on the Pi and the heartbeat is what curation
    # can see. Without it a configured-but-broken panel reads on the health surface
    # exactly like a device that never had one.
    surface: LabelSurface | None = None
    surface_error: str | None = None
    try:
        surface = label_surface(settings)
    except SurfaceUnavailable as exc:
        surface_error = str(exc)
        log.warning(
            "this device has a panel configured (%s) and no label will be drawn (%s); the wall keeps rotating",
            settings.epd_device,
            exc,
            extra={"event": "panel.unavailable"},
        )

    clock = Clock.system()
    with DisplayState(settings.state_path, now=clock.now) as state:
        daemon = Daemon(
            settings=settings,
            tv=tv,
            state=state,
            watcher=watcher,
            clock=clock,
            surface=surface,
            surface_error=surface_error,
        )
        await daemon.run(stop)
    return 0


def main() -> int:
    logs.configure()
    try:
        return asyncio.run(_run())
    except ConfigError as exc:
        # Named on stderr as well as logged, because the most likely reader of
        # this failure is a person who has just run the command by hand and a
        # JSON line is the harder of the two to read at a terminal.
        #
        # No traceback on either of these: both say a *deployment value* is wrong,
        # and the fix is in `.env` or in the rollout. A stack through `load()`
        # points at this codebase, which is the one place the problem is not.
        log.error("%s", exc, extra={"event": "daemon.misconfigured"})  # noqa: TRY400 -- the fix is in .env, not in a frame
        print(f"display plane cannot start: {exc}", file=sys.stderr)  # noqa: T201 — the operator is at a terminal
        return 2
    except StateSchemaTooNew as exc:
        log.error("%s", exc, extra={"event": "daemon.state_too_new"})  # noqa: TRY400 -- the fix is a rollout, not a frame
        print(f"display plane cannot start: {exc}", file=sys.stderr)  # noqa: T201 — the operator is at a terminal
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
