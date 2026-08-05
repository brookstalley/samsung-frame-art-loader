# Boundary Patterns — Samsung Frame Art Loader

<!-- Contract surfaces where components interact. When changes cross these
     boundaries, the builder investigates consumer impact before completing
     the chunk. The Critic verifies investigation occurred. -->

> **Status: three surfaces are real as of 2026-07-27**, the rest still
> prospective. The walking skeleton built the MCP tool surface, the service
> layer, and the catalogue schema end to end; the **Exists** column says which
> is which, per row. Everything below was written ahead of the code rather than
> left as a template, because an empty version of this file silently disarms the
> consumer-impact check for every future chunk — which is exactly what happened
> between 2026-07-19's two planning passes.

## Contract Surfaces

### MCP tool surface

- **Exists:** **yes**, as of 2026-07-27 — `curation/src/curation/mcp/`. All five
  tool names are registered and served over streamable HTTP at `/mcp`. **Four of
  the five now carry real actions**; only `art_review` still answers `help` alone
  and returns a teaching error for anything else. **Read this as a live external
  surface, not a placeholder:** an action added to any of the four is an addition
  to something clients already call.
  **`tools.py` is the roster, and this row deliberately no longer enumerates the
  actions.** It listed them until 2026-08-02 and was wrong by then — it still
  said `art_discovery` answered only `help` after two chunks had put eight real
  actions on it, which is precisely the "Exists: no" failure this file's preamble
  warns silently disarms the consumer-impact check. A count goes stale far more
  slowly than a list, and the list has one authoritative home.
- **Producer:** MCP tool bindings on the curation plane.
- **Consumer:** **External** — Claude Code, the in-UI agent, any MCP client.
- **Contract:** tool names, `action` values, argument schemas, and result shapes.
  Stability tiers and the additive-only evolution rules are in
  `api-contract.md` → Surface Inventory & Stability Tiers.
- **Crossing this boundary is the highest-consequence change in the product.** Tool
  names are frozen; action removal is breaking; and — non-obviously — **a
  description change counts as breaking**, because it alters tool-selection
  probability even when the schema is untouched.
- **Generated, not hand-maintained.** Definitions derive from one registry record
  per action. A change to a record propagates to the wire schema, validation, `help`
  output, and error messages together; editing any of those by hand is the
  violation. Records live in `curation/src/curation/mcp/tools.py`; the generators
  in `registry.py`. `tests/contract/test_mcp_surface.py` pins the five names,
  the 2 KB description budget, the annotations, and that every action in a
  schema's enum also appears in the prose — the drift check.

### HTTP API (curation UI)

- **Exists:** **yes, as of 2026-08-01.** This row read "no" until then,
  including in the bundle that built it — which mattered because an `Exists: no`
  row silently disarms the consumer-impact investigation this file exists to
  arm, and the discovery half of the browser surface extends exactly this one
  rather than standing up a second.
- **Producer:** the FastAPI app on the curation plane — `curation/src/curation/http/api.py`,
  with typed responses in `http/models.py`.
- **Consumer:** the curation UI, and nothing else — `http/static/app.js`, which
  binds concrete field names (`work.status`, `s.rights_status`,
  `s.last_fetch_status`, the heartbeat and backup fields, and on the review grid
  `shown_is_on_offer`, `preview_available`, `instances_held` and the verdict).
  **It is a real consumer**: a renamed field breaks the page with no test failing
  unless one is written for it.
- **What now fails when it breaks:** the browser suite executes the client
  against the real routes, so a rename that reaches a bound field is caught rather
  than merely likely to be. That is coverage of *executed* behaviour, not of every
  field — `tests/browser/`, marker `browser`, and `tools/mutation_sweep.py` is
  what says which behaviours are actually defended.
- **Contract:** response models. **No stability obligation** — shipped and deployed
  with its only consumer. That exemption is about *versioning*, not about
  changing fields blindly: producer and consumer ship together, so a rename is
  free only when both move in the same commit.

### Service layer

- **Exists:** **yes**, as of 2026-07-27 — `curation/src/curation/services/`, split
  by concern into `CatalogueService` (works already accepted), `DiscoveryService`
  (everything before acceptance) and, since 2026-07-31, `DisplayService` (themes,
  the standing directive, and the manifest built from them), bound by a `Services`
  container that every surface takes. Discovery and display each depend on the
  catalogue and neither is depended on by it. Later operations join one of the
  three, or add a fourth member.
