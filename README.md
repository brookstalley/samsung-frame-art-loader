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

**What remains at the hardware** — the check that a rotation still completes with
a second subscriber attached, and an unattended run across a television
power-cycle. Both need the television, not the panel.

**The label's typography is built**, as of 2026-08-14 and two panel sittings. The
first visit turned three numbers into a redesign and the second tuned it at the
wall. All of it has landed: the type floor derives from the panel's geometry and
its reading distance, the catalogue carries `family_name`/`given_name`, a short
`display_nationality` and a commentary field, the artist is set above the work,
the identification block is **two** lines — the name, then the biography beneath
it at the floor — the family name is set in bold capitals with the title in
italic, optional content is admitted in priority order, and a long name takes its
own line before it gives up its size, at a size a fifth larger when it does. What
is left over vertically is spent on the gaps rather than falling to the bottom, so
the top and bottom margins match.

*(This paragraph said "one line rather than three" until 2026-08-14. That was
true of the collapse built on 2026-08-11 and stopped being true two days later,
when the first sitting sent the biography to its own line — the block is two, and
the name may take a third rung of its own.)*

**The type floor has exactly one exception, and it is the point rather than a
lapse.** The facts that identify the work — the artist's name and the title —
*shrink* below the floor rather than being dropped, because a name too small to
read at 7 feet can still be read by somebody who steps closer and a name that is
not there cannot. Every such shrink is journalled as `label.shrunk` at WARNING,
which is the condition that ruling rests on: illegible type fails invisibly, and
the exception would reopen that hole if nothing named it. All of it is specified in
`accessibility-spec.md` — § Type never shrinks to fit for the two content tiers,
§ The label's content model for the ordering, the name ladder and the fill rule —
which is where it stays after the build plan that schedules it is archived.

**The label reached e-ink on 2026-08-11**, which it never had before: rotation
does not run while the set is in standby, so the label path had never executed on
hardware at all. The operator read a type ladder from the viewing position and
settled the floor at **12.4 arcminutes** of cap height, with 8.8′ as the absolute
minimum for content a reader steps closer for.

**The derived type floor landed the same day, and the provisional sizes are gone.** The label's
type is now derived from two values a deployment states — the panel's diagonal
and the distance it is read from — against that calibrated cap height, so a
second device with a different panel at a different distance gets a correct
answer with nobody visiting it. Those two have no defaults and never will: a
guessed distance gives silently illegible type, which is what this product
shipped for as long as the sizes were fixed. **An existing `.env` needs both keys
added or its device draws no label** — see `deploy/README.md`.

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
