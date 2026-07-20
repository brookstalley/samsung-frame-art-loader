---
artifact: data-model
version: 1
depends_on:
  - artifact: product-brief
last_validated: null
---

# Data Model

## Direction

**Identity is never a source URL.** Every artwork carries a stable internal
identity independent of where it was found. Source URLs are attributes of a
*resolution attempt*, not of the work.

> **Why:** The 2024 catalogue keyed identity on the source URL. Two consequences
> followed: if a museum reorganises its site the artwork's identity breaks, and
> the same painting sourced from two institutions becomes two unrelated records.
> Both are silent corruptions — nothing errors, the collection just quietly
> degrades.
>
> **Status:** steady-state.
>
> **Retroactivity:** Not applied to `all.json`, which is being replaced rather
> than migrated. The 41 legacy records are re-ingested through curation as new
> works.

**A work is distinct from an image of it, at every stage.** Every entity that
represents "a piece of art" is a *work*; every entity that represents a file, URL,
scan, or photograph is an *instance* of some work. The two are never collapsed into
one row, before or after acceptance.

> **Why:** *The Persistence of Memory* is one work with many instances — the MoMA
> page, a Google Arts & Culture gigapixel scan, a Wikipedia upload, a poster shop's
> JPEG. A model that treats each found image as a candidate presents the curator
> with ten copies of one painting and asks them to approve one. Nothing errors; the
> product simply fails at the thing it exists to do. The distinction has to hold
> pre-acceptance too, because that is exactly where the duplication appears.
>
> **Corollary:** collapse aggressively, but never discard. Instances that lose
> canonical selection are *retained* as non-primary rows, so an over-eager merge is
> inspectable and reversible rather than silent. That is what makes biasing toward
> collapse safe: the failure mode of over-merging (a work quietly represented by
> the wrong scan) is recoverable, while the failure mode of under-merging (ten
> cards for one painting) is the one the curator experiences.
>
> **Status:** steady-state.
>
> **Retroactivity:** Not applied to `all.json`, which is being replaced.

**Per-device runtime state never lives in the catalogue.** Facts about a
particular television, panel, or rendering geometry live in device-scoped
entities owned by the plane that talks to that device.

> **Why:** The 2024 record embedded `tv_content_id` and `tv_content_thumb_md5`
> (facts about one specific TV) and a `label_file` whose name encoded
> `_w648_h480` (the geometry of a panel that is no longer the target). Mixing
> them in means the catalogue cannot be moved, shared, or rebuilt without
> carrying one television's state along with it — and it is why the recovered
> catalogue's label references point at the wrong panel.
>
> **Status:** steady-state.

**Derived artifacts are regenerated, never transported.** Anything rendered for a
specific output geometry is reproducible from upstream inputs and is never
synced between machines.

> **Candidate previews are a third class, and they are disposable.**
> `CandidateImage.preview_path` files are neither upstream (they are cheap and
> re-fetchable) nor derived (nothing renders them from a held original — there is no
> original yet). They exist only to make review work without depending on a museum
> server being reachable. **They are safe to delete once their `CandidateWork`
> reaches a terminal verdict**, and deleting them must never affect the catalogue:
> the accepted work's imagery comes from acquisition, not from the preview. Flagged
> 2026-07-19 by Critic review, which noted the rows are deliberately permanent while
> the files had no recorded lifecycle at all.

> **Why:** Recorded in `learnings.md` § Data and cache contract. Derived files
> are rendered for whichever display was targeted; copying them between machines
> produces either wrong output or a cache that cannot be trusted. Regenerating on
> the target is cheap and correct.
>
> **Status:** steady-state.

## What this data must answer

Per `methodology/planning.md`, a persisted format is a lock-in decision and its
consumers' queries are its requirements. These are the questions the model exists
to serve, elicited from the Product Brief's core flows:

| # | Question | Flow |
|---|----------|------|
| Q1 | Which artworks belong to theme X, so the display plane can sync them? | 5, 6 |
| Q2 | Which artwork is the TV showing right now, so the label panel can match it? | 6 |
| Q3 | Has this **work** already been suggested and rejected, so discovery does not re-surface it? | 2, 3 |
| Q4 | What has been spent this month, and what did this run cost? | 1, 2 |
| Q5 | Where did this candidate come from, and why was it suggested? | 2, 3 |
| Q6 | Can this artwork be re-acquired from scratch if every derived file is lost? | 4 |
| Q7 | What mat colour was chosen for this work, and on what basis? | 4 |
| Q8 | Which renditions exist for which output geometry, and are they current? | 4, 6 |
| Q9 | Who is the artist — name, nationality, dates — for the physical label? | 4 |
| Q10 | Which image instances were found for this work, which one was selected, and on what basis? | 2, 3 |
| Q11 | Has this **image** been rejected for a work the curator still wants, so the re-search does not return it? | 3 |
| Q12 | Which proposed works could not be resolved to any credible image, and are therefore suspect? | 2 |

