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
      - "the theme manifest file is the only channel from curation to display → conforms: every display chunk reads the manifest and image tree only; interactive commands ride the manifest's directive block (the recorded R-17 decision); issue #7's plane-isolation test lands in Chunk 12 (moved from 11 on 2026-08-01 — it checks the `display/` package, which Chunk 12 is the one to create) and enforces it mechanically from there. Until then the norm is Critic-enforced, which is what `project-preferences.md` now says; it previously named the test as though it already existed"
      - "operation logic lives only in the service layer; MCP tools and HTTP handlers are thin bindings → conforms: Chunk 07 establishes the registry/handler split as a directory boundary before any tool exists, and every later surface chunk binds service methods only; registry generation carries no per-tool logic"
  - artifact: nonfunctional-requirements
    dispositions:
      - "spend ceilings are enforced by the provider, never by application code → conforms: no chunk builds an application-side ceiling; `halted_by_budget` derives from the provider's refusal (Chunk 14B) and budget-remaining reads `GET /api/v1/key`, which lags by minutes and is therefore display-only, never a gate. The per-run search cap (Chunk 14A) is budgeting inside the norm's recorded scope note, not a ceiling"
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
- [RESOLVED 2026-08-01, half each way: a target exists (fork master `fe95ef1`) and carries Frame-generation support as a model-year branch, but `delete_list` is **not** fixable by bumping — it is unchanged on master, so the fallback fired and confirmed deletion is `tv_delete.delete_list_confirmed` in this repo. Two things the assumption did not anticipate: the target needs `websockets>=13.0` (the pinned 12.0 cannot import it), and its constructor performs blocking network I/O. **Live on hardware is still unverified** — Chunk 05 stays open for the bench pass]
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

This list is in **build order, not numeric order** — chunk numbers are stable
identities, and their detailed sections stay in numeric order below. The list was
re-ordered on 2026-07-31; the two changes and why are recorded in the Context
block under "Re-sequenced 2026-07-31".

The hardware-gated chunks are **no longer blocked** — the Pi and panel are on the
bench as of 2026-07-31 — so they take their place in build order rather than
sitting at the end. The reason they were parked there still holds for anything
that becomes blocked later: the tooling takes the first unchecked box as the
current chunk, and a blocked chunk ahead of active work silently hands its
`Critic mode:` and `Type:` to every chunk after it.

