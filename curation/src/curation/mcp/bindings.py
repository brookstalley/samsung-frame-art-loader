"""What each action calls, and how its answer is shaped for a model.

A binding does three things and nothing else: unpack the validated arguments,
call **one** service method, format the result. A binding that validates,
orders, or decides is the violation — that work belongs to the service, which
the HTTP handlers will call too. Two implementations of "list the catalogue"
diverge within weeks, and the divergence shows up as an agent and a click
disagreeing about the same catalogue.

Formatting is not logic and belongs here: tool results are shaped for a model
to read, HTTP responses for a UI to render, and forcing one shape on both is
what the shared service layer exists to avoid.
"""

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any, Final

from curation.mcp.envelope import ok
from curation.mcp.registry import HELP_ACTION, RegistryError
from curation.mcp.tools import TOOLS
from curation.persistence.records import Artist, Artwork
from curation.services.catalogue import ArtworkDetail, ArtworkListing, CatalogueService

#: A bound action: validated arguments in, a result payload out.
Binding = Callable[[CatalogueService, Mapping[str, Any]], dict[str, Any]]


def _list_artworks(service: CatalogueService, arguments: Mapping[str, Any]) -> dict[str, Any]:
    listing = service.list_artworks(
        status=arguments.get("status"),
        limit=arguments.get("limit"),
        offset=arguments.get("offset", 0),
    )
    return ok(
        artworks=[_summary(entry) for entry in listing.entries],
        count=len(listing.entries),
        total=listing.total,
        truncated=listing.truncated,
        notice=_truncation_notice(listing),
    )


def _get_artwork(service: CatalogueService, arguments: Mapping[str, Any]) -> dict[str, Any]:
    return ok(artwork=_full(service.get_artwork(arguments["artwork_id"])))


#: Every built action, keyed by tool and action name. A tool absent from here
#: answers `help` and nothing else, which is what its registry record says.
BINDINGS: Final[Mapping[tuple[str, str], Binding]] = {
    ("art_catalogue", "list"): _list_artworks,
    ("art_catalogue", "get"): _get_artwork,
}


def _check_bindings_match_registry() -> None:
    """Refuse a surface whose declarations and wiring disagree.

    Availability is otherwise reconstructed from three separate signals — the
    record's `unavailable_note`, the actions it declares, and the keys here —
    and nothing reconciles them. Both halves of a disagreement are silent in
    their own way: an action declared with no binding reaches a runtime branch
    that reports a defect to the caller, and a binding for an undeclared action
    is dead code that reads as a working feature. Checked at import, where the
    registry's other structural defects already fail, because the alternative
    is a client discovering it.
    """
    declared = {(tool.name, name) for tool in TOOLS for name in tool.action_names if name != HELP_ACTION}
    bound = set(BINDINGS)

    if unbound := sorted(declared - bound):
        raise RegistryError(f"Declared but not bound: {unbound}. Every non-help action needs a binding.")
    if unknown := sorted(bound - declared):
        raise RegistryError(f"Bound but not declared: {unknown}. Every binding needs a registry action.")


_check_bindings_match_registry()


def _truncation_notice(listing: ArtworkListing) -> str | None:
    """Say what was left out, or say nothing.

    A silently short list is indistinguishable from a complete one, which is
    how a caller concludes the catalogue holds twenty works when it holds
    eighty-four.
    """
    if not listing.truncated:
        return None
    shown = len(listing.entries)
    return f"showing {shown} of {listing.total}; raise limit or narrow with status to see the rest"


def _summary(entry: ArtworkDetail) -> dict[str, Any]:
    """The fields needed to choose a work. `get` returns the rest."""
    return {
        "artwork_id": entry.artwork.id,
        "title": entry.artwork.title,
        "artist": None if entry.artist is None else entry.artist.name,
        "date_created": entry.artwork.date_created,
        "status": str(entry.artwork.status),
    }


def _full(entry: ArtworkDetail) -> dict[str, Any]:
    return {
        **_artwork_fields(entry.artwork),
        "artist": None if entry.artist is None else _artist_fields(entry.artist),
    }


def _artwork_fields(artwork: Artwork) -> dict[str, Any]:
    return {
        "artwork_id": artwork.id,
        "title": artwork.title,
        # Free text, exactly as the source gave it: "1931", "c. 1650",
        # "1888-89". Normalising it would erase the difference between a known
        # year and an estimated one.
        "date_created": artwork.date_created,
        "medium": artwork.medium,
        "dimensions": artwork.dimensions,
        "description": artwork.description,
        # Provenance and source quality. It gates nothing.
        "rights": artwork.rights,
        "status": str(artwork.status),
        "accepted_at": _moment(artwork.accepted_at),
        "created_at": _moment(artwork.created_at),
    }


def _artist_fields(artist: Artist) -> dict[str, Any]:
    return {
        "artist_id": artist.id,
        "name": artist.name,
        "nationality": artist.nationality,
        "born": artist.born,
        "died": artist.died,
        "lifespan_text": artist.lifespan_text,
        "biography": artist.biography,
    }


def _moment(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()
