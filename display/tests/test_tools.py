"""The tools directory is code, and nothing was executing it.

**This file exists because of a specific failure.** 13B-1 moved three contract
surfaces at once — `lay_out` gained a required parameter, `LabelSurface` gained a
required property, and three module constants were deleted — and
`tools/label_preview.py` used all three. Every invocation raised. The suite stayed
green, the linters stayed green, and the only thing that would have discovered it
is the operator running the tool at the panel with the service stopped, which is
the most expensive place this product has to find a defect.

`tests/test_config.py` walks `display/tools/*.py`, but only with a regex looking
for deployment values — it never imports them. A file nothing imports is a file
the type checker, the test suite and the linter all agree is fine.

**The rasterizer is stubbed rather than skipped.** `label_preview` imports Pango
at module level, which does not install on every machine this suite runs on — and
an `importorskip` here would make the guard vanish on exactly the machines where
it is cheapest to run. The stub means what is under test is the tool's own wiring
to the layout seam, which is the half that broke and the half that has nothing to
do with typesetting.
"""

import math
import sys
import types
from pathlib import Path

import pytest

from display.panel.layout import Extent
from display.panel.raster import Raster

TOOLS = Path(__file__).resolve().parent.parent / "tools"


class StubRasterizer:
    """Enough of `Rasterizer` to drive the tool without a text stack."""

    @property
    def measure(self):
        def measure(text: str, size_px: int, wrap_px: int) -> Extent:
            glyph = max(1, size_px // 2)
            per_row = max(1, wrap_px // glyph)
            rows = max(1, math.ceil(len(text) / per_row))
            return Extent(width_px=min(len(text) * glyph, wrap_px), height_px=rows * size_px)

        return measure

    def render(self, layout) -> Raster:
        width, height = layout.surface.width_px, layout.surface.height_px
        return Raster(width_px=width, height_px=height, pixels=bytes(width * height))


@pytest.fixture
def label_preview(monkeypatch):
    """The tool, imported with Pango stood in for.

    Both the module the tool imports *from* and the name it already bound are
    patched: the first is what lets the import succeed on a machine with no text
    stack, and the second is what a machine that *has* one would otherwise use —
    so the test exercises the same code either way instead of quietly diverging.
    """
    # **The tool patches module constants permanently, and that is correct for a
    # one-shot CLI and poison in a suite.** `_apply_overrides` assigns
    # `COMFORTABLE_CAP_ARCMIN` and `MEASURE_EM` outright, so a test passing
    # `--cap-arcmin` would silently resize the type for every test that ran after
    # it. Re-setting each to its own current value registers it with monkeypatch,
    # which restores it at teardown — the leak is contained here rather than by
    # making the tool defend against a caller it does not have.
    from display.panel import layout, legibility

    monkeypatch.setattr(legibility, "COMFORTABLE_CAP_ARCMIN", legibility.COMFORTABLE_CAP_ARCMIN)
    monkeypatch.setattr(layout, "MEASURE_EM", layout.MEASURE_EM)

    stub_module = types.ModuleType("display.panel.pango")
    stub_module.PangoRasterizer = StubRasterizer
    monkeypatch.setitem(sys.modules, "display.panel.pango", stub_module)
    monkeypatch.syspath_prepend(str(TOOLS))
    monkeypatch.delitem(sys.modules, "label_preview", raising=False)

    import label_preview as module

    monkeypatch.setattr(module, "PangoRasterizer", StubRasterizer)
    return module


class TestTheLabelPreviewStillRuns:
    """**Behavioural, not an import check.** An import alone would have caught two
    of the four ways this tool broke and missed the other two: `_report` reads the
    layout module at call time, and the `lay_out` and `EpaperSurface` call sites
    only fail when reached."""

    def test_it_renders_a_png_through_the_whole_chain(self, label_preview, tmp_path, capsys):
        output = tmp_path / "label.png"

        assert label_preview.main([str(output)]) == 0
        assert output.exists() and output.stat().st_size > 0

        printed = capsys.readouterr().out
        assert "px per arcminute" in printed, "the report did not run, or stopped naming the visual angle"

    def test_the_report_names_the_angle_beside_every_size(self, label_preview, tmp_path, capsys):
        """The whole point of the tool's output. A pixel size at a terminal says
        nothing about whether the person at the wall can read it — which is how a
        body size at half the resolvable cap height passed every check there was."""
        label_preview.main([str(tmp_path / "label.png")])

        placed = [line for line in capsys.readouterr().out.splitlines() if "px =" in line]
        assert placed, "no line reported a placed block"
        assert all("' cap at y=" in line for line in placed)

    def test_the_calibration_override_changes_the_type(self, label_preview, tmp_path, capsys):
        """`--cap-arcmin` is the one judgement the operator still makes, so it is
        the one flag that must actually reach the derivation."""
        label_preview.main([str(tmp_path / "a.png")])
        default = capsys.readouterr().out

        label_preview.main([str(tmp_path / "b.png"), "--cap-arcmin", "20"])
        larger = capsys.readouterr().out

        assert _primary_of(default) < _primary_of(larger)

    def test_a_further_viewing_distance_asks_for_larger_type(self, label_preview, tmp_path, capsys):
        label_preview.main([str(tmp_path / "near.png"), "--viewing-distance-inches", "42"])
        near = capsys.readouterr().out

        label_preview.main([str(tmp_path / "far.png"), "--viewing-distance-inches", "168"])
        far = capsys.readouterr().out

        assert _primary_of(near) < _primary_of(far)

    def test_it_refuses_to_run_with_neither_an_output_nor_a_panel(self, label_preview):
        """Argparse's own error path, which exits rather than returning."""
        with pytest.raises(SystemExit):
            label_preview.main([])


def _primary_of(printed: str) -> int:
    """The primary tier out of the tool's own report line."""
    for line in printed.splitlines():
        if "tiers:" in line:
            return int(line.split("tiers:")[1].split("px")[0].strip())
    raise AssertionError(f"the report named no tiers:\n{printed}")
