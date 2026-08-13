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

**Content adapts to the surface; legibility does not — except for the facts that
identify the work.** This is the product's most important accessibility surface:
it is read at standing distance, without a backlight, in whatever light the room
has (`design_decisions.accessibility_approach`). So when everything will not fit,
optional facts come off at full size and the survivors keep theirs. The one
exception is the artist's name and the work's title, which shrink rather than
vanish, because a label that cannot say who made the work and what it is called
identifies nothing while an unreadably small name is still a name somebody can
walk closer to read. Which fact is which arrives on the fact itself
(`content.py`); this module never guesses it from a position.

**What was dropped and what was shrunk are both reported rather than discarded
quietly.** The journal can then say the surface is too small for the corpus,
rather than leaving somebody to notice missing dimensions by eye — and a shrink
is reported for a stronger reason than a drop: the whole argument for never
shrinking is that illegible type fails invisibly, so admitting a shrink re-opens
that hole unless something names it.

**What the floor *is* comes from `legibility.py` and arrives as a parameter**,
like the geometry and the measurer: it is derived from how far the reader stands
from this particular panel, so it is a fact about a device rather than a constant
this module could hold. A floor written down here would be a claim that every
panel is read from the same distance, which is how the sizes this replaced came
to be half the height at which a letter can be resolved at all.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Final

from display.panel.content import Candidate, Tier
from display.panel.legibility import TypeScale
from display.panel.styling import Line, Run, plain

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

#: How much of its size the mandatory tier gives up per attempt, once no
#: arrangement of it fits at the derived sizes.
#:
#: **Small enough that the answer is the size rather than the step.** At the
#: reference panel's 130 px primary tier this is under 3 px per attempt, so a name
#: that needed 5% off does not lose 20%; the whole search is at most fifty
#: measurements of a handful of lines, on a device that redraws once per rotation.
#: A coarser step would be visible on the panel as type smaller than it had to be,
#: which is the failure this whole module is arranged to prevent.
SHRINK_STEP: Final[float] = 0.02


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


#: Measure `line` at `size_px`, wrapped to `wrap_px`. Supplied by whatever will
#: draw — Pango in the deployment, arithmetic of the test's own choosing in the
#: suite.
#:
#: **It takes the styled runs and not their text, because styling changes the
#: answer.** Bold is wider than regular and capitals are wider than lower case, so
#: a measurer handed the plain string would under-report the one line this label
#: leads with — and the drop rule, which is driven entirely by measured height,
#: would keep a line that runs off the panel. Nobody discovers that except the
#: person standing in front of it.
Measure = Callable[[Line, int, int], Extent]


@dataclass(frozen=True, slots=True)
class Block:
    """One line of the label, placed.

    Carries its size rather than a style name so the renderer needs no table to
    interpret it: a block is drawable from what it holds. Since the label styles
    part of a line rather than a whole one, what it holds is runs.
    """

    runs: Line
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

    @property
    def text(self) -> str:
        """What this block says, as recorded — for a journal, a report or a test.

        Not what the renderer sets: the capitals belong to how the panel sets a
        name at 7 feet, and a log line shouting somebody's surname into a file
        would be carrying a typographic decision somewhere it means nothing.
        """
        return plain(self.runs)


@dataclass(frozen=True, slots=True)
class Layout:
    """A whole label, placed on a surface, with an honest account of what it cost."""

    surface: Geometry
    blocks: tuple[Block, ...]
    #: Facts that were left off because the surface could not hold them at a
    #: legible size, least-droppable first. Empty is the normal case.
    dropped: tuple[str, ...]
    #: Lines that had to be set below the legibility floor for the surface to hold
    #: them at all — the identifying facts, which shrink rather than vanish.
    #:
    #: **Reported for a stronger reason than `dropped` is.** A missing dimension
    #: is visible to anybody who looks at the panel; type that got quietly smaller
    #: is visible to nobody except the person who cannot read it, which is the
    #: entire argument for the rule this is the exception to. A device routinely
    #: filling this is misconfigured — too small a panel, or read from too far —
    #: and this is the only place that says so.
    shrunk: tuple[str, ...] = ()

    @property
    def is_empty(self) -> bool:
        """Whether this would put nothing on the surface. Nothing branches on it —
        a blank frame is what drawing no blocks already produces."""
        return not self.blocks


