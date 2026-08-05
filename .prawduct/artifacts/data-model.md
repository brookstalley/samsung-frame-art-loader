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
> `CandidateImage.preview_path` files are neither upstream (they are cheap, and
> losing one costs a picture rather than a record) nor derived (nothing renders
> them from a held original — there is no original yet). They exist only to make
> review work without depending on a museum server being reachable.
>
> **"Disposable" does not mean "comes back"** (corrected 2026-08-03, after the
> claim was retired from three other artifacts and survived here). Nothing
> re-fetches a preview: `PreviewCache.store` runs once, when phase 2 first records
> an instance, and a re-search does not restore the file either, because
> `record_image` returns the instance a work already holds for that URL without
> rewriting `preview_path`. A deleted preview costs its instance the inline
> picture for the rest of that work's review, leaving the card to report the
> source URL instead. That is what makes deleting them safe *once a work is
> decided* and lossy before then — which is precisely the line the sweep draws. **They are safe to delete once their `CandidateWork`
> reaches a terminal verdict**, and deleting them must never affect the catalogue:
> the accepted work's imagery comes from acquisition, not from the preview. Flagged
> 2026-07-19 by Critic review, which noted the rows are deliberately permanent while
> the files had no recorded lifecycle at all.
>
> **One file can belong to more than one work, so the rule is about the file and
> not about the row** (added 2026-08-03, found in build). A preview's name is a
> digest of its URL, so the same museum scan resolved for two candidate works is
> two `CandidateImage` rows over one file on disk — which is what happens whenever
> phase 1 proposes the same painting under two titles and phase 2 resolves both.
> A preview is therefore reclaimable only when **every** work referencing it has
> reached a terminal verdict; reclaiming on the first work's verdict takes the
> picture out from under a work still being judged.
>
> **A row must not outlive the file it names.** Clearing `preview_path` is part of
> reclaiming a preview rather than an optional tidy-up: a row still naming a
> deleted file makes the review card report "the cached copy could not be read",
> which is a corruption message for a routine reclamation. The file goes first and
> the column is cleared after, so an interruption strands a row — which the next
> pass finds and finishes — rather than bytes nothing references, which nothing
> would ever reclaim.

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
| Q12 | Which proposed works could not be resolved to any credible image, and which kind of nothing was it? | 2 |

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

**Q12 was widened on 2026-08-04, not amended.** It always asked *which* works could
not be resolved, and it still does; what it now also answers is *which kind of
nothing* each one was. The original phrasing called an unresolved work "therefore
suspect", and that turns out to hold for only one of the four routes to
`unresolved` — see `CandidateWork.unresolved_reason`. The question is unchanged;
its answer got a second column, and a claim it carried was too broad.

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
| `rights` | string | nullable | Rights statement as given. Display-only — rights gate nothing (decided 2026-07-20; constraint 13). |
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
| `url` | string | required | Where this work can be *found* — the provider's own page or object record, which is what a curator follows to check provenance and what both surfaces publish. An attribute of the source, never the identity of this row. **It is not necessarily fetchable, and nothing may treat it as a fetch target.** For a provider serving tiles the pixels live at an image service the object's address does not name; getting from one to the other is a question only the provider can answer, so it is asked at fetch time rather than stored — see `acquisition_method`. |
| `provider` | string | required | e.g. `artic`, `google_arts`, `gallery_site`, `prize_site`, `artist_portfolio`, `http`. Open vocabulary — the contemporary web has no fixed provider list. |
| `source_class` | enum | required | `institutional` \| `contemporary_web`. The load-bearing distinction; see below. |
| `acquisition_method` | enum | required | `dezoomify` \| `direct_http` \| `api`. Determines the fetch path. **Amended 2026-08-04: it selects the path, and for `dezoomify` a resolution step runs first.** The earlier wording read as "the recorded URL is the fetch target, and this says how" — which is what the fetch path implemented, and it meant no Art Institute source could ever be acquired: those record the object's API link, and the tile fetcher declines it along with every other dezoomer. The step is not stored because it is derived from a base the museum advertises in its own responses, so a copy would go stale the day the institution moves its image service. A provider whose recorded URLs the fetcher already reads (Google Arts & Culture) needs no resolver and gets none. **`api` has no producer and no fetch path as of 2026-08-03**: the one museum client in the product resolves to tiled URLs, so nothing records it, and acquisition refuses it by name rather than guessing at a shape no response has ever exercised. The value is kept because a provider serving images through an API rather than a tile grid is a real thing this model should be able to say — building the path belongs with the provider that first needs it. |
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
| `fetch_status` | enum | nullable | How the fetch that produced *these bytes* ended — `ok` or `partial_tiles`. Read by constraint 16. Null means the row predates the column. |

> **Why `fetch_status` is stored when `display_fit` was removed (added 2026-08-04).**
> The note below argues that a *verdict* must not be stored, and a reader arriving
> at this row is owed why the same argument does not retire it. It is the same
> distinction `width` and `height` sit on: `display_fit` is a judgement about a
> deployment's panel, and it goes silently wrong when the TV changes; `fetch_status`
> is a **fact about an event that already happened** — this file came back with
> gaps, or it did not — and no later change to any deployment can make it untrue.
>
> **It cannot be derived, which is the other half.** The obvious derivation is
> `Source.last_fetch_status` for the source named by `source_id`, and it is wrong:
> that column holds the source's *most recent* attempt, not the attempt that
> produced the held bytes. One failed re-fetch overwrites it to `failed` while the
> held original — protected by staging — is still the complete image from before.
> A guard reading it would then see "held quality: failed", conclude anything is an
> improvement, and let a partial overwrite a complete master, which is the exact
> defect constraint 16 exists to prevent.
>
> `failed` is not among the values. A failed fetch produces no bytes to record, so
> no Original can carry it.

> **`display_fit` is NOT a column — it is derived (decided 2026-07-20).** It was
> previously stored here, computed once at acquisition. That became wrong the moment
> panel geometry became a *deployment value* rather than a constant: whether an
> original is adequate depends on the artwork box, the artwork box depends on the
> panel and mat configuration, and this product must run on whatever Frame someone
> owns. A verdict computed at acquisition is a stored judgement about a machine the
> curation plane does not own, and it goes silently wrong the day the TV changes.
>
> `width` and `height` above are panel-independent **facts** and remain stored. The
> **verdict** is computed from `(width, height, panel geometry, mat configuration)`
> by one service-layer function, which both the review grid and the renderer call.
>
> **This preserves the real intent of the old constraint 12** — "keep the resolution
> policy in one place instead of implicit in each renderer" — using the ratified
> service-layer norm (`architecture.md` § Direction) rather than using storage to do
> it. Same guarantee, no value that can drift. Consistent with the readiness and
> re-search decisions: derived state cannot disagree with what it is derived from.
>
> **Values:** `native` (source ≥ artwork box; downscaled to fit) · `matted_small`
> (source smaller than the box; pasted at native size, so the mat is simply larger)
> · `below_floor` (would render smaller than the configured minimum wall size).
>
> **There is no `upscaled` value.** The pipeline never upscales — `image.thumbnail()`
> already never did, and "acquisition at gallery resolution" is a product promise.
> Upscaling is the one option that actively misrepresents quality: it converts an
> honest "this image is small" into an apparent rendering fault. A declared state
> with no producer is the same defect the re-search review flagged, so the value is
> removed rather than reserved.

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
| `chosen_at` | datetime | auto | When this choice was made. **Added 2026-07-27 at build.** |

> **`chosen_at` was a gap this artifact's own purpose exposed.** The field list
> had no timestamp, while the paragraph below required the history to be
> reviewable and reversible — and "which colour did the new model replace" has no
> answer in a set of rows with no order. Every sibling entity already carries its
> instant (`Source.last_fetched_at`, `Rendition.generated_at`,
> `Artwork.created_at`); this one was simply missed.

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

### Directive

