---
artifact: architecture
version: 1
depends_on:
  - artifact: product-brief
  - artifact: data-model
  - artifact: nonfunctional-requirements
last_validated: null
---

# Architecture

Two processes, one machine, one shared directory, and exactly one file between
them. That is the whole system, and the shape is deliberate: the split exists so
the wall keeps showing art while the curation process is restarted, upgraded, or
crashing — not because the work is too big for one box.

## Direction

<!-- Ratified by the owner 2026-07-20. Enforcement row in project-preferences.md. -->

**The theme manifest file is the only channel from curation to display.** The
display plane reads the manifest and the image tree. It makes no network call to
the curation process, imports no curation module, and queries no curation
database. Adding a second channel is a departure requiring a recorded decision.

> **Why:** The availability norm in `nonfunctional-requirements.md` says the
> display plane never requires the curation plane to be reachable. A single
> file-shaped channel makes that structurally true rather than carefully
> maintained — there is nothing to be unreachable. The danger a norm is needed for
> is the *plausible* second channel: "just fetch the label text live", "just ask
> curation which work is next". Each would work perfectly in development and in
> every test, because curation is up in development and in every test. The
> fallback path is the one that never gets exercised until the night it matters.
>
> **Corollary — the channel is one-directional.** Curation writes, display reads.
> Display never writes the manifest or the catalogue; its own device state lives in
> its own store (see Data Ownership).
>
> **Status:** steady-state.
>
> **Retroactivity:** No existing code has two planes. Nothing to migrate.

<!-- Ratified by the owner 2026-08-07, in the words they stated it: "The display
     device HAS to render the label. We may have multiple pi's with different
     displays, we may have a pc or Mac with a monitor and no e-ink that renders
     labels in the mat area." Raised mid-build while Chunk 13A was choosing where
     to render, and written before the interface was designed to it. -->

**A display device renders its own label, and the label travels as metadata.**
What crosses from curation is the label *text* the manifest already carries. How
that text is arranged, and what it is drawn onto, are decided by the device that
owns the output surface — never upstream of it. The chain is **metadata →
layout → rendering**, and only the first link is shared: layout and rendering
both live on the display device.

> **Why:** There is not one output surface and there will not be. Today's is a
> 1448×1072 e-paper panel on a Raspberry Pi; the deployment may hold several Pis
> with panels of different geometry, and a display device may have no e-ink at all
> — a PC or Mac with a monitor, where the label is drawn into the mat area around
> the artwork rather than onto a panel beside it. A label rendered upstream has to
> be rendered once per surface by something that knows every surface, which is the
> catalogue plane learning the geometry of every device on the wall. That is the
> shape `data-model.md` names by example as its anti-pattern: the 2024 index's
> `label_file` with `_w648_h480` baked into the filename.
>
> The alternative considered and rejected was pre-rendering label images in
> curation and shipping them down. It fails three ways: it puts per-device
> geometry in the catalogue plane, it makes the label a derived artifact with two
> upstreams to invalidate — edit a title and every stale image must be found — and
> it forecloses a label that says anything about *now*, since a pre-rendered image
> can only say what was known when it was drawn. It does not even buy a leaner
> display plane, because the e-paper driver takes a decoded image, so that plane
> needs an imaging dependency either way.
>
> **Corollary — output surfaces are plural and the interface must not assume
> e-ink.** The seam a device implements is "a surface a label can be put on",
> with its geometry as configuration. "This device has no label surface" is a
> valid configuration, not a fault.
>
> **Status:** steady-state.
>
> **Retroactivity:** The 2024 `ArtLabel` hardcodes one geometry and one panel and
> is retired with the rest of the 2024 modules; nothing else renders a label yet.

<!-- Ratified by the owner 2026-07-20. Enforcement row in project-preferences.md.
     Given a Direction home on 2026-07-20 after Critic review found it cited as
     binding in four artifacts with no recorded ratification anywhere. -->

**Operation logic lives only in the service layer.** MCP tools and HTTP handlers
are thin bindings: they unpack arguments, call one service method, and format the
result. A handler that validates, orders, or decides is the violation.

> **Why:** The product requires the MCP surface at parity with the web UI, but the
> UI's own controls call HTTP, not MCP. Parity is therefore only guaranteed if both
> are bindings over a single implementation. Two implementations of "accept a
> candidate" diverge within weeks, and the divergence is invisible until an agent
> and a click produce different results on the same catalogue — a failure the
> curator would experience as the product being untrustworthy rather than as a bug.
>
> **Status:** steady-state.
>
> **Enforcement is judgement, not structure.** The enforcement column says "Critic",
> which means a reviewer reading handlers — there is no test that fails when logic
> creeps into a binding. This is the same gap that sent the manifest-channel norm to
> issue #7 for a real test, and it is named here rather than left for a later reader
> to discover.
>
> **Retroactivity:** There is no service layer yet, so the honest code answer is
> "nothing to migrate" — and that answer is exactly why this needs the *artifact*
> question asked instead. Checked 2026-07-20 against every artifact that specifies
> handler or tool behaviour: `api-contract.md`'s five action-dispatch tools are
> specified as dispatch plus formatting, with the error model deriving `isError`
> from the payload rather than deciding it in the tool; `boundary-patterns.md`
> places validation at the service boundary. **No specified behaviour violates the
> norm.** The one thing it does bind going forward is the registry-generated tool
> definitions — generation must not become a place where per-tool logic accretes.

## Overview & Topology

**One host.** Raspberry Pi 4 Model B, 8 GB, Raspberry Pi OS Trixie, booting from
SD card. Both processes run here. This is a **2026-07-20 change** from the
recorded plan (curation on a desktop, NAS, or second Pi) — see Decision Log.

```
                    ┌──────────────────── Raspberry Pi 4 (8 GB) ───────────────────┐
                    │                                                              │
  MCP clients ─────►│  ┌─────────────────────────┐                                 │
  (Claude Code,     │  │  curation                │  writes                        │
   in-UI agent)     │  │  Python 3.14 venv        ├───────────┐                    │
                    │  │  FastAPI + uvicorn       │           │                    │
  Browser ─────────►│  │    /        web UI       │           ▼                    │
  (curation UI)     │  │    /api/*   HTTP API     │   ┌──────────────────────────┐ │
                    │  │    /mcp     MCP (SHTTP)  │   │  ART_ROOT (shared dir)   │ │
                    │  │                          │   │                          │ │
                    │  │  discovery · acquisition │   │   catalogue.sqlite  (C)  │ │
                    │  │  image prep · mat colour │   │   theme-manifest.json(C) │ │
                    │  └───────────┬──────────────┘   │   raw/ ready/ thumbs/    │ │
                    │              │                  │   tv-thumbs/ tile-cache/ │ │
                    │              │                  │   previews/              │ │
                    │              │ HTTPS            │                          │ │
                    │              ▼                  │   display-state.sqlite(D)│ │
                    │   OpenRouter, museum APIs,      └────────────┬─────────────┘ │
                    │   Google Arts & Culture                      │ reads         │
                    │                                              ▼               │
                    │                                 ┌──────────────────────────┐ │
                    │                                 │  display                 │ │
                    │                                 │  Python 3.13 venv        │ │
                    │                                 │  systemd Restart=always  │ │
                    │                                 │  rotation · label render │ │
                    │                                 └────┬──────────────┬──────┘ │
                    └──────────────────────────────────────┼──────────────┼────────┘
                                                 LAN ws    │              │ SPI
                                                           ▼              ▼
                                                    Samsung Frame TV   e-paper HAT
                                                                       1448×1072

  (C) = written by curation only    (D) = written by display only
```

**Why the product is split at all.** The original rationale — "it moves gigapixel
fetching, k-means over LAB arrays, and 4K compositing off a Pi 4" — **is no longer
true and must not be cited.** Co-location retires it. What survives:

1. **The display plane's Python version is pinned by hardware.** The IT8951
   e-paper driver compiles Cython from 2023 sources targeting 3.12/3.13, while the
   curation plane runs 3.14. Two venvs on one host is the cheap resolution, and it
   stays the resolution whatever the curation floor turns out to be.
   **What holds that floor is stated once, in `project-preferences.md` §
   Language & Runtime, and is not repeated here** — this item said the floor
   "rests on the models package alone" and was still saying it after that package
   moved to a test-only group. As of 2026-08-02 no default dependency requires
   3.14, so **this leg of the split is the weakest of the three** and the two
   below carry it: read them as the reasons, not this one.
