---
artifact: build-plan
version: 1
scope: curation-ux
depends_on:
  - artifact: information-architecture
  - artifact: design-direction
  - artifact: accessibility-spec
  - artifact: api-contract
  - artifact: data-model
  - artifact: architecture
  - artifact: security-model
  - artifact: nonfunctional-requirements
  - artifact: project-preferences
governed_by:
  - artifact: information-architecture
    dispositions:
      - "the curation surface is organised around what a curator does, never around the pipeline's stages → applies, and this plan IS the conformance. The norm was ratified 2026-08-11 against a surface that does not conform — five tabs named for pipeline stages — precisely so it would bind this work. Chunk 04 is where the departure ends; every chunk after it adds screens to the three destinations rather than beside them"
  - artifact: design-direction
    dispositions:
      - "the stylesheet is the source of truth for token values, and the artifact is the source of truth for the rules about them → conforms: Chunk 03 lands the revised palette in `app.css` and nowhere else, and `curation/tests/unit/test_design_tokens.py` — which refuses any colour written outside the token blocks — is the gate it has to pass. No chunk restates a hex value in prose"
  - artifact: accessibility-spec
    dispositions:
      - "WCAG 2.1 AA on the curation browser, and colour is never the sole carrier of state → applies to every screen chunk here, and this is the plan the norm was waiting for. `build-plan.md` recorded it `inapplicable` on the grounds that its remaining chunks render no browser screen; that reasoning does not survive contact with this plan. Each screen chunk carries the contrast pairs through `test_design_tokens.py` and the state-carrier rule through its own tests — the facet rail's disabled options and the Walls health indicator are the two places a first draft would reach for colour alone"
      - "the e-paper label is legible at standing distance → inapplicable because: no chunk here renders a label or touches the display plane's typesetting. Chunk 02 crosses the plane boundary, and it moves the manifest's *file layout* without touching a label field"
  - artifact: data-model
    dispositions:
      - "identity is never a source URL → conforms: no chunk introduces an identity, and `WorkFacet` (Chunk 06) keys on (`kind`, `value`) over an Artwork's own UUID"
      - "a work is distinct from an image of it, at every stage → conforms: the Collection grid and the Work screen both render an Artwork and reach its Renditions through it; no chunk collapses the two"
      - "per-device runtime state never lives in the catalogue → **RULING, recorded 2026-08-12 at `data-model.md` § Wall.** Chunk 01 puts a `Wall` entity in the catalogue, and the norm has to be engaged rather than assumed past. The ruling is that a wall is a *place* with a *name* — a curatorial fact — and that geometry, network address, panel model, TV content ids, upload state and heartbeat are all forbidden on it, permanently. Which device serves a wall stays display-plane configuration. The test the norm cares about — can the catalogue be rebuilt without one television's state — is better answered after this chunk than before it, because a wall now outlives the set that hangs on it"
      - "derived artifacts are regenerated, never transported → conforms: Chunk 02 changes which manifest a display reads, not whether renditions travel; nothing here syncs a rendered file"
  - artifact: architecture
    dispositions:
      - "the theme manifest file is the only channel from curation to display → conforms, and Chunk 02 is the chunk that could most easily have broken it. Per-wall manifests are still files in ART_ROOT written by curation and read by display; the count changes and the direction does not. The alternative shapes a builder might reach for — a per-wall command socket, or curation asking a display which wall it is — are both excluded by this norm and named in the chunk so they are not rediscovered"
      - "a display device renders its own label, and the label travels as metadata → conforms: Chunk 02 moves label fields between files without reading or styling one"
      - "operation logic lives only in the service layer; MCP tools and HTTP handlers are thin bindings → conforms: every route in this plan binds a service method. The wall parameter added in Chunk 01 is threaded through the binding, and the refusal logic it guards (`delete_theme` generalised to 'hung on any wall') stays in `DisplayService`"
  - artifact: nonfunctional-requirements
    dispositions:
      - "spend ceilings are enforced by the provider, never by application code → conforms: Chunk 10 is the only chunk that spends, it writes `SpendRecord` rows with category `conversation_tokens`, and it builds no application-side ceiling"
      - "the display plane's ability to show art never depends on the curation plane being reachable → conforms: Chunk 02 keeps display reading its wall's last manifest forever if curation dies, which is the same posture as today with a narrower file"
  - artifact: project-preferences
    dispositions:
      - "the mechanical norm-index rows (formatting, naming, imports, logging-not-print, type-annotate-on-touch, specific exceptions, no hardcoded deployment values) → conforms: ruff and black are established, and every chunk runs the curation plane's three commands"
      - "**WCAG 2.1 AA on the curation UI, and colour is never the sole carrier of state** (Test, `curation/tests/unit/test_design_tokens.py`) → applies to every screen chunk. The row itself records that the contrast half is mechanical and the non-colour half is not — a test can see a badge has a glyph, not that the glyph distinguishes anything — so each screen chunk owes the second half its own reasoning, not a green token test"
      - "**the stylesheet is the source of truth for token values** (Test, same file) → applies, and **Chunk 03 is what makes this row true**. It currently records its own gap: the revised palettes live only in the prototype, which the test does not read, so every revised colour is hand-checked and ungoverned, and the row 'becomes a true strict Test row for those values when they land in `app.css`, and not before'. Chunk 03 lands them and updates the row"
      - "**the curation surface is organised around what a curator does** (Critic) → applies. The row carries a retroactivity note saying it will read as violated until this work lands, deliberately rather than being softened to match the code. **Chunk 04 is what retires that note**, and updating the row is one of its deliverables"
      - "**the theme manifest file is the only channel from curation to display** (Test, `tests/preferences/test_plane_isolation.py`) → conforms; Chunk 02 is the chunk it guards and the test is a Done-when step there"
      - "**the two planes agree on the heartbeat's filename and its instant's key by construction** (Test, `tests/preferences/test_heartbeat_contract.py`) → **ruling needed, and Chunk 02 takes it.** That guard reads both planes' source with AST, compares two deliberately-duplicated string constants, and pins them literally against `observability-strategy.md`. Per-wall heartbeats change the filename on both sides at once — which is precisely the case the row says must still break the test. The guard is not weakened to accommodate the change: the chunk updates the pinned literal in `observability-strategy.md` first, and the test follows it"
