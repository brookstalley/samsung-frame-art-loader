"""Where the label's text goes on a surface of a given size.

The second of the three tiers. **It draws nothing and imports no imaging
library**, which is what lets the judgement about legibility be tested on any
machine — including one where the rasterizer will not build. What it needs from
the rasterizer is not drawing but *measuring*, and that arrives as a function.

**Measurement is injected rather than estimated.** Line breaking depends on the
real face at the real size, and a character-count approximation is wrong in the
direction that matters: it over-estimates capacity for wide type and produces a
label whose last line runs off the surface, which is invisible until somebody is
standing in front of it. So this module decides *policy* — what order, what
hierarchy, what to drop — and is handed the *facts* by whatever will actually
draw. Tests supply a measurer with arithmetic they choose, which is how the
policy is pinned without a font.

**The label drops content rather than shrinking below the legibility floor.**
This is the product's most important accessibility surface: it is read at
standing distance, without a backlight, in whatever light the room has
(`design_decisions.accessibility_approach`). Type that shrinks to fit has
silently converted an accessibility surface into a decorative one, and the
failure is invisible to everyone except the person who cannot read it. So when
everything will not fit, the least identifying lines come off the bottom and the
remaining type stays at its size. What was dropped is reported rather than
discarded quietly, so the journal can say the surface is too small for the
corpus rather than leaving somebody to notice missing dimensions by eye.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

#: The type sizes, in pixels, largest first: title, then artist, then everything
#: else. **PROVISIONAL, and now known to be wrong rather than merely unsettled.**
#: Measured against the reference deployment on 2026-08-11 — a 6-inch, ~300 PPI
#: panel read from 7 feet — `BODY_SIZE_PX` gives a cap height of **2.5 arcminutes**
#: against the **5** that 20/20 vision needs to resolve a letter at all. These are
#: roughly 4× too small for that wall, and they survived every check the product
#: had because nothing here knew the viewing distance.
#:
#: **They are placeholders for a derivation, not for a judgement.**
#: `accessibility-spec.md` § "The type floor is derived from viewing distance, not
#: chosen for a panel" specifies what replaces them: a floor computed from the
#: deployment's PPI and viewing distance against a stated minimum cap height in
#: arcminutes, with these three becoming ratios above that floor. Whoever builds it
#: replaces this note as well as the numbers.
TITLE_SIZE_PX: Final[int] = 40
ARTIST_SIZE_PX: Final[int] = 32
BODY_SIZE_PX: Final[int] = 26

#: Space between one block and the next, as a fraction of the block's own size.
#: Proportional rather than absolute so the whole label rescales coherently when
#: the sizes above are settled.
LEADING: Final[float] = 0.35

#: The widest a line may run before it wraps, as a multiple of its own type size.
#: The panel is far wider than continuous text stays comfortable to read across —
#: at the body size a full-width line on the reference panel runs well past any
#: measure a typographer would set — and line length is the third thing
#: `design_decisions.accessibility_approach` names as carrying legibility,
#: alongside type size and contrast.
#:
#: **In ems rather than characters**, though the readable range is conventionally
#: quoted in characters (roughly 45–75). This tier is handed a measurer and never
#: a face, so it cannot count characters without the approximation this module
#: exists to refuse; a multiple of the type size is the same rule expressed in the
#: one unit available here, and it scales the title and the body together instead
#: of pinning one and distorting the other. At the ~0.5em average glyph width
#: typical of text faces this lands near the middle of that range.
#:
#: **PROVISIONAL — no one has read this panel at standing distance yet.** It is
#: the third of the three settlements that have to be made together, since a
#: measure depends on the face and the size and a narrower one costs lines to the
#: drop rule. Whoever settles it replaces this note as well as the number.
MEASURE_EM: Final[float] = 30.0


@dataclass(frozen=True, slots=True)
class Geometry:
    """The size and margin a label is being laid out for.

    **Named for what it is rather than for what it describes**, which is not a
    nicety: this package also has a `LabelSurface` — the device a label is put
    onto — and `EpaperSurface(geometry=Surface(...))` was a line nobody could read
    twice the same way. One of the two had to give, and the device kept the word
    because that is the seam other code is written against.

    **Geometry is a parameter, never a constant.** The deployment may hold
    several devices with panels of different sizes, and a device may draw its
    label into the mat area around an artwork rather than onto a panel at all
    (`architecture.md` § Direction). A module-level 1448×1072 would make the
    second device a rewrite instead of a configuration.
    """

    width_px: int
    height_px: int
    margin_px: int

    @property
    def text_width_px(self) -> int:
        """How wide a line may be before it has to wrap."""
        return max(0, self.width_px - 2 * self.margin_px)

    @property
    def text_height_px(self) -> int:
        """How tall the whole label may be before something has to come off."""
        return max(0, self.height_px - 2 * self.margin_px)


@dataclass(frozen=True, slots=True)
class Extent:
    """How much room a piece of text takes at a given size, as the renderer measures it."""

    width_px: int
    height_px: int


#: Measure `text` at `size_px`, wrapped to `wrap_px`. Supplied by whatever will
#: draw — Pango in the deployment, arithmetic of the test's own choosing in the
#: suite.
Measure = Callable[[str, int, int], Extent]


@dataclass(frozen=True, slots=True)
class Block:
    """One run of text, placed.

    Carries its size rather than a style name so the renderer needs no table to
    interpret it: a block is drawable from what it holds.
    """

    text: str
    size_px: int
    x_px: int
    y_px: int
    width_px: int
    height_px: int


@dataclass(frozen=True, slots=True)
class Layout:
    """A whole label, placed on a surface, with an honest account of what did not fit."""

    surface: Geometry
    blocks: tuple[Block, ...]
    #: Lines that were left off because the surface could not hold them at a
    #: legible size, outermost-droppable last. Empty is the normal case.
    dropped: tuple[str, ...]

    @property
    def is_empty(self) -> bool:
        """Whether this would put nothing on the surface. Nothing branches on it —
        a blank frame is what drawing no blocks already produces."""
        return not self.blocks


def lay_out(lines: tuple[str, ...], surface: Geometry, measure: Measure) -> Layout:
    """Place the label's lines top-down, dropping from the bottom what will not fit.

    `lines` arrives in wall-label order — title, artist, nationality, dates,
    date, medium, dimensions — which is also least-droppable first. That ordering
    is `LabelText.lines`' responsibility and this function's assumption: it drops
    from the end, so the ordering *is* the priority.

    **The first line is never dropped**, even when it alone overflows. A surface
    too small for one title is a misconfigured device, and returning an empty
    label would present that as a work with no name; the block is placed, the
    overflow is real, and the operator can see what is wrong. Anything else here
    would be this plane hiding a deployment error behind a blank panel.
    """
    if surface.text_width_px <= 0 or surface.text_height_px <= 0:
        return Layout(surface=surface, blocks=(), dropped=lines)

    placed = _place(lines, surface, measure)
    while _overflows(placed, surface) and len(placed) > 1:
        placed = _place(lines[: len(placed) - 1], surface, measure)

    return Layout(
        surface=surface,
        blocks=tuple(placed),
        dropped=lines[len(placed) :],
    )


def _place(lines: tuple[str, ...], surface: Geometry, measure: Measure) -> list[Block]:
    """Stack these lines from the top margin down, at the size each one earns."""
    blocks: list[Block] = []
    y = surface.margin_px
    for index, text in enumerate(lines):
        size = _size_for(index)
        extent = measure(text, size, _wrap_width_for(size, surface))
        blocks.append(
            Block(
                text=text,
                size_px=size,
                x_px=surface.margin_px,
                y_px=y,
                width_px=extent.width_px,
                height_px=extent.height_px,
            )
        )
        y += extent.height_px + round(size * LEADING)
    return blocks


def _wrap_width_for(size_px: int, surface: Geometry) -> int:
    """How far a line of this size may run before it wraps.

    The narrower of the surface and the measure. **The bound only ever narrows** —
    a device smaller than the measure is a device whose margins still win, and a
    bound that widened a line past them would be drawing outside the surface.
    """
    return min(surface.text_width_px, round(MEASURE_EM * size_px))


def _size_for(index: int) -> int:
    """The type size the line at this position gets.

    Position rather than field name, because this tier is handed text and not a
    record: the hierarchy is "first line is the title, second is the artist, the
    rest is supporting" and that holds however the caller assembled the list.
    """
    if index == 0:
        return TITLE_SIZE_PX
    if index == 1:
        return ARTIST_SIZE_PX
    return BODY_SIZE_PX


def _overflows(blocks: list[Block], surface: Geometry) -> bool:
    """Whether the stack runs past the bottom margin.

    Measured to the bottom of the last block rather than by summing heights and
    leading, so the trailing gap below the final line is not counted against the
    fit — a label that is exactly as tall as its surface should fit, and summing
    would reject it for space nothing occupies.
    """
    if not blocks:
        return False
    last = blocks[-1]
    return last.y_px + last.height_px > surface.margin_px + surface.text_height_px