**Q3 is the one most easily missed.** Without persisted rejections, every
discovery run re-proposes the same works the curator has already declined, and
the product feels broken in a way no single component is responsible for.

**Q11 is Q3's trap.** The two look like the same question and must not share a
mechanism. Rejecting a *work* suppresses the work; rejecting an *image* must
suppress only that image and explicitly leave the work eligible — otherwise asking
for a better scan of a painting silently blacklists the painting. One suppression
key for both is the bug, and it is invisible until a curator wonders why a work
they asked to keep never came back.

**Q12 exists because phase 2 verifies phase 1.** A model asked for an artist's
famous works will occasionally invent a plausible title. A work for which no
credible instance can be found is evidence of exactly that, so the run must be able
to say "these N could not be resolved" rather than quietly returning a shorter
list — or, worse, attaching a confident near-match.

## Entities

### Artwork

The canonical record of a work. Plane-independent, device-independent, and the
only entity the curator thinks of as "a piece of art".

| Field | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | Stable internal identity. Never derived from a URL. |
| `title` | string | required | Work title. |
| `artist_id` | UUID | FK → Artist, nullable | Null for anonymous or unattributed works. |
| `date_created` | string | nullable | Free text — sources give "1931", "c. 1650", "1888–89". Not a date type; normalising would destroy information. |
| `medium` | string | nullable | e.g. "Oil and graphite on fiber board". |
| `dimensions` | string | nullable | Physical dimensions as the source states them. |
| `description` | text | nullable | May contain limited markup; see Constraints. |
| `rights` | string | nullable | Rights statement as given. Display-only — see open question in `project-state.yaml`. |
| `status` | enum | required | `accepted` \| `archived`. See State Machines. |
| `accepted_at` | datetime | nullable | Set on creation from an accepted CandidateWork. |
| `created_at` | datetime | auto | |

> **An Artwork only exists once accepted.** This entity previously carried
> `candidate` and `rejected` statuses, which duplicated what `CandidateWork.verdict`
> now owns. Two entities modelling the same lifecycle is how they drift — a work
> `rejected` on one and `accepted` on the other is unresolvable, and nothing would
> flag it. Pre-acceptance state lives on `CandidateWork`; the catalogue holds only
> works that made it.

### Artist

Separated from Artwork so the label can render nationality and lifespan without
re-parsing a blob, and so two works by the same artist agree.

| Field | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `name` | string | required | Display name, e.g. "Charles Demuth". |
| `nationality` | string | nullable | e.g. "American". |
| `born` | integer | nullable | Year only. |
| `died` | integer | nullable | Year only. |
| `lifespan_text` | string | nullable | Fallback free text when `born`/`died` cannot be parsed, e.g. "active 1620s". |
| `biography` | text | nullable | |

> Directly replaces the 2024 `artist_details` blob
> (`"Charles Demuth\nAmerican, 1883–1935"`), which `metadata.py` re-parsed with
> regex on every read. The parsing logic is preserved — it moves to ingest time
> and runs once. **Q9.**

### Source

A place an artwork can be obtained from. Many-to-one with Artwork: the same work
may exist at several institutions, and a broken source does not break the work.

| Field | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `artwork_id` | UUID | FK → Artwork, required | |
| `url` | string | required | The source URL. An attribute here, never an identity. |
| `provider` | string | required | e.g. `artic`, `google_arts`, `gallery_site`, `prize_site`, `artist_portfolio`, `http`. Open vocabulary — the contemporary web has no fixed provider list. |
| `source_class` | enum | required | `institutional` \| `contemporary_web`. The load-bearing distinction; see below. |
| `acquisition_method` | enum | required | `dezoomify` \| `direct_http` \| `api`. Determines the fetch path. |
| `rights_status` | enum | required | `public_domain` \| `in_copyright` \| `unknown`. |
| `is_primary` | boolean | default false | Which source was actually used for the held original. |
| `confidence` | float | nullable | Carried from `CandidateImage.confidence` at acceptance. |
| `selection_rationale` | text | nullable | Why this source was chosen as primary. Carried from `CandidateImage`. **Q10.** |
| `last_fetch_status` | enum | nullable | `ok` \| `partial_tiles` \| `failed`. `partial_tiles` is a normal dezoomify outcome, not an error. |
| `last_fetched_at` | datetime | nullable | |