- **Producer:** service methods.
- **Consumer:** **both** the MCP tool bindings and the HTTP handlers.
- **Contract:** method signatures and return types.
- **This is the boundary the product's central norm protects.** Operation logic
  lives here only; MCP tools and HTTP handlers are thin bindings
  (`project-preferences.md`, Critic-enforced). A handler that validates, orders, or
  decides is the violation. A change here crosses to *two* surfaces at once, which
  is the whole point — parity is structural rather than remembered.

### curation ↔ display contract

- **Exists:** **the producing half does**, as of 2026-07-31 — curation writes
  `theme-manifest.json` into `ART_ROOT` (schema major 1), atomically, with the
  rotation settings and directive block the design calls for. **The consuming
  half does not:** the display plane does not exist yet, so nothing reads this
  file yet. Curation also *reads* the reverse-direction heartbeat and reports
  honestly that none exists, which stays the true state until a display plane
  runs and writes one.
- **Producer:** curation plane. **Consumer:** display plane. **Same machine.**
- **Contract:** the **theme manifest** — a versioned JSON document written
  atomically (temp + `os.replace`) into the shared `ART_ROOT` and polled by display
  at ~1 s. It carries a schema version, the active theme, rotation settings
  (`rotation_interval_seconds`, `shuffle`), a directive block (`sequence`,
  optional `pinned_work_id`), and an ordered list of entries — work id, render
  path, and the label fields.
- **Stability obligation: bounded, not absent.** Additive changes are free; a
  breaking change bumps the major, and display refuses an unrecognised major and
  keeps the manifest it has. See `api-contract.md` → Surface Inventory.
- **Crosses a process boundary — not a machine boundary** (corrected 2026-07-20;
  both planes now run on the one Pi). The two planes do not share a database:
  `TvBinding` is display-plane state and references catalogue ids *by id only,
  never by foreign key* (`data-model.md` → Relationships).
- **This boundary is governed by a ratified norm.** The manifest is the *only*
  channel from curation to display (`architecture.md` § Direction). A change that
  adds a second one is a norm departure requiring a recorded decision, and issue #7
  files the plane-isolation test that enforces it.
- **The reverse direction exists and is narrow:** display writes a heartbeat/status
  file that curation reads. Sole writer is display; it never checks whether anyone
  read it, so it creates no dependency in the protected direction.

### Catalogue schema

- **Exists:** **yes**, as of 2026-07-27 — fourteen tables on stdlib `sqlite3` in
  one file, behind two Protocols in `curation/src/curation/persistence/`: the
  `CatalogueStore` over Artwork, Artist, Theme, Source, Original, Rendition,
  MatColor, ThemeMembership and the Directive singleton, and the `DiscoveryStore`
  over DiscoveryRun, CandidateWork, CandidateImage, SpendRecord and the
  ResolveRunWork join. A generic durable store sits under both adapters and is the
  only thing that opens the file, because acceptance writes across the two halves
  and has to commit once. All fifteen constraints, both discovery state machines
  and startup reconciliation are enforced in the service layer. The per-theme
  rotation settings landed with the manifest builder that reads them, and were the
  first change to a table that files on disk already carried — the durable store's
  column-widening step exists because of them. `work_dedup_key`'s derivation was
  decided by measurement on 2026-08-02; the column, the suppression that reads it
  and the caller that supplies the key were already in place, so **the change was
  to the value written, not to the surface** — which is why it crossed no boundary
  even though it altered every key. Changing it again against a catalogue holding
  `CandidateWork` rows *would* cross one, because stored keys would have to be
  recomputed: see `data-model.md` **Q3**. **That crossing happened on 2026-08-05,
  and what answers it is a mechanism rather than a one-off.** The citation rules
  gained the bare form, which changed the value written for seven rows already on
  disk; `DiscoveryService.reconcile` now re-cleans every stored title at startup
  and rewrites the key of any it changed, so the recompute is paid automatically
  by each later change instead of being owed by it. A future change to the
  derivation still crosses the boundary — it is the repair that is no longer
  each change's to write.
- **Producer:** the persistence layer. **Currently stdlib `sqlite3` behind a
  Protocol**, not 3tears collections — see the build plan's deferral note. The
  Protocol is what keeps that swap a one-module change.
- **Consumer:** services, and through them both external surfaces.
- **Contract:** entity fields, enums, and the Constraints list in `data-model.md`.
- **A persisted format is a lock-in decision.** The questions the data must answer
  (Q1–Q12) are its requirements; adding a consumer query is a schema change, not a
  read.

