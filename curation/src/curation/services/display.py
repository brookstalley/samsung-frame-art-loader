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
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from curation.manifest import heartbeat
from curation.manifest.builder import (
    ManifestBuild,
    WorkInputs,
    as_document,
    assess,
    entry_for,
    tv_rendition_of,
    write_atomically,
)
from curation.manifest.heartbeat import HeartbeatReading
from curation.persistence.catalogue import CatalogueStore
from curation.persistence.records import Directive, Theme, ThemeMembership
from curation.services.catalogue import ArtworkDetail, CatalogueService
from curation.services.errors import ServiceError
from curation.services.fields import require_text
from curation.services.store import store_write

log = logging.getLogger(__name__)


class Unset:
    """ "The caller said nothing about this field", as distinct from "set it to null".

    A sentinel type rather than a `None` default, because `None` is a meaningful
    value for every field that takes this: no description, and "inherit the
    global default" for both rotation settings.
    """


UNSET: Final[Unset] = Unset()


@dataclass(frozen=True, slots=True)
class WallSettings:
    """The deployment facts the wall's own operations need.

    Passed in rather than read from the environment here, because a service that
    resolved its own configuration could not be tested against two deployments
    and would make every caller share one.
    """

    manifest_path: Path
    #: Written by the display plane, read here. Never written by this plane.
    heartbeat_path: Path
    #: What a theme that has expressed no pace of its own inherits.
    rotation_interval_seconds: int
    shuffle: bool


