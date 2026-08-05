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
always.

> **The zero score is gone — re-measured 2026-08-04, and this half of the finding
> is retracted.** The same shape of query now comes back with ordinary relevance
> scores and no zeros at all:
>
> ```
> q="zzzqqx nonexistent painting nobody at all"   pagination.total 132634
>   69.80  'Flowers of All Seasons'
>   57.81  'A Sunday on La Grande Jatte — 1884'   Georges Seurat
>   57.08  'Nighthawks'                           Edward Hopper
>   54.26  'Untitled (Painting)'                  Mark Rothko
> ```
>
> So **nothing in the response discriminates a garbage query**, and the sentence
> this note replaces — that `_score == 0.0` is the one thing that does — described
> an API that no longer exists. The consequence is not small: the pre-filter built
> on it is now inert, and the identity comparison is the *only* thing standing
> between a nonsense query and *Nighthawks*. The filter is kept because what it
> asserts is still true whenever it fires, but it is a correctness detail and not
> a guard.
>
> **This is what the live suite is for**, and it worked exactly as designed: the
> test holding this measurement went red on its own, before anything depended on
> the stale belief. Finding 3 below is unaffected and is the one that mattered all
> along.

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
That conclusion is now load-bearing in a way it was not when it was written: with
the zero score gone (see the retraction above), the comparison is not the *main*
defence but the only one.

**And the artist is not sent to the search at all — measured 2026-08-04.** Folding
it into the free-text `q=` looked like a harmless narrowing and is not: the ranker
scores the whole term string, so the artist's tokens compete with the title's for
the ten places a result has. Over eight Ellsworth Kelly paintings the museum
holds, `q="<title>"` retrieved all eight and `q="<title> Ellsworth Kelly"`
retrieved six, never doing better on any one. A field filter is not the
alternative and never was — `artist_title.keyword` is an exact match against the
museum's own spelling, and "Sonia Delaunay" returns nothing where
"Sonia Delaunay-Terk" returns fifteen. The title retrieves; the identity
comparison judges.

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

## The object endpoint, which the fetch path depends on entirely

**Measured 2026-08-04.** Everything above concerns `/artworks/search`. Acquisition
uses a *different* endpoint, and no finding here covered it until a defect showed
that nothing did.

`GET https://api.artic.edu/api/v1/artworks/{id}?fields=id,image_id` returns
`data` as a **single object, not a list**, and carries the same `config.iiif_url`
the search envelope does. Joining `config.iiif_url` to `data.image_id` gives a
IIIF base that `dezoomify-rs` reads; `info.json` under it answers with real
`width`/`height`.

**Why this endpoint is reached at all:** a `Source` records the object's page or
API link, and neither is something the tile fetcher can read — all eleven of its
dezoomers decline both (`dezoomify-cli-findings.md`). The `image_id` needed to
build a usable URL is not persisted anywhere in the catalogue, so it is asked for
at fetch time. Both recorded URL shapes carry the object id in the same path
segment, so both resolve identically:

| Recorded on a Source | Where it comes from |
|---|---|
| `www.artic.edu/artworks/91194/golden-bird` | the 2024 index, seeded onto 32 sources |
| `api.artic.edu/api/v1/artworks/91194` | `api_link`, what discovery records today |

**`data.image_id` can be absent or null on a real record** — the museum holds the
object and publishes no picture of it. That is distinct from a failed lookup, and
the fetch path reports it as such rather than composing a base with nothing after
it.

Guarded by `live_museum` tests in
`curation/tests/live/test_artic_shapes_are_still_real.py`, including one that
fetches `info.json` under the resolved base rather than trusting the URL's shape.

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

> **This is not an ARTIC-client concern, and reading it as one is the mistake
> this note exists to prevent.** It was found here because this is where the live
> suite ran, but the exposure belongs to every httpx client in the plane, and
> **`openrouter.py` has it worse.** That client passes *scalar* timeouts —
> `COMPLETION_TIMEOUT_SECONDS = 180.0`, `KEY_TIMEOUT_SECONDS = 15.0` — and a
> scalar httpx timeout applies to every phase alike, so its connect phase is
> bounded at 180 seconds *per address* against this client's deliberate 5. The
> client that got hardened is the one that was already the least exposed.
>
> Left as it is on purpose rather than half-fixed: issue #47 is scoped to cover
> both clients and sits at `stage: design`, because the open question is which
> layer owns address-family policy rather than which constant to change. Tuning
> one client's timeouts while the other stays 36x worse per attempt would make the
> hazard look addressed.

**What it does not do, and why.** Forcing IPv4, or resolving and racing
addresses here, would put a network-family policy into a museum client — a new
configuration surface invented in the middle of a build rather than a requirement
anyone stated, and one that would break an IPv6-only deployment. The residual
exposure is recorded instead: on a partial-IPv6 network a discovery run is slow
rather than wrong, its per-work progress is visible in the log, and the run's own
status long-poll keeps a client from hanging on it. **Backlog issue #47** carries
the fix.

This is also why the live suite is deselected by default: it is free, but it is at
the mercy of whatever the local network is doing.

```
cd curation && uv run pytest -m live_museum
```