### `ART_ROOT` filesystem contract

- **Exists:** partially — the 2024 layout exists on the Pi; the split is recorded in
  `learnings.md` § Data and cache contract.
- **Producer:** acquisition and rendering. **Consumer:** both planes.
- **Contract:** **upstream artifacts** (`raw/`) are
  expensive and device-independent and *are* transported; **derived artifacts**
  (`ready/`, `thumbs/`, `tv-thumbs/`) are cheap and are **regenerated, never
  transported**. (`label/` removed from this row 2026-07-20 — see the retirement
  bullet below. `thumbs/` added 2026-08-01 — see the bullet below it.)
- **`tile-cache/` is neither, and `api-cache/` does not exist** *(corrected
  2026-08-03, when acquisition was built and the row's first list turned out to
  name one directory that is working space and one that has no producer)*.
  `tile-cache/` is transient working space for a fetch in progress: it holds the
  tiles of a **partial** download so a retry can resume, and it is removed per
  source as soon as that work holds a complete image. Transporting it would carry
  the debris of an interrupted fetch to another machine. `api-cache/` appears only
  in the 2024 `config.py`; the curation plane asks museums over HTTP and caches
  nothing on disk, so nothing produces it.
- All stored paths are relative to `ART_ROOT`. No absolute paths in any record.
- Candidate `preview_path` files are a third class — neither upstream nor derived;
  cheap, disposable, pre-acceptance. Their lifecycle **is** recorded in
  `data-model.md`: safe to delete once their `CandidateWork` reaches a terminal
  verdict, and deletion never touches the catalogue. **Settled 2026-08-03: a
  periodic sweep performs it, not an on-verdict hook.** `[DECISION: candidate
  previews are reclaimed by a periodic sweep over terminal-verdict CandidateWorks
  | a sweep derives what to delete from current state, so it is idempotent and a
  crashed pass costs a delay — where a hook that dies with the process leaks
  silently, and nothing afterwards is looking for a leaked preview | user can
  veto/override]` It runs on a daemon thread inside the application's lifespan,
  sweeping immediately at start and then on `PREVIEW_SWEEP_INTERVAL_SECONDS`
  (hourly by default, 0 to disable): a start-only sweep would reclaim nothing on
  an always-on plane, which is the deployment this exists for.
- **What it reclaims is bounded by the rows, and the shipped sweep is only half
  of what the decision above promised.** Every path it considers comes from a
  `CandidateImage.preview_path`, so a file written by a phase-2 run that died
  before recording its row is invisible to it — permanently, since nothing else
  ever looks at that directory. That is exactly the case a hook could not cover
  and the sweep was chosen to cover, so it is the half still owed rather than a
  limitation of the approach. Unbuilt and filed as issue #62; `operational-spec.md`
  § Add disk headroom names hand-deletion as the interim reclamation and states
  what it costs. **Not "re-fetchable" — nothing re-fetches a preview.**
  `PreviewCache.store` is called once, when phase 2 first records an instance, and
  a re-search does not restore the file either, because `record_image` returns the
  instance a work already holds for that URL without rewriting `preview_path`. A
  preview is disposable in the sense that losing one costs a picture rather than a
  record; it is not disposable in the sense of coming back.
- **The unit of deletion is the *path*, not the row**, because a preview file is
  named by a digest of its URL and two candidate works can therefore share one.
  A file survives while any work still under review references it. The producer
  of the sharing is ordinary — phase 1 naming one painting twice, phase 2
  resolving both to the same museum image — and deleting on the first work's
  verdict would take the picture out from under a work still being judged, which
  the review card would then report as a file it could not read.
- **`label/` is retired from this prospective contract (recorded 2026-07-20).**
  Labels are rendered on the display plane from manifest label text; a rendered
  label is device state, so any cache of one lives display-side, never in
  `ART_ROOT`. Mentions of `label/` elsewhere describe the recovered 2024 layout,
  which had no display plane. `[DECISION: no label/ directory in the prospective
  ART_ROOT | label rendering moved to display 2026-07-20, and derived artifacts
  are regenerated not transported, so a curation-side label cache would have no
  writer | user can veto/override]`
