"""The typesetter: Pango and Cairo, measuring and drawing the label's text.

**Isolated in its own module because it is the one part of this plane that needs
something a default install does not provide.** Pango arrives through PyGObject,
in the optional `raster` group: a device with a television and no panel installs
neither it nor the driver. The layout tier above was split out so the judgement
about legibility could be written and tested without any of that, leaving only
this file needing the real text stack. Nothing else in `display` imports it — the
composition root names it, and a device that has no panel never touches it.

**Why Pango rather than a simpler drawing library.** This product's corpus comes
from museum APIs: titles and artists' names arrive in whatever script the
institution records them in, and a single font does not cover them. Pango resolves
a face **per glyph** through fontconfig, so a Japanese title beside a French one
gets both rendered instead of one of them coming out as a row of empty boxes. A
library that binds one font file per draw call cannot do that, and the failure is
exactly the kind this product's accessibility posture exists to prevent
(`design_decisions.accessibility_approach`) — silent, and visible only to the
person trying to read the label.

**Text is set literally, never as markup.** `Pango.Layout.set_text` rather than
`set_markup`, which is the fix for a defect the 2024 label had by construction: it
interpolated museum-supplied description text into a markup string, so a title
containing `<` produced either mangled type or a parse failure (`data-model.md`).
The metadata tier deliberately does not escape, on the grounds that knowing one
renderer's markup is this tier's business — and this tier's answer is to use none.

**Which is also how the styling arrives: attributes over byte ranges, not tags.**
The family name is set bold and the title italic, and the obvious way to say so —
wrapping the run in `<b>` — would reintroduce exactly the defect above on exactly
the surface it was fixed for, because the text either side of that tag is still
museum-supplied. So the runs stay literal and a `Pango.AttrList` says which bytes
are heavy. The one thing to know about that API is that `AttrList.insert` copies:
an attribute whose range is set after it is inserted keeps the range it had, in
the list, silently.
"""

import gi

gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")

import cairo  # noqa: E402 -- gi.require_version must run before the repository import below
from gi.repository import Pango, PangoCairo  # noqa: E402 -- and ruff cannot see that ordering constraint

from display.panel.layout import Extent, Layout, Measure  # noqa: E402 -- same ordering constraint
from display.panel.raster import Raster, Rasterizer  # noqa: E402 -- same ordering constraint
from display.panel.styling import Line, Run, Slant, Weight, byte_spans, set_text  # noqa: E402 -- same ordering constraint

#: The font family, as fontconfig resolves it. **A generic alias rather than a
#: named face, and that is the accessibility decision**: `Sans` lets fontconfig
#: pick a covering face per script, so a Devanagari or Han title renders instead
#: of arriving as empty boxes. Naming a specific file would pin the Latin
#: appearance and silently drop every corpus work outside its coverage.
FONT_FAMILY: str = "Sans"


class PangoRasterizer(Rasterizer):
    """Measures and draws with Pango over a Cairo surface.

    Holds no surface of its own between calls: each `render` allocates the one it
    draws into and each measurement uses a scratch context. A panel changes at
    most once per rotation interval — 180 seconds in the reference deployment —
    so keeping a 1448×1072 buffer alive between them would trade real memory on a
    Pi for an allocation nobody can perceive.
    """

    def __init__(self, *, font_family: str = FONT_FAMILY) -> None:
        self._font_family = font_family

    @property
    def measure(self) -> Measure:
        return self._measure

    def _measure(self, line: Line, size_px: int, wrap_px: int) -> Extent:
        """How much room this line takes, as this rasterizer will actually draw it.

        Measured against a one-pixel scratch surface: Pango's extents come from the
        font metrics and the wrap width, not from the surface it would be drawn
        onto, so allocating a full-size one here would cost a megabyte per line
        measured and change no answer.

        **Styled, because the styling is what makes it wide.** This goes through
        the same `_layout_for` the drawing does rather than measuring the plain
        characters: bold capitals are appreciably wider than the letters they
        replace, and a measurement taken without them would under-report the one
        line the label leads with — on the panel, where the whole drop rule is
        driven by measured height.
        """
        layout = self._layout_for(cairo.Context(cairo.ImageSurface(cairo.FORMAT_A8, 1, 1)), line, size_px, wrap_px)
        width_px, height_px = layout.get_pixel_size()
        return Extent(width_px=width_px, height_px=height_px, rows=layout.get_line_count())

    def render(self, layout: Layout) -> Raster:
        """Draw the whole label — white ground, black type — at the layout's own size."""
        surface_geometry = layout.surface
        surface = cairo.ImageSurface(cairo.FORMAT_A8, surface_geometry.width_px, surface_geometry.height_px)
        context = cairo.Context(surface)

        for block in layout.blocks:
            # `block.wrap_px`, never the surface width: the block was measured at
            # its own bound, and wrapping differently here would draw a line the
            # layout tier never placed.
            text = self._layout_for(context, block.runs, block.size_px, block.wrap_px)
            context.move_to(block.x_px, block.y_px)
            # A8 carries coverage and no colour, so this paints "how much ink is
            # here" rather than a shade. Which end of the scale that means is
            # settled once, below, where the buffer is inverted.
            context.set_source_rgba(0, 0, 0, 1)
            PangoCairo.show_layout(context, text)

        surface.flush()
        return Raster(
            width_px=surface_geometry.width_px,
            height_px=surface_geometry.height_px,
            pixels=_greyscale(surface),
        )

    def _layout_for(self, context: cairo.Context, line: Line, size_px: int, wrap_px: int) -> Pango.Layout:
        """One configured Pango layout: literal text, styled runs, absolute size, wrapped."""
        pango_layout = PangoCairo.create_layout(context)
        # Literal, never markup — see the module docstring. `-1` is Pango's "the
        # string is NUL-terminated, measure it yourself".
        pango_layout.set_text(set_text(line), -1)
        pango_layout.set_attributes(_attributes(line))

        font = Pango.FontDescription()
        font.set_family(self._font_family)
        # **Absolute, not `set_size`.** `set_size` takes points and resolves through
        # a DPI this product never sets, so the pixel height it produced would
        # depend on an ambient setting rather than on the number the layout tier
        # chose. Every size in that tier is in pixels because the legibility
        # judgement is about pixels on a specific panel.
        font.set_absolute_size(size_px * Pango.SCALE)
        pango_layout.set_font_description(font)

        pango_layout.set_width(max(0, wrap_px) * Pango.SCALE)
        # `WORD_CHAR`, not `WORD`: a museum record can carry an unbroken run with
        # no space in it — a URL, a German compound, an accession string — and
        # under `WORD` that run is drawn past the right margin and off the panel.
        # Breaking mid-word is ugly; running off the edge is unreadable.
        pango_layout.set_wrap(Pango.WrapMode.WORD_CHAR)
        return pango_layout


