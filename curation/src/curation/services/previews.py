"""Local copies of candidate previews, so review never depends on a museum.

The review grid — in the browser and over MCP alike — has to show the picture. A
source-side URL alone means a curator reviewing an hour later sees broken images
when a museum is down or rate-limiting, and it means the MCP surface has nothing
local to inline. So the bytes are pulled once, when the instance is found, and
the catalogue records where they landed.

**These files are a third class, and the distinction is the data model's.**
Upstream files are backed up and never regenerated; derived files regenerate per
device and are never transported. A candidate preview is neither: it is
disposable, safe to delete the moment its work reaches a terminal verdict, and
deleting one never affects the catalogue — an accepted work's imagery comes from
acquisition, not from the preview that helped someone decide.

**A preview that will not download is not a failure.** The instance is still
real, still selectable, and still carries a source-side URL to fall back on.
Losing a work over a missing thumbnail would be the tail wagging the dog, so
every failure path here reports absence rather than raising.
"""

import hashlib
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from curation.services.errors import ServiceError

log = logging.getLogger(__name__)

#: Extensions a preview may keep from its URL. Anything else gets the default:
#: the name is ours, and a suffix copied unchecked from a URL is a path
#: component an attacker-controlled string could choose.
_KNOWN_SUFFIXES: Final[frozenset[str]] = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif", ".tif", ".tiff"})

_DEFAULT_SUFFIX: Final[str] = ".jpg"

#: How much of the URL digest names the file. Long enough that a collision is
#: not a practical concern across a catalogue of this size, short enough that the
#: directory stays readable when someone goes looking.
_NAME_LENGTH: Final[int] = 24


@dataclass(frozen=True, slots=True)
class PreviewSettings:
    """Where the image tree is, and where cached previews go inside it.

    Passed in rather than resolved here for the reason every other settings
    object gives: a service that read its own configuration could not be tested
    against two deployments and would make every caller share one.
    """

    art_root: Path
    directory: Path

    def __post_init__(self) -> None:
        """Refuse a cache outside the tree, at wiring time rather than mid-run.

        Every catalogue path is relative to `ART_ROOT`, so a preview written
        anywhere else has no representable path. Caught here it is a startup
        failure naming both directories; caught where the row is written it is a
        `ValueError` from `relative_to`, thrown on a worker thread partway
        through a run.
        """
        if not self.directory.is_relative_to(self.art_root):
            raise ServiceError(f"The preview cache at {self.directory} must sit inside ART_ROOT at {self.art_root}.")


class PreviewCache:
    """Fetch a preview once and hand back the path the catalogue should record."""

    def __init__(self, settings: PreviewSettings, fetch: Callable[[str], bytes | None]) -> None:
        self._settings = settings
        #: Injected rather than reached for, because the transport belongs behind
        #: the image seam: this class writes files and computes paths, and a
        #: service that also made HTTP requests could not be tested without one.
        self._fetch = fetch

    def store(self, url: str) -> str | None:
        """Cache the bytes at `url`, returning the path relative to `ART_ROOT`.

        `None` means no local copy exists — the fetch failed, or returned
        nothing. The caller records the instance regardless, with its source-side
        URL and no `preview_path`.

        **Already-cached bytes are not re-fetched.** The name is derived from the
        URL, so a work re-searched later finds its preview already on disk and
        the museum is asked once per distinct image rather than once per attempt.
        """
        destination = self._path_for(url)
        relative = str(destination.relative_to(self._settings.art_root))
        try:
            if destination.exists() and destination.stat().st_size > 0:
                return relative
            payload = self._fetch(url)
        except OSError as exc:
            return self._absent(url, f"the cache could not be read: {exc}")
        except Exception as exc:  # prawduct:allow prawduct/broad-except -- a provider fault must not fail the work
            # The seam promises `None` for a preview it cannot get, and a
            # provider that raises something else instead — an httpx URL error is
            # not an `HTTPError` — would otherwise reach the run-level handler and
            # fail the whole run over a thumbnail. That is precisely the outcome
            # this module exists to prevent, so the contract is enforced on this
            # side rather than trusted.
            return self._absent(url, f"the provider raised {type(exc).__name__}: {exc}")
        if not payload:
            # Distinguishes nothing-came-back from a fetch that reported failure:
            # the seam reports both as `None`, and neither is worth failing a
            # work over.
            return self._absent(url, "the provider returned no bytes")
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            # Written beside the target and renamed, so a process that dies
            # mid-write leaves no half-file that the `exists()` check above would
            # later treat as a valid cache hit.
            staging = destination.with_name(f"{destination.name}.partial")
            staging.write_bytes(payload)
            staging.replace(destination)
        except OSError as exc:
            # A full or read-only disk is a real operational condition, and it
            # must degrade the review card rather than end a run that has already
            # found the images it went looking for.
            return self._absent(url, f"the bytes could not be written: {exc}")
        log.info(
            "cached a preview",
            extra={"event": "preview.cached", "preview_url": url, "path": relative, "bytes": len(payload)},
        )
        return relative

    def _absent(self, url: str, why: str) -> None:
        """Report that no local copy exists, with the reason, and carry on.

        One exit for every way a preview can fail to arrive, so the log line
        cannot drift between them and a caller has exactly one thing to handle.
        """
        log.info(
            "no preview was cached for an instance; review will fall back to its source URL",
            extra={"event": "preview.absent", "preview_url": url, "reason": why},
        )
        return None

    def _path_for(self, url: str) -> Path:
        """Where this URL's bytes live. Derived from the URL, so it is stable.

        The name is a digest rather than anything taken from the URL's own path,
        because a museum's filename is not ours to trust as a path component and
        two museums may well use the same one.
        """
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:_NAME_LENGTH]
        suffix = Path(url.split("?", 1)[0]).suffix.lower()
        return self._settings.directory / f"{digest}{suffix if suffix in _KNOWN_SUFFIXES else _DEFAULT_SUFFIX}"
