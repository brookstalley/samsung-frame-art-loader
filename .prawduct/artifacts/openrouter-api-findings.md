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

## The vision call, and the model that makes it (measured 2026-08-03)

Probed before any mat client was written, with **real corpus images** rather than
a synthetic swatch: five works pulled as ARTIC IIIF derivatives, spanning a dark
blue, a sky blue, a warm Rothko, a pure-grey Mondrian and a near-black Hokusai.
Two rounds, thirty-one calls, **$0.0046 in total.**

### An image goes as a data URI on a content part, and costs nothing extra

The request differs from a text completion in one place — `content` becomes a
list of parts instead of a string:

```
messages[0].content = [
  {"type": "text",      "text": <the prompt>},
  {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,<...>"}},
]
```

The response shape is **identical to the text path** — same `choices[0].message.content`,
same `usage.cost`, same `finish_reason`. So the existing client's response reader
needed no change at all; only the request builder did.

**`usage.prompt_tokens_details.image_tokens` came back `None` on every model
probed.** Images bill inside `prompt_tokens`, so a cost estimate that added a
separate image charge would double-count. A 768-px JPEG lands in the low hundreds
of prompt tokens.

### An empty answer with `finish_reason: "length"` is a client fault, not a model one

**The finding that cost the most to learn, and the one most likely to recur.**
Round 1 reserved 700 output tokens for every candidate. Two models returned
**empty content, billed in full**, and read as "this model cannot follow the
schema". They are reasoning models: the reservation was spent entirely on
reasoning tokens before a single character of the answer was emitted.

```
openai/gpt-5-nano   max_tokens=700   ->  content "", finish_reason=length, 0/5 valid
openai/gpt-5-nano   max_tokens=3000  ->  1,600-2,048 reasoning tokens, 5/5 valid
```

So `max_output_tokens` has to clear a model's *reasoning* budget, not just its
answer, and the failure it produces when it does not is silent and expensive —
a billed call that returns nothing. **`finish_reason` is what distinguishes the
two**, and the mat client treats `length` as its own diagnosable case rather than
folding it into "the model did not answer".

### The choice: `qwen/qwen3.7-flash`

Cost is the operator's stated criterion at this stage — cheapest that does the
job, with evals and price/performance tuning deferred. Measured across both
rounds:

| model | valid JSON | mean ΔE to corpus | per call | note |
|---|---|---|---|---|
| **qwen/qwen3.7-flash** | **10/10** | **26.3** | **$0.000063** | ~160 reasoning tokens; never chose a bright mat |
| google/gemma-3-4b-it | 4/10 | 40.4 | $0.000037 | cheapest, but 429s on its provider and chose light mats |
| google/gemma-3-12b-it | 5/5 | 48.6 | $0.000041 | valid, but light greys and oranges |
| mistral-small-3.2-24b | 5/5 | 26.1 | $0.000093 | chose `#f5f5dc` — a near-white mat on a Mondrian |
| nex-agi/nex-n2-mini | 6/10 | 30.4 | $0.000142 | one answer omitted the leading `#` |
| openai/gpt-5-nano | 5/10 | 33.1 | $0.000821 | 13x the price, on reasoning tokens |

It is the only candidate that answered **every** call validly, it is the cheapest
of those that did, and its choices were the most conservative in the way this
product cares about: across ten images it never proposed a mat lighter than the
work, which is the one failure that glares on an emissive panel. The two cheaper
models both did — `#d8c69f` on a Rothko, `#f5f5dc` on a Mondrian.

**ΔE to the corpus is reported, not optimised against.** It is CIE76 distance to
the colour the 2024 pipeline chose and the operator kept, and a mean near 26 means
"a visibly different colour", which is what a different model choosing a mat
*should* produce. Ranking on it would be fitting a subjective judgement to one
prior sample of it. It earns its place as the sanity floor — a model answering
with distance 70 is not disagreeing about taste — and as the figure the operator's
corpus look starts from.

### Strict schema is honoured but **not guaranteed**, so the fallback is load-bearing

`qwen/qwen3.7-flash` advertises `response_format` but **not** `structured_outputs`
in `supported_parameters`, and still returned schema-conforming JSON on all ten
calls. Both facts matter: sending the schema is worth it, and *depending* on it is
not. The probe saw the concrete failures a client has to survive — content that is
empty, content that is truncated mid-string, and a hex triplet returned as
`3F6F7A` with no leading `#`.

