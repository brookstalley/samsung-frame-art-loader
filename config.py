"""Deployment configuration, read from the environment.

Every value here differs between the dev machine and the Pi, so none of them may
be a literal in source (`project-preferences.md`, "no hardcoded deployment
values"). A fresh clone runs by copying `.env.example` to `.env` and filling it
in — no source edit.

Required values fail fast at import with a message naming the variable and the
file it belongs in. That is deliberate: a missing `ART_ROOT` that quietly
defaulted to something plausible would write the catalogue to the wrong place
and look like it had worked.
"""

import logging
import os
from typing import Final

from dotenv import load_dotenv

# `.env` supplies defaults; anything already exported wins. That is the
# conventional dotenv contract and the only one under which
# `ART_ROOT=/tmp/scratch python -m …` does what it reads as — with the
# precedence inverted, an exported value is discarded in silence rather than
# refused, which is this product's worst failure shape: the wrong data looking
# exactly like the right data.
#
# (This read `override=True` "so we don't use cached values that pipenv loaded".
# Nothing here has used pipenv since the move to uv — there is no Pipfile and no
# other mention of it in the tree — so that reason had outlived its cause.)
load_dotenv()


class ConfigError(RuntimeError):
    """A required deployment value is missing or unusable."""


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ConfigError(f"{name} is not set. Copy .env.example to .env and set {name}.")
    return value


def _require_float(name: str) -> float:
    raw = _require(name)
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number, got {raw!r}. Check .env.") from exc


# --- Secrets -----------------------------------------------------------------
# Optional: only the code paths that call a given provider need its key.
OPENAI_KEY: Final[str | None] = os.environ.get("OPENAI_KEY")

# Names whose values must never reach a log line. Consulted by
# `redacted_config()`, so a new secret is declared here once rather than
# remembered at each logging call site.
_SECRET_KEYS: Final[frozenset[str]] = frozenset({"OPENAI_KEY", "OPENROUTER_API_KEY"})

# --- Storage -----------------------------------------------------------------
ART_ROOT: Final[str] = _require("ART_ROOT")

art_folder_raw: Final[str] = f"{ART_ROOT}/raw"
art_folder_ready: Final[str] = f"{ART_ROOT}/ready"
art_folder_tv_thumbs: Final[str] = f"{ART_ROOT}/tv-thumbs"
art_folder_label: Final[str] = f"{ART_ROOT}/label"
art_folder_temp: Final[str] = f"{ART_ROOT}/temp"
cache_folder: Final[str] = f"{ART_ROOT}/api-cache"
dezoomify_tile_cache: Final[str] = f"{ART_ROOT}/tile-cache"

# Anchored under ART_ROOT rather than the process CWD. Both were bare relative
# paths, so their meaning depended on where the process happened to be started
# from — and `token_file` in particular resolved inside the checkout, which is
# how it came to be committed.
upload_list_path: Final[str] = f"{ART_ROOT}/uploaded_files.json"
tv_token_file: Final[str] = os.environ.get("TV_TOKEN_FILE") or f"{ART_ROOT}/token_file"

# --- Television --------------------------------------------------------------
tv_address: Final[str] = _require("TV_ADDRESS")
# A protocol default, not a deployment value: 8002 is the Samsung secure
# websocket port and is the same on every installation.
tv_port: Final[int] = int(os.environ.get("TV_PORT") or 8002)

# --- Location (drives sun-position brightness) -------------------------------
latitude: Final[float] = _require_float("LATITUDE")
longitude: Final[float] = _require_float("LONGITUDE")
location_name: Final[str] = _require("LOCATION_NAME")
location_region: Final[str] = os.environ.get("LOCATION_REGION") or ""

# --- Display / label ---------------------------------------------------------
EPD_TYPE: Final[str | None] = os.environ.get("EPD_TYPE")

# Legacy 6" panel geometry, consumed by the 2024 `display.py`. Panel geometry is
# a deployment value and belongs to whichever plane owns the panel; this pair
# moves to the display plane when that plane is built, and is not extended here.
label_width: Final[int] = 648
label_height: Final[int] = 480

use_art_label: Final[bool] = (os.environ.get("USE_ART_LABEL") or "true").lower() not in {"false", "0", "no"}

# --- Behaviour ---------------------------------------------------------------
max_brightness: Final[float] = 10.0
min_brightness: Final[float] = -4.0

# Use strings so leading zeros don't get stripped
auto_artmode_time_on: Final[str] = "0530"
auto_artmode_time_off: Final[str] = "2200"

dezoomify_user_agent: Final[str] = (
    "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36"
)


def redacted_config() -> dict[str, object]:
    """The resolved deployment values, safe to log.

    Secrets are reported as present/absent and never by value. The operational
    spec requires logging resolved configuration at startup, which is exactly
    where a key would otherwise leak into the journal.
    """
    summary: dict[str, object] = {
        "ART_ROOT": ART_ROOT,
        "TV_ADDRESS": tv_address,
        "TV_PORT": tv_port,
        "TV_TOKEN_FILE": tv_token_file,
        "LATITUDE": latitude,
        "LONGITUDE": longitude,
        "LOCATION_NAME": location_name,
        "EPD_TYPE": EPD_TYPE,
        "USE_ART_LABEL": use_art_label,
    }
    for key in sorted(_SECRET_KEYS):
        summary[key] = "<set>" if os.environ.get(key) else "<unset>"
    return summary


def log_resolved_config(logger: logging.Logger | None = None) -> None:
    """Emit the resolved deployment values at startup, secrets redacted."""
    log = logger or logging.getLogger(__name__)
    for key, value in redacted_config().items():
        log.info("config %s=%s", key, value)
