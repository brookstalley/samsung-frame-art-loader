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

**Raspberry Pi OS Trixie ships Python 3.13. The curation plane gets its 3.14 from
a uv-managed standalone build: `uv python install 3.14`.**

> **Amended 2026-07-27.** The sentence above read "Nothing in this product needs
> 3.14 except `3tears`, whose packages declare `requires-python = ">=3.14"`". The
> catalogue takes no `3tears` core dependency at all now, so that is no longer the
> reason. The floor rests on `3tears-models` — the operator's own model adapters,
> which declare the same one and arrive with the discovery work — and on the
> verified fact that the whole curation dependency set resolves and imports on
> CPython 3.14.4. **Everything in this section that reasons about `3tears` core
> should be read through this amendment**, including the build-versus-relax
> analysis below, which is retained because it is why the floor is affordable, not
> as a live dependency claim.

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

> **Rationale re-based 2026-07-27** (see the amendment at the head of this section). The paragraphs around this one reason about `3tears` *core*, which this product no longer depends on at all — the catalogue's durable tier is first-party code shaped to that framework's contract, and no framework package is imported. The 3.14 floor still stands, and the compile-cost analysis above is still the reason it is affordable, but what now *requires* it is `3tears-models` — the operator's own model adapters, which the discovery work calls and which declare the same floor — plus the verified fact that the whole curation dependency set resolves and imports on CPython 3.14.4. Nothing below should be read as a live dependency on `3tears` core.


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

**No unit may rely on systemd's stock start rate limit** (settled 2026-08-02).
The default is five starts in ten seconds, and `Restart=always` with a fault that
reproduces on every start exhausts it in about half a second — leaving the unit
permanently `failed`, having logged five lines, with nothing still trying. That
defeats the success criterion requiring an unattended failure to be visible
without inspecting the wall: it produces a dark television *and* a service that
gave up. Every unit therefore sets `StartLimitIntervalSec=0` in `[Unit]` (the
documented value for no rate limiting, and a `[Unit]` directive rather than a
`[Service]` one) together with a `RestartSec=` of at least five seconds, so a
persistent fault stays legible in `systemctl status` and keeps writing to the
journal instead of going quiet. The retry interval is also what makes the setting
safe: without it, "retry forever" would mean retrying at 100 ms.

*(Applied to the recovered 2024 loader unit on 2026-08-02, which is the plane
running the wall today. The rule is stated for all units rather than that one,
because the same defaults ship with every unit file and the new display and
curation units are written against this section.)*

## Configuration

Environment variables via **one `.env` at the repository root, read by both
planes**, honouring the existing norm that deployment values never live in source.

**Every unit declares `EnvironmentFile=` pointing at that root `.env`, and never
prefixes it with `-`** (settled 2026-08-02). Both halves are the decision.

*Declared*, because the alternative on the table was to record the
`.env`-beside-`WorkingDirectory` placement as the contract and leave the unit
silent about it. A unit that names the file states its own dependency; one that
relies on a library's search path leaves the dependency discoverable only by
reading Python. The two resolve to the same file today, so this buys no new
capability — it buys the failure being attributable.

*Un-prefixed*, because that is the half that does real work. systemd treats a
missing un-prefixed `EnvironmentFile=` as fatal and refuses to start the unit,
naming the path it wanted. A `-` prefix makes it optional, which restores exactly
the silent failure this is meant to remove: the process starts, raises at import
against five missing variables, and dies for a reason nobody connects to a file
that was never placed.

**The directive is a presence guard, not the value source.** `load_dotenv(override=True)`
re-parses the same file inside the process and wins, so systemd's parser and
python-dotenv's cannot disagree about what the process ends up seeing — only
about whether the unit starts at all. Anything relying on the two parsers
agreeing on quoting or inline comments would be relying on something this
arrangement does not promise.

*(Settled 2026-08-01: this said "a `.env` file per plane", and what exists is one
shared root file — `.env.example` carries both planes' values, and
`curation/config.py`'s bare `load_dotenv()` resolves it by walking up from the
module rather than from the working directory. One file is also the right answer
rather than merely the built one: the two values that **must** agree across planes
are `ART_ROOT` and the panel geometry, and two files are precisely how they come
to disagree. This matters before the systemd units are written — a per-plane
`.env` dropped beside a unit's `WorkingDirectory` is not the file the curation
plane reads, so it would be edited and have no effect.)*

**Two values must agree across both planes**, and both are silent failures when
they do not.

`ART_ROOT` is the first, which makes it the highest priority to hoist — already
scoped that way in the v1 list. A mismatch is a silent failure: curation writes
manifests nobody reads and display waits forever on a file that will never appear.

**`ART_ROOT` is also the only value both planes share** (corrected 2026-07-20).
Panel geometry was briefly listed as a second shared value; it is not, because
"panel geometry" named two different physical panels:

