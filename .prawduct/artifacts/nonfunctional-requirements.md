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
> limit returns 402 and cannot be bypassed by any of those.
>
> **Corollary — read from the authority, not from a local tally.** "Budget
> remaining" is read from `GET /api/v1/key` (`limit_remaining`), and per-run actual
> cost from the `cost` field OpenRouter returns with each generation. A local
> counter would be a second source of truth for a number the provider already owns
> authoritatively, and the two would drift.
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

Measured against the real 41-work corpus (`all.json`, 2026-07-19):

| Dimension | Today | Design target | Verdict |
|---|---|---|---|
| Works | 41 | "hundreds" | SQLite at low thousands of rows is a non-issue. Not discussed further |
| Source image size | mean 17.6 MP, median 14.5 MP, max 49 MP (6220×7912) | unchanged | 39 of 41 are *downscaled* to reach a 4K canvas — source resolution is amply sufficient across the corpus |
| Source image bytes | ~0.4 GB for 41 works (~10 MB/work) | ~15 MB/work all-in incl. renders, thumbs, labels | **500 works ≈ 10 GB** |
| Concurrent discovery runs | — | 1 | One curator. Concurrency is a correctness question (two runs racing on the same work), not a throughput one |

**Storage is not an architectural constraint, and specifically does not force the
curation plane onto a NAS.** 10 GB for a corpus ten times the current size fits on
any laptop, any desktop, or a Pi with a USB SSD. This removes one input from the
open question about where the curation plane runs — that decision should be made
on availability and always-on-ness, not on disk.

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
- **The image tree is disposable.** `raw/`, `ready/`, `tv-thumbs/`,
  `tile-cache/`, `api-cache/` are all reconstructible. They are excluded from
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

Verified against OpenRouter's documentation, 2026-07-19 and re-verified
2026-07-20. LLM and search pricing moves fast — **re-verify before relying on
these figures.**

| Component | Unit cost | Per run (~20 works) |
|---|---|---|
| Discovery tokens (GLM-5.2) | $0.2219/M in, $0.6974/M out | ~$0.13 |
| Discovery tokens (DeepSeek V4 Pro) | $0.435/M in, $0.87/M out | ~$0.24 |
| Web search — Parallel | $0.001/request (10 results incl.) | $0.03–0.05 |
| Web search — Exa via OpenRouter | $0.005/request (10 results incl.) | $0.15–0.25 |
| Web search — Perplexity | $0.005/request | $0.15–0.25 |
| Mat-colour vision | one call per *accepted* work | negligible |
| Museum APIs, image acquisition | $0 | bandwidth only |

**This retires the recorded worry that search could exceed token spend "by an
order of magnitude".** Worst case it roughly doubles per-run cost. A run lands
between **$0.16 and $0.49**, so $20 buys on the order of **40–125 runs a month**.
Search goes *inside* the ceiling, comfortably.

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
- A 402 arrives **mid-run**, so a run can halt with some works acquired and others
  not. The error model already declares partial success normal, so this is
  consistent with the design rather than a new failure mode — but it is what makes
  `halted_by_budget` a state the catalogue must be able to represent, not merely an
  error string.

**Discovery carries a per-run search cap.** A monthly ceiling does not bound a
single runaway run, and a pre-run cost estimate is not an estimate if the run can
freely exceed it. The cap is derived from the work count, is a deployment value
(never hardcoded — `project-preferences.md`), and its being hit is a distinguishable
outcome rather than a silent truncation of results.

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
and its actual cost when it finishes, on every surface equally — web UI, MCP tool
surface, CLI.

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

### Open — engine choice

**Which search engine discovery defaults to is deliberately undecided**, pending a
build-time spike comparing result quality on real intents. The cost bound is
stated for all three above and does not discriminate: the spread between the
cheapest and dearest option is $0.05 versus $0.25 per run, which against a $20
ceiling is not decision-relevant. **Engine choice is therefore a quality decision,
and no quality evidence exists yet.** Choosing on price would be choosing on the
one axis that does not matter.

Constraint on the spike: it must compare on this product's actual hard case —
resolving a named work to a specific museum page, and answering a recency-bound
intent like "recent award-winning art" — not on generic search relevance.

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
record is `all.json` — replaced as a schema, but **retained as a test fixture**:
it is the only place the hand-tuned mat colours exist, so repo-hygiene work
(issue #4 untracks its *backups*) must not delete the file itself before the
regression fixture is extracted.

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

**Panel geometry is a deployment value, never a constant.** The operator's own
panel is 42", but nothing may depend on that — other people will run this on other
sizes, and the product must support any of them. Panel dimensions therefore join
`ART_ROOT` as configuration both planes must agree on (`operational-spec.md`).

Everything else follows arithmetically:

```
artwork box  =  canvas − mat(panel geometry, mat inches)

42" 16:9  →  36.6" wide  →  ~105 ppi  →  2.5" mat = 262 px/side
             artwork box 3316 × 1597 px  =  31.6" × 15.2" on the wall
75" 16:9  →  65.4" wide  →   ~59 ppi  →  2.5" mat = 147 px/side
             artwork box 3546 × 1723 px
```

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

**No upscaling.** See `data-model.md` → Original.

**The e-paper label must be legible at standing distance**, on a backlit-free
16-level greyscale panel, in whatever light the room has. The 2024 implementation
hardcodes "Sans 18" for a panel geometry that is no longer the target, so type
sizing must be re-derived for the 1448×1072 panel rather than carried forward.
This is the product's most important accessibility surface and it is a physical
one — see `design_decisions.accessibility_approach`.

## What This Artifact Hands Off

| To | What |
|---|---|
| `architecture.md` | The display-plane independence norm states the *requirement*; architecture owes the *mechanism* — what the Pi holds locally, and how stale it may be |
| `architecture.md` | Storage does not force a NAS; decide the curation host on availability grounds |
| `observability-strategy.md` | Every availability target here is unobservable without detection. "Down looks like up" is the defining constraint |
| `operational-spec.md` | Back up the catalogue; do not back up the image tree |
| Acquisition pipeline design | The minimum-resolution floor — **resolved 2026-07-20**: a minimum rendered size in inches, derived from panel geometry and mat width, both deployment values |
| `operational-spec.md` | Panel geometry joins `ART_ROOT` as configuration both planes must agree on |
| Build plan | The search-engine spike, with its stated comparison constraint |
