---
artifact: nonfunctional-requirements
version: 1
depends_on:
  - artifact: product-brief
last_validated: null
---

# Non-Functional Requirements

This product has one household, one TV, and one curator. Almost nothing here is
about scale. The three things that genuinely constrain it are **money** (an
unbounded agent loop against a metered API), **silence** (the only feedback
channel is a picture on a wall, so failure looks like success), and **visual
quality** (the entire point of the product is how something looks from across a
room). Those get depth. Throughput and concurrency get a sentence each, because
that is what they are worth here.

## Direction

<!-- Ratified by the owner 2026-07-20. A third candidate — "any operation that
     spends money reports its estimated cost before it runs and its actual cost
     when it finishes" — was proposed and deliberately NOT ratified; it survives as
     descriptive content under Cost Constraints § Cost visibility. Do not promote it
     back without the owner's call. -->

**Spend ceilings are enforced by the provider, never by application code.** The
monthly cap lives on the OpenRouter API key as a per-key credit limit with a
monthly reset. Application code may *read* spend — to estimate before a run, to
display after one, to halt gracefully — but it never owns the ceiling, and no code
path is permitted to be the only thing standing between the product and an
unbounded bill.

> **Why:** An application-side meter that fails open is indistinguishable from one
> that works. There is no error, no alert, and no wrong-looking behaviour — just a
> bill at the end of the month. Every failure mode is silent: a code path added
> later that forgets to check, a crash between the check and the call, an
> off-by-one in the accumulator, an exception swallowed inside the meter itself.
> This is precisely the defect shape this codebase already exhibits — `upload_file`
> catches every exception, logs it, and reports success anyway — so the product has
> demonstrated it is capable of building exactly this bug. A server-side per-key
> limit refuses the call and cannot be bypassed by any of those.
>
> **Corollary — read from the authority, not from a local tally.** "Budget
> remaining" is read from `GET /api/v1/key` (`limit_remaining`), and per-run actual
> cost from the `cost` field OpenRouter returns with each generation. A local
> counter would be a second source of truth for a number the provider already owns
> authoritatively, and the two would drift.
>
> *(Unchanged, and deliberately: this says where the number comes from **if** it is
> shown. **Whether to show it was settled "no" by the operator on 2026-08-04:
> `limit_remaining` is not surfaced in any form.** It lags the provider's own
> enforcement by minutes and was observed reporting credit remaining while calls
> were already being refused, so a panel carrying it would tell a curator they
> had budget at the moment they did not. That answer leaves this corollary
> exactly as it stands — it governs where the number is read from, not whether it
> is displayed — which is why the corollary was not swept when the question was.
> `services/health.py` carries the same decision at the site that would hold the
> field, and says not to add it back without reopening the decision.)*
>
> **Scope note:** this norm governs *ceilings*, not *budgeting*. A per-run search
> cap (below, under Cost) is application-enforced and does not depart from this —
> it bounds one run's ambition, it is not the thing that stops the bill.
>
> **Status:** steady-state.
>
> **Retroactivity:** No migration owed. `ai.py` spends money with no cap of any
> kind, but it is being replaced rather than extended, and the replacement is
> in-scope for v1 ("Hard monthly LLM spend cap that fails closed").

**The display plane's ability to show art never depends on the curation plane
being reachable.** Any design in which the Pi must reach the curation host to
select, render, or continue showing artwork is a departure requiring a recorded
decision.

> **Why:** The availability asymmetry is not a preference, it is the entire
> structural justification for splitting the product into two planes. Curation
> downtime is invisible — the household never sees it. Display downtime is a blank
> wall in a living room. If the display plane needs curation to be up, the split
> has paid all of its costs (a process boundary, a contract, two deployments, two
> Python versions) and delivered none of its benefit, and the honest move would be
> to collapse back to one process.
>
> **Boundary this norm had to survive, now resolved.** `api-contract.md` used to
> exempt the curation↔display contract from all stability obligations on "single
> consumer, deployed together" grounds — incompatible with this norm, because
> deployed-together and survives-independently cannot both hold without saying what
> the display plane keeps locally and how stale it may be.
>
> Settled 2026-07-20: the display plane holds a **theme manifest** file and may be
> arbitrarily stale — if curation stops, it keeps showing the last manifest
> forever, which is correct behaviour rather than degradation. The exemption is
> narrowed to a bounded obligation (additive changes free; a breaking change bumps
> a major that display refuses). Mechanism in `architecture.md`; contract row in
> `api-contract.md`.
>
> **Status:** steady-state.
>
> **Retroactivity:** The 2024 single-plane code has no curation plane to depend on,
> so it conforms vacuously. Nothing to migrate.

## Performance

**The product imposes no latency budget on curation. Its MCP client does.** This
is the inversion worth understanding: discovery is expected to take minutes, is
explicitly human-triggered, and nobody is waiting on a spinner — so the product
itself has no opinion. But Claude Code, verified 2026-07-19, aborts an HTTP call
that has sent no response and no progress notification for **5 minutes**, and
auto-backgrounds a call still running after **2 minutes**. Those are the only hard
latency numbers in the product, and they are inherited, not chosen.

| Requirement | Value | Where it comes from |
|---|---|---|
| A discovery call returns its run handle | immediately (< 2 s) | Anything else is a blocking call, which the 5-minute idle abort kills |
| Maximum duration of any single MCP call | 45 s | The status long-poll is the only long call, and it is what keeps every call comfortably under both client thresholds. **Corrected 2026-07-20** — this row previously required progress notifications every 60 s and called them load-bearing; see the note below |
| Status long-poll hold | ≤ 45 s | Sized under a 60 s tool timeout; the figure is `hallucinote`'s, arrived at independently |
| Phase 1 (intent → work list) | minutes, unbudgeted | Human-triggered, and the curator has just typed an intent and expects to wait |
| Phase 2 (per-work image search) | minutes, unbudgeted | Same. It runs in the background behind the run handle, so its duration never appears as a single call |

> **Progress notifications are not a latency requirement — corrected 2026-07-20.**
> This section originally required a notification every 60 s and called the
> mechanism load-bearing. It is neither required nor reliable:
> `Context.report_progress` silently no-ops when the client sent no
> `progressToken` (`mcp/server/fastmcp/server.py:1170-1173`), and with the run
> handle returning immediately, no call is ever idle long enough to be aborted.
> They are permitted as a nicety; nothing may depend on them. Full reasoning in
> `api-contract.md`.

**Display plane.** The label is the constraint, and the panel's own refresh
(seconds, on 16-level greyscale e-paper) dominates any code path.

