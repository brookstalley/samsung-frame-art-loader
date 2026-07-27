"""Deployment configuration for the curation plane.

Every value here differs between the dev Mac and the Pi, so none of them may
be a literal in source. A fresh checkout runs by copying `.env.example` to
`.env` and filling it in — never by editing a module.

Resolution is a function rather than module-level constants, unlike the 2024
plane's `config.py`, and the difference is deliberate: importing this module
must not require an environment, or the test suite and every tool that merely
wants to read a docstring would need one. Fail-fast is preserved by resolving
at process start, which is where a missing value should stop things.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from dotenv import load_dotenv

#: The catalogue's filename under `ART_ROOT`. Not configurable: both planes
#: and the backup path need to agree on where the catalogue is, and a setting
#: is just a way for them to stop agreeing.
CATALOGUE_FILENAME: Final[str] = "catalogue.sqlite"

DEFAULT_HOST: Final[str] = "127.0.0.1"
DEFAULT_PORT: Final[int] = 8770


class ConfigError(RuntimeError):
    """A required deployment value is missing or unusable."""


@dataclass(frozen=True, slots=True)
class Settings:
    """The resolved deployment values the curation plane runs on."""

    art_root: Path
    catalogue_path: Path
    host: str
    port: int

    @classmethod
    def from_env(cls) -> Settings:
        """Resolve from the environment, failing on anything missing.

        `ART_ROOT` has no default on purpose. A plausible-looking one would
        write the catalogue somewhere unintended and look like it had worked.
        """
        load_dotenv(override=True)
        art_root = Path(_require("ART_ROOT"))
        return cls(
            art_root=art_root,
            catalogue_path=art_root / CATALOGUE_FILENAME,
            # Loopback by default: the plane is reached over an overlay network
            # rather than by being exposed on the LAN, and a default that binds
            # every interface is a decision no one made.
            host=os.environ.get("CURATION_HOST") or DEFAULT_HOST,
            port=_port("CURATION_PORT", DEFAULT_PORT),
        )


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ConfigError(f"{name} is not set. Copy .env.example to .env and set {name}.")
    return value


def _port(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        port = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a whole number, got {raw!r}. Check .env.") from exc
    if not 1 <= port <= 65535:
        raise ConfigError(f"{name} must be between 1 and 65535, got {port}. Check .env.")
    return port
