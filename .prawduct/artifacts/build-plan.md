---
artifact: build-plan
version: 1
scope: v1-build
depends_on:
  - artifact: product-brief
  - artifact: data-model
  - artifact: architecture
  - artifact: api-contract
  - artifact: nonfunctional-requirements
  - artifact: security-model
  - artifact: operational-spec
  - artifact: observability-strategy
  - artifact: project-preferences
  - artifact: boundary-patterns
  - artifact: platform-and-dependency-findings
  - artifact: 3tears-integration-findings
governed_by:
  - artifact: architecture
    dispositions:
      - "the theme manifest file is the only channel from curation to display → conforms: every display chunk reads the manifest and image tree only; interactive commands ride the manifest's directive block (the recorded R-17 decision); issue #7's plane-isolation test lands in Chunk 11 and enforces it mechanically"
      - "operation logic lives only in the service layer; MCP tools and HTTP handlers are thin bindings → conforms: Chunk 07 establishes the registry/handler split as a directory boundary before any tool exists, and every later surface chunk binds service methods only; registry generation carries no per-tool logic"
  - artifact: nonfunctional-requirements
    dispositions:
      - "spend ceilings are enforced by the provider, never by application code → conforms: no chunk builds an application-side ceiling; `halted_by_budget` derives from a provider 402 (Chunk 14) and budget-remaining reads `GET /api/v1/key`. The per-run search cap (also Chunk 14) is budgeting inside the norm's recorded scope note, not a ceiling"
      - "the display plane's ability to show art never depends on the curation plane being reachable → conforms: the display daemon (Chunks 12–13) reads only the manifest, the image tree, and its own store; no network call to curation exists anywhere in the display package, and the plane-isolation test guards it"
  - artifact: data-model
    dispositions:
      - "identity is never a source URL → conforms: Artwork identity is a UUID from Chunk 07 on; source URLs live on Source/CandidateImage rows only"
      - "a work is distinct from an image of it, at every stage → conforms: CandidateWork/CandidateImage land as separate entities in Chunk 08, before any discovery code exists; acceptance is promotion, not transformation (Chunk 17)"
      - "per-device runtime state never lives in the catalogue → conforms: TvBinding and the last-acted-on sequence live in `display-state.sqlite` (Chunk 12); labels render display-side (Chunk 13); each plane's own panel geometry is configuration, stored in neither catalogue nor device state (Chunks 02, 09, 12) — the TV panel's physical size is curation's, the e-paper panel's is display's; corrected 2026-07-20, they are not one shared value"
      - "derived artifacts are regenerated, never transported → conforms: renditions carry `source_content_hash` and regenerate on staleness (Chunk 18); backup excludes the image tree (Chunk 20); candidate previews get their recorded disposable lifecycle in Chunk 17"
  - artifact: project-preferences
    dispositions:
      - "norm-index rows (formatting, naming, imports, logging-not-print, type-annotate-on-touch, specific exceptions, no hardcoded deployment values, async-at-the-boundary, hardware behind an interface) → conforms: ruff lands in Chunk 06 and the mechanical rows migrate to lint rules as each row's Why already directs; until then the Critic carries them per the index"
      - "no test suite (known departure, blocking for medium+ work) → conforms: pytest is established in Chunk 02 alongside the first code that needs it, before any substantive build chunk, and every chunk ships tests alongside code"
      - "uv for both planes, each plane with its own interpreter and its own lock → conforms: Chunk 06, gated on Chunk 04's build verification. The mechanism was settled 2026-07-20 ahead of the chunk: two SIBLING uv projects, not a uv workspace — a workspace shares one lockfile and one resolved interpreter, and uv 0.11.8 refuses to lock members mixing >=3.14 and ==3.13.* at all. The decision's substance (per-plane interpreter + per-plane lock) is unchanged"
last_validated: 2026-07-20
---

# Build Plan — Samsung Frame Art Loader v1

## Requirements Confidence

**Level:** Medium

**Why:** The problem, success criteria, and scope are each statable in one sentence
and are recorded in `product-brief.md` with unusual depth — three review passes
(Critic cumulative, a requested checkpoint review, verify-resolutions) closed
2026-07-20 with zero findings. What keeps this at Medium is a small set of named
unknowns, each with a resolving chunk early in the sequence rather than a hope
attached. The spine is deliberately evidence-first for exactly this reason.

**Open assumptions / unknowns:**

