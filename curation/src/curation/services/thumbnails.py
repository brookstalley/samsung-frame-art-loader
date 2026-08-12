"""Small images of held works, for a surface that shows forty of them at once.

A grid of the real files is not a page: the masters in this corpus run to 47
megapixels and 40 MB each, and the television renditions are 4K. So the browser
surface is served downscaled copies, cached on disk and **recorded in the
catalogue as renditions**, which is what keeps them from becoming an
untracked pile of files nothing owns. `RenditionKind.THUMBNAIL` has been in the
data model since the catalogue was designed; this is its producer.

**Staleness is the catalogue's rule plus one this kind alone needs.** A rendition
carries the content hash of the master it was made from, so it goes stale when
the work's original changes — the same relation that governs the television
render, applied by the same code. A thumbnail needs a second test because it is
the one rendition drawn from *another rendition*: once a work has a canvas, the
thumbnail is a copy of the canvas, and composing or recomposing one never touches
the original the hash test asks about. `_drawn_from` is that second test, and it
is deliberately not in `records.py` beside `is_current` — the shared rule is
shared because three surfaces must not disagree about it, while this one has a
single consumer and covers a relation only this kind has.

**Which image gets downscaled is reported, never assumed.** The television
rendition is preferred when it is current: it is already 4K rather than
gigapixel, so it is far cheaper to read, and it is what the wall is actually
showing. A stale one is refused outright rather than used — serving it would put
a superseded acquisition in front of the curator, which is precisely what the
staleness rule exists to prevent — and the master is used instead. Callers are
told which, because a curator looking at a grid deserves to know whether they are
seeing the composed presentation or the raw scan.
"""

import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final

from PIL import Image, UnidentifiedImageError

from curation.persistence.records import Rendition, RenditionKind, tv_renditions_newest_first
from curation.services.catalogue import CatalogueService
from curation.services.errors import ServiceError
from curation.services.imaging import encode_downscaled

log = logging.getLogger(__name__)

#: The box a thumbnail is fitted into, in pixels. One size rather than a
#: per-request parameter: a caller-chosen size makes the cache unbounded and the
#: rendition rows meaningless, and this surface has exactly one grid.
THUMBNAIL_MAX_EDGE_PX: Final[int] = 480

#: Quality for the re-encode. High enough that the grid is not visibly artefacted
#: on a retina display, low enough that forty of them are a page.
THUMBNAIL_JPEG_QUALITY: Final[int] = 82


class ThumbnailUnavailable(ServiceError):
    """No thumbnail can be produced, and the message says what is missing.

    A distinct type because "this work has no image yet" is a normal state on a
    catalogue mid-acquisition, not a refused operation: a surface reports it
    beside the work rather than as an error the curator did something to cause.
    """


@dataclass(frozen=True, slots=True)
class ThumbnailSource:
    """Which held image a thumbnail was made from."""

    #: `tv_display` or `original` — what the curator is actually looking at.
    kind: str
    path: Path
    #: When this source image was itself produced, and `None` for the master.
    #:
    #: The asymmetry is the point rather than an omission. A thumbnail of the
    #: master goes stale when the master changes, and the catalogue's own
    #: staleness rule already answers that by hash. A thumbnail of a *canvas* has
    #: no such cover: the canvas is a rendition too, and composing or recomposing
    #: one leaves the original untouched, so the hash says "current" for a
    #: thumbnail drawn from an image that no longer exists. Comparing against
    #: this is what closes it, and only the canvas branch needs it.
    #:
    #: **Undefaulted on purpose**, though `None` is one of its two legitimate
    #: values. `kind` already says which branch this is, so a default here would
    #: make the two fields able to disagree silently — a future `tv_display`
    #: construction that omitted the stamp would restore the defect this rule
    #: exists to close, and no consumer would notice, because every other reader
    #: of this type looks only at `kind`.
    generated_at: datetime | None


@dataclass(frozen=True, slots=True)
class ThumbnailSettings:
    """Where the images are and where their downscaled copies go.

    Passed in rather than resolved here for the reason `DisplaySettings` gives: a
    service that read its own configuration could not be tested against two
    deployments and would make every caller share one.
    """

    art_root: Path
    directory: Path

    def __post_init__(self) -> None:
        """Refuse a cache outside the tree, at wiring time rather than mid-request.

        Every catalogue path is relative to `ART_ROOT`, so a thumbnail written
        anywhere else has no representable path. Caught here, that is a startup
        failure naming both directories; caught where the row is written, it is a
        `ValueError` from `relative_to` on the fortieth image of a page load.
        """
        if not self.directory.is_relative_to(self.art_root):
            raise ServiceError(f"The thumbnail cache at {self.directory} must sit inside ART_ROOT at {self.art_root}.")


