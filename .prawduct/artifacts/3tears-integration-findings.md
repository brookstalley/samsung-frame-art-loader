# 3tears Integration Findings

Recorded 2026-07-19 during discovery. Everything below was verified by reading
`/Users/brookstalley/source/3tears` at the checkout present on this machine, not
recalled. 3tears is **alpha (`0.x`)**; its README states the public API can shift
between minor versions, so re-verify these findings when the pinned version moves.

## The question this answers

> "I would like to use 3-tier entities, MCP tools, and agent memory. But is there
> really no way to avoid pulling in Docker/Postgres/NATS in that model?"

**Mostly yes, there is a way — with one genuine exception.** The three wants have
three different answers.

## Answer 1: three-tier entities — no infrastructure required

L2 and L3 are **injected, and absent tiers are a designed-for mode**, not an accident.

- `CollectionRegistry.__init__` initialises `_l1_backend`, `_l2_client`, and
  `_l3_pool` all to `None`. `configure()` sets only what you pass
  (`collections/registry.py:96-120`).
- `BaseCollection` types the L2 client `NatsClient | None` and guards every use:
  KV access returns early (`if self._nats_client is None: return None`,
  `collections/base.py:439`), and cache invalidation calls
  `_warn_missing_nats_client_once()` (`base.py:746-754`) — a one-shot WARNING with
  deliberate anti-log-spam machinery keyed per table.

That last detail is the tell: someone built spam suppression for the no-NATS path,
which means running without a broker is an anticipated configuration rather than a
degraded accident.

**Conclusion:** L1 SQLite alone is a valid configuration. No NATS, no Postgres, no
Docker.

**AMENDED 2026-07-27 — valid, but not *durable*, and this section read as though it
were.** Everything above is accurate about *tiers being optional*; none of it is
about persistence. `cache/sqlite.py:104` opens `file:/{db_name}?vfs=memdb` — a named
**in-memory** database, as that module's own docstring states ("L1 cache backend
using SQLite named in-memory database"). L1 is a cache, not a store: an L1-only
collection holds the catalogue in RAM and loses it when the process exits. There is
no file-backed mode and no path option — the URI is hardcoded.

Durability therefore comes only from the L3 tier described in Answer 2. The
parenthetical at the end of this document — "(optionally a SQLite `DurableStore`
L3)" — was carrying that entire load, and "optionally" was wrong.

## Answer 2: the L3 durable tier is pluggable, and there is a working precedent

`backends/protocol.py` deliberately separates two levels:

- `L3Backend` — raw SQL transport (`fetch`/`execute`/…). "Irreducibly SQL"; a
  non-SQL backend legitimately does not implement it.
- `DurableStore` — structured ops (`fetch_one`/`upsert`/`delete`/`scan`) keyed by
  table + column dict + pk, **no SQL string**. The module docstring calls this
  "the seam that makes a non-SQL durable backend possible" and names a git working
  tree as a first-class L3.

**That is not theoretical.** scriob already ships one:
`scriob/server/src/scriob_server/content/git_l3.py`. A SQLite- or file-backed
`DurableStore` for this project is a well-trodden path, not new ground.

**Made explicit 2026-07-27:** 3tears itself ships **no** SQLite `DurableStore`. The
only implementation in the tree is `backends/sql.py` (`SqlL3Backend`, asyncpg over
Postgres). "Pluggable" here means *we write the plug* — which is what makes the
durable tier this product's own code under every 3tears configuration, and what
makes shaping it to `fetch_one`/`upsert`/`delete`/`scan` worth doing whether or not
the collection layer is ever adopted.

Two further constraints found the same day, both bearing on how much of 3tears a
consumer can take incrementally:

- **Collections have no query API.** `BaseCollection` is entity-by-primary-key
  (`get`/`save_entity`/`delete`/`ensure`/`__getitem__`/`__contains__`). Ordered,
  paged, counted listing has no home in it; `DurableStore.scan` takes equality
  filters with no ordering, paging, or total. Any listing path goes to the durable
  tier directly, under every configuration.
