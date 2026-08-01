"""Catalogue operations — the only place their logic lives.

Everything above this module is a binding: the MCP tools unpack arguments,
call one method here, and format what comes back; the HTTP handlers will do
the same. Two implementations of "list the catalogue" would diverge within
weeks, and the divergence would show up as an agent and a click disagreeing
about the same catalogue, which reads as the product being untrustworthy
rather than as a bug.

**This is also where the catalogue's rules are enforced, at write time.** A rule
applied on the way out instead of on the way in is a rule the data can already
violate, and the violation is then permanent. Rules that span rows — exactly one
mat colour current, at most one primary source — are applied inside a store
transaction as a clear-then-set pair, because a pair that can be interrupted
between its halves leaves the catalogue in the state the rule forbids.

Works, artists, sources, originals, renditions and mat colours live here. Themes,
the standing directive and the manifest built from them live in `display.py`,
which holds this service; nothing here holds that one.

Methods are synchronous. The store is a local file answering point lookups in
well under a millisecond, and a synchronous core keeps this logic testable
without an event loop.
"""

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Final

from curation.persistence.catalogue import CatalogueStore
from curation.persistence.records import (
    AcquisitionMethod,
    Artist,
    Artwork,
    ArtworkStatus,
    FetchStatus,
    MatColor,
    MatMethod,
    Original,
    Rendition,
    RenditionKind,
    RightsStatus,
    Source,
    SourceClass,
)
from curation.services.display_fit import ArtworkBox, FitAssessment, assess_display_fit
from curation.services.errors import ServiceError
from curation.services.fields import description_markup, relative_path, require_member, require_text
from curation.services.store import store_write

log = logging.getLogger(__name__)

#: How many works a listing returns when the caller does not say.
DEFAULT_LIST_LIMIT: Final[int] = 25

#: The most a single listing will return. A cap exists because the MCP client
#: truncates oversized tool output, and a silently truncated list is worse than
#: a short one that says how much it left behind.
MAX_LIST_LIMIT: Final[int] = 100


@dataclass(frozen=True, slots=True)
class ArtworkDetail:
    """A work together with the artist record it points at, if any."""

    artwork: Artwork
    artist: Artist | None


@dataclass(frozen=True, slots=True)
class ArtworkListing:
    """One page of works, and enough context to describe it honestly."""

    entries: Sequence[ArtworkDetail]
    total: int
    limit: int
    offset: int

    @property
    def truncated(self) -> bool:
        """True when works matched the filter that this page does not carry."""
        return self.offset + len(self.entries) < self.total


@dataclass(frozen=True, slots=True)
class RenditionView:
    """A rendition and whether it still matches the image it was made from.

    Staleness is derived on every read rather than stored, so it cannot disagree
    with the original it is a statement about. The 2024 code expressed the same
    intent imperatively — clearing the television's state whenever it regenerated
    an image — which worked only at the one site that remembered to.
    """

    rendition: Rendition
    stale: bool


