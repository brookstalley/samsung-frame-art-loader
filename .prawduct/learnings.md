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

4. **2026-07-20, fourth recurrence — and this one was NOT a paraphrase problem.**
   The re-search decision superseded "re-search spend attributes to the originating
   run". The literal phrase survived in `data-model.md` § SpendRecord, ~180 lines
   below the note stating the new rule, in the same file — and I had rewritten its
   twin sentence by hand in `api-contract.md` minutes earlier.

**The correction: editing a file is not sweeping it.** The sweep grep I ran was

    grep -rn "<concepts>" .prawduct/artifacts/*.md | grep -v "data-model.md\|api-contract.md"

I excluded the two files I was *editing*, reasoning that editing them handled them.
That reasoning is wrong and it inverts the risk: the artifacts you edit are the ones
most likely to contain the superseded claim, because they are the ones the decision
is about. A 750-line artifact does not become consistent because you changed one
section of it.

**So the closing check has three passes, not two:** (1) grep the literal phrasing —
cheap, catches survivors; (2) walk `depends_on` and re-read dependents for the
*concept* — catches paraphrase; (3) **re-read the files you edited, in full, as if
someone else wrote them** — catches the survivor sitting below your own edit. Pass 3
is the one that was missing, and it is the cheapest of the three.

5. **2026-07-20, fifth recurrence — in the commit that authored the remedy.**
   `project-preferences.md` still described a single product-wide Python target 140
   lines below its own corrected per-plane section, in a file that same commit
   edited. Pass 3 would have caught it on first application. Writing a remedy and
   applying it are different acts, and the commit that adds the remedy is exactly
   where the gap shows.

6. **2026-07-20, sixth and seventh recurrences — the correction itself was the
   miss.** A Critic finding named three artifacts carrying the same rule
   (`data-model.md`, `architecture.md`, `operational-spec.md`). I edited one. My
   pass-3 grep used the literal strings from the file I had just written;
   `architecture.md` phrased the rule differently ("reconciles every non-terminal
   run to `failed`") and did not match. `operational-spec.md` was worse than stale —
   it had inverted, telling the operator that a healthy waiting run was a bug.

**The correction: when a Critic finding lists files, that list IS the sweep set.**
No dependency walk is needed and no grep pattern has to be guessed — the reviewer
already did the work and handed over the answer. Using one file from a three-file
finding is not a sweep failure of technique, it is not reading the finding.

**And the generalisation behind passes 1–3: never let the grep pattern come from the
text you just wrote.** Your own phrasing is the one phrasing guaranteed to be
consistent; the survivors are, by definition, the sites that say it differently. Grep
for the *concept's* distinctive nouns (`awaiting_approval`, `reconcil`, `non-terminal`)
rather than for a sentence.

**A second structural gap, found by the Critic on `rev-20260720T145500Z-2fcf2f8f`**
(the review that produced recurrence 4 — named rather than left as "the same review",
after an inserted entry silently re-anchored that phrase to the wrong one)**:** the two entries
under `artifact_manifest.findings` had *no `depends_on` edges at all*, so pass 2
could not reach them even when run correctly — which is why the retired product-wide
Python target survived in `platform-and-dependency-findings.md` across four
corrections elsewhere. Edges added 2026-07-20. **A dependency-graph sweep is only as
good as the graph**, and an unedged node is invisible rather than merely
low-priority. Worth checking the graph is complete before trusting a walk of it —
including for issue #8, whose check would have inherited the same blind spot.

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

- Python version is **per plane, not one number** (corrected 2026-07-20 — the
  product-wide "target 3.13" predates the two-plane split and kept resurfacing).
  **Display plane: 3.13** (matches Raspberry Pi OS Trixie), falling back to 3.12;
  verified working on 3.12, and 3.13 is an open assumption until a build proves it.
  **Curation plane: 3.14** on a uv-managed standalone build, with `3tears`
  unmodified.
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