last_validated: null
---

# Build Plan — The Curation Surface

**This plan is independent of `build-plan.md` and does not wait on it.** That plan's
remaining chunks — 13A, 13B and 20 — are blocked on a television, a panel and a
backup exercise. Nothing here is. `information-architecture.md` § Status originally
gated this work on Chunk 13A resolving; **the operator lifted that gate on
2026-08-12** on the grounds that queuing browser work behind hardware bought delay
and nothing else.

**`build-plan.md` stays the `active_build_plan` pointer** until its own chunks
close. Two live plans is the documented gitflow case, and the Stop hook's gates
follow the pointer — so chunk-close here runs `/prawduct:critic` explicitly rather
than relying on the gate to fire.

**Pass `--chunk` on those dispatches.** With the pointer on the other plan,
record-lint otherwise grades that plan's next unticked box instead of the chunk
being closed — a green grade for work nobody reviewed. Noted by the Critic on the
round that authored this plan.

## Requirements Confidence

**Level:** Medium

**Why:** The design is unusually settled for work that has not started.
`information-architecture.md` carries nine screens, six flows, an empty/loading/error
state per screen and a committed working prototype; `api-contract.md` § The routes
the interface design requires fixes the route set and the rules; `accessibility-spec.md`
and `design-direction.md` carry ratified norms. The three questions that were open on
2026-08-11 — conversation deletion, `TvBinding` uniqueness, one-theme-per-wall — were
all ruled on 2026-08-12 and are written into the artifacts.

What holds this at Medium is that **two of the eleven chunks build against entities
that have never existed and a conversational flow nobody has exercised.** Chunks 10
and 11 carry `Conversation`, `ConversationTurn` and `Affinity`, and flow 1's hard
requirement — the commit card transforming in place into a run card — is a claim
about an interaction, not about a schema. The other nine chunks are Medium-High and
the plan is ordered so they do not wait on the two.

**Open assumptions / unknowns:**

