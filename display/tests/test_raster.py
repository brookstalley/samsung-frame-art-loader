"""The one promise the raster type makes, and why it is checked rather than trusted.

A rasterizer works in a surface whose rows are padded out to an alignment
boundary; a device reads a flat buffer. Handing the padded one across puts every
row after the first a few pixels late, and the label arrives sheared. That failure
is invisible on the reference panel — 1448 pixels wide, so the padding is zero —
and appears the day somebody configures a width that is not a multiple of four.
So the type states the guarantee and refuses a buffer that breaks it, rather than
leaving a comment that each implementation is free to overlook.
"""

import pytest

from display.panel.raster import Raster


def test_a_flat_buffer_is_what_the_type_is_for():
    raster = Raster(width_px=3, height_px=2, pixels=bytes(6))

    assert len(raster.pixels) == raster.width_px * raster.height_px


def test_a_padded_buffer_is_refused_at_the_seam_rather_than_drawn_sheared():
    """Three-wide rows padded to four is exactly what a Cairo A8 surface hands
    back, so this is the real mistake and not an invented one."""
    with pytest.raises(ValueError) as raised:
        Raster(width_px=3, height_px=2, pixels=bytes(8))

    assert "padded" in str(raised.value)


def test_a_short_buffer_is_refused_too():
    with pytest.raises(ValueError):
        Raster(width_px=3, height_px=2, pixels=bytes(5))
