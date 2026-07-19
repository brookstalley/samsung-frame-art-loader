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
| Q3 | Has this work already been suggested and rejected, so discovery does not re-surface it? | 2, 3 |
| Q4 | What has been spent this month, and what did this run cost? | 1, 2 |
| Q5 | Where did this candidate come from, and why was it suggested? | 2, 3 |
| Q6 | Can this artwork be re-acquired from scratch if every derived file is lost? | 4 |
| Q7 | What mat colour was chosen for this work, and on what basis? | 4 |
| Q8 | Which renditions exist for which output geometry, and are they current? | 4, 6 |
| Q9 | Who is the artist — name, nationality, dates — for the physical label? | 4 |

**Q3 is the one most easily missed.** Without persisted rejections, every
discovery run re-proposes the same works the curator has already declined, and
the product feels broken in a way no single component is responsible for.

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
| `status` | enum | required | `candidate` \| `accepted` \| `rejected` \| `archived`. See State Machines. |
| `accepted_at` | datetime | nullable | Set on transition to `accepted`. |
| `created_at` | datetime | auto | |

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
| `provider` | enum | required | `artic` \| `google_arts` \| `http` \| other, extensible. |
| `acquisition_method` | enum | required | `dezoomify` \| `direct_http` \| `api`. Determines the fetch path. |
| `is_primary` | boolean | default false | Which source was actually used for the held original. |
| `last_fetch_status` | enum | nullable | `ok` \| `partial_tiles` \| `failed`. `partial_tiles` is a normal dezoomify outcome, not an error. |
| `last_fetched_at` | datetime | nullable | |

> **Q6.** Multiple sources per work is what makes re-acquisition robust when an
> institution reorganises its site.

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

### Rendition

A derived, device-specific output. **Regenerated, never transported.**

| Field | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `artwork_id` | UUID | FK → Artwork, required | |
| `kind` | enum | required | `tv_display` \| `label` \| `thumbnail`. |
| `target_width` | integer | required | e.g. 3840 for TV, 1448 for the 6" HD panel. |
| `target_height` | integer | required | e.g. 2160, 1072. |
| `relative_path` | string | required | Relative to `ART_ROOT`. |
| `source_content_hash` | string | required | The `Original.content_hash` this was rendered from. Mismatch ⇒ stale ⇒ regenerate. |
| `generated_at` | datetime | auto | |

> **Q8.** Geometry is *columns*, not a filename suffix. The 2024 design encoded
> it as `_w648_h480` in the filename, which is why the recovered catalogue points
> at a panel that no longer exists. Carrying `source_content_hash` is what lets
> staleness be detected rather than assumed — the 2024 code cleared TV state
> whenever it regenerated an image, which is the same intent expressed
> imperatively and only at one site.

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
| `status` | enum | required | `estimating` \| `running` \| `completed` \| `failed` \| `halted_by_budget`. |
| `estimated_cost_usd` | decimal | nullable | Shown before the run. |
| `actual_cost_usd` | decimal | nullable | Reconciled after. |
| `started_at`, `completed_at` | datetime | nullable | |

> `halted_by_budget` is a first-class terminal state, not an error. The cap fails
> closed and the curator must be able to see that is what happened.

### Candidate

A work discovery proposed, and the curator's verdict on it. Distinct from
Artwork: most candidates never become artworks.

| Field | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `discovery_run_id` | UUID | FK → DiscoveryRun, required | |
| `artwork_id` | UUID | FK → Artwork, nullable | Set on acceptance. |
| `proposed_title` | string | required | Pre-acquisition; may be wrong. |
| `proposed_artist` | string | nullable | |
| `candidate_url` | string | nullable | Where it was found. |
| `rationale` | text | required | Why the model matched it to the intent. **Q5.** |
| `dedup_key` | string | required, indexed | Normalised identity for cross-run dedup. **Q3.** |
| `verdict` | enum | required | `pending` \| `accepted` \| `rejected`. |
| `rejected_reason` | text | nullable | Optional curator note. |
| `decided_at` | datetime | nullable | |

> **Q3.** `dedup_key` is the field that stops discovery re-proposing declined
> works forever. Its derivation (normalised artist + title, or a source
> identifier where one exists) is a design decision deferred to build — but the
> *column* is specified now because retrofitting dedup after rejections have
> accumulated means the early rejections are unrecoverable.

### SpendRecord

The meter behind the fail-closed cap.

| Field | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `discovery_run_id` | UUID | FK → DiscoveryRun, nullable | Null for non-discovery spend, e.g. mat colour. |
| `artwork_id` | UUID | FK → Artwork, nullable | Set for per-artwork spend. |
| `category` | enum | required | `discovery_tokens` \| `web_search` \| `mat_color_vision`. |
| `model_id` | string | nullable | |
| `input_tokens`, `output_tokens` | integer | nullable | Null where the unit is not tokens. |
| `units` | integer | nullable | e.g. number of web searches. |
| `cost_usd` | decimal | required | What was actually billed. |
| `occurred_at` | datetime | auto, indexed | Indexed — the cap is a time-windowed sum. |

> **Q4.** `category` separates `web_search` because it is billed per search, not
> per token, and may dominate token spend entirely — an unresolved open question.
> A meter that counts only tokens cannot enforce a dollar cap.

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
- A **DiscoveryRun** produces many **Candidates** (one-to-many). A **Candidate**
  becomes at most one **Artwork**.
- A **DiscoveryRun** accrues many **SpendRecords** (one-to-many).
- A **TvBinding** references an **Artwork** across the plane boundary — by id
  only, never by foreign key, because the two planes do not share a database.

## State Machines

### Artwork

```
candidate ──accept──▶ accepted ──archive──▶ archived
    │                     ▲                     │
    └───reject──▶ rejected└──────restore────────┘
```

- `candidate → accepted` — curator accepts; acquisition and preparation begin.
- `candidate → rejected` — terminal for discovery purposes; the `Candidate`'s
  `dedup_key` continues to suppress re-proposal (**Q3**).
- `accepted → archived` — removed from circulation without losing the record or
  its mat history.
- `archived → accepted` — restoration is permitted; renditions may be stale and
  are checked via `source_content_hash`.

### DiscoveryRun

```
estimating ──▶ running ──┬──▶ completed
                         ├──▶ failed
                         └──▶ halted_by_budget
```

All three end states are terminal. `halted_by_budget` is a normal outcome.

### Candidate

```
pending ──┬──▶ accepted   (creates or links an Artwork)
          └──▶ rejected
```

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
7. **A rejected Candidate's `dedup_key` suppresses future proposals** unless the
   curator explicitly reconsiders it.
8. **`Artwork.description` may contain only `<i>` and `<b>` markup.** Sources
   return `<p>` and `<em>`; these are normalised at ingest. The label renderer
   passes description text to Pango markup, so unescaped or unexpected markup is
   a rendering failure — today `art.py` does this substitution inline at render
   time, which means every renderer must remember to.
9. **Spend is summed over a calendar month by `occurred_at`.** When the sum
   reaches the configured ceiling, discovery transitions to `halted_by_budget`
   rather than degrading.

## Deliberately not modelled

- **Users, accounts, roles, sessions.** Single operator; `has_multiple_party_types`
  is false. Adding these later is accommodated by the fact that Theme and
  DiscoveryRun already have owners implicitly (there is one).
- **Slideshow ordering and timing.** Owned by the TV's own art-mode slideshow
  settings, not by this product's data.
- **Agent conversation history.** Agents are stateless across sessions by
  decision; there is no memory to persist.
