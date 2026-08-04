"""Turning a catalogued work's source into a held original.

This is the operation the fetch paths exist to serve, and everything policy-shaped
lives here rather than in them: which source is used, whether there is room to
start, what a failure is recorded as, and what is reclaimed afterwards. The
modules beside this one know how to get bytes; none of them knows what a work is.

**Every outcome is recorded, including the ones that are not failures.** A tiled
fetch that returns most of its tiles produces a usable image with gaps, which the
catalogue records as `partial_tiles` — a normal outcome, not an error — and the
work goes on the wall. Recording that faithfully is what lets a curator ask for a
re-fetch later on evidence rather than on suspicion.

**A refusal is data about a source, not a fault in the process.** A URL the fetch
policy rejects, a body over the ceiling, a museum that has gone away: each records
a failed fetch against the source and returns, so one bad source in a batch never
ends the pass over the works behind it. The two things that *do* raise are the
ones no source is responsible for — the binary being absent, and the disk being
too full to start — because retrying the work cannot fix either.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Final

from curation.acquisition.dezoomify import (
    TileOutcome,
    reclaim_tile_cache,
    tile_fetch,
)
from curation.acquisition.direct import StreamOpener, direct_fetch
from curation.acquisition.space import NotEnoughSpace, require_free_space
from curation.acquisition.urls import Resolver, UrlRefused, check_fetchable, system_resolver
from curation.persistence.records import AcquisitionMethod, FetchStatus, Source
from curation.services.catalogue import CatalogueService
from curation.services.errors import ServiceError
from curation.services.imaging import measure

log = logging.getLogger(__name__)

#: What a work's master image is called on disk. The work's own id, because a
#: title is not unique, not stable, and not a filename — the 2024 tree keyed files
#: by title and could not hold two works with the same name.
_FILENAME: Final[str] = "{artwork_id}.jpg"


class AcquisitionOutcome(Enum):
    """How an attempt ended, from the catalogue's point of view."""

    ACQUIRED = "acquired"
    PARTIAL = "partial"
    FAILED = "failed"
    #: The fetch worked and was refused anyway, because promoting it would have
    #: lowered the quality of the image the work already holds. Distinct from
    #: `FAILED` on purpose: the source answered correctly, and recording this as a
    #: failure would put a `failed` status on a working source and send whoever
    #: reads it to a museum that is fine.
    KEPT_HELD = "kept_held"


@dataclass(frozen=True, slots=True)
class AcquisitionResult:
    """What happened, in terms a curator or an agent can act on."""

    artwork_id: str
    source_id: str
    outcome: AcquisitionOutcome
    detail: str
    relative_path: str | None = None
    byte_size: int = 0
    width: int | None = None
    height: int | None = None

    @property
    def acquired(self) -> bool:
        """Whether *this attempt* is the one the work's held image came from.

        `KEPT_HELD` is deliberately false here even though the work does hold an
        image afterwards: the one caller is the tile-cache reclaim, and reclaiming
        on a refused promotion would throw away the tiles of the very fetch that
        was told to try again. "The work has an image" and "this attempt produced
        it" are different questions, and only the second one has callers.
        """
        return self.outcome in (AcquisitionOutcome.ACQUIRED, AcquisitionOutcome.PARTIAL)


@dataclass(frozen=True, slots=True)
class AcquisitionSettings:
    """Where acquisition writes, what it may spend, and what it refuses.

    Passed in for the reason every settings object in this plane is: a service
    that resolved its own configuration could not be handed a second deployment
    in a test, and would make every caller share one.
    """

    art_root: Path
    originals_path: Path
    tile_cache_path: Path
    user_agent: str
    tile_binary: str
    tile_max_pixels: int
    tile_timeout_seconds: int
    max_image_bytes: int
    min_free_bytes: int

    def __post_init__(self) -> None:
        """Refuse a tree outside `ART_ROOT` at wiring time rather than mid-fetch.

        Every catalogue path is relative to `ART_ROOT`, so an original written
        anywhere else has no representable path. Caught here it names both
        directories at startup; caught where the row is written it is a
        `ValueError` from `relative_to` thrown partway through an acquisition.
        """
        for directory in (self.originals_path, self.tile_cache_path):
            if not directory.is_relative_to(self.art_root):
                raise ServiceError(f"The acquisition directory at {directory} must sit inside ART_ROOT at {self.art_root}.")