- [ASSUMPTION: text search is SQLite FTS5 over title, artist name and facet values, not a `LIKE` scan | MED impact | Chunk 06 settles it against the real corpus; a 41-work collection cannot tell the two apart and a 4,000-work one can. User can override toward the simpler option if the measurement says it is enough]
- [ASSUMPTION: one wall exists at cutover and the migration assigns it the currently-active theme | HIGH impact if wrong | this is what keeps Chunk 01 from blanking the wall. User can correct the wall's name; the count is verifiable and is verified in the chunk]
- [ASSUMPTION: the conversation's model turn can be served by the existing OpenRouter client without a new abstraction | MED impact | Chunk 10's verify-api step tests it rather than assuming; the discovery use is single-shot and this one is multi-turn with images]
- [ASSUMPTION: the contact-sheet threshold is "a few hundred" works | LOW impact | `information-architecture.md` § Open questions already names this a guess to be set from a real thousands-scale corpus. Chunk 07 makes it one constant with the guess recorded at its site, not a decision spread through the grid]
- **Whether Review needs its own density control is deliberately unresolved** and is
  not an assumption — the IA defers it until a run is large enough to hurt, and no
  chunk here builds one.

**What would raise confidence:** Chunk 10's `verify-api` step, and Chunk 06's
measurement against a seeded thousands-scale corpus. Both are cheap, both convert a
named assumption into a recorded fact, and neither blocks the chunks before it.

## Status

- [ ] Chunk 01: Wall, ThemeAssignment, and the end of `Theme.is_active`
- [ ] Chunk 02: One manifest per wall — the inter-plane half
- [ ] Chunk 03: The revised palette lands in the stylesheet
- [ ] Chunk 04: Three destinations — the navigation reshape
- [ ] Chunk 05: The Walls screen — the product's home
- [ ] Chunk 06: `WorkFacet`, text search, and facet counts
- [ ] Chunk 07: Collection — the grid, the rails, and the three empties
- [ ] Chunk 08: The Work screen, archive and restore
- [ ] Chunk 09: The Theme screen — rename, reorder, hang, delete
- [ ] Chunk 10: Conversation — the thread, the turns, and the commit seam
- [ ] Chunk 11: Taste — affinities, reactions, and the delete that detaches

Context: Plan authored 2026-08-12, the day the operator ruled on the three questions
that had been holding it. Nothing built. **Build order is the list order**, and the
one ordering decision worth knowing is that the wall chunks come first: they are
underneath every screen, they are the expensive retrofit, and `information-architecture.md`
§ More than one wall argues that fixing the *shape* while it is free is the whole
point. Chunk 03 is out of dependency order deliberately — it is small, it is an
existing debt, and every screen chunk after it is easier to look at once the palette
is right.

## Scaffolding

The curation plane is built, tooled and tested; nothing here needs a scaffold. The
commands are `CLAUDE.md`'s curation column, and all three must pass:

```sh
cd curation && uv run pytest          # already -n auto; add -n0 to debug
cd curation && uv run ruff check .
cd curation && uv run black .
```

### Verification Strategy

**Three layers, and the middle one is the one this plan lives or dies by.**

- **The Python suite** covers routes, services and entities, booting a real uvicorn
  server per test class of surface work — never an in-process ASGI transport, for
  the lifespan reason `CLAUDE.md` records.
- **The browser suite** (`-m browser -n0`) is the only thing that executes
  `app.js`, and this plan rewrites `app.js`. **Every screen chunk ships browser
  tests**, not as a bonus but because neither Python suite runs a line of the
  client. `-n0` matters: these tests time real poll intervals.
- **`tools/mutation_sweep.py` on every chunk that claims a new branch is covered.**
  A green suite says nothing about a branch no test reaches, and this plan adds
  branch-heavy code — facet counts that exclude their own facet, three distinct
  empty states, a disabled-not-hidden option. The sweep drives `app.js` as happily
  as a Python file; the browser-suite invocation needs the marker passed through
  (`-- -m browser`).

**Beyond tests:** run the plane (`cd curation && uv run python -m curation`) and use
it as a curator would. `.prawduct/artifacts/prototypes/curation-ia-prototype.html`
is the reference for what each screen should feel like — open it beside the real
thing. It carries a synthetic 2,000-work corpus, which is the only place any scale
claim in this plan can be checked; the real collection is 41 works and cannot
falsify one.

## Project Structure

No new packages. The work lands in the existing curation plane:

```
curation/src/curation/
├── http/
│   ├── api.py            # routes — extended, not restructured
│   ├── models.py         # response shapes
│   └── static/           # index.html, app.css, app.js — the redesign
├── services/             # display.py, and the new conversation/taste services
├── catalogue/            # entities and the durable-store adapter
└── manifest/builder.py   # per-wall in Chunk 02
```

### Module Boundaries

Unchanged and binding: **operation logic lives in the service layer**; routes and
MCP tools are thin bindings over it. A rule that appears in both surfaces —
the delete-theme refusal, the archive wall-consequence — is written once in a
service and called twice.

## Build Chunks

### Chunk 01: Wall, ThemeAssignment, and the end of `Theme.is_active`

- **Description:** Themes become global and hanging becomes an act against a named
  wall. This is the structural keystone: it is underneath every screen in this plan,
  it is what `information-architecture.md` § More than one wall calls the expensive
  retrofit, and it engages a `## Direction` norm head-on.
- **Depends on:** none
- **Artifacts consumed:** `data-model.md` §§ Wall, ThemeAssignment, Directive,
  Constraint 1; `api-contract.md` § Three built routes gain a wall
- **Deliverables:**
  - `Wall` and `ThemeAssignment` entities in the catalogue; `Theme.is_active` and
    the `themes_one_active` partial index removed
  - `Directive` keyed by wall rather than a singleton
  - A migration that creates one wall, names it from configuration, assigns it the
    currently-active theme, and moves the directive row onto it
  - `reconcile()`'s promote-the-oldest behaviour **removed**, per the recorded
    decision at `data-model.md` § ThemeAssignment
  - `POST /api/themes/{id}/activate` and `GET /api/manifest` take a wall;
    `art_theme(action='activate')` and `art_display` take it too, by the parity
    requirement in `product-brief.md` item 8
  - `DisplayService.delete_theme`'s refusal generalised from "the active theme while
    another exists" to "a theme hung on any wall"
- **Tests:** unit — the assignment key rejects a second theme on a wall; the
  migration assigns the active theme and creates exactly one wall; the generalised
  refusal fires for a theme on two walls and permits the last unhung theme.
  Integration — activate names a wall and the published manifest reflects only that
  wall; a `next` on one wall does not advance another's sequence
- **Acceptance criteria:** the existing single-wall installation behaves identically
  through the surface — same theme hanging, same manifest content, same directive
  behaviour — with a wall now named in every request that changes a wall. All three
  curation commands pass.
- **Critic mode:** final
  <!-- Override: inference picks `chunk` for a first chunk in a multi-chunk plan.
       This one lands four entity changes, a migration over live data, and a ruling
       against a Direction norm — the coherence matters before ten chunks build on
       it. -->
- **Done when:**
  1. Acceptance criteria met and tests pass
  2. `tools/mutation_sweep.py` run over the assignment key, the migration and the
     generalised refusal — the three places where a passing test could be passing
     for the wrong reason
  3. `/prawduct:critic` run and blocking findings resolved
  4. Committed and chunk marked `[x]` in Status

### Chunk 02: One manifest per wall — the inter-plane half

- **Description:** The manifest and the heartbeat become one file per wall, and the
  display plane reads the wall it is configured to serve. The chunk that could most
  easily break the architecture norm it is governed by.
- **Depends on:** Chunk 01
- **Artifacts consumed:** `architecture.md` § One manifest per wall, § Data Ownership
  & Consistency; `boundary-patterns.md`
- **Deliverables:**
  - `curation/src/curation/manifest/builder.py` writes one manifest per wall,
    atomically as today
  - The display plane takes a wall id from configuration, as it already takes
    `TV_ADDRESS`, and reads only that wall's manifest
  - `display-heartbeat.json` likewise per wall, so health can name which wall is
    silent — **the pinned literal in `observability-strategy.md` moves first**, then
    `tests/preferences/test_heartbeat_contract.py` follows it. That guard exists
    because both planes declare the filename separately and may not import each
    other, and its whole value is that *both sides moving together is still a
    break*. This chunk is that case: update the specification, not the assertion
  - `GET /api/health` aggregates across walls — "well", or the wall that has not
    reported
- **Tests:** display — the daemon reads its own wall's manifest and ignores another's
  (over the existing double, no hardware); a manifest for an unknown wall is not
  acted on. Curation — one wall's rewrite does not touch another wall's file mtime,
  which is the property the per-file decision was made for
- **Acceptance criteria:** a two-wall fixture drives two independent manifests with
  independent directive sequences; the one-wall case is byte-identical to today's
  behaviour apart from the filename. Both plane suites pass.
- **Done when:**
  1. Acceptance criteria met and tests pass
  2. The plane-isolation test still passes — this chunk touches both planes and is
     exactly the shape that erodes it
  3. `/prawduct:critic` run and blocking findings resolved
  4. Committed and chunk marked `[x]` in Status

### Chunk 03: The revised palette lands in the stylesheet

- **Description:** Move the prototype's palette into `app.css`, where the token norm
  says values live. Closes the `information-architecture.md` § Status row that has
  read "Proposed only… ungoverned until they land" since 2026-08-11.
- **Depends on:** none
- **Artifacts consumed:** `design-direction.md` § Direction;
  `.prawduct/artifacts/prototypes/curation-ia-prototype.html`
- **Deliverables:**
  - The revised light and dark palettes in `app.css`, including the tokens the built
    stylesheet has never had — `--good`/`--warn`/`--crit` and their quiet variants,
    `--scrim`/`--scrim-text`, `--rail`, `--masthead`
  - **The `project-preferences.md` token row updated.** It currently records that
    these values live only in the prototype and are therefore ungoverned, and says
    it becomes a true `strict` Test row "when they land in `app.css`, and not
    before". This chunk is that moment; leaving the row unchanged would leave the
    index under-claiming its own enforcement, which that table keeps a rule about
- **Tests:** `curation/tests/unit/test_design_tokens.py` computes every text and
  control pair in both schemes and refuses any colour outside the token blocks — the
  new tokens go through it unchanged. Extend it only if a new pair exists that it
  cannot already see.
- **Acceptance criteria:** every pair meets AA in both schemes; no hex outside a
  token block; the built surface still reads correctly with the new values.
- **Visual change:** yes — a palette is the one thing a contrast test cannot approve
  on its own; the question is whether it looks like a museum.
- **Done when:**
  1. Acceptance criteria met and tests pass
  2. `.prawduct/operator-verification.md` entry appended
  3. `/prawduct:critic` run and blocking findings resolved
  4. Committed and chunk marked `[x]` in Status

### Chunk 04: Three destinations — the navigation reshape

- **Description:** Five pipeline-stage tabs become three destinations — The Walls,
  Collection, Discover — with Health demoted to a masthead indicator and Review and
  Theme becoming contextual screens. **This is the chunk the IA's Direction norm was
  ratified to bind**, and the point at which the surface stops violating it.
- **Depends on:** Chunk 01 (walls exist to navigate to)
- **Artifacts consumed:** `information-architecture.md` §§ Direction, Navigation
  Structure, Screen Inventory
- **Deliverables:**
  - `index.html` and `app.js`: three destinations, flat, no drawer, no nesting
  - The masthead status indicator — always present, reads "well" or names what is
    wrong, expands to Health. **The indicator is the contract that makes demoting
    Health safe**; a silent one is worse than the tab it replaced
  - A persistent search affordance
  - Contextual screens return to the destination they were opened from, on real
    URLs, so browser back does it natively
  - Addressable state extended to search and filters
  - **The `project-preferences.md` row for the IA norm updated.** It carries a
    retroactivity note saying the built surface does not conform and the row will
    read as violated until this work lands. This is the work; the note is retired
    here and nowhere earlier
- **Tests:** browser — each destination is reachable and addressable; a Work opened
  from one destination returns to it and not to a fixed parent; the status indicator
  announces a degraded state without colour being the sole carrier. Unit — route
  parsing for the extended state
- **Acceptance criteria:** no destination in the navigation names a pipeline stage;
  Health is reachable and not navigable-to; every screen and consequential state has
  a URL.
- **Visual change:** yes
- **Done when:**
  1. Acceptance criteria met and tests pass
  2. `tools/mutation_sweep.py` over the routing and the indicator's degraded branch
     (`-- -m browser`)
  3. `/prawduct:critic` run and blocking findings resolved
  4. Committed and chunk marked `[x]` in Status

### Chunk 05: The Walls screen — the product's home

- **Description:** What is hanging right now on each wall, the theme it is drawn
  from, and what is next. One wall is the degenerate case of many, never a special
  case — there is no single-wall layout for a second display to replace.
- **Depends on:** Chunks 01, 02, 04
- **Artifacts consumed:** `information-architecture.md` §§ More than one wall,
  Information Hierarchy, Screen States; flow 6
- **Deliverables:** the Walls screen; the per-wall theme control and `next`; the
  activation confirmation that **names the wall and the consequence** — "Hang Winter
  in the living room" — even with one wall; the four named empty reasons (no theme
  hung / empty theme / display plane silent / cannot reach a plane) each offering
  the fix for that reason specifically
