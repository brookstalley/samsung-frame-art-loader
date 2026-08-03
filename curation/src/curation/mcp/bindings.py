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
from curation.mcp.envelope import ImageBlock, ok, with_images
from curation.mcp.registry import HELP_ACTION, RegistryError
from curation.mcp.tools import TOOLS
from curation.persistence.discovery_records import CandidateWork, DiscoveryRun, InitiatedBy, RunKind, RunStatus
from curation.persistence.records import Artist, Artwork, Directive, Theme
from curation.services.catalogue import MAX_LIST_LIMIT, ArtworkDetail, ArtworkListing
from curation.services.container import Services
from curation.services.display import UNSET
from curation.services.previews import InlinePreview
from curation.services.review import MAX_REVIEW_LIMIT, CandidatePage, CandidateView, InstanceListing, InstanceView
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


def _resolve_images(services: Services, arguments: Mapping[str, Any]) -> dict[str, Any]:
    run = services.runner.resolve_images(
        candidate_work_ids=arguments["work_ids"],
        initiated_by=InitiatedBy.MCP_CLIENT,
    )
    return ok(
        **_run_fields(run),
        notice=(
            "The re-search is under way; this is a handle, not a result. Call "
            f"art_discovery(action='status', run_id='{run.id}'), which holds until something changes. "
            "What it spends is added to the run that first proposed these works."
        ),
    )


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


def _list_candidate_works(services: Services, arguments: Mapping[str, Any]) -> dict[str, Any]:
    page = services.review.list_works(
        arguments["run_id"],
        limit=arguments.get("limit"),
        offset=arguments.get("offset", 0),
    )
    pictures = _Pictures()
    works = [_candidate_summary(entry, pictures) for entry in page.entries]
    return with_images(
        ok(
            run_id=page.run.id,
            run_status=str(page.run.status),
            works=works,
            count=len(works),
            total=page.total,
            # Echoed so a page describes its own place in the set, exactly as the
            # catalogue's listing does: a caller told to page needs to know which
            # offset produced this one.
            limit=page.limit,
            offset=page.offset,
            truncated=page.truncated,
            notice=_joined(pictures.notice(), _review_truncation_notice(page)),
        ),
        pictures.blocks,
    )


def _get_candidate_work(services: Services, arguments: Mapping[str, Any]) -> dict[str, Any]:
    pictures = _Pictures()
    described = _candidate_detail(services.review.get_work(arguments["work_id"]), pictures)
    # No `run_id` beside the work: the work carries `discovery_run_id`, and one
    # fact under two names in one payload is a fact that can be read twice and
    # believed once.
    return with_images(ok(work=described, notice=pictures.notice()), pictures.blocks)


def _list_candidate_images(services: Services, arguments: Mapping[str, Any]) -> dict[str, Any]:
    listing = services.review.list_images(arguments["work_id"])
    pictures = _Pictures()
    instances = [_instance_fields(instance, pictures) for instance in listing.instances]
    return with_images(
        ok(
            work_id=listing.work.id,
            title=listing.work.proposed_title,
            images=instances,
            count=len(instances),
            held=listing.held,
            truncated=listing.truncated,
            notice=_joined(
                pictures.notice(),
                _no_instances_notice(instances),
                _instances_truncation_notice(listing),
            ),
        ),
        pictures.blocks,
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
    ("art_discovery", "resolve_images"): _resolve_images,
    ("art_discovery", "list_runs"): _list_runs,
    ("art_discovery", "spend"): _spend,
    ("art_review", "list_works"): _list_candidate_works,
    ("art_review", "get_work"): _get_candidate_work,
    ("art_review", "list_images"): _list_candidate_images,
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
        # How the intent was read, in the engine's own words. Carried beside the
        # verbatim intent because a work list is judged against the reading of the
        # request rather than against its wording — "you asked for recent, I took
        # that to mean 2026 prize winners" is what makes a surprising list
        # explicable instead of merely wrong. Null while a run is still working:
        # nothing has read the intent yet.
        "strategy": run.strategy,
        "approval_required": run.approval_required,
        "estimated_cost_usd": None if run.estimated_cost_usd is None else str(run.estimated_cost_usd),
        "actual_cost_usd": None if run.actual_cost_usd is None else str(run.actual_cost_usd),
        "unresolved_work_count": run.unresolved_work_count,
        "parent_run_id": run.parent_run_id,
        "started_at": _moment(run.started_at),
        "completed_at": _moment(run.completed_at),
    }