The standing instruction to the display plane. **Exactly one row, always** — a
singleton, seeded when the catalogue file is created so that no caller ever has
to make it.

| Field | Type | Constraints | Description |
|---|---|---|---|
| `sequence` | integer | required | Monotonically increasing for the life of the catalogue. The display plane acts once each time it observes this go up. |
| `pinned_work_id` | UUID | FK → Artwork, nullable | The work an advance points at. Null means the advance is a plain step. |

> **This entity was added 2026-07-27, at build, to close a gap this artifact had
> left open.** `architecture.md` § The theme manifest pins the directive sequence
> as *catalogue-side* — "curation owns the counter and stores it catalogue-side,
> which is what makes this cheap to guarantee" — and `operational-spec.md`'s
> exercised restore path restores it along with everything else, so it is part of
> the persisted format whether or not it was modelled. It had no entity here, and
> an unmodelled part of a persisted format is one the next chunk invents
> implicitly, in whatever shape that chunk happens to need.
>
> **Why it is not a column on Theme.** The sequence has to survive theme
> switching — a switch rewrites the manifest's entry list and carries the counter
> forward unchanged. A per-theme counter would reset on every switch, and a reset
> reads to the display plane as an advance (or masks a real one), firing a
> directive nobody issued.
>
> **When the pin is cleared** *(settled 2026-07-27; previously unstated)*. The pin
> is not standing state that persists until replaced, and it is not cleared by
> everything either. Exactly two things clear it:
>
> - **A `next` directive**, which supersedes it. A step that left the pin in place
>   would be read as "jump to that work again" rather than "move on", so the two
>   cannot both be in force.
> - **Archiving the pinned work**, which makes it unsatisfiable — an archived work
>   is out of circulation, so a pin naming one is an instruction that can never be
>   carried out. This withdrawal **does not advance the sequence**: archiving is
>   not an instruction to the display plane, and an advance here would fire a
>   directive nobody issued, stepping the wall to an unrelated work.
>
> Nothing else clears it. In particular a manifest rebuild carries both the
> sequence and the pin forward, because the display plane acts only on an advance
> and a pin sitting behind an unchanged sequence is inert.
>
> **Widened at build, 2026-07-31:** the refusal below now covers every work that
> could not reach the wall, not only archived ones — a work with no original, no
> render, a stale render or no current mat colour is unshowable in exactly the
> same way, and pinning one produced a written directive and a wall that never
> moved. The reasoning and the residual display-side obligation are in
> `api-contract.md` § How `art_display` reaches the display plane.
>
> For the same reason, `show_now` **refuses an archived work** rather than pinning
> one and relying on the manifest to filter it out later.

### DiscoveryRun

One invocation of the discovery flow. Exists to make cost visible and to give
candidates provenance.

| Field | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `kind` | enum | required | `discovery` \| `resolve`. A `resolve` run is phase 2 only — the re-search behind `resolve_images`. See below. |
| `parent_run_id` | UUID | nullable, FK → DiscoveryRun | Set on `resolve` runs: the run that originally proposed these works. Null on `discovery` runs. |
| `intent_text` | text | required for `kind='discovery'`, else nullable | The curator's natural-language intent, verbatim. A `resolve` run has no intent of its own — it inherits the parent's. |
| `strategy` | text | nullable | The interpreted plan, for explaining results. **Written by the phase-1 engine when the work list settles (2026-08-02)** — it is the model's own account of how the intent was read, so it cannot exist before the intent has been read, and a run still in `resolving_works` honestly has none. Deliberately not composed from configuration, which would describe the deployment rather than the reading. |
| `initiated_by` | enum | required | `web_ui` \| `web_ui_agent` \| `mcp_client`. Which surface started this run. |
| `status` | enum | required | `resolving_works` \| `awaiting_approval` \| `resolving_images` \| `completed` \| `failed` \| `declined` \| `cancelled` \| `halted_by_budget` \| `interrupted`. See State Machines. |
| `estimated_cost_usd` | decimal | nullable | Phase-2 estimate, computed from the phase-1 work count. |
| `actual_cost_usd` | decimal | nullable | Reconciled after. |
| `approval_required` | boolean | required | Whether the resolved **work count** crossed the configured threshold (amended 2026-07-20 from "the phase-2 estimate"). Recorded per run, not re-derived — the threshold can change. |
| `unresolved_work_count` | integer | nullable | Works from phase 1 for which no credible instance was found. **Q12.** |
| `started_at` | datetime | required | **Narrowed from nullable 2026-07-27.** A run row is only created by starting one, and both entry states (`resolving_works` for a discovery run, `resolving_images` for a resolve run) are active — there is no state in which a row exists and the run has not started. Nullable would have made every reader handle an absence that cannot occur. |
| `completed_at` | datetime | nullable | Written by whichever transition ends the run. On `interrupted` it records when the death was *observed* at startup, not when it happened: the process that died could not write one, and a terminal run with no end time silently drops out of any window a report asks for. |

> **The re-search is a run, not a side effect (decided 2026-07-20).** `resolve_images`
> is a paid, minutes-long operation, and it previously created no row at all — so the
> one tool the design says is the only one that spends money had no handle to poll, no
> cancel, no cost of its own, and nothing stopping the same work ids being submitted
> twice concurrently. Modelling it as a `DiscoveryRun` with `kind='resolve'` fixes all
> four at once by reusing machinery that already exists, rather than inventing a
> second, weaker handle beside it. A resolve run enters directly at
> `resolving_images`: `resolving_works` and `awaiting_approval` are unreachable for
> it, because phase 1 already happened on the parent.
>
> **`parent_run_id` is what keeps cost attributable to intent.** Spend from a
> re-search belongs to the resolve run — that is the point of giving it a row — but
> "what did asking for Dalí actually cost?" must still be answerable, so it rolls up
> through the parent chain. This supersedes the earlier rule that re-search spend
> attributes directly to the originating run; that rule existed only because there
> was no other row to attribute it to. A `completed` parent still never reopens.
>
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
| `provenance` | enum | required, defaults `proposed` | `proposed` \| `offered`. Who put this work in front of the curator: the model named it, or a wired collection volunteered it. Nullable *on disk* only so the column can be added to files written before collections were browsable — a null reads as `proposed`, that being the only thing which could have written a row then. |
| `resolution_status` | enum | required | `pending` \| `resolved` \| `unresolved`. Reflects the **latest** resolution attempt, whether that was the original phase 2 or a later re-search. `unresolved` ⇒ that attempt found no credible instance the curator has not already rejected. **Q12.** |
| `unresolved_reason` | enum | nullable | Which kind of nothing: `not_held` \| `identity_refused` \| `size_unknown` \| `below_floor` \| `all_rejected`. Set whenever `resolution_status = unresolved`, null otherwise — **with one honest exception: a row whose attempt predates the column reads null beside `unresolved`.** The column was added nullable and existing files are widened without backfill, so the two runs that motivated it are themselves in that state. A null beside `unresolved` therefore means "this attempt happened before the reason was recorded", never "no reason applies". **Q12.** |
| `verdict` | enum | required | `pending` \| `accepted` \| `rejected` \| `awaiting_better_image`. See State Machines. |
| `rejected_reason` | text | nullable | Optional curator note. |
| `decided_at` | datetime | nullable | |

> **`confidence` has a fourth derivation, and it is not a comparison result.**
> The three tiers below this table grade *how much of an identity was
> confirmable* when a provider's record was checked against a work someone else
> named. An `offered` instance was never checked against anything: the collection
> produced the work and the picture of it from one row of its own catalogue, so
> there is no near-match question to answer. It is recorded at the same value as a
> confirmed title-and-artist match and means something different — **anything
> ranking, thresholding or auto-accepting on `confidence` is reading two kinds of
> number**, and must consult `provenance` to tell them apart. Not raised to 1.0
> for the same reason the confirmed tier is not: nothing has inspected the image.