> **Q6.** Multiple sources per work is what makes re-acquisition robust when an
> institution reorganises its site.
>
> **`source_class` is the field that carries the 2026-07-19 scope expansion.** The
> two classes have almost nothing in common operationally:
>
> | | `institutional` | `contemporary_web` |
> |---|---|---|
> | Resolution | gigapixel via IIIF tiles | web JPEG, often ≤2000px |
> | Metadata | structured API | scraped, partial, or absent |
> | Rights | usually public domain | usually in copyright |
> | Fetch path | `dezoomify` | `direct_http` |
> | Rate limits | published, throttled | unknown, per-site |
>
> Modelling this as one undifferentiated `provider` string would push the
> difference into conditionals scattered across the acquisition code. Making it a
> column means the pipeline can branch once, and the review grid can show the
> curator which kind of thing they are looking at.

### Original

The acquired master image. Upstream, expensive, device-independent — the half of
the art tree that rsync carries and git does not.

| Field | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `artwork_id` | UUID | FK → Artwork, required, unique | One held original per work. |
| `source_id` | UUID | FK → Source, required | Which source produced it. |
| `relative_path` | string | required | Path **relative to `ART_ROOT`**, never absolute. |
| `width` | integer | required | |
| `height` | integer | required | |
| `byte_size` | integer | required | Zero-byte files are a known failure mode; see Constraints. |
| `content_hash` | string | required | Identifies the bytes; lets a rendition detect a stale parent. |
| `display_fit` | enum | required | `native` \| `matted_small` \| `upscaled` \| `below_floor`. How this original can honestly be shown on a 3840x2160 canvas. |

> **`display_fit` exists because the mat engine has a resolution premise.** Its
> whole design is that the artwork sits *inside* a mat at native resolution — the
> mat is the deliberate frame, not padding around a stretched image. A 1200px
> press image on a 4K canvas is either a small island in a very large mat, or an
> upscale that undermines the quality bar the engine exists to protect.
>
> Deriving this once at acquisition, rather than re-deciding it at every render,
> is what lets the review grid warn the curator *before* they accept a work.
>
> **The threshold values and the policy for `below_floor` are an open question**
> (`project-state.yaml` → open_questions): reject outright, accept and upscale,
> accept and mat generously, or surface it and let the curator choose per work.
> The column is specified now because retrofitting it means re-examining every
> acquired original.

### Rendition

A derived, device-specific output. **Regenerated, never transported.**

| Field | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `artwork_id` | UUID | FK → Artwork, required | |
| `kind` | enum | required | `tv_display` \| `thumbnail`. **`label` was removed 2026-07-20** — see below. |
| `target_width` | integer | required | e.g. 3840 for the TV canvas. |
| `target_height` | integer | required | e.g. 2160. |
| `relative_path` | string | required | Relative to `ART_ROOT`. |
| `source_content_hash` | string | required | The `Original.content_hash` this was rendered from. Mismatch ⇒ stale ⇒ regenerate. |
| `generated_at` | datetime | auto | |

> **Q8.** Geometry is *columns*, not a filename suffix. The 2024 design encoded
> it as `_w648_h480` in the filename, which is why the recovered catalogue points
> at a panel that no longer exists. Carrying `source_content_hash` is what lets
> staleness be detected rather than assumed — the 2024 code cleared TV state
> whenever it regenerated an image, which is the same intent expressed
> imperatively and only at one site.

> **`kind = 'label'` removed 2026-07-20 (Critic R-2).** A label Rendition carried
> `target_width` 1448 / `target_height` 1072 — the geometry of one specific e-paper
> panel — in the **curation catalogue**. That is the precise thing this artifact's
> third Direction norm forbids, and `_w648_h480` is the anti-pattern that norm
> cites. Moving geometry from a filename suffix into columns fixed the *encoding*
> and left the *ownership* violation intact, which is why it survived a norm
> written to catch it.
>
> Labels are rendered **on the display plane** from the label fields carried in the
> theme manifest (decided 2026-07-20). The panel's geometry lives with the plane
> that owns the panel, and the catalogue no longer knows a panel exists.
>
> What remains here is correct: `tv_display` at 3840×2160 is a property of the
> *artwork's presentation*, not of a device — any 4K display shows it, and the mat
> is composed against that canvas. `thumbnail` is device-independent by definition.

### MatColor

Separate from Artwork because it is a *judgement* with provenance, and because
regenerating it costs money.

