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
| `provider` | string | required | e.g. `artic`, `google_arts`, `gallery_site`, `prize_site`, `artist_portfolio`, `http`. Open vocabulary — the contemporary web has no fixed provider list. |
| `source_class` | enum | required | `institutional` \| `contemporary_web`. The load-bearing distinction; see below. |
| `acquisition_method` | enum | required | `dezoomify` \| `direct_http` \| `api`. Determines the fetch path. |
| `rights_status` | enum | required | `public_domain` \| `in_copyright` \| `unknown`. |
| `is_primary` | boolean | default false | Which source was actually used for the held original. |
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
>
> **A run produces one batch, reviewed as a grid** (decided 2026-07-19). The run
> completes, then the curator reviews its candidates together and accepts or
> rejects in bulk. This is why `estimated_cost_usd` is meaningful: a batch run has
> a knowable scope to estimate, which an open-ended iterative conversation would
> not. It also matches the "short curation sessions" constraint — the curator is
> not held at the keyboard while discovery works.
>
> `target_candidate_count` is deliberately **not** modelled as a column yet: it is
> unclear whether the curator sets it per run, whether it is a global preference,
> or whether the agent decides based on how much matches the intent. That is a
> design question, and guessing it into the schema now would be a lock-in without
> a requirement behind it.

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
| `source_class` | enum | nullable | `institutional` \| `contemporary_web`, where determinable pre-acquisition. |
| `estimated_max_width` | integer | nullable | Best pre-acquisition guess at available resolution. |
| `rights_status` | enum | nullable | `public_domain` \| `in_copyright` \| `unknown`. |
| `verdict` | enum | required | `pending` \| `accepted` \| `rejected`. |
| `rejected_reason` | text | nullable | Optional curator note. |
| `decided_at` | datetime | nullable | |

> The three nullable signal fields exist so the **review grid can show resolution
> and rights before acceptance**, not after. Accepting a work triggers a slow,
> possibly expensive acquisition; discovering only then that it is a 900px
> in-copyright press photo wastes the fetch and the curator's attention. They are
> nullable because they are estimates — some sources will not reveal available
> resolution without fetching.

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
10. **An Original's `display_fit` is derived at acquisition, never at render
    time.** Render paths read it; they do not recompute it. This keeps the
    resolution policy in one place instead of implicit in each renderer.
11. **`Source.rights_status` is recorded for every source, including `unknown`.**
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
3. **The display plane resolves** active Theme → ThemeMembership → Artwork →
   TvBinding.`tv_content_id`, then rotates over that id list.

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