- **`thumbs/` joins the contract (added 2026-08-01), and it is deliberately not
  `tv-thumbs/`.** The browser surface serves downscaled copies of held works —
  the masters run to 47 megapixels and the television renditions are 4K, so a
  grid of the real files is not a page. Written by curation, read by curation,
  regenerated on whatever machine is serving. **`tv-thumbs/` was the obvious
  place and is the wrong one:** the 2024 tree uses it for images *downloaded
  from the television*, keyed by `tv_content_id`, which is per-device television
  state — the class this catalogue was redesigned to keep out, and the same
  reasoning that retired `label/`. It stays in the row above because the display
  plane may still want it; nothing in curation writes or reads it.
  `[DECISION: curation's thumbnail cache is thumbs/, not tv-thumbs/ | tv-thumbs/
  holds per-device TV state and reusing it would re-import the identity defect
  the catalogue was rebuilt to remove | user can veto/override]`
- Each derived directory is device-specific in a different way, which is worth
  stating because the row above reads as if they were alike: `ready/` and
  `tv-thumbs/` are specific to the *television*, while `thumbs/` is specific to
  nothing — a thumbnail is a thumbnail. It is regenerated rather than
  transported because it is cheap and disposable, not because it would be wrong
  elsewhere.

### Configuration

- **Exists:** **yes**, as of 2026-07-27 — every deployment value reads from `.env`
  in both planes. _(This read "partially, and badly — `config.py` hardcodes the TV
  address, art root, and coordinates"; the same bundle that wrote that hoisted all
  three.)_
- **Producer:** environment / config file. **Consumer:** both planes.
- **Contract:** no hardcoded deployment values in source. Now mechanically
  enforced rather than Critic-enforced:
  `tests/test_config.py::test_no_source_file_carries_a_deployment_value` fails on
  any of the hoisted values reappearing in a module.
- Values known to belong here: `ART_ROOT`, TV address, coordinates, the **phase-2
  approval work-count threshold** (added 2026-07-19 as a cost threshold; amended
  2026-07-20 to count — see `data-model.md`), and the **per-run search cap**
  (added 2026-07-20).
- **The LLM spend ceiling is deliberately *not* here** (struck 2026-07-20): the
  ratified norm is that spend ceilings are enforced by the provider, never by
  application code, so the ceiling is a setting on the OpenRouter key — not a
  value this product reads. Listing it as deployment config invited exactly the
  application-side enforcement the norm forbids. What the product *may* read is
  budget **remaining** (`GET /api/v1/key`), which is an observation, not a control.

## Test Levels

Every level below exists on the curation plane except end-to-end; the `Exists`
column is the authority, and it is per-row so that adding a level does not strand
a count in this sentence. Two
suites run: `uv run pytest tests` at the repo root for the 2024 modules, and
`cd curation && uv run pytest` for the plane. *(Corrected 2026-08-03: the root
command was written without `uv run`. Both planes need the prefix — the dev tools
are in a uv-only dependency group — and `CLAUDE.md` is the authority.)*

| Level | Exists | When to Run | Location |
|-------|--------|-------------|----------|
| Unit | **yes** (curation) | Every change | `curation/tests/unit/`, mirroring module layout |
| Integration | **yes** (curation) | Changes crossing the service-layer boundary | `curation/tests/integration/` |
| Contract | **yes** (curation) | **Any MCP tool-surface change**, including a description edit | `curation/tests/contract/` |
| Evaluation | **yes** (curation), opt-in | Any tool-surface change, before shipping it — **not** on every run | `curation/tests/eval/`, marker `llm_eval` |
| Live API — paid | **yes** (curation), opt-in | Any change to the OpenRouter client, and when a recorded price or response shape is in doubt | `curation/tests/live/`, marker `live_api` |
| Live API — free | **yes** (curation), opt-in | Any change to a museum client, and when a recorded response shape is in doubt | `curation/tests/live/`, marker **`live_museum`** |
| Live binary — free | **yes** (curation), opt-in | Any change to the dezoomify-rs wrapper, and when a recorded CLI behaviour is in doubt | `curation/tests/live/`, marker **`live_binary`** |
| Browser | **yes** (curation), opt-in | Any change to `app.js` | `curation/tests/browser/`, marker **`browser`** |
| End-to-end | no | Before release | — |

**The evaluation level is the only one that does not gate, and that is the
design** (added 2026-08-01). It drives the surface with a real model over
OpenRouter, so a run costs money and — the disqualifying property — can reach
the same goal by a different route next time. A non-deterministic pass/fail
either flakes or is loosened until it asserts nothing, so it is deselected by
default and run deliberately with `-m llm_eval`. It measures; the contract level
gates.