def lay_out(
    candidates: tuple[Candidate, ...],
    surface: Geometry,
    measure: Measure,
    scale: TypeScale,
) -> Layout:
    """Fill the surface with as much of the label as it will hold, legibly.

    `candidates` arrives in reading order — who made it, where they were from and
    when they lived, what it is called, when, out of what, how big, and any
    commentary. **Reading order is not priority order**, which is the change from
    the rule this replaced: each fact carries its tier, and the engine admits
    every mandatory fact before it considers any optional one. So the title is
    set below the identification line and admitted before the nationality that
    shares it.

    Four things happen, in this order, and the order is the policy:

    1. **The mandatory facts are admitted, not offered.** They are the room the
       rest competes for what is left of, rather than candidates competing for
       room. If they do not fit at the derived sizes, the name gives up its line
       before it gives up its size — and gives up its size last of all.
    2. **Optional facts are admitted from the top, each only if it still fits.**
       At the floor, never below it: an optional fact that will not fit legibly is
       dropped rather than squeezed.
    3. **Slack left over is spent on type, and only then.** A label set enormous
       with three of its six facts dropped is worse than one set comfortably with
       all six, so growth happens once no further fact can be admitted.
    4. **What it cost is reported** — what was dropped, and what had to be set
       below the floor.

    `scale` is the device's, not this module's. **The sizes cannot be constants
    here** because how large type has to be is a fact about the reader's distance
    from a particular panel, and holding a pixel value in this file would be the
    same defect that shipped a body size half the height at which a letter can be
    resolved — see `legibility.py`.
    """
    if surface.text_width_px <= 0 or surface.text_height_px <= 0:
        # There is nowhere to put anything, so nothing is placed and everything is
        # reported. A misconfigured device says so through the journal rather than
        # through a label nobody can see.
        return Layout(surface=surface, blocks=(), dropped=tuple(c.text for c in candidates), shrunk=())

    kept = tuple(index for index, candidate in enumerate(candidates) if candidate.tier is Tier.MANDATORY)
    placed = _admit_the_mandatory_facts(candidates, kept, surface, measure, scale)

    # **Nothing optional reaches a label that already had to shrink, and there is
    # deliberately no guard saying so.** A surface too small for the artist's name
    # at the floor has no slack to offer a medium — and `_arrange` is what
    # enforces it, since it only ever admits at the derived sizes and adding a
    # fact can only make an arrangement taller. A `if not placed.shrunk` here read
    # as the rule and was a branch nothing could enter; the rule is asserted as
    # behaviour instead, by `TestTheFactsThatIdentifyTheWorkShrinkInstead`.
    for index, candidate in enumerate(candidates):
        if candidate.tier is Tier.MANDATORY:
            continue
        trial = tuple(sorted((*kept, index)))
        attempt = _arrange(candidates, trial, surface, measure, scale)
        if attempt is None:
            # **Tried rather than abandoned**, so a one-word date is not lost to a
            # three-line medium that was merely earlier in the list. The facts
            # differ in size as well as in rank, and the journal reports every one
            # that came off either way.
            continue
        kept, placed = trial, attempt
    placed = _grow_into_the_slack(placed, surface, measure, scale)

    return Layout(
        surface=surface,
        blocks=placed.blocks,
        dropped=tuple(c.text for index, c in enumerate(candidates) if index not in kept),
        shrunk=placed.shrunk,
    )


@dataclass(frozen=True, slots=True)
class _ComposedLine:
    """One line of the label before it has a size or a position."""

    runs: Line
    #: Whether any fact on this line is one the label may not drop. A line is
    #: mandatory if *any* of it is: the identification line carries a family name
    #: and may also carry a nationality, and the name is what decides its fate.
    mandatory: bool


@dataclass(frozen=True, slots=True)
class _Placement:
    """A set of lines, placed, and what it cost to place them.

    Carries what it was built from as well as what came out. Growth adjusts one
    size and re-places, and re-deriving which rung of the name ladder produced a
    set of blocks — by comparing runs against a fresh composition — was both
    fragile and a fact this already knew.
    """

    lines: tuple[_ComposedLine, ...]
    sizes: tuple[int, ...]
    blocks: tuple[Block, ...]
    shrunk: tuple[str, ...]


def _admit_the_mandatory_facts(
    candidates: tuple[Candidate, ...],
    kept: tuple[int, ...],
    surface: Geometry,
    measure: Measure,
    scale: TypeScale,
) -> _Placement:
    """Place the facts that identify the work, whatever it takes.

    They are never dropped, so this always returns a placement — see
    `_shrink_to_fit` for what happens when the surface will not hold them.
    """
    arranged = _arrange(candidates, kept, surface, measure, scale)
    if arranged is not None:
        return arranged
    return _shrink_to_fit(candidates, kept, surface, measure, scale)