def _drawn_from(thumbnail: Rendition, source: ThumbnailSource) -> bool:
    """Whether this cached thumbnail can have been made from `source`.

    **The catalogue's staleness rule does not reach this question**, and the gap
    is structural rather than an oversight. `is_current` compares a rendition
    against the *original*, which is right for every rendition drawn from the
    original — and a thumbnail is the one that is not: when a work has a canvas,
    the thumbnail is drawn from the canvas, a rendition itself. Composing a
    canvas, or recomposing one in a new mat colour, never touches the original,
    so the hash test answers "current" about an image the thumbnail has never
    seen. The two ways that surfaces: a card badged "wall render" over the bare
    master, and a mat colour a curator sets that changes the wall and not the
    picture in front of them.

    Time is the comparison because it is the only fact both rows carry that moves
    when the canvas is redrawn — the path does not (a recompose writes the same
    file) and the hash does not (it is the original's). `record_rendition` upserts
    the geometry row and stamps `generated_at` afresh, so a redrawn canvas is
    newer than a thumbnail taken before it — for as long as the wall clock runs
    forwards. `datetime.now(UTC)` is not monotonic, so a backwards correction
    landing between the two writes reinstates the defect until the original
    changes. Not engineered around: this is a single-operator local application,
    and the alternative is carrying a monotonic counter on a row that has no other
    use for one.

    An exact tie regenerates, which is the harmless direction: the two writes are
    separated by an image encode so it does not arise in practice, and paying one
    needless re-encode is the right side of a trade against serving a picture that
    is not what the work looks like. The window the other way is knowingly
    accepted and is the same shape: `thumbnail()` reads its source, encodes, and
    only then stamps its own row, so a canvas recomposed *inside* that window
    yields a thumbnail row postdating a canvas it was never drawn from. One image
    encode wide, on a surface one person drives.

    **What this deliberately does not answer, and cannot: what the cached
    thumbnail was actually drawn from.** Nothing records it, so the master branch
    below has to assume, and the assumption is wrong in one reachable state — a
    `tv_display` row that is current by hash but whose file has gone, which
    `preparation.py` documents as what a restored catalogue or a cleared `ready/`
    leaves. `source_for` then falls back to the master while the cache still holds
    the canvas-derived picture, and a curator is served a matted 16:9 thumbnail
    under a badge reading "master image" — this defect with its two sides swapped.
    It predates this rule rather than arriving with it, and closing it needs the
    thumbnail's provenance modelled on the row rather than inferred from the
    current source's timestamp. Filed as #116; do not close it by regenerating whenever an
    absent-file `tv_display` row exists, which spends a re-encode on every load for
    a thumbnail legitimately drawn from the master.
    """
    if source.generated_at is None:
        # Drawn from the master *now* — see the docstring for why "now" is not the
        # same claim as "when this thumbnail was made", and what that costs.
        return True
    return thumbnail.generated_at > source.generated_at


