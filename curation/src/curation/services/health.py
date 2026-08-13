"""Everything the health panel states, composed once, in one call.

**This is the product's only alerting surface.** The operator chose it as such in
2026-07-20 — no push, no email, no external monitor — and the consequence was
recorded honestly rather than left implicit: mean time to detection is bounded by
how often the curator opens the page. What follows from that is the rule this
module exists to hold: *every* observation the panel makes has to be reachable
from here, because a signal with no reader is the silent failure this whole
product is built to refuse, wearing the costume of the mechanism meant to catch
it.

**Observations with ages, never verdicts.** Nothing here computes healthy or
unhealthy, and nothing compares an age to a threshold. A green dot that is green
because nothing checked is exactly this product's characteristic failure wearing
a UI, and it would be worse than no panel at all because it manufactures
confidence. Each reading says what was found, when, and — when there is nothing
to say — that there is nothing to say.

**There is no budget balance here, and its absence is a decision rather than an
omission** (operator, 2026-08-04). The provider's `limit_remaining` was observed
reporting credit while live calls were already being refused, so it fails by
inversion rather than by staleness — and stating its age, which is this panel's
whole remedy for a stale figure, would not warn anyone about the case that bites.
The honest budget signals are recorded per-run spend and the `halted_by_budget`
outcome, and both are on the run view. Do not add the field back here without
reopening that decision.

Composed in the service layer rather than in the handler, so both the assembly
and its rules are testable without HTTP, and so the surface stays the thin
binding the architecture requires.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from curation.persistence import backup
from curation.persistence.backup import BackupReading
from curation.services.display import DisplayService, WallHeartbeat, describe_wall_status
from curation.services.display_fit import ArtworkBox


@dataclass(frozen=True, slots=True)
class HealthReading:
    """Every observation the panel makes, gathered at one instant."""

    #: What the display serving each wall last said about itself, including
    #: whatever else it chose to report. `observability-strategy.md`'s failure
    #: table maps TV connectivity, panel state and the last error onto this
    #: document, and the panel showing it is what gives those rows a reader.
    #:
    #: **A list rather than one reading**, because with a display per wall the
    #: interesting question stopped being "has the display plane reported" and
    #: became "which wall has not". One shared reading could not have answered it.
    walls: Sequence[WallHeartbeat]
    #: When the catalogue was last safely copied, or that nothing has copied it.
    backup: BackupReading
    #: The space this deployment renders into. Not a failure signal — it is here
    #: because a wrong mat or floor shows up only as works being labelled oddly in
    #: the grid, which reads as a catalogue problem rather than a configuration
    #: one.
    artwork_box: ArtworkBox

    def describe(self) -> str:
        """One sentence across every wall, from the readings this panel holds.

        Delegated rather than written here, because the tool surface states the
        same fact from the same readings and two hand-written sentences drift —
        a caller told "the study has not reported" by one surface and "every wall
        has reported" by the other has no way to tell which is lying.
        """
        return describe_wall_status(self.walls)


class HealthService:
    """Gather what the panel states. Decides nothing about any of it."""

    def __init__(self, display: DisplayService, *, backup_receipt_path: Path, box: ArtworkBox) -> None:
        self._display = display
        #: Where the backup job records that it succeeded. Passed in rather than
        #: resolved here, for the reason every settings object in this layer
        #: gives: a service that read its own configuration could not be tested
        #: against two deployments and would make every caller share one.
        self._backup_receipt_path = backup_receipt_path
        self._box = box

    def observe(self) -> HealthReading:
        """Read every signal the panel shows, now.

        One call rather than one per signal, which is what lets the handler above
        stay a dispatch: a surface assembling three reads is a surface deciding
        what the panel is made of, and the next signal would then have to be added
        in two places with nothing to notice if it reached only one.
        """
        return HealthReading(
            walls=self._display.survey_wall_status(),
            backup=backup.read(self._backup_receipt_path),
            artwork_box=self._box,
        )