- **TV panel physical geometry** (reference: 42") — **curation only**. The mat is
  specified in physical units and the resolution floor is a minimum size on the
  wall, so curation needs it to judge whether a source is adequate, to show the
  curator what a work would look like, and to compose the mat. Display receives the
  `tv_display` rendition with the mat already in it and never needs the TV's size.

  *(**Three values joined it on 2026-08-01** and are curation-only for the same
  reason: `MAT_WIDTH_INCHES`, `MAT_BOTTOM_WEIGHT` and `RESOLUTION_FLOOR_INCHES`.
  Panel geometry alone does not fix the artwork box — the mat has to be
  subtracted from it — so until these were configurable the box could not be
  constructed at all, and the readiness verdict that depends on it had been built
  and tested with no production caller. Each defaults to the reference
  deployment's figure, and the resolved box is logged at startup beside the panel
  it came from, because a wrong mat is otherwise visible only as works being
  labelled oddly in the review grid.)*
- **E-paper panel geometry** (1448×1072) — **display only**, for label typesetting.

Because neither is shared, neither can drift between planes. A wrong TV size is
still a real defect — the mat comes out the wrong width and the review grid's
warnings are computed against a TV that isn't there — but it is a single-plane
misconfiguration, not a cross-plane mismatch. **Nothing may hardcode either panel's
size**; the reference deployment is a 42" Frame but the product must run on any.

**Each plane logs its resolved `ART_ROOT` and its own panel geometry at startup**,
so a misconfiguration is one journal line away rather than a mystery.

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
| **Verify the spend ceiling** | In the OpenRouter console, confirm the key in `OPENROUTER_API_KEY` still carries a **USD 20 credit limit with a monthly reset**. **This setting is the entire cap** — nothing in this repository enforces one, by ratified decision, because an application-side meter that fails open is indistinguishable from one that works. A key whose limit was cleared, or a key swapped for an uncapped one, looks identical on every surface the product exposes right up to the bill. `cd curation && uv run pytest -m live_api` asserts it mechanically (`test_the_key_reports_a_monthly_ceiling`) and costs a few cents to run |
| Bound the journal | `SystemMaxUse=` in `journald.conf`. **Set this explicitly** — see below |
| Patch curation's CPython | `uv python upgrade 3.14`, then rebuild the venv and restart. **`apt upgrade` does not do this** — it patches the display plane's 3.13 only |
| Re-pair the TV | Rotates the pairing token. Nothing to untrack first — `token_file` was untracked 2026-07-27 and the token now resolves under `ART_ROOT`, outside the checkout, so a `git pull` no longer deletes it and re-pairing needs no repo work at all. Just re-pair at the hardware. *(Updated 2026-08-01: this row still ordered an untracking step that is done, and carried a `git pull` hazard `security-model.md` withdrew on 2026-07-27.)* See `security-model.md` |

## Failure Recovery

Mostly automatic; the table below is what a human would do when it is not.

| Symptom | First check | Action |
|---|---|---|
| TV showing one artwork indefinitely | Health panel: heartbeat age | If stale, `systemctl status display` and the journal |
| Label disagrees with the artwork | Journal for e-paper errors | The label path failed while rotation continued — by design, a panel failure never stops the TV |
| A theme shows fewer works than expected | The manifest build's exclusion report | It names the per-work reason. This is the designed surface, not a diagnostic dead end |
| Discovery refuses to start | The refusal text itself — it names the cause | *(Corrected 2026-08-02: this row sent the operator to `limit_remaining` on the health panel, a figure no surface exposes and which may not be trusted anyway — it lags by minutes, and was observed reporting credit remaining while live calls were already being refused.)* Two different refusals: **no key configured** says so and names `.env`; a run that started and then **halted_by_budget** means the provider refused the spend, for which the answer is the monthly UTC reset or a raised key limit |
| `resolve_images` refuses work ids as "already in flight" | The named run's status | It is always a `resolve` run, and a live one is always `resolving_images`. If it is genuinely searching, wait or `cancel` it. If nothing is actually working, startup reconciliation should have moved it to `interrupted`; that it did not is a bug, not an operator action. *(Corrected 2026-07-27: this row previously told the operator to approve or decline an `awaiting_approval` run to free the ids — a state a resolve run can never reach, so the advice named a run that cannot exist.)* |
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

**Third risk: the norms with no mechanical enforcement.** *(Re-scoped 2026-07-27.
This read "no test suite exists — zero tests across 2,216 lines"; that departure was
closed the same day and both planes now have suites, so the risk is no longer
absence of testing but the specific norms nothing yet checks.)* The **plane-isolation
test** that enforces a ratified Direction norm is still filed and unbuilt (issue #7),
and the service-layer norm's own enforcement column says "Critic" — a reviewer
reading handlers, with no test that fails when logic creeps into a binding.
