"""Local copies of candidate previews, so review never depends on a museum.

The review grid — in the browser and over MCP alike — has to show the picture. A
source-side URL alone means a curator reviewing an hour later sees broken images
when a museum is down or rate-limiting, and it means the MCP surface has nothing
local to inline. So the bytes are pulled once, when the instance is found, and
the catalogue records where they landed.

**These files are a third class, and the distinction is the data model's.**
Upstream files are backed up and never regenerated; derived files regenerate per
device and are never transported. A candidate preview is neither: it is
disposable, safe to delete the moment its work reaches a terminal verdict, and
deleting one never affects the catalogue — an accepted work's imagery comes from
acquisition, not from the preview that helped someone decide.

**A preview that will not download is not a failure.** The instance is still
real, still selectable, and still carries a source-side URL to fall back on.
Losing a work over a missing thumbnail would be the tail wagging the dog, so
every failure path here reports absence rather than raising. The two re-encoders
below hold the same posture for the same reason, one step further along: a file
that will not decode costs its instance a picture, never its place in the
listing.

**Two re-encoders, because there are two readers with unrelated budgets.** A model
pays for a picture in context tokens and a curator pays for it in pixels on a
screen. They share the decode and the media type and nothing else — see the two
box constants, which say why sharing one would be a slow leak from the visual
side into the model's context.
"""

import base64
import hashlib
import logging
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from PIL import Image, UnidentifiedImageError

from curation.services.errors import ServiceError
from curation.services.imaging import EncodedFrame, encode_downscaled

log = logging.getLogger(__name__)

#: Extensions a preview may keep from its URL. Anything else gets the default:
#: the name is ours, and a suffix copied unchecked from a URL is a path
#: component an attacker-controlled string could choose.
_KNOWN_SUFFIXES: Final[frozenset[str]] = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif", ".tif", ".tiff"})

_DEFAULT_SUFFIX: Final[str] = ".jpg"

#: How much of the URL digest names the file. Long enough that a collision is
#: not a practical concern across a catalogue of this size, short enough that the
#: directory stays readable when someone goes looking.
_NAME_LENGTH: Final[int] = 24

#: The box an inlined preview is fitted into, in pixels on its long edge.
#:
#: **This is a token budget, not a visual one.** An image costs a client roughly
#: `width * height / 750` tokens, so 400 px on the long edge is about 160 tokens
#: for a landscape scan and a forty-work batch is about 6,400 — under the 10,000
#: at which Claude Code warns, and well under its 25,000 ceiling, with room left
#: for the text beside it. Raising a client's own limit does not buy headroom
#: here: `_meta["anthropic/maxResultSizeChars"]` governs text and images do not
#: benefit from it.
#:
#: Deliberately smaller than the catalogue thumbnail's 480 px and deliberately
#: not shared with it. That one is fitted to a browser grid on a retina display
#: and is bounded by what looks right; this one is fitted to a model's context
#: and is bounded by arithmetic. One constant serving both would be moved by
#: whichever pressure spoke last, and the visual pressure only ever pushes up.
#:
#: It is sufficient for the judgement the review gate exists to make — is this
#: the right painting, and is it appropriate for a living room. It is *not*
#: sufficient for judging mat colour, which happens after acceptance on a real
#: screen.
INLINE_MAX_EDGE_PX: Final[int] = 400

#: Quality for the re-encode. Lower than the browser thumbnail's, because every
#: byte here is spent inside a model's context rather than on a screen, and the
#: artefacts a curator would notice at 480 px on a retina panel are invisible in
#: the judgement this image is for.
INLINE_JPEG_QUALITY: Final[int] = 75

