"""The colour arithmetic mat selection is reasoned in.

The CIEDE2000 cases are Sharma, Wu and Dalal's published test data (2005), which
exists because the standard's formulation has discontinuities that a plausible
implementation gets wrong — the hue-average and hue-difference wrap-arounds
especially. Their table is the accepted way to prove an implementation is the
CIE's function rather than something that agrees with it on easy pairs.
"""

import pytest

from curation.acquisition.color import (
    ColorError,
    Lab,
    delta_e,
    format_hex,
    hex_distance,
    lab_to_rgb,
    parse_hex,
    rgb_to_lab,
    scale_lightness,
)

#: (lab one, lab two, expected CIEDE2000) from the Sharma et al. reference set.
#: The chosen rows are the ones that discriminate: pairs 1-4 walk a difference
#: across the a* axis, 8-9 sit either side of the 0/360 hue wrap, 15-17 exercise
#: the blue rotation term, and 29-30 the near-neutral case mats occupy.
SHARMA_PAIRS = [
    ((50.0000, 2.6772, -79.7751), (50.0000, 0.0000, -82.7485), 2.0425),
    ((50.0000, 3.1571, -77.2803), (50.0000, 0.0000, -82.7485), 2.8615),
    ((50.0000, 2.8361, -74.0200), (50.0000, 0.0000, -82.7485), 3.4412),
    ((50.0000, -1.3802, -84.2814), (50.0000, 0.0000, -82.7485), 1.0000),
    ((50.0000, -1.1848, -84.8006), (50.0000, 0.0000, -82.7485), 1.0000),
    ((50.0000, -0.9009, -85.5211), (50.0000, 0.0000, -82.7485), 1.0000),
    ((50.0000, 0.0000, 0.0000), (50.0000, -1.0000, 2.0000), 2.3669),
    ((50.0000, -1.0000, 2.0000), (50.0000, 0.0000, 0.0000), 2.3669),
    ((50.0000, 2.4900, -0.0010), (50.0000, -2.4900, 0.0009), 7.1792),
    ((50.0000, 2.4900, -0.0010), (50.0000, -2.4900, 0.0011), 7.2195),
    ((50.0000, 2.4900, -0.0010), (50.0000, -2.4900, 0.0012), 7.2195),
    ((50.0000, -0.0010, 2.4900), (50.0000, 0.0009, -2.4900), 4.8045),
    ((50.0000, -0.0010, 2.4900), (50.0000, 0.0011, -2.4900), 4.7461),
    ((50.0000, 2.5000, 0.0000), (50.0000, 0.0000, -2.5000), 4.3065),
    ((50.0000, 2.5000, 0.0000), (73.0000, 25.0000, -18.0000), 27.1492),
    ((50.0000, 2.5000, 0.0000), (61.0000, -5.0000, 29.0000), 22.8977),
    ((50.0000, 2.5000, 0.0000), (56.0000, -27.0000, -3.0000), 31.9030),
    ((50.0000, 2.5000, 0.0000), (58.0000, 24.0000, 15.0000), 19.4535),
    ((50.0000, 2.5000, 0.0000), (50.0000, 3.1736, 0.5854), 1.0000),
    ((50.0000, 2.5000, 0.0000), (50.0000, 3.2972, 0.0000), 1.0000),
    ((50.0000, 2.5000, 0.0000), (50.0000, 1.8634, 0.5757), 1.0000),
    ((50.0000, 2.5000, 0.0000), (50.0000, 3.2592, 0.3350), 1.0000),
    ((60.2574, -34.0099, 36.2677), (60.4626, -34.1751, 39.4387), 1.2644),
    ((63.0109, -31.0961, -5.8663), (62.8187, -29.7946, -4.0864), 1.2630),
    ((61.2901, 3.7196, -5.3901), (61.4292, 2.2480, -4.9620), 1.8731),
    ((35.0831, -44.1164, 3.7933), (35.0232, -40.0716, 1.5901), 1.8645),
    ((22.7233, 20.0904, -46.6940), (23.0331, 14.9730, -42.5619), 2.0373),
    ((36.4612, 47.8580, 18.3852), (36.2715, 50.5065, 21.2231), 1.4146),
    ((90.8027, -2.0831, 1.4410), (91.1528, -1.6435, 0.0447), 1.4441),
    ((90.9257, -0.5406, -0.9208), (88.6381, -0.8985, -0.7239), 1.5381),
    # The two darkest rows in the set. They matter disproportionately here: mats
    # live near the bottom of the L* axis, and this is where a naive
    # implementation's lightness weighting goes wrong.
    ((6.7747, -0.2908, -2.4247), (5.8714, -0.0985, -2.2286), 0.6377),
    ((2.0776, 0.0795, -1.1350), (0.9033, -0.0636, -0.5514), 0.9082),
]


@pytest.mark.parametrize(("one", "two", "expected"), SHARMA_PAIRS)
def test_ciede2000_matches_the_published_reference_pairs(one, two, expected):
    """The standard's own discriminating cases, to four decimal places."""
    assert delta_e(Lab(*one), Lab(*two)) == pytest.approx(expected, abs=1e-4)


def test_delta_e_is_zero_for_a_colour_against_itself():
    lab = rgb_to_lab((39, 40, 91))
    assert delta_e(lab, lab) == pytest.approx(0.0, abs=1e-12)


def test_delta_e_is_symmetric():
    """Not guaranteed by the formula's shape — the hue average is order-dependent
    in a way a careless implementation gets wrong, and an asymmetric distance
    would make a corpus report depend on which column was written first."""
    one, two = rgb_to_lab((39, 40, 91)), rgb_to_lab((110, 72, 72))
    assert delta_e(one, two) == pytest.approx(delta_e(two, one), abs=1e-12)


