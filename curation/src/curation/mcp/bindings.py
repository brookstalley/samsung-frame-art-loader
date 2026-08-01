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

from curation.manifest.builder import ManifestBuild
from curation.mcp.envelope import ok
from curation.mcp.registry import HELP_ACTION, RegistryError
from curation.mcp.tools import TOOLS
from curation.persistence.records import Artist, Artwork, Directive, Theme
from curation.services.catalogue import MAX_LIST_LIMIT, ArtworkDetail, ArtworkListing
from curation.services.container import Services
from curation.services.display import UNSET

#: A bound action: validated arguments in, a result payload out. Every binding
#: takes the whole container rather than the one service it happens to need, so
#: an action moving between concerns is not also a change to the dispatcher.
Binding = Callable[[Services, Mapping[str, Any]], dict[str, Any]]


def _list_artworks(services: Services, arguments: Mapping[str, Any]) -> dict[str, Any]:
    listing = services.catalogue.list_artworks(
        status=arguments.get("status"),
        limit=arguments.get("limit"),
        offset=arguments.get("offset", 0),
    )
    return ok(
        artworks=[_summary(entry) for entry in listing.entries],
        count=len(listing.entries),
        total=listing.total,
        # Echoed so a page describes its own place in the set: a caller told to
        # page with `offset` needs to know which one produced this.
        limit=listing.limit,
        offset=listing.offset,
        truncated=listing.truncated,
        notice=_truncation_notice(listing),
    )


def _get_artwork(services: Services, arguments: Mapping[str, Any]) -> dict[str, Any]:
    return ok(artwork=_full(services.catalogue.get_artwork(arguments["artwork_id"])))


def _list_themes(services: Services, arguments: Mapping[str, Any]) -> dict[str, Any]:
    themes = services.display.list_themes()
    return ok(themes=[_theme_fields(theme) for theme in themes], count=len(themes))


def _get_theme(services: Services, arguments: Mapping[str, Any]) -> dict[str, Any]:
    theme_id = arguments["theme_id"]
    return ok(
        theme=_theme_fields(services.display.get_theme(theme_id)),
        works=[_summary(entry) for entry in services.display.theme_works(theme_id)],
    )


def _create_theme(services: Services, arguments: Mapping[str, Any]) -> dict[str, Any]:
    theme = services.display.add_theme(name=arguments["name"], description=arguments.get("description"))
    return ok(theme=_theme_fields(theme))


def _update_theme(services: Services, arguments: Mapping[str, Any]) -> dict[str, Any]:
    # `UNSET` for anything the caller did not name, so updating one field does
    # not clear the others — null is a meaningful value for all three.
    theme = services.display.update_theme(
        arguments["theme_id"],
        name=arguments.get("name"),
        description=arguments.get("description", UNSET),
        rotation_interval_seconds=arguments.get("rotation_interval_seconds", UNSET),
        shuffle=arguments.get("shuffle", UNSET),
    )
    return ok(theme=_theme_fields(theme))


def _delete_theme(services: Services, arguments: Mapping[str, Any]) -> dict[str, Any]:
    services.display.delete_theme(arguments["theme_id"])
    return ok(deleted=arguments["theme_id"])


def _add_to_theme(services: Services, arguments: Mapping[str, Any]) -> dict[str, Any]:
    membership = services.display.add_to_theme(
        theme_id=arguments["theme_id"],
        artwork_id=arguments["artwork_id"],
        position=arguments.get("position"),
    )
    return ok(theme_id=membership.theme_id, artwork_id=membership.artwork_id, position=membership.position)


def _remove_from_theme(services: Services, arguments: Mapping[str, Any]) -> dict[str, Any]:
    services.display.remove_from_theme(theme_id=arguments["theme_id"], artwork_id=arguments["artwork_id"])
    return ok(theme_id=arguments["theme_id"], removed=arguments["artwork_id"])


def _reorder_in_theme(services: Services, arguments: Mapping[str, Any]) -> dict[str, Any]:
    membership = services.display.move_in_theme(
        theme_id=arguments["theme_id"],
        artwork_id=arguments["artwork_id"],
        position=arguments.get("position"),
    )
    return ok(theme_id=membership.theme_id, artwork_id=membership.artwork_id, position=membership.position)


def _activate_theme(services: Services, arguments: Mapping[str, Any]) -> dict[str, Any]:
    # Activating publishes, so this answers with the same shape as `sync` — the
    # caller needs to know how much of the theme actually reached the wall.
    return _built(services.display.activate_theme(arguments["theme_id"]))


def _wall_status(services: Services, arguments: Mapping[str, Any]) -> dict[str, Any]:
    reading = services.display.wall_status()
    return ok(
        observation=reading.describe(),
        display_plane_has_reported=not reading.absent,
        reported_at=_moment(reading.reported_at),
        age_seconds=reading.age_seconds,
        problem=reading.problem,
        reported=reading.contents,
    )


