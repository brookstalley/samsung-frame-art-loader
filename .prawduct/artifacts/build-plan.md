---
artifact: build-plan
version: 1
scope: v1-build
depends_on:
  - artifact: product-brief
  - artifact: data-model
  - artifact: architecture
  - artifact: api-contract
  - artifact: nonfunctional-requirements
  - artifact: security-model
  - artifact: operational-spec
  - artifact: observability-strategy
  - artifact: project-preferences
  - artifact: boundary-patterns
  - artifact: platform-and-dependency-findings
  - artifact: 3tears-integration-findings
governed_by:
  - artifact: architecture
    dispositions:
      - "the theme manifest file is the only channel from curation to display → conforms: every display chunk reads the manifest and image tree only; interactive commands ride the manifest's directive block (the recorded R-17 decision); issue #7's plane-isolation test landed 2026-08-06 with the display plane's first modules and **enforces it mechanically now** — `tests/preferences/test_plane_isolation.py`, imports resolved transitively, HTTP-client construction banned with the television websocket exempted, planted violations proving both halves can fail. `project-preferences.md`'s enforcement column moved from Critic back to Test naming that file"
      - "operation logic lives only in the service layer; MCP tools and HTTP handlers are thin bindings → conforms: Chunk 07 establishes the registry/handler split as a directory boundary before any tool exists, and every later surface chunk binds service methods only; registry generation carries no per-tool logic"
  - artifact: nonfunctional-requirements
    dispositions:
      - "spend ceilings are enforced by the provider, never by application code → conforms: no chunk builds an application-side ceiling; `halted_by_budget` derives from the provider's refusal (Chunk 14B) and budget-remaining reads `GET /api/v1/key`, which lags by minutes and is therefore display-only, never a gate. The per-run search cap (Chunk 14A) is budgeting inside the norm's recorded scope note, not a ceiling"
      - "the display plane's ability to show art never depends on the curation plane being reachable → conforms: the display daemon (Chunks 12–13) reads only the manifest, the image tree, and its own store; no network call to curation exists anywhere in the display package, and the plane-isolation test guards it"
  - artifact: data-model
    dispositions:
      - "identity is never a source URL → conforms: Artwork identity is a UUID from Chunk 07 on; source URLs live on Source/CandidateImage rows only"
      - "a work is distinct from an image of it, at every stage → conforms: CandidateWork/CandidateImage land as separate entities in Chunk 08, before any discovery code exists; acceptance is promotion, not transformation (Chunk 17)"
      - "per-device runtime state never lives in the catalogue → conforms: TvBinding and the last-acted-on sequence live in `display-state.sqlite` (Chunk 12); labels render display-side (Chunk 13A); each plane's own panel geometry is configuration, stored in neither catalogue nor device state (Chunks 02, 09, 12) — the TV panel's physical size is curation's, the e-paper panel's is display's; corrected 2026-07-20, they are not one shared value"
      - "derived artifacts are regenerated, never transported → conforms: renditions carry `source_content_hash` and regenerate on staleness (Chunk 18B); backup excludes the image tree (Chunk 20); candidate previews get their recorded disposable lifecycle in Chunk 17"
  - artifact: project-preferences
    dispositions:
      - "norm-index rows (formatting, naming, imports, logging-not-print, type-annotate-on-touch, specific exceptions, no hardcoded deployment values, async-at-the-boundary, hardware behind an interface) → conforms: ruff lands in Chunk 06 and the mechanical rows migrate to lint rules as each row's Why already directs; until then the Critic carries them per the index"
      - "no test suite (known departure, blocking for medium+ work) → conforms: pytest is established in Chunk 02 alongside the first code that needs it, before any substantive build chunk, and every chunk ships tests alongside code"
      - "uv for both planes, each plane with its own interpreter and its own lock → conforms: Chunk 06, gated on Chunk 04's build verification. The mechanism was settled 2026-07-20 ahead of the chunk: two SIBLING uv projects, not a uv workspace — a workspace shares one lockfile and one resolved interpreter, and uv 0.11.8 refuses to lock members mixing >=3.14 and ==3.13.* at all. The decision's substance (per-plane interpreter + per-plane lock) is unchanged"
last_validated: 2026-07-20
---

# Build Plan — Samsung Frame Art Loader v1

## Requirements Confidence

**Level:** Medium

**Why:** The problem, success criteria, and scope are each statable in one sentence
and are recorded in `product-brief.md` with unusual depth — three review passes
(Critic cumulative, a requested checkpoint review, verify-resolutions) closed
2026-07-20 with zero findings. What keeps this at Medium is a small set of named
unknowns, each with a resolving chunk early in the sequence rather than a hope
attached. The spine is deliberately evidence-first for exactly this reason.

**Open assumptions / unknowns:**

