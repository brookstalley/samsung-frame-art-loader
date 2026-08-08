"""The typesetter: Pango and Cairo, measuring and drawing the label's text.

**Isolated in its own module because it is the one part of this plane that will
not import on every developer's machine.** Pango arrives through PyGObject, whose
Homebrew toolchain on macOS builds and then fails at import; the layout tier above
was split out precisely so the judgement about legibility could be written and
tested anywhere, leaving only this file needing the real text stack. Nothing else
in `display` imports it — the composition root names it, and a device that has no
panel never touches it.

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
"""

import gi

gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")

import cairo  # noqa: E402 -- gi.require_version must run before the repository import below
from gi.repository import Pango, PangoCairo  # noqa: E402 -- and ruff cannot see that ordering constraint

from display.panel.layout import Extent, Layout, Measure  # noqa: E402 -- same ordering constraint
from display.panel.raster import Raster, Rasterizer  # noqa: E402 -- same ordering constraint

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

    def _measure(self, text: str, size_px: int, wrap_px: int) -> Extent:
        """How much room this text takes, as this rasterizer will actually draw it.

        Measured against a one-pixel scratch surface: Pango's extents come from the
        font metrics and the wrap width, not from the surface it would be drawn
        onto, so allocating a full-size one here would cost a megabyte per line
        measured and change no answer.
        """
        layout = self._layout_for(cairo.Context(cairo.ImageSurface(cairo.FORMAT_A8, 1, 1)), text, size_px, wrap_px)
        width_px, height_px = layout.get_pixel_size()
        return Extent(width_px=width_px, height_px=height_px)

    def render(self, layout: Layout) -> Raster:
        """Draw the whole label — white ground, black type — at the layout's own size."""
        surface_geometry = layout.surface
        surface = cairo.ImageSurface(cairo.FORMAT_A8, surface_geometry.width_px, surface_geometry.height_px)
        context = cairo.Context(surface)

        for block in layout.blocks:
            text = self._layout_for(context, block.text, block.size_px, surface_geometry.text_width_px)
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

    def _layout_for(self, context: cairo.Context, text: str, size_px: int, wrap_px: int) -> Pango.Layout:
        """One configured Pango layout: literal text, absolute size, wrapped to width."""
        pango_layout = PangoCairo.create_layout(context)
        # Literal, never markup — see the module docstring. `-1` is Pango's "the
        # string is NUL-terminated, measure it yourself".
        pango_layout.set_text(text, -1)

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
