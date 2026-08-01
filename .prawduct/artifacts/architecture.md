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
                    │  └───────────┬──────────────┘   │   raw/ ready/ tv-thumbs/ │ │
                    │              │                  │   api-cache/ tile-cache/ │ │
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
   e-paper driver compiles Cython from 2023 sources targeting 3.12/3.13; the
   curation plane wants 3.14 for `3tears-models`, whose OpenRouter adapters the
   discovery work needs and which declares `>=3.14` like every package in that
   family. (Named specifically because the catalogue no longer takes `3tears`
   core — see `3tears-integration-findings.md`; the floor rests on the models
   package alone.) Two venvs on one host is the cheap resolution.
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
- **Internal layering, inside that plane** (established 2026-07-27):

  ```
  MCP tools  ·  HTTP handlers  ·  browser client   bindings: unpack, call one method, format
        └──────────────┬──────────────┘            (the client renders JSON and decides nothing)
                 Services container                what a surface is handed; no surface names one service
   ┌────────────┬──────┴───────┬────────────┐
  Discovery     │           Display      SurveyService   every rule, transition and derivation
  Service       │           Service           │          (all three hold CatalogueService;
        │       │              │        ThumbnailService   it holds none of them)
        │       └── CatalogueService ─────────┘
        │              │
  SqliteDiscovery  SqliteCatalogue                domain adapters: schema, record↔row, ordering
        └──────────────┬──────────────┘           and paging — the product judgements
              SqliteDurableStore                  generic: tables, keys, rows. Knows no artwork
  ```

  **Two services were added on 2026-08-01, with the first browser surface.**
  `ThumbnailService` produces the downscaled copies that make a forty-card grid a
  page, recording each as a `RenditionKind.THUMBNAIL` so the cache is catalogued
  rather than loose on disk and inherits the staleness rule already governing the
  television render. `SurveyService` composes a work with the two derived facts a
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

  Two patterns are load-bearing enough to name here rather than leave in module
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
- **Must never:** talk to the TV, talk to the e-paper panel, know the **e-paper
  panel's** geometry, or know TV content ids. Every device fact belongs to display.
  Note the TV panel's *physical* geometry is not a device fact in this sense and
  is curation's — see § Configuration; the two were conflated until 2026-07-20.

### display

- **Purpose:** make the physical world match the manifest.
- **Platform:** Python 3.13 venv, systemd `Restart=always`. Genuinely always-on.
- **Owned state (sole writer):** `display-state.sqlite` — TV content-id bindings,
  per-work upload status, last selected work, brightness state, and the
  last-acted-on directive sequence (see § The theme manifest). **Panel geometry
  is deliberately not listed** (corrected 2026-07-20 — it appeared here while
  every other artifact makes it *configuration* both planes read): a copy held as
  device state could drift from the value curation judges sources against, which
  is exactly the quiet mismatch `operational-spec.md` § Configuration warns
  about. Beyond `TvBinding`, this store's schema is display-internal and
  deliberately deferred (`data-model.md` § Deliberately not modelled).
  This is the ratified data-model norm ("per-device runtime state never lives in
  the catalogue") given a process to live in.
- **Reconciliation loop:** read manifest → ensure every listed work is uploaded to
  the TV → rotate through the list on a timer → on each `image_selected` callback,
  render and push the e-paper label.
- **Renders the e-paper label** (decided 2026-07-20 — see Decision Log). The
  **e-paper panel's** geometry (1448×1072) stays with the plane that owns that
  panel. Display does *not* render the mat — the mat is composed by curation into
  the `tv_display` rendition, so display never needs the TV's physical size.
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
  work id, the path to its prepared 4K render, and the label fields (title, artist,
  dates, medium, dimensions). Label *text* crosses; label *rendering* does not.
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

## Data Ownership & Consistency

**Single writer per store, with no exceptions and no shared tables.**

| Store | Sole writer | Readers |
|---|---|---|
| `catalogue.sqlite` | curation | curation |
| `theme-manifest.json` | curation | display |
| image tree (`raw/`, `ready/`, …) | curation | display |
| `display-state.sqlite` | display | display |
| `display-heartbeat.json` (heartbeat) | display | curation |

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
| E-paper write fails | label stale | Log and continue; never let a panel failure stop the TV rotation |
| Budget exhausted (402) mid-run | discovery halts partially | `halted_by_budget`, a modelled outcome. Already-acquired works stay acquired |
| SD card full | **both planes** | The one genuinely shared failure. Needs a free-space guard before acquisition, not a disk-full exception during it |
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

**Rollback** is `git checkout` plus two restarts. No data migration spans the
planes, because no data is shared — the manifest is regenerated, never migrated.

## Scaling Model

Every component is a singleton and will remain one. Nothing scales horizontally,
nothing is replicated, and there is no load balancer, queue, or worker pool. This
is a recorded decision, not an oversight: the targets in
`nonfunctional-requirements.md` are one household, one TV, hundreds of works.

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

- **The TV panel's physical geometry** (reference deployment: 42", 16:9) is
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
