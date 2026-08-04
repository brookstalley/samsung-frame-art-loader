"""Drawing a work into its mat on the television canvas.

The geometry asserted here is `nonfunctional-requirements.md`'s own worked
example for the reference 42" panel — 262 px of mat at the top and sides, 301 at
the bottom, a 3316 x 1597 artwork box. `test_config.py` proves `tv_artwork_box`
computes that box; this proves the compositor *draws* it, which is a separate
claim: the box could be right in every arithmetic test while the picture is
pasted in the middle of the canvas, undoing the bottom weighting with nothing to
report it.
"""

import pytest
from PIL import Image

from curation.acquisition.color import ColorError
from curation.acquisition.compose import compose
from curation.services.display_fit import ArtworkBox, DisplayFit

#: The reference 42" 4K Frame, as `nonfunctional-requirements.md` works it out.
PANEL_WIDTH = 3840
PANEL_HEIGHT = 2160
SIDE_MAT = 262
BOTTOM_MAT = 301
REFERENCE_BOX = ArtworkBox(width=3316, height=1597, pixels_per_inch=104.87, floor_inches=12.0)

MAT_HEX = "#27285b"
MAT_RGB = (39, 40, 91)


def _source(tmp_path, width, height, colour=(220, 30, 30), name="work.jpg"):
    path = tmp_path / name
    Image.new("RGB", (width, height), colour).save(path, format="JPEG", quality=95)
    return path


def _composed(tmp_path, source, *, box=REFERENCE_BOX, mat_hex=MAT_HEX):
    destination = tmp_path / "ready" / "work.jpg"
    result = compose(
        source,
        destination=destination,
        mat_hex=mat_hex,
        panel_width=PANEL_WIDTH,
        panel_height=PANEL_HEIGHT,
        box=box,
    )
    return result, Image.open(destination)


def _is_mat(pixel, *, tolerance: int = 12) -> bool:
    """Whether a sampled pixel is the mat, allowing for the JPEG round trip.

    **Exact comparison is not available here and asking for it would be testing
    the codec.** The canvas is saved as JPEG, so a flat `#27285b` comes back as
    something within a few counts of it — and *at* the boundary with the artwork
    it rings much further than that, which is why every sample below is taken
    well inside a region rather than one pixel from its edge. The margins
    themselves are asserted exactly, from the placement `compose` reports.
    """
    return all(abs(channel - expected) <= tolerance for channel, expected in zip(pixel, MAT_RGB, strict=True))


