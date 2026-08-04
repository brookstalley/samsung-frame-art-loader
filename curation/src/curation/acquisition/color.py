"""Colour arithmetic for mat selection: hex, CIE LAB, and perceptual distance.

**Written here rather than taken from a library, deliberately.** The 2024
implementation reached this through OpenCV, NumPy and scikit-image; those three
land on a memory-capped Pi co-located with the display plane, to do arithmetic
that is thirty lines and fully specified. The dependency list this plane keeps is
argued package by package, and none of them could be argued for this.

**Everything is D65 / sRGB.** That is what a JPEG from a museum is, what a
television shows, and what a model returning "#27285b" means. No colour
management, no ICC profiles: this product composes one flat colour behind a
picture, and a rendering-intent decision would be a claim it cannot support.

The distance function is **CIEDE2000**, not the Euclidean CIE76 that a first
implementation reaches for. It matters here specifically: mats cluster in the
dark, low-chroma corner of the space, and CIE76 disagrees with the eye most
sharply about how far apart two colours in one region are. The number this
returns is read by a person deciding whether a new mat engine regressed against
the corpus, so a metric that overstates a difference costs a real judgement.
"""

from dataclasses import dataclass
from math import atan2, cos, degrees, exp, hypot, radians, sin, sqrt
from typing import Final

#: The D65 white point, the reference sRGB is defined against.
_WHITE_X: Final[float] = 0.95047
_WHITE_Y: Final[float] = 1.00000
_WHITE_Z: Final[float] = 1.08883

#: The CIE standard's own constants, named rather than inlined so the two places
#: they appear cannot drift: 216/24389 is the linear/cubic crossover, 841/108 the
#: linear segment's slope.
_EPSILON: Final[float] = 216 / 24389
_KAPPA_SLOPE: Final[float] = 841 / 108
_KAPPA_OFFSET: Final[float] = 4 / 29


class ColorError(ValueError):
    """A colour could not be read as one."""


@dataclass(frozen=True, slots=True)
class Lab:
    """A colour in CIE LAB, the space mat choices are reasoned in."""

    l: float  # noqa: E741 - L* is the CIE's own name for this axis
    a: float
    b: float