2. **The wall must not go blank when curation restarts.** This matters *more* on
   one box, not less: during development the curation process is restarted
   constantly, and a single-process design would blank the TV every time.
3. **"E-paper behind an interface" becomes a process boundary** rather than a
   convention someone has to respect.

**What co-location removed.** The split's real cost was the distributed-systems
tax — a network contract, sync, two deployments, two failure domains to reason
about. A shared filesystem pays that down to near zero. The split got *cheaper*
when it stopped being distributed.

**Honest note on the classification.** `multi_process_distributed` remains the
recorded characteristic and this artifact remains warranted — two processes that
can fail independently is the trigger. But the product is now multi-process and
*not* distributed, which is why the resilience section below is much shorter than
it would otherwise be: there is no network partition between planes, because there
is no network between planes.

## Components & Responsibilities

### curation

- **Purpose:** turn curatorial intent into displayable, prepared artwork.
- **Platform:** Python 3.14 venv on a uv-managed standalone interpreter — *not* the
  system 3.13, and it cannot see distro site-packages (`operational-spec.md`
  § The Curation Interpreter). FastAPI on uvicorn, systemd unit. Always-on but
  usually idle — it is on-demand in behaviour, resident in lifecycle.
- **Owned state (sole writer):** the entire catalogue — works, image instances,
  verdicts, suppression scopes, mat colours, themes and their membership,
  discovery runs. Plus the whole image tree and the theme manifest.
- **Serves three surfaces from one ASGI app:** the web UI, its HTTP API, and the
  MCP streamable-HTTP endpoint. All three are thin bindings over one service layer
  (`project-preferences.md`, Critic-enforced).

  *(Built 2026-08-01, and the first two turned out to be **one** surface rather
  than two. The UI is a static shell plus a script that reads `/api/*`; there is
  no server-side rendering and no template engine. Server-rendered pages would
  have left the HTTP API either unused or carrying a second shape of every read —
  the divergence the shared service layer exists to prevent, reappearing one
  layer up. No framework and no build step: a Node toolchain on the Pi buys
  nothing a single operator on a private network can see.)*
- **A fourth binding is not a surface:** `curation/seed/` is a hand-run command
  that reads the 2024 index and mints its works through `CatalogueService`. It is
  bound by the same rule for the same reason — it enforces no catalogue
  constraint of its own, so a work that arrived from the old index obeys exactly
  what a work that arrived from discovery does. What it *does* own is how to read
  one particular outside file, and what to say about a record that would not seed
  cleanly. It takes the catalogue service alone rather than the container: it
  writes no discovery state and no directive, so it needs neither the services
  that own them nor the startup reconciliation that repairs them.
