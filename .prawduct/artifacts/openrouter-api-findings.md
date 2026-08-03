# OpenRouter API Findings

Captured 2026-08-02 by probing the live API before writing any client, because a
fake built against assumed shapes encodes the assumptions rather than testing
them. Everything below is **measured**, not recalled or read from documentation,
except where a line says otherwise.

**Two probe rounds, on different keys, and which one produced a finding matters
when reading it.** The first used a **borrowed key** from another product on this
machine (`limit` 10, not this product's ceiling): adequate for response shapes and
cost arithmetic, inadequate for anything about this product's own ceiling. The
second, later the same day, used **this product's own keys** — the real $20
monthly-reset key, and a throwaway limited to $0.25 that was deliberately burned
to exhaustion. Everything about the ceiling and the refusal codes comes from the
second round.

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
data.limit_reset            null | str   (null when no reset is configured;
                                          "monthly" on a key that has one)
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
for.** The ceiling is enforced by OpenRouter refusing the call outright (a 403 —
see below), never by this product reading a number and deciding. That is the
ratified Direction norm, and the lag is precisely the kind of silent failure the
norm exists to avoid. So:

- `/key` is right for **displaying budget remaining**. It is eventually
  consistent, and a figure a few seconds stale is honest for that purpose.
- `/key` is wrong for **any in-run guard or gate**. A run that checked remaining
  budget between calls would be reading a number that does not yet include the
  calls it just made.
- Per-run actual comes from summing `usage.cost` across the run's calls, which is
  immediate and complete.

## Exhaustion is **403**, and the 402 means something else (measured 2026-08-02)

**This corrects an assumption every artifact in this repo carried.** The refusal
that means "this key is out of money" is `403`, not `402`. Driven on a real key
with a $0.25 limit, burned to exhaustion:

```
403  {"error": {"message": "Key limit exceeded (total limit). Manage it using
                            https://openrouter.ai/…/keys/<key id>",
                "code": 403}}
```

**`402` is a different refusal, and it arrives with credit still in the account.**
It is a *pre-flight affordability check*, priced against `max_tokens` rather than
against what the call would actually cost:

```
402  "This request requires more credits, or fewer max_tokens.
      You requested up to 32000 tokens, but can only afford 3333."
```

The arithmetic is exact and worth understanding, because it is not what anyone
would guess: $0.25 remaining ÷ $75/M **output** price = 3,333 tokens. OpenRouter
reserves the *maximum output the request could produce* and declines if that
reservation exceeds the remaining credit. Nothing is generated and nothing is
spent — the first burn attempt returned 402 with `usage` still exactly `0`.

**Three consequences, none of them cosmetic:**

- **`halted_by_budget` is triggered by 403.** A client watching only for 402 would
  never recognise exhaustion at all.
- **A client that leaves `max_tokens` unset will be refused at full credit.** With
  no ceiling given, the reservation is the model's maximum output, so a nearly
  empty key refuses everything and a well-funded one refuses expensive models.
  Setting `max_tokens` deliberately is therefore a correctness requirement of the
  client, not a tuning choice — and treating that 402 as "out of money" would halt
  runs with money in the account.
- **The two must not be collapsed.** They call for different responses: 403 means
  stop until the limit resets or rises; 402 means ask for less and continue.

**The `/key` lag was demonstrated rather than inferred, in the same run.** While
live calls were already being refused as limit-exceeded, `/key` still reported
`usage 0.20634, limit_remaining 0.04366` — a key with money left, according to a
figure that was already wrong. That is the recorded lag, caught mid-error, and it
is exactly why `/key` may never gate anything.

## What this did not establish

**Two gaps this file named are now closed, recorded here rather than deleted so
that a reader of an earlier revision can see they were answered.** The
$20-limited key was provisioned and `limit_reset` reads `"monthly"` on it, and
the over-limit path was driven on a throwaway key — both above, both measured
2026-08-02. What follows is what remains open.

- **What a mid-generation exhaustion looks like.** Both refusals above arrived
  *before* any tokens were produced. Whether a call that begins affordably and
  crosses the limit while streaming is cut off, completed, or billed over is
  unmeasured — the runs here were short and the reservation check appears to make
  it hard to reach. `nonfunctional-requirements.md` states that a refusal arrives
  mid-run and a run can halt with some works acquired and others not; that remains
  true at the level of a *run* (many calls), and is unestablished for a single call.
- **Whether 403 distinguishes an exhausted key from a disabled one.** The message
  says "Key limit exceeded (total limit)", so the text discriminates; whether the
  status alone does is untested.
- **~~Whether the fee is flat across search *back-ends*.~~ Answered 2026-08-02:
  it is not, and the difference is large.** Everything below was measured on the
  default route, which resolves to Exa at $0.005 per request. Parallel bills
  $0.001 for the same work. A nine-call comparison ran at $0.0119 on Parallel
  against $0.0472 on Exa and $0.0475 on Perplexity — a four-fold spread on
  identical results, which is what decided the engine. So a per-request fee
  recorded here is a fact about *one back-end*, and `DISCOVERY_SEARCH_COST_USD`
  now has to agree with whichever `DISCOVERY_SEARCH_ENGINE` names.

## The web fee is per request, not per result (measured 2026-08-02)

**This closes the gap that most constrained the design**, and it went the useful
way. Four calls on `deepseek/deepseek-v4-flash` differing only in `max_results`:

| `max_results` | `usage.cost` | inference | fee | citations |
|---|---|---|---|---|
| 1 | 0.00512438 | 0.00012438 | **0.00500000** | 1 |
| 3 | 0.00524290 | 0.00024290 | **0.00500000** | 3 |
| 5 | 0.00530378 | 0.00030378 | **0.00500000** | 5 |
| 10 | 0.00534478 | 0.00034478 | **0.00500000** | 10 |

The fee is **identical to eight decimal places** while citations scale one for
one with the request. So **breadth is free**: a search returning ten pages costs
exactly what one returning a single page costs, and `DISCOVERY_SEARCH_RESULTS`
ships at 10 because a lower number saves nothing and sees less.

Two consequences beyond the number itself:

- **The per-run search cap keeps its recorded sizing.** It counts *requests*, and
  the price per request is what the analysis assumed. Nothing about the cap's
  value needed revisiting.
- **`cost_details` is populated identically on this model**, which closes the
  second gap this section used to name: the decomposition was previously measured
  only on `openai/gpt-4o-mini`, and the engine's actual default now shows the
  same shape.

**The recency gap was demonstrated in the same round, not argued.** The same
prompt without the plugin answered *"No major art prize has been awarded in 2026
as of 2025"*, and asked for a work list it returned 2022–2024 winners while
describing them as recent. With the plugin it returned 2026 prize winners. That
is issue #12's premise as a measurement.

## What one real phase-1 run actually costs (measured 2026-08-02)

A full run through the booted plane — `"recent award-winning art"`, nine works
proposed, one search at `max_results: 10`:

```
discovery_tokens   0.0005882058   3,453 in / 1,608 out
web_search         0.0050000000   1 request
run total          0.0055882058   (matches the provider's usage.cost exactly)
```

**The estimate shown for the same run was $0.127** — about twenty times the
actual. The overstatement is not in the prices, which are right, but in the
assumed token consumption: `DISCOVERY_PHASE1_INPUT_TOKENS` ships at 490,000
against a measured 3,453. The web plugin injects excerpts, not whole pages.

Both figures above are on the provider's default route, which is Exa at $0.005;
this run predates the engine decision. The phase-1 estimate is **$0.087** on the
engine since pinned, and the same run would bill about **$0.0016**. The
overstatement widens rather than narrows, because what is wrong with it is the
token basis and only the search component got cheaper.

~~**Recorded rather than corrected here, deliberately.**~~ **Corrected
2026-08-02, when phase 2 was built.** The reasoning for leaving it standing was
that the 490,000 figure came from a cost analysis of a *whole run* while the code
spent it on phase 1 alone, and phase 2's own consumption was in no estimate and
unmeasurable until phase 2 existed — so re-basing phase 1 in isolation would have
traded a visible overstatement for an invisible understatement.

**Phase 2 turned out to consume no tokens at all.** It queries museum APIs, which
are open and unmetered, and decides whether a result is the requested work by
comparing titles and artists locally rather than by asking a model
(`artic-api-findings.md`). So the understatement the correction was held back
against does not exist, and both halves could be settled at once:

```
DISCOVERY_PHASE1_INPUT_TOKENS    490,000  ->  8,000   (measured 3,453, bounded at ~2x)
DISCOVERY_PHASE1_OUTPUT_TOKENS    30,000  ->  8,000   (the provider-priced reservation)
phase-1 estimate                  $0.087  ->  $0.01336
phase-2 estimate            work_count x 2 searches  ->  $0
```

The measured run above billed $0.0056 on the default route and would bill about
$0.0016 on the pinned engine, so the shipped bound is now roughly eight times a
real run rather than fifty — which is what a bound over an allowance a run uses
one of should look like. See `nonfunctional-requirements.md` § Cost Constraints.

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

Prices and endpoint shapes both move, so **this file is no longer the durable
form of these findings — a test is.**
`curation/tests/live/test_openrouter_shapes_are_still_real.py` asserts each fact
above that the client depends on, against the live API:

```
cd curation && uv run pytest -m live_api
```

It is deselected by default because it spends real money, and each test names the
client behaviour that breaks if its fact stops holding — so a failure reads as
"the provider moved, and here is what now mis-parses". Covered: inline
`usage.cost`, the flat per-request web fee, citations and their excerpts, the
key's monthly ceiling, strict structured output on the default model, a
recency-bound intent resolving to post-cutoff works, and — on a deliberately
exhausted second key — a real 403 halting a real run as `halted_by_budget` with
no spend recorded.

The prose above remains the *record of when and how* each fact was established,
which a test cannot carry; treat its numbers as a snapshot dated at the top and
the test as the thing that keeps them honest.