#: The box a preview is fitted into on its way to a browser, in pixels.
#:
#: **Its own constant, not `INLINE_MAX_EDGE_PX` reused, and that separation is the
#: point rather than an accident.** That one is bounded by arithmetic — an image
#: costs a model roughly `width * height / 750` tokens — and this one is bounded
#: by a review card on a screen. One constant serving both would be moved by
#: whichever pressure spoke last, and the visual pressure only ever pushes up,
#: which would silently spend a curator's model context on pixels it cannot use.
#:
#: The value matches the catalogue thumbnail's for the reason both were sized:
#: cards of about this width on a retina display. It is deliberately not *shared*
#: with it either — that one downscales a 47-megapixel master a work already
#: holds, this one re-encodes a preview a museum served — so the two move for
#: unrelated reasons and neither should drag the other.
#:
#: Sufficient for the judgement the review gate exists to make: is this the right
#: painting, and is it appropriate for a living room. It is emphatically *not*
#: how a curator judges resolution — a 900 px scan and a 6000 px scan look
#: identical at any card size, which is why every instance travels with the size
#: it would render at on the wall, in inches, beside the picture.
BROWSER_MAX_EDGE_PX: Final[int] = 480

#: Quality for the browser's copy. Higher than the inline one's, because these
#: bytes land on a screen a curator is looking at rather than in a context window.
BROWSER_JPEG_QUALITY: Final[int] = 82

#: What a re-encoded preview is declared as on the wire, whichever reader asked.
#: Everything becomes JPEG on the way out — museums serve JPEG, PNG and the
#: occasional TIFF — and one media type for both is not merely tidy. For a model,
#: a content block whose type varied per instance would make the cost per image
#: depend on the museum's choice of format rather than on the picture. For a
#: browser it is stronger than that: a cached preview's *suffix* is taken from a
#: URL and falls back to `.jpg` for anything unrecognised, so the name on disk is
#: not evidence of what the bytes are — and a TIFF served under a type a browser
#: cannot paint is a blank card with nothing saying why.
PREVIEW_MEDIA_TYPE: Final[str] = "image/jpeg"


@dataclass(frozen=True, slots=True)
class PreviewSettings:
    """Where the image tree is, and where cached previews go inside it.

    Passed in rather than resolved here for the reason every other settings
    object gives: a service that read its own configuration could not be tested
    against two deployments and would make every caller share one.
    """

    art_root: Path
    directory: Path

    def __post_init__(self) -> None:
        """Refuse a cache outside the tree, at wiring time rather than mid-run.

        Every catalogue path is relative to `ART_ROOT`, so a preview written
        anywhere else has no representable path. Caught here it is a startup
        failure naming both directories; caught where the row is written it is a
        `ValueError` from `relative_to`, thrown on a worker thread partway
        through a run.
        """
        if not self.directory.is_relative_to(self.art_root):
            raise ServiceError(f"The preview cache at {self.directory} must sit inside ART_ROOT at {self.art_root}.")


