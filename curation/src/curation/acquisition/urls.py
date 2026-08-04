"""What may be fetched, decided before anything is fetched.

A source URL originates in web discovery, so it is attacker-influenceable text
that this process is about to hand to an HTTP client and to a third-party binary.
Two properties of that binary make an unchecked URL worse than it looks: its input
argument accepts a local path as readily as a URL, and its bulk mode will take the
list of URLs it fetches *out of a file it reads*. So the question "is this thing
even a remote address?" cannot be left to the fetcher.

**The check is on what a host is, never on which host it is.** A registry of
permitted hosts would make every new gallery, prize site or artist portfolio a code
change, and the catalogue deliberately keeps an open vocabulary of providers — so
pinning names here would quietly re-scope the product to whatever was known on the
day this was written. Publicly routable is a property the open web has and a
household's own LAN does not, which is the distinction actually being drawn.

**This is a pre-flight, and it is defeatable by a name that resolves differently
the second time.** Nothing here pins an address: the binary performs its own
resolution and cannot be handed a socket, so a rebinding attack survives this
check. Recorded rather than papered over — the value is that it closes the
straightforward cases (a literal address, a `file://` URL, a `.local` name) and
raises the cost of the rest, not that it is a proof.
"""

import ipaddress
import socket
from collections.abc import Callable, Sequence
from typing import Final
from urllib.parse import urlsplit

#: The only schemes a source may be fetched over. `file` is absent for the reason
#: this module exists; `ftp`, `data` and the rest are absent because no provider
#: uses them and an unused scheme is only a way to be surprised.
ALLOWED_SCHEMES: Final[frozenset[str]] = frozenset({"http", "https"})

#: Resolves to a loopback address on most desktop systems and to whatever answers
#: mDNS on a home network, which is exactly the population this check exists to
#: keep out. Refused by suffix because the name never reaches a resolver here.
_MDNS_SUFFIX: Final[str] = ".local"

#: A resolver, so a test can state what a name resolves to rather than depending on
#: the network it runs on. Returns the addresses as strings.
Resolver = Callable[[str], Sequence[str]]


class UrlRefused(ValueError):
    """A URL was not fetched, and the message says which rule stopped it.

    A `ValueError` rather than a service error because the caller that catches it
    is the acquisition path, which turns it into a recorded fetch failure — the
    refusal is data about a source, not a fault in the process.
    """


def system_resolver(host: str) -> Sequence[str]:
    """Every address a name currently resolves to, IPv4 and IPv6 alike.

    Both families, because a check that looked only at IPv4 would pass any name
    with a private IPv6 answer — and on a home network with a router handing out
    unique-local addresses, that is not a hypothetical.
    """
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UrlRefused(f"{host!r} does not resolve: {exc}") from exc
    return [info[4][0] for info in infos]


def check_fetchable(url: str, *, resolve: Resolver = system_resolver) -> str:
    """Return the URL if it may be fetched, or raise `UrlRefused` saying why not.

    Returns the URL unchanged rather than a rewritten one. Normalising here would
    mean the string that was checked and the string that gets fetched are not the
    same string, and the whole value of this function is that they are.
    """
    if not url or not url.strip():
        raise UrlRefused("A source URL is empty, so there is nothing to fetch.")

    parts = urlsplit(url)
    if parts.scheme.lower() not in ALLOWED_SCHEMES:
        allowed = ", ".join(sorted(ALLOWED_SCHEMES))
        # Named rather than generic: `file:` is the case worth being loud about,
        # since it is the one that reads the loader's own disk.
        raise UrlRefused(f"{parts.scheme or '(no scheme)'!r} is not a fetchable scheme; only {allowed} are.")

    host = parts.hostname
    if not host:
        raise UrlRefused(f"{url!r} names no host to fetch from.")
    if host.lower().rstrip(".").endswith(_MDNS_SUFFIX):
        raise UrlRefused(f"{host!r} is a local-network name, which a source may never be.")

    for address in _addresses_of(host, resolve=resolve):
        if not _is_public(address):
            raise UrlRefused(f"{host!r} resolves to {address}, which is not a public address.")
    return url


def _addresses_of(host: str, *, resolve: Resolver) -> Sequence[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """The addresses to judge, whether the host was a literal or a name.

    A literal is judged directly and never resolved: sending `127.0.0.1` to a
    resolver is a round trip to be told what the string already says, and on some
    systems a resolver will happily answer for text that is not a name at all.
    """
    try:
        return [ipaddress.ip_address(host.strip("[]"))]
    except ValueError:
        pass

    resolved = [ipaddress.ip_address(address) for address in resolve(host)]
    if not resolved:
        # Distinct from a resolution failure: an empty answer means the name is
        # known and points nowhere, and fetching it would fail anyway — but
        # falling through with an empty list would pass the loop above silently.
        raise UrlRefused(f"{host!r} resolves to no addresses.")
    return resolved


def _is_public(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Whether an address belongs to the open internet rather than to this network.

    `is_global` is the stdlib's own answer to this question and is preferred to a
    hand-written list of ranges, which is how these checks acquire a gap. The other
    clauses are the families it does not fold in — multicast reads `is_global=True`
    on both families, so dropping that clause would let `224.0.0.1` and `ff02::1`
    through.

    **An IPv4-mapped IPv6 address is judged as the address it carries, and that
    unwrapping is deliberate even though it looks redundant.** How `ipaddress`
    classifies `::ffff:x.x.x.x` moved between interpreter versions: on 3.12
    `::ffff:8.8.8.8` reports `is_reserved=True`, and on 3.14 it reports
    `is_reserved=False, is_global=True`. Either version answers *this* function
    correctly for the private cases, which is why no input can distinguish the two
    — a mutation sweep finds nothing to kill here, and that is a statement about
    the sweep rather than about the branch. Unwrapping first makes the verdict a
    property of the address instead of a property of whichever CPython the plane
    was last upgraded to, on a check whose failure mode is reaching the operator's
    own network.
    """
    mapped = getattr(address, "ipv4_mapped", None)
    if mapped is not None:
        return _is_public(mapped)
    if address.is_loopback or address.is_link_local or address.is_private:
        return False
    if address.is_multicast or address.is_reserved or address.is_unspecified:
        return False
    return address.is_global