- **Tests:** browser — each empty reason renders its own text and its own fix, and
  they are four branches rather than one; the confirmation names the wall; a poll
  does not move focus. Integration — activation publishes to the named wall only
- **Acceptance criteria:** with one wall it reads as a single-wall home; with two
  fixture walls it shows two, with no layout switch.
- **Visual change:** yes
- **Done when:**
  1. Acceptance criteria met and tests pass
  2. `tools/mutation_sweep.py` over the four empty branches — the exact shape where
     one test passing for all four looks like coverage
  3. `/prawduct:critic` run and blocking findings resolved
  4. Committed and chunk marked `[x]` in Status

### Chunk 06: `WorkFacet`, text search, and facet counts

- **Description:** The retrieval layer Collection stands on. `nonfunctional-requirements.md`
  made search mandatory rather than optional, and the fields it searches did not
  exist until `WorkFacet` was designed.
- **Depends on:** none (backend-only; may run in parallel with 04–05)
- **Artifacts consumed:** `data-model.md` § WorkFacet; `information-architecture.md`
  § Retrieval: search and facets; `api-contract.md` (the `GET /api/works` extension)
- **Deliverables:**
  - `WorkFacet` with `kind`, `value` and a required `derivation` of `sourced` or
    `inferred`, sharing `Affinity.kind`'s vocabulary
  - `GET /api/works` gains `q` and one repeatable filter per facet kind
  - **Facet counts in the same response, not a second route** — each facet's counts
    computed over the results filtered by *every other* facet, never its own
  - `art_catalogue(action='list')` gains the same filters