| Requirement | Value | Status |
|---|---|---|
| E-paper label matches the displayed artwork, after a TV image change | within 15 s | `[ASSUMPTION: 15 s | LOW impact | user can correct]` — chosen so the label is right before a viewer who noticed the image change has walked over to read it. The panel refresh is most of it |
| Art on the wall is correct after a display-plane restart | within 60 s | `[ASSUMPTION: 60 s | LOW impact | user can correct]` — bounds systemd restart plus reconnecting the TV websocket |
| Image preparation on the Pi | unbudgeted, but it stays on the Pi | **Corrected 2026-07-20**, hours after this table was written. It said "moved off entirely"; the operator then decided both planes run on the Pi. Measured: largest corpus work is 49 MP (~148 MB loaded), and the colour work downsizes to 2048² first (~100 MB), against 8 GB. Comfortable. The exposure is a true 1–2 gigapixel scan — see `architecture.md` § Scaling Model |

## Scalability and Capacity

**Scale is explicitly not a goal.** One household, one TV, one curator, one
discovery run at a time. Anything that trades simplicity for scale is the wrong
trade. What follows is therefore sizing, not scaling — the numbers exist to prove
that no capacity problem exists, so that no capacity engineering happens.

> **Amended 2026-08-10: the catalogue target moves from "hundreds" to thousands
> of works, and nothing else in this section moves with it.** The operator set the
> target while scoping the curation interface, and the amendment is deliberately
> surgical: *load* is still one household, one curator, one run at a time, and
> every claim below that rests on load — concurrency, run rate, image preparation,
> the co-location decision — stands unchanged and unre-argued. What a bigger
> catalogue changes is **how much a reader must be able to find their way through**,
> and that is a human-interface problem before it is a capacity one.
>
> The consequences that do follow, recorded here because the interface work
> depends on them rather than being free to rediscover them:
>
> - **Search stops being optional.** At hundreds of works a curator can scroll; at
>   thousands they cannot, and a catalogue with no query is a catalogue with no
>   retrieval. This is the one place the amendment creates a *requirement* rather
>   than relaxing a bound, and it lands on the collection surface, not the store.
> - **A client may no longer hold the whole catalogue.** `app.js` fetches every
>   page of `/api/works` and renders a card each. That is correct at 41 and
>   indefensible at 4,000 — the browser surface has to page, filter and virtualise
>   against the server instead. The runaway guard that made whole-catalogue
>   fetching safe is not a substitute for not doing it.
> - **Thumbnail generation becomes a first-visit cost.** Thumbnails are made on
>   first ask; a first view of a thousands-work catalogue asks for as many as it
>   paints. Bounded by paging, which is another reason paging is not optional.
> - **Storage stays comfortable but stops being unremarkable.** On the 15 MB/work
>   all-in basis below, 2,000 works ≈ 30 GB and 5,000 ≈ 75 GB. A Pi with a USB SSD
>   still carries that, so the co-location decision does not reopen — but "fits on
>   anything" is no longer the reason, and a deployment now has a disk figure worth
>   stating rather than waving past.
>
> **SQLite is still not the question.** Low thousands of rows was already a
> non-issue at the old target and remains one at this one; the change is entirely
> above the store.

Measured against the real 41-work corpus (`all.json`, 2026-07-19):

| Dimension | Today | Design target | Verdict |
|---|---|---|---|
| Works | 41 | **thousands** *(was "hundreds"; amended 2026-08-10, above)* | SQLite at low thousands of rows is a non-issue. The pressure is on retrieval and on the browser client, not on the store |
| Source image size | mean 17.6 MP, median 14.5 MP, max 49 MP (6220×7912) | unchanged | 39 of 41 are *downscaled* to reach a 4K canvas — source resolution is amply sufficient across the corpus |
| Source image bytes | ~0.4 GB for 41 works (~10 MB/work) | ~15 MB/work all-in incl. renders, thumbs, labels | **500 works ≈ 10 GB** |
| Concurrent discovery runs | — | 1 | One curator. Concurrency is a correctness question (two runs racing on the same work), not a throughput one |

**Storage is not an architectural constraint, and specifically does not force the
curation plane onto a NAS.** 10 GB for a corpus ten times the current size fits on
any laptop, any desktop, or a Pi with a USB SSD. This removed one input from the
question of where the curation plane runs, which was **CLOSED 2026-07-20: both
planes are co-located on the Pi** (`project-state.yaml`). Decided on availability
and always-on-ness, as this section argued — not on disk. Left phrased as open
here until 2026-07-20.

**The one thing that could break this estimate** is gigapixel sourcing. Google
Arts & Culture scans fetched via dezoomify can reach 1–2 gigapixels — roughly 100×
the corpus mean — and a corpus that skews that way changes the number by an order
of magnitude. Whether stored source resolution is capped, and at what, is an open
acquisition-pipeline decision; it is flagged here because capacity is where it
becomes visible.

**The tile cache is the transient exception.** `tile-cache/` and `temp/` are
working space during acquisition, not steady-state storage, and are sized by the
largest single work in flight rather than by the corpus.

## Availability

| Plane | Target | What "down" means |
|---|---|---|
| Display | Continuous. Recovers without human action | The TV is not advancing through the active theme, **or** the label disagrees with the artwork |
| Curation | On-demand. No uptime target | The web UI or MCP surface does not answer. Invisible to the household by definition |

**The failure mode that matters is that display-plane "down" looks exactly like
"up".** A stalled loader leaves the TV in art mode holding the last selected work
— which is a perfectly good picture on a wall. Nobody notices for days. Every
availability requirement here is therefore really a *detection* requirement, and
it is owned by `observability-strategy.md`: an availability target with no way to
observe a breach is a wish.

**Recovery is unattended or it does not count.** The display plane runs under
systemd with `Restart=always` and must survive TV power-cycles, websocket drops,
and network outages without anyone SSHing in. The curator is not on call for their
own living room.

### The television belongs to whoever is using it

**The display plane never takes the screen from a person.** It may only put a
picture up when the set is *already* showing art. If somebody is watching
something, or the set is off, the wall waits — it does not select, it does not
advance its place in the theme, and it does not consume a pending directive.

This is a requirement about the household, not about the API, and it outranks
availability: **a wall that is late is a smaller failure than a television that
interrupts the person watching it.** The availability target above says the
display plane is "down" when it is not advancing through the theme; this is the
one condition under which not advancing is correct.

Recorded 2026-08-07, after it happened. It was not written down before because
the failure had never been observed, and the plane had a deliberate decision
pointing the other way — art mode was read only *after* a selection failed, on
the reasoning that reading it beforehand would spend a call on every rotation
about to succeed. That priced a wasted call against nothing, because the cost on
the other side had not been measured. It has now: with the operator watching a
programme, a due rotation sent `select_image` and the set **switched itself into
art mode**, and the picture they were watching was gone. Somebody watching
television is a daily event, so this is a daily interruption, not an edge case.

