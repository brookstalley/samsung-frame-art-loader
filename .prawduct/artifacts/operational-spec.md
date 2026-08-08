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

## The Service Account — decided

**Both units run as `tvpi`** (settled 2026-08-04). The name was the only part in
question and it is kept: it is what the committed unit, `deploy/README.md` and
this product's own history already say, and renaming would have bought nothing
but a diff across every one of them.

The account itself does not exist on the machine. The Pi was rebuilt onto a fresh
card and `tvpi` did not survive it — see `platform-and-dependency-findings.md`
§ That card is gone. What has to be created:

| | |
|---|---|
| Login | None. `--system`, no password, shell `/usr/sbin/nologin` |
| Privilege | No sudo. Nothing either plane does needs root |
| Groups | `spi` and `gpio` — the e-paper HAT is reached through both |
| Owns | `ART_ROOT`, and the checkout the units execute from |

**Create it as part of the systemd-unit cutover, not before.** The account, its
group memberships, moving `ART_ROOT` under it, and both unit files are one
change: any of them landing alone leaves a machine that is neither the old
arrangement nor the new one. That cutover is the work that installs the new
systemd units, and this account is created as part of it.

**`ART_ROOT` is not settled by this section.** The committed unit puts the art
tree at `/home/tvpi/art`, inside a home directory that a service account with no
login has no other use for. A neutral path — `/srv/art` or `/var/lib/samsung-art`
— matches what the account actually is, and is the shape to prefer at cutover.
Deciding it costs nothing today because every reader of that path is already
configuration: `ART_ROOT` in the root `.env`, which is where the existing norm
against deployment values in source put it.

## The Curation Interpreter — decided

**Raspberry Pi OS Trixie ships Python 3.13. The curation plane gets its 3.14 from
a uv-managed standalone build: `uv python install 3.14`.**

> **Amended 2026-07-27, amended again 2026-08-02.** The sentence above read
> "Nothing in this product needs 3.14 except `3tears`, whose packages declare
> `requires-python = ">=3.14"`", and the first amendment replaced that with
> `3tears-models`, "which arrive with the discovery work". Both are retired: the
> catalogue takes no `3tears` core dependency, and `3tears-models` went to the
> opt-in `eval` group on 2026-08-02. **What holds the floor is stated once, in
> `project-preferences.md` § Language & Runtime — this amendment deliberately does
> not restate it**, because restating it here is what let a retired claim survive
> two revisions in this file. The short of it is that no default dependency
> requires 3.14 today. **Everything in this section that reasons about `3tears` core
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

> **Rationale re-based 2026-07-27, re-based again 2026-08-02** (see the amendment at the head of this section). The paragraphs around this one reason about `3tears` *core*, which this product no longer depends on at all — the catalogue's durable tier is first-party code shaped to that framework's contract, and no framework package is imported. The compile-cost analysis above is still the reason the floor is affordable, which is why it is retained. **What the floor rests on is stated once, in `project-preferences.md` § Language & Runtime, and is not restated here.** The claim this passage used to carry — that `3tears-models` "requires" 3.14 and "the discovery work calls it" — was retired on 2026-08-02 when that package moved to the opt-in `eval` group. Nothing below should be read as a live dependency on `3tears` core, and nothing here should be read as evidence that a default dependency needs 3.14.


**The tradeoff this does incur:** curation's interpreter now comes from Astral's
distribution channel rather than Debian's, so CPython security fixes arrive via
`uv python upgrade`, not `apt upgrade`. That is a real patching obligation and it is
recorded in `security-model.md` § Supply Chain and in Routine Operations below.
The display plane is unaffected — it stays on the system 3.13, which is what gives
it the distro C bindings the e-paper driver needs.

**A standalone interpreter cannot see distro site-packages.** That is fine here, and
only because label rendering already moved to the display plane: curation's stack
(FastAPI, starlette, uvicorn, mcp, python-dotenv, pydantic, pillow, httpx) is all
wheels, verified against the PyPI JSON API. `pycairo` — the one source-only aarch64
dependency — is on the display side, where the GTK stack already lives. **If
anything needing distro C bindings is ever added to curation, this decision is what
it breaks.**

