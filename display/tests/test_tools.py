"""The tools directory is code, and nothing was executing it.

**This file exists because of a specific failure.** The type-floor derivation
moved three contract surfaces at once — `lay_out` gained a required parameter,
`LabelSurface` gained a required property, three module constants were deleted — and
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


@pytest.fixture
def deployment(monkeypatch, tmp_path):
    """A complete, hermetic environment for the tool's `.env` road.

    **Every test touching that road needs this, and the reason is a defect these
    tests shipped with.** `display.config.load` calls `load_dotenv()`, which reads
    the repo-root `.env` — gitignored, so absent in CI and present with different
    contents on the Pi and on a developer's machine. Tests that merely set or
    deleted the two `EPD_*` variables therefore passed on exactly one machine:
    CI has no `ART_ROOT` so `load` raised and the tool refused where a test
    expected success, and the Pi's `.env` re-injected the two values so the tool
    proceeded where a test expected refusal. Three tests, three different results,
    none of them a statement about the code.

    So this stubs `load_dotenv` to a no-op and supplies the full required set
    itself. Nothing here reads the ambient filesystem, and every fact a test
    depends on is stated where the test can see it.
    """
    from display import config

    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: None)
    for name, value in (
        ("ART_ROOT", str(tmp_path)),
        ("WALL_ID", "living-room"),
        ("TV_ADDRESS", "10.0.0.2"),
        ("LATITUDE", "45.68"),
        ("LONGITUDE", "-111.04"),
        ("LOCATION_NAME", "Bozeman"),
    ):
        monkeypatch.setenv(name, value)
    # The two under test start absent on every machine, whatever its own .env says.
    monkeypatch.delenv("EPD_PANEL_DIAGONAL_INCHES", raising=False)
    monkeypatch.delenv("EPD_VIEWING_DISTANCE_INCHES", raising=False)


#: The two physical facts the tool refuses to guess, as the reference wall's.
#: **Stated by every invocation below rather than defaulted**, which is the
#: behaviour under test as much as a fixture detail: the tool used to carry these
#: numbers itself, so an operator at a different panel calibrated against this
#: wall's geometry and the report echoed figures nobody supplied.
WALL = ["--diagonal-inches", "6.0", "--viewing-distance-inches", "84"]


def run(module, *arguments):
    """Drive the tool with the viewing conditions supplied, as a real caller must."""
    return module.main([*arguments, *WALL])


class TestTheLabelPreviewStillRuns:
    """**Behavioural, not an import check.** An import alone would have caught two
    of the four ways this tool broke and missed the other two: `_report` reads the
    layout module at call time, and the `lay_out` and `EpaperSurface` call sites
    only fail when reached."""

    def test_it_renders_a_png_through_the_whole_chain(self, label_preview, tmp_path, capsys):
        output = tmp_path / "label.png"

        assert run(label_preview, str(output)) == 0
        assert output.exists() and output.stat().st_size > 0

        printed = capsys.readouterr().out
        assert "px per arcminute" in printed, "the report did not run, or stopped naming the visual angle"

    def test_the_report_names_the_angle_beside_every_size(self, label_preview, tmp_path, capsys):
        """The whole point of the tool's output. A pixel size at a terminal says
        nothing about whether the person at the wall can read it — which is how a
        body size at half the resolvable cap height passed every check there was."""
        run(label_preview, str(tmp_path / "label.png"))

        placed = [line for line in capsys.readouterr().out.splitlines() if "px =" in line]
        assert placed, "no line reported a placed block"
        assert all("' cap at y=" in line for line in placed)

    def test_the_sample_shows_the_label_a_seeded_catalogue_produces(self, label_preview, tmp_path, capsys):
        """**The one omission that would make this tool lie rather than break.**

        A label with no family and given parts is legal and falls back to the
        whole name unstyled — so a sample missing them renders cleanly, reports
        cleanly, and shows the operator a label the wall does not produce. That
        is worse than a crash, because the operator's whole reason for running
        this is to judge what the panel will show. Asserted on the tool's own
        output rather than on the dict, so it holds however the sample is built.
        """
        run(label_preview, str(tmp_path / "label.png"))

        printed = capsys.readouterr().out
        assert "Katsushika, Hokusai" in printed, "the sample no longer carries the name parts the panel sets"

    def test_the_report_shows_the_drop_rule_taking_the_lowest_line_off(self, label_preview, tmp_path, capsys):
        """**The half of the label that is invisible in the image.**

        The drop rule's whole failure mode is silence: a label that lost its
        dimensions looks like a label that never had any. So the sample has to
        overflow — a fully populated work, down to the commentary that is first to
        go — or the tool renders a comfortable label and never exercises the line
        it exists to make visible.

        **What this can and cannot say.** It runs against `StubRasterizer`, whose
        measure is arithmetic of this file's choosing, so it establishes that the
        sample overflows *the stub* and not that it overflows Pango on the real
        panel — no test on this machine can say the second thing. What transfers
        is the property under test: the sample is populated enough to reach the
        drop rule at all, and the lowest-priority line is the one it takes. A
        sample trimmed back to something comfortable fails here first.
        """
        run(label_preview, str(tmp_path / "label.png"))

        (dropped,) = [line for line in capsys.readouterr().out.splitlines() if "DROPPED" in line]
        # `Layout.dropped` keeps label order, so the LAST name here is the
        # lowest-priority line — the first one the rule actually gave up.
        # Asserting on that end pins the ordering rather than merely that
        # something came off.
        taken = dropped.split(":", 1)[1].strip()
        assert taken.endswith(
            "One of thirty-six views, and the one that outran the series."
        ), f"commentary was not the lowest line given up: {taken}"

    def test_the_calibration_override_changes_the_type(self, label_preview, tmp_path, capsys):
        """`--cap-arcmin` is the one judgement the operator still makes, so it is
        the one flag that must actually reach the derivation."""
        run(label_preview, str(tmp_path / "a.png"))
        default = capsys.readouterr().out

        run(label_preview, str(tmp_path / "b.png"), "--cap-arcmin", "20")
        larger = capsys.readouterr().out

        assert _primary_of(default) < _primary_of(larger)

    def test_a_further_viewing_distance_asks_for_larger_type(self, label_preview, tmp_path, capsys):
        label_preview.main([str(tmp_path / "near.png"), "--diagonal-inches", "6.0", "--viewing-distance-inches", "42"])
        near = capsys.readouterr().out

        label_preview.main([str(tmp_path / "far.png"), "--diagonal-inches", "6.0", "--viewing-distance-inches", "168"])
        far = capsys.readouterr().out

        assert _primary_of(near) < _primary_of(far)

    def test_it_refuses_to_run_with_neither_an_output_nor_a_panel(self, label_preview):
        """Argparse's own error path, which exits rather than returning."""
        with pytest.raises(SystemExit):
            label_preview.main([])

    def test_it_refuses_to_guess_the_viewing_conditions(self, label_preview, deployment, tmp_path, capsys):
        """**The instrument must not answer for a wall it was not pointed at.**

        This tool carried the reference wall's 6 inches and 7 feet as argument
        defaults, which meant an operator at a *different* panel who ran it
        without flags calibrated `--cap-arcmin` against somebody else's geometry
        — and the report echoed two numbers nobody had supplied, so it read as
        confirmation. It is the same failure `.env.example` was emptied to
        prevent, arriving on the surface that exists to expose it.

        Refusing names both environment variables and both flags, because the
        person who hits this needs to know which two facts are missing.
        """
        with pytest.raises(SystemExit):
            label_preview.main([str(tmp_path / "label.png")])

        complaint = capsys.readouterr().err
        assert "EPD_PANEL_DIAGONAL_INCHES" in complaint and "EPD_VIEWING_DISTANCE_INCHES" in complaint
        assert "--diagonal-inches" in complaint and "--viewing-distance-inches" in complaint

    def test_it_takes_the_conditions_from_the_deployment_when_no_flag_gives_them(
        self, label_preview, deployment, tmp_path, monkeypatch, capsys
    ):
        """**The convenience half of the refusal above, and the half the Pi uses.**

        Both documented short invocations — this file's own docstring, and
        `deploy/README.md` — pass no geometry, because on the machine that owns
        the panel the `.env` already states it. So the `.env` road is not a
        fallback for tidiness; it is the road the operator actually walks, and it
        must be the *same* two settings the daemon reads rather than a second
        spelling of them.

        **This test exists because the mutation sweep found that road dead.** The
        first version called a constructor the config module does not have; the
        broad catch printed the `AttributeError` and carried on with no settings,
        so every run refused and the refusal tests all passed. Deleting the whole
        lookup changed nothing any test noticed — which is exactly what "green
        suite, undefended branch" looks like.
        """
        monkeypatch.setenv("EPD_PANEL_DIAGONAL_INCHES", "10.3")
        monkeypatch.setenv("EPD_VIEWING_DISTANCE_INCHES", "120")

        assert label_preview.main([str(tmp_path / "label.png")]) == 0

        printed = capsys.readouterr().out
        # Both numbers, and a floor that is NOT the reference wall's 92 px —
        # echoing the geometry proves it was read, and the derived size proves it
        # was used rather than merely printed.
        assert '10.3" panel read from 120.0"' in printed, "the report did not echo the deployment's own geometry"
        assert _floor_of(printed) != 92, "the deployment's geometry was echoed but not derived from"

    def test_one_stated_fact_does_not_let_the_other_be_guessed(self, label_preview, deployment, tmp_path, capsys):
        """Half-known conditions are the dangerous case: a run with a real diagonal
        and an invented distance looks more trustworthy than one with neither."""
        with pytest.raises(SystemExit):
            label_preview.main([str(tmp_path / "label.png"), "--diagonal-inches", "6.0"])

        complaint = capsys.readouterr().err
        assert "EPD_VIEWING_DISTANCE_INCHES" in complaint
        assert "EPD_PANEL_DIAGONAL_INCHES" not in complaint, "it named a fact the caller had supplied"


def _floor_of(printed: str) -> int:
    """The floor tier out of the tool's own report line."""
    for line in printed.splitlines():
        if "tiers:" in line:
            return int(line.split("over a")[1].split("px")[0].strip())
    raise AssertionError(f"the report named no tiers:\n{printed}")


def _primary_of(printed: str) -> int:
    """The primary tier out of the tool's own report line."""
    for line in printed.splitlines():
        if "tiers:" in line:
            return int(line.split("tiers:")[1].split("px")[0].strip())
    raise AssertionError(f"the report named no tiers:\n{printed}")
