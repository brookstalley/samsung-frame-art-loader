---
artifact: build-plan
version: 1
scope: curation-ui-fixes
depends_on:
  - artifact: information-architecture
  - artifact: architecture
  - artifact: accessibility-spec
  - artifact: project-preferences
governed_by:
  - artifact: information-architecture
    dispositions:
      - "the curation surface is organised around what a curator does, never around the pipeline's stages → conforms: no chunk here adds a destination or renames one. Chunk 04 makes an existing contextual screen addressable, which is the navigation rule below rather than this one; the three destinations are untouched by every chunk"
      - "every screen and every consequential state is addressable (§ Navigation Structure) → **Chunk 04 is what makes this true for a theme**, and Chunk 01 is what makes the failure visible next time. The rule is stated in § Navigation Structure and has no enforcement; #133 is a screen that has been unaddressable since it was built, found by eye a chunk later"
      - "One row here per screen in § Screen Inventory, and the agreement is the check (§ Information Hierarchy) → **Chunk 01 replaces the check.** The rule asks a human to read two lists against each other, and it has now failed three times in one artifact (#123 closed 2026-08-12, #148 filed 2026-08-17). The rule is not deleted — it still says what agreement means — but the reading is derived by a test, because a rule whose enforcement is 'somebody notices' has a measured failure rate here of three"
  - artifact: architecture
    dispositions:
      - "a module under `screens/` may import from `core/` and must never import another screen (§ Components & Responsibilities) → **Chunk 03 is the chunk this norm exists for.** `conversation.js:50-51` records that it hand-copied the run view's poll chain *because* of this rule — the duplication is the norm working as designed, and `core/poll.js` is the third option the norm's own text says exists. `curation/tests/unit/test_client_module_boundaries.py` is the mechanical half and stays green throughout"
      - "operation logic lives only in the service layer; MCP tools and HTTP handlers are thin bindings → conforms: Chunk 02 moves a *sentence* between a shared helper and three callers, none of which gains a decision. The helper is text formatting, not operation logic, and it is deliberately not placed in `services/`"
  - artifact: accessibility-spec
    dispositions:
      - "WCAG 2.1 AA on the curation browser, and colour is never the sole carrier of state → applies to Chunks 03 and 04, and neither introduces a colour-carried state. Chunk 04 adds one link per theme chip and one heading per addressed theme; the accessible name of a chip that both filters and opens is the thing to get right, and it is called out in that chunk's tests"
      - "the e-paper label is legible at standing distance → inapplicable because: no chunk here renders a label, touches the display plane, or changes a catalogue field a label reads. Chunk 02 edits `manifest/builder.py`'s *summary prose*, which is read by the curation surface and by no typesetter"
  - artifact: project-preferences
    dispositions:
      - "the mechanical norm-index rows (formatting, naming, imports, logging-not-print, type-annotate-on-touch, specific exceptions, no hardcoded deployment values) → conforms: every chunk runs the curation plane's three commands, and the root plane's where it touches `tests/`"
last_validated: null
lifecycle: active
---

# Build Plan — The Curation UI Backlog

**This plan is independent of `build-plan.md` and does not wait on it.** That
plan's remaining boxes — 13A, 13B, and 24 through 27 — are blocked on a
television and a panel. Nothing here needs either: every chunk is browser
client, MCP notice text, or an artifact, and the whole of it is exercised by
suites that run on a laptop.

**`active_build_plan` is pointed here for the duration**, and moves back to
`artifacts/build-plan.md` when this plan is archived. Unset, governance resolves
every chunk below against the v1 plan — the Critic's chunk-ref verification then
answers about a *different* plan's Chunk 01 and reports a pass. That is not a
missing check; it is a check that runs against the wrong subject and passes.
The reasoning is `project-state.yaml`'s own, recorded there when
`build-plan-curation-ux.md` was live.

## What this plan is

Four backlog items, all `area:curation-ui` and all `stage:ready`, picked
together on 2026-08-17 because they are the whole of what is buildable in that
area without a design round first. The other eight `curation-ui` items sit at
`stage:design` or `stage:idea` and are deliberately not here.

