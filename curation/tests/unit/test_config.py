"""Deployment configuration resolution.

The values here differ between the dev Mac and the Pi, so the failure this
module exists to prevent is a plausible-looking default that quietly writes the
catalogue somewhere unintended. These tests assert the refusals, not just the
happy path.
"""

import os
from decimal import Decimal
from pathlib import Path

import pytest

from curation.config import (
    CATALOGUE_FILENAME,
    DEFAULT_HOST,
    DEFAULT_PORT,
    DEFAULT_ROTATION_INTERVAL_SECONDS,
    DEFAULT_ROTATION_SHUFFLE,
    DEFAULT_TV_PANEL_DIAGONAL_INCHES,
    DEFAULT_TV_PANEL_HEIGHT_PX,
    DEFAULT_TV_PANEL_WIDTH_PX,
    ConfigError,
    Settings,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Resolve from this process's environment and nothing else.

    `from_env` calls `load_dotenv()` with no path, and dotenv searches from
    `config.py`'s own directory upward — never the cwd — so chdir'ing to a
    scratch directory isolates nothing.

    The stub is still needed after the 2026-08-05 precedence fix, for the half
    that fix did not change: a name this fixture *deletes* is absent from the
    environment, so a real `.env` is free to supply it, and the documented
    setup step (`cp .env.example .env`) creates exactly that file. Every
    missing-value assertion below would otherwise be green only on a machine
    where nobody has followed the README. Names this fixture *sets* no longer
    need it — that is what `test_an_exported_value_beats_the_dotenv_file`
    pins.
    """
    monkeypatch.setattr("curation.config.load_dotenv", lambda **_: False)
    for name in (
        "ART_ROOT",
        "CURATION_HOST",
        "CURATION_PORT",
        "ROTATION_INTERVAL_SECONDS",
        "ROTATION_SHUFFLE",
        "TV_PANEL_WIDTH_PX",
        "TV_PANEL_HEIGHT_PX",
        "TV_PANEL_DIAGONAL_INCHES",
    ):
        monkeypatch.delenv(name, raising=False)


def _dotenv_supplying(monkeypatch, **values):
    """Stand in for `python-dotenv`, honouring its real precedence flag.

    Measured against the installed python-dotenv on 2026-08-05: with no
    `override` an entry already in `os.environ` is left alone, and the file's
    value is used only for names that are absent; `override=True` replaces
    both. The fake reproduces exactly that, so it is the *library* being stood
    in for — `Settings.from_env` itself is driven for real, and if it ever
    passes `override=True` again the fake honours it and the caller below goes
    red. A stub that simply ignored the flag would make that mutation
    invisible, which is the whole failure this pair of tests exists to catch.
    """

    def loader(*_args, override=False, **_kwargs):
        for name, value in values.items():
            if override or name not in os.environ:
                monkeypatch.setenv(name, value)
        return True

    return loader


def test_an_exported_value_beats_the_dotenv_file(monkeypatch):
    """`.env` supplies defaults; whatever is already exported wins.

    The inverse shipped until 2026-08-05 and made
    `ART_ROOT=/tmp/scratch uv run python -m curation` boot against the real
    catalogue — the export was discarded rather than refused, so the wrong
    tree looked exactly like the right one.
    """
    monkeypatch.setenv("ART_ROOT", "/from-the-environment")
    monkeypatch.setattr(
        "curation.config.load_dotenv",
        _dotenv_supplying(monkeypatch, ART_ROOT="/from-the-dotenv-file"),
    )

    assert Settings.from_env().art_root == Path("/from-the-environment")


def test_the_dotenv_file_still_supplies_what_the_environment_does_not(monkeypatch):
    """The other half, and it is not redundant with the test above.

    Deleting the `load_dotenv()` call outright would satisfy that one and
    break every machine set up by the documented `cp .env.example .env` step.
    This is the case that test cannot rescue.
    """
    monkeypatch.delenv("ART_ROOT", raising=False)
    monkeypatch.setattr(
        "curation.config.load_dotenv",
        _dotenv_supplying(monkeypatch, ART_ROOT="/from-the-dotenv-file"),
    )

    assert Settings.from_env().art_root == Path("/from-the-dotenv-file")


def test_a_missing_art_root_fails_fast_and_names_the_file_to_fix():
    with pytest.raises(ConfigError) as caught:
        Settings.from_env()

    assert "ART_ROOT" in str(caught.value)
    assert ".env" in str(caught.value)


def test_an_empty_art_root_is_refused_rather_than_treated_as_the_cwd(monkeypatch):
    monkeypatch.setenv("ART_ROOT", "")

    with pytest.raises(ConfigError, match="ART_ROOT"):
        Settings.from_env()


def test_the_catalogue_is_anchored_under_art_root(monkeypatch, tmp_path):
    monkeypatch.setenv("ART_ROOT", str(tmp_path))

    settings = Settings.from_env()

    assert settings.catalogue_path == tmp_path / CATALOGUE_FILENAME
    assert settings.catalogue_path.parent == settings.art_root


def test_the_defaults_bind_loopback_on_the_protocol_port(monkeypatch, tmp_path):
    # Asserted against literals, not against the constants themselves — that
    # form agrees with whatever value they are changed to. Widening the bind
    # to a non-loopback address is a deliberate exposure decision, and this
    # should fail when someone makes it quietly.
    monkeypatch.setenv("ART_ROOT", str(tmp_path))

    settings = Settings.from_env()

    assert (settings.host, settings.port) == ("127.0.0.1", 8770)
    assert (DEFAULT_HOST, DEFAULT_PORT) == ("127.0.0.1", 8770)


def test_a_non_numeric_port_is_rejected_with_the_offending_value(monkeypatch, tmp_path):
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv("CURATION_PORT", "eight-thousand")

    with pytest.raises(ConfigError) as caught:
        Settings.from_env()

    assert "eight-thousand" in str(caught.value)


@pytest.mark.parametrize("port", ["0", "65536", "-1"])
def test_a_port_outside_the_valid_range_is_refused(monkeypatch, tmp_path, port):
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv("CURATION_PORT", port)

    with pytest.raises(ConfigError, match="between 1 and 65535"):
        Settings.from_env()


def test_an_explicit_host_and_port_override_the_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv("CURATION_HOST", "0.0.0.0")  # noqa: S104 - the point of the test
    monkeypatch.setenv("CURATION_PORT", "9001")

    settings = Settings.from_env()

    assert (settings.host, settings.port) == ("0.0.0.0", 9001)


# -- the wall's own settings ---------------------------------------------------
#
# Every value below reaches the manifest or the mat. A silently wrong one is not
# a crash: it is a wall running at the wrong pace, or a mat composed for a
# television that is not on the wall.


def test_the_manifest_and_heartbeat_are_anchored_under_art_root_and_named_per_wall(monkeypatch, tmp_path):
    """Both planes have to agree where these are, so neither is configurable.

    And both are **per wall**: the file set is indexed by wall id, which is what
    keeps one room's rewrite out of another room's file and lets health name which
    wall is silent. A settings object holding one path apiece is what let a second
    wall's theme overwrite the first's until 2026-08-12.
    """
    monkeypatch.setenv("ART_ROOT", str(tmp_path))

    settings = Settings.from_env()

    assert settings.manifest_path("living-room") == tmp_path / "theme-manifest-living-room.json"
    assert settings.heartbeat_path("living-room") == tmp_path / "display-heartbeat-living-room.json"
    # Two walls, two files. The assertion the singular fields could not make.
    assert settings.manifest_path("study") != settings.manifest_path("living-room")


def test_the_shipped_rotation_defaults_are_what_the_wall_runs_today(monkeypatch, tmp_path):
    """Carried forward from the 2024 plane; the cutover must not change the pace."""
    monkeypatch.setenv("ART_ROOT", str(tmp_path))

    settings = Settings.from_env()

    assert settings.rotation_interval_seconds == DEFAULT_ROTATION_INTERVAL_SECONDS
    assert settings.rotation_shuffle == DEFAULT_ROTATION_SHUFFLE
    assert settings.tv_panel_width_px == DEFAULT_TV_PANEL_WIDTH_PX
    assert settings.tv_panel_height_px == DEFAULT_TV_PANEL_HEIGHT_PX
    assert settings.tv_panel_diagonal_inches == DEFAULT_TV_PANEL_DIAGONAL_INCHES


def test_a_deployment_can_override_every_wall_setting(monkeypatch, tmp_path):
    """Values no default could produce, so a setting read from the wrong name would show."""
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv("ROTATION_INTERVAL_SECONDS", "931")
    monkeypatch.setenv("ROTATION_SHUFFLE", "false")
    monkeypatch.setenv("TV_PANEL_WIDTH_PX", "1920")
    monkeypatch.setenv("TV_PANEL_HEIGHT_PX", "1080")
    monkeypatch.setenv("TV_PANEL_DIAGONAL_INCHES", "55.5")

    settings = Settings.from_env()

    assert settings.rotation_interval_seconds == 931
    assert settings.rotation_shuffle is False
    assert settings.tv_panel_width_px == 1920
    assert settings.tv_panel_height_px == 1080
    assert settings.tv_panel_diagonal_inches == 55.5


@pytest.mark.parametrize("spelling", ["false", "False", "FALSE", "0", "no", "off", " off "])
def test_every_spelling_of_off_turns_shuffle_off(monkeypatch, tmp_path, spelling):
    """The hazard this reader exists for: `bool("false")` is True in Python.

    A lenient reader turns a deliberate "off" into "on" and reports nothing, on
    the setting that reaches the manifest and drives the wall.
    """
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv("ROTATION_SHUFFLE", spelling)

    assert Settings.from_env().rotation_shuffle is False


@pytest.mark.parametrize("spelling", ["true", "True", "1", "yes", "on"])
def test_every_spelling_of_on_turns_shuffle_on(monkeypatch, tmp_path, spelling):
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv("ROTATION_SHUFFLE", spelling)

    assert Settings.from_env().rotation_shuffle is True


def test_a_flag_that_is_neither_is_refused_rather_than_guessed(monkeypatch, tmp_path):
    """Guessing here is how "shuffle=maybe" becomes "shuffle=on" with nothing said."""
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv("ROTATION_SHUFFLE", "sometimes")

    with pytest.raises(ConfigError, match="must be true or false, got 'sometimes'"):
        Settings.from_env()


@pytest.mark.parametrize(
    "name",
    ["ROTATION_INTERVAL_SECONDS", "TV_PANEL_WIDTH_PX", "TV_PANEL_HEIGHT_PX"],
)
def test_a_non_numeric_whole_number_setting_is_refused_with_the_offending_value(monkeypatch, tmp_path, name):
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv(name, "wide")

    with pytest.raises(ConfigError, match="must be a whole number, got 'wide'"):
        Settings.from_env()


@pytest.mark.parametrize(
    "name",
    ["ROTATION_INTERVAL_SECONDS", "TV_PANEL_WIDTH_PX", "TV_PANEL_HEIGHT_PX"],
)
@pytest.mark.parametrize("value", ["0", "-1"])
def test_a_setting_that_must_be_positive_refuses_zero_and_below(monkeypatch, tmp_path, name, value):
    """Zero is the dangerous one: a zero interval spins, a zero panel divides by nothing."""
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv(name, value)

    with pytest.raises(ConfigError, match="must be greater than zero"):
        Settings.from_env()


def test_a_non_numeric_panel_diagonal_is_refused_with_the_offending_value(monkeypatch, tmp_path):
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv("TV_PANEL_DIAGONAL_INCHES", "big")

    with pytest.raises(ConfigError, match="must be a number, got 'big'"):
        Settings.from_env()


def test_a_panel_with_no_size_is_refused_rather_than_dividing_by_zero(monkeypatch, tmp_path):
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv("TV_PANEL_DIAGONAL_INCHES", "0")

    with pytest.raises(ConfigError, match="must be greater than zero"):
        Settings.from_env()


def test_pixels_per_inch_is_derived_from_the_panels_own_geometry(monkeypatch, tmp_path):
    """What the mat and the resolution floor are computed from.

    A 3840x2160 panel measures 4405.8 pixels corner to corner; over 42 inches
    that is 104.9 per inch. Derived rather than configured, so a deployment
    cannot state a scale that disagrees with the size it also stated.
    """
    monkeypatch.setenv("ART_ROOT", str(tmp_path))

    assert Settings.from_env().tv_pixels_per_inch == pytest.approx(104.9, abs=0.01)


def test_a_larger_panel_of_the_same_resolution_has_fewer_pixels_per_inch(monkeypatch, tmp_path):
    """The relationship the floor depends on: inches on the wall, not pixel counts."""
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv("TV_PANEL_DIAGONAL_INCHES", "84")

    assert Settings.from_env().tv_pixels_per_inch == pytest.approx(52.45, abs=0.01)


def test_the_artwork_box_reproduces_the_reference_panels_worked_example(monkeypatch, tmp_path):
    """The 42" 4K Frame, as `nonfunctional-requirements.md` works it out.

    That artifact's table is the specification of this arithmetic, so the table
    and the code are pinned to each other here — the alternative is two
    statements of one rule, drifting.
    """
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    box = Settings.from_env().tv_artwork_box

    assert (box.width, box.height) == (3316, 1597)
    assert box.width / box.pixels_per_inch == pytest.approx(31.6, abs=0.05)
    assert box.height / box.pixels_per_inch == pytest.approx(15.2, abs=0.05)


def test_the_same_mat_in_inches_gives_a_bigger_box_on_a_bigger_panel(monkeypatch, tmp_path):
    """The whole point of specifying the mat physically: it scales with the panel.

    The 75" row of the same table. A pixel mat would take the same bite out of
    both canvases and mean something different on each wall.
    """
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv("TV_PANEL_DIAGONAL_INCHES", "75")
    box = Settings.from_env().tv_artwork_box

    assert (box.width, box.height) == (3546, 1844)
    assert box.width / box.pixels_per_inch == pytest.approx(60.4, abs=0.05)


def test_the_bottom_margin_is_deeper_than_the_top(monkeypatch, tmp_path):
    """A true-centred image reads as sitting low, so the vertical mat is not symmetric.

    Asserted as the *relationship* rather than as two numbers: the box is
    shorter than a four-equal-sides mat would leave it, by exactly the extra the
    weighting adds.
    """
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv("MAT_BOTTOM_WEIGHT", "1.5")
    settings = Settings.from_env()
    box = settings.tv_artwork_box

    top = round(settings.mat_width_inches * settings.tv_pixels_per_inch)
    assert box.width == 3840 - 2 * top
    assert box.height == 2160 - top - round(top * 1.5)
    assert box.height < 2160 - 2 * top, "the bottom margin is not deeper than the top"


def test_a_mat_wider_than_the_panel_leaves_a_box_rather_than_a_negative_one(monkeypatch, tmp_path):
    """A misconfiguration should not produce geometry that crashes the fit rule.

    `assess_display_fit` refuses a box with a non-positive side, so an absurd mat
    must clamp to something it can refuse *about* rather than something it
    refuses to even describe.
    """
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv("MAT_WIDTH_INCHES", "40")
    box = Settings.from_env().tv_artwork_box

    assert box.width >= 1
    assert box.height >= 1


def test_the_floor_reaches_the_box_that_is_judged_against_it(monkeypatch, tmp_path):
    """A configured floor nothing carried would be a setting with no effect."""
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv("RESOLUTION_FLOOR_INCHES", "18.5")

    assert Settings.from_env().tv_artwork_box.floor_inches == 18.5


def test_the_thumbnail_cache_sits_inside_the_art_root(monkeypatch, tmp_path):
    """Every stored path is relative to ART_ROOT, so a cache outside it is unstorable."""
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    settings = Settings.from_env()

    assert settings.thumbnails_path.is_relative_to(settings.art_root)
    # Not `tv-thumbs/`, which holds images downloaded from the television keyed
    # by its own content ids — per-device state this catalogue excludes.
    assert settings.thumbnails_path.name != "tv-thumbs"


# -- discovery: what it may do, and what it is priced at ------------------------


def test_the_shipped_discovery_defaults_reproduce_the_recorded_cost_analysis(monkeypatch, tmp_path):
    """The defaults are a derivation, not a preference, and this is where it is checked.

    The figures come from a cost analysis arrived at independently of this code.
    If the shipped settings cannot reproduce them, one of the two is wrong and a
    curator is authorising against a number that describes nothing.

    **Twice now the analysis has moved under a decision, and neither time was
    this assertion relaxed to fit.** The engine choice (2026-08-02) took a search
    request from $0.005 to $0.001, and the model-only component was untouched at
    eight cents — which is what made the fall attributable to search. Then phase 2
    was built and measured (2026-08-02), and both halves of the run changed at
    once:

    - **Phase 1's token basis was re-based against a measured run** — 3,453 in and
      1,608 out, against a shipped 490,000 / 30,000. The old input figure was a
      whole-run basis being spent on phase 1 alone, and it made the number shown
      to a curator about twenty times the actual. The bounds now shipped are
      8,000 each: roughly twice the measured input, and for output the
      provider-priced reservation itself.
    - **Phase 2 costs nothing**, because it asks open museum APIs and establishes
      identity by local comparison rather than by a model call. That is what made
      the re-basing safe to do: correcting phase 1 while phase 2's consumption was
      unknown would have traded a visible overstatement for an invisible
      understatement of the run as a whole.

    Computed here rather than compared against a copied total, so the assertion
    fails when the composition changes rather than tracking it.
    """
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    discovery = Settings.from_env().discovery_settings

    # A typical run finds about twenty works. Bounded, so this is the ceiling
    # rather than the expectation.
    typical_works = 20
    run_total = discovery.phase1_estimate_usd + discovery.phase2_estimate_usd(typical_works)
    # Only phase 1 searches for money. The per-work allowance still bounds phase
    # 2's fan-out and is still reported beside a run's usage — it simply bills
    # nothing, which is why it is absent from this sum rather than multiplied by
    # a price.
    paid_searches = discovery.phase1_search_allowance
    search_spend = paid_searches * discovery.search_cost_usd
    model_spend = run_total - search_spend

    assert paid_searches == 10
    assert (
        discovery.phase1_search_allowance + typical_works * discovery.phase2_searches_per_work == 50
    ), "the fan-out cap is unchanged at 10 + 2/work; only its price went to zero"
    assert search_spend == Decimal("0.010"), "ten requests at the pinned engine's $0.001"
    assert discovery.phase2_estimate_usd(typical_works) == Decimal(0), "museum APIs are free and phase 2 makes no model call"
    assert run_total == Decimal("0.01336"), "a bounded run, an order of magnitude under the pre-measurement estimate"
    # The model call alone: 8,000 in at $0.14/M and 8,000 out at $0.28/M.
    assert model_spend == Decimal("0.00336")
    # The correction's whole point, stated as a relation rather than a number so
    # it cannot be satisfied by a stale constant: a real run measured $0.0016, and
    # a bound that far exceeds what it bounds is not informative. Ten-fold is
    # generous headroom for an allowance a run uses one of.
    assert run_total < 10 * Decimal("0.0016"), "the estimate is a usable bound rather than a twenty-fold overstatement"


def test_the_search_price_matches_the_engine_that_is_pinned(monkeypatch, tmp_path):
    """The two *shipped defaults* are one decision and must not drift apart.

    Parallel bills $0.001 and the other back-ends $0.005, so shipping an engine
    and a price that disagree would put a five-fold error into the only figure a
    curator sees before authorising a run.

    **This cannot see a deployment, and saying so is the point.** The module's
    autouse `_clean_env` stubs `load_dotenv` and clears no `DISCOVERY_*` name, so
    what runs here compares two constants in `config.py` to each other. That stub
    is correct — a config test that read the developer's own `.env` would pass or
    fail by machine — but it means the case in the sentence above, *a deployment*
    that changed one and left the other, is invisible here and was live on this
    repo's own `.env` while this test was green: `DISCOVERY_SEARCH_COST_USD=0.005`
    with no engine pinned, so estimates priced Exa while the engine was the
    `parallel` default.

    The mechanism for the deployment case is therefore **not a test**: startup
    logs the engine and the price on one line, so a mismatch is one journal read
    rather than a silent five-fold error. Adding a boot-time refusal was
    considered and not done — a household product that will not start because two
    optional settings disagree fails harder than the error it is preventing.
    """
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    settings = Settings.from_env()

    prices = {"parallel": Decimal("0.001"), "exa": Decimal("0.005"), "perplexity": Decimal("0.005")}
    expected = prices.get(settings.discovery_search_engine)

    assert expected is not None, (
        f"{settings.discovery_search_engine!r} has no recorded per-request price; add it here with the "
        "measurement behind it, or the run estimate is guessing"
    )
    assert settings.search_cost_usd == expected, (
        f"the engine is {settings.discovery_search_engine!r} at {expected}/request, but the configured "
        f"search price is {settings.search_cost_usd}"
    )


def test_the_gate_ships_at_the_value_a_typical_run_does_not_trip(monkeypatch, tmp_path):
    """Twenty-five, against a typical run of about twenty.

    Chosen so it never fires on an ordinary run and does fire on one that read
    the intent far more broadly than intended. A gate that fires every time is
    one a curator learns to approve without reading.
    """
    monkeypatch.setenv("ART_ROOT", str(tmp_path))

    assert Settings.from_env().discovery_settings.approval_threshold == 25


def test_a_deployment_can_override_every_discovery_setting(monkeypatch, tmp_path):
    """None of these may be a literal in source: prices move and policy is local."""
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    for name, value in {
        "DISCOVERY_APPROVAL_THRESHOLD": "40",
        "DISCOVERY_PHASE1_SEARCH_ALLOWANCE": "6",
        "DISCOVERY_PHASE2_SEARCHES_PER_WORK": "3",
        "DISCOVERY_SEARCH_COST_USD": "0.001",
        "DISCOVERY_INPUT_COST_USD_PER_MTOK": "0.30",
        "DISCOVERY_OUTPUT_COST_USD_PER_MTOK": "2.50",
        "DISCOVERY_PHASE1_INPUT_TOKENS": "100000",
        "DISCOVERY_PHASE1_OUTPUT_TOKENS": "5000",
    }.items():
        monkeypatch.setenv(name, value)

    discovery = Settings.from_env().discovery_settings

    assert discovery.approval_threshold == 40
    assert discovery.phase1_search_allowance == 6
    assert discovery.phase2_searches_per_work == 3
    assert discovery.search_cost_usd == Decimal("0.001")
    # 100,000 in at $0.30/M is $0.03; 5,000 out at $2.50/M is $0.0125; six
    # searches at $0.001 add $0.006.
    assert discovery.phase1_estimate_usd == Decimal("0.0485")
    # Zero whatever the per-work allowance is set to, because phase 2 asks museum
    # APIs and identifies works locally — it makes no paid call for the allowance
    # to price. The allowance is still read and still bounds fan-out, which is
    # what the assertion three lines up checks; what it no longer does is cost
    # anything.
    assert discovery.phase2_estimate_usd(10) == Decimal(0)


def test_a_price_is_read_as_a_decimal_rather_than_through_a_float(monkeypatch, tmp_path):
    """A tenth of a cent that cannot be represented exactly is a rounding error
    in every figure derived from it, including a running total nobody will
    reconcile against the provider's own."""
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv("DISCOVERY_SEARCH_COST_USD", "0.005")
    monkeypatch.setenv("DISCOVERY_PHASE1_SEARCH_ALLOWANCE", "3")

    priced = Settings.from_env().discovery_settings.search_cost_usd * 3

    assert priced == Decimal("0.015")
    assert str(priced) == "0.015", "a price that went through float would not render exactly"


@pytest.mark.parametrize(
    "name",
    ["DISCOVERY_APPROVAL_THRESHOLD", "DISCOVERY_PHASE1_SEARCH_ALLOWANCE", "DISCOVERY_PHASE1_INPUT_TOKENS"],
)
def test_a_count_that_is_not_a_number_is_refused_with_the_offending_value(monkeypatch, tmp_path, name):
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv(name, "several")

    with pytest.raises(ConfigError, match="must be a whole number, got 'several'"):
        Settings.from_env()


@pytest.mark.parametrize(
    "name",
    ["DISCOVERY_APPROVAL_THRESHOLD", "DISCOVERY_PHASE1_SEARCH_ALLOWANCE", "DISCOVERY_PHASE2_SEARCHES_PER_WORK"],
)
def test_a_count_of_zero_is_allowed_rather_than_refused(monkeypatch, tmp_path, name):
    """Zero gates every run, or forbids searching. Both are coherent settings for
    a cautious deployment, and refusing them would be config inventing a policy
    nobody wrote — which is the distinction from a zero rotation interval."""
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv(name, "0")

    assert Settings.from_env()


@pytest.mark.parametrize(
    "name",
    ["DISCOVERY_APPROVAL_THRESHOLD", "DISCOVERY_PHASE1_SEARCH_ALLOWANCE"],
)
def test_a_negative_count_is_refused(monkeypatch, tmp_path, name):
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv(name, "-1")

    with pytest.raises(ConfigError, match="cannot be negative"):
        Settings.from_env()


def test_a_price_that_is_not_a_number_is_refused_with_the_offending_value(monkeypatch, tmp_path):
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv("DISCOVERY_SEARCH_COST_USD", "five cents")

    with pytest.raises(ConfigError, match="must be a decimal number of US dollars, got 'five cents'"):
        Settings.from_env()


def test_a_negative_price_is_refused(monkeypatch, tmp_path):
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv("DISCOVERY_INPUT_COST_USD_PER_MTOK", "-0.14")

    with pytest.raises(ConfigError, match="is a price and cannot be negative"):
        Settings.from_env()


def test_a_deployment_can_override_every_engine_setting(monkeypatch, tmp_path):
    """The engine's own values are deployment values too, and none may be a
    literal in source: the model and its price move independently of this code,
    and the output reservation is what a provider refuses a request against."""
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv("DISCOVERY_MODEL", "probe/model-under-test")
    monkeypatch.setenv("DISCOVERY_MAX_OUTPUT_TOKENS", "1234")
    monkeypatch.setenv("DISCOVERY_SEARCH_RESULTS", "6")
    monkeypatch.setenv("DISCOVERY_SEARCH_ENGINE", "exa")

    settings = Settings.from_env()

    assert settings.discovery_model == "probe/model-under-test"
    assert settings.discovery_max_output_tokens == 1234
    assert settings.discovery_search_results == 6
    assert settings.discovery_search_engine == "exa"


def test_a_search_engine_is_always_resolved_to_a_name(monkeypatch, tmp_path):
    """Blank and absent both mean the chosen engine, and neither may mean "none".

    Leaving the engine unset does not select a neutral default — it hands the
    choice to whichever model is configured, because the provider resolves an
    absent engine to that model provider's own native search where it has one and
    to Exa where it does not. A deployment changing `DISCOVERY_MODEL` would then
    silently change how the product searches, which is the thing pinning exists
    to stop.
    """
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.delenv("DISCOVERY_SEARCH_ENGINE", raising=False)

    assert Settings.from_env().discovery_search_engine == "parallel"

    monkeypatch.setenv("DISCOVERY_SEARCH_ENGINE", "")

    assert Settings.from_env().discovery_search_engine == "parallel", "blank is unset, not a request for no engine"


def test_the_chosen_engine_is_the_one_the_comparison_selected(monkeypatch, tmp_path):
    """Parallel, on measured cost at indistinguishable quality.

    Across sixteen "resolve a named work to its holding museum" cases and a
    recency-bound intent, Exa, Parallel and Perplexity each found the institution
    every time. Parallel bills a fifth of what the other two do per request, which
    made the measured comparison run four times cheaper for the same results.
    """
    monkeypatch.setenv("ART_ROOT", str(tmp_path))

    assert Settings.from_env().discovery_search_engine == "parallel"


def test_the_engine_settings_ship_at_the_values_the_analysis_chose(monkeypatch, tmp_path):
    """A floating model alias, and a search breadth of ten because breadth is free.

    The fee is charged per search request and was measured identical at one,
    three, five and ten results, so a lower default would save nothing and see
    less. The alias is floating rather than a dated snapshot so a snapshot
    retirement cannot break the product's only paid path.
    """
    monkeypatch.setenv("ART_ROOT", str(tmp_path))

    settings = Settings.from_env()

    assert settings.discovery_model == "deepseek/deepseek-v4-flash"
    assert ":" not in settings.discovery_model, "a dated snapshot pin, not the floating alias"
    assert settings.discovery_search_results == 10


def test_the_conversation_has_its_own_model_and_reservation(monkeypatch, tmp_path):
    """A third model, and neither of the other two would do.

    `DISCOVERY_MODEL` lists `input_modalities: ["text"]` and cannot see a
    picture; the mat reservation is sized to let a reasoning model finish, and a
    conversational turn switches reasoning off instead. One setting for all three
    would make each choice a constraint on the others.
    """
    monkeypatch.setenv("ART_ROOT", str(tmp_path))

    settings = Settings.from_env()

    assert settings.conversation_model == "qwen/qwen3.7-flash"
    assert ":" not in settings.conversation_model, "a dated snapshot pin, not the floating alias"
    assert settings.conversation_max_output_tokens == 2_000

    monkeypatch.setenv("CONVERSATION_MODEL", "probe/model-under-test")
    monkeypatch.setenv("CONVERSATION_MAX_OUTPUT_TOKENS", "512")
    overridden = Settings.from_env()

    assert overridden.conversation_model == "probe/model-under-test"
    assert overridden.conversation_max_output_tokens == 512


def test_the_conversation_reservation_must_be_positive(monkeypatch, tmp_path):
    """Same reason as the other two: a request reserving nothing is refused."""
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv("CONVERSATION_MAX_OUTPUT_TOKENS", "0")

    with pytest.raises(ConfigError, match="CONVERSATION_MAX_OUTPUT_TOKENS"):
        Settings.from_env()


def test_the_output_reservation_must_be_positive(monkeypatch, tmp_path):
    """There is no coherent request that reserves no output, and the provider
    refuses one rather than running it cheaply."""
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv("DISCOVERY_MAX_OUTPUT_TOKENS", "0")

    with pytest.raises(ConfigError, match="DISCOVERY_MAX_OUTPUT_TOKENS"):
        Settings.from_env()


def test_the_api_key_is_absent_rather_than_empty_when_unset(monkeypatch, tmp_path):
    """`None` is what the entry point tests to decide whether discovery can run,
    and an empty string would be truthy-adjacent enough to invite a bug."""
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv("OPENROUTER_API_KEY", "")

    assert Settings.from_env().openrouter_api_key is None


def test_the_api_key_never_appears_in_the_redacted_configuration(monkeypatch, tmp_path):
    """Driven off the declaration rather than a remembered list, so declaring a
    new secret is what gets it redacted — and checked."""
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-should-never-be-logged")

    redacted = Settings.from_env().redacted()

    assert "sk-or-v1-should-never-be-logged" not in str(redacted)
    assert redacted["openrouter_api_key"] == "<set>"
    assert set(redacted) == set(Settings.__dataclass_fields__), "every field is accounted for, secret or not"