- **Internal layering, inside that plane** (established 2026-07-27; `acquisition/`
  added 2026-08-03 — the fetch paths, the guards and the URL policy, sitting beside
  `discovery/` as the other package that reaches outside the machine, and extended
  the same day with preparation: the mat engine, the compositor and the colour
  arithmetic they share. **`PreparationService` is a peer of `AcquisitionService`,
  not its tail**, because a work is acquired once and prepared repeatedly — on a
  panel change, a re-chosen mat, or a stale rendition — and folding the two
  together would make every re-render read as a re-fetch in the journal. The mat
  engine reaches OpenRouter through the same first-party client discovery uses,
  with its own model: discovery wants a text model that searches, preparation
  wants one that can see):

  ```
  MCP tools  ·  HTTP handlers  ·  browser client   bindings: unpack, call one method, format
        └──────────────┬──────────────┘            (the client renders JSON and decides nothing)
                 Services container                what a surface is handed; no surface names one service
   ┌────────────┬──────┴───────┬────────────┐
  Discovery     │           Display      SurveyService   every rule, transition and derivation
  Runner ──┐    │           Service           │          (all hold CatalogueService;
        │  │    │              │        ThumbnailService   it holds none of them)
        │  ├─ DiscoveryEngine (Protocol)      │          phase 1 — discovery's paid seam, reachable
        │  │    UnavailableEngine ships       │          by no other service. NOT the only paid edge
        │  │                                  │          any more: MatEngine is the second, below
        │  ├─ ImageSearch (Protocol)          │          phase 2 — the museum seam. Free, but
        │  │    ArticImageSearch ships        │          behind a seam for the same reason
        │  ├─ CollectionBrowse (Protocol)     │          what the collection HOLDS by an artist, as
        │  │                                  │          opposed to what it can find: the offer
        │  │                                  │          supplementing works phase 2 could not confirm
        │  └─ PreviewCache                    │          writes the disposable local copy an
        │                                     │          instance is reviewed from
        │                                HealthService    every signal the health panel states, in one
        │                                     │          call. A service and not a handler concern
        │                                  observations   because WHICH signals the panel makes is a
        │                                     │          product rule — so the next one is added in
        │                                     │          one place, testable without HTTP, rather
        │                                     │          than in a handler and a client separately.
        │                                     │          `observations.observe` is the single parse
        │                                     │          under both observed documents (the display
        │                                     │          heartbeat, the backup receipt): one parser,
        │                                     │          because two would drift. Absent, unreadable
        │                                     │          and aged are three answers, never an
        │                                     │          exception — a panel that raised where an age
        │                                     │          belongs would be an outage of its own
  Discovery ── ReviewService                  │          the pre-acceptance twin of SurveyService
  Service ──── PreviewSweep                   │          reclaims the previews of decided works;
        │       │              │              │          the plane's second background thread
        │       │   AcquisitionService        │          fetches the master a work was accepted for.
        │       │    ├─ StreamOpener (seam)   │          the only service that runs a subprocess; all
        │       │    ├─ Resolver   (seam)     │          three edges are injected, so the policy above
        │       │    └─ TileTarget  (seam)    │          them runs offline. TileTarget is the odd one:
        │       │              │              │          it reaches a MUSEUM, not a network primitive,
        │       │              │              │          because only the provider knows where an
        │       │              │              │          object's tiles are actually served
        │       │   PreparationService        │          turns a held original into a mat and a 4K
        │       │    └─ MatEngine  (seam)     │          canvas. Its seam is the SECOND paid edge —
        │       │              │              │          a vision model, keyless deployments fall
        │       │              │              │          back to the mechanical producer and say so
        │       └── CatalogueService ─────────┘
        │              │
  SqliteDiscovery  SqliteCatalogue                domain adapters: schema, record↔row, ordering
        └──────────────┬──────────────┘           and paging — the product judgements
              SqliteDurableStore                  generic: tables, keys, rows. Knows no artwork
  ```

  **`AcquisitionService` is the one service that leaves the machine to do its
  job**, and its three foreign edges are injected rather than reached for: an HTTP
  stream opener, a name resolver, and — added 2026-08-04 — a per-provider tile-target
  resolver, which is the one that reaches a *museum* rather than a network
  primitive. It exists because the URL a `Source` records identifies the object
  and is not always where the pixels are served; only the provider can close that
  gap, and storing its answer would put a derived URL in a durable row. It is a
  required constructor argument with no default, because an empty map is
  indistinguishable from correct wiring until a museum source fails. That is the same
  arrangement `DiscoveryEngine`
  and `ImageSearch` have one row up, for the same reason — the rules worth testing
  exhaustively (which source is used, what a refusal is recorded as, whether a
  host may be fetched at all) then run with no network. The subprocess is not
  behind a Protocol: there is one binary, its contract is captured in
  `dezoomify-cli-findings.md`, and a second implementation would be a second
  fiction rather than a second provider.

  **`ReviewService` is `SurveyService`'s counterpart on the other side of
  acceptance, and they are deliberately two classes rather than one.** Both
  compose "a work as a surface showing it to a human needs it", but they read
  different entities entirely — one the catalogue, one the pipeline — and share
  no logic, so a single service spanning both would hold the catalogue and
  discovery stores at once to save a name. `ReviewService` holds
  `DiscoveryService`, never the reverse, which keeps the dependency running the
  way the pipeline does.

  **`PreviewCache` hangs off the runner, beside the two engine seams**, because a
  preview is fetched at the moment an instance is found and from nowhere else.
  `ReviewService` reads those files without going through it: producing a
  small copy for a tool result is a read of the art tree, not another reason to
  reach a museum.

  **`PreviewSweep` is the plane's second background thread, and the first driven
  by a timer** (added 2026-08-03). The runner's threads are one per run, started
  by a request and finished when that run is; this one is started by the
  application's lifespan, sweeps immediately, then waits out
  `PREVIEW_SWEEP_INTERVAL_SECONDS` and repeats until shutdown stops it. It sits
  beside `ReviewService` on `DiscoveryService` rather than under the runner,
  because what it needs is the record layer and the art tree — never an engine,
  never a museum, and nothing that can cost money. It is in the container for
  the reason every service is: the entry point wires one thing, and a concern
  reachable only by an entry point is one no surface and no test can exercise.

  Its pass runs inside one store transaction, and **what that closes is narrower
  than "the sweep and phase 2 cannot race"**. Deciding what to delete is a read
  and deleting it is a write to the filesystem; holding the lock across both stops
  `record_image` landing *between* them, because it takes the same lock. It does
  not stop the writer's own two halves straddling it — `PreviewCache.store` checks
  the file with no lock at all and `record_image` takes one afterwards, so a row
  can still be written naming a file a pass removed in between. That residual is
  filed, and its consequence is bounded rather than hidden: `ReviewService` reports
  a `preview_path` with no file behind it as an absent copy, not an unreadable one.
  This is the one place in this plane where a transaction spans work outside the
  store, and it is bounded to a walk of the catalogue's rows plus a handful of
  unlinks.

  `DiscoveryRunner` holds `DiscoveryService`, not the other way round, and the
  engine hangs off the runner alone — no other service can reach it, which is
  what "exactly one tool runs a *paid discovery engine*" looks like as a
  dependency edge rather than as a rule somebody remembers. *(Narrowed 2026-08-03:
  the edge is real and unchanged, but it never said "exactly one tool spends
  money", which stopped being true when `PreparationService` gained a mat engine
  reaching the same provider. The two paid paths share the transport and share
  nothing else — no service can reach both — and that is the property the
  structure actually enforces.)*

  **`DiscoveryRunner` and the engine seam were added 2026-08-02, and the split
  between the runner and `DiscoveryService` is the load-bearing part.**
  `DiscoveryService` owns the *records* — both state machines, the verdicts, the
  spend rows — and is deliberately synchronous with no notion of a process.
  `DiscoveryRunner` sits above it and owns everything that has one: a worker per
  run behind the handle `start` returns, the `status` hold, the approval gate's
  threshold, the estimates, and spend reporting. A record layer that also knew
  about worker threads would be untestable without them.

  **`DiscoveryEngine` is a Protocol, and every call that can cost money is behind
  it.** That placement is the structural half of the ratified norm that spend
  ceilings are the provider's: the engine reports what it spent and raises
  `BudgetExhausted` when the provider refuses, and nothing above it consults a
  local tally to decide whether it may proceed. It is also what makes the run
  lifecycle testable without a network, an API key, or a cent — a property a test
  enforces by parsing the modules behind the seam and refusing any import that
  could open a socket.

  A deployment gets `UnavailableEngine` only when it holds no API key, and it
  declares why it cannot run so that `start` is refused *before* a run exists. A
  convincing stand-in wired here instead would write invented works into a real
  catalogue, indistinguishable from found ones; the test double therefore lives
  under `tests/` and is deliberately out of a deployment's reach.

  **`ImageSearch` is phase 2's seam, added 2026-08-02, and it is a seam despite
  costing nothing.** Museum APIs are open and unmetered, so the money argument
  that placed `DiscoveryEngine` does not apply — the reason here is the other
  one: everything above the seam (driving a run, ranking instances, caching
  previews, deciding a work is unresolved) must be testable without a network,
  and `provider` is an open vocabulary in the data model precisely because one
  museum is the first of many. A second provider is an implementation of this
  protocol rather than a change to anything that consumes it. The same parsing
  test that guards the paid seam covers this one, as an allowlist over the whole
  package rather than a list of named files.

  **It grew a fetch-path member on 2026-08-04, and that is a real widening worth
  naming.** `tile_url` answers "where are this object's tiles actually served",
  which acquisition asks and phase 2 never does — so the protocol now spans two
  callers with different concerns. It went here anyway because the alternative is
  worse: a second protocol over the same museum client, implemented by the same
  class, wired from the same configuration, would be two names for one seam. The
  cost is narrower than this entry first claimed, and the correction is worth
  keeping because it changes what the coupling actually costs: **`AcquisitionService`
  does not depend on the protocol at all.** It imports one *exception*
  (`ImageSearchFailure`) and is handed `tile_url` by the container as a plain
  callable keyed by provider. So the dependency is on a discovery-package error
  vocabulary, not on a discovery-package interface, and the seam is looser than
  "two callers share a protocol" suggests.

  **The third concern arrived on 2026-08-04, and it was split rather than
  added.** Browsing a collection by artist is a different question from searching
  it for a work: a search is given a work and must judge whether what came back
  is it, while a browse is given a facet and everything matching is by
  construction a work the collection holds. `CollectionBrowse` is therefore its
  own protocol beside `ImageSearch`, not a member on it. The rule this follows is
  the one stated above — split when a third concern arrives — and the test that
  decided it is whether a caller would ever want one without the other: a
  deployment can sensibly resolve images without offering adjacent works, and the
  reverse is incoherent, so they are genuinely separable. They are implemented by
  two classes over the same museum, wired independently from the same
  identifier.

  **What is deliberately *not* behind it: the judgement.** A provider reports
  what its collection holds; whether any of it is the work that was asked for is
  decided above the seam, in `discovery/phase_two.py`, so two providers cannot
  come to disagree about what "confident" means. That placement is a measurement
  rather than a preference — the Art Institute's own relevance score was measured
  unusable for the purpose (`artic-api-findings.md`), and a design that trusted
  each provider's score would have taken it.

  **The asymmetry with phase 1 is deliberate**: a missing model client refuses
  `start` before a run exists, while a missing image provider leaves an existing
  run at `resolving_images` and says so through `status`. Phase 2 has a run in
  hand by the time it would refuse, and failing that run would record something
  breaking when in fact a capability is simply not configured. The run view
  carries whether resolution is available, so the surface's wording comes from
  the wiring rather than from a sentence that goes stale the day it is built —
  which is exactly what happened to the one it replaced.

  **The real implementation landed 2026-08-02 and is two modules, both behind the
  seam.** `discovery/openrouter.py` is a first-party HTTP client — one provider,
  one account, and no knowledge of what a discovery run is; `discovery/phase_one.py`
  is the engine, which turns an intent into works and attributes what that cost.
  The split is what keeps the client's measured response shapes testable against a
  recorded transport while the engine's decisions stay testable without either.

  **The network guard was inverted when the client landed, and the inversion is
  the interesting part.** It had named three modules that may not import a
  transport — the three that were the whole of discovery when it was written. A
  list of *guarded* files silently stops covering whatever is added next while its
  result looks identical, so a phase-2 engine added above the seam would have been
  unguarded with nothing to show it. It now guards **every module in the package
  except a named allowlist**, each entry carrying its reason in the list itself:
  the OpenRouter client and the Art Institute client, each the far side of its own
  seam and exactly where a transport belongs, and the legacy seed reader, which
  touches `urllib.parse` and makes no request. Reaching the provider from anywhere
  else fails the suite by default rather than by having been anticipated. *(The
  allowlist is named rather than counted here: it grew by one the moment phase 2
  landed a second client, and this sentence still said "two-name" until Critic
  review caught it — a count in prose about a list that exists to be added to.)*

  **Two services were added on 2026-08-01, with the first browser surface.**
  `ThumbnailService` produces the downscaled copies that make a forty-card grid a
  page, recording each as a `RenditionKind.THUMBNAIL` so the cache is catalogued
  rather than loose on disk and inherits the staleness rule already governing the
  television render.

  **That "inherits" became true on 2026-08-05 and was not before.** The rule was
  written twice — once in `CatalogueService.list_renditions`, once inline in the
  manifest builder, which reached past the service into the store to feed itself
  — so a change to what "current" means would have landed in one and left the
  other deciding wall membership by the old one: a work badged current on the
  review grid and silently dropped from the wall as `stale_rendition`. Both the
  predicate (`is_current`) and the preference between several television renders
  (`tv_renditions_newest_first`) now live with the records, and the grid, the
  thumbnail service and the manifest all read them. The second of those closed a
  live disagreement rather than a hypothetical one: the builder took the most
  recently generated render while the thumbnail service took the first current
  one the store returned, and the unique index on `(artwork_id, kind,
  target_width, target_height)` makes two television renders reachable.

  **One kind-local supplement joined it on 2026-08-10, and the shape of the
  exception is the point.** `is_current` compares a rendition against the
  *original*, which is the whole answer for every kind drawn from the original —
  and the thumbnail is the one that is not: once a work has a canvas, the
  thumbnail is a copy of *that*. Composing or recomposing a canvas never touches
  the original, so the shared predicate answered "current" for a thumbnail of an
  image that had since been redrawn. `ThumbnailService._drawn_from` supplies the
  missing term, and it deliberately did **not** join `is_current`: the shared rule
  is shared so three consumers cannot disagree, and folding in a term only one of
  them can evaluate would break exactly that. The two actions this paragraph would
  otherwise invite are both refused — do not move the term into `is_current`, and
  do not re-invent a second supplement at another surface. A kind whose parent is
  another rendition is the only thing that earns one.
  `[DECISION: currency stays consolidated in `is_current`, with a bounded
  kind-local supplement for renditions drawn from another rendition | this
  paragraph argued for consolidation and the #90 fix departs from it, so the
  departure is decided rather than asserted: the two alternatives are folding
  `_drawn_from` into `is_current`, which hands the shared predicate a term two of
  its three consumers cannot evaluate and so re-opens the disagreement
  consolidation exists to close, and a second supplement at another surface, which
  is the duplication the 2026-08-05 consolidation removed; the exception's bound is
  the parent — only a kind whose parent is another rendition earns one, which today
  is the thumbnail alone | user can veto/override]`

  `SurveyService` composes a work with the two derived facts a
  human-facing surface needs beside it — how large it would render on this
  deployment's wall, and which held image it would be shown — because
  `api-contract.md` requires that same pairing of `art_review`, and a composition
  written once at each surface is the divergence this layer exists to prevent.

  **The layer is split by concern, and the split runs all the way down.** The
  catalogue owns works already accepted; discovery owns runs, proposals, image
  instances, spend and verdicts; display owns themes, the standing directive, and
  the manifest built from them. **Both discovery and display depend on the
  catalogue and neither is depended on by it** — acceptance is a promotion *into*
  the catalogue (a candidate becomes a work and its instances become that work's
  sources), and a theme is a grouping *of* catalogue works. Display reads the
  catalogue through `CatalogueService` and the theme/membership/directive tables
  through `CatalogueStore`, which is the same file: the manifest has to be built
  and the directive advanced in one consistent read.

  **One write crosses the concern line, deliberately.** Archiving a work nulls a
  directive pin naming it, from `CatalogueService`. The line it respects is
  *integrity* versus *semantics*: clearing an unsatisfiable reference in the
  transaction that creates it, never advancing the sequence. Every rule about what
  an advance means lives in `DisplayService`, unduplicated.

  **Both adapters share one connection**, which is what lets the promotion commit
  once or not at all; a surface takes the container rather than a service, so a
  fourth concern changes the wiring and nothing else.

  Three patterns are load-bearing enough to name here rather than leave in module
  docstrings:

  - **The persistence seam is split by schema knowledge, and its lower half is
    shaped to a foreign contract on purpose.** `SqliteDurableStore` matches the
    decomposition and naming of the `DurableStore` protocol in the operator's own
    three-tier framework, so that adopting that framework's collection layer later
    is an adapter over this class rather than a rewrite of it — while importing
    none of it, because a dependency is not worth taking to call no code. This is
    what the whole 3tears question resolved to; see the Decision Log below.
  - **The action surface is generated from one record per action.** The wire
    schema, argument validation, the `help` text and the error messages all derive
    from a single registry entry, so a tool cannot declare one thing and do
    another. Generation carries no per-tool logic — that would be the
    thin-binding norm's stated failure mode arriving by a side door.
  - **A schema change the file cannot be widened into is a migration, and there
    is no version number anywhere in the mechanism** *(added 2026-08-12, with the
    first such change this product has ever made — the walls one)*. The durable
    store widens a file by adding columns the declared schema has and the file
    lacks; that is the only change SQLite applies in place without losing data,
    so a column that goes *away*, a table replaced by a differently-keyed one, or
    rows carried between the two is written by hand in
    `curation/src/curation/persistence/migrations.py`. The facts a later schema
    change needs and cannot infer from reading one migration:
    - Migrations are **handed to the store at construction** —
      `SqliteDurableStore(path, schema, migrations=...)` — never reached for from
      inside it. The tier that knows no domain concept goes on knowing none.
    - They run **after widening and before the schema is read back**, in that
      order and for that reason: widening must not be denied the columns a
      migration will need, and the read-back must see the shape the migration
      left, because one of them may take a column away.
    - **Idempotent, and safe to interrupt.** Every step is guarded by what the
      file actually holds rather than by a recorded version, and the order is
      chosen so that any prefix leaves a file the next open finishes correctly —
      rows are carried before anything holding them is dropped. A version table
      was available and was deliberately not taken: it would be one more thing
      the file has to be trusted to keep accurate, and a half-applied migration
      is exactly the case where that trust is misplaced.
    - **`migrations.py` may hold no domain concept the durable tier does not.**
      It speaks in tables, columns and rows. The one exception is the default
      wall's *name*, which is a deployment value the migration must apply at the
      moment it creates the wall — declared there and read back down by
      `config.py`, rather than reached upward for.
    - **A migration makes the catalogue one-way**, which is a deployment fact
      before it is a persistence one — see § Deployment & Version Skew.
