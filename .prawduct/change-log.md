# Change Log — Samsung Frame Art Loader

<!-- Append new entries at the top. Each entry is a ## section.
     This file is separate from project-state.yaml to reduce merge conflicts
     when multiple branches add entries simultaneously.

     # Tagged entries (enabled by default; set `views_enabled: false` in project-state.yaml to opt out)

     With views enabled (the default), add a tag-line directly under each ##
     header to mark which build-plan chunks the entry shipped and which
     release it belongs to. `prawduct-hook regen-views` uses these tags to
     regenerate three derived views:
       * build-plan `## Status` block — checkboxes flip from `status=shipped`
       * `.prawduct/release-notes.md` — sections grouped by `release=`
       * `scope_rollups:` block in project-state.yaml — grouped by `scope=`
     Untagged entries are ignored by all three views.

     Format:

         ## YYYY-MM-DD: title (vN.M.P)

         <!-- prawduct: chunks=00,01,02 | release=v1.3.18 | status=shipped | scope=v1.4 -->

         **Why:** ...

     Recognized keys:
       chunks   - comma-separated chunk IDs (zero-padded, must match
                  build-plan.md ## Status headers exactly: `Chunk 00:`)
       release  - version string (used by the release-notes view)
       status   - shipped | merged (legacy). Write a new entry with NO
                  status= on the feature branch: a statusless tagged entry
                  is the release-pending state, and it becomes "merged" by
                  construction when its PR lands — no stamp, no post-merge
                  bookkeeping commit (protected branches take commits only
                  by PR). Flip to `shipped` as part of release-prep when
                  the integration branch is released (gitflow), or write
                  `status=shipped` directly in the closing PR when the
                  PR's base IS the release surface (trunk; include
                  `release=vN.M.P` when the product tracks versions —
                  release-notes groups by it) — either way the tag merges
                  atomically with the work it describes.
                  `merged` is a legacy stamp some logs carry; it is treated
                  as statusless. Any other value (including a typo) is a
                  fatal regen-views error — fix it, don't invent states.
       scope    - rollup identifier (e.g., v1.4)

     With `views_enabled: true`, the Status checkboxes in build-plan.md are a
     derived view. Don't hand-edit them — add/update a tagged entry here and
     run `prawduct-hook regen-views`. -->

## 2026-08-01: The TV library moved two years forward, and deletion stopped being a guess

<!-- prawduct: chunks=05 | scope=v1-build -->

**Why:** The display plane's rotation design binds to this library's verified
behaviour, so the pin had to move before that plane is built. It carries no
`status=` because it is **not finished**: everything here comes from reading the
library's source and installing it, and what a television does is a separate
question that needs the set. `tv_api_check.py` is the scripted pass that answers
it, and until it runs green the new pins are unverified.

**What the verification found, past what the item anticipated.** The PyPI release
was never a candidate — it ships no async art client and no event callbacks at
all, so switching to it would have been a rewrite of the TV boundary rather than a
bump. `delete_list` is unchanged on the fork's master, byte for byte with the
two-year-old pin, so the bump does not fix it and the fallback fired. And
`upload()`'s new chunking is selected by argument *type*: a path streams, bytes do
not, and this product was reading files itself — so the bump alone would have
bought the new library and none of the benefit.

**Two costs nobody had priced.** The target imports `websockets.asyncio.client`,
which does not exist before websockets 13.0, while its own metadata still claims
`websockets>=10.2` — so this is a two-pin change that a resolver would have
allowed and an import would have failed. And building the art client now performs
blocking network I/O and raises when the set is unreachable, where the pin
deferred that to first use; the display daemon inherits that and cannot construct
one on its event loop.

**Deletion now reports what the set holds.** The new `tv_delete` verifies against
the television's own content list and keeps three outcomes apart — gone, still
listed, and unconfirmable — because collapsing them is the defect this replaces.
Images the set kept are a WARNING naming them, so the outcome cannot go
unreported even where a caller drops the result. The unconfirmable case has two
entry points that differ only in what it costs the caller:
`delete_list_confirmed` raises, and `remove_from_tv` logs an ERROR and carries on
— which is what the loader uses, because stopping there would skip the catalogue
save and every pending upload.

**Also found while verifying, and filed rather than fixed:** `requirements.txt`
cannot stand up a working legacy environment — `art.py` imports `cairo` and `gi`,
and neither `pycairo` nor `PyGObject` is listed, though both are in the Pi's
recovered freeze. That surfaced from actually installing the file rather than
reading it.

## 2026-08-01: A browser can see the collection, build a theme, and read why a work is not on the wall

<!-- prawduct: chunks=10B | status=shipped | scope=v1-build -->

**Why:** Eleven chunks of catalogue, themes and manifests had no human surface. This
is the first one — `/` and `/api/*` over the services that already exist, rather
than waiting for the ones that do not. It takes the catalogue/theme/health third of
the full UI's scope and leaves the discovery two-thirds where they are, because
every one of those binds a service built later.

**The UI checkpoint was held first, and it found something.** Issue #2 was disposed
as tokens-now and component-inventory-deferred: its acceptance list asks for
components covering the candidate review grid and intent entry, and neither screen
is specified, which is why its own stage is `design`. Issue #10 was deferred, and
that one is forced rather than chosen — the second-look shelf shows works accepted
over MCP, `art_review` is declared and unbuilt, so a shelf built now would be a
surface with no producer. The third checkpoint question — does the UI scope still
match the built product — is what surfaced the defect below.

**`assess_display_fit` had no production caller, and could not have had one.** It
was built with tests in the manifest chunk; the review grid is specified to show its
verdict and the rendered size in inches. Nothing anywhere constructed the
`ArtworkBox` it takes, because the box needs a mat width and a resolution floor and
neither had ever reached the deployment surface — `nonfunctional-requirements.md`
specified both in physical units and `Settings` carried neither. Three values joined
`.env` (`MAT_WIDTH_INCHES`, `MAT_BOTTOM_WEIGHT`, `RESOLUTION_FLOOR_INCHES`), and the
resolved box is logged at startup beside the panel it came from.

**The mat's bottom weighting had never been given a number**, only a direction —
"weighted larger than the top". A box height cannot be computed from a direction, so
it had to be settled: 1.15, which is the factor that reproduces that artifact's own
42" worked example exactly (262 px of mat, a 3316 x 1597 box). Checking it against
the 75" row showed **that row is wrong** — its height implies a 1.97 weighting, so
at most one of the two could ever have been right. Corrected to 3546 x 1844, and
both rows are now asserted by tests rather than being arithmetic done once by hand.
The rounding order turned out to be part of the rule and is now stated: whole-pixel
mat first, bottom derived from the rounded top.

**Thumbnails are renditions, not a cache.** A grid of the real files is not a page —
the masters run to 47 megapixels and 40 MB. The downscaled copies are recorded as
`RenditionKind.THUMBNAIL`, which had been in the data model since the catalogue was
designed with nothing producing it, so they inherit the staleness rule that already
governs the television render instead of needing a second one. A replaced master
therefore regenerates the thumbnail rather than serving the previous acquisition —
and because that is only affordable if revalidating is cheap, the route answers a
conditional request with an empty 304 rather than the 1.28 MB below. `FileResponse`
sets an `ETag` and never reads one, so that comparison is the handler's own.
They live in a new `thumbs/`, deliberately **not** `tv-thumbs/` — that directory
holds images downloaded from the television keyed by `tv_content_id`, per-device
state of exactly the class this catalogue was rebuilt to keep out.

**Pillow arrives a chunk early**, named rather than slipped in. It was already this
plane's declared image dependency; nothing in the standard library decodes a JPEG.
Measured on the real corpus: 40 thumbnails in 6.6 s cold, 0.23 s warm, 1.28 MB
against ~1.2 GB of masters.

**The accessibility baseline is enforced, not claimed.** A test reads the real token
values out of the served stylesheet and computes every text and control pair in both
colour schemes against AA, and refuses any colour written outside the token blocks —
because "AA verified" is exactly the sentence that is true the day it is written and
false three edits later. Colour is never the sole carrier of state: every badge
pairs a distinct glyph with a distinct word.

**Resolving the review's own findings changed the surface further**, and the
record says so rather than describing the first version of it. The client now
pages the catalogue to the end instead of stopping at the API's 100-work cap —
which mattered because the theme picker shared that cap, so work 101 could not be
put in a theme at all and nothing said why. An archived work carries a badge of
its own, since the catalogue lists accepted and archived together and a card that
showed no difference was the same silence one screen earlier. A thumbnail that
fails to load falls back to the reason rather than a blank tile, and navigating
moves focus into the new view, without which the surface is not keyboard-navigable
at all.

**Running it found what the tests could not**, for the second chunk running. Two
defects were visible in the first screenshot and in no test: `replaceChildren`
coerces a null to the string "null" and printed the word on the page, and every
image tile silently returned to the shape of its own picture because a replaced
child at `height: 100%` inside a box sized by `aspect-ratio` is circular and the
browser resolves it by letting the content win.

**The verify pass then caught the same defect class inside the fix for it.**
R-4's remedy added an `If-None-Match` helper whose docstring described `*`
handling it did not implement — a false comment, one function after the one a
false comment had just been found in. Implemented and tested rather than deleted
from the docstring. Two notes were also taken: the archived badge was borrowing
the below-floor verdict's CSS class, so two unrelated states painted identically
and would have drifted together; and the client's new paging loop is control flow
no suite executes, which is filed as #30 rather than accepted, because Chunk 19
adds five more stateful screens and several of them spend money.

**One divergence was introduced and caught during the build.** Writing the browser's
"3 of 6 works are on the wall" sentence created a second hand-written version of the
tool surface's. Both now come from `ManifestBuild.summarise()`; only the pointer at
`not_displayable`, which is meaningless outside a tool result, stayed at the surface.
The shared version also fixed a case neither had: an empty theme previously read
"All 0 works in this theme are on the wall."

## 2026-08-01: The wall's own works, re-ingested — and the index read closely enough to argue with