| Field | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `artwork_id` | UUID | FK → Artwork, required | |
| `hex_rgb` | string | required | e.g. `#27285b`. |
| `lab_l`, `lab_a`, `lab_b` | float | nullable | Preserved when the model returns them. |
| `reason` | text | nullable | The model's stated rationale. |
| `method` | enum | required | `vision_model` \| `dominant_color_fallback` \| `manual`. |
| `model_id` | string | nullable | e.g. the OpenRouter model slug. Which model chose it. |
| `is_current` | boolean | required | Superseded choices are retained, not overwritten. |

> **Q7.** History is kept deliberately: mat quality is the product's subjective
> quality bar, the 41 hand-tuned legacy colours are the regression corpus, and
> "the new model picked a worse colour" must be answerable and reversible.
> `method` matters because `image_utils.get_mat_color` silently falls back to a
> darkened dominant colour when the model fails — today that fallback is
> invisible in the data.

### Theme

The curator's unit of intention. What "per-user preferences" resolved to — a
naming and grouping concept, not an accounts concept.

| Field | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `name` | string | required, unique | e.g. "American Modernists". |
| `description` | text | nullable | |
| `is_active` | boolean | required | Exactly one theme is active; see Constraints. |
| `created_at` | datetime | auto | |

### ThemeMembership

Join entity. Explicit rather than implicit so ordering can be curated.

| Field | Type | Constraints | Description |
|---|---|---|---|
| `theme_id` | UUID | FK → Theme, PK part | |
| `artwork_id` | UUID | FK → Artwork, PK part | |
| `position` | integer | nullable | Curator-defined order; null ⇒ unordered/shuffle. |
| `added_at` | datetime | auto | |

> **Q1.**

### DiscoveryRun

One invocation of the discovery flow. Exists to make cost visible and to give
candidates provenance.

| Field | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `intent_text` | text | required | The curator's natural-language intent, verbatim. |
| `strategy` | text | nullable | The interpreted plan, for explaining results. |
| `initiated_by` | enum | required | `web_ui` \| `web_ui_agent` \| `mcp_client`. Which surface started this run. |
| `status` | enum | required | `resolving_works` \| `awaiting_approval` \| `resolving_images` \| `completed` \| `failed` \| `declined` \| `cancelled` \| `halted_by_budget`. See State Machines. |
| `estimated_cost_usd` | decimal | nullable | Phase-2 estimate, computed from the phase-1 work count. |
| `actual_cost_usd` | decimal | nullable | Reconciled after. |
| `approval_required` | boolean | required | Whether the resolved **work count** crossed the configured threshold (amended 2026-07-20 from "the phase-2 estimate"). Recorded per run, not re-derived — the threshold can change. |
| `unresolved_work_count` | integer | nullable | Works from phase 1 for which no credible instance was found. **Q12.** |
| `started_at`, `completed_at` | datetime | nullable | |

> `halted_by_budget` is a first-class terminal state, not an error. The cap fails
> closed and the curator must be able to see that is what happened.
>
> **A run produces one batch, reviewed as a grid** (decided 2026-07-19). The run
> completes, then the curator reviews its candidates together and accepts or
> rejects in bulk. This is why `estimated_cost_usd` is meaningful: a batch run has
> a knowable scope to estimate, which an open-ended iterative conversation would
> not. It also matches the "short curation sessions" constraint — the curator is
> not held at the keyboard while discovery works.
>
> **`target_candidate_count` is resolved, and it is not a column.** This artifact
> previously deferred it, listing three options: the curator sets it per run, it is
> a global preference, or the agent decides from how much matches the intent. The
> two-phase split produces a fourth that beats all three — **the phase-1 work list
> *is* the count**, and it is a reviewable, trimmable list rather than a number
> guessed in advance. Nothing needs to be stored: the count is
> `COUNT(CandidateWork)` for the run.
>
> **`approval_required` is stored rather than derived** because the threshold is
> configuration and configuration changes. A run that stopped for approval last
> month must still read as "this stopped for approval", not as whatever the current
> threshold would imply.
>
> **`initiated_by` exists because agents can now start runs.** An MCP client can
> issue "add all of Salvador Dalí's most famous works" without the curator
> watching, so "why did forty Dalí candidates appear, and who asked for them"
> must be answerable from the data. It is also the field that makes agent spend
> attributable in `SpendRecord` — cost per surface, not just cost per month.
>
> Note what `initiated_by` is **not**: an authorisation input. Every surface has
> identical authority, because `has_multiple_party_types` is false and there is
> one principal. Agent-initiated runs queue candidates for exactly the same
> reason UI-initiated runs do — the review gate is universal, not a restriction
> applied to agents. Branching behaviour on this field would reintroduce the
> parity split the MCP requirement exists to prevent.

### CandidateWork