- **Must never:** talk to the TV, talk to the e-paper panel, know the **e-paper
  panel's** geometry, or know TV content ids. Every device fact belongs to display.
  Note the TV panel's *physical* geometry is not a device fact in this sense and
  is curation's — see § Configuration; the two were conflated until 2026-07-20.

### display

- **Purpose:** make the physical world match the manifest.
- **Platform:** Python 3.13 venv, systemd `Restart=always`. Genuinely always-on.
- **Owned state (sole writer):** `display-state.sqlite` — TV content-id bindings,
  per-work upload status, last selected work, whether this device has already
  switched the set's own slideshow off, and the last-acted-on directive sequence
  (see § The theme manifest).

  *(**Two corrections from building it, 2026-08-06.** "Brightness state" was
  listed here and is deliberately **not** persisted: it is recomputed from the sun
  and the clock on a timer, so a stored copy could only ever be a value that has
  gone stale — including after somebody moves the brightness with the remote —
  and the cost of not having it is one idempotent call on restart. The slideshow
  flag replaced it, and that one genuinely must survive a restart: `Restart=always`
  makes restarts routine and the call is only correct to make once.)* **Panel geometry
  is deliberately not listed** (corrected 2026-07-20 — it appeared here while
  every other artifact makes it *configuration* both planes read): a copy held as
  device state could drift from the value curation judges sources against, which
  is exactly the quiet mismatch `operational-spec.md` § Configuration warns
  about. Beyond `TvBinding`, this store's schema is display-internal and
  deliberately deferred (`data-model.md` § Deliberately not modelled).
  This is the ratified data-model norm ("per-device runtime state never lives in
  the catalogue") given a process to live in.
- **Reconciliation loop, as built (2026-08-06/07):** poll the manifest's mtime
  (~1 s) → adopt a new one, refusing an unrecognised major and keeping the last
  good document → reconcile the binding table against the set, removing what it
  holds that nothing accounts for → apply sun-position brightness → act on at most
  one directive → rotate when the interval is up. **Uploads are carried one per
  pass rather than batched on adoption**, so a fresh install shows something in
  seconds instead of blanking the wall for the five minutes forty uploads take.
  **A selection is confirmed by the set's own `image_selected` announcement**
  before anything is logged or recorded (§ Failure Modes). That callback is
  registered by the television seam, per connection. **The library keeps one
  handler per event rather than a list**, so a second subscriber registered
  directly would replace the confirmation handler rather than join it — silently,
  after which every rotation falls to its timeout and reports a wall that will not
  move while the newcomer works perfectly. That hazard is closed as of 2026-08-07:
  the seam fans the announcement out through `TvClient.observe_selections`, which
  resolves the pending selection first and then hands the announcement to every
  observer, isolating each so one that raises costs neither another observer nor
  the socket's reader task. Adding a listener is therefore safe; registering one
  with the library directly is still not, and nothing should.
- **Renders the e-paper label** (decided 2026-07-20 — see Decision Log). The
  **e-paper panel's** geometry (1448×1072) stays with the plane that owns that
  panel. Display does *not* render the mat — the mat is composed by curation into
  the `tv_display` rendition, so display never needs the TV's physical size.
  **The label follows what the set says is on the wall, not what this plane put
  there** — those differ whenever somebody picks a work with the remote, and a
  label driven only from the rotation would then name the previous picture for up
  to a full interval. It is the person standing in front of the wall who cannot
  tell a confident wrong label from a right one, so a picture the manifest cannot
  name gets an empty label rather than a stale one.
- **Must never:** write the catalogue, write the manifest, call the curation
  process, or import curation code.

## Communication & Boundaries

| # | Channel | Transport | Direction | Sync | Contract lives in |
|---|---|---|---|---|---|
| 1 | Theme manifest | File in ART_ROOT, atomic write + rename | curation → display | async | Below, and `boundary-patterns.md` |
| 2 | Image tree | Files in ART_ROOT | curation → display | async | Path convention, below |
| 2b | **Heartbeat / display status** | File in ART_ROOT, atomic write + rename | **display → curation** | async | `observability-strategy.md` § The Health Surface |
| 3 | MCP tool surface | Streamable HTTP at `/mcp` | external client → curation | sync | `api-contract.md` |
| 4 | UI HTTP API | HTTP JSON at `/api/*` | browser → curation | sync | `api-contract.md` |
| 5 | TV control | LAN websocket (`samsungtvws`) | display ↔ TV | async both ways | Foreign API |
| 6 | E-paper | SPI | display → panel | sync | Foreign API |
| 7 | Model + search | HTTPS | curation → OpenRouter | sync | Foreign API |
| 8 | Sources | HTTPS | curation → museum APIs, GA&C | sync | Foreign API |

**Trust boundaries.** Channels 3 and 4 are the only inbound ones, and both are
reached over an overlay network (Tailscale/VPN) rather than public exposure — the
network layer carries the trust boundary, which is what keeps
`security-model.md` short. Channel 5 crosses onto the LAN. Channels 7 and 8 reach
the open internet and are where prompt-injection content enters; bounds are in
`security-model.md`.

**Channels 1 and 2 are not trust boundaries** — same host, same user, same
filesystem. They are *coordination* boundaries.

### The theme manifest

The single inter-plane contract. A JSON document written to ART_ROOT by curation,
read by display.

- **Atomicity:** written to a temp file in the same directory and `os.replace`d
  onto the target. POSIX rename is atomic within a filesystem, so display never
  observes a partial manifest. This is the entire concurrency-control story
  between the planes.
- **Contents:** a schema version, the active theme's identity, the **rotation
  settings** that drive the display timer (`rotation_interval_seconds`, `shuffle`),
  a **directive block** (below), and an ordered list of entries — for each, the
  work id, the path to its prepared 4K render, and the label fields (title, the
  artist's whole name **and its family and given parts**, nationality, dates,
  date, medium, dimensions, commentary). Label *text* crosses; label *rendering*
  does not — which is why the parts cross as data rather than as a styled string:
  the plane that decides how the family name is set is the one that owns the
  panel, and the plane that knows which part is the family name is the one that
  owns the catalogue.
- **The directive block carries interactive commands.** A monotonically increasing
  `sequence` integer plus an optional `pinned_work_id`. When display sees
  `sequence` advance it acts once: with no pin it steps to the next work; with a
  pin it jumps to that work and continues rotating from there.

  > `[DECISION: interactive display commands ride in the manifest as a
  > sequence-nonce directive rather than getting their own channel | the ratified
  > norm makes the manifest the ONLY curation→display channel, and
  > `art_display(action='show_now'|'next')` was otherwise unimplementable — Critic
  > R-17. A directive in the manifest preserves the norm literally and in spirit:
  > still one channel, still one direction, and still no availability coupling,
  > because display works forever off the last manifest and simply stops receiving
  > directives if curation dies | user can veto/override]`

  The manifest is therefore **desired display state**, not merely a list. That
  framing is what makes commands expressible without a command channel.

  **Three semantics pinned before build (2026-07-20)**, because the directive is
  the one place where desired-state and command genuinely differ and none of the
  three follows from "it is a state file":

  - **The sequence is monotonic for the life of the catalogue; a manifest rebuild
    never resets it.** `sync` and theme switches rewrite the entry list but carry
    the current sequence forward unchanged — only `next`/`show_now` increment it.
    Curation owns the counter and stores it catalogue-side, which is what makes
    this cheap to guarantee. A rebuild that reset the counter would read to
    display as an advance (or mask a real one) and fire a phantom directive.
  - **Display persists the last-acted-on sequence in `display-state.sqlite`.**
    Without that, a restarted display re-observes the current manifest and cannot
    tell "already acted" from "new directive" — it would re-execute the last jump
    on every restart, and `Restart=always` makes restarts routine.
  - **Rapid directives coalesce.** Two `next` calls inside one poll interval
    advance the sequence twice but are observed once, producing one step.
    `[DECISION: latest-wins coalescing is accepted | the alternative — replaying
    every intermediate directive — turns the manifest into a command log, which is
    the channel shape the norm rejects; for a human pressing "next", latest-wins
    is also the expected behaviour | user can veto/override]`
  - **On sequence regression, display re-baselines without acting.** A manifest
    whose sequence is *lower* than the last-acted-on value is possible — the
    counter lives in the catalogue, and `operational-spec.md`'s exercised restore
    path can bring back an older one. A regression is not a directive: display
    logs one WARNING, adopts the observed value as its new baseline, and acts
    only on the next advance. Same posture as the unknown-major rule — when the
    channel says something impossible, keep state and say so rather than guess.
    This is what keeps a catalogue restore from replaying a stale pin.

- **Change detection:** display polls the manifest's mtime.
- **The poll interval is set by `next`, not by theme switching.** This is the
  non-obvious consequence of the decision above. A theme change tolerates seconds
  of latency happily; a human pressing "next" and waiting three seconds thinks the
  product is broken. So the interval is **~1 s**, which is one `stat()` per second
  — free — rather than the "few calls a minute" that the list-only design would
  have justified. Polling rather than inotify, deliberately: a mechanism that
  cannot silently unsubscribe.
- **Versioned, despite the co-location exemption.** See Deployment & Version Skew
  — this is where a recorded contradiction gets resolved rather than inherited.

### One manifest per wall — designed 2026-08-12, not built

The operator's ruling that **themes are global and assigned per wall**
(`data-model.md` § ThemeAssignment) reaches the inter-plane contract, because
everything above is written in the singular: *the* active theme's identity, *the*
sequence, *the* file. With more than one wall each of those is a per-wall fact.

**The manifest becomes one file per wall**, named by wall id, and each display
instance reads only the manifest for the wall it is configured to serve. The
directive semantics above are unchanged — they simply become per wall, which is
what the ruling already did to the counter itself.

`[DECISION: one manifest file per wall, rather than one file carrying a section
per wall | change detection is an mtime poll at ~1 s, and a shared file makes
every wall's display wake on every other wall's change while making "the
manifest's sequence" ambiguous exactly where the coalescing and
sequence-regression rules need it to be singular; per-file also keeps a display
plane unable to read a wall it does not serve | user can veto/override]`

**Two consequences, both cheap now:**

- **`display-heartbeat.json` takes the same treatment**, for the same reason and
  in the other direction — `information-architecture.md` requires health to name
  which wall is silent, and one shared heartbeat file has no way to say it.
- **The single-writer table below generalises rather than growing rows.** One
  writer per file still holds; the file set is now indexed by wall.

**What is built today is the single-file form**, `theme-manifest.json` in
`ART_ROOT` (`curation/src/curation/manifest/builder.py`), and it stays that way
until `build-plan-curation-ux.md` migrates it. The one-wall installation is the
degenerate case: one wall, one manifest, byte-identical behaviour.

## Data Ownership & Consistency

**Single writer per store, with no exceptions and no shared tables.**

| Store | Sole writer | Readers |
|---|---|---|
| `catalogue.sqlite` | curation | curation |
| `theme-manifest.json` — **one per wall once § One manifest per wall lands** | curation | display |
| image tree (`raw/`, `ready/`, …) | curation | display |
| `display-state.sqlite` | display | display |
| `display-heartbeat.json` (heartbeat) — **likewise one per wall** | display | curation |

There is no entity written by both planes, so there is no coordination protocol,
no conflict resolution, and no distributed-transaction problem. That is the payoff
of taking the manifest as the only channel: **the hard part of two-writer systems
is designed out rather than solved.**

> **On the heartbeat and the ratified norm.** The Direction norm governs the
> **curation → display** direction: display must never need curation reachable. The
> heartbeat runs the other way, and creates no dependency in the protected
> direction — display writes it and never checks whether anyone read it, so
> curation being absent changes nothing about display's behaviour. Single-writer
> still holds: display is its sole writer, curation only reads.
>
> Recorded explicitly because the omission was a real one — the heartbeat was
> introduced in `observability-strategy.md` and initially reached neither of these
> tables (Critic finding), which is how a second channel becomes load-bearing
> without ever being reviewed as one.

### Readiness — the question that was open, and why it dissolved

The recorded open question asked for "the single source of truth for *this artwork
is ready to display*", noting it was reconstructible only by joining six signals
with nothing owning the conjunction, and that an accepted-but-unacquired work is a
legal theme member — so the display plane could select something it cannot render.

**The bug was conflating two different readinesses.**

- **Catalogue readiness** — *can this be rendered?* An original exists, the fetch
  succeeded, the render is current, a mat colour is current. This is curation's
  question, and it is evaluated **at manifest-build time, in exactly one place**.
- **Device readiness** — *is this on the TV?* This is display's question, it lives
  in `display-state.sqlite`, and it never enters the catalogue.

Neither is a stored flag on the work, so neither can drift. **Manifest membership
IS catalogue readiness** — the manifest is the readiness-filtered projection of a
theme, and because it is the only thing display ever sees, the display plane
*cannot* select an unrenderable work. The failure mode is structurally impossible
rather than defended against.

Theme membership stays what it should always have been: a **curatorial** statement
("this belongs in this theme"), not a technical one. A work can be in a theme and
absent from the manifest.

**The cost, which must be paid explicitly.** A work can be in a theme and silently
not on the wall. That is precisely this product's characteristic failure — silence
— so it does not get to be silent: **the manifest build reports its exclusions**,
per work and with a reason, and the curation UI surfaces "3 works in this theme are
not currently displayable, because …". A manifest builder that only returns a list
is an incomplete implementation of this design.

**The five exclusion causes, as built (2026-07-31).** `archived`, `no_original`,
`no_mat_color`, `no_rendition`, `stale_rendition`. Each is a distinct thing a
curator would do something different about, which is the test for whether a cause
earns its own name.

> **"The fetch succeeded" is deliberately not a sixth check** *(settled at build;
> the four-signal sentence above reads as though it were).* Holding an original is
> what a succeeded fetch produces, so the condition is already carried by
> `no_original`. Read instead as "the *most recent* fetch attempt succeeded", it
> would take a work off the wall because a later re-acquisition failed while a
> perfectly good original and a current render were still held — a regression
> wearing a safety check's clothes. The signal is a conjunct of readiness, not an
> independent test of it.

**Archiving removes a work from the manifest and leaves it in the theme.**
Membership is curatorial and readiness is technical, so archiving moves one and
not the other; the work reappears on the wall if it is restored, with no
membership to rebuild.

### Consistency

Eventually consistent, with unbounded staleness by design. Display picks up a new
manifest within one poll interval. If curation is stopped, display keeps showing
the last manifest **forever**, which is the correct behaviour and not a degraded
mode — see Failure Modes.

## Failure Modes & Resilience

There is no network between the planes, so most of the usual multi-runtime failure
catalogue does not apply. What remains:

| Failure | Effect on the rest | Intended behaviour |
|---|---|---|
| curation process down/restarting/crashed | none **on display**; a run actively working dies with it, while one at `awaiting_approval` survives | Display keeps rotating the last manifest indefinitely — **normal operation, not degradation**, the norm working. But this is *not* "no effect": a run actively working is lost, and **on next start curation reconciles runs left in a process-held state (`resolving_works`, `resolving_images`) to `interrupted`** (`data-model.md` → State Machines). `awaiting_approval` is deliberately NOT reconciled — it is human-held state that must survive a restart. Without reconciliation a crash would strand the run's works as permanently un-re-searchable via constraint 14. Note `MemoryMax` on the curation unit exists to cause exactly this kill |
| display process down | none to curation; wall freezes | TV stays in art mode holding the last work; label goes stale. systemd restarts |
| Manifest references a missing image file | one work unshowable | Display **skips it, logs at WARNING, continues the rotation.** Never crashes, never blanks the wall. Fatal-for-one-item, per the recorded error taxonomy |
| Manifest has an unknown major schema version | new theme not adopted | Display **keeps the previous manifest** and logs at ERROR. Refusing to guess beats rendering a misparse |
| TV unreachable / websocket drop | rotation stalls | Retry with backoff; the TV holds its last image. Expected operating condition, not an incident |
| **TV reachable, panel dark: it takes selections and displays none of them** | rotation stalls, and every call reports success | **The one failure a return value cannot carry**, and it is the everyday condition of a set someone switched off — measured on the deployment's own television (`samsung-tv-state-findings.md`): uploads, deletions, listings and brightness all work, while `select_image` is accepted, raises nothing, emits no event, and changes nothing. So **a selection is confirmed by the set's own `image_selected` announcement**, which carries the id and an `is_shown` flag and does not fire at all in this state. It is the *only* sound signal: the set answers a "what are you displaying" question with the art-store slot, unchanged by anything this product selects, so the obvious confirming *read* reports every real rotation as a failure and parks the wall on one picture (measured 2026-08-07, both directions). Because the announcement is pushed rather than polled, **asking and confirming are one operation** at the television seam — a listener registered after the request races an answer measured arriving in half a second. A selection that did not land is its own outcome rather than a failure to show one work: the pass ends instead of walking the theme, the place in the rotation is given back rather than consumed, a `show_now` is left unconsumed by the same rule an outage leaves it unconsumed, and nothing is recorded as having been on the wall. Said **once**, with the set's own art-mode flag in the line, and said again when it recovers. **Backed off from on the same ladder as an unreachable set** (5 s doubling to 300 s, reset on recovery), because the rotation timer governs rotation and nothing governed the directive path: an unconsumed `show_now` — which is the correct thing to leave behind — would otherwise be re-asked once per poll all night. The cost is that the wall resumes within the current wait of someone switching the set on rather than instantly, which is the same trade this plane already makes for a television that has gone away |
| E-paper write fails | label stale | Log and continue; never let a panel failure stop the TV rotation |
| Budget exhausted mid-run (the provider refuses — a 403; see `openrouter-api-findings.md`) | discovery halts partially | `halted_by_budget`, a modelled outcome. Already-acquired works stay acquired |
| Preview sweep stops running | **curation only, and silently** | The characteristic failure of the plane's one periodic job: no error, no refusal, and no symptom until the SD card fills. It is upstream of the row below, and the only signal is positive — `preview.swept` at INFO on **every** pass, including the ones that reclaim nothing, so absence over an interval is the fault. A pass that hangs instead of stopping is the neighbouring case and reads differently: `preview.sweep_started` with no `preview.swept`, and at shutdown a `preview.sweep_wedged` warning, because that pass holds the store lock the next generation of services will want |
| SD card full | **both planes** | The one genuinely shared failure. **Built 2026-08-03**: `acquisition/space.py` refuses before a fetch begins, sized by `MIN_FREE_BYTES` (2 GiB) and protecting `catalogue.sqlite` on the same device rather than the fetch. It raises rather than recording, because a full disk is a fact about the machine that every work behind this one would hit. **It is not the only one, and this row said it was until 2026-08-04.** The rule is general: a condition no source is at fault for raises, because a `failed` row against a source sends whoever reads it to the museum to look for a problem that is in the deployment. Three qualify today — a full disk, `dezoomify-rs` missing, and a provider with no tile resolver wired — and the next acquisition failure is judged against that rule rather than against this list, which is why the rule is stated here and the count is not |
| SD card corruption | catastrophic | The catalogue is the irreplaceable asset and it lives here. Mitigation is off-device backup — see `operational-spec.md` |

**Restart order does not exist**, and that is a property worth naming: neither
plane depends on the other being up, so systemd unit ordering between them is
unnecessary. Either can start first, in any order, at any time.

**No unbounded queues anywhere.** The only inter-plane buffer is a single file that
is overwritten, so backpressure is structurally impossible.

## Deployment & Version Skew

**One deploy unit in practice, two in principle.** Both planes live in one git
repo, are updated together (`git pull` plus two `systemctl restart`s), and there is
no scenario in which someone deliberately runs an old display against a new
curation.

**But skew still exists, and this is where a recorded contradiction gets
resolved.** `api-contract.md` exempts the curation↔display contract from stability
obligations as "single consumer, deployed together" — which the availability norm
contradicts, because deployed-together and survives-independently are not
compatible claims. The resolution is neither exemption nor a full compatibility
regime:

> **The manifest carries a schema version. Display refuses a manifest whose major
> version it does not recognise and keeps the one it has.**

That is a *small* obligation, and it is sized to the real risk. The two processes
restart independently even in a co-located deploy — there are seconds to minutes
during an upgrade where a new curation has written a manifest that an
old display is still reading, and a Pi that reboots mid-upgrade can extend that
window to "until someone notices". Without a version field the failure there is a
misparse rendering wrong art or a crash loop blanking the wall; with one it is a
logged refusal and yesterday's theme still on the wall.

**So the contract is not "no stability obligation".** It is: additive changes are
free, breaking changes bump the major version, and the display plane's response to
an unrecognised major is defined. `api-contract.md` now says exactly that
(amended 2026-07-20) — the blanket exemption is retired there too, so this
obligation reads as discharged, not outstanding.

**No data migration spans the planes**, because no data is shared — the manifest
is regenerated, never migrated. That half is unchanged and structural.

**Rollback stopped being `git checkout` plus two restarts on 2026-08-12**, and
the sentence said it for the whole life of the product before that. What changed
is *within* the curation plane: the walls migration drops `themes.is_active` and
the singleton `directive` table, and a previous release reopening that file hits
the durable store's widening step, which refuses a NOT NULL column it cannot
default. **The plane declines to start**, which is the good half — loud,
immediate, and before anything is served, where the alternative is a release
quietly reading a catalogue it does not understand. The missing half was the
record.

So a rollback **across a migration is a restore, not a checkout**: check out the
previous commit, put back the `catalogue.sqlite` copied before the deploy, then
restart both. **The backup is the rollback plan** — without one, rolling back
across this migration is not possible, and re-creating what the migration removed
by hand would reset the directive counter it was careful to carry. A rollback
that crosses no migration is still the old two-step. `operational-spec.md`
§ Routine Operations carries the operator-facing form.

## Scaling Model

Every component is a singleton and will remain one. Nothing scales horizontally,
nothing is replicated, and there is no load balancer, queue, or worker pool. This
is a recorded decision, not an oversight: the targets in
`nonfunctional-requirements.md` are one household, one TV, thousands of works
*(was "hundreds"; amended there 2026-08-10)*.

**The amendment does not weaken this paragraph, and the distinction is the whole
reason it survives unchanged.** Singletons are a decision about *load* — one
curator, one run at a time — and the amendment moved only *catalogue size*, which
no component's replication count answers. What a bigger catalogue does bite is
retrieval and the browser client, both above this layer.

**The known bottlenecks, in the order they will bite:**

1. **The SD card.** Write-heavy tile caching plus ~10 GB of artwork on consumer
   flash, hosting the one irreplaceable asset. First thing to fix if anything is
   fixed. Signal: free space, and filesystem errors in the journal.
2. **RAM during a gigapixel acquisition.** 8 GB is comfortable for the measured
   corpus (largest work 49 MP → ~148 MB loaded; colour work is downsized to 2048²
   first, ~100 MB). A genuine 1–2 gigapixel Google Arts & Culture scan is 20–40×
   that and is the one input that could exhaust the box. Signal: peak RSS of the
   curation unit. Mitigation if it bites: a cap on stored source resolution, which
   is an open acquisition-pipeline decision anyway.

   **The other memory path is a preview, and unlike an acquisition it is driven
   by a stranger.** A preview URL comes out of a museum's JSON response and the
   fetch follows redirects, so both its size and its final host are the
   provider's choice, and the bytes are held whole in RAM before anything
   reaches disk. That read is bounded at `PREVIEW_MAX_BYTES` and enforced while
   streaming, so the ceiling — not the box — is what an endless body costs. The
   unit's `MemoryMax` sits behind it and would contain the blast to "curation
   dies" rather than "the wall goes dark", which is worth stating because it
   made the unbounded read look survivable: a run lost to a thumbnail is still
   the tail wagging the dog.
3. **Nothing else.** SQLite at low thousands of rows, one concurrent user, and one
   discovery run at a time are not going to be problems and should not be designed
   for.

**Deliberately not scaled for:** multiple TVs, multiple display planes, multiple
households, concurrent discovery runs, and any form of high availability. These sit
in the product brief's *accommodate* list — designed around, not built.

## Cross-Cutting Runtime Concerns

**Correlation.** A discovery run id is the correlation key across the curation
plane and is carried in structured logs. It does **not** cross into display, and
should not: the manifest is a statement of current state, not a record of the run
that produced it. Display correlates on work id. Detail belongs to
`observability-strategy.md`.

**Time.** UTC everywhere internally; local time only at render (label dates, the
sun-position brightness loop, which is inherently local). One non-obvious
consequence already recorded: the OpenRouter key's spend limit resets at midnight
**UTC**, so the product's "month" is the UTC calendar month regardless of where the
curator lives.

**Configuration and secrets.** Environment variables with a `.env` file, per the
existing preference that deployment values never live in source. Each plane reads
its own config at start; a config change means a restart of that plane only.
**`ART_ROOT` is the one value that must agree across both planes** (corrected
2026-07-20 — this briefly said panel geometry was a second, on the mistaken
premise that display renders the mat). It remains the single most important thing
to get out of source, already scoped that way in the v1 list; a mismatch is a
silent failure, with curation writing manifests nobody reads.

**"Panel geometry" was one name for two different physical panels, and separating
them is what dissolves the shared-value problem** (2026-07-20):

- **The TV panel's physical geometry** (this deployment: 50", 16:9 — the worked
  examples elsewhere stay at 42" deliberately, as arithmetic demonstrations) is
  **curation's alone**. The mat is specified in physical inches and the resolution
  floor is a minimum size on the wall, so curation needs it to judge a source, to
  show the curator what a work would look like, and to compose the mat into the
  `tv_display` rendition. Display receives that rendition already composed and
  never needs the TV's size.
- **The e-paper panel's geometry** (1448×1072) is **display's alone**, for label
  typesetting. Curation never needs it.

Neither is shared, so neither can drift between planes — the quiet-mismatch risk
this section previously described for panel geometry does not exist once the two
are named apart. **Nothing may hardcode either panel's size**: the product must run
on whatever Frame someone owns. See `operational-spec.md` § Configuration.

API keys are curation-only; display holds no credentials except the TV pairing
token, which is device state and lives with display.

**Environment parity — the honest gap.** Curation runs unmodified on a developer
Mac: it is a FastAPI app over a filesystem and an HTTP client. Display does not,
and cannot — it needs SPI hardware and a TV on the LAN. The parity story is
therefore asymmetric and should be admitted rather than papered over: curation is
developed locally against a real ART_ROOT, display is developed on the Pi, and the
two device interfaces (TV, e-paper) are the two things that cannot be meaningfully
faked end-to-end. This is already recorded as the reason "verify the TV still
works" is a gating item rather than a routine test.

## Decision Log

**2026-07-27 — The catalogue's durable tier is first-party code shaped to the
`DurableStore` contract, and no framework dependency is taken.** The recorded plan
was to adopt the operator's three-tier framework for the catalogue. Reading it
before building against it retired the plan's target configuration and its stated
reason at once: its L1 tier is a *named in-memory* database, so an "L1-only SQLite"
catalogue persists nothing across a restart; it ships no SQLite durable backend, so
the tier that actually persists is this product's own code under every
configuration; and its collections are async throughout with no query API, which
would convert three layers to async against the ratified "async at the I/O
boundary, synchronous core". *Trade-off accepted:* the compatibility is structural
rather than enforced — nothing fails if the foreign protocol changes, and the
divergences (sync methods, no `conn` handle, no `cas` fence) are enumerated in
`persistence/durable.py` rather than asserted as parity. *Consequence:* the
"on-ramp to the framework's agents" rationale is retired and must not be cited;
`3tears-models` depends on neither this contract nor that framework's core.

**2026-07-20 — Both planes run on the Raspberry Pi, sharing a data directory.**
Reverses the recorded plan that curation would run on a desktop, NAS, or second Pi.
Operator's call. The image-processing rationale for offloading was checked and does
not hold: the existing code downsizes to 2048² before colour work, so peak memory
is a few hundred MB against 8 GB. Co-location removes the split's cost (network
contract, sync, two deployments) while keeping its benefit (independent restart).
*Trade-off accepted:* one hardware failure domain, and the curation process now
competes for the Pi's resources with the display daemon. *Consequence:* the
"moves work off a Pi 4" rationale is retired and must not be cited anywhere.

