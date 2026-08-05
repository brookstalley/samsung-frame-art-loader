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

**The destination is never written or removed here.** The binary fetches to a
staging path beside it, and promoting that is the caller's step. Clearing the
destination up front — which the binary's refusal to overwrite invites — would mean
a re-fetch that then failed had already destroyed the image the work was
displaying, while its `Original` row went on naming the deleted file.

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
    """Fetch a tiled image beside `destination`, reporting what actually arrived.

    Returns the **staged** path, not `destination`. Promoting it is the caller's
    step; see the module docstring.

    `url` must already have passed the fetch policy; nothing here re-checks it,
    because a second opinion in a second place is how the two come to disagree.
    """
    resolved = shutil.which(binary)
    if resolved is None:
        raise DezoomifyUnavailable(f"{binary!r} is not on PATH; tiled acquisition cannot run in this deployment.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    # Beside the destination, never the destination itself — and **the suffix stays
    # last**. The binary picks its output encoder from the file extension, so a
    # path ending `.partial` is refused outright: probed at 2.18.1, it exits 1 with
    # `The file extension ."partial" was not recognized as an image format` and
    # leaves a zero-byte file. Naming it `<stem>.partial<suffix>` keeps `.jpg`
    # where the binary looks for it.
    staged = destination.with_name(f"{destination.stem}.partial{destination.suffix}")
    # Observed: given a cache directory that does not exist, the binary warns once
    # per tile and completes with an empty cache — losing exactly the
    # retry-without-refetching this directory exists for, and saying so only in
    # warnings nobody reads.
    tile_cache.mkdir(parents=True, exist_ok=True)
    if staged.exists():
        # The binary refuses to overwrite. A retry is a normal operation here, so
        # a staged file left by an earlier attempt is cleared — the destination
        # itself is not touched, so the image the work holds is never at risk.
        staged.unlink()

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
    # Two separate guards, because these are two separate bug classes and only one
    # of them is about a shell. Passing each value as its own element is what makes
    # a URL carrying `;`, `$(...)` or a quote inert — it reaches the binary as data,
    # never as anything a shell reads. `--` ends the options, which is what stops the
    # *binary's own parser* reading a URL beginning with `-` as a flag and silently
    # overriding one of the settings above.
    #
    # Nothing reaching here can begin with `-` today: `check_fetchable` refuses any
    # scheme but http/https before this is called, and a `-` string parses to no
    # scheme at all. The fence is here anyway because that is a guarantee held in
    # another module, one caller away — and this URL is remote-derived, composed from
    # the museum's own `config.iiif_url`. Do not drop it as redundant: it is what
    # holds if `ALLOWED_SCHEMES` widens or a second caller arrives unguarded.
    argv += ["--", url, str(staged)]

    try:
        completed = subprocess.run(  # noqa: S603 - argv list, no shell, resolved binary
            argv,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        _discard(staged)
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
    size = staged.stat().st_size if staged.exists() else 0

    if size <= 0:
        # Observed on total failure: exit 1 *and* a zero-byte file left behind.
        # Recording that path would persist a row naming an empty image, which is
        # the constraint the catalogue enforces on the way in.
        _discard(staged)
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
            path=staged,
            byte_size=size,
            tiles_fetched=fetched,
            tiles_expected=expected,
            detail=f"{fetched} of {expected} tiles arrived; the image has gaps",
        )

    if completed.returncode != 0:
        # An image, a non-zero exit, and no tile counts to read. The binary said
        # something went wrong in wording this code does not recognise — a
        # rephrased message in a later release is the likely cause, and this is
        # the branch that decides what a rephrasing costs.
        #
        # Called PARTIAL rather than COMPLETE deliberately. Complete is the
        # claim that would be *silently* wrong: it records a gappy image as
        # `ok` and reclaims the tiles that would have made the retry cheap.
        # Partial overstates at worst — the work is still held and still shown,
        # and the curator is told a retry may improve it.
        log.warning("tile fetch of %s exited %s with an image and no tile counts", url, completed.returncode)
        return TileResult(
            outcome=TileOutcome.PARTIAL,
            path=staged,
            byte_size=size,
            tiles_fetched=None,
            tiles_expected=None,
            detail=(
                f"the fetch reported a problem this version does not recognise "
                f"(exit {completed.returncode}); the image may have gaps"
            ),
        )

    return TileResult(
        outcome=TileOutcome.COMPLETE,
        path=staged,
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
    """Remove an unusable output so no later step mistakes it for an image.

    **A removal that fails is logged, not raised**, and the difference is the
    module docstring's promise that one bad source never ends the pass over the
    works behind it. This ran without the guard: a read-only mount or a
    permissions problem turned an unlink into an `OSError` that escaped
    `tile_fetch`, through `_acquire_tiled`, which catches nothing, and ended the
    whole acquisition — over a leftover file, on the path that exists to clean up
    after a failure. The two sibling helpers in `direct.py` and `service.py`
    already caught it; this one is now the same contract rather than the odd one.
    """
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        log.warning("could not remove the unusable tile output at %s: %s", path, exc)
