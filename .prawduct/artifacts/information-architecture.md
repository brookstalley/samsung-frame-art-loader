---
artifact: information-architecture
version: 1
depends_on:
  - artifact: product-brief
  - artifact: data-model
  - artifact: nonfunctional-requirements
  - artifact: api-contract
last_validated: null
---

# Information Architecture

The curation plane's screen structure, navigation and flows. Authored 2026-08-10,
after the surface had already been built across six chunks — so this artifact is
partly a description of what exists and partly a redesign of it, and every place
those differ is marked **CHANGE** with the reasoning.

## Direction

<!-- Ratified by the owner 2026-08-11. Enforcement row in project-preferences.md. -->

**The curation surface is organised around what a curator does, never around the
pipeline's stages.** Three destinations — the Walls, Collection, Discover — and a
new screen earns a place in that navigation only by being a thing a curator sets
out to do, not by being a subsystem that acquired a UI.

> **Why:** the built surface's five tabs were the pipeline's stages in pipeline
> order, and each one was correct as the chunk that produced it. That is the
> failure mode this norm exists to catch: it is invisible per-chunk and only
> visible in the sum, so no per-chunk review would ever have caught it. A sixth
> subsystem will want a sixth tab for exactly the same locally-good reasons.
>
> **Enforcement is judgment (Critic), not a test.** The violation is a
> destination that names a stage rather than an intention, which has no import
> signature and no grep.
>
> **Status:** steady-state. Ratified by the owner 2026-08-11, together with the
> token norm in `design-direction.md`.
>
> **Retroactivity:** the built surface does **not** conform — five tabs named for
> pipeline stages — and this artifact is the plan for making it do so. The norm was
> ratified in that state deliberately: it binds the work that reshapes the surface,
> and a norm written only after the code already agreed with it would have bound
> nothing. No code changed on the commit that introduced it.

**A working prototype of everything below is committed beside this file:**
`prototypes/curation-ia-prototype.html` — one self-contained page, no build step,
opened directly in a browser. It carries a synthetic 2,000-work corpus because
every scale claim here is unfalsifiable against the real 41. It is a **design
deliverable, not a component**: it shares the product's tokens deliberately, but
nothing in `curation/` imports from it and it ships to no one.

## The problem this artifact was written to fix

The built surface has five equal tabs — Works, Discovery, Themes, On the wall,
Health. Those are **the pipeline's internal stages**, in pipeline order. They were
each correct as the chunk that produced them, and the sum is an interface organised
around how the software works rather than around what a curator does.

Three symptoms, each traceable to that:

- **Themes are a separate destination from the collection they select from.** A
  curator organising work sees the collection in one tab and the organisation of it
  in another, and must hold the mapping in their head.
- **Health is a peer of the art.** An appliance-status panel sits at the same rank
  as the catalogue, in a product whose stated identity is "museum, not gadget".
- **The wall is fourth.** The thing the entire product exists to produce is the
  fourth item in the navigation, behind three tabs about producing it.

## Screen Inventory

Priority is **core** (on a stated core flow) or **supporting**.

| Screen | Purpose | Entry points | Priority |
|---|---|---|---|
| **The Walls** | What is hanging right now on each display, the theme it is drawn from, and what is next. The product's home. | Launch; masthead brand; after activating a theme | core (flow 6) |
| **Collection** | Everything acquired. Find, sort, filter, group, organise into themes, remove. | Primary nav; search from anywhere; from a theme; after a run's accepted works land | core (flows 3, 5) |
| **Work** | One work at full size, with its sources, renditions, mat history and theme membership. | A tile in Collection; a tile on a Wall; a row in Review | core (flows 4, 5) |
| **Discover** | Conversation, the runs it seeds, and the review of what they return — one continuous place. | Primary nav; "find something new" on the Walls and on an empty Collection | core (flows 1, 2, 3) |
| **Review** | Judging one run's candidates: accept, reject, choose a scan, ask for a better one. | A completed run in Discover; the run's own notification | core (flow 3) |
| **Theme** | One theme: its members in curated order, its name, and the act of hanging it. | Collection's theme rail; a wall's theme control | core (flows 5, 6) |
| **Health** | The three observations the panel states, and the spend record. | The masthead status indicator; a failure's own link | supporting |
| **Conversation** *(new)* | One intent-forming thread, its samples, and what it committed to. | Discover; the conversation list; an affinity's provenance | core (flow 1) |
| **Taste** *(new)* | The affinities the product has accumulated, with their derivation, correctable. | Discover; a suggestion's "why am I seeing this?" | supporting |

