"""The theme manifest — the one channel from curation to the display plane.

**Membership in this document IS catalogue readiness.** There is no readiness
flag on a work to drift out of step with the facts; readiness is evaluated here,
once, at build time, and the display plane sees only what survived. That is what
makes "the wall selects a work it cannot render" structurally impossible rather
than defended against.

**The cost of that design is paid here, in full.** A work can sit in a theme and
never reach the wall. Silence is this product's characteristic failure, so this
build does not get to be silent: every excluded work is named, with a reason, in
what the build returns. A builder that returned only a list would be an
incomplete implementation of the design, not a simpler one.

The document is written temp-and-rename. POSIX rename is atomic within a
filesystem, so the display plane polling this path never observes a half-written
manifest — which is the entire concurrency-control story between the two planes.
"""

import json
import logging
import os
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Final

from curation.counting import agree, counted
from curation.persistence.records import (
    Artist,
    Artwork,
    ArtworkStatus,
    MatColor,
    Original,
    Rendition,
    Theme,
    Wall,
    is_current,
    tv_renditions_newest_first,
)

log = logging.getLogger(__name__)

#: The manifest's filename under `ART_ROOT`, **one file per wall**. Not
#: configurable: both planes have to agree where it is, and a setting is only a
#: way for them to stop agreeing.
#:
#: One file per wall rather than one file carrying a section per wall. Change
#: detection on the other side is an mtime poll at about a second, so a shared
#: file would wake every wall's display on every other wall's change — and would
#: make "the manifest's sequence" ambiguous exactly where the coalescing and
#: sequence-regression rules need it to be singular. Per file also leaves a
#: display plane structurally unable to read a wall it does not serve: it is
#: configured with one wall's id and stats one path.
MANIFEST_FILENAME_TEMPLATE: Final[str] = "theme-manifest-{wall_id}.json"

#: Bumped only by a change that would stop an existing display plane reading a
#: manifest correctly — a removed field, a changed meaning, a new required key.
#: Display refuses a major it does not recognise and keeps the last manifest it
#: had, so a bump is a deliberate cutover rather than a silent break.
SCHEMA_MAJOR: Final[int] = 1

#: Bumped by additive changes. Display ignores a minor it does not know, which is
#: what makes adding a field free.
SCHEMA_MINOR: Final[int] = 1


def manifest_path_in(art_root: Path, wall_id: str) -> Path:
    """Where one wall's manifest lives under a given art root.

    The one place the template is filled in on this side, so a caller cannot
    spell the name a second way — and so the display plane's own copy of the
    template has exactly one thing to agree with.
    """
    return art_root / MANIFEST_FILENAME_TEMPLATE.format(wall_id=wall_id)


class ExclusionReason(StrEnum):
    """Why a theme member did not reach the wall.

    Each value is a distinct thing a curator would do something different about,
    which is the test for whether a reason earns its own name: an archived work
    is a decision, a missing original is acquisition's job, and a stale rendition
    is the renderer's.
    """

    #: Out of circulation. Theme membership is curatorial and survives archiving,
    #: so the work stays in the theme and simply stops being shown.
    ARCHIVED = "archived"
    #: No master image has been acquired, so there is nothing to render from.
    NO_ORIGINAL = "no_original"
    #: Nothing has been rendered for the television yet.
    NO_RENDITION = "no_rendition"
    #: A render exists but was made from a different image than the work now
    #: holds — showing it would put the previous acquisition on the wall.
    STALE_RENDITION = "stale_rendition"
    #: No mat colour is current, so the work has no composed presentation.
    NO_MAT_COLOR = "no_mat_color"


@dataclass(frozen=True, slots=True)
class WorkInputs:
    """Everything the readiness rule needs about one work, gathered by the caller.

    A record rather than a store handle so the rule below is a pure function of
    stated facts: it can be read, and tested, without a database.
    """

    artwork: Artwork
    artist: Artist | None
    original: Original | None
    tv_rendition: Rendition | None
    mat_color: MatColor | None


@dataclass(frozen=True, slots=True)
class Exclusion:
    """One work that is in the theme and not on the wall, and why."""

    work_id: str
    title: str
    reason: ExclusionReason
    #: A sentence a curator can act on, not a restatement of the enum.
    detail: str


@dataclass(frozen=True, slots=True)
class ManifestEntry:
    """One work as the display plane receives it."""

    work_id: str
    #: Relative to `ART_ROOT`. No stored path is absolute, so the two planes can
    #: disagree about where the tree is mounted without disagreeing about this.
    render_path: str
    label: dict[str, str | None]