**2026-07-20 — The theme manifest file is the only inter-plane channel.**
Alternatives: a full local mirror on the Pi (rejected — a sync problem with a
conflict story, and nothing asks the Pi to make curatorial decisions); the display
plane polling curation over HTTP with a cache fallback (rejected — makes display a
client of curation, so the norm is satisfied only by a fallback path that is never
exercised until it matters). *Trade-off accepted:* the display plane cannot switch
themes on its own.

**2026-07-20 — The e-paper label is rendered on the display plane.** Alternative:
render on curation alongside the 4K TV image. Rejected because it would put panel
geometry in the catalogue, which the ratified data-model norm forbids and whose
2024 incarnation (`label_file` named `_w648_h480`) is that norm's cited
anti-pattern. Text rendering is cheap; it was gigapixel compositing that did not
belong on a Pi. *Secondary benefit:* keeps the PyGObject/Pango/cairo system stack
off the curation venv, where `pycairo` has no aarch64 wheel and would need a source
build.

**2026-07-20 — FastAPI serves the curation plane.** Alternatives: Starlette
directly (rejected — hand-written validation for an API recorded as needing typed,
paginated, partial data, and validation logic tends to leak into handlers, which
the service-layer norm forbids); `FastMCP.custom_route` alone (rejected — a minimal
API at lowest route precedence, making the UI surface a second-class citizen of the
MCP server rather than a peer). Neither of the operator's production MCP servers is
a precedent — hallucinote is stdio-only, cordyceps is C# on a hand-rolled
`HttpListener` — so this was decided on merits rather than inherited.

