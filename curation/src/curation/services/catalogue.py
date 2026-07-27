"""Catalogue operations — the only place their logic lives.

Everything above this module is a binding: the MCP tools unpack arguments,
call one method here, and format what comes back; the HTTP handlers will do
the same. Two implementations of "list the catalogue" would diverge within
weeks, and the divergence would show up as an agent and a click disagreeing
about the same catalogue, which reads as the product being untrustworthy
rather than as a bug.

Methods are synchronous. The store is a local file answering point lookups in
well under a millisecond, and a synchronous core keeps this logic testable
without an event loop.
"""

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

from curation.persistence.catalogue import (
    Artist,
    Artwork,
    ArtworkStatus,
    CatalogueStore,
    StorageError,
    Theme,
)
from curation.services.errors import ServiceError

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


class CatalogueService:
    """Read and write the catalogue."""

    def __init__(self, store: CatalogueStore) -> None:
        self._store = store

    # -- reads ----------------------------------------------------------------

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
        artwork = self._store.get_artwork(artwork_id)
        if artwork is None:
            raise ServiceError(f"No artwork with id {artwork_id!r} is in the catalogue.")
        return ArtworkDetail(artwork=artwork, artist=self._resolve_artist(artwork.artist_id, {}))

    def list_themes(self) -> Sequence[Theme]:
        """Return every theme."""
        return self._store.list_themes()

    def get_theme(self, theme_id: str) -> Theme:
        """Return one theme."""
        theme = self._store.get_theme(theme_id)
        if theme is None:
            raise ServiceError(f"No theme with id {theme_id!r} is in the catalogue.")
        return theme

    # -- writes ---------------------------------------------------------------

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
        self._write(lambda: self._store.add_artist(artist))
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
            description=description,
            rights=rights,
            accepted_at=now,
        )
        self._write(lambda: self._store.add_artwork(artwork))
        return artwork

    def add_theme(self, *, name: str, description: str | None = None) -> Theme:
        """Record a theme and return it."""
        theme = Theme(
            id=str(uuid.uuid4()),
            name=self._require_text(name, "name"),
            created_at=datetime.now(UTC),
            description=description,
        )
        self._write(lambda: self._store.add_theme(theme))
        return theme

    # -- internals ------------------------------------------------------------

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
    def _require_text(value: str, field: str) -> str:
        text = value.strip()
        if not text:
            raise ServiceError(f"{field} cannot be empty.")
        return text

    @staticmethod
    def _write(operation: Callable[[], None]) -> None:
        """Run a store write, reporting a refusal in the service's own terms.

        The store speaks in constraint violations; callers above this layer
        should never have to know that the catalogue happens to be SQL.
        """
        try:
            operation()
        except StorageError as exc:
            raise ServiceError(str(exc)) from exc
