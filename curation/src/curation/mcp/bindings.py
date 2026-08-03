"""What each action calls, and how its answer is shaped for a model.

A binding unpacks the validated arguments, calls **one** service method, and
formats the result. A binding that validates, orders, or decides is the
violation — that work belongs to the service, which the HTTP handlers call too.
Two implementations of "list the catalogue" diverge within weeks, and the
divergence shows up as an agent and a click disagreeing about the same
catalogue.

**One binding here departs**: answering "get theme" pairs the theme with its
works, two reads behind one action. That is the same composite-read shape the
HTTP surface departs in, and it is recorded alongside those under "Known
departures" in the project preferences rather than excused here. The rule binds
every other binding in this file, and binds the next one written.

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
from curation.persistence.discovery_records import DiscoveryRun, InitiatedBy, RunStatus
from curation.persistence.records import Artist, Artwork, Directive, Theme
from curation.services.catalogue import MAX_LIST_LIMIT, ArtworkDetail, ArtworkListing
from curation.services.container import Services
from curation.services.display import UNSET
from curation.services.runner import RunView

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


def _estimate(services: Services, arguments: Mapping[str, Any]) -> dict[str, Any]:
    estimate = services.runner.estimate(arguments.get("run_id"))
    return ok(
        phase=estimate.phase,
        # A string rather than a float: a price rendered through binary floating
        # point is a price that can come back as 0.12699999999999999.
        estimated_cost_usd=str(estimate.cost_usd),
        basis=estimate.basis,
        run_id=estimate.run_id,
        notice="Estimating costs nothing. This is the only art_discovery action that does not spend.",
    )


def _start_discovery(services: Services, arguments: Mapping[str, Any]) -> dict[str, Any]:
    run = services.runner.start(
        intent_text=arguments["intent"],
        # Provenance, never authorisation: every surface has identical authority,
        # and this records which one asked so that "who wanted forty Dalí
        # candidates" is answerable from the data.
        initiated_by=InitiatedBy.MCP_CLIENT,
    )
    return ok(
        **_run_fields(run),
        notice=(
            "The run is under way; this is a handle, not a result. Call "
            f"art_discovery(action='status', run_id='{run.id}'), which holds until something changes."
        ),
    )


def _run_status(services: Services, arguments: Mapping[str, Any]) -> dict[str, Any]:
    return _run_view(services.runner.run_status(arguments["run_id"]))


def _approve_run(services: Services, arguments: Mapping[str, Any]) -> dict[str, Any]:
    return _run_view(services.runner.approve(arguments["run_id"]))


def _decline_run(services: Services, arguments: Mapping[str, Any]) -> dict[str, Any]:
    return _run_view(services.runner.decline(arguments["run_id"]))


def _cancel_run(services: Services, arguments: Mapping[str, Any]) -> dict[str, Any]:
    return _run_view(services.runner.cancel(arguments["run_id"]))


def _list_runs(services: Services, arguments: Mapping[str, Any]) -> dict[str, Any]:
    runs = services.runner.list_runs(status=arguments.get("status"), kind=arguments.get("kind"))
    return ok(runs=[_run_fields(run) for run in runs], count=len(runs))


def _spend(services: Services, arguments: Mapping[str, Any]) -> dict[str, Any]:
    report = services.runner.spend_report(
        run_id=arguments.get("run_id"),
        year=arguments.get("year"),
        month=arguments.get("month"),
    )
    return ok(
        scope=report.scope,
        cost_usd=str(report.cost_usd),
        run_id=report.run_id,
        # What this run alone was billed, beside what asking cost altogether. A
        # run billed little whose re-searches cost ten times more is a fact worth
        # being able to see rather than one totalled away.
        run_direct_cost_usd=None if report.run_direct_usd is None else str(report.run_direct_usd),
        year=report.year,
        month=report.month,
    )


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
    ("art_discovery", "estimate"): _estimate,
    ("art_discovery", "start"): _start_discovery,
    ("art_discovery", "status"): _run_status,
    ("art_discovery", "approve"): _approve_run,
    ("art_discovery", "decline"): _decline_run,
    ("art_discovery", "cancel"): _cancel_run,
    ("art_discovery", "list_runs"): _list_runs,
    ("art_discovery", "spend"): _spend,
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


def _run_fields(run: DiscoveryRun) -> dict[str, Any]:
    """One run as a caller sees it.

    The terminal state is returned as itself and never collapsed into an
    ok/failed flag. An agent has to be able to tell "you are out of money" from
    "it broke" from "the process was restarted underneath it", because the
    correct response to each is different — stop, investigate, and simply run it
    again respectively.
    """
    return {
        "run_id": run.id,
        "kind": str(run.kind),
        "status": str(run.status),
        "initiated_by": str(run.initiated_by),
        "intent": run.intent_text,
        "strategy": run.strategy,
        # How the intent was read, in the engine's own words. Carried beside the
        # verbatim intent because a work list is judged against the reading of the
        # request rather than against its wording — "you asked for recent, I took
        # that to mean 2026 prize winners" is what makes a surprising list
        # explicable instead of merely wrong. Null while a run is still working:
        # nothing has read the intent yet.
        "approval_required": run.approval_required,
        "estimated_cost_usd": None if run.estimated_cost_usd is None else str(run.estimated_cost_usd),
        "actual_cost_usd": None if run.actual_cost_usd is None else str(run.actual_cost_usd),
        "unresolved_work_count": run.unresolved_work_count,
        "parent_run_id": run.parent_run_id,
        "started_at": _moment(run.started_at),
        "completed_at": _moment(run.completed_at),
    }


def _run_view(view: RunView) -> dict[str, Any]:
    """One run in full, with its works and what it has used of its search cap."""
    return ok(
        **_run_fields(view.run),
        works={
            "total": view.work_count,
            "resolved": view.resolved,
            "unresolved": view.unresolved,
            "pending": view.pending,
        },
        # Reported as two numbers rather than one verdict: the usage is this
        # run's own history and the allowance is the deployment's current
        # setting, so a run read after the setting changed shows both instead of
        # a boolean quietly recomputed against a rule it never ran under.
        searches={
            "used": view.searches_used,
            "allowance": view.search_allowance,
            "exhausted": view.searches_exhausted,
        },
        notice=_run_notice(view),
    )


def _run_notice(view: RunView) -> str:
    """What this run's state means, and what the caller can do about it.

    A state name tells a model what happened; this tells it what to do next,
    which is the part it otherwise has to guess. Every branch is reachable: the
    states enumerated here are the ones a run can be read in.
    """
    status = view.run.status
    if status is RunStatus.RESOLVING_WORKS:
        return "Phase 1 is working out which works match the intent. Call status again to keep watching."
    if status is RunStatus.AWAITING_APPROVAL:
        return (
            f"This run proposed {view.work_count} works, which is more than the configured threshold, so it "
            "stopped to ask. Approve it to let it look for images, or decline it — nothing more is spent "
            "until you do."
        )
    if status is RunStatus.RESOLVING_IMAGES:
        # Two different situations share this state, and which one it is comes
        # from the wiring rather than from a sentence written here — a hardcoded
        # answer was true until phase 2 was built and false the moment it was.
        if not view.image_resolution_available:
            return (
                f"The work list of {view.work_count} works is settled, but no image provider is configured "
                "in this deployment, so the run will stay here; cancel it when you are done reading it."
            )
        return (
            f"The work list of {view.work_count} works is settled and the run is looking for an image of each. "
            "Call status again to keep watching."
        )
    if status is RunStatus.COMPLETED:
        settled = f"This run finished: {view.resolved} of {view.work_count} works have an image."
        if view.unresolved:
            settled += (
                f" {view.unresolved} could not be matched to any image and are reported as unresolved "
                "rather than dropped, because that is the signal a proposed work may not exist."
            )
        if view.pending:
            # Held apart from unresolved on purpose. "We looked and it is not
            # there" and "we could not look" lead to opposite actions, and
            # collapsing them would tell a curator their painting does not exist
            # because a museum was briefly unreachable.
            settled += (
                f" {view.pending} could not be looked up at all — the image provider was unreachable for them, "
                "which says nothing about whether they exist. Re-run to try those again."
            )
        return settled
    if status is RunStatus.HALTED_BY_BUDGET:
        return (
            "The provider refused further spend, so this run stopped where it was. This is not a transient "
            "error: retrying will fail the same way until the credit limit resets or is raised."
        )
    if status is RunStatus.INTERRUPTED:
        return (
            "The process working on this run stopped underneath it — a restart or a crash, not a fault in the "
            "run. Start it again with the same intent; there is nothing to investigate."
        )
    if status is RunStatus.FAILED:
        return "This run hit an error and stopped. The server log has the details; this is worth investigating."
    if status is RunStatus.DECLINED:
        return "The work list was declined, so no images were looked for and nothing further was spent."
    if status is RunStatus.CANCELLED:
        return "This run was stopped on request. Anything it had already spent is still recorded against it."
    return f"This run {status}."


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