- **The collection API is async throughout, and the `*_sync` methods are
  L1-cache-only** — `get_field_sync`/`get_row_sync` return `MISSING`/`None` when L1
  is absent rather than reading through to L3 (`collections/base.py:339-395`).
  Adopting collections is therefore an async conversion of every caller above the
  store, which `project-preferences.md`'s "async at the I/O boundary, synchronous
  core" norm makes a recorded departure rather than a detail.

## Answer 3: agent memory is the exception — it requires Postgres

`packages/agent/memory/pyproject.toml` declares:

```
"3tears", "3tears-agent-acl", "3tears-langgraph", "3tears-observe",
"pgvector", "langchain-core",
```

`pgvector` is a **PostgreSQL extension** for vector similarity search. There is no
way to take 3tears agent memory without running Postgres. This is the one want that
genuinely forces infrastructure.

## Answer 4: MCP tools pull NATS as a package dependency

`3tears-mcp` → `3tears-epoch` → `3tears-nats`, and `mcp/auth.py:40-41` imports
`EpochClient`, `EpochListener`, and `Subjects` at module scope.

`nats-py` therefore gets **installed**. Whether a **running broker** is required
depends on whether the RBAC/auth path is exercised — the imports sit in `auth.py`,
not in `tool.py` or `server.py`.

**Unverified.** Using `McpTool` / `register_tool` without a live broker is
plausible but was not proven. Treat as an open assumption; it needs a spike before
anything is designed on top of it.

## Package dependency map (verified)

| Package | Needs `3tears` core? | Infrastructure |
| --- | --- | --- |
| `3tears-media-contracts` | no — zero dependencies | none |
| `3tears-models` | **no** — only media-contracts + observe | **none** — langchain adapters for anthropic, openai, openrouter |
| `3tears` (core) | — | **none** if L1-only; asyncpg/nats-py install but need not connect |
| `3tears-langgraph` | yes | asyncpg installed; checkpointer executor is injected |
| `3tears-mcp` | yes → epoch → nats | nats-py installed; live broker **unverified** |
| `3tears-agent-memory` | yes | **Postgres + pgvector — hard requirement** |
| `object-store` | yes | aioboto3 (S3-compatible) |

## The Python 3.14 constraint is real today — and removable

Audited 2026-07-19 by compiling every source file under `core`, `models`,
`media-contracts`, and `observe` against real CPython 3.13 / 3.12 / 3.11
interpreters, cross-checked with an AST-driven stdlib-symbol existence check and
`vermin`. All three methods converged on the same list.

**Verdict: 3.14 is genuinely required as shipped, not merely declared — but only
by 16 source sites, every one of them mechanical.**

| Package | Declared | True minimum as shipped | What sets the floor |
| --- | --- | --- | --- |
| `media-contracts` | >=3.14 | **3.9** | nothing — zero version-gated constructs |
| `observe` | >=3.14 | **3.14** | `observe/logging.py:176` PEP 758 |
| `models` | >=3.14 | **3.14** | `models/price_lookup.py:137` PEP 758 |
| `core` | >=3.14 | **3.14** | `core/utils/atomic_write.py:18` `from uuid import uuid7` |

### The complete blocker list — 16 sites

**A. PEP 758 unparenthesised `except A, B:` (3.14-only syntax) — 13 sites, each a
one-line fix (add parentheses):**

- `core/backends/schema_sql.py:254`, `core/cache/duckdb.py:293`,
  `core/cache/sqlite.py:460`, `core/collections/schema_backed.py:1252`
- `models/price_lookup.py:137` and `:410`, `models/registry_loader.py:113`,
  `models/tracking.py:361`
- `observe/logging.py:176`, `observe/tracing.py:68`
- `nats/client.py:236`, `:608`, `:1109`

**B. `uuid.uuid7` (3.14 stdlib addition) — 3 sites, all in `core`:**