A *work* discovery proposed, and the curator's verdict on it. Produced by phase 1,
before any image exists. Distinct from Artwork: most candidate works never become
artworks.

| Field | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `discovery_run_id` | UUID | FK → DiscoveryRun, required | |
| `artwork_id` | UUID | FK → Artwork, nullable | Set on acceptance. |
| `proposed_title` | string | required | As phase 1 named it; may be wrong or invented. |
| `proposed_artist` | string | nullable | |
| `rationale` | text | required | Why the model matched this work to the intent. **Q5.** |
| `work_dedup_key` | string | required, indexed | Normalised work identity for cross-run suppression. **Q3.** |
| `resolution_status` | enum | required | `pending` \| `resolved` \| `unresolved`. `unresolved` ⇒ phase 2 found no credible instance. **Q12.** |
| `verdict` | enum | required | `pending` \| `accepted` \| `rejected` \| `awaiting_better_image`. See State Machines. |
| `rejected_reason` | text | nullable | Optional curator note. |
| `decided_at` | datetime | nullable | |

> **`awaiting_better_image` is the verdict an accept/reject binary cannot express**
> — "I want this work; this instance is not good enough; find another." It is not
> an edge case, and it is not terminal: the work returns to review once a new
> instance is selected. Modelling it as a rejection would suppress the work via
> `work_dedup_key` and silently lose a painting the curator explicitly asked to
> keep (**Q11**).
>
> **`resolution_status = unresolved` is a first-class outcome, not an absent row.**
> Phase 2 failing to find any credible instance is the signal that phase 1 may have
> invented the work. Dropping it from the batch discards that signal; attaching a
> low-confidence near-match actively launders it.
>
> **Q3.** `work_dedup_key` is what stops discovery re-proposing declined works
> forever. Its derivation (normalised artist + title, or a source identifier where
> one exists) is a design decision deferred to build — but the *column* is specified
> now, because retrofitting suppression after rejections have accumulated makes the
> early rejections unrecoverable.

### CandidateImage

One image *instance* found for a candidate work. Many per work; exactly one
selected. Produced by phase 2.

| Field | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `candidate_work_id` | UUID | FK → CandidateWork, required | |
| `url` | string | required | Where this instance was found. |
| `preview_url` | string | nullable | Small image for review. Source-side URL. |
| `preview_path` | string | nullable | Cached local copy, relative to `ART_ROOT`. Review must not depend on a museum server being reachable. |
| `provider` | string | required | e.g. `artic`, `google_arts`, `gallery_site`. Open vocabulary. |
| `source_class` | enum | required | `institutional` \| `contemporary_web`. |
| `estimated_width`, `estimated_height` | integer | nullable | Best pre-acquisition guess at available resolution. |
| `rights_status` | enum | nullable | `public_domain` \| `in_copyright` \| `unknown`. |
| `confidence` | float | required | Is this genuinely that work — not a detail crop, study, poster, or "after"? |
| `quality_score` | float | nullable | Resolution, fidelity, rights, institutional provenance. |
| `selection_rationale` | text | nullable | Why this instance was chosen over the others. **Q10.** |
| `is_selected` | boolean | required | Exactly one per work at a time. |
| `rejected_at` | datetime | nullable | Set when the curator rejects this instance; suppresses it from re-selection. **Q11.** |

> **`confidence` and `quality_score` are separate because they conflict.** A
> museum's own page is maximum confidence and may be lower resolution than a
> gigapixel scan elsewhere. Collapsing them into one number makes the trade
> invisible and the choice unexplainable — and `selection_rationale` is what the
> review card shows when the curator asks *why this one*.
>
> Which axis dominates depends on `source_class`. For `institutional` sources many
> instances of one work exist and canonicity is the hard problem. For
> `contemporary_web` there is usually exactly one image and the risk is that it is
> the wrong one — a photo of the gallery wall, or an "inspired by" — so confidence
> carries almost all the weight.
>
> **`preview_path` exists because review cannot depend on the network.** The review
> grid — in the web UI and over MCP alike — must show the picture. A source-side URL
> alone means a curator reviewing an hour later sees broken images if a museum is
> down or rate-limiting, and it means the MCP surface has nothing local to inline.
>
> **Losing instances are retained, never deleted.** They are what makes an
> over-eager merge inspectable, they are the alternates the review card offers, and
> on acceptance they become the work's non-primary `Source` rows — which is what
> makes re-acquisition robust when an institution reorganises its site (**Q6**).
>
> **`rejected_at` is instance-scoped suppression** and must never be conflated with
> `CandidateWork.work_dedup_key`. See **Q11**.

### SpendRecord

The meter behind the fail-closed cap.

