"""How large type has to be, derived from where the reader stands.

**These are the tests that would have caught the defect the module exists for.**
The product shipped a 26 px body size that gives a 2.5 arcminute cap height at the
reference wall's viewing distance, against the 5 arcminutes 20/20 vision needs to
resolve a letter at all — and it passed a hardware probe, a Critic round and a
cutover, because nothing anywhere converted pixels into the angle a person
actually sees. So the assertions here are in arcminutes wherever the claim is
about legibility, and in pixels only where the claim is about arithmetic.
"""

import math

import pytest

from display.panel.legibility import (
    CAP_RATIO,
    COMFORTABLE_CAP_ARCMIN,
    MINIMUM_CAP_ARCMIN,
    TypeScale,
    ViewingConditionsUnknown,
    margin_for,
    pixels_per_arcminute,
    pixels_per_inch,
    type_scale_for,
)

#: The reference wall, and the only place in this file where these numbers are
#: real: a 6-inch 1448×1072 panel read from 7 feet.
REFERENCE = {
    "width_px": 1448,
    "height_px": 1072,
    "diagonal_inches": 6.0,
    "viewing_distance_inches": 84.0,
}


def cap_arcminutes(size_px: float, *, ppi: float, viewing_distance_inches: float) -> float:
    """The angle this type's capitals subtend at the reader's eye.

    **The test's own arithmetic, deliberately not the module's.** Reusing
    `pixels_per_arcminute` here would make every assertion below a restatement of
    the implementation, and the two would agree however wrong they were.
    """
    cap_height_inches = (size_px * CAP_RATIO) / ppi
    return math.degrees(math.atan(cap_height_inches / viewing_distance_inches)) * 60


class TestTheReferenceWall:
    """The calibration, pinned. These four numbers are what the operator settled at
    the panel on 2026-08-11, and a change to any constant that moves them is a
    change to a judgement made by eye rather than a refactor."""

    def test_the_panel_s_resolution_comes_off_its_diagonal_and_its_pixels(self):
        """~300 PPI, which is the figure every measurement in the spec rests on."""
        ppi = pixels_per_inch(width_px=1448, height_px=1072, diagonal_inches=6.0)

        assert ppi == pytest.approx(300.3, abs=0.1)

    def test_an_arcminute_is_about_seven_pixels_at_seven_feet(self):
        ppi = pixels_per_inch(width_px=1448, height_px=1072, diagonal_inches=6.0)

        assert pixels_per_arcminute(ppi=ppi, viewing_distance_inches=84.0) == pytest.approx(7.34, abs=0.01)

    def test_the_two_tiers_land_where_the_operator_put_them(self):
        """130 px read as comfortable at a glance; 92 px as acceptable if a reader
        steps closer. The derivation has to reproduce the ladder it was fitted to,
        or it is describing a different wall than the one that was looked at."""
        scale = type_scale_for(**REFERENCE)

        assert (scale.primary_px, scale.floor_px) == (130, 92)

    def test_the_provisional_sizes_this_replaced_were_below_the_acuity_threshold(self):
        """**The defect, asserted so it cannot come back unnoticed.**

        `BODY_SIZE_PX` was 26. Five arcminutes is the cap height 20/20 vision needs
        to resolve a letter *at all* — not to read it comfortably — so a body size
        under that was not merely small, and no test the product had could say so
        because none of them knew the distance.
        """
        ppi = pixels_per_inch(width_px=1448, height_px=1072, diagonal_inches=6.0)

        retired_body_size = cap_arcminutes(26, ppi=ppi, viewing_distance_inches=84.0)
        assert retired_body_size < 5, "the size this derivation replaced would have been resolvable after all"

        scale = type_scale_for(**REFERENCE)
        assert cap_arcminutes(scale.floor_px, ppi=ppi, viewing_distance_inches=84.0) > 5


class TestWhatTheTiersMean:
    def test_both_tiers_subtend_the_angle_they_were_specified_at(self):
        """The round-trip: pixels back to arcminutes, against the two settled
        readings. This is the assertion that survives a change of panel."""
        scale = type_scale_for(**REFERENCE)
        ppi = pixels_per_inch(width_px=1448, height_px=1072, diagonal_inches=6.0)

        seen = {
            tier: cap_arcminutes(size, ppi=ppi, viewing_distance_inches=84.0)
            for tier, size in (("primary", scale.primary_px), ("floor", scale.floor_px))
        }

        assert seen["primary"] == pytest.approx(COMFORTABLE_CAP_ARCMIN, abs=0.05)
        assert seen["floor"] == pytest.approx(MINIMUM_CAP_ARCMIN, abs=0.05)

    def test_the_floor_is_below_the_primary_tier_and_neither_is_below_acuity(self):
        scale = type_scale_for(**REFERENCE)

        assert scale.floor_px < scale.primary_px

    def test_there_is_no_tier_between_them(self):
        """The rung the operator called "made out with effort" is the squint
        boundary, recorded so nothing aims at it. A third size here would be type
        set at the size that was reported as taking work to read."""
        assert set(vars(TypeScale)["__slots__"]) == {"primary_px", "floor_px"}