This is why `MatColor.method` carries `dominant_color_fallback` as a first-class
recorded value rather than the mat engine retrying until the model complies. An
unparseable answer is a normal outcome of an unenforced schema, not an incident.

## The conversation call: a longer `messages` array, and two defects it exposes (measured 2026-08-12)

Probed against the live API, nine days after the vision call above, because the
curation-UX build plan needed its least confident assumption tested before code
was written against it:

> [ASSUMPTION: the conversation's model turn can be served by the existing
> OpenRouter client without a new abstraction | MED impact]

Same model as the choice above, `qwen/qwen3.7-flash`, routed to **Alibaba** on
every call — the cheapest vision-capable model this product has already chosen,
and therefore representative rather than a stand-in. **Total spend: $0.00156**
across 41 real calls in four rounds plus a latency probe.

**The assumption holds, and the gap is one method's signature, not a new
abstraction.** The *response* half of the client needs nothing at all. The
*request* half cannot express a conversation, because `complete()`
(`openrouter.py:235-291`) takes `prompt: str` and builds a one-message list from
it at `openrouter.py:270`:

```python
"messages": [{"role": "user", "content": content}],
```

There is no parameter through which a caller can supply a history; reaching a
multi-turn call means going around `complete()` into `_post()` directly, which is
what this probe did. The narrowest honest fix is a second method on the same
client taking a `Sequence[Message]` and sharing `_post`, `_read_body` and
`_read_completion` — not a new abstraction. What is not settled by this probe is
whether that method belongs directly on `OpenRouterClient` or behind a
conversation-shaped engine above it; the wire tells what it needs, not which
shape is right.

### A conversation is just a longer `messages` array, and the provider keeps no state

Every turn resends the whole history; there is no thread id, no
`previous_response_id`, nothing server-side to reference. Two threads were driven
four turns each, twice — once with reasoning on and once with it off — and a
third round isolated the round-trip questions: twelve multi-turn calls in all,
none of which needed anything the single-shot path does not already send.
`usage: {"include": true}`, `max_tokens` and `model` are the same three keys the
existing client sends today. A `system` message is accepted at the head of a
thread, which is where a conversation's standing instruction would go, and two
`user` turns in a row with no assistant between them are also accepted (HTTP
200) — so a thread whose model turn failed does not have to be repaired before
the next question can be asked.

This did not establish whether a *long* thread behaves the same. The longest
history probed was five messages and 628 prompt tokens, and nothing here measured
prompt caching — `usage.prompt_tokens_details.cached_tokens` came back `0` on
every single call, including the four that resent an identical 434-token image,
so on this route the resent history is **not** discounted.

### Everything downstream of the response was already correct — verified, not assumed

Running the probe's payloads through the real `_read_completion` confirmed:
`openrouter.py:393-395`'s `choices[0].message.content` with `or ""` in front of
it is load-bearing on this route, because a truncated turn returns
`"content": null`, not `""`, and the `or ""` is what keeps that from becoming a
`None` in a `Completion`. `usage.cost`, `cost_details.upstream_inference_cost`,
`prompt_tokens` and `completion_tokens` (`openrouter.py:397-410`) are all present
and identically shaped on a multi-turn image call. `finish_reason`
(`openrouter.py:413`) is present and is the only signal that separates a usable
turn from a truncated one. `annotations` (`openrouter.py:412`) is correctly
absent on every call here, since no search plugin was sent. `_money`'s
`parse_float=Decimal` (`openrouter.py:358`, `436-453`) parsed costs arriving as
both `0.00001896` and `4.78e-06` without incident.

Two things the client sends that a conversational turn should not want, and
neither is reachable to switch off: `schema` is optional, so a conversational
turn simply omits it — fine. `reasoning` cannot be passed at all, because the
body at `openrouter.py:268-278` has a fixed key set, which matters more than it
looks — see below.

### An assistant turn round-trips verbatim — unless its content is `null`, which is a 400

This is the finding a retryable multi-turn conversation most needs, because the
null case is exactly the failed turn such a feature has to keep in the thread.
The response message object on this route carries four or five keys —
`{"role": "assistant", "content": "…", "refusal": null, "reasoning": "…",
"reasoning_details": [...]}` — and fed straight back into the next request's
`messages`, including `reasoning`, `reasoning_details` and `refusal: null`, it is
accepted (HTTP 200). Stripping the two reasoning keys is also accepted. So the
extra keys are ignored, not rejected, and a caller may store and resend the
message object as it came.

