"""Fetching an image that is served whole, over one HTTP request.

This is the `direct_http` path — the contemporary-web half of the source model,
where a gallery or portfolio serves a single JPEG rather than a tile pyramid.
Everything it has to be careful about comes from the same fact as the tiled path:
the URL came from web discovery, so the response is not to be trusted either.

**The response is streamed and bounded.** A source that serves an endless body
would otherwise fill the disk this deployment's top operational risk is about, and
the free-space guard runs *before* a fetch rather than during one. So the ceiling
is enforced here, on the way in, and a body that exceeds it is a failed fetch
rather than a partial file.

**Bytes land at their final path only once they are all present.** The download
writes beside the destination and renames, so a process that dies mid-fetch leaves
no truncated file for a later step to mistake for an image. That is the same rule
`PreviewCache` follows, for the same reason.
"""

import hashlib
import logging
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

#: Opens a URL and yields its body in chunks. A seam rather than a direct httpx
#: call so this module can be tested without a network, and so the transport can
#: be shared with whatever else needs one.
StreamOpener = Callable[[str], AbstractContextManager[Iterator[bytes]]]


@dataclass(frozen=True, slots=True)
class DirectResult:
    """What arrived, or why nothing did."""

    path: Path | None
    byte_size: int
    content_hash: str | None
    detail: str

    @property
    def usable(self) -> bool:
        return self.path is not None


def direct_fetch(
    url: str,
    *,
    destination: Path,
    open_stream: StreamOpener,
    max_bytes: int,
) -> DirectResult:
    """Fetch `url` to `destination`, bounded at `max_bytes`.

    `url` must already have passed the fetch policy. The hash is computed while
    the bytes stream past rather than by re-reading the file afterwards: the file
    is potentially very large, and re-reading it to hash it is a second pass over
    the slowest device in the deployment.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.with_name(f"{destination.name}.partial")
    digest = hashlib.sha256()
    written = 0
    over_ceiling = False

    try:
        with open_stream(url) as chunks:
            with staging.open("wb") as handle:
                for chunk in chunks:
                    if not chunk:
                        continue
                    written += len(chunk)
                    if written > max_bytes:
                        # Refused rather than truncated: a half-image recorded as
                        # an original is a worse outcome than no image, because
                        # nothing downstream can tell it is half. Stopping here
                        # also stops reading, so an endless body costs the
                        # ceiling and not the disk.
                        over_ceiling = True
                        break
                    digest.update(chunk)
                    handle.write(chunk)
    except OSError as exc:
        # Covers both ends: a disk that cannot be written and a transport that
        # raises while streaming. Both mean no image, and the message says which.
        _discard(staging)
        return DirectResult(path=None, byte_size=0, content_hash=None, detail=f"the fetch failed: {exc}")
    except Exception as exc:  # prawduct:allow prawduct/broad-except -- a source fault must not end the run
        # The transport seam is free to raise anything — an httpx URL error is
        # not an `OSError` and not an `HTTPError` either — and one bad source
        # must degrade to a recorded fetch failure rather than ending an
        # acquisition pass over the works behind it.
        _discard(staging)
        log.warning("direct fetch of %s raised %s", url, type(exc).__name__, exc_info=True)
        return DirectResult(
            path=None,
            byte_size=0,
            content_hash=None,
            detail=f"the source raised {type(exc).__name__}: {exc}",
        )

    if over_ceiling:
        _discard(staging)
        return DirectResult(
            path=None,
            byte_size=0,
            content_hash=None,
            detail=f"the source served more than the {max_bytes} byte ceiling for a single image",
        )

    if written <= 0:
        # The zero-byte failure the catalogue refuses to record, caught before it
        # can be offered: a served-but-empty body is a real observed outcome and
        # is indistinguishable from a good file by name alone.
        _discard(staging)
        return DirectResult(path=None, byte_size=0, content_hash=None, detail="the source returned no bytes")

    staging.replace(destination)
    return DirectResult(
        path=destination,
        byte_size=written,
        content_hash=digest.hexdigest(),
        detail=f"{written} bytes arrived",
    )


def _discard(path: Path) -> None:
    """Remove a staged file so no later step can mistake it for a finished one."""
    try:
        if path.exists():
            path.unlink()
    except OSError as exc:
        # A stranded `.partial` is never read — nothing looks for that suffix —
        # so this is worth a line in the journal and nothing more.
        log.warning("could not remove the staged file at %s: %s", path, exc)