- **Tests:** unit — a facet's counts exclude its own selection, so a curator can
  change their mind without clearing; a zero-count option is returned as disabled
  rather than omitted; selecting a movement narrows era without a rule saying so.
  Integration — search over a seeded thousands-scale corpus
- **Acceptance criteria:** no filter combination the control offers can return an
  unexplained empty grid. Search latency measured on the seeded corpus, and the
  FTS5-vs-`LIKE` assumption settled with the number recorded.
- **Done when:**
  1. Acceptance criteria met and tests pass
  2. `tools/mutation_sweep.py` over the count-exclusion logic — the branch whose
     absence is invisible at 41 works and ruinous at 4,000
  3. `/prawduct:critic` run and blocking findings resolved
  4. Committed and chunk marked `[x]` in Status

### Chunk 07: Collection — the grid, the rails, and the three empties

- **Description:** Everything acquired, in one place, with the organisation of it
  beside it rather than in another tab. Themes stop being a destination and become a
  rail that filters and is editable.
- **Depends on:** Chunks 04, 06
- **Artifacts consumed:** `information-architecture.md` §§ Information Hierarchy,
  Screen States; flow 5
- **Deliverables:**
  - The grid, with **density as a control**: contact sheet (image only, uniform
    tiles) and catalogue (the built card), remembered and part of the addressable
    state
  - The facet rail — typed vocabulary, counts shown, zero options disabled and not
    hidden, the inferred-is-the-rule footnote below the facts and the rare `sourced`
    marked with a tick rather than a word
  - The theme rail: filters the grid to a theme's members, membership edited in
    place with multi-select
  - **Three distinct empty states** — no works at all; no works matching the filter;
    filtered to one artist and holding none of them
  - Skeleton tiles at the grid's real geometry, so nothing reflows