- [ASSUMPTION: the IT8951 stack builds under uv's PEP 517 isolation on 3.13/aarch64 | HIGH impact | Chunk 04 proves or disproves it before any plane scaffolding exists; user can reorder]
- [ASSUMPTION: a samsungtvws target exists that carries LS03A/B/C/D support and a fixable `delete_list` | MED impact | Chunk 05's verify step answers it; the fallback (local confirm-deletion wrapper) is scoped in issue #3]
- [ASSUMPTION: the 2024 code keeps running the wall throughout the build; cutover to the new display plane happens at Chunk 13, and the legacy modules are deleted only at Chunk 20 | MED impact | user can override with an earlier or later cutover]
- [ASSUMPTION: the existing sun-position brightness behaviour (`local.py`) ports into the display daemon in v1 — it runs on the wall today, so dropping it would be a regression, but the v1 scope list does not name it | LOW impact | user can defer to Later]
- [ASSUMPTION: rotation timing is per-theme with a global fallback | LOW impact | carried from `data-model.md`; user can collapse to global]
- `work_dedup_key` derivation and the discovery search-engine default are **unknowns
  with scheduled spikes** (Chunk 15), not assumptions — nothing downstream of them is
  designed until they resolve.
- **One operator decision is pending and gates deployment paths:** issue #13
  (SD-card mitigation — USB/SSD storage vs SSD boot). Five minutes, needed before
  Chunk 03 bakes paths into deployment config.

**What would raise confidence:** Chunks 04, 05, and 15 — the two hardware/build
verifications and the two spikes. Each is cheap, early, and converts an assumption
into a recorded fact.

## Status

- [x] Chunk 01: Untrack the TV pairing token; drop the catalogue backups (issue #4)
- [x] Chunk 02: Deployment values out of source (issue #5) + `art.py` defect dispositions (issue #6)
- [ ] Chunk 03: Pi operational hardening and the vendor-risk answer (issues #15, #16, #13) — **needs hardware**
- [ ] Chunk 04: Verify the IT8951 build under uv PEP 517 isolation (issue #9) — **needs hardware**
- [ ] Chunk 05: Replace the samsungtvws pin, verified on hardware (issue #3) — **needs hardware**
- [x] Chunk 06: uv restructure (curation only), lint/test tooling — *display plane deferred, mat fixture deferred*
- [x] Chunk 07: Walking skeleton — catalogue core → service layer → MCP tool, end to end
- [ ] Chunk 08: Full catalogue schema, state machines, constraints, startup reconciliation
- [ ] Chunk 09: Manifest builder, themes, directives — `art_theme` and `art_display`
- [ ] Chunk 10: Seed the catalogue with the 41 existing works (v1 scope item)
- [ ] Chunk 11: Contract tests — MCP evaluation harness (issue #17) and plane isolation (issue #7)
- [ ] Chunk 12: Display daemon core — poll, rotate, TvBinding, directive semantics
- [ ] Chunk 13: E-paper label, heartbeat, systemd units — cutover to the new planes
- [ ] Chunk 14: Discovery phase 1 — intent to works, runs, cost visibility (issue #12)
- [ ] Chunk 15: Spikes — search-engine choice and `work_dedup_key` derivation (issue #18)
- [ ] Chunk 16: Discovery phase 2 — works to instances, resolve runs
- [ ] Chunk 17: Review and acceptance — `art_review`, thumbnails inline, promotion
- [ ] Chunk 18: Acquisition and preparation — fetch, metadata, mat engine, 4K render
- [ ] Chunk 19: Curation web UI and HTTP API
- [ ] Chunk 20: Backup/restore exercise (issue #14), ops close-out, legacy retirement

Context: Plan authored 2026-07-20. Chunks 01, 02 and 06 landed 2026-07-27 in one
pass; **Chunk 07 landed the same day**, took its `final` Critic round and the
follow-up `verify-resolutions` pass, and the architecture now runs end to end —
a real MCP client lists five tools over HTTP and reads a seeded catalogue.
**Next: the 3tears catalogue swap**, then **Chunk 08** (full schema, state
machines, constraints), which widens the three entities Chunk 07 proved into the
other twelve. The swap is sequenced first, at the operator's direction, so the
twelve new entities are written once against their final backend rather than
against stdlib `sqlite3` and then again.

Deviations from the plan as written, all deliberate:

- **Chunks 01–06 were collapsed into a single commit** rather than six governed
  cycles with a Critic round each. The plan's own ceremony was on track to cost
  more than the work; the operator called this, and it stands as the working rule
  for mechanical chunks. Contract-setting chunks (07, 08, 09, 14, 16) keep the
  full treatment.
- **No token rotation.** Chunk 01 specified untrack-then-re-pair at the hardware.
  The operator confirmed the leaked token is expired and useless, so untracking
  was the whole job and the hardware sitting was not needed.
- **`display/` was not created.** Chunk 06 specified both plane projects, but
  `display/` is not needed until Chunk 12 and its dependency set is exactly what
  Chunks 04–05 must verify on the Pi. Building it now would have meant guessing at
  pins that hardware will decide. `curation/` alone unblocks Chunk 07.
- **The mat regression fixture was not extracted.** It is consumed in Chunk 18;
  `all.json` stays tracked until then and remains the corpus. Extracting it now
  would have been inventory, not progress.
- **Chunks 03–05 are hardware-gated**, not skipped. They need the Pi and the TV:
  the journald cap, the IT8951 build under uv, and the samsungtvws target. None
  of them blocks Chunk 07. They want one sitting at the hardware.

Verified this pass, which retires the plan's largest curation-side unknown: the
**full 3.14 dependency set resolves and imports on CPython 3.14.4** — fastapi
0.140.6, mcp SDK, pydantic 2.13.4. The interpreter floor is real and it works.

### Chunk 07 as built (2026-07-27)

Delivered as specified; three things are worth carrying forward.

**The SDK constraints were re-verified, not assumed.** The plan wrote them
against `mcp>=1.27`; 1.28.1 is installed. All three hold verbatim — the
`RuntimeError` on an uninitialised task group, the once-per-instance `run()`,
and `session_manager` raising before `streamable_http_app()`. Recorded in
`architecture.md` § Decision Log with line references.

**One contract rule was retired rather than quietly broken.** "An unknown *tool*
stays a protocol error" is not implementable on the official SDK: its
`call_tool` handler wraps the registered function in an unconditional
`except Exception` and converts everything to a normal error result. Retirement
and substitute are recorded in `api-contract.md` § Error Model and
`project-state.yaml`.

**The `3tears` API/MCP question was investigated and answered no** (raised
mid-build). No package there renders one declaration to two surfaces; what it
has is the inverse architecture, MCP tool handlers as HTTP clients of the
product's own REST API. Rejected with the decisive reason recorded in
`architecture.md` § Decision Log: the HTTP API carries *no* stability
obligation while the MCP surface carries a real one, so building MCP on HTTP
would silently promote the UI's API to a frozen external contract.

**Deliberately not built, so nothing reads as missing:** the twelve other
entities and the fifteen write-time constraints (Chunk 08 — `Theme.is_active`
exists as a column with no exactly-one enforcement behind it); any HTTP API
beyond the placeholder page (Chunk 19); the `tests/preferences/` plane-isolation
test (Chunk 11, and there is no display plane to isolate yet).

**One Chunk 06 deliverable was found missing and landed here.** Both suites were
to be declared as `test_commands` in `project-state.yaml`; they were not, and the
omission appeared in no deviation note — so the evidence hook was silently
falling back to a default invocation that resolves neither plane. Declared now,
with `tests_dirs` spanning both trees.

**The Critic round (`final`, the keystone override) returned 0 blocking, 21
warnings, 9 notes.** Fourteen warnings were fixed in the same pass and verified
by a `verify-resolutions` delta review; six are routed to the backlog, named
here so none reads as forgotten: DNS-rebinding protection on `/mcp`, the
loopback-vs-overlay bind contradiction, the silent empty-install on a mistyped
`ART_ROOT`, the unbounded MCP session table, the MCP layer's direct import of
the persistence package, and a test for the waived broad-except path.

Four defects were found independently by two reviewers each, which is what
argued for fixing rather than routing them: the unknown-tool error's hint named
the server (not a callable tool), so a model following the one teaching element
that path has would make a second failing call; a one-sided range rendered "must
be between 0 and None"; `starlette` was imported but declared by no package; and
the catalogue filename disagreed with four artifacts, which would have pointed
Chunk 20's backup job at a file that does not exist. Two more were structural:
built-vs-unbuilt tool state was reconstructed from three unreconciled signals
across two modules, now a single import-time check that Chunks 08–19 will run
four more times; and raw `sqlite3` constraint text reached the wire, which the
write-heavy Chunks 08 and 17 would have copied.

**The verify pass caught a defect introduced by the fix round itself** — the
rewritten linting norm claimed a strictness the ruff configs do not have, which
is the shape that gets "fixed" by loosening the config to match the artifact.
Corrected against both files as they actually are.

### The 3tears catalogue dependency is deferred, not dropped (2026-07-27)

The plan says the catalogue sits on "3tears L1 SQLite". Investigating that
turned up two defects that made it unusable as written, both now fixed upstream
and awaiting review:

- **[pacepace/3tears#243]** — `uuid-utils` is imported by `collections/registry.py`
  and `cache/sqlite.py` but declared by no package. It resolves inside the 3tears
  workspace via the shared lock, so `from threetears.core.collections import
  BaseCollection` fails for *every* external consumer.
- **[pacepace/3tears#244]** — `threetears.nats.__init__` eagerly imported the nine
  submodules that reach `nats-py`/`nkeys`, so an L1-only consumer loaded the whole
  NATS client. Decisive for this product: **`nkeys` publishes no wheels**, so the
  Pi would source-build it while every other package in the set has a prebuilt
  aarch64/cp314 wheel. Now lazy (PEP 562) with `nats-py` behind a `[client]` extra;
  the Pi target resolves to 20 packages, all wheels, zero builds.

**Chunk 07 does not wait on either.** The catalogue is built behind a persistence
Protocol on stdlib `sqlite3` — the plan already requires that persistence is
reached only through the service layer, so the backend is a swap rather than a
rewrite. Everything Chunk 07 actually proves (service layer, registry, MCP tool,
error envelope) is identical under either backend.

**When the PRs merge**, pin a released `3tears` version and implement the
Protocol against `BaseCollection`. Do *not* take a path dependency on the local
`~/source/3tears` checkout — it tracks whatever branch is checked out and cannot
build on the Pi.

An open question the swap must answer: `BaseCollection` is a three-tier cache
whose value is multi-process coherence, which `product-brief.md` § Scope rules
out ("one household, one TV, one curation process"). The reason to adopt it
anyway is the operator's — it is the on-ramp to agents later. That is a real
reason, and it is a decision to make with the Protocol in hand rather than
before.

## Scaffolding

### Project Initialization

Chunks 01–05 run against the repo as it stands (flat 2024 modules; pytest is
bootstrapped at the root in Chunk 02). Chunk 06 restructures:

- `uv python install 3.14` on the Pi (curation interpreter; prebuilt
  `cpython-3.14-linux-aarch64-gnu`, verified available — `operational-spec.md`).
- Two plane projects, `curation/` and `display/`, each with its own
  `pyproject.toml`, its own interpreter pin (3.14 / 3.13), and its own lockfile.
  The 2024 modules stay at the repo root, untouched and running production, until
  Chunk 13's cutover; they are deleted in Chunk 20.

### Dependencies

Rationale per package lives in `project-preferences.md` § Tooling,
`3tears-integration-findings.md`, and `platform-and-dependency-findings.md`.

- **curation (3.14):** fastapi, uvicorn, `mcp>=1.27` (official SDK — decided over
  `3tears-mcp`, which drags NATS), 3tears core (L1 SQLite only) + 3tears-models
  (OpenRouter adapters), httpx, pillow, opencv-python-headless, scikit-image,
  numpy, pydantic, python-dotenv. All wheels on aarch64/3.14, verified 2026-07-20.
- **display (3.13, system interpreter):** samsungtvws (target decided in Chunk 05),
  pillow, IT8951 (pinned per Chunk 04's outcome), omni-epd, pycairo + PyGObject
  (Pango label typesetting; the GTK stack lives on this plane deliberately),
  RPi.GPIO/spidev, python-dotenv.
- **dev (both):** pytest, ruff, black (line-length 130 carried forward).
- **External binary:** dezoomify (tiled fetch), configured not vendored.

### Build & Test Configuration

Per-plane `uv run pytest` from each project; `tests/` mirrors module layout
(`project-preferences.md` § Testing). Contract tests live in `tests/contract/`,
the norm-enforcement test in `tests/preferences/`
(`boundary-patterns.md` § Test Levels). Chunk 06 declares both suites as
`test_commands` in `project-state.yaml` so the test-evidence hook runs the real
invocations. Ruff configured at the root; the mechanical norm-index rows migrate
from Critic to lint rules as Chunk 06 lands them.

### Scaffold Verification

After Chunk 06: both plane venvs resolve from their lockfiles (display's on the
Pi — this is what Chunk 04 de-risks); `uv run pytest` green in both; black and
ruff run clean. After Chunk 07: a placeholder page answers on the curation port
and a real MCP client lists the five tools.

### Verification Strategy

Beyond tests, each chunk is verified the way its consumers experience it:

- **Curation** is exercised through a real MCP client (the Chunk 11 harness, and
  Claude Code by hand) and, later, the browser. Development is on the dev Mac
  against a real `ART_ROOT` — the recorded parity asymmetry
  (`architecture.md` § Cross-Cutting).
- **Display** is verified only on the Pi against the live TV and panel — the two
  interfaces that cannot be meaningfully faked
  (`design_decisions.infrastructure_dependencies`). Every display chunk ends with
  a hardware pass: art on the wall, label matching, journal clean.
- **Mat quality** is judged by the operator side-by-side against the 2024 corpus
  (Chunk 18's visual-change entry) — the bar is subjective and the 41 hand-tuned
  mats are the regression corpus.
- **The restore path is exercised, not described** (Chunk 20), restoring the
  catalogue onto a scratch directory and watching the system self-heal visibly.

## Project Structure

```
samsung-frame-art-loader/
├── curation/                  # Python 3.14 plane (Chunk 06)
│   ├── pyproject.toml         #   own interpreter pin + lock
│   └── src/curation/
│       ├── services/          #   the ONLY home for operation logic
│       ├── persistence/       #   3tears L1 collections, catalogue schema
│       ├── mcp/               #   registry records + thin tool bindings
│       ├── http/              #   thin HTTP handlers (Chunk 19)
│       ├── discovery/         #   phase 1 / phase 2 engines
│       ├── acquisition/       #   fetch, prepare, mat engine
│       └── manifest/          #   manifest builder + exclusion reporting
├── display/                   # Python 3.13 plane (Chunk 06)
│   ├── pyproject.toml
│   └── src/display/
│       ├── daemon.py          #   poll → reconcile → rotate loop
│       ├── tv/                #   samsungtvws behind an interface
│       ├── panel/             #   e-paper + Pango label behind an interface
│       └── state/             #   display-state.sqlite (TvBinding, sequence)
├── tests/                     # bootstrapped Chunk 02; split per-plane in 06
├── deploy/                    # systemd units, journald drop-in, README
└── (2024 modules at root)     # production until Chunk 13; deleted in Chunk 20
```

### Module Boundaries

Three boundaries carry ratified norms and are restated here because every chunk
touches at least one: **handlers and tools never contain operation logic** (the
registry record is declarative; the service method does the work); **display
imports no curation code and opens no channel to the curation process** (manifest
and image tree only, enforced by `tests/preferences/test_plane_isolation.py` from
Chunk 11 on); **hardware sits behind interfaces** (the TV client and panel driver
are swappable modules, so a frozen 2023 driver never again dictates an
interpreter). Persistence is reached only through the service layer.

## Build Chunks

**Groundwork — evidence first, at the hardware (Chunks 01–05).** These precede
the walking skeleton deliberately: they close the live credential leak first of
all, then retire the two build-blocking unknowns on real hardware. The
architecture-proving slice is Chunk 07.

### Chunk 01: Untrack and rotate the TV pairing token; drop the catalogue backups (issue #4)

- **Description:** Close the live credential leak in the public repo, in the
  corrected order: untrack first, then re-pair — the reverse order commits the
  fresh token (`security-model.md` § Credentials). One sitting, at the hardware,
  because the untracking commit deletes `token_file` on the Pi's next `git pull`
  and TV auth is down until re-pairing. Also drops the three `all.json` backup
  snapshots. `all.json` itself stays tracked — it is the mat regression corpus
  until Chunk 06 extracts the fixture.
- **Depends on:** none (hardware access required)
- **Artifacts consumed:** `security-model.md` § Credentials and Secrets,
  issue #4
- **Deliverables:** `token_file`, `all.backup`, `all.json.backup`,
  `all.json.backup2` untracked (`--cached` only) and gitignored; TV re-paired so
  the published token no longer authenticates; the history-rewrite decision
  recorded explicitly (recommendation: no — rotation kills the credential, and a
  public-repo force-push buys nothing further)
- **Tests:** none (repo-state change); verification is behavioural
- **Acceptance criteria:** all four files absent from `git ls-files`, present in
  the working tree; display connects to the TV on real hardware with the fresh
  token; `git status` clean afterwards
- **Type:** cleanup
- **Done when:**
  1. Acceptance criteria met on the Pi
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

### Chunk 02: Deployment values out of source (issue #5) + `art.py` defect dispositions (issue #6)

- **Description:** Hoist the three classes of hardcoded deployment value onto the
  existing dotenv path — `ART_ROOT` first (fail fast, no default), then
  `TV_ADDRESS`/`TV_PORT` (single source; `remote_test.py` stops carrying its own
  literal), then coordinates + location name. Fix the CWD-dependent relative
  paths (`upload_list_path`, the bare `token_file`) while in there. This touches
  the legacy modules that still run the wall, so it also discharges issue #6's
  triage: **dispositions recorded by this plan** — defect 1 (`art.py:366`
  `raise e` on an unbound name) is fixed here, one line, because it degrades
  diagnosis today; defects 2 and 3 (shared mutable list state, discarded
  None-filter) die with the ArtSet/metadata replacement in Chunks 08 and 18 and
  are not fixed in legacy code; defect 4 (`art_label.py`, dead and broken) is
  deleted in Chunk 06 after confirming no out-of-tree importer.
- **Depends on:** Chunk 01 (the token path work lands on an untracked file)
- **Artifacts consumed:** issue #5, issue #6, `project-preferences.md` § Known
  departures, `operational-spec.md` § Configuration
- **Deliverables:** `config.py` reads `ART_ROOT`, TV address/port, and location
  from the environment; `.env.example` extended in the existing style; README
  dev-setup section (a fresh clone runs without touching source); `art.py:366`
  bare `raise`; issue #6 updated with the four dispositions; **the repo's first
  `tests/` — pytest config at the root**, carrying this chunk's config tests.
  It lands here because this is the first chunk that produces code to test, and
  the no-test-suite departure must close before any substantive chunk; Chunk 06
  splits the suite per plane
- **Carried finding:** "no secret may ever reach a log line" is stated forcefully
  in two artifacts but has no mechanism, no norm-index row, and no chunk — while
  `operational-spec.md` mandates logging resolved config at startup, which is
  exactly where a secret would leak. This chunk writes that startup logging, so
  it owns the redaction helper and the norm-index row that makes it enforceable.
- **Tests:** unit — config loading fails fast with a clear message naming `.env`
  when `ART_ROOT` is missing; no configured secret appears in the startup log
  line (assert on the emitted record, with a secret deliberately set)
- **Acceptance criteria:** the code runs on the dev Mac and the Pi with no source
  edit, only `.env` differences; a missing `ART_ROOT` fails at import with an
  actionable message
- **Done when:**
  1. Acceptance criteria met and tests pass; verified on both machines
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

### Chunk 03: Pi operational hardening and the vendor-risk answer (issues #15, #16, #13)

- **Description:** Three small deployment items done in one hardware sitting.
  Set `SystemMaxUse=` explicitly (journald's default scales with the disk it is
  supposed to protect) and carry it in the repo's deploy config, not only on the
  box. Establish on the actual TV whether firmware auto-update can be disabled —
  the vendor has removed art mode by firmware before — and record the finding in
  its three homes (`security-model.md` § Open, `operational-spec.md` § Risks,
  `project-state.yaml` risk factor). Capture the operator's issue #13 decision
  (USB/SSD storage vs SSD boot) and update `operational-spec.md` § Risks so the
  top risk reads mitigated-by-decision; the chosen medium determines the paths
  later chunks bake into deployment.
- **Depends on:** operator decision on issue #13 (blocking for this chunk only)
- **Artifacts consumed:** `operational-spec.md` § Risks, issues #13/#15/#16
- **Deliverables:** new `deploy/journald.conf.d/` drop-in (applied on the Pi);
  auto-update finding recorded in all three named homes and the disable/keep
  decision recorded with its trade-off; #13 decision recorded with alternatives
- **Tests:** none (config + recorded findings)
- **Acceptance criteria:** `journalctl` reflects the explicit cap on the Pi;
  neither risk in `operational-spec.md` § Risks still reads "undecided"
- **Type:** doc-only
- **Done when:**
  1. Acceptance criteria met on the Pi
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

### Chunk 04: Verify the IT8951 build under uv PEP 517 isolation (issue #9)

- **Description:** The uv-for-both-planes decision carries exactly one named
  verification item and this is it: a 2023-era `setup.py` that imports Cython at
  module scope but does not declare it in build-requires fails under PEP 517
  isolation before a single `.pyx` is touched. Prove or disprove empirically on
  the Pi — read the pinned source first (cheap, may answer outright), then a
  throwaway uv project pinning `9f13613`, **not** the real display project. The same
  live install also answers the adjacent-but-distinct interpreter risk (the stack
  last proved on 3.12; 3.13 is an open assumption). If it fails, decide the
  remediation (declare build-requires via an override, vendor the ~1,500 lines,
  or pin differently) and record it as a decision.
- **Depends on:** none (hardware access)
- **Artifacts consumed:** issue #9,
  `platform-and-dependency-findings.md` (both existing IT8951 risks),
  `project-preferences.md` § Language & Runtime
- **Foreign API:** IT8951 (frozen 2023 source build)
- **Deliverables:** outcome recorded in `platform-and-dependency-findings.md`
  alongside the interpreter-version risk, keeping the two distinct; remediation
  decision if needed; issue #9 closed via `/prawduct:backlog`
- **Tests:** the spike **is** the test — a real install on the real target
- **Acceptance criteria:** a definitive recorded answer: the display plane's
  dependency set installs under uv on the Pi (3.13, falling back 3.12), or a
  chosen remediation makes it install
- **Done when:**
  0. verify-api — read `setup.py`/`pyproject.toml` at the pinned commit; capture
     what `[build-system] requires` declares (or that no `pyproject.toml` exists)
  1. Acceptance criteria met; findings recorded
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

### Chunk 05: Replace the samsungtvws pin, verified on hardware (issue #3)

- **Description:** The display plane's rotation design binds to this library's
  verified behaviour, so the pin moves before that plane is built. Select the
  target with evidence, not by default: confirm the PyPI release carries the
  fork's LS03A/B/C/D support before preferring it; check whether async
  `delete_list`'s missing `return` — the library's only removal verb, currently
  unconfirmable — is fixed on the target, and if not, add the local
  confirm-deletion wrapper (or upstream PR) issue #3 scopes. Confirm `upload()`
  chunks with a timeout rather than buffering whole 4K files, and re-confirm the
  dual-callback registration, whose failure modes are asymmetric across TV
  generations.
- **Depends on:** Chunk 01 (fresh pairing token in place)
- **Artifacts consumed:** issue #3, `data-model.md` § Rotation is host-driven,
  `project-state.yaml` → `classification.foreign_apis`
- **Foreign API:** samsungtvws
- **Deliverables:** the pin replaced in `requirements.txt` (the legacy install
  keeps running production; Chunk 06 carries the same target into the display
  project); confirm-deletion wrapper if upstream is still broken; verification
  notes recorded on issue #3
- **Tests:** a scripted hardware pass against the live TV — upload, select,
  confirmed delete, callback registration — captured as notes now, promoted into
  the display plane's test suite in Chunk 12
- **Acceptance criteria:** issue #3's five acceptance boxes checked, including
  real-hardware verification, not just a green install
- **Done when:**
  0. verify-api — read the candidate target's source for `delete_list`,
     `upload()` chunking/timeout, and LS03 support before selecting it
  1. Acceptance criteria met on the Pi
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

**Foundation (Chunks 06–10).** The planes get their structure, then a thin slice
proves the architecture, then the catalogue and the manifest land in full and
the existing 41 works are seeded into them.

### Chunk 06: uv two-plane restructure, lint/test tooling, mat regression fixture (issue #11)

- **Description:** Restructure onto the decided shape: `curation/` (3.14,
  uv-managed standalone) and `display/` (3.13, system interpreter), each with its
  own pyproject, interpreter pin, and lockfile. **Two sibling projects, not a uv
  workspace** — settled with evidence 2026-07-20, see the governed_by note; the
  chunk builds the decided shape rather than rediscovering it. Wire pytest per plane, adopt ruff (the
  mechanical norm-index rows migrate to lint rules), carry black's line-length
  130, give each plane its own `target-version` (retiring the single `py312`
  departure). Extract the mat regression fixture from `all.json` — all 41 works
  with their hand-tuned mat colours and what a re-render needs — and point
  `nonfunctional-requirements.md` § Output Quality at the fixture as the corpus's
  canonical record. Delete `art_label.py` (issue #6 defect 4) after confirming no
  out-of-tree importer on the Pi. Rename the recovered `r` freeze to say what it
  is (evidence, not scratch). Legacy modules stay at the root, running
  production, per the recorded assumption.
- **Depends on:** Chunk 04 (display's dependency set must be known to install
  under uv before the project is stood up), Chunk 05 (the samsungtvws target is
  what the display project pins)
- **Artifacts consumed:** `project-preferences.md` (Language & Runtime, Tooling,
  Enforcement), `operational-spec.md` § The Curation Interpreter, issue #11
- **Deliverables:** new `curation/pyproject.toml`, new `display/pyproject.toml`,
  per-plane lockfiles and venvs; ruff config with the migrated rules; new
  `tests/fixtures/mat_corpus.json` (name per what the comparison needs);
  `nonfunctional-requirements.md` § Output Quality repointed at the fixture and
  the `all.json` untrack-or-keep call recorded; `art_label.py` deleted; `r`
  renamed; `test_commands` declared in `project-state.yaml` for both planes
- **Tests:** fixture round-trip (41 works, every mat colour present); both plane
  suites runnable and green; ruff clean
- **Acceptance criteria:** both venvs resolve from their locks (display's on the
  Pi); `uv run pytest` green in both projects; the fixture is the corpus's
  canonical record per the amended artifact
- **Done when:**
  1. Acceptance criteria met and tests pass
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

### Chunk 07: Walking skeleton — catalogue core → service layer → MCP tool, end to end

- **Description:** The thin vertical slice through the entire curation
  architecture, proving the layers connect before anything widens: a minimal
  catalogue (Artwork, Artist, Theme on 3tears L1 SQLite) → a service layer that
  owns all logic → the registry → one generated tool (`art_catalogue`, actions
  `list`/`get`/`help`) served over streamable HTTP from the same ASGI app as a
  placeholder UI route. This chunk lands the project-wide concepts everything
  else binds to, so the surfaces are enumerated here deliberately: the registry
  record shape (description, params, example, tips — no logic), wire-schema
  generation, per-action validation, generated `help`, the error envelope
  (`isError` derived from `success`, errors that teach: what was wrong, the valid
  set, an example, a help pointer), mandatory tool annotations, and the
  ≤2KB-description budget. The known SDK hazard is handled, not discovered:
  Starlette does not run a mounted sub-app's lifespan, so the host app must enter
  `session_manager.run()` in its own lifespan or every `/mcp` request fails.
- **Depends on:** Chunk 06
- **Artifacts consumed:** `architecture.md` (§ Direction, § Decision Log — the
  FastAPI decision and the mount hazard), `api-contract.md` (§ The surface,
  § Argument shape, § Error Model, § Help), `data-model.md` (the three entities),
  `boundary-patterns.md` § Service layer
- **Exposed API:** mcp-tool-surface (versioning and error-model decisions
  recorded — `design_decisions.api_versioning_approach` /
  `api_error_model_approach`, both `status: active`)
- **Foreign API:** mcp Python SDK (`mcp>=1.27`)
- **Deliverables:** new `curation/src/curation/persistence/`, new
  `curation/src/curation/services/`, new `curation/src/curation/mcp/` (registry +
  bindings), the ASGI app with `/mcp` mounted and the lifespan wired, all five
  tool **names** registered from birth (names are frozen; actions grow additively
  per the contract — unbuilt tools carry only `help` and return a teaching error
  otherwise), a first contract test booting the real server and asserting
  `list_tools()` against the registry
- **Tests:** unit — service methods, registry generation, error envelope
  derivation; contract — server boots, five tool names pinned, descriptions
  under budget, annotations present; integration — a real MCP client calls
  `art_catalogue(action='list')` against a seeded catalogue
- **Acceptance criteria:** Claude Code (or the MCP inspector) pointed at the
  server lists the tools and reads the seeded works; the handler layer contains
  dispatch and formatting only
- **Critic mode:** final
  <!-- Keystone override: inference would pick `chunk` mid-plan, but every later
       surface builds on this slice's shape — worth the full review now. -->
- **Done when:**
  0. verify-api — re-confirm the mount/lifespan behaviour and
     `session_manager` constraints against the installed SDK version (they were
     verified from source at design time; the pin may have moved)
  1. Acceptance criteria met and tests pass
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

### Chunk 08: Full catalogue schema, state machines, constraints, startup reconciliation

- **Description:** The rest of `data-model.md`, faithfully: Source (with
  `source_class` as the load-bearing branch point), Original, Rendition
  (`tv_display`/`thumbnail` only — no `label` kind), MatColor with history,
  ThemeMembership, DiscoveryRun (both kinds, all nine statuses), CandidateWork,
  CandidateImage, SpendRecord (attribution only — it enforces nothing),
  ResolveRunWork. All fifteen constraints enforced at write time in the service
  layer, including the two-scope suppression rule (Q11) and the
  single-entry-point rule for `awaiting_better_image` (constraint 15). Startup
  reconciliation moves process-held runs (`resolving_works`, `resolving_images`)
  to `interrupted` — deliberately not `awaiting_approval`, which is human-held
  state that must survive a restart — releasing ResolveRunWork coverage and
  logging one WARNING per run moved, which is the only signal a run died.
- **Depends on:** Chunk 07
- **Artifacts consumed:** `data-model.md` in full (entities, relationships,
  state machines, constraints 1–15)
- **Carried finding:** the curation-side directive sequence counter is pinned as
  catalogue-side by `architecture.md` but has no modelled home, and a catalogue
  restore restores it — so it is part of the persisted format. Give it one here
  (a settings/singleton row or equivalent) rather than letting Chunk 09 invent it
  implicitly; `pinned_work_id`'s clearing rule is unstated and settles here too
- **Deliverables:** the full schema in `curation/src/curation/persistence/`,
  service-layer operations and transitions, reconciliation on startup,
  `display_fit` as the single service-layer derivation (never stored)
- **Tests:** unit per constraint (each of the fifteen has at least one test that
  fails without its enforcement); state-machine transition coverage including the
  illegal edges (`set_verdict` refusing `awaiting_better_image`, resolve runs
  never reaching phase-1 states); reconciliation — a seeded process-held run is
  moved, an `awaiting_approval` run is not, coverage is released
- **Acceptance criteria:** the schema answers Q1–Q12 from
  `data-model.md` § What this data must answer, demonstrated by a test per
  question
- **Done when:**
  1. Acceptance criteria met and tests pass
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

### Chunk 09: Manifest builder, themes, directives — `art_theme` and `art_display`

- **Description:** The inter-plane contract, curation side. The manifest builder
  is the one place catalogue readiness is evaluated; membership in the manifest
  IS readiness, and **the build reports its exclusions per work with reasons — a
  builder that only returns a list is an incomplete implementation of the
  design**. Atomic write (temp + `os.replace`), schema version, rotation
  settings, label fields, and the directive block with its three pinned
  semantics: the sequence is monotonic for the life of the catalogue
  (curation stores it catalogue-side; rebuilds carry it forward unchanged — only
  `next`/`show_now` increment), rapid directives coalesce latest-wins, and the
  display side's regression/persistence obligations are Chunk 12's. Full
  `art_theme` (create/update/delete/add/remove/reorder/activate) and
  `art_display` (sync/show_now/next; `status` reads the heartbeat file and
  reports honestly that none exists yet). The **TV panel's physical geometry**
  enters configuration here — curation's alone, since curation composes the mat —
  and is logged at startup.
- **Depends on:** Chunk 08
- **Carried finding:** archiving a work has no specified effect on manifest
  membership, and `security-model.md` bound 4 depends on it having one. Settle it
  here, where readiness is evaluated: an archived work leaves the manifest.
- **Artifacts consumed:** `architecture.md` (§ The theme manifest, § Readiness),
  `api-contract.md` § How `art_display` reaches the display plane,
  `boundary-patterns.md` § curation ↔ display contract,
  `operational-spec.md` § Configuration
- **Deliverables:** new `curation/src/curation/manifest/` (builder + exclusion
  report), theme services, the two tools' actions live, directive sequence
  persisted catalogue-side, panel-geometry config
- **Tests:** unit — exclusion reasons per unreadiness cause; atomicity (no
  reader ever observes a partial manifest); sequence carried unchanged through
  rebuild and theme switch, incremented only by directives; integration —
  `activate` produces a manifest whose entries are exactly the readiness-filtered
  theme
- **Acceptance criteria:** switching the active theme rewrites the manifest with
  zero TV writes implied; every excluded work is named with a reason in the
  build's report; directive actions return "the directive is written", never a
  claim the wall changed
- **Done when:**
  1. Acceptance criteria met and tests pass
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

### Chunk 10: Seed the catalogue with the 41 existing works (v1 scope item)

- **Description:** The v1 scope commits to a "new catalogue built through
  curation, seeded with the existing 41 artworks as worked examples"
  (`product-brief.md` § Scope, `data-model.md` — "the 41 legacy records are
  re-ingested through curation as new works"). This chunk owns it. Without it
  the new catalogue has no ready work by any built path until Chunk 18, and the
  display chunks below have nothing to put on the wall — which is why it sits
  here rather than late: **it is what makes Chunks 12–13's cutover acceptance
  executable.** Re-ingest, do not migrate: read `all.json` as an input file and
  mint fresh entities through the service layer, so every catalogue invariant
  from Chunk 08 applies to the seeded rows exactly as to discovered ones. **The corpus
  is complete on identity and incomplete on the label** — measured against the
  tracked `all.json` on 2026-07-20, not assumed: all 41 carry `title`, `artist`,
  `date_created`, `raw_file`, `mat_hexrgb`, and pixel dimensions, but **14 of 41
  have no nationality, 8 have no lifespan, 8 carry no `artist_details` at all,
  and 2 each lack medium and physical dimensions.** That shapes the work: Artist
  parsing cannot assume `artist_details` exists and must fall back to the flat
  `artist` field; the label must render legibly with nationality and dates absent
  (data-model Q9 wants them, so a partial label is a real outcome, not an error);
  and the 2 works without physical dimensions can get neither mat geometry nor a
  floor classification — they seed with dimensions null and are reported, which is
  the same unknown-dimensions case `data-model.md`'s `display_fit` note still owes
  a rule. **Backfilling from the source URL is out of scope here** — these works
  are re-fetchable, and completing them is discovery's job, not seeding's. Originals point at the existing
  `raw/` tree and renditions at the existing `ready/` renders, with
  `source_content_hash` computed at ingest so Chunk 18's staleness rule governs
  them from birth. Known defects in the legacy shape are corrected on the way
  in, not carried: identity becomes a UUID (never the source URL),
  `artist_details` is parsed into Artist rows, and `tv_content_id` is **not**
  written to the catalogue — it is per-device state and belongs to the display
  plane (it is seeded into TvBinding in Chunk 12).
- **Depends on:** Chunk 09 (the manifest build is how seeding is proven)
- **Artifacts consumed:** `data-model.md` (Artwork, Artist, Source, Original,
  Rendition, MatColor; the re-ingest note), `product-brief.md` § Scope,
  `nonfunctional-requirements.md` § Output Quality (the floor)
- **Deliverables:** a one-shot seeding path in the curation service layer
  (invocable, re-runnable, and idempotent — re-running must not duplicate
  works); the 41 works in the catalogue with artists, sources, originals,
  renditions, and mat colours; `MatColor.method` recorded as the legacy
  hand-tuned value, never as a fresh derivation; a report of anything that did
  not seed cleanly, per work with a reason — silence is not success
- **Tests:** unit — `artist_details` parsing across the corpus's real shapes
  (the multi-line "Charles Demuth\nAmerican, 1883–1935" form, **and the 8
  records carrying no `artist_details` at all**, which must fall back to the
  flat `artist` field rather than fail); a work with no physical dimensions
  seeds with nulls and is reported, never silently given a default size;
  identity is a UUID and no row carries a source URL as identity; no
  `tv_content_id` reaches the catalogue; idempotence — seeding twice yields 41
  works, not 82; integration — after seeding, a theme over all 41 builds a
  manifest whose entries and exclusions together account for all 41, with the
  2 dimensionless works excluded by name and reason
- **Acceptance criteria:** all 41 works are in the catalogue; a theme built over
  them produces a manifest whose exclusions are exactly the works with a named,
  understood cause, never a silent drop; every work with incomplete label
  metadata is listed in the seed report, so the gap is visible now rather than
  discovered at the wall
- **Done when:**
  1. Acceptance criteria met and tests pass
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

**Contract enforcement (Chunk 11).** Pinned before the display plane and
discovery build against these surfaces.

### Chunk 11: Contract tests — MCP evaluation harness (issue #17) and plane isolation (issue #7)

- **Description:** The two named test investments, built at the point where both
  have something real to bite on. The harness drives the MCP surface as a real
  client: tool names, schemas, and descriptions pinned against the registry so
  drift fails loudly (a description edit is a behavioural change — the recorded
  reason the contract level comes first), plus evaluation scenarios exercising
  real flows through the consolidated tools; scenarios grow with each later
  chunk. The plane-isolation test settles issue #7's design questions as this
  plan frames them: "the display plane" is the `display/` package (the boundary
  now exists, from Chunk 06); imports are checked transitively (a direct-only
  check is evaded by one shared helper); and the no-network-channel half bans
  HTTP client construction in display modules outright — the bright line — with
  the TV websocket explicitly exempt because talking to the TV is display's job.
  Static, so it holds whether or not curation is running, which is the point.
- **Depends on:** Chunks 07–09 (live tools to pin), Chunk 06 (the package
  boundary to enforce)
- **Artifacts consumed:** `api-contract.md` § Validation and § Versioning,
  `boundary-patterns.md` § Test Levels, issues #7 and #17,
  `project-preferences.md` (the manifest-channel norm row naming the test path)
- **Deliverables:** new `tests/contract/` harness (real client boot, registry
  assertion, scenario runner + first scenarios), new
  `tests/preferences/test_plane_isolation.py`, issue #7's design decisions
  recorded on the issue
- **Tests:** this chunk **is** tests; its own acceptance is that each guard
  demonstrably fails on a violation (a renamed tool, an over-budget description,
  a planted curation import in a display module) — a green test that cannot catch
  a real violation is worse than none
- **Acceptance criteria:** harness green against the real server; both halves of
  the isolation test proven able to fail; norm-index row for the manifest channel
  now points at an existing, passing enforcement artifact
- **Done when:**
  1. Acceptance criteria met and tests pass
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

**Display plane (Chunks 12–13).** Built on the Pi, verified on the wall.

### Chunk 12: Display daemon core — poll, rotate, TvBinding, directive semantics

- **Description:** The reconciliation loop: poll the manifest's mtime (~1 s — the
  interval is set by `next`, not by theme switching), adopt new manifests, refuse
  an unrecognised major version at ERROR and keep the last good one, ensure every
  listed work is uploaded (TvBinding in `display-state.sqlite`, `upload_status`
  explicit so a failed upload can never read as success — the 2024 defect made
  impossible), rotate via host-driven `select_image`, disable the native
  slideshow once (`set_slideshow_status(duration=0)`), skip missing files at
  WARNING and continue. Directive semantics display-side: persist the
  last-acted-on sequence (a restart must not re-execute the last jump under
  `Restart=always`), coalesce latest-wins, and on sequence regression re-baseline
  without acting, logging one WARNING — a catalogue restore must not replay a
  stale pin. Ports the sun-position brightness behaviour. TV access sits behind
  an interface.
- **Depends on:** Chunks 05 (verified library), 06 (display project), 09
  (manifests to read), 10 (a seeded catalogue, so the wall has content to
  rotate), 11 (isolation test now guards this plane as it grows)
- **Artifacts consumed:** `architecture.md` (§ The theme manifest, § Failure
  Modes, § display component), `data-model.md` (§ Rotation is host-driven,
  TvBinding), `observability-strategy.md` § What Each Failure Looks Like
- **Foreign API:** samsungtvws (target verified in Chunk 05)
- **Deliverables:** new `display/src/display/daemon.py`, new
  `display/src/display/tv/`, new `display/src/display/state/` with
  `display-state.sqlite` (TvBinding + last-acted-on sequence), structured logging
  with `work_id` correlation, resolved `ART_ROOT` and the **e-paper panel's**
  geometry logged at startup (display never reads the TV's physical size); **a one-shot TvBinding adoption path** seeded from the 41 legacy
  `tv_content_id` values in `all.json` — the works are already uploaded to this
  TV, so a fresh empty binding table would re-upload 41 4K images and orphan the
  existing set. Adoption is verified against the TV's own list, not trusted:
  a `tv_content_id` the TV does not report is discarded and the work re-uploads
  normally
- **Tests:** unit — manifest parsing, version refusal, directive
  persistence/coalescing/regression, binding state machine (TV faked at its
  interface, built after Chunk 05's verified shapes); TvBinding adoption —
  a content id the TV still reports is adopted, one it does not is discarded and
  re-uploaded, and adoption is idempotent across restarts; hardware — a live pass
  on the Pi: theme on the wall with no mass re-upload, `next`/`show_now` land
  within the poll interval, a deleted render file skips with a WARNING and
  rotation continues
- **Acceptance criteria:** the wall rotates the active theme from the new
  daemon; killing curation changes nothing about display's behaviour; a display
  restart neither re-executes the last directive nor loses its place
- **Done when:**
  1. Acceptance criteria met and tests pass, including the hardware pass
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

### Chunk 13: E-paper label, heartbeat, systemd units — cutover to the new planes

- **Description:** The label renders on the display plane from manifest label
  text — the e-paper panel's geometry stays with the plane that owns that panel. Type sizing is
  re-derived for the 1448×1072 panel rather than carrying the 2024 "Sans 18"
  forward; this is the product's most important accessibility surface
  (`design_decisions.accessibility_approach`). On each `image_selected` callback,
  render and push; a panel failure never stops TV rotation. The heartbeat file
  lands (atomic write, display → curation: timestamp, manifest version loaded,
  current work, TV and panel state, last error) — display never checks whether
  anyone read it. Systemd units committed in `deploy/`: display `Restart=always`
  with the restart-loop guard the recovered unit lacked; curation
  `Restart=on-failure` + `MemoryMax` so a runaway acquisition cannot OOM-kill the
  display plane. Cutover: the Pi runs the two new units; `tvart.py` stops being
  the production entry point (legacy files remain until Chunk 20).
- **Depends on:** Chunk 12; Chunk 04 (panel stack installs under uv)
- **Artifacts consumed:** `observability-strategy.md` § The Health Surface,
  `operational-spec.md` § Process Management, `nonfunctional-requirements.md`
  § Output Quality (label legibility) and Performance (15 s label budget),
  `design_decisions.accessibility_approach`
- **Foreign API:** IT8951 / omni-epd (build verified in Chunk 04)
  <!-- Chunk 04 verified that the stack COMPILES, not how it displays. This
       chunk writes a driver against omni-epd's runtime surface, so it owes its
       own verify-api (step 0 below). -->
- **Visual change:** yes — label legibility at standing distance on the real
  panel needs the operator's eyes, not a test
- **Deliverables:** new `display/src/display/panel/` (driver behind an
  interface + Pango label rendering), heartbeat writer, new
  `deploy/curation.service` and new `deploy/display.service`, cutover performed
  and recorded
- **Tests:** unit — label layout against fixed metadata (golden-image or
  measured-extent checks), heartbeat shape and atomicity; hardware — label
  matches the artwork within the 15 s budget across several rotations; killing
  the panel mid-run leaves rotation running
- **Acceptance criteria:** wall + label run unattended from the two new units
  through a TV power-cycle and a display restart with no human action; heartbeat
  advances and carries honest state
- **Done when:**
  0. verify-api — probe omni-epd/IT8951's runtime display surface on the real
     panel (init, draw, partial vs full refresh, and what a failure returns)
     before writing the driver; Chunk 04 verified the build, not this
  1. Acceptance criteria met on the Pi, including the operator's legibility look
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

**Discovery and acquisition (Chunks 14–18).** The paid, silent-failure-prone
core, built against the surfaces the contract tests already pin.

### Chunk 14: Discovery phase 1 — intent to works, runs, cost visibility (issue #12)

- **Description:** Intent → an enumerable work list, as a `DiscoveryRun` with the
  full recorded lifecycle: `start` returns a handle immediately (< 2 s), `status`
  long-polls ≤ 45 s, the work-count approval gate (`awaiting_approval` when the
  configured count threshold is crossed; `approve`/`decline`), `cancel`, and the
  `interrupted` path already reconciled by Chunk 08. Phase 1 can search the web
  when the intent is recency-bound (issue #12) — a text-only call cannot
  enumerate works past the model's cutoff, and finding works the curator could
  not have named is the product's definition of discovery; those searches count
  inside the per-run search cap and the pre-run estimate. **Cost visibility is a
  named deliverable here, not a norm** (`nonfunctional-requirements.md` § Cost
  visibility records that it must survive as one): the estimate before
  (computable from the work count), the actual after (provider-reported cost),
  on every surface equally. Spend records attribute per category; a 402 lands as
  `halted_by_budget`, distinguishable in logs and tool results; budget remaining
  reads `GET /api/v1/key`. `run_id` on every log line.
- **Depends on:** Chunks 08, 11 (harness grows discovery scenarios)
- **Artifacts consumed:** `product-brief.md` § Flow 2 (as amended),
  `data-model.md` (DiscoveryRun, SpendRecord), `api-contract.md`
  (§ Long-running operations, § Error Model), `nonfunctional-requirements.md`
  (§ Cost Constraints, § Performance), issue #12
- **Foreign API:** OpenRouter (chat + web-search plugin + key endpoint)
- **Deliverables:** **the spend ceiling itself, provisioned before the first paid
  call** — a dedicated OpenRouter key with a USD 20/month per-key credit limit and
  monthly reset (`nonfunctional-requirements.md` § Cost Constraints), recorded as a
  routine-operations item in `operational-spec.md` and added to `.env.example` as
  `OPENROUTER_API_KEY` (the file still declares only the legacy `OPENAI_KEY`). The
  ratified norm forbids an application-side ceiling, which makes this key setting
  the *entire* cap: an unprovisioned key is indistinguishable from a capped one on
  every surface the product exposes, so leaving it to setup lore would mean there
  is no ceiling at all. Then: new `curation/src/curation/discovery/` phase-1
  engine; `art_discovery` actions live: `estimate`, `start`, `status`, `approve`,
  `decline`, `cancel`, `list_runs`, `spend` (`resolve_images` arrives in
  Chunk 16); per-run search cap as a deployment value; harness scenarios for the
  run lifecycle including `halted_by_budget` vs `failed` vs `interrupted`
- **Tests:** unit — gate threshold recorded per run (`approval_required` stored,
  not re-derived), estimate computed from work count, cap enforcement as a
  distinguishable outcome; integration — full lifecycle against a faked provider
  built after verify-api; contract — an agent can distinguish "out of money"
  from "fetch failed" from "restarted underneath" by the returned state alone
- **Acceptance criteria:** a real intent resolves to a work list with a shown
  estimate; a recency-bound intent ("recent award-winning art") resolves to
  real, post-cutoff works; the curator can trim the list before paying for
  phase 2; **the ceiling is proven to fail closed, not assumed to** — provision a
  throwaway key with a near-zero limit, drive a real call into the 402, and show
  it surfacing as `halted_by_budget`. "Fails closed" is a claim about a path
  nobody has executed until someone executes it
- **Done when:**
  0. verify-api — probe the live OpenRouter key endpoint and one generation:
     capture the actual `limit_remaining` and per-generation `cost` shapes and
     the web-plugin invocation format before writing the client; re-verify the
     recorded prices (they move fast — `nonfunctional-requirements.md` says
     re-verify before relying)
  1. Acceptance criteria met and tests pass
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

### Chunk 15: Spikes — search-engine choice and `work_dedup_key` derivation (issue #18)

- **Description:** Two build-time spikes the artifacts explicitly hand to this
  plan, run against Chunk 14's real output rather than synthetic data. The
  search-engine spike compares Parallel, Exa-via-OpenRouter, and Perplexity **on
  this product's hard cases** — resolving a named work to a specific museum page,
  and a recency-bound intent — not on generic relevance; cost does not
  discriminate ($0.05–0.25/run spread), so this is a quality decision needing
  quality evidence. The dedup-key spike runs candidate derivations against real
  phase-1 output, measuring false positives ("Untitled", "Composition") and
  false negatives (translated, date-suffixed titles), and lands one shared
  implementation for the three call sites (cross-run suppression, Artist rows at
  acceptance, within-run dedup) — the linchpin of "a discovery run proposes each
  work exactly once", front-loaded so it cannot be decided implicitly three
  different ways.
- **Depends on:** Chunk 14
- **Artifacts consumed:** `nonfunctional-requirements.md` § Open — engine
  choice (the spike's stated constraint), issue #18, `data-model.md`
  (CandidateWork.work_dedup_key, Q3/Q11)
- **Deliverables:** engine decision recorded (`project-state.yaml` open question
  resolved, `nonfunctional-requirements.md` § Cost Constraints updated); the
  derivation recorded in `data-model.md` and implemented once in the service
  layer with the three call sites named; both decisions swept per
  `learnings.md` § "Retiring a claim is a repo-wide grep, not a local edit" —
  each dependent artifact acknowledged explicitly ("updated" / "checked,
  unaffected"), never inferred. This is the plan's largest amendment burst and
  the sweep is manual until the mechanical check ships upstream
  (brookstalley/prawduct#136); acknowledge per artifact in the commit message
- **Tests:** the spike measurements themselves, kept as regression tests over
  the hard-case corpus the spike assembles
- **Acceptance criteria:** issue #18's boxes checked (real output, hard cases
  exercised not assumed, one shared implementation); the engine default is a
  recorded decision with evidence attached
- **Done when:**
  1. Acceptance criteria met; decisions recorded in their homes
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

### Chunk 16: Discovery phase 2 — works to instances, resolve runs

- **Description:** Per-work search across museum APIs and the open web producing
  CandidateImages; ranking on the two deliberately-separate axes (confidence vs
  quality, dominance depending on `source_class`); exactly one selected instance
  per work with `selection_rationale`; previews cached locally
  (`preview_path` — review must not depend on a museum being reachable);
  below-floor instances shown, labelled with rendered physical size, never
  auto-selected, never hidden; works with no credible instance land at
  `unresolved` — reported, never silently dropped, never filled with a confident
  near-match. `resolve_images` arrives as the re-search: a `DiscoveryRun` with
  `kind='resolve'` and `parent_run_id`, refusing work ids already covered by an
  in-flight resolve run and naming them in the error (constraint 14 against
  ResolveRunWork), spend attributed to the resolve run and rolled up through the
  parent.
- **Depends on:** Chunks 14, 15 (the engine and the dedup key are decided)
- **Artifacts consumed:** `data-model.md` (CandidateImage, ResolveRunWork,
  constraints 8/9/14), `api-contract.md` § Rejecting an image does not
  re-search, `product-brief.md` § Canonical selection,
  `nonfunctional-requirements.md` § Output Quality (the floor)
- **Foreign API:** museum APIs (ARTIC first; open vocabulary by design)
- **Deliverables:** phase-2 engine in `curation/src/curation/discovery/`;
  `resolve_images` live with coverage enforcement; selection with recorded
  rationale; preview caching
- **Tests:** unit — selection respects suppression (`rejected_at` instances
  excluded; the work stays eligible — Q11), constraint 14 refusal names ids,
  below-floor never auto-selected, unresolved reported; **the terminal-verdict
  guard — a resolve run completing against a work the curator accepted (or
  rejected) in the meantime leaves the verdict alone and reports its result, and
  no path ever yields a work with an `artwork_id` and a non-accepted verdict**;
  integration — a double-submitted resolve is refused, an interrupted resolve
  frees its coverage
- **Acceptance criteria:** a run over a small intent produces one card's worth
  of data per work — selected instance, alternates, rationale — with unresolved
  works reported as their own outcome
- **Done when:**
  0. verify-api — probe the ARTIC API for the actual response shapes (fields,
     IIIF tile endpoints) before writing the client; fakes follow the captured
     shapes
  1. Acceptance criteria met and tests pass
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

### Chunk 17: Review and acceptance — `art_review`, thumbnails inline, promotion

- **Description:** The human gate, on the surface where it is hardest to hold:
  `list_works`/`get_work`/`list_images` return thumbnails **inline as image
  content blocks** (capped 400 px long edge — a 40-work batch stays inside the
  client's token budget), alongside the service-derived `display_fit` and
  rendered-inches figures a thumbnail cannot convey. Verdicts: `set_verdict`
  accepts `accepted`/`rejected` only, requires explicit work ids (refusing a
  bare accept-everything — the accepted set must appear in the transcript), and
  returns a teaching error naming `reject_image` for `awaiting_better_image`;
  `reject_image` is the single entry to that state and always sets
  `rejected_at`. Acceptance is promotion: mint the Artwork, CandidateImages
  become Sources (selected → `is_primary`), Artist parsed and normalised at
  ingest. The preview-file lifecycle decision that `boundary-patterns.md` leaves
  open is made here: `[DECISION: candidate previews are deleted by a periodic
  sweep over terminal-verdict CandidateWorks, not an on-verdict hook | a sweep
  is idempotent and safe to re-run after crashes, where a hook that dies with
  the process leaks silently — and deletion never touches the catalogue either
  way | user can veto/override]`. Truncation in listings is always explicit.
- **Depends on:** Chunk 16
- **Artifacts consumed:** `api-contract.md` (§ What the review surface must
  show, § Images are returned inline, § Token budget, § set_verdict),
  `security-model.md` § Content Appropriateness, `data-model.md`
  (promotion relationships, constraints 7/15)
- **Deliverables:** `art_review` actions live; promotion in the service layer;
  the preview sweep; harness scenarios covering the review flow with images
  asserted present in results
- **Tests:** unit — promotion mirrors the candidate shape into the catalogue
  shape; suppression scopes never share a key (Q3 vs Q11, both directions);
  `set_verdict` is accepted from `awaiting_better_image` (the curator is never
  blocked on a running re-search) while still refusing that value as a *target*;
  contract — every accept-capable result carries the image block; a 40-work
  listing stays under the token ceiling; explicit-ids enforcement
- **Acceptance criteria:** the worked example runs end to end over MCP from a
  real client: works reviewed with images in the transcript, accepted works
  appear in the catalogue with sources and rationale intact
- **Done when:**
  1. Acceptance criteria met and tests pass
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

### Chunk 18: Acquisition and preparation — fetch, metadata, mat engine, 4K render

- **Description:** Accepted works become wall-ready. Fetch by
  `acquisition_method` (dezoomify tiles / direct / API) with the zero-byte guard
  (constraint 5), `partial_tiles` as a normal recorded outcome, and the
  **free-space guard before acquisition starts** — disk-full is the one shared
  failure and it must be prevented, not caught. **The legacy `shell=True`
  invocation of dezoomify is not ported forward**: source URLs come from web
  discovery, which `security-model.md` establishes as attacker-influenceable, so
  interpolating one into a shell command is a command-injection vector. This
  chunk invokes the binary with an argv list and no shell, allowlists URL
  schemes before fetching, and treats every museum/source URL as untrusted
  input. Metadata normalisation at
  ingest: description markup reduced to `<i>`/`<b>` (constraint 10) so renderers
  stop re-fixing it. The mat engine: vision-model selection reasoning in LAB
  space via OpenRouter — the cheap vision model is selected here with prices
  re-verified at build (a slug picked months early is guaranteed stale; volume
  is one call per accepted work, so the choice barely moves cost), the
  dominant-colour fallback **recorded** on `MatColor.method` (never invisible),
  history retained. Composition: the mat in physical inches, bottom-weighted,
  against the configured TV panel geometry; the floor in rendered inches; **no
  upscaling, ever**; renditions carry `source_content_hash` and regenerate on
  staleness. `retry_acquisition`, `set_mat_color`, `regenerate` actions land.
  Mat quality is judged against the 41-work fixture from Chunk 06.
- **Depends on:** Chunk 17 (acceptance produces the work to acquire)
- **Artifacts consumed:** `nonfunctional-requirements.md` § Output Quality (mat
  geometry, the floor), `data-model.md` (Original, Rendition, MatColor,
  constraints 4/5/10/12), `design_decisions.error_handling_approach`,
  issue #6 (defects 2/3 die here with the module replacement)
- **Foreign API:** dezoomify (external binary) and museum image endpoints
  <!-- Its CLI contract is unowned and unversioned: capture it at step 0 below
       rather than inferring it from the 2024 call site. -->

- **Carried finding:** `tile-cache/` and `api-cache/` are created here and have
  no lifecycle owner. "Transient working space" holds only if something reclaims
  them — on the device already named the top operational risk. Give them a
  reclaim rule, or record that the operator prunes them and surface it on the
  health panel.
- **Visual change:** yes — mats over the regression corpus need the operator's
  eyes; "at least as good as 2024" is the subjective bar
- **Deliverables:** new `curation/src/curation/acquisition/` (fetch, prepare,
  mat engine); remaining `art_catalogue` actions (`archive`, `restore`,
  `retry_acquisition`, `set_mat_color`, `regenerate`); the free-space guard;
  vision-model choice recorded with verified pricing
- **Carried finding — settle before writing the mat engine:** the two recorded
  worked examples do not share a bottom-weight rule. The widths reproduce
  exactly, but the 42" box implies bottom = 1.15x top and the 75" box implies
  1.98x, and the factor itself is stated in no artifact. Those figures are named
  below as the unit-test oracle, so an oracle that cannot be satisfied has to be
  fixed first: derive the rule, correct whichever example is wrong, and record it
  in `nonfunctional-requirements.md`.
- **Tests:** unit — mat arithmetic against the recorded worked examples (42"/75"
  panels), floor classification, staleness detection, fallback recording;
  security — the fetch path refuses a non-allowlisted URL scheme, and a source
  URL carrying shell metacharacters reaches dezoomify as one inert argv element
  (the test must be able to fail: assert on the argv actually passed, not on the
  absence of a crash); regression — mat outputs across the 41-work fixture
  compared to the hand-tuned corpus; integration — a small accepted work goes
  intent-to-ready on the dev machine
- **Acceptance criteria:** an accepted work acquires, gets a mat with recorded
  provenance, renders to 4K, enters the manifest, and reaches the wall; the
  operator's corpus look finds no regression
- **Done when:**
  0. verify-api — two unowned interfaces, both probed before their client is
     written: (a) the chosen vision model through OpenRouter with a real image,
     capturing the response shape; (b) dezoomify's CLI contract — arguments,
     exit codes, output layout, and partial-tile behaviour — captured from the
     installed binary rather than inferred from the 2024 call site
  1. Acceptance criteria met and tests pass, including the corpus look
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

**UI and operations (Chunks 19–20).** Last by design: every operation the UI
binds already exists and is contract-tested.

> **Carried finding for Chunk 19:** the health panel is the product's *only*
> alerting surface, but its scoped fields omit the TV, panel, and last-error
> state that `observability-strategy.md`'s failure table maps failures onto.
> Either the panel surfaces them or that table has no reader.

### Chunk 19: Curation web UI and HTTP API

- **Description:** The browser surface, as thin HTTP bindings over the same
  service layer (typed, paginated, partial data — the recorded reason the UI
  does not ride MCP). Scope: intent entry with the estimate at the point of
  decision; the run view (status, work list trimming, approval gate, costs
  before and after); the review grid (image-forward, one card per work,
  alternates behind it, `display_fit` and rendered-inches labels, non-colour
  state indicators per the accessibility decision); themes (create, order,
  activate); and the health panel — heartbeat age in absolute terms (never a
  green dot), `limit_remaining`, manifest exclusions with reasons, backup age
  (fed by Chunk 20). WCAG 2.1 AA baseline; UI chrome never competes with
  artwork for contrast. The pre-UI governance checkpoint (below) disposes
  issues #2 (design system) and #10 (MCP second-look shelf) before this chunk
  starts — neither is silently included nor silently dropped.
- **Depends on:** Chunks 14–18 (every operation it binds), 13 (heartbeat to
  display); the pre-UI checkpoint
- **Artifacts consumed:** `product-brief.md` (§ Identity, flows 1/3/5),
  `design_decisions.accessibility_approach`,
  `observability-strategy.md` § The Health Surface, `api-contract.md` (the HTTP
  surface carries no stability obligation)
- **Visual change:** yes — a human-facing surface end to end
- **Deliverables:** new `curation/src/curation/http/` handlers (thin bindings);
  the UI pages above; health panel
- **Tests:** integration — every handler is dispatch + formatting over an
  existing service method (the service-layer norm holds by construction);
  the flows above exercised through the HTTP surface
- **Acceptance criteria:** the full curator loop — intent → estimate → review
  with images → accept → theme → wall — runs in the browser without touching
  the filesystem, JSON, or SSH; the health panel states observations with ages,
  never verdicts
- **Done when:**
  1. Acceptance criteria met and tests pass, plus the operator's look
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

### Chunk 20: Backup/restore exercise (issue #14), ops close-out, legacy retirement

- **Description:** The catalogue is the irreplaceable asset — the image tree is
  deliberately not backed up. Scheduled backup of `catalogue.sqlite` to another
  LAN machine using the SQLite backup API or `VACUUM INTO` (never a live file
  copy), several generations retained because the destination may be asleep;
  backup age surfaced on the health panel. **The restore is exercised, not
  described:** restore onto a scratch directory, watch the manifest build
  exclude everything with reasons, watch re-acquisition refill the tree — the
  designed, visible self-heal. Ops close-out: deploy/rollback procedures
  confirmed as documented, the legacy 2024 modules deleted now that nothing
  runs them, and the final cumulative review makes the branch release-ready.
- **Depends on:** Chunks 13 (health panel target exists), 18 (re-acquisition
  refills a restored catalogue), 19 (panel shows backup age)
- **Artifacts consumed:** `operational-spec.md` (§ Backup and Restore, § Routine
  Operations), issue #14, `nonfunctional-requirements.md` § Durability
- **Carried findings (hygiene, close-out):** `deploy/README.md` and the committed
  unit still describe the single-process 2024 loader with no pointer to the
  two-unit deployment; three artifact `depends_on` headers disagree with the
  derivation their own prose shows. Both corrected here.
- **Deliverables:** backup job + schedule in `deploy/`; backup age on the
  health panel; the restore exercise performed and its outcome recorded; legacy
  modules removed; README brought current
- **Tests:** the restore exercise is the test, plus a unit test that the backup
  path refuses the file-copy shape
- **Acceptance criteria:** issue #14's four boxes checked; a restored catalogue
  self-heals visibly per the recorded design; `git ls-files` carries no dead
  2024 module
- **Type:** cumulative-final
  <!-- Last chunk: commit, then its review IS the one `/prawduct:critic
       cumulative` over the whole bundle — no separate final. -->
- **Done when:**
  1. Acceptance criteria met, restore exercised
  2. Committed, then `/prawduct:critic cumulative` run and blocking findings
     resolved
  3. Chunk marked `[x]` in Status

## Early Feedback Milestone

**Milestone chunk:** 07
**What the user can do:** point Claude Code at the server, list the five tools,
and read the seeded catalogue through `art_catalogue` — the product's own worked
interaction, three layers deep, before anything widens. (Chunks 01–05 already
put the operator's hands on the hardware, but 07 is the first product
interaction.) The wall runs on the new planes at Chunk 13.

## Governance Checkpoints

**Commit & PR cadence:** commit per chunk after its Critic review passes
(per-chunk commit is what scopes `chunk`-mode reviews). PR boundaries are the
operator's call (`PR creation: wait_for_user`); if a phase ships as its own PR,
override that phase's last chunk to `cumulative` at that point. Chunk 20's
cumulative review is the release-readiness gate.

- **After Chunk 07** — architecture validation: the registry/service/persistence
  shape, the ASGI+MCP mount, and the thin-binding norm, reviewed before ten
  chunks build on them. (The chunk's own `final`-mode review is this checkpoint.)
- **After Chunk 13** — mid-build trajectory review: the wall runs on the new
  planes; verify the norms held under real hardware (plane isolation green,
  manifest the only channel, no false success anywhere in the journal), and that
  the cutover left nothing load-bearing in the legacy modules.
- **Before Chunk 19** — the UI checkpoint: dispose issue #2 (design system now,
  or accept one-off CSS with a recorded revisit) and issue #10 (second-look
  shelf in scope or explicitly deferred); confirm the UI scope above still
  matches what the built product needs.
- **After Chunk 20** — the cumulative review, per the chunk's `cumulative-final`
  type.

## Explicitly deferred — named so nothing is silently dropped

- **Issue #8 (decision-amendment acknowledgement check)** — **moved out of this
  product, not dropped.** It was Chunk 01 of this plan. The check reads only
  prawduct's own data model (`technical_decisions` markers, the
  `artifact_manifest` graph), so building it here would make this repo the
  maintainer of framework tooling and leave every other prawduct repo to
  re-solve it. Filed upstream as `brookstalley/prawduct#136` with the full
  thirteen-recurrence evidence and the five cause classes. **The obligation it
  was to mechanize still binds in the meantime** — every amendment in this build
  sweeps its dependent artifacts by hand per `learnings.md` § "Retiring a claim
  is a repo-wide grep, not a local edit", with per-artifact acknowledgement in
  the commit message. Chunk 15 carries the largest such burst and says so.
- **Issue #10 (second-look shelf)** and **issue #2 (design system)** — decided
  at the pre-UI checkpoint, not silently included or dropped now.
  `security-model.md` records #10 as "filed as backlog work, not committed
  design".
- **Ambient adaptation beyond the ported brightness loop** (auto art-mode
  scheduling, weather-aware brightness) — the brief's Later list.
- **MCP resources** — decided no for v1 (additive later; recorded 2026-07-20).
- **3tears relaxation to 3.13** — off this product's path entirely
  (`operational-spec.md`); an upstream concern.
- **Multi-account, multi-TV, HA, concurrent runs** — accommodate-only per the
  brief; designed around, not built.
