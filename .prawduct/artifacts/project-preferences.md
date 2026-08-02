# Project Preferences

Developer preferences for how code is written in this project. Captured during discovery, updated as preferences evolve. Every session should read this before writing code.

> **Status: inferred from the existing codebase on 2026-07-19, not yet confirmed by the
> owner.** Every entry below marked _(inferred)_ is a vetoable assumption. Entries marked
> _(target)_ are norms the existing 2024-era code does **not** yet meet — they bind new and
> touched code, and the gap is tracked in "Known departures" below rather than papered over
> by weakening the norm.

## Language & Runtime

- **Language**: Python _(inferred — all 13 modules are `.py`)_
- **Version**: **per plane, not one number** (corrected 2026-07-20 — this previously
  read "target 3.13, floor 3.12" for the whole product, which had been true before
  the two-plane split and was the fourth site where a superseded version claim
  outlived its amendment).
  - **Display plane: 3.13**, floor 3.12. Raspberry Pi OS Trixie ships 3.13, and the
    IT8951 e-paper driver compiles Cython from 2023 sources targeting 3.13/3.12.
    This is the plane whose version is pinned by hardware.
  - **Curation plane: 3.14**, **settled 2026-07-20; rationale re-based 2026-07-27** —
    this read "required by nothing except `3tears`", and the catalogue no longer
    depends on `3tears` core at all. What holds the floor now is `3tears-models`,
    the operator's own model adapters that the discovery work calls and which
    declare the same floor — plus the verified fact that the whole curation
    dependency set resolves and imports on CPython 3.14.4. Provisioned
    as a uv-managed standalone build (`uv python install 3.14`), not compiled: a
    prebuilt `cpython-3.14-linux-aarch64-gnu` exists, so the "30–45 minute source
    build per patch release" that made this an open question was never the real
    price. See `operational-spec.md` § The Curation Interpreter.
  - _(Resolved 2026-07-27: this said `pyproject.toml` "still declares
    `target-version = ["py312"]` and matches neither plane". The sibling-project
    split gave each plane its own.)_
  See [learnings.md](../learnings.md) § Platform and dependencies.
- **Package manager**: pip against a pinned `requirements.txt` _(inferred)_. `pyproject.toml`
  exists but carries only black config — there is no project/dependency table, so the repo is
  not an installable package. **DECIDED 2026-07-20: uv for both planes**, structured as
  two **sibling uv projects** so each plane carries its own interpreter and its own
  lock. _(AMENDED 2026-07-20: this said "a uv workspace". A workspace has one lockfile
  and one resolved interpreter across all members — verified against uv 0.11.8, where a
  workspace mixing `>=3.14` and `==3.13.*` refuses to lock at all: "Found conflicting
  Python requirements". The per-plane interpreter and per-plane lock were always the
  substance; only the mechanism is corrected.)_ uv was already required on the Pi to provision curation's interpreter, so it is
  the incumbent rather than a new dependency, and `uv.lock` gives real lockfiles while
  preserving the exact pinning `requirements.txt` has today. **Named verification item:**
  IT8951 compiles Cython from 2023-era `.pyx` sources, and a `setup.py` of that vintage
  may not declare Cython in build-requires — which PEP 517 build isolation would then not
  provide. This is **adjacent to but distinct from** the existing "IT8951 build is
  unverified" risk in `platform-and-dependency-findings.md`, which is about the
  interpreter version rather than the build frontend; an earlier draft claimed it folded
  into that risk, which overstated the coverage. **Tracked as issue #9.** A single
  `target-version` still cannot describe both planes; that is settled by the workspace
  split, not by picking a number.

## Code Style

- **Naming**: `snake_case` functions and module-level names, `PascalCase` classes
  (`ArtFile`, `ArtSet`, `DisplayLabel`, `ResizeOptions`) _(inferred — consistent across all modules)_
