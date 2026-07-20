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
| Processes | `curation` (Python 3.14, uv-managed standalone) and `display` (Python 3.13, system interpreter), both under systemd |
| Shared state | `ART_ROOT` on local disk |

## The Curation Interpreter — decided

**Raspberry Pi OS Trixie ships Python 3.13. Nothing in this product needs 3.14
except `3tears`, whose packages declare `requires-python = ">=3.14"`. The curation
plane gets its 3.14 from a uv-managed standalone build: `uv python install 3.14`.**

The premise that made this a problem was wrong. It was recorded as a choice
between a 30–45 minute pyenv compile per patch release, relaxing `3tears` to 3.13,
or adding Docker — and the first of those set the price. But a prebuilt CPython
3.14 for this exact target already exists and is what uv installs:

```
cpython-3.14.4-linux-aarch64-gnu
  releases.astral.sh/github/python-build-standalone/releases/download/
  20260414/cpython-3.14.4+20260414-aarch64-unknown-linux-gnu-install_only_stripped.tar.gz
```

Verified 2026-07-20 against `uv python list --all-platforms --all-arches`. It is a
download and extract — no compiler, no build dependencies, minutes at most. Trixie's
glibc is far above the build's baseline, and the Pi is aarch64, which is the same
fact the wheel audit already established.

So the compile cost that made relaxing `3tears` attractive does not exist. That
matters beyond convenience: relaxing `3tears` carried a real, *untested* behavioural
risk — asyncio internals and pydantic/langchain annotation resolution under eager
(3.13) versus lazy (3.14) `__annotations__`, which the 2026-07-19 audit could not
close because it was static. Keeping `3tears` unmodified means that risk never has
to be taken, and the Python version pin stays intact as a rationale for the
two-plane split rather than leaving the split on its other two legs.

**The tradeoff this does incur:** curation's interpreter now comes from Astral's
distribution channel rather than Debian's, so CPython security fixes arrive via
`uv python upgrade`, not `apt upgrade`. That is a real patching obligation and it is
recorded in `security-model.md` § Supply Chain and in Routine Operations below.
The display plane is unaffected — it stays on the system 3.13, which is what gives
it the distro C bindings the e-paper driver needs.

**A standalone interpreter cannot see distro site-packages.** That is fine here, and
only because label rendering already moved to the display plane: curation's stack
(FastAPI, opencv, scikit-image, numpy, pydantic) is all wheels, verified against the
PyPI JSON API. `pycairo` — the one source-only aarch64 dependency — is on the
display side, where the GTK stack already lives. **If anything needing distro C
bindings is ever added to curation, this decision is what it breaks.**

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

**Two values must agree across both planes**, and both are silent failures when
they do not.

`ART_ROOT` is the first, which makes it the highest priority to hoist — already
scoped that way in the v1 list. A mismatch is a silent failure: curation writes
manifests nobody reads and display waits forever on a file that will never appear.

**Panel geometry is the second (added 2026-07-20).** The mat is specified in
physical units and the resolution floor is a minimum size on the wall, so both
planes need the panel's dimensions: curation to judge whether a source is adequate
and to show the curator what a work would look like, display to render the mat. A
mismatch is quieter than the `ART_ROOT` one and therefore worse — nothing fails,
the mat is simply the wrong width and the review grid's warnings are computed
against a TV that isn't there. **Nothing may hardcode a panel size**; the reference
deployment is 42" but the product must run on any Frame.

**Both planes log their resolved `ART_ROOT` and panel geometry at startup**, so
either mismatch is one journal line away rather than a mystery.

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
| Bound the journal | `SystemMaxUse=` in `journald.conf`. **Set this explicitly** — see below |
| Patch curation's CPython | `uv python upgrade 3.14`, then rebuild the venv and restart. **`apt upgrade` does not do this** — it patches the display plane's 3.13 only |
| Re-pair the TV | Rotates the pairing token. **Untrack `token_file` FIRST, then re-pair** — corrected 2026-07-20; the reverse order commits the new token. Note the untracking commit deletes the file on `git pull`, so TV auth is down until the re-pair — do both in one sitting, at the hardware. See `security-model.md` |

## Failure Recovery

Mostly automatic; the table below is what a human would do when it is not.

| Symptom | First check | Action |
|---|---|---|
| TV showing one artwork indefinitely | Health panel: heartbeat age | If stale, `systemctl status display` and the journal |
| Label disagrees with the artwork | Journal for e-paper errors | The label path failed while rotation continued — by design, a panel failure never stops the TV |
| A theme shows fewer works than expected | The manifest build's exclusion report | It names the per-work reason. This is the designed surface, not a diagnostic dead end |
| Discovery refuses to start | `limit_remaining` on the health panel | If zero, the monthly UTC reset or a raised key limit |
| `resolve_images` refuses work ids as "already in flight" | The named run's status | If `awaiting_approval`, that is **healthy** — the run is waiting for you, so approve or decline it and the ids free up. If `resolving_works` or `resolving_images` with nothing actually working, startup reconciliation should have moved it to `interrupted`; that it did not is a bug, not an operator action |
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

**Journal growth is an unguarded path to that same failure.** Structured logging is
the product's primary observability signal and both planes log continuously to the
journal, on a machine whose top risk is disk. **`SystemMaxUse=` must be set
explicitly in `journald.conf`** rather than left to the default, which sizes itself
as a fraction of the filesystem — so it grows with the disk you were trying to
protect. The pre-acquisition free-space guard cannot see this: it is curation-side
and checks before a fetch, while the journal fills between fetches and from the
display plane, which never fetches anything.

**Second risk: vendor removal of the TV art-mode API.** Samsung has already
removed art mode from some units via firmware (1710, Sept 2025). The operator
confirmed it works today, so the risk is prospective rather than present — but the
capability the entire product rests on is controlled by a vendor who has withdrawn
it before, and auto-update could do it here. Worth establishing whether TV
auto-update can be disabled.

**Third risk: no test suite exists.** Zero tests across 2,216 lines, and the plane-
isolation test that enforces a ratified norm is filed but unbuilt (issue #7).
Recorded as a departure in `project-preferences.md`; blocking for medium+ work.