<!-- prawduct: chunks=10 | status=shipped | scope=v1-build -->

**Why:** The v1 scope commits to seeding the new catalogue with the corpus the wall
is already running. Until this landed, no built path put a ready work in the
catalogue before Chunk 18, so the display chunks had nothing to put on a screen —
this is what makes their cutover acceptance executable.

**Counting the corpus changed the chunk.** The plan said 41 works; the index holds
41 records describing **40**. Two are the same painting — same URL, same master,
same title — differing only in the mat colour someone chose for it. Seeding both
would have put one painting in the catalogue twice, which is the thing a minted
identity exists to prevent. They collapse to one work; the operator's call was that
the later record wins and the earlier colour is dropped rather than kept as
superseded history, so the report names the discarded value. This also settles the
"41 records but 46 files in `raw/`" note that had sat unreconciled in learnings: 40
referenced masters plus 6 unreferenced files.

**The index's own parse of its artists is wrong often enough to distrust.** It
carries both the source's words (`artist_details`) and its reading of them, and the
two disagree: Brancusi's stored death year is 1952 where the source text says 1957.
Its parser only understood the newline form, so every parenthetical one — "Georgia
O'Keeffe (American, 1887–1986)" — yielded no nationality at all, as did "American,
born 1930". Reading the words instead and falling back to the stored fields
recovers nine of the fourteen missing nationalities. One record has no
`artist_details` at all and hides the whole clause in the artist's name; the year
is what tells that from an alternate name, so "Juan Gris (Spanish, 1887–1927)"
parses and "Mark Rothko (Marcus Rothkowitz)" is left alone.

**Three artifact claims did not survive contact with the code Chunk 09 built.** The
plan required the two works without physical dimensions to be *excluded* from the
manifest; the readiness rule asks for an original, a mat and a current render and
reads nothing about physical size, and `assess_display_fit` judges an original's
**pixel** size against a box built from panel geometry and a mat width in inches.
Excluding them would have taken two works off the wall that are showing today. The
plan also said those works "can get neither mat geometry nor a floor
classification" (both false) and pointed at an unknown-dimensions rule
`data-model.md` was said to owe (it owes none). Corrected in place, each with what
it said before.

**A measurement in the plan mixed units in a single sentence** — nationality and
`artist_details` counted per record, "8 have no lifespan" counted per distinct
artist. Recounted per work, and a missing *death* year deliberately earns no report
line: two of these artists are alive, and a report that lists complete works is one
people stop reading.

**Everything the catalogue records about a file is measured from the file.** Sizes
come from the JPEG frame header rather than from the index's copy of them, read
with the standard library — so no image dependency arrives a chunk early. The
reader was checked against all 41 masters: every measurement matched what the index
recorded.

**Running it found the bug the tests could not.** Every test one layer down wired
the service itself, so the command handing a *store* where a *service* belongs
stayed green all the way to the first real invocation. That is now covered by tests
that run the command, and the fix was verified by putting the defect back. Against
the real corpus: 40 works from 41 records, 40 masters hashed and measured, and a
second run creating nothing — no duplicate work, no second mat row.

## 2026-07-31: A theme reaches the wall, and says what did not come with it

<!-- prawduct: chunks=09 | status=shipped | scope=v1-build -->

**Why:** The inter-plane contract's producing half. Curation had a full data model
and no way to tell the display plane anything, so nothing the catalogue held could
reach a television. This chunk builds the manifest that will carry it, the theme
operations that shape it, and the directive that steers it.

**The carried finding was closed first, as its own commit** — the third time that
pattern has paid. 08B's review asked for the theme and display concern to come out
of `CatalogueService` before the chunk that grows it; `DisplayService` now owns
themes, membership, the standing directive and the manifest. Both it and
`DiscoveryService` hold the catalogue and neither is held by it: acceptance is a
promotion *into* the catalogue, a theme is a grouping *of* catalogue works. The
suite is the evidence that nothing changed — every test that ran before ran after,
none added and none removed, with
assertions untouched.

**What landed.** The manifest builder: atomic temp-and-rename, schema major 1,
rotation settings with a deployment fallback, label text but never label geometry,
and the directive block carried forward unchanged so a rebuild never reads as an
advance. `art_theme` and `art_display` live with thirteen actions. The TV panel's
physical geometry — never the e-paper panel's — enters configuration and is logged
at startup with the resolved `ART_ROOT`.

**The half that matters is the exclusion report.** Membership in the manifest *is*
catalogue readiness, which is what makes "the wall selects a work it cannot render"
structurally impossible; the price is that a work can sit in a theme and never
appear. So the build names every work it left out, with a cause a curator can act
on. A builder returning only a list would have passed every count assertion in the
suite and still been an incomplete implementation of the design.

**Three things the artifacts had left open, settled where the rule lives.** The
global rotation default is deployment config at 180s on shuffle, carried forward
from what the 2024 wall runs today rather than chosen. "The fetch succeeded" is not
a separate readiness check, because holding an original is what a succeeded fetch
produces — the other reading would take a work off the wall for a failed
*re*-acquisition. And activating a theme publishes it, which `api-contract.md`
already said and the first implementation did not do.

**The store gained a real widening step.** The rotation columns were the first
change to a table that files on disk already carry, and `CREATE TABLE IF NOT
EXISTS` does nothing at all to a table that exists. The intended shape is learned
by running the same DDL against an in-memory database, so SQLite parses the schema
rather than this code. Only additions; a `NOT NULL` addition with no default is
refused outright rather than half-applied.

**Four review rounds, and the last two were about prose that ships.** Two tool tips
described behaviour the service no longer had — `activate` said it did not publish,
`show_now` said only archived works were refused — and neither was visible to a
contract suite that pinned names, schemas and descriptions but never tip text. The
second fix is the recurrence rather than the instance: a table keyed on
`ExclusionReason` now asserts every cause is named in the tip and that its tokens
are distinct, and the service is driven to prove each documented refusal is one the
code actually makes. The first version of that guard shared a word between two
reasons and was green for a case it did not cover, which the next round caught.

`show_now` also widened to refuse any work that could not reach the wall, not only
an archived one: pinning an unrendered work wrote a directive naming something the
manifest does not carry, answered "the directive is written", and the wall never
moved.

## 2026-07-27: The discovery pipeline — five entities, two state machines, one repair

<!-- prawduct: chunks=08B | status=shipped | scope=v1-build -->

**Why:** The half of `data-model.md` that 08A did not carry: everything a work
goes through before it is accepted. Nothing could record what discovery proposed,
what the curator decided about a work or an image, what a run cost, or what to do
with a run whose process died — and the last of those was not a gap in coverage
but a hole in the model, because every terminal state a run had was one its own
process must write.

**The carried finding was closed first, as its own commit.** Two reviewers
independently called out `CatalogueService` — one class over nine entity families
and ~740 lines, about to gain five more. `DiscoveryService` now sits beside it and
a `Services` container binds the two; `create_app`, `dispatch` and the `Binding`
type no longer name a single service class. The helpers both services need moved
to where more than one entity already obeys a rule, so a candidate work and a
catalogued work refuse an empty title in the same words because it is the same
function. Splitting before adding meant the entity work was reviewed against the
shape it keeps rather than tangled with a refactor.

**What landed.** DiscoveryRun (both kinds, all nine statuses), CandidateWork,
CandidateImage, SpendRecord and the ResolveRunWork join — fourteen tables in the
catalogue file, up from nine. Constraints 7–9, 11, 14 and 15 enforced at write
time. Both state machines closed on their illegal edges. Acceptance as promotion.
Startup reconciliation. 405 curation tests, up from 285.

**Twenty mutations, and two of them stayed green.** Every enforcement was removed
in turn and the suite re-run — the same check that found a hole in 08A, run again
because the previous round is not evidence about this one. Eighteen went red.
Two did not, and both are the *same* species as 08A's: a behaviour tested one
layer below where its wiring lives.

- **The container's call to the discovery repair was referenced by no test.**
  `DiscoveryService.reconcile()` had six tests and every one of them passed with
  the call deleted from `Services.reconcile()`. This is 08A's constraint-10 defect
  exactly, one chunk later, in the code written by someone who had just written
  the learning about it.
- **The instance ranking passed because the store's listing order agreed with
  it.** Replacing `selection.best` with "take the first the store returned" left
  the suite green — the store orders a review card by confidence, the ranking
  orders by confidence, and the quality tie-break that separates them was never
  exercised. Two policies coinciding today is not one policy.

**`interrupted` had to exist before the double-spend guard could be safe.** A
work is refused to a new resolve run while any run covering it is non-terminal.
Every terminal state except `interrupted` is written by the run's own process — so
without startup reconciliation, one OOM kill would refuse those work ids for the
life of the catalogue, silently, on the only operation that spends money. The two
features are one feature, and the test that proves it kills a run mid-re-search
and then re-searches the work.

**`awaiting_approval` is excluded from that repair, and the reason is the deploy
step.** It advances when the *curator* approves, not when a process runs.
Reconciling it would let `systemctl restart` destroy a pending decision along with
the phase-1 spend already incurred to produce it, and curation is restarted
constantly during development.

**Two model gaps surfaced while implementing promotion, and were written down
rather than settled in code.** `data-model.md` says the candidate-side and
catalogue-side shapes mirror each other "so acceptance is a promotion rather than
a transformation" — and every `Source` field did have a counterpart except
`acquisition_method`, which is `NOT NULL`. So the claim was very nearly true and
the exception fell on the field that says how to fetch the bytes; a guess there
surfaces as a re-acquisition failing at the moment every derived file has already
been lost. It is now carried on `CandidateImage`, where the search that found the
instance is the only thing that knows it, and the artifact gained a field-by-field
promotion table so "mirror rather than transform" is checkable instead of
asserted. Separately, `DiscoveryRun.started_at` is narrowed from nullable: a row
is only created by starting a run and both entry states are active, so nullable
would have made every reader handle an absence that cannot occur.

