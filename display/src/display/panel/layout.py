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

**What the floor *is* comes from `legibility.py` and arrives as a parameter**,
like the geometry and the measurer: it is derived from how far the reader stands
from this particular panel, so it is a fact about a device rather than a constant
this module could hold. A floor written down here would be a claim that every
panel is read from the same distance, which is how the sizes this replaced came
to be half the height at which a letter can be resolved at all.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from display.panel.legibility import TypeScale

#: Space between one block and the next, as a fraction of the block's own size.
#: Proportional rather than absolute, so the whole label rescales coherently with
#: the scale it is laid out against — which now varies per device.
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
#: **Inert on the reference wall, and deliberately kept anyway.** Now that the
#: sizes derive from the viewing distance, 30 em at that panel's ~92 px floor is
#: ~2760 px against 1318 px of usable width, so the panel's own edge always
#: governs there and this bound narrows nothing. It stays because it is the
#: mechanism that matters on the *other* surface the architecture norm names — a
#: device drawing its label into the mat area around an artwork, where the
#: available width is far larger than any measure a typographer would set — and
#: because a rule deleted for being unexercised on one device is a rule the next
#: device does not get. `TestTheMeasure` therefore exercises it on a surface wide
#: enough for it to bite, rather than on this panel.
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
    #: The width this block was measured at, and the width it must be drawn at.
    #: **Carried rather than recomputed, because the two sides silently disagreed
    #: once.** The measure bound narrows a line below the surface width, so a
    #: renderer that wrapped at the surface width instead would draw one row where
    #: two were measured: the drawn line runs past its bound, every block below it
    #: sits a row lower than the ink, and the drop rule sheds a line the panel
    #: would have held. Nothing about that is visible until somebody is standing
    #: in front of the panel.
    wrap_px: int


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


def lay_out(lines: tuple[str, ...], surface: Geometry, measure: Measure, scale: TypeScale) -> Layout:
    """Place the label's lines top-down, dropping from the bottom what will not fit.

    `lines` arrives least-droppable first — who made it, what it is called, when,
    out of what, how big, and any commentary. That ordering is `LabelText.lines`'
    responsibility and this function's assumption: it drops from the end, so the
    ordering *is* the priority. **Named by role rather than by field**, because
    the leading line is composed from four of them and a list of field names here
    went stale the moment the identification block was collapsed into one line.

    `scale` is the device's, not this module's. **The sizes cannot be constants
    here** because how large type has to be is a fact about the reader's distance
    from a particular panel, and holding a pixel value in this file would be the
    same defect that shipped a body size half the height at which a letter can be
    resolved — see `legibility.py`.

    **The first line is never dropped**, even when it alone overflows. A surface
    too small for one title is a misconfigured device, and returning an empty
    label would present that as a work with no name; the block is placed, the
    overflow is real, and the operator can see what is wrong. Anything else here
    would be this plane hiding a deployment error behind a blank panel.
    """
    if surface.text_width_px <= 0 or surface.text_height_px <= 0:
        return Layout(surface=surface, blocks=(), dropped=lines)

    placed = _place(lines, surface, measure, scale)
    while _overflows(placed, surface) and len(placed) > 1:
        placed = _place(lines[: len(placed) - 1], surface, measure, scale)

    return Layout(
        surface=surface,
        blocks=tuple(placed),
        dropped=lines[len(placed) :],
    )


def _place(lines: tuple[str, ...], surface: Geometry, measure: Measure, scale: TypeScale) -> list[Block]:
    """Stack these lines from the top margin down, at the size each one earns."""
    blocks: list[Block] = []
    y = surface.margin_px
    for index, text in enumerate(lines):
        size = _size_for(index, scale)
        wrap = _wrap_width_for(size, surface)
        extent = measure(text, size, wrap)
        blocks.append(
            Block(
                text=text,
                size_px=size,
                x_px=surface.margin_px,
                y_px=y,
                width_px=extent.width_px,
                height_px=extent.height_px,
                wrap_px=wrap,
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


def _size_for(index: int, scale: TypeScale) -> int:
    """The type size the line at this position gets.

    Position rather than field name, because this tier is handed text and not a
    record: the hierarchy is "the leading line is the most identifying one, the
    rest supports it" and that holds however the caller assembled the list.

    **Two tiers rather than three, which is what the calibration supports.** The
    sizes used to be title, artist, everything-else, three judged numbers with no
    stated relationship. Reading them off a scale leaves exactly the two readings
    the operator settled by eye; the rung between them is the size that was
    reported as taking effort to read, so interpolating a middle tier would be
    aiming type at the one reading recorded as a boundary rather than a target.
    """
    return scale.primary_px if index == 0 else scale.floor_px


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
