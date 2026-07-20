# Learnings

Accumulated wisdom from building this product.

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

- **Curation plane** — Web UI, LLM discovery, image acquisition and preparation.
  Runs off the Pi.
- **Display plane** — Python 3.13 on the Pi 4. TV websocket and e-paper only.

It survives because the display plane **does not want 3tears at all** — it needs an
HTTP client, `samsungtvws`, PIL, and the e-paper driver, and three-tier entities are
of no use to it. Beyond that: it matches the upstream/derived data contract below,
it moves gigapixel fetching and 4K compositing off a Pi 4, it makes "e-paper behind
an interface" a process boundary rather than a convention, and it is what lets the
display plane keep working when curation is down.

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
