# Learnings

Accumulated wisdom from building this product.

## Retiring a claim is a repo-wide grep, not a local edit

**When you void, amend, or supersede a factual claim, grep the whole repo for it
before calling the correction done.** Prose has no compiler, so a claim that lives in
four artifacts stays true in three of them until someone looks.

**Confirmed by recurrence — twice in two sessions, both caught by the Critic and
neither by self-review:**

1. **2026-07-19, first pass.** The architecture rationale was amended from "the split
   was *forced* by a Python version conflict" to "the split is a *choice*" across
   `product-brief.md`, `project-state.yaml`, and `3tears-integration-findings.md`.
   `learnings.md` kept a section literally headed *"The Python version split is not
   negotiable"* for a full session.
2. **2026-07-19, second pass.** `api-contract.md` § Security spent a paragraph
   explaining that *"agents cannot auto-accept (every addition stops at curator
   review)"* was void and must not be left standing. `project-state.yaml` →
   `risk_profile` was still asserting it, verbatim, in the same commit.

**Root cause:** thinking in artifacts. You correct the file you are editing and the
correction *feels* complete, because the edit you made is the edit you intended. The
claim's other homes are invisible precisely because you are not editing them.

**What to do:** after writing any correction, grep for a distinctive phrase from the
*old* claim — not the new one — across `.prawduct/` and the repo. Fix every hit or
say why it stays. Cheap, mechanical, and it catches the whole class.

**Related:** the same session produced a near-miss of the adjacent shape — an
*unverified inference riding along with a verified claim* ("streamable HTTP is
forced" was verified; "mounted in the same ASGI application" was not, and was written
as though it were). Verification instincts fire on the part that looks like a
foreign-system claim, not on what is attached to it. Principle 24 (Retrieval Over
Generation) and the Complete Delivery principle both bear on this.

## Platform and dependencies

See [platform-and-dependency-findings.md](artifacts/platform-and-dependency-findings.md)
for the full record established 2026-07-19. Summary:

- Target **Python 3.13** (matches Raspberry Pi OS Trixie), falling back to 3.12.
  Verified working on 3.12; 3.13 is an open assumption until a build proves it.
- Hardware is a **Pi 4 Model B**, so `RPi.GPIO` works and none of the Pi 5 /
  RP1 / `rpi-lgpio` complications apply.
- Both display drivers are **dormant** (omni-epd 2024-11, IT8951 2023-11), and
  the IT8951 dependency is **unpinned** — pin or vendor it.
- The hardware surface is only ~119 lines (`display.py`, `spi_test.py`), so it
  belongs behind an interface. That is what keeps a frozen 2023 driver from
  dictating the project's Python version.

**This constraint turned out to be architecture-defining.** See below.

## The two-plane split is a choice, not a forced constraint

> **Corrected 2026-07-19.** This section previously read *"The Python version split
> is not negotiable"* and described the split as **forced** by an irreconcilable
> version conflict. An audit the same day proved otherwise, and the correction was
> carried into `product-brief.md`, `project-state.yaml`, and
> `3tears-integration-findings.md` — but not here, which left the project's
> learnings file asserting the opposite of its own architecture decision. Caught by
> Critic review on 2026-07-19.
>
> **The durable lesson is the one that generalises:** "forced by X" is a claim about
> X, and it needs the same verification as any other foreign-system claim. Recording
> a constraint as non-negotiable without auditing it is how a removable limit becomes
> permanent architecture.

Established 2026-07-19 during discovery; full record in
[3tears-integration-findings.md](artifacts/3tears-integration-findings.md).

Every 3tears package declares `requires-python = ">=3.14"`, and the e-paper driver
stack is pinned to **3.13/3.12** for the reasons above. Taken at face value these
cannot share an interpreter. **But the audit found 3.14 is required only by 16
mechanical source sites, with no third-party dependency imposing any floor above
3.10** — so the constraint is removable, and "forced" is not an honest rationale.

The split stands on its own merits:

- **Curation plane** — Python 3.14. Web UI, LLM discovery, image acquisition and
  preparation. **Runs on the Pi** (amended 2026-07-20 — previously "runs off the Pi").
- **Display plane** — Python 3.13 on the Pi 4. TV websocket, e-paper, and label
  rendering.

