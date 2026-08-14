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
from dataclasses import dataclass, replace
from typing import Final

from display.panel.content import Candidate, Tier
from display.panel.legibility import TypeScale
from display.panel.styling import Line, Run, plain

#: Space between one block and the next, as a fraction of the block's own size.
#: Proportional rather than absolute, so the whole label rescales coherently with
#: the scale it is laid out against — which now varies per device.
LEADING: Final[float] = 0.35

#: Space between a line and its own continuation, as a fraction of the same size.
#:
#: **Tighter than `LEADING` because the two lines are one fact.** The name ladder
#: breaks `FAMILY, Given` across two lines, and at the ordinary leading the gap
#: inside the name was identical to the gap between the name and the biography —
#: 198 px against 198 px on the reference panel — so the eye had nothing to tell
#: it which two lines belonged together. Read at the wall on 2026-08-14.
#:
#: **Stated as continuation rather than as a name**, for the reason `LEADING`
#: itself is proportional: today only the ladder produces a continuation, and a
#: constant named for the one case that exists is a constant the next case has to
#: be added to rather than covered by.
CONTINUATION_LEADING: Final[float] = 0.28

#: How much larger than the identification tier a family name is set when the
#: ladder has given it a line of its own.
#:
#: **A third size, above both tiers rather than between them**, which is why it
#: does not contradict the calibration the other two are read off: the rung the
#: operator recorded as taking effort to read lies between the floor and the
#: primary tier, and nothing here aims at it. It spends slack the panel already
#: has on the fact the operator ranked above all others.
#:
#: **Fixed rather than fitted, and the operator named the reason**: a family name
#: scaled to fill its line would set the *shortest* names largest, so `LI` would
#: be half the height of the panel. A fixed multiple emphasises without making
#: emphasis a function of how short somebody's name happens to be.
FAMILY_EMPHASIS: Final[float] = 1.2

