"""The real HTTP transport for `direct_http` sources.

Separate from `direct.py` for the reason every foreign dependency in this plane is
separated: the fetch logic — ceilings, staging, the zero-byte guard — is the part
worth testing exhaustively, and it cannot be if reaching it requires a network.
This module is the thin part that is exercised live instead.
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Final, Never

import httpx

from curation.acquisition.direct import StreamOpener
from curation.services.errors import ServiceError

log = logging.getLogger(__name__)

#: How long a single image may take. Longer than a metadata call — these are
#: multi-megabyte bodies from institutions that throttle deliberately — and
#: bounded per operation rather than per byte, so a stalled connection cannot
#: hold a slot forever.
CONNECT_TIMEOUT_SECONDS: Final[float] = 10.0
READ_TIMEOUT_SECONDS: Final[float] = 120.0

#: Read in chunks rather than at once. The ceiling in `direct_fetch` can only be
#: enforced on a body that arrives in pieces — asked for whole, an oversized
#: response is already in memory by the time anyone could refuse it.
CHUNK_BYTES: Final[int] = 64 * 1024


def http_stream(user_agent: str) -> StreamOpener:
    """Build a stream opener that identifies itself as this deployment asked."""

    @contextmanager
    def open_stream(url: str) -> Iterator[Iterator[bytes]]:
        timeout = httpx.Timeout(READ_TIMEOUT_SECONDS, connect=CONNECT_TIMEOUT_SECONDS)
        # Redirects are followed, because museums move images and a 301 to the
        # new path is the normal case. The fetch policy ran against the URL that
        # was recorded, so a redirect can land somewhere it would have refused —
        # named here rather than left implicit, and bounded by keeping the
        # product's only reachable private surface off this machine's network in
        # the first place (`security-model.md` § The fetch trigger fired).
        with httpx.stream(
            "GET",
            url,
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": user_agent},
        ) as response:
            if response.status_code >= 400:
                # Read as a refusal rather than raised as a transport fault: the
                # caller records it against the source, which is where a 404 from
                # a museum that reorganised its site belongs.
                raise ServiceError(f"the source answered HTTP {response.status_code}")
            yield response.iter_bytes(CHUNK_BYTES)

    return open_stream


def no_transport(_url: str) -> Never:
    """The default when nothing wired a transport, and it says so.

    A deployment that reaches this has a wiring mistake rather than a bad source,
    so it must not look like a source failure — which a silently empty stream
    would.
    """
    raise ServiceError("No HTTP transport is wired for direct fetches; the plane was assembled without one.")