> **Corrected 2026-08-04, and the correction makes the argument stronger rather
> than weaker.** This sentence named *opencv, scikit-image and numpy* as part of
> curation's stack. They were forecast for "acquisition and the mat engine" and
> never declared: both landed 2026-08-03 needing none of the three, and
> `curation/pyproject.toml` now records that as **a rejection rather than a
> deferral** — the LAB conversion and CIEDE2000 distance are thirty lines of
> fully-specified arithmetic in `acquisition/color.py`, and the dominant-colour
> fallback uses Pillow's median-cut quantiser where 2024 used OpenCV k-means.
>
> Worth noting how this survived: the same bundle that made the rejection wrote
> the rule that a descope must be walked back through every artifact that promised
> it, walked back the *fixture* descope, and left this one. The forecast lived in
> a sentence about interpreters, which is not where anyone looks when deciding a
> dependency.

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

**The directive is the value source — corrected 2026-08-06.** It was a presence
guard while `config.py` called `load_dotenv(override=True)`, which re-parsed the
same file inside the process and won. That `override=True` was retired, because
discarding an exported value in silence is this product's worst failure shape, so
python-dotenv now supplies *defaults* and whatever is already in the environment
wins. systemd has put this file's contents there before the process starts.

So the guarantee inverted, and the paragraph this replaces asserted the old one.
The two parsers **can** now disagree about what the process sees — they differ on
quoting and inline comments — and a mis-parsed value is live rather than
overwritten.

**Which plane is exposed, stated precisely, because a first version of this
correction was not.** `curation.art_root` refuses to start against a directory
that is neither marked nor holding a catalogue, so a mis-parsed `ART_ROOT`
reports an error rather than quietly creating an empty second collection — for
the *curation* plane. The unit in `deploy/` starts `tvart.py`, the 2024 plane,
which reads `ART_ROOT` through the root `config.py` and calls `os.makedirs` on
what it finds. There is no curation unit there yet, so pointing at that guard
from the unit's own comment claimed a protection the process it starts does not
have.

For the 2024 plane the exposure stands. The other four required values raise at
import when a mis-parse leaves them empty, which covers the common case;
`ART_ROOT` is the one that silently creates instead. It closes when that plane is
retired and the curation unit lands beside it.

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

