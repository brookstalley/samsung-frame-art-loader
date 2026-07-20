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

3. **2026-07-20 — and this one escalates the rule, because the rule's own remedy was
   followed and still failed.** The co-location decision retired "the split moves
   gigapixel work off a Pi 4". I *did* grep the old phrasing and fixed six sites.
   The Critic then found four more, plus the 2026-07-19 "forced" claim still alive in
   two places it had already been amended out of once.

**Why grep was not enough — the correction to this learning.** A retired claim does
not propagate as *text*, it propagates as *paraphrase*. "Forced by a version
conflict" had become "Forced by the Python 3.14 vs 3.13 constraint, not chosen" in
`risk_profile` and "two planes on two machines, forced by an irreconcilable Python
version constraint" in the classification block. Neither matches a grep for the
original sentence. Grep finds literal survivors and is blind to exactly the
restatements that a careful writer produces.

**The unit of sweep is the DECISION, not the sentence.** When a decision changes,
the sweep target is every artifact that depends on that decision — which
`project-state.yaml` → `artifact_manifest.artifacts[].depends_on` now actually
encodes (populated 2026-07-20). Walk the dependency graph and re-read each dependent
artifact for the *concept*; use grep only as the cheap first pass, never as the
check that closes the sweep.

**Structural escalation, per the learning lifecycle.** Three recurrences across two
sessions, every one caught by the Critic and none by self-review, means writing it
down is not working. What would actually catch it: a check that, when a
`technical_decisions` entry gains an `AMENDED`/`SUPERSEDED`/`RETIRED` marker, lists
the artifacts declaring a `depends_on` edge to it and requires each to be
acknowledged. Filed rather than improvised here.

**Sharpest tell that this is systemic, not carelessness:** on 2026-07-20 the sweep
failure landed in the same bundle that *added this learning*, three commits later —
and one of the claims I had to retire was one I had written myself an hour earlier.

**Related:** the same session produced a near-miss of the adjacent shape — an
*unverified inference riding along with a verified claim* ("streamable HTTP is
forced" was verified; "mounted in the same ASGI application" was not, and was written
as though it were). Verification instincts fire on the part that looks like a
foreign-system claim, not on what is attached to it. Principle 24 (Retrieval Over
Generation) and the Complete Delivery principle both bear on this.

## Ratifying a norm creates retroactive obligations on ARTIFACTS, not just code

**When a norm is ratified, the artifacts written before it are as much in scope as
the code — and in a planning-stage product they are the *only* thing in scope.**
Re-derive every specification the norm now governs, before calling ratification done.

**What happened, 2026-07-20.** Three norms were ratified. For each, the Retroactivity
line read some version of *"no existing code has two planes — nothing to migrate"*,
which was true and useless. All four blocking Critic findings that followed were
norm-versus-predating-*artifact* conflicts:

- `data-model.md` still told the display plane to resolve `Theme → ThemeMembership →
  Artwork → TvBinding` — catalogue entities — hours after a norm was ratified saying
  the display plane "queries no curation database".
- `Rendition(kind='label')` still carried one panel's geometry in the catalogue,
  which that artifact's *own* Direction norm forbids and whose cited anti-pattern is
  the 2024 `_w648_h480` filename. Moving geometry from a filename into columns had
  fixed the *encoding* and left the *ownership* violation intact — which is how it
  survived a norm written to catch it.
- `api_contract.md` exposed `art_display(show_now|next)`, unimplementable the moment
  the manifest became the only channel.

**Root cause:** "retroactivity" was read as a code-migration question, because that
is what the word connotes and what the examples describe. In a product with zero
production code the field reads as trivially satisfied — so the one question it
exists to force never gets asked.

**What to do:** at ratification, list the artifacts the norm governs and re-read each
one *against* the norm. Specifications violate norms exactly the way code does, and a
spec violation is worse: it is the instruction a builder will faithfully follow.

**Related principle:** Complete Delivery — a decision whose consequences are not
propagated is not delivered. Also `docs/norms.md` § Birth, whose three retroactivity
outcomes (migrate / contain / grandfather) all read as code-shaped and may deserve an
artifact-shaped fourth reading.

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
