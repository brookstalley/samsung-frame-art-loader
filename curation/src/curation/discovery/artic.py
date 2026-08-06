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
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Final
from urllib.parse import quote

import httpx

from curation.config import DEFAULT_PREVIEW_MAX_BYTES
from curation.discovery.browse import BrowseQuery, CollectionBrowse, CollectionBrowseFailure, OfferedGroup
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

#: What a browse will offer, as the museum's own `artwork_type_title` vocabulary
#: spells it. **Case matters and is not uniform across this API's keyword
#: fields**: `artwork_type_title.keyword` preserves the museum's capitalisation,
#: while `artist_title.keyword` is folded to lower case — so a value copied from
#: one field's aggregation into the other's filter silently matches nothing.
#:
#: The set is what a curator would hang. `Photograph` and `Textile` are held out
#: deliberately rather than forgotten: across the whole recorded corpus their
#: inclusion changed nothing at all, so all they buy is an artist held *only* as
#: textile, whose offer would be a flat-photographed fabric sample presented
#: beside paintings. Widening is a measurement before it is a feature
#: (`product-brief.md`).
_WALL_TYPES: Final[tuple[str, ...]] = ("Painting", "Print", "Drawing and Watercolor")

_TYPE_KEYWORD: Final[str] = "artwork_type_title.keyword"
_ARTIST_KEYWORD: Final[str] = "artist_title.keyword"

#: The aggregations a browse reads. Named here rather than spelled at both the
#: request and the response, because the two must agree and a typo in either
#: reads as a collection that holds nothing.
_FACET_AGG: Final[str] = "by_facet"
_TOP_AGG: Final[str] = "top"
_VOCABULARY_AGG: Final[str] = "by_surname"
_WHO_AGG: Final[str] = "who"

#: What a browse hit must carry to become an instance. The same fields the
#: per-work search asks for, because the row it builds is the same row.
_SOURCE_FIELDS: Final[tuple[str, ...]] = (
    "id",
    "title",
    "artist_title",
    "image_id",
    "is_public_domain",
    "thumbnail",
    "api_link",
)

#: A parenthesised aside in an artist's name, which the model supplies often
#: enough to matter — "Titian (Tiziano Vecellio)", "El Greco (Domenikos
#: Theotokopoulos)" — and whose last word is not the surname.
_PARENTHETICAL: Final[re.Pattern[str]] = re.compile(r"\([^)]*\)")

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


def _museum_client(user_agent: str, client: httpx.Client | None) -> tuple[httpx.Client, dict[str, str]]:
    """One transport policy for every question this module asks the museum.

    Shared rather than repeated because the policy is a *measurement*, not a
    preference: `_CONNECT_TIMEOUT_SECONDS` is short because a partial-IPv6
    network multiplies the connect phase across two dozen addresses, and that
    reasoning has to apply to whichever client is issuing the request. Two copies
    means whoever acts on it next — a retry, an async transport, a redirect
    policy — fixes one and leaves the other.
    """
    if not user_agent:
        raise ValueError(
            "The Art Institute's API asks callers to identify themselves. Set ARTIC_USER_AGENT to a "
            "string naming this deployment and a contact address."
        )
    http = client or httpx.Client(
        timeout=httpx.Timeout(
            connect=_CONNECT_TIMEOUT_SECONDS,
            read=_READ_TIMEOUT_SECONDS,
            write=_READ_TIMEOUT_SECONDS,
            pool=_READ_TIMEOUT_SECONDS,
        )
    )
    return http, {"AIC-User-Agent": user_agent}


