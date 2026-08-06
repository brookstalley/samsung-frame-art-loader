"""Deployment configuration for the display plane.

Every value here differs between the dev Mac and the Pi, so none of them may be a
literal in source. A fresh checkout runs by copying `.env.example` to `.env` and
filling it in — never by editing a module. Both planes read that one file: the
value they must agree on is `ART_ROOT`, and two files are precisely how two
planes come to disagree about it.

Resolution is a function rather than module-level constants, so importing this
module does not require an environment — otherwise the test suite and every tool
that merely wants to read a docstring would need one. Fail-fast is preserved by
resolving at process start, which is where a missing value should stop things.

**This plane knows nothing about the television's physical size.** The mat is
already composed into the render it is handed, so the only panel geometry here is
the e-paper label's, and a value for the TV's diagonal appearing in this file
would be the cross-plane drift `operational-spec.md` § Configuration warns about.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from dotenv import load_dotenv

#: The manifest's filename under `ART_ROOT`. **Not configurable, deliberately**:
#: this is the name of the only channel between the planes, and a setting is just
#: a way for the writer and the reader to stop agreeing about where it is. It is
#: written here as a literal rather than imported from the plane that writes it,
#: because importing that plane is the thing the isolation norm forbids.
MANIFEST_FILENAME: Final[str] = "theme-manifest.json"

#: This plane's own store, under `ART_ROOT` beside the manifest it reads. Display
#: is its sole writer and nothing else ever opens it.
STATE_FILENAME: Final[str] = "display-state.sqlite"

#: The name this process pairs to the television under. **Changing it costs a
#: pairing prompt somebody has to walk over and accept**: the set issues a token
#: per client name, so a new name is a new client to it and the existing token in
#: `TV_TOKEN_FILE` will not be honoured. It is `tvpi` because that is the name the
#: 2024 loader paired under, and the cutover replacing that process should
#: continue as the same client rather than arrive as a stranger.
DEFAULT_TV_CLIENT_NAME: Final[str] = "tvpi"

#: The e-paper label panel, in pixels. Defaults are the reference deployment's
#: 1448×1072 IT8951; overridable because nothing may hardcode a panel's size —
#: this product must run on any panel, and the 2024 plane's baked-in 648×480 is
#: the anti-pattern being retired.
DEFAULT_EPD_PANEL_WIDTH_PX: Final[int] = 1448
DEFAULT_EPD_PANEL_HEIGHT_PX: Final[int] = 1072

#: How often the manifest's mtime is read. **Set by `next`, not by theme
#: switching** — a theme change tolerates seconds of latency happily, while a
#: human pressing "next" and waiting three seconds thinks the product is broken.
#: One `stat()` a second is free.
DEFAULT_POLL_INTERVAL_SECONDS: Final[float] = 1.0

#: Fallbacks for rotation, used only when a manifest carries no usable values.
#: The manifest normally resolves them — curation writes the theme's settings or
#: the deployment default into every one it publishes — so these are the answer
#: to "the file said nothing", not a second place the pace is configured.
DEFAULT_ROTATION_INTERVAL_SECONDS: Final[int] = 180
DEFAULT_ROTATION_SHUFFLE: Final[bool] = True

#: The television's brightness scale, which is neither 0-100 nor 0-10: this set
#: takes -4 through 10, and the sun-position curve is mapped onto that range.
#: Carried forward from the 2024 plane, which runs the wall on these numbers.
DEFAULT_TV_MIN_BRIGHTNESS: Final[int] = -4
DEFAULT_TV_MAX_BRIGHTNESS: Final[int] = 10

#: How often the sun is re-consulted. The sun moves slowly and the scale above
#: has fifteen steps, so anything under a minute would compute the same answer
#: repeatedly; five minutes puts a step boundary within half a step of when it
#: is due. The television is only written to when the computed value *changes*,
#: so this interval costs a local calculation and no traffic.
DEFAULT_BRIGHTNESS_INTERVAL_SECONDS: Final[float] = 300.0

#: The wait for the set's `image_added` acknowledgement. **A correctness value,
#: not a tuning knob**: the library's own default of 10 seconds was measured
#: failing on this deployment's 4K composites while the image landed anyway, so a
#: caller at the default is told an upload failed that succeeded, and a retry
#: duplicates it on the wall. Sized well above the 8.4 s a real upload measured.
DEFAULT_UPLOAD_TIMEOUT_SECONDS: Final[float] = 60.0

#: The ceiling on opening the art channel. `start_listening()` has been observed
#: **hanging** rather than raising when the set is not in art mode, so a caller
#: that does not impose its own bound never returns at all — which for an
#: unattended daemon is a wedge, not an error.
DEFAULT_TV_CONNECT_TIMEOUT_SECONDS: Final[float] = 30.0

#: How long a work whose upload failed is left alone before it is tried again.
#: **A television that is reachable and refuses one image is a different fault
#: from one that is asleep**, and it does not back off with the connection: the
#: pass would otherwise retry it every second, each attempt costing a round trip,
#: a WARNING and a row rewritten. `observability-strategy.md` sizes writes on this
#: medium deliberately, and an unbounded small-write source on an SD card is the
#: thing it says not to build. Wall time rather than elapsed, so the wait survives
#: a restart — a crash loop must not turn into a retry loop.
DEFAULT_UPLOAD_RETRY_SECONDS: Final[float] = 300.0

#: Reconnection backoff after the television goes away. An asleep set is the
#: expected operating condition rather than an incident, so the ceiling is low
#: enough that the wall resumes promptly when someone turns it on and high enough
#: that a night of standby is not a night of connection attempts.
DEFAULT_TV_RETRY_MIN_SECONDS: Final[float] = 5.0
DEFAULT_TV_RETRY_MAX_SECONDS: Final[float] = 300.0


class ConfigError(RuntimeError):
    """A deployment value is missing or unusable, and starting would be worse."""


@dataclass(frozen=True)
class Settings:
    """Everything this plane needs from its environment, resolved once."""

    art_root: Path
    tv_address: str
    tv_port: int
    tv_token_file: Path
    tv_client_name: str

    #: The **e-paper label** panel, never the television's. This plane is handed
    #: a composed canvas and never needs the TV's size; holding one here is how
    #: the two panels' geometry came to be confused in the first place.
    epd_panel_width_px: int
    epd_panel_height_px: int

    latitude: float
    longitude: float
    location_name: str
    location_region: str

    tv_min_brightness: int
    tv_max_brightness: int

    poll_interval_seconds: float
    brightness_interval_seconds: float
    upload_timeout_seconds: float
    upload_retry_seconds: float
    tv_connect_timeout_seconds: float
    tv_retry_min_seconds: float
    tv_retry_max_seconds: float

    rotation_interval_fallback_seconds: int
    rotation_shuffle_fallback: bool

    @property
    def manifest_path(self) -> Path:
        """The one channel from curation, and the only file this plane waits on."""
        return self.art_root / MANIFEST_FILENAME

    @property
    def state_path(self) -> Path:
        """This plane's own store. Display is its sole writer."""
        return self.art_root / STATE_FILENAME

    def startup_lines(self) -> dict[str, object]:
        """What goes in the startup log line, so a misconfiguration is one line away.

        `ART_ROOT` and this plane's own panel geometry, per
        `operational-spec.md` § Configuration — a wrong art root otherwise shows
        up as a manifest that never arrives, and a wrong panel as a label that
        renders off the edge of a display nobody is looking at closely.

        No secret is resolvable from these, and none is added: this plane reaches
        no paid API and holds no key. The pairing token is a **path** here, never
        its contents.
        """
        return {
            "art_root": str(self.art_root),
            "manifest_path": str(self.manifest_path),
            "state_path": str(self.state_path),
            "epd_panel_px": f"{self.epd_panel_width_px}x{self.epd_panel_height_px}",
            "tv_address": f"{self.tv_address}:{self.tv_port}",
            "tv_token_file": str(self.tv_token_file),
            "tv_client_name": self.tv_client_name,
        }