**What the plane may rely on**, from `samsung-tv-state-findings.md`: `get_artmode`
answers `on` only in art mode, and `off` in both the states where selecting is
wrong — so one reading distinguishes them, and `PowerState` does not (it reads
`on` for a television programme). The set announces its own transitions on the art
channel, so returning to art mode is observed rather than waited for.

**Not in scope, deliberately: the plane does not turn the television on.** A dark
set stays dark until a person lights it. That is a product decision — a picture
frame that switches itself on is a different appliance — and it currently costs
nothing to honour, since neither `select_image` nor `set_artmode('on')` can wake
this set anyway.

### Durability — the catalogue is the irreplaceable asset, not the images

This is the non-obvious one, and it inverts the intuitive backup priority.

Every source image is re-fetchable from its source URL — the product already
relies on this, and it is the stated reason `all.json` is being replaced rather
than migrated rather than treated as precious. What is **not** re-fetchable is the
curatorial layer: which works were accepted and which rejected, which image
instance was chosen as canonical and why, hand-approved mat colours, theme
membership, and the suppression scopes that keep rejected work from coming back.

Losing that means re-running discovery, which costs real money and re-asks the
curator every judgement they have already made. So:

- **The SQLite catalogue is backed up.** It is small (megabytes), it is the entire
  product's memory, and it is the only artefact whose loss cannot be repaired by
  spending time instead of money.
- **The image tree is disposable.** `raw/`, `ready/`, `tv-thumbs/` and
  `tile-cache/` are all reconstructible. They are excluded from
  backup deliberately, not by oversight — this is the upstream/derived split
  already recorded in `learnings.md`, applied to durability. (`label/` was listed
  here from the 2024 layout; it is retired from the prospective `ART_ROOT`
  contract — labels render on the display plane. See `boundary-patterns.md`.)

## Cost Constraints

**Hard ceiling: USD 20/month on all LLM and search spend, failing closed.** No
cloud hosting costs; both planes run on hardware already owned; electricity only.

The cap's purpose is to **bound an unbounded agent loop**, not to economise on
token price. At the chosen models $20 buys far more discovery than a household
needs, so the cap should feel generous in normal use and bite only when something
has run away.

### What a run actually costs

Model prices **re-verified against the live `GET /api/v1/models` endpoint
2026-08-02**; search prices carried from OpenRouter's documentation, 2026-07-19
and re-verified 2026-07-20. LLM and search pricing moves fast — **re-verify
before relying on these figures.** The 2026-08-02 pass earned its keep: GLM-5.2
had risen ~28% from the figure recorded on 2026-07-20, while DeepSeek V4 Pro was
unchanged to the cent. A price table nobody re-reads is a table that quietly
stops describing the product.

The per-run token basis was **~0.49M input / ~0.03M output** until 2026-08-02.
**It is now 8,000 in / 8,000 out**, and both halves of that changed for different
reasons, which matters because the second one reorders the table.

*Input* is a measurement: a real run consumed **3,453** tokens, because the web
plugin injects excerpts rather than whole pages. 8,000 is roughly twice that,
for headroom.

*Output* is not a measurement — it is `DISCOVERY_MAX_OUTPUT_TOKENS`, the
reservation the provider prices and refuses against. A run physically cannot emit
more, so it is the true bound, where any multiple of the measured 1,608 would be
a chosen one.

**The consequence: the basis is no longer input-dominated, so output price is no
longer nearly irrelevant.** The old basis had output at 6% of tokens and the
claim followed; the new one is even, and a model with cheap input and expensive
output is now priced accordingly. Two rows swap because of it — Gemini 3.5 Flash
Lite, at $2.50/M output, moves from third to last. **The decision below is
unaffected**: DeepSeek V4 Flash is cheapest on both bases, by a wide margin on
each.

| Component | Unit cost | Per run, old basis | Per run, measured basis |
|---|---|---|---|
| Discovery tokens — **DeepSeek V4 Flash** *(the default)* | $0.14/M in, $0.28/M out | ~$0.08 | **~$0.0034** |
| Discovery tokens — GLM-5.2 | $0.2842/M in, $0.8932/M out | ~$0.17 | ~$0.0094 |
| Discovery tokens — DeepSeek V4 Pro | $0.435/M in, $0.87/M out | ~$0.24 | ~$0.0104 |
| Discovery tokens — Gemini 3.5 Flash Lite *(named alternative)* | $0.30/M in, $2.50/M out | ~$0.22 | ~$0.0224 |
| Web search — **Parallel** *(the default, chosen 2026-08-02)* | $0.001/request (10 results incl.) | $0.03–0.05 | **$0.010** |
| Web search — Exa via OpenRouter | $0.005/request (10 results incl.) | $0.15–0.25 | $0.050 |
| Web search — Perplexity | $0.005/request | $0.15–0.25 | $0.050 |
| Mat-colour vision — **Qwen3.7 Flash** *(the default, chosen 2026-08-03)* | $0.000063/call, one call per *accepted* work | negligible | **$0.0013 per 20 works** |
| Museum APIs, image acquisition | $0 | bandwidth only | bandwidth only |

The search rows fall in the fourth column for a different reason from the token
rows: not a re-based basis, but **phase 2 no longer searching the web at all**.
Only phase 1's flat allowance of 10 is billed, where the third column priced all
50 of the two-part cap.

**This retires the recorded worry that search could exceed token spend "by an
order of magnitude".** On the old basis a run landed between **$0.11 and $0.33**
across every row above, so $20 bought on the order of **60–180 runs a month**,
and search went *inside* the ceiling comfortably.

**On the measured basis search is the dominant component after all — and it no
longer matters.** A bounded run is now cents rather than tens of cents, so the
ceiling is not the constraint it was sized against and the ranking above is a
model-choice input rather than a budget one. The worry was about proportion; what
retired it in the end was the absolute figure falling by a factor of ten.

> **On the engine actually pinned, a bounded run lands at $0.013 (2026-08-02).**
> The range above spans all four models and all three back-ends, which was the
> right shape while both were open. With `parallel` chosen and
> `deepseek/deepseek-v4-flash` the default, the bounded figure was $0.127 — about
> eight cents of model call and five of search — until the token basis behind the
> model half was re-based against a measured run later the same day. It is now
> **$0.01336**: a third of a cent of model call and a cent of search allowance.
> $20 buys on the order of **1,500 bounded runs a month**, and far more real ones,
> since a typical run uses one of its ten searches.
>
> **The "search is now the dominant component" reading that used to sit here was
> true of a $0.005 request and is not true of a $0.001 one.** Model spend is now
> the larger half again. The prices in the table are per-request facts about
> vendors and stay as they are; which one applies is the decision in "Decided —
> engine choice" below, and `DISCOVERY_SEARCH_COST_USD` has to move with
> `DISCOVERY_SEARCH_ENGINE` or every pre-run estimate is wrong five-fold.
> `test_the_search_price_matches_the_engine_that_is_pinned` is what stops them
> drifting apart.

