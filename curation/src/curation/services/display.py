"""What the wall shows — themes, the standing directive, and the manifest.

The catalogue answers "what do we hold"; this answers "what is on the wall, in
what order, and what should it do next". They are separated because they change
for different reasons: a work's metadata changes when a curator corrects it, and
a theme changes when a curator changes their mind about an evening.

**This service depends on the catalogue and never the reverse.** A theme is a
grouping of works, so building one requires reading them; nothing about a work
requires knowing which themes hold it. The one place that direction looks
violated is `CatalogueService.archive_artwork`, which nulls a pin naming the work
it archives. That is deliberate, and the split it respects is *integrity* versus
*semantics*: a pin naming an archived work is an unsatisfiable reference, cleared
in the same transaction that creates it exactly as any other dangling reference
would be, and it never advances the sequence. Every rule about what an advance
*means* — that the counter is monotonic, that rebuilds carry it forward, that a
step supersedes a pin — lives here.

Methods are synchronous, for the reason `catalogue.py` gives.
"""

import logging
import uuid
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime

from curation.persistence.catalogue import CatalogueStore
from curation.persistence.records import ArtworkStatus, Directive, Theme, ThemeMembership
from curation.services.catalogue import ArtworkDetail, CatalogueService
from curation.services.errors import ServiceError
from curation.services.fields import require_text
from curation.services.store import store_write

log = logging.getLogger(__name__)


class DisplayService:
    """Read and write the themes, memberships, and directive the wall runs on."""

    def __init__(self, store: CatalogueStore, catalogue: CatalogueService) -> None:
        self._store = store
        self._catalogue = catalogue

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
        memberships = self._store.list_memberships(theme_id)
        return self._catalogue.resolve_details([membership.artwork_id for membership in memberships])

    # -- reads: the display directive -----------------------------------------

    def read_directive(self) -> Directive:
        """The standing instruction to the display plane."""
        return self._store.get_directive()

    # -- writes: themes and membership ----------------------------------------

    def add_theme(self, *, name: str, description: str | None = None) -> Theme:
        """Record a theme and return it.

        A theme arrives active when no other theme currently is, because a
        catalogue that has themes and no active one leaves the display plane with
        no sync target at all — and nothing would report that as a problem. The
        condition is "none is active" rather than "there are none", so that a
        catalogue which somehow reached that state is repaired by the next
        addition rather than staying broken until someone notices.
        """
        with self._store.transaction():
            theme = Theme(
                id=str(uuid.uuid4()),
                name=require_text(name, field="name"),
                created_at=datetime.now(UTC),
                description=description,
                is_active=not any(existing.is_active for existing in self._store.list_themes()),
            )
            store_write(self._store.add_theme, theme)
        return theme

    def activate_theme(self, theme_id: str) -> Theme:
        """Make this the theme the wall shows, and the only one."""
        theme = self.get_theme(theme_id)
        activated = replace(theme, is_active=True)
        with self._store.transaction():
            for other in self._store.list_themes():
                if other.is_active and other.id != theme_id:
                    stood_down = replace(other, is_active=False)
                    store_write(self._store.update_theme, stood_down)
            store_write(self._store.update_theme, activated)
        return activated

    def add_to_theme(self, *, theme_id: str, artwork_id: str, position: int | None = None) -> ThemeMembership:
        """Place a work in a theme, optionally at a curated position."""
        self.get_theme(theme_id)
        self._catalogue.get_artwork(artwork_id)
        membership = ThemeMembership(
            theme_id=theme_id,
            artwork_id=artwork_id,
            added_at=datetime.now(UTC),
            position=self._require_position(position),
        )
        store_write(self._store.add_membership, membership)
        return membership

    def move_in_theme(self, *, theme_id: str, artwork_id: str, position: int | None) -> ThemeMembership:
        """Change where a work sits in a theme, or return it to unplaced."""
        membership = self._store.get_membership(theme_id, artwork_id)
        if membership is None:
            raise ServiceError(f"Artwork {artwork_id!r} is not in theme {theme_id!r}.")
        moved = replace(membership, position=self._require_position(position))
        store_write(self._store.update_membership, moved)
        return moved

    def remove_from_theme(self, *, theme_id: str, artwork_id: str) -> None:
        """Take a work out of a theme. The work itself is untouched."""
        if self._store.get_membership(theme_id, artwork_id) is None:
            raise ServiceError(f"Artwork {artwork_id!r} is not in theme {theme_id!r}.")
        store_write(self._store.remove_membership, theme_id, artwork_id)

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
        artwork = self._catalogue.get_artwork(artwork_id).artwork
        if artwork.status is ArtworkStatus.ARCHIVED:
            raise ServiceError(f"Artwork {artwork_id!r} is archived, so it is out of circulation and cannot be shown.")
        return self._advance(pinned_work_id=artwork_id)

    # -- repair ---------------------------------------------------------------

    def reconcile(self) -> None:
        """Repair rules a catalogue on disk may predate. Run once, as the plane starts.

        A catalogue file outlives any single version of this code, so a rule added
        after a file was written has to be brought to that file rather than
        assumed of it. Exactly one theme active is such a rule: an earlier
        revision created every theme inactive and offered no way to activate one,
        so a catalogue from then holds themes with none active — the state the
        rule forbids, and precisely the one where the display plane has no sync
        target while nothing reports a problem.

        No ordinary write repairs it. The index the file carries states only "at
        most one", which that state satisfies; and while adding a theme now
        promotes one when none is active, a catalogue nobody adds to would stay
        broken indefinitely.

        The repair is logged at WARNING because it is a silent condition being
        corrected: nothing else would ever say the catalogue had been in it.
        """
        with self._store.transaction():
            themes = self._store.list_themes()
            if not themes or any(theme.is_active for theme in themes):
                return
            # The oldest theme, so the choice is the same on every machine that
            # opens the same file rather than whichever the listing happened to
            # put first.
            promoted = min(themes, key=lambda theme: (theme.created_at, theme.id))
            log.warning(
                "Catalogue held %d theme(s) with none active, which leaves the display plane no sync target; activated %r.",
                len(themes),
                promoted.name,
            )
            store_write(self._store.update_theme, replace(promoted, is_active=True))

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
            store_write(self._store.set_directive, advanced)
        return advanced

    @staticmethod
    def _require_position(position: int | None) -> int | None:
        if position is not None and position < 0:
            raise ServiceError(f"A position cannot be negative, got {position}.")
        return position