**Nine screens, one of which (Health) is reachable but not navigable-to.** Two are
new and exist only because conversational intent-forming does
(`product-brief.md` flow 1, amended 2026-08-10).

**CHANGE — Themes stops being a top-level screen.** A theme is a *saved selection
over the collection*, not a parallel noun, and the built surface's own routes say
so: every theme operation is membership and order over works. Promoting it to a
peer of the collection is what forces the curator to hold a mapping in their head.
It becomes a rail inside Collection — a filter that is also editable — plus a
**Theme** screen for the one thing that genuinely is its own act: hanging it.

## Navigation Structure

**Primary pattern: three destinations, flat.** No hierarchy above them, no drawer,
no nesting.

```
  The Walls  ·  Collection  ·  Discover                   [status] [search]
```

- **Persistent:** the three destinations, a status indicator, and a search
  affordance. Search is persistent because at thousands of works it is the primary
  retrieval mechanism, and a retrieval mechanism you must first navigate to is one
  more step on the most frequent action.
- **Contextual:** everything else. Theme, Work, Review, Conversation and Taste are
  reached *from* a destination and return to it.
- **Health is not in the navigation.** It is a status indicator in the masthead
  that reads "well" or names what is wrong, and expands to the Health screen. This
  is the demotion the "museum, not gadget" identity asks for, and it is safe
  **only because the indicator is always present and speaks up** — a status surface
  you must remember to visit is worse than one in the nav. The indicator is the
  contract; the tab was merely the location.

**Back/escape.** Every contextual screen returns to the destination it was opened
from, not to a fixed parent — a Work opened from Review returns to Review, the same
Work opened from Collection returns to Collection with scroll position intact.
Browser back does this natively if each is a real URL, which is the reason they are.

**URLs.** Every screen and every consequential state (a search query, an active
filter set, a run, a conversation) is addressable. The built client already routes
on the hash; this keeps that property and extends it to search and filter state, so
a curator can bookmark "unmatted works by Kandinsky" and an agent can link to one.

> **The counter-argument to the Walls as home, recorded because it is real.** Most
> sessions begin with an *intention* — find something, organise something — and
> opening on a screen that mostly shows pictures puts a click in front of every
> such session. Two things answer it: the Walls screen carries the live entry
> points (search, "find something new", the theme control) rather than being a dead
> end, and the product's identity claim is that it is a collection rather than a
> tool. If the click proves to cost more than the orientation is worth, the fix is
> to make the entry points better, not to open on a grid. **Revisit trigger:** the
> operator reports routinely skipping past it.

## More than one wall

The operator stated on 2026-08-10 that multiple displays are coming soon. Nothing
here builds for them; what this section does is fix the **shape** now, while the
shape is still free to choose, and name what genuinely blocks the extension so it
is found in a plan rather than in a chunk.

**The governing rule: one wall is the degenerate case of many, never a special
case.** The screen is "The Walls" from the outset. With one display it shows one
wall filling the screen and reads exactly as a single-wall home would; with three
it shows three. There is no single-wall layout that a second display replaces —
which is what stops the extension from being a rewrite of the product's home.

Three consequences, all cheap to honour now and expensive to retrofit:

- **Every act that changes a wall names which wall**, in its control and in its
  confirmation, even when there is one and the answer is obvious. "Hang Winter"
  becomes "Hang Winter in the living room". A confirmation that reads correctly
  today only because there is one possible target is a sentence that silently
  becomes wrong.
- **Health is per-device and already nearly is.** The masthead indicator
  aggregates — "well", or "the study panel has not reported since 09:14" — so it
  gains a device dimension rather than a new design.
- **A theme is not owned by a wall.** Themes stay collection-scoped; *hanging* is
  the per-wall act. Two walls may hang the same theme, and that must not require
  duplicating it.

### Two structural blockers, found 2026-08-10 and not fixed here

Both are in `data-model.md` and both need a decision before multi-display is
planned. Recorded here because an interface designed against them unknowingly is
the expensive kind of wrong.