- **Formatting**: black, `line-length = 130` (configured in `pyproject.toml`)
- **Linting**: ruff, configured per plane. Both select `E,F,I,UP,B,T20,TRY` at
  `line-length = 130`. The two configs differ, and the differences are the norm:
  - **Root** (`pyproject.toml`, excludes `curation/` and `display/`) also ignores
    `TRY400` and `TRY003` project-wide, and carries a per-file carve-out over
    eleven files of two kinds. Eight are 2024 wall modules waiving `T20`,
    `E501`, `F841`, `TRY002`, `TRY201`, `TRY300`, `B007` (plus `E402` on
    `art.py` and `display.py`); their carve-out has a scheduled end date — they
    are deleted once both planes exist. Three are hand-run operator tools
    (`spi_test.py`, `remote_test.py`, `urls_to_json.py`) waiving only `T20`,
    `E501`, `F841` and — on `spi_test.py` — `E402`, because `print()` is their
    output rather than logging; nothing schedules these for deletion, so their
    waiver is permanent until someone argues otherwise. Within the whole
    carve-out the deliberate holds are `B006` and all of `F` **except `F841`**
    (assigned-but-never-used, waived in all eleven); the unbound-name class that
    produced real defects here still fails the build. `config.py` is excluded
    from the carve-out and held to the strict set.
  - **Curation** (`curation/pyproject.toml`) adds `ANN`, ignores `TRY003`, and
    turns `ANN` off under `tests/*`. No legacy carve-out: this plane is new code.

  The mechanical style norms below that ruff covers are enforced by it rather than
  by the Critic.
- **Type annotations**: currently sparse and inconsistent — `image_utils.py` annotates 8
  return types, six modules annotate none, and `art.py` mixes bare class attributes with
  annotated `__init__` params. _(target)_ Annotate every new or touched function signature.
- **Imports**: absolute, one module per line, stdlib-then-third-party-then-local **loosely**
  grouped — `art.py` and `ai.py` interleave `config` with third-party imports. _(target)_
  Group strictly: stdlib / third-party / local, blank line between.
- **Logging vs print**: `logging` is configured in `art.py` and `tvart.py`, but `print()` is
  used for operational output throughout (`ai.py`, `display.py`). _(target)_ `logging` only;
  `print()` is reserved for deliberate CLI output.

## Testing

- **Framework**: pytest, one suite per plane — `tests/` at the root for the 2024
  modules, `curation/tests/` for the curation plane, each on its own interpreter.
  Both are declared as `test_commands` in `project-state.yaml` so the evidence hook
  runs the real invocations rather than a default that resolves neither.
- **Style**: descriptive test names stating the behaviour under test.
- **Coverage expectations**: _(target)_ happy path + error cases for pure logic
  (`image_utils`, `metadata` parsing, `source_utils`, the `all.json` catalogue round-trip).
  Hardware and network paths are covered behind interfaces, not by hitting a real TV.
- **Testing strategies**: _(target)_ plain example-based tests; the network (museum APIs,
  OpenAI, the TV websocket) and the e-paper panel are mocked at their module boundary.
- **Test location**: _(target)_ `tests/` mirroring the module layout.
- **Parallelization**: not applicable at this size.

## Architecture Patterns

- **Data modeling**: hand-rolled classes with `to_json`/`from_json`-style methods
  (`ArtFile`, `ArtSet` in `art.py`), persisted to `all.json` _(inferred)_. The catalogue's
  known defects — identity keyed on source URL, per-device state mixed into the record,
  semi-structured `artist_details` — are recorded in [learnings.md](../learnings.md)
  § Known problems in the existing index.
- **Error handling**: exceptions, with one custom domain exception (`DownloadError` in
  `art.py`) _(inferred)_. _(target)_ Catch specific exception types; a genuinely necessary
  broad catch carries `# prawduct:allow prawduct/broad-except -- reason`.