def _attributes(line: Line) -> Pango.AttrList:
    """Which bytes of this line are heavy, and which are slanted.

    **Every range comes from `byte_spans`, which counts bytes and not
    characters** — Pango's indices are byte offsets into the UTF-8 the layout was
    set with, and this corpus is full of text where the two differ: an en dash in
    a life-date spends three bytes, a Japanese title spends three per glyph. A
    character offset puts the bold part-way through a name and nothing raises.

    **The range is set before the attribute is inserted, and that order is
    load-bearing.** `AttrList.insert` copies what it is given, so an attribute
    mutated afterwards keeps its old range in the list while the Python object
    reports the new one — a disagreement that is invisible from the calling side
    and shows up only as the wrong word in bold.

    An unstyled line contributes nothing and gets an empty list rather than
    `None`, so there is one path through here rather than two.
    """
    attributes = Pango.AttrList()
    for span in byte_spans(line):
        for attribute in _attributes_for(span.run):
            attribute.start_index = span.start_byte
            attribute.end_index = span.end_byte
            attributes.insert(attribute)
    return attributes


def _attributes_for(run: Run) -> list[Pango.Attribute]:
    """The Pango attributes one run's styling asks for, rangeless as yet.

    Case is absent on purpose: it is applied to the characters by `set_text`
    rather than requested of the renderer, because Pango can transform case only
    from 1.50 and `str.upper` does the same job with no version floor
    (`styling.py`).
    """
    attributes: list[Pango.Attribute] = []
    if run.weight is Weight.BOLD:
        attributes.append(Pango.attr_weight_new(Pango.Weight.BOLD))
    if run.slant is Slant.ITALIC:
        attributes.append(Pango.attr_style_new(Pango.Style.ITALIC))
    return attributes


def _greyscale(surface: cairo.ImageSurface) -> bytes:
    """The surface's coverage, as unpadded greyscale with white for ground.

    **Two conversions, and both are load-bearing.**

    *Stride.* Cairo pads each row out to an alignment boundary, so its buffer is
    `stride * height` rather than `width * height`. Handing that through unchanged
    puts every row after the first a few pixels late and the label arrives sheared
    — which happens to be invisible at the panel's own 1448 pixels, where the
    padding is zero, and appears the moment somebody configures a width that is
    not a multiple of four. Sliced here so that never depends on the geometry.

    *Sense.* `FORMAT_A8` stores coverage: 0 where nothing was drawn, 255 under
    solid type. Greyscale reads the other way round — 0 is black. So the byte is
    inverted, which turns "no ink" into white ground and full coverage into black
    type, and carries the antialiased edges across as the intermediate greys that
    are the whole reason this panel is driven in `gray16` rather than 1-bit.
    """
    width = surface.get_width()
    stride = surface.get_stride()
    data = bytes(surface.get_data())
    rows = (data[row * stride : row * stride + width] for row in range(surface.get_height()))
    return bytes(255 - coverage for row in rows for coverage in row)