**`content: null` is refused, by the provider, with a 400:**

```
{"error": {"message": "Provider returned error", "code": 400,
  "metadata": {"raw": "data: {\"error\":{\"code\":\"invalid_parameter_error\",\"param\":null,
                       \"message\":\"The content field is a required field.\",
                       \"type\":\"invalid_request_error\"},…}",
               "provider_name": "Alibaba", "is_byok": false}},
 "user_id": "user_…"}
```

Measured twice, on two different histories. **`content: ""` is accepted** — HTTP
200, and the model answered the following question sensibly. So a turn that
failed must be stored and resent with `""`, never `null`: a conversation that
stored the provider's `null` verbatim would 400 on the *next* turn, for a reason
that has nothing to do with why the first turn failed. `data-model.md` already
requires `ConversationTurn.text`, so the storage layer forbids null on its own —
the risk is a handler that passes the provider's message object through
untouched.

This did not establish whether other providers accept `content: null`. The
refusal came from Alibaba, not from OpenRouter's edge, so a route that lands on a
different provider may be more forgiving. Building on `""` is the safe answer
either way.

### An image on an **assistant** turn is refused outright

On the wire, a model's own reply cannot carry image content, only text:

```
POST with messages[1] = {"role": "assistant", "content": [
  {"type": "text", …}, {"type": "image_url", …}]}

400  "An incorrect modal `image` was entered, which may not be supported by the
      model or was placed in the wrong position (e.g., in system/assistant)."
```

Images may appear **only on `user` turns**, as a list of content parts — the same
shape the mat client already sends (`openrouter.py:262-267`). This decides the
design of any surface that shows a curator inline samples alongside a model's
reply: those samples are the product's own preview files, not pixels the model
returned, and nothing requires them to have come from the model. What it forbids
is the naive implementation where a stored assistant turn is replayed to the
provider with its samples attached — if a later turn needs the model to *see* a
sample it previously named, that image has to go on the **curator's** next turn,
not the assistant's stored one.

This did not establish whether a vision model exists on OpenRouter that accepts
assistant-role images. One model was probed. The finding to carry forward is that
the product must not depend on one existing.

### An image on an earlier turn is re-sent, re-billed, and genuinely re-read — every turn, at full price

Two four-turn threads, identical text, differing only in whether turn 2 carried
an image: a 768-px JPEG of a real corpus preview (45,276 bytes, a
60,391-character data URI). With every assistant turn forced to the empty string
in both threads, so the prompt-token difference is the image and nothing else:

| turn | thread A `prompt_tokens` (image) | thread B (control) | difference |
|---|---|---|---|
| 1 (no image yet) | 39 | 39 | **0** |
| 2 (image sent) | 502 | 68 | **434** |
| 3 (image in history) | 527 | 93 | **434** |
| 4 (image in history) | 551 | 117 | **434** |

**434 prompt tokens, to the token, on every turn the image remains in the
history.** The provider re-bills it in full each time; `cached_tokens` was `0`
throughout, so nothing discounts the repeat. `usage.completion_tokens_details.image_tokens`
was **`0`** here, not `None` as the 2026-08-03 vision probe recorded above —
either way the image bills inside `prompt_tokens`, and a cost model that added a
separate image charge would double-count.

What it costs, with reasoning disabled so the assistant turns carried real text:

| turn | C in/out | C cost | D in/out | D cost |
|---|---|---|---|---|
| 1 | 41 / 24 | 0.00000435 | 41 / 24 | 0.00000435 |
| 2 | 528 / 24 | 0.00001896 | 94 / 22 | 0.00000568 |
| 3 | 576 / 28 | 0.00002092 | 141 / 22 | 0.00000709 |
| 4 | 628 / 27 | 0.00002235 | 188 / 19 | 0.00000811 |
| **thread** | | **0.00006658** | | **0.00002523** |

