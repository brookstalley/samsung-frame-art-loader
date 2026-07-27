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
theme active, exactly one mat colour current, at most one primary source — are
applied inside a store transaction as a clear-then-set pair, because a pair that
can be interrupted between its halves leaves the catalogue in the state the rule
forbids.

Methods are synchronous. The store is a local file answering point lookups in
well under a millisecond, and a synchronous core keeps this logic testable
without an event loop.
"""

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Final

from curation.persistence.catalogue import CatalogueStore, StorageError
from curation.persistence.records import (
    AcquisitionMethod,
    Artist,
    Artwork,
    ArtworkStatus,
    Directive,
    FetchStatus,
    MatColor,
    MatMethod,
    Original,
    Rendition,
    RenditionKind,
    RightsStatus,
    Source,
    SourceClass,
    Theme,
    ThemeMembership,
)
from curation.services.display_fit import ArtworkBox, FitAssessment, assess_display_fit
from curation.services.errors import ServiceError
from curation.services.fields import description_markup, relative_path

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

    # -- reads: themes --------------------------------------------------------

    def list_themes(self) -> Sequence[Theme]:
        """Return every theme."""
        return self._store.list_themes()

    def get_theme(self, theme_id: str) -> Theme:
        """Return one theme."""
        theme = self._store.get_theme(theme_id)
        if theme is None:
            raise ServiceError(f"No theme with id {theme_id!r} is in the catalogue.")
        return theme

    def active_theme(self) -> Theme | None:
        """The theme the wall is showing, or None while the catalogue has no themes."""
        for theme in self._store.list_themes():
            if theme.is_active:
                return theme
        return None

    def theme_works(self, theme_id: str) -> Sequence[ArtworkDetail]:
        """The theme's works in curated order, each with its artist resolved.

        Ordered because the entries carry a curator's placement; the ones nobody
        placed follow the ones somebody did. Artists come along because a theme
        listing is read to decide what goes on the wall, and attribution is the
        first thing that decision turns on.
        """
        self.get_theme(theme_id)
        artists: dict[str, Artist | None] = {}
        entries: list[ArtworkDetail] = []
        for membership in self._store.list_memberships(theme_id):
            artwork = self._store.get_artwork(membership.artwork_id)
            if artwork is None:
                # A membership row cannot outlive its work: the foreign key
                # forbids it. Reaching here means the file was edited by
                # something other than this code.
                raise ServiceError(
                    f"Theme {theme_id!r} refers to artwork {membership.artwork_id!r}, which is not in the catalogue."
                )
            entries.append(ArtworkDetail(artwork=artwork, artist=self._resolve_artist(artwork.artist_id, artists)))
        return entries

    # -- reads: the display directive -----------------------------------------

    def read_directive(self) -> Directive:
        """The standing instruction to the display plane."""
        return self._store.get_directive()

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
            name=self._require_text(name, "name"),
            nationality=nationality,
            born=born,
            died=died,
            lifespan_text=lifespan_text,
            biography=biography,
        )
        self._write(self._store.add_artist, artist)
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
            title=self._require_text(title, "title"),
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
        self._write(self._store.add_artwork, artwork)
        return artwork

    def archive_artwork(self, artwork_id: str) -> Artwork:
        """Take a work out of circulation, keeping its record and its mat history."""
        artwork = self._require_artwork(artwork_id)
        if artwork.status is ArtworkStatus.ARCHIVED:
            raise ServiceError(f"Artwork {artwork_id!r} is already archived.")
        archived = replace(artwork, status=ArtworkStatus.ARCHIVED)
        with self._store.transaction():
            self._write(self._store.update_artwork, archived)
            # A pin naming a work that is out of circulation is an instruction
            # the display plane can never carry out, so archiving withdraws it.
            directive = self._store.get_directive()
            if directive.pinned_work_id == artwork_id:
                self._write(self._store.set_directive, replace(directive, pinned_work_id=None))
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
        self._write(self._store.update_artwork, restored)
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
            url=self._require_text(url, "url"),
            provider=self._require_text(provider, "provider"),
            source_class=self._require_member(source_class, SourceClass, "source_class"),
            acquisition_method=self._require_member(acquisition_method, AcquisitionMethod, "acquisition_method"),
            rights_status=self._require_member(rights_status, RightsStatus, "rights_status"),
            is_primary=is_primary,
            confidence=confidence,
            selection_rationale=selection_rationale,
        )
        with self._store.transaction():
            if is_primary:
                self._demote_primary_sources(artwork_id)
            self._write(self._store.add_source, source)
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
            self._write(self._store.update_source, promoted)
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
            last_fetch_status=self._require_member(status, FetchStatus, "status"),
            last_fetched_at=at if at is not None else datetime.now(UTC),
        )
        self._write(self._store.update_source, updated)
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
                content_hash=self._require_text(content_hash, "content_hash"),
            )
            if held is None:
                self._write(self._store.add_original, original)
            else:
                self._write(self._store.update_original, original)
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
            resolved_kind = self._require_member(kind, RenditionKind, "kind")
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
                self._write(self._store.add_rendition, rendition)
            else:
                self._write(self._store.update_rendition, rendition)
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
        """
        self._require_artwork(artwork_id)
        mat_color = MatColor(
            id=str(uuid.uuid4()),
            artwork_id=artwork_id,
            hex_rgb=self._require_hex(hex_rgb),
            method=self._require_member(method, MatMethod, "method"),
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
                    self._write(self._store.update_mat_color, superseded)
            self._write(self._store.add_mat_color, mat_color)
        return mat_color

    # -- writes: themes and membership ----------------------------------------

    def add_theme(self, *, name: str, description: str | None = None) -> Theme:
        """Record a theme and return it.

        The first theme is active, because a catalogue that has themes and no
        active one leaves the display plane with no sync target at all — and
        nothing would report that as a problem.
        """
        with self._store.transaction():
            theme = Theme(
                id=str(uuid.uuid4()),
                name=self._require_text(name, "name"),
                created_at=datetime.now(UTC),
                description=description,
                is_active=not self._store.list_themes(),
            )
            self._write(self._store.add_theme, theme)
        return theme

    def activate_theme(self, theme_id: str) -> Theme:
        """Make this the theme the wall shows, and the only one."""
        theme = self.get_theme(theme_id)
        activated = replace(theme, is_active=True)
        with self._store.transaction():
            for other in self._store.list_themes():
                if other.is_active and other.id != theme_id:
                    stood_down = replace(other, is_active=False)
                    self._write(self._store.update_theme, stood_down)
            self._write(self._store.update_theme, activated)
        return activated

    def add_to_theme(self, *, theme_id: str, artwork_id: str, position: int | None = None) -> ThemeMembership:
        """Place a work in a theme, optionally at a curated position."""
        self.get_theme(theme_id)
        self._require_artwork(artwork_id)
        membership = ThemeMembership(
            theme_id=theme_id,
            artwork_id=artwork_id,
            added_at=datetime.now(UTC),
            position=self._require_position(position),
        )
        self._write(self._store.add_membership, membership)
        return membership

    def move_in_theme(self, *, theme_id: str, artwork_id: str, position: int | None) -> ThemeMembership:
        """Change where a work sits in a theme, or return it to unplaced."""
        membership = self._store.get_membership(theme_id, artwork_id)
        if membership is None:
            raise ServiceError(f"Artwork {artwork_id!r} is not in theme {theme_id!r}.")
        moved = replace(membership, position=self._require_position(position))
        self._write(self._store.update_membership, moved)
        return moved

    def remove_from_theme(self, *, theme_id: str, artwork_id: str) -> None:
        """Take a work out of a theme. The work itself is untouched."""
        if self._store.get_membership(theme_id, artwork_id) is None:
            raise ServiceError(f"Artwork {artwork_id!r} is not in theme {theme_id!r}.")
        self._write(self._store.remove_membership, theme_id, artwork_id)

    # -- writes: the display directive ----------------------------------------

    def step_display(self) -> Directive:
        """Tell the display plane to move to the next work.

        The step clears any standing pin. A sequence that advanced while a pin
        was still set would read as "jump to that work again" rather than as
        "move on", so the two directives cannot both be in force.
        """
        return self._advance(pinned_work_id=None)

    def show_work_now(self, artwork_id: str) -> Directive:
        """Tell the display plane to jump to this work and carry on from there."""
        artwork = self._require_artwork(artwork_id)
        if artwork.status is ArtworkStatus.ARCHIVED:
            raise ServiceError(f"Artwork {artwork_id!r} is archived, so it is out of circulation and cannot be shown.")
        return self._advance(pinned_work_id=artwork_id)

    # -- internals ------------------------------------------------------------

    def _advance(self, *, pinned_work_id: str | None) -> Directive:
        """Move the directive on by one.

        The counter only ever increases, for the life of the catalogue. The
        display plane acts each time it sees the number go up, so a counter that
        reset — on a manifest rebuild, on a theme switch — would fire a directive
        nobody issued.
        """
        with self._store.transaction():
            current = self._store.get_directive()
            advanced = Directive(sequence=current.sequence + 1, pinned_work_id=pinned_work_id)
            self._write(self._store.set_directive, advanced)
        return advanced

    def _demote_primary_sources(self, artwork_id: str) -> None:
        """Clear whichever source currently claims to have produced the original."""
        for other in self._store.list_sources(artwork_id):
            if other.is_primary:
                demoted = replace(other, is_primary=False)
                self._write(self._store.update_source, demoted)

    def _detail(self, artwork_id: str) -> ArtworkDetail:
        artwork = self._require_artwork(artwork_id)
        return ArtworkDetail(artwork=artwork, artist=self._resolve_artist(artwork.artist_id, {}))

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
    def _require_member[E: StrEnum](value: object, enum: type[E], field: str) -> E:
        """Accept the enum member or its string value, and nothing else.

        Callers reach this layer from a tool or an HTTP handler, where every
        value started as text — so the string form has to work — but an unknown
        one has to fail here rather than reach a column as a value nothing can
        read back.
        """
        try:
            return enum(value)
        except ValueError as exc:
            valid = ", ".join(sorted(member.value for member in enum))
            raise ServiceError(f"Unknown {field} {value!r}. Valid values are: {valid}.") from exc

    @staticmethod
    def _require_text(value: str, field: str) -> str:
        text = value.strip()
        if not text:
            raise ServiceError(f"{field} cannot be empty.")
        return text

    @staticmethod
    def _require_hex(value: str) -> str:
        text = value.strip().lower()
        if len(text) != 7 or not text.startswith("#") or any(character not in "0123456789abcdef" for character in text[1:]):
            raise ServiceError(f"A mat colour must be a hex triplet like '#27285b', got {value!r}.")
        return text

    @staticmethod
    def _require_position(position: int | None) -> int | None:
        if position is not None and position < 0:
            raise ServiceError(f"A position cannot be negative, got {position}.")
        return position

    @staticmethod
    def _write[**P](operation: Callable[P, None], *args: P.args, **kwargs: P.kwargs) -> None:
        """Run a store write, reporting a refusal in the service's own terms.

        The store speaks in constraint violations; callers above this layer
        should never have to know that the catalogue happens to be SQL. The
        arguments are passed through rather than closed over so that a write
        inside a loop cannot capture the wrong iteration's record.
        """
        try:
            operation(*args, **kwargs)
        except StorageError as exc:
            raise ServiceError(str(exc)) from exc
