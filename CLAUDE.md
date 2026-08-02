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

Two independent projects, two interpreters, two suites. Both must pass.

| | 2024 modules (repo root) | curation plane |
|---|---|---|
| Test | `pytest tests` | `cd curation && uv run pytest` |
| Lint | `ruff check .` | `cd curation && uv run ruff check .` |
| Format | `black .` | `cd curation && uv run black .` |

Run the curation plane: `cd curation && uv run python -m curation`. It needs
`ART_ROOT` (copy `.env.example` to `.env`); the browser interface serves on
`CURATION_PORT`, its JSON API under `/api`, and MCP clients connect to `/mcp` on
the same port.

The curation suite boots a real uvicorn server per test class of surface work.
Do not replace that with an in-process ASGI transport: Starlette does not run a
mounted sub-app's lifespan, and the lifespan is what makes the MCP mount work,
so an in-process test would pass against an app that fails every real request.
