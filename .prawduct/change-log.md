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
