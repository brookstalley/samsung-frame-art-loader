# ARTIC API Findings

Captured 2026-08-02 by probing the live Art Institute of Chicago API before
writing any client, because a fake built against assumed shapes encodes the
assumptions rather than testing them. Everything below is **measured**, not
recalled or read from documentation, except where a line says otherwise.

No key, no account, no quota negotiation: the API is open. It asks for an
`AIC-User-Agent` header identifying the caller and a contact address, which every
probe here sent.

Base: `https://api.artic.edu/api/v1`. The probes ran against API version `1.14`,
reported in every response's `info.version`.

## The search response carries everything phase 2 needs, in one call

`GET /artworks/search?q=…&fields=…` returns the selected fields inline. One
request per work, not two:

```
pagination.{total,limit,offset,total_pages,current_page}
data[].\_score                    float   relevance, see the warning below
data[].id                        int
data[].api_link                  string
data[].title                     string
data[].artist_title              string   e.g. "Grant Wood"
data[].artist_display            string   e.g. "Grant Wood (American, 1891-1942)"
data[].date_display              string   e.g. "1930"
data[].dimensions                string   free text, physical, e.g. "78 x 65.3 cm (30 3/4 x 25 3/4 in.)"
data[].medium_display            string
data[].department_title          string
data[].classification_title      string   e.g. "oil paintings (visual works)"
data[].image_id                  string   the IIIF identifier
data[].is_public_domain          bool
data[].thumbnail.{lqip,width,height,alt_text}
info.{license_text,license_links,version}
config.{iiif_url,website_url}
```

### `thumbnail.width`/`height` are the **full image's** dimensions, not the thumbnail's

Measured on two works by fetching the IIIF `info.json` for the same `image_id`
and comparing:

| Work | `thumbnail.width` x `height` | IIIF `info.json` `width` x `height` |
|---|---|---|
| American Gothic (6565) | 6949 x 8400 | 6949 x 8400 |
| Thorne room E-29 (43784) | 1503 x 2250 | 1503 x 2250 |

Identical in both cases. The name is misleading — `thumbnail` is the *preview
descriptor*, and its dimensions describe the master the preview was derived from.

**This is what makes `CandidateImage.estimated_width`/`estimated_height` free.**
They come from the same search response that produced the candidate, so no
per-result IIIF round trip is needed to know whether a work clears the rendered-size
floor. A client that fetched `info.json` per result would triple the request count
for data it already had.

`config.iiif_url` gives the IIIF base (`https://www.artic.edu/iiif/2`) in every
response, so it is read from the response rather than hardcoded.

## `_score` cannot carry the confidence axis — this is the load-bearing finding

Three separate measurements, each of which independently rules it out.

**1. Scores are not comparable across queries.** Two queries that both found their
target correctly:

```
"American Gothic"            top score 3361.53   -> "American Gothic"  (correct)
"Persistence of Memory Dali" top score  122.10   -> wrong work (see below)
```

A 27x spread between two well-formed queries means no absolute threshold
separates a good match from a bad one.

**2. A nonsense query returns the entire collection, not an empty result.**

```
q="zzzqqxnonexistent"   pagination.total 132630   data[0] "Self-Portrait"  _score 0.0
q="asdfghjkl qwerty"    pagination.total 132630   data[0] "Self-Portrait"  _score 0.0
```

`pagination.total` is the collection size regardless of the query, and results are
always returned. **Neither the presence of results nor `total` is evidence that
anything matched.** A client checking "did the search return anything" gets yes,
always. The one thing that does discriminate garbage is `_score == 0.0` exactly.

**3. The near-match hazard is real and reproducible.** ARTIC does not hold *The
Persistence of Memory* — it is MoMA's. Asking for it anyway:

```
110.56  'Ann-In Memory'                        Joseph Cornell
 91.24  'In Memory of My Father'               Sylvia Plimack Mangold
 82.97  'A Memory'                             Gene Charlton
 58.16  'In Memory of Robert Schumann'         Henri Fantin-Latour
 52.78  'Design for Memorial to Pope Gregory XV'  Alessandro Algardi
```

Every score is comfortably non-zero and the top result is a real artwork by a real
artist. A client that ranked by `_score` and took the leader would attach *Ann-In
Memory* by Joseph Cornell to a request for a Dalí, with no signal that anything
went wrong — the exact "confident near-match" that `data-model.md` constraint 9
and the build plan both forbid, arriving through the most obvious implementation.

**So confidence must come from comparing the returned `title` and `artist_title`
against the work that was asked for, not from the engine's relevance number.**
`_score == 0` is usable only as a cheap pre-filter for a query that matched
nothing at all.

## Every IIIF response is 843 pixels wide, whatever you ask for

The public IIIF endpoint rewrites the size segment of every request to `843,`.
Measured by decoding the returned JPEG's SOF header rather than trusting the URL:

