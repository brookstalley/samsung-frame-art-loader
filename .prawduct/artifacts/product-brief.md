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
| 2 | LLM-assisted discovery | must-have |
| 3 | Review and accept | must-have |
| 4 | Acquire and prepare | must-have |
| 5 | Organise into themes | must-have |
| 6 | Display and sync | must-have |
| 7 | Ambient adaptation | nice-to-have |

**1. Express curatorial intent.** The curator states an intent in the web UI. The
system interprets it into a discovery strategy and shows an estimated cost
*before* running anything. Cost visibility at the point of decision is what makes
the spend ceiling feel like a guardrail rather than a surprise.

**2. LLM-assisted discovery.** An agentic search over museum APIs and the open web
produces candidate works, each with provenance: which source, what licence, and
why it matched the intent. This is the flow with unbounded cost and runtime, and
therefore the one the spend ceiling exists to bound.

**3. Review and accept.** The curator accepts or rejects candidates. Only accepted
works enter the catalogue. This is the human-in-the-loop gate that bounds both
spend and taste, and it is deliberately not automatable.

**4. Acquire and prepare.** Fetch at gallery resolution (tiled where the source
requires it), extract and normalise metadata across providers, select a mat
colour, render the 4K TV image and the e-paper label. Largely exists today in
`art.py` and `image_utils.py`.

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

## Success Criteria

- A curator goes from natural-language intent to artwork on the wall without
  touching the filesystem, editing JSON, or SSHing into the Pi.
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

Two planes.

- **Curation plane** — a web application, deployed wherever a long-running process
  is available (desktop, NAS, or a second Pi). Owns discovery, acquisition,
  preparation, and the catalogue.
- **Display plane** — a systemd daemon on a Raspberry Pi 4 Model B, driving a
  Samsung Frame TV over LAN websocket and a Waveshare 6" HD e-paper HAT
  (1448x1072, 16-level greyscale) over SPI.

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
- It moves tiled gigapixel fetching, k-means over LAB pixel arrays, and 4K
  compositing off a Pi 4.
- It makes "e-paper behind an interface" a process boundary rather than a
  convention.
- It is what lets the display plane keep working when curation is down — the
  availability asymmetry that matters, since the household experiences only the TV.

Relaxing 3tears remains worth doing on *its* merits — a latent portability limit
in a framework the operator maintains, plus two real defects the audit turned up —
but it is no longer a dependency of this product's architecture. See
`.prawduct/artifacts/3tears-integration-findings.md`.