- **Async**: `asyncio` at the TV boundary only (`tvart.py`, driven by `samsungtvws`'s
  `SamsungTVAsyncArt`); everything else is synchronous _(inferred)_. _(target)_ Keep it that
  way — async at the I/O boundary, sync core.
- **File organization**: flat — 13 modules at the repository root, no package directory
  _(inferred)_. _(target)_ Decide during discovery whether to keep flat or move to a package;
  flat is defensible at 2,216 lines but the hardware and TV boundaries need real interfaces
  regardless (see learnings § Platform and dependencies).

## Tooling

- **Key libraries**:
  - `samsungtvws` — pinned to a **git SHA on a fork** (`NickWaterton/samsung-tv-ws-api`),
    not PyPI. This is the TV control surface.
  - `omni-epd` (`display.py`) — e-paper driver, dormant upstream since 2024-11. Not in
    `requirements.txt`; installed out-of-band on the Pi.
  - `pycairo` + `PyGObject`/Pango (`art.py`) — label typesetting. System-level GTK
    dependencies, not pure-Python wheels.
  - `openai` (`ai.py`) — mat-colour selection, currently calling `gpt-4o`. Real per-call spend.
  - `dezoomify` (external binary, configured in `config.py`) — tiled high-res image fetch.
- **Dev commands**: `python tvart.py [--flags]` is the entry point for the 2024 modules.
  **Established 2026-07-27** and current: `pytest tests` / `ruff check .` / `black .` at the
  root, and `uv run pytest` / `uv run ruff check .` / `uv run black .` in `curation/`.
  _(This read "There is no test, lint, or format command wired up"; both departures were
  closed the same day.)_
- **`requirements.txt` vs `r`**: `requirements.txt` is the hand-maintained direct-dependency
  list (18 entries). `r` is an extensionless **`pip freeze` capture from the Pi's venv** (60
  entries) — it is the only record of the full transitive set that actually ran, including
  four git-sourced packages absent from `requirements.txt`: `IT8951` (pinned to `9f13613`),
  `omni_epd`, `waveshare-epd`, and the `inky`/`spidev`/`RPi.GPIO` hardware stack. Treat it as
  a recovered lockfile, not scratch — it is evidence, and it should be renamed to say so.
- **Configuration**: everything deployment-specific reads from `.env`. **Hoisted 2026-07-27**
  — the TV's address and port, the art root, and the geographic coordinates all left source
  along with the secrets that were already there, and a test now fails on any of them
  reappearing. _(This read "everything else hardcoded as module constants in `config.py`
  including the TV's IP address, the art root `/home/tvpi/art`, and geographic coordinates",
  which the same chunk that hoisted them made false.)_ See learnings § Data and cache contract.

## Workflow

- **Branching**: feature-branches (default: feature-branches — create a branch for medium+ work, direct commits to protected branches only for trivial fixes; set to "direct" for solo projects where committing to main is OK)
- **Protected branches**: main, develop (branches that should not receive direct commits unless branching is "direct")
- **PR creation**: wait_for_user (default: wait_for_user — only create PRs when explicitly asked; set to "automatic" to create PRs after Critic review passes)
- **PR merge**: wait_for_user (default: wait_for_user — present the PR for user review before merging; set to "automatic" to merge after CI passes and review is clean)
- **PR merge strategy**: merge commit (default: merge commit — `gh pr merge --merge`; preserves each commit's identity so a reused branch's merge-base stays correct and the review/PR gates don't re-review already-merged work; set to "squash" for one linear commit per PR, or "rebase" — with either, branches are single-use: delete after merge and never reuse, because the rewritten history strands a reused branch's merge-base)
- **Commit attribution**: none (default: none — no `Co-Authored-By`, `Signed-off-by`, or "Generated with …" trailers on commits or PR bodies; set to "co-authored" to add a Claude `Co-Authored-By` trailer)

---

