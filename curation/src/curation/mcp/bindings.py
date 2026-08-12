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

import logging
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import Any, Final

from curation.acquisition.dezoomify import DezoomifyUnavailable
from curation.acquisition.preparation import PreparationResult
from curation.acquisition.service import AcquisitionOutcome, AcquisitionResult
from curation.acquisition.space import NotEnoughSpace
from curation.acquisition.tiles import TileTargetUnavailable
from curation.manifest.builder import ManifestBuild
from curation.mcp.envelope import ImageBlock, ok, with_images
from curation.mcp.registry import HELP_ACTION, RegistryError
from curation.mcp.tools import TOOLS
from curation.persistence.discovery_records import CandidateWork, DiscoveryRun, InitiatedBy, RunKind, RunStatus
from curation.persistence.records import Artist, Artwork, Directive, Source, Theme, Wall
from curation.services.catalogue import MAX_LIST_LIMIT, ArtworkDetail, ArtworkListing
from curation.services.container import Services
from curation.services.discovery import VerdictOutcome
from curation.services.display import UNSET, ThemePlacement, WallView, describe_wall_status
from curation.services.display_fit import DisplayFit
from curation.services.errors import ServiceError
from curation.services.previews import InlinePreview
from curation.services.review import MAX_REVIEW_LIMIT, CandidatePage, CandidateView, InstanceListing, InstanceView
from curation.services.runner import RunListing, RunView

#: A bound action: validated arguments in, a result payload out. Every binding
#: takes the whole container rather than the one service it happens to need, so
#: an action moving between concerns is not also a change to the dispatcher.
Binding = Callable[[Services, Mapping[str, Any]], dict[str, Any]]

log = logging.getLogger(__name__)


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


def _list_sources(services: Services, arguments: Mapping[str, Any]) -> dict[str, Any]:
    artwork_id = arguments["artwork_id"]
    sources = services.catalogue.list_sources(artwork_id)
    return ok(
        artwork_id=artwork_id,
        sources=[_source_fields(source) for source in sources],
        count=len(sources),
        notice=_sources_notice(sources),
    )


def _archive_artwork(services: Services, arguments: Mapping[str, Any]) -> dict[str, Any]:
    artwork = services.catalogue.archive_artwork(arguments["artwork_id"])
    return ok(
        artwork=_artwork_fields(artwork),
        notice="It is out of every theme's rotation until action='restore' brings it back. Nothing is deleted.",
    )


def _restore_artwork(services: Services, arguments: Mapping[str, Any]) -> dict[str, Any]:
    artwork = services.catalogue.restore_artwork(arguments["artwork_id"])
    return ok(
        artwork=_artwork_fields(artwork),
        notice="It is eligible for the wall again; a theme holding it will carry it at the next manifest build.",
    )


def _retry_acquisition(services: Services, arguments: Mapping[str, Any]) -> dict[str, Any]:
    try:
        result = services.acquisition.acquire(
            arguments["artwork_id"],
            source_id=arguments.get("source_id"),
        )
    # Translated rather than allowed to reach the generic handler. These are the
    # conditions acquisition deliberately raises for instead of recording,
    # because no source is at fault — and a caller told only that the call
    # "failed unexpectedly" would go looking at the museum. What each clause adds
    # is the **remedy**: the sentence naming what an operator changes to make the
    # refusal stop. That is a tool-boundary concern and it belongs here.
    #
    # The journal line is *not* here, and that is the division. It follows the
    # condition, so `AcquisitionService` emits it at the raise and every caller
    # gets it — a browser route added later inherits the signal instead of
    # inheriting silence. Adding a `_deployment_fault(...)` call back into these
    # clauses would log every MCP refusal twice.
    #
    # **Every raise-rather-record condition needs a clause here.** Adding one to
    # the service without one here is silent: the generic handler drops the
    # exception text, so the deliberate refusal arrives as the very "failed
    # unexpectedly" these clauses exist to prevent.
    except NotEnoughSpace as exc:
        raise ServiceError(
            f"Acquisition did not start: {exc} Free space on the art tree's disk, or lower MIN_FREE_BYTES "
            "if this deployment means to run closer to full."
        ) from exc
    except DezoomifyUnavailable as exc:
        raise ServiceError(
            f"Acquisition did not start: {exc} This is a deployment problem rather than a bad source — "
            "install dezoomify-rs, or set DEZOOMIFY_PATH to where it lives. Every source using "
            "acquisition_method='dezoomify' is affected, and no source is at fault."
        ) from exc
    except TileTargetUnavailable as exc:
        raise ServiceError(
            f"Acquisition did not start: {exc} Set ARTIC_USER_AGENT in .env to a string naming this "
            "deployment and a contact address — the museum's API is open, but it asks callers to identify "
            "themselves, and an object's image service can only be reached by asking. Every source from "
            "that provider is affected, and no source is at fault."
        ) from exc
    return ok(
        artwork_id=result.artwork_id,
        source_id=result.source_id,
        outcome=result.outcome.value,
        detail=result.detail,
        relative_path=result.relative_path,
        byte_size=result.byte_size,
        width=result.width,
        height=result.height,
        notice=_acquisition_notice(result),
    )


