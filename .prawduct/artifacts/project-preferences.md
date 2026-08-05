# Project Preferences

Developer preferences for how code is written in this project. Captured during discovery, updated as preferences evolve. Every session should read this before writing code.

> **Status: inferred from the existing codebase on 2026-07-19, not yet confirmed by the
> owner.** Every entry below marked _(inferred)_ is a vetoable assumption. Entries marked
> _(target)_ are norms the existing 2024-era code does **not** yet meet — they bind new and
> touched code, and the gap is tracked in "Known departures" below rather than papered over
> by weakening the norm.

## Language & Runtime

- **Language**: Python _(inferred — every module at the repository root is `.py`)_
- **Version**: **per plane, not one number** (corrected 2026-07-20 — this previously
  read "target 3.13, floor 3.12" for the whole product, which had been true before
  the two-plane split and was the fourth site where a superseded version claim
  outlived its amendment).
  - **Display plane: 3.13**, floor 3.12. Raspberry Pi OS Trixie ships 3.13, and the
    IT8951 e-paper driver compiles Cython from 2023 sources targeting 3.13/3.12.
    This is the plane whose version is pinned by hardware. _(2026-08-04: 3.13 is no
    longer an assumption — the driver builds and imports on 3.13/aarch64 under uv's
    PEP 517 isolation. 3.12 stays as a floor, not as a fallback anyone expects to
    take. Noted here because this row's own history records it as the fourth site
    where a superseded version claim outlived its amendment, and a discharged
    contingency left standing is how the fifth one starts.)_
  - **Curation plane: 3.14**, **settled 2026-07-20; rationale re-based 2026-07-27,
    re-based again 2026-08-02.** This read "required by nothing except `3tears`",
    then "`3tears-models`, the operator's own model adapters that the discovery
    work calls". Neither holds: the catalogue takes no `3tears` core dependency,
    and `3tears-models` was confined to the opt-in `eval` group on 2026-08-02 when
    discovery went to OpenRouter through a first-party client instead.
    **This is the canonical statement of what holds the floor, and deliberately the
    only one.** Other artifacts point here rather than restate it — restating it is
    exactly how this claim came to sit three revisions out of date in four places
    at once, the fourth recurrence for a Python-version claim specifically. What
    holds it today: nothing in the default install requires 3.14, the only declared
    holder is a test-only dependency in the `eval` group, and what is left is the
    verified fact that the whole curation dependency set resolves and imports on
    CPython 3.14.4. So **lowering the floor is an available decision rather than a
    correction** — the split's other two legs (hardware-pinned display plane, the
    wall not blanking on curation restart) do not depend on it. Provisioned
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
  into that risk, which overstated the coverage. ~~**Tracked as issue #9.**~~ **Both
  closed 2026-08-04, issue #9 with them** — the pinned commit does declare Cython in
  build-requires so isolation was never at risk, and a current Cython emits
  3.13-compatible C on aarch64. The real blocker was undeclared `python3-dev`. A single
  `target-version` still cannot describe both planes; that is settled by the workspace
  split, not by picking a number.

## Code Style

- **Naming**: `snake_case` functions and module-level names, `PascalCase` classes
  (`ArtFile`, `ArtSet`, `DisplayLabel`, `ResizeOptions`) _(inferred — consistent across all modules)_
- **Formatting**: black, `line-length = 130` (configured in `pyproject.toml`)
- **Linting**: ruff, configured per plane. All three select `E,F,I,UP,B,T20,TRY`
  at `line-length = 130`. The configs differ, and the differences are the norm:
  - **Root** (`pyproject.toml`, excludes `curation/` and `display/`) also ignores
    `TRY400` and `TRY003` project-wide, and carries a per-file carve-out of
    **three kinds**. *(A third kind was added 2026-08-05:
    `.github/scripts/*.py` waives `T20`, because GitHub Actions raises
    annotations by reading `::error::` lines off a step's **stdout** — so
    `print()` there is the interface rather than a substitute for logging, and a
    logger writing to stderr would produce a job that fails with its reason
    invisible in the summary. It is written above the other two groups in the
    config rather than appended, because that file's own comments make both of
    those lists load-bearing: one is dated debt with a deletion date, the other
    is hand-run tools, and this is neither. Permanent, like the tools group.)*
    Of the original twelve files in two kinds: eight are 2024 wall modules waiving `T20`,
    `E501`, `F841`, `TRY002`, `TRY201`, `TRY300`, `B007` (plus `E402` on
    `art.py` and `display.py`); their carve-out has a scheduled end date — they
    are deleted once both planes exist. Four are hand-run operator tools, because
    `print()` is their output rather than logging: `spi_test.py`, `remote_test.py`
    and `urls_to_json.py` waive `T20`, `E501`, `F841` and — on `spi_test.py` —
    `E402`, while `tv_api_check.py` waives `T20` alone. Nothing schedules these
    for deletion, so their waiver is permanent until someone argues otherwise.
    Within the whole carve-out the deliberate holds are `B006` and all of `F`
    **except `F841`** (assigned-but-never-used, waived in the eleven that carry
    the fuller set); the unbound-name class that produced real defects here still
    fails the build. `config.py` is excluded from the carve-out and held to the
    strict set. _(Corrected 2026-08-01 by the norm sweep: this read "eleven files"
    and "Three are hand-run operator tools", missing `tv_api_check.py` — the same
    omission as the `T20` norm row below, in a second location. Found only because
    the row's fix prompted a re-read of this section, which is the point of
    "retiring a claim is a repo-wide grep, not a local edit".)_
  - **Curation** (`curation/pyproject.toml`) adds `ANN`, ignores `TRY003`, and
    turns `ANN` off under `tests/*`. No legacy carve-out: this plane is new code.
  - **Display** (`display/pyproject.toml`) is the same set as Curation — adds
    `ANN`, ignores `TRY003`, turns `ANN` off under `tests/*` — at
    `target-version = py312`, which is the Pi's interpreter rather than a
    preference. It arrived with the plane's manifest and **before any module**, so
    it currently lints an empty tree; that is deliberate, because a config landing
    after the first module is a config the first module was never held to.
    _(Added 2026-08-05. `ANN` was described here as a curation-only addition while
    a third config selecting it sat in the tree, which is exactly the drift the
    Norm Health sweep reads this list to find — it would have audited two configs
    of three and reported no gap.)_

  The mechanical style norms below that ruff covers are enforced by it rather than
  by the Critic.