**Ambiguity implemented literally and named rather than quietly narrowed.**
`api-contract.md` says rejecting an image moves the work to
`awaiting_better_image`, unconditionally. That includes rejecting an *alternate*
while the instance actually on offer is fine — arguably not what a curator means,
but the narrower rule is written nowhere and inventing it here would be inventing
a requirement. Implemented as specified, flagged for whoever revisits the review
flow.

**The cumulative round: 2 blocking, 9 warnings, 7 notes over 104 files.** Both
blocking findings were bookkeeping rather than code — a build-plan path missing
its `curation/` prefix, so the one mechanical pointer handed to whoever widens the
`themes` table resolved to nothing; and Chunk 06's "`r` renamed" deliverable,
never done and, unlike that chunk's three other shortfalls, never recorded. The
file is now `deploy/pi-freeze-2024.txt` and says what it is.

**One warning was against shipped behaviour and it was mine.** `fail_run` and
`halt_run_for_budget` refused only terminal states, so both were reachable from
`awaiting_approval` — and a test of mine was asserting one of the undrawn edges.
Resolved in both directions: phase 1 makes model calls and searches the web, so it
really can break and really can be refused credit, and `data-model.md` now draws
those endings from both working states; they are refused where nothing is
executing. `cancelled` stays available everywhere active, because wanting a run
gone is not declining it.

**The store was speaking one domain's language on both error paths.** `durable.py`
answered "it is already in the catalogue" for every table — including, after this
chunk, for a `CandidateWork`, which is precisely *not* in the catalogue, in a
message that reaches whoever asked. The rationale for that wording was written
when the store held one domain and was not revisited when it gained a second. A
layer that cannot see which table it refused must not name one.

**Two more retired claims that outlived their amendment**, both the shape
`learnings.md` already records as a repo-wide grep obligation: the 3tears
withdrawal was swept through the dependency lists but not through
`observability-strategy.md`, which still named `3tears-observe` as the source of
curation's structured logging — so the artifact calling structured logs the
primary signal rested on a package no manifest carries, and the log shape had no
owning chunk. It has one now. And `envelope.py` still opened with the "iff
`success` is false" reading its own `is_error()` does not implement.

**Deferred deliberately, and recorded rather than quietly dropped:**
`CatalogueService` is still 743 lines over nine entity families — 08B added a
sibling rather than decomposing it, which is what the carried task asked for and
not what it was worried about. Extracting the theme and display concern is now
Chunk 09's first task, landing immediately before the chunk that grows it, which
is the sequencing that just worked here. The MCP session table gained an idle
timeout (it had none, on an always-on unit with a `MemoryMax` cap). Three
findings about backlog routing need the operator: they turn on creating issues on
a public repository.

**Artifacts brought level with the code**, since both described a service layer
with one service in it: `architecture.md`'s internal-layering diagram (now two
services under a container, two adapters over one connection),
`boundary-patterns.md`'s service-layer and catalogue-schema entries (fourteen
tables, all fifteen constraints, both state machines), and the build plan's
project-structure comment, which still said persistence was "3tears L1
collections" — a claim 07B retired and this is the first pass to have touched the
line since.

## 2026-07-27: The accepted catalogue — five entities, nine rules, and the directive's home

<!-- prawduct: chunks=08A | status=shipped | scope=v1-build -->

**Why:** Chunk 08 as authored was the whole of `data-model.md` beyond the three
entities Chunk 07 proved — eleven entities, fifteen constraints, three state
machines and startup reconciliation, an estimated ~2,500 lines. That is one
Critic round over a diff large enough that review quality degrades, on the most
contract-setting chunk in the plan. **The operator chose to split it**, and the
line is the one the model already draws: the accepted catalogue here, the
pre-acceptance pipeline in 08B. Nothing is descoped — every entity, constraint,
state machine and acceptance question appears in exactly one half. The 07/07B
precedent is the evidence: two of that split's five defects were unreachable from
the smaller surface and were found only because the smaller surface was reviewed
on its own.

**What landed.** Five entities — Source, Original, Rendition, MatColor,
ThemeMembership — plus the Directive singleton, taking the catalogue file from
three tables to nine. The Artwork state machine (`archive`/`restore`, both
illegal edges refused). Constraints 1–6, 10, 12 and 13, each enforced at write
time in the service layer. `display_fit` as one service-layer function that
stores nothing.

**"Each constraint has a test that fails without it" was checked rather than
claimed, and the check found a hole.** Every one of the nine enforcements was
removed in turn and the suite re-run. Eight went red immediately. Constraint 10
did not: `description_markup` had thorough tests of its own, and nothing asserted
that `add_artwork` ever *called* it — so deleting the call from the service left
the suite entirely green. A normaliser nothing calls is the same defect as no
normaliser, and it looks identical from the normaliser's unit tests. Two tests
now cover the wiring, and the mutation re-run confirms they fail without it. This
is the previous cycle's learning applied forward: a claim about what the tests
pin is worth as much as the run that establishes it.

**Persistence gained a transaction seam, and it is conformance rather than
divergence.** Three of the rules span rows — exactly one theme active, exactly
one mat colour current, at most one primary source — and each is applied as a
clear-then-set pair. A pair interruptible between its halves leaves the catalogue
in the state the rule forbids: no active theme at all, and so no sync target for
the display plane. The matched framework contract threads a `conn` transaction
handle through every method for exactly this reason; this store has one
connection, so `transaction()` is the same capability with the handle implicit.

**A correction to what the previous entry claimed.** That entry said the durable
store matched the framework protocol's "decomposition, naming and argument
shape". The first two hold; the third does not, and did not when it was written —
the framework's signatures also carry `conn` and `cas`, and its `pk` is optional
where this one requires it. The module docstring now enumerates each difference
and why it is taken, instead of asserting a parity the code does not carry. This
is the fourth round in a row where the defect was a sentence claiming slightly
more than the thing it described.

**The carried finding is closed where it was raised.** The directive sequence was
pinned as catalogue-side by `architecture.md`, is restored by the exercised
restore path, and had no entity in `data-model.md` — an unmodelled part of a
persisted format is one the next chunk invents implicitly. It now has one, with
its singleton row seeded by the schema so no caller ever creates it. The pin's
clearing rule, which the finding also named as unstated, is settled and recorded:
`next` supersedes it, archiving the pinned work withdraws it **without advancing
the sequence**, and nothing else clears it — an advance on archive would fire a
directive nobody issued.

**Two gaps in `data-model.md` were found by implementing it and are now fixed
there, not just in code.** `MatColor` had no timestamp while the paragraph beneath
it required the history to be reviewable and reversible; "which colour did the new
model replace" has no answer in a set of rows with no order. And the Directive
entity above. Both are marked in the artifact as added at build.

**One test's assertion was inverted, deliberately.**
`test_a_theme_starts_inactive` asserted that a new theme is inactive. That
described `Theme.is_active` as it shipped in Chunk 07 — a column the build plan
explicitly recorded as having "no exactly-one enforcement behind it", deferred to
this chunk. Constraint 1 now governs it and says the opposite: a catalogue holding
themes with none active gives the display plane nothing to sync, and nothing
reports it. The test is renamed, keeps its location, and carries the reasoning for
the inversion in its own docstring.

**Two Theme columns were deliberately not added.** `rotation_interval_seconds`
and `shuffle` exist in the data model and are consumed by the theme manifest,
which Chunk 09 builds. Adding them here would be the first change that widens a
table an existing catalogue file already has — a migration to write rather than a
column to append quietly — and nothing reads them until that builder exists. They
land in Chunk 09 with the migration they need; a test asserts the current file
gains new *tables* on open, and says in its docstring that the next widening will
not have that luxury.

**Product verification found a defect the tests had not.** Driving a real
catalogue on disk showed the description normaliser dropping a `<script>` tag but
keeping its contents, so a scraped page's script source would have reached the
physical label as visible text. Unknown tags are unwrapped and their text kept —
right for `<span>`, wrong for code. Fixed, with tests for both the closed and the
unclosed case.

**295 tests pass across both suites** (283 curation, 12 root), up from 154. Ruff
and black clean. The real server was launched against a scratch `ART_ROOT` and
wrote a catalogue carrying all nine tables and its seeded directive row — verified
by reading the file the server itself wrote, not one a test wrote.

**The Critic ran `cumulative` over the whole branch: 0 blocking, 17 warnings, 10
notes.** It found one real defect in this chunk's own work, fixed here: **a
catalogue written before 08A upgrades into a permanent violation of the rule 08A
added.** The earlier revision created every theme inactive and shipped no way to
activate one, so such a file holds themes with none active — and nothing repaired
it, because the index the file carries states only "at most one", which zero
satisfies. `CatalogueService.reconcile()` now runs as the plane starts, promotes
the oldest theme, and logs one WARNING, because a silent condition being corrected
should say so. The read-compatibility fixture was complicit and is corrected too:
it wrote an *active* theme, a row shape the earlier revision could not produce, so
the only shape that actually exists on disk was the one nothing tested.

Also closed from that round, in this chunk's own code: `_detail` was dead and
byte-identical to `get_artwork`; an original exactly the size of the artwork box
was reported `matted_small` where both the data model and the enum's own docstring
call that `native`, now pinned from both sides; `pydantic` and `httpx` were
declared with no consumer in a manifest that states twice that the declared set
describes what the code imports; and `architecture.md` gained the two structural
patterns this bundle established — the persistence seam and the generated action
surface — plus the Decision Log entry the durable-tier answer had earned
everywhere except there.

**Ten of the seventeen warnings were one defect: artifacts describing the repo as
it was before this branch changed it.** Two still asserted the repo has no test
suite, in the bundle that established two. `project-preferences.md` — the norm
index, where staleness decides whether a rule is enforced by a linter or by a
human — still said "once ruff lands" for rows ruff now covers, still described the
pre-hoist `config.py`, and had no row at all for "no secret ever reaches a log
line". `security-model.md` still told an operator to schedule hardware access for
a coupling this branch removed. All swept, each with the retired sentence quoted
so the correction is legible rather than invisible.