One image carried through three further turns cost **$0.0000414** more than the
same conversation without it — about **$0.0000138 per resend** on this model. At
$0.03/M prompt tokens, an image is a rounding error; on a model priced like the
discovery model it would be roughly five times that, and still a rounding error.
The figure that would not be a rounding error is *many* images: a thread that
accumulated a dozen samples would carry ~5,000 prompt tokens of image on every
subsequent turn, growing without bound, so any surface that resends history has
to deliberately bound how many images stay in it. The measurement says the cost
is linear in (images × remaining turns).

And the model actually re-reads it — not inferable from the token count, so it
was asked directly. Turn 4 of both threads asked *"what colours dominate the work
I showed you earlier?"*, two turns after the image was sent: thread C (image in
history) answered *"The work is dominated by soft, muted tones of beige,
off-white, and faint gray, with subtle charcoal or graphite shading"* — the work
is a graphite portrait on aged paper, correct. Thread D (control) answered *"You
have not yet provided the work you are considering, so I cannot identify its
dominant colors."* So a resent image-bearing history is a working conversation,
not merely an accepted one.

This did not establish more than one image at one size on one model. The token
count scales with the encoded image, and `MAT_IMAGE_MAX_EDGE` (768) is the dial.
Nothing here measured two images in one turn, or an image on the first turn.

### Per-turn cost is one number, immediately, and a thread's cost is their sum

`usage.cost` is present on every turn, exactly as the single-shot path above
already relies on. There is no thread-level total and no need for one — a
`SpendRecord` per turn maps to `usage.cost` one-for-one, and a conversation's
cost is the sum of its turns' rows. Thread C turn 2, the image-bearing turn, in
full:

```
usage.prompt_tokens                                     528
usage.completion_tokens                                 24
usage.cost                                              0.00001896
usage.cost_details.upstream_inference_cost              0.00001896   (identical: no search)
usage.cost_details.upstream_inference_prompt_cost       0.00001584
usage.cost_details.upstream_inference_completions_cost  0.00000312
usage.prompt_tokens_details.cached_tokens               0
usage.completion_tokens_details.reasoning_tokens        0            (900 with reasoning on)
usage.completion_tokens_details.image_tokens            0
```

With no search plugin sent, `cost` and `upstream_inference_cost` are equal, so a
search-cost figure computed from the difference is correctly zero. Costs arrived
in both fixed and scientific notation — `0.00001896` on one call, `4.78e-06` and
`6.6E-7` on others — and `Decimal(str(value))` handled both; a fake built only
from fixed-notation numbers would not exercise that.

This did not establish whether `/key`'s ledger moves by the summed figure across
a thread. The 2026-08-02 measurement above established that for single calls and
that `/key` lags by minutes; this round did not re-check it, and there is no
reason to think a thread is different — each turn is an independent billed call.

### Reasoning is the failure mode of a conversational turn, and it is invisible

**The single most expensive thing this round found, and it is not what the build
plan was looking for.** Every one of the first ten calls returned **empty
content**, billed in full:

```
max_tokens=200   -> completion_tokens 202, reasoning_tokens 200, content null, finish_reason "length"
max_tokens=900   -> completion_tokens 902, reasoning_tokens 900, content null, finish_reason "length"
max_tokens=16    -> completion_tokens  18, reasoning_tokens  16, content null, finish_reason "length"
```

**`reasoning_tokens` came back exactly equal to `max_tokens` at every size
tried** — the reservation was consumed entirely by reasoning, before a character
of the answer was emitted. This is the same failure shape the mat call recorded
above, but there it was ~160 reasoning tokens on a tightly-specified schema
prompt at a reservation of 8,000, and it was recorded as solved. **An open-ended
conversational prompt is a different animal**: "suggest a direction for a calm,
contemplative wall" produced runaway reasoning at every budget offered.

`reasoning: {"enabled": false}` fixes it completely:

| | reasoning on | reasoning off |
|---|---|---|
| turn 1 content | `null`, `finish_reason: "length"` | *"Choose a single, large-scale piece with muted tones and ample negative space…"* |
| `completion_tokens` | 902 (900 reasoning) | 24 |
| cost | 0.00011843 | 0.00000435 |
| wall-clock | seconds to minutes | under a second |

**A 27-fold cost difference, and the difference between an answer and nothing.**
The whole reasoning-on round cost $0.00139 and produced ten empty turns; the
whole reasoning-off round cost $0.00013 and produced twelve good ones. **And the
client cannot send that key** — the fixed body at `openrouter.py:268-278` has no
`reasoning` parameter, so a conversational feature either passes it through
(which the same signature change that adds `messages` can carry), or sets a
reservation large enough that reasoning completes, which on this evidence is not
a number anyone can name in advance.