- [x] Chunk 01: Untrack the TV pairing token; drop the catalogue backups (issue #4)
- [x] Chunk 02: Deployment values out of source (issue #5) + `art.py` defect dispositions (issue #6)
- [x] Chunk 06: uv restructure (curation only), lint/test tooling — *display plane deferred, mat fixture deferred*
- [x] Chunk 07: Walking skeleton — catalogue core → service layer → MCP tool, end to end
- [x] Chunk 07B: The durable seam — persistence reshaped to the `DurableStore` contract
- [x] Chunk 08A: The accepted-catalogue entities, their constraints, and `display_fit`
- [x] Chunk 08B: The discovery entities, both state machines, startup reconciliation
- [x] Chunk 09: Manifest builder, themes, directives — `art_theme` and `art_display`
- [x] Chunk 10: Seed the catalogue with the existing corpus (v1 scope item)
- [x] Chunk 10B: The first browser surface — catalogue, themes, manifest, health
- [x] Chunk 11: Contract tests — MCP evaluation harness (issue #17) — *plane isolation (#7) split to Chunk 12*
- [x] Chunk 14A: `art_discovery` surface, run correlation, the search cap — no spend
- [x] Chunk 14B: The OpenRouter client, the phase-1 engine, the ceiling (issue #12)
- [ ] Chunk 05: Replace the samsungtvws pin, verified on hardware (issue #3)
- [ ] Chunk 04: Verify the IT8951 build under uv PEP 517 isolation (issue #9)
- [ ] Chunk 03: Pi operational hardening and the vendor-risk answer (issues #15, #16, #13)
- [ ] Chunk 12: Display daemon core — poll, rotate, TvBinding, directive semantics *(+ plane isolation, from 11)*
- [ ] Chunk 13: E-paper label, heartbeat, systemd units — cutover to the new planes
- [x] Chunk 15: Spikes — search-engine choice and `work_dedup_key` derivation (issue #18)
- [ ] Chunk 16: Discovery phase 2 — works to instances, resolve runs
- [ ] Chunk 17: Review and acceptance — `art_review`, thumbnails inline, promotion
- [ ] Chunk 18: Acquisition and preparation — fetch, metadata, mat engine, 4K render
- [ ] Chunk 19: Curation web UI and HTTP API — the discovery half, onto 10B's surface
- [ ] Chunk 20: Backup/restore exercise (issue #14), ops close-out, legacy retirement

Context: Plan authored 2026-07-20. Chunks 01, 02 and 06 landed 2026-07-27 in one
pass; **Chunk 07 landed the same day**, took its `final` Critic round and the
follow-up `verify-resolutions` pass, and the architecture now runs end to end —
a real MCP client lists five tools over HTTP and reads a seeded catalogue.
**Chunk 07B landed 2026-07-27** — persistence is split into a generic durable
store and a domain adapter, the 3tears question is answered and closed, and the
on-disk catalogue format is now pinned by a read-compatibility test rather than by
assertion.

**Chunk 08 was split into 08A and 08B on 2026-07-27** at the operator's call —
the accepted catalogue, then the pre-acceptance pipeline — because one Critic
round over the whole of it would read ~2,500 lines at once; see the section below
for what each half carries. **Both halves landed 2026-07-27.** 08A took the
catalogue file from three tables to nine and enforced constraints 1–6, 10, 12 and
13; 08B took it to fourteen, added constraints 7–9, 11, 14 and 15, closed both
discovery state machines, and made startup reconciliation real — which is what
keeps the double-spend guard from becoming a permanent block after a crash.
Acceptance is now a promotion in the service layer: a candidate work mints an
Artwork and its image instances become that work's Sources. The service layer is
split by concern (`CatalogueService` / `DiscoveryService`) behind a container
every surface takes, closing the finding 08A's review carried forward.

**The whole of `data-model.md` is now built.** What remains of the model is the
per-theme rotation settings, whose only reader is the manifest builder in Chunk
09, and `work_dedup_key`'s derivation, whose spike is Chunk 15 — the column and
the suppression that reads it are in place, and the caller supplies the key.

**Chunk 09 landed 2026-07-31.** The service layer is three concerns now, not two:
the theme/directive/manifest half came out of `CatalogueService` first, as its own
commit, before anything was added to it. The manifest builder is real — atomic
temp-and-rename, schema major 1, rotation settings with a deployment fallback, the
directive block carried forward unchanged — and it **reports its exclusions**, per
work with a reason, which is the half of the readiness design that a list-only
builder would have silently dropped. `art_theme` and `art_display` are live over
MCP with all thirteen actions between them.

Three things were settled at build that the artifacts had left open, each recorded
where the rule lives rather than only in code: **the global rotation default** is
deployment config at 180s/shuffle, carried forward from what the 2024 wall runs
today; **"the fetch succeeded" is not a separate readiness check**, because holding
an original is what a succeeded fetch produces and the other reading would take a
work off the wall for a failed *re*-acquisition; and **activating a theme
publishes it**, which the api-contract already said ("changes the wall
immediately") and the first implementation did not do.

The durable store also gained a real widening step, because the rotation columns
were the first change to a table that files on disk already carry.

**Re-sequenced 2026-07-31 — two operator decisions.**

*First: the hardware chunks are unblocked.* The Pi and panel are on the bench, so
03, 04 and 05 move from the blocked list into build order. They keep their numbers
and their specs; only their position changed. They sit after 10B because 09 and 10
are on every path to anything visible, and before 11–13 because 05 verifies the
library Chunk 12 is written against and 04 verifies the panel stack Chunk 13 needs
— both are assumptions in Requirements Confidence above, and each converts to a
recorded fact cheaply. **If bench access turns out to be time-limited, pull 04 and
05 ahead of 09** — that is a live reordering, not a re-plan, and it is the
operator's call.

*Second: a first browser surface lands at 10B instead of waiting for Chunk 19.*
The reason the whole UI sat at position 19 was that it binds every operation, and
most operations did not exist. After Chunk 10 that is no longer true for a real
subset: 41 seeded works with images on disk, themes, and a manifest with reasoned
exclusions. **10B is a re-sequencing of scope Chunk 19 already specifies, not new
scope** — it takes the catalogue/theme/health third of 19's list and leaves the
discovery two-thirds (intent entry, run view, approval gate, cost display, the
review grid with alternates) where they are, because the services behind them
arrive in 14–18. Chunk 19 keeps its number and builds onto 10B's surface rather
than standing one up.

The cost is named rather than discovered: the **UI checkpoint moves from "before
Chunk 19" to "before 10B"**, so issues #2 (design system) and #10 (second-look
shelf) come due earlier, and every chunk from 14 on now has a UI surface it may
need to extend. The benefit is that the product becomes usable by a human eleven
chunks earlier, and each later chunk's UI is reviewed as it lands instead of all
at once.

**Chunk 11 landed 2026-08-01, split in two.** The MCP evaluation harness is
built; the plane-isolation half (issue #7) moved to Chunk 12, where the
`display/` package it checks is actually created — the premise that Chunk 06 had
already created it was simply wrong, and a guard over an empty tree is the
green-test-that-cannot-fail this plan explicitly rejects. The correction that
matters beyond this chunk: **the manifest-channel norm row named that test as a
live `Test` mechanism and no such file had ever existed.** That is the second
norm row in two sessions found asserting enforcement it did not have, after the
broad-except row's linter claim — the recurrence, not either instance, is the
finding.

What the harness delivers is shaped by a distinction `api-contract.md` §
Validation already drew and the chunk entry had blurred: contract tests assert
the surface's **shape**, and the harness asserts a model can **use** it. The
shape half landed with 07–09, so this chunk is the other two: a deterministic
**scenario runner** in the default suite, and a **model-driven evaluation**
behind the `llm_eval` marker, deselected by default. Both produce the same
transcript, so the scripted route is the yardstick a model's route is measured
against rather than a separate exercise. The model half runs through
`3tears-models` over OpenRouter at the operator's call — its own dependency
group, because it is the heaviest install in the repo and nothing in the default
run imports a line of it.

**Re-sequenced and split 2026-08-02 — discovery moves ahead of the hardware
chunks.** Bench access lapsed, and Chunk 14 depends on 08 and 11 alone: nothing in
it touches the TV or the panel, and its foreign API is OpenRouter. Leaving it
behind five hardware-gated chunks would have stalled every non-hardware path in
the plan behind a blocker unrelated to it — and, per the Status preamble's own
warning, left a blocked chunk sitting at the first unchecked box handing its
`Critic mode:` and `Type:` to everything after it. 05, 04, 03, 12 and 13 keep
their numbers and specs; only their position moved.

**Chunk 14 is split into 14A and 14B**, at the seam
`openrouter-api-findings.md` already argues for — the narrow first-party interface
the engine depends on. 14A builds everything up to that seam and spends nothing;
14B builds what sits behind it. The split's value is that 14A needs no API key, no
credit and no operator action, so it proceeds while the ceiling is provisioned.
The risk it carries is named rather than discovered: building to a seam before the
thing behind it exists can encode the wrong shape. Judged low **because the live
probe recorded the real shapes first** — that is precisely what the verify-api
step bought, and it is why the split is safe here and would not have been before
2026-08-02.

**14A landed 2026-08-02.** Eight of `art_discovery`'s ten actions are live and
drive the real service; `resolve_images` is deliberately not advertised, because
a declared action a model cannot distinguish from a working one is a promise the
surface cannot keep. The seam stayed **phase 1 only**, which is the one scoping
call worth carrying forward: defining phase 2's interface now would encode a
shape before the ARTIC probe that Chunk 16 makes its own first step, and the
split's stated risk applies exactly there. The consequence is visible and
truthful rather than hidden — a run that passes the gate sits in
`resolving_images`, and `status` says in plain words that image resolution is not
wired up in this deployment and offers `cancel`. **That sentence is owed a
deletion when phase 2 lands**: a run waiting on a capability that now exists
would be told the opposite of the truth.

The values the plan left to this chunk are settled and recorded where their rules
live: the gate at 25 and the two-part cap at 10 + 2/work in
`nonfunctional-requirements.md`, the estimate's arity in `api-contract.md`, the
provisional key's site and its two known failure modes in `data-model.md`, and
the log shape in `observability-strategy.md`.

**14B landed 2026-08-02 and discovery now spends.** Everything 14A owed is
settled: every run searches rather than a trigger deciding (the failure mode of a
wrong trigger is silent and unrecoverable), the engine writes
`DiscoveryRun.strategy` when the work list settles, and the phase-1 allowance
stays at 10 because the fee proved to be **per request and flat across result
counts** — which also makes search breadth free. Exhaustion (403) and
unaffordability (402) are held apart in the client, and the ceiling is *proven*
closed: a deliberately exhausted key drives a real run to `halted_by_budget` in a
live suite behind `-m live_api`, which is now the durable form of
`openrouter-api-findings.md`.

**One thing 14B found and deliberately did not fix.** A real run cost $0.0056
against a $0.127 estimate, because `DISCOVERY_PHASE1_INPUT_TOKENS` assumes
490,000 tokens where the plugin injects 3,453. That figure is the cost analysis's
*whole-run* basis spent on phase 1 alone, and phase 2's tokens are in no estimate
at all — so re-basing phase 1 by itself would swap a visible overstatement for an
invisible understatement. **Chunk 16 owns the correction**, being the first point
both halves can be measured.

**A requirements pass ran before either half (2026-08-02)** and is the reason the
chunk entries below carry values rather than the phrase "the configured
threshold". It found nine gaps, of which the load-bearing ones were: the per-run
search cap was **undefined for phase 1** (it "derived from the work count", which
phase 1 exists to produce — corrected in `nonfunctional-requirements.md` to a
two-part cap), `estimate`'s behaviour had never been specified despite the action
shipping in the surface table since the start (now in `api-contract.md`), and
`work_dedup_key`'s interim derivation had no owner even though the column is
`required` and phase 1 mints rows (now in `data-model.md`). A tenth finding was a
requirement for a surface that does not exist — cost visibility "on CLI" — struck
rather than silently inherited.

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

- **curation (3.14):** fastapi, uvicorn, `mcp>=1.28.1` (official SDK — decided over
  `3tears-mcp`, which drags NATS), 3tears-models (OpenRouter adapters, arriving with
  Chunk 14), httpx, pillow, opencv-python-headless, scikit-image, numpy, pydantic,
  python-dotenv. All wheels on aarch64/3.14, verified 2026-07-20. *(Amended
  2026-07-27: 3tears **core** is no longer in this set — the catalogue's durable
  tier is first-party code shaped to the framework's `DurableStore` contract, so
  no framework code is imported. See § The 3tears catalogue dependency.)*
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
│       ├── persistence/       #   catalogue schema on stdlib sqlite3, behind Protocols
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
and image tree only; Critic-enforced until the `display/` package exists, then by
`tests/preferences/test_plane_isolation.py`, which is a deliverable of the chunk
that creates that package); **hardware sits behind interfaces** (the TV client and panel driver
are swappable modules, so a frozen 2023 driver never again dictates an
interpreter). Persistence is reached only through the service layer.

## Build Chunks

**Groundwork — evidence first, at the hardware (Chunks 01–05).** These precede
the walking skeleton deliberately: they close the live credential leak first of
all, then retire the two build-blocking unknowns on real hardware. The
architecture-proving slice is Chunk 07.

### Chunk 01: Untrack the TV pairing token; drop the catalogue backups (issue #4)

- **Description:** Close the credential leak in the public repo, in the corrected
  order: untrack first, then re-pair — the reverse order commits the fresh token
  (`security-model.md` § Credentials). *(Two things this said are withdrawn, both
  as of 2026-07-27: the "one sitting, at the hardware" coupling is gone — the
  config hoist moved the token under `ART_ROOT`, outside the checkout, so the
  untracking commit does **not** delete it on the Pi's next `git pull`; and the
  re-pair was not needed at all, the operator having confirmed the leaked token
  already expired. See the Deliverables below and `security-model.md`.)* Also
  drops the three `all.json` backup snapshots. `all.json` itself stays tracked — it is the mat regression corpus
  until Chunk 06 extracts the fixture.
- **Depends on:** none (hardware access required)
- **Artifacts consumed:** `security-model.md` § Credentials and Secrets,
  issue #4
- **Deliverables:** `token_file`, `all.backup`, `all.json.backup`,
  `all.json.backup2` untracked (`--cached` only) and gitignored; ~~TV re-paired so
  the published token no longer authenticates~~ — **not done, and not needed: the
  operator confirmed the leaked token had already expired, so it authenticates
  nothing and there is no live credential to rotate**; the history-rewrite decision
  recorded explicitly (recommendation: no — rotation kills the credential, and a
  public-repo force-push buys nothing further)
- **Tests:** none (repo-state change); `tests/test_repo_hygiene.py` guards the
  untracking from here on
- **Acceptance criteria:** all four files absent from `git ls-files`, present in
  the working tree; ~~display connects to the TV on real hardware with the fresh
  token~~ — **dropped with the re-pairing above**; `git status` clean afterwards

> **Deviation recorded 2026-07-27**, after Critic review found this section still
> asserting a hardware deliverable the chunk did not perform while its three
> siblings each carried their own. The Status line's title was shortened to
> "Untrack" when the chunk landed and the change-log named the deviation, but a
> builder or auditor reads *this* section — where it said the criterion was met.
> The hardware chunks (03, 04, 05) remain blocked, and none of them depends on
> this one having re-paired.
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
  are not fixed in legacy code — **amended 2026-07-27: defect 2 was fixed after
  all, because the ruff configuration adopted in the same chunk selects `B006`
  and deliberately does not waive it for `art.py`, so the mutable default
  argument fails the build. Defect 3's disposition stands unchanged.** Recorded
  here rather than left implicit: the plan otherwise states something false about
  the code, and a later reader would believe defect 2 is still live; defect 4 (`art_label.py`, dead and broken) is
  deleted in Chunk 06 after confirming no out-of-tree importer.
  **A fifth defect gets its disposition here, added 2026-07-27:** `tvart.py`'s
  `upload_file` catches every exception, logs it, and returns with
  `remote_filename` still `None`, so the caller records a null content id as an
  uploaded file. It was never in issue #6's four, so nothing scheduled it — while
  the codebase cites it *by name* in two places as the motivating example for
  never reporting success on a failed operation (`envelope.py`'s docstring and
  `observability-strategy.md` § Two Defects to Fix, Not Inherit). **Disposition:
  dies with the 2024 modules at Chunk 20, not fixed in legacy code.** The
  reasoning is the same as defect 3's — the replacement is already designed and
  records `upload_status` explicitly for exactly this reason (`data-model.md` →
  TvBinding) — and it is written down so the defect is not rediscovered as a
  surprise by someone who finds it cited as a lesson and assumes it was fixed.
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
- **Verify-api landed 2026-08-01; the source half is done and the hardware half
  is not.** What the read settled, beyond what the chunk anticipated:
  - **PyPI was never a candidate.** That package ships no async art client and
    no callbacks — the whole TV boundary here is built on both. The choice was
    between fork SHAs, not between fork and release.
  - **`delete_list` is unchanged on master**, so the bump does not fix it and the
    fallback fired: `tv_delete.delete_list_confirmed` verifies against the set's
    own content list. It keeps *unconfirmable* apart from *failed*, because
    collapsing them is the original defect.
  - **`upload()` streams only when handed a path.** The chunker is picked from
    the argument type, so the caller had to change too; passing bytes it had
    already read would have taken the bump and none of the benefit.
  - **The target needs `websockets>=13.0`** — it imports `websockets.asyncio.client`,
    absent from the pinned 12.0. Nothing costed this; it is a two-pin change.
  - **Constructing the client now blocks on network I/O** and raises when the set
    is unreachable, where the pin deferred that to first use. Chunk 12's daemon
    inherits this: construction cannot sit on the event loop, and an asleep
    television surfaces there rather than at `start_listening`.
- **`tv_api_check.py` has no unit tests, and cannot have them here.** It imports
  `samsungtvws`, a Pi-side runtime dependency the root project deliberately keeps
  in `requirements.txt` rather than installing, so the module has no reachable
  test home in this suite. The symbol-grep coverage floor scores it as
  "referenced" on the `tv_delete` symbols it imports — that is the floor behaving
  as documented, not a coverage claim. Its logic goes into the display plane's
  suite with the rest of the TV boundary, where the library is present. The
  deletion wrapper it calls is separately and fully tested, because that module
  takes the client as a parameter and imports nothing.
- **What the bench pass still owes:** `tv_api_check.py` is the scripted pass —
  construction cost, model and API generation, which callback spelling this set
  emits, a real 4K upload timed by path, and a confirmed delete of only the image
  it uploaded. Until it runs green against the live set, the new pins are
  unverified and `deploy/pi-freeze-2024.txt` is the rollback.
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
  is (evidence, not scratch) — landed 2026-07-27 as `deploy/pi-freeze-2024.txt`,
  after Chunk 06 shipped without it. Legacy modules stay at the root, running
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
  catalogue (Artwork, Artist, Theme on SQLite) → a service layer that
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
- **Foreign API:** mcp Python SDK (`mcp>=1.28.1`)
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

### Chunk 07B: The durable seam — persistence reshaped to the `DurableStore` contract

- **Description:** Split the catalogue's persistence into two layers so that the
  twelve entities Chunk 08 adds are written once, against their final shape. Below:
  a generic, table-oriented durable store owning the connection, the lock, the
  schema, and constraint-refusal translation, exposing `fetch_one` / `upsert` /
  `delete` / `scan` keyed by table plus a primary-key mapping — the decomposition
  and naming of 3tears' `DurableStore` protocol, so that a later collection layer
  is an adapter rather than a rewrite. The **argument lists are a subset**, not a
  match: the divergences (sync methods, no `conn` transaction handle, no `cas`
  fence, a required rather than optional `pk`) are enumerated in the module
  itself, because a parity claim wider than the code is how the next reader is
  misled about what can be swapped. Above: `SqliteCatalogue`
  as the domain adapter, mapping records to rows and owning ordering, paging and
  totals. This is a refactor: no existing test changes, and no change to what any
  caller receives. The one deliberate exception is the journal — a refused write
  logs from both layers, so that the record's identity and the SQL cause are each
  recorded by the layer that can see them.
- **Depends on:** Chunk 07
- **Artifacts consumed:** `3tears-integration-findings.md` (§ Answer 2 — the
  contract being matched and why it is worth matching), `architecture.md` § Data
  Ownership (single writer per store), `project-preferences.md` (async at the I/O
  boundary, synchronous core)
- **Foreign API:** none — 3tears' `DurableStore` is matched structurally and
  **not imported**; no dependency is added
- **Deliverables:** new `curation/src/curation/persistence/durable.py`;
  `curation/src/curation/persistence/sqlite.py` reduced to the domain adapter; the ordered-page read
  named as sitting deliberately outside the matched contract, because 3tears'
  contract has no ordered paging and its collection layer never will
- **Tests:** unit — the durable store's own contract, including the
  insert-versus-upsert conflict modes and the constraint-refusal translation that
  `SqliteCatalogue` has never had a direct test for; a read-compatibility test
  that rebuilds a catalogue from the previous revision's frozen DDL and inserts
  and reads it back through the current adapter, so the on-disk contract is
  evidence rather than assertion; a structural test asserting that only the
  durable store imports `sqlite3`, since a stray import elsewhere would pass every
  behavioural test while dissolving the seam; the existing service, contract and
  integration suites stand unchanged as the behaviour-preservation evidence
- **Acceptance criteria:** both suites pass with no test modified; a catalogue
  written before the change is read correctly after it (same file, same schema);
  no module under `curation/src` outside the durable store imports `sqlite3`
  (tests may, and one does). The last two are pinned by tests so they keep holding
  through Chunk 08; "no test modified" is a property of the diff, evidenced by
  review of the change set
- **Critic mode:** chunk
- **Done when:**
  1. Acceptance criteria met and tests pass
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

### Chunk 08 was split into 08A and 08B (2026-07-27)

Chunk 08 as authored was the whole of `data-model.md` beyond the three entities
Chunk 07 proved: eleven entities, fifteen constraints, three state machines and
startup reconciliation — an estimated ~2,500 lines with tests. That is a single
Critic round over a diff large enough that review quality degrades
(`methodology/building.md` § Session Scope Discipline), on the most
contract-setting chunk in the plan. The operator chose the split. Nothing is
descoped: every entity, constraint, state machine and acceptance question below
appears in exactly one of the two halves, and the split line is the one the model
already draws — the accepted catalogue versus the pre-acceptance pipeline.

The 07/07B precedent is the evidence: two of that split's five defects were
unreachable from the smaller surface and were found only because the smaller
surface was reviewed on its own.

### Chunk 08A: The accepted-catalogue entities, their constraints, and `display_fit`

- **Description:** Everything `data-model.md` says about a work that has already
  been accepted: Source (with `source_class` as the load-bearing branch point),
  Original, Rendition (`tv_display`/`thumbnail` only — no `label` kind), MatColor
  with history, ThemeMembership. The Artwork state machine (`archive`/`restore`).
  Constraints 1–6, 10, 12 and 13 enforced at write time in the service layer.
  Multi-row constraints (one active Theme, one current MatColor, one primary
  Source) need a transaction seam on the durable store, which lands here — the
  matched framework contract threads a `conn` handle through every method for
  exactly this reason, so a seam is conformance, not divergence.
- **Depends on:** Chunk 07B
- **Artifacts consumed:** `data-model.md` (entities Source, Original, Rendition,
  MatColor, ThemeMembership; Artwork state machine; constraints 1–6, 10, 12, 13),
  `architecture.md` § The theme manifest
- **Carried finding:** the curation-side directive sequence counter is pinned as
  catalogue-side by `architecture.md` but has no modelled home, and a catalogue
  restore restores it — so it is part of the persisted format. Give it one here
  (a settings/singleton row or equivalent) rather than letting Chunk 09 invent it
  implicitly; `pinned_work_id`'s clearing rule is unstated and settles here too
- **Deliverables:** the accepted-catalogue schema in
  `curation/src/curation/persistence/`, its service-layer operations and the
  Artwork transitions, `display_fit` as the single service-layer derivation
  (never stored), the directive-sequence settings row
- **Tests:** unit per constraint (each of 1–6, 10, 12, 13 has at least one test
  that fails without its enforcement); the Artwork transitions including the
  illegal edges; the durable transaction seam rolls back a partial multi-row write
- **Acceptance criteria:** the schema answers Q1, Q2, Q6, Q7, Q8 and Q9 from
  `data-model.md` § What this data must answer, demonstrated by a test per
  question
- **Done when:**
  1. Acceptance criteria met and tests pass
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

### Chunk 08B: The discovery entities, both state machines, startup reconciliation

- **Description:** Everything `data-model.md` says about the pipeline before
  acceptance: DiscoveryRun (both kinds, all nine statuses), CandidateWork,
  CandidateImage, SpendRecord (attribution only — it enforces nothing),
  ResolveRunWork. The DiscoveryRun and CandidateWork state machines. Constraints
  7–9, 11, 14 and 15 enforced at write time in the service layer, including the
  two-scope suppression rule (Q11) and the single-entry-point rule for
  `awaiting_better_image` (constraint 15). Startup reconciliation moves
  process-held runs (`resolving_works`, `resolving_images`) to `interrupted` —
  deliberately not `awaiting_approval`, which is human-held state that must
  survive a restart — releasing ResolveRunWork coverage and logging one WARNING
  per run moved, which is the only signal a run died.
- **Depends on:** Chunk 08A
- **First task, carried from 08A's Critic round:** **split `CatalogueService`
  before adding to it.** It is one class over nine entity families and ~740 lines;
  this chunk adds five more families, and two reviewers independently called the
  split out. The seam that has been waiting for a second concern is here — a
  `DiscoveryService` alongside the catalogue one, both bound by a small container
  the surfaces take, so `create_app` and the MCP bindings stop naming a single
  service class. Do it first, as its own commit, so the entity work lands against
  the shape it will keep.
- **Artifacts consumed:** `data-model.md` (entities DiscoveryRun, CandidateWork,
  CandidateImage, SpendRecord, ResolveRunWork; both state machines; constraints
  7–9, 11, 14, 15), `api-contract.md` § `set_verdict` cannot set
  `awaiting_better_image`
- **Deliverables:** the discovery-side schema, its service-layer operations and
  transitions, acceptance as promotion (CandidateImages become Sources),
  reconciliation on startup
- **Tests:** unit per constraint (each of 7–9, 11, 14, 15 has at least one test
  that fails without its enforcement); state-machine transition coverage
  including the illegal edges (`set_verdict` refusing `awaiting_better_image`,
  resolve runs never reaching phase-1 states); reconciliation — a seeded
  process-held run is moved, an `awaiting_approval` run is not, coverage is
  released
- **Acceptance criteria:** the schema answers Q3, Q4, Q5, Q10, Q11 and Q12 from
  `data-model.md` § What this data must answer, demonstrated by a test per
  question
- **Done when:**
  1. Acceptance criteria met and tests pass
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

### Chunk 09: Manifest builder, themes, directives — `art_theme` and `art_display`

- **First task, carried from 08B's Critic round:** **extract the theme and
  display concern out of `CatalogueService` before adding to it.** 08B split the
  service layer by adding `DiscoveryService` beside it, which is what the 08A
  finding asked for and is *not* what it was worried about: `CatalogueService` lost
  36 lines and still stands at ~743 over nine entity families, and three of the
  five tool nouns resolve into it. This chunk is the one that grows it — theme
  create/update/delete/reorder, display sync/show_now/next, and the manifest
  builder all land there otherwise. The container exists for exactly this, so a
  third service is cheap now and more expensive every chunk after. Do it first, as
  its own commit, the way 08B did — and update `architecture.md`'s
  internal-layering diagram in the same change, since it currently names two
  services.
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
- **Carried from 08A:** `Theme.rotation_interval_seconds` and `Theme.shuffle` are
  specified in `data-model.md` and are **not yet in the schema**. They exist to be
  written into the manifest's rotation settings, and nothing reads them until this
  builder does — but adding them is the **first change that widens a table an
  existing catalogue file already has**, so it needs a migration rather than an
  appended column. `CREATE TABLE IF NOT EXISTS` silently does nothing to a table
  that exists, so an old file would read back a `KeyError` on the new column
  rather than an error anyone could act on. The frozen-DDL compatibility test in
  `curation/tests/unit/test_catalogue_store.py` is what will fail first.
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

### Chunk 10: Seed the catalogue with the existing corpus (v1 scope item)

- **Description:** The v1 scope commits to a "new catalogue built through
  curation, seeded with the existing 41 artworks as worked examples"
  (`product-brief.md` § Scope, `data-model.md` — "the 41 legacy records are
  re-ingested through curation as new works"). This chunk owns it. Without it
  the new catalogue has no ready work by any built path until Chunk 18, and the
  display chunks below have nothing to put on the wall — which is why it sits
  here rather than late: **it is what makes Chunks 12–13's cutover acceptance
  executable.** Re-ingest, do not migrate: read `all.json` as an input file and
  mint fresh entities through the service layer, so every catalogue invariant
  from Chunk 08 applies to the seeded rows exactly as to discovered ones.

  **The index holds 41 records describing 40 works** *(measured 2026-08-01;
  the 2026-07-20 pass counted records and called them works)*. Two records are
  one painting — same URL, same master file, same title, differing only in
  `mat_hexrgb` (`#433735` and `#1c1818`). Seeding both would put one painting in
  the catalogue twice, which is what a minted identity exists to prevent, so they
  collapse to one work. *(Operator decision 2026-08-01: the later record in file
  order wins and the earlier colour is **dropped**, not retained as superseded
  history — the report names the discarded value so the choice stays visible.)*
  This also reconciles the "41 records but 46 files in the master tree" note in
  learnings: 40 referenced files plus 6 unreferenced ones, under $ART_ROOT on the
  Pi rather than anywhere in this checkout.

  **The corpus is complete on identity and incomplete on the label** — measured
  against the tracked `all.json`, not assumed. All 41 records carry `title`,
  `artist`, `date_created`, `raw_file`, `mat_hexrgb` and pixel dimensions. The
  gaps, **counted per work after parsing** *(corrected 2026-08-01 — the previous
  figures mixed units in one sentence: nationality and `artist_details` were per
  record, "8 have no lifespan" was per distinct artist)*: 8 of 41 records carry
  no `artist_details` at all, and the index's own parse leaves 14 works with no
  nationality. Reading the source's words rather than that parse recovers nine of
  those, leaving **5 works with no nationality, 9 with no birth year, and 2 each
  lacking medium and physical dimensions — different pairs, overlapping in one
  work.** A missing *death* year is not a gap: two of these artists are alive.

  That shapes the work: Artist parsing cannot assume `artist_details` exists and
  must fall back to the flat `artist` field, which for one record carries the
  whole clause; the label must render legibly with nationality and dates absent
  (data-model Q9 wants them, so a partial label is a real outcome, not an error);
  and the 2 works without physical dimensions **seed with dimensions null, are
  reported, and still reach the wall.** *(Corrected 2026-08-01: this said they
  "can get neither mat geometry nor a floor classification", and Chunk 09's built
  code says otherwise — `assess_display_fit` judges an original's **pixel** size
  against a box built from panel geometry and a mat width in inches, and reads
  nothing about the artwork's physical size. It also called this "the same
  unknown-dimensions case `data-model.md`'s `display_fit` note still owes a rule";
  that note owes no such rule. Physical dimensions are label text.)*

  **Backfilling from the source URL is out of scope here** — these works
  are re-fetchable, and completing them is discovery's job, not seeding's.
  Originals point at the existing masters, and renditions at the existing
  renders, in the deployed image tree under ART_ROOT — the raw and ready
  directories on the Pi, which are not part of this checkout — with
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
- **Deliverables:** a one-shot seeding path driving the curation service layer
  (invocable, re-runnable, and idempotent — re-running must not duplicate
  works, and must fill in whatever the tree did not hold last time, so the
  report names a problem the tool can also fix); the 40 works in the catalogue
  with artists, sources, originals, renditions, and mat colours; `MatColor.method`
  recorded as the legacy hand-tuned value, never as a fresh derivation; a report
  of anything that did not seed cleanly, per work with a reason — silence is not
  success
- **Tests:** unit — `artist_details` parsing across the corpus's real shapes
  (the multi-line "Charles Demuth\nAmerican, 1883–1935" form, the parenthetical
  form the index's own parser silently dropped, **and the 8 records carrying no
  `artist_details` at all**, which must fall back to the flat `artist` field
  rather than fail); a work with no physical dimensions seeds with nulls and is
  reported, never silently given a default size; identity is a UUID and no row
  carries a source URL as identity; no `tv_content_id` reaches the catalogue;
  idempotence — seeding twice yields 40 works, not 80, and does not grow the mat
  history by a row per run; integration — after seeding, a theme over all 40
  builds a manifest whose entries and exclusions together account for all 40,
  and a work whose render is missing from the tree is excluded by name and reason
  *(corrected 2026-08-01: this required the 2 dimensionless works to be the
  excluded ones, which contradicts the readiness rule Chunk 09 built — that rule
  asks for an original, a mat and a current render, and reads nothing about
  physical dimensions. Excluding them would take two works off the wall that are
  showing today.)*
- **Acceptance criteria:** all 41 records are accounted for — 40 works in the
  catalogue plus the one collapsed duplicate, named in the report with the mat
  colour it dropped; a theme built over them produces a manifest whose exclusions
  are exactly the works with a named, understood cause, never a silent drop;
  every work with incomplete label metadata is listed in the seed report, so the
  gap is visible now rather than discovered at the wall
- **Done when:**
  1. Acceptance criteria met and tests pass
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

### Chunk 10B: The first browser surface — catalogue, themes, manifest, health

- **Description:** The `/` and `/api/*` surfaces `architecture.md` has always
  drawn, built now over the services that exist rather than waiting for the ones
  that do not. **This is Chunk 19's scope, split — not new scope.** It takes the
  catalogue/theme/health third of 19's list and leaves the discovery two-thirds
  where they are. Scope: the work grid, image-forward, one card per work, with
  `display_fit` and rendered-inches labels and non-colour state indicators per the
  accessibility decision; a work detail view (metadata, artists, sources,
  renditions); themes (create, add/remove, reorder, activate); the manifest view —
  what the active theme's manifest contains and **every exclusion with its reason**,
  which is Chunk 09's exclusion report reaching a human for the first time; and the
  health panel, stating heartbeat age in absolute terms and reporting honestly that
  no heartbeat file exists yet, since the display plane arrives at Chunk 13.
  Thumbnail serving is a deliverable, not an assumption: the seeded renditions are
  4K files, and a grid of 41 of them is not a page. WCAG 2.1 AA baseline; UI chrome
  never competes with artwork for contrast.
- **Out of scope, deliberately, and named so it is not read as dropped:** intent
  entry and its estimate, the run view, the approval gate, cost display, and the
  review grid with alternates behind each card. Every one of those binds a service
  built in Chunks 14–18. They stay in Chunk 19.
- **Depends on:** Chunk 09 (themes and the manifest with its exclusion report),
  Chunk 10 (41 works with images on disk — a UI over an empty catalogue proves
  nothing), and the UI checkpoint, which moves here from before Chunk 19

**Four things this chunk had to settle before it could be built, recorded here
because each changes an artifact rather than only this chunk's code.**

*The artwork box needs two deployment values that were specified and never
surfaced.* `nonfunctional-requirements.md` § "The mat is geometric, and the floor
is physical" fixes the mat in inches and the floor as a minimum rendered size in
inches, and `Settings` carries neither — so `assess_display_fit`, built in Chunk
09 with tests, has **no production caller**, because nothing can construct the
`ArtworkBox` it takes. `MAT_WIDTH_INCHES` and `RESOLUTION_FLOOR_INCHES` join the
deployment surface here, defaulting to the reference panel's 2.5" and 12" — the
figures that artifact's own worked example uses. This is the chunk that first
needs the verdict, which is why it is the chunk that wires it.

*Pillow moves from Chunk 18 to here.* Thumbnail serving is a named deliverable
and the seeded renditions are 4K files; nothing in the standard library decodes
a JPEG, and `curation/src/curation/seed/images.py` reads only the SOF header for
dimensions precisely because it needed no decoder. Pillow was already the declared
acquisition/mat-engine dependency for this plane, so what changes is its arrival,
not the dependency set. Named rather than slipped in, by the same rule that made
`uvicorn`-not-`[standard]` a recorded decision.

*Thumbnails get a new derived directory in the image tree, named `thumbs`, and
the existing `tv-thumbs` is annotated rather than reused.* Both are directories
under `ART_ROOT` at runtime rather than anything in this checkout, which is why
they are named here without a path — the full contract, and the only normative
statement of it, is the `ART_ROOT` filesystem row in `boundary-patterns.md`. In
the 2024 tree, `tv-thumbs` holds images **downloaded from the television**, keyed
by `tv_content_id` — per-device TV state, which is exactly the class this
catalogue excluded by design; putting curation's own thumbnails there would
re-import the thing the model rejects. The new one is a derived,
device-independent cache and joins that contract as one, and the `tv-thumbs`
entry there is annotated the way the retired `label` entry was on 2026-07-20, for
the identical reason.

*The browser surface is the `/api/*` JSON API plus a client that renders it, not
server-rendered templates.* `architecture.md` already draws the UI and its HTTP
API as separate things and `project-state.yaml`'s FastAPI decision names "typed,
paginated, partial data — that is pydantic response models" as what the framework
was chosen for. Server-rendering the pages would leave `/api/*` either unused or
carrying a second shape of every read, which is the divergence the shared service
layer exists to prevent, one layer up. Pydantic is declared here, as that decision
anticipated ("the typed response models … arrive with the HTTP API"). No template
engine, no build step, no framework: the client is one stylesheet and one script.
- **Artifacts consumed:** `architecture.md` (§ Serves three surfaces from one ASGI
  app, § the internal-layering diagram), `api-contract.md` (§ the HTTP surface
  carries no stability obligation; § operation logic lives ONLY in the service
  layer), `security-model.md` (LAN-only, no authentication — the single-principal
  position is deliberate and already recorded),
  `design_decisions.accessibility_approach`
- **Visual change:** yes — the first human-facing surface this product has had
- **Deliverables:** real handlers in `curation/src/curation/http/` (thin bindings:
  unpack, call one service method, format), the pages above, a thumbnail path
- **Tests:** integration — every handler is dispatch + formatting over an existing
  service method, so the service-layer norm holds by construction; the flows
  exercised through the real HTTP surface against a booted server, per the suite's
  existing rule that surface work runs against real uvicorn, not an in-process
  transport
- **Acceptance criteria:** from a browser, touching no filesystem, no JSON and no
  SSH, a curator can see all 41 works with their images, build a theme, activate
  it, and read exactly why any work is absent from the resulting manifest; the
  health panel states observations with ages, never verdicts, and says plainly that
  the display plane is not running yet
- **Done when:**
  1. Acceptance criteria met and tests pass, plus the operator's look
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

**Contract enforcement (Chunk 11).** Pinned before the display plane and
discovery build against these surfaces.

### Chunk 11: Contract tests — MCP evaluation harness (issue #17)

**Split 2026-08-01. The plane-isolation half (issue #7) moved to Chunk 12, and
this is a descope recorded rather than a requirement dropped.** The premise
written here — that the display plane is a package this chunk could point a test
at, "the boundary now exists, from Chunk 06" — is false. Chunk 06 landed as
*curation only, display plane deferred*, and that package has never existed. The
only isolation test writable today would walk an empty tree and pass, which this
plan's own acceptance bar rejects in the next paragraph. Chunk 12 creates it, so
the test belongs to the chunk that gives it a subject; issue #7 is unchanged and
still open. The manifest-channel norm row was corrected the same day — it had
named this test as an existing Test mechanism, and never had one.

*(Paths in this paragraph are deliberately unfenced: the record lint reads a
backticked path in a chunk section as a claimed deliverable, and a descope
paragraph naming what this chunk is **not** shipping would otherwise report as
two missing deliverables.)*

- **Description:** The MCP evaluation harness, in the two halves the artifacts
  actually distinguish. `api-contract.md` § Validation is explicit that the
  contract tests assert the surface's *shape* while the harness asserts that a
  model can *use* it, and the shape half already landed with Chunks 07–09.
  So: (a) a **scenario runner** driving real product flows through the
  consolidated tools as a real MCP client, deterministic and in the default
  suite, where each step threads an id out of the previous step's envelope —
  the defect class no per-tool test can see, since two tools can each be correct
  and still disagree about what they hand each other; and (b) a **model-driven
  evaluation** behind a `llm_eval` marker, deselected by default, running
  verifiable operator prompts and measuring accuracy, call count and error rate.
  The split is not cost — it is that a model may legitimately reach a goal by a
  different route between runs, so it can measure but must not gate.
- **Depends on:** Chunks 07–09 (live tools to pin and real flows to drive)
- **Artifacts consumed:** `api-contract.md` § Validation and § Versioning,
  `boundary-patterns.md` § Test Levels, issue #17
- **Deliverables:** `curation/tests/contract/scenarios.py` (the runner: real
  client boot, transcript, envelope invariants checked on every call),
  `curation/tests/contract/test_mcp_scenarios.py` (first scenarios),
  `curation/tests/eval/` (driver + model-driven scenarios + the driver's own
  deterministic tests), the `llm_eval` marker and `eval` dependency group
- **Tests:** this chunk **is** tests; its own acceptance is that each guard
  demonstrably fails on a violation (a renamed tool, an over-budget description,
  a tool that echoes back a key its neighbour does not expect) — a green test
  that cannot catch a real violation is worse than none
- **Acceptance criteria:** scenario suite green against the real server and each
  guard proven able to fail by mutation; the model-driven suite deselected by
  default and skipping cleanly when its dependency group or API key is absent;
  the manifest-channel norm row no longer claims an enforcement artifact that
  does not exist
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
  rotate), 11 (the contract suite this plane's manifest reading is checked against)
- **Carries the plane-isolation test (issue #7), moved here 2026-08-01.** It was
  Chunk 11's, on the premise that a `display/` package already existed; it did
  not, and a test with no subject would have passed over an empty tree. **This
  chunk is where that package is born, so this is where the guard becomes
  writable — and it has to land with the package, not after it**, because the
  window in which display-plane code exists unguarded is exactly the window in
  which "just fetch the label text live" gets written and passes every test.
  Issue #7's design questions are settled as this plan frames them: "the display
  plane" is the `display/` package; imports are checked transitively (a
  direct-only check is evaded by one shared helper); the no-network-channel half
  bans HTTP client construction in display modules outright, with the TV
  websocket explicitly exempt because talking to the TV is display's job. Static,
  so it holds whether or not curation is running — which is the point, since a
  green suite is what a violation looks like without it. Both halves must be
  proven able to fail (plant a curation import; plant an HTTP client), issue #7's
  decisions recorded on the issue, and the manifest-channel norm row in
  `project-preferences.md` moved back from Critic to Test naming this file.
- **Carried from Chunk 09 — what an unsatisfiable pin does.** `show_now` refuses
  any work that is not *displayable* (widened at build 2026-07-31; see
  `api-contract.md`). It does **not** check *theme membership*, so a perfectly
  ready work that is simply not in the active theme can be pinned and the
  manifest's `entries` will not contain it. **That is the default path, not a
  rare race** — it is available on every call, and Chunk 09's own
  `test_the_directive_reaches_the_manifest` demonstrates it. The membership check
  was deliberately not added at the writing end, because only the display plane
  can decide what to do with a pin it cannot resolve. Answer it here: log one
  WARNING and continue rotating rather than stall or crash, by the same posture as
  a missing render file. Then say so in `api-contract.md` § How `art_display`
  reaches the display plane.
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

### Chunk 14A: `art_discovery` surface, run correlation, the search cap — no spend

- **Description:** Everything up to the engine seam, spending nothing. The eight
  `art_discovery` actions — `estimate`, `start`, `status`, `approve`, `decline`,
  `cancel`, `list_runs`, `spend` — over the `DiscoveryService` lifecycle Chunk 08B
  already built, driven by a **fake engine behind the narrow interface** 14B later
  implements for real. `start` returns a handle immediately (< 2 s); `status`
  long-polls ≤ 45 s; the work-count approval gate fires at **25**; `cancel` and the
  `interrupted` path already reconciled by Chunk 08 are exercised end to end.
  `estimate` ships with the arity-dependent behaviour `api-contract.md` now
  specifies, and is the one action on this tool that spends nothing.
  **Curation's structured log shape is owed here** and lands here: the plane emits
  plain formatted lines today, which is enough for startup, refusals and
  reconciliation and is not enough for per-run correlation
  (`observability-strategy.md` names discovery phase 1 as the owner rather than
  leaving the shape a property nobody holds — the artifact previously took it from
  `3tears-observe`, withdrawn with every other 3tears dependency on 2026-07-27).
  The fake is **not throwaway scaffolding**: it is the provider the integration
  tests run against, so it outlives this chunk.
- **Depends on:** Chunks 08, 11 (harness grows discovery scenarios)
- **Artifacts consumed:** `api-contract.md` (§ Long-running operations, § Error
  Model, § `estimate` answers two different questions),
  `nonfunctional-requirements.md` (§ Performance, § Cost Constraints),
  `observability-strategy.md` § Correlation, `data-model.md` (DiscoveryRun,
  SpendRecord)
- **Deliverables:** the eight actions live over MCP; the engine interface itself
  and a fake implementing it; curation's structured logging with `run_id` on every
  line emitted during a run, bound so that no call site can forget it; the
  **approval threshold (25)**, the **flat phase-1 search allowance** and the
  **per-work phase-2 component** as deployment values in `config.py` and
  `.env.example`; the **provisional `work_dedup_key`** derivation at one
  implementation site, marked provisional and named as Chunk 15's starting
  hypothesis; harness scenarios for the run lifecycle
- **Tests:** unit — gate threshold recorded per run (`approval_required` stored,
  not re-derived), `estimate` at both arities, cap enforcement as a distinguishable
  outcome rather than a silent truncation; integration — full lifecycle against the
  fake, including `halted_by_budget` vs `failed` vs `interrupted` as the fake can
  produce them; contract — an agent can distinguish those three by returned state
  alone; a log line emitted inside a run carries its `run_id`
- **Acceptance criteria:** every action is callable over real MCP and drives the
  real service; a run crosses the gate at 25 works and waits; `estimate` returns a
  phase-1 figure with no run id and the stored phase-2 figure with one; no code
  path in this chunk can reach the network
- **Done when:**
  1. Acceptance criteria met and tests pass
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

### Chunk 14B: Discovery phase 1 — the client, the engine, the ceiling (issue #12)

- **Description:** The real thing behind 14A's seam: an OpenRouter client written
  to the shapes `openrouter-api-findings.md` measured, and the phase-1 engine that
  turns an intent into an enumerable work list. Phase 1 can search the web when the
  intent is recency-bound (issue #12) — a text-only call cannot enumerate works
  past the model's cutoff, and finding works the curator could not have named is
  the product's definition of discovery; those searches count inside the per-run
  search cap and the pre-run estimate. **Cost visibility is a named deliverable
  here, not a norm** (`nonfunctional-requirements.md` § Cost visibility records
  that it must survive as one): the estimate before, the actual after
  (provider-reported), on every surface equally. Cost comes from **inline
  `usage.cost`** with `usage: {"include": true}` — not from a second request, and
  not computed as tokens × price, which would omit the web-search fee that can
  double a run. Spend records attribute per category; the provider's refusal lands as
  `halted_by_budget`, distinguishable in logs and tool results; budget remaining
  reads `GET /api/v1/key`, which **lags by minutes and may therefore never gate a
  run** — display only.
- **Settled at build (2026-08-02), each recorded where its rule lives:**
  - **"Recency-bound" is not decided at all — every run searches.** A trigger
    fails in the one direction the product cannot detect: a missed recency-bound
    intent returns real but pre-cutoff works with nothing marking them stale.
    Demonstrated on the default model, which without the plugin answered *"No
    major art prize has been awarded in 2026 as of 2025"*. The flat $0.005 per run
    is $0.30–0.90 a month against a $20 ceiling, and grounding a non-recency
    intent suppresses invented titles rather than wasting money. Rationale lives
    in `curation/src/curation/discovery/phase_one.py`'s module docstring.
  - **`DiscoveryRun.strategy` is written by the engine** when the work list
    settles — it is the model's own account of how the intent was read, so it
    cannot exist before the intent has been read (`data-model.md`).
  - **The phase-1 allowance stays at 10.** The measurement it waited on came back
    the useful way: the web fee is **per request, flat across one, three, five and
    ten results**, so the cap counts the right unit at the right price and its
    recorded derivation stands unchanged (`nonfunctional-requirements.md`).
    Breadth being free is why `DISCOVERY_SEARCH_RESULTS` ships at 10; the engine
    makes one request and so spends 1 of the 10.
- **Depends on:** Chunk 14A (the seam and the surface), Chunks 08, 11
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
  is no ceiling at all. Then: a first-party OpenRouter client behind 14A's
  interface (**not** `threetears.models.create_chat_model` — decided 2026-08-02,
  reasoning in `openrouter-api-findings.md`); new
  `curation/src/curation/discovery/` phase-1 engine; the **phase-1 model as a
  deployment value defaulting to `deepseek/deepseek-v4-flash`**, with
  `google/gemini-3.5-flash-lite` carried as the named alternative for Chunk 15's
  spike to measure at ~2.9× the token cost; `SpendRecord` rows carrying the model
  id actually used
- **Tests:** unit — the client's parsing of `usage.cost`, `cost_details` and
  search `annotations` against recorded fixtures; the recency-bound trigger,
  whichever form it takes; integration — a real run end to end against the live
  API on the capped key; contract — an agent can distinguish "out of money" from
  "fetch failed" from "restarted underneath" by the returned state alone.
  **A live re-verification test replaces the findings file's prose**, per the
  project rule that a verification worth writing down is usually worth keeping:
  prices and endpoint shapes both move, and the durable form is a test
- **Acceptance criteria:** a real intent resolves to a work list with a shown
  estimate; a recency-bound intent ("recent award-winning art") resolves to
  real, post-cutoff works; the curator can trim the list before paying for
  phase 2; **the ceiling is proven to fail closed, not assumed to.** The provider
  half of that is now *done* — a throwaway key was driven to exhaustion 2026-08-02
  and both refusal shapes are recorded in `openrouter-api-findings.md`. What
  remains for this chunk is the client half: the exhaustion **403** surfacing as
  `halted_by_budget`, and the affordability **402** *not* doing so, since it
  arrives with credit remaining and means "ask for less" rather than "stop"
- **Done when:**
  0. ~~verify-api~~ — **done 2026-08-02, recorded in `openrouter-api-findings.md`.**
     `limit_remaining`, the generation `cost` shape and the web-plugin invocation
     format are captured from the live API. Three results change the client's
     design and are not restatements of what was expected: per-call cost arrives
     **inline** via `usage: {"include": true}` (the `GET /api/v1/generation`
     route this step assumed returned 404), `usage.cost` **includes the web-search
     fee** (so a tokens x price computation would under-report by exactly the
     component that can double a run), and `/key` **lags by more than a minute**,
     which makes it sound for displaying remaining budget and unsound for any
     in-run guard. Still outstanding from this step: the recorded prices have not
     been re-verified against `/models`. **The key gaps closed 2026-08-02 in a
     second probe round** on this product's own keys: `limit_reset` reads
     `"monthly"` on the real $20 key, and the over-limit path was driven on a
     throwaway. It overturned this plan's assumption — exhaustion is a **403**,
     while the **402** is a pre-flight `max_tokens` affordability check that
     arrives with credit still available. The client must set `max_tokens`
     deliberately or it will be refused at full credit
  1. Acceptance criteria met and tests pass
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

### Chunk 15: Spikes — search-engine choice and `work_dedup_key` derivation (issue #18)

- **Description:** Two build-time spikes the artifacts explicitly hand to this
  plan, run against Chunk 14B's real output rather than synthetic data. The
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
- **Depends on:** Chunk 14B (the spike measures real phase-1 output, and the model
  tier is one of the things it measures — `deepseek/deepseek-v4-flash` against
  `google/gemini-3.5-flash-lite`, alongside the search-engine comparison). Its
  regression measurements pin an explicit model snapshot rather than the floating
  default, so an alias moving underneath them cannot read as a quality regression
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
- **Depends on:** Chunks 14B, 15 (the engine and the dedup key are decided)
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
  `rejected_at`. **The verdict rules and the promotion itself already landed in
  the service layer with the discovery entities** — minting the Artwork and
  turning CandidateImages into Sources (selected → `is_primary`) — so what this
  chunk owes is the tool surface over them **plus the one piece promotion still
  leaves out: the artist.** `proposed_artist` is free text that has to be parsed
  and matched against existing Artist rows, which is the same normalisation
  problem as `work_dedup_key`; until it is done an accepted work carries no
  `artist_id`, and **Q9 — who is the artist, for the physical label — has no
  answer for anything discovery accepted.** The preview-file lifecycle decision that `boundary-patterns.md` leaves
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
- **Tests:** unit — the artist is parsed, matched to an existing row where one
  fits, and reaches the accepted work (Q9 answerable for a discovered work, which
  it is not before this chunk); promotion mirrors the candidate shape into the
  catalogue shape end to end through the tool; suppression scopes never share a
  key (Q3 vs Q11, both directions);
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

### Chunk 19: Curation web UI and HTTP API — the discovery half

- **Description:** The rest of the browser surface, built **onto Chunk 10B's**
  rather than standing one up: same thin HTTP bindings over the same service layer
  (typed, paginated, partial data — the recorded reason the UI does not ride MCP),
  same design decisions, same accessibility baseline. What 10B could not build
  because the services did not exist yet: intent entry with the estimate at the
  point of decision; the run view (status, work list trimming, approval gate, costs
  before and after); and the review grid (image-forward, one card per work,
  **alternates behind it** — 10B's grid shows accepted works only, with no
  alternates to stack). It also completes the health panel 10B started, adding
  `limit_remaining` and backup age (fed by Chunk 20).
  **What 10B already delivered — the work grid, work detail, themes, the manifest
  view with its exclusion reasons, and heartbeat age — is not rebuilt here.**
  The pre-UI governance checkpoint disposed issues #2 (design system) and #10 (MCP
  second-look shelf) before 10B; if #2 was settled as one-off CSS with a recorded
  revisit, this is the chunk that revisits it, since it is where the surface stops
  being small.
- **Depends on:** Chunk 10B (the surface it extends), Chunks 14–18 (every
  operation it newly binds), 13 (heartbeat to display)
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
- **Before Chunk 10B** — the UI checkpoint, moved here from before Chunk 19 on
  2026-07-31 when the first browser surface was re-sequenced forward: dispose
  issue #2 (design system now, or accept one-off CSS with a recorded revisit) and
  issue #10 (second-look shelf in scope or explicitly deferred); confirm the UI
  scope still matches what the built product needs. It runs once, before the first
  surface exists — Chunk 19 inherits its dispositions rather than re-opening them,
  except for a #2 revisit that was explicitly deferred to it.

  **Held 2026-08-01. Three dispositions, all recorded on the issues themselves.**

  *Issue #2 — tokens now, component inventory deferred to Chunk 19.* The issue's
  own sequencing question was system-first versus extract-from-the-first-screen,
  and neither answer is available whole: its acceptance list asks for components
  covering the candidate review grid and intent entry, and both of those screens
  belong to chunks whose services do not exist — which is why the issue's own
  stage is `design` rather than `ready`, with `information_architecture` and
  `interaction_patterns` still empty. So the half that can be decided against a
  real screen is decided now and the half that cannot is not guessed at. **In
  scope here:** the token layer (colour, type scale, spacing, radius, elevation),
  light and dark handling, AA contrast verified against the token set, and the
  non-colour state indicator — every decision that ad-hoc CSS would otherwise
  make silently and that a later screen would then inherit. **Not in scope:** a
  component inventory for screens that are not specified. #2 stays open at
  `design`; its revisit is the deferral this checkpoint was allowed to make.

  *Issue #10 — deferred to Chunk 19, and the deferral is forced rather than
  chosen.* The shelf shows works accepted **over MCP** awaiting a human look.
  `art_review` is declared in the tool registry and unbuilt (`_UNBUILT`), so no
  work can be accepted over MCP at all; a shelf built now would be a surface with
  no producer, which is the defect shape this repo has already recorded twice
  (`display_fit.upscaled`, `Rendition(kind='label')`). It becomes buildable when
  acceptance does, in Chunk 17.

  *UI scope still matches what the product needs* — with one correction the
  checkpoint exists to catch. Chunk 10B's grid is specified to carry `display_fit`
  and rendered-inches labels, and **`assess_display_fit` has no production caller
  today**: nothing anywhere constructs an `ArtworkBox`, because the mat width and
  the resolution floor were specified in `nonfunctional-requirements.md` as
  deployment values and never added to the deployment surface. That is settled in
  the chunk entry rather than here.
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
  at the pre-UI checkpoint (now before Chunk 10B), not silently included or
  dropped now.
  `security-model.md` records #10 as "filed as backlog work, not committed
  design".
- **Ambient adaptation beyond the ported brightness loop** (auto art-mode
  scheduling, weather-aware brightness) — the brief's Later list.
- **MCP resources** — decided no for v1 (additive later; recorded 2026-07-20).
- **3tears relaxation to 3.13** — off this product's path entirely
  (`operational-spec.md`); an upstream concern.
- **Multi-account, multi-TV, HA, concurrent runs** — accommodate-only per the
  brief; designed around, not built.
