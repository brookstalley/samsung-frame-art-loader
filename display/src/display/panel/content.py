"""What a label's facts are, and what the engine may do with each of them.

**Shared vocabulary, held apart from both tiers that need it**, for the reason
`styling.py` is: `metadata.py` is the only tier that knows a nationality from a
family name, and `layout.py` is the only tier that knows whether either of them
fits — so the first decides what each fact *is* and the second decides what
survives, and neither is the other's to import for it.

**A fact carries its tier because the two tiers of content fail in opposite
directions.** The label's most important accessibility property is that type
never shrinks to fit (`accessibility-spec.md` § Type never shrinks to fit): type
that quietly got smaller has converted an accessibility surface into a decorative
one, and only the person who cannot read it finds out. That rule was flat until
it collided with itself — a title alone can overflow a surface, and a rule saying
both "the title is never dropped" and "nothing is set below the floor" says
nothing about which of the two yields. The operator's 2026-08-11 ruling split the
content instead of picking a winner:

* **Mandatory** — the artist's name and the work's title. These are what a label
  is *for*: one that cannot say who made the work and what it is called
  identifies nothing, and an unreadably small name is still a name somebody can
  walk closer to read. So they shrink, below the floor if that is what it takes,
  and are never dropped.
* **Optional** — everything else, and *everything* else: nationality, life dates,
  the work's date, its medium, its dimensions, any commentary. These drop at full
  size and are never set below the floor.

**The shrink is reported exactly like a drop, and that is the condition the
ruling rests on rather than a nicety.** The flat rule existed because illegible
type fails invisibly; admitting a shrink re-opens that hole unless the journal
names it. A panel routinely setting names at 20 px is a misconfigured device, and
nobody discovers that by eye at 7 feet.
"""

from dataclasses import dataclass
from enum import Enum

from display.panel.styling import Line, plain


class Tier(Enum):
    """What happens to a fact when the surface will not hold everything.

    Two values, and the asymmetry between them is the whole point — see this
    module's docstring. There is deliberately no third: "nothing else is
    mandatory" is what makes the optional tier affordable, since with four of the
    six tombstone facts droppable the slack below stops being a crisis and
    becomes a per-work answer.
    """

    #: Shrinks rather than vanishing, below the floor if that is what it takes.
    MANDATORY = "mandatory"
    #: Dropped at full size, never set below the floor.
    OPTIONAL = "optional"


@dataclass(frozen=True, slots=True)
class Candidate:
    """One fact the label may carry, and what the engine may do with it.

    **Candidates arrive in reading order, and priority is derived rather than
    carried.** A fact's priority is its tier first and its reading position
    second, which is exactly the order `accessibility-spec.md` lists them in — so
    a separate priority field would be a second ranking free to go stale against
    the first. The engine admits every mandatory fact, then walks the optional
    ones from the top.

    **Reading order and priority order genuinely differ**, which is why the old
    "the ordering *is* the priority" shortcut had to give: the title is set
    *below* the name and is admitted *before* the biography line beneath it,
    because the title is mandatory and where the artist was from is not.
    """

    runs: Line
    tier: Tier
    #: What to set before this fact when it lands on the same line as the fact
    #: declared before it — the comma-space of a tombstone. Empty means this fact
    #: always takes a line of its own.
    #:
    #: **The separator rides the fact that needs it rather than the one before**,
    #: which is what stops an anonymous work's line opening with a stray comma:
    #: a fact whose predecessors were all absent simply starts a line, and the
    #: separator it carries is never set.
    #:
    #: **Joinable facts are declared contiguously, after the fact they continue.**
    #: The engine joins onto the line it is currently building, so a joinable fact
    #: declared after some *other* line had opened would attach itself to that one
    #: instead. Nothing here defends against it — the identification block is the
    #: only run of joinable facts this label has, and it opens the label.
    continues_line: Line = ()
    #: Whether this fact is part of the name the label leads with.
    #:
    #: **Distinct from the tier, and the two are not interchangeable.** The title
    #: is mandatory and is not a name, so a layout asking "may the leading line be
    #: dropped?" in place of "is the leading line the name?" answers yes for a
    #: record with no maker — which is how a wrapping *title* came to be reported
    #: as a name the surface was too narrow for.
    #:
    #: **A culture sets this as readily as a person does.** Where no individual is
    #: known, museum practice puts the culture in the maker slot and leads with it
    #: (`museum-label-findings.md`), and this label follows: `Moche` is the name
    #: of what made the work in every sense this engine cares about.
    names_the_maker: bool = False

    @property
    def text(self) -> str:
        """What this fact says, as the catalogue recorded it.

        The form for a journal, a report or a test — never for the panel. The
        capitals a family name is set in belong to how type is read at 7 feet,
        and a log line shouting somebody's surname into a file would be carrying
        that decision somewhere it means nothing (`styling.plain`).
        """
        return plain(self.runs)
