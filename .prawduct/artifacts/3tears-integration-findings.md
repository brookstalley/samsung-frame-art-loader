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

## The hard constraint: Python 3.14

**Every** 3tears package declares `requires-python = ">=3.14"` (verified across all
`packages/*/pyproject.toml`).

This collides directly with
[platform-and-dependency-findings.md](platform-and-dependency-findings.md), which
chose **Python 3.13 with a 3.12 fallback** for the Pi and explicitly rejected 3.14:
IT8951 compiles Cython from `.pyx` sources at install time and was last touched
2023-11, and aarch64 wheels for opencv/scikit-image may lag.

**3tears and the e-paper driver cannot share an interpreter.** This is the single
constraint that most shapes the architecture, and it is why the curation plane and
the display plane are separate processes on separate Python versions.

## Consequence for this product

The decision collapses to one question: **do you want 3tears agent memory?**

- **No** → zero infrastructure. Three-tier entities on L1 SQLite (optionally a
  SQLite `DurableStore` L3), plus `3tears-models` for OpenRouter multi-provider
  access. No Docker, no Postgres, no NATS.
- **Yes** → one Postgres instance, which then makes a Postgres L3 free since it is
  already running.

Nothing in between buys anything: NATS is only worth running to keep caches coherent
across multiple pods, and this product has one curation process.
