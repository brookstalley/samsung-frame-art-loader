"""Constraint 12: the resolution verdict is derived, in one place, and never stored.

The geometry used here is the reference deployment worked out in the
non-functional requirements: a 42" 16:9 panel is about 36.6" wide, so a
3840-pixel canvas runs at roughly 105 pixels to the inch; a 2.5" mat takes 262
pixels off each side, leaving an artwork box of 3316 x 1597; and a 12" floor puts
the threshold at about 1260 pixels along the long edge.

The numbers are written out rather than computed so that a change to the
arithmetic has to face them.
"""

import pytest

from curation.services.display_fit import ArtworkBox, DisplayFit, assess_display_fit
from curation.services.errors import ServiceError

#: The reference 42" deployment.
_FORTY_TWO_INCH = ArtworkBox(width=3316, height=1597, pixels_per_inch=105.0, floor_inches=12.0)

#: The same product on a 75" panel: a wider wall spreads the same canvas over
#: more inches, so each pixel is physically larger.
_SEVENTY_FIVE_INCH = ArtworkBox(width=3546, height=1723, pixels_per_inch=58.7, floor_inches=12.0)


def test_a_gallery_resolution_source_is_downscaled_into_the_box():
    assessment = assess_display_fit(width=10000, height=7000, box=_FORTY_TWO_INCH)

    assert assessment.fit is DisplayFit.NATIVE
    assert assessment.rendered_width <= _FORTY_TWO_INCH.width
    assert assessment.rendered_height <= _FORTY_TWO_INCH.height


def test_a_source_smaller_than_the_box_is_pasted_at_native_size():
    """The mat is simply wider. On the real corpus this is uncommon and fine."""
    assessment = assess_display_fit(width=2000, height=1300, box=_FORTY_TWO_INCH)

    assert assessment.fit is DisplayFit.MATTED_SMALL
    assert (assessment.rendered_width, assessment.rendered_height) == (2000, 1300)


def test_the_pipeline_never_upscales():
    """`image.thumbnail()` never did, and acquisition at gallery resolution is a promise.

    Upscaling is the one option that misrepresents quality, turning an honest
    "this image is small" into an apparent rendering fault.
    """
    assessment = assess_display_fit(width=900, height=600, box=_FORTY_TWO_INCH)

    assert (assessment.rendered_width, assessment.rendered_height) == (900, 600)


def test_a_source_that_exactly_fills_the_box_is_native_not_matted_small():
    """The equality boundary, pinned from both sides.

    Nothing is downscaled at exactly the box size, but nothing is *smaller* than
    the box either, and the mat that results is the configured one rather than a
    wider one. Reporting a deficiency that is not there would put a warning on the
    review card for the best possible acquisition.
    """
    exact = assess_display_fit(width=3316, height=1597, box=_FORTY_TWO_INCH)
    assert exact.fit is DisplayFit.NATIVE
    assert (exact.rendered_width, exact.rendered_height) == (3316, 1597)

    # One pixel short in either direction and the mat really does grow.
    assert assess_display_fit(width=3315, height=1597, box=_FORTY_TWO_INCH).fit is DisplayFit.MATTED_SMALL
    assert assess_display_fit(width=3316, height=1596, box=_FORTY_TWO_INCH).fit is DisplayFit.MATTED_SMALL


def test_a_downscaled_source_is_native_even_where_the_mat_grows():
    """Aspect-ratio residue is not a resolution deficiency.

    This source is wider than the box and shorter than it, so it downscales and
    still leaves vertical space. That space is the shape of the work, not a
    shortage of pixels, which is exactly why occupancy is the wrong metric.
    """
    assert assess_display_fit(width=4000, height=1000, box=_FORTY_TWO_INCH).fit is DisplayFit.NATIVE


def test_a_small_web_image_lands_below_the_floor():
    assessment = assess_display_fit(width=800, height=600, box=_FORTY_TWO_INCH)

    assert assessment.fit is DisplayFit.BELOW_FLOOR


def test_the_verdict_carries_the_size_the_work_would_show_at():
    """The review grid says "would show at 8.6 inches", so the number has to come from here.

    Recomputing it in the grid would be a second implementation of the same
    scaling arithmetic, which is exactly what one derivation exists to prevent.
    """
    assessment = assess_display_fit(width=903, height=600, box=_FORTY_TWO_INCH)

    assert assessment.rendered_long_edge_inches == pytest.approx(8.6, abs=0.05)


def test_a_work_exactly_at_the_floor_is_not_below_it():
    assessment = assess_display_fit(width=1260, height=900, box=_FORTY_TWO_INCH)

    assert assessment.fit is DisplayFit.MATTED_SMALL
    assert assessment.rendered_long_edge_inches == pytest.approx(12.0, abs=0.01)


def test_one_pixel_under_the_floor_is_below_it():
    assert assess_display_fit(width=1259, height=900, box=_FORTY_TWO_INCH).fit is DisplayFit.BELOW_FLOOR


def test_the_same_image_clears_the_floor_on_a_larger_panel():
    """A pixel threshold would mean different things on a 42" and a 75".

    That is why the floor is physical: the same 800-pixel edge is 7.6 inches on
    the reference panel and 13.6 on a 75", and only one of those is too small to
    hang.
    """
    assert assess_display_fit(width=800, height=600, box=_FORTY_TWO_INCH).fit is DisplayFit.BELOW_FLOOR
    assert assess_display_fit(width=800, height=600, box=_SEVENTY_FIVE_INCH).fit is DisplayFit.MATTED_SMALL


def test_a_tall_narrow_work_is_judged_on_its_long_edge_not_on_canvas_occupancy():
    """Occupancy is dominated by aspect-ratio mismatch, which is not a resolution fault.

    This work fills under a tenth of the canvas's width and is still a perfectly
    good acquisition.
    """
    assessment = assess_display_fit(width=1000, height=5000, box=_FORTY_TWO_INCH)

    assert assessment.fit is DisplayFit.NATIVE
    assert assessment.rendered_width < _FORTY_TWO_INCH.width // 10


def test_there_is_no_upscaled_verdict():
    """A declared state with no producer is a defect, so the value is absent rather than reserved."""
    assert {member.value for member in DisplayFit} == {"native", "matted_small", "below_floor"}


@pytest.mark.parametrize(("width", "height"), [(0, 100), (100, 0), (-1, 100)])
def test_an_image_with_no_pixels_cannot_be_judged(width, height):
    with pytest.raises(ServiceError, match="positive width and height"):
        assess_display_fit(width=width, height=height, box=_FORTY_TWO_INCH)


def test_a_box_with_no_size_or_no_scale_cannot_judge_anything():
    with pytest.raises(ServiceError, match="positive size and scale"):
        assess_display_fit(width=100, height=100, box=ArtworkBox(width=0, height=10, pixels_per_inch=105.0, floor_inches=12.0))
    with pytest.raises(ServiceError, match="positive size and scale"):
        assess_display_fit(width=100, height=100, box=ArtworkBox(width=10, height=10, pixels_per_inch=0.0, floor_inches=12.0))


def test_a_negative_floor_is_refused():
    with pytest.raises(ServiceError, match="floor cannot be negative"):
        assess_display_fit(width=100, height=100, box=ArtworkBox(width=10, height=10, pixels_per_inch=105.0, floor_inches=-1.0))