**Both planes run on the same Pi 4 (8 GB), sharing `ART_ROOT` and communicating
through exactly one file — the theme manifest.** The clause "it moves gigapixel
fetching and 4K compositing off a Pi 4" is **retired and must not be cited**;
nothing moved off it. That claim was also weaker than it read — the existing code
downsizes to 2048² before the LAB/k-means work, so peak memory is a few hundred MB.

It survives because the display plane **does not want 3tears at all** — it needs an
HTTP client, `samsungtvws`, PIL, and the e-paper driver, and three-tier entities are
of no use to it. Beyond that: it matches the upstream/derived data contract below,
it makes "e-paper behind an interface" a process boundary rather than a convention,
and it is what lets the display plane keep working when curation is down.

Co-location did not weaken the split, it made it cheaper: the *cost* was the
distributed-systems tax (network contract, sync, two deployments) and a shared
filesystem removes it, while the *benefit* — the wall staying lit through a curation
restart — matters more on one box, not less.

Relaxing 3tears to 3.13 remains worth doing on *its* merits, but it is no longer a
dependency of this product's architecture.

## 3tears can run with zero infrastructure

Also 2026-07-19, verified by reading the source — not assumed:

- **L2 (NATS) is optional by design.** `CollectionRegistry` initialises all tiers
  to `None`; `BaseCollection` guards every L2 use and has one-shot warning
  machinery for the missing-client case. Spam suppression for a path implies the
  path is expected.
- **L3 is pluggable.** The `DurableStore` protocol is explicitly documented as
  "the seam that makes a non-SQL durable backend possible", and scriob's
  `GitL3Backend` is a working precedent.
- **`3tears-models` needs no core at all** — only `media-contracts` and `observe`.
- **`3tears-agent-memory` is the exception**: it depends on `pgvector`, so it
  genuinely requires Postgres. Deferring it is what keeps the curation plane
  infrastructure-free.

> The whole decision reduces to one question: do you want 3tears agent memory?
> No → zero infrastructure. Yes → Postgres. Nothing in between buys anything,
> because NATS only earns its keep across multiple pods.

## Data and cache contract

Established 2026-07-19. The `art/` tree is not one thing, and the two halves are
transported differently:

- **Upstream, expensive, device-independent** — `raw/`, `api-cache/`,
  `tile-cache/`. Costs network fetches and real API spend to regenerate.
- **Derived, cheap, device-specific** — `ready/`, `tv-thumbs/`, `label/`.
  Rendered for a particular target geometry (4K for the TV, 1448x1072 for the
  e-paper).

The rule that falls out:

> Git carries the code and the `all.json` index. Rsync carries the upstream
> blobs. Derived artifacts are never transported at all — they regenerate
> per-device.

Derived artifacts must **not** be copied between machines even though it is
technically possible: they are rendered for whichever display was targeted, so
shipping them produces either wrong output or a cache that cannot be trusted.
Regenerating them on the target is cheap and correct.

`all.json` is already the right shape for this — a 68 KB index tracked in git
while the blobs stay out of it. The design is sound; it needs making explicit,
starting with hoisting the art root into configuration as a single `ART_ROOT`
(it was hardcoded to `/home/tvpi/art`, correctly outside the repo, but only
implicitly).

## Known problems in the existing index

`all.json` conflates three separate concerns in one record, which the planned
pivot to canonical artwork identities plus a URL-resolution layer needs to
separate:

1. **Identity is the source URL.** If a museum site reorganises, identity
   breaks, and the same artwork cannot be sourced from two places.
2. **Per-device runtime state lives in the catalogue** — `tv_content_id` and
   `tv_content_thumb_md5` are facts about one specific television, and
   `label_file` embeds `_w648_h480`, geometry from a display that is no longer
   the target.
3. **Metadata is semi-structured** — `artist_details` is a newline-joined blob
   ("Charles Demuth\nAmerican, 1883-1935") needing parsing into artist,
   nationality, and lifespan.

Also unreconciled: **41 artworks in `all.json` but 46 files in `raw/`**, and
filenames encode identity in at least three mutually inconsistent conventions
(`Surname, Forename; Title; Year`, `Forename Surname - Title`, and at least one
`Title - Forename Surname` with the fields reversed).
