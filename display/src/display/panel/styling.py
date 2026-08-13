"""How a run of the label's text is set — the vocabulary the three tiers share.

**Its own module because all three tiers need the words and none of them owns
them.** Styling is decided where the text is composed (`metadata.py` is the only
tier that knows which characters are the family name), carried by the tier that
measures and places it (`layout.py`), and realised by the tier that draws
(`pango.py`). Putting these types in any one of those would make the other two
import it for a reason unrelated to what that tier is for — the renderer would be
importing "what a label says" in order to learn what bold means.

**Styling is declared here and applied at the last moment, never baked into the
text.** A run holds the characters as the catalogue recorded them, plus how they
are to be set; `set_text` is what turns the two into the string a renderer draws.
That split is what lets the family name reach the panel in capitals while the
journal, the preview's report and every test go on seeing the name somebody
actually wrote down. It is also what keeps measuring and drawing honest: both
reach the characters through the same function, so they cannot disagree about
what is being set.

**Nothing here is a markup language, and that is the whole point.** The 2024
label interpolated museum text into a Pango markup string, so a title containing
`<` produced mangled type or a parse failure (`data-model.md`). Styling a run by
wrapping it in `<b>` would reintroduce that defect on the exact surface it was
fixed for, so a run is a *range* with properties and the renderer applies
attributes to ranges. A title may contain any character at all and none of it
means anything to this module.
"""

from dataclasses import dataclass
from enum import Enum


class Weight(Enum):
    """How heavy a run is set.

    Two values because the label distinguishes exactly one thing by weight: the
    family name from everything sharing its line. A third would be a typographic
    decision nobody has taken.
    """

    NORMAL = "normal"
    BOLD = "bold"


class Slant(Enum):
    """Whether a run is set upright or italic.

    `UPRIGHT` rather than `NORMAL` so that a run's two style axes cannot both be
    spelled `NORMAL` and be quietly swapped at a call site.
    """

    UPRIGHT = "upright"
    ITALIC = "italic"


class Case(Enum):
    """Whether a run is set as recorded, or capitalised.

    **Not a Pango attribute, unlike its two neighbours.** Pango can transform case
    only from 1.50, and pinning the label's most important run to a version floor
    for something `str.upper` does exactly would buy nothing. So this one is
    realised by `set_text` rather than by the renderer's attribute list — which is
    also why `Run.text` keeps the recorded spelling: a label is not the place a
    person's name loses its capitals for good.
    """

    AS_RECORDED = "as recorded"
    CAPITALS = "capitals"


@dataclass(frozen=True, slots=True)
class Run:
    """A stretch of one line, set one way.

    Defaults are the unstyled case, so a plain fact is `Run("Oil on canvas")` and
    only the runs that depart from it say anything.
    """

    text: str
    weight: Weight = Weight.NORMAL
    slant: Slant = Slant.UPRIGHT
    case: Case = Case.AS_RECORDED

    @property
    def set_text(self) -> str:
        """The characters a renderer actually sets for this run."""
        return self.text.upper() if self.case is Case.CAPITALS else self.text


#: One line of a label: its runs, in reading order. A line is never empty — a
#: fact the label does not have produces no line at all rather than an empty one,
#: which is `LabelText.lines`' rule and the reason nothing here defends against it.
Line = tuple[Run, ...]


def plain(line: Line) -> str:
    """What the line says, as recorded and with no styling applied.

    **The form for anything a person reads outside the panel** — the journal's
    account of what was dropped, the preview's report, a test's expectation. The
    capitals are a fact about how the panel sets a name, and a log line reading
    `KATSUSHIKA, Hokusai` would be this plane shouting somebody's name into a file
    for a reason that only exists at 7 feet.
    """
    return "".join(run.text for run in line)


def set_text(line: Line) -> str:
    """The whole string a renderer draws for this line, with case transforms applied.

    Measuring and drawing both go through here, which is what stops them
    disagreeing: capitals are wider than lower case, so a measurer reading `plain`
    while the renderer set this would under-measure every name on the wall and the
    drop rule would keep a line that runs off the panel.
    """
    return "".join(run.set_text for run in line)


@dataclass(frozen=True, slots=True)
class Span:
    """Where one run lands in the string `set_text` produces, in bytes."""

    run: Run
    start_byte: int
    end_byte: int


def byte_spans(line: Line) -> tuple[Span, ...]:
    """Each run's range within `set_text(line)`.

    **In bytes rather than characters, because that is what Pango's attribute
    indices are** — and the difference is invisible on the corpus's American names
    and immediate on everything else. An en dash spends three bytes, so
    `1760–1849` is nine characters and eleven bytes; a Japanese title spends three
    per glyph. Counting characters puts the bold attribute part-way through a name
    the moment anything earlier on the line is not ASCII, which on this corpus is
    most of it, and the result is a run of the wrong length set in the wrong
    weight rather than an error anybody sees.

    Derived from `Run.set_text` and not from `Run.text`, for the same reason
    `set_text` exists: an index into a string that was never set points at the
    wrong characters as soon as a capital costs a different number of bytes than
    the letter it replaced.
    """
    spans: list[Span] = []
    offset = 0
    for run in line:
        end = offset + len(run.set_text.encode("utf-8"))
        spans.append(Span(run=run, start_byte=offset, end_byte=end))
        offset = end
    return tuple(spans)