#: How many of a run's works one result may carry. **The list this caps is not
#: bounded by anything else**: phase 1 is deliberately uncapped — "you asked for
#: Dalí and I found 200 works" is the case it is written for — and the approval
#: gate is computed *after* the whole list is recorded, so it pauses the run
#: without shortening it. The run that stops at the gate is therefore the broad
#: one by construction, and a human decides it by reading exactly this payload.
#:
#: 100 because a work here is five short fields, about sixty tokens, so a full
#: page is ~6,000 — under the 10,000 at which a client warns, with room for the
#: rest of the result. Deliberately not shared with the catalogue's list ceiling:
#: that one bounds a limit a caller chose, this one bounds a list nobody asked
#: for the length of, and one number serving both would move for two reasons.
MAX_WORKS_LISTED: Final[int] = 100


def _work_summary(work: CandidateWork) -> dict[str, Any]:
    """One proposed work, in the fields an action taking a work id needs.

    Enough to choose and to act, and no more. What an instance looks like — its
    preview, its size on the wall, why it was selected — belongs to the review
    surface, which returns images alongside it; duplicating a slice of that here
    would be a second review card that drifts from the real one. This exists so
    a caller can obtain a work id at all: every count-only listing left the
    actions that take one with no reachable source for it.
    """
    return {
        "work_id": work.id,
        "title": work.proposed_title,
        "artist": work.proposed_artist,
        "verdict": str(work.verdict),
        "resolution_status": str(work.resolution_status),
    }


class _Pictures:
    """The image blocks one result carries, and each row's index into them.

    **A row cannot name its picture, so it names its position.** The protocol
    gives an image content block no identity to key on, and the blocks a result
    carries are only the instances that actually had a local copy — so the index
    a row needs is not its own position in the listing and cannot be derived from
    it. Handing out the index at the moment a block is appended is what keeps the
    two in step; computing it afterwards from a filtered list is the same fact
    derived twice, and the second derivation is the one that goes wrong when an
    instance's preview fails to decode.
    """

    def __init__(self) -> None:
        self.blocks: list[ImageBlock] = []

    def index_of(self, preview: InlinePreview | None) -> int | None:
        """Add this instance's picture and return its block index, or None for no picture."""
        if preview is None:
            return None
        self.blocks.append(ImageBlock(data=preview.data, media_type=preview.media_type))
        return len(self.blocks) - 1

    def notice(self) -> str | None:
        """State how the pictures line up with the rows, or that none came.

        Never silent when blocks are present: a model that has to infer the
        pairing will infer it from position in the *listing* rather than position
        in the blocks, which is right until the first instance without a local
        copy and wrong from then on.
        """
        if not self.blocks:
            return (
                "No images accompany this result — none of these instances has a local copy cached. "
                "Each row says why beside its preview_note."
            )
        return (
            f"{len(self.blocks)} image(s) follow the text, in the order the rows list them; each row's "
            "image_block_index says which is its own."
        )


def _no_instances_notice(instances: list[dict[str, Any]]) -> str | None:
    """Say that a work has no instances at all, which is a different thing from no pictures."""
    if instances:
        return None
    return (
        "No image instances have been found for this work. It is reported unresolved rather than "
        "dropped, because that is the signal a proposed work may not exist; art_discovery("
        "action='resolve_images') looks again."
    )


def _instances_truncation_notice(listing: InstanceListing) -> str | None:
    """Say which instances the card left out, and why no offset is offered.

    The listing's notice names paging as the remedy; this one deliberately does
    not, because there is none and there is also no need for one: what a full card
    omits is never an instance the caller could have chosen. Saying that is more
    useful than an affordance that does not exist, which is the failure the
    withheld action was withheld to avoid.

    **It says what was dropped, and deliberately claims nothing about row order.**
    Selectable instances get first claim on the card's slots, but the rows keep
    the store's ranking — so a card can read [selectable, refused, …, selectable],
    and a sentence promising the selectable ones "first" would send a caller to
    the top of a list where the alternate they want sits last. Which rows are
    still open is a per-row fact and is reported as one, on
    `rejected_for_this_work`.
    """
    if not listing.truncated:
        return None
    shown_surviving = sum(1 for instance in listing.instances if not instance.rejected)
    if listing.surviving_held == 0:
        # Reached when a work's every instance has been turned down and it holds
        # more than a cardful. Branch A is true here in the empty sense — no
        # choosable scan is missing because none exists — and saying so as
        # reassurance would be the wrong sentence in the one state where the
        # curator's next move is not on this surface at all.
        what_was_dropped = (
            "none of these are still open to you; every scan found for this work has been turned down, so "
            "art_discovery(action='resolve_images') is what finds more"
        )
    elif listing.shows_every_choosable_instance:
        what_was_dropped = (
            f"all {shown_surviving} scans still open to you are on this card — the ones omitted are scans "
            "you have already turned down"
        )
    else:
        # Reached only when the choosable scans alone fill the card, which means
        # no refused scan is on it and every one of them was omitted. Their rank
        # is *not* below what is shown — a refused scan is typically the
        # highest-confidence one there is, which is why it was offered and
        # refused — so the two kinds of omission are named separately rather than
        # under one claim about ranking.
        what_was_dropped = (
            f"this work has {listing.surviving_held} scans you could still choose and the card holds the "
            f"{shown_surviving} best of them; what is omitted is the rest of those, which rank below every "
            "scan shown, together with every scan you have already turned down"
        )
    return (
        f"Showing {len(listing.instances)} of {listing.held} scans found for this work; "
        f"{what_was_dropped}. Read rejected_for_this_work on each row rather than its position — "
        "the rows keep their ranking, so a scan you can still choose may sit anywhere on the card. "
        "There is no paging here."
    )


