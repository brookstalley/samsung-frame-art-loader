"""The one downscale this product does, so its two callers cannot drift apart.

Thumbnails and inline previews want the same twelve lines — open, decode at a
reduced scale, respect EXIF rotation, flatten to RGB, resample, encode JPEG — and
differ only in the numbers they pass and what they do when it fails. Those
differences are real and stay with the callers. The decode is not, and keeping two
copies of it is how one acquires a fix the other does not: the copies had already
diverged on which exceptions they name, so the caller that missed one leaked it to
an HTTP 500 and stranded a temp file on the way out.

**Nothing here decides policy.** No size, no quality, no failure posture, no
caching. It raises what Pillow raises and lets each caller name the exceptions it
means to answer for — a thumbnail's absence is an error the API reports, a
preview's is a picture that simply does not travel, and flattening those into one
behaviour here would make the wrong one right somewhere.
"""

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Final

from PIL import Image, ImageOps

#: JPEG, always. Both callers produce something a client renders immediately
#: rather than an archival copy, and the source is already whatever the museum
#: served — re-encoding to a second format would cost a decision nobody needs.
_FORMAT: Final[str] = "JPEG"


@dataclass(frozen=True, slots=True)
class EncodedFrame:
    """A downscaled image and the size it actually came out at.

    The dimensions are the *encoded* ones, not the ones asked for: `thumbnail`
    preserves aspect ratio and never enlarges, so a 300 px source asked to fit 400
    stays 300. Callers report these to a client, so reporting the request instead
    would describe a picture nobody received.
    """

    data: bytes
    width: int
    height: int


def encode_downscaled(source: Path, *, max_edge: int, quality: int) -> EncodedFrame:
    """Decode `source`, fit it inside `max_edge`, and return it as JPEG bytes.

    Raises whatever Pillow raises — `UnidentifiedImageError` for a file that is
    not an image, `OSError` for a truncated one, `Image.DecompressionBombError`
    for one engineered to exhaust memory, and `ValueError` from `convert` for at
    least one mode (`La`, premultiplied greyscale alpha). Callers catch what they
    mean to answer for.
    """
    with Image.open(source) as image:
        # Decodes at a reduced DCT scale — up to eight times smaller per axis —
        # so a 47-megapixel master never becomes a 47-megapixel bitmap in memory
        # on its way to a few hundred pixels. A no-op for formats without it.
        image.draft("RGB", (max_edge, max_edge))
        upright = ImageOps.exif_transpose(image) or image
        # CMYK and greyscale scans both appear in museum downloads, and neither
        # saves as a JPEG every client renders the same way.
        frame = upright.convert("RGB")
        frame.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
        buffer = BytesIO()
        frame.save(buffer, format=_FORMAT, quality=quality, optimize=True)
        width, height = frame.size
    return EncodedFrame(data=buffer.getvalue(), width=width, height=height)


def measure(source: Path) -> tuple[int, int]:
    """The size an image would display at, without decoding it.

    Reads the header rather than the pixels, so asking a gigapixel master how
    large it is costs no memory — which matters because acquisition asks this of
    every image it writes, on the smallest machine in the deployment.

    **EXIF orientation is applied**, so a portrait photograph stored as a rotated
    landscape reports portrait dimensions. The catalogue's width and height feed
    the display-fit verdict and the mat geometry, both of which are judgements
    about the picture as a viewer sees it; reporting the stored orientation would
    make a work that renders tall get judged as though it were wide.

    Raises whatever Pillow raises for a file that is not a readable image, on the
    same terms as `encode_downscaled` above.
    """
    with Image.open(source) as image:
        width, height = image.size
        # `exif_transpose` would decode; the orientation tag alone answers the
        # question, and values 5 through 8 are the four that transpose the axes.
        orientation = image.getexif().get(0x0112)
        if orientation in (5, 6, 7, 8):
            width, height = height, width
    return width, height