- **`TvBinding.artwork_id` is `required, unique`** — one row per artwork across the
  whole installation. Two televisions showing the same work each need their own
  `tv_content_id`, which the uniqueness constraint forbids. The entity is
  per-television by its own docstring but carries no device identifier; the key
  almost certainly becomes (`device_id`, `artwork_id`).
- **Constraint 1 — "Exactly one Theme has `is_active = true`."** This is the
  single-wall assumption stated as an invariant. It becomes one active theme *per
  wall*, which moves activation off `Theme` and onto the binding between a theme
  and a device.

Neither changes anything in this artifact's layouts. Both change the routes beneath
them: `POST /api/themes/{id}/activate` and `GET /api/manifest` are today
installation-wide and become per-wall.

## Retrieval: search and facets

The amendment to `nonfunctional-requirements.md` made search mandatory rather than
optional. This section states what it has to do, and one thing it currently
*cannot*.

### A control never offers a dead end

**Facet options are derived from the current result set, carry their counts, and a
zero-count option is disabled.** The first prototype offered Movement and Era as
independent lists, which let a curator select "Colour Field" and "1920s" — a
combination that cannot exist — and get an empty grid with no explanation. A filter
that promises results it cannot produce is worse than no filter: it teaches the
curator that the collection is smaller than it is.

Three rules make that hold:

- **Each facet's counts are computed over the results filtered by every *other*
  facet, never by its own.** Including its own collapses the control to the single
  value already chosen, so the curator cannot change their mind without first
  clearing.
- **A zero option is disabled, not hidden.** Hiding it makes the vocabulary appear
  to shrink, which reads as data loss rather than as an empty intersection.
- **Counts are shown.** "Baroque (51)" is the difference between a filter and a
  guess, and at thousands of works it is how a curator decides where to look.

### The vocabulary has more than one axis

The operator's own list — "baroque, pointilism, street art, architecture,
impressionism" — mixes three kinds of thing, and that is evidence rather than
carelessness:

| Named | Actually |
|---|---|
| Baroque, Impressionism, Street art | **movement** — a school, with a period |
| Pointillism | **technique** — a method, used within a movement |
| Architecture | **subject** — what the work depicts |

A single flat "movement" facet forces all three into one list, where they read as
alternatives to each other and their counts become meaningless. **The facet
vocabulary is therefore typed, and it should be the same typed vocabulary
`Affinity.kind` already uses** — `artist`, `movement`, `era`, `subject`, `medium`,
`palette`. One vocabulary then serves three purposes: what a work *is*, what the
curator *likes*, and what discovery *weights*. Two vocabularies for the same idea
is the drift to avoid.

**A movement also implies its period.** Selecting Baroque should narrow Era to the
17th and 18th centuries automatically, because that is a fact about the world and
not a preference. This falls out of derived facets rather than needing its own
rule — but only if the underlying data actually carries both.

### The fields did not exist, and now have a home

**`Artwork` has no `movement`, no `subject` and no period.** It carries `title`,
`artist_id`, `date_created`, `medium`, `dimensions`, `description`, `rights` and
`status`. The first version of this section was designed against fields the
catalogue does not have — recorded rather than quietly fixed, because it is the
failure this artifact exists to prevent.

**Resolved 2026-08-10: `WorkFacet`** (`data-model.md`), carrying `kind`, `value`
and a required `derivation` of `sourced` or `inferred`. It uses **the same typed
vocabulary as `Affinity.kind`**, which is what lets the collection be filtered and
the curator's taste be matched against it in one set of terms.

Two consequences the interface must show rather than hide:

- **Most facets are `inferred`, and the marking is therefore inverted.**
  `curation/src/curation/discovery/browse.py` records that for the wired collection
  "style, classification and period were measured missing on ordinary spellings",
  and the recorded field inventory has no style field at all. The operator's
  direction is to lean on model inference rather than accept that coverage — so
  inferred is the *rule*, and **the screen states the default once, as a footnote,
  and marks only the exception — with a tick, not a word.** A first draft badged
  every inferred row, which is the failure mode to avoid: a label on almost
  everything is a label nobody reads, and it buried the rare sourced value that
  actually carries authority.

  **Two corrections followed from the same instinct, and they generalise.** The
  bordered word "sourced" was louder than the value it qualified — an annotation
  must not outrank its subject — so it became a tick, with the word kept for
  assistive technology so neither colour nor shape is the sole carrier. And the
  sentence explaining the default sat *above* the facts, where a rule that holds
  for every work outranked the facts particular to this one; it belongs below them,
  where a museum label puts its qualifications.
