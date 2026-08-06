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
from display.config import ConfigError, load
from display.daemon import Clock, Daemon
from display.manifest import Watcher
from display.state import DisplayState, StateSchemaTooNew
from display.tv.samsung import SamsungTv

log = logging.getLogger(__name__)


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
    )

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for received in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(received, stop.set)

    # One clock for both, because the daemon measures an upload's retry wait
    # against a timestamp the store wrote. Two sources here would be two answers
    # to the same question, and the store's is the one that has to survive a
    # restart.
    clock = Clock.system()
    with DisplayState(settings.state_path, now=clock.now) as state:
        daemon = Daemon(settings=settings, tv=tv, state=state, watcher=watcher, clock=clock)
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
