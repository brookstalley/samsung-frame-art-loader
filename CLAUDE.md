# CLAUDE.md

<!-- PRAWDUCT:ANCHOR — static governance pointer managed by the prawduct plugin. Keep it small and version-free: principles, methodology, and the active version live in the plugin and are injected at session start. -->

## Governance (Prawduct)

This repo is governed by **Prawduct**, installed as a Claude Code plugin — not as
committed framework files. The principles, methodology, Critic protocol, and PR
review live in the plugin and are read on demand (run `/prawduct:methodology`);
they are intentionally not copied into this repo.

**Before writing any code, STOP and read the build cycle: `/prawduct:methodology building`.**
Skipping it is the #1 governance failure.

The hardest rules (everything else is in the plugin):

- **Tests are contracts** — fix the code, never weaken a test.
- **No "pre-existing" exception** — fix what you find, or flag why you can't.
- **Never silently drop a requirement** — say so explicitly.
- **Run `/prawduct:critic` after medium+ work** — never write Critic findings
  yourself; the independence is the value.

**Enforcement is structural:** the plugin's Stop hook runs at session end and
**blocks** if code changed against an active build plan with no Critic findings.
The session-start banner shows the active version and what changed — this anchor
stays version-free.

## Dev commands

Three independent projects, three interpreters. **Two suites — and the third
column is why that is not a typo.**

| | 2024 modules (repo root) | curation plane | display plane |
|---|---|---|---|
| Test | `uv run pytest tests` | `cd curation && uv run pytest` | *(no suite yet — see below)* |
| Lint | `uv run ruff check .` | `cd curation && uv run ruff check .` | `cd display && uv run ruff check .` |
| Format | `uv run black .` | `cd curation && uv run black .` | `cd display && uv run black .` |

**The two suites that exist must both pass.** `display/` currently holds a project
manifest and no module, so its lint and format commands run against an empty tree
and its `pytest` would collect nothing and exit 5 — which is not a pass and not a
failure. It gets its suite, and its `test_commands` entry, from the commit that
writes its first module; that same commit owes the plane-isolation test, because
both are the same claim about when a guard starts guarding.

**`uv run` in every column, including the root.** pytest, ruff and black live in a
`[dependency-groups] dev` group that only uv installs — `pip install -e .` does
not. Dropping the prefix gets either command-not-found or, worse, a system-Python
pytest that resolves different dependencies and reports a green suite that means
nothing. This table is the authority README.md points at for running the tests, so
a wrong command here costs a fresh clone its first hour.

Run the curation plane: `cd curation && uv run python -m curation`. It needs
`ART_ROOT` (copy `.env.example` to `.env`); the browser interface serves on
`CURATION_PORT`, its JSON API under `/api`, and MCP clients connect to `/mcp` on
the same port.

The curation suite boots a real uvicorn server per test class of surface work.
Do not replace that with an in-process ASGI transport: Starlette does not run a
mounted sub-app's lifespan, and the lifespan is what makes the MCP mount work,
so an in-process test would pass against an app that fails every real request.

**That suite runs across cores** — `-n auto` is in the curation plane's
`addopts`, so `uv run pytest` is already parallel (118s → 21s, measured
2026-08-05). **Add `-n0` to debug a failure**: workers interleave output and a
`pdb` breakpoint has no terminal to stop in. The root suite covers the 2024
modules only, runs in a fraction of a second, and is left serial.

## The browser suite

The client in `curation/src/curation/http/static/app.js` is the product's only
human interface, and neither Python suite executes a line of it. `-m browser`
does, in a real Chromium against a real booted server:

```sh
cd curation && uv sync --group browser        # once
cd curation && uv run playwright install chromium   # once, ~200MB
cd curation && uv run pytest -m browser -n0
```

**Deselected by default for the browser download, not for anything about the
tests** — they are deterministic, free, and reach no foreign API. Run them when
you touch `app.js`; `.github/workflows/browser.yml` runs them on pull requests
and on pushes to `main`. Without the group the modules skip with the command
that fixes it, so a default `uv sync` is unaffected.