def load(environ: dict[str, str] | None = None) -> Settings:
    """Resolve the environment into `Settings`, or refuse to start.

    `environ` is injectable so tests do not have to mutate the process's own — a
    test that set `ART_ROOT` globally would leak it into every test after it.
    """
    load_dotenv()
    env = dict(os.environ) if environ is None else environ

    art_root = Path(_require(env, "ART_ROOT")).expanduser()
    if not art_root.is_dir():
        # A typo is invisible in `.env` and obvious the moment something reads it
        # back. Refusing here rather than at first use matters because the
        # alternative failure is *silence*: a mistyped root means a manifest that
        # never appears, which is indistinguishable from a curation plane that
        # has not published one yet — the daemon would wait politely forever.
        raise ConfigError(
            f"ART_ROOT is {art_root}, which is not an existing directory. "
            "Fix ART_ROOT in .env; a typo here shows up as a manifest that never arrives, "
            "which looks exactly like a curation plane that has not published one yet."
        )

    token_file = env.get("TV_TOKEN_FILE") or ""
    return Settings(
        art_root=art_root,
        tv_address=_require(env, "TV_ADDRESS"),
        tv_port=_int(env, "TV_PORT", 8002),
        tv_token_file=Path(token_file).expanduser() if token_file else art_root / "token_file",
        tv_client_name=env.get("TV_CLIENT_NAME") or DEFAULT_TV_CLIENT_NAME,
        epd_panel_width_px=_int(env, "EPD_PANEL_WIDTH_PX", DEFAULT_EPD_PANEL_WIDTH_PX),
        epd_panel_height_px=_int(env, "EPD_PANEL_HEIGHT_PX", DEFAULT_EPD_PANEL_HEIGHT_PX),
        latitude=_float(env, "LATITUDE", None),
        longitude=_float(env, "LONGITUDE", None),
        location_name=_require(env, "LOCATION_NAME"),
        location_region=env.get("LOCATION_REGION") or "",
        tv_min_brightness=_int(env, "TV_MIN_BRIGHTNESS", DEFAULT_TV_MIN_BRIGHTNESS),
        tv_max_brightness=_int(env, "TV_MAX_BRIGHTNESS", DEFAULT_TV_MAX_BRIGHTNESS),
        poll_interval_seconds=_float(env, "MANIFEST_POLL_SECONDS", DEFAULT_POLL_INTERVAL_SECONDS),
        brightness_interval_seconds=_float(env, "BRIGHTNESS_INTERVAL_SECONDS", DEFAULT_BRIGHTNESS_INTERVAL_SECONDS),
        upload_timeout_seconds=_float(env, "TV_UPLOAD_TIMEOUT_SECONDS", DEFAULT_UPLOAD_TIMEOUT_SECONDS),
        upload_retry_seconds=_float(env, "TV_UPLOAD_RETRY_SECONDS", DEFAULT_UPLOAD_RETRY_SECONDS),
        tv_connect_timeout_seconds=_float(env, "TV_CONNECT_TIMEOUT_SECONDS", DEFAULT_TV_CONNECT_TIMEOUT_SECONDS),
        tv_retry_min_seconds=_float(env, "TV_RETRY_MIN_SECONDS", DEFAULT_TV_RETRY_MIN_SECONDS),
        tv_retry_max_seconds=_float(env, "TV_RETRY_MAX_SECONDS", DEFAULT_TV_RETRY_MAX_SECONDS),
        rotation_interval_fallback_seconds=_int(env, "ROTATION_INTERVAL_SECONDS", DEFAULT_ROTATION_INTERVAL_SECONDS),
        rotation_shuffle_fallback=_bool(env, "ROTATION_SHUFFLE", DEFAULT_ROTATION_SHUFFLE),
    )


def _require(env: dict[str, str], name: str) -> str:
    value = env.get(name)
    if not value:
        raise ConfigError(f"{name} is not set. Copy .env.example to .env and fill it in.")
    return value


def _int(env: dict[str, str], name: str, default: int | None) -> int:
    raw = env.get(name)
    if not raw:
        if default is None:
            raise ConfigError(f"{name} is not set. Copy .env.example to .env and fill it in.")
        return default
    try:
        return int(raw)
    except ValueError as exc:
        # Refused rather than defaulted: a value somebody typed and got wrong is
        # a different thing from one they never typed, and quietly substituting
        # the default hides the typo behind behaviour that looks deliberate.
        raise ConfigError(f"{name} is {raw!r}, which is not a whole number.") from exc


def _float(env: dict[str, str], name: str, default: float | None) -> float:
    raw = env.get(name)
    if not raw:
        if default is None:
            raise ConfigError(f"{name} is not set. Copy .env.example to .env and fill it in.")
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} is {raw!r}, which is not a number.") from exc


def _bool(env: dict[str, str], name: str, default: bool) -> bool:
    raw = env.get(name)
    if not raw:
        return default
    return raw.strip().lower() not in {"false", "0", "no", "off"}