def parse_hex(value: str) -> tuple[int, int, int]:
    """Read a hex triplet as 8-bit sRGB, tolerating what a model actually sends.

    **Lenient on purpose, and the leniency is measured rather than imagined.** A
    probed model returned `3F6F7A` with no leading `#`, and shorthand and
    upper-case both appear. Each of those is unambiguously the colour it looks
    like, and refusing them would send a perfectly good choice to the fallback.

    What it will not do is guess. Anything that is not three or six hex digits
    raises, because a mat engine that quietly substituted a colour for an
    unreadable answer is the invisible-fallback failure this product records
    `method` to prevent.
    """
    text = value.strip().lstrip("#").strip()
    if len(text) == 3:
        # #abc is #aabbcc — the CSS shorthand, and the only expansion there is.
        text = "".join(character * 2 for character in text)
    if len(text) != 6 or any(character not in "0123456789abcdefABCDEF" for character in text):
        raise ColorError(f"{value!r} is not a hex colour triplet like '#27285b'.")
    return tuple(int(text[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]


def format_hex(rgb: tuple[int, int, int]) -> str:
    """An 8-bit sRGB triple as the lower-case `#rrggbb` the catalogue stores.

    Lower-case because `CatalogueService` compares mat colours as strings to
    decide whether a choice is new, and `#27285B` arriving where `#27285b` is
    already in force would write a history row recording that nothing changed.
    """
    red, green, blue = (max(0, min(255, round(channel))) for channel in rgb)
    return f"#{red:02x}{green:02x}{blue:02x}"


def _linearize(channel: float) -> float:
    """One sRGB channel, 0-1, with its transfer function removed."""
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def _delinearize(channel: float) -> float:
    """The inverse: linear light back to an sRGB-encoded channel."""
    return channel * 12.92 if channel <= 0.0031308 else 1.055 * channel ** (1 / 2.4) - 0.055


def _f(ratio: float) -> float:
    return ratio ** (1 / 3) if ratio > _EPSILON else _KAPPA_SLOPE * ratio + _KAPPA_OFFSET


def _f_inverse(value: float) -> float:
    cubed = value**3
    return cubed if cubed > _EPSILON else (value - _KAPPA_OFFSET) / _KAPPA_SLOPE


def rgb_to_lab(rgb: tuple[int, int, int]) -> Lab:
    """8-bit sRGB to CIE LAB."""
    red, green, blue = (_linearize(channel / 255) for channel in rgb)
    x = (0.4124564 * red + 0.3575761 * green + 0.1804375 * blue) / _WHITE_X
    y = (0.2126729 * red + 0.7151522 * green + 0.0721750 * blue) / _WHITE_Y
    z = (0.0193339 * red + 0.1191920 * green + 0.9503041 * blue) / _WHITE_Z
    fx, fy, fz = _f(x), _f(y), _f(z)
    return Lab(l=116 * fy - 16, a=500 * (fx - fy), b=200 * (fy - fz))


def lab_to_rgb(lab: Lab) -> tuple[int, int, int]:
    """CIE LAB back to 8-bit sRGB, clamped into the displayable gamut.

    **Clamping is the honest answer, not a silent one.** LAB describes colours
    sRGB cannot show, and a mat is painted by a television — so a value outside
    the gamut has to become one inside it. The alternative, refusing, would turn a
    model's slightly-out-of-gamut suggestion into a fallback for no reason a
    viewer could see.
    """
    fy = (lab.l + 16) / 116
    fx = fy + lab.a / 500
    fz = fy - lab.b / 200
    x = _f_inverse(fx) * _WHITE_X
    y = _f_inverse(fy) * _WHITE_Y
    z = _f_inverse(fz) * _WHITE_Z
    red = 3.2404542 * x - 1.5371385 * y - 0.4985314 * z
    green = -0.9692660 * x + 1.8760108 * y + 0.0415560 * z
    blue = 0.0556434 * x - 0.2040259 * y + 1.0572252 * z
    return tuple(max(0, min(255, round(_delinearize(max(0.0, min(1.0, channel))) * 255))) for channel in (red, green, blue))  # type: ignore[return-value]


def scale_lightness(rgb: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    """The same hue and chroma at a fraction of the lightness.

    Scaling L* rather than an RGB or HSL brightness is what makes "two thirds as
    light" mean two thirds as light *to a viewer*; the same multiplier applied to
    RGB channels darkens the blues far more than the yellows.
    """
    lab = rgb_to_lab(rgb)
    return lab_to_rgb(Lab(l=max(0.0, lab.l * factor), a=lab.a, b=lab.b))


def delta_e(one: Lab, two: Lab) -> float:
    """CIEDE2000 difference between two colours.

    Roughly: 1 is the threshold of a just-noticeable difference, 2-3 is a
    difference a careful eye finds when looking for it, and above 10 the two are
    plainly different colours.

    The implementation is the CIE's published formulation. It is worth none of it
    being simplified: the hue-rotation term that makes it long is exactly the part
    that corrects the blue region, and mats live there.
    """
    l_bar = (one.l + two.l) / 2
    c_one, c_two = hypot(one.a, one.b), hypot(two.a, two.b)
    c_bar = (c_one + c_two) / 2

    # Weights the a* axis up in the low-chroma region, which is what stops near-
    # neutral greys reading as further apart than they look.
    g = 0.5 * (1 - sqrt(c_bar**7 / (c_bar**7 + 25**7))) if c_bar > 0 else 0.5
    a_one_prime, a_two_prime = (1 + g) * one.a, (1 + g) * two.a
    c_one_prime, c_two_prime = hypot(a_one_prime, one.b), hypot(a_two_prime, two.b)
    c_bar_prime = (c_one_prime + c_two_prime) / 2

    h_one_prime = degrees(atan2(one.b, a_one_prime)) % 360 if (one.b or a_one_prime) else 0.0
    h_two_prime = degrees(atan2(two.b, a_two_prime)) % 360 if (two.b or a_two_prime) else 0.0

    delta_l_prime = two.l - one.l
    delta_c_prime = c_two_prime - c_one_prime

    if c_one_prime * c_two_prime == 0:
        delta_h_prime = 0.0
    elif abs(h_two_prime - h_one_prime) <= 180:
        delta_h_prime = h_two_prime - h_one_prime
    elif h_two_prime - h_one_prime > 180:
        delta_h_prime = h_two_prime - h_one_prime - 360
    else:
        delta_h_prime = h_two_prime - h_one_prime + 360
    delta_h_capital = 2 * sqrt(c_one_prime * c_two_prime) * sin(radians(delta_h_prime) / 2)

    if c_one_prime * c_two_prime == 0:
        h_bar_prime = h_one_prime + h_two_prime
    elif abs(h_one_prime - h_two_prime) <= 180:
        h_bar_prime = (h_one_prime + h_two_prime) / 2
    elif h_one_prime + h_two_prime < 360:
        h_bar_prime = (h_one_prime + h_two_prime + 360) / 2
    else:
        h_bar_prime = (h_one_prime + h_two_prime - 360) / 2

    t = (
        1
        - 0.17 * cos(radians(h_bar_prime - 30))
        + 0.24 * cos(radians(2 * h_bar_prime))
        + 0.32 * cos(radians(3 * h_bar_prime + 6))
        - 0.20 * cos(radians(4 * h_bar_prime - 63))
    )

    s_l = 1 + (0.015 * (l_bar - 50) ** 2) / sqrt(20 + (l_bar - 50) ** 2)
    s_c = 1 + 0.045 * c_bar_prime
    s_h = 1 + 0.015 * c_bar_prime * t

    rotation = -2 * sqrt(c_bar_prime**7 / (c_bar_prime**7 + 25**7)) * sin(radians(60 * exp(-(((h_bar_prime - 275) / 25) ** 2))))

    return sqrt(
        (delta_l_prime / s_l) ** 2
        + (delta_c_prime / s_c) ** 2
        + (delta_h_capital / s_h) ** 2
        + rotation * (delta_c_prime / s_c) * (delta_h_capital / s_h)
    )


def hex_distance(one: str, two: str) -> float:
    """CIEDE2000 between two hex triplets, for comparing a choice to a reference."""
    return delta_e(rgb_to_lab(parse_hex(one)), rgb_to_lab(parse_hex(two)))


__all__ = [
    "ColorError",
    "Lab",
    "delta_e",
    "format_hex",
    "hex_distance",
    "lab_to_rgb",
    "parse_hex",
    "rgb_to_lab",
    "scale_lightness",
]