**`-n0` matters here.** These tests time real two-second poll intervals, and
`-n auto` — which a command-line `-m` leaves in place — turns those windows into
flakes when workers contend for cores.

**A behaviour is not covered because a browser test exercises it.** Prove it with
`tools/mutation_sweep.py`, which drives `app.js` as happily as a Python file:
delete the branch and watch a test go red.

**Sweeping this suite needs the marker passed through:**

```sh
cd curation && uv run python tools/mutation_sweep.py m.json tests/browser/test_x.py -- -m browser
```

Without it pytest collects nothing and exits 5. The tool refuses to sweep unless
the chosen tests run and pass unmutated, so forgetting the marker now fails
loudly instead of reporting every mutation caught by runs that executed no test.
(`-n0` is the tool's own default — see the sweep paragraph below.)

## The live suites

Four markers — `live_museum`, `live_binary`, `live_api`, `llm_eval` — all
deselected by default. They are not correctness tests; the fakes cover that.
They are the durable form of the `*-api-findings.md` documents, and they fail
when a foreign API stops matching what the product was built against.

**Always pass `-n0` when you run one.** A `-m` on the command line replaces the
marker expression but leaves `-n auto` in place, so `-m live_museum` alone fires
concurrent requests at a public museum API — which comes back as a rate limit and
is indistinguishable from the contract change you were looking for.

```sh
cd curation && uv run pytest -m live_museum -n0     # free, needs the network
cd curation && uv run pytest -m live_binary -n0     # free, needs dezoomify-rs
cd curation && uv run pytest -m live_api -n0        # SPENDS REAL MONEY
```

**Locally the marker alone is enough; in CI it is not.** These commands collect
the whole tree and the opt-in modules `importorskip`, which is a skip you can
ignore at a terminal. In a workflow that same skip fails the job through
`assert_tests_ran.py` while every probe passed, so **a CI invocation scopes the
path as well** — `uv run pytest tests/live -m live_museum …`. That is asserted by
`tests/test_assert_tests_ran.py`, which reads the workflow files, so a new job
written from the line above fails at home rather than on a schedule.

Run one when your work touches that client. Otherwise leave the **three
`live_*` markers** to `.github/workflows/api-drift.yml`, which runs the two free
tiers weekly and the paid one monthly — drift is on the provider's schedule, not
on our commit rate.

**`llm_eval` is not in that workflow and is not meant to be.** It drives the
surface with a real model, so it spends and it can reach the same goal by a
different route next time; a non-deterministic check on a schedule either flakes
or gets loosened until it asserts nothing. It measures, and the contract level
gates. Run it by hand before shipping a tool-surface change — nothing else will.

**Every one of these tests skips itself when its dependency is missing**, which
is right locally and a trap in CI, where a green run that made no request looks
identical to a passing one. `.github/scripts/assert_tests_ran.py` is what closes
that: it fails the job on any skip and names which dependency was absent.

**A green suite says nothing about a branch no test reaches.** Before believing
new branches are covered, break them on purpose:
`cd curation && uv run python tools/mutation_sweep.py <mutations.json> <test paths>`.
Its docstring has the format. It has found something on every change it has been
run on, and it is the check that a diff review does not substitute for — the
undefended branches all looked right when read.

Budget `(mutations + 1) x the time your chosen test paths take`. **The sweep runs
serial by the tool's own doing** — it passes `-n0` ahead of your arguments, so a
`-n` of your own still wins. That is correctness, not speed: with `-x` under
xdist a failing test ends the session as INTERRUPTED and pytest exits **2**, not
1, so every *caught* mutation looked like the unclassifiable exit the tool
refuses to guess at. Serial costs nothing worth having here — 67s against 65s for
ten mutations over two files, a slice being dominated by per-run worker startup.
