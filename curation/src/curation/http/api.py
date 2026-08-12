"""The JSON surface the browser client reads, and the shaping that feeds it.

A handler unpacks the request, calls **one** service method, and formats the
result. A handler that validates, orders or decides is the violation — that work
belongs to the service layer, which the MCP tools call too. This is the same rule
`mcp/bindings.py` states, and it is stated twice on purpose: it is the only thing
keeping an agent and a click from disagreeing about the same catalogue.

**Some handlers below do not meet it today, and it binds anyway** — read it as
what to write next, not as a description of what is here. **Three shapes depart**,
and the shapes are the durable statement: read-back-after-mutate, composite reads,
and HTTP conditional-request handling. (This paragraph said "half the handlers"
while there were twelve; the run half took it to twenty without adding a
departure, so the fraction moved and the sentence did not. A count of a thing
that grows goes stale by being right once — the shapes do not.)
Each carries its reason where it happens, and all of them are recorded with an
open disposition under "Known departures" in the project preferences — which is
the point, because a norm with unrecorded exceptions dies by accumulation rather
than by anyone deciding to end it. Do not reconcile the gap by softening the
paragraph above.

**Handlers are synchronous `def`, deliberately.** The service layer is
synchronous and its work is real — sqlite reads, `fsync` on write, and a JPEG
downscale that can take a tenth of a second. Starlette runs a sync handler in a
worker thread, so none of that sits on the event loop, where it would stall the
MCP session manager sharing this process. The catalogue's one connection is
opened `check_same_thread=False` behind a re-entrant lock, which is what makes
that safe.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse

from curation.http.models import (
    AddWork,
    AffinityListOut,
    AffinityOut,
    ArtistOut,
    ArtworkBoxOut,
    BackupOut,
    CandidateCardOut,
    CandidatePageOut,
    CandidateWorkOut,
    CommitDirection,
    ConversationDeletionOut,
    ConversationListOut,
    ConversationOut,
    ConversationTurnOut,
    ConversationViewOut,
    CreateTheme,
    CreateWall,
    DirectiveOut,
    EstimateOut,
    ExclusionOut,
    FacetGroupOut,
    FacetOptionOut,
    FitOut,
    HangTheme,
    HealthOut,
    HeartbeatOut,
    ImageOut,
    InstanceListingOut,
    InstanceOut,
    ManifestEntryOut,
    ManifestOut,
    MatColorOut,
    MoveWork,
    OriginalOut,
    RenameTheme,
    RenditionOut,
    RunListOut,
    RunOut,
    RunTallyOut,
    RunViewOut,
    SampleOut,
    SearchUsageOut,
    SelectedImageOut,
    SelectImage,
    SetAffinity,
    SetVerdict,
    SourceOut,
    Speak,
    SpendOut,
    StartResolve,
    StartRun,
    StepDisplay,
    SuggestionOut,
    ThemeDetailOut,
    ThemeListOut,
    ThemeOut,
    ThemePlacementOut,
    VerdictOut,
    WallHeartbeatOut,
    WallListOut,
    WallOut,
    WallRefOut,
    WorkDetailOut,
    WorkFacetOut,
    WorkOut,
    WorkPageOut,
)
from curation.manifest.builder import ManifestBuild
from curation.manifest.heartbeat import HeartbeatReading
from curation.persistence.backup import BackupReading
from curation.persistence.discovery_records import (
    CandidateImage,
    CandidateWork,
    Conversation,
    DiscoveryRun,
    InitiatedBy,
)
from curation.persistence.records import Artist, Directive, MatColor, Original, Source, Theme, WorkFacet
from curation.services.catalogue import FacetGroup, RenditionView
from curation.services.container import Services
from curation.services.conversation import ConversationDeletion, ConversationView, TurnView
from curation.services.discovery import VerdictOutcome
from curation.services.display import ThemePlacement, WallView
from curation.services.display_fit import ArtworkBox
from curation.services.health import HealthReading
from curation.services.review import CandidatePage, CandidateView, InstanceListing, InstanceView
from curation.services.runner import Estimate, RunView, SpendReport
from curation.services.survey import WorkDossier, WorkSurvey
from curation.services.taste import AffinityView

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

#: Thumbnails are revalidated rather than held for a fixed window. A replaced
#: master regenerates the file under the same name, so a cached copy is a
#: *superseded acquisition* on screen — the exact thing the staleness rule
#: refuses everywhere else. The cost of that correctness is one conditional
#: request per card, answered below with a 304 rather than the bytes.
THUMBNAIL_CACHE_CONTROL: str = "private, no-cache"

#: A candidate preview, by contrast, is held rather than revalidated — and the
#: difference between the two lines is a property of the data rather than a
#: preference. A thumbnail is named for its *work*, and a re-acquired master
#: regenerates it under the same name, so a cached copy can become a superseded
#: acquisition on screen. A candidate preview is named for its *instance*: the
#: cache never re-fetches a file it already has, and nothing rewrites one, so the
#: bytes behind an image id are written once and only ever deleted. An id whose
#: content cannot change is the case `immutable` exists for, and it is what keeps
#: a repaint of a thirty-card grid from re-encoding thirty images on a Pi.
#:
#: Reclamation is not a hole in that. A decided work's previews are deleted, and a
#: card for such a work is told by the listing that no picture travels — so it
#: never asks, and a copy still in a browser cache is never shown.
PREVIEW_CACHE_CONTROL: str = "private, max-age=86400, immutable"


def _services(request: Request) -> Services:
    """The services this application was built around.

    Read off application state rather than injected per route, because they are
    constructed once at startup over one open catalogue file — a per-request
    dependency would suggest a lifetime they do not have.
    """
    return request.app.state.services


# -- works --------------------------------------------------------------------


@router.get("/works")
def list_works(
    request: Request,
    status: Annotated[str | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
    artist: Annotated[list[str] | None, Query()] = None,
    movement: Annotated[list[str] | None, Query()] = None,
    era: Annotated[list[str] | None, Query()] = None,
    subject: Annotated[list[str] | None, Query()] = None,
    medium: Annotated[list[str] | None, Query()] = None,
    palette: Annotated[list[str] | None, Query()] = None,
    limit: Annotated[int | None, Query()] = None,
    offset: Annotated[int, Query()] = 0,
) -> WorkPageOut:
    """A page of works with the facet controls for exactly this filter.

    `q` is free text; every word must appear somewhere in the work's own text or
    its artist's name. **One repeatable parameter per facet kind** — `?movement=
    Baroque&movement=Rococo` means either, and adding `&era=17th+c.` means both.
    Repeated rather than comma-joined because a facet value may itself contain a
    comma, and a separator a value can hold is a parser that goes wrong on the
    data rather than on the request.

    The six are spelled out rather than gathered from the raw query string:
    FastAPI generates this route's schema from the signature, so a named
    parameter is what makes the filter set discoverable and an unknown one a
    stated refusal instead of a silent no-op.
    """
    chosen = {"artist": artist, "movement": movement, "era": era, "subject": subject, "medium": medium, "palette": palette}
    page = _services(request).survey.list_works(
        status=status,
        q=q,
        facets={kind: values for kind, values in chosen.items() if values},
        limit=limit,
        offset=offset,
    )
    return WorkPageOut(
        works=[_work(entry) for entry in page.entries],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
        truncated=page.truncated,
        facets=[_facet_group(group) for group in page.facets],
    )


@router.get("/works/{artwork_id}")
def get_work(request: Request, artwork_id: str) -> WorkDetailOut:
    """One work in full — metadata, artist, sources, renditions and mats."""
    return _dossier(_services(request).survey.get_work(artwork_id))


@router.post("/works/{artwork_id}/archive")
def archive_work(request: Request, artwork_id: str) -> WorkDetailOut:
    """Take a work out of circulation, keeping its record and its mat history.

    **Archive rather than delete, and the noun in the path is the whole point.**
    `Artwork.status` has two values and restoration is permitted, so there is no
    route here that destroys a work; `information-architecture.md` argues the
    label follows the route, and the control this binds to reads *Archive*.

    The work stays in every theme that holds it — membership is curatorial and
    readiness is technical — so what changes is what the next manifest build puts
    on a wall. A standing pin naming this work is withdrawn in the same
    transaction, without advancing the sequence; both rules belong to the
    catalogue service and are not restated here.

    Returns the dossier, which is the same shape `GET /api/works/{id}` answers
    with: the interesting change is the work's whole state, the screen that
    archives is the screen that shows it, and a slimmer body would send that
    screen straight back for the rest. The read-back-after-mutate departure the
    theme routes take, for the same reason.
    """
    services = _services(request)
    services.catalogue.archive_artwork(artwork_id)
    return _dossier(services.survey.get_work(artwork_id))


@router.post("/works/{artwork_id}/restore")
def restore_work(request: Request, artwork_id: str) -> WorkDetailOut:
    """Return an archived work to circulation.

    The undo of the route above, and its existence is what makes archiving an
    ordinary act rather than a destructive one. Nothing is republished: a theme
    holding this work carries it again at the next manifest build, so the wall
    goes on showing what it was showing until then.
    """
    services = _services(request)
    services.catalogue.restore_artwork(artwork_id)
    return _dossier(services.survey.get_work(artwork_id))


# -- themes -------------------------------------------------------------------


@router.get("/themes")
def list_themes(request: Request) -> ThemeListOut:
    """Every theme, and the walls each is hanging on."""
    return ThemeListOut(themes=[_placement(placement) for placement in _services(request).display.survey_themes()])


@router.get("/themes/{theme_id}")
def get_theme(request: Request, theme_id: str) -> ThemeDetailOut:
    """A theme and the works it holds, in curated order."""
    return _theme_detail(_services(request), theme_id)


@router.post("/themes")
def create_theme(request: Request, body: CreateTheme) -> ThemeOut:
    """Record a theme."""
    return _theme(_services(request).display.add_theme(name=body.name, description=body.description))


@router.post("/themes/{theme_id}")
def rename_theme(request: Request, theme_id: str, body: RenameTheme) -> ThemeOut:
    """Change a theme's name.

    **`POST` rather than `PATCH`**, following this surface's own convention: it
    writes with `POST` and removes with `DELETE`, and one surface with two
    spellings for "change this" costs more than the orthodoxy is worth.

    Answers with the theme, so the screen repaints the name it now has rather
    than the one it sent. Those differ whenever the service normalises — a name
    surrounded by whitespace comes back trimmed — and a screen painting its own
    input would show a name the catalogue does not hold.
    """
    return _theme(_services(request).display.update_theme(theme_id, name=body.name))


@router.delete("/themes/{theme_id}")
def delete_theme(request: Request, theme_id: str) -> ThemeListOut:
    """Remove a theme and its membership rows. The works themselves are untouched.

    **The refusal is the service's, not this handler's.** `delete_theme` refuses
    a theme hanging on any wall and names the walls, and the same rule reaches
    `art_theme(action='delete')`; a guard written here would be a second copy for
    a click and an agent to disagree over. What arrives is a 400 carrying a
    sentence written to be shown, by the same path every other refusal takes.

    Answers with the themes that remain, because what a delete changes is the
    list it was performed from — and the alternative, an empty 204, would leave
    the screen re-reading a listing it has just been told the shape of.
    """
    services = _services(request)
    services.display.delete_theme(theme_id)
    return ThemeListOut(themes=[_placement(placement) for placement in services.display.survey_themes()])


@router.post("/themes/{theme_id}/works")
def add_to_theme(request: Request, theme_id: str, body: AddWork) -> ThemeDetailOut:
    """Place a work in a theme, and return the order that results.

    The membership alone would be a truthful answer and a useless one: a curator
    reordering a theme is looking at the list, and returning the list is what
    lets the surface repaint from the response instead of guessing where the
    work landed and then asking.
    """
    services = _services(request)
    services.display.add_to_theme(theme_id=theme_id, artwork_id=body.artwork_id, position=body.position)
    return _theme_detail(services, theme_id)


@router.delete("/themes/{theme_id}/works/{artwork_id}")
def remove_from_theme(request: Request, theme_id: str, artwork_id: str) -> ThemeDetailOut:
    """Take a work out of a theme, and return the order that results."""
    services = _services(request)
    services.display.remove_from_theme(theme_id=theme_id, artwork_id=artwork_id)
    return _theme_detail(services, theme_id)


@router.post("/themes/{theme_id}/works/{artwork_id}/position")
def move_in_theme(request: Request, theme_id: str, artwork_id: str, body: MoveWork) -> ThemeDetailOut:
    """Move a work within a theme's curated order, and return that order."""
    services = _services(request)
    services.display.move_in_theme(theme_id=theme_id, artwork_id=artwork_id, position=body.position)
    return _theme_detail(services, theme_id)


@router.post("/themes/{theme_id}/activate")
def activate_theme(request: Request, theme_id: str, body: HangTheme) -> ManifestOut:
    """Hang this theme on the named wall, and publish the manifest that follows.

    Returns the build, so the curator sees what actually reached that wall in the
    same response that put it there — including everything that did not, and
    including the wall's own name.
    """
    return _manifest(_services(request).display.activate_theme(theme_id, wall_id=body.wall_id))


# -- walls --------------------------------------------------------------------


@router.get("/walls")
def list_walls(request: Request) -> WallListOut:
    """Every wall, and what is hanging on each."""
    return WallListOut(walls=[_wall(view) for view in _services(request).display.survey_walls()])


@router.post("/walls")
def create_wall(request: Request, body: CreateWall) -> WallOut:
    """Record a wall. It arrives with nothing hanging on it.

    **A wall recorded here lights up once a display plane is pointed at it.**
    Hanging a theme writes that wall's own manifest, named by the id this route
    returns, and a display serves the one wall its `WALL_ID` names — so a second
    room needs a second device configured with that id, and nothing about it
    disturbs the first. Until 2026-08-12 there was one manifest for the
    installation and a second wall overwrote it silently.
    """
    services = _services(request)
    return _wall(services.display.get_wall_view(services.display.add_wall(name=body.name).id))


@router.delete("/walls/{wall_id}/theme")
def clear_wall(request: Request, wall_id: str) -> WallOut:
    """Take down whatever is hanging, leaving the wall holding nothing.

    Returns the wall, because the interesting change is what it now shows — the
    read-back-after-mutate shape the theme-membership routes already take, for
    the same reason and recorded as the same known departure.

    The wall keeps showing what it was showing until something else is hung: no
    manifest is rewritten, because publishing an empty one would blank the wall
    as a side effect of tidying up.
    """
    services = _services(request)
    services.display.clear_wall(wall_id)
    return _wall(services.display.get_wall_view(wall_id))


@router.post("/directives")
def step_display(request: Request, body: StepDisplay) -> DirectiveOut:
    """Tell the display serving one wall to move on to the next work.

    **The Walls screen's `next`, and until now the one screen action with an MCP
    action and no HTTP route at all.** `art_display(action='next')` has stepped a
    wall since the tool surface was built; the browser could only ever *read*
    `directive_sequence` off a manifest, so a curator standing in front of the
    television had no way to do the one thing they were most likely to want.

    The shape was left open while a directive was still a singleton, on the
    grounds that writing an installation-wide route would be writing the shape
    that had to change. It is per wall now, so the wall is named here as it is
    named in every other act that changes one.

    It returns the directive rather than the wall: what a step changes is what
    the wall was told to do, and nothing about what hangs there.
    """
    return _directive(_services(request).display.step_display(body.wall_id))


# -- the wall -----------------------------------------------------------------


@router.get("/manifest")
def get_manifest(
    request: Request,
    wall_id: Annotated[str, Query()],
    theme_id: Annotated[str | None, Query()] = None,
) -> ManifestOut:
    """What a theme would put on one wall, and every work it would leave off.

    Evaluates without writing, so a curator can ask what would happen before
    changing what is on the wall. The wall is required and the theme is not:
    exclusions belong to a wall once two walls can hang different themes, and the
    theme defaults to whatever is already hanging there.
    """
    return _manifest(_services(request).display.build_manifest(wall_id, theme_id))


@router.get("/health")
def get_health(request: Request) -> HealthOut:
    """Every observation the panel states, read at one instant.

    One service call, not three. This handler used to assemble the panel from a
    heartbeat here and a geometry there, which made "what signals does the panel
    make" a decision taken in the binding — and the next signal would have had to
    be added in two places with nothing to notice if it reached only one. The
    assembly is `HealthService.observe`'s now, and this is a dispatch again.
    """
    return _health(_services(request).health.observe())


# -- discovery runs -----------------------------------------------------------


@router.get("/estimate")
def get_estimate(request: Request, run_id: Annotated[str | None, Query()] = None) -> EstimateOut:
    """What a search would cost, before anyone commits to it.

    Answered without a run id for "what does asking cost", and with one for "what
    does resolving what this run found cost". Estimating spends nothing, which is
    what lets the intent screen show the price beside the field rather than after
    the decision.
    """
    return _estimate(_services(request).runner.estimate(run_id))


@router.post("/runs")
def start_run(request: Request, body: StartRun) -> RunOut:
    """Begin a discovery run and return its handle at once.

    Phase 1 proceeds on a worker behind this response. Waiting for it here would
    hold the request open for the minutes the search takes, which no browser will
    sit through — so the client is handed an id and follows it.
    """
    return _run(
        _services(request).runner.start(
            intent_text=body.intent,
            # Provenance, never authorisation: every surface has identical
            # authority, and this records which one asked so that "who wanted
            # forty Dalí candidates" is answerable from the data afterwards.
            initiated_by=InitiatedBy.WEB_UI,
        )
    )


@router.get("/runs")
def list_runs(
    request: Request,
    status: Annotated[str | None, Query()] = None,
    kind: Annotated[str | None, Query()] = None,
) -> RunListOut:
    """The newest runs, optionally narrowed, capped in the service layer.

    **`status` and `kind` are filters, not limits.** Omit both and this asked for
    the whole `discovery_runs` table — one row per search plus one per re-search,
    for ever, with nothing pruning them. What made it tolerable was a fact about
    the deployment rather than a mechanism: one household, one operator, so a
    year of use is hundreds of rows. A real bound, but an editorial one, and it
    stopped holding the moment this surface served anything else.

    The cap is `RunnerService.list_runs`', not this handler's, so this surface
    and the MCP twin cannot come to disagree about how much history exists —
    which is what the note here used to warn would happen if either were fixed
    alone. Both now read the same bound and report the same total.

    **There is still no paging parameter**, and that is a smaller gap than the
    one just closed: `total` says what was left out, and the two filters are how
    a caller reaches it. A `limit`/`offset` pair would change the contract of a
    shipped surface and earns its own review rather than riding along here.
    """
    listing = _services(request).runner.list_runs(status=status, kind=kind)
    return RunListOut(
        runs=[_run(run) for run in listing.runs],
        count=len(listing.runs),
        total=listing.total,
        truncated=listing.truncated,
    )


@router.get("/runs/{run_id}")
def get_run(request: Request, run_id: str) -> RunViewOut:
    """Where a run is, answered immediately rather than held open.

    **The MCP surface long-polls here and this one deliberately does not.** A
    model calls `status` once and waits, so holding the call is what keeps it
    from spinning. A browser is already an event loop: it polls on a timer, and a
    held request would occupy one of the worker threads Starlette runs these
    synchronous handlers in for the whole hold window — with a couple of tabs
    open that starves the same pool that serves thumbnails. The client asks
    again; nothing is lost but the hold.
    """
    return _run_view(_services(request).runner.run_status(run_id, wait=False))


@router.post("/runs/{run_id}/approve")
def approve_run(request: Request, run_id: str) -> RunViewOut:
    """Accept the work list and its price; phase 2 begins behind the response."""
    return _run_view(_services(request).runner.approve(run_id))


@router.post("/runs/{run_id}/decline")
def decline_run(request: Request, run_id: str) -> RunViewOut:
    """Refuse the work list. The run ends without phase 2 ever spending."""
    return _run_view(_services(request).runner.decline(run_id))


@router.post("/runs/{run_id}/cancel")
def cancel_run(request: Request, run_id: str) -> RunViewOut:
    """Stop a run from wherever it is. Money already spent stays recorded."""
    return _run_view(_services(request).runner.cancel(run_id))


@router.get("/runs/{run_id}/spend")
def get_run_spend(request: Request, run_id: str) -> SpendOut:
    """What a run has actually cost, including every re-search descended from it."""
    return _spend(_services(request).runner.spend_report(run_id=run_id))


@router.post("/runs/resolve")
def start_resolve_run(request: Request, body: StartResolve) -> RunOut:
    """Look again for images of works whose scans the curator turned down.

    A re-search is a run, which is what lets the run view follow it with nothing
    special to know — `status`, `cancel` and `spend` all take its id. The handle
    comes back at once and the search proceeds behind it, exactly as `start` does
    and for the same reason: this takes minutes.

    **Listed above `/runs/{run_id}` on purpose is not what makes this safe** — the
    paths do not overlap, since nothing serves `POST /api/runs/{id}`. It sits here
    because it is the third way a run begins and belongs beside the other two.
    """
    return _run(
        _services(request).runner.resolve_images(
            candidate_work_ids=body.work_ids,
            initiated_by=InitiatedBy.WEB_UI,
        )
    )


# -- review -------------------------------------------------------------------


@router.get("/runs/{run_id}/candidates")
def list_candidates(
    request: Request,
    run_id: str,
    limit: Annotated[int | None, Query()] = None,
    offset: Annotated[int, Query()] = 0,
) -> CandidatePageOut:
    """A page of the works a run is responsible for, each with a picture.

    Paged where the run view's own work list is not, and the difference is the
    payload rather than an inconsistency: that list is text, and this one carries
    a card per work. A curator scrolls a grid; they do not scroll two hundred
    pictures fetched at once on a Pi.
    """
    # `pictures=False`: this surface fetches each picture by URL, so inlining
    # them here would re-encode thirty images per page and discard the output.
    return _candidate_page(_services(request).review.list_works(run_id, limit=limit, offset=offset, pictures=False))


@router.get("/candidates/{work_id}")
def get_candidate(request: Request, work_id: str) -> CandidateCardOut:
    """One proposed work with the instance standing for it.

    What a card repaints from after a verdict or an image choice: the response to
    those calls says what changed, and this says what the card now looks like.
    """
    return _candidate_card(_services(request).review.get_work(work_id, pictures=False))


@router.get("/candidates/{work_id}/images")
def list_candidate_images(request: Request, work_id: str) -> InstanceListingOut:
    """Every scan found for this work, in the order the card offers them, capped.

    The alternates behind a card. Fetched on demand rather than with the grid: a
    thirty-work page would otherwise carry up to twelve instances each, and a
    curator opens the alternates for the few works whose first answer they doubt.
    """
    return _instance_listing(_services(request).review.list_images(work_id, pictures=False))


@router.post("/candidates/{work_id}/verdict")
def set_verdict(request: Request, work_id: str, body: SetVerdict) -> VerdictOut:
    """Accept or reject a proposed work. Acceptance promotes it into the catalogue."""
    return _verdict(_services(request).discovery.set_verdict(work_id, body.verdict, reason=body.reason))


@router.post("/candidate-images/{image_id}/select")
def select_candidate_image(request: Request, image_id: str, body: SelectImage) -> SelectedImageOut:
    """Make this the scan the work stands on, over the one the pipeline chose."""
    return _selected(_services(request).discovery.select_image(image_id, rationale=body.rationale))


@router.post("/candidate-images/{image_id}/reject")
def reject_candidate_image(request: Request, image_id: str) -> CandidateWorkOut:
    """Turn down a scan and keep the work. Nothing looks again until asked.

    Returns the work rather than the instance, because the interesting change is
    the work's: it moves to `awaiting_better_image`, which is the verdict an
    accept/reject binary cannot express — "I want this painting; this scan is not
    good enough". The card repaints from that.
    """
    return _candidate_work(_services(request).discovery.reject_image(image_id))


@router.get("/candidate-images/{image_id}/preview", response_class=Response)
def get_candidate_preview(request: Request, image_id: str) -> Response:
    """The picture for one instance, re-encoded for a browser.

    Not a `FileResponse` over the cached file, and not for want of trying to keep
    this thin. A cached preview's *name* is derived from its URL and falls back to
    `.jpg` for anything unrecognised, so the suffix on disk is not evidence of
    what the bytes are — serving a TIFF as `image/jpeg`, or as `image/tiff`, is a
    blank card either way. The re-encode is what makes one media type true.

    No conditional handling, unlike the catalogue's thumbnail. That one is a
    cached file whose ETag Starlette computes from a `stat`; this is generated per
    request from a file with no stable identity for a client to revalidate
    against, so a 304 would have nothing to compare. What bounds the cost instead
    is the grid: a card asks once, and only for the works whose alternates a
    curator opens.
    """
    rendered = _services(request).review.preview_image(image_id)
    return Response(content=rendered.data, media_type=rendered.media_type, headers={"Cache-Control": PREVIEW_CACHE_CONTROL})


# -- images -------------------------------------------------------------------


@router.get("/works/{artwork_id}/thumbnail", response_class=FileResponse)
def get_thumbnail(request: Request, artwork_id: str) -> Response:
    """A small copy of the work's held image, generated on first ask.

    **The conditional check is done here because nothing else does it.**
    `FileResponse` *sets* an `ETag` and never *reads* one — only Starlette's
    `StaticFiles` compares them, and these files are generated rather than
    served from a directory. Without this, `no-cache` means every repaint of a
    forty-card grid re-downloads every thumbnail; with it, it costs forty empty
    304s. Passing `stat_result` makes the header available before the response
    is sent and, more importantly, means the value compared against is the one
    Starlette itself would have produced rather than a second implementation of
    its formula.
    """
    path = _services(request).thumbnails.thumbnail(artwork_id)
    headers = {"Cache-Control": THUMBNAIL_CACHE_CONTROL}
    response = FileResponse(path, media_type="image/jpeg", headers=headers, stat_result=path.stat())
    etag = response.headers.get("etag")
    if etag is not None and _matches(request.headers.get("if-none-match"), etag):
        return Response(status_code=304, headers={**headers, "ETag": etag})
    return response


def _matches(header: str | None, etag: str) -> bool:
    """Whether an `If-None-Match` header already covers this thumbnail.

    Three cases, all of them real rather than defensive:

    * **A list of tags.** A client that has seen two versions of a URL may offer
      both, so comparing the raw header against one tag would miss a match it was
      handed.
    * **`*`.** RFC 9110 makes it match any current representation. By the time
      this is asked the file exists — `thumbnail()` returned its path — so there
      is one, and the answer is yes.
    * **The weak marker.** `W/"abc"` and `"abc"` are the same tag for a weak
      comparison, which is what a conditional GET performs.

    Stated as three cases because the previous version described the `*` one in
    its docstring and did not implement it — which is exactly the defect the
    conditional check above exists to fix, one function later.
    """
    if not header:
        return False
    offered = {tag.strip() for tag in header.split(",")}
    if "*" in offered:
        return True
    return etag in {tag.removeprefix("W/") for tag in offered}


# -- shaping ------------------------------------------------------------------


def service_error_response(message: str) -> JSONResponse:
    """The one error shape this surface returns.

    A single status for every refusal, because the service layer raises a single
    type by design and a per-error translation table here is what turns a thin
    binding into a thick one. The message is written to be shown: it names what
    was wrong and, where there is one, the thing to do instead.
    """
    return JSONResponse(status_code=400, content={"error": message})


def _theme_detail(services: Services, theme_id: str) -> ThemeDetailOut:
    """A theme with its works, in curated order."""
    return ThemeDetailOut(
        theme=_theme(services.display.get_theme(theme_id)),
        works=[_work(entry) for entry in services.survey.theme_works(theme_id)],
    )


def _work(survey: WorkSurvey) -> WorkOut:
    artwork = survey.detail.artwork
    return WorkOut(
        artwork_id=artwork.id,
        title=artwork.title,
        artist=None if survey.detail.artist is None else _artist(survey.detail.artist),
        date_created=artwork.date_created,
        medium=artwork.medium,
        dimensions=artwork.dimensions,
        description=artwork.description,
        commentary=artwork.commentary,
        rights=artwork.rights,
        status=str(artwork.status),
        fit=(
            None
            if survey.fit is None
            else FitOut(
                verdict=str(survey.fit.fit),
                rendered_width=survey.fit.rendered_width,
                rendered_height=survey.fit.rendered_height,
                rendered_long_edge_inches=survey.fit.rendered_long_edge_inches,
            )
        ),
        fit_note=survey.fit_note,
        image=ImageOut(
            available=survey.image.available,
            source_kind=survey.image.source_kind,
            note=survey.image.note,
        ),
    )


def _dossier(dossier: WorkDossier) -> WorkDetailOut:
    return WorkDetailOut(
        work=_work(dossier.survey),
        original=None if dossier.original is None else _original(dossier.original),
        sources=[_source(source) for source in dossier.sources],
        renditions=[_rendition(view) for view in dossier.renditions],
        mat_colors=[_mat_color(mat) for mat in dossier.mat_colors],
        facets=[_facet(facet) for facet in dossier.facets],
    )


def _facet(facet: WorkFacet) -> WorkFacetOut:
    return WorkFacetOut(
        facet_id=facet.id,
        kind=str(facet.kind),
        value=facet.value,
        derivation=str(facet.derivation),
        source_note=facet.source_note,
    )


def _facet_group(group: FacetGroup) -> FacetGroupOut:
    return FacetGroupOut(
        kind=str(group.kind),
        options=[
            FacetOptionOut(value=option.value, count=option.count, selected=option.selected, disabled=option.disabled)
            for option in group.options
        ],
        total_values=group.total_values,
        # The group's own property rather than `len(options) < total_values`
        # recomputed here, so a client and the service cannot disagree about
        # whether a rail is showing everything.
        truncated=group.truncated,
    )


def _artist(artist: Artist) -> ArtistOut:
    return ArtistOut(
        artist_id=artist.id,
        name=artist.name,
        nationality=artist.nationality,
        born=artist.born,
        died=artist.died,
        lifespan_text=artist.lifespan_text,
        biography=artist.biography,
        family_name=artist.family_name,
        given_name=artist.given_name,
    )


def _original(original: Original) -> OriginalOut:
    return OriginalOut(
        relative_path=original.relative_path,
        width=original.width,
        height=original.height,
        byte_size=original.byte_size,
        content_hash=original.content_hash,
    )


def _source(source: Source) -> SourceOut:
    return SourceOut(
        source_id=source.id,
        url=source.url,
        provider=source.provider,
        source_class=str(source.source_class),
        acquisition_method=str(source.acquisition_method),
        rights_status=str(source.rights_status),
        is_primary=source.is_primary,
        confidence=source.confidence,
        selection_rationale=source.selection_rationale,
        last_fetch_status=None if source.last_fetch_status is None else str(source.last_fetch_status),
        last_fetched_at=source.last_fetched_at,
    )


def _rendition(view: RenditionView) -> RenditionOut:
    return RenditionOut(
        rendition_id=view.rendition.id,
        kind=str(view.rendition.kind),
        target_width=view.rendition.target_width,
        target_height=view.rendition.target_height,
        relative_path=view.rendition.relative_path,
        stale=view.stale,
        generated_at=view.rendition.generated_at.isoformat(),
    )


def _mat_color(mat: MatColor) -> MatColorOut:
    return MatColorOut(
        hex_rgb=mat.hex_rgb,
        method=str(mat.method),
        is_current=mat.is_current,
        reason=mat.reason,
        chosen_at=mat.chosen_at.isoformat(),
    )


def _theme(theme: Theme) -> ThemeOut:
    return ThemeOut(
        theme_id=theme.id,
        name=theme.name,
        description=theme.description,
        rotation_interval_seconds=theme.rotation_interval_seconds,
        shuffle=theme.shuffle,
        created_at=theme.created_at.isoformat(),
    )


def _wall(view: WallView) -> WallOut:
    return WallOut(
        wall_id=view.wall.id,
        name=view.wall.name,
        created_at=view.wall.created_at.isoformat(),
        theme=None if view.hanging is None else _theme(view.hanging),
        directive_sequence=view.directive.sequence,
        pinned_work_id=view.directive.pinned_work_id,
    )


def _directive(directive: Directive) -> DirectiveOut:
    return DirectiveOut(
        wall_id=directive.wall_id,
        sequence=directive.sequence,
        pinned_work_id=directive.pinned_work_id,
    )


def _placement(placement: ThemePlacement) -> ThemePlacementOut:
    return ThemePlacementOut(
        theme=_theme(placement.theme),
        hanging_on=[WallRefOut(wall_id=wall.id, name=wall.name) for wall in placement.walls],
    )


def _manifest(build: ManifestBuild) -> ManifestOut:
    return ManifestOut(
        wall_id=build.wall.id,
        wall_name=build.wall.name,
        theme=_theme(build.theme),
        entries=[
            ManifestEntryOut(
                artwork_id=entry.work_id,
                title=entry.label.get("title") or "",
                artist=entry.label.get("artist"),
                render_path=entry.render_path,
            )
            for entry in build.entries
        ],
        exclusions=[
            ExclusionOut(
                artwork_id=exclusion.work_id,
                title=exclusion.title,
                reason=str(exclusion.reason),
                detail=exclusion.detail,
            )
            for exclusion in build.exclusions
        ],
        considered=build.considered,
        rotation_interval_seconds=build.rotation_interval_seconds,
        shuffle=build.shuffle,
        directive_sequence=build.directive_sequence,
        pinned_work_id=build.pinned_work_id,
        # The build's own sentence, not a second one written here: the tool
        # surface states the same fact, and two hand-written versions drift.
        summary=build.summarise(),
    )


def _run(run: DiscoveryRun) -> RunOut:
    return RunOut(
        run_id=run.id,
        kind=str(run.kind),
        status=str(run.status),
        is_terminal=run.status.is_terminal,
        initiated_by=str(run.initiated_by),
        intent=run.intent_text,
        strategy=run.strategy,
        approval_required=run.approval_required,
        estimated_cost_usd=None if run.estimated_cost_usd is None else str(run.estimated_cost_usd),
        actual_cost_usd=None if run.actual_cost_usd is None else str(run.actual_cost_usd),
        unresolved_work_count=run.unresolved_work_count,
        parent_run_id=run.parent_run_id,
        started_at=run.started_at.isoformat(),
        completed_at=None if run.completed_at is None else run.completed_at.isoformat(),
    )


def _run_view(view: RunView) -> RunViewOut:
    """A run with its works and both of its tallies.

    Every figure is read off the view's own properties rather than recomputed
    here. The counts and the list they describe would otherwise be two
    derivations of one fact, and the second is the one that goes wrong — which is
    not hypothetical: a run-level figure computed as `len(works)` beside a view
    that counted provenance apart is exactly the defect that reached a review.
    """
    return RunViewOut(
        run=_run(view.run),
        tally=RunTallyOut(
            total=view.work_count,
            proposed=view.proposed_count,
            offered=view.offered_count,
            resolved=view.resolved,
            resolved_proposals=view.resolved_proposals,
            unresolved=view.unresolved,
            pending=view.pending,
        ),
        works=[_candidate_work(work) for work in view.works],
        searches=SearchUsageOut(
            used=view.searches_used,
            allowance=view.search_allowance,
            exhausted=view.searches_exhausted,
        ),
        image_resolution_available=view.image_resolution_available,
    )


def _candidate_work(work: CandidateWork) -> CandidateWorkOut:
    return CandidateWorkOut(
        work_id=work.id,
        title=work.proposed_title,
        artist=work.proposed_artist,
        rationale=work.rationale,
        provenance=str(work.provenance),
        offered_for_artist=work.offered_for_artist,
        offered_artist_matched=work.offered_artist_matched,
        verdict=str(work.verdict),
        resolution_status=str(work.resolution_status),
        unresolved_reason=None if work.unresolved_reason is None else str(work.unresolved_reason),
    )


def _candidate_page(page: CandidatePage) -> CandidatePageOut:
    return CandidatePageOut(
        run=_run(page.run),
        works=[_candidate_card(entry) for entry in page.entries],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
        # The page's own property, not `offset + len(works) < total` recomputed
        # here. Two derivations of one fact is how a grid comes to promise a next
        # page that does not exist, and the second derivation is the wrong one.
        truncated=page.truncated,
    )


def _candidate_card(view: CandidateView) -> CandidateCardOut:
    return CandidateCardOut(
        work=_candidate_work(view.work),
        shown=None if view.shown is None else _instance(view.shown),
        shown_is_on_offer=view.shown_is_on_offer,
        instances_held=view.instances_held,
        instances_surviving=view.instances_surviving,
    )


def _instance_listing(listing: InstanceListing) -> InstanceListingOut:
    return InstanceListingOut(
        work=_candidate_work(listing.work),
        instances=[_instance(instance) for instance in listing.instances],
        held=listing.held,
        surviving_held=listing.surviving_held,
        truncated=listing.truncated,
        shows_every_choosable_instance=listing.shows_every_choosable_instance,
    )


def _instance(view: InstanceView) -> InstanceOut:
    image = view.image
    return InstanceOut(
        image_id=image.id,
        work_id=image.candidate_work_id,
        url=image.url,
        provider=image.provider,
        confidence=image.confidence,
        is_selected=image.is_selected,
        rejected=view.rejected,
        rights_status=None if image.rights_status is None else str(image.rights_status),
        selection_rationale=image.selection_rationale,
        fit=(
            None
            if view.fit is None
            else FitOut(
                verdict=str(view.fit.fit),
                rendered_width=view.fit.rendered_width,
                rendered_height=view.fit.rendered_height,
                rendered_long_edge_inches=view.fit.rendered_long_edge_inches,
            )
        ),
        fit_note=view.fit_note,
        # The view's own property. It is not `preview is not None` here, because
        # this surface asks for its pictures by URL and takes none inline — see
        # `InstanceView.preview_available`, which is why that property exists.
        preview_available=view.preview_available,
        preview_note=view.preview_note,
    )


def _verdict(outcome: VerdictOutcome) -> VerdictOut:
    work = outcome.work
    return VerdictOut(
        work=_candidate_work(work),
        artwork_id=work.artwork_id,
        decided_at=None if work.decided_at is None else work.decided_at.isoformat(),
        minted_artist=None if outcome.minted_artist is None else _artist(outcome.minted_artist),
        possible_duplicate_artists=[_artist(artist) for artist in outcome.duplicate_candidates],
        notice=_verdict_notice(outcome),
    )


def _verdict_notice(outcome: VerdictOutcome) -> str | None:
    """Say what acceptance did that the work's own fields do not show.

    Only the artist. Minting one is the single part of a promotion a curator can
    neither see in the accepted work nor undo from it — a duplicate row looks
    exactly like a painter newly encountered — so it is said in words at the
    moment it happens, where a field on a payload nobody re-reads would not
    reach them.

    **This is a byte-for-byte copy of `mcp/bindings.py`'s, and that is now
    stated rather than explained away.** The paragraph here used to claim the
    divergence the run-view sentence really has — "that one is written for a
    model and names tool calls in backticks; this one is read by a person" —
    which is true of `runSentence` and simply false of this: the text names
    artists, not tool calls, and the two functions are identical.

    They stay two, because the day one of them does need a reader-specific
    word is the day sharing them would be in the way, and because merging a
    formatter across the surfaces is what `architecture.md`'s 2026-07-27 entry
    declines. What changed is that the copy is held identical by
    `tests/unit/test_surface_parity.py` rather than by a docstring asserting a
    difference that was not there.
    """
    minted = outcome.minted_artist
    # Both conditions rather than the one that carries the message. Near-misses
    # are reported only alongside a mint, so `minted is None` here is currently
    # unreachable — but the sentence names the minted row, and deriving that it
    # exists from a *different* field being non-empty is how a payload comes to
    # say `None` where a name belongs the day the service reports near-misses for
    # anything else.
    if minted is None or not outcome.duplicate_candidates:
        return None
    names = ", ".join(repr(artist.name) for artist in outcome.duplicate_candidates)
    return (
        f"A new artist {minted.name!r} was recorded, and the catalogue already holds {names}. They may be "
        "the same painter under different spellings; matching is exact, because a wrong merge puts another "
        "painter's name on a label and leaves no trace. Both rows stand until someone decides."
    )


def _selected(image: CandidateImage) -> SelectedImageOut:
    return SelectedImageOut(
        image_id=image.id,
        work_id=image.candidate_work_id,
        url=image.url,
        selection_rationale=image.selection_rationale,
    )


def _estimate(estimate: Estimate) -> EstimateOut:
    return EstimateOut(
        phase=estimate.phase,
        # A string rather than a float, for the same reason the MCP surface does
        # it: a price through binary floating point comes back as
        # 0.12699999999999999.
        estimated_cost_usd=str(estimate.cost_usd),
        basis=estimate.basis,
        run_id=estimate.run_id,
    )


def _spend(report: SpendReport) -> SpendOut:
    return SpendOut(
        scope=report.scope,
        cost_usd=str(report.cost_usd),
        run_id=report.run_id,
        year=report.year,
        month=report.month,
    )


def _health(reading: HealthReading) -> HealthOut:
    return HealthOut(
        walls=[
            WallHeartbeatOut(wall_id=seen.wall.id, wall_name=seen.wall.name, heartbeat=_heartbeat(seen.heartbeat))
            for seen in reading.walls
        ],
        description=reading.describe(),
        backup=_backup(reading.backup),
        artwork_box=_artwork_box(reading.artwork_box),
    )


def _heartbeat(reading: HeartbeatReading) -> HeartbeatOut:
    return HeartbeatOut(
        path=str(reading.path),
        reported_at=None if reading.reported_at is None else reading.reported_at.isoformat(),
        age_seconds=reading.age_seconds,
        absent=reading.absent,
        problem=reading.problem,
        description=reading.describe(),
        reported=reading.contents,
    )


def _backup(reading: BackupReading) -> BackupOut:
    return BackupOut(
        path=str(reading.path),
        completed_at=None if reading.completed_at is None else reading.completed_at.isoformat(),
        age_seconds=reading.age_seconds,
        absent=reading.absent,
        problem=reading.problem,
        description=reading.describe(),
        reported=reading.contents,
    )


def _artwork_box(box: ArtworkBox) -> ArtworkBoxOut:
    return ArtworkBoxOut(
        width=box.width,
        height=box.height,
        pixels_per_inch=box.pixels_per_inch,
        floor_inches=box.floor_inches,
    )


# -- conversations ------------------------------------------------------------
#
# One block at the foot of the file rather than routes among the routes and
# mappers among the mappers, and it is a merge decision rather than a taste one:
# three chunks were appending to this module at once, and a block that touches no
# existing line cannot conflict with the other two. Route registration is by
# decorator at import, so position changes nothing about what is served.


@router.get("/conversations")
def list_conversations(request: Request) -> ConversationListOut:
    conversations = _services(request).conversation.list_conversations()
    return ConversationListOut(
        conversations=[_conversation(conversation) for conversation in conversations],
        count=len(conversations),
    )


@router.post("/conversations")
def start_conversation(request: Request) -> ConversationViewOut:
    """Open an empty thread.

    No body, and nothing spent. A curator who opens a conversation and thinks
    better of it has cost the household a row; the first question is a turn like
    every other.
    """
    return _conversation_view(_services(request).conversation.start())


@router.get("/conversations/{conversation_id}")
def get_conversation(request: Request, conversation_id: str) -> ConversationViewOut:
    return _conversation_view(_services(request).conversation.get(conversation_id))


@router.post("/conversations/{conversation_id}/turns")
def speak(request: Request, conversation_id: str, body: Speak) -> ConversationViewOut:
    """Ask something, or — with no text — ask again for the last answer.

    **A turn that could not be answered is a 200, not a 400.** The requirement is
    that a failed turn stays in the thread and is retryable, and an error body
    carries no thread: the client would show a sentence with the curator's
    question nowhere on screen. So the refusal travels as `failure` on the view,
    and only a request that recorded nothing at all — an unknown conversation,
    empty text with nothing outstanding to retry — is a refusal.
    """
    return _conversation_view(_services(request).conversation.speak(conversation_id, body.text))


@router.post("/conversations/{conversation_id}/commit")
def commit_conversation(request: Request, conversation_id: str, body: CommitDirection) -> ConversationViewOut:
    """Seed a discovery run from this thread, and stay in the thread.

    Returns the conversation rather than the run, and the difference is the whole
    seam: a response shaped like a run is a response a client navigates to. What
    comes back is the transcript with a committed turn at the end of it, which is
    what the commit card repaints itself from without going anywhere.
    """
    return _conversation_view(_services(request).conversation.commit(conversation_id, body.intent))


def _conversation(conversation: Conversation) -> ConversationOut:
    return ConversationOut(
        conversation_id=conversation.id,
        started_at=conversation.started_at.isoformat(),
        last_turn_at=conversation.last_turn_at.isoformat(),
        summary=conversation.summary,
    )


def _conversation_view(view: ConversationView) -> ConversationViewOut:
    unanswered = view.unanswered
    return ConversationViewOut(
        conversation=_conversation(view.conversation),
        turns=[_conversation_turn(turn) for turn in view.turns],
        committed_run_id=view.committed_run_id,
        failure=view.failure,
        unanswered_turn_id=None if unanswered is None else unanswered.id,
    )


def _conversation_turn(view: TurnView) -> ConversationTurnOut:
    return ConversationTurnOut(
        turn_id=view.turn.id,
        ordinal=view.turn.ordinal,
        role=str(view.turn.role),
        text=view.turn.text,
        suggested=[
            SuggestionOut(
                kind=suggestion.kind,
                value=suggestion.value,
                samples=[SampleOut(title=sample.title, artist=sample.artist, image_url=sample.image_url) for sample in samples],
            )
            for suggestion, samples in view.suggested
        ],
        committed_run_id=view.turn.committed_run_id,
        created_at=view.turn.created_at.isoformat(),
    )


@router.delete("/conversations/{conversation_id}")
def delete_conversation(request: Request, conversation_id: str) -> ConversationDeletionOut:
    """Destroy the thread and its turns, and detach everything derived from them.

    **The one operation in this product that genuinely destroys a record**, which
    is exactly why what stands on it is detached rather than destroyed with it:
    `Affinity.source_turn_id` and `SpendRecord.conversation_turn_id` are nulled,
    and nothing else is touched. An affinity is a judgment accumulated across
    conversations and cannot be reconstructed from a thread that no longer exists;
    a spend record is a ledger entry, and a month total that fell because somebody
    tidied would be a number that lies about the past.

    **The response names the consequence, not the row count.** What the curator
    loses is the ability to rebuild those judgments when the derivation improves,
    and `description` says so in those terms — the counts are there to qualify it.
    """
    return _conversation_deletion(_services(request).conversation.delete(conversation_id))


def _conversation_deletion(deletion: ConversationDeletion) -> ConversationDeletionOut:
    return ConversationDeletionOut(
        conversation_id=deletion.conversation_id,
        turns_deleted=deletion.turns_deleted,
        affinities_detached=deletion.affinities_detached,
        spend_records_detached=deletion.spend_records_detached,
        runs_unattributed=deletion.runs_unattributed,
        # Composed by the service so this surface and the tool one cannot come to
        # describe the same destruction differently.
        description=deletion.describe(),
    )


# -- taste --------------------------------------------------------------------


@router.get("/affinities")
def list_affinities(
    request: Request,
    kind: Annotated[str | None, Query()] = None,
    sentiment: Annotated[str | None, Query()] = None,
    derivation: Annotated[str | None, Query()] = None,
) -> AffinityListOut:
    """The curator's standing judgments, narrowed by any of the three.

    Unpaged: this is a household's whole taste, which is tens of rows, and a page
    over it would be a second way to read what one call hands back whole.
    """
    affinities = _services(request).taste.list_affinities(kind=kind, sentiment=sentiment, derivation=derivation)
    return AffinityListOut(affinities=[_affinity(entry) for entry in affinities], count=len(affinities))


@router.post("/affinities")
def set_affinity(request: Request, body: SetAffinity) -> AffinityOut:
    """Write one judgment over whatever was there, or write the first one.

    `POST` rather than `PATCH` because this surface writes with `POST` everywhere
    and one surface with two spellings for "change this" costs more than the
    orthodoxy is worth. It is an upsert addressed by (`kind`, `value`), so a
    correction needs no id — which is right for the caller that has a name in a
    sentence rather than a row it fetched.
    """
    return _affinity(
        _services(request).taste.set_affinity(
            kind=body.kind,
            value=body.value,
            sentiment=body.sentiment,
            open_to_more=body.open_to_more,
            derivation=body.derivation,
            rationale=body.rationale,
            source_turn_id=body.source_turn_id,
        )
    )


@router.delete("/affinities/{affinity_id}")
def delete_affinity(request: Request, affinity_id: str) -> AffinityOut:
    """Forget one judgment, and answer with what was forgotten.

    The row rather than an acknowledgement of the id, because this is not
    recoverable: a confirmation should name the thing that is gone rather than the
    handle it was addressed by.
    """
    return _affinity(_services(request).taste.delete_affinity(affinity_id))


def _affinity(view: AffinityView) -> AffinityOut:
    affinity = view.affinity
    return AffinityOut(
        affinity_id=affinity.id,
        kind=str(affinity.kind),
        value=affinity.value,
        sentiment=str(affinity.sentiment),
        open_to_more=affinity.open_to_more,
        derivation=str(affinity.derivation),
        rationale=affinity.rationale,
        source_turn_id=affinity.source_turn_id,
        # Resolved by the service from the cited turn rather than stored, so the
        # link and the citation cannot come apart — and absent for a judgment
        # whose conversation was deleted, which is what stops the screen offering
        # a way through to a thread that is not there.
        conversation_id=view.conversation_id,
        artist_id=affinity.artist_id,
        created_at=affinity.created_at.isoformat(),
        updated_at=affinity.updated_at.isoformat(),
    )