#: The most the fill pass may stretch a label's gaps to reach the bottom margin.
#:
#: **A bound rather than a preference, and the sparse label is what needs it.** A
#: record carrying two facts on a panel sized for six has hundreds of pixels of
#: slack and a single gap to spend them in; unbounded, the fill would set the two
#: halves of a tombstone at opposite edges of the panel and call it even spacing.
#: Past roughly twice its natural leading a gap stops reading as space between
#: lines of one label and starts reading as two labels.
#:
#: **Judged rather than derived**, unlike the sizes: nothing about viewing
#: distance says where a gap stops binding two lines together. It is the number
#: most likely to want a nudge at a panel sitting.
FILL_CAP: Final[float] = 2.0

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
    #: How many rows the line breaker produced. **Reported rather than inferred**,
    #: because the thing that laid the rows out is the only one that knows: a
    #: caller working it out from the height would need a single-row height it can
    #: only get by measuring again, at a width wide enough not to wrap — which is
    #: a width past the surface's own margins, and nothing here may ask for one.
    #: More than one row means the line breaker split the line where nobody chose
    #: to, which the name ladder exists to prevent.
    rows: int = 1


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
    #: How many rows the line breaker produced for this block, as the measurer
    #: reported them. One is the ordinary case; more means the line was split
    #: where nothing chose to split it.
    rows: int = 1

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
    #: legible size, in the order they read on the label. Empty is the normal
    #: case. **Reading order is not priority order** — that is this label's whole
    #: thesis — and on the surface with no usable area at all, where every fact is
    #: reported, the mandatory title lands after the optional facts above it.
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
    #: Lines the line breaker had to split across rows — which for the leading
    #: line means a name broken where nothing chose to break it.
    #:
    #: **Reported for the same reason `shrunk` is, and it was found the same
    #: way.** The 2026-08-13 panel sitting read `KATSUSHIKA,` / `Hokusai,
    #: Japanese` / `1760–1849` off the wall: every fact split mid-phrase, the
    #: comma that inverts the name stranded at the end of a row. Nothing reported
    #: it — the type was at its tier so `shrunk` was empty, every fact was placed
    #: so `dropped` was empty, and the journal said the label had been drawn. The
    #: name ladder exists to prevent exactly this, and the ladder cannot always
    #: win: on a surface where no rung fits, a wrapped name still beats giving up
    #: the size of the family name. When that is the trade taken, this is what
    #: says so.
    #:
    #: **The blocks rather than their text, because the report needs more than the
    #: words.** The journal names the row count and the width the line was broken
    #: at, and taking those from `blocks[0]` while the text came from here was a
    #: second source for one fact: once the ladder has broken the name, the line
    #: that wrapped is not the first one, and the two disagreed silently.
    wrapped: tuple[Block, ...] = ()
    #: What every gap between lines was multiplied by to fill the panel — 1.0 when
    #: there was nothing to spend, `FILL_CAP` at most.
    #:
    #: **Reported because a gap on the panel is no longer predictable from the
    #: constants alone.** `LEADING` and `CONTINUATION_LEADING` are the ratio the
    #: gaps stand in; this is what that ratio was scaled by, and the operator's
    #: instrument prints both so a reading at the wall can be checked against the
    #: source rather than reverse-engineered from pixel positions.
    fill: float = 1.0
    #: The height the label occupies at its natural leading, before the fill spends
    #: any slack — margin to the bottom of the last line.
    #:
    #: **What says how full the panel actually is**, which `fill` alone cannot: a
    #: multiplier of 2.0 is the cap being hit and means the label is sparse, but it
    #: does not say by how much. Together they are the whole account of the
    #: vertical, and the preview prints both.
    natural_height_px: int = 0

    @property
    def is_empty(self) -> bool:
        """Whether this would put nothing on the surface.

        **The daemon branches on this together with `dropped`**, and the pair is
        what tells the two blank frames apart: a work whose institution published
        no label text lays out to nothing and that is right, while facts that
        existed and were not placed is the accessibility surface failing
        completely. Anything that changes what produces an empty layout has to
        go and look at that warning.
        """
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
    set below the name and admitted before the biography line beneath it.

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

    # **A label that had to shrink is offered the same fill as any other, and
    # that is deliberate.** There was a `if not placed.shrunk` guard here, on the
    # reasoning that a surface too small for the artist's name has no slack for a
    # medium and that adding a fact can only make an arrangement taller. The
    # second half is false: a fact admitted onto the leading line can take the
    # identification tier away from it (`_sizes_for`), and a whole label at the
    # floor can be *shorter* than one line at 12.4′. So the trial can succeed —
    # and when it does it is strictly the better label, since `_arrange` only ever
    # admits at the derived sizes, which means the shrink is gone and the content
    # is greater. Guarding that out would have preferred illegible type to legible
    # type on the grounds of a rule about slack.
    for index, candidate in enumerate(candidates):
        if candidate.tier is Tier.MANDATORY:
            continue
        trial = tuple(sorted((*kept, index)))
        attempt = _arrange(candidates, trial, surface, measure, scale)
        if attempt is not None and attempt.name_wrapped and not placed.name_wrapped:
            # **`_arrange` returning a wrapped-but-fitting arrangement means
            # opposite things to its two callers, and this is the one it must not
            # mean it to.** For the mandatory pass, a wrapped name beats giving up
            # the family name's size, so `_arrange` prefers it to returning
            # nothing. Here, `None` means "leave this fact off" — so accepting the
            # same arrangement would say a medium is worth breaking a name for,
            # which inverts the ratified ordering (`accessibility-spec.md`, the
            # name block gives up its line as soon as keeping it would break the
            # name across rows). Admitting a fact may never introduce a wrap.
            continue
        if attempt is None:
            # **Tried rather than abandoned**, so a one-word date is not lost to a
            # three-line medium that was merely earlier in the list. The facts
            # differ in size as well as in rank, and the journal reports every one
            # that came off either way.
            continue
        kept, placed = trial, attempt
    placed = _grow_into_the_slack(placed, surface, measure, scale)
    blocks, fill, natural = _fill_the_panel(placed.blocks, surface)

    return Layout(
        surface=surface,
        blocks=blocks,
        dropped=tuple(c.text for index, c in enumerate(candidates) if index not in kept),
        shrunk=placed.shrunk,
        # Every line of the name that broke, in the order they are set. A title or
        # a medium wrapping is ordinary — that is what the measure is for — while a
        # line of the *name* wrapping is a fact broken where nothing chose to break
        # it. The ladder spreads a name over two lines, so reporting only the first
        # would stay silent on a given name the measure split beneath an intact
        # family name.
        wrapped=tuple(blocks[index] for index in placed.wrapped_name_lines),
        fill=fill,
        natural_height_px=natural,
    )


