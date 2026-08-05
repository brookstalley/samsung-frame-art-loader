"""The Art Institute of Chicago's API, as one image provider behind the seam.

One museum, one narrow surface: search the collection for a work, and fetch the
preview bytes for an instance. Nothing here knows what a discovery run is, and
nothing here judges whether a result is the work that was asked for — it reports
what the collection holds, and the judgement is made above the seam where it can
be made once for every provider.

Every shape below was **measured** against the live API before this module
existed, and the measurements are `artic-api-findings.md`. Three of them are
load-bearing enough to restate where the code depends on them:

**The search response carries the master's dimensions.** `thumbnail.width` and
`thumbnail.height` describe the full image, not the preview — verified equal to
the IIIF `info.json` dimensions on separate works. So an instance's size is known
from the same response that found it, and the per-result IIIF round trip a
careful implementation would otherwise make is not needed at all.

**Every IIIF response is 843 pixels wide, whatever is asked for.** A request for
`full/full` or any other size redirects to `full/843,`. That is why the preview
URL is built at exactly that size rather than negotiated: asking for anything
else returns the same bytes after an extra round trip. It is also why an instance
here is `dezoomify` — full resolution is reachable only by walking a region grid,
notwithstanding an advertised `maxArea` that says otherwise.

**A query that matches nothing still returns the whole collection**, with
`pagination.total` reporting the collection size regardless. So neither the
presence of results nor the total is evidence of a match.

**Nothing in the response distinguishes a garbage query from a real one**, and
this is a correction rather than an original finding. The first probe recorded
non-matching results arriving at `_score` 0.0, which made a zero-score pre-filter
a cheap first line. Re-measured 2026-08-04, a nonsense query returns ten real
works scoring in the fifties and sixties — *Nighthawks* among them. **The
pre-filter below is therefore no defence against a garbage query, and the
identity comparison above the seam is the only one.** The filter is kept because
what it says is still true — a record that matched no term cannot be the work —
but it is a correctness detail now and not a guard, and reading it as a guard is
what this paragraph exists to prevent.
"""

import logging
import re
from collections.abc import Mapping, Sequence
from typing import Any, Final
from urllib.parse import quote

import httpx

from curation.discovery.images import FoundImage, ImageQuery, ImageSearch, ImageSearchFailure
from curation.persistence.records import AcquisitionMethod, RightsStatus, SourceClass

log = logging.getLogger(__name__)

#: The provider string these instances are recorded under. An open vocabulary in
#: the data model, so this is a name rather than a member of an enum.
PROVIDER: Final[str] = "artic"

_SEARCH_URL: Final[str] = "https://api.artic.edu/api/v1/artworks/search"

#: Where one object is read by id. The same collection the search endpoint is
#: part of, named separately because a URL built by trimming another's last
#: segment reads as a coincidence rather than as an address.
_OBJECT_URL: Final[str] = "https://api.artic.edu/api/v1/artworks"

#: The object id inside either URL an Art Institute source carries: the museum's
#: own page (`www.artic.edu/artworks/91194/golden-bird`) and its API link
#: (`api.artic.edu/api/v1/artworks/91194`) put the same number in the same place.
#: Anchored to a path segment so a number anywhere else in the URL — a query
#: parameter, a fragment — cannot be read as one.
_OBJECT_ID: Final[re.Pattern[str]] = re.compile(r"/artworks/(\d+)(?:/|$|\?|#)")

#: The fields asked for. Explicit rather than taking the default projection: the
#: default omits `image_id` and the dimensions, which are the two things an
#: instance cannot be recorded without.
_FIELDS: Final[str] = ",".join(
    (
        "id",
        "title",
        "artist_title",
        "date_display",
        "image_id",
        "is_public_domain",
        "thumbnail",
        "api_link",
    )
)

#: Where the IIIF service lives if a response does not say. Every measured
#: response carried `config.iiif_url`, so this is a fallback for a field going
#: absent rather than the normal path — reading it from the response is what
#: keeps a service move from needing a release here.
_IIIF_FALLBACK: Final[str] = "https://www.artic.edu/iiif/2"