This did not establish whether reasoning-off is the right product answer. It is
the right *probe* answer — it made the shapes measurable. A conversational turn
might genuinely be better with reasoning on and a 16,000-token reservation, at
~30x the cost. That is a product judgement with a measured price tag attached,
not a fact this round settles.

### What a failure looks like on the wire, and a defect that hides half of it

Four kinds, and they arrive by three different routes. **Truncation** with
reasoning off returns *partial content* — the resendable case:

```
{"choices": [{"finish_reason": "length", "native_finish_reason": "length",
  "message": {"role": "assistant",
              "content": "The Hudson River School was the first American art movement, emerging",
              "refusal": null, "reasoning": null}}],
 "usage": {"prompt_tokens": 22, "completion_tokens": 12, "cost": 0.00000222, …}}
```

With reasoning on it returns `"content": null` instead. Both are billed, both
carry `finish_reason: "length"`, and only the second cannot be resent — the
finding above, "An empty answer with `finish_reason: 'length'` is a client
fault", **still holds**, and this round extends it: on a conversational prompt,
it is the *default* outcome, not an edge case.

**A refusal is not a failure at all.** Asked for sarin synthesis, the model
returned a polite decline as ordinary content — `finish_reason: "stop"`,
`refusal: null`, 174 completion tokens, $0.0000234. There is no wire signal that
distinguishes a refusal from an answer, so a conversation surface has to treat it
as a normal turn, which it is, and must not try to detect it.

A bad request from the provider arrives as HTTP 400 with the cause buried:

```
{"error": {"message": "Provider returned error", "code": 400,
  "metadata": {"raw": "…\"message\":\"curator is not one of ['system', 'assistant', 'user', 'tool', 'function']\"…",
               "provider_name": "Alibaba", "is_byok": false}}}
```

A bad request from OpenRouter's own edge has no `metadata` and says what is wrong
in `error.message` directly: `{"error": {"message": "Input required: specify
\"prompt\" or \"messages\"", "code": 400}}`. Nothing is billed on either —
`usage` is absent entirely.

**The client discards the diagnosable half of a provider 400.**
`openrouter.py:377-379`:

```python
error = body.get("error") if isinstance(body, dict) else None
if isinstance(error, dict) and error.get("message"):
    return str(error["message"])
```

For every provider-side 400 measured here, that returns the literal string
**"Provider returned error"**, collapsing at least three distinct causes — a null
content field, a misplaced image, an unknown role — into one string, while
`error.metadata.raw` carries the real one: *"The content field is a required
field"* or *"An incorrect modal `image` was entered"*. The user-facing message
becomes `OpenRouter returned HTTP 400: Provider returned error`. That is
tolerable for the two existing callers, which retry nothing and fall back. It is
not tolerable for a feature whose requirement is a failed turn that stays in the
thread and is retryable: the curator sees a failed turn with no account of why,
and a developer debugging it gets the same string regardless of which of the
three it was. **This is a pre-existing defect**, invisible while nothing
retries, that a retryable conversation turn would make user-visible. Reading
`error.metadata.raw` when present is a docstring-and-three-lines change in
`_provider_message`.

This did not re-establish the money refusals. 402 and 403 were not re-probed —
doing so means burning a key to exhaustion, they are already recorded against a
real key above, and `_read_body` discriminates them before any of this code is
reached. A conversation turn inherits that behaviour unchanged.

### A defect found by accident: the first request on an idle connection costs ~150 seconds, and the deployment shares the cause

Calls of identical shape took 0.3 s and 158 s. The pattern is not the model:

```
call 0: 151.25s   cost=0.00000185
call 1:   0.75s   cost=0.00000237
call 2:   0.88s   cost=0.00000250
call 3:   0.78s   cost=0.00000185
```

The cause, measured directly:

```
IPv4  104.18.3.115      connect 0.02s
IPv6  2606:4700::6812:273  FAILED after 20.00s: timed out
```