- [RESOLVED 2026-08-04: the IT8951 stack builds AND imports under uv's PEP 517 isolation on 3.13/aarch64, from the pinned `9f13613`. The feared cause never existed — that commit declares Cython in `build-requires` — so no remediation was needed and the 3.12 fallback is discharged. The real blocker was undeclared `python3-dev`, which fails in `rpi-gpio` rather than in IT8951 and so points at the wrong package. `Cython` is unpinned in that `build-requires`, so the build is reproducible today but not over time]
- [RESOLVED 2026-08-01, half each way: a target exists (fork master `fe95ef1`) and carries Frame-generation support as a model-year branch, but `delete_list` is **not** fixable by bumping — it is unchanged on master, so the fallback fired and confirmed deletion is `tv_delete.delete_list_confirmed` in this repo. Two things the assumption did not anticipate: the target needs `websockets>=13.0` (the pinned 12.0 cannot import it), and its constructor performs blocking network I/O. ~~Live on hardware is still unverified~~ — **verified 2026-08-04** against a 2024 `QN50LS03DAFXZA` on firmware 1310, art API 4.3.4.0. `delete_list_confirmed` returned `requested=1, deleted=1, surviving=()`. The pass also found what reading could not: **`upload()` reports failure on uploads that succeeded** (issue #73), and **only `image_selected` of the three registered callbacks fires**, the other two being slideshow-advance events host-driven rotation never triggers]
- [ASSUMPTION: the 2024 code keeps running the wall throughout the build; cutover to the new display plane happens at Chunk 13B, and the legacy modules are deleted only at Chunk 20 | MED impact | user can override with an earlier or later cutover]
- [ASSUMPTION: the existing sun-position brightness behaviour (`local.py`) ports into the display daemon in v1 — it runs on the wall today, so dropping it would be a regression, but the v1 scope list does not name it | LOW impact | user can defer to Later]
- [ASSUMPTION: rotation timing is per-theme with a global fallback | LOW impact | carried from `data-model.md`; user can collapse to global]
- `work_dedup_key` derivation and the discovery search-engine default are **unknowns
  with scheduled spikes** (Chunk 15), not assumptions — nothing downstream of them is
  designed until they resolve.
- ~~**One operator decision is pending and gates deployment paths:** issue #13
  (SD-card mitigation — USB/SSD storage vs SSD boot).~~ **Taken 2026-08-04 and issue
  #13 is closed:** the card stays, so no deployment path moved and nothing
  downstream was waiting on it. The residual risk transferred to the backup path
  rather than closing.

**What would raise confidence:** ~~Chunks 04, 05, and~~ Chunk 15 — the spikes.
*(04 and 05 ran on 2026-08-04 and are `[x]`; both assumptions are now recorded
facts, and the hardware pass turned up two the plan had not anticipated — see
their entries.)* Each is cheap, early, and converts an assumption into a recorded
fact.

## Status

This list is in **build order, not numeric order** — chunk numbers are stable
identities, and their detailed sections stay in numeric order below. The list was
re-ordered on 2026-07-31; the two changes and why are recorded in the Context
block under "Re-sequenced 2026-07-31".

**Every chunk that needs the bench sits behind every chunk that does not**, because
bench access lapsed on 2026-08-02. *(Updated 2026-08-04: it returned. 05, 04 and 03
ran and are shipped. The rule still governs 12 and 13, whose remaining bench need is
sustained access rather than a visit — and Chunk 12's stated dependency, a verified
library, is now satisfied, so what parks it is its own acceptance criteria and not a
blocked predecessor.)* This is the same rule that
parked 05, 04 and 03 originally, applied a third time: the tooling takes the first
unchecked box as the current chunk, and a blocked chunk ahead of active work
silently hands its `Critic mode:` and `Type:` to every chunk after it. Chunks keep
their numbers and their specs; only their position moves, and it moves back the
moment the bench returns.

The block moved on 2026-08-03 is **05, 04, 03, 12 and 13**, not the three named
before. The earlier arrangement placed the hardware chunks after the discovery
chunks, which was correct until the discovery chunks finished — at which point 05
became the first unchecked box and the hazard the rule exists to prevent arrived
anyway. The count grew because 12 and 13 are gated by the same bench at one
remove: Chunk 12 declares **"Depends on: Chunk 05 (verified library)"** and its
acceptance criteria call for a live pass on the Pi, and Chunks 13A and 13B are the e-paper
panel and its systemd units. Ordering them ahead of the curation chunks would have
re-created the same silence one line further down.

- [x] Chunk 01: Untrack the TV pairing token; drop the catalogue backups (issue #4)
- [x] Chunk 02: Deployment values out of source (issue #5) + `art.py` defect dispositions (issue #6)
- [x] Chunk 06: uv restructure (curation only), lint/test tooling — *display plane deferred; mat fixture **descoped** by Chunk 18B, not pending*
- [x] Chunk 07: Walking skeleton — catalogue core → service layer → MCP tool, end to end
- [x] Chunk 07B: The durable seam — persistence reshaped to the `DurableStore` contract
- [x] Chunk 08A: The accepted-catalogue entities, their constraints, and `display_fit`
- [x] Chunk 08B: The discovery entities, both state machines, startup reconciliation
- [x] Chunk 09: Manifest builder, themes, directives — `art_theme` and `art_display`
- [x] Chunk 10: Seed the catalogue with the existing corpus (v1 scope item)
- [x] Chunk 10B: The first browser surface — catalogue, themes, manifest, health
- [x] Chunk 11: Contract tests — MCP evaluation harness (issue #17) — *plane isolation (#7) split to Chunk 12*
- [x] Chunk 14A: `art_discovery` surface, run correlation, the search cap — no spend
- [x] Chunk 14B: The OpenRouter client, the phase-1 engine, the ceiling (issue #12)
- [x] Chunk 15: Spikes — search-engine choice and `work_dedup_key` derivation (issue #18)
- [x] Chunk 16A: Discovery phase 2 — works to instances, over a real museum API
- [x] Chunk 16B: `resolve_images` — the re-search, its coverage and its rollup
- [x] Chunk 17A: The review surface — works, instances, and the image in the transcript
- [x] Chunk 17B: The verdict, the artist, and the preview's death
- [x] Chunk 18A: Acquisition — the fetch paths, the guards, and a work's sources
- [x] Chunk 18B: Preparation — the mat engine, the 4K render, and the corpus look
- [x] Chunk 21: Say which kind of nothing — `unresolved_reason`, and the artist fold (issue #78)
- [x] Chunk 22: Grounded alternatives — the collection's own answer when the gate refuses
- [x] Chunk 19A: The run half — intent entry, the estimate, the run view and its gate
- [x] Chunk 23: The browser client gets executed coverage — Playwright (issue #30)
- [x] Chunk 19B: The review half — the grid, its alternates, the verdict, the panel
- [x] Chunk 05: Replace the samsungtvws pin, verified on hardware (issue #3)
- [x] Chunk 04: Verify the IT8951 build under uv PEP 517 isolation (issue #9)
- [x] Chunk 03: Pi operational hardening and the vendor-risk answer (issues #15, #16, #13)
- [x] Chunk 12: Display daemon core — poll, rotate, TvBinding, directive semantics *(+ plane isolation, from 11)*
- [ ] Chunk 13A: The panel, the label, the heartbeat and the two units — no hardware
- [ ] Chunk 13B: The Pi — service account, units installed, legibility, cutover
- [ ] Chunk 20: Backup/restore exercise (issue #14), ops close-out, legacy retirement

Context: Plan authored 2026-07-20. Chunks 01, 02 and 06 landed 2026-07-27 in one
pass; **Chunk 07 landed the same day**, took its `final` Critic round and the
follow-up `verify-resolutions` pass, and the architecture now runs end to end —
a real MCP client lists five tools over HTTP and reads a seeded catalogue.
**Chunk 07B landed 2026-07-27** — persistence is split into a generic durable
store and a domain adapter, the 3tears question is answered and closed, and the
on-disk catalogue format is now pinned by a read-compatibility test rather than by
assertion.

**Chunk 08 was split into 08A and 08B on 2026-07-27** at the operator's call —
the accepted catalogue, then the pre-acceptance pipeline — because one Critic
round over the whole of it would read ~2,500 lines at once; see the section below
for what each half carries. **Both halves landed 2026-07-27.** 08A took the
catalogue file from three tables to nine and enforced constraints 1–6, 10, 12 and
13; 08B took it to fourteen, added constraints 7–9, 11, 14 and 15, closed both
discovery state machines, and made startup reconciliation real — which is what
keeps the double-spend guard from becoming a permanent block after a crash.
Acceptance is now a promotion in the service layer: a candidate work mints an
Artwork and its image instances become that work's Sources. The service layer is
split by concern (`CatalogueService` / `DiscoveryService`) behind a container
every surface takes, closing the finding 08A's review carried forward.

**The whole of `data-model.md` is now built.** What remains of the model is the
per-theme rotation settings, whose only reader is the manifest builder in Chunk
09, and `work_dedup_key`'s derivation, whose spike is Chunk 15 — the column and
the suppression that reads it are in place, and the caller supplies the key.

**Chunk 09 landed 2026-07-31.** The service layer is three concerns now, not two:
the theme/directive/manifest half came out of `CatalogueService` first, as its own
commit, before anything was added to it. The manifest builder is real — atomic
temp-and-rename, schema major 1, rotation settings with a deployment fallback, the
directive block carried forward unchanged — and it **reports its exclusions**, per
work with a reason, which is the half of the readiness design that a list-only
builder would have silently dropped. `art_theme` and `art_display` are live over
MCP with all thirteen actions between them.

Three things were settled at build that the artifacts had left open, each recorded
where the rule lives rather than only in code: **the global rotation default** is
deployment config at 180s/shuffle, carried forward from what the 2024 wall runs
today; **"the fetch succeeded" is not a separate readiness check**, because holding
an original is what a succeeded fetch produces and the other reading would take a
work off the wall for a failed *re*-acquisition; and **activating a theme
publishes it**, which the api-contract already said ("changes the wall
immediately") and the first implementation did not do.

The durable store also gained a real widening step, because the rotation columns
were the first change to a table that files on disk already carry.

**Re-sequenced 2026-07-31 — two operator decisions.**

*First: the hardware chunks are unblocked.* The Pi and panel are on the bench, so
03, 04 and 05 move from the blocked list into build order. They keep their numbers
and their specs; only their position changed. They sit after 10B because 09 and 10
are on every path to anything visible, and before 11–13 because 05 verifies the
library Chunk 12 is written against and 04 verifies the panel stack Chunk 13A needs
— both are assumptions in Requirements Confidence above, and each converts to a
recorded fact cheaply. **If bench access turns out to be time-limited, pull 04 and
05 ahead of 09** — that is a live reordering, not a re-plan, and it is the
operator's call.

*Second: a first browser surface lands at 10B instead of waiting for Chunk 19.*
The reason the whole UI sat at position 19 was that it binds every operation, and
most operations did not exist. After Chunk 10 that is no longer true for a real
subset: 41 seeded works with images on disk, themes, and a manifest with reasoned
exclusions. **10B is a re-sequencing of scope Chunk 19 already specifies, not new
scope** — it takes the catalogue/theme/health third of 19's list and leaves the
discovery two-thirds (intent entry, run view, approval gate, cost display, the
review grid with alternates) where they are, because the services behind them
arrive in 14–18. Chunk 19 keeps its number and builds onto 10B's surface rather
than standing one up.

The cost is named rather than discovered: the **UI checkpoint moves from "before
Chunk 19" to "before 10B"**, so issues #2 (design system) and #10 (second-look
shelf) come due earlier, and every chunk from 14 on now has a UI surface it may
need to extend. The benefit is that the product becomes usable by a human eleven
chunks earlier, and each later chunk's UI is reviewed as it lands instead of all
at once.

**Chunk 11 landed 2026-08-01, split in two.** The MCP evaluation harness is
built; the plane-isolation half (issue #7) moved to Chunk 12, where the
`display/` package it checks is actually created — the premise that Chunk 06 had
already created it was simply wrong, and a guard over an empty tree is the
green-test-that-cannot-fail this plan explicitly rejects. The correction that
matters beyond this chunk: **the manifest-channel norm row named that test as a
live `Test` mechanism and no such file had ever existed.** That is the second
norm row in two sessions found asserting enforcement it did not have, after the
broad-except row's linter claim — the recurrence, not either instance, is the
finding.

What the harness delivers is shaped by a distinction `api-contract.md` §
Validation already drew and the chunk entry had blurred: contract tests assert
the surface's **shape**, and the harness asserts a model can **use** it. The
shape half landed with 07–09, so this chunk is the other two: a deterministic
**scenario runner** in the default suite, and a **model-driven evaluation**
behind the `llm_eval` marker, deselected by default. Both produce the same
transcript, so the scripted route is the yardstick a model's route is measured
against rather than a separate exercise. The model half runs through
`3tears-models` over OpenRouter at the operator's call — its own dependency
group, because it is the heaviest install in the repo and nothing in the default
run imports a line of it.

**Re-sequenced and split 2026-08-02 — discovery moves ahead of the hardware
chunks.** Bench access lapsed, and Chunk 14 depends on 08 and 11 alone: nothing in
it touches the TV or the panel, and its foreign API is OpenRouter. Leaving it
behind five hardware-gated chunks would have stalled every non-hardware path in
the plan behind a blocker unrelated to it — and, per the Status preamble's own
warning, left a blocked chunk sitting at the first unchecked box handing its
`Critic mode:` and `Type:` to everything after it. 05, 04, 03, 12 and 13 keep
their numbers and specs; only their position moved.

**Chunk 14 is split into 14A and 14B**, at the seam
`openrouter-api-findings.md` already argues for — the narrow first-party interface
the engine depends on. 14A builds everything up to that seam and spends nothing;
14B builds what sits behind it. The split's value is that 14A needs no API key, no
credit and no operator action, so it proceeds while the ceiling is provisioned.
The risk it carries is named rather than discovered: building to a seam before the
thing behind it exists can encode the wrong shape. Judged low **because the live
probe recorded the real shapes first** — that is precisely what the verify-api
step bought, and it is why the split is safe here and would not have been before
2026-08-02.

**14A landed 2026-08-02.** Eight of `art_discovery`'s ten actions went live and
drove the real service; `resolve_images` was deliberately withheld, because a
declared action a model cannot distinguish from a working one is a promise the
surface cannot keep. *(It runs and is advertised as of 16B — all ten are live.)*
The seam stayed **phase 1 only**, which is the one scoping
call worth carrying forward: defining phase 2's interface now would encode a
shape before the ARTIC probe that Chunk 16 makes its own first step, and the
split's stated risk applies exactly there. The consequence is visible and
truthful rather than hidden — a run that passes the gate sits in
`resolving_images`, and `status` says in plain words that image resolution is not
wired up in this deployment and offers `cancel`. **That sentence is owed a
deletion when phase 2 lands**: a run waiting on a capability that now exists
would be told the opposite of the truth.

The values the plan left to this chunk are settled and recorded where their rules
live: the gate at 25 and the two-part cap at 10 + 2/work in
`nonfunctional-requirements.md`, the estimate's arity in `api-contract.md`, the
provisional key's site and its two known failure modes in `data-model.md`, and
the log shape in `observability-strategy.md`.

**14B landed 2026-08-02 and discovery now spends.** Everything 14A owed is
settled: every run searches rather than a trigger deciding (the failure mode of a
wrong trigger is silent and unrecoverable), the engine writes
`DiscoveryRun.strategy` when the work list settles, and the phase-1 allowance
stays at 10 because the fee proved to be **per request and flat across result
counts** — which also makes search breadth free. Exhaustion (403) and
unaffordability (402) are held apart in the client, and the ceiling is *proven*
closed: a deliberately exhausted key drives a real run to `halted_by_budget` in a
live suite behind `-m live_api`, which is now the durable form of
`openrouter-api-findings.md`.

**One thing 14B found and deliberately did not fix.** A real run cost $0.0056
against a $0.127 estimate, because `DISCOVERY_PHASE1_INPUT_TOKENS` assumes
490,000 tokens where the plugin injects 3,453. That figure is the cost analysis's
*whole-run* basis spent on phase 1 alone, and phase 2's tokens are in no estimate
at all — so re-basing phase 1 by itself would swap a visible overstatement for an
invisible understatement. **Chunk 16 owns the correction**, being the first point
both halves can be measured.

**A requirements pass ran before either half (2026-08-02)** and is the reason the
chunk entries below carry values rather than the phrase "the configured
threshold". It found nine gaps, of which the load-bearing ones were: the per-run
search cap was **undefined for phase 1** (it "derived from the work count", which
phase 1 exists to produce — corrected in `nonfunctional-requirements.md` to a
two-part cap), `estimate`'s behaviour had never been specified despite the action
shipping in the surface table since the start (now in `api-contract.md`), and
`work_dedup_key`'s interim derivation had no owner even though the column is
`required` and phase 1 mints rows (now in `data-model.md`). A tenth finding was a
requirement for a surface that does not exist — cost visibility "on CLI" — struck
rather than silently inherited.

**Chunk 16 was split into 16A and 16B on 2026-08-02**, at the operator's call, at
the seam between turning works into instances and doing it a second time on
request — the same reason 08 and 14 were split, one Critic round over ~5,000 lines.
**16A landed the same day** and a discovery run now completes under its own power:
the `status` notice telling a curator that finding images was not wired up is
deleted, which is the sentence 14A recorded as owed.

**The verify-api probe ran first and changed the design rather than confirming
it**, which is the thing worth carrying forward about this chunk.
`artic-api-findings.md` records it. The load-bearing finding is that **the
museum's own relevance score cannot carry confidence**: scores are not comparable
between queries, a nonsense query returns the whole collection rather than
nothing, and asking for a painting the museum does not hold returns real works by
real artists at comfortable scores. The most obvious implementation — rank by
score, take the leader — produces exactly the "confident near-match" the data
model forbids, silently. So confidence is an identity comparison derived from the
same normalisation `work_dedup_key` uses, and **an artist disagreement
disqualifies rather than deducts**, because a deduction still selects the wrong
work whenever the right one is absent.

Two scoping decisions are settled and recorded where their rules live. **Phase 2
reaches museum APIs only** (`nonfunctional-requirements.md`): the comparison is
free and deterministic, so phase 2 spends nothing, and a work no museum holds
lands `unresolved` rather than triggering a paid fallback nobody has shown is
needed. **The floor is an exclusion in the single selection function**, not a
record-time filter and not a score deduction — the first hides the instance, the
second still selects it when nothing better exists.

**Chunk 16A owned the cost correction and both halves settled together.** Phase 2
consuming nothing is what retired 14B's reason for leaving `DISCOVERY_PHASE1_INPUT_TOKENS`
standing at 490,000 against a measured 3,453. A bounded run goes from $0.127 to
$0.01336. **One consequence is recorded rather than glossed**: the token basis is
no longer input-dominated, so "output price is nearly irrelevant to model choice"
no longer holds and the model table in `nonfunctional-requirements.md` reorders.
The chosen model is cheapest on either basis, so the decision stands.

**Chunk 16B landed 2026-08-03, and `art_discovery` is now whole** — all ten
actions live, the last of them the one 14A withheld on purpose. A curator who
turns down a scan can ask for a better one: `resolve_images` mints a
`kind='resolve'` run, returns its handle at once, re-searches every work it
covers, and rolls its spend up to the intent that proposed them. `status`,
`cancel` and `spend` take its id with no special-casing, which is what modelling
the re-search as a run bought.

**Most of the chunk was already there, and the part that was not was the part
that could not be seen from the record layer.** Coverage, constraint 14, the
parent link and the terminal-verdict guard all landed with 08B and 16A; what 16B
added is the runner half — and the rule that a re-search asks about **everything
it covers**, with no "not yet resolved" filter. Every covered work has been
resolved once by definition, so the discovery-run filter would have skipped the
entire request while still holding the works against a second attempt.

**The chunk found a defect the whole design depended on and nothing enforced.**
Instance suppression was scoped to the *row* carrying a rejection, not to the
URL — so a provider re-offering the same scan, which is the normal case between
two searches a minute apart, wrote a fresh row with a null `rejected_at` and
selected it. The curator asked for better and was handed back exactly what they
had just turned down. **Nothing before this chunk could produce it, because
nothing searched twice.** The rule is now written where it belongs, as a
corollary to constraint 7 in `data-model.md`: a work holds at most one instance
per `url`, and recording one it already has returns the instance already held.

Two smaller consequences are recorded rather than glossed. The registry gained an
**`array` parameter type** with a declared element type, because `work_ids` is
the surface's first list and a bare `{"type": "array"}` publishes nothing a model
can act on. And a re-search now carries an `estimated_cost_usd` of its own,
priced from the works it covers — without it, `estimate` on a resolve run
answered with a sentence about phase 1 finishing, which will never happen on a
run that never had one.

**Chunk 18A landed 2026-08-03** — the two fetch paths, the URL policy, the disk
guard and four `art_catalogue` actions. Its step-0 probe of `dezoomify-rs`
invalidated three things the 2024 call site implied, and its four review rounds
turned up a failed *retry* deleting the image the work was still displaying: both
fetch paths now stage and promote, so a failed re-fetch costs the work nothing.

**Chunk 18B landed 2026-08-03 and the preparation half is built.** The mat engine
asks a vision model in LAB and records `MatColor.method` on every path, so the
mechanical fallback the 2024 pipeline applied silently is now visible in the data
and in the tool's own notice. The compositor draws the artwork box
`Settings.tv_artwork_box` already computes — recovering the margins from the box
rather than recomputing them from inches and a weight, so the canvas and the
readiness verdict cannot disagree by the pixel or two that rounding order moves.
`set_mat_color` and `regenerate` are live, and a prepared work enters the
manifest end to end.

*Four things were settled at build.* **The vision model is `qwen/qwen3.7-flash`**,
chosen on the operator's stated criterion — cheapest that does the job — after
thirty-one probe calls over real corpus images: it was the only candidate to
answer every call usably, and the two cheaper ones proposed a near-white mat over
a Rothko and a Mondrian. **`MAT_MAX_OUTPUT_TOKENS` is a correctness value**, not a
tuning knob: a reservation that does not clear a model's *reasoning* budget
returns empty content billed in full, which reads as a model failure and is a
client misconfiguration — it was raised to 8,000 when a corpus run hit the ceiling
intermittently at 2,000. **The corpus is `all.json` itself** and Chunk 06's
deferred `tests/fixtures/mat_corpus.json` is deliberately not created: a copy
would be a second place the 41 colours live, free to drift silently from the one
the seed loads. **`art_catalogue` now declares `openWorldHint=true`**, which it
should have since 18A — `retry_acquisition` was already fetching arbitrary museum
URLs behind a closed-world declaration, and the contract test that should have
caught it asserted the old set of tools rather than the property.

**What 18B could not settle is the acceptance criterion's other half**, and it is
enqueued rather than assumed: "the operator's corpus look finds no regression" is
explicitly subjective. A full run is done — 33 of the 41 works compared, median
CIEDE2000 distance 9.8, the engine's median lightness 20.8 against the corpus's
20.7, one work over the darkness bar — and `tools/mat_corpus.py` regenerates the
side-by-side sheet. It is in `operator-verification.md` with the three pairs worth
looking at first.

**Chunk 19B landed 2026-08-05 and the curator loop closes in a browser** — intent,
estimate, review with images, accept, theme, wall, with no MCP client anywhere in
it. The grid rides Chunk 17's review service; verdicts and image selection are
thin bindings over methods that already enforce their rules; issue #2's last box
is closed by the grid's components.

*Three things settled at build.* **A binding for the re-search was added at the
operator's call**, because turning a scan down is one of the grid's own actions
and leaves the work `awaiting_better_image` where nothing looks again — shipping
the rejection without it would have made this chunk's own screen a dead end
escapable only from an MCP client. **The review listing stops inlining pictures
the browser discards**: both surfaces call the same methods, the browser passes
`pictures=False`, and a page costs a `stat` per instance instead of a re-encode.
**The health panel gained a reader for the display plane's own report**, which
closes the carried finding above Chunk 21 — the failure table mapped TV, panel and
last-error state onto a document nothing displayed. Backup age is built against a
receipt Chunk 20 will write (`backup-status.json`, key `completed_at`), and
`get_health` left the known-departures table by conforming.

**The mutation sweep was found reporting on runs that executed nothing**, and that
is the finding worth carrying past this chunk. Every opt-in suite is deselected by
`addopts`, naming such a test on the command line does not select it, pytest exits
5, and the tool read any non-zero exit as a caught mutation. Twenty-one mutations
of the review grid reported caught by runs that never executed a line of the file.
Re-run with `-- -m browser`, two survived and both were real. The tool now runs the
targets unmutated first and refuses to sweep unless they run and pass. **Chunk 23's
recorded acceptance was reached the same way and was re-swept rather than assumed —
all fourteen caught.** A vacuous proof and a false claim are different faults, and
that one was the first.

**Chunk 12 is built and is deliberately NOT checked off (2026-08-06).** The
display plane exists — manifest polling and version refusal, host-driven
rotation, `TvBinding` in `display-state.sqlite`, directive semantics, orphan
removal, the sun-position brightness port, and the television behind an abstract
interface — with a suite of its own, all three planes green, and lint clean.
**What is missing is the half no double can supply**: the acceptance criteria
call for a live pass on the Pi, and the television was in standby for the whole
session, so not one line of this has spoken to a set. The chunk stays open until
it has; `operator-verification.md` carries what to run.

**It spoke to a set on 2026-08-07, and the first thing it found was a defect no
double could have produced.** The daemon ran a full pass against the real
television from the dev Mac — native slideshow disabled, 41 legacy orphans
removed, brightness set from the solar angle, a work uploaded and selected — and
reported `showing Blue Half Circle` at a wall that was still displaying an
art-store image. **The set was dark, and in that state `select_image` is accepted
and ignored**: no error, no event, no change, indefinitely, while every other
call in a rotation succeeds. So a selection is now confirmed against the set
rather than assumed, and "the wall did not change" is its own outcome — the pass
ends rather than walking the theme, the place is given back, the `show_now` stays
unconsumed by the same rule an outage leaves it unconsumed, and it is said once
with the set's own art-mode flag rather than once per interval.

**This also retired a claim this plan and `operator-verification.md` both
carried** — that standby is the failure state where the art channel answers
`ms.channel.timeOut`. It is not: both websocket channels open, and `PowerState`
reports whether the panel is lit and nothing more. (`ms.channel.timeOut` has since
been seen *in art mode*, after heavy connection churn and a SIGKILLed daemon; it
is a connection-slot symptom, not a state signature.) The state map is
`samsung-tv-state-findings.md`, written from measurement.

**The wall was watched in art mode on 2026-08-07 and the confirming read was
wrong**, in the direction that stops the wall: `get_current` reports the
art-store slot, so every real rotation read as a failure and the wall parked on
one picture. Confirmation moved to the set's own `image_selected` announcement,
and the live pass then completed — three unattended rotations at the manifest's
180 s (Calder → Hokusai → Klee), each matching what the operator saw; the third
with curation stopped; and a restart that re-showed the same picture and then
carried on to the next work. **Chunk 12's three acceptance criteria are met on
the real television.**

`tests/preferences/test_plane_isolation.py` landed with the plane's first modules,
which closes the two-session-old finding that the norm index named an enforcement
artifact that had never existed — and the row in `project-preferences.md` moves
back from Critic to Test naming it. The other deliverable that had been waiting on
the same event landed too: the third `test_commands` entry, the third CI leg, and
the guard that the new leg needs no `--ignore` set.

Four things were settled at build and recorded where their rules live: a **restart
re-shows the picture already on the wall** rather than advancing, because
`Restart=always` would otherwise turn a crash loop into a strobing wall; a
**directive is consumed after the attempt, never before**, so an outage delays a
jump instead of eating it (`api-contract.md`); **uploads are carried one per pass**
rather than batched on adoption, because a forty-work theme at ten seconds an
upload would blank the wall for five minutes against a one-second poll interval;
and the **e-paper panel's geometry became configuration** (`operational-spec.md`).
Two artifacts were corrected against what the build proved rather than left to
drift — `TvBinding.tv_content_id` could not be `required` while a `failed` row
exists to have no id, and `display-state.sqlite` does not persist brightness
because a stored copy could only ever be stale.

**Chunk 12 shipped 2026-08-07** as PR #108, all three acceptance criteria met on
the real television and the cumulative Critic returning no blocking findings.

**Chunk 13 was split into 13A and 13B on 2026-08-07** at the operator's call, on
a seam the single entry already contained: it recorded that Pango type sizing
cannot be settled without the operator in front of the panel, while its
deliverables mixed code that runs anywhere with a service account, a directory
move and a machine cutover. 13A is the panel driver, the label renderer, the
heartbeat writer, both unit files and the two refactors Chunk 12 deferred — all
of it testable against doubles. 13B is the Pi: the `tvpi` account, the settled
`ART_ROOT` path, the units installed, the legibility look, the cutover. The cost
is named rather than discovered — **13A ships a type size it cannot justify**,
which is why the plan requires it to be marked provisional at its definition
site rather than merely chosen carefully.

**13A's code is complete as of 2026-08-07 and its box is still `[ ]`, because one
Done-when step is not code.** Step 0b — confirming against the real television
that both the selection confirmation and an observer receive `image_selected` —
has never run: the fan-out has spoken to no set. The daemon is stopped at the
operator's request, so that step waits on the operator rather than on the build.
Everything else the chunk owed is built, swept and green.

Three things were settled at build. **The rendering tier is two objects, not
one** — a `Rasterizer` that measures and draws into flat greyscale, and a device
that puts those bytes somewhere — because the two halves install on different
machines, and that turned out to be the same seam the ratified norm wanted: the
monitor-with-a-mat-area device reuses the typesetting and supplies its own
delivery. **The driver is injected rather than opened**, so the three corrections
this product makes at that seam (the greyscale read-back, the raise-don't-return
failure, the mounting rotation) are tested on a laptop with no panel and no
ability to install the library; only `open_panel` needs hardware. And **a panel
that will not open is a third state that is reported**, not a second road to
`surface=None` — that collapse made a broken panel indistinguishable from a
device that has none on curation's health surface, which is the same
two-meanings-in-one-value fault `has_label_surface` was split out to fix,
reappearing one level up.

**The IT8951 pin-or-vendor decision is taken: pinned, on both install paths, with
the Cython that builds it pinned too** — pinning the driver alone leaves the
compiler free to move, which is the half the trigger note warned about.
`project-state.yaml` carries the reasoning; it was verified resolving on the Pi
rather than assumed, which is what distinguishes it from the previous status
where a fresh resolve landed on the right commit only because upstream's master
still happened to be it.

**The typesetter got a CI job of its own**, because PyGObject does not import on
this project's development Mac and the alternative was leaving the product's most
important accessibility surface tested by nobody. `tests/test_default_suite_ci_scope.py`
grew the claim that no directory a leg ignores may go unrun by every other job —
the failure mode an `--ignore` introduces and a green board hides.

## Scaffolding

### Project Initialization

Chunks 01–05 run against the repo as it stands (flat 2024 modules; pytest is
bootstrapped at the root in Chunk 02). Chunk 06 restructures:

- `uv python install 3.14` on the Pi (curation interpreter; prebuilt
  `cpython-3.14-linux-aarch64-gnu`, verified available — `operational-spec.md`).
- Two plane projects, `curation/` and `display/`, each with its own
  `pyproject.toml`, its own interpreter pin (3.14 / 3.13), and its own lockfile.
  The 2024 modules stay at the repo root, untouched and running production, until
  Chunk 13B's cutover; they are deleted in Chunk 20.

### Dependencies

Rationale per package lives in `project-preferences.md` § Tooling,
`3tears-integration-findings.md`, and `platform-and-dependency-findings.md`.

- **curation (3.14):** fastapi, uvicorn, `mcp>=1.28.1` (official SDK — decided over
  `3tears-mcp`, which drags NATS), httpx, pillow, opencv-python-headless,
  scikit-image, numpy, pydantic, python-dotenv. All wheels on aarch64/3.14,
  verified 2026-07-20. *(Amended 2026-07-27: 3tears **core** is no longer in this
  set — the catalogue's durable tier is first-party code shaped to the framework's
  `DurableStore` contract, so no framework code is imported. See § The 3tears
  catalogue dependency.)* *(Amended 2026-08-02: **3tears-models leaves this list
  too.** It was carried here as "OpenRouter adapters, arriving with Chunk 14" —
  both halves of that chunk have since shipped and it did not arrive, because
  discovery reaches OpenRouter through a first-party client instead. It is a
  test-only dependency in the opt-in `eval` group now, so listing it among the
  plane's runtime dependencies overstated what a deployment installs.)*
- **display (3.13, system interpreter):** samsungtvws (target decided in Chunk 05),
  pillow, IT8951 (pinned per Chunk 04's outcome), omni-epd, pycairo + PyGObject
  (Pango label typesetting; the GTK stack lives on this plane deliberately),
  RPi.GPIO/spidev, python-dotenv.
- **dev (both):** pytest, ruff, black (line-length 130 carried forward).
- **External binary:** dezoomify (tiled fetch), configured not vendored.

### Build & Test Configuration

Per-plane `uv run pytest` from each project; `tests/` mirrors module layout
(`project-preferences.md` § Testing). Contract tests live in `tests/contract/`,
the norm-enforcement test in `tests/preferences/`
(`boundary-patterns.md` § Test Levels). Chunk 06 declares both suites as
`test_commands` in `project-state.yaml` so the test-evidence hook runs the real
invocations. Ruff configured at the root; the mechanical norm-index rows migrate
from Critic to lint rules as Chunk 06 lands them.

### Scaffold Verification

After Chunk 06: both plane venvs resolve from their lockfiles (display's on the
Pi — this is what Chunk 04 de-risks); `uv run pytest` green in both; black and
ruff run clean. After Chunk 07: a placeholder page answers on the curation port
and a real MCP client lists the five tools.

### Verification Strategy

Beyond tests, each chunk is verified the way its consumers experience it:

- **Curation** is exercised through a real MCP client (the Chunk 11 harness, and
  Claude Code by hand) and, later, the browser. Development is on the dev Mac
  against a real `ART_ROOT` — the recorded parity asymmetry
  (`architecture.md` § Cross-Cutting).
- **Display** is verified only on the Pi against the live TV and panel — the two
  interfaces that cannot be meaningfully faked
  (`design_decisions.infrastructure_dependencies`). Every display chunk ends with
  a hardware pass: art on the wall, label matching, journal clean.
- **Mat quality** is judged by the operator side-by-side against the 2024 corpus
  (Chunk 18B's visual-change entry) — the bar is subjective and the 41 hand-tuned
  mats are the regression corpus.
- **The restore path is exercised, not described** (Chunk 20), restoring the
  catalogue onto a scratch directory and watching the system self-heal visibly.

## Project Structure

```
samsung-frame-art-loader/
├── curation/                  # Python 3.14 plane (Chunk 06)
│   ├── pyproject.toml         #   own interpreter pin + lock
│   └── src/curation/
│       ├── services/          #   the ONLY home for operation logic
│       ├── persistence/       #   catalogue schema on stdlib sqlite3, behind Protocols
│       ├── mcp/               #   registry records + thin tool bindings
│       ├── http/              #   thin HTTP handlers (Chunk 19)
│       ├── discovery/         #   phase 1 / phase 2 engines
│       ├── acquisition/       #   fetch, prepare, mat engine
│       └── manifest/          #   manifest builder + exclusion reporting
├── display/                   # Python 3.13 plane (Chunk 06)
│   ├── pyproject.toml
│   └── src/display/
│       ├── daemon.py          #   poll → reconcile → rotate loop
│       ├── tv/                #   samsungtvws behind an interface
│       ├── panel/             #   e-paper + Pango label behind an interface
│       └── state/             #   display-state.sqlite (TvBinding, sequence)
├── tests/                     # bootstrapped Chunk 02; split per-plane in 06
├── deploy/                    # systemd units, journald drop-in, README
└── (2024 modules at root)     # production until Chunk 13B; deleted in Chunk 20
```

### Module Boundaries

Three boundaries carry ratified norms and are restated here because every chunk
touches at least one: **handlers and tools never contain operation logic** (the
registry record is declarative; the service method does the work); **display
imports no curation code and opens no channel to the curation process** (manifest
and image tree only; Critic-enforced until the `display/` package exists, then by
`tests/preferences/test_plane_isolation.py`, which is a deliverable of the chunk
that creates that package); **hardware sits behind interfaces** (the TV client and panel driver
are swappable modules, so a frozen 2023 driver never again dictates an
interpreter). Persistence is reached only through the service layer.

## Build Chunks

**Groundwork — evidence first, at the hardware (Chunks 01–05).** These precede
the walking skeleton deliberately: they close the live credential leak first of
all, then retire the two build-blocking unknowns on real hardware. The
architecture-proving slice is Chunk 07.

### Chunk 01: Untrack the TV pairing token; drop the catalogue backups (issue #4)

- **Description:** Close the credential leak in the public repo, in the corrected
  order: untrack first, then re-pair — the reverse order commits the fresh token
  (`security-model.md` § Credentials). *(Two things this said are withdrawn, both
  as of 2026-07-27: the "one sitting, at the hardware" coupling is gone — the
  config hoist moved the token under `ART_ROOT`, outside the checkout, so the
  untracking commit does **not** delete it on the Pi's next `git pull`; and the
  re-pair was not needed at all, the operator having confirmed the leaked token
  already expired. See the Deliverables below and `security-model.md`.)* Also
  drops the three `all.json` backup snapshots. `all.json` itself stays tracked — it is the mat regression corpus
  until Chunk 06 extracts the fixture.
- **Depends on:** none (hardware access required)
- **Artifacts consumed:** `security-model.md` § Credentials and Secrets,
  issue #4
- **Deliverables:** `token_file`, `all.backup`, `all.json.backup`,
  `all.json.backup2` untracked (`--cached` only) and gitignored; ~~TV re-paired so
  the published token no longer authenticates~~ — **not done, and not needed: the
  operator confirmed the leaked token had already expired, so it authenticates
  nothing and there is no live credential to rotate**; the history-rewrite decision
  recorded explicitly (recommendation: no — rotation kills the credential, and a
  public-repo force-push buys nothing further)
- **Tests:** none (repo-state change); `tests/test_repo_hygiene.py` guards the
  untracking from here on
- **Acceptance criteria:** all four files absent from `git ls-files`, present in
  the working tree; ~~display connects to the TV on real hardware with the fresh
  token~~ — **dropped with the re-pairing above**; `git status` clean afterwards

> **Deviation recorded 2026-07-27**, after Critic review found this section still
> asserting a hardware deliverable the chunk did not perform while its three
> siblings each carried their own. The Status line's title was shortened to
> "Untrack" when the chunk landed and the change-log named the deviation, but a
> builder or auditor reads *this* section — where it said the criterion was met.
> The hardware chunks (03, 04, 05) remain blocked, and none of them depends on
> this one having re-paired.
- **Type:** cleanup
- **Done when:**
  1. Acceptance criteria met on the Pi
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

### Chunk 02: Deployment values out of source (issue #5) + `art.py` defect dispositions (issue #6)

- **Description:** Hoist the three classes of hardcoded deployment value onto the
  existing dotenv path — `ART_ROOT` first (fail fast, no default), then
  `TV_ADDRESS`/`TV_PORT` (single source; `remote_test.py` stops carrying its own
  literal), then coordinates + location name. Fix the CWD-dependent relative
  paths (`upload_list_path`, the bare `token_file`) while in there. This touches
  the legacy modules that still run the wall, so it also discharges issue #6's
  triage: **dispositions recorded by this plan** — defect 1 (`art.py:366`
  `raise e` on an unbound name) is fixed here, one line, because it degrades
  diagnosis today; defects 2 and 3 (shared mutable list state, discarded
  None-filter) die with the ArtSet/metadata replacement in Chunks 08 and 18 and
  are not fixed in legacy code — **amended 2026-07-27: defect 2 was fixed after
  all, because the ruff configuration adopted in the same chunk selects `B006`
  and deliberately does not waive it for `art.py`, so the mutable default
  argument fails the build. Defect 3's disposition stands unchanged.** Recorded
  here rather than left implicit: the plan otherwise states something false about
  the code, and a later reader would believe defect 2 is still live; defect 4 (`art_label.py`, dead and broken) is
  deleted in Chunk 06 after confirming no out-of-tree importer.
  **A fifth defect gets its disposition here, added 2026-07-27:** `tvart.py`'s
  `upload_file` catches every exception, logs it, and returns with
  `remote_filename` still `None`, so the caller records a null content id as an
  uploaded file. It was never in issue #6's four, so nothing scheduled it — while
  the codebase cites it *by name* in two places as the motivating example for
  never reporting success on a failed operation (`envelope.py`'s docstring and
  `observability-strategy.md` § Two Defects to Fix, Not Inherit). **Disposition:
  dies with the 2024 modules at Chunk 20, not fixed in legacy code.** The
  reasoning is the same as defect 3's — the replacement is already designed and
  records `upload_status` explicitly for exactly this reason (`data-model.md` →
  TvBinding) — and it is written down so the defect is not rediscovered as a
  surprise by someone who finds it cited as a lesson and assumes it was fixed.
- **Depends on:** Chunk 01 (the token path work lands on an untracked file)
- **Artifacts consumed:** issue #5, issue #6, `project-preferences.md` § Known
  departures, `operational-spec.md` § Configuration
- **Deliverables:** `config.py` reads `ART_ROOT`, TV address/port, and location
  from the environment; `.env.example` extended in the existing style; README
  dev-setup section (a fresh clone runs without touching source); `art.py:366`
  bare `raise`; issue #6 updated with the four dispositions; **the repo's first
  `tests/` — pytest config at the root**, carrying this chunk's config tests.
  It lands here because this is the first chunk that produces code to test, and
  the no-test-suite departure must close before any substantive chunk; Chunk 06
  splits the suite per plane
- **Carried finding:** "no secret may ever reach a log line" is stated forcefully
  in two artifacts but has no mechanism, no norm-index row, and no chunk — while
  `operational-spec.md` mandates logging resolved config at startup, which is
  exactly where a secret would leak. This chunk writes that startup logging, so
  it owns the redaction helper and the norm-index row that makes it enforceable.
- **Tests:** unit — config loading fails fast with a clear message naming `.env`
  when `ART_ROOT` is missing; no configured secret appears in the startup log
  line (assert on the emitted record, with a secret deliberately set)
- **Acceptance criteria:** the code runs on the dev Mac and the Pi with no source
  edit, only `.env` differences; a missing `ART_ROOT` fails at import with an
  actionable message
- **Done when:**
  1. Acceptance criteria met and tests pass; verified on both machines
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

### Chunk 03: Pi operational hardening and the vendor-risk answer (issues #15, #16, #13)

- **Description:** Three small deployment items done in one hardware sitting.
  Set the journal bound explicitly and carry it in the repo's deploy config, not
  only on the box. *(This read "journald's default scales with the disk it is
  supposed to protect" — retracted 2026-08-04. The persistent default is capped at
  4G, and this machine's journal is volatile anyway, so `SystemMaxUse=` alone binds
  nothing on a stock Pi. The bound is worth setting because a ceiling should be
  chosen and visible, not because the journal could run away.)* Establish on the actual TV whether firmware auto-update can be disabled —
  the vendor has removed art mode by firmware before — and record the finding in
  its three homes (`security-model.md` § Open, `operational-spec.md` § Risks,
  `project-state.yaml` risk factor). The issue #13 storage decision is captured —
  see below.
- **The #13 decision landed 2026-08-04, off-bench, and it needed no hardware.**
  The operator kept the SD card: no USB SSD, no SSD boot, and no network storage.
  Recorded with its alternatives and its trade-off in `operational-spec.md`
  § Risks. Two consequences for the rest of this plan:
  - **No deployment paths move.** The chunk's premise was that the chosen medium
    determines the paths later chunks bake in; the medium did not change, so
    nothing downstream is waiting on it.
  - **The residual risk transferred to the backup path rather than closing.** The
    decision accepts card death at a frequency of once every few years, which
    makes issue #14 / Chunk 20 the entire mitigation instead of a complement to
    it. Chunk 20 sits last in the build order and needs no bench — worth pulling
    forward on that basis, which is an operator call and not a re-plan.
- **Depends on:** nothing outstanding. *(Was: the operator decision on issue #13,
  discharged 2026-08-04.)* ~~The two remaining deliverables need the bench.~~
  **Both landed 2026-08-04.** `deploy/journald.conf.d/10-bound-the-journal.conf`
  caps the journal at 256M and is applied on the Pi; firmware auto-update was
  established as disable-able and disabled, recorded in all three named homes. The
  requirement's own rationale was corrected in the process — systemd caps its
  default at 4G rather than growing with the disk, so an explicit bound buys a
  visible ceiling rather than averting runaway growth.
- **Artifacts consumed:** `operational-spec.md` § Risks, issues #13/#15/#16
- **Deliverables:** new `deploy/journald.conf.d/` drop-in (applied on the Pi);
  auto-update finding recorded in all three named homes and the disable/keep
  decision recorded with its trade-off; ~~#13 decision recorded with
  alternatives~~ — **done 2026-08-04**
- **Tests:** none (config + recorded findings)
- **Acceptance criteria:** `journalctl` reflects the explicit cap on the Pi; the
  vendor auto-update risk in `operational-spec.md` § Risks no longer reads
  "undecided" *(the storage risk half is met — it reads decided as of
  2026-08-04, with the caveat that its mitigation is unbuilt)*
- **Type:** doc-only
- **Done when:**
  1. Acceptance criteria met on the Pi
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

### Chunk 04: Verify the IT8951 build under uv PEP 517 isolation (issue #9)

- **Description:** The uv-for-both-planes decision carries exactly one named
  verification item and this is it: a 2023-era `setup.py` that imports Cython at
  module scope but does not declare it in build-requires fails under PEP 517
  isolation before a single `.pyx` is touched. Prove or disprove empirically on
  the Pi — read the pinned source first (cheap, may answer outright), then a
  throwaway uv project pinning `9f13613`, **not** the real display project. The same
  live install also answers the adjacent-but-distinct interpreter risk (the stack
  last proved on 3.12; 3.13 is an open assumption). If it fails, decide the
  remediation (declare build-requires via an override, vendor the ~1,500 lines,
  or pin differently) and record it as a decision.
- **Depends on:** none (hardware access)
- **Artifacts consumed:** issue #9,
  `platform-and-dependency-findings.md` (both existing IT8951 risks),
  `project-preferences.md` § Language & Runtime
- **Foreign API:** IT8951 (frozen 2023 source build)
- **Deliverables:** outcome recorded in `platform-and-dependency-findings.md`
  alongside the interpreter-version risk, keeping the two distinct; remediation
  decision if needed; issue #9 closed via `/prawduct:backlog`
- **Tests:** the spike **is** the test — a real install on the real target
- **Acceptance criteria:** a definitive recorded answer: the display plane's
  dependency set installs under uv on the Pi (3.13, falling back 3.12), or a
  chosen remediation makes it install
- **Answered 2026-08-04: it installs on 3.13, and no remediation was needed.** The
  chunk's central premise did not hold — the pinned commit declares Cython in
  `build-requires`, so PEP 517 isolation was never going to fail on it. The
  interpreter half is closed too: a current Cython emits 3.13-compatible C for
  those `.pyx` sources on aarch64, so the 3.12 fallback is retired. The real
  blocker was `python3-dev`, undeclared anywhere and failing in `rpi-gpio` rather
  than in IT8951; it is now in `requirements.txt`'s apt line. Detail lives in
  `platform-and-dependency-findings.md` rather than here.
- **Done when:**
  0. verify-api — read `setup.py`/`pyproject.toml` at the pinned commit; capture
     what `[build-system] requires` declares (or that no `pyproject.toml` exists)
  1. Acceptance criteria met; findings recorded
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

### Chunk 05: Replace the samsungtvws pin, verified on hardware (issue #3)

- **Description:** The display plane's rotation design binds to this library's
  verified behaviour, so the pin moves before that plane is built. Select the
  target with evidence, not by default: confirm the PyPI release carries the
  fork's LS03A/B/C/D support before preferring it; check whether async
  `delete_list`'s missing `return` — the library's only removal verb, currently
  unconfirmable — is fixed on the target, and if not, add the local
  confirm-deletion wrapper (or upstream PR) issue #3 scopes. Confirm `upload()`
  chunks with a timeout rather than buffering whole 4K files, and re-confirm the
  dual-callback registration, whose failure modes are asymmetric across TV
  generations.
- **Depends on:** Chunk 01 (fresh pairing token in place)
- **Artifacts consumed:** issue #3, `data-model.md` § Rotation is host-driven,
  `project-state.yaml` → `classification.foreign_apis`
- **Foreign API:** samsungtvws
- **Deliverables:** the pin replaced in `requirements.txt` (the legacy install
  keeps running production; Chunk 06 carries the same target into the display
  project); confirm-deletion wrapper if upstream is still broken; verification
  notes recorded on issue #3
- **Verify-api landed 2026-08-01; the source half is done and the hardware half
  is not.** What the read settled, beyond what the chunk anticipated:
  - **PyPI was never a candidate.** That package ships no async art client and
    no callbacks — the whole TV boundary here is built on both. The choice was
    between fork SHAs, not between fork and release.
  - **`delete_list` is unchanged on master**, so the bump does not fix it and the
    fallback fired: `tv_delete.delete_list_confirmed` verifies against the set's
    own content list. It keeps *unconfirmable* apart from *failed*, because
    collapsing them is the original defect.
  - **`upload()` streams only when handed a path.** The chunker is picked from
    the argument type, so the caller had to change too; passing bytes it had
    already read would have taken the bump and none of the benefit.
  - **The target needs `websockets>=13.0`** — it imports `websockets.asyncio.client`,
    absent from the pinned 12.0. Nothing costed this; it is a two-pin change.
  - **Constructing the client now blocks on network I/O** and raises when the set
    is unreachable, where the pin deferred that to first use. Chunk 12's daemon
    inherits this: construction cannot sit on the event loop, and an asleep
    television surfaces there rather than at `start_listening`.
- **`tv_api_check.py` has no unit tests, and cannot have them here.** It imports
  `samsungtvws`, a Pi-side runtime dependency the root project deliberately keeps
  in `requirements.txt` rather than installing, so the module has no reachable
  test home in this suite. The symbol-grep coverage floor scores it as
  "referenced" on the `tv_delete` symbols it imports — that is the floor behaving
  as documented, not a coverage claim. Its logic goes into the display plane's
  suite with the rest of the TV boundary, where the library is present. The
  deletion wrapper it calls is separately and fully tested, because that module
  takes the client as a parameter and imports nothing.
- ~~**What the bench pass still owes**~~ — **discharged 2026-08-04.**
  `tv_api_check.py` was executed against the live set for the first time and the
  pins are verified. Construction cost, API generation, callback spelling, a real
  4K upload timed by path and a confirmed delete were all measured; the numbers and
  the protocol trace live in `platform-and-dependency-findings.md` § The
  television, which is where a builder will look for them, and are not restated
  here. Two results the chunk did not anticipate — and the first of them is **live on the
  loader running the wall today**, not a future-plane concern: `tvart.py:140` calls
  `upload()` with no `timeout`, and `tvart.py:253` re-selects every file lacking a
  content id, so a mis-reported success becomes a duplicate on the next run. Issue
  #73 carries both halves. **`upload()` reports failure on
  uploads that succeeded** — measured at the default timeout, mechanism partly
  retracted and separated in #73 from what was actually observed — and **only
  `image_selected` of the three registered callbacks fires**, because the other two
  are slideshow-advance events and rotation here is host-driven. Acceptance box
  "LS03A/B/C/D support confirmed" is met **only for LS03D** — the operator holds
  one television and untestable compatibility branching is explicitly not being
  written.
- **Tests:** a scripted hardware pass against the live TV — upload, select,
  confirmed delete, callback registration — captured as notes now, promoted into
  the display plane's test suite in Chunk 12
- **Acceptance criteria:** issue #3's five acceptance boxes checked, including
  real-hardware verification, not just a green install
- **Done when:**
  0. verify-api — read the candidate target's source for `delete_list`,
     `upload()` chunking/timeout, and LS03 support before selecting it
  1. Acceptance criteria met on the Pi
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

**Foundation (Chunks 06–10).** The planes get their structure, then a thin slice
proves the architecture, then the catalogue and the manifest land in full and
the existing 41 works are seeded into them.

### Chunk 06: uv two-plane restructure, lint/test tooling

- **Description:** Restructure onto the decided shape: `curation/` (3.14,
  uv-managed standalone) and `display/` (3.13, system interpreter), each with its
  own pyproject, interpreter pin, and lockfile. **Two sibling projects, not a uv
  workspace** — settled with evidence 2026-07-20, see the governed_by note; the
  chunk builds the decided shape rather than rediscovering it. Wire pytest per plane, adopt ruff (the
  mechanical norm-index rows migrate to lint rules), carry black's line-length
  130, give each plane its own `target-version` (retiring the single `py312`
  departure). ~~Extract the mat regression fixture from `all.json` — all 41 works
  with their hand-tuned mat colours and what a re-render needs — and point
  `nonfunctional-requirements.md` § Output Quality at the fixture as the corpus's
  canonical record.~~ **Descoped 2026-08-03 — see the correction below.** Delete `art_label.py` (issue #6 defect 4) after confirming no
  out-of-tree importer on the Pi. Rename the recovered `r` freeze to say what it
  is (evidence, not scratch) — landed 2026-07-27 as `deploy/pi-freeze-2024.txt`,
  after Chunk 06 shipped without it. Legacy modules stay at the root, running
  production, per the recorded assumption.
- **Depends on:** Chunk 04 (display's dependency set must be known to install
  under uv before the project is stood up), Chunk 05 (the samsungtvws target is
  what the display project pins)
- **Artifacts consumed:** `project-preferences.md` (Language & Runtime, Tooling,
  Enforcement), `operational-spec.md` § The Curation Interpreter, issue #11
- **Deliverables:** new `curation/pyproject.toml`, new `display/pyproject.toml`,
  per-plane lockfiles and venvs; ruff config with the migrated rules;
  the `all.json` keep-and-track call recorded; `art_label.py` deleted; `r`
  renamed; `test_commands` declared in `project-state.yaml` for both planes
- **Tests:** both plane suites runnable and green; ruff clean
- **Acceptance criteria:** both venvs resolve from their locks (display's on the
  Pi); `uv run pytest` green in both projects; `all.json` is the corpus's
  canonical record and stays tracked, per the amended artifact
  <!-- The fixture half was deferred at build and DESCOPED on 2026-08-03 by Chunk
       18B, which this entry had explicitly delegated the call to ("this chunk
       decides whether that file is still worth having or the seeded rows are the
       corpus"). Three things were struck rather than left standing: the fixture
       deliverable under tests/fixtures, the test "fixture round-trip (41 works,
       every mat colour present)", and the criterion naming that fixture as the
       canonical record. A landed chunk asserting an acceptance criterion that can
       never come true reads to an auditor as a missed deliverable, and the next
       person to pick it up would build the copy the product decided against.
       The reason lives in `nonfunctional-requirements.md` § Output Quality and in
       `curation/tests/unit/test_mat_corpus.py`'s docstring: a second file holding
       the same 41 colours drifts silently from the one the seed loads, because
       both keep parsing and neither fails. Issue #11 asked for the extraction and
       is closed against this decision.
       The struck fixture is named in prose rather than backticked, because the
       deliverable check reads a backticked path in a chunk entry as a file the
       chunk was meant to add — the same reason Chunks 18A and 18B give for the
       cache directories and the display package.
       "Artifacts consumed" still lists issue #11, deliberately: it records what
       this chunk was written against, and editing that list after the fact would
       erase the trail from the requirement to the decision that retired it. -->
- **Superseded in part by:** Chunk 18B (the fixture half, 2026-08-03)
- **Done when:**
  1. Acceptance criteria met and tests pass
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

### Chunk 07: Walking skeleton — catalogue core → service layer → MCP tool, end to end

- **Description:** The thin vertical slice through the entire curation
  architecture, proving the layers connect before anything widens: a minimal
  catalogue (Artwork, Artist, Theme on SQLite) → a service layer that
  owns all logic → the registry → one generated tool (`art_catalogue`, actions
  `list`/`get`/`help`) served over streamable HTTP from the same ASGI app as a
  placeholder UI route. This chunk lands the project-wide concepts everything
  else binds to, so the surfaces are enumerated here deliberately: the registry
  record shape (description, params, example, tips — no logic), wire-schema
  generation, per-action validation, generated `help`, the error envelope
  (`isError` derived from `success`, errors that teach: what was wrong, the valid
  set, an example, a help pointer), mandatory tool annotations, and the
  ≤2KB-description budget. The known SDK hazard is handled, not discovered:
  Starlette does not run a mounted sub-app's lifespan, so the host app must enter
  `session_manager.run()` in its own lifespan or every `/mcp` request fails.
- **Depends on:** Chunk 06
- **Artifacts consumed:** `architecture.md` (§ Direction, § Decision Log — the
  FastAPI decision and the mount hazard), `api-contract.md` (§ The surface,
  § Argument shape, § Error Model, § Help), `data-model.md` (the three entities),
  `boundary-patterns.md` § Service layer
- **Exposed API:** mcp-tool-surface (versioning and error-model decisions
  recorded — `design_decisions.api_versioning_approach` /
  `api_error_model_approach`, both `status: active`)
- **Foreign API:** mcp Python SDK (`mcp>=1.28.1`)
- **Deliverables:** new `curation/src/curation/persistence/`, new
  `curation/src/curation/services/`, new `curation/src/curation/mcp/` (registry +
  bindings), the ASGI app with `/mcp` mounted and the lifespan wired, all five
  tool **names** registered from birth (names are frozen; actions grow additively
  per the contract — unbuilt tools carry only `help` and return a teaching error
  otherwise), a first contract test booting the real server and asserting
  `list_tools()` against the registry
- **Tests:** unit — service methods, registry generation, error envelope
  derivation; contract — server boots, five tool names pinned, descriptions
  under budget, annotations present; integration — a real MCP client calls
  `art_catalogue(action='list')` against a seeded catalogue
- **Acceptance criteria:** Claude Code (or the MCP inspector) pointed at the
  server lists the tools and reads the seeded works; the handler layer contains
  dispatch and formatting only
- **Critic mode:** final
  <!-- Keystone override: inference would pick `chunk` mid-plan, but every later
       surface builds on this slice's shape — worth the full review now. -->
- **Done when:**
  0. verify-api — re-confirm the mount/lifespan behaviour and
     `session_manager` constraints against the installed SDK version (they were
     verified from source at design time; the pin may have moved)
  1. Acceptance criteria met and tests pass
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

### Chunk 07B: The durable seam — persistence reshaped to the `DurableStore` contract

- **Description:** Split the catalogue's persistence into two layers so that the
  twelve entities Chunk 08 adds are written once, against their final shape. Below:
  a generic, table-oriented durable store owning the connection, the lock, the
  schema, and constraint-refusal translation, exposing `fetch_one` / `upsert` /
  `delete` / `scan` keyed by table plus a primary-key mapping — the decomposition
  and naming of 3tears' `DurableStore` protocol, so that a later collection layer
  is an adapter rather than a rewrite. The **argument lists are a subset**, not a
  match: the divergences (sync methods, no `conn` transaction handle, no `cas`
  fence, a required rather than optional `pk`) are enumerated in the module
  itself, because a parity claim wider than the code is how the next reader is
  misled about what can be swapped. Above: `SqliteCatalogue`
  as the domain adapter, mapping records to rows and owning ordering, paging and
  totals. This is a refactor: no existing test changes, and no change to what any
  caller receives. The one deliberate exception is the journal — a refused write
  logs from both layers, so that the record's identity and the SQL cause are each
  recorded by the layer that can see them.
- **Depends on:** Chunk 07
- **Artifacts consumed:** `3tears-integration-findings.md` (§ Answer 2 — the
  contract being matched and why it is worth matching), `architecture.md` § Data
  Ownership (single writer per store), `project-preferences.md` (async at the I/O
  boundary, synchronous core)
- **Foreign API:** none — 3tears' `DurableStore` is matched structurally and
  **not imported**; no dependency is added
- **Deliverables:** new `curation/src/curation/persistence/durable.py`;
  `curation/src/curation/persistence/sqlite.py` reduced to the domain adapter; the ordered-page read
  named as sitting deliberately outside the matched contract, because 3tears'
  contract has no ordered paging and its collection layer never will
- **Tests:** unit — the durable store's own contract, including the
  insert-versus-upsert conflict modes and the constraint-refusal translation that
  `SqliteCatalogue` has never had a direct test for; a read-compatibility test
  that rebuilds a catalogue from the previous revision's frozen DDL and inserts
  and reads it back through the current adapter, so the on-disk contract is
  evidence rather than assertion; a structural test asserting that only the
  durable store imports `sqlite3`, since a stray import elsewhere would pass every
  behavioural test while dissolving the seam; the existing service, contract and
  integration suites stand unchanged as the behaviour-preservation evidence
- **Acceptance criteria:** both suites pass with no test modified; a catalogue
  written before the change is read correctly after it (same file, same schema);
  no module under `curation/src` outside the durable store imports `sqlite3`
  (tests may, and one does). The last two are pinned by tests so they keep holding
  through Chunk 08; "no test modified" is a property of the diff, evidenced by
  review of the change set
- **Critic mode:** chunk
- **Done when:**
  1. Acceptance criteria met and tests pass
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

### Chunk 08 was split into 08A and 08B (2026-07-27)

Chunk 08 as authored was the whole of `data-model.md` beyond the three entities
Chunk 07 proved: eleven entities, fifteen constraints, three state machines and
startup reconciliation — an estimated ~2,500 lines with tests. That is a single
Critic round over a diff large enough that review quality degrades
(`methodology/building.md` § Session Scope Discipline), on the most
contract-setting chunk in the plan. The operator chose the split. Nothing is
descoped: every entity, constraint, state machine and acceptance question below
appears in exactly one of the two halves, and the split line is the one the model
already draws — the accepted catalogue versus the pre-acceptance pipeline.

The 07/07B precedent is the evidence: two of that split's five defects were
unreachable from the smaller surface and were found only because the smaller
surface was reviewed on its own.

### Chunk 08A: The accepted-catalogue entities, their constraints, and `display_fit`

- **Description:** Everything `data-model.md` says about a work that has already
  been accepted: Source (with `source_class` as the load-bearing branch point),
  Original, Rendition (`tv_display`/`thumbnail` only — no `label` kind), MatColor
  with history, ThemeMembership. The Artwork state machine (`archive`/`restore`).
  Constraints 1–6, 10, 12 and 13 enforced at write time in the service layer.
  Multi-row constraints (one active Theme, one current MatColor, one primary
  Source) need a transaction seam on the durable store, which lands here — the
  matched framework contract threads a `conn` handle through every method for
  exactly this reason, so a seam is conformance, not divergence.
- **Depends on:** Chunk 07B
- **Artifacts consumed:** `data-model.md` (entities Source, Original, Rendition,
  MatColor, ThemeMembership; Artwork state machine; constraints 1–6, 10, 12, 13),
  `architecture.md` § The theme manifest
- **Carried finding:** the curation-side directive sequence counter is pinned as
  catalogue-side by `architecture.md` but has no modelled home, and a catalogue
  restore restores it — so it is part of the persisted format. Give it one here
  (a settings/singleton row or equivalent) rather than letting Chunk 09 invent it
  implicitly; `pinned_work_id`'s clearing rule is unstated and settles here too
- **Deliverables:** the accepted-catalogue schema in
  `curation/src/curation/persistence/`, its service-layer operations and the
  Artwork transitions, `display_fit` as the single service-layer derivation
  (never stored), the directive-sequence settings row
- **Tests:** unit per constraint (each of 1–6, 10, 12, 13 has at least one test
  that fails without its enforcement); the Artwork transitions including the
  illegal edges; the durable transaction seam rolls back a partial multi-row write
- **Acceptance criteria:** the schema answers Q1, Q2, Q6, Q7, Q8 and Q9 from
  `data-model.md` § What this data must answer, demonstrated by a test per
  question
- **Done when:**
  1. Acceptance criteria met and tests pass
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

### Chunk 08B: The discovery entities, both state machines, startup reconciliation

- **Description:** Everything `data-model.md` says about the pipeline before
  acceptance: DiscoveryRun (both kinds, all nine statuses), CandidateWork,
  CandidateImage, SpendRecord (attribution only — it enforces nothing),
  ResolveRunWork. The DiscoveryRun and CandidateWork state machines. Constraints
  7–9, 11, 14 and 15 enforced at write time in the service layer, including the
  two-scope suppression rule (Q11) and the single-entry-point rule for
  `awaiting_better_image` (constraint 15). Startup reconciliation moves
  process-held runs (`resolving_works`, `resolving_images`) to `interrupted` —
  deliberately not `awaiting_approval`, which is human-held state that must
  survive a restart — releasing ResolveRunWork coverage and logging one WARNING
  per run moved, which is the only signal a run died.
- **Depends on:** Chunk 08A
- **First task, carried from 08A's Critic round:** **split `CatalogueService`
  before adding to it.** It is one class over nine entity families and ~740 lines;
  this chunk adds five more families, and two reviewers independently called the
  split out. The seam that has been waiting for a second concern is here — a
  `DiscoveryService` alongside the catalogue one, both bound by a small container
  the surfaces take, so `create_app` and the MCP bindings stop naming a single
  service class. Do it first, as its own commit, so the entity work lands against
  the shape it will keep.
- **Artifacts consumed:** `data-model.md` (entities DiscoveryRun, CandidateWork,
  CandidateImage, SpendRecord, ResolveRunWork; both state machines; constraints
  7–9, 11, 14, 15), `api-contract.md` § `set_verdict` cannot set
  `awaiting_better_image`
- **Deliverables:** the discovery-side schema, its service-layer operations and
  transitions, acceptance as promotion (CandidateImages become Sources),
  reconciliation on startup
- **Tests:** unit per constraint (each of 7–9, 11, 14, 15 has at least one test
  that fails without its enforcement); state-machine transition coverage
  including the illegal edges (`set_verdict` refusing `awaiting_better_image`,
  resolve runs never reaching phase-1 states); reconciliation — a seeded
  process-held run is moved, an `awaiting_approval` run is not, coverage is
  released
- **Acceptance criteria:** the schema answers Q3, Q4, Q5, Q10, Q11 and Q12 from
  `data-model.md` § What this data must answer, demonstrated by a test per
  question
- **Done when:**
  1. Acceptance criteria met and tests pass
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

### Chunk 09: Manifest builder, themes, directives — `art_theme` and `art_display`

- **First task, carried from 08B's Critic round:** **extract the theme and
  display concern out of `CatalogueService` before adding to it.** 08B split the
  service layer by adding `DiscoveryService` beside it, which is what the 08A
  finding asked for and is *not* what it was worried about: `CatalogueService` lost
  36 lines and still stands at ~743 over nine entity families, and three of the
  five tool nouns resolve into it. This chunk is the one that grows it — theme
  create/update/delete/reorder, display sync/show_now/next, and the manifest
  builder all land there otherwise. The container exists for exactly this, so a
  third service is cheap now and more expensive every chunk after. Do it first, as
  its own commit, the way 08B did — and update `architecture.md`'s
  internal-layering diagram in the same change, since it currently names two
  services.
- **Description:** The inter-plane contract, curation side. The manifest builder
  is the one place catalogue readiness is evaluated; membership in the manifest
  IS readiness, and **the build reports its exclusions per work with reasons — a
  builder that only returns a list is an incomplete implementation of the
  design**. Atomic write (temp + `os.replace`), schema version, rotation
  settings, label fields, and the directive block with its three pinned
  semantics: the sequence is monotonic for the life of the catalogue
  (curation stores it catalogue-side; rebuilds carry it forward unchanged — only
  `next`/`show_now` increment), rapid directives coalesce latest-wins, and the
  display side's regression/persistence obligations are Chunk 12's. Full
  `art_theme` (create/update/delete/add/remove/reorder/activate) and
  `art_display` (sync/show_now/next; `status` reads the heartbeat file and
  reports honestly that none exists yet). The **TV panel's physical geometry**
  enters configuration here — curation's alone, since curation composes the mat —
  and is logged at startup.
- **Depends on:** Chunk 08
- **Carried finding:** archiving a work has no specified effect on manifest
  membership, and `security-model.md` bound 4 depends on it having one. Settle it
  here, where readiness is evaluated: an archived work leaves the manifest.
- **Carried from 08A:** `Theme.rotation_interval_seconds` and `Theme.shuffle` are
  specified in `data-model.md` and are **not yet in the schema**. They exist to be
  written into the manifest's rotation settings, and nothing reads them until this
  builder does — but adding them is the **first change that widens a table an
  existing catalogue file already has**, so it needs a migration rather than an
  appended column. `CREATE TABLE IF NOT EXISTS` silently does nothing to a table
  that exists, so an old file would read back a `KeyError` on the new column
  rather than an error anyone could act on. The frozen-DDL compatibility test in
  `curation/tests/unit/test_catalogue_store.py` is what will fail first.
- **Artifacts consumed:** `architecture.md` (§ The theme manifest, § Readiness),
  `api-contract.md` § How `art_display` reaches the display plane,
  `boundary-patterns.md` § curation ↔ display contract,
  `operational-spec.md` § Configuration
- **Deliverables:** new `curation/src/curation/manifest/` (builder + exclusion
  report), theme services, the two tools' actions live, directive sequence
  persisted catalogue-side, panel-geometry config
- **Tests:** unit — exclusion reasons per unreadiness cause; atomicity (no
  reader ever observes a partial manifest); sequence carried unchanged through
  rebuild and theme switch, incremented only by directives; integration —
  `activate` produces a manifest whose entries are exactly the readiness-filtered
  theme
- **Acceptance criteria:** switching the active theme rewrites the manifest with
  zero TV writes implied; every excluded work is named with a reason in the
  build's report; directive actions return "the directive is written", never a
  claim the wall changed
- **Done when:**
  1. Acceptance criteria met and tests pass
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

### Chunk 10: Seed the catalogue with the existing corpus (v1 scope item)

- **Description:** The v1 scope commits to a "new catalogue built through
  curation, seeded with the existing 41 artworks as worked examples"
  (`product-brief.md` § Scope, `data-model.md` — "the 41 legacy records are
  re-ingested through curation as new works"). This chunk owns it. Without it
  the new catalogue has no ready work by any built path until Chunk 18B, and the
  display chunks below have nothing to put on the wall — which is why it sits
  here rather than late: **it is what makes Chunks 12–13's cutover acceptance
  executable.** Re-ingest, do not migrate: read `all.json` as an input file and
  mint fresh entities through the service layer, so every catalogue invariant
  from Chunk 08 applies to the seeded rows exactly as to discovered ones.

  **The index holds 41 records describing 40 works** *(measured 2026-08-01;
  the 2026-07-20 pass counted records and called them works)*. Two records are
  one painting — same URL, same master file, same title, differing only in
  `mat_hexrgb` (`#433735` and `#1c1818`). Seeding both would put one painting in
  the catalogue twice, which is what a minted identity exists to prevent, so they
  collapse to one work. *(Operator decision 2026-08-01: the later record in file
  order wins and the earlier colour is **dropped**, not retained as superseded
  history — the report names the discarded value so the choice stays visible.)*
  This also reconciles the "41 records but 46 files in the master tree" note in
  learnings: 40 referenced files plus 6 unreferenced ones, under $ART_ROOT on the
  Pi rather than anywhere in this checkout.

  **The corpus is complete on identity and incomplete on the label** — measured
  against the tracked `all.json`, not assumed. All 41 records carry `title`,
  `artist`, `date_created`, `raw_file`, `mat_hexrgb` and pixel dimensions. The
  gaps, **counted per work after parsing** *(corrected 2026-08-01 — the previous
  figures mixed units in one sentence: nationality and `artist_details` were per
  record, "8 have no lifespan" was per distinct artist)*: 8 of 41 records carry
  no `artist_details` at all, and the index's own parse leaves 14 works with no
  nationality. Reading the source's words rather than that parse recovers nine of
  those, leaving **5 works with no nationality, 9 with no birth year, and 2 each
  lacking medium and physical dimensions — different pairs, overlapping in one
  work.** A missing *death* year is not a gap: two of these artists are alive.

  That shapes the work: Artist parsing cannot assume `artist_details` exists and
  must fall back to the flat `artist` field, which for one record carries the
  whole clause; the label must render legibly with nationality and dates absent
  (data-model Q9 wants them, so a partial label is a real outcome, not an error);
  and the 2 works without physical dimensions **seed with dimensions null, are
  reported, and still reach the wall.** *(Corrected 2026-08-01: this said they
  "can get neither mat geometry nor a floor classification", and Chunk 09's built
  code says otherwise — `assess_display_fit` judges an original's **pixel** size
  against a box built from panel geometry and a mat width in inches, and reads
  nothing about the artwork's physical size. It also called this "the same
  unknown-dimensions case `data-model.md`'s `display_fit` note still owes a rule";
  that note owes no such rule. Physical dimensions are label text.)*

  **Backfilling from the source URL is out of scope here** — these works
  are re-fetchable, and completing them is discovery's job, not seeding's.
  Originals point at the existing masters, and renditions at the existing
  renders, in the deployed image tree under ART_ROOT — the raw and ready
  directories on the Pi, which are not part of this checkout — with
  `source_content_hash` computed at ingest so Chunk 18B's staleness rule governs
  them from birth.

  *(Corrected 2026-08-04: **there is no `ready/` left to point at.** The Pi was
  rebuilt onto a fresh card and the 2024 renditions were on the old one; the
  masters survive on the operator's Mac at `~/art/raw` but `ready/` was never
  copied off. Nothing about the seeding path changes — it already treats a
  missing rendition as a reported absence rather than an error, which is exactly
  the case this turned out to be — but every work now seeds `no_rendition`, and
  re-rendering the corpus for the wall is real work that was assumed already
  done. The television still holds its uploaded copies; recovering identity from
  them is Chunk 12's adoption path, not a file the tree can be pointed at.)* Known defects in the legacy shape are corrected on the way
  in, not carried: identity becomes a UUID (never the source URL),
  `artist_details` is parsed into Artist rows, and `tv_content_id` is **not**
  written to the catalogue — it is per-device state and belongs to the display
  plane (it is seeded into TvBinding in Chunk 12).
- **Depends on:** Chunk 09 (the manifest build is how seeding is proven)
- **Artifacts consumed:** `data-model.md` (Artwork, Artist, Source, Original,
  Rendition, MatColor; the re-ingest note), `product-brief.md` § Scope,
  `nonfunctional-requirements.md` § Output Quality (the floor)
- **Deliverables:** a one-shot seeding path driving the curation service layer
  (invocable, re-runnable, and idempotent — re-running must not duplicate
  works, and must fill in whatever the tree did not hold last time, so the
  report names a problem the tool can also fix); the 40 works in the catalogue
  with artists, sources, originals, renditions, and mat colours; `MatColor.method`
  recorded as the legacy hand-tuned value, never as a fresh derivation; a report
  of anything that did not seed cleanly, per work with a reason — silence is not
  success
- **Tests:** unit — `artist_details` parsing across the corpus's real shapes
  (the multi-line "Charles Demuth\nAmerican, 1883–1935" form, the parenthetical
  form the index's own parser silently dropped, **and the 8 records carrying no
  `artist_details` at all**, which must fall back to the flat `artist` field
  rather than fail); a work with no physical dimensions seeds with nulls and is
  reported, never silently given a default size; identity is a UUID and no row
  carries a source URL as identity; no `tv_content_id` reaches the catalogue;
  idempotence — seeding twice yields 40 works, not 80, and does not grow the mat
  history by a row per run; integration — after seeding, a theme over all 40
  builds a manifest whose entries and exclusions together account for all 40,
  and a work whose render is missing from the tree is excluded by name and reason
  *(corrected 2026-08-01: this required the 2 dimensionless works to be the
  excluded ones, which contradicts the readiness rule Chunk 09 built — that rule
  asks for an original, a mat and a current render, and reads nothing about
  physical dimensions. Excluding them would take two works off the wall that are
  showing today.)*
- **Acceptance criteria:** all 41 records are accounted for — 40 works in the
  catalogue plus the one collapsed duplicate, named in the report with the mat
  colour it dropped; a theme built over them produces a manifest whose exclusions
  are exactly the works with a named, understood cause, never a silent drop;
  every work with incomplete label metadata is listed in the seed report, so the
  gap is visible now rather than discovered at the wall
- **Done when:**
  1. Acceptance criteria met and tests pass
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

### Chunk 10B: The first browser surface — catalogue, themes, manifest, health

- **Description:** The `/` and `/api/*` surfaces `architecture.md` has always
  drawn, built now over the services that exist rather than waiting for the ones
  that do not. **This is Chunk 19's scope, split — not new scope.** It takes the
  catalogue/theme/health third of 19's list and leaves the discovery two-thirds
  where they are. Scope: the work grid, image-forward, one card per work, with
  `display_fit` and rendered-inches labels and non-colour state indicators per the
  accessibility decision; a work detail view (metadata, artists, sources,
  renditions); themes (create, add/remove, reorder, activate); the manifest view —
  what the active theme's manifest contains and **every exclusion with its reason**,
  which is Chunk 09's exclusion report reaching a human for the first time; and the
  health panel, stating heartbeat age in absolute terms and reporting honestly that
  no heartbeat file exists yet, which is the honest answer before any display
  device has run.
  Thumbnail serving is a deliverable, not an assumption: the seeded renditions are
  4K files, and a grid of 41 of them is not a page. WCAG 2.1 AA baseline; UI chrome
  never competes with artwork for contrast.
- **Out of scope, deliberately, and named so it is not read as dropped:** intent
  entry and its estimate, the run view, the approval gate, cost display, and the
  review grid with alternates behind each card. Every one of those binds a service
  built in Chunks 14–18. They stay in Chunk 19.
- **Depends on:** Chunk 09 (themes and the manifest with its exclusion report),
  Chunk 10 (41 works with images on disk — a UI over an empty catalogue proves
  nothing), and the UI checkpoint, which moves here from before Chunk 19

**Four things this chunk had to settle before it could be built, recorded here
because each changes an artifact rather than only this chunk's code.**

*The artwork box needs two deployment values that were specified and never
surfaced.* `nonfunctional-requirements.md` § "The mat is geometric, and the floor
is physical" fixes the mat in inches and the floor as a minimum rendered size in
inches, and `Settings` carries neither — so `assess_display_fit`, built in Chunk
09 with tests, has **no production caller**, because nothing can construct the
`ArtworkBox` it takes. `MAT_WIDTH_INCHES` and `RESOLUTION_FLOOR_INCHES` join the
deployment surface here, defaulting to the reference panel's 2.5" and 12" — the
figures that artifact's own worked example uses. This is the chunk that first
needs the verdict, which is why it is the chunk that wires it.

*Pillow moves from the render chunk (now 18B) to here.* Thumbnail serving is a named deliverable
and the seeded renditions are 4K files; nothing in the standard library decodes
a JPEG, and `curation/src/curation/seed/images.py` reads only the SOF header for
dimensions precisely because it needed no decoder. Pillow was already the declared
acquisition/mat-engine dependency for this plane, so what changes is its arrival,
not the dependency set. Named rather than slipped in, by the same rule that made
`uvicorn`-not-`[standard]` a recorded decision.

*Thumbnails get a new derived directory in the image tree, named `thumbs`, and
the existing `tv-thumbs` is annotated rather than reused.* Both are directories
under `ART_ROOT` at runtime rather than anything in this checkout, which is why
they are named here without a path — the full contract, and the only normative
statement of it, is the `ART_ROOT` filesystem row in `boundary-patterns.md`. In
the 2024 tree, `tv-thumbs` holds images **downloaded from the television**, keyed
by `tv_content_id` — per-device TV state, which is exactly the class this
catalogue excluded by design; putting curation's own thumbnails there would
re-import the thing the model rejects. The new one is a derived,
device-independent cache and joins that contract as one, and the `tv-thumbs`
entry there is annotated the way the retired `label` entry was on 2026-07-20, for
the identical reason.

*The browser surface is the `/api/*` JSON API plus a client that renders it, not
server-rendered templates.* `architecture.md` already draws the UI and its HTTP
API as separate things and `project-state.yaml`'s FastAPI decision names "typed,
paginated, partial data — that is pydantic response models" as what the framework
was chosen for. Server-rendering the pages would leave `/api/*` either unused or
carrying a second shape of every read, which is the divergence the shared service
layer exists to prevent, one layer up. Pydantic is declared here, as that decision
anticipated ("the typed response models … arrive with the HTTP API"). No template
engine, no build step, no framework: the client is one stylesheet and one script.
- **Artifacts consumed:** `architecture.md` (§ Serves three surfaces from one ASGI
  app, § the internal-layering diagram), `api-contract.md` (§ the HTTP surface
  carries no stability obligation; § operation logic lives ONLY in the service
  layer), `security-model.md` (LAN-only, no authentication — the single-principal
  position is deliberate and already recorded),
  `design_decisions.accessibility_approach`
- **Visual change:** yes — the first human-facing surface this product has had
- **Deliverables:** real handlers in `curation/src/curation/http/` (thin bindings:
  unpack, call one service method, format), the pages above, a thumbnail path
- **Tests:** integration — every handler is dispatch + formatting over an existing
  service method, so the service-layer norm holds by construction; the flows
  exercised through the real HTTP surface against a booted server, per the suite's
  existing rule that surface work runs against real uvicorn, not an in-process
  transport
- **Acceptance criteria:** from a browser, touching no filesystem, no JSON and no
  SSH, a curator can see all 41 works with their images, build a theme, activate
  it, and read exactly why any work is absent from the resulting manifest; the
  health panel states observations with ages, never verdicts, and says plainly that
  the display plane is not running yet
- **Done when:**
  1. Acceptance criteria met and tests pass, plus the operator's look
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

**Contract enforcement (Chunk 11).** Pinned before the display plane and
discovery build against these surfaces.

### Chunk 11: Contract tests — MCP evaluation harness (issue #17)

**Split 2026-08-01. The plane-isolation half (issue #7) moved to Chunk 12, and
this is a descope recorded rather than a requirement dropped.** The premise
written here — that the display plane is a package this chunk could point a test
at, "the boundary now exists, from Chunk 06" — is false. Chunk 06 landed as
*curation only, display plane deferred*, and that package has never existed. The
only isolation test writable today would walk an empty tree and pass, which this
plan's own acceptance bar rejects in the next paragraph. Chunk 12 creates it, so
the test belongs to the chunk that gives it a subject; issue #7 is unchanged and
still open. The manifest-channel norm row was corrected the same day — it had
named this test as an existing Test mechanism, and never had one.

*(Paths in this paragraph are deliberately unfenced: the record lint reads a
backticked path in a chunk section as a claimed deliverable, and a descope
paragraph naming what this chunk is **not** shipping would otherwise report as
two missing deliverables.)*

- **Description:** The MCP evaluation harness, in the two halves the artifacts
  actually distinguish. `api-contract.md` § Validation is explicit that the
  contract tests assert the surface's *shape* while the harness asserts that a
  model can *use* it, and the shape half already landed with Chunks 07–09.
  So: (a) a **scenario runner** driving real product flows through the
  consolidated tools as a real MCP client, deterministic and in the default
  suite, where each step threads an id out of the previous step's envelope —
  the defect class no per-tool test can see, since two tools can each be correct
  and still disagree about what they hand each other; and (b) a **model-driven
  evaluation** behind a `llm_eval` marker, deselected by default, running
  verifiable operator prompts and measuring accuracy, call count and error rate.
  The split is not cost — it is that a model may legitimately reach a goal by a
  different route between runs, so it can measure but must not gate.
- **Depends on:** Chunks 07–09 (live tools to pin and real flows to drive)
- **Artifacts consumed:** `api-contract.md` § Validation and § Versioning,
  `boundary-patterns.md` § Test Levels, issue #17
- **Deliverables:** `curation/tests/contract/scenarios.py` (the runner: real
  client boot, transcript, envelope invariants checked on every call),
  `curation/tests/contract/test_mcp_scenarios.py` (first scenarios),
  `curation/tests/eval/` (driver + model-driven scenarios + the driver's own
  deterministic tests), the `llm_eval` marker and `eval` dependency group
- **Tests:** this chunk **is** tests; its own acceptance is that each guard
  demonstrably fails on a violation (a renamed tool, an over-budget description,
  a tool that echoes back a key its neighbour does not expect) — a green test
  that cannot catch a real violation is worse than none
- **Acceptance criteria:** scenario suite green against the real server and each
  guard proven able to fail by mutation; the model-driven suite deselected by
  default and skipping cleanly when its dependency group or API key is absent;
  the manifest-channel norm row no longer claims an enforcement artifact that
  does not exist
- **Done when:**
  1. Acceptance criteria met and tests pass
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

**Display plane (Chunks 12–13).** Built on the Pi, verified on the wall.

### Chunk 12: Display daemon core — poll, rotate, TvBinding, directive semantics

- **Description:** The reconciliation loop: poll the manifest's mtime (~1 s — the
  interval is set by `next`, not by theme switching), adopt new manifests, refuse
  an unrecognised major version at ERROR and keep the last good one, ensure every
  listed work is uploaded (TvBinding in `display-state.sqlite`, `upload_status`
  explicit so a failed upload can never read as success — the 2024 defect made
  impossible), rotate via host-driven `select_image`, disable the native
  slideshow once (`set_slideshow_status(duration=0)`), skip missing files at
  WARNING and continue. Directive semantics display-side: persist the
  last-acted-on sequence (a restart must not re-execute the last jump under
  `Restart=always`), coalesce latest-wins, and on sequence regression re-baseline
  without acting, logging one WARNING — a catalogue restore must not replay a
  stale pin. Ports the sun-position brightness behaviour. TV access sits behind
  an interface.
- **Depends on:** Chunks 05 (verified library), 06 (display project), 09
  (manifests to read), 10 (a seeded catalogue, so the wall has content to
  rotate), 11 (the contract suite this plane's manifest reading is checked against)
- **Carries the plane-isolation test (issue #7), moved here 2026-08-01.** It was
  Chunk 11's, on the premise that a `display/` package already existed; it did
  not, and a test with no subject would have passed over an empty tree. **This
  chunk is where that package is born, so this is where the guard becomes
  writable — and it has to land with the package, not after it**, because the
  window in which display-plane code exists unguarded is exactly the window in
  which "just fetch the label text live" gets written and passes every test.
  Issue #7's design questions are settled as this plan frames them: "the display
  plane" is the `display/` package; imports are checked transitively (a
  direct-only check is evaded by one shared helper); the no-network-channel half
  bans HTTP client construction in display modules outright, with the TV
  websocket explicitly exempt because talking to the TV is display's job. Static,
  so it holds whether or not curation is running — which is the point, since a
  green suite is what a violation looks like without it. Both halves must be
  proven able to fail (plant a curation import; plant an HTTP client), issue #7's
  decisions recorded on the issue, and the manifest-channel norm row in
  `project-preferences.md` moved back from Critic to Test naming this file.
- **Carried from Chunk 09 — what an unsatisfiable pin does.** `show_now` refuses
  any work that is not *displayable* (widened at build 2026-07-31; see
  `api-contract.md`). It does **not** check *theme membership*, so a perfectly
  ready work that is simply not in the active theme can be pinned and the
  manifest's `entries` will not contain it. **That is the default path, not a
  rare race** — it is available on every call, and Chunk 09's own
  `test_the_directive_reaches_the_manifest` demonstrates it. The membership check
  was deliberately not added at the writing end, because only the display plane
  can decide what to do with a pin it cannot resolve. Answer it here: log one
  WARNING and continue rotating rather than stall or crash, by the same posture as
  a missing render file. Then say so in `api-contract.md` § How `art_display`
  reaches the display plane.
- **Artifacts consumed:** `architecture.md` (§ The theme manifest, § Failure
  Modes, § display component), `data-model.md` (§ Rotation is host-driven,
  TvBinding), `observability-strategy.md` § What Each Failure Looks Like
- **Foreign API:** samsungtvws (target verified in Chunk 05)
- **Deliverables:** new `display/src/display/daemon.py`, new
  `display/src/display/tv/`, new `display/src/display/state/` with
  `display-state.sqlite` (TvBinding + last-acted-on sequence), structured logging
  with `work_id` correlation, resolved `ART_ROOT` and the **e-paper panel's**
  geometry logged at startup (display never reads the TV's physical size);
  **the binding table starts empty, and the television's pre-existing uploads are
  orphans to be removed rather than assets to adopt.**

  **Two things this plane owes that its manifest alone does not give it**, both
  raised by Critic review on 2026-08-05 and deliberately carried here rather than
  filed, because this is the work that will meet them:

  1. **`tests/preferences/test_plane_isolation.py`, landing WITH the first
     display module and not after.** An AST/import check that no module here
     imports a curation module or constructs an HTTP client, the television
     websocket exempted. Imports checked transitively — a direct-only check is
     evaded by one shared helper. Both halves must be proven able to fail: plant
     a curation import, plant an HTTP client. It cannot be written earlier, since
     a check over an empty package passes vacuously; and it must not be written
     later, because the window where display code exists unguarded is the window
     in which "just fetch the label text live" gets written and passes every test
     — curation is up in development and in every test, so a green suite is
     exactly what a violation looks like. `project-preferences.md` § Enforcement
     moves the manifest-channel norm from Critic back to Test when it lands.
  2. ~~**A committed lockfile.**~~ **Discharged early, 2026-08-05 (`395910a`) —
     no longer owed by this chunk.** It was owed because this was the only plane
     without one, against three dependencies with no upper bound and one pinned to
     a git commit, and the television client is precisely where an unpinned resolve
     has already broken an import once. It arrived ahead of the chunk because
     making `CLAUDE.md`'s documented display-plane commands actually run produces a
     lock — `uv run` cannot proceed without one — and those commands turned out
     never to have been executed. `display/uv.lock` is tracked and pins the
     `samsungtvws` fork to its exact rev.

     **Deliverable 1 above is unaffected and still owed**, for the reason it
     states: a plane-isolation check written over an empty package passes
     vacuously, so it lands with the plane's first module.

  > **This replaces a one-shot TvBinding adoption path, descoped 2026-08-05 on
  > evidence rather than on preference.** The deliverable was to seed bindings
  > from the 41 legacy `tv_content_id` values in `all.json`, so that a fresh empty
  > table would not re-upload 41 images and orphan the set already on the
  > television. **Its premise no longer holds.** The 2024 renders those uploads
  > were made from are gone from the art tree — the ready directory under the art
  > root held exactly one file when this was written —
  > and seeding only ever recorded a 2024 render as a work's television rendition
  > when that file was present, so 39 of 40 accepted works have no television
  > rendition at all and the one that does was composed by the current pipeline
  > and is named by artwork id. Adoption would therefore bind a work to an image
  > that is **not** the render its manifest entry names: the wall would show the
  > 2024 composition while the catalogue recorded the current one as displayed.
  > No join survives either — the legacy index addresses works by source URL and
  > by the 2024 render naming, which suffixed each source stem with its resize
  > width, and neither reaches a manifest whose entries
  > carry an artwork id and a UUID-named render path.
  >
  > So the mass upload the deliverable existed to avoid is the correct behaviour:
  > those images have never been on the television. What is owed instead is that
  > the legacy uploads are recognised as orphans and removed, so the single
  > user-upload category does not accumulate two generations of the same corpus.
- **Tests:** unit — manifest parsing, version refusal, directive
  persistence/coalescing/regression, binding state machine (TV faked at its
  interface, built after Chunk 05's verified shapes); orphan removal — an upload
  the binding table does not account for is removed, and a work the manifest
  still names is never removed; **a set that takes selections and displays none
  of them** — not reported as shown, not recorded as on the wall, the pass ended
  rather than the theme walked, the place given back, the directive left
  unconsumed, and said once rather than once an interval; hardware — a live pass
  on the Pi: the theme reaches the wall, `next`/`show_now` land within the poll
  interval, a deleted render file skips with a WARNING and rotation continues

  **What the live pass actually covered, stated precisely** (2026-08-07), because
  "the hardware pass is done" is easy to read as more than it is. It ran **from
  the development Mac against the real television**, not from the Pi: the theme
  reached the wall, rotation and restart and curation-independence were all
  observed. **Three things in the line above remain unobserved** — `next` and
  `show_now` landing within the poll interval, a deleted render skipping with a
  WARNING while rotation continues, and anything at all running on the Pi. The
  first two are cheap and are in `operator-verification.md`; the third is Chunk
  13's, which is where the Pi, the units and the panel arrive. So this chunk is
  proven against real hardware and **not** proven as a deployment.

  **The selection-confirmation half arrived from the hardware, on 2026-08-07, and
  is the reason this chunk was worth holding open.** Every unit test passed
  against a double that could not express the failure: a real television with its
  panel dark accepts `select_image`, raises nothing, emits none of the three
  art-mode events and goes on displaying what it had, while uploads, deletions,
  listings and brightness all succeed. The daemon reported `showing X` at a wall
  that never changed — the 2024 defect class this plane made impossible for
  uploads and had left open for selection. `samsung-tv-state-findings.md` records
  which call works in which state; `architecture.md` § Failure Modes carries the
  rule; the double can now be armed with the behaviour, which is what makes the
  tests above possible at all.

  **The first pass in art mode, on 2026-08-07, then found the confirmation itself
  wrong — and this is the finding to carry past this chunk.** `get_current` was
  adopted as the confirming read the day before and had been *verified against a
  dark set*, where it agrees with the failure because it never changes at all. It
  reports the art-store slot: it named one `SAM-*` id across every observation
  ever made here while the wall visibly changed underneath it. So the mechanism
  built to stop the daemon claiming rotations it had not performed instead denied
  every rotation it *had* — and because the cursor only advances on a confirmed
  show, the wall parked on one picture and re-selected it on every backoff step.
  Confirmation is now the set's own `image_selected` announcement, which carries
  the id and `is_shown` and does not fire at all in the dark state; selecting and
  confirming became one operation at the seam, because an event measured arriving
  in half a second cannot be listened for after the request that causes it.

  **Both defects were invisible to nine passing suites and to two Critic rounds,
  and each was found only by the next state of real hardware.** The first needed a
  dark set, the second needed a lit one. The generalisable part is not "test
  against hardware" but that **a double encodes what you already believe**, so the
  states you have not been in are exactly the ones it cannot model — and that a
  read verified in one state can be pure coincidence in that state.
- **Acceptance criteria:** the wall rotates the active theme from the new
  daemon; killing curation changes nothing about display's behaviour; a display
  restart neither re-executes the last directive nor loses its place
- **Done when:**
  1. Acceptance criteria met and tests pass, including the hardware pass
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

### Chunk 13A: The panel, the label, the heartbeat and the two units — no hardware

**Split from a single Chunk 13 on 2026-08-07** at the operator's call, on the
seam the original entry already admitted: its own Visual-change line records that
Pango type sizing cannot be settled without the operator in front of the panel,
and its Deliverables mix code that runs anywhere with a service account, a
directory move and a cutover that exist only on the Pi. One Critic round over
both halves would read a refactor, a new subsystem, deploy configuration and a
machine migration at once — the same reason 08 and 14 were split. 13A is
everything that can be built and tested away from the hardware; 13B is the
hardware.

- **Inherits three things from the display plane's first chunk**, written here so
  a deferral does not quietly become a drop:
  1. **Collapse the repeated report-once shape.** The daemon holds three
     `report / recover / clear` episodes (unavailable, wall-unchanged, wall-not-
     ours) and two doubling ladders with identical bounds, each arrived at one
     commit at a time and only rhyming when read whole. **The panel and the
     heartbeat want a fourth episode of the same shape**, so collapsing them is
     cheapest inside a commit that is being made anyway.
  2. **The television seam keeps ONE handler per event, not a list.** A label that
     subscribes to `image_selected` *replaces* the selection-confirmation handler
     and every rotation then reports a wall that will not move, silently, while
     the label works perfectly. Fan out from the existing handler; issue **#106**
     carries the design.
  3. **Write the `verify-api` step this plan owes.** Chunk 12 is the only
     Foreign-API chunk whose Done-when never carried one — the substance was done
     and recorded in `samsung-tv-state-findings.md`, but the step was missing, and
     this chunk is the next to touch that API. **Written as step 0b below**, and it
     lands here rather than in 13B because the fan-out is what touches that seam.
- **Carries a decision trigger.** The IT8951 pin-or-vendor decision
  (`project-state.yaml` → `technical_decisions.operational`) was unblocked on
  2026-08-04 and deliberately left un-taken, with this chunk named as when to take
  it — wiring the panel is the first point at which a rebuild resolving the driver
  to whatever upstream master became would have a consequence anyone sees. Note
  when taking it that `Cython` is also unpinned in the driver's own build-requires,
  so pinning the driver alone does not make the build reproducible over time.

- **Description:** The label renders on the display plane from manifest label
  text — the e-paper panel's geometry stays with the plane that owns that panel. Type sizing is
  re-derived for the 1448×1072 panel rather than carrying the 2024 "Sans 18"
  forward; this is the product's most important accessibility surface
  (`design_decisions.accessibility_approach`). On each `image_selected` callback,
  render and push; a panel failure never stops TV rotation. The heartbeat file
  lands (atomic write, display → curation: timestamp, manifest version loaded,
  current work, TV and panel state, last error) — display never checks whether
  anyone read it. Systemd units committed in `deploy/`: display `Restart=always`
  with the restart-loop guard the recovered unit lacked; curation
  `Restart=on-failure` + `MemoryMax` so a runaway acquisition cannot OOM-kill the
  display plane.
- **The units are written here and installed in 13B, which is safe for one
  reason worth stating.** A unit names `User=`, `WorkingDirectory=` and
  `EnvironmentFile=` — all three are facts about a machine 13B provisions. The
  split works because `ART_ROOT` is *not* among them: it reaches both planes
  through the root `.env` the units point at, so the path can stay unsettled
  while the units are written and must be settled before they are enabled. The
  three that ARE in the file are written against the intended target and are
  13B's to confirm against the machine it actually creates.
- **The type size this chunk ships is provisional, and says so in the code.** The
  probe's ladder narrowed the range to mid-20s through low-40s px, but it was
  rendered with PIL/DejaVu against a product that typesets with Pango — different
  rasterizer, different face, different metrics. 13A picks a value inside that
  range, names it provisional at its definition site with the reason, and 13B
  replaces it with what the operator's eyes settle. Shipping it unmarked is the
  failure to avoid: a number that looks measured because it is precise.
- **Depends on:** Chunk 12; Chunk 04 (panel stack installs under uv)
- **Carries a number the unit must not be written without.** `TimeoutStopSec`
  has to clear this daemon's worst-case pass, which is a television connection
  attempt: roughly 15 s of blocking construction plus the 30 s art-channel
  ceiling. A SIGTERM landing inside one is honoured when that pass ends, not
  during it — measured at ~22 s against a sleeping set on 2026-08-06, with ~45 s
  the worst case. systemd's 90 s default clears it, so this is a note against
  *shortening* it: a unit that SIGKILLs the process leaves the set holding a
  half-open art channel until it times out on its own side.
- **Artifacts consumed:** `observability-strategy.md` § The Health Surface,
  `operational-spec.md` § Process Management, `nonfunctional-requirements.md`
  § Output Quality (label legibility) and Performance (15 s label budget),
  `design_decisions.accessibility_approach`
- **Foreign API:** IT8951 / omni-epd — **runtime surface probed on the real panel
  2026-08-04; step 0 below is discharged.** Findings in
  `platform-and-dependency-findings.md` § The e-paper panel. Read them before
  writing the driver: the default mode is 1-bit, `display()` returns nothing on
  success or failure, and there is no partial refresh.
- **Visual change:** no — 13A renders into a surface, never onto the panel. The
  operator's legibility look is 13B's, and it is what makes the type size real.
- **Built to a norm ratified mid-build, 2026-08-07.** The owner raised, while this
  chunk was choosing where to render, that **a display device renders its own
  label** and that output surfaces are plural — several Pis with panels of
  different geometry, or a device with no e-ink at all whose label is drawn into
  the mat area around the artwork. `architecture.md` § Direction carries it. The
  consequence here is structural rather than additional: the chain is **metadata →
  layout → rendering**, geometry is a parameter rather than a constant, the seam
  is "a surface a label can be put on" rather than "the e-paper panel", and a
  device configured with no label surface is valid rather than broken. **No second
  surface is built** — the monitor-with-a-mat-area device is a real future device
  and not this chunk's; what this chunk owes it is an interface it can be written
  against without one being reopened.
- **Deliverables:** new `display/src/display/panel/` — the three tiers as three
  modules (label metadata, geometry-parameterised layout, rendering behind a
  surface interface) with the omni-epd e-paper surface as the first
  implementation — heartbeat writer, new `deploy/curation.service` and new
  `deploy/display.service`, the report-once shape collapsed, the `image_selected`
  fan-out, the IT8951 pin-or-vendor decision taken and recorded
- **Tests:** unit — label layout against fixed metadata (golden-image or
  measured-extent checks), heartbeat shape and atomicity, **the panel is put in
  `gray16` and the driver asserts on `mode` rather than `max_colors`** (which
  reports 16 in both modes, so the obvious check passes against a 1-bit panel);
  a panel failure leaves TV rotation running; the fan-out delivers
  `image_selected` to both the selection confirmation and the label, and a label
  that raises does not cost the confirmation its event
- **Acceptance criteria:** the daemon runs with a panel double attached and
  rotates the wall while rendering a label per selection; a panel that fails at
  init, at draw and mid-run each leave rotation running; the heartbeat file
  appears under `ART_ROOT` as `display-heartbeat.json` with `reported_at`, and
  curation's existing reader — `curation/src/curation/manifest/heartbeat.py`, built before any
  writer existed — reads it without modification
- **Done when:**
  0. ~~verify-api — probe omni-epd/IT8951's runtime display surface on the real
     panel (init, draw, partial vs full refresh, and what a failure returns)
     before writing the driver; Chunk 04 verified the build, not this~~
     **Done 2026-08-04** — findings recorded in
     `platform-and-dependency-findings.md` § The e-paper panel
  0b. verify-api — the television seam, owed since Chunk 12 and written here
     because the `image_selected` fan-out is what touches it: confirm against the
     real set that both subscribers receive the announcement and that selection
     confirmation still resolves. `samsung-tv-state-findings.md` is the record.
  1. Acceptance criteria met and all three suites pass
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

### Chunk 13B: The Pi — service account, units installed, legibility, cutover

- **Description:** The hardware half of the original Chunk 13. The `tvpi` service
  account is created with its `spi` and `gpio` groups and given ownership of
  `ART_ROOT` and the checkout; `ART_ROOT`'s path is settled off `/home/tvpi/art`
  onto a neutral one (`operational-spec.md` § The Service Account records
  `/srv/art` or `/var/lib/samsung-art` as the shape to prefer, and leaves the
  choice to this cutover). 13A's two units are installed and enabled. The
  operator looks at the real panel at standing distance and settles the Pango
  type size, replacing 13A's provisional value. Cutover: the Pi runs the two new
  units and `tvart.py` stops being the production entry point — legacy files
  remain until Chunk 20.
- **The account and the cutover are one change, not four.** `operational-spec.md`
  § The Service Account is explicit: the account, its groups, moving `ART_ROOT`
  under it and both unit files land together, because any of them arriving alone
  leaves a machine that is neither the old arrangement nor the new one.
- **Depends on:** Chunk 13A
- **Carries a number the unit must not be written without.** `TimeoutStopSec`
  has to clear this daemon's worst-case pass, which is a television connection
  attempt: roughly 15 s of blocking construction plus the 30 s art-channel
  ceiling. A SIGTERM landing inside one is honoured when that pass ends, not
  during it — measured at ~22 s against a sleeping set on 2026-08-06, with ~45 s
  the worst case. systemd's 90 s default clears it, so this is a note against
  *shortening* it: a unit that SIGKILLs the process leaves the set holding a
  half-open art channel until it times out on its own side.
- **Artifacts consumed:** `operational-spec.md` § The Service Account and
  § Process Management, `platform-and-dependency-findings.md` § The e-paper panel,
  `design_decisions.accessibility_approach`
- **Visual change:** yes — label legibility at standing distance on the real
  panel needs the operator's eyes, not a test. The probe's type ladder narrowed
  the range (mid-20s to low-40s px) but was rendered with PIL/DejaVu, so its
  numbers do not transfer to Pango and the look has to be repeated.
- **Deliverables:** the `tvpi` account with its groups and ownership, the settled
  `ART_ROOT` path recorded in the root `.env` and in `operational-spec.md`, both
  units installed and enabled on the Pi, the settled Pango type size replacing
  13A's provisional one, cutover performed and recorded in `deploy/README.md`
- **Tests:** hardware — label matches the artwork within the 15 s budget across
  several rotations; killing the panel mid-run leaves rotation running; both
  units come back from a reboot with no human action
- **Acceptance criteria:** wall + label run unattended from the two new units
  through a TV power-cycle and a display restart with no human action; heartbeat
  advances and carries honest state
- **Done when:**
  1. Acceptance criteria met on the Pi, including the operator's legibility look
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

**Discovery and acquisition (Chunks 14–18).** The paid, silent-failure-prone
core, built against the surfaces the contract tests already pin.

### Chunk 14A: `art_discovery` surface, run correlation, the search cap — no spend

- **Description:** Everything up to the engine seam, spending nothing. The eight
  `art_discovery` actions — `estimate`, `start`, `status`, `approve`, `decline`,
  `cancel`, `list_runs`, `spend` — over the `DiscoveryService` lifecycle Chunk 08B
  already built, driven by a **fake engine behind the narrow interface** 14B later
  implements for real. `start` returns a handle immediately (< 2 s); `status`
  long-polls ≤ 45 s; the work-count approval gate fires at **25**; `cancel` and the
  `interrupted` path already reconciled by Chunk 08 are exercised end to end.
  `estimate` ships with the arity-dependent behaviour `api-contract.md` now
  specifies, and is the one action on this tool that spends nothing.
  **Curation's structured log shape is owed here** and lands here: the plane emits
  plain formatted lines today, which is enough for startup, refusals and
  reconciliation and is not enough for per-run correlation
  (`observability-strategy.md` names discovery phase 1 as the owner rather than
  leaving the shape a property nobody holds — the artifact previously took it from
  `3tears-observe`, withdrawn with every other 3tears dependency on 2026-07-27).
  The fake is **not throwaway scaffolding**: it is the provider the integration
  tests run against, so it outlives this chunk.
- **Depends on:** Chunks 08, 11 (harness grows discovery scenarios)
- **Artifacts consumed:** `api-contract.md` (§ Long-running operations, § Error
  Model, § `estimate` answers two different questions),
  `nonfunctional-requirements.md` (§ Performance, § Cost Constraints),
  `observability-strategy.md` § Correlation, `data-model.md` (DiscoveryRun,
  SpendRecord)
- **Deliverables:** the eight actions live over MCP; the engine interface itself
  and a fake implementing it; curation's structured logging with `run_id` on every
  line emitted during a run, bound so that no call site can forget it; the
  **approval threshold (25)**, the **flat phase-1 search allowance** and the
  **per-work phase-2 component** as deployment values in `config.py` and
  `.env.example`; the **provisional `work_dedup_key`** derivation at one
  implementation site, marked provisional and named as Chunk 15's starting
  hypothesis; harness scenarios for the run lifecycle
- **Tests:** unit — gate threshold recorded per run (`approval_required` stored,
  not re-derived), `estimate` at both arities, cap enforcement as a distinguishable
  outcome rather than a silent truncation; integration — full lifecycle against the
  fake, including `halted_by_budget` vs `failed` vs `interrupted` as the fake can
  produce them; contract — an agent can distinguish those three by returned state
  alone; a log line emitted inside a run carries its `run_id`
- **Acceptance criteria:** every action is callable over real MCP and drives the
  real service; a run crosses the gate at 25 works and waits; `estimate` returns a
  phase-1 figure with no run id and the stored phase-2 figure with one; no code
  path in this chunk can reach the network
- **Done when:**
  1. Acceptance criteria met and tests pass
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

### Chunk 14B: Discovery phase 1 — the client, the engine, the ceiling (issue #12)

- **Description:** The real thing behind 14A's seam: an OpenRouter client written
  to the shapes `openrouter-api-findings.md` measured, and the phase-1 engine that
  turns an intent into an enumerable work list. Phase 1 can search the web when the
  intent is recency-bound (issue #12) — a text-only call cannot enumerate works
  past the model's cutoff, and finding works the curator could not have named is
  the product's definition of discovery; those searches count inside the per-run
  search cap and the pre-run estimate. **Cost visibility is a named deliverable
  here, not a norm** (`nonfunctional-requirements.md` § Cost visibility records
  that it must survive as one): the estimate before, the actual after
  (provider-reported), on every surface equally. Cost comes from **inline
  `usage.cost`** with `usage: {"include": true}` — not from a second request, and
  not computed as tokens × price, which would omit the web-search fee that can
  double a run. Spend records attribute per category; the provider's refusal lands as
  `halted_by_budget`, distinguishable in logs and tool results; budget remaining
  reads `GET /api/v1/key`, which **lags by minutes and may therefore never gate a
  run** — display only.
- **Settled at build (2026-08-02), each recorded where its rule lives:**
  - **"Recency-bound" is not decided at all — every run searches.** A trigger
    fails in the one direction the product cannot detect: a missed recency-bound
    intent returns real but pre-cutoff works with nothing marking them stale.
    Demonstrated on the default model, which without the plugin answered *"No
    major art prize has been awarded in 2026 as of 2025"*. The flat $0.005 per run
    is $0.30–0.90 a month against a $20 ceiling, and grounding a non-recency
    intent suppresses invented titles rather than wasting money. Rationale lives
    in `curation/src/curation/discovery/phase_one.py`'s module docstring.
  - **`DiscoveryRun.strategy` is written by the engine** when the work list
    settles — it is the model's own account of how the intent was read, so it
    cannot exist before the intent has been read (`data-model.md`).
  - **The phase-1 allowance stays at 10.** The measurement it waited on came back
    the useful way: the web fee is **per request, flat across one, three, five and
    ten results**, so the cap counts the right unit at the right price and its
    recorded derivation stands unchanged (`nonfunctional-requirements.md`).
    Breadth being free is why `DISCOVERY_SEARCH_RESULTS` ships at 10; the engine
    makes one request and so spends 1 of the 10.
- **Depends on:** Chunk 14A (the seam and the surface), Chunks 08, 11
- **Artifacts consumed:** `product-brief.md` § Flow 2 (as amended),
  `data-model.md` (DiscoveryRun, SpendRecord), `api-contract.md`
  (§ Long-running operations, § Error Model), `nonfunctional-requirements.md`
  (§ Cost Constraints, § Performance), issue #12
- **Foreign API:** OpenRouter (chat + web-search plugin + key endpoint)
- **Deliverables:** **the spend ceiling itself, provisioned before the first paid
  call** — a dedicated OpenRouter key with a USD 20/month per-key credit limit and
  monthly reset (`nonfunctional-requirements.md` § Cost Constraints), recorded as a
  routine-operations item in `operational-spec.md` and added to `.env.example` as
  `OPENROUTER_API_KEY` (the file still declares only the legacy `OPENAI_KEY`). The
  ratified norm forbids an application-side ceiling, which makes this key setting
  the *entire* cap: an unprovisioned key is indistinguishable from a capped one on
  every surface the product exposes, so leaving it to setup lore would mean there
  is no ceiling at all. Then: a first-party OpenRouter client behind 14A's
  interface (**not** `threetears.models.create_chat_model` — decided 2026-08-02,
  reasoning in `openrouter-api-findings.md`); new
  `curation/src/curation/discovery/` phase-1 engine; the **phase-1 model as a
  deployment value defaulting to `deepseek/deepseek-v4-flash`**, with
  `google/gemini-3.5-flash-lite` carried as the named alternative for Chunk 15's
  spike to measure at ~2.9× the token cost; `SpendRecord` rows carrying the model
  id actually used
- **Tests:** unit — the client's parsing of `usage.cost`, `cost_details` and
  search `annotations` against recorded fixtures; the recency-bound trigger,
  whichever form it takes; integration — a real run end to end against the live
  API on the capped key; contract — an agent can distinguish "out of money" from
  "fetch failed" from "restarted underneath" by the returned state alone.
  **A live re-verification test replaces the findings file's prose**, per the
  project rule that a verification worth writing down is usually worth keeping:
  prices and endpoint shapes both move, and the durable form is a test
- **Acceptance criteria:** a real intent resolves to a work list with a shown
  estimate; a recency-bound intent ("recent award-winning art") resolves to
  real, post-cutoff works; the curator can trim the list before paying for
  phase 2; **the ceiling is proven to fail closed, not assumed to.** The provider
  half of that is now *done* — a throwaway key was driven to exhaustion 2026-08-02
  and both refusal shapes are recorded in `openrouter-api-findings.md`. What
  remains for this chunk is the client half: the exhaustion **403** surfacing as
  `halted_by_budget`, and the affordability **402** *not* doing so, since it
  arrives with credit remaining and means "ask for less" rather than "stop"
- **Done when:**
  0. ~~verify-api~~ — **done 2026-08-02, recorded in `openrouter-api-findings.md`.**
     `limit_remaining`, the generation `cost` shape and the web-plugin invocation
     format are captured from the live API. Three results change the client's
     design and are not restatements of what was expected: per-call cost arrives
     **inline** via `usage: {"include": true}` (the `GET /api/v1/generation`
     route this step assumed returned 404), `usage.cost` **includes the web-search
     fee** (so a tokens x price computation would under-report by exactly the
     component that can double a run), and `/key` **lags by more than a minute**,
     which makes it sound for displaying remaining budget and unsound for any
     in-run guard. Still outstanding from this step: the recorded prices have not
     been re-verified against `/models`. **The key gaps closed 2026-08-02 in a
     second probe round** on this product's own keys: `limit_reset` reads
     `"monthly"` on the real $20 key, and the over-limit path was driven on a
     throwaway. It overturned this plan's assumption — exhaustion is a **403**,
     while the **402** is a pre-flight `max_tokens` affordability check that
     arrives with credit still available. The client must set `max_tokens`
     deliberately or it will be refused at full credit
  1. Acceptance criteria met and tests pass
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

### Chunk 15: Spikes — search-engine choice and `work_dedup_key` derivation (issue #18)

- **Description:** Two build-time spikes the artifacts explicitly hand to this
  plan, run against Chunk 14B's real output rather than synthetic data. The
  search-engine spike compares Parallel, Exa-via-OpenRouter, and Perplexity **on
  this product's hard cases** — resolving a named work to a specific museum page,
  and a recency-bound intent — not on generic relevance; cost does not
  discriminate ($0.05–0.25/run spread), so this is a quality decision needing
  quality evidence. The dedup-key spike runs candidate derivations against real
  phase-1 output, measuring false positives ("Untitled", "Composition") and
  false negatives (translated, date-suffixed titles), and lands one shared
  implementation for the three call sites (cross-run suppression, Artist rows at
  acceptance, within-run dedup) — the linchpin of "a discovery run proposes each
  work exactly once", front-loaded so it cannot be decided implicitly three
  different ways.
- **Depends on:** Chunk 14B (the spike measures real phase-1 output, and the model
  tier is one of the things it measures — `deepseek/deepseek-v4-flash` against
  `google/gemini-3.5-flash-lite`, alongside the search-engine comparison). Its
  regression measurements pin an explicit model snapshot rather than the floating
  default, so an alias moving underneath them cannot read as a quality regression
- **Artifacts consumed:** `nonfunctional-requirements.md` § Open — engine
  choice (the spike's stated constraint), issue #18, `data-model.md`
  (CandidateWork.work_dedup_key, Q3/Q11)
- **Deliverables:** engine decision recorded (`project-state.yaml` open question
  resolved, `nonfunctional-requirements.md` § Cost Constraints updated); the
  derivation recorded in `data-model.md` and implemented once in the service
  layer with the three call sites named; both decisions swept per
  `learnings.md` § "Retiring a claim is a repo-wide grep, not a local edit" —
  each dependent artifact acknowledged explicitly ("updated" / "checked,
  unaffected"), never inferred. This is the plan's largest amendment burst and
  the sweep is manual until the mechanical check ships upstream
  (brookstalley/prawduct#136); acknowledge per artifact in the commit message
- **Tests:** the spike measurements themselves, kept as regression tests over
  the hard-case corpus the spike assembles
- **Acceptance criteria:** issue #18's boxes checked (real output, hard cases
  exercised not assumed, one shared implementation); the engine default is a
  recorded decision with evidence attached
- **Done when:**
  1. Acceptance criteria met; decisions recorded in their homes
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

### Chunk 16: Discovery phase 2 — works to instances, resolve runs

**Split into 16A and 16B on 2026-08-02, at the operator's call**, at the seam
between the two things the chunk does: turning works into instances, and doing
that a *second* time on request. The reason is the one that split 08 and 14 —
one Critic round over the whole would read a diff comparable to 14A and 14B
combined (~5,000 lines), and review quality is known to degrade across one that
size. 16A alone meets the acceptance criterion this entry states, which is what
makes the seam a delivery boundary rather than an arbitrary cut.

The **verify-api step ran first, before either half** (2026-08-02), and its
findings are `artic-api-findings.md`. Two of them changed the design rather than
confirming it, which is what the step is for — see 16A.

**Phase 2 reaches museum APIs only, ARTIC first (decided 2026-08-02).** The open
web stays out of both halves. This follows from the probe: confidence has to be a
title/artist comparison rather than a relevance score, and that comparison is free
and deterministic, so phase 2 over a museum API spends nothing. A work no museum
holds lands at `unresolved`, which is already a first-class outcome whose remedy
is the re-search — rather than a paid fallback added before anything has shown one
is needed. `provider` stays an open vocabulary, so a web provider is an addition
and not a rework.

### Chunk 16A: Discovery phase 2 — works to instances, over a real museum API

- **Description:** Per-work search against museum APIs producing CandidateImages;
  ranking on the two deliberately-separate axes (confidence vs quality — **the
  `source_class`-dependent dominance is explicitly descoped, see below**); exactly
  one selected instance per work with
  `selection_rationale`; previews cached locally (`preview_path` — review must
  not depend on a museum being reachable); below-floor instances shown, labelled
  with rendered physical size, never auto-selected, never hidden; works with no
  credible instance land at `unresolved` — reported, never silently dropped,
  never filled with a confident near-match. A run that clears the approval gate
  now proceeds through `resolving_images` to `completed` under its own power,
  which is what retires the `status` notice telling a curator that finding images
  is not wired up in this deployment.
- **Depends on:** Chunks 14B, 15 (the engine and the dedup key are decided)
- **Artifacts consumed:** `artic-api-findings.md` (the measured shapes),
  `data-model.md` (CandidateImage, constraints 8/9), `product-brief.md`
  § Canonical selection, `nonfunctional-requirements.md` § Output Quality (the
  floor)
- **Foreign API:** museum APIs (ARTIC first; open vocabulary by design)
- **Deliverables:** an ARTIC client and a phase-2 engine behind a seam of their
  own in `curation/src/curation/discovery/`; selection with recorded rationale;
  preview caching; the run driven to completion; the cost estimate corrected
- **Tests:** unit — **a near-match is refused rather than attached** (the probe's
  Dalí case: a real work by a real artist scoring well against a request for a
  work the museum does not hold), selection respects suppression (`rejected_at`
  instances excluded; the work stays eligible — Q11), below-floor never
  auto-selected but always reported with its rendered size, unresolved reported;
  integration — a run over a seeded intent reaches `completed` with instances,
  previews on disk, and unresolved works named
- **Acceptance criteria:** a run over a small intent produces one card's worth
  of data per work — selected instance, alternates, rationale — with unresolved
  works reported as their own outcome
- **Descoped, explicitly:** `source_class`-dependent axis dominance. Nothing
  produces a `contemporary_web` candidate — phase 2 reaches museum APIs only, so
  every instance is `institutional` — and a switch on it would ship one reachable
  branch and one no deployment can exercise. Confidence being a *gate* rather than
  a weight already covers the `contemporary_web` concern more strongly than
  dominance would; what is genuinely unbuilt is canonicity among many
  institutional copies of one work, which cannot arise with a single provider.
  **Owned by whichever chunk adds a non-museum provider**; the reasoning and the
  reopen trigger are in `data-model.md` → CandidateImage.
- **Done when:**
  0. ~~verify-api — probe the ARTIC API for the actual response shapes~~ **done
     2026-08-02**, recorded in `artic-api-findings.md`; fakes follow the captured
     shapes
  1. Acceptance criteria met and tests pass
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

### Chunk 16B: `resolve_images` — the re-search, its coverage and its rollup

- **Description:** `resolve_images` as the paid re-search over 16A's engine: a
  `DiscoveryRun` with `kind='resolve'` and `parent_run_id`, refusing work ids
  already covered by an in-flight resolve run and naming them in the error
  (constraint 14 against ResolveRunWork), spend attributed to the resolve run and
  rolled up through the parent. The action becomes advertised on `art_discovery`
  for the first time — 14A deliberately withheld it, because a declared action a
  model cannot distinguish from a working one is a promise the surface cannot
  keep.
- **Depends on:** Chunk 16A (the engine a resolve run drives)
- **Artifacts consumed:** `data-model.md` (ResolveRunWork, constraint 14),
  `api-contract.md` § Rejecting an image does not re-search
- **Deliverables:** `resolve_images` live and advertised, with coverage
  enforcement; spend rollup through `parent_run_id`
- **Tests:** unit — constraint 14 refusal names the offending ids; **the
  terminal-verdict guard — a resolve run completing against a work the curator
  accepted (or rejected) in the meantime leaves the verdict alone and reports its
  result, and no path ever yields a work with an `artwork_id` and a non-accepted
  verdict**; integration — a double-submitted resolve is refused, an interrupted
  resolve frees its coverage
- **Acceptance criteria:** a rejected image can be re-searched, the second
  submission of the same ids is refused by name, and the parent run's cost
  includes what the re-search spent
- **Done when:**
  1. Acceptance criteria met and tests pass
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

### Chunk 17: Review and acceptance — `art_review`, thumbnails inline, promotion

- **Description:** The human gate, on the surface where it is hardest to hold:
  `list_works`/`get_work`/`list_images` return thumbnails **inline as image
  content blocks** (capped 400 px long edge — a 40-work batch stays inside the
  client's token budget), alongside the service-derived `display_fit` and
  rendered-inches figures a thumbnail cannot convey. Verdicts: `set_verdict`
  accepts `accepted`/`rejected` only, requires explicit work ids (refusing a
  bare accept-everything — the accepted set must appear in the transcript), and
  returns a teaching error naming `reject_image` for `awaiting_better_image`;
  `reject_image` is the single entry to that state and always sets
  `rejected_at`. **The verdict rules and the promotion itself already landed in
  the service layer with the discovery entities** — minting the Artwork and
  turning CandidateImages into Sources (selected → `is_primary`) — so what this
  chunk owes is the tool surface over them **plus the one piece promotion still
  leaves out: the artist.** `proposed_artist` is free text that has to be parsed
  and matched against existing Artist rows, which is the same normalisation
  problem as `work_dedup_key`; until it is done an accepted work carries no
  `artist_id`, and **Q9 — who is the artist, for the physical label — has no
  answer for anything discovery accepted.** The preview-file lifecycle decision that `boundary-patterns.md` leaves
  open is made here: `[DECISION: candidate previews are deleted by a periodic
  sweep over terminal-verdict CandidateWorks, not an on-verdict hook | a sweep
  is idempotent and safe to re-run after crashes, where a hook that dies with
  the process leaks silently — and deletion never touches the catalogue either
  way | user can veto/override]`. **Delivered in part — see 17B's entry below
  for what the shipped sweep does not reclaim, and issue #62.** Truncation in
  listings is always explicit.
**Split into 17A and 17B on 2026-08-03, at the operator's call**, at the seam
between *showing* the curator the work and *recording* what they decided. The
reason is the one that split 08, 14 and 16 — one Critic round over the whole would
read ~2,000 lines, and review quality is known to degrade across a diff that size.

The seam is a delivery boundary rather than an arbitrary cut, but **only 17B meets
this entry's acceptance criterion**, and that is the honest reading: 17A ships the
half of the gate that can be built without a verdict existing, and a curator
cannot accept anything until 17B lands. What makes 17A worth shipping alone is
that it carries all of the *image* machinery — the inline content-block seam, the
candidate-preview thumbnail, the token budget — which is the part the security
model's control actually rests on, and the part that has no prior art in this
codebase to review against.

**`art_review` therefore declares three actions after 17A and six after 17B.**
That follows the contract's existing rule rather than departing from it: unbuilt
actions are never declared, `action='help'` answers the as-built question at
runtime, and a tool part-way through its action set is exactly what 14A/14B and
16A/16B already did to `art_discovery`.

### Chunk 17A: The review surface — works, instances, and the image in the transcript

- **Description:** The half of the human gate that shows the picture.
  `list_works`/`get_work`/`list_images` return candidate thumbnails **inline as
  image content blocks** (capped 400 px long edge — a 40-work batch stays inside
  the client's token budget), alongside the service-derived `display_fit` and
  rendered-inches figures a thumbnail cannot convey, with `rights_status` beside
  them as a provenance signal that gates nothing. A `below_floor` instance is
  **shown, labelled and offered** — never hidden, never auto-selected. **The
  envelope emits text content only today**, so the seam that carries an image
  block out of a binding is this chunk's, and it is the one piece of the surface
  with no prior art here to follow. Truncation in listings is always explicit,
  and the bound on every collection this adds is named where it is imposed.
- **Depends on:** Chunk 16
- **Artifacts consumed:** `api-contract.md` (§ What the review surface must
  show, § Images are returned inline, § Token budget),
  `security-model.md` § Content Appropriateness, `data-model.md` (CandidateWork,
  CandidateImage, constraint 7)
- **Deliverables:** `art_review`'s three read actions live; image content blocks
  reachable from a binding; a candidate-preview thumbnail producer distinct from
  the catalogue's (previews are disposable and are not renditions); harness
  scenarios asserting the image block is present in the result
- **Tests:** contract — every result a curator could judge from carries the image
  block; a 40-work listing stays under the token ceiling; unit — `display_fit`
  and rendered inches are reported per instance; a `below_floor` instance is
  listed and labelled rather than withheld; an instance whose preview never
  downloaded reports the absence and still lists, because losing a work over a
  missing thumbnail is the tail wagging the dog
- **Acceptance criteria:** a real MCP client lists the candidate works of a
  completed run and the images are present in the transcript, each beside the
  size it would render at on the wall
- **Done when:**
  1. Acceptance criteria met and tests pass
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

### Chunk 17B: The verdict, the artist, and the preview's death

> **Built in two passes on 2026-08-03.** The artist and the review card's slot
> budget landed first; `art_review`'s three write actions, the preview sweep and
> the harness scenario followed and closed the chunk. It was left unchecked in
> between rather than tagged early, because a `chunks=` tag flips the Status
> checkbox and the next session would have read the remaining work as done.

- **Description:** What the curator's decision does. `set_verdict` accepts
  `accepted`/`rejected` only, requires explicit work ids (refusing a bare
  accept-everything — the accepted set must appear in the transcript), and
  returns a teaching error naming `reject_image` for `awaiting_better_image`;
  `reject_image` is the single entry to that state and always sets `rejected_at`;
  `set_canonical` chooses among the instances 17A showed. **The verdict rules and
  the promotion itself already landed in the service layer with the discovery
  entities** — minting the Artwork and turning CandidateImages into Sources
  (selected → `is_primary`) — so what this chunk owes is the tool surface over
  them **plus the one piece promotion still leaves out: the artist.**
  `proposed_artist` is free text that has to be parsed and matched against
  existing Artist rows, which is the same normalisation problem as
  `work_dedup_key`; until it is done an accepted work carries no `artist_id`, and
  **Q9 — who is the artist, for the physical label — has no answer for anything
  discovery accepted.** The preview-file lifecycle decision that
  `boundary-patterns.md` leaves open is made here: `[DECISION: candidate previews
  are deleted by a periodic sweep over terminal-verdict CandidateWorks, not an
  on-verdict hook | a sweep is idempotent and safe to re-run after crashes, where
  a hook that dies with the process leaks silently — and deletion never touches
  the catalogue either way | user can veto/override]`.
  **Shipped partial, and this box is `[x]` anyway** (recorded 2026-08-03): the
  sweep reclaims previews whose `CandidateImage` row names them, which is the
  class an on-verdict hook would have reclaimed too. The crash-leaked file — no
  row, so invisible to a sweep that walks rows — is the half the rationale above
  actually turns on, and it is **unbuilt**, filed as issue #62 at `stage: design`
  because a bare directory walk cannot tell an orphan from a file a live run
  wrote seconds ago. The chunk is complete against its own deliverables; the
  decision is not yet fully delivered, and a reader taking this DECISION at face
  value would believe otherwise.
- **Depends on:** Chunk 17A
- **Artifacts consumed:** `api-contract.md` (§ set_verdict, § Rejecting an image
  does not re-search), `data-model.md` (promotion relationships, constraints
  7/15), `boundary-patterns.md` (the preview lifecycle it leaves open)
- **Deliverables:** `art_review`'s three write actions live; the artist parse and
  match reaching a promoted work; the preview sweep; the review card's slot
  budget, so rejected scans cannot crowd out selectable ones; harness scenarios
  covering the review flow through to acceptance
- **Tests:** unit — the artist is parsed, matched to an existing row where one
  fits, and reaches the accepted work (Q9 answerable for a discovered work, which
  it is not before this chunk); promotion mirrors the candidate shape into the
  catalogue shape end to end through the tool; suppression scopes never share a
  key (Q3 vs Q11, both directions); `set_verdict` is accepted from
  `awaiting_better_image` (the curator is never blocked on a running re-search)
  while still refusing that value as a *target*; the sweep deletes only
  terminal-verdict previews and is idempotent across a re-run; a work whose
  rejected instances alone exceed the card's cap still offers every selectable
  one, and the truncation notice stays true in that state; two unattributed works
  do not merge into one artist; contract — explicit-ids enforcement
- **Acceptance criteria:** the worked example runs end to end over MCP from a
  real client: works reviewed with images in the transcript, accepted works
  appear in the catalogue with sources, artist and rationale intact
- **Done when:**
  1. Acceptance criteria met and tests pass
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

**Chunk 18 was split into 18A and 18B on 2026-08-03**, at the operator's call, at
the seam the data model already draws: **the `Original`**. Everything in 18A
produces one — bytes on disk with a row naming them; everything in 18B consumes
one and produces nothing else's input. The split's value is that the two halves
share no foreign interface (a local binary plus museum image endpoints, against
OpenRouter vision), no entity (`Source`/`Original` against `MatColor`/`Rendition`),
and no failure mode, so neither Critic round has to read the other's code — the
same reason 08, 14 and 16 were split, and this chunk was larger than any of them.

The ordering is the data flow rather than a dependency: 18B could have gone first,
because the seeded corpus already holds 41 originals on disk and the mat engine can
be judged against them with no fetch path in existence. That remains true if 18A
stalls on the binary or the network.

### Chunk 18A: Acquisition — the fetch paths, the guards, and a work's sources

- **Description:** An accepted work acquires its master image. Fetch by
  `acquisition_method` (dezoomify tiles / direct HTTP; `api` has no producer and
  is refused by name — see the acceptance criteria) with the zero-byte guard
  (constraint 5), `partial_tiles` as a normal recorded outcome, and the
  **free-space guard before acquisition starts** — disk-full is the one shared
  failure and it must be prevented, not caught. **Source URLs are untrusted
  input**: they come from web discovery, which `security-model.md` establishes as
  attacker-influenceable, so the binary is invoked with an argv list and no shell
  and URL schemes are allowlisted before anything is fetched.
  <!-- The 2024 call site was already argv-based when this chunk was written
       (image_utils.py, corrected in 4fddf36); the requirement below governs the
       new code on its own merits, not as a port of a defect. -->
  Metadata normalisation at ingest: description markup reduced to `<i>`/`<b>`
  (constraint 10) so renderers stop re-fixing it. **`art_catalogue` gains
  `sources`** — the read that `retry_acquisition` needs and that issue #60 shows
  no MCP caller has, off the same `CatalogueService.list_sources()` the browser
  detail view already uses. Then `archive`, `restore` and `retry_acquisition`.
- **Depends on:** Chunk 17 (acceptance produces the work to acquire)
- **Artifacts consumed:** `data-model.md` (Source, Original, constraints 4/5/10),
  `security-model.md` (source URLs as attacker-influenceable),
  `design_decisions.error_handling_approach`, `api-contract.md` (the action
  table), issue #60, issue #6 (defects 2/3 die here with the module replacement)
- **Foreign API:** dezoomify (external binary) and museum image endpoints
  <!-- Its CLI contract is unowned and unversioned: capture it at step 0 below
       rather than inferring it from the 2024 call site. -->
- **Carried finding — closed at build.** The tile cache directory under ART_ROOT
  has a reclaim rule rather than an operator chore: tiles are cached per source
  and removed when that work holds a complete image, so what survives is exactly a
  partial fetch's tiles, which is when they are worth their disk. The API cache
  directory needed no rule — the curation plane never creates one, and it exists
  only in the 2024 root-plane config. Both corrections landed in
  `operational-spec.md`, `boundary-patterns.md` and `learnings.md`, which had all
  been listing that second directory as an upstream artifact to transport.
  <!-- Both are runtime directories under ART_ROOT, not repo paths; named in prose
       rather than backticked so the deliverable check does not read them as files
       this chunk was meant to add. -->
- **Visual change:** no
- **Deliverables:** new `curation/src/curation/acquisition/` (fetch paths, the
  guards, metadata normalisation); `art_catalogue` actions `sources`, `archive`,
  `restore`, `retry_acquisition`; the free-space guard; the cache lifecycle rule
- **Tests:** unit — the zero-byte guard, `partial_tiles` recording, free-space
  refusal, metadata normalisation against constraint 10; security — the fetch
  path refuses a non-allowlisted URL scheme, and a source URL carrying shell
  metacharacters reaches dezoomify as one inert argv element (the test must be
  able to fail: assert on the argv actually passed, not on the absence of a
  crash); contract — an MCP caller reads a catalogued work's sources, including
  `is_primary` and `last_fetch_status`; integration — an accepted work acquires
  on the dev machine and holds an `Original`
- **Acceptance criteria:** an accepted work acquires by **the two methods any
  source in this deployment records** — `dezoomify` and `direct_http` — its
  `Original` names bytes that exist and are non-empty, a failed or partial fetch
  is recorded on the `Source` rather than raised, and an MCP caller can read where
  the work came from and ask for the fetch again.
  <!-- The criterion said "each of the three methods" until 2026-08-03. `api` is a
       declared `AcquisitionMethod` with no producer: the one museum client in the
       product resolves to tiled URLs, so no `Source` carries it and a fetch path
       for it could not be written against a real response, let alone tested. It is
       refused by name rather than silently mishandled, and the criterion is
       corrected rather than left claiming coverage of a path that does not exist.
       Building it belongs with the provider that first needs it. -->
- **Done when:**
  0. verify-api — dezoomify's CLI contract (arguments, exit codes, output layout,
     partial-tile behaviour) captured from the installed binary rather than
     inferred from the 2024 call site
  1. Acceptance criteria met and tests pass
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

### Chunk 18B: Preparation — the mat engine, the 4K render, and the corpus look

- **Description:** An acquired work becomes wall-ready. The mat engine:
  vision-model selection reasoning in LAB space via OpenRouter — the cheap vision
  model is selected here with prices re-verified at build (a slug picked months
  early is guaranteed stale; volume is one call per accepted work, so the choice
  barely moves cost), the dominant-colour fallback **recorded** on
  `MatColor.method` (never invisible), history retained. Composition: the mat in
  physical inches, bottom-weighted at `MAT_BOTTOM_WEIGHT`, against the configured
  TV panel geometry; the floor in rendered inches; **no upscaling, ever**;
  renditions carry `source_content_hash` and regenerate on staleness.
  `set_mat_color` and `regenerate` actions land. Mat quality is judged against
  the 41 hand-tuned colours — **which are already in the catalogue**, loaded from
  the tracked `all.json` by the seed as `MatColor(method='manual')`; Chunk 06
  deferred extracting them to a standalone fixture and this chunk decides whether
  that file is still worth having or the seeded rows are the corpus.
- **Depends on:** Chunk 18A (an `Original` to prepare)
- **Artifacts consumed:** `nonfunctional-requirements.md` § Output Quality (mat
  geometry, the floor, `MAT_BOTTOM_WEIGHT`), `data-model.md` (Rendition,
  MatColor, constraints 4/12), `api-contract.md` (the action table)
- **Foreign API:** the chosen vision model through OpenRouter
- **Visual change:** yes — mats over the regression corpus need the operator's
  eyes; "at least as good as 2024" is the subjective bar
- **Deliverables:** the mat engine and compositor under
  `curation/src/curation/acquisition/`; `art_catalogue` actions `set_mat_color`
  and `regenerate`; vision-model choice recorded with verified pricing
- **Tests:** unit — mat arithmetic against the recorded worked examples (42"/75"
  panels), floor classification, staleness detection, fallback recording;
  regression — mat outputs across the 41 works compared to the hand-tuned colours;
  integration — an acquired work renders to 4K and enters the manifest
- **Acceptance criteria:** an acquired work gets a mat with recorded provenance,
  renders to 4K, and enters the manifest; the operator's corpus look finds no
  regression
  <!-- The criterion read "and reaches the wall" until 2026-08-03. Nothing can
       meet that here: the display plane is Chunks 12 and 13, both bench-blocked,
       and no display package exists yet. The wall half is verified when 13 lands
       and its hardware pass runs — it is descoped from this chunk explicitly
       rather than left as four fifths of a criterion that reads met.
       (The display package is named in prose rather than backticked, because the
       deliverable check reads a backticked path in a chunk entry as a file the
       chunk was meant to add — and this comment says the opposite. Chunk 18A's
       carried-finding comment does the same thing for the cache directories.) -->
- **Done when:**
  0. verify-api — the chosen vision model through OpenRouter with a real image,
     capturing the response shape, before its client is written
  1. Acceptance criteria met and tests pass, including the corpus look
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

**UI and operations (Chunks 19–20).** Last by design: every operation the UI
binds already exists and is contract-tested.

> **Carried finding for Chunk 19:** the health panel is the product's *only*
> alerting surface, but its scoped fields omit the TV, panel, and last-error
> state that `observability-strategy.md`'s failure table maps failures onto.
> Either the panel surfaces them or that table has no reader.

### Chunk 21: Say which kind of nothing — `unresolved_reason`, and the artist fold

- **Description:** Two runs on 2026-08-04 proposed works and resolved none of
  them, and nothing in the product could say why — a green suite over a pipeline
  returning nothing, because no rule anywhere says a run must resolve anything.
  This chunk does not meaningfully raise the resolution rate (measured 4/51 →
  5/51 on the real distribution); it makes the failure **diagnosable**, which is
  what makes the chunk after it falsifiable. Three parts. **First, and before
  anything else, own the RED live test** (issue #78): a nonsense query no longer
  scores 0.0 at the Art Institute, so the zero-score pre-filter is dead code and
  the identity gate is the only thing between a garbage query and *Nighthawks* —
  which must be settled *before* the query change below, since that change widens
  what reaches a gate that just lost its outer layer. **Second, `unresolved_reason`
  on `CandidateWork`** — one value per route to `unresolved`, derived on the same
  write as the status from decisions phase 2 already makes and throws away, with
  the precedence rule `data-model.md` now states. Two of the values are read from
  the rows the work already holds and the rest from what the search discarded, so
  the derivation spans the engine and the store and neither half can produce it
  alone. **Third, the artist fold**: the artist is folded into
  the free-text query, where its tokens dominate scoring, and the measured cost is
  that three different Frank Stella titles return a byte-identical top ten and
  Ellsworth Kelly resolves 0 of 12 held works against 10 of 12 title-only. Issue
  the title-only query; keep the artist for the gate, not the retrieval.
- **The test that pins the fold is a decision, not a formality.**
  `curation/tests/unit/test_artic_client.py` asserts the current behaviour under a
  name claiming the artist "narrows the query text" — which the live API refutes. Tests
  are contracts here and the code gets fixed, never the test; this is the case that
  rule exists to make hard. The reading to be ruled on is that a test pinning a
  measured-false claim is a recorded measurement rather than a contract, so the
  claim and the test move together. **Take that to `/prawduct:critic` rather than
  deciding it inside the chunk.**
- **Depends on:** Chunk 16A/16B (the phase-2 engine and its gates)
- **Artifacts consumed:** `data-model.md` § CandidateWork (`unresolved_reason` and
  its precedence rule), `product-brief.md` § Success Criteria (the resolution
  floor), `api-contract.md` (the work row and its token budget),
  `observability-strategy.md` (the two-way split that does not name a record which
  was never retrieved), issue #78
- **Foreign API:** museum APIs (ARTIC) — the artist fold changes what the phase-2
  query *sends*, so it is a change to a foreign surface even though it adds no
  new endpoint. Its `verify-api` step is the RED live test named first in the
  description, which measured the artist facet against the live collection rather
  than assuming it; `artic-api-findings.md` carries the result.
- **Visual change:** no — the reason reaches the wire and the review surfaces
  render it, but no new page
- **Deliverables:** the `unresolved_reason` column (additive and nullable, so the
  durable store's widening step applies it on open with no written migration) and
  its derivation threaded from the phase-2 engine through the runner to the write
  site; the title-only artic query; the resolution-floor test R2 calls for, naming
  its own figure; a re-measured `list_works` page, since the row gains
  a field and the ceiling already ran 2% over; `observability-strategy.md`'s split
  widened to name a record that was never retrieved — today it names two failure
  modes behind `phase_two.not_the_work`, and the Stella case is a third it cannot
  express, a record the query never retrieved at all
- **The narrowed claim is swept by grep, not by memory.** `data-model.md` now
  confines "unresolved means phase 1 may have invented the work" to `not_held`, and
  the broad form is asserted at more sites than the two an initial read found —
  service and persistence docstrings, the phase-2 engine, and three test docstrings
  and comments that state it as the thing being tested. The sweep is
  `grep -rn --include='*.md' --include='*.py' -e 'invented the work' -e 'may have
  invented' -e 'therefore suspect' -e 'may not exist' -e 'might not exist' .`, run
  before the chunk is called done, with `change-log.md`, `reflections.md` and
  `learnings*.md` excluded as the historical record they are. Written as a command
  rather than a count because a count is wrong the moment anyone adds a seventh.

  **The last two terms were added 2026-08-04, and their absence is the finding.**
  The original three were built from the freshly-narrowed text, so they could not
  match the paraphrase the surfaces actually shipped — "the signal a proposed work
  may not exist", live on three MCP-facing strings — and the sweep came back clean
  while the broad claim still reached callers. A sweep's blind spot is the
  vocabulary of whoever just rewrote the text; the second pass has to be built from
  what the OLD text would have said
- **Tests:** unit over every reason route and the precedence rule, plus the
  round trip to the store and the wire, since a reason derived and not reported
  is not a reason a curator has.
- **The fake reshape and the identity corpus moved to Chunk 22, explicitly rather
  than by omission — and the premise for doing them here turned out to be false.**
  This entry said the museum fake's exact-title dict lookup meant "every mutation
  below survives for the wrong reason". It did not: the sweep aimed the retrieval
  mutation at the client's own tests, which drive a mock transport and assert on
  the request URL, and it was caught along with the other nine. The fake's real
  incapacity is narrower than stated — an artist differing from the query is
  already expressible, and what is not is a work the museum holds under a
  *different title*, which no test in this chunk needs. Chunk 22 is where that
  bites, since a browse returns the collection's own titles by definition, and
  building the capability a chunk ahead of its first user means shipping test
  infrastructure nothing exercises.
- **Mutation sweep, and it is the acceptance evidence rather than a formality** —
  a green suite is not evidence here, having been green throughout the two runs
  that resolved nothing. At least: swap `identity_refused` for `not_held` in the
  derivation (a survivor means nothing distinguishes "the museum does not have it"
  from "it has it under another artist", which is the whole point of the column);
  swap `all_rejected` for `below_floor` (a survivor means nothing tests the split
  between the curator having turned everything down and the collection's scans
  being too small — the pair the store derives, and the pair that was nearly
  missed); neuter the `size_unknown` guard; neuter the `below_floor` route; flip
  the precedence comparison; revert the artic query to the artist fold (a survivor
  means nothing in the suite measures retrieval at all, which is true today)
- **Acceptance criteria:** every `unresolved` work carries a reason and the wire
  reports it beside the status; the live museum suite is green with the zero-score
  measurement either removed or re-justified against what the API now does; the
  floor test exists, names its figure, and that figure is stated against the 4/51
  baseline whether or not it moved; every mutation above dies
- **Done when:**
  1. Acceptance criteria met and tests pass
  2. `/prawduct:critic` run — including the ruling on the fold test — and blocking
     findings resolved
  3. Committed and chunk marked `[x]` in Status

### Chunk 22: Grounded alternatives — the collection's own answer when the gate refuses

- **Description:** The requirement ratified 2026-08-04 (`product-brief.md` flow 2):
  a run may **additionally** offer works drawn from a wired collection when phase 2
  cannot confirm what phase 1 named. Phase 1 and the gate run exactly as today —
  the rate is unchanged, Q12 intact, `unresolved` fully reachable — and the browse
  is a supplement *after* the gate refuses, never before phase 1 and never the
  route by which a named work gets its image. That placement is what defangs the
  failure that killed the inverted design: a query that compiles to nothing is a
  supplement returning nothing, not an authoritative "the collection holds nothing
  for this intent". **Scoped to artist adjacency (operator, 2026-08-04)**, which is
  the one facet reproduced live; style, classification and period miss on ordinary
  spellings and are explicitly out until measured. The seam is shaped so a facet
  compiled by a model can be added later without changing it.
- **Carried in from Chunk 21, which found it did not need them:** reshape the
  museum fake so a holding can be keyed independently of the query title — today
  it cannot express a work the collection holds under a *different* title, which
  a browse returning the collection's own titles produces by definition — and add
  a model-vs-museum identity corpus beside `phase_one_proposals.json`, which is
  phase-1-vs-phase-1 only and so cannot measure the comparison this chunk leans on.
- **Step 0 ran 2026-08-04. The artist facet is grounded, so this chunk keeps its
  shape and needs no facet-compile step.** The claim under test was that the
  model's artist field names artists the collection actually holds; the prior
  evidence was n=2 with 1 hit, and both observed runs had named their artists in
  the intent text themselves.
  - **The recorded intents could not be re-run: their texts were never captured.**
    `phase_one_proposals.json` keeps slug labels (`dutch_golden_age`, …), not
    prompts. Reconstructing them would have measured intents written after the
    fact while reporting them as the originals, so the substitute is a stronger
    control rather than a weaker copy: **six thematic intents matching those
    labels, each naming no artist at all**, which makes every artist that comes
    back model-originated by construction.
  - **Provenance (paid, $0.0084 over six live phase-1 runs):** the model
    originated **12 distinct artists** from intents naming none, and the
    collection holds wall-appropriate, floor-clearing work for **10 of the 12**.
  - **Reach (free, deterministic, no model call):** over the **29 distinct
    artists** already in the recorded corpus, **26** have such work — **932 works
    in total**, against a pipeline that currently resolves 5 of 51 named works.
    Supply at the *artist* level is therefore abundant where supply at the
    *named-work* level is the binding constraint, which is exactly the gap this
    chunk exists to fill.
  - **The two clean misses are honest ones**: the collection holds no Vermeer
    under any spelling, and its one Antonio Martorell is `Graphic Design`, which
    the wall-type filter correctly excludes.
  - **What Step 0 changed instead**: the facet's real failure mode is **name-form
    mismatch, not absent supply** — `"Wassily Kandinsky"` returns nothing while
    the museum's 24 "Vasily Kandinsky" works sit there, and `"Titian (Tiziano
    Vecellio)"` returns nothing against 20. That is a new requirement rather than
    a build detail, so it was written before design and ratified by the operator
    the same day: `product-brief.md`, the paragraph beginning "An artist the
    collection spells its own way is a miss". The measurements behind it are in
    `artic-api-findings.md` § Browsing by artist.
  - **Rights, now quantified rather than anticipated:** of the 932 works, **637
    are public domain and 295 are in copyright** (~32%). The ratified policy is
    record-and-show-never-gate, so this is the honest cost that policy carries,
    stated in a number.
- **Depends on:** Chunk 21 (`unresolved_reason` is what makes this falsifiable —
  without it nobody can tell whether this chunk worked), Chunk 16A/16B
- **Artifacts consumed:** `product-brief.md` flow 2 (the ratified requirement and
  its four conditions on every offered work), `nonfunctional-requirements.md`
  § The Supply Horizon, `data-model.md` § CandidateWork, `architecture.md` (adding
  a provider is a pre-authorised bounded extension)
- **Foreign API:** museum APIs (ARTIC) — and this is the bundle's largest new
  query surface: a POST search with `filters`/`top_hits`/`terms` aggregations, a
  wall-type keyword filter, and an ambiguity-bounded surname retry, none of which
  any earlier chunk sends. Its `verify-api` step is the "Step 0 ran 2026-08-04"
  section below, which measured the facet live before the design was fixed and
  found the case-sensitivity asymmetry between `artwork_type_title.keyword` and
  `artist_title.keyword`; `artic-api-findings.md` § Browsing by artist carries it.
- **Visual change:** yes — a run's work list stops being a flat list of what phase
  1 said, so the review grid, the API work list and the approval count each gain a
  second kind of row to render, count and explain. That is why this is a chunk and
  not a patch.
- **Deliverables:** a `CollectionBrowse` Protocol beside the image-search seam,
  with an Art Institute implementation issuing **one POST per run** (not per work)
  — a `bool.filter` on image presence, the display floor and a
  wall-appropriate type set, with a token-AND on the artist field. **The type set
  is `Painting`, `Print`, `Drawing and Watercolor`** (operator, 2026-08-04):
  measured across all 29 corpus artists, adding `Textile` or `Photograph` changes
  nothing at all — 3,158 works either way — so the widening buys only artists the
  collection holds *exclusively* as textile, and offering a flat-photographed
  fabric sample as wall art would make "offered work" mean two different things.
  **The ambiguity-bounded surname retry** the brief requires costs two further
  POSTs on the miss path — the ambiguity check cannot ride along with either
  browse, because it must NOT carry the wall-type filter (a filter that hides one
  of two colliding artists manufactures the confidence the check exists to
  withhold). So a run where every artist is held costs one request and the worst
  case is three. All three are per *run*: none scales with the work list, which is
  the property that matters. **The display floor is applied from `thumbnail.width`/`height` on the
  browse response** — the same property the per-work search has, so no per-result
  round trip — and it is the pipeline's own `assess_display_fit`, not a width
  threshold restated in a query, because two thresholds that can disagree will. **Filters, not
  relevance**: the score is boost-dominated and a constant score does not
  neutralise it, so a text-relevance query for a Dutch still life returns
  *American Gothic*. Facets derive from the run's own works — the artists it named,
  the type set, the floor — so there is no new model call and no new prompt. A
  nullable provenance field on `CandidateWork` distinguishing offered from
  proposed; the per-run bound and its separate reporting; the approval-count
  arithmetic; the review surfaces' labelling
- **Rights: recorded, shown, never gating** (operator, 2026-08-04). No filter, no
  public-domain preference, no exclusion — constraint 13 unchanged. The review card
  shows an offered work's rights, and the honest cost is stated rather than
  discovered: this raises how often in-copyright masters are acquired, and nothing
  downstream refuses on rights.
- **Tests:** unit over the query construction and the offered/proposed split;
  integration over a run that ends with the gate refusing everything and offers
  works anyway; the review surfaces asserting an offered work is never merged with
  or presented as a work phase 1 named
- **Acceptance criteria:** a run whose every proposed work is unresolved returns
  offered works with the collection's own titles and attributions, each labelled,
  bounded and counted separately; the resolution-floor figure from Chunk 21 is
  restated against the 4/51 baseline; **no offered image is ever attached to a
  model-named work**, asserted rather than asserted-about
- **Honest expectation — now measured (2026-08-04) rather than predicted, and both
  predictions were too pessimistic.** Against the two real runs that resolved
  nothing, under the settled type set and the pipeline's own display floor:
  - the run naming **Kelly, Noland, Louis and Stella** goes from nothing to **69
    offerable works** (Kelly 51, Stella 12, Noland 5, Louis 1), against a
    predicted "at least four";
  - the run naming **the Delaunays and Banksy** goes from nothing to **4**, all
    Robert Delaunay and all ordinary wall types — not the dress-fabric swatch
    that was predicted. Sonia Delaunay contributes nothing because her thirteen
    holdings are all `Textile`, and Banksy nothing because the collection holds
    none.

  **This remains not a general fix for the supply horizon and must not be sold as
  one** — it lifts artist-named runs and does nothing for a work no collection
  holds, which is still the binding constraint.

  **One consequence is a design obligation, not a happy number.** Sixty-nine
  candidates for a single run means the per-run bound is not a safety rail but
  the *primary selection mechanism*, and `_score` cannot break the tie — it is
  boost-dominated even inside a filter context (`artic-api-findings.md`). So the
  bound needs a stated rule for *which* works it keeps. **Round-robin across the
  run's own artists**, taking one per artist per pass: without it Kelly's 51
  crowd out Noland's 5 and the offer silently becomes about one artist rather
  than about the intent. Recorded here as the decision it is, so the review can
  disagree with it rather than discover it.
- **Done when:**
  1. Step 0 run and its result recorded, then acceptance criteria met and tests pass
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

### Chunk 19 was split into 19A and 19B (2026-08-05)

At the operator's call, for the same reason 08, 14, 16, 17 and 18 were split: one
Critic round over the whole of it reads more than a round can hold well. 10B's
entire surface is ~1,970 lines, and 19 binds `DiscoveryService`, the runner and
the review service on top of it, so the undivided chunk more than doubles the
surface under a single review.

**The seam is the curator's own two motions — commissioning a run, then judging
what it brought back** — which is the seam 17A/17B already used one layer down,
at the MCP surface. Each half is independently demoable: 19A ends with a run that
has finished and a curator who can see what it cost, 19B ends with the loop
closed onto the wall.

**What is shared, and holds for both halves:** the surface is built **onto Chunk
10B's** rather than standing one up — same thin HTTP bindings over the same
service layer (typed, paginated, partial data, which is the recorded reason the
UI does not ride MCP), same design decisions, same accessibility baseline.
**What 10B already delivered — the work grid, work detail, themes, the manifest
view with its exclusion reasons, and heartbeat age — is not rebuilt in either.**

**Issue #2 spans both halves and closes at the end of 19B.** Its still-open box
names components for "the candidate review grid *and* intent entry"; its
2026-08-01 disposition settled the sequencing as **tokens lead, components are
extracted as screens land**. So 19A extracts the intent-entry and run-view
components, 19B extracts the grid's, and only 19B can close the issue.

**One dependency the undivided entry claimed is not real and is dropped:** it
listed "13 (heartbeat to display)", but heartbeat age shipped with 10B and
`/health` reads `services.display.wall_status()` today. Nothing here waits on 13.

### Chunk 19A: The run half — intent entry, the estimate, the run view and its gate

- **Description:** The curator commissions a run and watches it, in the browser.
  **Intent entry with the estimate at the point of decision** — not on a later
  screen, because the estimate exists to inform the choice being made. **The run
  view**: status, work-list trimming, the approval gate, and costs before and
  after. Both are what 10B could not build because the services did not exist.
  **The run view is where Chunks 21 and 22 become visible to a human, and that is
  a requirement rather than a nicety:** 21 exists so a run that resolves nothing
  can say *which kind of nothing*, and a browser surface that renders a bare
  `unresolved` throws away the whole chunk. So the view reports
  `unresolved_reason` per work, and labels offered works apart from proposed ones
  — the provenance 22 put on the wire — including the run-level counts that
  Chunk 22's Critic round found computed and wired to nothing.
- **Depends on:** Chunk 10B (the surface it extends), 14A/14B (the run, the
  estimate, the ceiling), 16A/16B (a run that resolves, and the re-search),
  21 (`unresolved_reason`), 22 (offered/proposed provenance and its counts)
- **Artifacts consumed:** `product-brief.md` (§ Identity, flows 1/3),
  `design_decisions.accessibility_approach`, `api-contract.md` (the HTTP surface
  carries no stability obligation)
- **Visual change:** yes — two human-facing screens
- **Deliverables:** intent-entry and run-view handlers in
  `curation/src/curation/http/` (thin bindings); the two pages; the intent-entry
  and run-view component extraction against 10B's existing tokens
- **Tests:** integration — every handler is dispatch + formatting over an
  existing service method (the service-layer norm holds by construction); the
  flows exercised through the HTTP surface; the token/contrast test 10B built
  extends to the new components rather than being bypassed
- **Acceptance criteria:** a curator enters an intent, reads the estimate before
  deciding, approves or declines, and watches the run to a terminal state without
  touching the filesystem, JSON, or SSH; a run that resolves nothing says which
  kind of nothing, per work; offered works are distinguishable from proposed ones
  on the screen and in the run-level counts
- **Done when:**
  1. Acceptance criteria met and tests pass, plus the operator's look
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

### Chunk 23: The browser client gets executed coverage — Playwright (issue #30)

- **Description:** The client is not rendering-only any more and no test runs a
  line of it. Issue #30 said this stops being tolerable at Chunk 19 and asked for
  the decision *before* it; 19A shipped first, so this chunk pays that debt
  before 19B adds the most stateful screen in the product. **The option is
  settled — Playwright against the real surface** (operator, 2026-08-05, recorded
  in `technical_decisions.technology` with its costs and the reason the three
  cheaper options lose). What is left is building it.
  **The shipped client does not change.** `app.js` stays one hand-written file
  served as-is with no build step; what lands is a dev/CI harness in its own
  directory. The Pi runs the product, not the suite — the objection issue #30
  records against a Node toolchain is about the wrong thing, and the decision
  entry says so, so it is not re-litigated here.
- **Depends on:** Chunk 19A (the screens with the most untested logic), 10B (the
  three behaviours issue #30 names by hand)
- **Artifacts consumed:** issue #30, `technical_decisions.technology`,
  `boundary-patterns.md` § Test Levels, `project-preferences.md`
- **Visual change:** no — this is coverage of a surface that already exists
- **Deliverables:** a Playwright harness driving the booted server; its
  dependency kept off the default install path; the CI/dev invocation
  written down where `CLAUDE.md`'s command table can point at it.
  **The binding is Python, settled at build (operator, 2026-08-05).** The entry
  above said "its dependency manifest, kept out of the two Python planes",
  which assumed Node — Playwright's own Python bindings mean the harness lives
  in the curation suite behind a `browser` marker, and the "second language's
  package manifest" the decision accepted as a cost is simply not paid. Kept off
  the default install is the surviving intent, and it is met by an opt-in
  `browser` dependency group of the same shape as `eval`'s.
- **Tests:** the harness *is* the deliverable. **Issue #30's acceptance names
  three from 10B that must each fail when their behaviour is removed** —
  `fetchAllWorks` termination, the image-error fallback, and the post-navigation
  focus move. Add 19A's, which are the reason this moved up the order: the run
  view leaving the DOM alone when a poll changes nothing (assert focus survives),
  two concurrent paints resolving to one, and an unresolved work reaching the
  page as a sentence rather than a raw enum token.
  Each behaviour is paired with the assertion that fails if it *over*-fires —
  a loop that stops must also have collected everything, a focus move that always
  fires steals focus from a freshly loaded page, and suppression that never lifts
  freezes the page while the run moves on. The reason test is parametrised over
  `UnresolvedReason` rather than a list written in the test, so a sixth reason
  arrives as a failure instead of as a raw token on a curator's card.
- **Acceptance criteria:** every behaviour above is covered by a test that
  demonstrably fails when the behaviour is removed — demonstrated by the mutation
  sweep, not asserted; `boundary-patterns.md` § Test Levels and this plan's test
  strategy state what the harness covers and what it does not; issue #30 closes
  with its option recorded
- **Done when:**
  1. Acceptance criteria met and tests pass
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

### Chunk 19B: The review half — the grid, its alternates, the verdict, the panel

- **Description:** The curator judges what the run brought back, and the loop
  closes. **The review grid** — image-forward, one card per work, **alternates
  behind it**; 10B's grid shows accepted works only, with no alternates to stack,
  so the stacking is new here. The verdict and image selection ride the review
  service Chunk 17 built. It also **completes the health panel** 10B started,
  adding backup age and **no budget balance at all** — the gate the undivided
  entry used to name is resolved. That entry originally listed `limit_remaining`
  as a deliverable outright; the operator settled on 2026-08-04 that the panel
  does not surface it in any form, because the figure fails by reading *non-zero
  while calls are already refused*, which stating its age would not warn anyone
  about. Per-run spend and the `halted_by_budget` outcome are the budget signals,
  and both already exist. Do not add the field back without reopening that
  decision. **Backup age is built here against a source nothing populates yet**
  (operator, 2026-08-05): the panel's contract is that it states observations
  with ages and never verdicts, so "no backup recorded" is a true and useful
  observation before the backup exists, and the field reports real ages the moment
  the backup job lands with nothing further to wire. This is what breaks the
  circular dependency the two entries used to carry between them.
- **Depends on:** Chunk 19A (the run view a reviewed work is reached from),
  17A/17B (the review surface and the verdict), 18A/18B (images on disk to show)
- **Artifacts consumed:** `product-brief.md` (§ Identity, flows 1/5),
  `design_decisions.accessibility_approach`, `observability-strategy.md` § The
  Health Surface, `api-contract.md` (the HTTP surface carries no stability
  obligation), issue #2
- **Visual change:** yes — the surface a curator spends their time in
- **Deliverables:** review-grid and health handlers in
  `curation/src/curation/http/` (thin bindings); the grid with its alternates;
  the completed health panel; the grid's component extraction, which closes the
  last open box on issue #2.
  **Plus a binding for the re-search, added at build (operator, 2026-08-05).**
  Turning a scan down is one of the grid's own actions and it leaves the work
  `awaiting_better_image`, where nothing looks again — `resolve_images` is what
  looks, and it had no HTTP binding. Shipping the rejection without it would make
  this chunk's own screen a dead end escapable only from an MCP client. It is one
  thin handler over `runner.resolve_images`, which 16B built.
  **The carried finding above this chunk's neighbours is closed here too:** the
  panel had no reader for the document the display plane reports, so the failure
  table's TV, panel and last-error rows mapped onto nothing. It renders what the
  heartbeat carries rather than a schema invented here, because
  `observability-strategy.md` makes `reported_at` the only key that is contract
  and leaves the rest to the writer.
- **Tests:** integration — every handler is dispatch + formatting over an
  existing service method; the flows exercised through the HTTP surface; the
  non-colour state indicator holds for the grid's accept/reject, asserted rather
  than asserted-of. **Browser tests for the grid's client logic**, which is what
  Chunk 23 built its harness for and moved up the order to precede this — with
  the mutation sweep as the bar for covered, not the existence of a test
- **Acceptance criteria:** the full curator loop — intent → estimate → review
  with images → accept → theme → wall — runs in the browser without touching the
  filesystem, JSON, or SSH; the health panel states observations with ages, never
  verdicts, and says so plainly when it has no observation to state; issue #2's
  component box is closed
- **Done when:**
  1. Acceptance criteria met and tests pass, plus the operator's look
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed and chunk marked `[x]` in Status

### Chunk 20: Backup/restore exercise (issue #14), ops close-out, legacy retirement

- **Description:** The catalogue is the irreplaceable asset — the image tree is
  deliberately not backed up. Scheduled backup of `catalogue.sqlite` to another
  LAN machine using the SQLite backup API or `VACUUM INTO` (never a live file
  copy), several generations retained because the destination may be asleep;
  backup age surfaced on the health panel. **The restore is exercised, not
  described:** restore onto a scratch directory, watch the manifest build
  exclude everything with reasons, watch re-acquisition refill the tree — the
  designed, visible self-heal. Ops close-out: deploy/rollback procedures
  confirmed as documented, the legacy 2024 modules deleted now that nothing
  runs them, and the final cumulative review makes the branch release-ready.
- **Depends on:** Chunks 13 (health panel target exists), 18 (re-acquisition
  refills a restored catalogue), 19B (the panel's backup-age field already exists
  and reads empty — this chunk fills it, so the dependency runs one way only;
  the two entries used to name each other)
- **Artifacts consumed:** `operational-spec.md` (§ Backup and Restore, § Routine
  Operations), issue #14, `nonfunctional-requirements.md` § Durability
- **Carried findings (hygiene, close-out):** `deploy/README.md` and the committed
  unit still describe the single-process 2024 loader with no pointer to the
  two-unit deployment; three artifact `depends_on` headers disagree with the
  derivation their own prose shows. Both corrected here. **Amended 2026-08-04 —
  that pair is staler than this row says:** the Pi was rebuilt onto a fresh card
  and every `/home/tvpi/` path in both files now points at a directory that does
  not exist, on behalf of a user that does not exist. Chunk 13B creates the
  account and installs the units 13A writes, so what reaches this chunk is whatever
  `deploy/` still carries afterwards.
  **Added 2026-08-08 — `CLAUDE.md` is trimmed here, and this is the chunk that can
  do it cheaply.** It is at ~171 lines of project-specific content against the
  ~150 guidance, and the rules that actually stop a bad session — all three suites
  pass, `uv run` in every column, `-n0` on the marker suites, prove coverage with
  the mutation sweep — are competing with reference material for a reader's
  attention. Deleting the 2024 modules takes the root column out of the dev-command
  table and the root suite out of three of the surrounding paragraphs, which is
  most of the excess without anyone judging what matters. The rest is the
  `display/tests/raster` paragraph and the live-suites catalogue, both of which
  already exist in full in `platform-and-dependency-findings.md` and
  `deploy/README.md` and need only their command and a pointer here.
- **Deliverables:** backup job + schedule in `deploy/`; the health panel's
  backup-age field going from "no backup recorded" to a real age — the field
  itself ships with 19B, so what lands here is the source behind it; the restore
  exercise performed and its outcome recorded; legacy modules removed; README
  brought current
- **Tests:** the restore exercise is the test, plus a unit test that the backup
  path refuses the file-copy shape
- **Acceptance criteria:** issue #14's four boxes checked; a restored catalogue
  self-heals visibly per the recorded design; `git ls-files` carries no dead
  2024 module
- **Type:** cumulative-final
  <!-- Last chunk: commit, then its review IS the one `/prawduct:critic
       cumulative` over the whole bundle — no separate final. -->
- **Done when:**
  1. Acceptance criteria met, restore exercised
  2. Committed, then `/prawduct:critic cumulative` run and blocking findings
     resolved
  3. Chunk marked `[x]` in Status

## Early Feedback Milestone

**Milestone chunk:** 07
**What the user can do:** point Claude Code at the server, list the five tools,
and read the seeded catalogue through `art_catalogue` — the product's own worked
interaction, three layers deep, before anything widens. (Chunks 01–05 already
put the operator's hands on the hardware, but 07 is the first product
interaction.) The wall runs on the new planes at Chunk 13B.

## Governance Checkpoints

**Commit & PR cadence:** commit per chunk after its Critic review passes
(per-chunk commit is what scopes `chunk`-mode reviews). PR boundaries are the
operator's call (`PR creation: wait_for_user`); if a phase ships as its own PR,
override that phase's last chunk to `cumulative` at that point. Chunk 20's
cumulative review is the release-readiness gate.

- **After Chunk 07** — architecture validation: the registry/service/persistence
  shape, the ASGI+MCP mount, and the thin-binding norm, reviewed before ten
  chunks build on them. (The chunk's own `final`-mode review is this checkpoint.)
- **After Chunk 13B** — mid-build trajectory review: the wall runs on the new
  planes; verify the norms held under real hardware (plane isolation green,
  manifest the only channel, no false success anywhere in the journal), and that
  the cutover left nothing load-bearing in the legacy modules.
- **Before Chunk 10B** — the UI checkpoint, moved here from before Chunk 19 on
  2026-07-31 when the first browser surface was re-sequenced forward: dispose
  issue #2 (design system now, or accept one-off CSS with a recorded revisit) and
  issue #10 (second-look shelf in scope or explicitly deferred); confirm the UI
  scope still matches what the built product needs. It runs once, before the first
  surface exists — Chunk 19 inherits its dispositions rather than re-opening them,
  except for a #2 revisit that was explicitly deferred to it.

  **Held 2026-08-01. Three dispositions, all recorded on the issues themselves.**

  *Issue #2 — tokens now, component inventory deferred to Chunk 19.* The issue's
  own sequencing question was system-first versus extract-from-the-first-screen,
  and neither answer is available whole: its acceptance list asks for components
  covering the candidate review grid and intent entry, and both of those screens
  belong to chunks whose services do not exist — which is why the issue's own
  stage is `design` rather than `ready`, with `information_architecture` and
  `interaction_patterns` still empty. So the half that can be decided against a
  real screen is decided now and the half that cannot is not guessed at. **In
  scope here:** the token layer (colour, type scale, spacing, radius, elevation),
  light and dark handling, AA contrast verified against the token set, and the
  non-colour state indicator — every decision that ad-hoc CSS would otherwise
  make silently and that a later screen would then inherit. **Not in scope:** a
  component inventory for screens that are not specified. #2 stays open at
  `design`; its revisit is the deferral this checkpoint was allowed to make.

  *Issue #10 — deferred to Chunk 19, and the deferral is forced rather than
  chosen.* The shelf shows works accepted **over MCP** awaiting a human look.
  `art_review` is declared in the tool registry and unbuilt (`_UNBUILT`), so no
  work can be accepted over MCP at all; a shelf built now would be a surface with
  no producer, which is the defect shape this repo has already recorded twice
  (`display_fit.upscaled`, `Rendition(kind='label')`). It becomes buildable when
  acceptance does, in Chunk 17.

  *UI scope still matches what the product needs* — with one correction the
  checkpoint exists to catch. Chunk 10B's grid is specified to carry `display_fit`
  and rendered-inches labels, and **`assess_display_fit` has no production caller
  today**: nothing anywhere constructs an `ArtworkBox`, because the mat width and
  the resolution floor were specified in `nonfunctional-requirements.md` as
  deployment values and never added to the deployment surface. That is settled in
  the chunk entry rather than here.
- **After Chunk 20** — the cumulative review, per the chunk's `cumulative-final`
  type.

## Explicitly deferred — named so nothing is silently dropped

- **Issue #8 (decision-amendment acknowledgement check)** — **moved out of this
  product, not dropped.** It was Chunk 01 of this plan. The check reads only
  prawduct's own data model (`technical_decisions` markers, the
  `artifact_manifest` graph), so building it here would make this repo the
  maintainer of framework tooling and leave every other prawduct repo to
  re-solve it. Filed upstream as `brookstalley/prawduct#136` with the full
  thirteen-recurrence evidence and the five cause classes. **The obligation it
  was to mechanize still binds in the meantime** — every amendment in this build
  sweeps its dependent artifacts by hand per `learnings.md` § "Retiring a claim
  is a repo-wide grep, not a local edit", with per-artifact acknowledgement in
  the commit message. Chunk 15 carries the largest such burst and says so.
- **Issue #10 (second-look shelf)** and **issue #2 (design system)** — decided
  at the pre-UI checkpoint (now before Chunk 10B), not silently included or
  dropped now.
  `security-model.md` records #10 as "filed as backlog work, not committed
  design".
- **Ambient adaptation beyond the ported brightness loop** (auto art-mode
  scheduling, weather-aware brightness) — the brief's Later list.
- **MCP resources** — decided no for v1 (additive later; recorded 2026-07-20).
- **3tears relaxation to 3.13** — off this product's path entirely
  (`operational-spec.md`); an upstream concern.
- **Multi-account, multi-TV, HA, concurrent runs** — accommodate-only per the
  brief; designed around, not built.