> **An `offered` work is a candidate in every respect but its origin.** It takes a
> verdict, it can be accepted into the catalogue, and its instance is recorded and
> selected like any other — the label is not a lesser class of row. What the label
> forbids is the merge: an offered work's image may never be attached to a
> `proposed` work, and an offered work is never presented under a title the model
> named. Those are the same rule from two directions, and together they are what
> keeps this from becoming the confident near-match constraint 9 forbids. The two
> counts are also reported apart wherever a surface shows a number, because the
> curator approved a work list of a stated size and the supplement adds to it.
>
> **The approval gate cannot see offered works, structurally rather than by rule.**
> It is computed when the work list settles, which is before phase 2 has run and
> therefore before anything could have been offered — an offer exists only to
> supplement what phase 2 failed to confirm.

> **`awaiting_better_image` is the verdict an accept/reject binary cannot express**
> — "I want this work; this instance is not good enough; find another." It is not
> an edge case, and it is not terminal: the work returns to review once a new
> instance is selected. Modelling it as a rejection would suppress the work via
> `work_dedup_key` and silently lose a painting the curator explicitly asked to
> keep (**Q11**).
>
> **`resolution_status = unresolved` is a first-class outcome, not an absent row.**
> Phase 2 failing to find any credible instance is one of the signals that phase 1
> may have invented the work. Dropping it from the batch discards that signal;
> attaching a low-confidence near-match actively launders it.
>
> **`unresolved` must say which kind of nothing, and the sentence above is why.**
> A work reaches `unresolved` by five routes that are not interchangeable: nothing
> came back whose title matched (`not_held`); a record matched the title and
> disagreed on the artist (`identity_refused`); a matching record reported no
> dimensions, so it could not be judged against the floor (`size_unknown`); every
> matching record renders below the floor (`below_floor`); or the work holds
> instances and the curator has turned down every one of them, with this attempt
> finding nothing to add (`all_rejected`). The first is a fact about the
> collection, the second about two spellings of a name, the next two about the
> record, and the last about the curator. **Only the first carries the
> invented-work signal** — the rest are the collection saying "I have this, but not
> like that", or the curator saying "not that scan", which are nearly the opposite.
> So the claim that `unresolved` means phase 1 may have invented the work is
> narrowed here to `not_held`, and the docstrings asserting the broader reading are
> amended with it.
>
> > **`all_rejected` was added on 2026-08-04 after the list had been written at
> > four, and the correction is kept rather than smoothed over** because the reason
> > it was missed is reusable. It was ruled unreachable on the grounds that
> > rejecting every instance sets the *verdict* to `awaiting_better_image` rather
> > than the resolution status — true at the rejection, and irrelevant, because the
> > write that matters happens later: the re-search that finds nothing then lands
> > the same work at `unresolved`, which this document already said in as many
> > words a few paragraphs above. **Reachability was argued from the write site
> > that sets the value and not from the one that sets the status**, and a test
> > asserting the whole path existed the entire time. An enum value is reachable if
> > *any* path reaches it, so the search has to be over paths, not over the site
> > that looks most relevant.
>
> A curator reading a bare `unresolved` cannot tell those apart, and neither can
> anyone diagnosing a run afterwards — which is how two runs that resolved nothing
> on 2026-08-04 sat unexplained while both suites were green. The reason is
> therefore **derived on the same write as the status, from the same instances**,
> and reported on the wire beside it. It records decisions phase 2 already makes
> and currently throws away; it is not a new judgement, and it is not asserted by
> the caller.
>
> **Precedence is by how far the work got: the deepest gate any of its records
> reached is what it reports.** A work is `not_held` only when *no* record matched
> its title; a single title match takes that reading off the table however many
> other records missed. Past that, deeper beats shallower — `size_unknown` over
> `identity_refused` — because the deepest gate is the most informative thing that
> is true: "the collection holds this, too small for your wall" is actionable, and
> "some record somewhere did not match" is not. Stated here rather than left to the
> write site, because choosing one label where several apply is a judgement, and an
> underived rule is how it silently becomes whichever result the provider happened
> to return first.
>
> **The two deepest reasons need no precedence against anything, and that is a
> property of the data rather than a convention.** `below_floor` and `all_rejected`
> are read from the rows the work already holds, and they are mutually exclusive by
> construction: rejected instances are filtered out before the floor is applied, so
> a work whose surviving instances are all below the floor is `below_floor`, and a
> work with no surviving instances at all is `all_rejected`. A work cannot be both,
> and either one outranks every reason derived from what the search discarded —
> because a row on the card is further than a result that never became one.
>
> **One value was considered and deliberately left out.** A `no_rights_clear_image`
> is unreachable: rights are a quality weight and never a filter (constraint 13),
> so nothing is ever refused for them. Adding it would be a value nothing can
> produce, which reads to the next person as a route that exists — and the way to
> be sure of that is to look for a path that reaches it, not for a site that would
> set it.
>
> **Redefined 2026-07-20, deliberately and with the hazard named.** It previously
> meant "phase 2 found no credible instance" — an outcome of the original run only.
> It now tracks the *latest* resolution attempt, which is what gives a failed
> re-search a terminal representation without adding a verdict value for it. A work
> in `awaiting_better_image` whose re-search comes back empty lands at
> `unresolved`, and constraint 9 already forbids presenting it as accepted-able or
> silently omitting it — so the dead end reports itself.
>
> **This only happens when every instance is rejected.** If unrejected instances
> remain, re-search finding nothing new is not a dead end: constraint 8 selects the
> next-best surviving instance and the work returns to `pending`. So `unresolved`
> after a re-search means what it always meant — there is nothing here to accept.
> The redefinition is written down rather than left implicit because a widened
> meaning that nobody records is how the next drift starts.
>
> **Q3.** `work_dedup_key` is what stops discovery re-proposing declined works
> forever. The *column* was specified before its derivation, because retrofitting
> suppression after rejections have accumulated makes the early rejections
> unrecoverable. **The derivation was decided by measurement on 2026-08-02** and is
> recorded below.
>
> **A source identifier was considered and is ruled out.** An earlier phrasing here
> offered "normalised artist + title, *or a source identifier where one exists*".
> Both halves of that fail. It contradicts this document's own § Direction norm —
> **identity is never a source URL** — whose reasoning covers an institution's
> accession number just as well: the same painting held by two institutions would
> take two identities. And it is unreachable in any case, because the key is
> written by `propose_work` during phase 1, before phase 2 has found any source at
> all.
>
> **An interim derivation ships before the spike settles it, and that is named
> rather than left to happen (2026-08-02).** The column is `required`, and phase 1
> mints `CandidateWork` rows as soon as it exists — so discovery phase 1 cannot
> wait for the spike that chooses the derivation. Whatever phase 1 ships is
> therefore a **provisional** key: normalised artist + title, marked provisional at
> its single implementation site, and treated by the spike as its starting
> hypothesis rather than as an incumbent to be argued against.
>
> **Why this needed saying:** unrecorded, the sequence produces a derivation that
> is never *decided* — it is merely first, and by the time the spike runs there are
> rows depending on it. The spike's remit explicitly includes replacing it, and
> replacing it is a **re-key of existing rows**, not just a code change: keys
> already written under the provisional rule must be recomputed, or suppression
> silently splits into two regimes and the same work gets proposed twice.
>
> **Shipped 2026-08-02 at one site: `curation/src/curation/discovery/dedup.py`.**
> Normalised artist and title — casefolded, accents stripped, punctuation
> dropped, whitespace collapsed — joined by a separator normalisation guarantees
> cannot appear inside either half. A work with no artist is keyed under
> `(unattributed)`, whose brackets are load-bearing: no real name can normalise
> to it, and a bare sentinel collided with an artist actually so named.
>
> **Both known failure modes have tests asserting the wrong behaviour**, which is
> deliberate. "Untitled" by one artist collides with itself across genuinely
> different paintings (a false positive: one rejection suppresses a work nobody
> declined), and a translated title splits one work in two (a false negative:
> suppression quietly stops working). They pull in opposite directions, which is
> precisely why neither can be fixed by guessing — and a replacement argued for
> later needs the current behaviour written down rather than remembered.
>
> ---
>
> **DECIDED 2026-08-02 — the derivation, measured against real output.** The
> provisional key held **7 of 36** recurring works together across 128 proposals
> captured from 22 real runs. The rule now shipped holds **29 of 36**. That
> fraction is not a code-quality metric: it is the share of a curator's rejections
> that keep working, so a fifth of them holding meant Q3 was mostly not answered.
>
> **The provisional key's two named hazards were both wrong about what bites.**
> The feared false positive — bare "Untitled" repeated by one artist — barely
> occurs, because real catalogue titles carry disambiguators (`Untitled #1`,
> `Untitled #12`, `No. 1 (Untitled)`) that the normalisation already preserves.
> The dominant failure was one nobody had listed: **the same model, on the same
> intent, minutes apart, appends a year.** `Abstraction Blue` and `Abstraction
> Blue (1927)` are one painting and were two identities.
>
> The rules, each answering an observed rewrite: citation markup removed; a
> trailing date dropped; a trailing `from the series ...` clause dropped; a
> trailing alternate title in parentheses dropped *unless the remainder names
> nothing in particular*; a parenthesised alias dropped from the artist.
>
> *(Amended 2026-08-02: this list also carried "a bilingual `Original / English`
> compound reduced to its first half". That rule was removed from the code the same
> day and the clause is struck here so the decision record does not go on
> prescribing what the decision un-made. It fired on nothing — zero of the 128
> realistic proposals in the corpus carry the form, which appeared only in a capture
> whose intent had asked for titles in both languages — and its direction could not
> be chosen from evidence, while its failure direction is merge, the one with no
> recovery.)*
>
> **The two directions are not symmetric, and that decides every close call.** A
> split asks the curator about one painting twice — visible, self-correcting. A
> merge silently withholds a painting nobody turned down: it is skipped, and
> nothing tells them it existed. So two rules that *scored better* were rejected —
> stripping any trailing parenthetical (which collapses Richter's hundreds of
> `Abstraktes Bild` onto one identity) and reducing an artist to first and last
> name (which turns `Hans Holbein the Younger` into `hans younger`).
>
> **Note that this asymmetry is the opposite of the one in § Direction's "collapse
> aggressively, but never discard".** That corollary is scoped to *instances*,
> where a losing candidate is retained as a non-primary row and an over-eager merge
> stays inspectable. Nothing is retained at the work scope, so the same instinct
> applied here would invert the safety property — which is the Q3/Q11 trap in a
> new place.
>
> **The seven residual splits are two known shapes**, both asserted by
> `tests/unit/test_dedup_key_corpus.py` so the claim fails rather than decays: a
> trailing provenance tail (`..., ca. 1633-35, The Metropolitan Museum of Art`),
> and a patronymic (`Jacob Isaacksz van Ruisdael` against `Jacob van Ruisdael`).
>
> **The corpus cannot demonstrate an over-merge**, holding no two works any
> candidate would wrongly unite, so its zero merges is absence of evidence rather
> than evidence of absence. The cases that would show one are pinned as separate
> unit tests.
>
> **One known merge risk is carried deliberately, in the harmful direction.** The
> rule that drops a trailing parenthetical holds it back when the remainder "names
> nothing in particular", and *nothing in particular* is an enumerated,
> English-only set — `untitled`, `study`, `landscape`, `portrait` and the like. So
> `Landschaft (Studie)` reads as distinctive, its parenthetical is dropped, and it
> can merge onto a different `Landschaft`. Enumeration is still the right shape:
> length and word count cannot separate these from real one-word titles, since
> `Coquelicots` is as short as `Untitled`. The list grows only when a real proposal
> carries the term — never on the guess that a model might emit it — which means
> the exposure is non-English titles in that one narrow form, and it is recorded
> here rather than left to be rediscovered from the code.
>
> **The re-key shipped on 2026-08-05, as a mechanism rather than a one-off.**
> When it was written this said "no re-key shipped, because no rows exist to
> re-key" — true then, and false by the time the citation rules gained the bare
> form, by which point the catalogue held rows and seven of them were keyed under
> a citation the rules now strip. `DiscoveryService.reconcile` re-cleans
> every stored title at startup and rewrites the key of any it changed, so the
> obligation is discharged by each start rather than owed by each change. It is
> idempotent and normally a no-op. A title the cleaning empties is left exactly as
> stored — `require_text` refuses an empty one on the way in, so writing one would
> make the row unreadable and destroy the evidence of a rule that reached too far.

