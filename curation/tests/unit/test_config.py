"""Deployment configuration resolution.

The values here differ between the dev Mac and the Pi, so the failure this
module exists to prevent is a plausible-looking default that quietly writes the
catalogue somewhere unintended. These tests assert the refusals, not just the
happy path.
"""

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