#: What an advertised IIIF base must start with to be used. The response builds a
#: URL this process fetches and writes to disk, so the host it names is checked
#: rather than taken — a path change under this host needs no release, a host
#: change does.
_IIIF_TRUSTED_PREFIX: Final[str] = "https://www.artic.edu/"

#: The only derivative size the service actually serves. Not a tuning knob: every
#: other size redirects here, so a different number costs a round trip and
#: returns identical bytes.
_PREVIEW_WIDTH: Final[int] = 843

#: How many results one work's search asks for. Large enough that a museum
#: holding several instances of a work returns them all as alternates, small
#: enough that a query matching nothing does not drag the collection back — and
#: it is the identity check above the seam, not this number, that decides what
#: survives.
_RESULT_LIMIT: Final[int] = 10

#: How long each phase of one request may take. A work whose provider timed out
#: is a failed search, which the caller reports rather than treating as "not in
#: the collection".
#:
#: **This bounds each connection attempt, not the whole call, and the difference
#: was measured rather than assumed.** `api.artic.edu` resolves to two dozen
#: addresses, sixteen of them IPv6. httpx tries them in order; on a network where
#: IPv6 routes but does not reach, each attempt has to fail before the next
#: begins, and a single search was observed taking **80 seconds against a 10-second
#: timeout** while `curl` completed it in 0.7 — because curl implements Happy
#: Eyeballs (RFC 8305) and races the families, and httpx does not. So `connect` is
#: kept short: it is the phase that gets multiplied.
#:
#: The residual exposure is real and is recorded rather than papered over — see
#: `artic-api-findings.md` § A slow network multiplies the connect timeout.
_CONNECT_TIMEOUT_SECONDS: Final[float] = 5.0

#: How long the museum may take to answer once connected. Generous, because a
#: search that has reached the server is worth waiting for.
_READ_TIMEOUT_SECONDS: Final[float] = 20.0