| Field | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `discovery_run_id` | UUID | FK → DiscoveryRun, nullable | Null for non-discovery spend, e.g. mat colour. |
| `artwork_id` | UUID | FK → Artwork, nullable | Set for per-artwork spend. |
| `category` | enum | required | `discovery_tokens` \| `web_search` \| `image_research` \| `mat_color_vision`. |
| `model_id` | string | nullable | |
| `input_tokens`, `output_tokens` | integer | nullable | Null where the unit is not tokens. |
| `units` | integer | nullable | e.g. number of web searches. |
| `cost_usd` | decimal | required | What was actually billed. |
| `occurred_at` | datetime | auto, indexed | Indexed — the cap is a time-windowed sum. |

> **Q4.** `category` separates `web_search` because it is billed per search, not
> per token, and may dominate token spend entirely — an unresolved open question.
> A meter that counts only tokens cannot enforce a dollar cap.
>
> **`image_research` is re-search spend, and it attributes to the ORIGINATING run.**
> When a curator rejects an image and asks for a better one, the resulting search
> costs money after the run that proposed the work has already finished. That spend
> is not orphaned and does not reopen the run: `discovery_run_id` points at the
> original, and the run's `status` stays `completed`. Without this, the true cost of
> a run is understated by every re-search it provokes, and the monthly cap under-counts.
>
> The paid re-search is `art_discovery(action='resolve_images')` — deliberately not
> a side effect of `art_review(action='reject_image')`, so that exactly one tool
> spends. See `api-contract.md`.

### TvBinding *(display plane only)*

Everything about one specific television. **Not part of the catalogue** — this is
the entity that enforces the second Direction norm.

| Field | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `artwork_id` | UUID | required | Reference to the catalogue's Artwork id. |
| `tv_content_id` | string | required | The TV's own identifier for the uploaded image. |
| `tv_thumb_md5` | string | nullable | Used to re-match after the TV loses or renames content. |
| `uploaded_at` | datetime | auto | |
| `upload_status` | enum | required | `uploaded` \| `failed` \| `orphaned`. |

> `upload_status` is explicit because the 2024 `upload_file` caught every
> exception, logged, and still reported success — recording `tv_content_id =
> None` while the retry loop set `success = True`. A nullable id with no status
> makes that failure indistinguishable from "not yet uploaded".

## Relationships

- An **Artist** has many **Artworks** (one-to-many, optional — anonymous works
  have no artist).
- An **Artwork** has many **Sources** (one-to-many). Exactly one may be
  `is_primary`.
- An **Artwork** has one **Original** (one-to-one) and many **Renditions**
  (one-to-many, one per `kind` × geometry).
- An **Artwork** has many **MatColors** (one-to-many), of which exactly one is
  `is_current`.
- An **Artwork** belongs to many **Themes** and a **Theme** contains many
  **Artworks** (many-to-many via **ThemeMembership**).
- A **DiscoveryRun** produces many **CandidateWorks** (one-to-many). A
  **CandidateWork** has many **CandidateImages** (one-to-many), of which at most one
  has `is_selected`. A **CandidateWork** becomes at most one **Artwork**, and on
  acceptance its **CandidateImages** become that Artwork's **Sources** — the
  selected one as `is_primary`, the rest retained as alternates. The
  candidate-side and catalogue-side shapes mirror each other deliberately, so
  acceptance is a promotion rather than a transformation.
- A **DiscoveryRun** accrues many **SpendRecords** (one-to-many).
- A **TvBinding** references an **Artwork** across the plane boundary — by id
  only, never by foreign key, because the two planes do not share a database.

## State Machines

### Artwork

```
(created from an accepted CandidateWork)
        │
        ▼
    accepted ──archive──▶ archived
        ▲                     │
        └──────restore────────┘
```

- Creation — a `CandidateWork` is accepted; the Artwork is minted, its
  `CandidateImage`s become `Source`s, and acquisition and preparation begin.
- `accepted → archived` — removed from circulation without losing the record or
  its mat history.
- `archived → accepted` — restoration is permitted; renditions may be stale and
  are checked via `source_content_hash`.

Rejection has no Artwork state: a rejected work never becomes one. Suppression of
re-proposal is `CandidateWork.work_dedup_key` (**Q3**).

### DiscoveryRun

```
resolving_works ──┬──────────────────────────▶ resolving_images ──┬──▶ completed
   (phase 1)      │                                (phase 2)      ├──▶ failed
                  └──▶ awaiting_approval ──┬──▶ resolving_images  └──▶ halted_by_budget
                                           └──▶ declined

any of {resolving_works, awaiting_approval, resolving_images} ──▶ cancelled
```