- **Tests:** browser — the three empties are three branches with three texts; the
  density control survives a reload and a link; tiles do not reflow as images
  arrive; a poll does not move focus
- **Acceptance criteria:** at the prototype's 2,000-work scale the default is contact
  sheet and the grid stays legible; membership can be edited without leaving the
  screen.
- **Visual change:** yes
- **Done when:**
  1. Acceptance criteria met and tests pass
  2. `tools/mutation_sweep.py` over the three empty branches and the density default
  3. `/prawduct:critic` run and blocking findings resolved
  4. Committed and chunk marked `[x]` in Status

### Chunk 08: The Work screen, archive and restore

- **Description:** One work at full size, and the only two operations that take a
  work out of circulation and put it back. **There is no delete of a work in this
  product**, and this chunk is where that stops being a rule in an artifact and
  becomes a label on a control.
- **Depends on:** Chunks 04, 06
- **Artifacts consumed:** `information-architecture.md` § Information Hierarchy;
  `api-contract.md` § "Work delete" was the wrong word
- **Deliverables:**
  - The Work screen: image primary, facts stated once each, the mat showing its
    colour and nothing else, no label geometry
  - `POST /api/works/{id}/archive` and `/restore`, and the MCP actions already
    designed
  - The controls read **Archive** and **Restore**, styled as ordinary reversible
    acts — **not `danger`** — and the confirmation says which it is doing
  - Archiving a work hung on a wall names *which walls lose the picture*, computed
    from `GET /api/manifest` rather than predicted