class ArticImageSearch:
    """Search the Art Institute's collection and fetch previews from it."""

    def __init__(
        self,
        *,
        user_agent: str,
        client: httpx.Client | None = None,
        preview_max_bytes: int = DEFAULT_PREVIEW_MAX_BYTES,
    ) -> None:
        # Injectable so the suite can drive a recorded transport instead of the
        # network. The default is a real session; nothing else in the package
        # constructs one. No `base_url`: every request builds its full URL, and a
        # base half the code ignored would be a second answer to where the API
        # lives.
        self._http, self._headers = _museum_client(user_agent, client)
        # Defaulted rather than required, so a caller that has no Settings in
        # hand — the live probes, a scratch script — still fetches under a
        # ceiling. An unbounded read must not be reachable by forgetting an
        # argument.
        self._preview_max_bytes = preview_max_bytes

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
                f"{url!r} does not name an Art Institute object, so there is no collection record to ask for its image service."
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
        still real and still carries a source-side URL to fall back on. An
        over-ceiling body takes that same route — it is one more preview that
        did not arrive, and there is nothing a curator could do differently.

        **Streamed against a ceiling rather than read whole.** The URL comes out
        of the museum's own JSON and redirects are followed, so the body is
        foreign in both size and origin, and `response.content` on a
        non-streaming request materialises all of it before any caller can look.
        Reading in chunks and stopping at the ceiling means an endless body
        costs `preview_max_bytes` instead of the box — the failure this guards
        is an unbounded allocation on a Pi whose memory is the one input that
        could exhaust it.
        """
        try:
            with self._http.stream("GET", url, headers=self._headers, follow_redirects=True) as response:
                response.raise_for_status()
                chunks: list[bytes] = []
                received = 0
                for chunk in response.iter_bytes():
                    received += len(chunk)
                    if received > self._preview_max_bytes:
                        # Refused, not truncated. Half a JPEG is not a smaller
                        # preview; it is a corrupt one that nothing downstream
                        # can tell from a whole one, and the card degrades far
                        # better on no image than on a broken one.
                        log.warning(
                            "a preview exceeded the size ceiling and was refused; "
                            "the review card will fall back to the source URL",
                            extra={
                                "event": "phase_two.preview_too_large",
                                "provider": PROVIDER,
                                "preview_url": url,
                                "ceiling_bytes": self._preview_max_bytes,
                            },
                        )
                        return None
                    chunks.append(chunk)
        except httpx.HTTPError as exc:
            log.warning(
                "could not cache a preview; the review card will fall back to the source URL",
                extra={"event": "phase_two.preview_failed", "provider": PROVIDER, "error": str(exc)},
            )
            return None
        return b"".join(chunks)

    def _get(self, url: str, *, what: str) -> Mapping[str, Any]:
        """One GET, with every transport and shape failure named as one kind."""
        return _request(self._http, self._headers, "GET", url, what=what, failure=ImageSearchFailure)


def _request(
    http: httpx.Client,
    headers: Mapping[str, str],
    method: str,
    url: str,
    *,
    what: str,
    failure: type[Exception],
    json_body: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    """One request, with every transport and shape failure named as one kind.

    `failure` travels in rather than being fixed here because the two questions
    this module asks the museum are reported in different vocabularies — a search
    that cannot be run and a collection that cannot be browsed are different
    facts to whoever catches them — while the ways an HTTP call can go wrong are
    identical for both.
    """
    try:
        response = http.request(method, url, headers=dict(headers), json=json_body, follow_redirects=True)
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPError as exc:
        raise failure(f"Could not {what}: {exc}") from exc
    except ValueError as exc:
        raise failure(f"Could not {what}: the response was not JSON ({exc}).") from exc
    if not isinstance(payload, dict):
        raise failure(f"Could not {what}: the response was {type(payload).__name__}, not an object.")
    return payload


class ArticCollectionBrowse:
    """Ask the Art Institute what it holds by an artist, rather than for a work.

    **One POST covering every facet, plus at most two more on the miss path.**
    The retry needs its own ambiguity aggregation, and that one may not carry this
    browse's filters (see `_names_one_artist`), so it cannot ride along; a run
    where every artist is held costs exactly one request, and the worst case is
    three. All three are per *run* — none of them scales with the work list, which
    is the property that matters, and the one an earlier "one POST" reading of
    this docstring overstated.

    A named `filters` aggregation gives each
    facet its own bucket, so the collection does the matching and labels the
    result with the caller's own spelling — the alternative, partitioning one
    merged list by re-deriving which query matched which record, would be a
    second implementation of the museum's matcher, free to drift from it. Each
    bucket carries its own `top_hits`, which is what makes an even spread across
    artists possible at all: a single capped list orders by a score this API
    makes unreadable, and a prolific artist would fill it.
    """

    def __init__(self, *, user_agent: str, client: httpx.Client | None = None) -> None:
        self._http, self._headers = _museum_client(user_agent, client)

    @property
    def provider(self) -> str:
        """The name works offered from this collection are recorded under."""
        return PROVIDER

    def browse(self, queries: Sequence[BrowseQuery], *, per_query: int) -> Sequence[OfferedGroup]:
        """Wall-appropriate works held for each facet, plus what each facet matched."""
        wanted = [query for query in queries if query.artist.strip()]
        if not wanted or per_query <= 0:
            return tuple(OfferedGroup(query=query, matched=0, works=()) for query in queries)

        found = self._holdings({query.artist: query.artist for query in wanted}, per_query=per_query)
        recovered = self._recover_misses(
            [query.artist for query in wanted if found.get(query.artist, (0, ()))[0] == 0],
            per_query=per_query,
        )
        found.update(recovered)
        groups = []
        for query in queries:
            matched, works = found.get(query.artist, (0, ()))
            groups.append(OfferedGroup(query=query, matched=matched, works=works))
        return tuple(groups)

    def _recover_misses(self, missed: Sequence[str], *, per_query: int) -> dict[str, tuple[int, tuple[FoundImage, ...]]]:
        """Retry each missed artist on its surname, where the surname names one artist.

        A name the museum spells its own way returns nothing — `"Wassily
        Kandinsky"` against the twenty-four works it files under `"Vasily
        Kandinsky"`. Retrying the surname recovers those and would, unguarded,
        also offer one artist's work under another's name: `"Martorell"` reaches
        Antonio and Bernat, `"Stella"` four different artists. So the collection
        is asked how many artists the surname names, and the retry proceeds only
        where the answer is one (`product-brief.md`).
        """
        surnames = {artist: surname for artist in missed if (surname := _surname(artist)) and surname != artist}
        if not surnames:
            return {}
        # One call for every missed artist, not one per artist: the verdicts are
        # read out of a single aggregation, and asking inside the comprehension
        # would issue a request per iteration.
        verdicts = self._names_one_artist(surnames)
        unambiguous = {artist: surname for artist, surname in surnames.items() if verdicts.get(artist)}
        return self._holdings(unambiguous, per_query=per_query) if unambiguous else {}

    def _names_one_artist(self, surnames: Mapping[str, str]) -> Mapping[str, bool]:
        """Whether each surname reaches exactly one artist in the whole collection.

        **Deliberately unfiltered, and this is the load-bearing detail.** Asking
        this question inside the browse's own filters manufactures the confidence
        it exists to withhold: the Art Institute holds one Antonio Martorell, a
        `Graphic Design` the wall-type filter removes, so a filtered check sees
        only Bernat Martorell, reports "one artist", and offers his painting to a
        run that named Antonio. The collision is a fact about the collection's
        names, so it is measured against the collection's names.
        """
        payload = _request(
            self._http,
            self._headers,
            "POST",
            _SEARCH_URL,
            what=f"ask how many artists {sorted(set(surnames.values()))} name",
            failure=CollectionBrowseFailure,
            json_body={
                "limit": 0,
                "query": {"bool": {"filter": [_any_of(surnames.values())]}},
                "aggs": {
                    _VOCABULARY_AGG: {
                        "filters": {"filters": {artist: _artist_match(surname) for artist, surname in surnames.items()}},
                        # Two is all the decision needs: one is unambiguous and
                        # anything above one is refused identically, so asking
                        # for more buckets would cost the museum work to produce
                        # a number nothing reads.
                        "aggs": {_WHO_AGG: {"terms": {"field": _ARTIST_KEYWORD, "size": 2}}},
                    }
                },
            },
        )
        buckets = _buckets(payload, _VOCABULARY_AGG)
        verdicts = {}
        for artist in surnames:
            names = _bucket_keys(buckets.get(artist), _WHO_AGG)
            verdicts[artist] = len(names) == 1
            if verdicts[artist]:
                log.info(
                    "retrying an artist on its surname: the collection files that surname under one artist",
                    extra={
                        "event": "browse.surname_retried",
                        "provider": PROVIDER,
                        "artist": artist,
                        "surname": surnames[artist],
                        "names_found": sorted(names),
                    },
                )
            else:
                log.info(
                    "not retrying an artist on its surname: the collection files that surname under several artists",
                    extra={
                        "event": "browse.surname_ambiguous",
                        "provider": PROVIDER,
                        "artist": artist,
                        "surname": surnames[artist],
                        "names_found": sorted(names),
                    },
                )
        return verdicts

    def _holdings(self, facets: Mapping[str, str], *, per_query: int) -> dict[str, tuple[int, tuple[FoundImage, ...]]]:
        """What the collection holds for each facet, keyed by the caller's own name.

        `facets` maps the name to report under to the name to actually ask about;
        they differ only on the surname-retry path, which is what lets a
        recovered artist come back under the spelling the run used rather than
        the museum's.
        """
        if not facets:
            return {}
        payload = _request(
            self._http,
            self._headers,
            "POST",
            _SEARCH_URL,
            what=f"browse the collection for {sorted(facets.values())}",
            failure=CollectionBrowseFailure,
            json_body={
                "limit": 0,
                "query": {
                    "bool": {
                        "filter": [
                            {"exists": {"field": "image_id"}},
                            {"terms": {_TYPE_KEYWORD: list(_WALL_TYPES)}},
                            _any_of(facets.values()),
                        ]
                    }
                },
                "aggs": {
                    _FACET_AGG: {
                        "filters": {"filters": {name: _artist_match(asked) for name, asked in facets.items()}},
                        "aggs": {_TOP_AGG: {"top_hits": {"size": per_query, "_source": {"includes": list(_SOURCE_FIELDS)}}}},
                    }
                },
            },
        )
        iiif = _iiif_base(payload.get("config"))
        buckets = _buckets(payload, _FACET_AGG)
        holdings = {}
        for name in facets:
            bucket = buckets.get(name) or {}
            hits = _hits(bucket)
            works = tuple(
                image
                for hit in hits
                if isinstance(hit, dict) and (image := _instance(hit.get("_source"), iiif=iiif, scored=False)) is not None
            )
            holdings[name] = (_count(bucket.get("doc_count")), works)
        log.info(
            "browsed a collection by artist",
            extra={
                "event": "browse.searched",
                "provider": PROVIDER,
                "facets": len(facets),
                "facets_with_holdings": sum(1 for matched, _ in holdings.values() if matched),
                "works_brought_back": sum(len(works) for _, works in holdings.values()),
            },
        )
        return holdings


def _surname(artist: str) -> str:
    """The name a failed full-name match may be retried on, or empty.

    A parenthesised aside is dropped before the last word is taken, so `"Titian
    (Tiziano Vecellio)"` retries as `"Titian"` rather than as `"Vecellio)"`. What
    that recovers is decided by the ambiguity check, not here — Titian is refused
    by it, and correctly so.

    A one-word name yields itself, and the caller drops it: whether a retry is
    worth making is that caller's question, since it already has to compare the
    surname against the name that failed. Answering it here as well left a branch
    no test could reach, because the second guard caught everything the first did.
    """
    plain = _PARENTHETICAL.sub(" ", artist).strip()
    words = plain.split()
    return words[-1] if len(words) > 1 else plain


def _artist_match(artist: str) -> Mapping[str, Any]:
    """A token-AND on the artist field.

    Not the free-text `q=` (where the artist's tokens compete with a title's for
    the result window) and not `artist_title.keyword` (an exact match that fails
    on the museum's own spelling, returning nothing for "Sonia Delaunay" against
    the fifteen it files under "Sonia Delaunay-Terk"). Measured, both of them —
    `artic-api-findings.md`.
    """
    return {"match": {"artist_title": {"query": artist, "operator": "and"}}}


def _any_of(artists: Iterable[str]) -> Mapping[str, Any]:
    """A filter matching a record by any one of these artists."""
    return {"bool": {"should": [_artist_match(artist) for artist in artists], "minimum_should_match": 1}}


def _buckets(payload: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    """The named `filters` aggregation's buckets, or empty if it did not arrive.

    An aggregation that did not come back is an empty browse rather than a
    crash: the collection answered, and what it answered carries no holdings.
    """
    aggregations = payload.get("aggregations")
    if not isinstance(aggregations, dict):
        return {}
    buckets = (aggregations.get(name) or {}).get("buckets")
    return buckets if isinstance(buckets, dict) else {}


def _hits(bucket: Mapping[str, Any]) -> list[Any]:
    """The `top_hits` rows inside one facet bucket, or none.

    Every step is checked rather than chained, for the reason the rest of this
    module is: a `null` where an object was expected raises `AttributeError` on a
    chained `.get`, and this one would escape a caller that catches only a browse
    failure — ending an otherwise successful run as an unexplained fault, which is
    the opposite of a supplement that must not take a run down with it.
    """
    top = bucket.get(_TOP_AGG)
    inner = top.get("hits") if isinstance(top, dict) else None
    rows = inner.get("hits") if isinstance(inner, dict) else None
    return rows if isinstance(rows, list) else []


def _bucket_keys(bucket: object, name: str) -> set[str]:
    """The distinct keys a `terms` sub-aggregation reported."""
    if not isinstance(bucket, dict):
        return set()
    inner = (bucket.get(name) or {}).get("buckets")
    if not isinstance(inner, list):
        return set()
    return {key for entry in inner if isinstance(entry, dict) and (key := _text(entry.get("key")))}


def _count(raw: object) -> int:
    """A non-negative bucket count, or zero when the field is missing or not one."""
    return raw if isinstance(raw, int) and not isinstance(raw, bool) and raw >= 0 else 0


def _instance(entry: object, *, iiif: str, scored: bool = True) -> FoundImage | None:
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

    `scored` is false for a browse hit, which carries no score to read: a filter
    decided it, not a ranker. Skipping the check explicitly rather than letting a
    missing field fall through it keeps "there is no score here" from resting on
    `None` not comparing equal to zero.
    """
    if not isinstance(entry, dict):
        return None
    if scored and _number(entry.get("_score")) == 0:
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
        url=_text(entry.get("api_link")) or f"{_OBJECT_URL}/{entry.get('id')}",
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
    """Where this museum's image service lives, taken from the response but not blindly.

    Three callers now, which is why this no longer says "previews": a per-work
    search and a browse both build preview URLs from it, and `tile_url` builds the
    image service a tiled acquisition walks. All three fetch what it addresses, so
    the check below guards all three.

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


def build_image_search(
    *,
    user_agent: str,
    client: httpx.Client | None = None,
    preview_max_bytes: int = DEFAULT_PREVIEW_MAX_BYTES,
) -> ImageSearch:
    """The image provider a deployment gets. One museum today, by name."""
    return ArticImageSearch(user_agent=user_agent, client=client, preview_max_bytes=preview_max_bytes)


def build_collection_browse(*, user_agent: str, client: httpx.Client | None = None) -> CollectionBrowse:
    """The collection a deployment supplements from. The same museum, asked differently."""
    return ArticCollectionBrowse(user_agent=user_agent, client=client)