- **Type annotations**: currently sparse and inconsistent, and it partitions cleanly.
  **Fully annotated**: `config.py`, `ai.py`. **No return annotation anywhere**: `display.py`,
  `local.py`, `metadata.py`, `remote_test.py`, `spi_test.py`, `urls_to_json.py`.
  **Partial**: everything else, `art.py` most sharply — it mixes bare class attributes with
  annotated `__init__` params. _(target)_ Annotate every new or touched function signature.
  _(Corrected 2026-08-02 by the norm sweep: this said "`image_utils.py` annotates 8 return
  types" and the AST says 9 — a function gained an annotation and the sentence describing it
  did not. Replaced with a partition rather than a corrected count: naming the modules says
  which files to fix, where a tally says only that some exist, and the tally is what went
  stale. The "six modules annotate none" it also carried was re-measured and is exactly
  right — the same six now named.)_
- **Imports**: absolute, one module per line, stdlib-then-third-party-then-local **loosely**
  grouped — `art.py` and `ai.py` interleave `config` with third-party imports. _(target)_
  Group strictly: stdlib / third-party / local, blank line between.
- **Logging vs print**: `logging` is configured in `art.py` and `tvart.py`, but `print()` is
  used for operational output throughout (`ai.py`, `display.py`). _(target)_ `logging` only;
  `print()` is reserved for deliberate CLI output.

## Testing

- **Framework**: pytest, one suite per plane *that has code* — `tests/` at the
  root for the 2024 modules, `curation/tests/` for the curation plane, each on its
  own interpreter.
  Both are declared as `test_commands` in `project-state.yaml` so the evidence hook
  runs the real invocations rather than a default that resolves neither.
  **The display plane has a configured `testpaths` and no `tests/` directory yet**,
  so it is deliberately *not* a third `test_commands` entry: an invocation that
  collects nothing exits 5, and a declared command that cannot fail is worse than
  an absent one. It is added by the commit that creates that directory — the same
  commit `build-plan.md` requires to carry the plane-isolation test, since both
  are the same claim about when a guard starts guarding.
- **Style**: descriptive test names stating the behaviour under test.
- **Coverage expectations**: _(target)_ happy path + error cases for pure logic
  (`image_utils`, `metadata` parsing, `source_utils`, the `all.json` catalogue round-trip).
  Hardware and network paths are covered behind interfaces, not by hitting a real TV.
- **Testing strategies**: _(target)_ plain example-based tests; the network (museum APIs,
  OpenAI, the TV websocket) and the e-paper panel are mocked at their module boundary.
- **Test location**: _(target)_ `tests/` mirroring the module layout.
- **Browser testing**: Playwright, through its **Python** bindings
  (`pytest-playwright`), in `curation/tests/browser/` behind the `browser` marker.
  It is the only harness that executes the shipped client, and it stays inside the
  curation suite and its interpreter — the recorded decision accepted a second
  language's package manifest as a cost, and the Python bindings simply do not
  charge it. Its dependency is the opt-in `browser` group, not `dev`, because a
  ~200MB browser has no place on the default install path. **Do not add a Node
  toolchain or a build step for the shipped client** — that is a separate standing
  decision (`design_decisions.visual_direction`) and this one does not touch it.
- **Parallelization**: `-n auto` for the curation suite, in its `addopts`
  (118s → 21s, measured 2026-08-05); the root suite is small enough to stay serial.
  **`-n0` for the browser and live suites** — a command-line `-m` replaces the
  marker expression and leaves the parallelism in place, which turns real poll
  intervals into flakes and concurrent museum requests into a rate limit.

## Architecture Patterns

- **Data modeling**: hand-rolled classes with `to_json`/`from_json`-style methods
  (`ArtFile`, `ArtSet` in `art.py`), persisted to `all.json` _(inferred)_. The catalogue's
  known defects — identity keyed on source URL, per-device state mixed into the record,
  semi-structured `artist_details` — are recorded in [learnings.md](../learnings.md)
  § Known problems in the existing index.