- **Tests:** browser — the archive control's label and styling, and the confirmation
  naming a wall consequence when there is one and not when there is not. Integration
  — archive withdraws a pin without advancing the directive sequence
- **Acceptance criteria:** no control anywhere in the surface says "Remove" of a
  work; restoration works and is discoverable.
- **Visual change:** yes
- **Done when:**
  1. Acceptance criteria met and tests pass
  2. `tools/mutation_sweep.py` over the wall-consequence branch
  3. `/prawduct:critic` run and blocking findings resolved
  4. Committed and chunk marked `[x]` in Status

### Chunk 09: The Theme screen — rename, reorder, hang, delete

- **Description:** The one thing about a theme that is genuinely its own act rather
  than an operation on works.
- **Depends on:** Chunks 01, 07
- **Artifacts consumed:** `information-architecture.md` flow 5, flow 6;
  `api-contract.md` (theme rename and delete)
- **Deliverables:** members in wall order; rename via `POST /api/themes/{id}`;
  reorder; "hang this" naming the wall; `DELETE /api/themes/{id}` calling the
  service guard rather than writing its own, with the refusal message already
  written in `api-contract.md`
- **Tests:** integration — delete refuses a theme hung on any wall and permits the
  last unhung one; the refusal message is the normative sentence. Browser — reorder
  persists and repaints from the response
- **Acceptance criteria:** a theme hung on two walls cannot be deleted, and the
  refusal says why in words a curator can act on.
- **Visual change:** yes
- **Done when:**
  1. Acceptance criteria met and tests pass
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

### Chunk 10: Conversation — the thread, the turns, and the commit seam

- **Description:** Intent-forming as a conversation, and the seam that keeps it from
  becoming a wizard. **The in-place transform is this chunk's hard requirement, not
  a polish item** — the commit card becomes the run's progress card becomes "12
  works ready to review", with the transcript above it the whole time.
- **Depends on:** Chunk 04
- **Artifacts consumed:** `data-model.md` §§ Conversation, ConversationTurn;
  `information-architecture.md` flow 1; `api-contract.md` (the conversation routes)
- **Deliverables:** `Conversation` and `ConversationTurn`; `GET`/`POST
  /api/conversations`, `GET /api/conversations/{id}`, `POST .../turns`, `POST
  .../commit`; the thread UI with samples inline; the commit card and its in-place
  transform; a failed turn that stays in the thread and is retryable
- **Tests:** browser — the commit card transforms in place and the transcript stays
  above it; a failed turn is retryable and never silently vanishes. Integration — a
  turn writes a `SpendRecord` with category `conversation_tokens`; `committed_run_id`
  is set on the committing turn and a run started from Discover has none
- **Acceptance criteria:** committing a direction never navigates away. Spend for a
  conversation appears in the month total.
