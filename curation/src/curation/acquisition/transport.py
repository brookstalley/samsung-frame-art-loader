"""The real HTTP transport for `direct_http` sources.

Separate from `direct.py` for the reason every foreign dependency in this plane is
separated: the fetch logic — ceilings, staging, the zero-byte guard — is the part
worth testing exhaustively, and it cannot be if reaching it requires a network.
This module is the thin part that is exercised live instead.
"""

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Final, Never

import httpx

from curation.acquisition.direct import StreamOpener
from curation.acquisition.urls import check_fetchable
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

#: How many redirects one fetch may follow before it is treated as a loop. Museums
#: chain at most a couple — a longer chain is a misconfigured site or a source
#: trying to exhaust the follower.
MAX_REDIRECTS: Final[int] = 5

#: The policy each hop is put through. A parameter so the redirect handling can be
#: exercised without a resolver, for the same reason the service takes one.
UrlCheck = Callable[[str], str]


def http_stream(user_agent: str, *, check: UrlCheck = check_fetchable) -> StreamOpener:
    """Build a stream opener that identifies itself as this deployment asked.

    **Redirects are followed one hop at a time, and every hop is re-checked.**
    Museums move images, so a 301 to the new path is ordinary and refusing to
    follow redirects would break real sources. But the fetch policy ran against
    the URL the catalogue recorded, and `follow_redirects=True` would let a source
    answer a checked public URL with a `Location:` pointing at `127.0.0.1` — which
    hands back exactly the reach into the operator's own network the policy exists
    to deny, through the one door it does not watch. So the following is done here
    rather than by the client, and each `Location` goes through the same check as
    the original.
    """

    @contextmanager
    def open_stream(url: str) -> Iterator[Iterator[bytes]]:
        timeout = httpx.Timeout(READ_TIMEOUT_SECONDS, connect=CONNECT_TIMEOUT_SECONDS)
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            target = url
            for _ in range(MAX_REDIRECTS + 1):
                with client.stream("GET", target, headers={"User-Agent": user_agent}) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise ServiceError(f"the source answered HTTP {response.status_code} with no location")
                        # Resolved against the URL it came from, because a
                        # `Location` may be relative — and a relative one that
                        # went unresolved would be checked as a different string
                        # than the one actually requested.
                        target = check(str(response.url.join(location)))
                        continue
                    if response.status_code >= 400:
                        # Read as a refusal rather than raised as a transport
                        # fault: the caller records it against the source, which
                        # is where a 404 from a museum that reorganised its site
                        # belongs.
                        raise ServiceError(f"the source answered HTTP {response.status_code}")
                    yield response.iter_bytes(CHUNK_BYTES)
                    return
            raise ServiceError(f"the source redirected more than {MAX_REDIRECTS} times")

    return open_stream


def no_transport(_url: str) -> Never:
    """The default when nothing wired a transport, and it says so.

    A deployment that reaches this has a wiring mistake rather than a bad source,
    so it must not look like a source failure — which a silently empty stream
    would.
    """
    raise ServiceError("No HTTP transport is wired for direct fetches; the plane was assembled without one.")
