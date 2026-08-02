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

**Independently confirmed against the ledger.** Re-reading `/key` about five
minutes later showed `usage` had moved by `0.00523805` since the pre-call read —
exactly the reported `0.00523535` plus the `0.00000270` generation that preceded
it, to the cent. So two independent routes agree: the $0.005 decomposition inside
`cost_details`, and the account ledger moving by the full reported figure.

Both were needed. The arithmetic alone could have been a coincidence of the fee
matching the published rate while billing separately; the ledger alone could not
have shown *which* component the money went to.

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
moved for that call more than a minute later. It had caught up in full by about
five minutes. **So the lag is minutes, not seconds**, and the settled figure is
exact when it arrives; the problem is latency, never accuracy.

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
- **Any model other than `openai/gpt-4o-mini` with the web plugin.** The fee was
  a flat $0.005 at `max_results: 3`; whether it scales with `max_results`, and
  whether it is flat across search back-ends, was not measured. The per-run search
  cap is sized against that number, so it is worth establishing before the cap's
  value is chosen.

## The client is first-party, behind a seam (decided 2026-08-02)

**A direct HTTP client, written against the shapes above, behind a narrow
interface** — not `threetears.models.create_chat_model`, which
`curation/pyproject.toml` had anticipated ("it arrives with the discovery work
that calls it"). That note is superseded here rather than left to contradict the
code.

The alternative was investigated properly rather than dismissed:
`langchain-openrouter` *does* preserve what the ceiling depends on, surfacing
`cost` and `cost_details` into `response_metadata`, so this is not a correctness
argument. Three things decided it anyway:

- **Everything routes through one provider.** The recorded cost decision sends
  search through OpenRouter's own web plugin rather than a direct search account,
  so a multi-provider abstraction is carrying no traffic. The engine-choice spike
  compares *search back-ends behind that one plugin*, not model providers.
- **The install lands on the Pi.** `3tears-models` pulls `3tears-observe`,
  `3tears-media-contracts`, `anthropic`, `langchain-anthropic`,
  `langchain-openai`, `langchain-openrouter` and `jsonschema` into the curation
  plane's **default** install — the plane that runs co-located with display under
  a `MemoryMax`. Today that weight is opt-in, confined to the `eval` group.
- **The two model uses are not the same axis.** The eval harness's model plays the
  *curator*, driving the MCP surface from outside; the engine's model is the
  *discovery worker* behind it. "One model-construction path" reads like reuse and
  would actually be coupling two unrelated roles.

**The seam is the point, and it is what makes this reversible.** The engine
depends on a narrow first-party interface, not on the transport, so adopting
`create_chat_model` later is a one-file change if a second provider ever earns
it. Deferring the dependency is not the same as ruling it out.

**What is taken from the existing implementation is pattern, not code** — the
in-house chat surface on this machine was read for exactly this. Two shapes carry
over: decision logic as pure functions with no infrastructure, so the approval
threshold is unit-testable without a model or a graph; and an explicit marker
distinguishing a *measured* number from an *estimated* one, so a reader can always
tell which they are looking at. Its human-in-the-loop machinery is deliberately
**not** adopted: that gate is a mid-turn graph interrupt held by a checkpointer,
while this product's gate sits *between phases* and is already durable in the
`DiscoveryRun` record with startup reconciliation behind it. Adopting a
checkpointer would give "where is this run" a second owner.

## Re-verification

Prices and endpoint shapes both move. The probe scripts are disposable by
design — the durable form of these findings is a test against the real API once
the client exists, per the project rule that a verification worth writing down is
usually worth keeping. Until that lands, this file is prose and should be treated
as a snapshot dated at the top.