That cluster is the repo's own escalated learning recurring inside the bundle that
recorded it — *"retiring a claim is a repo-wide grep, not a local edit"*. Two of
this chunk's own corrections were the same shape: the 07B parity claim was fixed
in the module but left standing in the canonical decision record and the build
plan, and the correction itself said "every framework method takes `conn`" when
`scan` does not.

**A second `verify-resolutions` pass then found the same defect class one round
later, in the fix for the first one.** `reconcile()` had five tests; the *call* to
it in `main()` had none, so deleting the line left all 288 green — verbatim the
thing this entry had just described catching by mutation. The test that closes it
drives `main()` with uvicorn's run captured and reads the catalogue through a
second connection at the moment the server would start, so it pins the ordering as
well as the call; verified by removing the line and watching it go red. Two notes
from the same pass are closed with it: `ArtworkListing.limit` was set and never
read, and now names itself in the truncation notice, because "raise limit" is
advice a caller cannot act on without knowing what the limit currently is; and
`operational-spec.md` still opened its section with the retired 3.14 thesis in
bold, with the correction twenty-five lines below it and worded as though the
stale text were underneath.

**A third pass returned 0 blocking, 0 warning, 1 note, and the note found a real
edge the reworded message had sharpened.** Naming the limit made "raise limit"
concrete — and therefore wrong at the ceiling, where `MAX_LIST_LIMIT` is enforced
in both the service and the tool schema, so a caller at 100 was being told by name
to raise a number that returns an error. The notice now says "the maximum" and
points at `offset`, which is on the same action and does work. Pinned from both
sides of the ceiling.

**A fourth pass closed the last two, and both were the same defect walking
forward one step at a time.** Making the notice name the limit made it wrong at
the ceiling; fixing that made it recommend `offset` while its own counts still
ignored `offset`, so a caller who took the advice saw the identical sentence at
every page. The notice now reports the position — "showing 5-8 of 10" — and the
payload echoes the `limit` and `offset` that produced it, so a page describes its
own place in the set. The binding test that had been parked in the service-layer
file, whose docstring declares it independent of any surface, moved to a
`test_bindings.py` of its own; the binding layer is where the thin-binding norm is
enforced, and its tests living in a file that disclaims it is how that boundary
stops being legible. Nothing covered a truncated page at a non-zero offset; four
tests do now.

**A fifth pass found the same lesson a third time, one layer higher.** The
payload's new `offset` echo was asserted only at zero — which is also the
binding's own default, so the assertion held even if the argument were dropped on
the floor, and nothing anywhere passed a non-zero offset through the MCP surface.
That is the affordance the notice now steers a model into, and it was the one hop
never exercised. One integration call at `limit=1, offset=1` closes it, verified
against both mutations: dropping the argument and hard-coding the echo each turn
it red.

**One warning is recorded rather than resolved.** Seven backlog items were filed
into `.prawduct/backlog.md` after `project-state.yaml` declared it frozen and
repointed the live backlog at GitHub Issues, so the tooling cannot see them — two
of them, a mistyped `ART_ROOT` bootstrapping a healthy-looking empty install and
the missing Origin validation on `/mcp`, have no live tracking home at all.
Re-filing them means creating issues on a public repository, which is the
operator's call; the file now carries a note naming all seven so nothing is lost
while that decision is pending.

## 2026-07-27: The durable seam — persistence split, and the 3tears swap answered

<!-- prawduct: chunks=07B | status=shipped | scope=v1-build -->

**Why:** Chunk 08 widens the catalogue from three entities to fifteen. Whatever
shape the persistence layer has when that starts is the shape twelve new entities
get written against, so the backend question had to be settled first.

**The 3tears swap was scoped down to the durable tier, and the collection layer is
now deferred indefinitely rather than scheduled.** Reading the framework before
building against it retired the plan's target configuration and its stated reason
at once: L1 is a *named in-memory* database, so "L1-only SQLite" persists nothing
across a restart; 3tears ships no SQLite `DurableStore` (only asyncpg), so the
durable tier is this product's own code under every configuration; and collections
are async throughout with no query API, so adopting them converts three layers to
async — against the ratified "async at the I/O boundary, synchronous core" — while
listing still has to bypass the collection. The recorded reason to adopt anyway,
"the on-ramp to agents later", does not survive either: `3tears-models` depends
only on `media-contracts` and `observe`, never on `core`.

**What landed instead.** `persistence/durable.py` is a generic store — tables,
keys, rows — matching the `DurableStore` decomposition, naming and argument shape
so a future collection layer is an adapter rather than a rewrite. `sqlite.py` is
now the domain adapter above it, owning the schema, the record mapping, and the
ordering and paging that are product judgements rather than storage ones. No
framework dependency is taken, which also **withdraws** the develop-branch git
reference the previous record had accepted: an unreleased moving branch buys
nothing when no framework code is called.

**A refactor, held to that standard:** 154 tests pass across both suites (104
pre-existing — 92 curation, 12 root — none modified or weakened, plus 50 new).

Two of the three acceptance criteria are now pinned by a test that fails when they
stop holding: read-compatibility with an older catalogue, and the rule that inside
`curation/src` only the durable store imports `sqlite3` — the latter a structural
test walking that tree, because a stray import in a service or a binding would
dissolve the seam while passing every behavioural test. (Tests are outside its
scope deliberately; one of them reaches for the driver to inspect a file
directly.) That is the same reason
`tests/test_repo_hygiene.py` exists, and the same reason it is worth doing now:
Chunk 08 writes twelve entities against this package. The third criterion — that
no existing test was modified — is a property of the diff rather than of a run,
and stays evidenced by review of the change set.

Read-compatibility with catalogues already on disk is carried by a standing test,
`test_a_catalogue_written_by_an_earlier_revision_still_reads`, not by prose: it
builds a file from the previous revision's DDL and INSERT statements, frozen as
literals so they cannot drift with the code, then reads it back through the
current `SqliteCatalogue`. What it asserts, precisely: every column of one artist
and one artwork; a second artist with all five optional columns null; a second
artwork carrying the other `ArtworkStatus` value and the absent instant; a second
theme carrying the false side of the integer-to-bool mapping; the case-insensitive
title and name orderings; and one unpaged total. It was mutation-checked in both
directions — dropping the case-insensitive sort and mis-mapping a single column
each turn it red.

**One behaviour did change, and "refactor" should not be read as covering it:** a
refused write now logs twice rather than once, because the split put the record's
identity and the SQL cause in different layers — `durable.py` journals the table
and the driver text, `sqlite.py` journals which record was refused. That is the
answer to a prior review's finding that the refusal line no longer named the
record; the message returned to the caller is unchanged.

**Five defects surfaced, all in code paths the split newly exposed** — four by
writing the tests the old code never had, the fifth by probing the new store
during review: a partial composite key answered `fetch_one`
with whichever row sorted first rather than refusing; an `ON CONFLICT` target that
is not the table's real key would have made `update` insert duplicates; `offset`
without `limit` was silently discarded, because SQLite takes no OFFSET without a
LIMIT; requiring the whole key on a *plain insert* was over-strict, since that
path reaches no key at all; and filtering for an unset column rendered `= NULL`,
which is never true in SQL, so a scan for "the rows with no artist" answered
"none" whether or not any existed. The constraint-refusal translation — which
decides whether a duplicate id and a missing artist read differently to a curator
— had never had a direct test in any form.

Four of the five are the same failure in different clothes: **an answer that is
wrong but shaped like a right one**, which no caller can detect. That is the class
this layer now refuses by construction, and it is why the split was worth doing
before twelve more entities were written onto it — the nullable-column bug was
unreachable from today's three entities and would have shipped inside Chunk 08.

The null fix then had to be **scoped to filters only**, which review caught before
it landed: the same rendering helper serves the key paths, and `IS NULL` on a key
column reintroduces exactly the failure it had just removed — SQLite does not
enforce NOT NULL on a `TEXT PRIMARY KEY`, so a null key component can match
several rows and `fetch_one` would return an arbitrary one. A null is a legitimate
filter value and an illegitimate key value; the store now says so explicitly.

**Found while verifying, and fixed here:** the change-log carried no tagged entries
at all, so `prawduct-hook regen-views` unchecked chunks 01, 02, 06 and 07 in the
build plan's derived Status block. The chunks below backfill that evidence.

## 2026-07-27: Chunk 07 — the walking skeleton, end to end

<!-- prawduct: chunks=07 | status=shipped | scope=v1-build -->

**Why:** Prove the layers connect — catalogue core, service layer, registry,
generated MCP tool over streamable HTTP — before anything widens onto them.

Landed across `4508cd3`, `bfafb70` and `e379529`. A real MCP client lists five
tools over HTTP and reads a seeded catalogue. The `final` Critic round returned 0
blocking, 21 warnings, 9 notes; fifteen were fixed in the same pass and verified by
two `verify-resolutions` deltas, and six were routed to the backlog. One contract
rule was retired rather than quietly broken — "an unknown *tool* stays a protocol
error" is not implementable on the official SDK, whose `call_tool` handler converts
every exception to a normal error result.

## 2026-07-27: Chunks 01, 02 and 06 — hygiene, deployment values, and the curation plane

<!-- prawduct: chunks=01,02,06 | status=shipped | scope=v1-build -->

**Why:** Clear the security and configuration debt blocking a build, and stand up
the plane Chunk 07 needs.

Landed in `ba007cd`. Collapsed into a single commit rather than six governed cycles
at the operator's direction — the ceremony was on track to cost more than the work,
and that stands as the working rule for mechanical chunks while contract-setting
ones keep the full treatment. Three deliberate deviations are recorded in the build
plan: no token rotation (the leaked token is expired), no `display/` project (not
needed until Chunk 12, and its dependency set is what Chunks 04–05 must verify on
hardware), and no mat regression fixture (consumed in Chunk 18).

## 2026-07-20: Last blocking finding closed; remaining warnings routed to their chunks

**Why:** R-10 was the last blocker and the only one needing an operator decision.
Closing it clears the plan to build.