> **A measured phase-1 run came in at $0.0056 against an estimate of $0.127
> (2026-08-02, both figures as they stood before the engine was chosen).** The
> first real run through the built engine — nine works, one search at ten results
> — billed $0.0005882 of tokens (3,453 in / 1,608 out) plus the flat $0.005
> search fee. **Search was 89% of it.**
>
> On the engine now pinned both sides fall: the phase-1 estimate is **$0.087** and
> the same run would bill about **$0.0016**. The ratio between them goes from
> roughly twenty-fold to roughly fifty, because the estimate's error is in assumed
> *tokens* and only its search component got cheaper.
>
> That run predates the engine decision and used the provider's default, which
> resolved to Exa at $0.005. On the engine now pinned the same run bills about
> $0.0016 — measured separately at ~$0.0013 per searching call during the engine
> comparison — with search a smaller share of a much smaller total. The gap
> against the estimate widens rather than narrows.
>
> **The prices are right; the assumed token consumption was not.**
> `DISCOVERY_PHASE1_INPUT_TOKENS` shipped at 490,000 against a measured 3,453,
> because the web plugin injects *excerpts* rather than whole pages. That was the
> whole of the twenty-fold gap.
>
> **~~Left standing rather than re-based~~ — corrected 2026-08-02 when phase 2
> was built.** The reasoning for holding off was that 490,000 is this section's
> own per-run basis covering a *whole* run, while the code spent it on phase 1
> alone, and `phase2_estimate_usd` priced search only, so phase 2's model calls
> were in no estimate at all. Re-basing phase 1 in isolation would have traded a
> visible overstatement for an invisible understatement.
>
> **Phase 2 consumes no tokens, so the understatement does not exist.** It asks
> museum APIs, which are open and unmetered, and decides whether a result is the
> requested work by comparing titles and artists locally rather than by asking a
> model. Both halves therefore settled together:
>
> | | before | after |
> |---|---|---|
> | `DISCOVERY_PHASE1_INPUT_TOKENS` | 490,000 | **8,000** (measured 3,453, bounded ~2x) |
> | `DISCOVERY_PHASE1_OUTPUT_TOKENS` | 30,000 | **8,000** (the provider-priced reservation) |
> | phase-1 estimate | $0.087 | **$0.01336** |
> | phase-2 estimate | work count x 2 searches x $0.001 | **$0** |
> | a bounded run | $0.127 | **$0.01336** |
>
> The bound is now roughly eight times a real run rather than fifty, and the
> remaining gap is the search allowance: the estimate prices all ten searches
> because that is the most a run may use, and a typical run uses one. **That gap
> is the estimate doing its job**, not an error to squeeze out — a figure a run
> may freely exceed is not an estimate.
>
> **The per-run search cap is unchanged at 10 + 2/work.** It still bounds fan-out
> and is still reported beside a run's usage; what changed is that nothing it
> bounds is billed. A paid image provider added later reinstates the arithmetic
> in `phase2_estimate_usd`, which is the one place it lives.
>
> *(Superseded reasoning, kept because it is the shape of a good call rather than
> a wrong one: the correction was deferred to the chunk that builds phase 2, being
> the first point at which both halves could be measured. Until then the estimate
> was conservative in the safe direction, and the* actual *is reported from the
> provider on every surface — so nobody ever had to trust the estimate to know
> what a run cost. What made the deferral right was that the direction of the
> unknown was known: phase 2 could only add cost, never remove it.)*

**The phase-1 model is a deployment value, defaulting to
`deepseek/deepseek-v4-flash` (decided 2026-08-02).** The owner ruled out the
frontier tier explicitly. The reasoning that survives beyond that ruling: phase 1
is input-dominated extraction and synthesis rather than deep reasoning, which is
the task profile where tier differences are smallest and the price multiple is
largest — the frontier tier costs ~8× the chosen one. (The run-count figures that
stood here, 13–15 a month against 60–180, were computed on the pre-measurement
token basis. The *multiple* is what the ruling turned on and it is unchanged;
both absolute counts are now an order of magnitude higher.)

**No quality evidence distinguishes the candidates, and that is stated rather than
papered over.** The models above are ranked here on price, which is measurable, and
on nothing else. Whether a stronger model enumerates real works better than a
cheap one *on this product's intents* is unmeasured — the same gap that was
recorded for search back-ends under "Decided — engine choice" below. Gemini 3.5
Flash Lite is carried as the named alternative for that comparison at ~2.9× the
token cost.

**Measured 2026-08-02, and the default stands.** Both tiers were run over three
real intents with the pinned engine, and every work either proposed was checked
for an institutional page — the shape a hallucinated title takes here is one no
museum has heard of. `deepseek/deepseek-v4-flash` proposed **11 works, 11
verifiable**; `google/gemini-3.5-flash-lite` proposed **8 works, 8 verifiable**.
Neither invented anything, and the cheaper model proposed more.

**This is weak evidence and is recorded as such.** Three intents is a small
sample; "an institutional page exists" is a proxy for the work being real, not a
proof of it; and it cannot see the failure that would matter most — a model
quietly proposing *duller* works that are all perfectly real. What it does rule
out is the specific worry that motivated carrying an alternative: that the cheap
tier would fabricate plausible titles. It did not, on this sample.

**The same prediction failed for search back-ends** — quality was expected to
decide and did not discriminate at all, leaving price the only difference. Two
comparisons is not a rule, but it is now twice that the dearer option did not
earn its multiple on this product's work.

The default is the **floating** model id rather than a dated snapshot, so a
snapshot retirement cannot break the only paid path on a household product; the
dated pin is ~36% cheaper, which against this ceiling is not decision-relevant.
The spike's regression measurements pin an explicit snapshot instead, so a
floating alias moving underneath them cannot read as a quality regression.

### Three decisions this analysis produced

**Search is routed through OpenRouter's web plugin, not a direct search-provider
account.** Recorded as a finding rather than a trade-off, because it is strictly
better on both axes: Exa through OpenRouter is $0.005/request against $0.007
buying direct, *and* search fees bill as OpenRouter credits — so token spend and
search spend become one number under one ceiling instead of two meters that have
to be added up by something.