class TestGeometryIsAParameter:
    """The norm: nothing may reason about a panel's geometry anywhere but on that
    panel, and the deployment may hold several devices that differ."""

    def test_a_reader_twice_as_far_away_needs_twice_the_type(self):
        """The relationship, not a coincidence of one wall. Visual angle is linear
        in distance, so this is the property that says the conversion is real."""
        near = type_scale_for(**{**REFERENCE, "viewing_distance_inches": 42.0})
        far = type_scale_for(**{**REFERENCE, "viewing_distance_inches": 84.0})

        assert far.primary_px == pytest.approx(near.primary_px * 2, rel=0.01)
        assert far.floor_px == pytest.approx(near.floor_px * 2, rel=0.01)

    def test_a_coarser_panel_of_the_same_size_needs_fewer_pixels_for_the_same_letter(self):
        """Half the pixel count across the same diagonal is half the PPI, so the
        same physical letter is half as many pixels tall. A floor stated in pixels
        would have been silently wrong on this device."""
        fine = type_scale_for(**REFERENCE)
        coarse = type_scale_for(**{**REFERENCE, "width_px": 724, "height_px": 536})

        assert coarse.primary_px == pytest.approx(fine.primary_px / 2, rel=0.02)

    def test_a_large_panel_read_from_across_a_room_gets_its_own_answer(self):
        """A device drawing its label into the mat area around an artwork on a
        32-inch monitor at 10 feet — the second surface the architecture norm
        names, which must get a correct floor with nobody visiting it."""
        scale = type_scale_for(width_px=3840, height_px=2160, diagonal_inches=32.0, viewing_distance_inches=120.0)
        ppi = pixels_per_inch(width_px=3840, height_px=2160, diagonal_inches=32.0)

        assert cap_arcminutes(scale.primary_px, ppi=ppi, viewing_distance_inches=120.0) == pytest.approx(
            COMFORTABLE_CAP_ARCMIN, abs=0.1
        )
        assert scale != type_scale_for(**REFERENCE), "two different devices were given the same type size"


class TestAnUnknownDistanceIsNeverGuessed:
    """**The one thing that must not happen.** A wrong viewing distance gives
    silently illegible type, which is the failure the whole module prevents, and
    it looks like success from every direction."""

    @pytest.mark.parametrize(
        ("missing", "named"),
        [
            ("diagonal_inches", "EPD_PANEL_DIAGONAL_INCHES"),
            ("viewing_distance_inches", "EPD_VIEWING_DISTANCE_INCHES"),
        ],
    )
    def test_an_absent_measurement_raises_and_names_the_key_that_fixes_it(self, missing: str, named: str):
        with pytest.raises(ViewingConditionsUnknown, match=named):
            type_scale_for(**{**REFERENCE, missing: None})

    def test_both_absent_names_both(self):
        with pytest.raises(ViewingConditionsUnknown) as raised:
            type_scale_for(**{**REFERENCE, "diagonal_inches": None, "viewing_distance_inches": None})

        assert "EPD_PANEL_DIAGONAL_INCHES" in str(raised.value)
        assert "EPD_VIEWING_DISTANCE_INCHES" in str(raised.value)

    @pytest.mark.parametrize("unusable", [0, -6.0])
    @pytest.mark.parametrize("field", ["diagonal_inches", "viewing_distance_inches"])
    def test_a_measurement_of_zero_or_less_is_refused_like_an_absent_one(self, field: str, unusable: float):
        """`EPD_VIEWING_DISTANCE_INCHES=` with nothing after it arrives here as a
        zero, and a zero divides or floors to nonsense rather than to a message."""
        with pytest.raises(ViewingConditionsUnknown):
            type_scale_for(**{**REFERENCE, field: unusable})


class TestTheMargin:
    def test_the_border_scales_with_the_largest_type_on_the_label(self):
        """It cannot be picked independently: a border trades directly against how
        many lines survive the drop rule."""
        near = type_scale_for(**{**REFERENCE, "viewing_distance_inches": 42.0})
        far = type_scale_for(**REFERENCE)

        assert margin_for(far) > margin_for(near)

    def test_it_reproduces_the_border_the_panel_work_actually_ran(self):
        """60 px was used at the panel to keep the largest rung of the type ladder
        clear of the bezel. The derivation has to land near it or it is describing
        a label nobody looked at."""
        assert margin_for(type_scale_for(**REFERENCE)) == pytest.approx(60, abs=6)