**The live-API level, added 2026-08-02, is deselected for the first reason and
not the second.** It spends money, but it is entirely deterministic: it asserts
the provider's response shapes and prices — inline `usage.cost`, the flat
per-request search fee, citations, the key's monthly ceiling, strict structured
output, and a real 403 halting a real run — so a failure means the provider
moved, not that a model chose differently. It is the durable form of
`openrouter-api-findings.md`, which is otherwise prose nobody re-runs.

**It split into two markers later the same day, and the split is the point.**
The museum suite (`artic-api-findings.md`'s durable form) is deselected for a
*third* reason — neither non-determinism nor cost, but that it needs the network,
which a suite whose job is to be green cannot depend on. It rode `live_api`
briefly, which meant its own instruction to run `-m live_api` would also run both
OpenRouter suites and spend real credit whenever a key was in the environment: a
file arguing at length that it was free, filed on the marker whose registered
description reads "Costs money". **A marker is what records the distinction; the
paragraph explaining it is not.** Anything added that talks to a free API goes on
`live_museum`.

Every opt-in level is off by default, and **the marker expression that does it
lives in `curation/pyproject.toml`'s `addopts` — read it there.** A copy used to
sit here reading `-m 'not llm_eval and not live_api and not live_museum'`, and it
was already wrong twice over: `live_binary` and `browser` had both been added to
the real one. A quoted config value is a second place for that config to be
wrong, and it drifts silently because nothing reads it.

**The evaluation level's dependency** is an opt-in group (`uv sync --group eval`)
rather than `dev`, because it is the heaviest install in the repo and no
first-party module imports it. Both eval modules therefore `importorskip` at
import time, not inside a fixture: a marker deselection still *collects* the
module, so a missing group has to skip rather than fail — otherwise the default
run breaks for everyone who took the default.

**The browser level, added 2026-08-05, is deselected for a fourth reason and
none of the first three.** It spends nothing, reaches no foreign API, and is
entirely deterministic. What it needs is a ~200MB browser on the machine, which
is too much to put on the default `uv sync` — so its deselection is a packaging
decision, not a statement about the tests, and `.github/workflows/browser.yml`
runs it on pull requests and on pushes to `main`, so that being off the default
run does not become never running. Its dependency is its own group for the same
reason the evaluation level's is, and its modules `importorskip` for the same
reason too.

**What it covers is the client, with `/api` as its boundary.** The other suites
assert what the API answers and take on trust that the page does something
sensible with it; that trust had been wrong three times, and none of the three
was visible to a test reading JSON. Where a real server can produce the state it
does — paging runs against a real catalogue and the real `truncated` flag — and
routes are stubbed only for states a server cannot be asked for deterministically,
such as a poll that changes nothing or each unresolved reason in turn. Stubbed
payloads are built from the API's own response models rather than hand-written
dicts, so a response that changes shape cannot leave these tests green against a
page that has started to break.

**Its acceptance was a mutation sweep, not a count of tests.** `tools/mutation_sweep.py`
drives `app.js` as readily as a Python file, and every behaviour this level claims
was demonstrated by deleting it and watching a test go red. That is what caught
the one test here whose fixture could not have failed: a run at the approval gate
re-checks its paint generation after fetching the estimate, so the check under
test was masked by the one after it, and only a run in a state with no second
fetch could falsify the claim.

**Within `tests/contract/`, two things now live side by side.** The surface
tests assert shape — names, schemas, descriptions, annotations, tips. The
scenario tests assert *navigation*: that the five consolidated tools compose
into real flows, with each step threading an id out of the previous step's
envelope. That threading is the point rather than a convenience — two tools can
each be correct in isolation and still disagree about the name of the thing they
hand each other, and that defect is invisible to both of their own tests.

**The contract level was built first**, as planned. The MCP surface is the only
one with external consumers, and it is the only place where a change that looks
cosmetic — rewording a description — is a real behavioural change. Both of the
operator's production MCP servers already do the narrow version of this: cordyceps
pins its tool names in an explicit test; hallucinote boots a real server and asserts
`list_tools()` output against its registry, including that prose and code cannot
drift. See `api-contract.md` → Validation.

**Both the contract and integration suites boot a real uvicorn server on an
ephemeral port and drive it with a real MCP client over HTTP.** That is not
ceremony. An in-process ASGI transport does not run the application's lifespan,
and the lifespan is the only thing making the mounted MCP server work — so a
test that skipped it would pass against an application that fails every request
in production.
