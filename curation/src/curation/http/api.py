"""The JSON surface the browser client reads, and the shaping that feeds it.

A handler unpacks the request, calls **one** service method, and formats the
result. A handler that validates, orders or decides is the violation — that work
belongs to the service layer, which the MCP tools call too. This is the same rule
`mcp/bindings.py` states, and it is stated twice on purpose: it is the only thing
keeping an agent and a click from disagreeing about the same catalogue.

**Half the handlers below do not meet it today, and it binds anyway** — read it as
what to write next, not as a description of what is here. Three shapes depart:
read-back-after-mutate, composite reads, and HTTP conditional-request handling.
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
    ArtistOut,
    ArtworkBoxOut,
    CreateTheme,
    ExclusionOut,
    FitOut,
    HealthOut,
    HeartbeatOut,
    ImageOut,
    ManifestEntryOut,
    ManifestOut,
    MatColorOut,
    MoveWork,
    OriginalOut,
    RenditionOut,
    SourceOut,
    ThemeDetailOut,
    ThemeListOut,
    ThemeOut,
    WorkDetailOut,
    WorkOut,
    WorkPageOut,
)
from curation.manifest.builder import ManifestBuild
from curation.manifest.heartbeat import HeartbeatReading
from curation.persistence.records import Artist, MatColor, Original, Source, Theme
from curation.services.catalogue import RenditionView
from curation.services.container import Services
from curation.services.display_fit import ArtworkBox
from curation.services.survey import WorkDossier, WorkSurvey

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

#: Thumbnails are revalidated rather than held for a fixed window. A replaced
#: master regenerates the file under the same name, so a cached copy is a
#: *superseded acquisition* on screen — the exact thing the staleness rule
#: refuses everywhere else. The cost of that correctness is one conditional
#: request per card, answered below with a 304 rather than the bytes.
THUMBNAIL_CACHE_CONTROL: str = "private, no-cache"


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
    limit: Annotated[int | None, Query()] = None,
    offset: Annotated[int, Query()] = 0,
) -> WorkPageOut:
    """A page of works, each with its fit verdict and its image state."""
    page = _services(request).survey.list_works(status=status, limit=limit, offset=offset)
    return WorkPageOut(
        works=[_work(entry) for entry in page.entries],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
        truncated=page.truncated,
    )


@router.get("/works/{artwork_id}")
def get_work(request: Request, artwork_id: str) -> WorkDetailOut:
    """One work in full — metadata, artist, sources, renditions and mats."""
    return _dossier(_services(request).survey.get_work(artwork_id))


# -- themes -------------------------------------------------------------------


@router.get("/themes")
def list_themes(request: Request) -> ThemeListOut:
    """Every theme."""
    return ThemeListOut(themes=[_theme(theme) for theme in _services(request).display.list_themes()])


@router.get("/themes/{theme_id}")
def get_theme(request: Request, theme_id: str) -> ThemeDetailOut:
    """A theme and the works it holds, in curated order."""
    return _theme_detail(_services(request), theme_id)


@router.post("/themes")
def create_theme(request: Request, body: CreateTheme) -> ThemeOut:
    """Record a theme."""
    return _theme(_services(request).display.add_theme(name=body.name, description=body.description))


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
def activate_theme(request: Request, theme_id: str) -> ManifestOut:
    """Make this the theme the wall shows, and publish the manifest that follows.

    Returns the build, so the curator sees what actually reached the wall in the
    same response that put it there — including everything that did not.
    """
    return _manifest(_services(request).display.activate_theme(theme_id))


# -- the wall -----------------------------------------------------------------


@router.get("/manifest")
def get_manifest(request: Request, theme_id: Annotated[str | None, Query()] = None) -> ManifestOut:
    """What a theme would put on the wall, and every work it would leave off.

    Evaluates without writing, so a curator can ask what would happen before
    changing what is on the wall.
    """
    return _manifest(_services(request).display.build_manifest(theme_id))


@router.get("/health")
def get_health(request: Request) -> HealthOut:
    """Observations about the display plane and this deployment's own geometry."""
    services = _services(request)
    return HealthOut(
        heartbeat=_heartbeat(services.display.wall_status()),
        artwork_box=_artwork_box(services.survey.artwork_box),
    )


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
        is_active=theme.is_active,
        rotation_interval_seconds=theme.rotation_interval_seconds,
        shuffle=theme.shuffle,
        created_at=theme.created_at.isoformat(),
    )


def _manifest(build: ManifestBuild) -> ManifestOut:
    return ManifestOut(
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


def _heartbeat(reading: HeartbeatReading) -> HeartbeatOut:
    return HeartbeatOut(
        path=str(reading.path),
        reported_at=None if reading.reported_at is None else reading.reported_at.isoformat(),
        age_seconds=reading.age_seconds,
        absent=reading.absent,
        problem=reading.problem,
        description=reading.describe(),
    )


def _artwork_box(box: ArtworkBox) -> ArtworkBoxOut:
    return ArtworkBoxOut(
        width=box.width,
        height=box.height,
        pixels_per_inch=box.pixels_per_inch,
        floor_inches=box.floor_inches,
    )