def _fill_the_panel(blocks: tuple[Block, ...], surface: Geometry) -> tuple[tuple[Block, ...], float, int]:
    """Spend the leftover height on the gaps, and centre what the cap will not take.

    **The last pass, and the only one that moves a line without deciding
    anything** (`accessibility-spec.md` § Amended 2026-08-14: the label fills the
    panel it was given). Everything above has settled which facts are set and at
    what sizes; this changes where they sit and nothing else, which is why it can
    run unconditionally — it cannot drop a fact, cause a shrink, or wrap a line.

    **A multiplier over the gaps rather than a constant added to each.** The gaps
    stand in a tuned ratio — tighter inside a broken name than between two facts —
    and adding a flat amount to every gap would flatten that ratio toward one.
    Scaling preserves it exactly.

    **Capped, because a sparse label has more slack than gaps to spend it in.** Two
    facts on a panel sized for six would otherwise be set at opposite edges and
    called even spacing. Whatever the cap leaves over is split above and below, so
    the top and bottom margins match in every case rather than only where the
    arithmetic happens to land.
    """
    if not blocks:
        return blocks, 1.0, 0
    gaps = [blocks[i].y_px - (blocks[i - 1].y_px + blocks[i - 1].height_px) for i in range(1, len(blocks))]
    bottom = blocks[-1].y_px + blocks[-1].height_px
    # Measured before anything moves: `_place` stacks from the top margin down, so
    # this is the height the label wants at its own leading.
    natural = bottom - surface.margin_px
    slack = (surface.margin_px + surface.text_height_px) - bottom
    if slack <= 0:
        # A label that filled its surface, or overflowed one too small for it.
        # There is nothing to spend and nothing to centre.
        return blocks, 1.0, natural

    total = sum(gaps)
    fill = min(FILL_CAP, (total + slack) / total) if total > 0 else 1.0
    # **Floored, not rounded, and that is a correctness choice rather than a
    # taste.** `sum(gap * fill)` is exactly `total + slack`, so rounding each gap
    # to nearest can overshoot the budget by up to half a pixel per gap and push
    # the last line past the bottom margin — measured at a 40×10 surface, which
    # ended 1 px outside. Flooring can only ever undershoot, and what it leaves
    # over is precisely what the residual is for.
    stretched = [int(gap * fill) for gap in gaps]
    # What the cap, the flooring, or a label with no gaps at all would not take.
    residual = slack - (sum(stretched) - total)

    placed: list[Block] = []
    y = surface.margin_px + residual // 2
    for index, block in enumerate(blocks):
        if index:
            y += stretched[index - 1]
        placed.append(replace(block, y_px=y))
        y += block.height_px
    return tuple(placed), fill, natural


