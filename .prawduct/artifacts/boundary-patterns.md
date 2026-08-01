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
  tool names are registered and served over streamable HTTP at `/mcp`;
  `art_catalogue` answers `list` / `get` / `help`, the other four answer `help`
  and return a teaching error for anything else.
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

- **Exists:** no.
- **Producer:** HTTP handlers on the curation plane.
- **Consumer:** the curation UI, and nothing else.
- **Contract:** response models. **No stability obligation** — shipped and deployed
  with its only consumer.

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

- **Exists:** no — designed 2026-07-20, not implemented.
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
  and startup reconciliation are enforced in the service layer. **Still to come:**
  the per-theme rotation settings, whose only reader is the manifest builder.
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
- **Contract:** **upstream artifacts** (`raw/`, `api-cache/`, `tile-cache/`) are
  expensive and device-independent and *are* transported; **derived artifacts**
  (`ready/`, `tv-thumbs/`) are cheap and device-specific and are
  **regenerated, never transported**. (`label/` removed from this row 2026-07-20
  — see the retirement bullet below.)
- All stored paths are relative to `ART_ROOT`. No absolute paths in any record.
- Candidate `preview_path` files are a third class — neither upstream nor derived;
  cheap, disposable, pre-acceptance. Their lifecycle **is** recorded in
  `data-model.md`: safe to delete once their `CandidateWork` reaches a terminal
  verdict, and deletion never touches the catalogue. **Open (narrowed
  2026-07-20):** only *what performs* that deletion — an on-verdict hook or a
  periodic sweep — is a build decision not yet made.
- **`label/` is retired from this prospective contract (recorded 2026-07-20).**
  Labels are rendered on the display plane from manifest label text; a rendered
  label is device state, so any cache of one lives display-side, never in
  `ART_ROOT`. Mentions of `label/` elsewhere describe the recovered 2024 layout,
  which had no display plane. `[DECISION: no label/ directory in the prospective
  ART_ROOT | label rendering moved to display 2026-07-20, and derived artifacts
  are regenerated not transported, so a curation-side label cache would have no
  writer | user can veto/override]`

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

Three of the four levels exist on the curation plane as of 2026-07-27. Two
suites run: `pytest` at the repo root for the 2024 modules, and
`cd curation && uv run pytest` for the plane.

| Level | Exists | When to Run | Location |
|-------|--------|-------------|----------|
| Unit | **yes** (curation) | Every change | `curation/tests/unit/`, mirroring module layout |
| Integration | **yes** (curation) | Changes crossing the service-layer boundary | `curation/tests/integration/` |
| Contract | **yes** (curation) | **Any MCP tool-surface change**, including a description edit | `curation/tests/contract/` |
| End-to-end | no | Before release | — |

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
