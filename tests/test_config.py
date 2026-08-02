"""Config resolves from the environment, fails fast, and never logs a secret.

`config` reads the environment at import, so every test here reloads the module
under a controlled environment rather than mutating already-bound values.
"""

import ast
import importlib
import logging
import pathlib
import sys

import pytest

MINIMAL_ENV = {
    "ART_ROOT": "/tmp/art-root-under-test",
    "TV_ADDRESS": "192.0.2.10",
    "LATITUDE": "47.606",
    "LONGITUDE": "-122.332",
    "LOCATION_NAME": "Testville",
}

#: Every optional variable cleared before `config` is imported, so a developer's
#: own shell cannot change what these tests observe. The secrets are the
#: load-bearing half, and they are not left to memory:
#: `test_the_harness_clears_every_declared_secret` fails if `_SECRET_KEYS` grows
#: past this list, which is what keeps a redaction assertion from passing or
#: failing on an untracked environment rather than on the code.
#:
#: This is every optional variable `config` reads, not a remembered subset —
#: `EPD_TYPE` was missing until 2026-08-02, so `load_config`'s promise below was
#: false for it and a developer with an e-paper type exported ran these tests
#: against a different resolved config than CI did.
OPTIONAL_ENV = (
    "TV_PORT",
    "TV_TOKEN_FILE",
    "LOCATION_REGION",
    "USE_ART_LABEL",
    "EPD_TYPE",
    "OPENAI_KEY",
    "OPENROUTER_API_KEY",
)


def load_config(monkeypatch, **overrides):
    """Import `config` fresh under exactly the given environment."""
    for key in list(MINIMAL_ENV) + list(OPTIONAL_ENV):
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
    # Both planes, not just the 2024 modules at the root. The curation plane is
    # precisely the code that has to run unchanged on the Pi and on a dev Mac
    # once the legacy modules are retired, and this test is the enforcement
    # artifact `project-preferences.md` names for that norm — so a plane it never
    # walks is a norm nobody is checking.
    modules = sorted(repository_root.glob("*.py"))
    for plane in ("curation/src", "display/src"):
        modules.extend(sorted((repository_root / plane).rglob("*.py")))
    assert modules, f"expected the 2024 modules at {repository_root}; has the layout moved?"
    assert any(
        "curation/src" in str(path) for path in modules
    ), f"expected the curation plane under {repository_root}/curation/src; has the layout moved?"

    offenders = []
    for path in modules:
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue  # documentation of an example value is fine
            if forbidden.search(line):
                offenders.append(f"{path}:{number}: {stripped}")
    assert not offenders, "deployment values must live in .env, not source:\n" + "\n".join(offenders)


def test_the_harness_clears_every_variable_config_reads():
    """`load_config` promises "exactly the given environment". Hold it to that.

    Guards the **harness**, not a product norm — there is deliberately no norm
    index row for it, because what it protects is these tests' own isolation.

    The sibling below closes the same drift for `_SECRET_KEYS` and cannot close
    this one: those names are read through a loop variable, so no scan for string
    literals will ever see them, and this scan cannot see them either. The two
    guards are complementary and neither subsumes the other.

    One-directional on purpose. Every name `config` reads must be cleared; the
    reverse does not hold, because `OPENROUTER_API_KEY` is legitimately in
    `OPTIONAL_ENV` and appears in `config.py` only inside `_SECRET_KEYS`.
    """
    source = (pathlib.Path(__file__).resolve().parent.parent / "config.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    read: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        # `os.environ.get("X")`, `os.getenv("X")`, a bare `getenv("X")`, and
        # `_require*("X")`. Wider than the spellings `config.py` uses today, on
        # purpose: a scan that covers only current usage reports "covered" for
        # the first variable added a different way, and `_require` keeps the set
        # non-empty so the `assert read` canary below would not fire either —
        # silently reintroducing the exact drift this guard exists to catch.
        named = (isinstance(target, ast.Attribute) and target.attr in {"get", "getenv"}) or (
            isinstance(target, ast.Name) and (target.id.startswith("_require") or target.id == "getenv")
        )
        if named and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            read.add(node.args[0].value)
    for node in ast.walk(tree):
        # `os.environ["X"]`, which config.py does not use today and which would
        # otherwise slip past the call scan above.
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
            if isinstance(node.value, ast.Attribute) and node.value.attr == "environ":
                read.add(node.slice.value)

    assert read, "found no environment reads in config.py; has the resolution style moved?"
    uncleared = sorted(read - set(MINIMAL_ENV) - set(OPTIONAL_ENV))
    assert not uncleared, (
        f"config.py reads these and the harness never clears them: {uncleared}. "
        "A developer with one exported runs this suite against a different resolved config "
        "than CI does. Add each to MINIMAL_ENV (required) or OPTIONAL_ENV (optional)."
    )


def test_the_harness_clears_every_declared_secret(monkeypatch):
    """The two lists above must not drift apart, and only this notices if they do.

    A secret declared in `_SECRET_KEYS` but absent from `OPTIONAL_ENV` is never
    cleared, so it reads as whatever the developer's own shell holds — and the
    redaction tests below would then be asserting against an untracked file
    instead of against the code.
    """
    config = load_config(monkeypatch)
    uncleared = sorted(config._SECRET_KEYS - set(OPTIONAL_ENV))
    assert not uncleared, f"these secrets are declared but never cleared before import: {uncleared}. Add them to OPTIONAL_ENV."


def test_startup_logging_never_emits_a_secret(monkeypatch, caplog):
    """The carried finding: config is logged at startup, which is where a key leaks.

    Driven from `_SECRET_KEYS` rather than from the one name that happened to
    exist when this was written. `redacted_config()` already walks that
    frozenset, so a secret added there and nowhere else was covered by the code
    and by nothing that checked it — which is how a Test row quietly becomes a
    claim. Reading the declaration means the guard grows with it.
    """
    declared = sorted(load_config(monkeypatch)._SECRET_KEYS)
    assert declared, "config declares no secrets at all; has the redaction list moved?"

    for name in declared:
        secret = f"sk-do-not-log-me-{name.lower()}"
        config = load_config(monkeypatch, **{name: secret})

        caplog.clear()
        with caplog.at_level(logging.INFO):
            config.log_resolved_config()

        emitted = "\n".join(record.getMessage() for record in caplog.records)
        assert emitted, "startup logging must actually emit something"
        assert secret not in emitted, f"{name}'s value reached a log line"
        assert f"{name}=<set>" in emitted, f"{name}'s presence is reported; its value is not"
        # The non-secret values are the point of logging at all.
        assert MINIMAL_ENV["ART_ROOT"] in emitted


def test_redacted_config_reports_absent_secrets_without_inventing_them(monkeypatch):
    config = load_config(monkeypatch)
    for name in sorted(config._SECRET_KEYS):
        assert config.redacted_config()[name] == "<unset>", f"{name} is unset and must not be reported as present"