- `core/backends/nats_proxy.py:14` (8 call sites), `core/coordination/lease.py:35`,
  `core/utils/atomic_write.py:18`

There is already an in-repo precedent for the fix: `core/collections/registry.py:11`
and `observe/middleware.py:52` use `from uuid_utils import uuid7` (third party,
`requires-python >=3.9`).

**After remediation:** `core` floors at **3.12** (two PEP 695 type-parameter
declarations — `core/utils/pg_pool_kwargs.py:304` and `core/knowledge/chains.py:69`;
the latter is redundant, since the file already defines `T = TypeVar("T")` at line
65). Converting those two drops the whole subset to **3.11**.

### `3tears-nats` must be relaxed in the same change

`core` hard-depends on `3tears-nats` and imports it at 8 sites
(`collections/base.py:32`, `cache/kv.py:38`, `coordination/lease.py:41`,
`security/jwks_provider.py:33`, …). It declares `>=3.14` too and carries 3 of the
PEP 758 sites above. **Relaxing core without relaxing nats achieves nothing** —
core cannot install below 3.14 regardless. Note this does *not* mean a broker is
required at runtime; it is an install-time package dependency (see Answer 1).

### Third-party dependencies impose no floor

Verified against installed dist metadata. The highest floor across every declared
dependency of the four packages is **3.10**: sqlalchemy >=3.7, asyncpg >=3.9,
aiosqlite >=3.9, pydantic >=3.9, cryptography >=3.9, pyjwt >=3.9, nats-py >=3.7,
uuid-utils >=3.9, langchain-* >=3.10, duckdb >=3.10.

Relaxing 3tears is therefore **not** pointless — the dependency graph already
supports 3.10+.

### Two upstream defects found in passing

Both are real bugs in 3tears today, independent of this product:

1. **`3tears` core does not declare `uuid-utils`** despite
   `core/collections/registry.py:11` importing it unconditionally at module scope.
   It works only because `3tears-observe[asgi]`, langgraph, scheduled-jobs,
   agent-skills, and agent-wake happen to pull it in transitively. Any install
   that takes core without one of those breaks. A relaxation PR must add the
   declaration.
2. **`langchain-voyageai 0.3.3` declares `Requires-Python: >=3.10,<=3.13`** — the
   `models[voyageai]` extra is upstream-declared *incompatible* with 3.14, and
   `models/providers/_voyageai_compat.py:40` exists to paper over the breakage.
   That is an argument **for** relaxing, not against.

### What CI actually tests

**Only Python 3.14, single runner, no matrix.** Both `ci.yml` and `release.yml`
do `uv python install 3.14`. Reinforcing pins that would also need to move:
`.python-version`, root `[tool.ruff] target-version = "py314"`, root
`[tool.mypy] python_version = "3.14"`, `uv.lock` line 3, `docker/Dockerfile:35,53`,
and the `Programming Language :: Python :: 3.14` classifiers. No enforcement test
pins `requires-python`, so no test contract blocks the change.

### The one thing a PR must prove

The audit was static — syntax and stdlib-symbol level, high confidence. It could
**not** execute the test suites under 3.13, because the venv is 3.14 and building
a full 3.13 environment (asyncpg, duckdb, cryptography, testcontainers, langchain)
was out of scope. The realistic residual risk is behavioural rather than syntactic:
`asyncio` internals, and **pydantic/langchain annotation resolution under eager
(3.13) versus lazy (3.14) `__annotations__`**. A static PEP 649 reliance check
found zero hits, but only a real 3.13 test run closes this.

Also unverified: wheel availability on 3.13 (near-certain — 3.13 is older and
better covered than 3.14) and the workspace-wide `uv.lock`, which stays at
`>=3.14` until the whole workspace moves or the lock is regenerated.

## What this does NOT change