`cancelled` is reachable from `resolving_works`, `awaiting_approval`, and
`resolving_images` — a run stopped on request while it was working. It is the
terminal state behind `art_discovery(action='cancel')`; a run that spent money
before being cancelled keeps its `actual_cost_usd`, because the spend happened.

**Four terminal states describe four different things, and none may absorb
another.** `completed` (it finished), `failed` (something broke),
`halted_by_budget` (the cap fired), `declined` (the curator saw the work list and
its price and said no), `cancelled` (stopped on request mid-flight). Collapsing any
of them makes a deliberate choice indistinguishable from a malfunction — the same
mistake this artifact already refuses to make for `halted_by_budget`, and the same
reason `api-contract.md` requires an agent to be able to tell "you are out of
money" from "the fetch failed".

`awaiting_approval` is entered only when the resolved **work count** crosses the
configured threshold; below it the run goes straight to phase 2.

> **Amended 2026-07-20** from "the phase-2 estimate crosses the configured
> threshold". The gate was originally framed on cost. Once real per-run costs were
> measured ($0.16–0.49), a dollar threshold was gating on the axis that does not
> matter — it either never fires, or fires at a number that means nothing to a
> curator. The judgement the gate exists to invite is *scope*: "you asked for Dalí
> and I found 200 works — really?" Count is what a curator can act on at a glance.

`completed` covers runs where some works were `unresolved`. A run that resolved 34
of 40 works succeeded partially; it did not fail.

### CandidateWork

```
   ┌─────────────────────────────────────────────┐
   │                                             │
   ▼                                             │
pending ──┬──▶ accepted  (mints an Artwork)      │
          ├──▶ rejected  (terminal; suppresses)  │
          └──▶ awaiting_better_image ────────────┘
                 re-search via art_discovery(resolve_images);
                 a new instance is selected, and the work
                 returns to `pending` for review
```

`awaiting_better_image` is **not terminal**. It returns to `pending` once phase 2
selects a fresh instance, and it must not write `work_dedup_key` suppression —
that is reserved for `rejected` (**Q11**).

## Constraints

1. **Exactly one Theme has `is_active = true`.** The display plane's sync target
   is unambiguous. Enforced at write time, not assumed.
2. **Exactly one MatColor per Artwork has `is_current = true`.**
3. **At most one Source per Artwork has `is_primary = true`.**
4. **A Rendition is stale when its `source_content_hash` differs from its
   Artwork's Original `content_hash`.** Stale renditions are regenerated, never
   served.
5. **`Original.byte_size` must be greater than zero.** A zero-byte original is a
   known download failure — the 2024 code detected and deleted these inline; the
   constraint makes it impossible to record one as valid.
6. **All stored paths are relative to `ART_ROOT`.** No absolute paths in any
   record. This is what makes the catalogue portable between planes and machines,
   and it is the fix for `/home/tvpi/art` having been hardcoded in `config.py`.
7. **Suppression has two scopes and they never share a key.**
   a. A `rejected` **CandidateWork**'s `work_dedup_key` suppresses that *work* from
      future proposals, unless the curator explicitly reconsiders it.
   b. A **CandidateImage** with `rejected_at` set is excluded from re-selection for
      its work, and this must leave the work itself eligible.
   Enforcing (b) through (a) is the failure mode: asking for a better scan would
   blacklist the painting. **Q11.**
8. **Exactly one CandidateImage per CandidateWork has `is_selected = true`**, while
   the work has any unrejected instance. A work whose every instance has been
   rejected re-enters phase 2 rather than sitting selectionless.
9. **A CandidateWork with `resolution_status = unresolved` is never presented as
   accepted-able**, and never silently omitted from the run's results. It is
   reported. **Q12.**
10. **`Artwork.description` may contain only `<i>` and `<b>` markup.** Sources
   return `<p>` and `<em>`; these are normalised at ingest. The label renderer
   passes description text to Pango markup, so unescaped or unexpected markup is
   a rendering failure — today `art.py` does this substitution inline at render
   time, which means every renderer must remember to.
11. **Spend is summed over a calendar month by `occurred_at`.** When the sum
   reaches the configured ceiling, discovery transitions to `halted_by_budget`
   rather than degrading.
12. **An Original's `display_fit` is derived at acquisition, never at render
    time.** Render paths read it; they do not recompute it. This keeps the
    resolution policy in one place instead of implicit in each renderer.
13. **`Source.rights_status` is recorded for every source, including `unknown`.**
    Absence of a value is not permitted — "we did not check" and "we checked and
    could not tell" are different facts, and only the second is honest as
    `unknown`. Whether rights *gate* anything is still open; recording them is
    not.