### CandidateImage

One image *instance* found for a candidate work. Many per work; exactly one
selected. Produced by phase 2.

| Field | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `candidate_work_id` | UUID | FK → CandidateWork, required | |
| `url` | string | required | Where this instance was found. Unique per `candidate_work_id` — see constraint 7. |
| `preview_url` | string | nullable | Small image for review. Source-side URL. |
| `preview_path` | string | nullable | Cached local copy, relative to `ART_ROOT`. Review must not depend on a museum server being reachable. |
| `provider` | string | required | e.g. `artic`, `google_arts`, `gallery_site`. Open vocabulary. |
| `source_class` | enum | required | `institutional` \| `contemporary_web`. |
| `acquisition_method` | enum | required | `dezoomify` \| `direct_http` \| `api`. How the bytes are fetched. **Added 2026-07-27** — see below. |
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
> **`source_class`-dependent dominance is NOT built, and the ranking is
> unconditional (2026-08-02).** This is an explicit deferral, not an oversight —
> recorded here because the paragraph above reads as a description of shipped
> behaviour and is not one.
>
> **Why it is deferred: nothing produces a `contemporary_web` candidate.** Phase 2
> reaches museum APIs only, and every instance it records is `institutional`. The
> value appears on the candidate side nowhere else; the one other producer in the
> tree is the legacy seeder, which writes catalogue `Source` rows for works already
> accepted and never passes through this ranking. So a switch on `source_class`
> would today have exactly one reachable branch, and its other branch would be a
> test asserting behaviour no deployment can reach — the green-test-that-cannot-fail
> this project rejects elsewhere.
>
> **What replaces it is stronger in the direction `contemporary_web` needs, which
> is why the deferral is safe.** Confidence is not a weight here at all: an
> instance whose title or artist disagrees with the request is **refused**, not
> ranked lower. For a work with exactly one candidate image — the
> `contemporary_web` shape — that means confidence carries not "almost all" the
> weight but all of it, since a wrong image is discarded rather than left to lose a
> comparison it has no competitor in.
>
> **What is genuinely not yet built is the `institutional` half: canonicity.**
> Quality currently orders equally-confident instances by resolution and rights,
> which is a reasonable proxy while every candidate comes from the holding
> institution itself and is not one once a second provider offers copies of the
> same work. **The chunk that adds a non-museum provider owns this**, and should
> reopen this paragraph rather than inherit it.
> **How both scores are derived (settled 2026-08-02, when phase 2 was built).**
> The two fields existed with their meanings recorded and their *derivations*
> open. Both are now decided, and the first one was decided by measurement rather
> than by design.
>
> **`confidence` is an identity comparison, never a provider's relevance score.**
> The Art Institute's search was measured returning a real work by a real artist,
> at a comfortable score, for a painting it does not hold: asking for *The
> Persistence of Memory* surfaces *Ann-In Memory* by Joseph Cornell. Its scores
> are also not comparable between queries — two correct searches topped out at
> 3,362 and 122 — and a nonsense query returns the whole collection rather than
> nothing (`artic-api-findings.md`). So the test is whether the title the provider
> returned *is* the requested title and whether the artists agree, **derived from
> the same normalisation `work_dedup_key` is built from** rather than a second
> one free to drift from it.
>
> Three tiers, because how much of the identity was confirmable differs:
> both title and artist agree; the title agrees and the *request* named no
> artist; the title agrees and the *record* names no artist. **A disagreement
> between two named artists is disqualifying, not a deduction** — this collection
> holds *American Gothic* by Grant Wood and *American Gothic* by Elizabeth Layton,
> so a scheme that merely ranked one above the other would attach the wrong one
> whenever the right one was absent. Nothing that fails the comparison is recorded
> at all: a near-match kept at low confidence is still selected the moment nothing
> better exists, which is precisely the case a work no museum holds produces, so
> the only safe representation of "this is a different painting" is absence.
>
> **`quality_score` is the fit verdict banded, then graded within the band**, plus
> a small rights term. The metric is *not* rendered size, and the difference bites:
> a 6949x8400 master rendered into a wide artwork box is limited by the box's
> height and comes out shorter on the wall than a 2000x1500 one that suits the
> shape — while having four times the resolution to spare. Ranking on rendered
> inches prefers the smaller file. `nonfunctional-requirements.md` § Output Quality
> says what isolates resolution: whether the render is a downscale or a
> native-size paste. So the verdict picks the band and coverage grades within it.
>
> Rights contribute a minority term, which is this field's own definition
> ("resolution, fidelity, rights, institutional provenance") and **not a rights
> gate** — constraint 13 stands: nothing is excluded or filtered on rights, and an
> in-copyright instance with better resolution still wins.
>
> **`preview_path` exists because review cannot depend on the network.** The review
> grid — in the web UI and over MCP alike — must show the picture. A source-side URL
> alone means a curator reviewing an hour later sees broken images if a museum is
> down or rate-limiting, and it means the MCP surface has nothing local to inline.
>
> Cached under `previews/` in `ART_ROOT`, kept apart from `thumbs/` because the
> two have different lifecycles: a thumbnail belongs to a work the catalogue
> holds, a preview to one nobody has accepted and may never. The file is named
> from a digest of its source URL, so a work re-searched later finds its preview
> already on disk and the museum is asked once per distinct image rather than
> once per attempt. **A preview that will not download is not a failure** — the
> instance is recorded with its source-side URL and no `preview_path`, because
> losing a work over a missing thumbnail would be the tail wagging the dog.
>
> **Losing instances are retained, never deleted.** They are what makes an
> over-eager merge inspectable, they are the alternates the review card offers, and
> on acceptance they become the work's non-primary `Source` rows — which is what
> makes re-acquisition robust when an institution reorganises its site (**Q6**).
>
> **`rejected_at` is instance-scoped suppression** and must never be conflated with
> `CandidateWork.work_dedup_key`. See **Q11**.
>
> **`acquisition_method` was added 2026-07-27, when promotion was first
> implemented.** The Relationships section says the candidate-side and
> catalogue-side shapes mirror each other deliberately, "so acceptance is a
> promotion rather than a transformation" — and every field of `Source` did have a
> counterpart here except this one, which is `NOT NULL` on the far side. So the
> claim was very nearly true and the one exception fell on the field that says how
> to fetch the bytes.
>
> The alternatives were both worse than adding the column. Deriving it at
> acceptance from `source_class` guesses (an institution with a public API is
> `institutional` and is not dezoomify), and a wrong guess surfaces as a
> re-acquisition that fails at exactly the moment every derived file has already
> been lost — the scenario **Q6** exists for. Making it nullable on `Source` would
> weaken a catalogue-side record to accommodate a pipeline-side omission. It
> belongs here because it is knowable only here: the search reached this instance
> *through* a provider that offers tiles, a file, or an API, and nothing
> downstream can recover which.

