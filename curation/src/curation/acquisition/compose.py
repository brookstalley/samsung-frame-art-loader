"""Composing a work onto the television canvas: the mat, the picture, the floor.

The geometry is not this module's to invent. `Settings.tv_artwork_box` already
computes the space a work is rendered into, from the panel's own dimensions and
the mat in inches, and `assess_display_fit` already judges an original against
it. This module draws what those two decided, which is what stops a third answer
to "how big is the mat" existing.

**No upscaling, ever.** A source smaller than the artwork box is pasted at its
own size and the mat is simply wider. That is not a degraded path: it is what the
2024 pipeline did through `image.thumbnail()`, which never enlarged, and
acquisition at gallery resolution is a product promise. Upscaling is the one
option that actively misrepresents quality, converting an honest "this image is
small" into an apparent rendering fault.

**Below the floor is rendered, not refused.** A work whose original would appear
smaller on the wall than the configured minimum still composes — the floor's job
is to inform a curator's choice, and it does that in the review grid, before this
point. A renderer that second-guessed it would suppress a picture the curator
explicitly asked for.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from PIL import Image, ImageOps

from curation.acquisition.color import parse_hex
from curation.services.display_fit import ArtworkBox, DisplayFit, assess_display_fit

log = logging.getLogger(__name__)

#: What the composed canvas is encoded as. JPEG at high quality: the television
#: reads it, the file is regenerable from the original at any time, and a
#: lossless format would multiply the size of the one tree that is deliberately
#: not backed up.
_FORMAT: Final[str] = "JPEG"
_QUALITY: Final[int] = 95


@dataclass(frozen=True, slots=True)
class Composition:
    """A composed canvas and the facts a caller records about it.

    The rendered size and the fit come back because the caller reports them and
    recomputing them from the file would be a second implementation of the
    scaling arithmetic this module exists to hold once.
    """

    path: Path
    canvas_width: int
    canvas_height: int
    #: The size the artwork itself occupies inside the mat, in canvas pixels.
    rendered_width: int
    rendered_height: int
    #: Where the artwork's top-left corner sits on the canvas, in pixels.
    #:
    #: **Reported because it is the mat's geometry, and the mat is the product.**
    #: The margins are `artwork_left` on the left, `artwork_top` above, and the
    #: rest below — which is the bottom-weighting the whole arrangement exists to
    #: produce. Recovering it from the encoded file instead means hunting for the
    #: first pixel that differs from the mat colour, and JPEG rings at exactly
    #: that boundary, so the one number a reader most wants is the one the file
    #: answers least reliably.
    artwork_left: int
    artwork_top: int
    #: How the original met the space, for a caller that reports it.
    fit: DisplayFit
    #: How large the work appears on the wall along its long edge, in inches.
    rendered_long_edge_inches: float


def compose(
    source: Path,
    *,
    destination: Path,
    mat_hex: str,
    panel_width: int,
    panel_height: int,
    box: ArtworkBox,
) -> Composition:
    """Draw `source` centred in a mat of `mat_hex` on a `panel_width` x `panel_height` canvas.

    **The artwork is not centred on the canvas — it is centred in the artwork
    box**, and the box already sits higher than centre because its bottom margin
    is the deeper one. A true-centred picture reads as sitting low, which is the
    conservator's convention `MAT_BOTTOM_WEIGHT` encodes; centring on the canvas
    here would undo it silently while every arithmetic test still passed.

    The staging is the same rule acquisition follows and for the same reason: a
    regeneration that fails partway must cost the work the image it is currently
    displaying nothing. The file at `destination` is replaced only once a whole
    canvas has been written.
    """
    if panel_width <= 0 or panel_height <= 0:
        raise ValueError(f"The panel must have a positive size, got {panel_width}x{panel_height}.")
    # Parsed before the image is opened: an unreadable colour is a caller's
    # error, and finding it after decoding a gigapixel master wastes the decode.
    mat_rgb = parse_hex(mat_hex)

    with Image.open(source) as image:
        image.draft("RGB", (panel_width, panel_height))
        upright = ImageOps.exif_transpose(image) or image
        # CMYK and greyscale scans both appear in museum downloads, and a mat
        # painted in RGB cannot be pasted onto without a common mode.
        artwork = upright.convert("RGB")
        assessment = assess_display_fit(width=artwork.width, height=artwork.height, box=box)
        # `thumbnail` fits inside the box and never enlarges, so "no upscaling"
        # is a property of the operation rather than a rule to remember. A source
        # already smaller than the box passes through untouched.
        artwork.thumbnail((box.width, box.height), Image.Resampling.LANCZOS)

        canvas = Image.new("RGB", (panel_width, panel_height), mat_rgb)
        # **The margins are recovered from the box, never recomputed from the
        # configured weight.** `tv_artwork_box` builds the box as
        # `width = panel_width - 2 * mat` and `height = panel_height - mat -
        # bottom`, so half the width the box leaves *is* the mat — exactly, in the
        # whole pixels it was rounded to. Deriving it a second time from inches
        # and a weight would be a separate answer to a question already settled,
        # free to disagree by the pixel or two that rounding order moves it.
        side_mat = (panel_width - box.width) // 2
        # Whatever is left below is the deeper bottom margin, and it is deeper
        # because the box is shorter than a four-equal-sides mat would leave. The
        # weighting therefore arrives here as geometry rather than as a rule this
        # module has to remember to apply.
        top = side_mat + (box.height - artwork.height) // 2
        left = side_mat + (box.width - artwork.width) // 2
        canvas.paste(artwork, (left, top))

        rendered_width, rendered_height = artwork.size

    destination.parent.mkdir(parents=True, exist_ok=True)
    staged = destination.with_name(f"{destination.name}.composing")
    try:
        canvas.save(staged, format=_FORMAT, quality=_QUALITY, optimize=True)
        staged.replace(destination)
    except OSError:
        staged.unlink(missing_ok=True)
        raise

    log.info(
        "composed %s at %sx%s in a %s mat (%s, %.1f inches on the wall)",
        destination.name,
        rendered_width,
        rendered_height,
        mat_hex,
        assessment.fit.value,
        assessment.rendered_long_edge_inches,
    )
    return Composition(
        path=destination,
        canvas_width=panel_width,
        canvas_height=panel_height,
        rendered_width=rendered_width,
        rendered_height=rendered_height,
        artwork_left=left,
        artwork_top=top,
        fit=assessment.fit,
        rendered_long_edge_inches=assessment.rendered_long_edge_inches,
    )


__all__ = ["Composition", "compose"]