class AcquisitionService:
    """Acquire the master image for a catalogued work."""

    def __init__(
        self,
        catalogue: CatalogueService,
        settings: AcquisitionSettings,
        *,
        open_stream: StreamOpener,
        resolve: Resolver = system_resolver,
    ) -> None:
        self._catalogue = catalogue
        self._settings = settings
        #: Injected for the same reason `PreviewCache` injects its fetch: the
        #: transport belongs behind the image seam, and a service that also made
        #: HTTP requests could not be exercised without a network.
        self._open_stream = open_stream
        #: The other half of the same seam. Deciding whether a host is publicly
        #: routable is not answerable without asking what it resolves to, so the
        #: policy reaches DNS — and a service that reached it unconditionally
        #: would make every rule above it depend on the network the suite runs
        #: on, including the rules that have nothing to do with hosts.
        self._resolve = resolve

    def acquire(self, artwork_id: str, *, source_id: str | None = None) -> AcquisitionResult:
        """Fetch this work's image and record what came back.

        `source_id` names which source to use; omitting it takes the work's
        primary, and a work with no primary source is a refusal rather than a
        guess — "which of these is the right one" is exactly the judgement
        acceptance already made, and re-making it here could silently disagree.
        """
        source = self._select_source(artwork_id, source_id=source_id)

        # Before anything is fetched, and before the URL is even looked at: a disk
        # with no headroom is not a fact about this source, and checking it after
        # a 900 MB download would be checking it too late to prevent anything.
        require_free_space(self._settings.originals_path, required_bytes=self._settings.min_free_bytes)

        try:
            url = check_fetchable(source.url, resolve=self._resolve)
        except UrlRefused as exc:
            return self._record_failure(source, f"the source URL was refused: {exc}")

        destination = self._settings.originals_path / _FILENAME.format(artwork_id=artwork_id)
        if source.acquisition_method is AcquisitionMethod.DEZOOMIFY:
            return self._acquire_tiled(source, url=url, destination=destination)
        if source.acquisition_method is AcquisitionMethod.DIRECT_HTTP:
            return self._acquire_direct(source, url=url, destination=destination)
        # `api` is a declared method with no producer: nothing in this deployment
        # records a source that carries it, because the one museum client in the
        # product resolves to tiled URLs. Saying so is the honest answer — a path
        # that guessed at a shape no source has would be a fetch nobody could
        # have tested against a real response.
        return self._record_failure(
            source,
            f"no fetch path is built for acquisition_method={source.acquisition_method.value!r}; "
            "no source in this deployment records it",
        )

    def _acquire_tiled(self, source: Source, *, url: str, destination: Path) -> AcquisitionResult:
        # Its own directory per source, which is what makes the reclaim below
        # precise: one shared cache could only ever be emptied wholesale, taking
        # the tiles of a fetch that is still worth resuming.
        tile_cache = self._settings.tile_cache_path / source.id
        # `DezoomifyUnavailable` is deliberately allowed to propagate rather than
        # recorded against the source: no URL is at fault, and a `failed` row here
        # would send whoever reads it to a museum rather than to the deployment
        # that is missing a binary.
        result = tile_fetch(
            url,
            destination=destination,
            tile_cache=tile_cache,
            binary=self._settings.tile_binary,
            user_agent=self._settings.user_agent,
            max_width=self._settings.tile_max_pixels,
            max_height=self._settings.tile_max_pixels,
            timeout_seconds=self._settings.tile_timeout_seconds,
        )

        if not result.usable:
            return self._record_failure(source, result.detail)

        status = FetchStatus.OK if result.outcome is TileOutcome.COMPLETE else FetchStatus.PARTIAL_TILES
        outcome = AcquisitionOutcome.ACQUIRED if status is FetchStatus.OK else AcquisitionOutcome.PARTIAL
        recorded = self._record_success(
            source,
            staged=result.path,
            destination=destination,
            byte_size=result.byte_size,
            content_hash=_hash_file(result.path),
            status=status,
            outcome=outcome,
            detail=result.detail,
        )
        if recorded.acquired and result.outcome is TileOutcome.COMPLETE:
            # After the image is held, not before: a promotion that fails on
            # unreadable bytes leaves the work wanting a retry, and the tiles are
            # what makes that retry cheap. Reclaimed only when there is genuinely
            # nothing left to resume.
            reclaim_tile_cache(tile_cache)
        return recorded

    def _acquire_direct(self, source: Source, *, url: str, destination: Path) -> AcquisitionResult:
        result = direct_fetch(
            url,
            destination=destination,
            open_stream=self._open_stream,
            max_bytes=self._settings.max_image_bytes,
        )
        if not result.usable:
            return self._record_failure(source, result.detail)
        return self._record_success(
            source,
            staged=result.path,
            destination=destination,
            byte_size=result.byte_size,
            content_hash=result.content_hash,
            status=FetchStatus.OK,
            outcome=AcquisitionOutcome.ACQUIRED,
            detail=result.detail,
        )

    def _record_success(
        self,
        source: Source,
        *,
        staged: Path | None,
        destination: Path,
        byte_size: int,
        content_hash: str | None,
        status: FetchStatus,
        outcome: AcquisitionOutcome,
        detail: str,
    ) -> AcquisitionResult:
        """Promote a staged fetch to the held original, or discard it and say why.

        **Nothing before this point may touch `destination`, and this is why.** A
        re-fetch is an ordinary operation — the surface actively invites one after
        a partial result — so a failing retry must cost the work nothing. Both
        fetch paths therefore stage, and the file the work is displaying is
        replaced only once the new bytes have been proved readable. Otherwise a
        failed retry leaves an `Original` row naming a file that was deleted to
        make room for bytes that never arrived, and the tool tip promising "a
        failed fetch replaces nothing" is false at exactly the moment a curator
        relies on it.

        **The same promise has a second half, and staging alone does not keep
        it.** A fetch that succeeds *partially* is not a failure and reaches this
        method with usable bytes — so before staging was ever involved, a gappy
        re-fetch would promote straight over a complete master a work was already
        displaying. A retry is the operation most likely to produce one, because
        the surface recommends retrying after a partial result. So quality is
        compared here, and a result that would lower it is discarded with the held
        image untouched.
        """
        assert staged is not None and content_hash is not None  # noqa: S101 - guarded by `usable` above
        if refusal := self._would_lower_quality(source.artwork_id, incoming=status):
            _discard(staged)
            # Deliberately no `record_fetch`: the source answered, and stamping it
            # `partial_tiles` would overwrite the status of the fetch that produced
            # the image the work is keeping — the very fact the next comparison
            # reads. Nothing about this attempt changes what the work holds, so
            # nothing about the work is written.
            log.info(
                "kept the held original for %s: %s",
                source.artwork_id,
                refusal,
            )
            return AcquisitionResult(
                artwork_id=source.artwork_id,
                source_id=source.id,
                outcome=AcquisitionOutcome.KEPT_HELD,
                detail=refusal,
            )
        try:
            width, height = measure(staged)
        except Exception as exc:  # prawduct:allow prawduct/broad-except -- attacker-influenced bytes, reported not raised
            # Bytes arrived and are not an image this process can read. A failed
            # acquisition rather than a held original: a row naming an undecodable
            # file passes every later check by size and fails at render time.
            #
            # Broad on purpose. The imaging seam raises what Pillow raises, and
            # that is deliberately not one family — `UnidentifiedImageError` and a
            # truncated file give `OSError`, a `La`-mode image gives `ValueError`,
            # and an image engineered to exhaust memory gives
            # `DecompressionBombError`, which derives straight from `Exception`.
            # These bytes came from a URL discovery found, which the security model
            # treats as attacker-influenceable, so the one that is *chosen* by an
            # attacker is the one a narrower catch would let escape — orphaning the
            # staged file and failing the call instead of the work.
            # Logged with its type and traceback before it becomes a recorded
            # fetch failure. Without this a `TypeError` from a future edit to
            # `measure()` reads in the journal as a museum serving bad bytes, and
            # the one thing that would identify it as ours is nowhere. `direct.py`
            # waives the same rule and logs the same way, for the same reason.
            log.warning(
                "measuring the fetched image for %s raised %s",
                source.artwork_id,
                type(exc).__name__,
                exc_info=True,
            )
            _discard(staged)
            return self._record_failure(source, f"the fetched bytes are not a readable image: {exc}")

        staged.replace(destination)
        relative = str(destination.relative_to(self._settings.art_root))
        self._catalogue.record_original(
            artwork_id=source.artwork_id,
            source_id=source.id,
            path=relative,
            width=width,
            height=height,
            byte_size=byte_size,
            content_hash=content_hash,
            fetch_status=status,
        )
        self._catalogue.record_fetch(source.id, status=status)
        if not source.is_primary:
            # The source that produced the held original is what `is_primary`
            # means, so acquiring from a different one moves it rather than
            # leaving the catalogue asserting something that is no longer true.
            self._catalogue.set_primary_source(source.id)
        log.info(
            "acquired %s from %s as %s (%s bytes, %sx%s)",
            source.artwork_id,
            source.provider,
            status.value,
            byte_size,
            width,
            height,
        )
        return AcquisitionResult(
            artwork_id=source.artwork_id,
            source_id=source.id,
            outcome=outcome,
            detail=detail,
            relative_path=relative,
            byte_size=byte_size,
            width=width,
            height=height,
        )

    def _would_lower_quality(self, artwork_id: str, *, incoming: FetchStatus) -> str | None:
        """Say why this result must not replace the held original, or nothing.

        Only the complete/partial distinction is read. Pixel count deliberately is
        not: a complete fetch from a smaller scan is a legitimate re-acquisition —
        a curator moving a work to a different institution's file — and refusing it
        would have this guard second-guess a choice acceptance already made.

        Two partial results replace each other freely. Neither is authoritative,
        the second may hold more tiles than the first, and no tile count survives
        into either row to compare — so the only honest options are to allow it or
        to freeze the work at its first partial forever.
        """
        if incoming is not FetchStatus.PARTIAL_TILES:
            return None
        held = self._catalogue.get_original(artwork_id)
        if held is None:
            # Nothing to lower. A work's first image is an improvement on no image
            # even with gaps in it, which is why `partial_tiles` is a recorded
            # outcome rather than a refusal.
            return None
        if held.fetch_status is FetchStatus.PARTIAL_TILES:
            return None
        # `None` lands here with `OK`, and that is the protective reading rather
        # than an oversight: a row written before the column existed cannot be told
        # apart from a complete one, and treating it as partial would let exactly
        # the oldest originals be overwritten by a gappy fetch.
        held_quality = "complete" if held.fetch_status is FetchStatus.OK else "of unrecorded completeness"
        return (
            f"the fetch came back with missing tiles, and this work already holds an image {held_quality}; "
            "the held image is kept and nothing was replaced"
        )

    def _record_failure(self, source: Source, detail: str) -> AcquisitionResult:
        self._catalogue.record_fetch(source.id, status=FetchStatus.FAILED)
        log.info("acquisition of %s from %s failed: %s", source.artwork_id, source.provider, detail)
        return AcquisitionResult(
            artwork_id=source.artwork_id,
            source_id=source.id,
            outcome=AcquisitionOutcome.FAILED,
            detail=detail,
        )

    def _select_source(self, artwork_id: str, *, source_id: str | None) -> Source:
        sources = self._catalogue.list_sources(artwork_id)
        if not sources:
            raise ServiceError(f"Artwork {artwork_id!r} has no source to acquire from.")
        if source_id is not None:
            for source in sources:
                if source.id == source_id:
                    return source
            raise ServiceError(f"Source {source_id!r} does not belong to artwork {artwork_id!r}.")
        for source in sources:
            if source.is_primary:
                return source
        if len(sources) == 1:
            # Not a guess: one source is the only source, so naming it changes
            # nothing a curator decided.
            return sources[0]
        raise ServiceError(f"Artwork {artwork_id!r} has {len(sources)} sources and none is primary; " "name one with source_id.")


def _hash_file(path: Path | None) -> str:
    """Hash a file the fetch path did not hash while writing it.

    The tiled path cannot: the bytes are assembled by another process, so there
    is no stream to hash as it passes. The direct path hashes while streaming and
    never reaches here.
    """
    import hashlib

    assert path is not None  # noqa: S101 - only called for a usable result
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _discard(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        log.warning("could not remove the unusable image at %s: %s", path, exc)


__all__ = [
    "AcquisitionOutcome",
    "AcquisitionResult",
    "AcquisitionService",
    "AcquisitionSettings",
    "NotEnoughSpace",
]