- **Era is a derived, lossy reading that sits beside `date_created`, never over
  it.** The free text stays the evidence; the facet is only the index. A work shown
  as "Late 19th c." must still show "1888–89" on its own screen.

## User Flows

Each core flow from the Product Brief, traced through screens. A flow that cannot
be traced means the inventory is wrong.

### Flow 1 — Express curatorial intent *(rewritten 2026-08-10)*

`The Walls → Discover → Conversation → [commit] → Conversation (run inline)`

1. Curator opens Discover and types, or picks up an existing thread.
2. Each turn answers from model knowledge and shows a few sample pictures. Reactions
   are captured both in prose and by direct control on each sample — a sample
   carries "more like this" / "not this" / "tell me more", which is what writes an
   `Affinity` with `derivation='stated'` rather than making the model infer one.
   A fourth control, **"go to <artist>'s work"**, is kept visually apart from those
   three because it is a different kind of act: the reactions record taste and stay
   in the thread; this one leaves it, filtering Collection to that artist.

   > **Where it lands is the interesting part, and it is usually nowhere.** The
   > artists a conversation surfaces are by definition ones the curator could not
   > have named, so the overwhelmingly common outcome is a collection holding
   > nothing by them. Reporting that as "nothing matches these filters" would be
   > true and useless. The artist-filtered empty state therefore says so plainly —
   > *"Nothing by Wassily Kandinsky yet"* — states that this is normal rather than
   > broken, and offers the search. **This is a third empty state for Collection,
   > not a variant of the other two**, and it is the one the conversation makes
   > common.
3. When a direction firms up, the system offers it as a **commit card** in the
   thread: what would be searched, how many works, what it would cost.
4. Committing starts a `DiscoveryRun`. **The curator does not leave the
   conversation.**

> **The seam is the flow's hard requirement, not a polish item.** The commit card
> *becomes* the run's progress card in place, and then becomes "12 works ready to
> review", which opens Review. The transcript stays above it the whole time. A
> commit that navigates away turns the conversation into a wizard wearing a
> costume — the risk `product-brief.md` flow 1 names — and the in-place transform
> is this artifact's answer to it. Anything that breaks the transform breaks the
> flow.

### Flow 2 — Discovery

`Conversation (commit) or Discover (direct intent) → run → Review`

Unchanged from the built behaviour, and deliberately so: two phases, an estimate
against a real work list once phase 1 settles, a trimmable list, then phase 2.
Conversation is one of two ways in; the direct intent box is the other and does not
go away, because a curator who already knows what to ask for should not have to
chat their way to it.

### Flow 3 — Review and accept

`Review (grid of candidates) → Work or the card's own alternates → verdict`

Judging is the product's highest-stakes screen: accepting spends money and
acquires, rejecting suppresses a work from future runs (Q3). Both are consequential
and neither is fully reversible, which drives two rules:

- **No gesture-based judging**, on any viewport. No swipe-to-accept, no
  swipe-to-reject. Verdicts are explicit, labelled controls.
- **The picture is the evidence and gets the space.** Every other element on a
  candidate card yields to it.

### Flow 5 — Organise into themes

`Collection → select → add to theme` *(and)* `Collection → theme rail → Theme → reorder`

**CHANGE — organising happens in the collection, against the works being
organised.** The theme rail filters the grid to a theme's members; membership is
edited from the grid, in place, with multi-select. Reordering — which is genuinely
about the theme rather than about the works — happens on the Theme screen.

### Flow 6 — Display and sync

`The Walls → a wall's theme control → activate` *(or)* `Theme → hang this`

Activation is the one act in the product that changes what other people in the
house see. It gets a confirmation that names the consequence in those terms, and
the wall repaints from the published manifest rather than from optimism.

## Information Hierarchy

The governing rule, inherited from `product-brief.md` § Identity: **the artwork is
the primary content on every screen that shows one, and chrome yields to it.** What
follows applies it per screen.

