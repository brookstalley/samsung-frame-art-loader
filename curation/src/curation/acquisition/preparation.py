"""Turning a held original into a wall-ready canvas, and deciding when to.

Acquisition ends with bytes on disk and a row naming them. This is what happens
next: the work gets a mat colour with recorded provenance, and a television
canvas composed against the configured panel. Everything policy-shaped lives
here — when a mat is worth paying for, when a rendition is stale, what a failure
costs — while `mat.py` knows how to choose a colour and `compose.py` knows how to
draw one.

**Preparation is idempotent, and free to re-run once a work has a mat.** The
expensive half is the model call, so a work that already has a mat keeps it:
re-preparing a hundred works after a panel change costs a hundred renders and
nothing at all in model spend.

**The first preparation of a work is not free, and every result says so.** A work
that has never had a mat cannot be rendered without choosing one, and `acquire()`
does not prepare — so the first call on a freshly acquired work is a paid vision
call, which is the normal case rather than an edge. `PreparationResult.cost_usd`
carries it and the tool surface reports it. The tempting sentence was "regenerate
never spends"; it is false on exactly the call a curator makes first.

**Staleness is a comparison, not a flag.** A rendition records the
`content_hash` of the original it was drawn from, so "is this current" is
answered by reading both rather than by trusting something set at write time. The
2024 code expressed the same intent imperatively — clearing the television's
state whenever it regenerated an image — which held only at the one site that
remembered to do it.
"""

import logging
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Final

from curation.acquisition.compose import compose
from curation.acquisition.mat import MatChoice, MatEngine
from curation.persistence.records import MatColor, MatMethod, RenditionKind
from curation.services.catalogue import CatalogueService
from curation.services.display_fit import ArtworkBox, DisplayFit
from curation.services.errors import ServiceError
from curation.services.imaging import reading

log = logging.getLogger(__name__)

#: What a work's television canvas is called on disk. The work's own id, for the
#: reason the original's filename is: a title is not unique, not stable, and not
#: a filename. No geometry in the name — the `Rendition` row carries the target
#: size, and a `_w648_h480` suffix is how the 2024 tree ended up pointing at a
#: panel that no longer existed.
_FILENAME: Final[str] = "{artwork_id}.jpg"


class PreparationOutcome(Enum):
    """What preparing a work amounted to."""

    #: A canvas was composed and recorded.
    PREPARED = "prepared"
    #: The work was already current and nothing needed doing.
    UNCHANGED = "unchanged"


@dataclass(frozen=True, slots=True)
class PreparationResult:
    """What happened, in terms a curator or an agent can act on."""

    artwork_id: str
    outcome: PreparationOutcome
    detail: str
    mat_hex: str
    mat_method: str
    relative_path: str | None = None
    #: How the original met the space it was rendered into, so a caller can say
    #: "this is on the wall, and it is smaller than your floor" in one answer.
    fit: DisplayFit | None = None
    rendered_long_edge_inches: float | None = None
    #: What the mat choice cost, zero when no model was asked. A curator
    #: authorising a re-render is entitled to know whether it spends anything.
    cost_usd: Decimal = Decimal(0)
    #: Why the mat came from the fallback, when it did. `None` otherwise.
    #:
    #: **Both outcomes leave the work ready for the wall**, so there is no
    #: `prepared` flag to read: `unchanged` means the canvas was already current,
    #: not that anything failed. Failures raise, because every one of them —
    #: no original, an original missing from disk, a canvas that would not
    #: encode — needs a different thing done about it, and a caller handed a
    #: false-valued result would have to re-derive which.
    mat_fallback_detail: str | None = None


@dataclass(frozen=True, slots=True)
class PreparationSettings:
    """Where preparation writes and what geometry it composes against."""

    art_root: Path
    ready_path: Path
    #: The television's own panel, in pixels. The canvas is exactly this size.
    panel_width: int
    panel_height: int
    #: The region inside the mat, already composed from the panel and the mat in
    #: inches. Taken rather than derived for the reason `display_fit` takes it:
    #: one answer to "how big is the mat", computed where the deployment values
    #: are resolved.
    box: ArtworkBox

    def __post_init__(self) -> None:
        """Refuse a wiring that could only ever render wrongly, at wiring time.

        Every catalogue path is relative to `ART_ROOT`, so a canvas written
        anywhere else has no representable path. Caught here it names both
        directories at startup; caught where the row is written it is a
        `ValueError` from `relative_to` thrown after the render is already done.

        **The panel and the box are two fields that must agree, so the agreement
        is checked rather than trusted.** The box is *derived from* the panel
        wherever both come from one resolved `Settings` — but this object can be
        built with either from anywhere, and a box wider than its panel yields a
        negative mat, which pastes the artwork off the canvas and produces a
        plausible-looking file with the picture cropped. Nothing downstream could
        report that: the rendition row would be written, the manifest would carry
        it, and the first sign would be the wall.
        """
        if not self.ready_path.is_relative_to(self.art_root):
            raise ServiceError(f"The rendition directory at {self.ready_path} must sit inside ART_ROOT at {self.art_root}.")
        if self.panel_width <= 0 or self.panel_height <= 0:
            raise ServiceError(f"The panel must have a positive size, got {self.panel_width}x{self.panel_height}.")
        if self.box.width > self.panel_width or self.box.height > self.panel_height:
            raise ServiceError(
                f"The artwork box of {self.box.width}x{self.box.height} does not fit the "
                f"{self.panel_width}x{self.panel_height} panel it is composed against. These two are derived from "
                "one another in a resolved configuration, so a mismatch here means the panel and the box came from "
                "different deployments."
            )