@dataclass(frozen=True, slots=True)
class ManifestBuild:
    """What one build produced — including, deliberately, what it left out."""

    #: Which wall this build is about. Carried so that a surface can name it in
    #: the confirmation — "Hang Winter in the living room" — without asking a
    #: second question; a confirmation that reads correctly only because there is
    #: one possible target silently becomes wrong when a second display arrives.
    #: It is deliberately **not** a field inside the document `as_document`
    #: writes: the wall is carried by the *filename*, which is what makes a
    #: display plane unable to open a wall it does not serve rather than merely
    #: unwilling to act on it. A field would be a second answer to the same
    #: question, and the two could disagree.
    wall: Wall
    theme: Theme
    entries: Sequence[ManifestEntry]
    exclusions: Sequence[Exclusion]
    rotation_interval_seconds: int
    shuffle: bool
    directive_sequence: int
    pinned_work_id: str | None

    @property
    def considered(self) -> int:
        """Every member the theme offered. Entries plus exclusions account for all of them."""
        return len(self.entries) + len(self.exclusions)

    def summarise(self) -> str:
        """One sentence saying how much of the theme reached the wall.

        **It lives on the build rather than on either surface.** Both the tool
        result and the browser response state this same fact, and two
        hand-written sentences drift — a caller told "9 of 12" by one surface and
        "all 12" by the other has no way to tell which is lying. Formatting may
        differ per surface; what is *claimed* may not.

        Stated on the clean build too, deliberately. A message that appeared only
        when something was wrong would train a reader to skim past its absence,
        and "12 of 12" is the sentence that makes "9 of 12" legible.

        **It stops at the counts and does not tell the reader where to look.**
        Each surface knows what it put in front of whoever is reading — a field
        name in a tool result, a table on a page — and this cannot. An earlier
        version ended "each for the reason given", which left the tool result
        saying the same thing twice once its own pointer was appended.
        """
        if self.considered == 0:
            return "This theme holds no works yet, so nothing is on the wall."
        if not self.exclusions:
            # The no-exclusions branch agrees with its sibling below, and both
            # were fixed together: taking one and leaving the other makes this
            # method correct when a theme has exclusions and wrong when it does
            # not, which is the harder of the two to notice.
            return f"All {counted(self.considered, 'work')} in this theme " f"{agree(self.considered, 'is', 'are')} on the wall."
        return (
            f"{len(self.entries)} of {counted(self.considered, 'work')} in this theme "
            f"{agree(self.considered, 'is', 'are')} on the wall; "
            f"{len(self.exclusions)} {agree(len(self.exclusions), 'is', 'are')} not currently displayable."
        )


def assess(inputs: WorkInputs) -> Exclusion | None:
    """Judge one work's catalogue readiness. `None` means it reaches the wall.

    **"The fetch succeeded" is deliberately not a sixth check.** Holding an
    original is what a succeeded fetch produces, so the condition is already
    carried by `NO_ORIGINAL`. Reading it as "the *last* fetch attempt succeeded"
    would take a work off the wall because a later re-acquisition failed while a
    perfectly good original and a current render were still held — a regression
    dressed as a safety check.
    """
    artwork = inputs.artwork
    if artwork.status is ArtworkStatus.ARCHIVED:
        return _excluded(artwork, ExclusionReason.ARCHIVED, "It has been archived, so it is out of circulation.")
    if inputs.original is None:
        return _excluded(
            artwork,
            ExclusionReason.NO_ORIGINAL,
            "No master image has been acquired for it yet.",
        )
    if inputs.mat_color is None:
        return _excluded(
            artwork,
            ExclusionReason.NO_MAT_COLOR,
            "No mat colour has been chosen, so it has no composed presentation.",
        )
    if inputs.tv_rendition is None:
        return _excluded(
            artwork,
            ExclusionReason.NO_RENDITION,
            "It has a master image but has not been rendered for the television yet.",
        )
    # Through the shared predicate, because it already owns what "current"
    # means. This re-derived it inline, so a change to the rule would have
    # decided manifest membership by the old one while the review grid used the
    # new — the work badged current and silently dropped from the wall.
    if not is_current(inputs.tv_rendition, inputs.original):
        return _excluded(
            artwork,
            ExclusionReason.STALE_RENDITION,
            "Its render was made from an earlier acquisition and needs regenerating.",
        )
    return None