**`live_museum`, not `live_api`** — the two are separate markers precisely so that
running this free suite does not also run the OpenRouter ones, which spend real
credit. `tests/live/test_artic_shapes_are_still_real.py` is the durable form of
everything above: the shapes here are prose, and prose nobody re-runs quietly
stops describing the API.

## Browsing by artist: filters work where relevance does not

Measured 2026-08-04, against the question of whether the collection can be asked
for *works by an artist* rather than for one named work. It can, over a `POST` to
the same `/artworks/search` endpoint carrying an Elasticsearch `bool.filter`.

**A filter context does not neutralise the boost.** Inside `bool.filter`, with no
scoring clause at all, one Ellsworth Kelly painting came back at `_score`
13535.94 and the rest between 6.4 and 7.9. Whatever produces that spread is
applied after the filter, so **ranking a browse by score reproduces the same
hazard ranking a search by score does** — the filters decide the set, and nothing
should read the order.

**`match` with `operator: and` is the artist query; `artist_title.keyword` is
not.** This corrects the alternative recorded above as unusable. A token-AND on
the analysed field is neither the free-text fold (which makes the artist compete
with the title) nor the exact keyword (which fails on the museum's own spelling):

```
artist_title.keyword  "Sonia Delaunay"        ->  0     (recorded above)
match/and             "Sonia Delaunay"        -> 13     spelled "Sonia Delaunay-Terk"
match/and             "El Greco (Domenikos Theotokopoulos)"
                                              ->  1     spelled "El Greco (Doménikos
                                                        Theotokópoulos) and workshop"
```

So the analyser folds diacritics and the AND matches a *subset* of the museum's
own name. Both are why the token-AND recovers names the keyword refuses.

**What it does not survive is a different name-form**, and this is the residual
failure. The AND requires every token, so a spelling the museum does not use
returns nothing while the artist sits in the collection:

```
"Wassily Kandinsky"          ->  0     while "Kandinsky" -> 24, all "Vasily Kandinsky"
"Titian (Tiziano Vecellio)"  ->  0     while "Titian"    -> 20
```

**A surname retry is the obvious repair and it is unsafe — measured, not
supposed.** Surnames collide, and the collision returns a *different artist*
under the first one's name:

```
"Martorell" -> antonio martorell (1), bernat martorell (1)
"Stella"    -> claudine bouzonnet-stella (18), frank stella (14), joseph stella (3), jacques stella (2)
"Delaunay"  -> nicolas delaunay (20), sonia delaunay-terk (13), jules-elie delaunay (11), robert delaunay (4)
```

**A `terms` aggregation on `artist_title.keyword` prices that ambiguity before
committing to it**: it reports how many distinct artists a surname reaches, so
"one" and "several" are told apart by measurement rather than by guessing.
`Kandinsky` and `Monet` return exactly one; the three above return two, six and
four.

**It must be its own request, and this is the trap.** The check cannot ride along
with the browse, because inside the browse's filters it manufactures the
confidence it exists to withhold. Measured: the collection holds one Antonio
Martorell, a `Graphic Design` the wall-type filter removes — so a filtered check
sees only `bernat martorell`, reports one artist, and licenses offering Bernat's
painting to a run that named Antonio. Unfiltered, the same surname reports both.
A `global` aggregation to escape the query context was tried and the API did not
answer it with JSON, so the check is a separate POST.

**The artwork-type filter is load-bearing, not cosmetic.** `artwork_type_title`
is a closed vocabulary (`Print` 45,961, `Photograph` 23,373, `Drawing and
Watercolor` 13,806, `Textile` 9,543, `Painting` 3,651, and 34 more). Restricting
to what hangs on a wall is what keeps a browse from offering a fabric swatch or a
poster layout as a painting:

```
Sonia Delaunay-Terk   13 works held, 0 of them Painting/Print/Drawing  (all Textile)
Antonio Martorell      1 work  held, 0 of them Painting/Print/Drawing  (Graphic Design)
```

**`thumbnail.width`/`height` come back on a browse too**, so the display floor is
applied to the same response that found the work — no per-result round trip, the
same property the per-work search has.

## What this hands off

| To | What |
|---|---|
| Phase-2 engine | Confidence is a title/artist comparison, never `_score` — and since the zero score went, that comparison is the only defence, not the main one |
| A browse by artist | `POST` a `bool.filter`: `exists image_id`, `terms artwork_type_title.keyword`, `match artist_title` with `operator: and`. Read the set, never the order |
| A browse by artist | The token-AND fails on an unused name-form, and a surname retry collides across artists — a `terms` aggregation on `artist_title.keyword` measures that ambiguity instead of assuming it |
| Museum query | The title alone is sent; the artist would compete with it for the ten result places, and is applied by the comparison instead |
| Phase-2 engine | One search request per work returns dimensions, rights and preview URL together |
| `CandidateImage` | `estimated_width`/`estimated_height` from `thumbnail.width`/`height`; `rights_status` from `is_public_domain`; `acquisition_method = dezoomify`; `provider = artic` |
| Preview caching | `{iiif_url}/{image_id}/full/843,/0/default.jpg`, one GET, no size negotiation |
| Acquisition | Full resolution requires walking an 843-pixel region grid; the advertised `maxArea` is not honoured |
| Client conventions | Send `AIC-User-Agent`; read the IIIF base from `config.iiif_url`; no rate-limit headers exist to read |