| Screen | Primary | Secondary | Actions | Status |
|---|---|---|---|---|
| The Walls | Each wall's hanging work, large | Title, artist, theme, which wall | Change theme, next, open work | Panel + TV health, quietly |
| Collection | The grid of images | Counts, active filters | Search, filter, select, add to theme, remove | Total, and what is filtered out |
| Work | The image at full size | Artist, facets, mat colour, rendition size | Theme membership, re-mat, remove | Fit verdict, image state |
| Discover | The conversation, or the run list | Samples inline | Type, react, commit, start direct | Run progress, spend |
| Review | The candidate picture | Title, artist, size on this wall | Accept, reject, choose scan, ask better | Verdict, provenance, resolution |
| Theme | Members in wall order | Name, count | Reorder, rename, hang, delete | Whether it is the active theme |
| Health | The three observations | Spend history | — | The whole screen is status |

**"Remove" is the wrong word on both rows above, and the control must not use
it.** `Artwork.status` is `accepted` or `archived` and restoration is permitted —
there is no delete in this product, and `api-contract.md` § The routes the
interface design requires records why a delete route was not written. A button
labelled *Remove* promises the work is gone; the work is in fact still catalogued,
still restorable, and merely out of circulation. The label is **Archive**, its
undo is **Restore**, and the confirmation says which of the two it is doing. This
matters beyond wording: a curator who believes removal is destructive will
hesitate over an action that is cheap and reversible, and one who discovers the
work is still there will trust the next confirmation less.

**A screen states a fact once.** The Work screen carried the movement twice — as an
eyebrow above the title and as a row in the facts list three lines below — which
is not merely redundant: two copies of one fact invite the reader to look for the
difference between them, and one of the two will eventually be the one that goes
stale. Where a fact has a labelled home, that is its only home; the eyebrow slot is
for something the labelled list does not carry, or it is empty.

**An annotation must not outrank its subject.** A qualifier — a provenance mark, a
derivation note, a count — is read *after* the value it qualifies and should be
quieter than it. Where the qualifier applies to every row, it is a footnote under
the block rather than a mark on each row.

**What is recorded and what is shown are different questions**, and the Work screen
answers the second. Two consequences, decided 2026-08-10:

- **The mat shows its colour and nothing else.** `MatColor` keeps the method and
  the date it was derived, and must — that record exists so "the new model picked a
  worse colour" stays answerable and reversible, and because the engine's silent
  fallback to a darkened dominant colour would otherwise be invisible in the data.
  But that is a *diagnostic* question asked rarely, and putting its answer on every
  work's label is putting the audit trail where the label goes. **Nothing here
  reduces what is stored.**
- **Label geometry is not shown, because it is not a property of the work.**
  `data-model.md` already settles this — "panel geometry is in neither store; it is
  configuration both planes read" — and a label is rendered to whatever panel is
  asking, whenever it asks. A per-work label resolution was a fact this artifact
  invented, and it contradicted a recorded decision. Only the artwork rendition,
  which *is* a per-work artefact, remains.

**Density is a control, not a decision, and this is what makes Collection work at
thousands.** Two modes:

- **Contact sheet** — image only, uniform tiles, metadata on hover and on focus.
  The default above a few hundred works, because per-tile chrome that reads as
  informative at 41 reads as noise at 4,000 and actively competes with the art.
- **Catalogue** — the built card: image, title, artist, badges. The default below
  that threshold, and always available above it.

The mode is remembered and is part of the addressable state.

## Screen States

Empty, loading, populated, error — assessed for every screen, because the built
surface has good error handling (`role="alert"`, announced not merely coloured) and
almost no considered empty states.

| Screen | Empty | Loading | Error |
|---|---|---|---|
| The Walls | Nothing hanging on a wall: name the reason (no active theme / empty theme / display plane silent) and offer the fix for that reason specifically | The frame, then the image | Cannot reach the display plane — say which of the two planes answered |
| Collection | **Three different empties.** No works at all → an invitation into Discover. No works *matching the filter* → the filter, and how to clear it. **Filtered to one artist and holding none of them** → say so as a normal state and offer the search (see flow 1). Conflating the first two tells a curator with 3,000 works that they own nothing; conflating the third with the second reports the expected result of following a suggestion as a failed query | Skeleton tiles at the grid's real geometry, so nothing reflows | Partial page: show what arrived and say what did not |
| Work | n/a | Image placeholder at the work's own aspect ratio | Named per missing part — a work with no rendition is not a failed page |
| Discover | No conversations and no runs → the intent box, prominent, with two or three worked examples | Per-turn, in the thread | A failed turn stays in the thread and is retryable; it never silently vanishes |
| Review | No candidates: which of the four kinds of nothing (Q12) | Per-card | Per-card, so one bad candidate does not blank the grid |
| Theme | A theme with no members → how to add from Collection | Skeleton rows | Inline |
| Taste | No affinities yet → what would create some | — | Inline |

