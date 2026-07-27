"""The catalogue's records and the persistence contract over them.

The store is a `Protocol` rather than a base class because the backing
technology is expected to change: today it is stdlib `sqlite3`, and the
three-tier collection store it is destined for is not yet consumable. Naming
the contract here means that swap touches one implementation module and
nothing above it.

The records are plain frozen dataclasses. They carry no persistence
behaviour — no `save()`, no lazy relationship loading — so that a service
holding one cannot accidentally reach the database through it. Reads that need
more go back through the store.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol


class ArtworkStatus(StrEnum):
    """The only two states a catalogued work can be in.

    An artwork exists only once it has been accepted; everything before that
    is a candidate, which is a different entity with its own lifecycle.
    """

    ACCEPTED = "accepted"
    ARCHIVED = "archived"


@dataclass(frozen=True, slots=True)
class Artist:
    """A person a work is attributed to.

    Separate from the work so the physical label can render nationality and
    lifespan without re-parsing a blob, and so two works by the same artist
    agree about them.
    """

    id: str
    name: str
    nationality: str | None = None
    born: int | None = None
    died: int | None = None
    lifespan_text: str | None = None
    biography: str | None = None


@dataclass(frozen=True, slots=True)
class Artwork:
    """The canonical record of a work.

    `id` is a stable internal identity and is never derived from a source URL:
    a museum reorganising its site must not break a work's identity, and the
    same painting held by two institutions must not become two records.

    `date_created` is free text on purpose. Sources give "1931", "c. 1650",
    and "1888-89"; normalising those to a date type would destroy the
    distinction between a known year and an estimated one.
    """

    id: str
    title: str
    created_at: datetime
    status: ArtworkStatus = ArtworkStatus.ACCEPTED
    artist_id: str | None = None
    date_created: str | None = None
    medium: str | None = None
    dimensions: str | None = None
    description: str | None = None
    rights: str | None = None
    accepted_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class Theme:
    """A curator's grouping of works, and the unit the wall rotates through."""

    id: str
    name: str
    created_at: datetime
    description: str | None = None
    is_active: bool = False


@dataclass(frozen=True, slots=True)
class ArtworkPage:
    """One page of works plus the size of the set it was drawn from.

    `total` is what lets a caller say "showing 20 of 84" instead of silently
    handing back a short list.
    """

    artworks: Sequence[Artwork]
    total: int


class CatalogueStore(Protocol):
    """Everything the catalogue can be asked of its storage.

    Implementations own persistence and nothing else: no validation, no
    ordering decisions beyond a deterministic sort, no derived values. Those
    belong to the service layer, which is the only caller.
    """

    def add_artist(self, artist: Artist) -> None:
        """Persist an artist. Raises if the id is already present."""
        ...

    def get_artist(self, artist_id: str) -> Artist | None:
        """Return the artist, or None if no such id is stored."""
        ...

    def add_artwork(self, artwork: Artwork) -> None:
        """Persist a work. Raises if the id is already present."""
        ...

    def get_artwork(self, artwork_id: str) -> Artwork | None:
        """Return the work, or None if no such id is stored."""
        ...

    def list_artworks(self, *, status: ArtworkStatus | None, limit: int, offset: int) -> ArtworkPage:
        """Return a page of works in a stable order, with the unpaged total."""
        ...

    def add_theme(self, theme: Theme) -> None:
        """Persist a theme. Raises if the id or the name is already present."""
        ...

    def get_theme(self, theme_id: str) -> Theme | None:
        """Return the theme, or None if no such id is stored."""
        ...

    def list_themes(self) -> Sequence[Theme]:
        """Return every theme in a stable order."""
        ...

    def close(self) -> None:
        """Release the underlying resources."""
        ...


class StorageError(RuntimeError):
    """A write the store refused, such as a duplicate id or a missing artist."""