def _arrange(
    candidates: tuple[Candidate, ...],
    kept: tuple[int, ...],
    surface: Geometry,
    measure: Measure,
    scale: TypeScale,
) -> _Placement | None:
    """Place these facts at their proper sizes, or say that they will not fit.

    **The name ladder is the two rungs tried here**, and it is stated as a
    preference with a fallback rather than as a number of lines: the name block
    gives up its line before it gives up its size. A layout engine told "two
    lines" would break `ANDERS, Joseph` for every short name on the wall; one told
    "one line" would shrink a long one to fit a break it could have taken for
    free.

    The second rung is worth what it is because the sizes then become
    independent: `KATSUSHIKA` holds the identification tier on a line of its own
    while `Hokusai, Japanese, 1760–1849` follows at the floor, which costs less
    height than three wrapped rows of the whole thing at the larger size. That is
    a long family name costing only itself.
    """
    for broken in (False, True):
        lines = _compose(candidates, kept, break_first_join=broken)
        placement = _placed(lines, _sizes_for(lines, scale), surface, measure, scale)
        if not _overflows(placement.blocks, surface):
            return placement
    return None


def _shrink_to_fit(
    candidates: tuple[Candidate, ...],
    kept: tuple[int, ...],
    surface: Geometry,
    measure: Measure,
    scale: TypeScale,
) -> _Placement:
    """Give up size, having already given up layout, and say so.

    **The last resort, and the only place this product sets type below its own
    floor.** The alternative the operator rejected was dropping the title, which
    leaves a picture beside a label that does not name it; a name too small to
    read at 7 feet can still be read by somebody who steps closer, and a name that
    is not there cannot.

    **Every line shrinks by the same factor**, so the hierarchy survives the
    reduction: a label whose identification line kept its size while its title
    collapsed would be saying that one of the two identifies the work and the
    other does not.

    **Both rungs of the ladder are shrunk and the larger answer wins**, rather
    than the shorter arrangement being shrunk. Which rung is shorter at full size
    is the wrong question — giving up size last of all is the whole ordering — and
    the two questions genuinely disagree. On a wide panel they land within a few
    percent, because breaking the name buys a smaller tail and pays a line box for
    it; on a **narrow** surface, which the architecture norm names as a supported
    device, the joined line wraps far enough that the break wins by several sizes.
    A rule chosen on the panel in front of us would have been wrong for the one
    beside it.
    """
    attempts = [
        _shrink_one_arrangement(_compose(candidates, kept, break_first_join=broken), surface, measure, scale)
        for broken in (False, True)
    ]
    # `max` keeps the first of equals, which is the unbroken arrangement: the same
    # legibility for one fewer line box.
    return max(attempts, key=_leading_size)


def _shrink_one_arrangement(
    lines: tuple[_ComposedLine, ...],
    surface: Geometry,
    measure: Measure,
    scale: TypeScale,
) -> _Placement:
    """The largest this arrangement can be set and still fit."""
    full = _sizes_for(lines, scale)
    factor = 1.0
    placement = _placed(lines, full, surface, measure, scale)
    while _overflows(placement.blocks, surface) and factor > SHRINK_STEP:
        factor -= SHRINK_STEP
        placement = _placed(lines, tuple(max(1, round(size * factor)) for size in full), surface, measure, scale)
    # A surface that overflows even at a single pixel is a misconfigured device,
    # and the label is placed anyway: returning nothing would present a broken
    # deployment as a work with no name.
    return placement


def _leading_size(placement: _Placement) -> int:
    """How large the most identifying line ended up — what a shrink is judged by."""
    return placement.blocks[0].size_px if placement.blocks else 0


def _grow_into_the_slack(
    placed: _Placement,
    surface: Geometry,
    measure: Measure,
    scale: TypeScale,
) -> _Placement:
    """Spend what is left on type, now that no further fact can be admitted.

    **Only the identifying facts grow, and only to the tier above.** The two
    sizes are the two readings the operator settled at the panel, and the rung
    between them is the size reported as taking effort to read — so growth is a
    promotion from one to the other rather than a search, and nothing lands
    between them. Optional facts stay at the floor by construction: this is the
    two-distance label museum practice sets, where the identification block is for
    the approach and everything else is for whoever walks up.

    An anonymous untitled work is what this exists for — a label with two facts on
    a panel sized for six leaves most of the surface empty otherwise.
    """
    for index, line in enumerate(placed.lines):
        if index == 0 or not line.mandatory or placed.sizes[index] == scale.primary_px:
            continue
        grown = (*placed.sizes[:index], scale.primary_px, *placed.sizes[index + 1 :])
        candidate_placement = _placed(placed.lines, grown, surface, measure, scale)
        if _overflows(candidate_placement.blocks, surface):
            # Growth stops at the first line that will not take it rather than
            # skipping past: promoting a lower line while the one above stayed
            # small would invert the hierarchy to fill space.
            break
        placed = candidate_placement
    return placed