**`openrouter.ai` resolves to an IPv6 address that black-holes on this machine.**
httpx tries it first, waits out the connect timeout — which `_post` sets to
`COMPLETION_TIMEOUT_SECONDS`, 180 s (`openrouter.py:52`, `319`) — and then
succeeds over IPv4. httpx has no happy-eyeballs fallback and no connection
warm-up, so a cold connection waits out the full 180-second connect timeout
before falling back — measured at 151 s, then sub-second once warm. httpx's
default `keepalive_expiry` is 5 seconds, so **any gap longer than five seconds
between calls pays it again** — and a conversation, with a curator reading and
typing between turns, is nothing but gaps longer than five seconds.

Three consequences follow, and only the first is about this round: the round's
own wall-clock was dominated by this, not by the API. **The 180-second timeout is
the only reason anything works** — a shorter one, which a browser-facing turn
would reasonably want, turns every turn into `OpenRouterError: Could not reach
OpenRouter`. And it affects discovery and the mat engine **today**; it is
invisible there because both run on a worker thread behind an already-returned
run handle, while a conversation turn is a synchronous POST a curator is
watching.

**Traced afterwards, and the first reading was wrong in the way that mattered.**
This is not one machine's LAN. IPv6 is configured correctly and works locally — a
global SLAAC address, a valid default route, the router answering `ping6` in 5 ms.
Packets leave the house and die four hops out, in the *provider's* transit:

```
traceroute6 → Cloudflare              traceroute6 → Google
 1-3  (local, then the ISP)            1-3  (same)
 4    edge8.denver1.level3.net  15ms   4    edge8.denver1.level3.net  16ms
 5-12 * * * * * * * *                  5-12 * * * * * * * *
```

Over IPv4 that same Level3 interface forwards fine. So it is IPv6-specific,
**destination-independent** — Google and Cloudflare die identically — and
upstream of the building: an advertised prefix with no working transit behind it.
`openrouter.ai` is incidental; every AAAA on the internet black-holes from this
address.

**Which means the deployment shares it, and this stops being a dev-machine quirk
to note and move past.** The panel runs on the same uplink.

**The fix is one argument, and it does not wait on the ISP.** `_post` passes a
*scalar* `timeout=` (`openrouter.py:319`), and httpx applies a scalar to connect,
read, write and pool alike — so the dead socket gets the whole generation budget.
Splitting it bounds the doomed attempt without touching the budget generation
actually needs:

```python
httpx.Timeout(180.0, connect=5.0)
```

`discovery/artic.py` already carries exactly this shape; the mitigation this
codebase had already chosen was applied to one client and not the other.

**One number to be careful with, because two readings of this got it wrong in
opposite directions.** `openrouter.ai` publishes **two** AAAA records and two A
records (verified 2026-08-12) — not the ten an earlier arithmetic assumed. So
`connect=5.0` costs about *ten* seconds on a cold connection, not five and not
fifty: httpx walks the resolved list in order and each dead address costs the
bound. That is still the difference between a turn a curator abandons and one
they wait through. **And the measured 151 s does not decompose cleanly against
two addresses** — it is recorded here as measured and unexplained, rather than
fitted to a formula.

The finding is not "the provider is slow"; it is that the client has no fallback
path when the fast one is broken, on a network where the fast one is broken.

### What this round left open

One model, one provider, one day: every finding above is `qwen/qwen3.7-flash`
routed to Alibaba on 2026-08-12. The `content: null` refusal, the assistant-image
refusal and the runaway reasoning are all provider behaviours another route may
not share; the shapes — `messages`, `usage`, `finish_reason` — are OpenRouter's
own and are the same ones already recorded above. `DISCOVERY_MODEL` cannot do any
of this: `deepseek/deepseek-v4-flash` lists `input_modalities: ["text"]`, so a
conversation carrying images needs a vision model and its own model setting, the
same argument `config.py:413-419` already records for `mat_model` — this round
used the mat model because it was there, not because it was chosen. Nothing here
covers a long thread, concurrency or cancellation: four turns is the longest
measured, and nothing says what a fiftieth turn costs, whether two turns in
flight on one conversation interleave safely, or what happens when a curator
navigates away mid-turn. Nothing here is a caching measurement worth the name —
`cached_tokens` was `0` everywhere, which is a fact about this route rather than
a claim that caching is unavailable on OpenRouter. And nothing here is about the
surface above the wire: whether a commit card transforms in place, whether a
failed turn is visibly retryable, is outside what this probe can settle.

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