> **Integration hazard, recorded because it is silent and non-obvious.** Starlette
> does **not** run a mounted sub-app's lifespan. `Mount("/mcp",
> app=mcp.streamable_http_app())` therefore fails *every* request with
> `RuntimeError: Task group is not initialized` unless the host application enters
> `session_manager.run()` in its own lifespan
> (`mcp/server/streamable_http_manager.py:143-144`). Two related constraints:
> `session_manager` raises if touched before `streamable_http_app()` has been
> called, and `.run()` may be entered only once per instance. The SDK names this
> exact use case as supported (`fastmcp/server.py:263-265`), but the failure mode
> for getting it wrong is total and gives no hint about lifespans.

> **Re-verified 2026-07-27 against the installed SDK, mcp 1.28.1** (the pin had
> moved from the 1.27 this was written against). All three constraints hold
> verbatim: `handle_request` raises `RuntimeError("Task group is not
> initialized. Make sure to use run().")` when `_task_group is None`
> (`streamable_http_manager.py:159-160`); `run()` guards re-entry with
> `_has_started` under a lock; `FastMCP.session_manager` raises unless
> `streamable_http_app()` has been called. The one addition: `streamable_http_app()`
> sets its *own* Starlette lifespan to `self.session_manager.run()`
> (`fastmcp/server.py:1044`), which is precisely why mounting that app under a
> host is silent — the correct lifespan exists, mounted where nothing runs it.

**2026-07-27 — The service layer stays the shared implementation; MCP is not
built as a client of the HTTP API.** Raised as a direct question: does `3tears`
offer an abstraction that makes shipping the API and the MCP surface one job?
Investigated against the checkout at `0e37d8b3`. **It does not** — no package
renders one declaration to both surfaces. `McpTool` is MCP-only and carries a
hand-written `input_schema`; `APIRouter`/`fastapi` appears twice in the whole
repo, in a scrape sidecar and a channels webhook test, with no shared route
layer.

What 3tears *does* have is a different answer to the same problem, and it was
weighed on merits: `PlatformHttpClient` exists so that **MCP tool handlers call
the product's own REST API** (`packages/mcp/.../http_client.py`, whose docstring
gives `list_conversations` delegating to `client.get("/api/v1/admin/conversations")`
as the worked case). Parity is real under that shape — but rejected here for
three reasons, in ascending order of weight: an in-process loopback hop and
double serialisation to reach code already in memory; `3tears-mcp` drags
`3tears-epoch` and `3tears-nats`, and its mandatory default-deny
`required_permission` is backed by a Postgres `mcp_tool_grants` table with
nothing in this single-principal product to gate. **The decisive one is a
stability consequence not previously recorded anywhere:** `api-contract.md`
grants the HTTP API *no* stability obligation because it ships with its only
consumer, while the MCP surface carries a real external one. Building MCP on
top of HTTP would silently promote the UI's API to a frozen contract and make
every UI-driven shape change a breaking change on an external surface. The
service layer delivers the same single implementation one rung lower, where
neither surface constrains the other. *Trade-off accepted:* the two bindings
each format their own results, which is intended — tool results are shaped for
a model, HTTP responses for a UI.