- **Error handling**: exceptions, with one custom domain exception (`DownloadError` in
  `art.py`) _(inferred)_. _(target)_ Catch specific exception types; a genuinely necessary
  broad catch carries `# prawduct:allow prawduct/broad-except -- reason`.
- **Async**: `samsungtvws`'s `SamsungTVAsyncArt` forces async at the TV edge, and every
  module that talks to the television is async because of it (`tvart.py`, `tv_delete.py`,
  `tv_api_check.py`, `remote_test.py`) — that part is the norm working. **It did not stop
  there**: `art.py`, `image_utils.py`, `metadata.py` and `source_utils.py` are async too,
  including functions that touch no I/O at all — `source_utils.cache_filename_for_url` is a
  hash and a path join, `metadata.parse_artic_details` is string parsing. The curation plane
  conforms exactly, with `async def` only where ASGI and the MCP session manager require it
  (`app.py`, `mcp/server.py`); nothing else in that plane is a coroutine.
  _(target)_ **Async at the I/O boundary, sync core.** Binds new and touched code in both
  planes; the root plane's departure is in "Known departures" below.
  _(Corrected 2026-08-02 by the norm sweep. This read "`asyncio` at the TV boundary only
  (`tvart.py`); everything else is synchronous _(inferred)_" followed by "_(target)_ Keep it
  that way". Four modules said otherwise and had since before the inference was made, so the
  descriptive half was wrong on the day it was written — and the normative half, phrased as
  preserving a state that did not exist, read as "no work owed" when the departure was
  already there. The Why makes the miss sharper than a wording slip: it is "letting it spread
  makes the image and metadata logic untestable without an event loop", and where it spread
  to is image and metadata logic. Those are the same modules § Testing names as owing
  coverage and none of them has any — which is what the norm predicted would happen and what
  nothing was watching for.)_