class CatalogueService:
    """Read and write the catalogue."""

    def __init__(self, store: CatalogueStore) -> None:
        self._store = store

    # -- reads: works ---------------------------------------------------------

    def list_artworks(
        self,
        *,
        status: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> ArtworkListing:
        """Page through the catalogue.

        `status` is optional: omitting it lists accepted and archived works
        together, which is what "the whole catalogue" means.
        """
        resolved_status = self._parse_status(status)
        resolved_limit = DEFAULT_LIST_LIMIT if limit is None else limit
        if not 1 <= resolved_limit <= MAX_LIST_LIMIT:
            raise ServiceError(f"limit must be between 1 and {MAX_LIST_LIMIT}, got {resolved_limit}.")
        if offset < 0:
            raise ServiceError(f"offset cannot be negative, got {offset}.")

        page = self._store.list_artworks(status=resolved_status, limit=resolved_limit, offset=offset)
        # Attribution is the first thing anyone judges a work by, so a listing
        # that returned a bare artist id would send every caller straight back
        # for a second read. Resolved here, memoised within the page: a page is
        # capped at MAX_LIST_LIMIT local point lookups, and works by the same
        # artist collapse to one.
        artists: dict[str, Artist | None] = {}
        entries = [
            ArtworkDetail(artwork=artwork, artist=self._resolve_artist(artwork.artist_id, artists)) for artwork in page.artworks
        ]
        return ArtworkListing(entries=entries, total=page.total, limit=resolved_limit, offset=offset)

    def get_artwork(self, artwork_id: str) -> ArtworkDetail:
        """Return one work in full, with its artist resolved."""
        artwork = self._require_artwork(artwork_id)
        return ArtworkDetail(artwork=artwork, artist=self._resolve_artist(artwork.artist_id, {}))

    # -- reads: how a work can be re-acquired ---------------------------------

    def list_sources(self, artwork_id: str) -> Sequence[Source]:
        """Every place this work can be obtained from, the primary one first.

        More than one is the point: a work held by several institutions survives
        any one of them reorganising its site, which is what makes re-acquiring
        it from scratch a promise rather than a hope.
        """
        self._require_artwork(artwork_id)
        return self._store.list_sources(artwork_id)

    def get_original(self, artwork_id: str) -> Original | None:
        """The master image this work holds, or None if none has been acquired."""
        self._require_artwork(artwork_id)
        return self._store.get_original(artwork_id)

    def display_fit(self, artwork_id: str, *, box: ArtworkBox) -> FitAssessment:
        """Judge the work's held original against the space it would be rendered into."""
        original = self.get_original(artwork_id)
        if original is None:
            raise ServiceError(f"Artwork {artwork_id!r} has no acquired original to judge.")
        return assess_display_fit(width=original.width, height=original.height, box=box)

    # -- reads: what has been rendered ----------------------------------------

    def list_renditions(self, artwork_id: str) -> Sequence[RenditionView]:
        """Every derived output for this work, each with whether it is current.

        A stale rendition is one whose source image is no longer the image the
        work holds. It is regenerated rather than served, so saying which are
        stale is the whole reason the parent's hash is carried on the row.
        """
        self._require_artwork(artwork_id)
        original = self._store.get_original(artwork_id)
        # No original at all means nothing can vouch for any rendition, so none
        # of them may be served on the strength of having once been generated.
        held_hash = None if original is None else original.content_hash
        return [
            RenditionView(rendition=rendition, stale=rendition.source_content_hash != held_hash)
            for rendition in self._store.list_renditions(artwork_id)
        ]

    # -- reads: the mat -------------------------------------------------------

    def mat_color_history(self, artwork_id: str) -> Sequence[MatColor]:
        """Every mat colour ever chosen for this work, newest first.

        Superseded choices are kept because mat quality is this product's
        subjective quality bar: "the new model picked a worse colour" has to be
        both answerable and reversible.
        """
        self._require_artwork(artwork_id)
        return self._store.list_mat_colors(artwork_id)

    def current_mat_color(self, artwork_id: str) -> MatColor | None:
        """The mat colour in force, or None if none has been chosen."""
        for mat_color in self.mat_color_history(artwork_id):
            if mat_color.is_current:
                return mat_color
        return None

    def resolve_details(self, artwork_ids: Sequence[str]) -> Sequence[ArtworkDetail]:
        """Return these works in the order given, each with its artist resolved.

        One artist lookup per distinct artist rather than per work: a theme is
        typically many works by few artists, and the caller is building a list to
        put on a wall rather than reading one record.
        """
        artists: dict[str, Artist | None] = {}
        entries: list[ArtworkDetail] = []
        for artwork_id in artwork_ids:
            artwork = self._require_artwork(artwork_id)
            entries.append(ArtworkDetail(artwork=artwork, artist=self._resolve_artist(artwork.artist_id, artists)))
        return entries

    # -- writes: artists and works --------------------------------------------

    def add_artist(
        self,
        *,
        name: str,
        nationality: str | None = None,
        born: int | None = None,
        died: int | None = None,
        lifespan_text: str | None = None,
        biography: str | None = None,
    ) -> Artist:
        """Record an artist and return it with its minted identity."""
        artist = Artist(
            id=str(uuid.uuid4()),
            name=require_text(name, field="name"),
            nationality=nationality,
            born=born,
            died=died,
            lifespan_text=lifespan_text,
            biography=biography,
        )
        store_write(self._store.add_artist, artist)
        return artist

    def add_artwork(
        self,
        *,
        title: str,
        artist_id: str | None = None,
        date_created: str | None = None,
        medium: str | None = None,
        dimensions: str | None = None,
        description: str | None = None,
        rights: str | None = None,
    ) -> Artwork:
        """Record a work in the catalogue and return it.

        A work enters the catalogue already accepted — there is no other way
        in. Everything before acceptance is a candidate, which is a separate
        entity with its own verdict, so an artwork never carries a pending or
        rejected state of its own to drift out of step with it.
        """
        if artist_id is not None and self._store.get_artist(artist_id) is None:
            raise ServiceError(f"No artist with id {artist_id!r} is in the catalogue.")
        now = datetime.now(UTC)
        artwork = Artwork(
            id=str(uuid.uuid4()),
            title=require_text(title, field="title"),
            created_at=now,
            status=ArtworkStatus.ACCEPTED,
            artist_id=artist_id,
            date_created=date_created,
            medium=medium,
            dimensions=dimensions,
            # Normalised on the way in, once, rather than by every renderer that
            # ever reads it back out.
            description=description_markup(description),
            rights=rights,
            accepted_at=now,
        )
        store_write(self._store.add_artwork, artwork)
        return artwork

    def archive_artwork(self, artwork_id: str) -> Artwork:
        """Take a work out of circulation, keeping its record and its mat history."""
        artwork = self._require_artwork(artwork_id)
        if artwork.status is ArtworkStatus.ARCHIVED:
            raise ServiceError(f"Artwork {artwork_id!r} is already archived.")
        archived = replace(artwork, status=ArtworkStatus.ARCHIVED)
        with self._store.transaction():
            store_write(self._store.update_artwork, archived)
            # A pin naming a work that is out of circulation is an instruction
            # the display plane can never carry out, so archiving withdraws it.
            #
            # This is the one directive write outside the service that owns the
            # directive, and the line it respects is integrity versus semantics:
            # clearing an unsatisfiable reference in the same transaction that
            # creates it, exactly as a dangling reference anywhere else would be.
            # It deliberately does NOT advance the sequence — archiving is not an
            # instruction to the display plane, and an advance would step the wall
            # to an unrelated work. Every rule about what an advance *means* lives
            # in the display service; none of them is duplicated here.
            directive = self._store.get_directive()
            if directive.pinned_work_id == artwork_id:
                # Said out loud: a standing instruction disappearing is exactly the
                # kind of silent state change that turns into "the wall stopped
                # doing what I told it" with nothing to read back.
                log.info("archiving %s withdrew the standing pin naming it", artwork_id)
                store_write(self._store.set_directive, replace(directive, pinned_work_id=None))
        return archived

    def restore_artwork(self, artwork_id: str) -> Artwork:
        """Return an archived work to circulation.

        Its renditions may have gone stale while it was away; they are checked
        against the held original's hash on every read, so nothing has to
        remember to invalidate them here.
        """
        artwork = self._require_artwork(artwork_id)
        if artwork.status is ArtworkStatus.ACCEPTED:
            raise ServiceError(f"Artwork {artwork_id!r} is not archived.")
        restored = replace(artwork, status=ArtworkStatus.ACCEPTED)
        store_write(self._store.update_artwork, restored)
        return restored

    # -- writes: sources ------------------------------------------------------

    def add_source(
        self,
        *,
        artwork_id: str,
        url: str,
        provider: str,
        source_class: SourceClass,
        acquisition_method: AcquisitionMethod,
        rights_status: RightsStatus,
        is_primary: bool = False,
        confidence: float | None = None,
        selection_rationale: str | None = None,
    ) -> Source:
        """Record a place this work can be obtained from.

        `rights_status` has no default on purpose. "We did not check" and "we
        checked and could not tell" are different facts, and only the second is
        honest as `unknown` — so the value is always recorded and the caller is
        always the one who decided it.
        """
        self._require_artwork(artwork_id)
        source = Source(
            id=str(uuid.uuid4()),
            artwork_id=artwork_id,
            url=require_text(url, field="url"),
            provider=require_text(provider, field="provider"),
            source_class=require_member(source_class, enum=SourceClass, field="source_class"),
            acquisition_method=require_member(acquisition_method, enum=AcquisitionMethod, field="acquisition_method"),
            rights_status=require_member(rights_status, enum=RightsStatus, field="rights_status"),
            is_primary=is_primary,
            confidence=confidence,
            selection_rationale=selection_rationale,
        )
        with self._store.transaction():
            if is_primary:
                self._demote_primary_sources(artwork_id)
            store_write(self._store.add_source, source)
        return source

    def set_primary_source(self, source_id: str) -> Source:
        """Name the source that produced the held original.

        Which source that is is a single fact about the work, so promoting one
        demotes the rest in the same breath.
        """
        source = self._store.get_source(source_id)
        if source is None:
            raise ServiceError(f"No source with id {source_id!r} is in the catalogue.")
        promoted = replace(source, is_primary=True)
        with self._store.transaction():
            self._demote_primary_sources(source.artwork_id)
            store_write(self._store.update_source, promoted)
        return promoted

    def record_fetch(self, source_id: str, *, status: FetchStatus, at: datetime | None = None) -> Source:
        """Record how the last fetch from this source went.

        `partial_tiles` is a normal dezoomify outcome rather than an error: a
        tile server dropping a few tiles still yields a usable master image.
        """
        source = self._store.get_source(source_id)
        if source is None:
            raise ServiceError(f"No source with id {source_id!r} is in the catalogue.")
        updated = replace(
            source,
            last_fetch_status=require_member(status, enum=FetchStatus, field="status"),
            last_fetched_at=at if at is not None else datetime.now(UTC),
        )
        store_write(self._store.update_source, updated)
        return updated

    # -- writes: originals and renditions -------------------------------------

    def record_original(
        self,
        *,
        artwork_id: str,
        source_id: str,
        path: str,
        width: int,
        height: int,
        byte_size: int,
        content_hash: str,
    ) -> Original:
        """Record the master image acquired for this work, replacing any held before.

        Re-acquiring is an edit rather than a mistake — a source is re-fetched
        when it is reorganised or when the first attempt came back partial — so
        this replaces rather than refusing. Renditions made from the previous
        image read as stale immediately afterwards, because they carry the hash
        they were made from.
        """
        self._require_artwork(artwork_id)
        source = self._store.get_source(source_id)
        if source is None:
            raise ServiceError(f"No source with id {source_id!r} is in the catalogue.")
        if source.artwork_id != artwork_id:
            raise ServiceError(f"Source {source_id!r} belongs to a different artwork than {artwork_id!r}.")
        if byte_size <= 0:
            # The 2024 pipeline's known download failure: a file that exists,
            # holds nothing, and is indistinguishable from a good one by name.
            raise ServiceError(f"An original cannot be {byte_size} bytes; a zero-length file is a failed download.")
        if width <= 0 or height <= 0:
            raise ServiceError(f"An original must have a positive width and height, got {width}x{height}.")

        with self._store.transaction():
            held = self._store.get_original(artwork_id)
            original = Original(
                id=held.id if held is not None else str(uuid.uuid4()),
                artwork_id=artwork_id,
                source_id=source_id,
                relative_path=relative_path(path, field="path"),
                width=width,
                height=height,
                byte_size=byte_size,
                content_hash=require_text(content_hash, field="content_hash"),
            )
            if held is None:
                store_write(self._store.add_original, original)
            else:
                store_write(self._store.update_original, original)
        return original

    def record_rendition(
        self,
        *,
        artwork_id: str,
        kind: RenditionKind,
        target_width: int,
        target_height: int,
        path: str,
    ) -> Rendition:
        """Record a derived output, stamped with the image it was made from.

        The parent's hash is read here rather than accepted from the caller, so a
        rendition is born current and can only ever become stale by the original
        changing under it. A caller-supplied hash would let a rendition claim a
        parent it was not made from, which is the one thing this column exists to
        make impossible.
        """
        self._require_artwork(artwork_id)
        if target_width <= 0 or target_height <= 0:
            raise ServiceError(f"A rendition must have a positive target size, got {target_width}x{target_height}.")
        with self._store.transaction():
            original = self._store.get_original(artwork_id)
            if original is None:
                raise ServiceError(f"Artwork {artwork_id!r} has no acquired original to render from.")
            resolved_kind = require_member(kind, enum=RenditionKind, field="kind")
            existing = next(
                (
                    candidate
                    for candidate in self._store.list_renditions(artwork_id)
                    if candidate.kind is resolved_kind
                    and candidate.target_width == target_width
                    and candidate.target_height == target_height
                ),
                None,
            )
            rendition = Rendition(
                id=existing.id if existing is not None else str(uuid.uuid4()),
                artwork_id=artwork_id,
                kind=resolved_kind,
                target_width=target_width,
                target_height=target_height,
                relative_path=relative_path(path, field="path"),
                source_content_hash=original.content_hash,
                generated_at=datetime.now(UTC),
            )
            if existing is None:
                store_write(self._store.add_rendition, rendition)
            else:
                store_write(self._store.update_rendition, rendition)
        return rendition

    # -- writes: the mat ------------------------------------------------------

    def record_mat_color(
        self,
        *,
        artwork_id: str,
        hex_rgb: str,
        method: MatMethod,
        lab_l: float | None = None,
        lab_a: float | None = None,
        lab_b: float | None = None,
        reason: str | None = None,
        model_id: str | None = None,
    ) -> MatColor:
        """Choose a mat colour, superseding rather than overwriting the last one.

        `method` is recorded because the fallback is otherwise invisible: the
        2024 pipeline silently substituted a darkened dominant colour whenever
        the vision model failed, so a hand-quality choice and a mechanical one
        looked identical in the data.

        **Re-choosing what is already in force is a no-op, not a new row.** The
        history exists so that "the new model picked a worse colour" is
        answerable and reversible, and a row recording that nothing changed
        answers nothing while making every real change harder to find. Anything
        that runs repeatedly — a re-seed, a re-render — would otherwise grow the
        history by a row per work per run. `method` is part of what "the same
        choice" means: the same hex arrived at by a vision model rather than by
        hand is a different fact about the colour, and worth keeping.
        """
        self._require_artwork(artwork_id)
        resolved_hex = self._require_hex(hex_rgb)
        resolved_method = require_member(method, enum=MatMethod, field="method")
        current = self.current_mat_color(artwork_id)
        if current is not None and current.hex_rgb == resolved_hex and current.method is resolved_method:
            return current
        mat_color = MatColor(
            id=str(uuid.uuid4()),
            artwork_id=artwork_id,
            hex_rgb=resolved_hex,
            method=resolved_method,
            chosen_at=datetime.now(UTC),
            is_current=True,
            lab_l=lab_l,
            lab_a=lab_a,
            lab_b=lab_b,
            reason=reason,
            model_id=model_id,
        )
        with self._store.transaction():
            for previous in self._store.list_mat_colors(artwork_id):
                if previous.is_current:
                    superseded = replace(previous, is_current=False)
                    store_write(self._store.update_mat_color, superseded)
            store_write(self._store.add_mat_color, mat_color)
        return mat_color

    # -- internals ------------------------------------------------------------

    def _demote_primary_sources(self, artwork_id: str) -> None:
        """Clear whichever source currently claims to have produced the original."""
        for other in self._store.list_sources(artwork_id):
            if other.is_primary:
                demoted = replace(other, is_primary=False)
                store_write(self._store.update_source, demoted)

    def _require_artwork(self, artwork_id: str) -> Artwork:
        artwork = self._store.get_artwork(artwork_id)
        if artwork is None:
            raise ServiceError(f"No artwork with id {artwork_id!r} is in the catalogue.")
        return artwork

    def _resolve_artist(self, artist_id: str | None, seen: dict[str, Artist | None]) -> Artist | None:
        if artist_id is None:
            return None
        if artist_id not in seen:
            seen[artist_id] = self._store.get_artist(artist_id)
        return seen[artist_id]

    @staticmethod
    def _parse_status(status: str | None) -> ArtworkStatus | None:
        if status is None:
            return None
        try:
            return ArtworkStatus(status)
        except ValueError as exc:
            valid = ", ".join(sorted(member.value for member in ArtworkStatus))
            raise ServiceError(f"Unknown status {status!r}. Valid values are: {valid}.") from exc

    @staticmethod
    def _require_hex(value: str) -> str:
        text = value.strip().lower()
        if len(text) != 7 or not text.startswith("#") or any(character not in "0123456789abcdef" for character in text[1:]):
            raise ServiceError(f"A mat colour must be a hex triplet like '#27285b', got {value!r}.")
        return text