> **A fourth derivation exists and is not a comparison result.** An `offered`
> candidate — one a wired collection volunteered rather than the model naming it
> — was never checked against anything: the collection produced the work and the
> picture of it from one row of its own catalogue. Its instance is recorded at the
> same value as a confirmed title-and-artist match and means something different,
> so **anything ranking, thresholding or auto-accepting on `confidence` is reading
> two kinds of number** and must consult `provenance` to tell them apart. The
> reasoning is restated at § CandidateWork, where `provenance` is defined.

### Where a candidate's fields land on acceptance

Promotion is mechanical, and this table is what makes "mirror rather than
transform" checkable rather than asserted:

| `CandidateImage` | → `Source` | Note |
|---|---|---|
| `url`, `provider`, `source_class`, `acquisition_method`, `confidence`, `selection_rationale` | same field | Carried unchanged |
| `rights_status` | `rights_status` | `unknown` where the candidate has none: constraint 13 forbids absence, and "we did not check" is honestly `unknown` |
| `is_selected` | `is_primary` | The selected instance becomes the primary source; the rest are retained as alternates (**Q6**) |
| `preview_url`, `preview_path`, `estimated_width`, `estimated_height`, `quality_score` | *(not carried)* | Pre-acceptance facts. Previews are disposable, and real dimensions come from the acquired `Original` rather than from an estimate |

`CandidateWork.proposed_artist` is **not** carried into an `Artist` row here. It
is free text that has to be parsed and matched against existing artists; until
that lands an accepted work carries no `artist_id` and the attribution is added
with it.

**What the 2026-08-02 derivation spike settles for this, and what it does not
(recorded because "settled with `work_dedup_key`" used to stand here and is too
strong).** Artist matching is the third call site the derivation is meant to
serve, alongside cross-run suppression and within-run dedup. The first two are
live and share `curation/src/curation/discovery/dedup.py`; **this one must derive
its identity from that module rather than reimplement normalisation**, which is
the whole point of settling it once.

What is settled: casefolding, accent-stripping, punctuation-dropping and
alias-dropping — `El Greco (Domenikos Theotokopoulos)` and `El Greco` are one
painter, and that is measured.

What is **not** settled, and is a live hazard for this call site specifically: an
artist's name varies in ways a work's title does not. `Jacob Isaacksz van
Ruisdael` and `Jacob van Ruisdael` appeared in the same corpus as one painter and
key apart. The obvious fix — keeping the first and last name tokens — was measured
and rejected, because it turns `Hans Holbein the Younger` into `hans younger`. So
whoever builds this inherits an open question rather than a solved one, and it
carries the harsher failure direction: merging two painters attributes a work to
the wrong person on a physical label (**Q9**), where splitting one merely creates
a duplicate `Artist` row.

No artist-identity function ships ahead of that call site. There is nothing to
measure a candidate against until `Artist` rows are being matched, and shipping an
unmeasured one now would repeat exactly the mistake this spike was convened to
correct.

`[DECISION: a candidate matches an existing Artist only on exact `artist_key()`
equality, and a near-miss is reported rather than merged | the failure directions
are not symmetric, so the tie goes to the reversible one — a duplicate `Artist`
row is visible in the catalogue and can be merged later, where a wrong merge puts
another painter's name on a physical label and leaves no trace that a decision was
ever made. Every heuristic that would close the `Jacob Isaacksz van Ruisdael` /
`Jacob van Ruisdael` gap was measured against the corpus and takes the harsher
direction to do it: keeping first and last tokens turns `Hans Holbein the Younger`
into `hans younger`, and a stopword list for the forms that break it (`the
Younger`/`Elder`, `Sr`/`Jr`, patronymics like `Isaacksz`, nobiliary particles) is a
set of guesses measured against nothing until real accepted works exist to measure
against. So the split is taken deliberately and made *visible*: when a new row is
minted and an existing artist shares a surname token, acceptance says so, which
turns a silent duplicate into a reported one a curator can act on. | user can
veto/override]`

**Two properties this inherits from `artist_key()` rather than restating.** It
normalises casefolding, accents, punctuation and parenthesised aliases, so
`El Greco (Domenikos Theotokopoulos)` and `El Greco` are one painter without any
work here. And it returns **empty** for a name that normalises to nothing — which
a matcher must read as *unattributed*, never as a key. Two unattributed works
share that empty string, so a lookup that keyed on it would merge every
unattributed work in the catalogue into a single artist named nothing: the
worst-case wrong merge, reached without any name being similar to any other. An
unattributed candidate takes no artist at all, which is what `artist_id`'s
nullability is for.