class ArticImageSearch:
    """Search the Art Institute's collection and fetch previews from it."""

    def __init__(self, *, user_agent: str, client: httpx.Client | None = None) -> None:
        if not user_agent:
            raise ValueError(
                "The Art Institute's API asks callers to identify themselves. Set ARTIC_USER_AGENT to a "
                "string naming this deployment and a contact address."
            )
        # Injectable so the suite can drive a recorded transport instead of the
        # network. The default is a real session; nothing else in the package
        # constructs one. No `base_url`: every request builds its full URL, and a
        # base half the code ignored would be a second answer to where the API
        # lives.
        self._http = client or httpx.Client(
            timeout=httpx.Timeout(
                connect=_CONNECT_TIMEOUT_SECONDS,
                read=_READ_TIMEOUT_SECONDS,
                write=_READ_TIMEOUT_SECONDS,
                pool=_READ_TIMEOUT_SECONDS,
            )
        )
        self._headers = {"AIC-User-Agent": user_agent}

    @property
    def provider(self) -> str:
        """The name this client's instances are recorded under."""
        return PROVIDER

    def find_images(self, query: ImageQuery) -> Sequence[FoundImage]:
        """Every instance the collection holds for this work, unjudged.

        **The artist is not sent at all, and this was measured rather than
        reasoned.** It is not a field filter either — a filter would silently
        return nothing for a name the museum spells its own way, which is why one
        was never used. But folding the artist into the free-text query is not the
        harmless middle it looks like: the search ranks over the whole term
        string, so the artist's tokens compete with the title's for the ten places
        the result has, and works the collection demonstrably holds fall out of
        the window. Measured 2026-08-04 over eight Ellsworth Kelly paintings the
        museum holds: the title alone retrieved all eight, the title with
        "Ellsworth Kelly" appended retrieved six, and it was never the better of
        the two on any title.

        The artist still decides the outcome — it is simply the identity
        comparison above the seam that applies it, where a near miss is visible
        and refusable, rather than the ranker, where it is silent.
        """
        payload = self._get(
            f"{_SEARCH_URL}?q={quote(query.title)}&limit={_RESULT_LIMIT}&fields={_FIELDS}",
            what=f"search the collection for {query.title!r}",
        )
        iiif = _iiif_base(payload.get("config"))
        data = payload.get("data")
        if not isinstance(data, list):
            raise ImageSearchFailure(f"The Art Institute's search returned no data array for {query.title!r}.")
        found = [image for entry in data if (image := _instance(entry, iiif=iiif)) is not None]
        log.info(
            "searched a museum collection for a work",
            extra={
                "event": "phase_two.searched",
                "provider": PROVIDER,
                "work_title": query.title,
                "results_returned": len(data),
                "instances_usable": len(found),
            },
        )
        return found

    def tile_url(self, url: str) -> str:
        """The IIIF image service for the object `url` names.

        The recorded URL is the object's identity — either the museum's own page
        or its API link — and neither is something a tile fetcher can read. What
        it needs is `{iiif_base}/{image_id}`, and `image_id` is a fact only the
        collection holds, so this asks for it rather than deriving it.

        The base comes from the same response, checked the same way previews'
        does: a service move needs no release here, but the response cannot
        redirect the fetcher off the museum's own host.

        Failure is `ImageSearchFailure` — the same kind every other question this
        client asks reports — so that reaching the museum stays this module's
        vocabulary and the fetch path translates it into its own.
        """
        object_id = _object_id(url)
        if object_id is None:
            raise ImageSearchFailure(
                f"{url!r} does not name an Art Institute object, so there is no collection record to ask "
                "for its image service."
            )
        payload = self._get(
            f"{_OBJECT_URL}/{object_id}?fields=id,image_id",
            what=f"look up the image service for object {object_id}",
        )
        data = payload.get("data")
        image_id = _text(data.get("image_id")) if isinstance(data, dict) else ""
        if not image_id:
            # A real answer that carries no image: the museum holds the object and
            # publishes no picture of it. Distinct from a failed lookup, and the
            # difference matters to whoever reads the recorded failure.
            raise ImageSearchFailure(
                f"The Art Institute's record for object {object_id} carries no image_id, so the collection "
                "publishes no image of it."
            )
        return f"{_iiif_base(payload.get('config')).rstrip('/')}/{image_id}"

    def fetch_preview(self, url: str) -> bytes | None:
        """The preview bytes, or `None` when they could not be got.

        A missing preview degrades a review card rather than invalidating an
        instance, so this reports absence instead of raising: the instance is
        still real and still carries a source-side URL to fall back on.
        """
        try:
            response = self._http.get(url, headers=self._headers, follow_redirects=True)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            log.warning(
                "could not cache a preview; the review card will fall back to the source URL",
                extra={"event": "phase_two.preview_failed", "provider": PROVIDER, "error": str(exc)},
            )
            return None
        return response.content

    def _get(self, url: str, *, what: str) -> Mapping[str, Any]:
        """One GET, with every transport and shape failure named as one kind."""
        try:
            response = self._http.get(url, headers=self._headers, follow_redirects=True)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            raise ImageSearchFailure(f"Could not {what}: {exc}") from exc
        except ValueError as exc:
            raise ImageSearchFailure(f"Could not {what}: the response was not JSON ({exc}).") from exc
        if not isinstance(payload, dict):
            raise ImageSearchFailure(f"Could not {what}: the response was {type(payload).__name__}, not an object.")
        return payload