- **File organization**: per plane, not per repository. The root plane is flat — bare modules
  at the repository root, no package directory — and **shrinking**: they are deleted at the
  legacy retirement, and the rule below means the set only ever loses members. A root module
  count that has gone *up* is the violation, which is why no count is quoted here. The
  curation plane is a `src/` layout package. The display plane will be a package when it is
  created. _(target)_ Keep each as it is:
  **new code goes in a plane package; nothing new is added at the root.**
  _(Decided 2026-08-02, closing a question left open at discovery. The row asked to "decide
  during discovery whether to keep flat or move to a package"; discovery closed 2026-07-20
  and nobody did, so the tree answered by default and the answer went unwritten.
  **Converting the root plane to a package had stopped being a live option before the
  decision was owed**: the build plan scheduled those modules for deletion at the legacy
  retirement on the same day discovery closed, so from that point a package move was a
  refactor of code with a settled death date, paid in merge conflicts against the plane that
  replaces it. The rule that
  carries the intent forward is the one about additions, not about layout — flat is
  survivable for a fixed set of modules on their way out, and unsurvivable as a habit that
  new work is allowed to join.
  **The clause about interfaces was discharged elsewhere and is retired here, not dropped.**
  The row's Why ran "the hardware and TV boundaries need real interfaces regardless", and
  they got them — but from the two-plane split rather than from any directory move: the
  theme manifest is the curation→display interface, and the TV boundary became testable when
  `tv_delete` took the client as a parameter instead of importing one. A package directory
  would not have produced either, which is why "regardless" was the wrong word for it.
  This also retires the line count as a live input. It was re-measured 2026-08-01 by the norm
  sweep — the row had read "13 modules" and "defensible at 2,216 lines", both exactly right
  on 2026-07-19 and neither recomputed since, the second 19% under the truth. It was load
  bearing only while the flat-vs-package judgement was open, and the judgement is now closed
  on a reason no count moves.
  Still unassigned: this row has **no mechanism** — it is Critic-enforced like the other
  three `(target)` preferences the 2026-08-02 sweep found carrying none. A guard over "the
  root gains no new module" is the cheap form if this erodes.)_

## Tooling

- **Key libraries**:
  - `samsungtvws` — pinned to a **git SHA on a fork** (`NickWaterton/samsung-tv-ws-api`),
    not PyPI. This is the TV control surface.
  - `omni-epd` (`display.py`) — e-paper driver, dormant upstream since 2024-11. Not in
    `requirements.txt`; installed out-of-band on the Pi.
  - `pycairo` + `PyGObject`/Pango (`art.py`) — label typesetting. System-level GTK
    dependencies, not pure-Python wheels.
  - `openai` (`ai.py`) — mat-colour selection, currently calling `gpt-4o`. Real per-call spend.
  - `dezoomify-rs` (external binary) — tiled high-res image fetch. **Not configured in
    `config.py`**: the binary name and its tuning flags are module-level literals in
    `image_utils.py`, and `.env.example` does not mention it. `config.py` holds only its
    tile-cache directory and user-agent string. It is therefore the one dependency here
    resolved off `PATH` at call time, which is worth knowing because `deploy/README.md`
    records that the recovered systemd unit ships a hand-written `PATH` of pyenv shims.
    *(Corrected 2026-08-02 by the norm sweep: this read "configured in `config.py`", which
    would send someone looking for a setting that has never been there.)*
- **Dev commands**: `python tvart.py [--flags]` is the entry point for the 2024 modules.
  **Established 2026-07-27** and current: `uv run pytest tests` / `uv run ruff check .` /
  `uv run black .` at the root, and `uv run pytest` / `uv run ruff check .` /
  `uv run black .` in `curation/`.
  _(This read "There is no test, lint, or format command wired up"; both departures were
  closed the same day. **Corrected 2026-08-03**: the root column had dropped `uv run`,
  contradicting `CLAUDE.md`, which is the authority README.md points at and which explains
  the consequence — pytest, ruff and black live in a `[dependency-groups] dev` group only uv
  installs, so a bare `pytest` is command-not-found or, worse, a system-Python run that
  resolves different dependencies and reports a green suite meaning nothing.)_
- **`requirements.txt` vs `deploy/pi-freeze-2024.txt`**: `requirements.txt` is the
  hand-maintained direct-dependency list — the set installed on the Pi.
  `deploy/pi-freeze-2024.txt` is a **`pip freeze` capture from the Pi's venv**, the only
  record of the full transitive set that actually ran, including four git-sourced packages
  absent from `requirements.txt`: `IT8951` (pinned to `9f13613`), `omni_epd`,
  `waveshare-epd`, and the `inky`/`spidev`/`RPi.GPIO` hardware stack. It is evidence, not
  scratch: nothing installs from it, and it is the rollback target for the 2026-08-01
  `samsungtvws`/`websockets` move. Its own header says all of that, and `deploy/README.md`
  § What `pi-freeze-2024.txt` is says it again.
  *(Corrected 2026-08-02 by the norm sweep: this entry was written about a file called `r`,
  at the repository root, and asked that it "should be renamed to say so". The rename was a
  deliverable of the walking-skeleton work and landed in `807f97a` — so this bullet went on requesting shipped
  work and pointing at a path that no longer resolved. The counts it carried are dropped
  rather than restated: nothing recomputes them, and a reader takes a number for evidence.
  Both files now carry their own headers, which is the version that cannot drift from
  them.)*
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
- **Found problems — fix or file**: **strong bias towards fixing.** Filing is the
  exception and needs one of exactly two reasons:
  1. it is **orthogonal to the current work AND would require design or
     requirements**, or
  2. it is **medium or larger** work.

  Both halves of (1) must hold. Orthogonal but obvious is a fix; entangled but
  fiddly is a fix. Only "not what I am doing" *and* "somebody has to decide
  something" earns an issue.

  **Why**, in the operator's terms: an issue is a promise to pay attention later,
  and a backlog of small obvious repairs is a pile of promises nobody redeems.
  A one-line fix costs less now — while the file is open and the cause is
  understood — than it costs to write up, triage, re-find, re-understand and
  re-verify. Prawduct's own guidance ("accept is the default; filing everything
  turns the backlog into a guilt pile") argues the same way from the other end:
  this preference says the third option, *just fix it*, is the one to reach for
  first.

  **Retroactive**: yes, to anything already filed. An open issue meeting neither
  test is a fix waiting to be done, not a backlog item — closing it by doing it
  is the intended outcome. Ratified 2026-08-05, prompted by a UX walkthrough that
  filed nine items where several were small and self-evident.

  **This does not license scope creep.** A fix taken under this preference is
  still reported — silently widening a diff is the failure mode it trades
  against, so say what you fixed and why it did not meet the filing bar.

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
| **A found problem is fixed, not filed, unless it is (orthogonal AND needs design) or medium+** | Critic | — | janitor | Judgment-required by construction: "would this need design" and "is this medium+" are exactly the calls no check can make, and a mechanical rule would either block every issue or none. What a reviewer *can* check is the one thing that makes it auditable — a filed item should carry which of the two tests it met, and an issue asserting neither is the finding. Retroactive to open items, so the audit runs against the backlog rather than only against new work. |
| black formatting, line-length 130 | Linter (the formatting) + Test (the plane boundary) | `[tool.black]`, both `pyproject.toml`s; `tests/preferences/test_tool_config.py` | janitor | Already configured; removes formatting from review entirely. *(Corrected 2026-08-01: the artifact read `pyproject.toml` singular, written when the repo had one. Both planes carry a `[tool.black]` at line-length 130 — the root at `py312`, curation at `py314` — and a reader checking the norm against "the" pyproject would have audited half of it.)* *(Extended 2026-08-02 by the norm sweep: the root config drew the plane boundary for ruff and not for black, so `black .` at the root walked both planes — 103 files, not 18 — and formatted curation under `py312`. Fixed, and given a Test half, because the boundary is now drawn twice in two syntaxes (ruff takes a list of paths, black a regex) with nothing making them agree. The output was byte-identical either way, which is the whole argument for a mechanical guard: the split had stopped holding for formatting while still holding for lint, and no green suite anywhere would have said so.)* |
| The shipped browser client is executed by a test, not only read | Test | `curation/tests/browser/`, marker `browser`; `.github/workflows/browser.yml` runs it on pull requests and on pushes to `main`, and `.github/scripts/assert_tests_ran.py` fails the job if it skipped | advisory | Added 2026-08-05 with the harness (issue #30). `app.js` is the product's only human interface and neither Python suite ran a line of it, which is how three defects reached a running product — `replaceChildren` printing the string "null", every image tile taking the shape of its own picture, and a poll loop stealing focus every two seconds from the one screen with a decision on it. **The mechanism is a Test rather than the Critic because reading is what missed all three.** The bar for a behaviour being covered here is the mutation sweep, not the existence of a test: `tools/mutation_sweep.py` drives `app.js` and every behaviour this suite claims was demonstrated by deleting it and watching a test go red. It found a test whose fixture could not fail, which is exactly the failure mode a green suite cannot report. |
| snake_case functions, PascalCase classes | Critic | — | janitor | Ruff landed 2026-07-27 and `N` was **deliberately not selected**: the 2024 modules would fail it in bulk on names that are load-bearing at call sites, and a rule that has to be waived everywhere teaches people to waive rules. Stays with the Critic; revisit when the legacy modules are retired. |
| Strict stdlib / third-party / local import grouping | Linter | ruff `I`, both `pyproject.toml`s | janitor | Mechanical; it should not cost review attention, and since 2026-07-27 it does not. |
| `logging` only; `print()` reserved for deliberate CLI output | Linter | ruff `T20`, both `pyproject.toml`s. **Two distinct carve-outs, plus the norm's own stated exception**: the hand-run operator tools — every root module carved out beneath the `Operator tools run by hand` comment in the root `pyproject.toml`, which is the list rather than this sentence being it, today `tv_api_check.py`, `spi_test.py`, `remote_test.py` and `urls_to_json.py` — where `print()` *is* the output and the rule does not apply; eight legacy modules (`ai.py`, `art.py`, `display.py`, `image_utils.py`, `local.py`, `metadata.py`, `source_utils.py`, `tvart.py`) where it is debt with a scheduled end date; and, in new code, a hand-run command whose report is the reason for running it — waived per line as `# noqa: T201 -- <reason>`, never per file | janitor | This runs unattended on a Pi under systemd; `print()` output has no level and no timestamp, so failures are invisible in the journal. **The second carve-out includes modules the Why is precisely about** — `tvart.py`, `display.py` and `local.py` all run unattended — which is why it is a dated waiver and not an exemption. *(Corrected 2026-07-27: this row described one carve-out for "the legacy CLI entry points", which is not what the eight-module set is; a reader checking the waiver against the norm would have concluded the daemon was out of scope.)* *(Extended 2026-08-01: "reserved for deliberate CLI output" always permitted a hand-run command; nothing said how to express it in new curation-plane code, which has no per-file ignore and should not gain one. Per-line keeps the waiver next to its reason and keeps the rest of the module under the rule — the seeding command is the first case, and its report is a value its callers can assert on, so only the printing is waived, not the reporting.)* *(Corrected 2026-08-01 by the norm sweep: this row said "the three hand-run operator tools" and named three, while `pyproject.toml` carved out four. `tv_api_check.py` gained its `T20` ignore in `8d2bc77` at 2026-08-01 18:39, and this row was last written by `8efc672` the same afternoon at 15:34 — the commit that added the "Extended 2026-08-01" note directly above. **"Three" was correct when written; the config overtook the prose three hours later.** The carve-out is right (a hand-run bench tool whose six `print()` calls are its output) and the index is what went stale. A list that falls out of date within hours of being authored is the clearest available argument for pointing at the config instead of restating it, which is what this row now does.)* |
| Type-annotate every new or touched function signature | Linter (curation shipped code) + Critic (everything else: legacy modules, and both planes' test trees) | ruff `ANN` in `curation/pyproject.toml`, **excluding `tests/*`**; not selected at the root | janitor | Split deliberately 2026-07-27: the curation plane's shipped code is held to the rule mechanically, while annotating on touch converts the untyped legacy tree incrementally rather than by a stop-the-world pass. Promote the root when the ratio is high enough to be worth failing on. *(Corrected 2026-08-01 by the norm sweep, two ways. This row said "the curation plane is all new code and is held to the rule mechanically" while `curation/pyproject.toml` carries `"tests/*" = ["ANN"]` — the test tree is new curation-plane code and is exempt, so the sentence overstated the rule's reach; the exemption is defensible and is now stated rather than discovered. And the tree it described as "2,216-line" was exactly that on 2026-07-19 and is 2,735 lines across 14 root modules today — the figure is dropped rather than restated, because nothing recomputes it and the next reader takes a number for evidence. The Mechanism column is split to match: the first version of this correction stated the `tests/*` exemption in the Enforcement column while leaving Mechanism at "Linter (new code) + Critic (legacy)", which answered "the linter" for a surface the linter does not cover and left curation test code under the norm and under nothing — against this artifact's own rule never to leave a preference unassigned. **That first split then missed its own neighbour**: it read "Critic (legacy and curation tests)", which covers neither the root test tree nor the `tests/preferences/` file added in the same sweep, whose functions are unannotated in keeping with the root convention. Closing one unassigned surface and opening the adjacent one is the same error at one remove, which is why the column now names everything the linter does not reach rather than listing the parts remembered.)* |
| Catch specific exceptions; broad catch needs `# prawduct:allow prawduct/broad-except -- reason` | Critic | — | advisory | A swallowed exception in an unattended loader shows up as "the TV just stopped changing", with nothing in the log to say why. *(Corrected 2026-08-01: this row claimed Mechanism "Critic + linter" and Enforcement artifact "ruff `B`/`TRY`, both `pyproject.toml`s". **Neither rule set flags `except Exception:`** — bugbear has no blind-except rule and every selected `TRY` rule is about raise or log shape. The rule that would is `BLE001`, and `BLE` is selected nowhere here, so the norm has been Critic-only since it was written while the index said otherwise. The live proof is that `ruff check .` is green over every unwaived `except Exception` in the root plane — among them `tvart.py`'s inside `upload_file`, which logs and swallows in the unattended loader this row's Why is about. Selecting `BLE` is not a one-line fix and is why this is a correction rather than a repair: the sanctioned waiver is a Prawduct pragma, not a ruff directive, so `BLE` would fail the correctly-waived catches alongside the unwaived ones, and needs a paired `# noqa: BLE001` convention written into this row. **The two planes are not in the same position** — every broad catch in curation is waived with the pragma, so it can take `BLE` for one paired `noqa` per waived site, a figure `grep` recomputes rather than one this row has to keep true; the root plane's unwaived catches are all in modules scheduled for deletion at the legacy retirement, which is a per-file ignore with a dated end rather than a waiver each. Tracked as issue #33.)* *(Corrected 2026-08-02 by the norm sweep, and this correction changes what the tracked issue costs. The sentence above read "curation is new code whose **only** broad catch is already waived, so it can take `BLE` for the cost of **one** paired `noqa`." There were three: `mcp/server.py` was the waived one, while `manifest/builder.py` and `persistence/durable.py` both caught `BaseException` and neither carried a pragma. **A fourth — `services/runner.py`'s worker boundary — landed the same day, hours after this correction was written**, which is why the sentence above now states the invariant instead of a number: this row has been overtaken by the tree twice in two corrections, and a count is the part that keeps being wrong. `BLE001` flags `BaseException` as readily as `Exception`, so #33's estimate was understated threefold — by a row that, like the `T20` row before it, was never counted against the tree. Both sites are **cleanup-and-reraise**: one cleanup step, then the same exception continues. So the norm's Why — an exception swallowed in an unattended loader — was never in play, and the norm's letter, which names no exception for that shape, plainly was. **Owner's ruling 2026-08-02: waive per site, do not exempt the shape.** One waiver form with no shapes to remember is what makes this row auditable, and the pragma puts the reason beside the catch rather than in a reader's memory of this table. Both sites now carry it, and `grep` over both planes now returns broad catches and their reasons in the same line.)* |
| No hardcoded deployment values in source (IP, art root, coordinates) | Test | `tests/test_config.py::test_no_source_file_carries_a_deployment_value` | advisory | The same code runs on the Pi and on a dev Mac; a hardcoded `/home/tvpi/art` means the dev path is a source edit, which is how config drift starts. |
| Async at the I/O boundary, synchronous core | Critic | — | janitor | `samsungtvws` forces async at the TV edge only. Letting it spread makes the image and metadata logic untestable without an event loop. |
| Hardware + network access sits behind an interface | Critic | — | janitor | Both display drivers are dormant upstream and one is unpinned; an interface keeps a frozen 2023 driver from dictating the project's Python version (learnings § Platform and dependencies). |
| No secret ever reaches a log line | Test (startup config path) + Critic (everywhere else) | `tests/test_config.py::test_startup_logging_never_emits_a_secret` and `tests/test_config.py::test_the_harness_clears_every_declared_secret` | advisory | Added 2026-07-27; it was stated in `security-model.md` and had no row here, so nothing assigned it a mechanism and nothing looked for it. The repository is public and the journal is read over someone's shoulder during a failure — which is exactly when logging is turned up. Judgment-required beyond the startup path: the violation is usually a whole object logged for context whose repr happens to include a token, not a literal secret in a format string. *(Corrected 2026-08-01 by the norm sweep, in the opposite direction to this table's other corrections: the row claimed Mechanism `Critic` and no artifact, while a real mechanical guard already existed — `ba007cd`, **2026-07-27**, byte-identical to the body it has today. This row's own opening dates the norm to 2026-07-27 as well, so **norm and guard shipped in the same bundle on the same day**: the index recorded `Critic` from the moment the mechanism existed, rather than being right when authored and drifting later. It covers the norm's highest-risk known path — configuration logged at startup — and it refuses the vacuous pass, asserting that logging emitted something at all and that presence is reported as `<set>`. Verified by mutation: making `redacted_config` return the raw value fails it. **Under-claiming is the milder error and not a harmless one** — an enforcement artifact no row points at is one a refactor can delete with nothing noticing, which is how a Test row becomes the next `test_plane_isolation.py`.)* *(Extended 2026-08-02 by the norm sweep: the guard asserted the one secret that existed when it was written, while `config._SECRET_KEYS` declares two and `redacted_config()` walks the whole frozenset — so the second was redacted by the code and checked by nothing. It now drives off that frozenset, and a sibling test fails if a declared secret is not also cleared from the test environment, which is what stops these assertions passing on a developer's own shell instead of on the code. Verified by mutation both ways: emitting the second secret's value fails the guard, and declaring a third secret without clearing it fails the sibling. A guard that grows with its declaration is the difference between a Test row and a Test claim.)* |
| **Operation logic lives ONLY in the service layer; MCP tools and HTTP handlers are thin bindings** — norm lives in `architecture.md` § Direction | Critic | — | janitor | Ratified by the owner 2026-07-20. Judgment-required: a handler that validates, orders, or decides is the violation; one that unpacks arguments, calls a single service method, and formats the result is the norm. Rationale and retroactivity check live with the norm. |
| **Spend ceilings are provider-enforced, never application-enforced** — norm lives in `nonfunctional-requirements.md` § Direction | Critic | — | janitor | An application meter that fails open is indistinguishable from one that works — no error, no alert, just a bill. This codebase has already shipped that exact defect shape (`upload_file` reports success on failure). Judgment-required: the violation is "this code path is the only thing stopping the bill", which no pattern match can see. |
| **The display plane never requires the curation plane to be reachable** — norm lives in `nonfunctional-requirements.md` § Direction | Critic | — | janitor | The availability asymmetry is the entire structural justification for the two-plane split; a display plane that phones home has paid the split's costs and kept none of its benefit. Judgment-required: a new call to the curation host is only a violation depending on whether rotation can proceed without it. |
| **WCAG 2.1 AA on the curation UI, and colour is never the sole carrier of state** — decision lives in `project-state.yaml` § `design_decisions.accessibility_approach` | Test | `curation/tests/unit/test_design_tokens.py` | advisory | Added 2026-08-01 with the first browser surface. The contrast half is fully mechanical: the test reads the real token values out of the served stylesheet, computes every text and control pair in both colour schemes, and refuses any colour written outside the token blocks — so "AA verified" cannot rot into a sentence with nothing under it. The non-colour half stays judgment-required: a test can see that a badge has a glyph, not that the glyph distinguishes anything. |
| **The theme manifest file is the only channel from curation to display** — norm lives in `architecture.md` § Direction | Critic | — | advisory | The mechanical form of the availability norm above, and the one that *can* carry a real rail: an AST/import check that display-plane modules import no curation module and open no HTTP client to the curation host. The violations this guards against ("just fetch the label text live") work perfectly in development and in every test, because curation is up in development and in every test — so a green test suite is exactly what a violation looks like without this check. **Corrected 2026-08-01: this row named `tests/preferences/test_plane_isolation.py` as an existing Test mechanism, and no such file has ever existed.** It could not have: the check's subject is the `display/` package, which the walking-skeleton work deferred and nothing has created since, so the only test writable today would pass over an empty set — the "green test that cannot catch a real violation" this table's own guardrail rejects. Enforcement is Critic judgement until the display plane exists; the test is a deliverable of the chunk that creates it, and this row moves back to Test then. |

### Known departures (existing code, not yet conforming)

These are real gaps, not exemptions. They are listed so no future session mistakes the
current state for the norm — and so nobody "fixes" the mismatch by weakening a norm.

| Departure | Where | Disposition |
|---|---|---|
| ~~No test suite at all~~ | ~~whole repo~~ | **Closed 2026-07-27.** pytest established per plane; both suites declared as `test_commands`. |
| ~~No linter~~ | ~~whole repo~~ | **Closed 2026-07-27.** ruff configured at the root and in the curation plane; the mechanical norms it covers moved from Critic to lint rules. |
| `print()` used for operational output | Eight legacy modules; see the `T20` row above for the list | **Disposition changed 2026-07-27: dies with the 2024 modules at the legacy retirement, not converted on touch.** "Convert on touch" had no mechanism behind it — all eight were touched during the 07/08 bundle and **not one `print()` call was converted**, so the stated disposition was describing something nobody was doing. *(Corrected 2026-08-02 by the norm sweep: this said "19 `print()` calls stayed". Measured across the eight modules at `ba007cd^`, at `ba007cd`, and today, the count is **39 every time** — the number was never right, not even on the day it was written, and it understated the gap it was arguing about by twenty. Replaced with the invariant rather than with 39, per this project's own rule that a tally in durable prose goes stale and a claim that cannot goes on being true: "none were converted" is checkable against that bundle forever, and no future reader has to trust a number nothing recomputes. That the wrong number appeared in the row arguing for an end date **because "convert on touch" had no mechanism** is the joke at this table's expense — the argument was right and its evidence was invented.)* The two honest options were a ratchet that fails the build on a touched file, or an end date; the modules are deleted at the legacy retirement and their replacements log from the first line, so the end date is the proportionate one. |
| `async` spread past the I/O boundary into the sync core | `art.py`, `image_utils.py`, `metadata.py`, `source_utils.py` — image fetch, image processing, metadata parsing, and the HTTP/cache helper, none of them a TV boundary | **Added 2026-08-02 by the norm sweep; dies with the 2024 modules at the legacy retirement, not converted on touch.** The norm's own Why is that spreading async "makes the image and metadata logic untestable without an event loop", and these four *are* that logic — `source_utils.cache_filename_for_url` is `async def` over a hash and a path join, `metadata.parse_artic_details` over string parsing. So the departure is not cosmetic: it is the predicted consequence, arrived, in the modules § Testing names as owing coverage and which have none. It gets an end date rather than a conversion for the same reason the `print()` row above does — every one of these functions is awaited from `art.py`'s download path, so unwinding them is a change to doomed code with no tests to catch a mistake, and their replacements in the curation plane are synchronous from the first line. **The norm still binds everything else**, and the curation plane meets it today: `async def` appears there only where ASGI and the MCP session manager require it. *(This row did not exist until the sweep looked. The norm read "asyncio at the TV boundary only (`tvart.py`); everything else is synchronous" — so there appeared to be nothing to record, and a departure with no row is one no future reader is warned about.)* |
| Handlers that do more than the service-layer norm's "call one service method" | `curation/src/curation/http/api.py` — `add_to_theme`, `remove_from_theme` and `move_in_theme` mutate then read back through `_theme_detail` (three service calls each); `get_theme` composes two reads; `get_thumbnail` makes one call and carries the HTTP conditional-request decisioning. **Three departing shapes, and every departure is named above** — stated as the shapes rather than as a fraction, which is this table's own rule arriving for the third time. It read "six of twelve handlers, counted by AST 2026-08-02" until 2026-08-05, when the run half took the file from twelve handlers to twenty *without adding a departure*: the sentence had silently become 50% against a real 30% — in the row whose whole purpose is to show an owner how far a ratified norm has drifted before they rule on it. The two rows above this one each record the same lesson from their own wrong number; this one is the first where the count was right on the day it was written and was made wrong by conforming work. **`get_health` left this list on 2026-08-05**, which is the first departure here closed by conformance rather than by deletion: the panel's three observations were assembled in the handler, so *which signals the panel makes* was a product decision taken in a binding — and the next one would have had to be added in two places with nothing to notice if it reached only one. It is a `HealthService.observe()` call now. The composite-read shape survives it in `get_theme`, so the three shapes still stand; nine handlers were added the same day and none departs. **Also `curation/src/curation/mcp/bindings.py` — `_get_theme` pairs `get_theme` with `theme_works`, the same composite-read shape (the only binding in the file that does; every other one makes exactly one service call, re-checked by AST 2026-08-03 when `resolve_images` was added as a conforming one).** *(The MCP layer was missing from this row until 2026-08-02, when Critic review found it stating the identical absolute in its own module docstring while departing from it. The row had scoped itself to `http/api.py` because that is where the sweep looked — so the fork below was put to the owner against an undercount, which is the specific way a "known departures" table stops being the thing that stops a norm dying by accumulation.)* | **DISPOSITION UNDECIDED — recorded 2026-08-02, deliberately not resolved.** Every one of them carries an in-code reason and none is "operation logic" in the sense the norm's Why guards against: the MCP bindings reach the same services, so an agent and a click cannot disagree, which is the failure the norm exists to prevent. What is nonetheless true is that an owner-ratified norm has exceptions in three shapes and records none — the shape where a norm dies by accumulation rather than by decision. The fork was put to the owner during the sweep and **deferred**: re-affirm with a named exception for the three shapes (read-back-after-mutate, composite read, protocol handling), or amend the norm's text. This row exists so the interval before that call is not mistaken for conformance. *(Recorded only because Critic review asked why the async departure found in the same sweep got a row and this one got a `deferred:` bullet in `project-state.yaml`. It was the right question: the reasoning written into the async row — "a departure with no row is one no future reader is warned about" — does not stop applying because the disposition is open.)* |
| ~~Deployment values hardcoded~~ | ~~`config.py` (`tv_address`, `base_folder`, lat/long)~~ | **Closed 2026-07-27.** All three hoisted to `.env`; `tests/test_config.py` fails on any of them returning to source. |
| Sparse type annotations | `local.py`, `remote_test.py`, `spi_test.py` and `urls_to_json.py` carry no annotation of any kind; `display.py` and `metadata.py` annotate parameters but never a return | Annotate on touch. *(Corrected 2026-08-01 by the norm sweep: this read "6 of 13 modules have none". The **6 is still exactly right** and the denominator is not — the root plane is 14 modules now, `art_label.py` having gone and `tv_api_check.py` and `tv_delete.py` arrived. The count also silently depended on which "none" was meant: 6 modules have no *return* annotation, 4 have no annotation at all, and the row never said which — so it read as wrong to the first person to re-measure it. Named rather than counted, because the names say which modules to fix and a fraction says only that some exist.)* |
| ~~`pyproject.toml` declares a single `target-version = ["py312"]` for a two-plane product~~ | ~~`pyproject.toml`~~ | **Closed 2026-07-27.** The sibling-project split gave each plane its own `pyproject.toml`, so each carries its own target rather than one setting trying to describe both. |

**Rule for adding a new preference:** assign a mechanism. If the preference can be expressed as "every file/function/config matches pattern X with named exceptions" → write a test. If a linter rule already exists for it → configure the linter. If it requires understanding intent → assign to Critic. Never leave a preference unassigned.

**False-confidence guardrail:** if a generated test would pass on conforming code but couldn't reliably catch a real violation (e.g., greppy heuristics for semantic rules), prefer Critic over a weak test. A green test that doesn't actually check the rule is worse than no test.