def test_white_is_lightness_one_hundred_and_neutral():
    lab = rgb_to_lab((255, 255, 255))
    assert lab.l == pytest.approx(100.0, abs=1e-3)
    assert lab.a == pytest.approx(0.0, abs=1e-3)
    assert lab.b == pytest.approx(0.0, abs=1e-3)


def test_black_is_lightness_zero():
    lab = rgb_to_lab((0, 0, 0))
    assert lab.l == pytest.approx(0.0, abs=1e-9)


def test_mid_grey_is_neutral_but_not_half_lightness():
    """L* is perceptual, so 50% signal is not 50 lightness — a check that the
    transfer function is actually applied rather than the channels used raw."""
    lab = rgb_to_lab((128, 128, 128))
    assert lab.a == pytest.approx(0.0, abs=1e-3)
    assert lab.b == pytest.approx(0.0, abs=1e-3)
    assert 53 < lab.l < 54


@pytest.mark.parametrize("rgb", [(0, 0, 0), (255, 255, 255), (39, 40, 91), (110, 72, 72), (1, 2, 3), (254, 200, 7)])
def test_lab_round_trips_back_to_the_same_bytes(rgb):
    """Every colour a mat can be survives the trip, so darkening one cannot
    introduce a drift that accumulates over repeated regeneration."""
    assert lab_to_rgb(rgb_to_lab(rgb)) == rgb


@pytest.mark.parametrize("lab", [Lab(l=100, a=120, b=-120), Lab(l=50, a=-128, b=127), Lab(l=140, a=0, b=0), Lab(l=-20, a=0, b=0)])
def test_out_of_gamut_lab_clamps_to_paintable_bytes_rather_than_raising(lab):
    """A model may answer with a colour sRGB cannot show, and a television has to
    paint something — so the requirement is that every channel comes back
    paintable, not that it lands on any particular substitute. The exact bytes
    are a consequence of clamping linear light, which is arithmetic rather than a
    decision, so pinning them would be testing the implementation."""
    assert all(0 <= channel <= 255 for channel in lab_to_rgb(lab))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("#27285b", (39, 40, 91)),
        ("#27285B", (39, 40, 91)),
        ("27285b", (39, 40, 91)),
        ("  #27285b  ", (39, 40, 91)),
        ("#abc", (170, 187, 204)),
        ("abc", (170, 187, 204)),
    ],
)
def test_parse_hex_accepts_the_forms_a_model_actually_sends(text, expected):
    """The bare form is not hypothetical: a probed model returned `3F6F7A`."""
    assert parse_hex(text) == expected


@pytest.mark.parametrize("text", ["", "#", "#12345", "#1234567", "rebeccapurple", "#gggggg", "#27285z", "12 34 56"])
def test_parse_hex_refuses_what_it_cannot_read_rather_than_guessing(text):
    """A substituted colour is the invisible fallback `method` exists to prevent."""
    with pytest.raises(ColorError):
        parse_hex(text)


def test_format_hex_is_lower_case():
    """`CatalogueService` compares mat colours as strings to decide whether a
    choice is new, so an upper-case duplicate would write a history row
    recording that nothing changed."""
    assert format_hex((39, 40, 91)) == "#27285b"


def test_format_hex_clamps_out_of_range_channels():
    assert format_hex((-5, 260, 128)) == "#00ff80"


def test_scale_lightness_darkens_without_moving_the_hue():
    original = (110, 72, 72)
    darker = scale_lightness(original, 0.66)
    before, after = rgb_to_lab(original), rgb_to_lab(darker)
    assert after.l < before.l
    assert after.l == pytest.approx(before.l * 0.66, abs=0.5)
    # Chroma is preserved, so darkening does not quietly turn a colour grey.
    assert after.a == pytest.approx(before.a, abs=1.0)
    assert after.b == pytest.approx(before.b, abs=1.0)


@pytest.mark.parametrize("factor", [-0.5, -2.0, -1e6])
@pytest.mark.parametrize("rgb", [(10, 10, 10), (200, 120, 60), (255, 255, 255)])
def test_a_negative_factor_floors_at_zero_lightness_rather_than_going_below_it(rgb, factor):
    """A negative L* is not a colour, and this is a public function — the mat
    engine calls it with a fixed constant, but nothing in the signature says a
    caller must.

    **A zero factor does not exercise the floor**, and a test using only zero left
    it undefended: `0.0 * L*` is already zero, so the clamp is a no-op there and
    deleting it changes nothing a test could see. A mutation sweep found exactly
    that. Negative factors are what reach it.

    The floor is zero *lightness*, not the colour black. Chroma is preserved by
    design — that is what stops darkening turning a colour grey — so a chromatic
    input floors at the darkest paintable colour of its own hue, which is not
    `(0, 0, 0)`. Asserting black here would be asserting that this function
    discards hue, which the test above proves it must not.
    """
    floored = scale_lightness(rgb, factor)

    assert rgb_to_lab(floored).l == pytest.approx(rgb_to_lab(scale_lightness(rgb, 0.0)).l, abs=1e-9)
    assert rgb_to_lab(floored).l < 8


def test_hex_distance_reads_the_corpus_pair_it_will_be_used_on():
    """Two real corpus mats, far enough apart that any sane metric says so."""
    assert hex_distance("#27285b", "#6b6b6b") > 10
    assert hex_distance("#27285b", "#27285b") == pytest.approx(0.0, abs=1e-12)