## Rotation is host-driven, and the product owns its timing

> **This section corrects an earlier assumption in this artifact.** Rotation
> ordering and timing were initially listed as "deliberately not modelled — owned
> by the TV's own art-mode slideshow settings". Verifying the Samsung art API
> against the `samsungtvws` source proved that wrong, and the correction changes
> the model rather than being a footnote.

The TV supports exactly **one** user-upload category (`MY-C0002`), and its native
slideshow can only be scoped to a whole category — `set_slideshow_status` takes
`duration`, `type`, and `category_id`, and no content-id list. There is no album,
playlist, or non-destructive "remove from rotation" verb.

Taken at face value that forces delete-and-re-upload on every theme switch. But
the library author's own production examples
(`async_art_slideshow_anything.py`, `async_art_update_from_directory.py`) **never
call `set_slideshow_status`.** They keep the full library on the TV and drive
rotation from the host with a local timer calling `select_image(content_id)`.

**This product adopts host-driven rotation.** The consequence for the model: an
active theme becomes a *host-side pointer into a TV-side content library*, and
rotation timing becomes this product's data rather than the TV's setting.

### Theme — additional fields

| Field | Type | Constraints | Description |
|---|---|---|---|
| `rotation_interval_seconds` | integer | nullable | How long each work is shown. Null ⇒ inherit the global default. |
| `shuffle` | boolean | nullable | Random vs. `ThemeMembership.position` order. Null ⇒ global default. |

> `[ASSUMPTION: rotation timing is per-theme with a global fallback, rather than
> a single global setting | LOW impact | user can collapse to global]` — it costs
> two nullable columns and lets a contemplative theme breathe while a busy one
> moves, but no stated requirement demands it.

### Why this is nearly free here

Host-driven rotation normally trades away independence: the TV stops rotating if
the host stops. **This product already pays that cost.** The e-paper label
requires the display plane to be running and reacting to `image_selected`
callbacks, so a stopped Pi already means a stale label. Adding rotation to the
same process introduces no new availability requirement — a stopped Pi now yields
a frozen image *and* a stale label instead of a rotating image *and* a stale
label. The failure is benign: the TV stays in art mode showing the last selected
work.

What it buys is large: **theme switching becomes zero TV writes.** The
delete-and-re-upload path costs roughly 5 seconds per file by the examples'
own budgeting, so switching a 50-work theme would take minutes of churn — for the
single interaction the product exists to make easy.

### Consequent requirements

1. **`TvBinding` is persistent and survives theme changes.** It already is, in
   this model. Under the native-slideshow design it would have had to be
   torn down and rebuilt per switch.
2. **The native slideshow must be explicitly disabled once** —
   `set_slideshow_status(duration=0)` — so it does not fight host-driven
   `select_image` calls.
3. **The display plane resolves nothing from the catalogue.** It reads the **theme
   manifest** — an ordered list of entries written by curation into the shared
   `ART_ROOT` — and rotates over that. It then maps each work id to a
   `tv_content_id` using its *own* device-local store, which it is the sole writer
   of.

> **Corrected 2026-07-20 (Critic R-1/R-18).** This requirement previously read
> *"The display plane resolves active Theme → ThemeMembership → Artwork →
> TvBinding.`tv_content_id`, then rotates over that id list."* Theme,
> ThemeMembership and Artwork are **catalogue** entities, and the Direction norm
> ratified the same day says the display plane "makes no network call to the
> curation process, imports no curation module, and queries no curation database."
> A builder implementing the old sentence would have violated the norm on day one
> — and it is exactly the violation issue #7's plane-isolation test exists to
> catch.
>
> The resolution from theme to ordered id list happens **on the curation side, at
> manifest-build time**, which is also where catalogue readiness is evaluated (see
> `architecture.md` § Readiness). `TvBinding` is device state and lives in the
> display plane's own store, not in the catalogue — per this artifact's own third
> Direction norm.

## Deliberately not modelled

- **Users, accounts, roles, sessions.** Single operator; `has_multiple_party_types`
  is false. Adding these later is accommodated by the fact that Theme and
  DiscoveryRun already have owners implicitly (there is one).
- **Agent conversation history.** Agents are stateless across sessions by
  decision; there is no memory to persist.
- **TV favourites (`MY-C0004`).** A tagging primitive exists (`change_favorite`),
  but the library author notes that on 2022+ sets favourites can only be applied
  to Art Store artwork, not user uploads. Unconfirmed against real hardware, and
  it would only ever support one active subset rather than named themes — so it
  is not a path to this product's requirements even if it works.
