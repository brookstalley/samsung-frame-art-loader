"""Deployment configuration resolution.

The values here differ between the dev Mac and the Pi, so the failure this
module exists to prevent is a plausible-looking default that quietly writes the
catalogue somewhere unintended. These tests assert the refusals, not just the
happy path.
"""

from decimal import Decimal

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
from curation.manifest.builder import MANIFEST_FILENAME
from curation.manifest.heartbeat import HEARTBEAT_FILENAME


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Resolve from this process's environment and nothing else.

    `from_env` calls `load_dotenv(override=True)` with no path, and dotenv
    searches from `config.py`'s own directory upward — never the cwd — so
    chdir'ing to a scratch directory isolates nothing. With `override=True` a
    real `.env` beats every value set here, and the documented setup step
    (`cp .env.example .env`) creates exactly that file: without this stub the
    whole module is green only on a machine where nobody has followed the
    README.
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


def test_the_manifest_and_heartbeat_are_anchored_under_art_root(monkeypatch, tmp_path):
    """Both planes have to agree where these are, so neither is configurable."""
    monkeypatch.setenv("ART_ROOT", str(tmp_path))

    settings = Settings.from_env()

    assert settings.manifest_path == tmp_path / MANIFEST_FILENAME
    assert settings.heartbeat_path == tmp_path / HEARTBEAT_FILENAME


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

    The cost analysis these values come from records a bounded run at $0.11–$0.33
    and its search component at $0.15–0.25 on a $0.005 engine. Those figures were
    arrived at independently of this code; if the shipped settings cannot
    reproduce them, one of the two is wrong and a curator is authorising against
    a number that describes nothing.

    Computed here rather than compared against a copied total, so the assertion
    fails when the composition changes rather than tracking it.
    """
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    discovery = Settings.from_env().discovery_settings

    # A typical run finds about twenty works. Bounded, so this is the ceiling
    # rather than the expectation.
    typical_works = 20
    searches = discovery.phase1_search_allowance + typical_works * discovery.phase2_searches_per_work
    search_spend = searches * discovery.search_cost_usd
    run_total = discovery.phase1_estimate_usd + discovery.phase2_estimate_usd(typical_works)

    assert searches == 50
    assert search_spend == Decimal("0.250"), "the search component's recorded ceiling"
    assert run_total == Decimal("0.327"), "a bounded run, against a recorded range topping out at $0.33"
    # The model call alone, against a table recording roughly eight cents.
    assert Decimal("0.07") < run_total - search_spend < Decimal("0.08")


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
    assert discovery.phase2_estimate_usd(10) == Decimal("0.030")


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
