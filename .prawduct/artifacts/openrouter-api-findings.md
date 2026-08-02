# OpenRouter API Findings

Captured 2026-08-02 by probing the live API before writing any client, because a
fake built against assumed shapes encodes the assumptions rather than testing
them. Everything below is **measured**, not recalled or read from documentation,
except where a line says otherwise.

**Probed with a borrowed key** from another product on this machine (`limit` 10,
not the product's own ceiling). That is adequate for shapes and for the cost
arithmetic, and inadequate for anything about *this* product's ceiling — see
"What this did not establish".

## The generation response carries its own cost, in USD

Sending `usage: {"include": true}` in the request body returns a `usage` block on
the response:

```
usage.prompt_tokens          int
usage.completion_tokens      int
usage.total_tokens           int
usage.cost                   float   <- USD, the number that matters
usage.is_byok                bool
usage.cost_details.upstream_inference_cost              float
usage.cost_details.upstream_inference_prompt_cost       float
usage.cost_details.upstream_inference_completions_cost  float
usage.prompt_tokens_details.{cached_tokens,cache_write_tokens,audio_tokens,video_tokens}
usage.completion_tokens_details.{reasoning_tokens,image_tokens,audio_tokens}
```

**This retires the assumption that per-call cost needs a second request.**
`api-contract.md` and the build plan were written expecting `GET /api/v1/generation?id=…`
to supply it. That endpoint returned **HTTP 404** on every attempt here, with
`{"error": {"message": str, "code": int}}`. Whether it moved, was withdrawn, or
wants a different id form was not chased, because the inline field is strictly
better: one request instead of two, no polling lag, and no failure mode where the
generation record is not yet queryable.

### `usage.cost` includes the web-search fee

This is the load-bearing fact for the ceiling, so it gets its evidence written
out. One call with `plugins: [{"id": "web", "max_results": 3}]` reported:

```
usage.cost                                  0.00523535
usage.cost_details.upstream_inference_cost  0.00023535
difference                                  0.00500000   exactly
```

That difference is the documented $0.005 per-request search fee to the cent, and
`cost_details` accounts only for the inference portion. So **`usage.cost` is
inference plus search**, and a per-run actual summed from it is complete.

**Why this needed checking rather than assuming:** search fees bill as OpenRouter
credits but are not tokens, so any cost computed as tokens x price — which is what
a price-table lookup produces — would have silently omitted the one component
`nonfunctional-requirements.md` § Cost Constraints says can roughly double a run.
The failure would have been a systematic under-report, not an error.

**Confidence: high, and it is arithmetic rather than ledger observation.** The
$0.005 decomposition is exact and matches the published fee. The independent
confirmation — watching `/key` move by the full amount — is recorded below as not
yet obtained.

### Search citations come back as annotations

`choices[0].message.annotations` is present when a search ran, absent when none
did, which makes it the signal for "did this call actually search" rather than
inferring from cost:

```
annotations[].type                    str   ("url_citation")
annotations[].url_citation.url        str
annotations[].url_citation.title      str
annotations[].url_citation.content    str
annotations[].url_citation.start_index / end_index   int
```

Three citations came back for `max_results: 3`. The `content` field carries the
excerpt the model was given, which is what makes a discovered work traceable to
the page it came from rather than to the model's assertion.

## `GET /api/v1/key` — the ceiling from outside

```
data.limit                  int     (null when the key is uncapped)
data.usage                  float
data.limit_remaining        float
data.limit_reset            null    (on the probed key)
data.is_free_tier           bool
data.is_provisioning_key    bool
data.is_management_key      bool
data.include_byok_in_limit  bool
data.usage_daily / usage_weekly / usage_monthly       numeric
data.byok_usage{,_daily,_weekly,_monthly}             numeric
data.expires_at             null
data.creator_user_id        str
data.rate_limit.{requests:int, interval:str, note:str}
```

`usage_daily` / `usage_weekly` / `usage_monthly` were not anticipated by any
artifact and are worth knowing: the monthly figure is closer to what the ceiling
means than the lifetime `usage` is.

### `/key` lags materially, and the design must not depend on it being current

Measured: after a call reporting `usage.cost` of `0.00523535`, `/key`'s `usage`
had moved by `0.00000270` — the *previous* probe's generation — and had still not
moved for that call more than a minute later.

**This does not weaken the ceiling, and it does constrain what `/key` may be used
for.** The ceiling is enforced by OpenRouter returning 402, not by this product
reading a number and deciding — that is the ratified Direction norm, and the lag
is precisely the kind of silent failure that norm exists to avoid. So:

- `/key` is right for **displaying budget remaining**. It is eventually
  consistent, and a figure a few seconds stale is honest for that purpose.
- `/key` is wrong for **any in-run guard or gate**. A run that checked remaining
  budget between calls would be reading a number that does not yet include the
  calls it just made.
- Per-run actual comes from summing `usage.cost` across the run's calls, which is
  immediate and complete.

## What this did not establish

Named rather than left for a reader to assume covered:

- **Nothing about a $20-limited key.** The probe key's limit is 10 and belongs to
  another product. `limit_reset` read `null` here, so the monthly-reset behaviour
  the cost analysis relies on is **unobserved** — it may only populate on a key
  configured with a reset.
- **The 402 path was not driven.** No call was pushed into the over-limit
  response, so `halted_by_budget`'s trigger shape is still assumed. The build plan
  makes this an acceptance criterion for a reason; it needs a throwaway near-zero
  key.
- **One model, one provider route.** `openai/gpt-4o-mini`. Whether `cost_details`
  is populated identically across the models the discovery engine will actually
  use is untested.
- **The ledger confirmation of the search fee** — see above; the arithmetic is
  exact but `/key` had not caught up within the observation window.

## Re-verification

Prices and endpoint shapes both move. The probe scripts are disposable by
design — the durable form of these findings is a test against the real API once
the client exists, per the project rule that a verification worth writing down is
usually worth keeping. Until that lands, this file is prose and should be treated
as a snapshot dated at the top.