**R-10 — `CandidateWork.verdict` had two writers and no rule between them.** The
curator writes it through `art_review`; a resolve run writes it on completion.
Nothing ordered them, so a resolve finishing after an accept wrote `pending` over
`accepted`, leaving a work with an `artwork_id` and a non-accepted verdict — a
combination nothing else in the model can produce or repair. Constraint 14 does
not cover it; that guards run *creation*, not the write at completion.

**Decided (operator, 2026-07-20): terminal verdicts win.** A resolve run writes
`pending` only if the work is still `awaiting_better_image` when it finishes;
otherwise its result is reported, not applied. The guard sits on the run's
completion write rather than on `set_verdict`, which stays available at all times
— **a curator must never be blocked on a background job.** The alternative
(refusing verdicts during a resolve) was rejected for that reason, and because an
interrupted run would strand the work.

The state machine also gained two edges it always had in practice: `set_verdict`
constrains its *target* value, never its source state, so `awaiting_better_image →
accepted` and `→ rejected` were reachable and unmodelled. Both are now drawn, and
Chunks 16 and 17 carry the tests.

**Remaining warnings routed, not dropped.** Per the operator's cadence decision —
build now, review at the checkpoints rather than every chunk — the twelve surviving
warnings were written into the chunks that own them, where a builder meets them,
rather than collected in a list nobody reads at the point of work:

| Finding | Owner |
|---|---|
| Mat worked examples imply two different bottom-weight rules | Chunk 18, before the mat engine |
| "No secret may ever reach a log line" has no mechanism | Chunk 02, which writes the startup logging |
| Chunk 13 has a Foreign API with no verify-api (04 verified the *build*, not the display surface) | Chunk 13, new step 0 |
| Directive sequence counter has no modelled home | Chunk 08 |
| Archiving a work has no specified manifest effect | Chunk 09 |
| Health panel omits the fields the failure table maps onto | Chunk 19 |
| `tile-cache/`, `api-cache/` have no lifecycle owner | Chunk 18 |
| Stale `deploy/README.md`; three wrong `depends_on` headers | Chunk 20 close-out |

R-6 (no test evidence) resolves when Chunk 02 lands the first suite; R-8 (tracked
token) is Chunk 01 and is why Chunk 01 is first; R-17/R-24 (revisit triggers for
the alpha and dormant pins) belong at the post-Chunk-06 checkpoint.

**No product code changed.**

## 2026-07-20: Second Critic round — two blocking closed, and one of my own claims retracted

**Why:** The review of the revised plan returned 3 blocking. Two are closed here;
the third (R-10) needs an operator decision and is not silently absorbed.

**R-1/R-21 (blocking) — the spend ceiling had no owner.** The v1 scope commits to
a "hard monthly LLM spend cap that fails closed" and the security model rates it
bound #1, *Strong*. Every chunk covered only the consumption half. Because the
ratified norm forbids an application-side ceiling, the unprovisioned key *was* the
absence of any ceiling. Chunk 14 now provisions the USD 20/month per-key limit,
adds `OPENROUTER_API_KEY` to `.env.example` (which still declared only the legacy
`OPENAI_KEY`), and — the part that matters — **proves the 402 fails closed with a
near-zero-limit key rather than asserting it**. `boundary-patterns.md` no longer
lists the ceiling as deployment config, which had invited the very
application-side enforcement the norm forbids.

**R-9 (blocking) — "panel geometry" named two different physical panels.** The TV
panel (physical inches; drives mat geometry and the resolution floor) and the
Waveshare e-paper HAT (1448×1072; drives label typesetting) were one config value,
and two artifacts concluded from the conflation that *display renders the mat* —
it does not; curation composes the mat into the `tv_display` rendition. That made
`architecture.md` self-contradictory and produced a false "two values must agree
across both planes" analysis. Separated: TV geometry is curation's alone, e-paper
geometry is display's alone, **neither is shared, so neither can drift** — the
cross-plane mismatch risk dissolves rather than needing mitigation. `ART_ROOT` is
again the only shared value. Swept through architecture, operational-spec, and
five build-plan sites.

**R-2 — a claim of mine, retracted.** Chunk 10 said all 41 legacy records carry
seven named fields, "verified 2026-07-20". I had measured four. Measured properly:
**14 of 41 have no nationality, 8 no lifespan, 8 no `artist_details` at all** — the
field the chunk's own unit test was written around — and 2 each lack medium and
physical dimensions. The chunk now states the real numbers and specifies the
consequences: Artist parsing falls back to the flat `artist` field, labels render
with dates absent, and the 2 dimensionless works seed with nulls and are reported
rather than excluded silently. The acceptance criterion changed too — it had
required an *empty* exclusion report, which the data cannot produce.

**R-4/R-18 — the uv workspace decision was mechanically impossible.** Recorded as
settled in two homes: "two projects in a uv workspace, each with its own
interpreter and its own lock". A uv workspace has one lockfile and one resolved
interpreter. Verified rather than reasoned: against uv 0.11.8, a workspace whose
members declare `>=3.14` and `==3.13.*` refuses to lock — *"error: Found
conflicting Python requirements"*. The decision's substance was always per-plane
interpreter and per-plane lock; only the mechanism was wrong, and it is amended to
two sibling projects. The build plan had hedged toward this; it is now settled with
evidence, so Chunk 06 builds a decided shape instead of rediscovering it.

**R-7, R-14 — two settled questions still written as open** (MCP resources in
`api-contract.md`; the curation host in `nonfunctional-requirements.md`, both
homes). The repo's signature defect, and cheap. `api-contract.md` is what an
implementer binds, so a live "open question" there invites re-opening settled
scope.

**R-19 — the sweep failure this session created.** Moving issue #8 upstream left
four stale pointers in `learnings.md` — the escalation document was the one home
its own remedy missed. Swept. `change-log.md` and `reflections.md` were left
alone deliberately: they are dated records, and rewriting them would falsify
history rather than correct a live claim.

**Still open — R-10 (blocking), for the operator.** `CandidateWork.verdict` has two
writers and an incomplete transition set: a resolve run completing after an accept
can write `pending` over `accepted`, leaving `artwork_id` set on a non-accepted
work. Fixing it is a behaviour decision, not a coherence fix, so it is not being
absorbed quietly.

**No product code changed.**

## 2026-07-20: Plan revised on review — seeding chunk added, governance check moved upstream

**Why:** A pre-build review of the Phase D plan against the open Critic round
found three things worth fixing before any code, and one worth moving out of the
product entirely.

**The blocking gap (Critic R-1, with R-9 as the same defect seen from the other
end):** the v1 scope commits in three places to a catalogue "seeded with the
existing 41 artworks", and no chunk implemented it. That was not a bookkeeping
miss — it made the display chunks unbuildable as written. Manifest membership
requires readiness, the only chunk producing originals/renders/mat colours was
18, and the cutover chunks accept on "theme on the wall" at 12–13. There was no
product path to any wall content. **New Chunk 10** owns the re-ingest, placed
after the manifest builder so seeding is proven by the manifest it produces.
`all.json` was checked before scoping it: all 41 records carry metadata,
`raw_file`, `mat_hexrgb`, and pixel dimensions, so the chunk is an ingest, not a
re-acquisition.

**A gap the Critic did not find:** all 41 records also carry `tv_content_id` —
the works are already uploaded to this TV. A fresh empty TvBinding table at
cutover would re-upload 41 4K images and orphan the existing set. Chunk 12 now
carries a TvBinding adoption path, verified against the TV's own list rather
than trusted, since a stale content id must re-upload normally.

**Issue #8 moved upstream, not dropped.** The decision-amendment
acknowledgement check was Chunk 01. It reads only prawduct's own data model
(`technical_decisions` markers, the `artifact_manifest` graph), so building it
here would have made this repo the maintainer of framework tooling while every
other prawduct repo re-solved it. Filed as `brookstalley/prawduct#136` with the
thirteen-recurrence evidence and the five cause classes; #8 is closed `dropped`
(not `shipped` — no work landed here). **The obligation it was to mechanize
still binds**: amendments sweep by hand per the learning, and Chunk 15 — the
plan's largest amendment burst — says so explicitly. Chunk 01's other
deliverable, the repo's first `tests/` bootstrap, moved to Chunk 02 rather than
leaving with it; that is the chunk where the first testable code appears.

