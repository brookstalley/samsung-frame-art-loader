# samsung-frame-art-loader

Curated art on a Samsung Frame TV, with a matching e-paper label beside it.

The design is two independent planes on one Raspberry Pi, sharing a directory and
exactly one file between them:

- **curation** (`curation/`, Python 3.14) — the catalogue, discovery, image
  preparation, an HTTP API and an MCP server. It writes the theme manifest.
  **Built**, and the only plane with code in it today.
- **display** (`display/`, Python 3.13 on the Pi; 3.12 declared floor) — polls that manifest, drives
  the TV and the e-paper panel, and keeps showing art whether or not curation is
  running. **Not built yet:** `display/` holds a project manifest and no module,
  so the package exists as a place for the first one to land and nothing more.
  The root `display.py` is a 2024 module and does none of this.

**What runs the wall right now is the 2024 loader at the repository root**, and it
does so until the display plane exists. Said plainly because a reader who takes
the design for the state would look for a package that is not there, and because
the manifest curation already writes has, for now, nothing on the other end of it.

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

`.env` supplies defaults and an exported variable beats it, so a run against a
scratch tree needs no edit to the file: `ART_ROOT=/tmp/scratch uv run python -m
curation`.

Then open `http://127.0.0.1:$CURATION_PORT/` — the browser interface serves the
catalogue, discovery runs, themes, the wall manifest and a health view. MCP
clients connect to `/mcp` on the same port, and the UI's own JSON API answers
under `/api`.