**What belongs here**: How you want code written. Conventions, tools, style preferences, workflow preferences.

**What doesn't belong here**: What to build (product-brief), system design (data-model, architecture), performance targets (nonfunctional-requirements), or deployment (operational-spec).

## Enforcement

Each preference above should be enforced by one of three mechanisms — assign the mechanism when you add the preference so it doesn't quietly become aspirational.

| Mechanism | Where it lives | What it catches | Trade-off |
|---|---|---|---|
| **Linter** | Project's configured linter (ruff, eslint, swiftlint, etc.) | Mechanical style/naming rules | Best tool when configured. If no linter, preferences in this category fall through to Critic. |
| **Test** | `tests/preferences/test_*.py` (or equivalent) | Structural rules with named exceptions (AST checks, config-presence checks) | Bakes the rule into CI; refuses to be silent. Cost: re-validate when the rule's shape changes. |
| **Critic** | `/critic` review (Goal 4: Norms) | Judgment-required rules (semantic naming, "appropriate" anything, what counts as a "boundary") | No false-confidence test. Cost: requires reviewer per chunk; misses violations between reviews. |

This per-preference table is the product's **norm index** (`/prawduct:methodology norms`): each row assigns a norm its **mechanism** (linter / test / Critic) and its **audit home** — `janitor` (only the deep sweep sees it) or `advisory` (a mechanical probe fires on it). A row may be a **pointer** to a `## Direction` section instead of restating the norm, and every norm carries its **why** (a whyless norm is unenforceable at its edges).

