"""Small images of held works, for a surface that shows forty of them at once.

A grid of the real files is not a page: the masters in this corpus run to 47
megapixels and 40 MB each, and the television renditions are 4K. So the browser
surface is served downscaled copies, cached on disk and **recorded in the
catalogue as renditions**, which is what keeps them from becoming an
untracked pile of files nothing owns. `RenditionKind.THUMBNAIL` has been in the
data model since the catalogue was designed; this is its producer.

**Staleness is the catalogue's rule, not a second one invented here.** A
rendition carries the content hash of the master it was made from, so a thumbnail
is stale exactly when the work's original changes — the same relation that
governs the television render, applied by the same code.

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
from pathlib import Path
from typing import Final

from PIL import Image, ImageOps, UnidentifiedImageError

from curation.persistence.records import RenditionKind
from curation.services.catalogue import CatalogueService
from curation.services.errors import ServiceError

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


@dataclass(frozen=True, slots=True)
class ThumbnailSettings:
    """Where the images are and where their downscaled copies go.

    Passed in rather than resolved here for the reason `WallSettings` gives: a
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

        for view in self._catalogue.list_renditions(artwork_id):
            if view.rendition.kind is not RenditionKind.TV_DISPLAY or view.stale:
                continue
            rendered = self._settings.art_root / view.rendition.relative_path
            if rendered.is_file():
                return ThumbnailSource(kind=RenditionKind.TV_DISPLAY.value, path=rendered)

        master = self._settings.art_root / original.relative_path
        if not master.is_file():
            raise ThumbnailUnavailable(f"The master image is recorded at {original.relative_path} but no file is there.")
        return ThumbnailSource(kind="original", path=master)

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
        # All three conditions, because each one alone is satisfiable while the
        # cached file is wrong: a fresh row can point at a file someone deleted,
        # and a present file can predate the master it claims to depict.
        if held is not None and not held.stale and cached.is_file():
            return cached

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
        try:
            with Image.open(source) as image:
                # Decodes the JPEG at a reduced DCT scale — up to eight times
                # smaller per axis — so a 47-megapixel master never becomes a
                # 47-megapixel bitmap in memory. A no-op for other formats.
                image.draft("RGB", (THUMBNAIL_MAX_EDGE_PX, THUMBNAIL_MAX_EDGE_PX))
                upright = ImageOps.exif_transpose(image) or image
                # CMYK and greyscale scans both appear in museum downloads, and
                # neither saves as a JPEG a browser will render the same way.
                frame = upright.convert("RGB")
                frame.thumbnail((THUMBNAIL_MAX_EDGE_PX, THUMBNAIL_MAX_EDGE_PX), Image.Resampling.LANCZOS)
                frame.save(staging, format="JPEG", quality=THUMBNAIL_JPEG_QUALITY, optimize=True)
        except Image.DecompressionBombError as exc:
            staging.unlink(missing_ok=True)
            raise ThumbnailUnavailable(f"The image at {source.name} is too large to open safely: {exc}") from exc
        except (OSError, UnidentifiedImageError) as exc:
            staging.unlink(missing_ok=True)
            raise ThumbnailUnavailable(f"The image at {source.name} could not be read: {exc}") from exc
        os.replace(staging, destination)