class DisplayService:
    """Read and write the themes, memberships, and directive the wall runs on."""

    def __init__(self, store: CatalogueStore, catalogue: CatalogueService, settings: WallSettings) -> None:
        self._store = store
        self._catalogue = catalogue
        self._settings = settings

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

    def activate_theme(self, theme_id: str) -> ManifestBuild:
        """Make this the theme the wall shows, and publish it.

        **Activating rewrites the manifest**, so switching themes changes the
        wall rather than arming a later `sync`. A curator who chose a theme and
        found the wall unchanged would reasonably conclude the product was
        broken, and the two-step alternative exists only as an artefact of how
        the operations decompose.

        The switch costs **zero television writes**: the whole library stays on
        the TV and rotation is driven from here, so this is a file rewrite rather
        than minutes of upload churn.

        It returns the build, not the theme, because the theme alone cannot say
        how much of itself reached the wall — and a switch that silently put up
        four of a theme's twelve works is the failure this report exists for.
        """
        theme = self.get_theme(theme_id)
        activated = replace(theme, is_active=True)
        with self._store.transaction():
            for other in self._store.list_themes():
                if other.is_active and other.id != theme_id:
                    stood_down = replace(other, is_active=False)
                    store_write(self._store.update_theme, stood_down)
            store_write(self._store.update_theme, activated)
        return self.sync(theme_id)

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

    def update_theme(
        self,
        theme_id: str,
        *,
        name: str | None = None,
        description: str | None | Unset = UNSET,
        rotation_interval_seconds: int | None | Unset = UNSET,
        shuffle: bool | None | Unset = UNSET,
    ) -> Theme:
        """Change a theme's name, description, or pace.

        The nullable fields take a sentinel rather than defaulting to `None`,
        because `None` is a meaningful value for all three — "no description",
        and "inherit the global default" for the two rotation settings. Without
        it, a caller changing only the name would silently clear the theme's pace.
        """
        theme = self.get_theme(theme_id)
        updated = replace(
            theme,
            name=theme.name if name is None else require_text(name, field="name"),
            description=theme.description if isinstance(description, Unset) else description,
            rotation_interval_seconds=(
                theme.rotation_interval_seconds
                if isinstance(rotation_interval_seconds, Unset)
                else self._require_interval(rotation_interval_seconds)
            ),
            shuffle=theme.shuffle if isinstance(shuffle, Unset) else shuffle,
        )
        store_write(self._store.update_theme, updated)
        return updated

    def delete_theme(self, theme_id: str) -> None:
        """Remove a theme and its membership rows. The works themselves are untouched.

        The active theme is refused while another exists, rather than deleted and
        silently repaired: `reconcile` would promote the oldest remaining theme,
        which means a curator deleting what is on the wall gets *some* other
        theme on it without having chosen one. Deleting the last theme is allowed
        — no themes at all is a normal empty state, not the forbidden one.

        **Deleting the last theme deliberately does not rewrite the manifest.**
        The wall keeps showing what it was showing, which is the same posture as
        curation being stopped entirely: the display plane runs off the last
        manifest indefinitely, and that is normal operation rather than
        degradation. Publishing an empty manifest instead would blank the wall as
        a side effect of tidying up the catalogue.
        """
        theme = self.get_theme(theme_id)
        if theme.is_active and len(self._store.list_themes()) > 1:
            raise ServiceError(
                f"Theme {theme.name!r} is the one the wall is showing. Activate another theme first, "
                "so that what replaces it on the wall is a choice rather than whichever is oldest."
            )
        with self._store.transaction():
            for membership in self._store.list_memberships(theme_id):
                store_write(self._store.remove_membership, theme_id, membership.artwork_id)
            store_write(self._store.remove_theme, theme_id)

    # -- reads: what the display plane says about itself -----------------------

    def wall_status(self) -> HeartbeatReading:
        """Observe the display plane's heartbeat.

        An observation, never a verdict: the reading carries an age in seconds
        and the caller decides what that means. Absent is a true answer — on a
        deployment where the display plane has not been started, it is the
        correct one.
        """
        return heartbeat.read(self._settings.heartbeat_path)

    # -- writes: the display directive ----------------------------------------

    def step_display(self) -> Directive:
        """Tell the display plane to move to the next work.

        The step clears any standing pin. A sequence that advanced while a pin
        was still set would read as "jump to that work again" rather than as
        "move on", so the two directives cannot both be in force.
        """
        return self._advance(pinned_work_id=None)

    def show_work_now(self, artwork_id: str) -> Directive:
        """Tell the display plane to jump to this work and carry on from there.

        **Refused if the work is not displayable**, with the same reason the
        manifest build would have given. `data-model.md` specifies the refusal
        for an archived work; this applies the whole readiness rule, because the
        neighbouring cases fail identically from the curator's side. Pinning a
        work with no render writes a directive naming something the manifest does
        not carry, answers "the directive is written", and the wall never moves —
        which is the silence the exclusion report exists to break, arriving
        through the one path that did not consult readiness.

        **It checks readiness, not theme membership**, so it does not remove the
        display plane's own obligation. A perfectly displayable work that is
        simply not in the active theme can still be pinned, and the manifest will
        not carry it — that is available on every call rather than a timing
        window. The membership check belongs to the plane that has to resolve the
        pin rather than the one writing it: display logs one WARNING and carries
        on rotating, by the same posture as a missing render file. What this
        closes is the case a curator can be told about now.
        """
        excluded = assess(self._gather(artwork_id))
        if excluded is not None:
            raise ServiceError(f"Artwork {artwork_id!r} cannot be shown on the wall: {excluded.detail}")
        return self._advance(pinned_work_id=artwork_id)

    # -- the manifest ---------------------------------------------------------

    def build_manifest(self, theme_id: str | None = None) -> ManifestBuild:
        """Evaluate a theme's readiness without writing anything.

        Separate from `sync` so a curator can ask "what would go on the wall, and
        what would not" before changing what is on it — and so the readiness rule
        is testable without a filesystem.
        """
        theme = self.get_theme(theme_id) if theme_id is not None else self._require_active_theme()
        directive = self._store.get_directive()

        entries = []
        exclusions = []
        for membership in self._store.list_memberships(theme.id):
            inputs = self._gather(membership.artwork_id)
            excluded = assess(inputs)
            if excluded is None:
                entries.append(entry_for(inputs))
            else:
                exclusions.append(excluded)

        return ManifestBuild(
            theme=theme,
            entries=entries,
            exclusions=exclusions,
            # Null on either field means "inherit the global default", so the
            # theme's own value is used only when it has expressed one.
            rotation_interval_seconds=(
                theme.rotation_interval_seconds
                if theme.rotation_interval_seconds is not None
                else self._settings.rotation_interval_seconds
            ),
            shuffle=theme.shuffle if theme.shuffle is not None else self._settings.shuffle,
            # Carried forward unchanged. A rebuild is not a directive, and a
            # counter that reset here would read to the display plane as an
            # advance — firing a jump nobody asked for on every sync.
            directive_sequence=directive.sequence,
            pinned_work_id=directive.pinned_work_id,
        )

    def sync(self, theme_id: str | None = None) -> ManifestBuild:
        """Rebuild the manifest and publish it to the display plane.

        Returns what it wrote **and what it left out**. A caller that only
        reports the entry count is describing a theme that may be silently
        half on the wall.

        This writes desired state; it does not command the television. The wall
        converges within the display plane's poll interval, and saying anything
        stronger would assert something this plane cannot observe.
        """
        build = self.build_manifest(theme_id)
        write_atomically(self._settings.manifest_path, as_document(build))
        if build.exclusions:
            # Named at WARNING with the count, because a theme quietly showing
            # fewer works than it holds is precisely this product's
            # characteristic failure.
            log.warning(
                "Theme %r: %d of %d works are not currently displayable (%s).",
                build.theme.name,
                len(build.exclusions),
                build.considered,
                ", ".join(sorted({exclusion.reason.value for exclusion in build.exclusions})),
            )
        log.info("Wrote manifest for theme %r with %d entries.", build.theme.name, len(build.entries))
        return build

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

    def _require_active_theme(self) -> Theme:
        theme = self.active_theme()
        if theme is None:
            raise ServiceError("No theme is active, so there is nothing to put on the wall. Create a theme first.")
        return theme

    def _gather(self, artwork_id: str) -> WorkInputs:
        """Collect everything the readiness rule judges one work on."""
        detail = self._catalogue.get_artwork(artwork_id)
        # Everything here comes through the catalogue service, because it owns
        # what each of these means. Renditions reached straight past it into the
        # store until 2026-08-05, and the hazard was the one the mat colour was
        # already routed around: a second path to the same fact decides manifest
        # membership while the first decides everything else, and only one of
        # them is updated when the rule changes. The readiness rule judges the
        # record rather than the view, so the view is unwrapped here — the rule
        # it would have read is now a shared predicate `assess` calls directly.
        return WorkInputs(
            artwork=detail.artwork,
            artist=detail.artist,
            original=self._catalogue.get_original(artwork_id),
            tv_rendition=tv_rendition_of([view.rendition for view in self._catalogue.list_renditions(artwork_id)]),
            mat_color=self._catalogue.current_mat_color(artwork_id),
        )

    @staticmethod
    def _require_position(position: int | None) -> int | None:
        if position is not None and position < 0:
            raise ServiceError(f"A position cannot be negative, got {position}.")
        return position

    @staticmethod
    def _require_interval(seconds: int | None) -> int | None:
        """Null inherits the default; a number has to be a length of time.

        Zero is refused rather than treated as "as fast as possible": the display
        plane would spin selecting images, and nothing about that reads as a
        setting somebody chose.
        """
        if seconds is not None and seconds <= 0:
            raise ServiceError(f"A rotation interval must be greater than zero seconds, got {seconds}.")
        return seconds
