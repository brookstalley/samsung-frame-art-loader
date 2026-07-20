---
artifact: operational-spec
version: 1
depends_on:
  - artifact: architecture
  - artifact: nonfunctional-requirements
  - artifact: observability-strategy
last_validated: null
---

# Operational Specification

One machine, two systemd units, one shared directory. Operations here should be
boring, and this document exists mostly to make sure the two things that are *not*
boring — getting Python 3.14 onto a Pi, and having a restore path that actually
works — are decided rather than discovered.

## Deployment Target

| | |
|---|---|
| Host | Raspberry Pi 4 Model B, 8 GB |
| OS | Raspberry Pi OS Trixie (Debian 13) |
| Boot media | SD card — see Risks |
| Processes | `curation` (Python 3.14) and `display` (Python 3.13), both under systemd |
| Shared state | `ART_ROOT` on local disk |

## The Python 3.14 Problem — flagged, not solved

**Raspberry Pi OS Trixie ships Python 3.13. Nothing in this product needs 3.14
except `3tears`, whose packages declare `requires-python = ">=3.14"` — and the
2026-07-19 audit found that requirement removable in 16 mechanical source sites,
with no third-party dependency imposing a floor above 3.10.**

While curation was going to run on a desktop or NAS, 3.14 was free. Co-locating
onto the Pi changed the price and nobody has re-priced it. The options:

1. **Build 3.14 on the Pi with pyenv.** Roughly 30–45 minutes of compile on a Pi 4,
   repeated for every patch release you want to pick up. Works, costs nothing but
   time, and is the path of least decision.
2. **Relax 3tears to 3.13** (the 16 sites) and run both planes on the system
   interpreter. Removes the build entirely. Note the knock-on: the Python version
   pin is the *first* listed surviving rationale for the two-plane split, so this
   would leave the split resting on its other two legs — the wall staying lit
   through a curation restart, and e-paper behind a process boundary. Both are
   real, and the operator has already chosen to keep the split, but the change
   should be made knowingly.
3. **Run curation in a container** from a `python:3.14` base image. No compiling,
   but it adds Docker to a product whose operator explicitly ruled out heavy
   infrastructure, and it complicates the shared-directory design that the whole
   inter-plane contract now rests on.

**This is unresolved and is tracked as an open question.** It does not block the
artifacts, but it does block the first build chunk, because it determines what
interpreter the curation venv is built against.

## Process Management

Two systemd units, no ordering dependency between them — neither plane requires
the other to start, so either may come up first, in any order.

**`display`** — `Restart=always`. It is the plane whose downtime is visible, and
it should come back from anything without human action. Survives TV power-cycles,
websocket drops, and network outages by design.

**`curation`** — `Restart=on-failure`, plus a `MemoryMax`. The memory cap is the
one non-obvious setting and it exists because of co-location: a runaway
acquisition (a genuine gigapixel scan is 20–40× the measured corpus maximum) must
not be able to invoke the OOM killer against the display plane. Capping curation
converts a shared-fate failure into a contained one, which is most of what the
process split is for on a single box.

## Configuration

Environment variables via a `.env` file per plane, honouring the existing
Critic-enforced norm that deployment values never live in source.

`ART_ROOT` is the one value both planes must agree on, which makes it the highest
priority to hoist — already scoped that way in the v1 list. A mismatch between the
two planes' `ART_ROOT` is a silent failure: curation writes manifests nobody reads
and display waits forever on a file that will never appear. **Both planes log their
resolved `ART_ROOT` at startup**, so the mismatch is one journal line away rather
than a mystery.

Secrets live in `.env`, never in source, never in a committed file — the
repository is public (`security-model.md`).

## Backup and Restore

**What is backed up: the catalogue, and nothing else.** The image tree is
deliberately excluded — every source image is re-fetchable from its source URL,
while the curatorial layer (verdicts, canonical-instance choices and their
reasons, hand-approved mat colours, theme membership, suppression scopes) is not
reproducible at any price except re-running discovery and re-asking the curator
every judgement they have already made.

