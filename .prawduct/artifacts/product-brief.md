---
artifact: product-brief
version: 1
depends_on:
  - artifact: project-state
    section: product-definition
last_validated: null
---

# Product Brief

## Vision

A curated art appliance for a Samsung Frame TV: the curator expresses intent in
natural language — "recent award-winning work", "American modernists" — and an
LLM-assisted discovery layer finds and acquires matching artwork at gallery
resolution, presents it on the wall with a museum-quality mat, and prints a
physical label beside it. The curator never manages files, URLs, or geometry.

The distinction that defines the product: **this is discovery, not search.** A
system that filters a known collection is a different, easier product. The
requirement is to find works the curator has not seen and could not have named.

## Landscape

The closest existing thing is [NickWaterton/gallery](https://github.com/NickWaterton/gallery),
by the author of the `samsungtvws` fork this project already depends on: a Flask
front-end on a Raspberry Pi with kiosk and display modes, a caption display, and
LLM-generated descriptions. It is worth reading before designing the curation UI —
it has already made many of the same decisions.

What it does not do, and this product does:

- **Curatorial intent as the input.** Gallery displays a folder you assembled.
  This product assembles the folder from a stated intent.
- **Acquisition at gallery resolution.** Tiled gigapixel fetching from museum
  sources, with metadata normalised across providers.
- **The mat-colour engine.** Vision-model-assisted selection reasoning in LAB
  space about mat area, artwork luminance, and the fact that an emissive display
  makes a bright mat overpower the work.

That third item is the hardest-won logic in the existing codebase and the clearest
reason to continue this project rather than adopt an existing one.

## Identity

**Museum, not gadget.**

The curator-facing surface should read like a private collection management tool:
calm, typographic, image-forward. The household-facing surfaces — the TV and the
e-paper label — should disappear entirely into the artwork.

One hard constraint inherited from the existing product: **the TV output is the
artwork plus a mat, with no chrome, no overlay, and no branding.** The mat-colour
engine exists precisely so the bars read as a deliberate framing choice rather
than as letterboxing.

Beyond that, visual direction is deferred to design. The 2024 product had no
visual surface at all, so there is no existing style to honour or break from.

## Users & Personas

### The Curator (operator)

The single operator. Owns the hardware, the API keys, and every decision.

- **Technical level:** advanced — authors the `3tears` framework this product may
  build on. The UI must not be condescending or hand-holding.
- **Needs:** express curatorial intent in natural language and get real candidates
  back; review, accept, and reject before anything reaches the wall; organise
  accepted work into themes and switch what the TV is showing; see what discovery
  cost, before and after running it.
- **Constraints:** will not run Kubernetes, NATS, or heavy infrastructure for a
  household appliance. Curation happens in short sessions — this is a leisure
  activity and must never feel like sysadmin work.

### The Household (viewers)

Everyone who sees the TV. **Non-interactive** — they never log in, configure, or
curate.

- **Technical level:** none.
- **Needs:** art that looks good on the wall at every time of day; enough context
  to know what they are looking at, via the physical label.
- **Constraints:** no interface, no accounts, no controls. This is the
  accessibility surface that matters most in this product, and it is a *physical*
  one — label legibility on a 16-level greyscale e-paper panel at reading
  distance, and artwork legibility at varying room brightness.

## Core Flows

Framed as a pipeline with a human gate in the middle, because the product both
`runs_unattended` (display) and `has_human_interface` (curation).

| # | Flow | Priority |
|---|------|----------|
| 1 | Express curatorial intent | must-have |
| 2 | LLM-assisted discovery — intent to works, then works to image instances | must-have |
| 3 | Review and accept a work with its selected image | must-have |
| 4 | Acquire and prepare | must-have |
| 5 | Organise into themes | must-have |
| 6 | Display and sync | must-have |
| 7 | Ambient adaptation | nice-to-have |
| 8 | Drive everything from an agent, over MCP | must-have |

**1. Express curatorial intent.** The curator states an intent — an artist, a
style, a prize, a period — in the web UI or through an agent. The system
interprets it into a discovery strategy. Cost visibility at the point of decision
is what makes the spend ceiling feel like a guardrail rather than a surprise; flow
2 explains where that estimate becomes a real number rather than a guess.

**2. LLM-assisted discovery, in two phases.** This is the flow with unbounded cost
and runtime, and therefore the one the spend ceiling exists to bound.

> **A work is not an image.** This distinction is the product's central
> requirement, not an implementation detail. *The Persistence of Memory* is one
> **work**; the MoMA page, the Google Arts & Culture scan, the Wikipedia upload and
> the poster shop's JPEG are four **instances** of it. A curator who asks for
> Dalí's most famous works and is handed ten copies of the same painting to
> approve one of has been failed by the product, even though nothing errored.

- **Phase 1 — intent to works.** One cheap call resolves the intent into a set of
  *works*: titles and artists, not images. This is where "American modernists" or
  "Dalí's most famous" becomes an enumerable list.
- **Phase 2 — works to instances.** Each work gets its own search across museum
  APIs and the open web, producing several candidate *image instances*. The system
  ranks them and selects one canonical instance per work, recording why.

Three consequences follow from the split, and each is load-bearing:

- **The cost estimate stops being a guess.** Phase 1 is one call; phase 2 costs
  roughly one search per work. So the moment phase 1 finishes, the work count is
  known and the phase-2 cost is *computable* rather than predicted. The estimate is
  shown against a real list — "your intent resolved to 40 works, resolving images
  will cost about $X" — which is what flow 1's cost-visibility requirement actually
  needs.
- **The work list is the count.** How many candidates a run should produce is not a
  number set in advance. It is the phase-1 list, which the curator can trim before
  paying for phase 2.
- **Phase 2 verifies phase 1.** Models invent plausible artwork titles. A work for
  which no credible instance can be found is evidence the work is not real, and
  that must surface as its own outcome — never be silently dropped from the batch,
  and never be filled with a confident near-match.

**Approving the work list is gated by scope, not by policy.** When the resolved
work count is small the run proceeds straight through; when it crosses a
configured threshold it stops and waits. A leisure activity in short sessions
should not demand two review passes for a modest run, and a run that has
interpreted the intent far more broadly than the curator meant should not proceed
unwatched.

> **Amended 2026-07-20** from "gated by cost". The gate stands; its trigger
> changed. Real per-run costs turned out to be $0.16–0.49, so a dollar threshold
> gated on the axis that does not matter. The estimate is still computed and still
> shown — it is what makes phase 2 authorisable — it is simply not what opens the
> gate.

**Canonical selection trades two axes against each other.** *Confidence* asks
whether this instance is genuinely that work — not a detail crop, a study, a
poster, an "after Dalí", or a photograph of a gallery wall. *Quality* asks about
resolution, colour fidelity, rights, and whether the source is the holding
institution. They conflict: a museum's own page is maximum confidence and may be
lower resolution than a gigapixel scan elsewhere. Which axis dominates depends on
the source class — canonicity is the hard problem for institutional sources, where
many instances of one work exist; confidence is the hard problem for the
contemporary web, where a living artist's piece usually has exactly one image and
the risk is that it is the wrong one.

**3. Review and accept.** The curator reviews one card per *work*, showing the
selected image, the alternates that were found, and why this one was chosen. Only
accepted works enter the catalogue.

The decision bundles two judgements that fail independently — *do I want this
work* and *is this image good enough* — so there are three outcomes, not two:

| Verdict | Meaning |
|---|---|
| **Accept** | Add this work, using this image. |
| **Reject work** | I do not want this work. Do not propose it again. |
| **Reject image** | I want this work; this instance is not good enough. Find a better one. |

The third is the one an accept/reject binary cannot express, and it is not an edge
case — "yes, Persistence of Memory, but not that 900px poster scan" is ordinary.
It also means **suppression has two scopes**: rejecting a work suppresses the work;
rejecting an image suppresses *that image only* and must explicitly not suppress
the work. Getting that backwards silently blacklists a painting the curator asked
to keep.

This is the human-in-the-loop gate. It bounds three things, in ascending order of
how well the argument holds: spend (weakest — the ceiling is $20), taste, and
**content appropriateness** (strongest — see flow 8).

**4. Acquire and prepare.** Fetch at gallery resolution (tiled where the source
requires it), extract and normalise metadata across providers, select a mat
colour, and render the 4K TV image. Largely exists today in `art.py` and
`image_utils.py`. **The e-paper label is not rendered here** — corrected
2026-07-20; label rendering belongs to the display plane, which owns the panel
(see flow 6 and § Platform). Panel geometry in the curation catalogue is the
violation the ratified data-model norm forbids, which is why
`Rendition(kind='label')` was removed.

**5. Organise into themes.** Group accepted works into named themes. Switching the
active theme changes what the TV shows. Themes are the curator's unit of
intention — this is what "per-user preferences" resolved to, and it is a naming
and grouping concept, not an accounts concept.

**6. Display and sync.** Keep the accepted library uploaded to the TV, **rotate
through the active theme's subset from the host**, and drive the label panel from
the resulting callbacks. Partly exists in `tvart.py` — but the rotation mechanism
changes: the TV's native slideshow can only be scoped to a whole category, so
switching themes through it would mean deleting and re-uploading every work.
Host-driven rotation makes a theme switch cost zero TV writes.

**7. Ambient adaptation.** Brightness follows sun position; art mode follows time
of day. Exists today in `local.py`; the auto art-mode logic is currently
commented out.

**8. Drive everything from an agent, over MCP.** Every content-management
operation is available as an MCP tool, at parity with the web UI. The worked
example: point Claude Code at the server and say *"add all of Salvador Dalí's most
famous works."* The same tools back the in-UI agent.

This is a **must-have**, and it is what flipped the product to having external
API consumers. Three consequences that are easy to miss:

- **The gate is that a human saw the artwork — not that a surface was withheld.**
  An earlier draft of this brief said the review gate was "deliberately not
  automatable, by any surface, agent or human", while also promising that *every*
  content-management operation is an MCP tool. Both cannot hold, and the conflict
  was resolved in favour of a sharper reading of what the gate is for.

  The gate's durable justification is **content appropriateness**, not spend.
  Discovery searches the open web, so a bad search can surface work that is
  explicit, disturbing, or simply wrong for a living room — and it would appear
  on a wall in a shared home, seen by household members and guests who have no
  interface with which to object, possibly while the curator is elsewhere. The
  failure is fully reversible but publicly visible while it lasts. Spend alone
  ($20 ceiling, ~$0.13 a run) would not justify the gate; this does.

  What actually prevents that failure is a person **looking at the picture**. So
  accepting is available over MCP, and the requirement that carries the gate is
  that **the reviewing surface must show the image**: candidate listings return
  thumbnails, not just titles and rationales. A curator accepting from a terminal
  on the strength of a title alone is the failure this gate exists to stop, and it
  is a failure the web UI would never have permitted.

- **The blast radius is smaller than "cannot", and the brief should say so.**
  Because an agent holds a verdict tool, a prompt-injected gallery page can in
  principle steer an acceptance. Three things bound it, and none of them is
  "impossible": acceptance is **visible** (it changes the wall), **fully
  reversible** (archive restores), and the curator is **present in the session**
  that issued the request. That is a weaker claim than the one this brief used to
  make, and stating the weaker true claim is the point.

- **Parity is structural, not aspirational.** Both the web UI's own agent and
  external clients such as Claude Code speak MCP; the UI's direct controls call
  HTTP. All of them are thin bindings over one service layer. Two implementations
  of "accept a work" diverge within weeks, invisibly. The norm lives in
  `architecture.md` § Direction (ratified 2026-07-20).

  **The in-UI agent is an MCP client rather than an in-process caller**, decided
  deliberately: either way the agent must be taught a surface, and MCP describes
  itself. More importantly it makes the server the unit of "an art library on a
  system", so one agent can manage several — which promotes multiple libraries
  from an accommodate-only concern toward a design driver. What that does *not*
  imply is routing the UI's own controls through MCP: tool results are shaped for
  a model to read, while a UI wants typed, paginated, partial data. Location
  transparency belongs in the service layer, beneath both surfaces, not in the
  choice of surface.

## Success Criteria

- A curator goes from natural-language intent to artwork on the wall without
  touching the filesystem, editing JSON, or SSHing into the Pi.
- **A discovery run proposes each work exactly once**, with one selected image and
  its alternates available behind it. Being shown the same painting several times
  and asked to pick counts as a failed run even if every instance is individually
  good.
- **A curator never accepts a work without having seen its image** — on any
  surface, including an agent's.
- Themes are switchable from the web UI and materialise on the TV without a
  redeploy.
- LLM spend stays under the declared monthly ceiling, and hitting the ceiling
  **stops** discovery rather than silently degrading it.
- The display plane keeps showing art when the curation plane is down.
- A failure in the unattended loader is visible **without inspecting the wall** —
  it reaches a log or surface a human actually reads.
- Mat-colour quality is at least as good as the 2024 implementation. This bar is
  subjective; the 41 existing artworks and their hand-tuned mats are the
  regression corpus.

## Scope

### v1

- Verify the Frame TV art API still works on current firmware — **done
  2026-07-19, art mode confirmed working**
- Curation plane and display plane, split as the architecture requires
- Web UI for curation: LLM-assisted discovery, review/accept, themes
- **MCP tool surface covering all content management, at parity with the web UI** —
  on the official `mcp` SDK, with a service layer that both MCP tools and the
  UI's HTTP handlers bind over
- New catalogue built through curation, seeded with the existing 41 artworks as
  worked examples
- Hard monthly LLM spend cap (USD 20) that fails closed
- OpenRouter multi-provider model access, with a separate cheap vision model for
  mat-colour selection
- E-paper label rendering behind a display interface
- **A test suite — none exists today**
- Deployment values out of source (`ART_ROOT` first); `token_file` out of git

### Accommodate (design for, don't build)

- Multiple household accounts with per-user curation
- Multiple TVs / multiple display planes
- Swapping the e-paper panel or driver without touching curation

### Later

- Re-enabling automatic art-mode on/off scheduling (commented out in `tvart.py`)
- Weather-aware brightness (`local.py`'s `weather_adjustments` table is hardcoded
  to `"clear"`)

### Out of scope

| Excluded | Rationale |
|---|---|
| Kubernetes, NATS, multi-pod deployment | Stated directly by the operator. One household, one TV, one curation process — the coherence problems that infrastructure solves do not exist here. |
| 3tears agent memory | Depends on `pgvector`, which forces Postgres. Operator confirmed agents may be stateless across sessions, so this is dropped rather than deferred — and dropping it is what keeps the curation plane infrastructure-free. |
| Migrating the existing `all.json` schema | Decided to start over through curation. The 41 records have known defects (identity keyed on source URL, per-device TV state embedded, semi-structured `artist_details`) and every work is re-fetchable from its source URL. |
| Public or third-party API consumers | The HTTP surface exists only to back this product's own UI and its display plane. |

## Platform

Two processes, **one machine**.

Host: Raspberry Pi 4 Model B, 8 GB, Raspberry Pi OS Trixie, SD-card boot.

- **Curation plane** — a Python 3.14 FastAPI application under systemd. Owns
  discovery, acquisition, preparation, and the catalogue. Serves the web UI, its
  HTTP API, and the MCP endpoint from one ASGI application.
- **Display plane** — a Python 3.13 systemd daemon (`Restart=always`), driving a
  Samsung Frame TV over LAN websocket and a Waveshare 6" HD e-paper HAT
  (1448x1072, 16-level greyscale) over SPI. Renders the e-paper label.

They share `ART_ROOT` on local disk and communicate through exactly one file — the
theme manifest. The display plane makes no network call to curation. Topology,
channels, and failure modes are in `architecture.md`.

> **Amended 2026-07-20.** This previously read "deployed wherever a long-running
> process is available (desktop, NAS, or a second Pi)". The operator decided both
> planes run on the Pi. Storage was checked and does not force otherwise — 500
> works is roughly 10 GB.

**The split was originally forced by a Python version conflict. It is now a
choice — and it survives as one.**

Every `3tears` package declares `requires-python = ">=3.14"`, while the IT8951
e-paper driver compiles Cython from 2023-era sources and targets 3.13/3.12. An
audit confirmed 3.14 is genuinely required as shipped, but only by **16 mechanical
source sites**, with no third-party dependency imposing a floor above 3.10 — so
the constraint is removable.

That does not merge the planes, because **the display plane does not want 3tears
at all.** It needs an HTTP client, `samsungtvws`, PIL, and the e-paper driver.
Three-tier entities are of no use to it, and the shared-catalogue case that would
justify them is exactly the multi-pod coherence problem ruled out of scope.

The separation therefore stands on its own merits:

- It matches the data contract already recorded in `learnings.md` — upstream
  artifacts (`raw/`, `api-cache/`, `tile-cache/`) are expensive and
  device-independent; derived artifacts (`ready/`, `tv-thumbs/`, `label/`) are
  cheap and device-specific and must never be transported.
- It makes "e-paper behind an interface" a process boundary rather than a
  convention.
- It is what lets the display plane keep working when curation is down — the
  availability asymmetry that matters, since the household experiences only the TV.
  Now a ratified norm (`nonfunctional-requirements.md` § Direction).

> **A rationale withdrawn, 2026-07-20.** This list previously included "it moves
> tiled gigapixel fetching, k-means over LAB pixel arrays, and 4K compositing off a
> Pi 4." Both planes now run on the Pi, so that is false and must not be cited. It
> was weaker than it read anyway: the existing code downsizes to 2048² before the
> colour work, so peak memory is a few hundred MB on an 8 GB machine.
>
> The split survives the change comfortably. Its *cost* was the distributed-systems
> tax, and a shared filesystem removes that; its *benefit* — the wall staying lit
> through a curation restart — matters more on one box, because that restart now
> happens constantly during development.

Relaxing 3tears remains worth doing on *its* merits — a latent portability limit
in a framework the operator maintains, plus two real defects the audit turned up —
but it is no longer a dependency of this product's architecture. See
`.prawduct/artifacts/3tears-integration-findings.md`.