def _sync(services: Services, arguments: Mapping[str, Any]) -> dict[str, Any]:
    return _built(services.display.sync(arguments.get("theme_id")))


def _built(build: ManifestBuild) -> dict[str, Any]:
    """What a manifest build looks like to a caller. Shared by `sync` and `activate`.

    One shape for both, because they answer the same question — what is on the
    wall now, and what is not — and two shapes would let a caller learn the
    exclusions from one path and not the other.
    """
    return ok(
        theme=_theme_fields(build.theme),
        on_the_wall=[{"artwork_id": entry.work_id, "title": entry.label["title"]} for entry in build.entries],
        # Never omitted when empty: a caller that saw this key only sometimes
        # would learn to read its absence as "everything is fine", which is
        # exactly the silence the exclusion report exists to break.
        not_displayable=[
            {
                "artwork_id": exclusion.work_id,
                "title": exclusion.title,
                "reason": str(exclusion.reason),
                "detail": exclusion.detail,
            }
            for exclusion in build.exclusions
        ],
        considered=build.considered,
        rotation={"interval_seconds": build.rotation_interval_seconds, "shuffle": build.shuffle},
        notice=_sync_notice(build),
    )


def _show_now(services: Services, arguments: Mapping[str, Any]) -> dict[str, Any]:
    directive = services.display.show_work_now(arguments["artwork_id"])
    return ok(**_directive_fields(directive))


def _next(services: Services, arguments: Mapping[str, Any]) -> dict[str, Any]:
    return ok(**_directive_fields(services.display.step_display()))


#: Every built action, keyed by tool and action name. A tool absent from here
#: answers `help` and nothing else, which is what its registry record says.
BINDINGS: Final[Mapping[tuple[str, str], Binding]] = {
    ("art_catalogue", "list"): _list_artworks,
    ("art_catalogue", "get"): _get_artwork,
    ("art_theme", "list"): _list_themes,
    ("art_theme", "get"): _get_theme,
    ("art_theme", "create"): _create_theme,
    ("art_theme", "update"): _update_theme,
    ("art_theme", "delete"): _delete_theme,
    ("art_theme", "add"): _add_to_theme,
    ("art_theme", "remove"): _remove_from_theme,
    ("art_theme", "reorder"): _reorder_in_theme,
    ("art_theme", "activate"): _activate_theme,
    ("art_display", "status"): _wall_status,
    ("art_display", "sync"): _sync,
    ("art_display", "show_now"): _show_now,
    ("art_display", "next"): _next,
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
    # The limit is named rather than merely referred to: "raise limit" is advice a
    # caller cannot act on without knowing what it currently is, and a caller who
    # passed none is looking at a default it never chose. At the ceiling the advice
    # changes, because telling someone to raise a number that is already the
    # maximum sends them to a refusal — `offset` is the move there, and it is on
    # the same action.
    #
    # The position is reported rather than only the count, for the same reason: a
    # message that steers a caller to `offset` and then reads identically at every
    # offset gives them no way to see that paging moved.
    first = listing.offset + 1
    last = listing.offset + len(listing.entries)
    remedy = "page with offset" if listing.limit >= MAX_LIST_LIMIT else "raise limit or page with offset"
    ceiling = ", the maximum" if listing.limit >= MAX_LIST_LIMIT else ""
    return (
        f"showing {first}-{last} of {listing.total} at limit {listing.limit}{ceiling}; "
        f"{remedy}, or narrow with status to see the rest"
    )


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


def _theme_fields(theme: Theme) -> dict[str, Any]:
    return {
        "theme_id": theme.id,
        "name": theme.name,
        "description": theme.description,
        "is_active": theme.is_active,
        # Null means "inherit the deployment default" rather than "unset", so it
        # is reported as it is stored rather than resolved to a number that would
        # read as a choice the curator made.
        "rotation_interval_seconds": theme.rotation_interval_seconds,
        "shuffle": theme.shuffle,
        "created_at": _moment(theme.created_at),
    }


def _directive_fields(directive: Directive) -> dict[str, Any]:
    return {
        "sequence": directive.sequence,
        "pinned_work_id": directive.pinned_work_id,
        # The contract's own words. This action cannot observe the television, so
        # a result implying it had changed would be asserting something curation
        # has no way to know.
        "notice": "The directive is written. The wall converges within about a second; this is not a confirmation it has.",
    }


def _sync_notice(build: ManifestBuild) -> str:
    """How much of the theme reached the wall, plus the pointer this surface can give.

    The counts come from the build itself, so this surface and the browser one
    cannot disagree about them. Only the field name is this surface's own — a
    model reading a tool result has `not_displayable` in front of it, and naming
    it is worth a clause that would be meaningless anywhere else.
    """
    summary = build.summarise()
    if not build.exclusions:
        return summary
    return f"{summary} See not_displayable for each one and why."
