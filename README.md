# samsung-frame-art-loader

Curated art on a Samsung Frame TV, with a matching e-paper label beside it.

The design is two independent planes on one Raspberry Pi, sharing a directory and
exactly one file between them:

- **curation** (`curation/`, Python 3.14) — the catalogue, discovery, image
  preparation, an HTTP API and an MCP server. It writes the theme manifest.
  **Built.**
- **display** (`display/`, Python 3.13 on the Pi; 3.12 declared floor) — polls that manifest, drives
  the TV and the e-paper panel, and keeps showing art whether or not curation is
  running. **Built as of 2026-08-06, except the panel:** it reads the manifest,
  rotates the active theme over the television, keeps its own record of what that
  set is holding, and executes the `next` and `show_now` directives the manifest
  carries. The e-paper label, the heartbeat and the systemd units are the next
  chunk. The root `display.py` is a 2024 module and does none of this.

**What runs the wall day to day is still the 2024 loader at the repository root.**
The new display plane has now driven the real television — on 2026-08-07 it
rotated a theme unattended, confirmed every picture against the set, survived a
restart without moving the wall, and kept going with the curation plane stopped.
It did so **from a development Mac, not from the Pi**, so what is proven is the
plane's behaviour against real hardware rather than the deployment: the systemd
units, the panel and the Pi itself are the next chunk, and that is the cutover.
Take the plane as working and not yet deployed.

## Where things are written down

| For | Read |
|---|---|
| Running the tests, the linters, and the curation plane | `CLAUDE.md` |
| Every environment variable, and which are required | `.env.example` |
| The systemd units and their caveats | `deploy/README.md` |
| Why any of it is shaped this way | `.prawduct/artifacts/` |

## Quick start

```sh
cp .env.example .env                       # then set ART_ROOT
cd curation && uv run python -m curation --init   # once, to make ART_ROOT an art root
cd curation && uv run python -m curation          # every run after that
```

**`--init` is needed once per art root, and leaving it out is the point.** The
plane refuses to start against a directory that is neither marked as an art root
nor already holding a catalogue, because the alternative is what it used to do: a
typo in `ART_ROOT` created the directory, created an empty catalogue, and started
cleanly, leaving the operator with a working plane and an empty collection. An
existing art root needs nothing — a directory holding a catalogue is one by
better evidence than a marker.

`.env` supplies defaults and an exported variable beats it, so a run against a
scratch tree needs no edit to the file — with the same one-time flag the first
time, since a scratch tree is a new art root:
`ART_ROOT=/tmp/scratch uv run python -m curation --init`.

Then open `http://127.0.0.1:$CURATION_PORT/` — the browser interface serves the
catalogue, discovery runs, themes, the wall manifest and a health view. MCP
clients connect to `/mcp` on the same port, and the UI's own JSON API answers
under `/api`.
