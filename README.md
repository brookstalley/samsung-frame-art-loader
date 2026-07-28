# samsung-frame-art-loader

Curated art on a Samsung Frame TV, with a matching e-paper label beside it.

Two independent planes on one Raspberry Pi, sharing a directory and exactly one
file between them:

- **curation** (`curation/`, Python 3.14) — the catalogue, discovery, image
  preparation, an HTTP API and an MCP server. It writes the theme manifest.
- **display** (Python 3.13) — polls that manifest, drives the TV and the e-paper
  panel, and keeps showing art whether or not curation is running.

The 2024 loader still runs the wall from the repository root and is retired once
the new planes take over.

## Where things are written down

| For | Read |
|---|---|
| Running the tests, the linters, and the curation plane | `CLAUDE.md` |
| Every environment variable, and which are required | `.env.example` |
| The systemd units and their caveats | `deploy/README.md` |
| Why any of it is shaped this way | `.prawduct/artifacts/` |

## Quick start

```sh
cp .env.example .env          # then set ART_ROOT
cd curation && uv run python -m curation
```

The browser interface is not built yet; the MCP server answers at `/mcp` on
`CURATION_PORT`.
