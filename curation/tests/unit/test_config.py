"""Deployment configuration resolution.

The values here differ between the dev Mac and the Pi, so the failure this
module exists to prevent is a plausible-looking default that quietly writes the
catalogue somewhere unintended. These tests assert the refusals, not just the
happy path.
"""

import pytest

from curation.config import CATALOGUE_FILENAME, DEFAULT_HOST, DEFAULT_PORT, ConfigError, Settings


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
    for name in ("ART_ROOT", "CURATION_HOST", "CURATION_PORT"):
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
