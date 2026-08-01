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

from curation.manifest.builder import MANIFEST_FILENAME
from curation.manifest.heartbeat import HEARTBEAT_FILENAME
from curation.services.display_fit import ArtworkBox

#: The catalogue's filename under `ART_ROOT`. Not configurable: both planes
#: and the backup path need to agree on where the catalogue is, and a setting
#: is just a way for them to stop agreeing.
CATALOGUE_FILENAME: Final[str] = "catalogue.sqlite"

#: Where thumbnails are cached under `ART_ROOT`. Derived and device-independent:
#: regenerated on whatever machine needs them, never copied between machines.
THUMBNAILS_DIRNAME: Final[str] = "thumbs"

DEFAULT_HOST: Final[str] = "127.0.0.1"
DEFAULT_PORT: Final[int] = 8770

#: What the wall does for a theme that has expressed no pace of its own. Carried
#: forward from the 2024 plane, which ran the wall at three minutes on shuffle —
#: this is the behaviour on the wall today, and changing it silently at cutover
#: would be a regression nobody asked for.
DEFAULT_ROTATION_INTERVAL_SECONDS: Final[int] = 180
DEFAULT_ROTATION_SHUFFLE: Final[bool] = True

#: The reference deployment is a 42" Frame at 4K, but nothing may hardcode a
#: panel: the mat is specified in physical units and the resolution floor is a
#: minimum size on the wall, so both are wrong on a different television. These
#: are defaults for the reference panel, overridable per deployment.
DEFAULT_TV_PANEL_WIDTH_PX: Final[int] = 3840
DEFAULT_TV_PANEL_HEIGHT_PX: Final[int] = 2160
DEFAULT_TV_PANEL_DIAGONAL_INCHES: Final[float] = 42.0

#: The mat's width on the sides and top, in inches on the wall. Physical units
#: rather than pixels or a ratio, so it means the same thing on any panel.
DEFAULT_MAT_WIDTH_INCHES: Final[float] = 2.5

#: How much deeper the bottom margin is than the top. A true-centred image reads
#: as sitting low, so conservators weight the bottom — the convention this
#: product's mat is specified against.
DEFAULT_MAT_BOTTOM_WEIGHT: Final[float] = 1.15

#: The smallest a work may render along its long edge, in inches on the wall,
#: before it is labelled as below the floor. Below-floor works are shown and
#: remain selectable; the floor is a warning, never a filter.
DEFAULT_RESOLUTION_FLOOR_INCHES: Final[float] = 12.0


class ConfigError(RuntimeError):
    """A required deployment value is missing or unusable."""