- **Foreign API:** openrouter
  <!-- The client exists from Chunk 14B, but its use there is single-shot and this
       one is multi-turn with images. The shape is what needs verifying, not the
       vendor. -->
- **Visual change:** yes
- **Done when:**
  0. verify-api — probe a real multi-turn exchange with image samples through the
     existing client; capture the actual request and response shapes before any
     handler is drafted, and build fakes from what came back
  1. Acceptance criteria met and tests pass
  2. **`conversation_tokens` ships with its producer or not at all** — the rule
     `data-model.md` states for this category. A route that spends without writing
     the row fails this chunk
  3. `/prawduct:critic` run and blocking findings resolved
  4. Committed and chunk marked `[x]` in Status

### Chunk 11: Taste — affinities, reactions, and the delete that detaches

- **Description:** What the product has accumulated about the curator, correctable,
  with its derivation visible. And the one operation in this product that genuinely
  destroys a record.
- **Depends on:** Chunk 10
- **Artifacts consumed:** `data-model.md` § Affinity; `security-model.md` § Deleting
  a conversation; `api-contract.md` § `art_taste`
- **Deliverables:**
  - `Affinity`, unique on (`kind`, `value`), with `rationale` **required** for
    `inferred` and `observed`
  - `GET`/`POST /api/affinities`, `DELETE /api/affinities/{id}`; the `art_taste` MCP
    tool with `list`, `set`, `delete`
  - Per-sample reactions in the thread — "more like this" / "not this" / "tell me
    more" writing `derivation='stated'`, with "go to <artist>'s work" kept visually
    apart because it leaves the thread
  - The Taste screen, with each affinity's derivation and a correction path
  - `DELETE /api/conversations/{id}`: deletes the thread and its turns, **nulls**
    `Affinity.source_turn_id` and `SpendRecord.conversation_turn_id`, and confirms
    by naming what is lost — the ability to rebuild those judgments — rather than a
    row count
- **Tests:** integration — deleting a conversation leaves its affinities and spend
  rows standing with null citations; the month total is unchanged across the delete;
  an `inferred` affinity with a null `source_turn_id` loads and renders. Unit —
  `set` refuses `derivation='observed'`, refuses to overwrite provenance with a
  weaker one, and requires `rationale` for the two derivations that now need it.
  Browser — the artist-filtered empty state says "Nothing by X yet" as a normal
  state
- **Acceptance criteria:** the `inferred ⇒ source_turn_id` rule is enforced **on the
  write path only** — a stored constraint here makes the delete impossible and fails
  the chunk. The spend ledger's month total is provably unchanged by a conversation
  delete.
- **Type:** cumulative-final
- **Visual change:** yes
- **Done when:**
  1. Acceptance criteria met and tests pass
  2. `tools/mutation_sweep.py` over the detach logic — nulling versus cascading is
     one line and both look correct in a diff
  3. Committed, then `/prawduct:critic cumulative` run and blocking findings resolved
  4. Chunk marked `[x]` in Status

## Early Feedback Milestone

**Milestone chunk:** 04

**What the user can do:** open the surface and find it organised around what they
do — three destinations, the wall first, Health where a status indicator belongs.
Everything before 04 is underneath; 04 is where the redesign becomes visible, and
it is the chunk whose feedback most changes what follows.

## Governance Checkpoints

**Commit & PR cadence:** commit per chunk after its Critic review passes — per-chunk
commit is what scopes `chunk`-mode reviews, and this plan has eleven of them. Chunk
11's `cumulative` review makes the branch PR-ready.

- **After Chunk 01:** the keystone review. Four entity changes, a migration over
  live data and a ruling against a Direction norm — confirm the shape before ten
  chunks build on it.
- **After Chunk 02:** the plane boundary. This is the only chunk that writes on both
  sides of it; confirm the isolation test still means what it says.
- **After Chunk 07:** the scale checkpoint. Collection at 2,000 works is where every
  claim in `information-architecture.md` about density, facets and retrieval either
  holds or does not — and it is the last point where changing the answer is cheap.
- **After Chunk 11 (cumulative):** full-bundle review, against the IA's Direction
  norm specifically. The failure this norm exists to catch is invisible per-chunk
  and visible only in the sum, which is exactly what a cumulative pass reads.