### SpendRecord

**Attribution and history — not enforcement.** This is the record of what was
spent, on what, by which surface. It does **not** hold the ceiling and no code
path consults it before spending.

| Field | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `discovery_run_id` | UUID | FK → DiscoveryRun, nullable | Null for non-discovery spend, e.g. mat colour. |
| `artwork_id` | UUID | FK → Artwork, nullable | Set for per-artwork spend. |
| `category` | enum | required | `discovery_tokens` \| `web_search` \| `image_research` \| `mat_color_vision` — **the last of these has a producer but writes no row today; see the deferral below.** |
| `model_id` | string | nullable | |
| `input_tokens`, `output_tokens` | integer | nullable | Null where the unit is not tokens. |
| `units` | integer | nullable | e.g. number of web searches. |
| `cost_usd` | decimal | required | What was actually billed. |
| `occurred_at` | datetime | auto, indexed | Indexed for reporting windows. **Not** the basis of any ceiling — see below. |

> **This table does not enforce the ceiling, and must never be made to.** The
> ratified Direction norm (`nonfunctional-requirements.md`) is that *spend ceilings
> are enforced by the provider, never by application code* — the hard cap is an
> OpenRouter per-key credit limit that refuses calls when exhausted. A local sum that
> fails open is indistinguishable from one that works: no error, no alert, just a
> bill. `halted_by_budget` is therefore derived from **the provider's refusal**, and "budget left"
> is read from `GET /api/v1/key` (`limit_remaining`), never from `SUM(cost_usd)`.
>
> What this table *is* for: per-run and per-surface cost attribution, the
> after-the-fact "what did this run cost", and monthly reporting. Those are real
> needs and none of them is enforcement.
>
> **`mat_color_vision` is declared and unwritten, recorded here so the row does not
> read as implemented (2026-08-04).** The category and its two nullable-key columns
> predate any producer. Chunk 18B shipped the producer — a vision call per accepted
> work through `MatEngine` — and it writes no SpendRecord: the cost is returned to
> the caller on `cost_usd`, reported in the tool result, and then discarded. So the
> monthly total from `art_discovery(action='spend')` omits every mat call. The
> figures are small (about $0.000063 a call, one per accepted work) and the ceiling
> is unaffected either way, because the ceiling is the provider's and this table
> never enforced it — but a month total that silently excludes a whole paid path is
> the wrong kind of small.
>
> **It is deferred rather than merely missing, and the reason is where the writer
> would have to live.** `record_spend` belongs to `DiscoveryService`, so recording
> mat spend today means `PreparationService` taking a dependency on the discovery
> service to reach an accounting concern that has nothing to do with discovery —
> deepening precisely the coupling that is already filed for removal. Spend
> accounting is separable on its own records and its own aggregation, and the mat
> path is the second caller that proves it. The writer lands with that split, and
> both are tracked in the backlog.
>
> **Q4.** `category` separates `web_search` because it is billed per search rather
> than per token, so a token-only breakdown would misattribute cost. The earlier
> claim that it "may dominate token spend entirely — an unresolved open question"
> is **retired**: resolved 2026-07-20 at $0.03–0.25 per run against $0.13–0.24 of
> tokens, so worst case it roughly doubles a run. Search fees bill as OpenRouter
> credits, so the provider ceiling already covers both without this table's help.
>
> **`image_research` is re-search spend, and it attributes to the RESOLVE run**
> (2026-07-20). `discovery_run_id` points at the `kind='resolve'` run, which is the
> point of giving the re-search a row of its own; cost rolls up to the original
> intent through `DiscoveryRun.parent_run_id`. **This supersedes the earlier rule
> that it attributed directly to the originating run** — that rule existed only
> because there was no other row to attribute it to. Still true, and unchanged: the
> originating run never reopens, and its `status` stays `completed`.
>
> The paid re-search is `art_discovery(action='resolve_images')` — deliberately not
> a side effect of `art_review(action='reject_image')`, so that exactly one tool
> spends. See `api-contract.md`.

### ResolveRunWork

Which `CandidateWork`s a `kind='resolve'` run covers. A join, nothing more.

| Field | Type | Constraints | Description |
|---|---|---|---|
| `resolve_run_id` | UUID | FK → DiscoveryRun, required | Must reference a run with `kind='resolve'`. |
| `candidate_work_id` | UUID | FK → CandidateWork, required | |
| | | PK (`resolve_run_id`, `candidate_work_id`) | A work appears at most once per run. |

> **This entity exists because the 2026-07-20 re-search decision was incomplete
> without it** — caught by Critic review, not by the design that introduced the
> gap. Modelling the re-search as a `DiscoveryRun` and deriving its state from the
> run row silently assumed a coverage relation that nothing recorded. Two claims
> depended on it and neither was answerable: constraint 14's double-spend guard had
> no data to evaluate, on the only tool that spends money; and the CandidateWork
> table's "re-search in flight ⇒ an active resolve run *covering this work*" could
> not be computed. `art_discovery(action='status')` on a resolve run also had no way
> to say which works it was resolving.
>
> **It is a join, deliberately, and not a `resolve_run_id` column on CandidateWork.**
> A nullable column on the work would be a second copy of status living beside the
> run row — precisely the stored-truth-that-can-drift the readiness decision
> rejects, and it would lose the history of earlier resolve attempts. A join records
> a *fact about the run's scope*, which does not change when the run's status does.
>
> Constraint 14 is enforced against this table: at creation, a resolve run is
> refused if any requested work already appears in a `ResolveRunWork` row whose run
> is still `resolving_images`.

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
- A **DiscoveryRun** with `kind='resolve'` **covers** many **CandidateWorks**
  (many-to-many via **ResolveRunWork**), and a work may be covered by many resolve
  runs over its life — but by at most one *active* run at a time (constraint 14).
  This is a different relation from the one above: `CandidateWork.discovery_run_id`
  records which run **proposed** the work and is its provenance (**Q5**); coverage
  records which run is **re-searching** it. Overloading provenance to mean coverage
  would destroy the provenance, and `parent_run_id` cannot serve either, because a
  resolve run covers a *subset* of the parent's works.
- A **DiscoveryRun** accrues many **SpendRecords** (one-to-many).
- The **Directive** singleton may reference one **Artwork** as its pin. It belongs
  to the catalogue rather than to any Theme, so that switching themes carries the
  sequence forward instead of resetting it.
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
  its mat history. If the work is the **Directive**'s pin, archiving withdraws
  the pin; that rule and its reasoning live with the Directive entity and are
  deliberately not restated here.
- `archived → accepted` — restoration is permitted; renditions may be stale and
  are checked via `source_content_hash`.

Rejection has no Artwork state: a rejected work never becomes one. Suppression of
re-proposal is `CandidateWork.work_dedup_key` (**Q3**).

### DiscoveryRun

```
kind='discovery':

resolving_works ──┬──────────────────────────▶ resolving_images ──▶ completed
   (phase 1)      │                                (phase 2)
                  └──▶ awaiting_approval ──┬──▶ resolving_images
                                           └──▶ declined

kind='resolve':          (the re-search — phase 2 only)

                                          resolving_images ──▶ completed
                                            (entry state)

{resolving_works, resolving_images} ──┬──▶ failed
                                      ├──▶ halted_by_budget
                                      └──▶ interrupted   (curation startup reconciliation)

any of {resolving_works, awaiting_approval, resolving_images} ──▶ cancelled
```

**`failed` and `halted_by_budget` are drawn from both working states, not only
from phase 2 (corrected 2026-07-27, when the machine was first implemented).**
Phase 1 makes model calls and can search the web, so it both spends and can
break; drawing these only from `resolving_images` left the run that actually
broke during phase 1 with no ending that says so. They are refused from
`awaiting_approval`, which is the other half of the same rule: nothing is
executing there, so neither ending would be describing something that happened.
`cancelled` stays available from all three, because a curator looking at a work
list may simply want the run gone — which is a different act from declining it.