class TestTheCanvasGeometry:
    def test_the_canvas_is_exactly_the_panel(self, tmp_path):
        source = _source(tmp_path, 4000, 3000)

        result, canvas = _composed(tmp_path, source)

        assert canvas.size == (PANEL_WIDTH, PANEL_HEIGHT)
        assert (result.canvas_width, result.canvas_height) == (PANEL_WIDTH, PANEL_HEIGHT)

    def test_a_work_that_fills_the_box_leaves_the_reference_margins(self, tmp_path):
        """The whole point, and the one thing a correct box cannot prove on its
        own: 262 px above and either side, 301 below."""
        # 3316 x 1597 is the box exactly, so the work is not scaled at all.
        source = _source(tmp_path, 3316, 1597)

        result, _ = _composed(tmp_path, source)

        assert result.artwork_left == SIDE_MAT
        assert result.artwork_top == SIDE_MAT
        assert PANEL_WIDTH - result.artwork_left - result.rendered_width == SIDE_MAT
        assert PANEL_HEIGHT - result.artwork_top - result.rendered_height == BOTTOM_MAT

    def test_the_bottom_margin_is_deeper_than_the_top(self, tmp_path):
        """The conservator's convention `MAT_BOTTOM_WEIGHT` encodes: a
        true-centred picture reads as sitting low. Asserted as an inequality
        rather than a figure, so it holds at any configured weighting."""
        source = _source(tmp_path, 3316, 1597)

        result, _ = _composed(tmp_path, source)

        below = PANEL_HEIGHT - result.artwork_top - result.rendered_height
        assert below > result.artwork_top

    def test_a_centred_paste_would_fail_this(self, tmp_path):
        """Guards the guard. If the compositor centred on the canvas instead of
        placing the box, the margins above and below would be equal — so this
        records what a centred paste would have produced, and that the
        compositor does not produce it."""
        source = _source(tmp_path, 3316, 1597)

        result, _ = _composed(tmp_path, source)

        centred_top = (PANEL_HEIGHT - 1597) // 2
        assert result.artwork_top != centred_top
        assert result.artwork_top < centred_top

    def test_the_mat_is_actually_painted_around_the_work(self, tmp_path):
        """The placement above is arithmetic; this is the picture. Sampled well
        inside each margin, because the boundary itself is where JPEG rings."""
        source = _source(tmp_path, 3316, 1597)

        result, canvas = _composed(tmp_path, source)
        pixels = canvas.convert("RGB").load()

        inset = 20
        column, row = PANEL_WIDTH // 2, PANEL_HEIGHT // 2
        assert _is_mat(pixels[column, result.artwork_top - inset])
        assert _is_mat(pixels[result.artwork_left - inset, row])
        assert _is_mat(pixels[result.artwork_left + result.rendered_width + inset, row])
        assert _is_mat(pixels[column, result.artwork_top + result.rendered_height + inset])
        # And the picture is genuinely inside it, not a mat all the way across.
        assert not _is_mat(pixels[column, row])

    def test_the_mat_fills_every_corner(self, tmp_path):
        """A corner is the cheapest place for an off-by-one to hide."""
        source = _source(tmp_path, 3316, 1597)

        _, canvas = _composed(tmp_path, source)
        pixels = canvas.convert("RGB").load()

        for corner in [(0, 0), (PANEL_WIDTH - 1, 0), (0, PANEL_HEIGHT - 1), (PANEL_WIDTH - 1, PANEL_HEIGHT - 1)]:
            assert _is_mat(pixels[corner])


class TestNoUpscaling:
    def test_a_source_smaller_than_the_box_is_pasted_at_its_own_size(self, tmp_path):
        """Not a degraded path: the mat is simply wider. Upscaling is the one
        option that turns an honest "this image is small" into an apparent
        rendering fault.

        1600 px is chosen to clear the floor as well as sit inside the box — at
        the reference panel's ~105 ppi it renders at 15 inches against a 12-inch
        floor, so the verdict under test is `matted_small` and not `below_floor`,
        which takes precedence over it."""
        source = _source(tmp_path, 1600, 1200)

        result, _ = _composed(tmp_path, source)

        assert (result.rendered_width, result.rendered_height) == (1600, 1200)
        assert result.fit is DisplayFit.MATTED_SMALL
        # And the mat grew to absorb it, rather than the picture growing.
        assert result.artwork_left > SIDE_MAT

    def test_a_source_larger_than_the_box_is_downscaled_to_fit(self, tmp_path):
        """4:3 against a wider box, so height is the binding constraint and the
        assertion can name which edge it expects to be filled."""
        source = _source(tmp_path, 8000, 6000)

        result, _ = _composed(tmp_path, source)

        assert result.rendered_height == REFERENCE_BOX.height
        assert result.rendered_width <= REFERENCE_BOX.width
        assert result.fit is DisplayFit.NATIVE

    def test_downscaling_preserves_the_aspect_ratio(self, tmp_path):
        """A tall narrow work legitimately fills little of a 16:9 canvas, and
        stretching it to fill more would be the wrong fix for that."""
        source = _source(tmp_path, 2000, 6000)

        result, _ = _composed(tmp_path, source)

        assert result.rendered_height == REFERENCE_BOX.height
        assert result.rendered_width == pytest.approx(REFERENCE_BOX.height * 2000 / 6000, abs=1)

    def test_a_tiny_source_still_composes_rather_than_being_refused(self, tmp_path):
        source = _source(tmp_path, 12, 9)

        result, canvas = _composed(tmp_path, source)

        assert (result.rendered_width, result.rendered_height) == (12, 9)
        assert canvas.size == (PANEL_WIDTH, PANEL_HEIGHT)


