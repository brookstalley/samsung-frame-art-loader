# samsung-frame-art-loader

Curated art on a Samsung Frame TV, with a matching e-paper label beside it.

The design is two independent planes on one Raspberry Pi, sharing a directory and
exactly one file between them:

- **curation** (`curation/`, Python 3.14) — the catalogue, discovery, image
  preparation, an HTTP API and an MCP server. It writes the theme manifest.
  **Built.**
- **display** (`display/`, Python 3.13 on the Pi; 3.12 declared floor) — polls that manifest, drives
  the TV and the e-paper panel, and keeps showing art whether or not curation is
  running. **Built.** It reads the manifest, rotates the active theme over the
  television, keeps its own record of what that set is holding, executes the
  `next` and `show_now` directives the manifest carries, renders the wall label
  onto this device's own surface, and writes the heartbeat curation's health panel
  reads. `deploy/curation.service` and `deploy/display.service` are written.
  The root `display.py` is a 2024 module and does none of this.

**Both new planes now run on the Pi, from systemd, as of 2026-08-11.** The `tvpi`
service account exists, `ART_ROOT` is `/srv/art`, the checkout is at
`/opt/samsung-frame-art-loader`, and `display.service` and `curation.service` are
installed and enabled. The catalogue was seeded there from the 2024 index — 40
works — and the display plane reconciled the television against a manifest and
re-uploaded the theme without a warning. `deploy/README.md` § The cutover is the
record and the procedure.

That was a **first install, not a swap**: nothing of this product was running
unattended on that machine beforehand, so the 2024 loader at the repository root
stopped being the answer to "what runs the wall" some time before this, not at the
cutover. Those modules are still present and are deleted at the legacy retirement.

**What remains is what only a person standing in front of the hardware can do**:
the label's type sizes, its margin and a line-length bound, all three still marked
provisional in source; the check that a rotation still completes with a second
subscriber attached; and an unattended run across a television power-cycle. The
label renders into a surface today and **has never been drawn onto e-ink**.

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