@dataclass(frozen=True, slots=True)
class _ComposedLine:
    """One line of the label before it has a size or a position."""

    runs: Line
    #: Whether any fact on this line is one the label may not drop. A line is
    #: mandatory if *any* of it is: the identification line carries a family name
    #: may also carry the given name, and the name is what decides its fate.
    mandatory: bool
    #: Whether *every* fact on this line identifies the work — which is a
    #: different question from the one above, and asking the one above in its
    #: place is what let optional facts reach the identification tier.
    #:
    #: **Survival and size are decided by opposite quantifiers.** A line holding
    #: one fact that may not be dropped must survive whole, because there is no
    #: way to drop half a line. A line holding one fact that does *not* identify
    #: the work must not be set at the identification tier, because at that size
    #: it claims the work is identified by a medium or a date — the two-distance
    #: label read backwards. On the name ladder's second rung this is exactly the
    #: tail: `Hokusai, Japanese, 1760–1849` may not be dropped, and is not the
    #: name.
    wholly_identifying: bool
    #: Whether any fact on this line is part of the maker's name — the same
    #: quantifier as `mandatory`, and for the same reason: the family name and the
    #: given name share a line, and the name is what decides its fate.
    #:
    #: **A third question rather than a rephrasing of the two above.** A record
    #: with no maker composes a leading line — its title — that is both mandatory
    #: and wholly identifying and is not a name, so neither of the others can
    #: stand in for this one.
    carries_the_name: bool
    #: Whether this line is the rest of the fact on the line above it, rather than
    #: the next fact. Set only by the name ladder's break today, and consulted for
    #: two independent decisions: the tighter leading that binds a broken name
    #: together, and whether the line above it is a family name holding its own
    #: line and so takes the emphasis.
    #:
    #: **A property of the line below rather than a flag on the line above**,
    #: because that is where both readers need it — leading is applied before a
    #: line, and the emphasis question is "does anything continue me".
    continues_the_line_above: bool = False


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

    @property
    def wrapped_name_lines(self) -> tuple[int, ...]:
        """Which of the placed lines carry the name and were split across rows.

        **Every line the name occupies, not just the first**, because the ladder's
        whole purpose is to spread a name over two of them: once it has broken
        `FAMILY` / `Given`, a given name too wide for the measure wraps on line
        *one*, and a check that looked only at line zero would call that label
        clean. That is the same fault the 2026-08-13 sitting found — a fact split
        where nothing chose to split it — one rung further down the ladder, and
        the arrangement that produces it is accepted on height alone.
        """
        return tuple(index for index, block in enumerate(self.blocks) if self.lines[index].carries_the_name and block.rows > 1)

    @property
    def name_wrapped(self) -> bool:
        """Whether the line that identifies the work was split across rows.

        **Carried as a property rather than a flag because it is derived**, and a
        flag would be a second place the same fact lives. Two callers ask it and
        they want opposite things from the answer: `lay_out`'s optional-admission
        loop refuses to buy a fact with it, and the report says so when nothing
        could avoid it.

        **Gated on the leading line actually carrying the name**, which is what
        makes this about the name rather than about wrapping. The ladder exists
        for names and only names, so reaching here means no arrangement of one
        fitted; a line with no name in it had no ladder to take, and its wrapping
        is the measure working.

        **Undroppability is the near-miss, and it was the first shape of this.**
        Gating on `mandatory` reads as the same question, because the name is
        always mandatory — but so is the title, so a record with no maker reported
        its wrapping title as a name too narrow to set. That fires the warning on
        an ordinary label, which is how a warning stops being read, and this one
        is load-bearing beyond its own report (`observability-strategy.md`).

        **Asked of every line the name occupies, not the leading one.** The ladder
        exists to spread a name across two lines, so a check that looked only at
        the first would go quiet on exactly the arrangement taken to avoid a break.
        """
        return bool(self.wrapped_name_lines)


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

    **Three rungs, tried in order, each only when the one above it fails.** The
    name block gives up its line before it gives up its size, and the family name
    gives up nothing until the given name has given up everything — which is the
    ordering the operator stated at the panel: the name above all, and the family
    name most important of all.

    1. `FAMILY, Given` on one line at the identification tier.
    2. Broken — `FAMILY` / `Given` — with **both** at the identification tier. The
       given name is name, and setting it at the floor presents it as biography.
    3. Broken, with the given name at the floor. Rung 2 costs a second full-size
       line box, which a narrow surface cannot always pay for; this is what it
       gives up before anything shrinks.

    Below all three is `_shrink_to_fit`, which is where size finally goes.

    **A joined name that merely *fits* is not enough — it must also not have
    wrapped.** A wrapped one costs the rows the ladder would have spent
    deliberately and spends them in the wrong places: `KATSUSHIKA,` /
    `Hokusai, Japanese` splits facts mid-phrase and strands the comma that inverts
    the name at the end of a row, where the weight that distinguishes it from a
    list separator cannot do that work. Read at the wall on 2026-08-13, that was
    the arrangement on the panel.
    """
    joined_lines, _ = _compose(candidates, kept, break_first_join=False)
    joined = _placed(joined_lines, _sizes_for(joined_lines, scale), surface, measure, scale)
    joined_fits = not _overflows(joined.blocks, surface)
    if joined_fits and not (joined.blocks and joined.blocks[0].rows > 1):
        return joined

    broken_lines, broke = _compose(candidates, kept, break_first_join=True)
    if broke:
        for identifying_lines in (2, 1):
            placement = _placed(
                broken_lines,
                _sizes_for(broken_lines, scale, identifying_lines=identifying_lines),
                surface,
                measure,
                scale,
            )
            if not _overflows(placement.blocks, surface):
                return placement
    # A wrapped name that fits still beats giving up size, which is what returning
    # nothing spends next.
    return joined if joined_fits else None


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
        _shrink_one_arrangement(_compose(candidates, kept, break_first_join=broken)[0], surface, measure, scale)
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
    """The largest this arrangement can be set and still fit.

    At the identification tier for the leading line only: by the time size is
    being given up, the given name has already given up its tier at rung three.
    """
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

    **This does not re-ask whether a promotion broke the name, and `lay_out`'s
    optional-admission loop does.** The two paths answer the same question
    differently on purpose only insofar as they cannot disagree: growth promotes a
    line to `primary_px`, which widens its text against a wrap bound that does not
    move, so in principle it could split a line admission would have refused to
    buy. It is left unguarded because the name is already at that tier by
    *allocation* — `_sizes_for` hands the identification tier to the name's lines
    before any optional fact is admitted — so there is no name line for this loop
    to promote. Searched for rather than assumed: some seventy-eight thousand
    surface-and-name combinations produced no case where growth alone turned a
    whole name into a broken one. A guard here would be a branch no test could
    reach; if the allocation rule ever changes, this is the paragraph that says
    what that change costs.
    """
    for index, line in enumerate(placed.lines):
        if index == 0:
            continue
        # **Every one of these is a `break` rather than a `continue`**, because
        # each says the same thing: the line above this one is not at the
        # identification tier. Promoting past it would set a lower line larger
        # than a higher one, which reads as a hierarchy nobody chose — and it is
        # reachable, since a leading line that identifies nothing stays at the
        # floor (see `_sizes_for`).
        #
        # **`wholly_identifying`, not `mandatory`**, and the two differ on exactly
        # the line beneath the name: the biography may not be dropped as a whole
        # when the name is on the same line, and it does not identify the work.
        # Asking whether a line may be *dropped* would promote a demonym and a
        # pair of life dates to the size reserved for identifying the work. Since
        # 2026-08-13 the biography has its own line, so the two questions differ
        # here rather than on the ladder's tail — the tail is the given name now,
        # and it is wholly identifying, which is why it *is* promoted.
        # **`<`, not `!=`.** The guard asks whether promoting this line would set
        # it larger than the line above; since 2026-08-14 a family name holding its
        # own line is set *above* the identification tier, and an equality test
        # would read that emphasis as a reason to stop — silently pinning every
        # line beneath a broken name to the floor.
        if not line.wholly_identifying or placed.sizes[index - 1] < scale.primary_px:
            break
        grown = (*placed.sizes[:index], scale.primary_px, *placed.sizes[index + 1 :])
        candidate_placement = _placed(placed.lines, grown, surface, measure, scale)
        if _overflows(candidate_placement.blocks, surface):
            break
        placed = candidate_placement
    return placed