**Renumbering:** with Chunk 01 gone and a new chunk at 10, old 02–10 shifted
down to 01–09 and old 11–20 kept their numbers. Done as one scripted pass over
137 reference runs, then audited — the pass missed one dependency line where a
parenthetical broke the number run (old Chunk 12's deps), caught by a bare-number
sweep. Roster, Status block, and every internal reference verified consistent;
`verify-chunk-refs` and `regen-views --check` both green. Nothing external
referenced the old numbers (no shipped chunks, no `chunks=` tags), which is why
renumbering was safe to do now and would not have been later.

**Critic R-14:** `build-plan` is now registered in `artifact_manifest` with the
edges its own front matter declares, and the "still owed" comment is struck.
Left unfixed, the plan — the most decision-dense artifact in the repo — stayed
invisible to exactly the dependency walk the repo relies on.

**Also fixed, being cheap and in the same place:** R-3 — the legacy dezoomify
`shell=True` invocation is now explicitly barred from being ported forward,
since discovery-sourced URLs are attacker-influenceable by the security model's
own reasoning; Chunk 18 requires argv-list invocation, scheme allowlisting, and
a test that asserts on the argv actually passed rather than on the absence of a
crash. R-2 — Chunk 18's verify-api step covered only the vision model while the
chunk declared dezoomify as a Foreign API too; step 0 now probes both, with
dezoomify's CLI contract captured from the installed binary rather than inferred
from the 2024 call site.

**Deliberately not fixed now:** R-6, R-7, R-8, R-11, R-12, R-13 are design
details that bind at the chunks that consume them (08/09/16/17), and are better
resolved with code in hand than by another artifact pass. R-5 (stale test
evidence) resolves itself when Chunk 02 lands the first suite. R-4 (the live
token) is Chunk 01 and is the reason it is Chunk 01.

**No product code changed.**

## 2026-07-20: Phase D — the v1 build plan authored

**Why:** Every artifact question was closed and the checkpoint review's spine was
endorsed; what remained was the plan itself. `artifacts/build-plan.md` (scope
`v1-build`) now carries twenty dependency-ordered chunks on the evidence-first
spine: groundwork at the hardware (issues #4, #5, #15, #16, plus the #9 and #3
verifications) → two-plane restructure → a walking skeleton through
catalogue/service/MCP → full catalogue and manifest → contract tests (#17, #7) →
display plane and cutover → discovery with its two spikes (#12, #18) → UI and the
exercised restore (#14) last. Issue #8's amendment-acknowledgement check is
Chunk 01, per the escalation argument (thirteen recurrences, none caught by the
author's own check). The plan declares `governed_by:` with per-norm dispositions
for the four norm-carrying artifacts — seeded with `prawduct-hook jurisdiction`,
curated to the artifacts that actually bind. Issue #6's four defects are
dispositioned in the plan (fix one now, two die with the rewrite, one deleted).
Requirements Confidence: Medium, with each named unknown tied to the early chunk
that resolves it; the operator's #13 storage decision is flagged as the one
pending input, gating Chunk 04.

**No code changed.**

## 2026-07-20: Checkpoint review landed; Critic cumulative round remediated

**Why:** The operator asked for a big-picture design checkpoint before Phase D.
The review's verdict — the design is right for the scope — landed with four
findings, each fixed in its single home: phase 1 is search-capable (a text-only
call cannot serve the Vision's own "recent award-winning work" example), the MCP
review gate's enforceable claim is "the image was there to see" rather than "a
human saw it", three directive-block semantics were pinned (monotonic sequence
across rebuilds, persisted last-acted-on value, latest-wins coalescing, plus a
regression re-baseline rule from Critic R-7), and `all.json` is retained as the
mat regression fixture. Nine backlog items filed (#10–#18), #3 and #8 annotated.

The Critic's cumulative round (1 blocking, 2 warnings, 8 notes) then found the
tenth and eleventh recurrences of the sweep-failure class: three surviving sites
of the retired "single consumer, deployed together" versioning exemption
(api-contract twice, `api_versioning_approach` in project-state — R-19's
enumeration partially consumed, again), and the rights decision's miss of
`security-model.md` plus a dangling pointer in `data-model.md`. All struck;
panel geometry's authoritative home clarified as configuration (not
display-state); `label/` retired from the prospective ART_ROOT contract; the
deploy/README `OnFailure=` prescription withdrawn as contradicting the recorded
alerting decision. Tally refreshed to eleven in learnings.md and issue #8 —
then verify-resolutions found recurrences twelve and thirteen *in the
remediation itself* (the gate-criterion amendment unswept to project-state's
goals and an api-contract quote; R-8's fourth enumerated home, the learnings
data-contract section, unconsumed). Both struck same day; **final tally
thirteen**, reconciled in learnings.md entries 11–12, this entry, and issue #8.

## 2026-07-20: Narrow the reconciliation rule, add `interrupted`, and sweep the sites the finding named

**Why:** `verify-resolutions` closed all six blocking findings from the previous
round but found the crash-lifecycle fix **over-reached**, then a further pass found
the correction had landed in only one of the three artifacts that carried the rule.

**The over-reach.** The edge was `any non-terminal ──▶ failed`, justified by "a run
only advances while its owning process is alive." True of `resolving_works` and
`resolving_images`; **false of `awaiting_approval`**, which advances when the
*curator* calls `approve` — durable, human-held state that is meant to outlive a
restart. As written, `systemctl restart` (the documented deploy step) would silently
destroy a pending approval and the phase-1 spend behind it, and curation restarts
constantly during development. **A rule justified by process liveness must apply only
to the states process liveness governs.**

**`interrupted` is now its own terminal state**, not a flavour of `failed`: "stopped
underneath it" and "something broke" call for different responses — re-run versus
investigate — which is the discriminator test already applied to `halted_by_budget`.
`api-contract.md` carries it, since an agent that can't tell them apart will either
retry a real fault forever or escalate a routine restart as a bug.

**The terminal-state count is now unstated.** It read "four" while listing five, then
"six" while another sentence 21 lines away still said four. A number maintained by
hand in prose gets it wrong; the rule doesn't need the count.

**The seventh recurrence, and its root cause is sharper than the previous six.** The
finding that produced the fix **named three files**. I fixed one. My pass-3 grep used
the literal strings from the artifact I'd edited, and `architecture.md` phrased the
same rule differently — the paraphrase blindness pass 2 exists to catch, which I
skipped because I believed passes 1 and 3 had covered it. `operational-spec.md` was
worse than stale: it told the operator that a non-terminal run with no work happening
means reconciliation is broken, which had become the exact description of a *healthy*
run waiting on the curator.

**Correction added to `learnings.md`: when a Critic finding lists files, that list
*is* the sweep set.** No graph walk was needed — the answer was handed over and a
third of it was used.

**Also:** the observability cross-reference was made true rather than deleted;
`resolve_images`'s operator-recovery row now distinguishes healthy-waiting from
stranded; constraint 14's "every terminal state is written by the run's own process"
corrected, since `interrupted` is precisely the exception; PEP 517 verification filed
as **issue #9** rather than claimed as "tracked".

**Files:** `data-model.md`, `architecture.md`, `operational-spec.md`,
`api-contract.md`, `observability-strategy.md`, `project-preferences.md`,
`project-state.yaml`, `learnings.md`.

## 2026-07-20: Address Critic findings — the crash lifecycle, the token order, flow 4, and a decision recorded in only one home

**Why:** Cumulative Critic (`rev-20260720T160759Z-cbc0d27e`, 3 reviewers) returned
6 blocking (4 distinct — two found independently by two reviewers each), 15 warning,
10 note.

**The security finding is the one to read.** `security-model.md` prescribed *rotate
first, then untrack*. That order creates a **second leak**: rotating while the file
is still tracked puts the freshly-issued token into a tracked file, and the next
`git add -A` commits it — this session alone ran that command eight times. The old
order was argued from *perception* ("untracking first looks like it's been dealt
with"), which honest prose already answers. Corrected to untrack → re-pair, and
`token_file` added to `.gitignore`.

**A hazard neither reviewer raised, found by checking the runtime:** `tvart.py` opens
`token_file` by *relative path*, and deployment is `git pull` — so the untracking
commit **deletes the file on the Pi** and breaks TV auth until re-pair. The two steps
must therefore happen in one sitting at the hardware, which is now recorded. The file
is deliberately **not** untracked in this commit for that reason: doing so unilaterally
would strand the Pi on next deploy.

**The lifecycle defect was self-inflicted, and that's the lesson.** The re-search
decision rejected a stored `resolving` verdict on the grounds that *"a crashed resolve
run would leave the work reading `resolving` forever with nothing to correct it"* —
then moved the truth to the run row **without re-asking that question of the run
row**. The defect moved with it and got worse: combined with constraint 14, a crash
left the covered works permanently un-re-searchable, silently, on the only tool that
spends money. `MemoryMax` on the curation unit exists to cause exactly that kill, and
a deploy is `systemctl restart` — routine, not exotic.

Fixed with **startup reconciliation**: every non-terminal run becomes `failed` when
curation starts. Chosen over timeouts or heartbeats because a run only advances while
its owning process lives and there is exactly one such process — so the inference is
total rather than heuristic, with no timer to tune and no liveness field to keep
fresh. `failed` being terminal is what releases the `ResolveRunWork` coverage.

**Flow 4** still had curation rendering the e-paper label in both `product-brief.md`
and `project-state.yaml` — instructing a builder straight into the geometry-in-the-
catalogue violation that `Rendition(kind='label')` was removed to prevent.

**A decision recorded in only one of its two homes.** "uv for both planes" was written
as DECIDED in `project-preferences.md` while `project-state.yaml` still said
"deliberately NOT decided here", with no `technical_decisions` entry at all. Now
recorded properly with alternatives. The claim that the PEP 517 verification item
"folds into" the existing IT8951 risk was also an overstatement — that risk is about
the interpreter version, not the build frontend — and is now tracked separately.

**Files:** `data-model.md`, `architecture.md`, `operational-spec.md`,
`security-model.md`, `product-brief.md`, `project-preferences.md`, `.gitignore`,
`project-state.yaml`.

**Deferred, not fixed (count as of 2026-07-20, `rev-20260720T164451Z-cde89172`):**
thirteen WARNING findings from `rev-20260720T160759Z-cbc0d27e` were open and recorded
as still present in the evidence store — among them panel geometry's two candidate homes, `constraint 8` vs
`api-contract.md` on what `reject_image` costs, the manifest `sequence` counter
having no persisted home, and the manifest exclusion report having no action or
result field. They are advisory at the PR gate; naming them here so the round is not
read as fully closed.

## 2026-07-20: Close the remaining decisions — mat geometry, resolution floor, rights, MCP resources, dependency manager

**Why:** Walked the operator through every decision still blocking progress. Open
questions went **6 → 3**, and none of the three remaining waits on them — all are
research items that block nothing.

**The mat geometry was never a filed question, and it blocked the filed one.** The
minimum-resolution question asked for a number. Adequacy is defined against the
artwork box, the box is defined by panel geometry and mat width — and mat geometry
was specified *nowhere*. Worse, the 2024 code contradicts the artifact: `data-model.md`
claims "the artwork sits inside a mat, the mat is the deliberate frame", but
`image.thumbnail((3840,2160))` makes the mat aspect-ratio residue, so a 16:9 source
gets **no mat at all**. The premise was aspirational and nothing implemented it.

**Decided: the mat is physical.** Specified in inches with the bottom margin weighted
larger than the top — the conservator's convention, since a true-centred image reads
as sitting low.

**Panel geometry is a deployment value, not a constant** — the operator's instruction,
because other people will run this on other panel sizes. That lands it under the
already-ratified "no hardcoded deployment values" norm and makes it the **second**
value both planes must agree on after `ART_ROOT` — with a quieter failure mode, and
therefore a worse one: nothing breaks, the mat is merely the wrong width.

**So the floor is a formula, not a number** — a minimum rendered size *in inches*,
scaling with the panel automatically. On a 42" (~105 ppi) a 12" floor is ~1260 px on
the long edge; on a 75" (~59 ppi) the same floor is ~708 px. **Below it, nothing is
silently dropped or silently accepted:** phase 2 won't auto-select a below-floor
instance, the grid shows it labelled with its rendered inches, and the curator may
take it anyway. All-below-floor lands at `resolution_status = unresolved`, which is
already first-class — the machinery landed earlier the same day.

The load-bearing detail: **a thumbnail cannot convey resolution.** 900 px and 6000 px
look identical in a review grid, so the "a human saw the artwork" gate does not by
itself prevent hanging a postage stamp. The rendered-inches figure is what makes that
judgement possible at all.

**`display_fit` is now derived, never stored — amending constraint 12.** A verdict
computed at acquisition is a stored judgement about a machine the curation plane
doesn't own, and it goes silently wrong when the TV changes. `width`/`height` stay
stored; they're panel-independent facts. Constraint 12's real intent — policy in one
place, not implicit in each renderer — is met by the service-layer norm ratified
hours earlier rather than by storage. **Third application of derived-not-stored**
after readiness and the re-search states.

**No upscaling**, so `display_fit`'s `upscaled` value is removed rather than
reserved — a declared state with no producer is the exact defect the re-search review
flagged this morning.

**Rights are display-only and gate nothing**, reframed as a provenance and
source-quality signal rather than a legal one: a holding institution's own
public-domain scan is usually the authoritative file. Reopen trigger recorded
(sharing/export, or the catalogue going public). **No MCP resources in v1** — tools
cover every read and adding resources later is purely additive. **uv for both planes**
in a workspace, with the IT8951 Cython build under PEP 517 isolation as a named
verification item folded into that driver's existing must-prove-early risk.

**Pass 3 of the sweep rule earned itself immediately** — re-reading my own edited
files caught `architecture.md` still asserting `ART_ROOT` was the only cross-plane
value, plus two stale consequence lists in `project-state.yaml`. That is the pass
whose absence caused the fourth and fifth recurrences.

**Files:** `data-model.md`, `nonfunctional-requirements.md`, `architecture.md`,
`operational-spec.md`, `api-contract.md`, `project-preferences.md`,
`project-state.yaml`.

## 2026-07-20: Address Critic findings — all 4 blocking, plus the sweep root cause

**Why:** Cumulative Critic (`rev-20260720T145500Z-2fcf2f8f`, 3 reviewers) returned
4 blocking / 13 warning / 13 note. **Two of the four blocking were defects I
introduced in this session's own commits**, which is worth stating plainly.

**R-10 — the coverage relation I assumed and never modelled.** I proposed the run
row as the fix for "nothing prevents double-submission", wrote constraint 14 to
enforce it, and never asked what data that constraint would read.
`CandidateWork.discovery_run_id` is provenance (**Q5**) and reusing it destroys
that; `parent_run_id` points at the originating run and a resolve run covers a
subset. Added **`ResolveRunWork`** — a join, deliberately, not a nullable column on
the work, because a column would be the stored-second-truth the readiness decision
rejects and would lose earlier attempts. Constraint 14, the "in flight" derivation,
and `status` reporting on a resolve run are all now answerable.

**R-2 — the sweep failed again, and the root cause is sharper than before.** The
sweep grep I ran *excluded the two files I was editing*, on the assumption that
editing a file handles it. So `data-model.md` § SpendRecord kept "re-search spend
attributes to the ORIGINATING run" — the exact rule I superseded 180 lines above it
in the same file, and whose twin I rewrote by hand in `api-contract.md`. **Plain
grep would have caught this; I removed it from grep's reach.** Correction recorded
in `learnings.md`: editing a file is not sweeping it, and the largest artifacts need
the sweep most.

**R-1 — a ratified norm violated by a numbered constraint.** Constraint 11
specified an application-side monthly spend sum driving `halted_by_budget`, which
is precisely what the provider-enforced ceiling norm forbids — and a numbered
constraint is what a builder implements. Rewritten to derive `halted_by_budget`
from a 402 and read remaining budget from `limit_remaining`; `SpendRecord` restated
as attribution and reporting only. Also fixed "calendar month" → UTC month, and
retired the "search may dominate token spend" claim resolved on 2026-07-20.

**R-3 — a norm binding four artifacts with no ratification. Now ratified by the
owner.** "Operation logic lives only in the service layer" was cited as binding and
Critic-enforced in four artifacts and leaned on five times in `project-state.yaml`,
with no decision record, no Direction home, and a circular pointer trail. Given a
Direction home in `architecture.md` with a dated marker; preferences row demoted to
a pointer. **Retroactivity was done artifact-shaped** — the correction from last
session's learning — and found no specified behaviour in violation.

**The structural cause of the repeat drift, found by the sustainability reviewer:**
both findings files sat under `artifact_manifest.findings` with **no `depends_on`
edges at all**, so the dependency-graph sweep the learning prescribes — and the
check proposed in issue #8 — could not reach the two documents carrying the most
raw decision text. That is why the retired product-wide Python target survived there
through four recurrences. Edges added; the stale target corrected in
`platform-and-dependency-findings.md`, `learnings.md`, and the retired "Pi 4
performance" rationale in `3tears-integration-findings.md`.

**Files:** `data-model.md`, `api-contract.md`, `architecture.md`,
`project-preferences.md`, `product-brief.md`, `platform-and-dependency-findings.md`,
`3tears-integration-findings.md`, `learnings.md`, `project-state.yaml`.

## 2026-07-20: Model the re-search — a run row, derived states, one entry point

**Why:** Three interacting defects the Critic raised on the one paid path, deferred
last session rather than patched because fixing any one alone moves the ambiguity
instead of removing it. They were right to be one question — fixing the first
largely dissolved the second.

**`resolve_images` now creates a `DiscoveryRun` with `kind='resolve'`.** It was a
paid, minutes-long operation creating no row at all, so the one tool the design says
is the only one that spends money had no handle to poll, no cancel, no cost of its
own, and no guard against the same work ids being submitted twice concurrently. A
resolve run enters directly at `resolving_images` and carries `parent_run_id`, so
`status`, `cancel`, `spend`, and `halted_by_budget` all work on it with no new
machinery.

**No new states — the run row *was* the missing state.** `awaiting_better_image` was
carrying "not yet re-searched", "re-search running", and "re-search found nothing"
as one value. The fix separates curator *intent* from job *state*: the verdict now
means only "the curator wants this work and this instance isn't good enough", which
doesn't change when a job starts or stops. Running derives from the run row; found-
nothing is `resolution_status = unresolved`. That follows the ratified derived-not-
stored readiness decision instead of re-litigating it — a stored `resolving` would be
a second truth beside the run row, and a crashed run would strand a work in it.

**Cost named rather than discovered later:** `resolution_status` is redefined from
"phase 2 found no credible instance" to "the latest attempt found none". Written down
explicitly, because a widened meaning nobody records is how the next drift starts.

**`set_verdict` no longer accepts `awaiting_better_image`.** Both paths reached it and
only `reject_image` set `rejected_at`, so a re-search could hand back the image just
rejected — the Q11 suppression failure reappearing on the instance scope. One entry
point makes it impossible rather than defended against.

**Swept by decision again**, and it found a dependent that names none of the changed
terms: the **per-run search cap** in `nonfunctional-requirements.md` now bounds each
*attempt* rather than a work's lifetime, because re-searches are runs. Accepted and
recorded — the monthly ceiling still bounds the aggregate and can't be multiplied by
creating runs. Also swept `observability-strategy.md`, where `run_id` now covers the
product's second paid fan-out, which previously logged with no correlation key.

**Also fixed, no pre-existing exception:** `api-contract.md` still listed the
`set_verdict` explicit-ids question as open after it was decided on 2026-07-20 — one
of the Critic's outstanding warnings.

**Files:** `data-model.md`, `api-contract.md`, `nonfunctional-requirements.md`,
`observability-strategy.md`, `project-state.yaml`.

## 2026-07-20: Settle the curation interpreter — uv-managed 3.14, 3tears unmodified

**Why:** The interpreter question was the highest-priority open item and it gated the
curation plane's first build chunk, because it determines what the venv is built
against.

**The premise was wrong, which is the whole finding.** The question was framed as a
cost tradeoff anchored on "3.14 on a Pi means a 30–45 minute source build per patch
release" — and that made relaxing `3tears` to 3.13 look attractive despite an
untested behavioural risk. But the 30–45 minutes is a fact about *pyenv*, not about
3.14 on a Pi. A prebuilt `cpython-3.14.4-linux-aarch64-gnu` is published via
python-build-standalone and is what `uv python install 3.14` fetches — verified with
`uv python list --all-platforms --all-arches --show-urls`, not recalled. The
expensive option was never expensive, so the tradeoff the question posed did not
exist. **That is the fifth open question this project has dissolved by checking its
premise rather than researching its answer.**

Keeping `3tears` unmodified also avoids a risk the 2026-07-19 audit could not close:
that audit was static, so behaviour under 3.13 — asyncio internals, pydantic/
langchain annotation resolution under eager vs lazy `__annotations__` — was never
exercised. And it preserves the Python version pin as a live rationale for the
two-plane split.

**Two consequences recorded rather than waved past.** Curation's CPython now comes
from Astral's channel, so `apt upgrade` does not patch it — a CVE is a two-plane
action where an operator would assume one (`security-model.md` § Supply Chain, new;
`operational-spec.md` § Routine Operations). And a standalone interpreter cannot see
distro site-packages, which is survivable only because label rendering already moved
to the display plane — so adding anything needing distro C bindings to curation is
what breaks this decision.

**Swept by decision, not by grep** — the correction the learning demanded after three
failures. Two dependents carried no matching text: `security-model.md` had no supply
chain section at all, and the package-manager preference (still open, deferred to
discovery) had its inputs changed, since uv is now a required install on the Pi
regardless and is therefore the incumbent rather than a new dependency. Neither is
reachable by grepping "3.14".

**Files:** `operational-spec.md` (§ The Python 3.14 Problem → § The Curation
Interpreter, now decided), `security-model.md` (new § Supply Chain),
`project-preferences.md`, `architecture.md`, `.subagent-briefing.md`,
`project-state.yaml` (decision recorded, question closed, the stale 3.13-test
question marked off this product's path).

## 2026-07-20: Complete Phase B/C — five strategy artifacts, and co-locate the planes

**Why:** Five strategy-class artifacts were missing and the structural-coverage
advisory named all of them. Authoring them in dependency order (NFRs before
architecture, deliberately — so architecture couldn't be back-filled into
requirements that happened to match it) forced four high-priority open questions to
resolve and surfaced one structural change nobody had planned.

**The structural change: both planes now run on the Pi, sharing a data directory.**
The operator's call, made mid-session. It reversed the recorded deployment plan and
retired the split's stated rationale — "it moves gigapixel fetching, k-means over LAB
arrays, and 4K compositing off a Pi 4" — which is simply false once both planes are
on the one machine. The split was *kept*, and it got cheaper rather than weaker: its
cost was the distributed-systems tax (network contract, sync, two deployments) and a
shared filesystem pays that down to near zero, while its benefit — the wall staying
lit through a curation restart — matters more on one box, not less.

**Questions that resolved by having their premise rejected rather than answered:**

- **"Is paid web search inside or outside the $20 ceiling?"** Inside, comfortably.
  The recorded worry that search could exceed token spend "by an order of magnitude"
  was wrong: worst case it roughly doubles per-run cost, and a run is $0.16–0.49. The
  metering half of the question dissolved too — search bills as OpenRouter credits, so
  one ceiling covers both.
- **"What is the single source of truth for *ready to display*?"** There isn't one,
  and looking for one was the bug. Catalogue readiness (renderable) and device
  readiness (on the TV) are different questions owned by different planes. Manifest
  membership *is* catalogue readiness, so the recorded failure — the display plane
  selecting a work it cannot render — became structurally impossible rather than
  defended against.
- **"What cost threshold gates the work list?"** None: it gates on **work count**.
  Once runs were measured, a dollar threshold gated on the axis that doesn't matter.
  The judgement the gate invites is scope — "you asked for Dalí and I found 200 works"
  — and count is what a curator can act on at a glance.

**Two claims withdrawn after reading source rather than trusting the record:**

- **"The server MUST emit `notifications/progress`; it is what keeps the connection
  alive."** `Context.report_progress` silently no-ops when the client sent no
  `progressToken` — so the mechanism a design was resting on can do nothing, invisibly.
  And it's unnecessary: with the run handle returning immediately, no call is ever idle
  long enough to abort. Neither of the operator's production MCP servers emits them.
- **Neither of those servers was a precedent for the framework decision either** —
  hallucinote is stdio-only, cordyceps is C# on a hand-rolled `HttpListener`. The
  previous session's pattern was to defer to their practice; here there was nothing to
  defer to, and FastAPI was decided on merits. Recorded with the SDK's silent lifespan
  hazard, which fails *every* request and gives no hint about lifespans.

**Norms:** three candidates proposed, two ratified (provider-enforced spend ceilings;
display-plane independence), one deliberately declined and demoted to prose with its
lack of enforcement flagged. A third — the manifest as the only inter-plane channel —
was ratified with a Test mechanism, so its test was filed as issue #7 at norm birth
rather than left aspirational.

**Verified rather than recalled:** every 3.14 aarch64 wheel question (all clear, via
the PyPI API), OpenRouter's per-key credit limits and search pricing (via docs), the
repo's public visibility, and the real corpus — 41 works, mean 17.6 MP, ~10 GB at 500
works, which is what proved storage does not force a NAS.

**Surfaced, not solved:** Pi OS Trixie ships Python 3.13, and nothing needs 3.14 except
3tears — whose requirement the audit already found removable in 16 sites. On a desktop
that was free; on a Pi it is a 30–45 minute source build per patch release. Filed high,
because it gates the first build chunk.

**Also swept:** two further sites where the "forced by a version conflict" phrasing had
outlived its amendment — the third and fourth occurrences of the same recurrence
`learnings.md` already records. One of the claims I had to retire this session was one I
wrote myself an hour earlier.

**Still open, not fixed:** `token_file` remains tracked (issue #4). The security model
now records the order of operations that matters — rotate against the TV *first*, then
untrack; the reverse leaves a live token in public history while looking resolved.

**No code changed.**

## 2026-07-19: Resolve the MCP tool surface and split work from image instance

**Why:** Two things were blocking Phase C. The MCP tool surface was the highest-value
open question — it gated the api-contract's operations table, the versioning and
error-model decisions, and the service layer's shape. And a central product
requirement had never been written down: a *work* is not an *image* of it, so a
request for "Dalí's Persistence of Memory" must not return ten copies for the
curator to pick one of.

**What changed:**

- **`product-brief.md`** — flows 1–3 rewritten around two-phase discovery (intent →
  works, then per-work → image instances, with canonical selection). Flow 3 gains a
  third verdict: accept the work, reject the *image*, re-search. Flow 8 rewritten to
  resolve a contradiction it carried with flow 3. Two success criteria added.
- **`data-model.md`** — new Direction norm: a work is distinct from an image of it,
  at every stage. `Candidate` splits into `CandidateWork` + `CandidateImage`,
  mirroring the existing `Artwork`/`Source` shape so acceptance is a promotion rather
  than a transformation. `DiscoveryRun` gains `awaiting_approval` and `declined`
  states. Three new questions the data must answer (Q10–Q12). Suppression split into
  two scopes. `Artwork` loses the pre-acceptance states that now live on
  `CandidateWork`.
- **`api-contract.md`** — operations table filled: five action-dispatch tools with
  registry-generated definitions. Transport, error envelope, versioning, deprecation,
  and stability tiers all decided. New Validation section.
- **`project-state.yaml`** — `api_versioning_approach` and `api_error_model_approach`
  move from `deferred` to `active`. Six new technical decisions. The MCP surface
  question closes; two narrower ones open.

**Corrections to committed material, recorded rather than quietly dropped:**

- The api-contract's prompt-injection analysis opened with *"agents cannot
  auto-accept"*. Putting the verdict tool on the MCP surface voids that. The
  replacement bounds are weaker and are stated as weaker.
- The api-contract framed the tool-granularity trade around the Dalí request being
  "one call" under intention-shaped tools. It can never be one call — phase 2 takes
  minutes and review needs a human — which dissolves most of the trade.
- `data-model.md` deferred `target_candidate_count`, listing three options. The
  two-phase split produces a fourth that beats all three, so the deferral is closed
  rather than carried.

**Evidence:** decisions were taken against the operator's two production MCP servers
(`cordyceps`, public and in wide use; `hallucinote`, private), Anthropic's published
tool-design guidance, and MCP spec revision `2025-11-25` — not from recall. Two
findings depend on that: MCP Tasks are unusable because Claude Code declined to
implement them, and inline image results are a deliberate *departure* from both of
the operator's servers, justified by remote transport.

**No code changed.** This is planning work.

## 2026-07-19: Address Critic findings on the MCP-surface planning bundle

**Why:** Cumulative Critic review (`rev-20260720T031744Z-b47f2ffa`, three independent
reviewers) returned 0 blocking, 15 warnings, 11 notes. Several were defects
introduced by the immediately preceding commit; the rest were pre-existing
contradictions that commit walked past.

**Introduced by `9ed0317` and fixed here:**

- **`art_discovery(action='cancel')` had no modelled outcome.** The contract exposed
  the action; `DiscoveryRun.status` had no `cancelled` state. Added, with all five
  terminal states now documented as describing five different things — none may
  absorb another.
- **The re-search after "reject this image" had no owner.** It would have spent money
  from `art_review`, breaking the premise the whole per-tool gating design rests on.
  Moved to `art_discovery(action='resolve_images')`; spend attributes to the
  originating run via a new `image_research` category, and the run does not reopen.
- **An ASGI framework was presupposed, never chosen.** The transport decision read as
  though ASGI were settled. Scoped the decision to co-mounting and filed the framework
  as a high-priority open question.
- **The `CandidateWork` state diagram contradicted its own prose** — the return edge
  landed on `accepted` where the text says `pending`.
- **An open question was claimed but never filed** (MCP resources).

**Pre-existing, fixed rather than deferred:**

- **`risk_profile` still asserted the security bound the same commit declared void.**
  Correcting it in `api-contract.md` while leaving it standing in the risk register is
  precisely the drift the correction existed to prevent.
- **`product_definition` was a generation behind `product-brief.md`**, which declares
  it as its `depends_on` source — 7 flows not 8, single-phase discovery, binary
  verdict, TV-side reconcile. Brought into line.
- **`learnings.md` asserted the opposite of the architecture decision** — "the Python
  version split is not negotiable" and "forced by a version conflict", both retired by
  the 2026-07-19 audit and corrected everywhere except there. Rewritten, with the
  generalisable lesson recorded: *"forced by X" is a claim about X, and needs the same
  verification as any other foreign-system claim.*
- **`boundary-patterns.md` was still the stock template** while four real contract
  surfaces existed. Filled — an empty version silently disarms the consumer-impact
  check for every future chunk.
- **The recovered systemd unit defeats a stated goal.** `Restart=always` with no
  `RestartSec`/`StartLimit*` means a fast-crashing loader exhausts its burst in half a
  second and sits in `failed` with no notification — the exact opposite of "a failure
  in the unattended loader is visible without inspecting the wall". Documented in
  `deploy/README.md`; the unit stays as-recovered on purpose.

**Also recorded:** candidate preview files as a disposable third class in the cache
contract, and three new open questions — display-readiness source of truth, where the
display plane's rotation list lives when curation is down, and the web framework.

**Still open, not fixed:** `token_file` remains tracked (issue #4). Removing it from
the index would not remove it from history; the real fix is rotating the pairing token
against the TV, which needs hardware access.

**No code changed.**
