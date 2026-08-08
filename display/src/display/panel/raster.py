"""Turning a laid-out label into pixels, without knowing what will show them.

The third tier's first half. `surface.py` says what a label can be *put onto*;
this says what a label *looks like*, and the two are separate because a
deployment may pair one answer with several of the other. The e-paper panel and a
monitor drawing into the mat area around the artwork want the same typesetting
and different delivery (`architecture.md` § Direction), so the typesetter is its
own object that a device is handed rather than something each device grows.

**The pixels are eight-bit greyscale and nothing more.** No image library appears
in this module's interface, which is what lets a device choose its own — the
e-paper driver wants a PIL image, and a device that painted into a framebuffer or
an X window would want neither. Handing over the bytes leaves that choice where
the device is, and it costs one conversion in the one implementation that needs
one.

**Measuring and drawing come from the same object on purpose.** The layout tier
breaks lines against measured extents, so a label measured by one rasterizer and
drawn by another is a label whose line breaks are wrong — invisible in every test
that does not look at the pixels, and visible to anyone standing in front of the
panel. Keeping both on one object makes that pairing impossible to get wrong
rather than merely documented.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from display.panel.layout import Layout, Measure


@dataclass(frozen=True, slots=True)
class Raster:
    """A rendered label, as eight-bit greyscale pixels.

    Row-major, one byte per pixel, **exactly `width_px * height_px` bytes with no
    row padding**. Rasterizers routinely work in surfaces whose rows are padded
    out to an alignment boundary, and handing that buffer over unchanged is the
    classic way a label arrives on a panel sheared diagonally: every row after the
    first starts a few pixels late. Stripping the padding is the producer's job
    because only the producer knows its stride, so this type states the guarantee
    rather than leaving each consumer to ask.

    **0 is black and 255 is white**, matching how every greyscale imaging library
    reads a buffer of this shape. The panel this was written for shows 16 levels
    rather than 256, and quantising to them is the driver's business — a
    rasterizer that pre-quantised would be encoding one device's depth into a type
    that other devices share.
    """

    width_px: int
    height_px: int
    pixels: bytes

    def __post_init__(self) -> None:
        # Checked rather than trusted, because the failure it catches is silent:
        # a buffer that is a few bytes short still draws, just wrongly, and the
        # only symptom is a label that looks subtly skewed to a person standing
        # in front of it. Cheap here, unfindable later.
        expected = self.width_px * self.height_px
        if len(self.pixels) != expected:
            raise ValueError(
                f"a {self.width_px}x{self.height_px} raster needs {expected} bytes of greyscale, "
                f"got {len(self.pixels)} — a rasterizer is passing its surface's padded rows through"
            )


class Rasterizer(ABC):
    """Something that measures text and draws it, in one object.

    An abstract base rather than a structural protocol, matching `LabelSurface`
    and `TvClient` and for the same reason: the test double subclasses it, so a
    verb added here fails the double loudly at import instead of leaving it
    quietly behind.
    """

    @property
    @abstractmethod
    def measure(self) -> Measure:
        """How this rasterizer measures text, for the layout tier to arrange with.

        The same object that draws, because line breaking depends on the real face
        at the real size and a layout measured against different metrics than it
        is drawn with breaks its lines in the wrong places.
        """

    @abstractmethod
    def render(self, layout: Layout) -> Raster:
        """Draw this label onto a fresh surface the size of `layout.surface`.

        The whole surface every time, background included — there is no partial
        anything here. A caller gets a complete picture of what the label should
        look like, and a device that can only replace its whole display (which is
        every e-paper panel) needs exactly that.

        Raises nothing device-specific: a rasterizer talks to a text stack, not to
        hardware, so its failures are programming errors rather than the
        operational ones `SurfaceUnavailable` exists for.
        """