def _compose(
    candidates: tuple[Candidate, ...],
    kept: tuple[int, ...],
    *,
    break_first_join: bool,
) -> tuple[tuple[_ComposedLine, ...], bool]:
    """Join the admitted facts into lines, in reading order, and say whether it broke one.

    A fact starts a line unless it carries a separator *and* there is a line under
    construction to join. That second condition is what keeps an anonymous work's
    label from opening with a stray comma: a nationality whose name parts were
    never recorded simply opens the line it would have continued.

    `break_first_join` refuses the first join only — the second rung of the name
    ladder, which puts the family name on a line of its own and the given name
    beneath it, both at the identification tier.

    **Whether a break actually happened is returned rather than assumed from the
    argument**, because asking for one does not produce one: a record with a
    single name part has no first join to refuse, and the two arrangements come
    out identical. A caller that took the argument for the answer would hand the
    identification tier to whatever line happened to be second — the biography, or
    the work's own title.
    """
    lines: list[tuple[list[Run], bool, bool, bool, bool]] = []
    broken = False
    for index in kept:
        candidate = candidates[index]
        mandatory = candidate.tier is Tier.MANDATORY
        joins = bool(candidate.continues_line) and bool(lines)
        continues = False
        if joins and break_first_join and not broken:
            joins = False
            broken = True
            # The line about to be started is the rest of the line above it — it
            # would have joined, and only the ladder refused it.
            continues = True
        if joins:
            runs, was_mandatory, was_wholly, was_name, was_continuation = lines[-1]
            runs.extend(candidate.continues_line)
            runs.extend(candidate.runs)
            # **`or` for two of them, `and` for the other, and the asymmetry is
            # the point.** One fact that may not be dropped commits the whole line
            # to surviving, and one fact that is part of the name makes the line
            # the name's; but one fact that does not identify the work
            # disqualifies the whole line from claiming that it does.
            lines[-1] = (
                runs,
                was_mandatory or mandatory,
                was_wholly and mandatory,
                was_name or candidate.names_the_maker,
                was_continuation,
            )
        else:
            lines.append(([*candidate.runs], mandatory, mandatory, candidate.names_the_maker, continues))
    return (
        tuple(
            _ComposedLine(
                runs=tuple(runs),
                mandatory=mandatory,
                wholly_identifying=wholly,
                carries_the_name=is_name,
                continues_the_line_above=continues,
            )
            for runs, mandatory, wholly, is_name, continues in lines
        ),
        broken,
    )