class TestTheFloor:
    def test_a_work_below_the_floor_is_still_rendered(self, tmp_path):
        """The floor informs a curator's choice in the review grid, before this
        point. A renderer that second-guessed it would suppress a picture the
        curator explicitly asked for."""
        source = _source(tmp_path, 300, 200)

        result, canvas = _composed(tmp_path, source)

        assert result.fit is DisplayFit.BELOW_FLOOR
        assert canvas.size == (PANEL_WIDTH, PANEL_HEIGHT)

    def test_the_rendered_size_on_the_wall_is_reported_in_inches(self, tmp_path):
        """So a caller can say "this is on the wall, and it is smaller than your
        floor" in one answer rather than recomputing the scaling to find out."""
        source = _source(tmp_path, 300, 200)

        result, _ = _composed(tmp_path, source)

        assert result.rendered_long_edge_inches == pytest.approx(300 / REFERENCE_BOX.pixels_per_inch, abs=0.01)


class TestWhatItRefuses:
    def test_an_unreadable_mat_colour_is_refused_before_the_image_is_decoded(self, tmp_path):
        source = _source(tmp_path, 4000, 3000)

        with pytest.raises(ColorError):
            _composed(tmp_path, source, mat_hex="octarine")

    @pytest.mark.parametrize(("width", "height"), [(0, 2160), (3840, 0), (-1, 2160)])
    def test_a_panel_with_no_size_is_refused(self, tmp_path, width, height):
        source = _source(tmp_path, 400, 300)

        with pytest.raises(ValueError, match="positive size"):
            compose(
                source,
                destination=tmp_path / "ready" / "work.jpg",
                mat_hex=MAT_HEX,
                panel_width=width,
                panel_height=height,
                box=REFERENCE_BOX,
            )


class TestWritingTheFile:
    def test_the_directory_is_created_if_it_is_not_there(self, tmp_path):
        source = _source(tmp_path, 400, 300)

        result, _ = _composed(tmp_path, source)

        assert result.path.is_file()
        assert result.path.parent.name == "ready"

    def test_a_failed_composition_leaves_the_previous_canvas_untouched(self, tmp_path):
        """The same rule acquisition follows and for the same reason: a
        regeneration that fails partway must cost the work the image it is
        currently displaying nothing."""
        destination = tmp_path / "ready" / "work.jpg"
        destination.parent.mkdir(parents=True)
        destination.write_bytes(b"the canvas already on the wall")
        source = _source(tmp_path, 400, 300)
        # A directory where the staging file must go: `save` fails, and what
        # matters is what survives.
        (destination.parent / f"{destination.name}.composing").mkdir()

        with pytest.raises(OSError):
            compose(
                source,
                destination=destination,
                mat_hex=MAT_HEX,
                panel_width=PANEL_WIDTH,
                panel_height=PANEL_HEIGHT,
                box=REFERENCE_BOX,
            )

        assert destination.read_bytes() == b"the canvas already on the wall"

    def test_re_composing_replaces_the_canvas_in_place(self, tmp_path):
        source = _source(tmp_path, 400, 300)
        first, _ = _composed(tmp_path, source)
        first_bytes = first.path.read_bytes()

        second, _ = _composed(tmp_path, source, mat_hex="#6b6b6b")

        assert second.path == first.path
        assert second.path.read_bytes() != first_bytes


class TestSourcesThatArriveOddly:
    def test_a_portrait_work_stored_sideways_is_composed_upright(self, tmp_path):
        """`measure()` reports EXIF-corrected dimensions to the catalogue, so a
        compositor that ignored the tag would render a work the display-fit
        verdict was never computed for."""
        path = tmp_path / "rotated.jpg"
        image = Image.new("RGB", (3000, 1500), (220, 30, 30))
        exif = image.getexif()
        exif[0x0112] = 6  # rotate 90 CW on display
        image.save(path, format="JPEG", exif=exif)

        result, _ = _composed(tmp_path, path)

        assert result.rendered_height > result.rendered_width

    def test_a_greyscale_scan_is_composed_onto_a_colour_mat(self, tmp_path):
        """Greyscale and CMYK both appear in museum downloads, and neither can be
        pasted onto an RGB canvas without a common mode."""
        path = tmp_path / "grey.jpg"
        Image.new("L", (2000, 1500), 90).save(path, format="JPEG")

        _, canvas = _composed(tmp_path, path)

        assert _is_mat(canvas.convert("RGB").load()[0, 0])