| Preference / norm | Mechanism | Enforcement artifact | Audit home | Why |
|---|---|---|---|---|
| black formatting, line-length 130 | Linter | `pyproject.toml` `[tool.black]` | janitor | Already configured; removes formatting from review entirely. |
| snake_case functions, PascalCase classes | Critic | — | janitor | Ruff landed 2026-07-27 and `N` was **deliberately not selected**: the 2024 modules would fail it in bulk on names that are load-bearing at call sites, and a rule that has to be waived everywhere teaches people to waive rules. Stays with the Critic; revisit when the legacy modules are retired. |
| Strict stdlib / third-party / local import grouping | Linter | ruff `I`, both `pyproject.toml`s | janitor | Mechanical; it should not cost review attention, and since 2026-07-27 it does not. |
| `logging` only; `print()` reserved for deliberate CLI output | Linter | ruff `T20`, both `pyproject.toml`s. **Two distinct carve-outs, plus the norm's own stated exception**: the three hand-run operator tools (`spi_test.py`, `remote_test.py`, `urls_to_json.py`), where `print()` *is* the output and the rule does not apply; eight legacy modules (`ai.py`, `art.py`, `display.py`, `image_utils.py`, `local.py`, `metadata.py`, `source_utils.py`, `tvart.py`) where it is debt with a scheduled end date; and, in new code, a hand-run command whose report is the reason for running it — waived per line as `# noqa: T201 -- <reason>`, never per file | janitor | This runs unattended on a Pi under systemd; `print()` output has no level and no timestamp, so failures are invisible in the journal. **The second carve-out includes modules the Why is precisely about** — `tvart.py`, `display.py` and `local.py` all run unattended — which is why it is a dated waiver and not an exemption. *(Corrected 2026-07-27: this row described one carve-out for "the legacy CLI entry points", which is not what the eight-module set is; a reader checking the waiver against the norm would have concluded the daemon was out of scope.)* *(Extended 2026-08-01: "reserved for deliberate CLI output" always permitted a hand-run command; nothing said how to express it in new curation-plane code, which has no per-file ignore and should not gain one. Per-line keeps the waiver next to its reason and keeps the rest of the module under the rule — the seeding command is the first case, and its report is a value its callers can assert on, so only the printing is waived, not the reporting.)* |
| Type-annotate every new or touched function signature | Linter (new code) + Critic (legacy) | ruff `ANN` in `curation/pyproject.toml`; not selected at the root | janitor | Split deliberately 2026-07-27: the curation plane is all new code and is held to the rule mechanically, while annotating on touch converts the 2,216-line untyped legacy tree incrementally rather than by a stop-the-world pass. Promote the root when the ratio is high enough to be worth failing on. |
| Catch specific exceptions; broad catch needs `# prawduct:allow prawduct/broad-except -- reason` | Critic | — | advisory | A swallowed exception in an unattended loader shows up as "the TV just stopped changing", with nothing in the log to say why. *(Corrected 2026-08-01: this row claimed Mechanism "Critic + linter" and Enforcement artifact "ruff `B`/`TRY`, both `pyproject.toml`s". **Neither rule set flags `except Exception:`** — bugbear has no blind-except rule and every selected `TRY` rule is about raise or log shape. The rule that would is `BLE001`, and `BLE` is selected nowhere here, so the norm has been Critic-only since it was written while the index said otherwise. The live proof is that `ruff check .` is green over every unwaived `except Exception` in the root plane — among them `tvart.py`'s inside `upload_file`, which logs and swallows in the unattended loader this row's Why is about. Selecting `BLE` is not a one-line fix and is why this is a correction rather than a repair: the sanctioned waiver is a Prawduct pragma, not a ruff directive, so `BLE` would fail the correctly-waived catches alongside the unwaived ones, and needs a paired `# noqa: BLE001` convention written into this row. **The two planes are not in the same position** — curation is new code whose only broad catch is already waived, so it can take `BLE` for the cost of one paired `noqa`; the root plane's unwaived catches are all in modules scheduled for deletion at the legacy retirement, which is a per-file ignore with a dated end rather than a waiver each. Tracked as issue #33.)* |
| No hardcoded deployment values in source (IP, art root, coordinates) | Test | `tests/test_config.py::test_no_source_file_carries_a_deployment_value` | advisory | The same code runs on the Pi and on a dev Mac; a hardcoded `/home/tvpi/art` means the dev path is a source edit, which is how config drift starts. |
| Async at the I/O boundary, synchronous core | Critic | — | janitor | `samsungtvws` forces async at the TV edge only. Letting it spread makes the image and metadata logic untestable without an event loop. |
| Hardware + network access sits behind an interface | Critic | — | janitor | Both display drivers are dormant upstream and one is unpinned; an interface keeps a frozen 2023 driver from dictating the project's Python version (learnings § Platform and dependencies). |
| No secret ever reaches a log line | Critic | — | advisory | Added 2026-07-27; it was stated in `security-model.md` and had no row here, so nothing assigned it a mechanism and nothing looked for it. The repository is public and the journal is read over someone's shoulder during a failure — which is exactly when logging is turned up. Judgment-required: the violation is usually a whole object logged for context whose repr happens to include a token, not a literal secret in a format string. |
| **Operation logic lives ONLY in the service layer; MCP tools and HTTP handlers are thin bindings** — norm lives in `architecture.md` § Direction | Critic | — | janitor | Ratified by the owner 2026-07-20. Judgment-required: a handler that validates, orders, or decides is the violation; one that unpacks arguments, calls a single service method, and formats the result is the norm. Rationale and retroactivity check live with the norm. |
| **Spend ceilings are provider-enforced, never application-enforced** — norm lives in `nonfunctional-requirements.md` § Direction | Critic | — | janitor | An application meter that fails open is indistinguishable from one that works — no error, no alert, just a bill. This codebase has already shipped that exact defect shape (`upload_file` reports success on failure). Judgment-required: the violation is "this code path is the only thing stopping the bill", which no pattern match can see. |
| **The display plane never requires the curation plane to be reachable** — norm lives in `nonfunctional-requirements.md` § Direction | Critic | — | janitor | The availability asymmetry is the entire structural justification for the two-plane split; a display plane that phones home has paid the split's costs and kept none of its benefit. Judgment-required: a new call to the curation host is only a violation depending on whether rotation can proceed without it. |
| **WCAG 2.1 AA on the curation UI, and colour is never the sole carrier of state** — decision lives in `project-state.yaml` § `design_decisions.accessibility_approach` | Test | `curation/tests/unit/test_design_tokens.py` | advisory | Added 2026-08-01 with the first browser surface. The contrast half is fully mechanical: the test reads the real token values out of the served stylesheet, computes every text and control pair in both colour schemes, and refuses any colour written outside the token blocks — so "AA verified" cannot rot into a sentence with nothing under it. The non-colour half stays judgment-required: a test can see that a badge has a glyph, not that the glyph distinguishes anything. |
| **The theme manifest file is the only channel from curation to display** — norm lives in `architecture.md` § Direction | Critic | — | advisory | The mechanical form of the availability norm above, and the one that *can* carry a real rail: an AST/import check that display-plane modules import no curation module and open no HTTP client to the curation host. The violations this guards against ("just fetch the label text live") work perfectly in development and in every test, because curation is up in development and in every test — so a green test suite is exactly what a violation looks like without this check. **Corrected 2026-08-01: this row named `tests/preferences/test_plane_isolation.py` as an existing Test mechanism, and no such file has ever existed.** It could not have: the check's subject is the `display/` package, which Chunk 06 deferred and nothing has created since, so the only test writable today would pass over an empty set — the "green test that cannot catch a real violation" this table's own guardrail rejects. Enforcement is Critic judgement until the display plane exists; the test is a deliverable of the chunk that creates it, and this row moves back to Test then. |

### Known departures (existing code, not yet conforming)

These are real gaps, not exemptions. They are listed so no future session mistakes the
current state for the norm — and so nobody "fixes" the mismatch by weakening a norm.

| Departure | Where | Disposition |
|---|---|---|
| ~~No test suite at all~~ | ~~whole repo~~ | **Closed 2026-07-27.** pytest established per plane; both suites declared as `test_commands`. |
| ~~No linter~~ | ~~whole repo~~ | **Closed 2026-07-27.** ruff configured at the root and in the curation plane; the mechanical norms it covers moved from Critic to lint rules. |
| `print()` used for operational output | Eight legacy modules; see the `T20` row above for the list | **Disposition changed 2026-07-27: dies with the 2024 modules at Chunk 20, not converted on touch.** "Convert on touch" had no mechanism behind it — all eight were touched during the 07/08 bundle and 19 `print()` calls stayed, so the stated disposition was describing something nobody was doing. The two honest options were a ratchet that fails the build on a touched file, or an end date; the modules are deleted at Chunk 20 and their replacements log from the first line, so the end date is the proportionate one. |
| ~~Deployment values hardcoded~~ | ~~`config.py` (`tv_address`, `base_folder`, lat/long)~~ | **Closed 2026-07-27.** All three hoisted to `.env`; `tests/test_config.py` fails on any of them returning to source. |
| Sparse type annotations | 6 of 13 modules have none | Annotate on touch. |
| ~~`pyproject.toml` declares a single `target-version = ["py312"]` for a two-plane product~~ | ~~`pyproject.toml`~~ | **Closed 2026-07-27.** The sibling-project split gave each plane its own `pyproject.toml`, so each carries its own target rather than one setting trying to describe both. |

**Rule for adding a new preference:** assign a mechanism. If the preference can be expressed as "every file/function/config matches pattern X with named exceptions" → write a test. If a linter rule already exists for it → configure the linter. If it requires understanding intent → assign to Critic. Never leave a preference unassigned.

**False-confidence guardrail:** if a generated test would pass on conforming code but couldn't reliably catch a real violation (e.g., greppy heuristics for semantic rules), prefer Critic over a weak test. A green test that doesn't actually check the rule is worse than no test.
