"""Driving `dezoomify-rs`, against the contract it actually has.

Every rule below was observed from the installed binary at 2.18.1 rather than read
out of its help text or inherited from the 2024 call site, and two of them
contradict what that call site assumed.

**Exit codes classify nothing.** `0` is returned both for a successful save and
for a run that read no input and wrote no file. `1` is returned both when no tile
could be fetched and when most tiles arrived and a usable image was written. The
two outcomes this product must tell apart — `partial_tiles`, which the catalogue
records as normal, and `failed` — share an exit code, so the classification is made
from the file on disk: absent or empty is a failure, present and non-empty is an
image, and the tile counts in the log say which kind of image it is.

**The success message goes to stderr, and it is a log line rather than an
interface.** The 2024 code parsed the saved filename out of stdout, which is empty
on every non-interactive path — that parse raises on success. Here the output path
is supplied and then stated, so nothing has to be parsed to know where the bytes
went.

**A partial image is kept.** The 2024 code deleted the output on any non-zero exit,
which discarded a real image built from most of its tiles and made
`Source.last_fetch_status = 'partial_tiles'` unreachable in practice.

**The binary is never given a shell, and never an unvalidated argument.** Its input
argument accepts a local path as readily as a URL, so callers pass URLs that have
already been through the fetch policy. `stdin` is closed and `--image-index` is
always supplied, because the binary prompts interactively both when its input is
missing and when a source offers several images — a prompt a service would either
block on or answer with EOF, which it reports as a silent success.
"""

import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Final

log = logging.getLogger(__name__)

#: How the binary announces a partial result. Read to report *how* partial, never
#: to decide whether the fetch worked — that question is answered by the file.
_PARTIAL: Final[re.Pattern[str]] = re.compile(r"Only (\d+) tiles? out of (\d+) could be downloaded")

#: Which image to take when a source offers several. Always passed: omitting it is
#: what sends the binary to an interactive prompt inside a service.
_IMAGE_INDEX: Final[str] = "0"


class TileOutcome(Enum):
    """What a dezoomify invocation produced, judged from the file it left."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class TileResult:
    """The outcome, and enough detail to record and explain it."""

    outcome: TileOutcome
    path: Path | None
    byte_size: int
    tiles_fetched: int | None
    tiles_expected: int | None
    detail: str

    @property
    def usable(self) -> bool:
        """Whether an image exists to record, partial or not."""
        return self.outcome in (TileOutcome.COMPLETE, TileOutcome.PARTIAL)


class DezoomifyUnavailable(RuntimeError):
    """The binary is not installed or not on `PATH`.

    Distinct from a fetch failure: no source is at fault and retrying the work
    will not help, so the caller reports a deployment problem rather than
    recording a failed fetch against a URL that may be perfectly good.
    """


def tile_fetch(
    url: str,
    *,
    destination: Path,
    tile_cache: Path,
    binary: str,
    user_agent: str,
    max_width: int,
    max_height: int,
    timeout_seconds: int,
    referer: str | None = None,
) -> TileResult:
    """Fetch a tiled image to `destination`, reporting what actually arrived.

    `url` must already have passed the fetch policy; nothing here re-checks it,
    because a second opinion in a second place is how the two come to disagree.
    """
    resolved = shutil.which(binary)
    if resolved is None:
        raise DezoomifyUnavailable(f"{binary!r} is not on PATH; tiled acquisition cannot run in this deployment.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    # Observed: given a cache directory that does not exist, the binary warns once
    # per tile and completes with an empty cache — losing exactly the
    # retry-without-refetching this directory exists for, and saying so only in
    # warnings nobody reads.
    tile_cache.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        # The binary refuses to overwrite. A re-fetch is a normal operation here,
        # so the stale file is cleared rather than the retry being refused.
        destination.unlink()

    argv = [
        resolved,
        "--max-width",
        str(max_width),
        "--max-height",
        str(max_height),
        "--image-index",
        _IMAGE_INDEX,
        "--tile-cache",
        str(tile_cache),
        "--header",
        f"User-Agent: {user_agent}",
    ]
    if referer is not None:
        argv += ["--header", f"Referer: {referer}"]
    # The URL is the last option-free argument and is passed as one element. That
    # is what makes a URL carrying `;`, `$(...)` or a quote inert: it reaches the
    # binary as data, never as anything a shell reads.
    argv += [url, str(destination)]

    try:
        completed = subprocess.run(  # noqa: S603 - argv list, no shell, resolved binary
            argv,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        _discard(destination)
        return TileResult(
            outcome=TileOutcome.FAILED,
            path=None,
            byte_size=0,
            tiles_fetched=None,
            tiles_expected=None,
            detail=f"the tile fetch did not finish within {timeout_seconds}s",
        )

    messages = completed.stderr.decode("utf-8", errors="replace")
    fetched, expected = _tile_counts(messages)
    size = destination.stat().st_size if destination.exists() else 0

    if size <= 0:
        # Observed on total failure: exit 1 *and* a zero-byte file left behind.
        # Recording that path would persist a row naming an empty image, which is
        # the constraint the catalogue enforces on the way in.
        _discard(destination)
        return TileResult(
            outcome=TileOutcome.FAILED,
            path=None,
            byte_size=0,
            tiles_fetched=fetched,
            tiles_expected=expected,
            detail=_failure_detail(messages, completed.returncode),
        )

    if fetched is not None and expected is not None and fetched < expected:
        log.info("tile fetch returned %s of %s tiles for %s", fetched, expected, url)
        return TileResult(
            outcome=TileOutcome.PARTIAL,
            path=destination,
            byte_size=size,
            tiles_fetched=fetched,
            tiles_expected=expected,
            detail=f"{fetched} of {expected} tiles arrived; the image has gaps",
        )

    return TileResult(
        outcome=TileOutcome.COMPLETE,
        path=destination,
        byte_size=size,
        tiles_fetched=fetched,
        tiles_expected=expected,
        detail="every tile arrived",
    )


def reclaim_tile_cache(tile_cache: Path) -> None:
    """Drop a completed work's cached tiles.

    The cache earns its disk only while a fetch might be retried: its whole
    purpose is letting a partial download resume without re-fetching what already
    arrived. Once a work holds a complete image there is nothing left to resume,
    so the tiles are dead weight on the device this deployment's top operational
    risk is about. Kept after a *partial* fetch, which is the one case where they
    are worth exactly what they cost.
    """
    shutil.rmtree(tile_cache, ignore_errors=True)


def _tile_counts(messages: str) -> tuple[int | None, int | None]:
    match = _PARTIAL.search(messages)
    if match is None:
        return None, None
    return int(match.group(1)), int(match.group(2))


def _failure_detail(messages: str, returncode: int) -> str:
    """The binary's own last word on why, so a recorded failure is readable."""
    lines = [line for line in messages.splitlines() if line.strip()]
    for line in reversed(lines):
        if "[ERROR]" in line:
            return line.split("[ERROR]", 1)[1].strip()
    return f"the tile fetch failed (exit {returncode}) and wrote no image"


def _discard(path: Path) -> None:
    """Remove an unusable output so no later step mistakes it for an image."""
    if path.exists():
        path.unlink()