class PreviewCache:
    """Fetch a preview once and hand back the path the catalogue should record."""

    def __init__(self, settings: PreviewSettings, fetch: Callable[[str], bytes | None]) -> None:
        self._settings = settings
        #: Injected rather than reached for, because the transport belongs behind
        #: the image seam: this class writes files and computes paths, and a
        #: service that also made HTTP requests could not be tested without one.
        self._fetch = fetch

    def store(self, url: str) -> str | None:
        """Cache the bytes at `url`, returning the path relative to `ART_ROOT`.

        `None` means no local copy exists — the fetch failed, or returned
        nothing. The caller records the instance regardless, with its source-side
        URL and no `preview_path`.

        **Already-cached bytes are not re-fetched.** The name is derived from the
        URL, so a work re-searched later finds its preview already on disk and
        the museum is asked once per distinct image rather than once per attempt.
        """
        destination = self._path_for(url)
        relative = str(destination.relative_to(self._settings.art_root))
        # The cache read and the provider call are guarded separately, because an
        # `OSError` can come out of either and they are different diagnoses: an
        # unreadable cache directory is this machine's problem, and a provider
        # raising one is the network's. One handler over both would report the
        # second as the first, sending whoever reads the log to the wrong place.
        try:
            if destination.exists() and destination.stat().st_size > 0:
                return relative
        except OSError as exc:
            return self._absent(url, f"the cache could not be read: {exc}")
        try:
            payload = self._fetch(url)
        except Exception as exc:  # prawduct:allow prawduct/broad-except -- a provider fault must not fail the work
            # The seam promises `None` for a preview it cannot get, and a
            # provider that raises something else instead — an httpx URL error is
            # not an `HTTPError` — would otherwise reach the run-level handler and
            # fail the whole run over a thumbnail. That is precisely the outcome
            # this module exists to prevent, so the contract is enforced on this
            # side rather than trusted.
            return self._absent(url, f"the provider raised {type(exc).__name__}: {exc}")
        if not payload:
            # Distinguishes nothing-came-back from a fetch that reported failure:
            # the seam reports both as `None`, and neither is worth failing a
            # work over.
            return self._absent(url, "the provider returned no bytes")
        # Written beside the target and renamed, so a process that dies mid-write
        # leaves no half-file that the `exists()` check above would later treat as
        # a valid cache hit.
        staging = destination.with_name(f"{destination.name}.partial")
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            staging.write_bytes(payload)
            staging.replace(destination)
        except OSError as exc:
            # A full or read-only disk is a real operational condition, and it
            # must degrade the review card rather than end a run that has already
            # found the images it went looking for.
            #
            # The partial is removed on the way out. Its name is derived from the
            # destination, so every retry for this preview writes the same path —
            # a leftover is never read (nothing looks for `.partial`) and never
            # reclaimed either, and on the one failure this handles, a full disk,
            # the stranded bytes are the last thing the device can afford.
            #
            # The cleanup can fail for the same reason the write did, and if it
            # does the original failure is still the one worth reporting —
            # replacing it with the tidy-up's would name the second-order problem
            # and lose the first.
            with suppress(OSError):
                staging.unlink(missing_ok=True)
            return self._absent(url, f"the bytes could not be written: {exc}")
        log.info(
            "cached a preview",
            extra={"event": "preview.cached", "preview_url": url, "path": relative, "bytes": len(payload)},
        )
        return relative

    def _absent(self, url: str, why: str) -> None:
        """Report that no local copy exists, with the reason, and carry on.

        One exit for every way a preview can fail to arrive, so the log line
        cannot drift between them and a caller has exactly one thing to handle.
        """
        log.info(
            "no preview was cached for an instance; review will fall back to its source URL",
            extra={"event": "preview.absent", "preview_url": url, "reason": why},
        )
        return None

    def _path_for(self, url: str) -> Path:
        """Where this URL's bytes live. Derived from the URL, so it is stable.

        The name is a digest rather than anything taken from the URL's own path,
        because a museum's filename is not ours to trust as a path component and
        two museums may well use the same one.
        """
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:_NAME_LENGTH]
        suffix = Path(url.split("?", 1)[0]).suffix.lower()
        return self._settings.directory / f"{digest}{suffix if suffix in _KNOWN_SUFFIXES else _DEFAULT_SUFFIX}"


@dataclass(frozen=True, slots=True)
class InlinePreview:
    """One cached preview, small enough to travel inside a tool result.

    The bytes are base64 already, because that is the only form the wire takes
    them in and handing a caller raw bytes it must encode is an invitation for
    two call sites to encode them differently.

    The dimensions are the *encoded* ones rather than the box that was asked
    for: fitting preserves aspect ratio, so one edge comes out shorter, and a
    caller reporting the box would state a size the picture does not have.
    """

    data: str
    media_type: str
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class RenderedPreview:
    """One cached preview, re-encoded for a browser to paint directly.

    Raw bytes rather than base64: these travel as an HTTP response body, and
    encoding them for a transport that does not need it would cost a third more
    bytes on every card of a thirty-work grid.

    No dimensions. The MCP twin reports them because a model cannot see the
    picture and prices it by area; a browser lays the image out from the bytes
    themselves, so a size in the payload would be a number nothing reads.
    """

    data: bytes
    media_type: str


