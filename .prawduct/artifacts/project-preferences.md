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
  - **Curation plane: 3.14** as currently decided — required by nothing except
    `3tears`, whose `requires-python = ">=3.14"` the 2026-07-19 audit found
    removable in 16 mechanical sites. **This is an open question**, not a settled
    preference: Trixie ships 3.13, so 3.14 on the Pi means a 30–45 minute source
    build per patch release. See `operational-spec.md` § The Python 3.14 Problem.
  - `pyproject.toml` still declares `target-version = ["py312"]` and matches
    neither plane.
  See [learnings.md](../learnings.md) § Platform and dependencies.
- **Package manager**: pip against a pinned `requirements.txt` _(inferred)_. `pyproject.toml`
  exists but carries only black config — there is no project/dependency table, so the repo is
  not an installable package. _(target)_ Choose one dependency manager during discovery;
  `requirements.txt` pins exact versions today, which is good and should survive whatever
  replaces it.

## Code Style

- **Naming**: `snake_case` functions and module-level names, `PascalCase` classes
  (`ArtFile`, `ArtSet`, `DisplayLabel`, `ResizeOptions`) _(inferred — consistent across all modules)_
- **Formatting**: black, `line-length = 130` (configured in `pyproject.toml`)
- **Linting**: none configured _(target: adopt ruff)_ — with no linter, every mechanical
  style norm below falls through to the Critic, which is weaker and slower than a lint rule.
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

- **Framework**: none — there is no test suite, no `tests/` directory, and no test runner
  in `requirements.txt`. _(target: pytest)_
- **Style**: _(target)_ descriptive test names stating the behaviour under test.
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
- **Dev commands**: `python tvart.py [--flags]` is the entry point. There is no test, lint,
  or format command wired up. _(target)_ Establish `pytest`, `ruff check`, `black .`.
- **`requirements.txt` vs `r`**: `requirements.txt` is the hand-maintained direct-dependency
  list (18 entries). `r` is an extensionless **`pip freeze` capture from the Pi's venv** (60
  entries) — it is the only record of the full transitive set that actually ran, including
  four git-sourced packages absent from `requirements.txt`: `IT8951` (pinned to `9f13613`),
  `omni_epd`, `waveshare-epd`, and the `inky`/`spidev`/`RPi.GPIO` hardware stack. Treat it as
  a recovered lockfile, not scratch — it is evidence, and it should be renamed to say so.
- **Configuration**: split — secrets via `.env` → `config.py` (`OPENAI_KEY`, `EPD_TYPE`),
  everything else hardcoded as module constants in `config.py` including the TV's IP address,
  the art root `/home/tvpi/art`, and geographic coordinates. _(target)_ Hoist deployment-
  specific values (starting with `ART_ROOT`) out of source; see learnings § Data and cache contract.

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
| snake_case functions, PascalCase classes | Critic | — | janitor | No linter configured yet; promote to a ruff `N` rule once ruff lands. |
| Strict stdlib / third-party / local import grouping | Critic | — | janitor | Promote to ruff `I` (isort) once ruff lands — mechanical, shouldn't cost review attention. |
| `logging` only; `print()` reserved for deliberate CLI output | Critic | — | janitor | This runs unattended on a Pi under systemd; `print()` output has no level and no timestamp, so failures are invisible in the journal. |
| Type-annotate every new or touched function signature | Critic | — | janitor | Annotating on touch converts a 2,216-line untyped codebase incrementally, without a stop-the-world typing pass. Promote to a mypy/ruff gate once the ratio is high enough to be worth failing on. |
| Catch specific exceptions; broad catch needs `# prawduct:allow prawduct/broad-except -- reason` | Critic | — | advisory | A swallowed exception in an unattended loader shows up as "the TV just stopped changing", with nothing in the log to say why. |
| No hardcoded deployment values in source (IP, art root, coordinates) | Critic | — | janitor | The same code runs on the Pi and on a dev Mac; a hardcoded `/home/tvpi/art` means the dev path is a source edit, which is how config drift starts. |
| Async at the I/O boundary, synchronous core | Critic | — | janitor | `samsungtvws` forces async at the TV edge only. Letting it spread makes the image and metadata logic untestable without an event loop. |
| Hardware + network access sits behind an interface | Critic | — | janitor | Both display drivers are dormant upstream and one is unpinned; an interface keeps a frozen 2023 driver from dictating the project's Python version (learnings § Platform and dependencies). |
| **Operation logic lives ONLY in the service layer. MCP tools and HTTP handlers are thin bindings and contain no business logic.** | Critic | — | janitor | The product requires MCP at parity with the web UI, but UI controls call HTTP rather than MCP — so parity is only guaranteed if both are bindings over one implementation. Two implementations of "accept a candidate" diverge within weeks, and the divergence is invisible until an agent and a click produce different results. A handler that validates, orders, or decides is the violation; a handler that unpacks arguments, calls one service method, and formats the result is the norm. |
| **Spend ceilings are provider-enforced, never application-enforced** — norm lives in `nonfunctional-requirements.md` § Direction | Critic | — | janitor | An application meter that fails open is indistinguishable from one that works — no error, no alert, just a bill. This codebase has already shipped that exact defect shape (`upload_file` reports success on failure). Judgment-required: the violation is "this code path is the only thing stopping the bill", which no pattern match can see. |
| **The display plane never requires the curation plane to be reachable** — norm lives in `nonfunctional-requirements.md` § Direction | Critic | — | janitor | The availability asymmetry is the entire structural justification for the two-plane split; a display plane that phones home has paid the split's costs and kept none of its benefit. Judgment-required: a new call to the curation host is only a violation depending on whether rotation can proceed without it. |
| **The theme manifest file is the only channel from curation to display** — norm lives in `architecture.md` § Direction | Test | `tests/preferences/test_plane_isolation.py` | advisory | The mechanical form of the availability norm above, and the one that can carry a real rail: an AST/import check that display-plane modules import no curation module and open no HTTP client to the curation host. The violations this guards against ("just fetch the label text live") work perfectly in development and in every test, because curation is up in development and in every test — so a green test suite is exactly what a violation looks like without this check. |

### Known departures (existing code, not yet conforming)

These are real gaps, not exemptions. They are listed so no future session mistakes the
current state for the norm — and so nobody "fixes" the mismatch by weakening a norm.

| Departure | Where | Disposition |
|---|---|---|
| No test suite at all | whole repo | Blocking for medium+ work. Establish pytest before the first substantive build chunk. |
| No linter | whole repo | Adopt ruff; migrate the Critic-enforced mechanical norms above to lint rules. |
| `print()` used for operational output | `ai.py`, `display.py`, others | Convert on touch. |
| Deployment values hardcoded | `config.py` (`tv_address`, `base_folder`, lat/long) | Hoist during the config work; `ART_ROOT` first. |
| Sparse type annotations | 6 of 13 modules have none | Annotate on touch. |
| `pyproject.toml` declares `py312` while the platform target is 3.13 | `pyproject.toml` | Reconcile once 3.13 is actually verified on the Pi. |

**Rule for adding a new preference:** assign a mechanism. If the preference can be expressed as "every file/function/config matches pattern X with named exceptions" → write a test. If a linter rule already exists for it → configure the linter. If it requires understanding intent → assign to Critic. Never leave a preference unassigned.

**False-confidence guardrail:** if a generated test would pass on conforming code but couldn't reliably catch a real violation (e.g., greppy heuristics for semantic rules), prefer Critic over a weak test. A green test that doesn't actually check the rule is worse than no test.
