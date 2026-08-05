"""Reaching a tile-manifest URL from the URL a Source actually carries.

**A Source's `url` is where a curator goes to check provenance, and that is not
always where the bytes are.** For a site the tile fetcher can read directly the
two coincide, and for a museum serving IIIF they do not: the recorded URL names
the object, while the fetcher needs the image service's manifest. Deriving one
from the other takes a question only the provider can answer, so it happens here,
at fetch time, against a provider that is asked.

Resolving rather than storing is deliberate. The manifest URL is a *derived*
value — it is composed from a base the museum advertises in its own responses —
so a stored copy would be a second place that base lives, free to go stale the
day the institution moves its image service. Asking costs one metadata request
against a fetch that is about to pull tens of megabytes of tiles.

**A provider that needs resolution and has none wired raises, and is never a
pass-through nor a recorded failure.** It is the same kind of problem as the tile
binary being absent: no source is at fault and retrying the work cannot help, so
it reaches the caller as a deployment fault. Recorded against the source instead,
it would send whoever reads it to the museum to look for a problem that is in this
deployment's wiring — and handed to the fetcher instead, it would produce exactly
that misleading row, which is the defect this module was written to close.
"""

from collections.abc import Callable, Mapping
from typing import Final

from curation.persistence.records import Source

#: Given the URL a Source carries, the URL the tile fetcher can read. Raises
#: rather than returning a sentinel: every failure here is either a URL the
#: provider does not recognise or a provider that could not be asked, and both
#: are worth a sentence naming which.
#:
#: **An implementation may raise `ImageSearchFailure` and nothing else**, and the
#: contract is named here because a `Callable` alias cannot carry it. The caller
#: translates that one type into a recorded failure against the source; anything
#: else propagates out of `acquire`, past the deliberate clauses at the tool
#: boundary, and reaches a curator as "failed unexpectedly" — the exact outcome
#: those clauses exist to prevent, and it would name no source, no provider and
#: no remedy. This matters because the seam is a declared extension point: the
#: container's map is overridable, so the next resolver is written by someone
#: reading this line and not the caller's `except` list. A resolver that talks to
#: something with its own exceptions wraps them here.
TileTargetResolver = Callable[[str], str]

#: Providers whose recorded URL is an identity and never a tile manifest, so a
#: fetch without a resolver cannot work. `artic` records the museum's object
#: link; Google Arts & Culture is deliberately absent because the tile fetcher
#: ships a reader for its pages, so its recorded URL *is* fetchable.
#:
#: A provider earns a place here by being unable to fetch without help — not by
#: being a museum. Getting it wrong in the safe-looking direction is what this
#: module exists to prevent, so the omission is the thing to check when a new
#: provider's fetches fail.
RESOLUTION_REQUIRED: Final[frozenset[str]] = frozenset({"artic"})


class TileTargetUnavailable(RuntimeError):
    """No tile manifest could be reached for this source."""


def resolve_tile_target(source: Source, *, resolvers: Mapping[str, TileTargetResolver]) -> str:
    """The URL to hand the tile fetcher for `source`.

    A provider with no resolver keeps the URL it recorded, which is right for
    every provider whose pages the fetcher reads on its own — unless the provider
    is one that cannot work that way, which is a wiring fault and is named as one.
    """
    resolver = resolvers.get(source.provider)
    if resolver is not None:
        return resolver(source.url)
    if source.provider in RESOLUTION_REQUIRED:
        raise TileTargetUnavailable(
            f"Sources from {source.provider!r} record the object's page rather than its image service, so "
            "one has to be resolved before tiles can be fetched, and this deployment has no resolver wired "
            f"for {source.provider!r}. Nothing was fetched. This is a configuration fault here, not a "
            "problem with the source."
        )
    return source.url
