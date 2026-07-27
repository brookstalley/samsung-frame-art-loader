"""The persistence contract over the catalogue's records, and its two errors.

The store is a `Protocol` rather than a base class so that the layers above it
bind to what the catalogue can be asked, not to how one file answers. Persistence
is reached only through the service layer, so naming the contract here is what
keeps the backing technology a local concern. The records themselves are in
`records.py`.

Implementations own persistence and nothing else: no validation, no derived
values, no ordering decisions beyond a deterministic sort. Every rule about what
a valid catalogue looks like belongs to the service layer, which is the only
caller — a store that also enforced would be a second place for those rules to
live, and the two would disagree.
"""

from collections.abc import Sequence
from contextlib import AbstractContextManager
from typing import Protocol

from curation.persistence.records import (
    Artist,
    Artwork,
    ArtworkPage,
    ArtworkStatus,
    Directive,
    MatColor,
    Original,
    Rendition,
    Source,
    Theme,
    ThemeMembership,
)


class CatalogueStore(Protocol):
    """Everything the catalogue can be asked of its storage."""

    # -- atomicity ------------------------------------------------------------

    def transaction(self) -> AbstractContextManager[None]:
        """Group several writes so they commit together or not at all.

        Several of the catalogue's rules span rows — exactly one theme is
        active, exactly one mat colour is current, at most one source is
        primary. Each is applied as a clear-then-set pair, and a pair that can
        be interrupted between its halves leaves the catalogue in a state the
        rule forbids: no active theme at all, and so no sync target for the
        display plane. Nesting is permitted and joins the outer group, so a
        service operation composed of others still commits once.
        """
        ...

    def close(self) -> None:
        """Release the underlying resources."""
        ...

    # -- artists --------------------------------------------------------------

    def add_artist(self, artist: Artist) -> None:
        """Persist an artist. Raises if the id is already present."""
        ...

    def get_artist(self, artist_id: str) -> Artist | None:
        """Return the artist, or None if no such id is stored."""
        ...

    # -- artworks -------------------------------------------------------------

    def add_artwork(self, artwork: Artwork) -> None:
        """Persist a work. Raises if the id is already present."""
        ...

    def get_artwork(self, artwork_id: str) -> Artwork | None:
        """Return the work, or None if no such id is stored."""
        ...

    def update_artwork(self, artwork: Artwork) -> None:
        """Overwrite a stored work with this one. Raises if the id is absent."""
        ...

    def list_artworks(self, *, status: ArtworkStatus | None, limit: int, offset: int) -> ArtworkPage:
        """Return a page of works in a stable order, with the unpaged total."""
        ...

    # -- sources --------------------------------------------------------------

    def add_source(self, source: Source) -> None:
        """Persist a source. Raises if the id is already present."""
        ...

    def get_source(self, source_id: str) -> Source | None:
        """Return the source, or None if no such id is stored."""
        ...

    def update_source(self, source: Source) -> None:
        """Overwrite a stored source with this one. Raises if the id is absent."""
        ...

    def list_sources(self, artwork_id: str) -> Sequence[Source]:
        """Return a work's sources in a stable order, the primary one first."""
        ...

    # -- originals ------------------------------------------------------------

    def add_original(self, original: Original) -> None:
        """Persist the master image. Raises if the work already has one."""
        ...

    def get_original(self, artwork_id: str) -> Original | None:
        """Return the work's master image, or None if none has been acquired."""
        ...

    def update_original(self, original: Original) -> None:
        """Overwrite a stored master image with this one. Raises if the id is absent."""
        ...

    # -- renditions -----------------------------------------------------------

    def add_rendition(self, rendition: Rendition) -> None:
        """Persist a derived output. Raises if the id is already present."""
        ...

    def update_rendition(self, rendition: Rendition) -> None:
        """Overwrite a stored rendition with this one. Raises if the id is absent."""
        ...

    def list_renditions(self, artwork_id: str) -> Sequence[Rendition]:
        """Return a work's renditions in a stable order."""
        ...

    # -- mat colours ----------------------------------------------------------

    def add_mat_color(self, mat_color: MatColor) -> None:
        """Persist a mat colour choice. Raises if the id is already present."""
        ...

    def update_mat_color(self, mat_color: MatColor) -> None:
        """Overwrite a stored mat colour with this one. Raises if the id is absent."""
        ...

    def list_mat_colors(self, artwork_id: str) -> Sequence[MatColor]:
        """Return a work's mat colours newest first, which is its history."""
        ...

    # -- themes ---------------------------------------------------------------

    def add_theme(self, theme: Theme) -> None:
        """Persist a theme. Raises if the id or the name is already present."""
        ...

    def get_theme(self, theme_id: str) -> Theme | None:
        """Return the theme, or None if no such id is stored."""
        ...

    def update_theme(self, theme: Theme) -> None:
        """Overwrite a stored theme with this one. Raises if the id is absent."""
        ...

    def list_themes(self) -> Sequence[Theme]:
        """Return every theme in a stable order."""
        ...

    # -- theme membership -----------------------------------------------------

    def add_membership(self, membership: ThemeMembership) -> None:
        """Place a work in a theme. Raises if it is already in that theme."""
        ...

    def get_membership(self, theme_id: str, artwork_id: str) -> ThemeMembership | None:
        """Return the entry, or None if the work is not in the theme."""
        ...

    def update_membership(self, membership: ThemeMembership) -> None:
        """Overwrite a stored entry with this one. Raises if it is absent."""
        ...

    def remove_membership(self, theme_id: str, artwork_id: str) -> None:
        """Take a work out of a theme. Removing an absent entry is not an error."""
        ...

    def list_memberships(self, theme_id: str) -> Sequence[ThemeMembership]:
        """Return a theme's entries in curated order, unordered entries last."""
        ...

    # -- the display directive ------------------------------------------------

    def get_directive(self) -> Directive:
        """Return the standing directive. A fresh catalogue has one already."""
        ...

    def set_directive(self, directive: Directive) -> None:
        """Replace the standing directive."""
        ...


class StorageError(RuntimeError):
    """The store could not do what was asked, in terms fit to show whoever asked.

    Usually a refused write — a duplicate id, a missing artist — and also a read
    of a row the catalogue cannot represent, such as one missing a timestamp its
    record requires. Both are conditions the caller did nothing wrong to cause and
    can be told about plainly, which is the line this type draws; a call that is
    itself malformed is a `StoreMisuseError` instead.

    `reason` is the refusal on its own — "it is already in the catalogue." — kept
    separate from the message so a layer that knows what was being stored can say
    so without re-deriving why the store said no.
    """

    def __init__(self, message: str, *, reason: str | None = None) -> None:
        super().__init__(message)
        self.reason = reason if reason is not None else message


class StoreMisuseError(RuntimeError):
    """A call the store could not make sense of — an unknown table, column or key.

    Deliberately **not** a `StorageError`. That type means the store refused a
    write a caller could reasonably have attempted, and its message is written to
    be shown to whoever asked. This one means the calling code is wrong, and its
    message names internal identifiers — so it must never be translated into
    something a curator or a model reads as advice about their request.
    """