def _compose(
    candidates: tuple[Candidate, ...],
    kept: tuple[int, ...],
    *,
    break_first_join: bool,
) -> tuple[_ComposedLine, ...]:
    """Join the admitted facts into lines, in reading order.

    A fact starts a line unless it carries a separator *and* there is a line under
    construction to join. That second condition is what keeps an anonymous work's
    label from opening with a stray comma: a nationality whose name parts were
    never recorded simply opens the line it would have continued.

    `break_first_join` refuses the first join only — the second rung of the name
    ladder, which puts the family name on a line of its own and lets everything
    that shared it follow at the floor.
    """
    lines: list[tuple[list[Run], bool]] = []
    broken = False
    for index in kept:
        candidate = candidates[index]
        mandatory = candidate.tier is Tier.MANDATORY
        joins = bool(candidate.continues_line) and bool(lines)
        if joins and break_first_join and not broken:
            joins = False
            broken = True
        if joins:
            runs, was_mandatory = lines[-1]
            runs.extend(candidate.continues_line)
            runs.extend(candidate.runs)
            lines[-1] = (runs, was_mandatory or mandatory)
        else:
            lines.append(([*candidate.runs], mandatory))
    return tuple(_ComposedLine(runs=tuple(runs), mandatory=mandatory) for runs, mandatory in lines)


def _sizes_for(lines: Sequence[_ComposedLine], scale: TypeScale) -> tuple[int, ...]:
    """The size each composed line is set at before any shrink or growth.

    The leading line takes the identification tier and everything below it sits at
    the floor. **Two tiers rather than three, which is what the calibration
    supports**: the sizes used to be title, artist, everything-else, three judged
    numbers with no stated relationship. Reading them off a scale leaves exactly
    the two readings the operator settled by eye; the rung between them is the
    size that was reported as taking effort to read, so interpolating a middle
    tier would be aiming type at a boundary somebody recorded to avoid.
    """
    return tuple(scale.primary_px if index == 0 else scale.floor_px for index in range(len(lines)))


def _placed(
    lines: tuple[_ComposedLine, ...],
    sizes: tuple[int, ...],
    surface: Geometry,
    measure: Measure,
    scale: TypeScale,
) -> _Placement:
    """Place these lines at these sizes, and notice what it cost.

    **The one place a shrink is detected, derived from the sizes that were
    actually set** rather than reported by whoever asked for them. A caller that
    announced its own shrink could announce the wrong one, and this is the signal
    the whole exception to the type floor is conditional on.
    """
    blocks = _place(lines, sizes, surface, measure)
    return _Placement(
        lines=lines,
        sizes=sizes,
        blocks=blocks,
        shrunk=tuple(block.text for block in blocks if block.size_px < scale.floor_px),
    )


def _place(
    lines: Sequence[_ComposedLine],
    sizes: Sequence[int],
    surface: Geometry,
    measure: Measure,
) -> tuple[Block, ...]:
    """Stack these lines from the top margin down, at the sizes given."""
    blocks: list[Block] = []
    y = surface.margin_px
    for line, size in zip(lines, sizes, strict=True):
        wrap = _wrap_width_for(size, surface)
        extent = measure(line.runs, size, wrap)
        blocks.append(
            Block(
                runs=line.runs,
                size_px=size,
                x_px=surface.margin_px,
                y_px=y,
                width_px=extent.width_px,
                height_px=extent.height_px,
                wrap_px=wrap,
            )
        )
        y += extent.height_px + round(size * LEADING)
    return tuple(blocks)


def _wrap_width_for(size_px: int, surface: Geometry) -> int:
    """How far a line of this size may run before it wraps.

    The narrower of the surface and the measure. **The bound only ever narrows** —
    a device smaller than the measure is a device whose margins still win, and a
    bound that widened a line past them would be drawing outside the surface.
    """
    return min(surface.text_width_px, round(MEASURE_EM * size_px))


def _height_of(blocks: Sequence[Block]) -> int:
    """How far down the surface this stack reaches, measured to its last ink."""
    return blocks[-1].y_px + blocks[-1].height_px if blocks else 0


def _overflows(blocks: Sequence[Block], surface: Geometry) -> bool:
    """Whether the stack runs past the bottom margin.

    Measured to the bottom of the last block rather than by summing heights and
    leading, so the trailing gap below the final line is not counted against the
    fit — a label that is exactly as tall as its surface should fit, and summing
    would reject it for space nothing occupies.
    """
    if not blocks:
        return False
    return _height_of(blocks) > surface.margin_px + surface.text_height_px