Relaxing 3tears would remove the *forcing* reason for the two-plane split, but it
does not follow that the planes should merge — **the display plane does not want
3tears at all.** It needs an HTTP client, `samsungtvws`, PIL, and the e-paper
driver. Three-tier entities are of no use to it, and the shared-catalogue use case
that would justify them is precisely the multi-pod coherence problem the operator
ruled out.

So the split survives on its independent merits (the display plane's
hardware-pinned interpreter, the upstream/derived data contract, availability
asymmetry), and the PR is worth doing
on *its* merits — a latent portability limit plus two real defects in a framework
the operator maintains — rather than to unblock this product.

## The original constraint, as first recorded

**Every** 3tears package declares `requires-python = ">=3.14"` (verified across all
`packages/*/pyproject.toml`).

This collides directly with
[platform-and-dependency-findings.md](platform-and-dependency-findings.md), which
chose **Python 3.13** for the Pi and explicitly rejected 3.14 *(the 3.12 fallback
that used to be named here was discharged 2026-08-04 — the build succeeded on 3.13,
so 3.12 is a floor rather than a landing site)*:
IT8951 compiles Cython from `.pyx` sources at install time and was last touched
2023-11, and aarch64 wheels for opencv/scikit-image may lag.

**3tears and the e-paper driver cannot share an interpreter.** This is the single
constraint that most shapes the architecture, and it is why the curation plane and
the display plane are separate processes on separate Python versions.

## Consequence for this product

> **SUPERSEDED 2026-07-27 — read this before the analysis below.** The product
> answered "no" to the question this section poses, and then **declined the
> three-tier entities as well**. The catalogue's durable tier is first-party
> SQLite *shaped to* `DurableStore`'s decomposition and naming, with no framework
> package imported: reading the framework showed that its L1 is a named in-memory
> database, that it ships no SQLite durable backend (so the tier that persists is
> this product's own code under every configuration), and that its collections are
> async throughout with no query API — which would convert three layers to async
> against a ratified norm. So "required, not optional" below is **retired**: what
> was required was *a durable SQLite tier*, not that framework's entities over one.
> `3tears-models` is unaffected and still arrives with the discovery work; it
> depends on `media-contracts` and `observe`, never on core. Recorded in
> `architecture.md` § Decision Log, `project-state.yaml` →
> `technical_decisions.technology`, and `curation/pyproject.toml`.
>
> > **That last sentence was overtaken on 2026-08-02 and is corrected here rather
> > than edited away, because the reasoning above is still the record of what was
> > believed when.** `3tears-models` did **not** arrive with the discovery work.
> > Discovery reaches OpenRouter through a first-party client
> > (`curation/src/curation/discovery/openrouter.py`) behind the engine seam, and
> > `3tears-models` stays confined to the opt-in `eval` group, where it plays the
> > *curator* driving the MCP surface from outside rather than the discovery
> > worker behind it. The deciding factor is the one this file already cares
> > about: it would pull seven packages into the curation plane's **default**
> > install, on the Pi, under a `MemoryMax`. Full reasoning in
> > `openrouter-api-findings.md` § "The client is first-party, behind a seam";
> > superseding entry in `project-state.yaml` → `technical_decisions.technology`.
> >
> > **So the analysis below names a shape the product does not build.** Where it
> > says "3tears-models for OpenRouter multi-provider access" is required, read
> > that as the July position, not the answer.
>
> The analysis below is retained because it is what produced that answer, and
> because § Answer 2 is still a live input. It is not a live recommendation.

The decision collapses to one question: **do you want 3tears agent memory?**

- **No** → zero infrastructure. Three-tier entities over a SQLite `DurableStore` L3
  — **required, not optional**: L1 is an in-memory cache, so it is the L3 that makes
  the catalogue survive a restart — plus `3tears-models` for OpenRouter
  multi-provider access. No Docker, no Postgres, no NATS.
- **Yes** → one Postgres instance, which then makes a Postgres L3 free since it is
  already running.

Nothing in between buys anything: NATS is only worth running to keep caches coherent
across multiple pods, and this product has one curation process.