def _review_truncation_notice(page: CandidatePage) -> str | None:
    """Say what the page left out, and how to reach it.

    Unlike a run's status view — which caps its work list and can only report the
    omission — this listing takes an offset, so the notice names a remedy that
    exists. That is the paged listing the status notice points at.
    """
    if not page.truncated:
        return None
    first = page.offset + 1
    last = page.offset + len(page.entries)
    remedy = "page with offset" if page.limit >= MAX_REVIEW_LIMIT else "raise limit or page with offset"
    ceiling = ", the maximum" if page.limit >= MAX_REVIEW_LIMIT else ""
    return f"Showing {first}-{last} of {page.total} works at limit {page.limit}{ceiling}; {remedy} to see the rest."


def _candidate_summary(view: CandidateView, pictures: _Pictures) -> dict[str, Any]:
    """One proposed work as a *listing* shows it: enough to choose, and one picture.

    **Deliberately narrower than the detail view, and the budget is why.** Every
    row here carries an image block, so a page's cost is dominated by pictures —
    but only until the rows get wide enough to compete. Measured at forty works:
    the full instance shape put the text at ~7,000 tokens against the images'
    6,400, which together sit past the 10,000 at which a client warns. The same
    split the catalogue already draws — listings carry what is needed to choose,
    `get` returns the record — is what keeps a full page inside the budget.
    """
    return {
        "work_id": view.work.id,
        "title": view.work.proposed_title,
        # As phase 1 wrote it, unparsed. Matching it to a catalogue artist is
        # acceptance's job and does not happen until a work is promoted.
        "artist": view.work.proposed_artist,
        "verdict": str(view.work.verdict),
        "resolution_status": str(view.work.resolution_status),
        "instances_held": view.instances_held,
        "shown_image": None if view.shown is None else _shown_fields(view.shown, pictures),
    }


def _candidate_detail(view: CandidateView, pictures: _Pictures) -> dict[str, Any]:
    """One proposed work in full: why it was proposed, and its picture in full detail.

    Built field by field rather than by widening the listing shape, because
    `_shown_fields` *appends a block* as a side effect of assigning an index.
    Composing the two would picture this work twice — one instance, two identical
    blocks, and a caller charged for both.
    """
    return {
        "work_id": view.work.id,
        "title": view.work.proposed_title,
        "artist": view.work.proposed_artist,
        "verdict": str(view.work.verdict),
        "resolution_status": str(view.work.resolution_status),
        "instances_held": view.instances_held,
        "instances_surviving": view.instances_surviving,
        "shown_image": None if view.shown is None else _instance_fields(view.shown, pictures),
        # The engine's account of why this work answers the intent. A curator
        # judges a work against the reading of their request rather than against
        # its wording, which is what makes a surprising proposal explicable
        # instead of merely wrong. Too long to repeat on every row of a listing,
        # which is the other half of why the two shapes differ.
        "rationale": view.work.rationale,
        "discovery_run_id": view.work.discovery_run_id,
        "artwork_id": view.work.artwork_id,
        "decided_at": _moment(view.work.decided_at),
    }