def _sizes_for(lines: Sequence[_ComposedLine], scale: TypeScale, *, identifying_lines: int = 1) -> tuple[int, ...]:
    """The size each composed line is set at before any shrink or growth.

    **`identifying_lines` is how much of the top the name occupies**, which is one
    line ordinarily and two once the ladder has broken it. It is an allocation
    rather than a promotion: the given name takes the identification tier before
    any optional fact is admitted, so the room for it is competed for by the drop
    rule rather than left over by it. Leaving it to `_grow_into_the_slack` was the
    first shape of this and it read wrong at the panel — a medium, or a pair of
    life dates that happened to fit first, kept a person's given name at the floor.

    The leading line takes the identification tier and everything below it sits at
    the floor. **Two tiers rather than three, which is what the calibration
    supports**: the sizes used to be title, artist, everything-else, three judged
    numbers with no stated relationship. Reading them off a scale leaves exactly
    the two readings the operator settled by eye; the rung between them is the
    size that was reported as taking effort to read, so interpolating a middle
    tier would be aiming type at a boundary somebody recorded to avoid.

    **The identification tier is withheld when nothing on the leading line
    identifies the work**, which is the one place this module sizes by tier rather
    than by position — and it has to. A record with no name at all puts its
    nationality on the leading line and its title beneath (`metadata.py` composes
    the identification block whether or not a name reached it), so sizing by
    position alone set a demonym at 12.4′ over a work's own title at the floor:
    an optional fact claiming to identify the work, which is the two-distance
    label read backwards. Such a label is simply set small throughout. It is the
    honest answer — nothing here is the token a passer-by scans — and it is not a
    comfortable one; see `accessibility-spec.md` § The label's content model for
    the ordering question it leaves open.
    """
    if not lines or not lines[0].mandatory:
        return tuple(scale.floor_px for _ in lines)
    sizes = [scale.primary_px if index < identifying_lines else scale.floor_px for index in range(len(lines))]
    if _family_name_holds_its_own_line(lines, identifying_lines):
        sizes[0] = round(scale.primary_px * FAMILY_EMPHASIS)
    return tuple(sizes)


def _family_name_holds_its_own_line(lines: Sequence[_ComposedLine], identifying_lines: int) -> bool:
    """Whether the leading line is a family name the ladder gave a line of its own.

    **Rung 2 and only rung 2** (`accessibility-spec.md` § Amended 2026-08-14). Rung
    3 reaches the same arrangement by *demoting* the given name, which it does
    precisely because the surface could not pay for two full-size line boxes —
    emphasising the family name there would spend room the rung had just
    established there is none of. `identifying_lines` is what tells the two apart.

    The shrink path is excluded by the same reasoning and by construction: it calls
    `_sizes_for` at the default single identifying line.
    """
    return identifying_lines >= 2 and len(lines) > 1 and lines[1].continues_the_line_above


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
    previous_size = 0
    for line, size in zip(lines, sizes, strict=True):
        if blocks:
            # **The two gaps are charged to different lines, and the asymmetry is
            # the point.** Ordinary leading trails a fact that has ended, so it
            # scales with what just ended. A continuation gap sits *inside* one
            # fact, and charging it to the line above would make it grow with the
            # family name's emphasis — so emphasising the name would buy distance
            # between its halves, which is exactly what this gap exists to remove.
            # Measured at the panel on 2026-08-14: charged upward, a 20% tighter
            # fraction over a 20% larger size moved the whitespace by 2 px.
            if line.continues_the_line_above:
                y += round(size * CONTINUATION_LEADING)
            else:
                y += round(previous_size * LEADING)
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
                rows=extent.rows,
            )
        )
        y += extent.height_px
        previous_size = size
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
