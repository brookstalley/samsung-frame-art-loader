"""Config resolves from the environment, fails fast, and never logs a secret.

`config` reads the environment at import, so every test here reloads the module
under a controlled environment rather than mutating already-bound values.
"""

import importlib
import logging
import sys

import pytest

MINIMAL_ENV = {
    "ART_ROOT": "/tmp/art-root-under-test",
    "TV_ADDRESS": "192.0.2.10",
    "LATITUDE": "47.606",
    "LONGITUDE": "-122.332",
    "LOCATION_NAME": "Testville",
}


def load_config(monkeypatch, **overrides):
    """Import `config` fresh under exactly the given environment."""
    for key in list(MINIMAL_ENV) + ["TV_PORT", "TV_TOKEN_FILE", "OPENAI_KEY", "LOCATION_REGION", "USE_ART_LABEL"]:
        monkeypatch.delenv(key, raising=False)
    for key, value in {**MINIMAL_ENV, **overrides}.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    # `load_dotenv(override=True)` would let a developer's real .env leak in and
    # make these assertions depend on an untracked file.
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)
    sys.modules.pop("config", None)
    return importlib.import_module("config")


def test_missing_art_root_fails_fast_and_names_the_file(monkeypatch):
    with pytest.raises(Exception) as exc:
        load_config(monkeypatch, ART_ROOT=None)
    message = str(exc.value)
    assert "ART_ROOT" in message
    assert ".env" in message, "the error must tell the operator where to set it"


def test_missing_tv_address_fails_fast(monkeypatch):
    with pytest.raises(Exception) as exc:
        load_config(monkeypatch, TV_ADDRESS=None)
    assert "TV_ADDRESS" in str(exc.value)


def test_non_numeric_latitude_is_rejected_with_the_offending_value(monkeypatch):
    with pytest.raises(Exception) as exc:
        load_config(monkeypatch, LATITUDE="north-ish")
    message = str(exc.value)
    assert "LATITUDE" in message
    assert "north-ish" in message


def test_paths_are_anchored_under_art_root_not_the_cwd(monkeypatch):
    config = load_config(monkeypatch)
    root = MINIMAL_ENV["ART_ROOT"]
    # These two were bare relative paths, so their meaning depended on where the
    # process was started from — and token_file resolved inside the checkout.
    assert config.upload_list_path.startswith(root)
    assert config.tv_token_file.startswith(root)
    assert not config.tv_token_file.startswith("./")
    for path in (config.art_folder_raw, config.art_folder_ready, config.cache_folder, config.dezoomify_tile_cache):
        assert path.startswith(root)


def test_token_file_path_is_overridable(monkeypatch):
    config = load_config(monkeypatch, TV_TOKEN_FILE="/var/lib/frame/token")
    assert config.tv_token_file == "/var/lib/frame/token"


def test_tv_port_defaults_to_the_protocol_port(monkeypatch):
    assert load_config(monkeypatch).tv_port == 8002
    assert load_config(monkeypatch, TV_PORT="9999").tv_port == 9999


def test_no_source_file_carries_a_deployment_value(monkeypatch):
    """The norm this whole change exists to satisfy, asserted mechanically."""
    import pathlib
    import re

    # The previously-hardcoded values, plus the shape of any absolute home path.
    forbidden = re.compile(r"10\.23\.17\.77|/home/tvpi|/Users/brookstalley|47\.606|-122\.332")
    # Anchored to this file rather than to the working directory: a glob rooted
    # at "." matches nothing when pytest is invoked from elsewhere, and a guard
    # whose whole value is that it cannot be quietly satisfied must not have a
    # green path through checking zero files.
    repository_root = pathlib.Path(__file__).resolve().parent.parent
    modules = sorted(repository_root.glob("*.py"))
    assert modules, f"expected the 2024 modules at {repository_root}; has the layout moved?"

    offenders = []
    for path in modules:
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue  # documentation of an example value is fine
            if forbidden.search(line):
                offenders.append(f"{path}:{number}: {stripped}")
    assert not offenders, "deployment values must live in .env, not source:\n" + "\n".join(offenders)


def test_startup_logging_never_emits_a_secret(monkeypatch, caplog):
    """The carried finding: config is logged at startup, which is where a key leaks."""
    secret = "sk-do-not-log-me-0123456789"
    config = load_config(monkeypatch, OPENAI_KEY=secret)

    with caplog.at_level(logging.INFO):
        config.log_resolved_config()

    emitted = "\n".join(record.getMessage() for record in caplog.records)
    assert emitted, "startup logging must actually emit something"
    assert secret not in emitted
    assert "OPENAI_KEY=<set>" in emitted, "presence is reported; the value is not"
    # The non-secret values are the point of logging at all.
    assert MINIMAL_ENV["ART_ROOT"] in emitted


def test_redacted_config_reports_absent_secrets_without_inventing_them(monkeypatch):
    config = load_config(monkeypatch, OPENAI_KEY=None)
    assert config.redacted_config()["OPENAI_KEY"] == "<unset>"
