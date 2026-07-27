"""Whether a held image is big enough for the wall — the one place that is decided.

The verdict is **derived and never stored.** It was a column once, computed at
acquisition, and that stopped being right the moment panel geometry became a
deployment value: whether an original is adequate depends on the artwork box, the
box depends on the panel and the mat, and this product has to run on whatever
Frame someone owns. A stored verdict is a judgement about one particular
television, and the day the television changes it goes quietly wrong with nothing
to report the drift.

What stays stored is the pair of panel-independent facts — the original's pixel
width and height. Everything else is arithmetic done here, by the single function
both the review grid and the renderer call, so neither grows a resolution policy
of its own.

**The floor is physical, not pixel-counted.** A pixel threshold means different
things on a 42" panel and a 75" one, and megapixels are the wrong metric outright
because canvas occupancy is dominated by aspect-ratio mismatch rather than by
resolution — a tall narrow work legitimately fills little of a 16:9 canvas. So the
floor is a minimum rendered size on the wall in inches, the same unit the mat is
specified in, and it scales with the panel automatically.
"""

from dataclasses import dataclass
from enum import StrEnum

from curation.services.errors import ServiceError


class DisplayFit(StrEnum):
    """How an original will meet the space it is rendered into.

    There is deliberately no `upscaled` value. The pipeline never upscales —
    `image.thumbnail()` never did, and acquisition at gallery resolution is a
    product promise. Upscaling is the one option that actively misrepresents
    quality, turning an honest "this image is small" into an apparent rendering
    fault, so a state with no producer is not reserved for one.
    """

    #: The source is at least as large as the artwork box and is downscaled into it.
    NATIVE = "native"
    #: The source is smaller than the box and is pasted at native size, so the
    #: mat is simply wider. On the real corpus this is the uncommon case and it
    #: is not a defect.
    MATTED_SMALL = "matted_small"
    #: The source would render smaller on the wall than the configured floor.
    #: Not a rejection: the work is shown labelled with the size it would appear
    #: at, and the curator may still choose it.
    BELOW_FLOOR = "below_floor"


@dataclass(frozen=True, slots=True)
class ArtworkBox:
    """The region of the TV canvas an artwork is rendered into, and its scale.

    Constructed by whoever resolves deployment configuration, because every value
    here comes from one: the panel's size, the mat's width in inches, and the
    floor. It arrives already composed rather than as a panel plus a mat width
    because the mat's own geometry — in particular the conservator's weighting of
    the bottom margin heavier than the top — belongs to the code that composes the
    mat, not to the verdict computed from the space it leaves.
    """

    #: The box in canvas pixels.
    width: int
    height: int
    #: How many canvas pixels make an inch on the wall. A 42" 16:9 panel is about
    #: 36.6" wide, so a 3840-pixel canvas runs at roughly 105.
    pixels_per_inch: float
    #: The smallest the rendered work may measure along its long edge, in inches
    #: on the wall.
    floor_inches: float


@dataclass(frozen=True, slots=True)
class FitAssessment:
    """The verdict, and the rendered size it was reached from.

    The size is returned rather than recomputed by the caller because the review
    grid has to say *how* small — "would show at 8.6 inches" — and a second
    implementation of the same scaling arithmetic to answer that is exactly the
    duplication this function exists to prevent.
    """

    fit: DisplayFit
    rendered_width: int
    rendered_height: int
    rendered_long_edge_inches: float


def assess_display_fit(*, width: int, height: int, box: ArtworkBox) -> FitAssessment:
    """Judge an original of `width` x `height` pixels against the space it will fill."""
    if width <= 0 or height <= 0:
        raise ServiceError(f"An image must have a positive width and height, got {width}x{height}.")
    if box.width <= 0 or box.height <= 0 or box.pixels_per_inch <= 0:
        raise ServiceError("The artwork box must have a positive size and scale.")
    if box.floor_inches < 0:
        raise ServiceError(f"The floor cannot be negative, got {box.floor_inches}.")

    # Never above 1: the pipeline downscales to fit and otherwise leaves the
    # image alone, which is what makes "no upscaling" a property of the geometry
    # rather than a rule each renderer has to remember.
    scale = min(box.width / width, box.height / height, 1.0)
    rendered_width = max(1, round(width * scale))
    rendered_height = max(1, round(height * scale))
    long_edge_inches = max(rendered_width, rendered_height) / box.pixels_per_inch

    if long_edge_inches < box.floor_inches:
        fit = DisplayFit.BELOW_FLOOR
    elif scale < 1:
        fit = DisplayFit.NATIVE
    else:
        fit = DisplayFit.MATTED_SMALL

    return FitAssessment(
        fit=fit,
        rendered_width=rendered_width,
        rendered_height=rendered_height,
        rendered_long_edge_inches=long_edge_inches,
    )