*Scoped 2026-08-06, because this entry read as covering every projection and it
does not.* The rationale describes surfaces whose shapes genuinely **differ**, and
only the artwork pair actually does: `WorkOut` adds `fit` and `image` and drops
`accepted_at`/`created_at`, where `_artwork_fields` keeps the timestamps and has
neither — two shapes for two readers, exactly as argued. Theme, Artist and the
candidate-work summary are not that. They are one shape written twice, key for
key, from the same record. `http/models.py` already forbids the consequence —
*"they are not allowed to differ in what a thing is called, because that is how an
agent and a click come to disagree about the same catalogue in a way no test would
catch"* — and until this date nothing enforced it.

They stay independently formatted rather than merged: the MCP side returns plain
dicts and the HTTP side pydantic models whose field docstrings are documentation,
so a shared formatter would cost one of those. What changed is that divergence is
now a test failure at the moment of the edit —
`curation/tests/unit/test_surface_parity.py`, which also asserts the artwork pair
still differs, since that divergence is this entry's only evidence.

**2026-07-20 — Readiness is manifest membership, not a stored flag.** Resolves the
open question by separating catalogue readiness (curation's, evaluated at
manifest-build time) from device readiness (display's, in its own store). Rejected:
a materialised `is_displayable` column (derived state that drifts when a recompute
is missed) and a readiness state machine on the work (machinery for a conjunction
that only one caller needs). *Obligation accepted:* the manifest build must report
its exclusions with reasons, or the design trades a loud failure for a silent one.

**2026-07-20 — The manifest is versioned; the co-location exemption is narrowed.**
Reverses `api-contract.md`'s blanket "no stability obligation, single consumer,
deployed together" for this one channel, which was in direct tension with the
availability norm. Independent restarts create a real skew window even on one host.

**Superseded — 2026-07-19's "the split moves image processing off a Pi 4".**
Retired by the co-location decision above. Retained here only so a future reader
who encounters the old phrasing in `learnings.md` or `project-state.yaml` knows it
was withdrawn deliberately.