def entry_for(inputs: WorkInputs) -> ManifestEntry:
    """Turn a ready work into the entry the display plane reads.

    Label *text* crosses to the display plane; label *rendering* does not. The
    e-paper panel's geometry belongs to the plane that owns that panel, so what
    goes here is the words and nothing about how they are set.

    **The artist's name crosses three times over, and that is not redundancy.**
    `artist` is what the source called them, `artist_family_name` and
    `artist_given_name` are which part is which. A display plane setting the
    family name apart needs the parts; one drawing a plain line needs
    the whole; and a work whose artist has no recorded parts has only the whole.
    Sending the parts alone would make the third case unlabelable, and sending
    the whole alone would put the split back where it was refused — in a rule
    over a string that is wrong for "van Gogh".
    """
    if inputs.tv_rendition is None:
        # Raised rather than asserted: `assert` disappears under -O, and what it
        # would have caught is a caller that skipped `assess` — which would put a
        # work with no render into the manifest and take the wall down to a
        # missing file rather than to a named exclusion.
        raise ValueError(f"Work {inputs.artwork.id!r} has no television render; call assess before entry_for.")
    artist = inputs.artist
    return ManifestEntry(
        work_id=inputs.artwork.id,
        render_path=inputs.tv_rendition.relative_path,
        label={
            "title": inputs.artwork.title,
            "artist": None if artist is None else artist.name,
            "artist_family_name": None if artist is None else artist.family_name,
            "artist_given_name": None if artist is None else artist.given_name,
            # **The short form wins, and the fallback resolves here rather than at
            # the panel.** The manifest is what the display plane parses, not a
            # catalogue export, so it carries the string the label should set;
            # which of two recorded strings that is, is a question about content,
            # and content is this plane's. A display told to choose would be
            # re-deciding curation policy from the far side of the seam.
            "artist_nationality": None if artist is None else (artist.display_nationality or artist.nationality),
            "artist_dates": None if artist is None else _artist_dates(artist),
            "date_created": inputs.artwork.date_created,
            "medium": inputs.artwork.medium,
            "dimensions": inputs.artwork.dimensions,
            "commentary": inputs.artwork.commentary,
        },
    )


def as_document(build: ManifestBuild) -> dict[str, Any]:
    """The manifest as the display plane parses it.

    Exclusions are **not** in the document. They are curation's report to a
    curator about its own catalogue; the display plane has no use for a list of
    things it is not being asked to show, and putting them here would invite a
    reader to treat the manifest as a catalogue export.
    """
    return {
        "schema": {"major": SCHEMA_MAJOR, "minor": SCHEMA_MINOR},
        "generated_at": datetime.now(UTC).isoformat(),
        "theme": {"id": build.theme.id, "name": build.theme.name},
        "rotation": {
            "interval_seconds": build.rotation_interval_seconds,
            "shuffle": build.shuffle,
        },
        "directive": {
            "sequence": build.directive_sequence,
            "pinned_work_id": build.pinned_work_id,
        },
        "entries": [
            {"work_id": entry.work_id, "render_path": entry.render_path, "label": entry.label} for entry in build.entries
        ],
    }


def write_atomically(path: Path, document: dict[str, Any]) -> None:
    """Replace the manifest in one step, so no reader ever sees a partial one.

    The temp file is created in the destination's own directory because
    `os.replace` is only atomic within a filesystem, and the obvious temp
    location is frequently a different one.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(document, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            # The rename below publishes whatever is in the file. Without this the
            # bytes may still be in a buffer, and a reader would be handed a
            # truncated document that parses as invalid JSON rather than as absent.
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:  # prawduct:allow prawduct/broad-except -- cleanup-and-reraise; the temp file must go on any exit
        # Wider than `Exception` deliberately, and it swallows nothing: a
        # `KeyboardInterrupt` or an early close leaves this body just as surely
        # as an error does, and each one would strand a `.theme-manifest.json.*`
        # file beside the real manifest. The same exception continues.
        Path(temporary).unlink(missing_ok=True)
        raise


def _excluded(artwork: Artwork, reason: ExclusionReason, detail: str) -> Exclusion:
    return Exclusion(work_id=artwork.id, title=artwork.title, reason=reason, detail=detail)


def _artist_dates(artist: Artist) -> str | None:
    """The dates as they should read on a label.

    The stored text wins when there is any, because it came from the source and
    carries forms — "c. 1450–1516", "active 1520s" — that two integers cannot.
    Falling back to the years means a work whose artist has only one known date
    still gets a legible label rather than nothing.
    """
    if artist.lifespan_text:
        return artist.lifespan_text
    if artist.born is None and artist.died is None:
        return None
    return f"{artist.born or ''}–{artist.died or ''}"


def tv_rendition_of(renditions: Sequence[Rendition]) -> Rendition | None:
    """The television render the wall would use, or None if there is none.

    The preference itself lives with the records, so the thumbnail service can
    walk the same order and the two cannot pick different pictures of the same
    work. Stale renders are included on purpose — `assess` needs one in hand to
    say "needs regenerating" rather than "never rendered".
    """
    ordered = tv_renditions_newest_first(renditions)
    return ordered[0] if ordered else None