**The ceiling is an OpenRouter per-key credit limit with monthly reset.** See the
Direction norm above for why this is not application code's job. Two residuals,
recorded rather than waved past:

- The reset is at **midnight UTC**, so "monthly" means the UTC calendar month, not
  the curator's local one. Harmless, but it should not be discovered as a surprise.
- The refusal arrives **mid-run**, so a run can halt with some works acquired and
  others not. *(Measured 2026-08-02: the refusal is a **403**, "Key limit exceeded".
  A 402 is a different answer entirely — a pre-flight check that the reserved
  `max_tokens` is affordable — and it arrives with credit still in the account.
  Collapsing them would halt runs that still have money. Shapes in
  `openrouter-api-findings.md`.)* The error model already declares partial success normal, so this is
  consistent with the design rather than a new failure mode — but it is what makes
  `halted_by_budget` a state the catalogue must be able to represent, not merely an
  error string.

**Discovery carries a per-run search cap.** A monthly ceiling does not bound a
single runaway run, and a pre-run cost estimate is not an estimate if the run can
freely exceed it. The cap is a deployment value (never hardcoded —
`project-preferences.md`), and its being hit is a distinguishable outcome rather
than a silent truncation of results.

> **The cap has two components, and this corrects a contradiction (2026-08-02).**
> This section previously said only that the cap "is derived from the work count".
> That is undefined for phase 1, whose entire job is to *produce* the work count —
> so the cap could not bound the phase that issue #12 requires it to bound ("Phase-1
> search calls are counted inside the per-run search cap and the pre-run estimate").
> The cap is therefore:
>
> - a **flat phase-1 allowance** — a fixed number of searches, since there is no
>   count to derive from yet; and
> - a **per-work phase-2 component**, derived from the phase-1 work count as
>   originally stated.
>
> The estimate decomposes the same way, which is what makes issue #12's "pre-run
> estimate" a real number: the phase-1 figure is computable before anything runs,
> and the phase-2 figure becomes computable the moment the work count exists. This
> is why `art_discovery(action='estimate')` is meaningful both with and without a
> run id — see `api-contract.md`.
>
> **Values shipped 2026-08-02: a flat 10 for phase 1, and 2 per work for phase 2**
> (`DISCOVERY_PHASE1_SEARCH_ALLOWANCE`, `DISCOVERY_PHASE2_SEARCHES_PER_WORK`).
> They are a derivation from the table above rather than a preference: a
> twenty-work run is bounded at 10 + 20×2 = 50 searches. At the $0.005 the
> comparison engines charge that is **$0.25 — exactly the top of the search band
> recorded above** — and a bounded run total of $0.327 against the recorded
> $0.11–$0.33, which is the arithmetic these allowances were sized by. On the
> engine since pinned the same 50 searches cost **$0.05**, for a bounded run of
> $0.127.
>
> **Only 10 of those 50 are billed now**, because phase 2 asks museum APIs
> instead of searching the web: the phase-2 component of the cap bounds fan-out
> against a provider that charges nothing, so a bounded run is **$0.01336** and
> its search half is $0.010. The *counts* are unchanged, and deliberately so: they bound how much
> a run may do, which is a policy about fan-out rather than about price, and
> re-deriving them every time a vendor's rate moves would make the bound follow
> the market instead of the household. A cap has to sit at the ceiling of the
> recorded range rather than at its middle, or it stops runs the analysis says are
> ordinary. `curation/tests/unit/test_config.py` recomputes both
> figures from the shipped settings, so the derivation is checked rather than
> asserted, and a settings change that walks away from this analysis fails.
>
> **No longer provisional, and the values stand (measured 2026-08-02).** The one
> open question was whether the web fee scales with `max_results`, since the cap
> is sized against it. It does not: the fee is **charged per search request and
> is identical at one, three, five and ten results** — $0.00500000 to eight
> decimal places in all four — while citations scale one for one with the
> request (`openrouter-api-findings.md` § The web fee is per request). So the
> cap counts the right unit at the right price, and nothing here needed
> revisiting. The corollary is that **breadth is free**, which is why
> `DISCOVERY_SEARCH_RESULTS` ships at 10.
>
> **A third bound joined these on 2026-08-04, and it is not a cost bound at all**
> (`DISCOVERY_OFFERED_WORKS_PER_RUN`, shipped at 12). It limits how many works a
> run may *offer* from a wired collection on top of the list it proposed. Browsing
> a museum costs nothing, so what it protects is the curator's attention and the
> proportion between a supplement and the list they approved. **It is also the
> selection mechanism, which is why it cannot simply be set high**: the collection
> holds far more than any run will show — one real run's four artists had 69
> offerable works between them — and the museum's relevance score is unusable for
> ordering them (`artic-api-findings.md`). So the works kept are taken one per
> artist per pass, and this number is how many passes. Twelve is about half the
> approval threshold, which keeps the supplement visibly secondary while still
> giving a four-artist run three works each. Zero turns it off.
>
> **Overrunning the allowance fails the run rather than trimming its results.**
> An engine that searched past its bound spent money the estimate did not cover,
> so its work list was bought outside what anyone authorised; accepting it with a
> note attached would make the breach a footnote on a bill already paid. The
> searches themselves are still recorded, because they happened.

> **The cap applies per run, and re-searches are now runs (2026-07-20).** Modelling
> `resolve_images` as a `DiscoveryRun` with `kind='resolve'` gave the re-search a
> handle, a cancel, and its own cost — but it also means the per-run cap no longer
> bounds a *work* across its lifetime, only each attempt at it. A curator who
> rejects an image ten times gets ten capped runs, not one capped work.
>
> **That is accepted, not overlooked.** Each re-search is a deliberate human act on
> a named set of work ids, which is a different risk shape from an agent loop
> running away inside one run — the thing the cap exists to bound. The monthly
> OpenRouter ceiling is what bounds the aggregate, and it cannot be multiplied by
> creating more runs. Recorded because "per-run" quietly changed denominator here,
> and a reader who assumed the cap bounded total re-search spend would be wrong.

### Cost visibility

Every operation that spends money should report its estimated cost before it runs
and its actual cost when it finishes, on every surface equally — the web UI and
the MCP tool surface.

> **"CLI" struck 2026-08-02.** This sentence listed a third surface the product
> does not have and has never planned: no CLI appears in `api-contract.md`'s
> surface inventory or `product-brief.md`'s flows, and `curation/__main__.py` only
> starts the server. Left standing it would read as an unbuilt requirement — a
> surface silently owed by whichever chunk noticed — when in fact nothing was ever
> dropped. Struck rather than deleted quietly, so a reader of an earlier revision
> can see it was answered.