def _shown_fields(instance: InstanceView, pictures: _Pictures) -> dict[str, Any]:
    """The pictured instance, as a listing row carries it.

    Carries the pair `api-contract.md` requires of a review surface — the fit
    verdict and the size on the wall — because those are exactly what a picture
    cannot say, and dropping them to save tokens would leave the rows looking
    complete while removing the reason the gate works.

    `is_on_offer` is here rather than inferred, because it is false in two very
    different situations a curator must not confuse with each other: a work whose
    only scans are below the floor, and one whose scans were all turned down.

    **No `image_id`.** Nothing a caller does from a listing takes one — the row's
    `work_id` is what every action here accepts — and choosing among a work's
    scans means reading them first, where `list_images` returns the id beside
    each. A uuid on forty rows is about 600 tokens spent on an argument no action
    at this level would accept.
    """
    fit = instance.fit
    return {
        "is_on_offer": instance.image.is_selected,
        "display_fit": None if fit is None else str(fit.fit),
        "renders_at_inches": None if fit is None else round(fit.rendered_long_edge_inches, 1),
        "image_block_index": pictures.index_of(instance.preview),
        # Both omitted when there is nothing to say, which is the common case.
        # A null repeated on forty rows is pure cost.
        **({} if instance.fit_note is None else {"fit_note": instance.fit_note}),
        **({} if instance.preview_note is None else {"preview_note": instance.preview_note}),
    }


def _instance_fields(instance: InstanceView, pictures: _Pictures) -> dict[str, Any]:
    """One image instance in full — what `list_images` shows about an alternate.

    Everything a curator weighing one scan against another needs: where it came
    from, how sure the match is, how good the file is, and why it was chosen. A
    listing carries a subset of this; the split is `_candidate_summary`'s.
    """
    image = instance.image
    fit = instance.fit
    return {
        # The id lives here and not on a listing row, because this is the level
        # at which a caller picks one scan out of several and needs to name it.
        "image_id": image.id,
        **_shown_fields(instance, pictures),
        "url": image.url,
        "provider": image.provider,
        # Reported as a fact about this work only. A rejected scan is excluded
        # from re-selection here and from nothing else — the painting stays
        # wanted, which is the whole reason instance suppression and work
        # suppression are different keys.
        "rejected_for_this_work": instance.rejected,
        "renders_at_pixels": None if fit is None else f"{fit.rendered_width}x{fit.rendered_height}",
        "estimated_width": image.estimated_width,
        "estimated_height": image.estimated_height,
        # Provenance and source quality, returned alongside. It gates nothing.
        "rights_status": None if image.rights_status is None else str(image.rights_status),
        "confidence": image.confidence,
        "quality_score": image.quality_score,
        "selection_rationale": image.selection_rationale,
    }


def _run_view(view: RunView) -> dict[str, Any]:
    """One run in full, with its works and what it has used of its search cap."""
    listed = list(view.works[:MAX_WORKS_LISTED])
    return ok(
        **_run_fields(view.run),
        works={
            "total": view.work_count,
            "resolved": view.resolved,
            "unresolved": view.unresolved,
            "pending": view.pending,
            # The works themselves, because the counts alone cannot be acted on —
            # every action taking a work id has this as its only reachable source.
            "each": [_work_summary(work) for work in listed],
            "listed": len(listed),
            "truncated": len(listed) < view.work_count,
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
        notice=_joined(_run_notice(view), _works_truncation_notice(view, len(listed))),
    )


def _joined(*sentences: str | None) -> str:
    return " ".join(sentence for sentence in sentences if sentence)


def _works_truncation_notice(view: RunView, listed: int) -> str | None:
    """Say what `each` left out, or say nothing.

    The contract's rule, applied where it bites hardest: a result that omits rows
    says so and says how many, never a silent cut. A short list read as a
    complete one is worse here than in a catalogue listing, because the count
    beside it is the *run's* count — so the two disagree in the same payload and
    a caller has no way to tell which is the whole truth.

    It names no way to fetch the rest, because there is none: `status` takes no
    offset, and a paged listing of a run's works arrives with the review surface.
    Promising an affordance that does not exist is the failure the withheld
    action was withheld to avoid.
    """
    if listed >= view.work_count:
        return None
    return (
        f"Only the first {listed} of this run's {view.work_count} works are listed; the rest are omitted to "
        "keep the result inside a client's token budget, not because anything is wrong with them."
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
                f"There are {view.work_count} works to find images for, but no image provider is configured "
                "in this deployment, so the run will stay here; cancel it when you are done reading it."
            )
        # A re-search never had a work list of its own to settle — the curator
        # named its works — so the sentence a discovery run gets would describe
        # a phase this run did not perform.
        if view.run.kind is RunKind.RESOLVE:
            return (
                f"This re-search is looking again for images of the {view.work_count} works it covers. "
                "Call status again to keep watching."
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