def inline_preview(path: Path) -> InlinePreview | None:
    """Downscale a cached preview into something a tool result can carry.

    `None` means this instance travels without a picture, and it is never an
    error: a preview is a disposable convenience, and the same reasoning that
    makes a failed *download* report absence makes a failed *decode* report it
    too. The instance is still real, still listed, and still carries its
    source-side URL. Raising instead would lose a curator the other thirty-nine
    works over one museum's malformed JPEG.
    """
    frame = _rendered(path, max_edge=INLINE_MAX_EDGE_PX, quality=INLINE_JPEG_QUALITY)
    if frame is None:
        return None
    return InlinePreview(
        data=base64.b64encode(frame.data).decode("ascii"),
        media_type=PREVIEW_MEDIA_TYPE,
        width=frame.width,
        height=frame.height,
    )


def browser_preview(path: Path) -> RenderedPreview | None:
    """Downscale a cached preview into bytes a browser renders.

    Absence is reported the same way and for the same reason as above: a review
    card whose picture will not decode still shows the work, its size on the
    wall, and its source URL, and is still selectable. The card knows before it
    asks — the listing carries `preview_available` — so a `None` here is the
    narrow race where the file went away between the listing and the request.
    """
    frame = _rendered(path, max_edge=BROWSER_MAX_EDGE_PX, quality=BROWSER_JPEG_QUALITY)
    return None if frame is None else RenderedPreview(data=frame.data, media_type=PREVIEW_MEDIA_TYPE)


def _rendered(path: Path, *, max_edge: int, quality: int) -> EncodedFrame | None:
    """Re-encode a cached preview, reporting absence rather than raising.

    One decode for both callers. They differ in the box, the quality and what
    they wrap the bytes in, and in nothing else — and this module's own sibling
    is the standing argument for not keeping two copies of a decode: the two that
    predate `imaging.py` had already drifted on which exceptions they named.

    **Nothing is cached on the way out, for either caller.** The input is already
    a preview — ARTIC's default is 843 px on the long edge — and `draft` decodes
    it at a reduced scale, so a full forty-work batch measured **under 300 ms**
    on the build machine (2026-08-03), and a 3000 px input cost no more than an
    843 px one because the reduced-scale decode absorbs the difference. What a
    cache would cost is a second disposable class: files derived from files that
    are themselves deleted when a work is decided, needing their own place in
    that sweep and their own answer to "is this one stale". The preview lifecycle
    is deliberately the only one of its kind.
    """
    try:
        return encode_downscaled(path, max_edge=max_edge, quality=quality)
    except Image.DecompressionBombError as exc:
        # Pillow's own guard against a decompression bomb. Caught by name rather
        # than swept up with the rest, because a file engineered to exhaust
        # memory is worth a different log line from one that is merely corrupt.
        return _no_inline(path, f"it is too large to open safely: {exc}")
    except (OSError, UnidentifiedImageError, ValueError) as exc:
        # `OSError` and `UnidentifiedImageError` are the ordinary two — a
        # truncated download, a file that is not an image — and are what the
        # tests exercise.
        #
        # `ValueError` is boundary defence rather than a covered path, and the
        # measurement is worth recording so nobody re-derives it: Pillow raises
        # it from `convert` for at least one mode (`La`, premultiplied greyscale
        # alpha), but no image format round-trips to that mode through
        # `Image.open`, so it was not reachable from a file on disk when this was
        # written. It is caught anyway because the alternative is one museum's
        # unusual file costing a curator the other thirty-nine works in the
        # listing, which is the outcome this whole module exists to prevent.
        return _no_inline(path, f"it could not be read: {exc}")


def _no_inline(path: Path, why: str) -> None:
    """Report that no picture travels with this instance, with the reason.

    One exit for every way a preview can fail to be re-encoded, so the log line
    cannot drift between them — the same shape `_absent` holds for the download
    it mirrors.
    """
    log.info(
        "a cached preview could not be rendered; the instance is listed without a picture",
        extra={"event": "preview.not_inlined", "path": str(path), "reason": why},
    )
    return None