class PreparationService:
    """Give a work a mat and a television canvas."""

    def __init__(self, catalogue: CatalogueService, mat_engine: MatEngine, settings: PreparationSettings) -> None:
        self._catalogue = catalogue
        self._mat = mat_engine
        self._settings = settings

    def prepare(self, artwork_id: str, *, force: bool = False) -> PreparationResult:
        """Make this work ready for the wall, doing only what is not already done.

        `force` re-renders a canvas that is already current. It does **not**
        re-choose the mat: a colour is a judgement with history, and replacing one
        because someone asked for a re-render would spend money to overwrite a
        decision they did not mention. Choosing again is `choose_mat` — a separate
        request, because it is a separate intent.

        **This is free for a work that already has a mat, and only for one.** A
        work that has never had a mat cannot be rendered without choosing one, so
        the first preparation of a freshly acquired work asks the vision model —
        and `acquire()` does not prepare, so that first call is the normal case
        rather than an edge. The cost comes back on `cost_usd` and the caller
        reports it. Saying "this never spends" would have been the easier
        sentence and it would have been false at exactly the moment a curator
        relied on it.
        """
        original = self._catalogue.get_original(artwork_id)
        if original is None:
            raise ServiceError(f"Artwork {artwork_id!r} has no acquired original to prepare; acquire it first.")

        source = self._settings.art_root / original.relative_path
        if not source.is_file():
            # The row says the work holds an image and the disk disagrees. Worth
            # its own message: this is what a restored catalogue looks like before
            # re-acquisition refills the tree, and "no such file" from deep inside
            # Pillow would send whoever reads it to the wrong place entirely.
            raise ServiceError(
                f"Artwork {artwork_id!r} records an original at {original.relative_path!r} that is not on disk. "
                "Re-acquire it before preparing."
            )

        mat, chosen = self._current_or_chosen_mat(artwork_id, source=source)
        current = self._current_tv_rendition(artwork_id)
        if current is not None and not force:
            return PreparationResult(
                artwork_id=artwork_id,
                outcome=PreparationOutcome.UNCHANGED,
                detail="the television canvas was already current",
                mat_hex=mat.hex_rgb,
                mat_method=mat.method.value,
                relative_path=current,
                # Not unconditionally zero. A work with no mat gets one chosen
                # above, and that can be a paid call even on the branch that then
                # finds the canvas current — which is a real sequence, not a
                # hypothetical: a rendition can outlive the mat row that a
                # restored catalogue lost.
                cost_usd=Decimal(0) if chosen is None else chosen.cost_usd,
                mat_fallback_detail=None if chosen is None else chosen.fallback_detail,
            )

        destination = self._settings.ready_path / _FILENAME.format(artwork_id=artwork_id)
        # **Translated, because this is the path where an undecodable original
        # would otherwise escape as a bare Pillow error.** The mat engine
        # translates its own reads, so a work with no mat is refused by name — but
        # a work that *has* one skips the engine entirely and reaches the
        # compositor first, and every `set_mat` does the same. One seam, both
        # callers, which is the arrangement `services/imaging.py` exists to hold.
        composition = reading(
            source,
            lambda: compose(
                source,
                destination=destination,
                mat_hex=mat.hex_rgb,
                panel_width=self._settings.panel_width,
                panel_height=self._settings.panel_height,
                box=self._settings.box,
            ),
        )
        relative = str(destination.relative_to(self._settings.art_root))
        # Recorded after the file exists, never before: a row naming a canvas that
        # was never written would be served to the television as current.
        self._catalogue.record_rendition(
            artwork_id=artwork_id,
            kind=RenditionKind.TV_DISPLAY,
            target_width=composition.canvas_width,
            target_height=composition.canvas_height,
            path=relative,
        )
        return PreparationResult(
            artwork_id=artwork_id,
            outcome=PreparationOutcome.PREPARED,
            detail=f"composed at {composition.rendered_width}x{composition.rendered_height} in a {mat.hex_rgb} mat",
            mat_hex=mat.hex_rgb,
            mat_method=mat.method.value,
            relative_path=relative,
            fit=composition.fit,
            rendered_long_edge_inches=composition.rendered_long_edge_inches,
            cost_usd=Decimal(0) if chosen is None else chosen.cost_usd,
            mat_fallback_detail=None if chosen is None else chosen.fallback_detail,
        )

    def choose_mat(self, artwork_id: str) -> PreparationResult:
        """Ask the vision model for this work's mat colour again, and re-render.

        Its own operation rather than a flag on `prepare`, because it is the one
        that spends money and the one that supersedes a judgement. The previous
        colour is kept — `record_mat_color` never overwrites — so a worse choice
        is reversible.
        """
        original = self._catalogue.get_original(artwork_id)
        if original is None:
            raise ServiceError(f"Artwork {artwork_id!r} has no acquired original to choose a mat for.")
        source = self._settings.art_root / original.relative_path
        if not source.is_file():
            raise ServiceError(
                f"Artwork {artwork_id!r} records an original at {original.relative_path!r} that is not on disk. "
                "Re-acquire it before choosing a mat."
            )

        choice = self._mat.choose(source)
        self._catalogue.record_mat_color(
            artwork_id=artwork_id,
            hex_rgb=choice.hex_rgb,
            method=choice.method,
            lab_l=choice.lab_l,
            lab_a=choice.lab_a,
            lab_b=choice.lab_b,
            reason=choice.reason or None,
            model_id=choice.model_id,
        )
        # Forced, because the canvas that exists was painted in the old colour and
        # is current by the only test the catalogue applies — the original has not
        # changed. Without this the work would keep showing the superseded mat
        # while the catalogue reported the new one.
        result = self.prepare(artwork_id, force=True)
        return PreparationResult(
            artwork_id=result.artwork_id,
            outcome=result.outcome,
            detail=result.detail,
            mat_hex=result.mat_hex,
            mat_method=result.mat_method,
            relative_path=result.relative_path,
            fit=result.fit,
            rendered_long_edge_inches=result.rendered_long_edge_inches,
            cost_usd=choice.cost_usd,
            mat_fallback_detail=choice.fallback_detail,
        )

    def set_mat(self, artwork_id: str, hex_rgb: str) -> PreparationResult:
        """Record a mat colour the curator chose, and re-render in it.

        Recorded as `manual`, which is the same provenance the 41 legacy colours
        carry: a person decided this one. It supersedes whatever the model chose
        without discarding it.
        """
        self._catalogue.record_mat_color(artwork_id=artwork_id, hex_rgb=hex_rgb, method=MatMethod.MANUAL)
        return self.prepare(artwork_id, force=True)

    def _current_or_chosen_mat(self, artwork_id: str, *, source: Path) -> tuple[MatColor, MatChoice | None]:
        """The mat in force, choosing one only if the work has never had one.

        **The reason a re-render is free for a work that already has a mat.** A
        mat is a judgement, and re-asking a model for one the work already has
        would both spend money and quietly replace a decision — including a
        curator's own manual choice, which is the worst version of it.

        Returns the choice alongside the record, and the second element is the
        whole point: `None` means nothing was asked and nothing was spent, while a
        `MatChoice` carries what the call cost and whether the model actually
        answered. Without it the caller cannot tell a free call from a paid one,
        and would have to either report every preparation as free — which is
        false on a work's first — or report a cost it never incurred.
        """
        current = self._catalogue.current_mat_color(artwork_id)
        if current is not None:
            return current, None
        choice = self._mat.choose(source)
        recorded = self._catalogue.record_mat_color(
            artwork_id=artwork_id,
            hex_rgb=choice.hex_rgb,
            method=choice.method,
            lab_l=choice.lab_l,
            lab_a=choice.lab_a,
            lab_b=choice.lab_b,
            reason=choice.reason or None,
            model_id=choice.model_id,
        )
        return recorded, choice

    def _current_tv_rendition(self, artwork_id: str) -> str | None:
        """The path of a television canvas that is current and actually on disk.

        Three conditions, and none is redundant. The hash test is the catalogue's
        — `list_renditions` derives it by comparing each rendition's recorded
        parent against the original the work holds now. The panel test catches a
        canvas composed for a television this deployment no longer has, which the
        hash cannot see because the *original* did not change. And the file test
        catches a row that is current by both and whose file has been deleted,
        which is exactly the state a restored catalogue or a cleared `ready/`
        leaves — trusting the row alone would report a work ready for a wall it
        cannot reach.
        """
        for view in self._catalogue.list_renditions(artwork_id):
            rendition = view.rendition
            if rendition.kind is not RenditionKind.TV_DISPLAY or view.stale:
                continue
            if rendition.target_width != self._settings.panel_width or rendition.target_height != self._settings.panel_height:
                # Composed for a different panel. Not stale by the hash test —
                # the original has not changed — but not showable here either,
                # and the panel is a deployment value that can change under a
                # catalogue that outlives the television.
                continue
            if (self._settings.art_root / rendition.relative_path).is_file():
                return rendition.relative_path
            log.info(
                "the recorded canvas for %s at %s is not on disk; re-composing",
                artwork_id,
                rendition.relative_path,
            )
        return None


__all__ = [
    "PreparationOutcome",
    "PreparationResult",
    "PreparationService",
    "PreparationSettings",
]