class ThumbnailService:
    """Produce and cache small copies of held works."""

    def __init__(self, catalogue: CatalogueService, settings: ThumbnailSettings) -> None:
        self._catalogue = catalogue
        self._settings = settings

    def source_for(self, artwork_id: str) -> ThumbnailSource:
        """The held image a thumbnail of this work would be made from.

        Separate from `thumbnail` so a listing can say what each card will show —
        and say why a card will show nothing — without decoding forty images to
        find out.
        """
        original = self._catalogue.get_original(artwork_id)
        if original is None:
            raise ThumbnailUnavailable("No master image has been acquired for this work yet.")

        # Newest first, which is the order the wall prefers them in — expressed
        # once, beside the records, so a card and the wall cannot show different
        # pictures of the same work. This walked the store's own order and took
        # the first current row it met; two television renders at different
        # geometries are reachable under the unique index, and on such a work the
        # two would have disagreed with nothing saying which was right.
        views = {view.rendition.id: view for view in self._catalogue.list_renditions(artwork_id)}
        for rendition in tv_renditions_newest_first([view.rendition for view in views.values()]):
            if views[rendition.id].stale:
                continue
            rendered = self._settings.art_root / rendition.relative_path
            # Kept walking rather than falling straight to the master: a recorded
            # render whose file has gone is not a reason to ignore an older one
            # that is still there and still current.
            if rendered.is_file():
                return ThumbnailSource(
                    kind=RenditionKind.TV_DISPLAY.value,
                    path=rendered,
                    generated_at=rendition.generated_at,
                )

        master = self._settings.art_root / original.relative_path
        if not master.is_file():
            raise ThumbnailUnavailable(f"The master image is recorded at {original.relative_path} but no file is there.")
        return ThumbnailSource(kind="original", path=master, generated_at=None)

    def thumbnail(self, artwork_id: str) -> Path:
        """An absolute path to a current thumbnail, generating one if needed."""
        source = self.source_for(artwork_id)
        cached = self._settings.directory / f"{artwork_id}.jpg"
        # The id reaches this filename from a URL path segment. Nothing that is
        # not a catalogue id gets this far — `source_for` refuses an unknown work
        # first — but the guard is here rather than resting on that, because a
        # traversal is only ever one refactor away from being written to disk and
        # this check costs nothing.
        if not cached.resolve().is_relative_to(self._settings.directory.resolve()):
            raise ServiceError(f"Artwork id {artwork_id!r} does not name a file inside the thumbnail cache.")

        held = next(
            (view for view in self._catalogue.list_renditions(artwork_id) if view.rendition.kind is RenditionKind.THUMBNAIL),
            None,
        )
        # All four conditions, because each one alone is satisfiable while the
        # cached file is wrong: a fresh row can point at a file someone deleted,
        # a present file can predate the master it claims to depict, and a
        # thumbnail of the master can outlive the moment a canvas replaced it as
        # what this work looks like.
        if held is not None and not held.stale and cached.is_file() and _drawn_from(held.rendition, source):
            return cached

        if held is not None and not held.stale and cached.is_file():
            # Reached only when `_drawn_from` is the condition that failed, which
            # is the one whose *wrong* answer costs work rather than a wrong
            # picture: anything holding the comparison false — a canvas upsert
            # that stopped restamping, a clock correction, a caller passing the
            # wrong stamp — re-encodes a 4K canvas per card per page load and
            # reaches the operator as "the grid got slow", against a journal with
            # nothing in it. INFO rather than DEBUG for that reason: the
            # deployment where this matters is the one running with DEBUG off.
            log.info(
                "regenerating the thumbnail for %s: it predates the %s it would be drawn from",
                artwork_id,
                source.kind,
                extra={
                    "event": "thumbnail.superseded",
                    "work_id": artwork_id,
                    "source_kind": source.kind,
                    "thumbnail_generated_at": held.rendition.generated_at.isoformat(),
                    "source_generated_at": None if source.generated_at is None else source.generated_at.isoformat(),
                },
            )

        self._write(source.path, cached)
        # Recorded after the file exists, so a row can never promise an image
        # that is not there. The reverse — a file with no row — costs one
        # regeneration and nothing else.
        self._catalogue.record_rendition(
            artwork_id=artwork_id,
            kind=RenditionKind.THUMBNAIL,
            # The box requested, not the size produced: fitting preserves aspect
            # so one edge comes out shorter, and recording that would give every
            # work its own geometry and defeat the upsert this depends on.
            target_width=THUMBNAIL_MAX_EDGE_PX,
            target_height=THUMBNAIL_MAX_EDGE_PX,
            path=str(cached.relative_to(self._settings.art_root)),
        )
        return cached

    def _write(self, source: Path, destination: Path) -> None:
        """Downscale `source` into `destination`, atomically."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        # A distinct name per attempt, so two requests for the same work racing
        # each other cannot write the same temp file: rename is atomic, but two
        # writers sharing one path are interleaving their bytes before it.
        staging = destination.with_name(f"{destination.name}.{uuid.uuid4().hex}.tmp")
        # **Cleanup in `finally`, not per handler.** The staging name is unique
        # per attempt, so anything this method fails to unlink is stranded for
        # good and every retry strands another — and cleaning up only inside the
        # handlers meant an exception neither of them named leaked a file as well
        # as a 500. After a successful `os.replace` the name is already gone, so
        # the unlink is a no-op on the happy path.
        try:
            frame = encode_downscaled(source, max_edge=THUMBNAIL_MAX_EDGE_PX, quality=THUMBNAIL_JPEG_QUALITY)
            staging.write_bytes(frame.data)
            os.replace(staging, destination)
        except Image.DecompressionBombError as exc:
            raise ThumbnailUnavailable(f"The image at {source.name} is too large to open safely: {exc}") from exc
        except (OSError, UnidentifiedImageError, ValueError) as exc:
            # `ValueError` is here for the same reason `inline_preview` carries
            # it: Pillow raises it from `convert` for at least one mode (`La`).
            # It was absent here while the sibling had it, which is exactly the
            # drift that comes of keeping two copies of one decode.
            raise ThumbnailUnavailable(f"The image at {source.name} could not be read: {exc}") from exc
        finally:
            staging.unlink(missing_ok=True)