| Chunk | Issue | What it is |
|---|---|---|
| 01 | #148 | Three IA tables that no longer describe the surface, and the check that replaces the reading |
| 02 | #113 | "1 works" — subject–verb agreement across five surfaces and two languages |
| 03 | #136 | `core/poll.js` — the poll chain `run.js` and `conversation.js` each carry |
| 04 | #133 | A theme becomes individually addressable |

**Build order is the order above, and two of the three orderings matter.**
Chunk 01 lands the derived table check *before* Chunk 04 edits the same tables,
so the edit is guarded rather than trusted. Chunk 02 lands before Chunk 03
because both touch `run.js` and Chunk 02 is the smaller diff — the sentences and
the poll chain are separate regions of the file, but a reviewer reading one diff
over both would be reading two unrelated changes. Chunk 04 is last because it is
the only one that changes what a screen does.

## Status

- [x] Chunk 01: The IA's three tables, reconciled — and derived rather than read (issue #148)
- [x] Chunk 02: One count, one noun, one verb — the plural helper and its callers (issue #113)
- [x] Chunk 03: `core/poll.js` — the chain both watching screens carry (issue #136)
- [ ] Chunk 04: A theme gets an address (issue #133)

---

### Chunk 01: The IA's three tables, reconciled — and derived rather than read

- **Description:** `information-architecture.md` describes the surface in three
  per-screen tables, and all three have drifted from `app.js`'s route table and
  from each other. Reconcile them, then replace the rule that was supposed to
  catch this with a test, because the rule has now failed three times in the
  same artifact.
- **Depends on:** none
- **Artifacts consumed:** `information-architecture.md` §§ Screen Inventory,
  Navigation Structure, Information Hierarchy, Screen States
- **Deliverables:**
  - **A Run row in § Screen Inventory, § Information Hierarchy and § Screen
    States**, and Run added to § Navigation Structure's contextual enumeration —
    which today reads *"Theme, Work, Review, Conversation and Taste"* and leaves
    out a screen that has been routed at `app.js:65` since it was built. Run is a
    real destination rather than an implementation detail: flow 2's direct intent
    box starts a run with no conversation to host it, so the seam flow 1
    describes — *"the commit card becomes the run's progress card in place"* —
    cannot be the whole story.
  - **Conversation and Health rows in § Screen States.** Its preamble claims the
    four states are *"assessed for every screen"* and the table carries seven of
    ten. Conversation is one of the two screens § Screen Inventory marks *(new)*,
    on the flow `product-brief.md` calls core.
  - **§ Screen Inventory's count sentence corrected.** It reads "Nine screens";
    the route table has ten. Written as a count rather than as a rule, which is
    the shape § Information Hierarchy's own preamble warns about three lines
    below its table — so it is **restated relationally** rather than incremented,
    and the new test is what holds it.
  - **`tests/preferences/test_screen_tables.py`** — the derived check. It parses
    `ROUTES` out of `curation/src/curation/http/static/app.js` and the three
    tables out of `information-architecture.md`, and fails when a route has no
    row or a row names no route. It lives in `tests/preferences/` because that is
    where this repo's artifact-versus-code contracts already live —
    `test_plane_isolation.py`, `test_heartbeat_contract.py`,
    `test_norm_index.py`, `test_label_corpus_contract.py` — and because the two
    files it reads are in two different projects, which the root suite spans and
    neither plane's does.
  - **§ Information Hierarchy's rule keeps its sentence and loses its job.** The
    rule ("One row here per screen in § Screen Inventory, and the agreement is
    the check") still states what agreement *means*; the note that the reading is
    how it is enforced is replaced by a pointer to the test. Deleting the rule
    would leave the test asserting a contract no artifact states.
- **Tests:** `tests/preferences/test_screen_tables.py` — a route with no row in
  each of the three tables fails, and does so naming the screen and the table; a
  table row naming no route fails; the parser finds all ten routes, so a parse
  that silently matched nothing cannot pass. **Planted violations for both
  directions**, per this repo's practice at `test_plane_isolation.py`: a check
  that has never been seen to fail is a check nobody has tested.
- **Acceptance criteria:** every route in `app.js` has a row in all three
  tables; § Navigation Structure's contextual list matches § Screen Inventory;
  the new test fails when either half is edited away. Root plane's three
  commands pass.
- **Critic mode:** chunk
- **Done when:**
  1. Acceptance criteria met and the root suite passes
  2. `tools/mutation_sweep.py` over the new test's two failure directions — a
     check whose green is untested is the defect this chunk exists to stop
     repeating, and it would be the sharpest possible irony to ship it here

**Scope-out:** no code changes to any screen, and no screen redesign. Whether
the Run screen *should* exist is in scope only as far as recording the answer.
The answer taken here is that it should: it is routed, it is reachable by URL,
and flow 2 produces one with no conversation to live inside.

---

### Chunk 02: One count, one noun, one verb — the plural helper and its callers

- **Description:** A run of exactly one work reads "1 works". The client already
  gets this right in one place and wrong in six lines of the same function, so
  the page can print a correct singular and an incorrect one in the same
  paragraph. That inconsistency is what makes it a defect rather than a style
  preference. The same sentence exists on non-client surfaces too, and a
  client-only fix leaves them wrong — and cannot fix the test that pins one of
  them.
- **Depends on:** none
- **Artifacts consumed:** none — neither `information-architecture.md` nor
  `accessibility-spec.md` bears on subject–verb agreement. That is itself the
  #124 sweep's finding about this item.
- **Deliverables:**
  - **A Python helper**, `curation/src/curation/counting.py` — count, singular,
    optional plural — and a verb form for the "is/are", "has/have" agreements.
    `curation/src/curation/observations.py` already carries an inline version,
    and `curation/src/curation/services/conversation.py` carries three
    hand-written ternaries; the helper is written to serve them, and **the sites
    that are already correct are left alone** — this chunk fixes a defect, it
    does not conduct a migration.
  - **A JS helper**, `curation/src/curation/http/static/core/counting.js`, same
    contract, because a screen cannot import a Python function and must not grow
    a second private one.
  - **Every site the run sentences reach, in one change**, because they are one
    omission copied across surfaces:
    - `curation/src/curation/http/static/screens/run.js` — the six sentences
      that hard-code the plural, plus the two that hard-code the *verb* ("…and
      **are** reported"; "the image provider was unreachable for **them**"). Its
      one correct inline ternary goes through the helper rather than being left
      as a seventh spelling.
    - `curation/src/curation/mcp/bindings.py` `_run_notice` — **the surface the
      pinned test actually exercises**, so it must move with the client or that
      test cannot be fixed.
    - `curation/src/curation/services/runner.py` — the two sentences at the
      phase-2 gate.
    - `curation/src/curation/manifest/builder.py` — the exclusion summary, **and
      the no-exclusions branch three lines above it**, which the issue's Actual
      list does not name. Taking one and leaving the other makes `summarise()`
      correct when there are exclusions and wrong when there are none.
    - `curation/src/curation/http/static/screens/conversation.js` — **a fifth
      surface, which #113 named none of and this plan first said did not exist.**
      Its commit card composes its own sentences from the same tally: two hard-
      coded the plural and a third was already correct. Found by grepping the
      client after the other four were fixed. *"One omission copied four ways"
      is what this line said before, and stating a count as if it were surveyed
      is what let the fifth through — the four were the ones the issue listed,
      not the ones that existed.*
  - **The pinned tests rewritten to keep the number without pinning the
    plural.** The issue predicted three and there were **eight** — six in the
    curation suite and two more, in `curation/tests/browser/test_the_walls.py`,
    that only the browser suite reaches. Each asserts a literal string containing
    the ungrammatical form. **Their claims are load-bearing and are preserved
    exactly** — that the count includes works the collection just added, that the
    re-search names the works it covers, that the summary reports what is not
    displayable. What changes is that they assert the count and the sense rather
    than the exact ungrammatical spelling. This is the narrow case the
    tests-never-weaken rule permits and it is recorded here because it looks like
    the case it forbids: the assertion's *subject* is unchanged and its strength
    is unchanged; an over-specified literal is replaced by the claim it was
    standing in for. **If a rewrite cannot keep the claim, the code is wrong and
    the test stays.**
- **Tests:** unit — the helper at 0, 1 and 2 for both noun and verb; each of the
  every changed module's sentences at a count of exactly one, asserting the singular noun
  *and* the singular verb, since the verb is the half a noun-only fix leaves
  behind. `manifest/builder.py`'s **two** branches at one, which is the pair that
  a partial fix splits.
- **Acceptance criteria:** no surface prints "1 works", "1 … are" or "1 … have";
  a count of two is unchanged everywhere. All three planes' commands pass.
- **Critic mode:** chunk
- **Done when:**
  1. Acceptance criteria met and all three suites pass
  2. `curation/tools/mutation_sweep.py` over the helper's singular branch and
     over **each site the fix changed** — near-identical call sites are exactly
     the shape where a green suite covers all but one. Two traps this chunk hit,
     recorded because both produce a reassuring green: mutate the line the fix
     *changed*, never a neighbouring one that was already correct; and give the
     sweep a timeout it can finish inside, because a killed sweep leaves the
     source mutated and a `.sweepbak` beside it

**Scope-out:** the three already-correct ternaries in
`curation/src/curation/services/conversation.py` and the correct one in
`curation/src/curation/observations.py` are not migrated. A helper's arrival is
not a licence to rewrite every caller that never had the bug. **Distinct from
`curation/src/curation/http/static/screens/conversation.js`**, which is in scope
above because two of its sentences were actually wrong — the similar basenames
are the reason this sentence names both paths in full.

---

### Chunk 03: `core/poll.js` — the chain both watching screens carry

- **Description:** `run.js` and `conversation.js` each implement the same
  generation-guarded poll: bump `state.poll`, capture the generation, check it
  after every await, and reschedule only while the view is non-terminal. The
  duplication is acknowledged in the source — `conversation.js:50-51` says it is
  *"Copied in shape from the run view rather than imported from it: a screen
  never imports another screen"* — which names the architecture norm and its own
  third option in one sentence. `curation/src/curation/http/static/core/` is that option, and
  `curation/src/curation/http/static/core/hanging.js` is the precedent, extracted for the same reason after the same Critic finding.
- **Depends on:** Chunk 02 (both touch `run.js`; sequencing, not logic)
- **Artifacts consumed:** `architecture.md` § Components & Responsibilities
- **Deliverables:**
  - **`curation/src/curation/http/static/core/poll.js`** owning the schedule, the generation guard and the
    reschedule decision. Each screen's own predicates stay parameters — which
    view and detail id are current, and what counts as terminal — because those
    genuinely differ.
  - **Both screens consume it**, and neither imports the other.
  - **The two-second interval is unchanged**, and stays two *constants* if
    folding them into one shared value would change either screen's timing.
    `RUN_POLL_MS` and `CONVERSATION_POLL_MS` are equal today and are not
    thereby the same fact.
  - **`run.js`'s failure counting stays in `run.js`.** `RUN_POLL_MAX_FAILURES`
    and `noteWatchFailure`/`noteWatchSuccess` are a property of watching a *run*
    — a run can 400 forever from a stale bookmark, and a conversation's
    equivalent has not been designed. Hoisting it into `curation/src/curation/http/static/core/` would invent a
    requirement for the conversation screen that no issue asks for.
- **Tests:** the browser suite is the level this is tested at, because the
  behaviour is a real timer against a real server. Existing `-m browser` tests
  over both screens must pass unchanged — **this is a refactor, so the tests do
  not move**; a test that has to change is the signal that behaviour did.
- **Acceptance criteria:** `curation/src/curation/http/static/core/poll.js` owns all three responsibilities; both
  screens consume it; `test_client_module_boundaries.py` stays green; the
  interval is unchanged and `cd curation && uv run pytest -m browser -n0`
  passes.
- **Critic mode:** chunk
- **Done when:**
  1. Acceptance criteria met, curation suite and browser suite both pass
  2. **The extraction is proved by mutation, not by a green suite** —
     `uv run python tools/mutation_sweep.py m.json <paths> -- -m browser`, with
     the marker passed through, or pytest collects nothing and exits 5

**Scope-out:** no change to poll timing or to what either screen renders. No
change to `curation/src/curation/http/static/core/hanging.js`. No other screen is brought in unless it already
carries the same chain, which is to be checked rather than assumed.

**The constraint that makes this chunk risky:** the browser suite measures real
elapsed poll windows rather than a mocked clock, which is why it runs `-n0`. An
extraction that shifts the interval, or folds the two constants into one value
with different timing, breaks tests that are asserting real time — and it breaks
them as flakes, not as failures.

---

### Chunk 04: A theme gets an address

- **Description:** `information-architecture.md:92` describes Theme as *"One
  theme: its members in curated order, its name, and the act of hanging it"*,
  reached from Collection's theme rail and from a wall's theme control. The
  built screen is a themes *index* — a create form plus one panel per theme,
  with all four acts per panel — and no theme has an address. The IA's
  § Navigation Structure requires that "every screen and every consequential
  state is addressable", and one theme is a consequential state.
- **Depends on:** Chunk 01 (its IA edits are guarded by Chunk 01's test)
- **Artifacts consumed:** `information-architecture.md` §§ Screen Inventory,
  Navigation Structure
- **Decision, taken by the owner 2026-08-17:** the route grows an **optional**
  id. `#theme` stays the index; `#theme/<id>` opens that one theme. The two
  alternatives were put and declined: making Theme detail-only matches the
  artifact literally but moves the create/manage index into Collection's rail and
  redesigns two screens, and deep-linking a panel via `?focus=` leaves the
  navigation rule satisfied in wording only.
- **Deliverables:**
  - **`core/route.js`'s grammar grows a third mode.** Today `parseRoute` is
    binary — line 116 takes an id only for `detail: true`, line 117 enters a
    route only for `detail: false`, and a `detail: true` route entered without an
    id falls through to the fallback. An optional-id route must return its view
    with `id: null` when the tail is absent and with the id when it is present.
  - **`core/router.js`** threads the optional id to the render function.
  - **`screens/theme.js`** renders one theme when given an id, and the index when
    not. **Both paths keep every act** — a curator who navigated to one theme
    must not lose rename, reorder, hang or delete by having arrived a different
    way.
  - **`screens/collection.js`** — the theme rail's chips gain a way to *open* a
    theme, distinct from filtering the grid by it. The chip is currently one
    control doing one thing; two things need two accessible names, and a chip
    whose label is a theme name and whose action depends on where you clicked is
    the failure this deliverable has to avoid.
  - **`screens/walls.js:235`** — a wall's theme control links to the theme that
    is hanging, which is what the IA's "from a wall's theme control" entry point
    means and what `go("theme")` with no id cannot do. `:323`'s "Create a theme"
    stays pointed at the index, which is where creating happens.
  - **`information-architecture.md`** — a recorded ruling under § Screen
    Inventory: Theme is an index *and* an addressable detail. Line 92's "One
    theme" describes the detail and no longer describes the whole screen. The
    reason the index survives is that creating a theme and managing the set of
    them have no other home — Collection's rail is a *filter* over the grid, and
    making it a manager is the redesign this decision declined.
- **Tests:** unit — `test_route_parsing.py` drives `parseRoute` directly and is
  where the grammar is pinned: an optional-id route with a tail, without a tail,
  with an empty tail, and with a tail that will not decode; a `detail: true`
  route's existing refusal of a missing id is **unchanged**, which is the
  regression the third mode could most easily cause. Browser — `#theme/<id>`
  renders that theme and no other; the four acts work from the addressed view;
  a wall's theme control lands on the hung theme; a rail chip's filter and its
  open are separately reachable by keyboard and separately named.
- **Acceptance criteria:** a theme is addressable, bookmarkable, and linkable by
  an agent; every act still works from both paths; the three destinations are
  unchanged. Curation suite, browser suite and Chunk 01's table test all pass.
- **Critic mode:** final
  <!-- Override: inference picks `chunk` for a last chunk in a multi-chunk plan
       whose earlier chunks took `chunk`. This one changes a grammar every screen
       is addressed through, and it is the plan's last box — the coherence of the
       four together, and the cross-checks `final` carries, matter more here than
       a fourth goals-1-3 pass. -->
- **Done when:**
  1. Acceptance criteria met; curation, browser and root suites pass
  2. `tools/mutation_sweep.py` over the third mode's branches in `parseRoute` —
     the optional-id path and the unchanged `detail: true` refusal, which is the
     branch a green suite is likeliest to be passing for the wrong reason
  3. `active_build_plan` moved back to `artifacts/build-plan.md` and this plan
     archived, per the pointer's own recorded reasoning

**Scope-out:** no change to what a theme *is*, to its API, or to the acts
themselves. Collection's rail does not become a manager. Wall deletion, theme
merging and anything else the addressed view might invite are not here.