**Destination: another machine on the network** (desktop or NAS, over LAN or the
overlay network). Decided 2026-07-20. No third party, no cost, no credential on
the Pi beyond what already exists.

**Accepted limitation:** it only protects you if the destination is awake when the
backup runs. So the schedule assumes gaps and the retention keeps several
generations rather than one — a backup that silently stopped succeeding a month ago
is the failure mode, and it is the same silent-failure class as everything else in
this product. **Backup age is surfaced on the health panel** in absolute terms
alongside the display heartbeat: "last successful backup: 6 days ago".

**Use SQLite's backup API or `VACUUM INTO`, not a file copy.** Copying a SQLite
file out from under a live writer can capture a torn database. This is the sort of
thing that appears to work for a year and then does not.

### The restore path is a deliverable, not a paragraph

**A backup path that has never been restored from is a hope.** The restore path
ships with an exercise step: restore onto a scratch directory and confirm the
system comes up against it.

The design makes this unusually cheap to verify, and the reason is worth
understanding. **Restore is partial by design.** Drop the catalogue back with an
empty image tree, and:

- the manifest build finds no current render for any work,
- it excludes them all *and reports why*, per work,
- the health panel shows a theme with everything excluded and the reason,
- re-acquisition refills the tree, and works reappear as they complete.

The system self-heals **visibly**. Verifying a restore therefore does not require
staging gigabytes of imagery — which is exactly what makes the exercise something
that will actually get run rather than skipped.

## Routine Operations

| Operation | Procedure |
|---|---|
| Deploy | `git pull`, then `systemctl restart` each unit. No migration spans the planes — the manifest is regenerated, never migrated |
| Rollback | `git checkout` the previous commit, restart both |
| Restart one plane | Safe at any time, in either order. The other is unaffected by design |
| Add disk headroom | Prune `tile-cache/` and `temp/` — working space, not steady-state storage, sized by the largest single work in flight |
| Re-pair the TV | Rotates the pairing token. **Do this before untracking `token_file`**, not after — see `security-model.md` |

## Failure Recovery

Mostly automatic; the table below is what a human would do when it is not.

| Symptom | First check | Action |
|---|---|---|
| TV showing one artwork indefinitely | Health panel: heartbeat age | If stale, `systemctl status display` and the journal |
| Label disagrees with the artwork | Journal for e-paper errors | The label path failed while rotation continued — by design, a panel failure never stops the TV |
| A theme shows fewer works than expected | The manifest build's exclusion report | It names the per-work reason. This is the designed surface, not a diagnostic dead end |
| Discovery refuses to start | `limit_remaining` on the health panel | If zero, the monthly UTC reset or a raised key limit |
| Acquisition fails on every work | Free disk space | The pre-acquisition guard should have caught it; if it did not, that is a bug in the guard |
| Neither plane starts after a reboot | Both planes' resolved `ART_ROOT` in the journal | Mismatched or missing `ART_ROOT` is the likely cause |

## Risks

**The SD card is the top operational risk, and it carries the irreplaceable
asset.** Write-heavy tile caching plus ~10 GB of artwork on consumer flash, with
`catalogue.sqlite` on the same device, in an always-on machine subject to
unexpected power loss. SQLite plus power loss on consumer flash is the classic Pi
corruption story.

This is what makes the backup *and restore* path load-bearing rather than
diligent. Two cheap mitigations, neither yet decided: move `ART_ROOT` and the
catalogue to USB storage, or move to SSD boot entirely. Either closes it.

**Second risk: vendor removal of the TV art-mode API.** Samsung has already
removed art mode from some units via firmware (1710, Sept 2025). The operator
confirmed it works today, so the risk is prospective rather than present — but the
capability the entire product rests on is controlled by a vendor who has withdrawn
it before, and auto-update could do it here. Worth establishing whether TV
auto-update can be disabled.

**Third risk: no test suite exists.** Zero tests across 2,216 lines, and the plane-
isolation test that enforces a ratified norm is filed but unbuilt (issue #7).
Recorded as a departure in `project-preferences.md`; blocking for medium+ work.