def _set_mat_color(services: Services, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Set a mat colour, or ask the model for one when none is given.

    **One action rather than two, because the parameter is the whole difference.**
    "Use this colour" and "pick me a colour" are the same request about the same
    field, differing in who decides — and a surface with `set_mat_color` beside a
    `choose_mat_color` would make a caller pick between them before knowing that
    only one of them costs anything. The tip says which does.
    """
    artwork_id = arguments["artwork_id"]
    hex_rgb = arguments.get("hex_rgb")
    if hex_rgb:
        result = services.preparation.set_mat(artwork_id, str(hex_rgb))
    else:
        result = services.preparation.choose_mat(artwork_id)
    return ok(
        artwork_id=result.artwork_id,
        hex_rgb=result.mat_hex,
        method=result.mat_method,
        outcome=result.outcome.value,
        detail=result.detail,
        relative_path=result.relative_path,
        # A string rather than a float: the ledger keeps money exact, and a
        # `Decimal` serialised through JSON would become the binary float this
        # whole path exists to avoid.
        cost_usd=str(result.cost_usd),
        notice=_mat_notice(result),
    )


def _mat_notice(result: PreparationResult) -> str | None:
    """What the recorded method means, when it means more than the word does.

    `dominant_color_fallback` is the one that has to speak up: it is the state
    the 2024 pipeline entered silently, leaving a mechanical colour and a
    considered one indistinguishable forever after. The caller asked a model to
    choose and did not get one, and only this line says so.
    """
    if result.mat_fallback_detail is None:
        return None
    return (
        f"The vision model did not choose this colour — it was derived from the artwork's own dominant "
        f"colour and darkened, because {result.mat_fallback_detail}. Setting hex_rgb yourself overrides it, "
        "and asking again may succeed if the cause was temporary."
    )


def _regenerate(services: Services, arguments: Mapping[str, Any]) -> dict[str, Any]:
    result = services.preparation.prepare(arguments["artwork_id"], force=bool(arguments.get("force")))
    return ok(
        artwork_id=result.artwork_id,
        outcome=result.outcome.value,
        detail=result.detail,
        relative_path=result.relative_path,
        hex_rgb=result.mat_hex,
        method=result.mat_method,
        # Present only when something was actually rendered. On `unchanged` there
        # is no fresh assessment to report, and repeating a stored one would be
        # answering a question this call did not ask.
        fit=None if result.fit is None else result.fit.value,
        rendered_long_edge_inches=result.rendered_long_edge_inches,
        # **Reported even though this action is usually free.** A work that has
        # never had a mat gets one chosen here, and that is a paid call — so a
        # field present only on the paying path would be indistinguishable from
        # one the caller forgot to look at. Always present, usually "0".
        cost_usd=str(result.cost_usd),
        notice=_regenerate_notice(result),
    )


def _regenerate_notice(result: PreparationResult) -> str | None:
    """Said out loud when the work is on the wall smaller than the floor allows.

    Not a refusal and not an error: the curator may have chosen this instance
    knowing it was small, and `nonfunctional-requirements.md` is explicit that
    such a work is rendered rather than hidden. But a canvas reported as composed
    with no mention of it would let a work quietly appear as a postage stamp in
    an enormous mat, which is the gap the floor exists to close.
    """
    notices = []
    if result.mat_fallback_detail is not None:
        # A first preparation chooses a mat, and that choice can fall back. Said
        # here as well as on `set_mat_color` because this is the action that
        # actually makes it happen for most works — `acquire` does not prepare,
        # so the mat a work ends up wearing is usually the one chosen on the
        # `regenerate` that follows.
        notices.append(
            f"This work had no mat, so one was chosen for it — but not by the vision model, because "
            f"{result.mat_fallback_detail}. It was derived from the artwork's own dominant colour and darkened."
        )
    if result.fit is DisplayFit.BELOW_FLOOR and result.rendered_long_edge_inches is not None:
        notices.append(
            f"This work renders at about {result.rendered_long_edge_inches:.1f} inches on the wall, below the "
            "configured floor, so it will appear small in a wide mat. It is on the wall regardless; "
            "art_review's re-search finds a larger scan if one exists."
        )
    return " ".join(notices) or None


def _acquisition_notice(result: AcquisitionResult) -> str | None:
    """What the outcome means for the work, when the outcome alone understates it."""
    if result.outcome is AcquisitionOutcome.PARTIAL:
        # Said out loud because `partial` reads like a failure and is not one:
        # the work is on the wall, with gaps, and asking again may close them.
        return (
            "The image is usable and the work holds it, but some tiles never arrived, so it has gaps. "
            "Retrying re-uses the tiles already fetched, so a second attempt is cheap and may complete it."
        )
    if result.outcome is AcquisitionOutcome.FAILED:
        return (
            "The work holds whatever image it had before; a failed fetch replaces nothing. "
            "art_catalogue(action='sources') shows the other sources this work has, if any."
        )
    if result.outcome is AcquisitionOutcome.KEPT_HELD:
        # The one outcome where the source did nothing wrong and the work still
        # changed nothing, so neither "acquired" nor "failed" describes it. Said in
        # full because the obvious next move — retry again — has the same result
        # until the tile server stops dropping tiles.
        return (
            "The fetch worked but came back with missing tiles, and the work already holds a better image, "
            "so nothing was replaced. Retrying repeats this until the source returns every tile; "
            "art_catalogue(action='sources') shows the work's other sources, if any."
        )
    return None


def _sources_notice(sources: Sequence[Source]) -> str | None:
    if not sources:
        # A catalogued work with no source cannot be re-acquired at all, which is
        # worth saying rather than leaving an empty list to be read as "none yet".
        return "This work records no source, so there is nothing to re-acquire it from."
    if not any(source.is_primary for source in sources):
        return (
            "No source is marked primary, so nothing records which one produced the held image. "
            "With more than one source, action='retry_acquisition' needs source_id until one has succeeded; "
            "with a single source it uses that one."
        )
    return None


def _list_themes(services: Services, arguments: Mapping[str, Any]) -> dict[str, Any]:
    # Where each theme hangs travels with it, because "which one is on the wall"
    # is what this listing is read to answer — and a caller that had to ask per
    # theme would ask once and guess after. The pairing is the service's, not
    # this binding's: the browser surface states the same fact.
    placements = services.display.survey_themes()
    return ok(themes=[_placement_fields(placement) for placement in placements], count=len(placements))


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
    # Hanging publishes, so this answers with the same shape as `sync` — the
    # caller needs to know how much of the theme actually reached the wall.
    return _built(services.display.activate_theme(arguments["theme_id"], wall_id=arguments["wall_id"]))


def _unhang(services: Services, arguments: Mapping[str, Any]) -> dict[str, Any]:
    services.display.clear_wall(arguments["wall_id"])
    return ok(
        wall_id=arguments["wall_id"],
        # The contract's own words: nothing is republished, so a result implying
        # the wall had gone blank would be wrong about the thing that matters.
        notice="Nothing is hanging there now. The wall goes on showing what it was showing until a theme is hung.",
    )


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
    listing = services.runner.list_runs(status=arguments.get("status"), kind=arguments.get("kind"))
    return ok(
        runs=[_run_summary(run) for run in listing.runs],
        count=len(listing.runs),
        total=listing.total,
        truncated=listing.truncated,
        notice=_runs_truncation_notice(listing),
    )


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
                _nothing_choosable_notice(listing),
                _instances_truncation_notice(listing),
            ),
        ),
        pictures.blocks,
    )


def _set_canonical(services: Services, arguments: Mapping[str, Any]) -> dict[str, Any]:
    chosen = services.discovery.select_image(arguments["image_id"], rationale=arguments.get("rationale"))
    # **No `is_on_offer`.** It was here, and it could only ever be `true`:
    # `select_image` either makes this instance the one on offer or raises, and a
    # raise returns no payload at all. A field with one reachable value restates
    # the envelope's own `success`, and its only possible defence would be a test
    # written to defend it — which is the reason `InstanceListing` dropped its
    # `run_id` rather than pinning it. Which scan is on offer is a question
    # `list_images` answers per row, where it has two answers.
    return ok(
        image_id=chosen.id,
        work_id=chosen.candidate_work_id,
        url=chosen.url,
        selection_rationale=chosen.selection_rationale,
    )


def _set_verdict(services: Services, arguments: Mapping[str, Any]) -> dict[str, Any]:
    outcome = services.discovery.set_verdict(
        arguments["work_id"],
        arguments["verdict"],
        reason=arguments.get("reason"),
    )
    work = outcome.work
    return ok(
        work_id=work.id,
        title=work.proposed_title,
        verdict=str(work.verdict),
        # None on a rejection, and the id of the minted work on an acceptance.
        # It is the handle every catalogue action takes, so an acceptance hands
        # back the thing a caller's next call needs rather than making them go
        # looking for the work they just created.
        artwork_id=work.artwork_id,
        decided_at=_moment(work.decided_at),
        # Both reported on every acceptance, empty included. A key present only
        # when an artist was minted would teach a caller to read its absence as
        # "nothing happened", which is the silence this pair exists to break —
        # the same rule `not_displayable` follows on the display surface.
        #
        # **Uncapped, and what bounds it is worth naming rather than assuming.**
        # `possible_duplicate_artists` holds artists already in the catalogue that
        # plausibly name the painter just minted, which `attribution` derives by
        # shared name tokens — so it is bounded by how many *held* painters share
        # a name with one new one, in a catalogue sized by a single wall. Two is a
        # lot. A cap here would truncate the one thing this field exists to make
        # visible, and the bound is a property of the data rather than of a limit
        # anybody chose.
        minted_artist=None if outcome.minted_artist is None else _artist_fields(outcome.minted_artist),
        possible_duplicate_artists=[_artist_fields(artist) for artist in outcome.duplicate_candidates],
        notice=_verdict_notice(outcome),
    )


def _reject_image(services: Services, arguments: Mapping[str, Any]) -> dict[str, Any]:
    work = services.discovery.reject_image(arguments["image_id"])
    return ok(
        image_id=arguments["image_id"],
        work_id=work.id,
        title=work.proposed_title,
        verdict=str(work.verdict),
        # The next move, in the payload rather than only in the tool's tips: a
        # caller arrives here having decided the scan is not good enough, and
        # the one thing that finds a better one is a different tool. Naming it
        # at the moment of rejection is what keeps "reject" from reading as a
        # request that something will act on.
        notice=(
            "The scan is turned down and cannot be offered for this work again. Nothing is searching for a "
            "replacement: art_discovery(action='resolve_images', work_ids=['"
            f"{work.id}']) is what looks, and it spends. Reject every scan you want re-searched first, then "
            "ask once."
        ),
    )


def _verdict_notice(outcome: VerdictOutcome) -> str | None:
    """Say what acceptance did that the work's own fields do not show.

    Only the artist. Minting one is the single part of a promotion a curator can
    neither see in the accepted work nor undo from it — a duplicate row looks
    exactly like a painter newly encountered — so it is said in words at the
    moment it happens, where a field on a payload nobody re-reads would not
    reach them.
    """
    minted = outcome.minted_artist
    # Both conditions rather than the one that carries the message. Near-misses
    # are reported only alongside a mint, so `minted is None` here is currently
    # unreachable — but the sentence names the minted row, and deriving that it
    # exists from a *different* field being non-empty is how a payload comes to
    # say `None` where a name belongs the day the service reports near-misses
    # for anything else.
    if minted is None or not outcome.duplicate_candidates:
        return None
    names = ", ".join(repr(artist.name) for artist in outcome.duplicate_candidates)
    return (
        f"A new artist {minted.name!r} was recorded, and the catalogue already holds {names}. They may be "
        "the same painter under different spellings; matching is exact, because a wrong merge puts another "
        "painter's name on a label and leaves no trace. Both rows stand until someone decides."
    )


def _wall_status(services: Services, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Every wall's heartbeat, and one sentence across them.

    **All the walls rather than one**, and without a `wall_id` to narrow it. The
    question this action is asked is "is anything wrong", and an action that
    answered it about one room would let a model report a healthy installation
    having looked at the room that was fine.
    """
    seen = services.display.survey_wall_status()
    return ok(
        # Composed from the readings just taken rather than from a second pass,
        # so the sentence and the list below it cannot describe two different
        # instants — and from the shared function, so it cannot differ in
        # wording from what the browser panel states.
        observation=describe_wall_status(seen),
        walls=[
            {
                "wall_id": each.wall.id,
                "wall_name": each.wall.name,
                "observation": each.heartbeat.describe(),
                "display_plane_has_reported": not each.heartbeat.absent,
                "reported_at": _moment(each.heartbeat.reported_at),
                "age_seconds": each.heartbeat.age_seconds,
                "problem": each.heartbeat.problem,
                "reported": each.heartbeat.contents,
            }
            for each in seen
        ],
        count=len(seen),
    )


def _sync(services: Services, arguments: Mapping[str, Any]) -> dict[str, Any]:
    return _built(services.display.sync(arguments["wall_id"], arguments.get("theme_id")))


def _list_walls(services: Services, arguments: Mapping[str, Any]) -> dict[str, Any]:
    views = services.display.survey_walls()
    return ok(walls=[_wall_view_fields(view) for view in views], count=len(views))


def _add_wall(services: Services, arguments: Mapping[str, Any]) -> dict[str, Any]:
    return ok(wall=_wall_fields(services.display.add_wall(name=arguments["name"])))


def _built(build: ManifestBuild) -> dict[str, Any]:
    """What a manifest build looks like to a caller. Shared by `sync` and `activate`.

    One shape for both, because they answer the same question — what is on the
    wall now, and what is not — and two shapes would let a caller learn the
    exclusions from one path and not the other.
    """
    return ok(
        # The wall by name, so a caller reporting back says "in the living room"
        # rather than "on the wall" — a sentence that reads correctly today only
        # because there is one wall is one that silently becomes wrong.
        wall=_wall_fields(build.wall),
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
    directive = services.display.show_work_now(arguments["wall_id"], arguments["artwork_id"])
    return ok(**_directive_fields(directive))


def _next(services: Services, arguments: Mapping[str, Any]) -> dict[str, Any]:
    return ok(**_directive_fields(services.display.step_display(arguments["wall_id"])))


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
    ("art_review", "set_canonical"): _set_canonical,
    ("art_review", "set_verdict"): _set_verdict,
    ("art_review", "reject_image"): _reject_image,
    ("art_catalogue", "list"): _list_artworks,
    ("art_catalogue", "get"): _get_artwork,
    ("art_catalogue", "sources"): _list_sources,
    ("art_catalogue", "archive"): _archive_artwork,
    ("art_catalogue", "restore"): _restore_artwork,
    ("art_catalogue", "retry_acquisition"): _retry_acquisition,
    ("art_catalogue", "set_mat_color"): _set_mat_color,
    ("art_catalogue", "regenerate"): _regenerate,
    ("art_theme", "list"): _list_themes,
    ("art_theme", "get"): _get_theme,
    ("art_theme", "create"): _create_theme,
    ("art_theme", "update"): _update_theme,
    ("art_theme", "delete"): _delete_theme,
    ("art_theme", "add"): _add_to_theme,
    ("art_theme", "remove"): _remove_from_theme,
    ("art_theme", "reorder"): _reorder_in_theme,
    ("art_theme", "activate"): _activate_theme,
    ("art_theme", "unhang"): _unhang,
    ("art_display", "walls"): _list_walls,
    ("art_display", "add_wall"): _add_wall,
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


def _source_fields(source: Source) -> dict[str, Any]:
    """A source as the surface reports it.

    The same fields `GET /api/works/{id}` returns, off the same service read, so
    the two surfaces cannot describe a work's provenance differently.
    """
    return {
        "source_id": source.id,
        "url": source.url,
        "provider": source.provider,
        "source_class": str(source.source_class),
        "acquisition_method": str(source.acquisition_method),
        "rights_status": str(source.rights_status),
        "is_primary": source.is_primary,
        "confidence": source.confidence,
        "selection_rationale": source.selection_rationale,
        "last_fetch_status": None if source.last_fetch_status is None else str(source.last_fetch_status),
        "last_fetched_at": _moment(source.last_fetched_at),
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
        # The line written for a wall label. Distinct from `description`, which
        # is the holding institution's paragraph — an agent asked to write one
        # must not read the other back and think it is done.
        "commentary": artwork.commentary,
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
        # Which part of the name is the family name — the part the e-paper label
        # leads with. Null where nobody has said, and on a record that is not a
        # person at all.
        "family_name": artist.family_name,
        "given_name": artist.given_name,
    }


def _moment(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _theme_fields(theme: Theme) -> dict[str, Any]:
    return {
        "theme_id": theme.id,
        "name": theme.name,
        "description": theme.description,
        # Null means "inherit the deployment default" rather than "unset", so it
        # is reported as it is stored rather than resolved to a number that would
        # read as a choice the curator made.
        "rotation_interval_seconds": theme.rotation_interval_seconds,
        "shuffle": theme.shuffle,
        "created_at": _moment(theme.created_at),
    }


def _wall_fields(wall: Wall) -> dict[str, Any]:
    """One wall as a caller sees it: a place and a name, never a device."""
    return {"wall_id": wall.id, "name": wall.name, "created_at": _moment(wall.created_at)}


def _wall_view_fields(view: WallView) -> dict[str, Any]:
    """One wall, what hangs on it, and what it was last told to do."""
    return {
        **_wall_fields(view.wall),
        # Never omitted when nothing hangs: a key a caller saw only sometimes
        # would be read as "there is always something", and an empty wall is an
        # ordinary state this surface has to be able to state.
        "hanging": None if view.hanging is None else _theme_fields(view.hanging),
        "directive": _directive_fields(view.directive),
    }


def _placement_fields(placement: ThemePlacement) -> dict[str, Any]:
    """One theme and every wall showing it."""
    return {**_theme_fields(placement.theme), "hanging_on": [_wall_fields(wall) for wall in placement.walls]}


def _directive_fields(directive: Directive) -> dict[str, Any]:
    return {
        "wall_id": directive.wall_id,
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


#: What a run's *listing* row drops, and why each one is detail rather than
#: summary. `api-contract.md § Summary then detail`: a listing carries the fields
#: needed to decide, and `get` returns the record.
#:
#: `strategy` is the engine's reading of the intent in its own words — unbounded
#: prose, on every row, and the second of the two fields that made this listing
#: grow with what people typed rather than with how many runs there were. It is
#: not lost: `action='status'` returns one run in full, which is where a caller
#: goes once the listing has told them which run they want.
#:
#: The verbatim `intent` stays, deliberately, though it is unbounded too. It is
#: the only human-readable way to tell one run from another in a list — two runs
#: sharing a prefix are indistinguishable once it is truncated — so trimming it
#: would save bytes by making the listing stop answering the question it exists
#: for.
_RUN_DETAIL_ONLY: Final[frozenset[str]] = frozenset({"strategy"})


def _run_summary(run: DiscoveryRun) -> dict[str, Any]:
    """One run as a *listing* row shows it.

    Derived from `_run_fields` by subtraction rather than written out, so a field
    added to a run reaches the listing automatically and only a deliberate entry
    in `_RUN_DETAIL_ONLY` keeps it out. Written the other way round — two literal
    shapes — a new field would land in one and not the other, which is the drift
    the candidate-work projections took four coordinated edits to maintain before
    they were collapsed into one.
    """
    return {key: value for key, value in _run_fields(run).items() if key not in _RUN_DETAIL_ONLY}


def _runs_truncation_notice(listing: RunListing) -> str | None:
    """Say how much history was left out, or say nothing.

    **Names the filters rather than an offset, because there is no offset here.**
    `list_runs` takes `status` and `kind` and no paging parameter, so advice to
    page would send a caller to an argument the action does not accept — the
    failure the withheld action was withheld to avoid, one surface over. What a
    caller *can* do is narrow, and both filters are on this same action.

    Says the rows are the newest, because that is what makes the remainder
    ignorable: a caller who wanted a run from last March now knows the filter is
    the way to reach it, rather than assuming it has been forgotten.
    """
    if not listing.truncated:
        return None
    return (
        f"showing the {len(listing.runs)} most recent of {listing.total} runs. "
        "There is no paging on this action; narrow with status= or kind= to reach older ones."
    )


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

    **This is the one place the MCP surface writes this set of keys.** They were
    emitted with identical expressions at three sites in this module, so adding
    `provenance` took three coordinated edits and the next field added to
    `CandidateWork` would have reached some of them — one shape silently missing
    it, which is exactly the "an agent and a click disagree about the same
    catalogue" failure `http/models.py`'s docstring forbids. The richer shapes
    spread this and add their own keys. (Said as *the set* rather than as a
    count: this docstring claimed seven through two later fields, and a number
    kept in prose beside a dict is one that goes wrong on the edit that matters.)

    The HTTP surface's `CandidateWorkOut` is this set plus `rationale`, and that
    pairing is pinned by `tests/unit/test_surface_parity.py` rather than shared:
    the two surfaces format independently on purpose (`architecture.md`, Decision
    Log 2026-07-27), and a test makes divergence a failure at the moment of the
    edit without collapsing that independence.
    """
    return {
        "work_id": work.id,
        "title": work.proposed_title,
        # As phase 1 wrote it, unparsed. Matching it to a catalogue artist is
        # acceptance's job and does not happen until a work is promoted. On an
        # offered work this is the collection's own attribution instead, which is
        # the point: it is recorded verbatim and never reconciled with whatever
        # the model named.
        "artist": work.proposed_artist,
        # Whether the model named this work or the collection volunteered it.
        # On every row rather than only where it differs, because a label that
        # appears only sometimes is one a reader learns to stop looking for.
        "provenance": str(work.provenance),
        # Which browse query produced an offered work, and how many works it
        # matched; null on both for a proposed work. Carried here and not left to
        # the review surface because it is exactly the signal an agent choosing
        # between offers needs — `product-brief.md` asks that one-of-four-hundred
        # read differently from one-of-one, and that is a judgement an MCP caller
        # makes as readily as a curator.
        #
        # These do not inherit `rationale`'s HTTP-only exemption, which exists
        # because forty rows of the same prose blew the token budget this shape
        # is measured against. Two short facts are the cheap form of what that
        # prose was carrying, which is most of why they are facts now.
        "offered_for_artist": work.offered_for_artist,
        "offered_artist_matched": work.offered_artist_matched,
        "verdict": str(work.verdict),
        "resolution_status": str(work.resolution_status),
        "unresolved_reason": _reason(work),
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
        "dropped; `unresolved_reason` says which kind of nothing, and only `not_held` suggests the "
        "work may not exist — the others mean the collection has it and cannot offer it usably, or "
        "that you have already turned down everything it offered. art_discovery("
        "action='resolve_images') looks again."
    )


def _instances_truncation_notice(listing: InstanceListing) -> str | None:
    """Say which instances the card left out, and why no offset is offered.

    The listing's notice names paging as the remedy; this one deliberately does
    not, because there is none and no need for one: nothing omitted is both
    choosable and better than what is shown. That is weaker than "what is omitted
    could not have been chosen" — a card can omit choosable scans, once those
    alone outrun the cap — and the weaker claim is the one that is true. Saying it
    is more useful than an affordance that does not exist, which is the failure
    the withheld action was withheld to avoid.

    **It names what was dropped, and never implies that position sorts it.**
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
        # Nothing is choosable, so every sentence this function knows how to say
        # about choosable scans is vacuous — **including the tail**, which is why
        # this branch returns rather than falling through to it. Both halves said
        # the same wrong thing in different words: "all 0 scans still open to you
        # are on this card" reads as reassurance directly after
        # `_nothing_choosable_notice` reported none are open, and "a scan you can
        # still choose may sit anywhere on the card" advises reading a per-row
        # field to tell apart rows that are all the same. Removing only the first
        # left the second, which is exactly what happened once.
        return (
            f"Showing {len(listing.instances)} of {listing.held} scans found for this work; the ones "
            "omitted are also scans you have already turned down. There is no paging here."
        )
    if listing.shows_every_choosable_instance:
        # Every scan the curator can act on is here, so what fell off is refused
        # scans only.
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
        # under one claim about ranking. The refused clause is conditional because
        # this state does not require any to exist.
        also_refused = listing.held - listing.surviving_held
        what_was_dropped = (
            f"this work has {listing.surviving_held} scans you could still choose and the card holds the "
            f"{shown_surviving} best of them; what is omitted is the rest of those, which rank below every "
            "scan shown"
        ) + (f", together with the {also_refused} you have already turned down" if also_refused else "")
    return (
        f"Showing {len(listing.instances)} of {listing.held} scans found for this work; "
        f"{what_was_dropped}. Read rejected_for_this_work on each row rather than its position — "
        "the rows keep their ranking, so a scan you can still choose may sit anywhere on the card. "
        "There is no paging here."
    )


def _nothing_choosable_notice(listing: InstanceListing) -> str | None:
    """Say when a card holds pictures but no scan the curator can act on.

    Independent of truncation, which is the point: a work whose every scan was
    turned down is the ordinary result of rejecting alternates one at a time, and
    it far more often holds a handful than more than a cardful. Folding this into
    the truncation notice made it reach only the works with thirteen or more
    scans — the rare ones — and stay silent on exactly the common case.

    It names the paid action rather than leaving a curator to infer it, because
    this surface has no remedy of its own to offer: every row on the card is
    evidence of a decision already taken, and looking again costs money and lives
    on `art_discovery`.
    """
    if not listing.instances or listing.surviving_held:
        return None
    return (
        f"None of the {listing.held} scans found for this work are still open to you — every one has been "
        "turned down. art_discovery(action='resolve_images') searches again for a better one; it spends, "
        "and it is the only thing that changes this."
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


def _reason(work: CandidateWork) -> str | None:
    """Which kind of nothing, beside the status that raises the question.

    Carried on every shape that carries `resolution_status`, because the two are
    one answer: a caller holding "unresolved" and nothing else cannot tell a
    title the collection does not have from a scan too small for the wall, and
    would have to fetch each work in turn to find out — which costs more than the
    field it was saving.
    """
    return str(work.unresolved_reason) if work.unresolved_reason else None


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
        **_work_summary(view.work),
        "instances_held": view.instances_held,
        "shown_image": None if view.shown is None else _shown_fields(view.shown, pictures),
    }


def _candidate_detail(view: CandidateView, pictures: _Pictures) -> dict[str, Any]:
    """One proposed work in full: why it was proposed, and its picture in full detail.

    **Does not compose `_candidate_summary`**, because `_shown_fields` *appends a
    block* as a side effect of assigning an index. Calling the listing shape here
    would picture this work twice — one instance, two identical blocks, and a
    caller charged for both.

    It does compose `_work_summary`, and the difference is the whole point: that
    one is side-effect-free, and it is precisely the seven text keys this shape
    used to repeat. The argument above is about the *image* half and never
    reached them.
    """
    return {
        **_work_summary(view.work),
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
            # The curator approved a work list of a stated size, and a supplement
            # adds to it. Reported apart because a single total describes a run
            # as having found more of what was asked for than it did — with
            # twelve offered works behind one unresolved proposal, a merged
            # "12 of 13 have an image" is a resolution rate the run never
            # achieved (`product-brief.md` flow 2).
            "proposed": view.proposed_count,
            "offered": view.offered_count,
            "resolved": view.resolved,
            # The numerator any resolution rate is stated over, and it is here
            # because the notice beside it already quotes this figure. Without
            # it a caller can only compute `resolved / proposed` — `resolved`
            # counts every provenance — which is the mixed rate `api-contract.md`
            # and `data-model.md` both forbid: twelve offered works resolved
            # behind one unresolved proposal reads as 12 of 1, contradicting the
            # notice in the same response.
            "resolved_proposals": view.resolved_proposals,
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
            # `proposed_count`, matching its sibling below rather than merely
            # equalling it: a deployment with no image provider never reaches the
            # supplement, so the two are the same number today — and two adjacent
            # lines counting differently read as a disagreement whichever one a
            # later change follows.
            return (
                f"There are {view.proposed_count} works to find images for, but no image provider is configured "
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
            # The proposed count, not the total: the supplement writes its works
            # during this same window, so a total read mid-run climbs while the
            # sentence claims a settled work list.
            f"The work list of {view.proposed_count} works is settled and the run is looking for an image of each. "
            "Call status again to keep watching."
        )
    if status is RunStatus.COMPLETED:
        # Both kinds get their own sentence, for the same reason the
        # `resolving_images` branch above splits: a re-search's works are the
        # ones it *covers*, owned by the parent run and carrying the parent's
        # provenance — so "proposed" describes a phase this run never performed,
        # and counting a proposed rate over them answers about the wrong thing.
        # The clauses below are provenance-neutral and are shared.
        if view.run.kind is RunKind.RESOLVE:
            settled = f"This re-search finished: {view.resolved} of the {view.work_count} works it covers have an image."
        else:
            # Rated against what the model proposed, never against the total: the
            # works the collection offered arrived carrying their images, so
            # counting them in the numerator reports a retrieval rate nothing
            # achieved. Both figures are direct counts — a numerator derived by
            # subtracting the offered works goes negative the moment one of them
            # is re-searched to nothing, which is a flow this same file
            # recommends.
            settled = f"This run finished: {view.resolved_proposals} of {view.proposed_count} proposed works have an image."
            if view.offered_count:
                # "found no image for", matching the two browser surfaces word for
                # word. The run did name works for those artists — an agent
                # reading this result can list them, each carrying an
                # `unresolved_reason` — so "could not confirm" is contradicted by
                # the very rows beside it. Issue #95 fixed that on the review
                # grid; the same sentence lived here and on the run view, and one
                # surface telling an agent something the other two do not is the
                # failure `http/models.py` and this module exist to prevent.
                works = "work" if view.offered_count == 1 else "works"
                settled += (
                    f" Separately, the collection offered {view.offered_count} more {works} by artists this run "
                    "found no image for. They are labelled `offered` and are not what was asked for."
                )
        if view.unresolved:
            settled += (
                f" {view.unresolved} could not be matched to any image and are reported as unresolved "
                "rather than dropped. Read `unresolved_reason` for which kind of nothing: only `not_held` "
                "suggests the work may not exist."
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