The three groupings above are not cosmetic. **A run can end by breaking, by being
refused credit, or by having its process stopped exactly when it is the process
doing the work** — which is why those three share a source set, and why
`awaiting_approval` is in none of them.

**Runs left in a PROCESS-HELD state are reconciled to `interrupted` when the
curation plane starts (added 2026-07-20; scope corrected same day).** Without this,
the state machine had no edge for *process death* — every one of its terminal states
required the run's own process to write it, which a crashed process by definition
cannot do.

> **`awaiting_approval` is deliberately excluded, and getting this wrong was the
> first version of this fix.** The justification for reconciliation is that a run
> only advances while the process that owns it is alive — which is true of
> `resolving_works` and `resolving_images` and **false** of `awaiting_approval`.
> That state advances when the *curator* calls `approve`; it is durable, human-held
> state that is *supposed* to outlive a restart. Reconciling it would let a
> `systemctl restart` — the documented deploy step — silently destroy a pending
> decision along with the phase-1 spend already incurred to produce it, and curation
> is restarted constantly during development. A rule justified by process liveness
> must apply only to states process liveness actually governs.
>
> Nothing else depends on the wider scope: a `resolve` run can never enter
> `awaiting_approval`, so coverage release and constraint 14 are unaffected.

Reconciliation logs one WARNING per run it moves, carrying the run id and prior
status — see `observability-strategy.md` § What Each Failure Looks Like. That line
is the *only* signal a run died, because the dying process cannot report its own
death.

**This was a real defect and it was self-inflicted.** The re-search decision
rejected a stored `resolving` verdict on the grounds that "a crashed resolve run
would leave the work reading `resolving` forever with nothing to correct it" — then
moved the truth to the run row without re-asking that question of the run row. The
defect moved with it, and got worse: combined with constraint 14, a crash left the
covered works **permanently un-re-searchable**, silently, on the only tool that
spends money. The curation unit's `MemoryMax` exists precisely to cause OOM kills,
and a deploy is `systemctl restart` — so this is routine, not exotic.

**Why startup reconciliation rather than timeouts or heartbeats:** a run in a
process-held state only advances while the curation process that owns it is alive,
and there is exactly one such process (one systemd unit). If curation is starting,
no previously-recorded run is running, so the inference is total rather than
heuristic — no timer to tune, no liveness field to keep fresh, and nothing that can
be wrong.

**`interrupted` is its own terminal state, not a flavour of `failed`.** The rule
below — each terminal state describes a different thing and none may absorb
another — applies to this one too. "The process was stopped underneath it" and
"something broke" call for different operator responses: an interrupted run is
simply re-run, a failed one is investigated. Folding them together would need a
free-text reason field to tell them apart again, which is the absorption the rule
exists to prevent.

`interrupted` is terminal, so reconciliation also releases `ResolveRunWork`
coverage — which is what makes the works re-searchable again.

A `resolve` run enters at `resolving_images` and can never reach `resolving_works`,
`awaiting_approval`, or `declined` — phase 1 already happened on the parent, so
there is no work list to approve or decline. Every other state behaves identically,
which is the point of reusing the entity: `status`, `cancel`, `halted_by_budget`,
and spend attribution all work on a re-search without a line of new machinery.

`cancelled` is reachable from `resolving_works`, `awaiting_approval`, and
`resolving_images` — a run stopped on request while it was working. It is the
terminal state behind `art_discovery(action='cancel')`; a run that spent money
before being cancelled keeps its `actual_cost_usd`, because the spend happened.

**Each terminal state describes a different thing, and none may absorb another.**
`completed` (it finished), `failed` (something broke), `halted_by_budget` (the cap
fired), `declined` (the curator saw the work list and its price and said no),
`cancelled` (stopped on request mid-flight), `interrupted` (the curation process was
stopped underneath it — re-run it, do not investigate it). *(The count is
deliberately not stated: it read "four" while listing five, then "six" while another
sentence still said four. A number that must be maintained in prose gets it wrong.)*
Collapsing any
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
               entered ONLY via art_review(reject_image)
                    │
                    ├──▶ accepted   via set_verdict
                    └──▶ rejected   via set_verdict