- **TV panel physical geometry** (this deployment: 50") — **curation only**. The mat is
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

  *(**Three more joined them on 2026-08-03**, when the mat engine landed, and are
  curation-only for a different reason — display never asks a model anything:
  `MAT_MODEL`, `MAT_MAX_OUTPUT_TOKENS` and `MAT_IMAGE_MAX_EDGE`. The middle one
  is a correctness value rather than a limit: a reservation that does not clear
  the model's *reasoning* budget returns empty content billed in full, and the
  work is then matted by the mechanical fallback with only `MatColor.method`
  recording that anything went wrong. The model is logged at startup alongside
  the discovery model, and a deployment with no `OPENROUTER_API_KEY` logs that
  every mat will come from the dominant colour — which is a supported deployment,
  not a failure, but one worth reading in the journal rather than inferring from
  forty rows.)*
- **E-paper panel geometry** (1448×1072) — **display only**, for label typesetting.

  *(**Became configuration on 2026-08-06**, with the display plane's first
  modules: `EPD_PANEL_WIDTH_PX` and `EPD_PANEL_HEIGHT_PX`, defaulting to the
  reference panel's figures. Until then it was a number in prose, which is the
  same standing the TV's geometry had before it was hoisted — and the rule below
  that nothing may hardcode either panel's size applies to this one too. The
  plane logs the resolved pair at startup beside its `ART_ROOT`.)*

  *(**Read for the first time on 2026-08-07**, when the label reached the panel.
  Three values joined it, all display-only and all optional:*

  - *`EPD_DEVICE` — omni-epd's identifier for this device's panel
    (`waveshare_epd.it8951` on the reference wall, `omni_epd.mock` where the
    driver is installed and no panel is attached). **Empty means this device
    draws no label, which is a supported deployment rather than a broken one** —
    most display devices are a television and nothing else. It is also what
    decides whether the two optional dependency groups are needed at all, so it
    is the one value that changes what has to be installed.*
  - *`EPD_MARGIN_PX` (40) — the clear border. **Provisional**, and settled by the
    same look at the real panel that settles the type sizes: it trades border
    against how many lines fit before the label's drop rule takes one off.*
  - *`EPD_ROTATE_DEGREES` (180) — how far the frame is turned before it reaches
    the panel, the reference wall's panel being mounted ribbon-uppermost. Only 0
    and 180 are accepted; a quarter turn exchanges the panel's width and height,
    so the label would have to be laid out against the swapped geometry.*

  *The panel's own reported size is compared against the configured pair at
  startup and a disagreement is **warned about rather than refused**, the same
  call `panel_check` makes about the television's diagonal and for the same
  reason: a wrong size gives a label that looks wrong, a refusal gives no label at
  all, and the label may never be a reason the wall stops.)*

Because neither is shared, neither can drift between planes. A wrong TV size is
still a real defect — the mat comes out the wrong width and the review grid's
warnings are computed against a TV that isn't there — but it is a single-plane
misconfiguration, not a cross-plane mismatch. **Nothing may hardcode either panel's
size**; this deployment is a 50" Frame but the product must run on any.

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

> **Three kinds of file live under `ART_ROOT`, and the exclusion covers all
> three.** Upstream originals in the image tree; derived renditions and
> `thumbs/`, regenerated per device; and — since 2026-08-02 — `previews/`, the
> candidate previews phase 2 caches so review works when a museum does not.
> Previews are the most disposable of the three, and **disposable here means
> "losing one costs a picture, not a record" — not "it comes back"** (corrected
> 2026-08-03). Nothing re-fetches a preview: `PreviewCache.store` runs once, when
> phase 2 first records an instance, and a re-search does not restore the file
> because `record_image` returns the instance a work already holds for that URL
> without rewriting `preview_path`. So a restored catalogue with an empty
> `previews/` shows review cards that fall back to reporting their source URLs —
> permanently for every candidate still under review, until acquisition fetches
> the real image after acceptance. That is a degraded review surface rather than
> a loss, which is why the exclusion stands; it is not self-healing, which the
> earlier wording implied. The **judgements** made against those previews — which
> instance was selected, the rationale, which images were rejected — are catalogue
> rows and are backed up.

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
| Add disk headroom | **`tile-cache/` reclaims itself since 2026-08-03** and is no longer an operator chore: tiles are cached under the id of the source being fetched, and that directory is removed the moment the work holds a complete image. What survives a pass is exactly the tiles of a **partial** fetch, which is the one case they are worth their disk — they are what lets `art_catalogue(action='retry_acquisition')` finish the image without re-downloading what already arrived. So a `tile-cache/` that is large is a report that works are sitting partially fetched, and the remedy is to retry them rather than to delete the directory; deleting it is safe and costs those retries their head start. `temp/` belongs to the 2024 modules and is still pruned by hand until they are retired. **`api-cache/` needs no rule: the curation plane never creates one** — phase 2 asks museums over HTTP with no on-disk cache, and the directory exists only in the 2024 `config.py`. **`previews/` reclaims itself since 2026-08-03**: the plane sweeps it hourly (`PREVIEW_SWEEP_INTERVAL_SECONDS`, 0 to disable), deleting the cached thumbnails of candidate works the curator has accepted or rejected, and logging `preview.swept` every pass whether or not it took anything — a plane that has stopped sweeping is therefore visible in the journal rather than only in the free-space figure. **Two things it does not reclaim, and the second is why deleting the directory by hand is still a listed remedy.** The previews of works nobody has judged yet — those are the ones review still needs, so a backlog of undecided candidates is a state in which this directory legitimately grows, and deciding them is the remedy. And **files no row names**: the sweep derives every path it considers from `CandidateImage.preview_path`, so bytes written by a phase-2 run that died between writing the file and recording the row are invisible to it permanently. That is not hypothetical — it is the case an on-verdict hook could never have covered, which is part of why the sweep exists — and it is unbuilt, filed rather than glossed. Until it is built, **`rm -rf` on `previews/` is the only thing that reclaims an orphan**, and it costs more than the word "disposable" suggests: **nothing re-fetches a preview.** `PreviewCache.store` is called once, by phase 2 when an instance is first recorded, and a re-search does not restore the file either — `record_image` returns the instance a work already holds for that URL without rewriting `preview_path`. So deleting the directory permanently costs the inline picture of every candidate **still under review**, whose cards fall back to reporting a source URL a curator would have to open by hand; works already decided lose nothing, since their previews were the sweep's to take anyway. Safe on a full card, and not free — prefer deciding the outstanding candidates first, which lets the sweep reclaim them properly. It matters here because § Risks opens with the SD card as the top operational risk |
| **Verify the spend ceiling** | In the OpenRouter console, confirm the key in `OPENROUTER_API_KEY` still carries a **USD 20 credit limit with a monthly reset**. **This setting is the entire cap** — nothing in this repository enforces one, by ratified decision, because an application-side meter that fails open is indistinguishable from one that works. A key whose limit was cleared, or a key swapped for an uncapped one, looks identical on every surface the product exposes right up to the bill. `cd curation && uv run pytest -m live_api` asserts it mechanically (`test_the_key_reports_a_monthly_ceiling`) and costs a few cents to run |
| Bound the journal | Install `deploy/journald.conf.d/10-bound-the-journal.conf` and restart `systemd-journald`. **`SystemMaxUse=` alone is not enough** — Raspberry Pi OS ships `Storage=volatile`, so the journal is in RAM and `RuntimeMaxUse=` is the directive that binds; the drop-in sets both. Verify with journald's own `Journal ... max` startup line, not `systemd-analyze cat-config`, which only proves the file parses — see § Risks |
| **Decide on a TV firmware update** | Auto-update is **off** (2026-08-04) and the set is held at 1310 with 1400 offered. Nothing arrives on its own, so this recurs whenever there is a reason to update. Default answer is stay: the update is one-way and every measured fact about this set is firmware-scoped. If one is ever taken, re-run `python tv_api_check.py --image <a 4K composite>` — it is what says which behaviours moved |
| **Diagnosis after a reboot** | There is none from the journal: `Storage=volatile` means it does not survive one. If the wall froze and the Pi restarted, `journalctl` holds nothing about the run that failed. **Do not reach for `Storage=persistent` here** — it was declined on 2026-08-04 and switching it reverses a recorded decision and puts logging on the card, which is the top operational risk. Diagnose from the health surface's heartbeat age or the catalogue instead; see § Risks |
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
| Acquisition fails on every work | Free disk space | The pre-acquisition guard should have caught it; if it did not, that is a bug in the guard. It refuses **before** a fetch begins and names the shortfall in GiB, so the refusal itself says whether disk is the cause. `MIN_FREE_BYTES` (default 2 GiB) is the floor, and it protects `catalogue.sqlite` on the same device rather than the fetch |
| Acquisition fails on one work with a refused URL | `art_catalogue(action='sources')` for that work | The fetch policy refused the URL and the reason is recorded on the source. Schemes other than `http`/`https`, and hosts that resolve to this network rather than the open internet, are refused by design (`security-model.md` § The fetch trigger fired) — a source that needs one of those is a source this product will not fetch |
| Every tiled acquisition fails at once | `dezoomify-rs` on the unit's `PATH` | Acquisition raises rather than recording a failed fetch when the binary is absent, precisely so this is not mistaken for museums going away. Install it, or set `DEZOOMIFY_PATH` to where it lives |
| Every **Art Institute** acquisition raises, while other providers fetch fine | `ARTIC_USER_AGENT` in `.env` | An artic source records the museum's page for the object, and the tile fetcher needs the image service — which only the collection can be asked for. Unset, there is no way to reach those tiles, so acquisition raises by name rather than handing the fetcher a URL it cannot read. Set it and the same works fetch unchanged. Raises rather than records for the same reason the row above does: no source is at fault, and a `failed` row here would send its reader to the museum |
| Neither plane starts after a reboot | Both planes' resolved `ART_ROOT` in the journal | Mismatched or missing `ART_ROOT` is the likely cause |

## Risks

**The SD card is the top operational risk, and it carries the irreplaceable
asset.** Write-heavy tile caching plus ~10 GB of artwork on consumer flash, with
`catalogue.sqlite` on the same device, in an always-on machine subject to
unexpected power loss. SQLite plus power loss on consumer flash is the classic Pi
corruption story.

**Decided 2026-08-04: the card stays.** `ART_ROOT` and the catalogue remain on the
128 GB SD card — no USB SSD, no SSD boot, no network storage. The reasoning is the
write *profile* rather than the medium's reputation. The image tree is additive and
written once: works are added, and rarely deleted or rebuilt, so the total bytes
written is bounded by the size of the collection rather than by churn. A collection
that eventually fills most of the card is on the order of a hundred gigabytes
written across years, which is a small fraction of any modern card's rated
endurance. What wears a card out is small writes that never stop, and this product
was thought to have exactly two — the journal and the display heartbeat.

> **Corrected 2026-08-04, on the machine: the journal is not one of them.**
> Raspberry Pi OS ships `Storage=volatile` in
> `/usr/lib/systemd/journald.conf.d/40-rpi-volatile-storage.conf`, so the journal
> lives in `/run/log/journal` — a tmpfs — and **logging writes to RAM, not to the
> card.** Every sentence that treats journal growth as flash wear was describing a
> persistent journal this deployment does not have. **The display heartbeat is
> therefore the only continuous-write path to the card**, and its writer is not
> built, so no part of this wear reasoning is exercised by anything running today.
>
> The journal still gets an explicit bound, for the different reason given below,
> and **that bound is in force as of 2026-08-04** — evidenced by journald's own
> startup line moving from `max 156.1M` to `max 256M` across the restart, which is
> the check that proves the bound took. An earlier version of this paragraph
> cited `systemd-analyze cat-config` instead; that proves only that the drop-in
> parses, and it would have reported success just as happily while the directive
> bound nothing — which is exactly what was happening, because the file set only
> `SystemMaxUse=` and volatile storage is governed by `RuntimeMaxUse=`.

The heartbeat's bound is 60 s in `observability-strategy.md` § The Health Surface;
the journal's is the requirement below.

*The alternatives, and why they lost.* **USB SSD for `ART_ROOT`, or SSD boot** —
issue #13's two original options. Both work, and the Pi 4's USB 3.0 ports make
either comfortably fast, but they buy endurance this write profile does not need,
and USB boot adds a second failure class in enclosure and UASP behaviour for a
speed benefit nothing here requires. **`ART_ROOT` on network storage**, raised and
rejected the same day: `catalogue_path` resolves to `art_root / catalogue.sqlite`,
so this puts SQLite on a network filesystem — where advisory locking is unreliable,
and WAL, the mode that would otherwise reduce the exposure, cannot be used at all
because it requires shared memory between processes on a single host. It would also
put the wall's uptime behind a second machine, since the display plane polls the
manifest and reads the image tree continuously, and it would rest the manifest and
heartbeat channels' atomic write-and-rename on semantics a network filesystem
decides rather than the kernel.

*The trade-off, stated plainly.* Card death costs a rebuild plus whatever curation
happened since the last backup, at an accepted frequency of once every few years.
**That makes the backup and restore path the entire mitigation for this risk rather
than a complement to it** — and it is not built. Until issue #14 lands, this risk is
*decided* rather than *closed*: nothing on the Pi today would survive the card. The
storage medium is no longer the open question; the backup is.

**The journal is bounded explicitly, for a narrower reason than this section once
gave.** Structured logging is the product's primary observability signal and both
planes log continuously to it. `deploy/journald.conf.d/10-bound-the-journal.conf`
sets **256M** with 32M segments, on **both** ceilings — `SystemMaxUse=` for a
persistent journal and `RuntimeMaxUse=` for the volatile one this machine actually
uses — so the file is correct whichever storage mode is in force.

> **Corrected twice on 2026-08-04, and the second correction reverses the first's
> premise.** This paragraph originally said the default "sizes itself as a fraction
> of the filesystem — so it grows with the disk you were trying to protect."
> Neither half survived contact with the machine: systemd caps its persistent
> default at 4G, and this journal is not on the filesystem at all. Two things
> follow.
>
> **The bound protects nothing about the card**, per the correction above. What it
> buys is a ceiling that is *chosen and visible* rather than inherited from
> defaulting rules a reviewer would have to know.
>
> **On this machine it is a raise, not a cap.** The runtime default was 156.1M of
> RAM; 256M is more. That is affordable on 8 GB and is the intent — but it is the
> opposite of what "bound the journal" suggests, so it is said plainly rather than
> left in the arithmetic. 256M was chosen against a measurement: 9.2 MB after first
> boot and a full provisioning run, so it is weeks of history at that rate.

**What volatile storage costs is diagnosis, and the operator decided 2026-08-04 to
accept that cost: the journal stays volatile.** It does not survive a reboot, so
"the wall froze and the Pi restarted" is precisely the case `journalctl` cannot
answer — and it is the case an operator is most likely to be investigating.
`Storage=persistent` would fix that and would move logging onto the card, making
the journal a wear path for the first time; it was declined. **Two consequences to
carry rather than rediscover.** Post-reboot diagnosis has to come from somewhere
other than the journal — the health surface's heartbeat age, or the catalogue —
which is a constraint on how failures are made visible, not merely a missing
convenience. And the top operational risk keeps its narrowest form: nothing this
product does writes continuously to the card except the display heartbeat, whose
writer is not built.

The pre-acquisition free-space guard is unrelated to any of this: it is
curation-side and checks before a fetch.

**Second risk: vendor removal of the TV art-mode API — the auto-update question is
answered.** Samsung has already removed art mode from some units via firmware
(1710, Sept 2025). The capability the entire product rests on is controlled by a
vendor who has withdrawn it before.

**Firmware auto-update can be disabled on this television, and was disabled
2026-08-04.** The set is held at firmware **1310**; **1400** is offered and has not
been taken. Two consequences worth stating:

- **The risk is now a decision rather than an exposure.** Nothing arrives
  overnight; taking 1400 is a deliberate act.
- **Updating is effectively one-way** — there is no rollback — so the standing
  recommendation is to stay on 1310 unless a release note shows 1400 fixes
  something wanted. Staying costs nothing known and keeps the set on behaviour that
  has been *measured*; every figure in
  `platform-and-dependency-findings.md` § The television was taken against 1310.
  The counter-argument, security patching, is weak for a LAN device behind NAT on a
  network `security-model.md` already treats as the trust boundary.
- **What makes this recoverable in knowledge, if not in firmware**, is
  `tv_api_check.py`: re-run it after any future update and it reports what moved.
  That is the defence against vendor change — not compatibility branching, which
  could not be tested here against a second set anyway.

**Third risk: the norms with no mechanical enforcement.** *(Re-scoped 2026-07-27.
This read "no test suite exists — zero tests across 2,216 lines"; that departure was
closed the same day and both planes now have suites, so the risk is no longer
absence of testing but the specific norms nothing yet checks.)* The **plane-isolation
test** that enforces a ratified Direction norm was built on 2026-08-06 with the
display plane's first modules (issue #7) — imports resolved transitively, HTTP-client
construction banned with the television websocket exempted, and planted violations
proving both halves can fail. What remains uncovered is the **service-layer norm**,
whose enforcement column says "Critic" — a reviewer reading handlers, with no test
that fails when logic creeps into a binding.