**This is a requirement, not a norm.** It was proposed as a Direction entry on
2026-07-20 and deliberately not ratified, so nothing enforces it structurally: it
has to survive as a named build-plan deliverable or it will quietly not ship.
Flagged here so a later reader does not mistake its absence from Direction for its
absence from scope — it is a v1 goal ("See what LLM discovery cost, before and
after running it") and a stated persona need.

The reasoning it rests on: the curator is asked to authorise spending and cannot
authorise what they cannot see. The MCP surface sharpens this rather than softening
it — an agent driving discovery has no wallet, no instinct for what is expensive,
and no way to steward a budget it cannot observe. An estimate in the tool result is
the only channel through which it can behave responsibly.

The estimate must be *bounded* rather than *typical*, which is what the per-run
search cap is for. A number a run can freely exceed is not an estimate.

### Decided — engine choice: Parallel (2026-08-02)

**Discovery pins `parallel`, and the reasoning came out the opposite way round
from what was predicted here.** This section previously argued that the cost
spread was not decision-relevant against a $20 ceiling, so engine choice had to be
a quality decision and choosing on price would be choosing on the one axis that
did not matter.

The measurement says quality is the axis that does not matter. Exa, Parallel and
Perplexity were compared on both hard cases named below — sixteen "resolve a named
work to the museum that holds it" cases, and a recency-bound intent. **All three
found the holding institution in every case and returned the same share of
in-period citations.** Nothing separated them. Cost separates them four to one:
$0.001 per request against $0.005.

So the constraint below was honoured and answered, and the conclusion it was
meant to support did not survive it. Price decided because it was the only thing
left that differed.

**The first eight cases were world-famous paintings, which is the generic
relevance this section warned against** — any engine finds the Rijksmuseum page
for The Night Watch. The comparison was re-run on mid-tier works whose holdings
were known independently rather than read back from an engine's own citations,
which would have scored the others against one engine's answer. All three scored
identically on that set too.

**What was measured is phase 1's search: given a work, find its institution.**
Phase 2 retrieves image *instances*, with rights and resolution, which is a
different retrieval task and may separate these engines where this did not. That
is Chunk 16's to establish. The engine is a deployment value
(`DISCOVERY_SEARCH_ENGINE`), so revising the answer is a configuration change.

**Pinning matters independently of which engine wins.** Left unset, the provider
resolves the engine from the *model* — that model provider's native search where
one exists, Exa where none does — so an unpinned engine makes the search back-end
a side effect of `DISCOVERY_MODEL`, and changing the model silently changes how
the product searches.

Held by `tests/live/test_search_engine_choice_still_holds.py`, which re-checks
both halves: that the chosen engine still resolves works to their museums, and
that the price gap it was chosen for has not closed. Both can decay — an index
can rot, a per-request price can move — and a decision nobody re-runs quietly
stops describing the world.

### The Supply Horizon

**Measured 2026-08-04. This is a fact about supply, not a policy about rights.**
Intents whose works predate the public-domain boundary resolve; intents past it do
not, and wiring more providers does not move it. The eight works from two real runs
were put to four open-access providers — the Art Institute, the Met, Cleveland, and
Wikidata/Commons — and each returned nothing for all eight. A per-intent sweep over
the recorded phase-1 corpus put pre-boundary intents around two thirds and
post-boundary intents at or near zero, with one mid-century American intent
measuring 0 of 10. The partition is not *which collection is wired*; it is
copyright. The measured break sat around 1929, and the boundary itself moves
forward a year at a time, so it is the boundary that is the constant here and not
the date.

**This sits against a recorded decision, and the collision is recorded rather than
quietly resolved.** `project-state.yaml` § integrations commits discovery to museum
collections *and* the contemporary web — gallery sites, prize announcements, artist
portfolios — with "museum/public-domain only" listed as its **explicitly rejected**
alternative, on the reasoning that "recent award-winning art" cannot be satisfied
from institutions alone. Only the museum half is wired. So the product today ships
the alternative that decision rejected, and a curator asking for contemporary work
gets a run that spends money and returns nothing.

**No rights gate follows from this, and that is a decision rather than an
oversight** (operator, 2026-08-04: *record rights, do not gate, do not filter*).
Constraint 13 already holds rights to a quality weight and never an exclusion, and
nothing measured here amends it — none of this is about whether a work may be
shown. What is open, and is deliberately left open, is whether the contemporary-web
half of that integrations decision gets built or gets retracted. Until one of those
happens this section exists so the horizon is read rather than rediscovered, which
so far has cost two runs.

## Output Quality

<!-- Not a template section. Added because for this product visual output quality
     IS a non-functional requirement — it is the thing the product exists to
     deliver, it is not covered by any functional requirement, and it has a
     regression corpus. -->

The product's output is a picture on a wall seen from across a room. Quality here
is not polish; it is the requirement.

**Mat colour must be at least as good as the 2024 implementation.** This is
explicitly a subjective bar, and the 41 existing artworks with their hand-tuned
mats are the regression corpus. A new mat engine that scores well on any metric
while producing visibly worse mats on those 41 has failed. The corpus's canonical
record is `all.json` — replaced as a schema, but **retained, tracked, and read
directly**: it is the only place the hand-tuned mat colours exist, so repo-hygiene
work (issue #4 untracks its *backups*) must not delete the file itself.

> **Settled 2026-08-03: there is no extracted fixture, and this record is
> permanent rather than interim.** This paragraph read "retained as a *test
> fixture* … must not delete the file itself **before the regression fixture is
> extracted**", which promised that `all.json` would hand its role to a copy under
> `tests/fixtures/`. That copy is deliberately not created. A second file holding
> the same 41 colours is a second place they live, free to drift from the one the
> seed actually loads — and the drift is silent, because both files keep parsing
> and neither fails. The regression test reads `all.json` through the product's
> own `read_index` instead of a second parser, so the corpus and the seed cannot
> disagree without a test failing. The consequence to accept knowingly: deleting
> or untracking `all.json` destroys the corpus outright, with no successor to fall
> back to, which is why `.gitignore` excludes only its backups and says so inline.

**The mechanical derivation did not land in the corpus's region, and measurement
is how that was established (2026-08-10).** The dominant-colour fallback
(`acquisition/mat.py`, Pillow median-cut darkened by `_FALLBACK_LIGHTNESS`) was
described during the 2026-08-05 walkthrough as landing where the corpus sits,
which is what made it acceptable as a *default* rather than a fallback. Run over
the operator's own masters and paired against the hand-tuned colour for the same
painting, it did not — it put a mat above the bar on 7 of 40 works where the human
breached it on none, the worst being Demuth's "...And the Home of the Brave" at
L\* 59.5 against a hand-tuned L\* 18.8. The full before-and-after is the table
below; it is not repeated here.

A near-white mat over a Mondrian is the exact failure `CORPUS_MAX_LIGHTNESS`
exists to refuse: `test_mat_corpus.py`'s docstring records that two candidate
models were rejected during probing for proposing one over a Rothko and a
Mondrian. The bar was written to keep *models* out of that failure, and the
mechanical producer — which the bar was never run against on real images — walked
into it on the same painting.

**Why no test caught this, which is the part worth carrying forward.** The test
then named `..._for_most_works` fed the engine six synthetic flat colours, the
lightest of which was mid-grey, and asserted all six landed under the bar. Its
docstring said "most" while its assertion said "every", and both were true of
*that* input — flat colours have no cluster competition and no pale regions. The
corpus's real masters have both. **A regression corpus that is only read for its
answers is not being used as a corpus**: the 41 colours were checked against the
bar, and the 40 images they were derived *from* never went through the producer
being judged. The test is now
`test_the_fallback_stays_within_the_corpus_bar_for_every_work` and its palette
leads with white and a pale wash — the cases darkening alone cannot rescue, and
therefore the cases that prove the clamp is doing the work.

**Both halves of the intended check exist as of 2026-08-11, and the split is the
design above.** The masters are not in the repository and must not be, so the
*clamp* is arithmetic asserted on synthetic input by `test_mat_corpus.py`, while
the *comparison against the hand-tuned 40* is an operator-run measurement against
`ART_ROOT` carried by `tools/mat_masters.py`. Making the bar structural is what
lets a cheap test carry it; a statistical claim over images CI cannot see is not a
test, and writing one that passes on synthetic flats is how this was missed.

**A clamp on L\* alone does not hold, which is worth recording because the naive
version passes every test.** Holding lightness at the ceiling while keeping a\* and
b\* asks for a colour sRGB often cannot show; the conversion clips into the gamut
and returns something *lighter* than requested — a pure magenta at L\* 49.6, over
the ceiling being enforced, and still under the round-number bar of 50 that the
suite checks. The engine therefore trades **lightness, not chroma**: it goes
darker until the colour is displayable at its own hue, which is what the prompt
that produced the corpus says to do in doubt, and which avoids answering a vivid
work with a grey. Swept over the whole RGB cube the worst realised lightness is
L\* 45.2. No work among the operator's 40 reaches this path.

`mat.py` clamps derived lightness to **`_DERIVED_LIGHTNESS_CEILING` (45.2)**, and
that constant is **not a second copy of the corpus's ceiling** —
`test_mat_corpus.py` derives the lightest mat from `all.json` and fails if the two
disagree, so a corpus that gains a lighter mat cannot leave the engine enforcing a
bar the corpus no longer sets.

> **Corrected 2026-08-11: this sentence used to name `_CORPUS_MAX_LIGHTNESS`,
> which exists nowhere in the tree.** The module has two ceilings and that name is
> a hybrid of both: public `CORPUS_MAX_LIGHTNESS = 50.0` is the looser requirement
> bar the engine deliberately never compares against, and private
> `_DERIVED_LIGHTNESS_CEILING = 45.2` is what the clamp actually enforces. The
> wrong name is worth a correction note rather than a silent edit because of where
> it led: someone reconciling code to this artifact greps, finds only the public
> 50.0, and concludes the clamp should be 50 — restoring exactly the 4.8 L\* of
> slack that let issue #115 ship.

**What the fix bought, measured over the operator's own 40 pairs on 2026-08-11:**

```
                                            before        after
  machine over CORPUS_MAX_LIGHTNESS = 50     7 / 40       0 / 40
  re-encode moved the derived colour at all  5 / 40       5 / 40   (ΔE > 5)
    ... to a plainly different colour        5 / 40       2 / 40   (ΔE > 10)
    worst single move                       ΔE 60.7      ΔE 45.6
  machine lighter than the human chose      31 / 40      31 / 40   median +14.2 L*
```

The last row's `+14.2` and the `+15.2` recorded on 2026-08-10 are the same 40
measurements under two conventions — the sample is even, its middle gaps are 13.3
and 15.2, and the earlier record quoted the upper one. `tools/mat_masters.py`
prints the mean of the two, which is the figure to quote, because it is the one a
reader can reproduce.

**Two of those columns did not move, and both are deliberate.** The lightness
*bias* is untouched: the clamp is a ceiling, so it removes the tail above the bar
and leaves the median where it was. Closing that gap is a question about which
colour to choose rather than arithmetic on the one already chosen, and it belongs
to the vision model — which is why the mechanical derivation is the default only
in the sense of "always present", not "preferred where a model can be asked". And
the count of works that move *at all* under a re-encode is unchanged at 5: the
residue is not a split colour losing a vote but two genuinely different regions of
one painting close enough in area that a re-encode reorders them. No merge
threshold fixes a real tie, and one wide enough to try would collapse the picture
to a single colour.

**The committed *look* instrument still does not measure this, and the two are
not interchangeable.** `tools/mat_corpus.py` states in its own docstring that its
images come from each work's museum as a small IIIF derivative rather than from
`ART_ROOT` — the very substitution that changes the derived colour visibly on 5 of
25 works. It is a sheet for judging look; `tools/mat_masters.py` is the numeric
comparison against the masters. Run the second after any change to
`acquisition/mat.py` or `acquisition/color.py`.

**Two mat presets, and their values come from the corpus rather than from
convention (decided 2026-08-10).** A curator's one-press neutrals are `#222222`
(L\* 13.2 — the most common hand-tuned colour, chosen three times) and `#6b6b6b`
(L\* 45.2 — the lightest in the corpus, and the mat a human chose for the
Mondrian). The operator's opening ask was black and off-white; **off-white was
withdrawn on the same evidence that withdrew it as the default** — no mat in the
41 exceeds L\* 45.2, so an off-white preset would sit roughly fifty L\* points
above anything the corpus contains, on the emissive panel where that glares.
Pure black was not chosen either, for the quieter reason that the corpus does not
contain it: the darkest of the 41 is `#14141e` at L\* 6.7.

**Rendered size must be adequate, and the current pipeline has no floor.**
`resize_file_with_matte` uses PIL's `image.thumbnail()`, which **never upscales** —
so the de facto 2024 policy is "accept any resolution, never upscale, let the mat
absorb the difference." On the real corpus that is almost always fine: median work
occupies 59% of the 4K canvas, and only two works are pasted at native size rather
than downscaled. But there is no floor at all, so a small web-sourced press image
would be rendered as a postage stamp in an enormous mat, and nothing would report a
problem. Now that contemporary web sources are in scope, that gap is live.

The right metric is **not** megapixels — canvas occupancy is dominated by
aspect-ratio mismatch, not by resolution, so a tall narrow work legitimately fills
little of a 16:9 canvas. The metric that isolates resolution is whether the render
is a *downscale* or a *native-size paste*.

### The mat is geometric, and the floor is physical (decided 2026-07-20)

**The mat is specified in physical units, not pixels or ratios.** A mat width in
inches, with the bottom margin weighted larger than the top — the conservator's
convention, because a true-centred image reads as sitting low. This is what
"museum-quality mat" has to mean if it means anything; the 2024 pipeline's mat was
aspect-ratio residue, so a 16:9 source got no mat at all.

*(**The weighting was stated without a number until 2026-08-01**, when the first
surface to judge a work against the artwork box needed a box height and so had to
have one. It is now a deployment value,
`MAT_BOTTOM_WEIGHT`, defaulting to **1.15** — the bottom margin is 1.15x the top.
That figure is not invented: it is the one that reproduces the 42" worked example
below exactly, which is the best available evidence of what that example was
drawn from. The rounding order is part of the rule, because it moves the answer
by a pixel or two — the mat is rounded to whole pixels first and the bottom is
derived from that rounded top, which is the arithmetic a compositor drawing in
pixels will do. **Open for the operator to overrule**: 1.15 is a subtle
weighting, and a more pronounced one is a matter of taste rather than of
correctness.)*

**Panel geometry is a deployment value, never a constant.** The operator's own
panel is **50"** — a `QN50LS03DAFXZA`, established from the set's own `modelName`
on 2026-08-04, having been recorded here as 42" until then — but nothing may depend
on that — other people will run this on other sizes, and the product must support
any of them. The worked examples elsewhere in this document stay at 42" on purpose:
they are arithmetic demonstrations, and re-cutting them would lose the check that
the numbers reproduce. Panel dimensions therefore join
`ART_ROOT` as configuration both planes must agree on (`operational-spec.md`).

Everything else follows arithmetically:

```
artwork box  =  canvas − mat(panel geometry, mat inches)

42" 16:9  →  36.6" wide  →  ~105 ppi  →  2.5" mat = 262 px top and sides,
                                                     301 px bottom (x1.15)
             artwork box 3316 × 1597 px  =  31.6" × 15.2" on the wall
75" 16:9  →  65.4" wide  →   ~59 ppi  →  2.5" mat = 147 px top and sides,
                                                     169 px bottom (x1.15)
             artwork box 3546 × 1844 px  =  60.4" × 31.4" on the wall
```

*(**Corrected 2026-08-01.** The 75" row read `3546 × 1723`, which no single
bottom weighting produces: 1723 implies a bottom margin 1.97x the top while the
42" row implies 1.15x, so at most one of the two could ever have been right. Both
rows above are now computed by `Settings.tv_artwork_box` and asserted against
these exact figures in `curation/tests/unit/test_config.py`, so this table has a
mechanism behind it rather than being arithmetic done once by hand.)*

**The floor is a minimum rendered size on the wall, in inches** — the same units as
the mat, and it scales with the panel automatically. It was never going to be one
number: a pixel threshold means different things on a 42" and a 75", and megapixels
were already ruled out. On a 42" panel a 12" floor puts the threshold at ~1260 px on
the long edge.

**Below the floor, the work is not rejected and the image is not hidden.** Phase 2
does not *auto-select* a below-floor instance; the review grid shows it labelled
with its rendered physical size ("would show at 8.6 inches") and the curator may
select it anyway. If every instance is below floor the work lands at
`resolution_status = unresolved`, which is already a first-class outcome that may
never be silently omitted (`data-model.md` constraint 9), and the work stays
eligible for re-search. Nothing is silently dropped and nothing is silently
accepted — which is the requirement, on a product whose defining constraint is that
failure is silent.

> **Built 2026-08-02, and the mechanism is worth naming because "not
> auto-selected" had three places it could have lived.** It is an exclusion in
> the single function that decides which instance represents a work
> (`services/selection.py`), not a filter at recording time and not a deduction
> in the score. Recording-time filtering would have hidden the instance, which
> this section forbids outright. A score deduction would still select it whenever
> nothing better existed — the exact case the floor is for.
>
> Excluding it there makes every consequence fall out of one rule: the instance
> is stored and listed as an alternate; a work with only below-floor instances
> gets no selection and is therefore reported `unresolved`; a curator can still
> choose one by name, because that path does not go through automatic selection;
> and **rejecting a good scan does not fall through to a below-floor alternate**,
> which would otherwise hand a curator asking for something better the worst
> instance on the card.
>
> The artwork box has to reach the service layer for this, since the floor is a
> size on the wall and cannot be evaluated from a stored row. A deployment with
> no configured geometry gets the ranking with no floor applied rather than an
> invented one.

**No upscaling.** See `data-model.md` → Original.

**The e-paper label must be legible at standing distance**, on a backlit-free
16-level greyscale panel, in whatever light the room has. The 2024 implementation
hardcodes "Sans 18" for a panel geometry that is no longer the target, so type
sizing must be re-derived for the 1448×1072 panel rather than carried forward.
This is the product's most important accessibility surface and it is a physical
one — see `design_decisions.accessibility_approach`.

> **The 16 grey levels are not the default and must be claimed.** Measured on the
> panel 2026-08-04: the driver comes up in 1-bit `bw`, and the obvious sanity
> check cannot detect it because `max_colors` reports 16 either way. The display
> plane therefore has to set the mode explicitly and assert on `mode` itself —
> otherwise this requirement is unmet by a build that passes every test. Full
> measurements in `platform-and-dependency-findings.md` § The e-paper panel.

## What This Artifact Hands Off

| To | What |
|---|---|
| `architecture.md` | The display-plane independence norm states the *requirement*; architecture owes the *mechanism* — what the Pi holds locally, and how stale it may be |
| `architecture.md` | Storage does not force a NAS; the curation host was decided on availability grounds — co-located on the Pi, 2026-07-20 |
| `observability-strategy.md` | Every availability target here is unobservable without detection. "Down looks like up" is the defining constraint |
| `operational-spec.md` | Back up the catalogue; do not back up the image tree |
| Acquisition pipeline design | The minimum-resolution floor — **resolved 2026-07-20**: a minimum rendered size in inches, derived from panel geometry and mat width, both deployment values |
| `operational-spec.md` | Panel geometry joins `ART_ROOT` as configuration both planes must agree on |
| Build plan | The search-engine spike, with its stated comparison constraint |