**The loading state's job is to not move.** Skeletons occupy the final geometry.
The built client has already been bitten by layout that reflows as images arrive
(`project-preferences.md`, the browser-suite row — every image tile taking the
shape of its own picture), and a grid
of art that jumps while it loads is the opposite of the identity.

**One state rule that is not in the table:** a poll must never move focus. This is
a recorded defect from the built surface (`project-preferences.md`, the
browser-suite row; also in `change-log.md`) — a two-second poll stole focus on the one
screen with a decision on it — and it binds every live region here, of which this
design adds several.

## Boundaries

What this interface does **not** include, stated so the absences read as decisions:

- **No accounts, login, roles, or sharing.** One operator (`data-model.md`).
- **No editing of artwork metadata.** Titles, artists and dates come from the
  source and are the label's evidence; a free-text override would make the physical
  label unfalsifiable against the collection it cites.
- **No in-browser image editing** — no crop, no colour adjustment, no manual mat
  override beyond re-deriving it. The mat engine is the product's hardest-won logic
  and a hand-placed mat would have no recorded basis.
- **No mobile-native app.** Responsive web only.
- **No TV-facing or panel-facing screen here.** Those surfaces have no interface by
  requirement — they are the artwork and the label.
- **No onboarding flow.** A single expert operator who built the thing; a first-run
  wizard would be the condescension `product-brief.md` warns against. The empty
  states carry the work an onboarding flow would otherwise do.
- **No offline mode.** The curation plane is a loopback service on the same Pi.

## Status — what this artifact is waiting on

Recorded here rather than only in a session handoff file, because a handoff file is
session-scoped and these obligations are not. **No build plan references this
artifact yet**, and that is deliberate: `build-plan.md` is live with Chunk 13A
waiting on hardware, so the work here belongs in a scope-named
`build-plan-curation-ux.md` that is written once 13A resolves. Until someone writes
it, this list is the only durable record that the round left debts.

| What | Owed to | State |
|---|---|---|
| The routes this design needs: text search and facet counts, theme rename and delete, work **archive** (not delete), the conversation surface, the taste surface | `api-contract.md` | **Amended 2026-08-11** — § The routes the interface design requires. The set and the rules are fixed; field-level shapes belong to the chunk that builds each. Two decisions there are owed to the operator, not to the builder: whether deleting an active theme refuses or cascades, and whether taste earns an MCP tool |
| `accessibility-spec.md` | the human-interface artifact set | **Written 2026-08-11.** It is *not* the browser-only codification this row used to describe — `design_decisions.accessibility_approach` records two surfaces with different profiles and says the important one is the physical label, so a spec scoped to this artifact's screens would have covered the lesser half |
| The revised palettes | `app.css` and `test_design_tokens.py` | Proposed only. Live in the prototype and are ungoverned until they land |
| Conversation deletion's effect on derived affinities | `security-model.md` | Tracked as **issue #118** (`stage: requirements`) — the rule has to be written before anything builds deletion |
| Multi-display: `TvBinding.artwork_id` uniqueness, and one-active-theme-per-wall | `data-model.md` | Named in § More than one wall. Blocks planning, not this design |

## Open questions

- **Deleting a conversation must have a stated effect on the affinities derived
  from it**, and neither this artifact nor `security-model.md` states it yet. Three
  candidate rules: orphan them (keep the judgment, lose the provenance), delete
  them with the thread, or refuse the delete while they are cited. **Tracked as
  issue #118**, at `stage: requirements` — the rule is the work; building deletion
  is a later chunk. The sharp half is `Affinity.source_turn_id`: deletion has an
  unstated effect on judgments the product still consults.
- **The threshold at which Collection defaults to contact sheet** is written above
  as "a few hundred" and is a guess. It should be set from the first real
  thousands-scale corpus, not now.
- **Whether Review needs its own density control.** Judging wants maximum picture;
  a run of 40 wants an overview. Deferred until a run is large enough to hurt.