```

`awaiting_better_image` is **not terminal**. It returns to `pending` once a
resolution attempt selects a fresh instance, and it must not write
`work_dedup_key` suppression — that is reserved for `rejected` (**Q11**).
**The curator may also leave it directly** via `set_verdict` — accepting the best
instance on offer, or giving up on the work — which is why the two edges above
exist (added 2026-07-20; the diagram previously drew no exit but `set_verdict`
constrains only its *target* value, so the transition was reachable and unmodelled).

**Terminal verdicts are never overwritten by a resolve run (decided 2026-07-20).**
`verdict` has two writers — the curator through `art_review`, and a resolve run
completing — and only the curator's is authoritative. A resolve run writes
`pending` **only if the work is still `awaiting_better_image` when it finishes**;
if the curator has since accepted or rejected it, the run's result is **reported,
not applied**, and the verdict stands. Without this rule a resolve completing after
an accept writes `pending` over `accepted`, leaving a work with an `artwork_id` and
a non-accepted verdict — a combination nothing else in this model can produce or
repair. Constraint 14 does not cover it: that guards resolve-run *creation*, not
the write at completion. Note the guard lives at the completion write, not on
`set_verdict`, which stays available at all times — a curator must never be blocked
on a background job.

**The three situations inside it are distinguished without storing them
(decided 2026-07-20).** The verdict was carrying "not yet re-searched",
"re-search running", and "re-search found nothing" as one indistinguishable
value, so a curator could not tell a pending job from a dead end. The fix is not
more enum values — it is to stop conflating curator *intent* with job *state*:

| Situation | How it is known |
|---|---|
| Curator asked for better; nothing running | `awaiting_better_image`, and no `ResolveRunWork` row for it on a run in `resolving_images` |
| Re-search in flight | A `ResolveRunWork` row for this work whose run is in `resolving_images` |
| Re-search found nothing | `resolution_status = unresolved` — see above |

`awaiting_better_image` therefore means exactly one thing: *the curator wants this
work and the current instance is not good enough*. It is a statement of intent, and
intent does not change when a job starts or finishes.

**This follows the readiness decision rather than re-litigating it.** Storing
"re-search running" as a verdict value would create a second truth beside the run
row, and the two can disagree — a crashed resolve run would leave the work reading
`resolving` forever with nothing to correct it. Derived state cannot drift from the
thing it is derived from. See `architecture.md` § readiness.

**Entry is single-path by construction (decided 2026-07-20).** `set_verdict` does
**not** accept `awaiting_better_image`; `reject_image` is the only way in. Both
previously reached it and only `reject_image` set `rejected_at`, so a re-search
could legitimately return the image the curator had just rejected — the exact
suppression failure **Q11** exists to prevent, reappearing on the instance scope.
Narrowing the entry makes that impossible rather than defended against, and it
matches the scope boundary the tools already have: `awaiting_better_image` is a
judgement about the *instance*, and `set_verdict` is work-scoped.

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
   **(b) is scoped to the URL, not to the row that holds it** *(added 2026-08-03,
   when the re-search was first built and immediately defeated it)*. A work holds
   **at most one instance per `url`**: recording one it already has returns the
   instance already held rather than adding a second. Without that, suppression
   lasts exactly as long as nothing searches again — a re-search re-offering the
   same URL, which is the normal case because museums do not move their images
   between two searches a minute apart, wrote a fresh row with a null
   `rejected_at` and selected it. The curator asked for a better scan and was
   handed back the one they had just turned down, with nothing anywhere recording
   that it was the same image. The rule also retires the duplicate alternate a
   second search would otherwise add to every review card.
8. **Exactly one CandidateImage per CandidateWork has `is_selected = true`**, while
   the work has any unrejected instance **that clears the display floor**. There
   are two selectionless states, not one, and they are different situations for a
   curator:
   - *Every instance rejected.* The work re-enters phase 2 rather than sitting
     selectionless.
   - *Every surviving instance below the floor.* Selection declines them all —
     that is what the floor is for, so nothing under it is ever chosen without
     being asked for. The instances are still shown, still labelled with the size
     they would appear at, and still choosable; what does not happen is an
     automatic choice. **Acceptance is refused until one is chosen explicitly**,
     because promoting with no selection mints an artwork whose every source is
     `is_primary = false` — no record of which scan produced the original, and a
     work on the wall nobody picked.

   > The second state was reachable and undescribed until 2026-08-03: the
   > constraint named only the rejection case, while `selection.best` had declined
   > below-floor instances since the floor was introduced. The guard that now
   > refuses acceptance is what makes the constraint true of the code rather than
   > only of the intent.
9. **A CandidateWork with `resolution_status = unresolved` is never presented as
   accepted-able**, and never silently omitted from the run's results. It is
   reported. **Q12.**
10. **`Artwork.description` may contain only `<i>` and `<b>` markup.** Sources
   return `<p>` and `<em>`; these are normalised at ingest. The label renderer
   passes description text to Pango markup, so unescaped or unexpected markup is
   a rendering failure — today `art.py` does this substitution inline at render
   time, which means every renderer must remember to.
11. **`halted_by_budget` is derived from the provider's refusal, never from a local sum.**
    The ceiling is an OpenRouter per-key credit limit; no application code path
    stands between the product and an unbounded bill (ratified Direction norm,
    `nonfunctional-requirements.md`). `SpendRecord` is attribution and reporting
    only. Where "budget remaining" is shown, it is read from `GET /api/v1/key`
    (`limit_remaining`), which cannot drift from a local tally because it is the
    authority. Reporting windows follow the provider's reset: **midnight UTC**, so
    the month is the UTC calendar month, not the operator's local one.
    *(Amended 2026-07-20 — this constraint previously specified an application-side
    monthly sum, which is exactly the defect the norm was ratified to prevent.)*
12. **An Original's `display_fit` is derived wherever it is needed, from a single
    service-layer function — and is never stored.** *(Amended 2026-07-20; this
    previously required derivation at acquisition and storage on the row.)* The
    verdict depends on panel geometry and mat configuration, both deployment
    values, so a stored verdict is a claim about one specific TV that no longer
    holds when the TV changes — and nothing would report the drift. The original
    intent, "resolution policy in one place rather than implicit in each renderer",
    is now met by the service-layer norm (`architecture.md` § Direction): the review
    grid and the renderer call the same function, and neither has a policy of its
    own.
13. **`Source.rights_status` is recorded for every source, including `unknown`.**
    Absence of a value is not permitted — "we did not check" and "we checked and
    could not tell" are different facts, and only the second is honest as
    `unknown`. **Rights gate nothing (decided 2026-07-20)** — the value is
    display-only, surfaced in the review grid as a *provenance and source-quality*
    signal rather than a legal one, because a holding institution's own
    public-domain scan is usually the authoritative file while unknown-rights
    images are more often downstream reproductions. Private household display keeps
    the legal stakes genuinely low, and the corpus is deliberately in-copyright, so
    a filter would contradict a decision already made. **Reopen if** the product
    gains sharing or export, or the catalogue itself becomes public — those change
    the analysis, and this is recorded so the trigger is recognisable rather than
    rediscovered.
14. **A CandidateWork is covered by at most one active `resolve` run at a time.**
    Coverage is recorded in **ResolveRunWork**; the constraint is enforced at
    run-creation time by checking that table — `resolve_images` refuses any work id
    appearing in a `ResolveRunWork` row whose run is in a **non-terminal** status,
    and names the offending ids in the refusal rather than silently deduplicating.
    Without this, double-submitting the same ids spends twice for one result on the
    only tool that spends money at all.
    **"Non-terminal" is safe to key on only because of startup reconciliation** (see
    State Machines). Every terminal state *except* `interrupted` is written by the
    run's own process — which is precisely why `interrupted` had to exist: without
    it, a crash left no writer for the terminal state, and this constraint would
    refuse those work ids forever. The guard against double-spend must not become a
    permanent block, which is exactly what it was before reconciliation was
    specified.
    *(Corrected 2026-07-27, when this was first implemented.)* This constraint
    previously added: "Note a run sitting at `awaiting_approval` also holds its
    coverage, and that is correct." **It cannot.** Coverage rows name a
    `kind='resolve'` run, and the State Machines section says in as many words
    that a resolve run can never reach `awaiting_approval` — the reconciliation
    note above even relies on that fact to argue coverage release is unaffected.
    So the two halves of this artifact disagreed, and the dead half had reached
    `operational-spec.md` as a remedy telling an operator to approve a run that
    cannot exist. A live coverage-holding run is always `resolving_images`.
15. **`awaiting_better_image` is reachable only through `art_review(reject_image)`.**
    The path that sets `rejected_at` and the path that sets the verdict are the same
    path, so instance suppression can never be skipped. `set_verdict` rejects the
    value with an error naming `reject_image` — see `api-contract.md`.
16. **A re-fetch never lowers the quality of the image a work already holds: a
    `partial_tiles` result does not replace a held Original unless that Original is
    itself recorded as `partial_tiles`.** *(Added 2026-08-04.)* Re-acquisition is an
    ordinary operation the surface actively invites after a partial result, so the
    guarantee a curator needs is that asking again cannot cost them what they have.
    Chunk 18A's staging discipline established half of it — a fetch that *fails*
    replaces nothing — and this is the other half: a fetch that *succeeds partially*
    must not either. Without it `Original.fetch_status` and `Source.last_fetch_status`
    are written and displayed while no decision reads them, and the tool tip on
    `retry_acquisition` promising that a retry is safe is true only for the failure
    case it happens to name.

    **The comparison is quality, not recency, and it is deliberately coarse.** Only
    the complete/partial distinction is read. Pixel count is *not* consulted: a
    complete fetch from a smaller scan is a legitimate re-acquisition — a curator
    switching to a different institution's file — and refusing it would make the
    guard second-guess a choice acceptance already made. Two partials replace each
    other freely, because neither is authoritative and the second may hold more
    tiles; nothing in a tile count is comparable across two runs.

    **A null `fetch_status` counts as complete.** Rows written before the column
    existed cannot be distinguished, and the protective reading costs nothing real:
    a partial replacing an unknown was never an improvement worth having, while the
    permissive reading reintroduces the data loss for exactly the oldest rows.

    A refused promotion is **not** a failed fetch. The staged file is discarded, the
    held original and its `Source` row are untouched, and the result says plainly
    that the work kept the better image it already had — recording it as a failure
    would put a `failed` status on a source that just answered correctly, and send
    whoever read it to a museum that is working.

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
>
> **Where "the global default" lives** *(settled 2026-07-31, at build; this
> artifact named the fallback without saying what supplied it).* It is deployment
> configuration — `ROTATION_INTERVAL_SECONDS` and `ROTATION_SHUFFLE` — defaulting
> to **180 seconds on shuffle**, which is what the 2024 plane runs the wall at
> today. The values are carried forward rather than chosen: the cutover at Chunk
> 13 replaces the machinery, and a wall that silently changed pace on the same
> day would be a regression nobody asked for.
>
> Null is therefore "inherit", never "unset". The distinction is load-bearing in
> two places: the row mapping keeps null as null rather than coercing it, and a
> partial update to a theme leaves an unnamed field alone rather than clearing
> it — otherwise renaming a theme would silently reset its pace.

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
- **`display-state.sqlite` beyond `TvBinding`.** The display plane's other device
  state (last selected work, brightness state, the last-acted-on directive
  sequence) is display-internal, never read by curation, and specified at build
  time. Only `TvBinding` is modelled here, because it is the entity that enforces
  the per-device Direction norm; the rest earns no catalogue-side contract.
  Panel geometry is in neither store — it is configuration both planes read
  (`operational-spec.md` § Configuration).