def _instance(entry: object, *, iiif: str) -> FoundImage | None:
    """One search result as an instance, or `None` where it cannot be one.

    Three things disqualify a result and each is a fact about the record rather
    than a judgement about the work. A **zero score** means the record matched no
    term in the query, so it cannot be the work — true whenever it happens, and
    as of 2026-08-04 it no longer happens for a garbage query, which is why the
    module docstring above insists this is not the defence against one. **No
    `image_id`** means the museum holds the object but publishes no image of it.
    **No dimensions** means the rendered size on the wall cannot be computed, and
    an instance recorded without them would be indistinguishable from one that
    clears the floor.
    """
    if not isinstance(entry, dict):
        return None
    if _number(entry.get("_score")) == 0:
        return None
    image_id = _text(entry.get("image_id"))
    title = _text(entry.get("title"))
    if not image_id or not title:
        return None
    thumbnail = entry.get("thumbnail")
    width, height = (None, None)
    if isinstance(thumbnail, dict):
        width, height = _size(thumbnail.get("width")), _size(thumbnail.get("height"))
    if width is None or height is None:
        return None
    return FoundImage(
        # The museum's page for the object, not the image file: this is the
        # instance's identity and what a curator follows to check provenance.
        # The bytes are reached through `acquisition_method`, which is what that
        # field is for.
        url=_text(entry.get("api_link")) or f"{_SEARCH_URL.rsplit('/', 1)[0]}/{entry.get('id')}",
        provider=PROVIDER,
        source_class=SourceClass.INSTITUTIONAL,
        # Tiles, because every simple size request is capped at 843px wide. The
        # advertised maxArea says a full-resolution GET is allowed and it is not.
        acquisition_method=AcquisitionMethod.DEZOOMIFY,
        title=title,
        artist=_text(entry.get("artist_title")) or None,
        preview_url=f"{iiif.rstrip('/')}/{image_id}/full/{_PREVIEW_WIDTH},/0/default.jpg",
        estimated_width=width,
        estimated_height=height,
        # `is_public_domain` is a boolean, so a false reads as "the museum says
        # it is not" rather than "nobody checked" — which is `in_copyright`, not
        # `unknown`. The field being absent altogether is the honest `unknown`.
        rights_status=_rights(entry.get("is_public_domain")),
    )


def _rights(raw: object) -> RightsStatus:
    """What the museum's public-domain flag says, always as a recorded value.

    Never `None`, deliberately: constraint 13 forbids absence, and a field the
    museum did not send is honestly `unknown` rather than unrecorded. A `False`
    is a different fact again — the museum checked and says it is in copyright.
    """
    if raw is True:
        return RightsStatus.PUBLIC_DOMAIN
    if raw is False:
        return RightsStatus.IN_COPYRIGHT
    return RightsStatus.UNKNOWN


def _iiif_base(config: object) -> str:
    """Where previews are fetched from, taken from the response but not blindly.

    Read from `config.iiif_url` so a service move needs no release here, and
    checked because the value is used to build a URL this process then fetches
    and writes to disk. The check is narrow on purpose — the host must be one the
    Art Institute serves over TLS — because the point is to keep a compromised or
    malformed response from redirecting the fetcher somewhere else, not to
    validate a URL in general.
    """
    if isinstance(config, dict):
        advertised = _text(config.get("iiif_url"))
        if advertised.startswith(_IIIF_TRUSTED_PREFIX):
            return advertised
        if advertised:
            log.warning(
                "ignoring an unexpected IIIF base in the response and using the known one",
                extra={"event": "phase_two.iiif_base_rejected", "provider": PROVIDER, "advertised": advertised},
            )
    return _IIIF_FALLBACK


def _object_id(url: str) -> str | None:
    """The collection's id for the object a source URL names, or `None`."""
    match = _OBJECT_ID.search(url)
    return None if match is None else match.group(1)


def _text(raw: object) -> str:
    """A trimmed string, or empty — never a stringified `None` or number."""
    return raw.strip() if isinstance(raw, str) else ""


def _number(raw: object) -> float | None:
    """A score as a number, or `None` when the field is missing or not one."""
    return float(raw) if isinstance(raw, (int, float)) and not isinstance(raw, bool) else None


def _size(raw: object) -> int | None:
    """A positive pixel dimension, or `None`. Zero and negatives are not sizes."""
    if isinstance(raw, bool) or not isinstance(raw, int):
        return None
    return raw if raw > 0 else None


def build_image_search(*, user_agent: str, client: httpx.Client | None = None) -> ImageSearch:
    """The image provider a deployment gets. One museum today, by name."""
    return ArticImageSearch(user_agent=user_agent, client=client)