@dataclass(frozen=True, slots=True)
class Settings:
    """The resolved deployment values the curation plane runs on."""

    art_root: Path
    catalogue_path: Path
    manifest_path: Path
    heartbeat_path: Path
    host: str
    port: int
    rotation_interval_seconds: int
    rotation_shuffle: bool
    #: The **television's** panel, never the e-paper one. Curation composes the
    #: mat and judges whether a source is large enough for the wall, so it needs
    #: the TV's physical size; it must hold no fact about the label panel, which
    #: belongs to the plane that owns it.
    tv_panel_width_px: int
    tv_panel_height_px: int
    tv_panel_diagonal_inches: float
    #: The mat's geometry, in inches on the wall, and the floor judged against it.
    mat_width_inches: float
    mat_bottom_weight: float
    resolution_floor_inches: float

    @property
    def thumbnails_path(self) -> Path:
        """Where the browser surface's thumbnails are cached.

        Derived and device-independent, so it is regenerated rather than
        transported. Deliberately **not** `tv-thumbs/`, which holds images
        downloaded from the television keyed by its own content ids — per-device
        television state, the class this catalogue exists to keep out.
        """
        return self.art_root / THUMBNAILS_DIRNAME

    @property
    def tv_pixels_per_inch(self) -> float:
        """Canvas pixels to an inch on the wall, from the panel's own geometry.

        Derived rather than configured: a diagonal and a pixel count already fix
        it, and a third setting that could disagree with the other two is a way
        for a deployment to be quietly wrong about how big anything is.
        """
        diagonal_px = (self.tv_panel_width_px**2 + self.tv_panel_height_px**2) ** 0.5
        return diagonal_px / self.tv_panel_diagonal_inches

    @property
    def tv_artwork_box(self) -> ArtworkBox:
        """The region of the television canvas an artwork is rendered into.

        Composed here because every input is a deployment value: the panel, the
        mat in inches, and the floor. The bottom margin is deeper than the top,
        so the vertical mat is not twice the horizontal one — a work judged
        against a four-equal-sides approximation would be reported as larger on
        the wall than it will actually appear.

        **The mat is rounded to whole pixels before anything is subtracted, and
        the bottom margin is derived from that rounded top.** A mat is drawn in
        pixels, so this is the arithmetic the compositor will do; carrying
        fractions through and rounding at the end gives a box a pixel or two
        different from the one that ends up on the panel. On the reference 42"
        4K Frame it reproduces `nonfunctional-requirements.md`'s own worked
        example exactly — 262 px of mat, a 3316 x 1597 box — which is the
        strongest available evidence that the default bottom weighting matches
        what that example was drawn from.
        """
        top_mat_px = round(self.mat_width_inches * self.tv_pixels_per_inch)
        bottom_mat_px = round(top_mat_px * self.mat_bottom_weight)
        return ArtworkBox(
            width=max(1, self.tv_panel_width_px - 2 * top_mat_px),
            height=max(1, self.tv_panel_height_px - top_mat_px - bottom_mat_px),
            pixels_per_inch=self.tv_pixels_per_inch,
            floor_inches=self.resolution_floor_inches,
        )

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
            manifest_path=art_root / MANIFEST_FILENAME,
            heartbeat_path=art_root / HEARTBEAT_FILENAME,
            # Loopback by default: the plane is reached over an overlay network
            # rather than by being exposed on the LAN, and a default that binds
            # every interface is a decision no one made.
            host=os.environ.get("CURATION_HOST") or DEFAULT_HOST,
            port=_port("CURATION_PORT", DEFAULT_PORT),
            rotation_interval_seconds=_positive_int("ROTATION_INTERVAL_SECONDS", DEFAULT_ROTATION_INTERVAL_SECONDS),
            rotation_shuffle=_flag("ROTATION_SHUFFLE", DEFAULT_ROTATION_SHUFFLE),
            tv_panel_width_px=_positive_int("TV_PANEL_WIDTH_PX", DEFAULT_TV_PANEL_WIDTH_PX),
            tv_panel_height_px=_positive_int("TV_PANEL_HEIGHT_PX", DEFAULT_TV_PANEL_HEIGHT_PX),
            tv_panel_diagonal_inches=_positive_float("TV_PANEL_DIAGONAL_INCHES", DEFAULT_TV_PANEL_DIAGONAL_INCHES),
            mat_width_inches=_positive_float("MAT_WIDTH_INCHES", DEFAULT_MAT_WIDTH_INCHES),
            mat_bottom_weight=_positive_float("MAT_BOTTOM_WEIGHT", DEFAULT_MAT_BOTTOM_WEIGHT),
            resolution_floor_inches=_positive_float("RESOLUTION_FLOOR_INCHES", DEFAULT_RESOLUTION_FLOOR_INCHES),
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


def _positive_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a whole number, got {raw!r}. Check .env.") from exc
    if value <= 0:
        raise ConfigError(f"{name} must be greater than zero, got {value}. Check .env.")
    return value


def _positive_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number, got {raw!r}. Check .env.") from exc
    if value <= 0:
        raise ConfigError(f"{name} must be greater than zero, got {value}. Check .env.")
    return value


def _flag(name: str, default: bool) -> bool:
    """Read a boolean, refusing anything that is not unmistakably one.

    Python's `bool("false")` is True, so a lenient reader turns a deliberate
    "off" into "on" and reports nothing. Every accepted spelling is listed.
    """
    raw = os.environ.get(name)
    if not raw:
        return default
    text = raw.strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"{name} must be true or false, got {raw!r}. Check .env.")