| Request | Result |
|---|---|
| `full/full/0/default.jpg` | 307 -> `full/843,` -> 843 x 1019 |
| `full/1686,/0/default.jpg` | 307 -> `full/843,` -> 843 x 1019 |
| `full/843,/0/default.jpg` | 200 directly, 843 x 1019, 237,307 bytes |
| region `0,0,843,1019` | 843 x 1019 — 1:1, the native tile |
| region `0,0,2529,3057` | 843 x 1019 — downscaled 3x |
| region `0,0,256,256` | rewritten to `0,0,256,256/843,` — *upscaled* |

The `info.json` profile advertises `maxArea` equal to the full pixel count
(58,371,600 for American Gothic) and `sizeByW` support, which reads as though a
full-resolution single GET were allowed. **It is not** — the rewrite happens in
front of the image server, so the profile describes a capability the deployment
does not expose. This is why the shapes were measured rather than read.

Two consequences, and they are the ones the data model already has fields for:

- **Preview is solved and costs one request.** `full/843,/0/default.jpg` is the
  only simple derivative, and 843px on the long edge is a good review preview.
  That is `CandidateImage.preview_url`, and the bytes behind `preview_path`.
- **Full resolution is tiles-only**, so an ARTIC instance is
  `acquisition_method = dezoomify`. Region requests do return native pixels when
  the region is 843 wide, which is the grid a tiled fetcher walks. Anything
  larger comes back downscaled and anything smaller comes back upscaled, so the
  tile width is not a tuning knob — it is 843.

## Failure and edge shapes

**A missing artwork** returns HTTP 404 with:

```json
{"status": 404, "error": "Not found", "detail": "The item you requested cannot be found."}
```

**Every result in a 40-result sample carried `image_id` and a populated
`thumbnail` with dimensions** — zero had `thumbnail: null`, zero lacked
`image_id`. That is a sample, not a guarantee, and both fields are documented as
nullable; a work with no image cannot become a `CandidateImage` and is skipped
rather than recorded with absent dimensions.

**No rate-limit headers are exposed.** No `X-RateLimit-*`, no `Retry-After` on
any probe. Responses pass through CloudFront (`x-cache`, `x-amz-cf-*`) with
`cache-control: no-cache, private`. So a client cannot discover its budget from
the response and must be conservative on its own terms; there is no signal to
read back.

## A slow network multiplies the connect timeout — httpx has no Happy Eyeballs

Measured on this machine partway through the same day the shapes above were
captured, when the local network's IPv6 path degraded:

```
curl  https://api.artic.edu/api/v1/artworks/search?q=test   0.7s
httpx same URL, timeout=10.0                               80.2s   (status 200)
```

Reproduced three times. **The timeout was not honoured**, and DNS is not the
cause — `getaddrinfo` returns in 0.1 s. The cause is the shape of what it
returns: **24 addresses, 16 of them IPv6.** `curl` implements Happy Eyeballs
(RFC 8305), racing the two families with a short head start, so a dead IPv6 path
costs it milliseconds. httpx walks the list in order, and an httpx timeout bounds
**each attempt**, not the sequence — so on a network where IPv6 routes but does
not reach, the wall-clock cost is roughly *addresses tried x connect timeout*.

**What the client does about it:** the connect timeout is set short (5 s)
separately from the read timeout (20 s), because connect is the phase that gets
multiplied and read is the one worth waiting on. That reduces the worst case; it
does not bound it.

**What it does not do, and why.** Forcing IPv4, or resolving and racing
addresses here, would put a network-family policy into a museum client — a new
configuration surface invented in the middle of a build rather than a requirement
anyone stated, and one that would break an IPv6-only deployment. The residual
exposure is recorded instead: on a partial-IPv6 network a discovery run is slow
rather than wrong, its per-work progress is visible in the log, and the run's own
status long-poll keeps a client from hanging on it. **Backlog issue #47** carries
the fix.

This is also why the live suite (`tests/live/test_artic_shapes_are_still_real.py`)
is deselected by default: it is free, but it is at the mercy of whatever the
local network is doing.

## What this hands off

| To | What |
|---|---|
| Phase-2 engine | Confidence is a title/artist comparison, never `_score`; `_score == 0` is a pre-filter only |
| Phase-2 engine | One search request per work returns dimensions, rights and preview URL together |
| `CandidateImage` | `estimated_width`/`estimated_height` from `thumbnail.width`/`height`; `rights_status` from `is_public_domain`; `acquisition_method = dezoomify`; `provider = artic` |
| Preview caching | `{iiif_url}/{image_id}/full/843,/0/default.jpg`, one GET, no size negotiation |
| Acquisition (Chunk 18) | Full resolution requires walking an 843-pixel region grid; the advertised `maxArea` is not honoured |
| Client conventions | Send `AIC-User-Agent`; read the IIIF base from `config.iiif_url`; no rate-limit headers exist to read |
