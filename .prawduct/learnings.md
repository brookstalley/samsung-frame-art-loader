# Learnings

Accumulated wisdom from building this product. Each `## ` heading states a rule.

**Evidence lives in `learnings-detail.md`, under the identical heading** — the
worked instances, the recurrence tallies, and what actually happened. A heading
here with no body under it is not an entry that lost its evidence; it is one whose
evidence is in that file. Entries written before 2026-07-31 still carry theirs
inline, which the record linter flags; moving them is tracked as issue #26.

## A measured behaviour and an explanation of it are separate claims

**Record what the system did and what you inferred about why as two things, and
label which is which** — a measurement earns confidence, and the mechanism written
beside it inherits that confidence without earning any.

## A test double that fails EARLIER than the real thing makes every test past it vacuous

**When** a fake stands in for a client with connection state, **make it fail where
the real one fails**, not at the first opportunity — and check what it *lets
through*, not just what it returns. **Because** a double that raises at the top of
a call sequence prevents every later line from executing, and the tests asserting
those lines pass with no assertion looking wrong.

Worked instance, 2026-08-06: `FakeTv.connect()` re-checked reachability on every
call, while the real `SamsungTv.connect()` returns immediately once it holds a
client — so in production a set that goes away is discovered by the next *real*
call, and in the fake it was discovered at the top of the tick. Two tests
asserting "a directive is not consumed while the television is asleep" passed
because the directive code never ran. Making the fake faithful turned both red,
and one was a genuine behaviour with no coverage at all.

**The tell is a test that passes on the first try for a rule you have not
implemented yet.** The general check: for each test, name the line that would
have to execute for the assertion to mean anything, and confirm the fixture
reaches it. A mutation sweep answers this mechanically and found this one.

**Its sibling: the module with no tests is the one the doubles replaced.**
`display/src/display/tv/samsung.py` exists entirely to correct a library that
misreports in both directions, and nothing reached it — the suite runs against
the double by design. A green suite, a passing review, and a symbol-reference
coverage floor all agreed it was covered.

## Do not trust a foreign client's return value in either direction — confirm against the system itself

**When a boundary library reports success or failure, verify the claim against the
remote system's own state before acting on it** — ask, then read the remote list
back, and keep *unconfirmable* apart from *failed*.

## A test double expresses what you already believe the dependency does, so it cannot catch "says yes, does nothing"

**When a dependency's state-changing verb has no confirming read, make the double
able to model acceptance-without-effect before trusting a green suite** — because
a double is written from your model of the dependency, so the failure mode you did
not know about is exactly the one it cannot express, and every test passes while
the real system ignores you.

## A test that advances an injected clock must not step by a multiple of the interval under test

**When a test drives a fake clock, choose amounts that are not multiples of the
period the code computes against** — because a step equal to the interval makes a
daemon that *wrongly consumed* that interval indistinguishable from one that
correctly withheld it, and the test then passes on arithmetic rather than on
behaviour.

## A guard aimed at a named line must be verified against that line

**When you clamp, filter or redact one named line in a dependency, open the
dependency and read that line before choosing the threshold** — because a guard
built on a remembered level protects nothing and looks exactly like protection.

## Retiring a claim is a repo-wide grep, not a local edit

**When you void, amend, or supersede a factual claim, grep the whole repo for it
before calling the correction done.** Prose has no compiler, so a claim that lives in
four artifacts stays true in three of them until someone looks.

**Confirmed by recurrence, and the list below has only ever grown.** Nearly every
entry was caught by a Critic round or a later verification pass rather than by the
self-review that immediately preceded it — which is the rule's real content: this
failure is invisible from inside the edit that causes it. *(The preamble here once
read "twice in two sessions" while thirteen numbered entries sat under it. Stating
the count made this entry an instance of the rule that a durable artifact should
carry an invariant rather than a tally — the count moves, the shape does not; it
now states the shape, which cannot go stale.)*

1. **2026-07-19, first pass.** The architecture rationale was amended from "the split
   was *forced* by a Python version conflict" to "the split is a *choice*" across
   `product-brief.md`, `project-state.yaml`, and `3tears-integration-findings.md`.
   `learnings.md` kept a section literally headed *"The Python version split is not
   negotiable"* for a full session.
2. **2026-07-19, second pass.** `api-contract.md` § Security spent a paragraph
   explaining that *"agents cannot auto-accept (every addition stops at curator
   review)"* was void and must not be left standing. `project-state.yaml` →
   `risk_profile` was still asserting it, verbatim, in the same commit.

**Root cause:** thinking in artifacts. You correct the file you are editing and the
correction *feels* complete, because the edit you made is the edit you intended. The
claim's other homes are invisible precisely because you are not editing them.

3. **2026-07-20 — and this one escalates the rule, because the rule's own remedy was
   followed and still failed.** The co-location decision retired "the split moves
   gigapixel work off a Pi 4". I *did* grep the old phrasing and fixed six sites.
   The Critic then found four more, plus the 2026-07-19 "forced" claim still alive in
   two places it had already been amended out of once.

**Why grep was not enough — the correction to this learning.** A retired claim does
not propagate as *text*, it propagates as *paraphrase*. "Forced by a version
conflict" had become "Forced by the Python 3.14 vs 3.13 constraint, not chosen" in
`risk_profile` and "two planes on two machines, forced by an irreconcilable Python
version constraint" in the classification block. Neither matches a grep for the
original sentence. Grep finds literal survivors and is blind to exactly the
restatements that a careful writer produces.

**The unit of sweep is the DECISION, not the sentence.** When a decision changes,
the sweep target is every artifact that depends on that decision — which
`project-state.yaml` → `artifact_manifest.artifacts[].depends_on` now actually
encodes (populated 2026-07-20). Walk the dependency graph and re-read each dependent
artifact for the *concept*; use grep only as the cheap first pass, never as the
check that closes the sweep.

**Structural escalation, per the learning lifecycle. The count is the argument, so
keep it current: EIGHTEEN recurrences across six sessions as of 2026-08-02**
(entries 1–16 below; entries 6 and 14 each cover two). All but one were caught by
the Critic — the eleventh by a requested design-checkpoint review (entry 10) — and
none by the author's own sweep-closing check, across at least five distinct causes —
literal-text survival, paraphrase, excluding one's own edited files, consuming
only part of a finding's enumerated scope, and a home outside the artifact graph
entirely. Each correction was
locally right and none prevented the next,
which is the real signal: **the remedy class is wrong, not the remedy.** Prose
instructions to a careful reader keep failing because the failure is not
carelessness.

What would actually catch it: a check that, when a `technical_decisions` entry gains
an `AMENDED`/`SUPERSEDED`/`RETIRED` marker, lists the artifacts declaring a
`depends_on` edge to it and requires each to be acknowledged. Originally filed as
issue #8 here; **moved to `brookstalley/prawduct#136` on 2026-07-20** — the check
reads only prawduct's own data model, so it belongs in the framework rather than in
one product. Issue #8 is closed `dropped` (no work landed here). **It must validate
graph completeness first** — see the unedged-findings gap below, which would
otherwise be inherited as a blind spot. **Until it ships, the sweep is manual and
this learning is the whole control.**

**Sharpest tell that this is systemic, not carelessness:** on 2026-07-20 the sweep
failure landed in the same bundle that *added this learning*, three commits later —
and one of the claims I had to retire was one I had written myself an hour earlier.

4. **2026-07-20, fourth recurrence — and this one was NOT a paraphrase problem.**
   The re-search decision superseded "re-search spend attributes to the originating
   run". The literal phrase survived in `data-model.md` § SpendRecord, ~180 lines
   below the note stating the new rule, in the same file — and I had rewritten its
   twin sentence by hand in `api-contract.md` minutes earlier.

**The correction: editing a file is not sweeping it.** The sweep grep I ran was

    grep -rn "<concepts>" .prawduct/artifacts/*.md | grep -v "data-model.md\|api-contract.md"

I excluded the two files I was *editing*, reasoning that editing them handled them.
That reasoning is wrong and it inverts the risk: the artifacts you edit are the ones
most likely to contain the superseded claim, because they are the ones the decision
is about. A 750-line artifact does not become consistent because you changed one
section of it.

**So the closing check has three passes, not two:** (1) grep the literal phrasing —
cheap, catches survivors; (2) walk `depends_on` and re-read dependents for the
*concept* — catches paraphrase; (3) **re-read the files you edited, in full, as if
someone else wrote them** — catches the survivor sitting below your own edit. Pass 3
is the one that was missing, and it is the cheapest of the three.

5. **2026-07-20, fifth recurrence — in the commit that authored the remedy.**
   `project-preferences.md` still described a single product-wide Python target 140
   lines below its own corrected per-plane section, in a file that same commit
   edited. Pass 3 would have caught it on first application. Writing a remedy and
   applying it are different acts, and the commit that adds the remedy is exactly
   where the gap shows.

6. **2026-07-20, sixth and seventh recurrences — the correction itself was the
   miss.** A Critic finding named three artifacts carrying the same rule
   (`data-model.md`, `architecture.md`, `operational-spec.md`). I edited one. My
   pass-3 grep used the literal strings from the file I had just written;
   `architecture.md` phrased the rule differently ("reconciles every non-terminal
   run to `failed`") and did not match. `operational-spec.md` was worse than stale —
   it had inverted, telling the operator that a healthy waiting run was a bug.

7. **2026-07-20, eighth recurrence — inside one table row.** The fix for recurrence
   6 rewrote the third column of `architecture.md`'s curation-down row and left the
   second column reading "any in-flight discovery run dies with it" — asserting
   precisely what the same row's next cell denied, since this repo's vocabulary puts
   `awaiting_approval` inside "in flight". The finding had enumerated *two* defects
   in that row; only the grep-able one got fixed.

8. **2026-07-20, ninth recurrence — a home the graph cannot reach.** Having just
   refreshed the recurrence tally in `learnings.md` *because the count is the
   escalation argument*, I did not refresh it in **issue #8**, which was then the
   artifact the argument exists to support and the live home
   (`backlog_service_repo` is set; the work has since moved to
   `brookstalley/prawduct#136`).
   The issue still read "three times across two sessions" and still scoped its
   acceptance to "the three recorded violations".

**The structural point, recorded here rather than only in a reflection: the backlog
sits outside the artifact dependency graph entirely.** No sweep of `.prawduct/` can
reach a GitHub issue, and no `depends_on` edge can ever point at one. A structural
check of this shape (now `brookstalley/prawduct#136`) that walks artifacts will have
this blind spot on day one —
which is a different defect from an unedged manifest node, because this home can
never be a manifest entry at all. **When a decision or count is cited in the backlog,
the backlog is part of its sweep set.**

9. **2026-07-20, tenth recurrence — a finding's enumeration consumed partially,
   again.** Critic finding R-19 listed five sites carrying the retired "single
   consumer, deployed together" versioning exemption. Two were fixed; three
   survived to the next cumulative review — `api-contract.md` twice (one flatly
   contradicting the amended table fifty lines above it) and the `status: active`
   `api_versioning_approach` decision record in `project-state.yaml`, the
   canonical versioning home, still asserting the un-made decision. Exactly the
   sub-shape of recurrences 6 and 8: **the finding's enumerated list IS the sweep
   set**, and partial consumption is now the dominant recorded way these survive.

10. **2026-07-20, eleventh recurrence — the first caught by something other than
    the Critic.** The rights-display-only decision, swept the same day into five
    artifacts, missed `security-model.md`, whose `## Open` section still
    presented the settled question as open and pointed at an open-questions entry
    that no longer exists — found by a requested design-checkpoint review. The
    Critic then found its twin: `data-model.md`'s `rights` field row still said
    "see open question in `project-state.yaml`", ~700 lines above that same
    file's corrected constraint 13. `depends_on` edges existed and the dependency
    walk still did not happen — further evidence for the mechanical check, not
    for more care.

11. **2026-07-20, twelfth recurrence — the amendment that recorded a weaker claim
    was itself unswept.** The review-gate criterion amendment ("having been
    *shown* its image") landed in `product-brief.md` and `security-model.md` but
    missed `project-state.yaml`'s goals list — the canonical criteria home — and
    `api-contract.md`, which quoted the old wording verbatim from a file that no
    longer contained it. Found by verify-resolutions in the very commit pair that
    remediated recurrences 10 and 11.

12. **2026-07-20, thirteenth recurrence — a finding's fourth enumerated home,
    unconsumed.** R-8 listed four homes for the stale `label/` references; the
    remediation swept three and annotated none in `learnings.md` § Data and cache
    contract — the section the other three annotations *cite as the live
    contract*. Entry 9's observation held within the same session: partial
    consumption of an enumerated scope is the dominant way these survive, and it
    survived the remediation performed with that entry open in the editor.

13. **2026-08-01, fourteenth recurrence — the finding's file list read as the
    scope.** A Critic finding named two artifacts still reporting the TV pairing
    token as an unremediated leak, closed in July. Both were fixed and the
    disposition recorded. The verify pass then found a third home
    (`project-state.yaml`'s `classification` block — what briefings and security
    reviews read as *current state*) and a fourth (`build-plan.md` Chunk 01, still
    carrying a `git pull`-deletes-the-token hazard `security-model.md` had already
    withdrawn). **A finding's `files:` list is a sample, not an inventory** — it
    names where the reviewer looked, and the reviewer was reading a diff. The
    remedy is unchanged and takes seconds: grep the concept's distinctive noun
    (`token_file`) across the repo, not the two paths handed to you.
14. **2026-08-01, fifteenth and sixteenth recurrences — the rule failed twice in
    one session, the second time immediately after being told about the first.**
    The Norm Health sweep retired "2,216 lines / 13 modules" in one norm-index row
    and left the same figures standing three lines above in the *same file*
    (including a live flat-vs-package design judgement resting on a number 19%
    under the truth), plus a `project-state.yaml` risk factor —
    "No test suite exists" — that `operational-spec.md` had retired eight days
    earlier. The Critic named this entry by title when it raised it. Then, after
    those fixes, the identical stale carve-out ("eleven files", "three hand-run
    operator tools") surfaced a *third* time in the Code Style section of the file
    already twice edited — found only because a backup-restore made the harness
    echo the file back. **Being told "this is a repo-wide grep" is not the same as
    running one**, and the section you already edited is exactly where the next
    home hides, because having edited the file reads as having covered it.

15. **2026-08-02, seventeenth recurrence — and the one that changes the remedy.**
    The `3tears-models` supersession (confined to an opt-in test group when
    discovery went to a first-party OpenRouter client) was recorded in the three
    artifacts that argued for it and swept nowhere else. Critic named five stale
    sites plus a `pyproject.toml` contradicting itself fifty lines apart; the
    repo-wide grep found **nine** — the extras being a *test docstring* teaching the
    retired claim to everyone who reads the suite, this learnings file, and a
    `project-state.yaml` decision record. Fourth recurrence for a Python-version
    claim specifically, which is the tell: the same claim keeps going stale because
    it was written down nine times.

16. **2026-08-02, eighteenth recurrence — in the commit that added entry 15.** The
    same pass fixed the two `limit_remaining` sites a finding named and missed four
    more, including one 175 lines below the correction *in the same file* and a
    build-plan deliverable in a file that commit was already editing for an
    unrelated sweep. Caught by the verify-resolutions round. Entry 15 above, written
    in that commit, is the escalation arguing that attention has stopped working;
    it did not survive its own commit.

17. **2026-08-02, nineteenth and twentieth recurrences — with the rule read at
    session start and not applied.** Chunk 16A corrected the phase-1 token basis
    across `config.py`, six artifacts and the tests, and stopped at `.env.example`,
    which pinned the superseded values *and* carried the superseded reasoning.
    Found by booting the product, which printed the old estimate — not by any
    review. Then, in the fix for a Critic finding about a test marker, the split
    reached the test file, `pyproject.toml` and the docstring, and missed
    `boundary-patterns.md`, which still quoted the old `addopts` verbatim. The
    Critic's phrasing is the sharpest statement of this rule yet: **"the fix
    corrected every site the finding named and none it did not."**

    Two things make this pair worth recording rather than being two more tallies.
    First, **the deployment surface was the miss both times that mattered** —
    `.env.example` is what a curator's `.env` is copied from, so the correction
    reached everything except the file that decides what anyone actually sees.
    Second, **the remedy for that one is entry 15's, applied**: the pins are now
    commented out rather than corrected, because a value pinned in `.env.example`
    is a value copied into every `.env` where no later correction can reach it.
    A default in one place beats a correct value in two.

18. **2026-08-03, twenty-first recurrence — and I had already written the correct
    value down.** Adding `resolve_images` took the MCP bindings from 23 to 24. I
    counted them, wrote "one of twenty-four MCP bindings" into the handoff notes,
    and left `project-preferences.md` § Known departures saying twenty-three —
    the artifact that *governs* the norm, whose count exists to make the
    departure legible. The Critic found it. **Knowing the number is not the same
    as having swept for it**: I produced the corrected figure for a file nobody
    enforces and never asked which file held the old one. The row now states the
    shape ("the only binding in the file that does; every other one makes exactly
    one service call") rather than a count, which is the remedy the paragraph
    below prescribes and the one this entry's own preamble was already an
    instance of.

19. **2026-08-03, twenty-second recurrence — the sweep that retired a claim left
    the claim standing at its most load-bearing site.** A preview-sweep docstring
    claimed a race was closed when it was not, and the claim had been copied into
    five places. I
    fixed four, listed them in the change-log as "the module docstring, the
    inline comment, `architecture.md`, and this entry", and called the sweep
    done. The fifth was `DiscoveryService.transaction()`'s docstring — carrying
    the sentence near word-for-word, and the single site most needing the
    correction, since it defines what that exposure buys and is the API anyone
    would change to close the residual. **The list was assembled by recalling
    where I had written the claim, not by grepping for it**, which is entry 18's
    failure exactly ("knowing the number is not the same as having swept for
    it"). One `grep -rn "concurrent writer"` would have returned all five; it
    now returns none. Two things make this the sharpest datapoint here: it is
    entry 16's shape — the failure recurring in the very commit correcting it —
    and the vehicle was an *enumeration certifying completeness*, which is this
    section's dominant sub-shape. A count is a claim about a search, and it goes
    stale the instant the search was incomplete. The change-log now records the
    lesson and points here rather than restating it.

20. **2026-08-03, twenty-third recurrence — three sweeps, three sites short, on
    the same claim.** "A preview is re-fetchable" was false and lived in four
    artifacts. The first correction fixed `operational-spec.md` § Add disk
    headroom. The Critic named `boundary-patterns.md` in the same round and the
    fix did not reach it. The PR reviewer then found `boundary-patterns.md` still
    standing — **in the branch that added entry 19 above, about exactly this** —
    and running the `grep -rn "re-fetchable"` it prescribed turned up two *more*
    sites the reviewer had not named: `operational-spec.md`'s backup section and
    `data-model.md`'s disposability block. Every one of those corrections was made
    by a reader who believed they had just finished the sweep.
    **The tell is doing the grep at the end.** Entry 19's lesson was "grep, don't
    recollect", and it was still applied as a *check on a list I had already
    written* rather than as the thing that produces the list. A grep run after the
    edits confirms the edits; a grep run before them is the only one that finds
    the sites you were never going to think of. Where a Critic or reviewer names
    one site, treat it as a sample and not as the set — they read a diff, not the
    repo.

**The correction that follows: stop sweeping a duplicated claim, stop duplicating
it.** Every remedy above escalates *how well you look* — grep, then walk the
decision graph, then do not exclude the files you edited, then treat the finding's
enumeration as a checklist. All of them are attention, and attention has now lost
seventeen times. The claim "what holds the 3.14 floor" was restated in nine places
because restating it felt like being thorough; each restatement was a new thing to
keep true. It now lives in exactly one place — `project-preferences.md` § Language
& Runtime — and the other eight sites point at it. **A claim stated once cannot
drift; a claim stated nine times drifts in nine places, and the sweep only ever
finds the homes you thought of.** So the question when you retire something is not
only "where else does this appear" but "why does it appear anywhere twice" — and
where a second home is genuinely needed, it carries a pointer, not a copy.

This does not retire the sweep — existing duplication still has to be found the
hard way, and the mechanical check filed as `brookstalley/prawduct#136` is still
the thing that would catch it. It changes what you leave behind afterwards.

*(This entry is itself the evidence for why the count keeps moving: the failure is
**fractal**. Every act of propagating a claim is a fresh opportunity to miss a home,
so each correction creates the conditions for the next recurrence. That is a stronger
argument for a mechanical check than the raw tally is — a careful reader cannot
out-attention a failure mode that regenerates at every level of the fix.)*

**Refinement: a finding's enumerated defects are a checklist, and it is not done
until every item is struck.** Recurrences 6 and 8 are the same error at different
scales — a finding naming three files, then a finding naming two clauses. Both times
the reviewer had already done the analysis and I consumed part of it. **The sweep
set is never smaller than what the finding explicitly lists.**

**The correction: when a Critic finding lists files, that list IS the sweep set.**
No dependency walk is needed and no grep pattern has to be guessed — the reviewer
already did the work and handed over the answer. Using one file from a three-file
finding is not a sweep failure of technique, it is not reading the finding.

**And the generalisation behind passes 1–3: never let the grep pattern come from the
text you just wrote.** Your own phrasing is the one phrasing guaranteed to be
consistent; the survivors are, by definition, the sites that say it differently. Grep
for the *concept's* distinctive nouns (`awaiting_approval`, `reconcil`, `non-terminal`)
rather than for a sentence.

**A second structural gap, found by the Critic on `rev-20260720T145500Z-2fcf2f8f`
(the review that produced recurrence 4):** the two entries
under `artifact_manifest.findings` had *no `depends_on` edges at all*, so pass 2
could not reach them even when run correctly — which is why the retired product-wide
Python target survived in `platform-and-dependency-findings.md` across four
corrections elsewhere. Edges added 2026-07-20. **A dependency-graph sweep is only as
good as the graph**, and an unedged node is invisible rather than merely
low-priority. Worth checking the graph is complete before trusting a walk of it —
including for the check now tracked as `brookstalley/prawduct#136`, which would have
inherited the same blind spot. (The build plan itself was an unedged node until
2026-07-20, found by the same Critic goal — the pattern recurs at every scale.)

**Related:** the same session produced a near-miss of the adjacent shape — an
*unverified inference riding along with a verified claim* ("streamable HTTP is
forced" was verified; "mounted in the same ASGI application" was not, and was written
as though it were). Verification instincts fire on the part that looks like a
foreign-system claim, not on what is attached to it. Principle 24 (Retrieval Over
Generation) and the Complete Delivery principle both bear on this.

## "Verified" must enumerate what was actually measured

**When writing a verification claim, name the fields, cases, or files the check
actually covered — never restate the thing's full shape as though the check had
covered all of it.** A "verified <date>" stamp is a credibility marker with no
built-in obligation to list its own scope, which is exactly how a claim broader
than its evidence acquires one.

**Worked instance (2026-07-20, found by Critic R-2).** A build chunk asserted that
all 41 legacy records carry seven named fields, "verified 2026-07-20". Three
fields had been measured. Measured properly: 14 of 41 had no nationality, 8 no
lifespan, **8 no `artist_details` at all** — the field the chunk's own unit test
was written around — and 2 each lacked medium and dimensions. The acceptance
criterion built on it ("an empty exclusion report") was unsatisfiable by that data.

**Root cause:** the sentence was written from the *data model's* field list rather
than from the *check's* field list, and a clean result on the narrow check carried
a feeling of confirmation across the gap. Nothing in the sentence's form forced the
two lists to be compared.

**The rule:** a verification claim states its own scope inline — "measured against
X on <date>: A, B, C present in all N; D missing in M" — so the claim and its
evidence cannot drift apart later. If enumerating the scope feels tedious, that is
the tell that the scope is wider than the check. This is the authoring-side twin of
the sweep failure above: a claim propagating past the evidence that licensed it.

### The corollary: a check that ran once is not evidence the repo holds

**Added 2026-07-27, third occurrence of this family in eight days.** A durable
claim needs durable evidence. Verifying something in a throwaway script, a
scratch worktree, or a one-off command tells *you*; it leaves the repo with a
sentence and nothing underneath it. The next reader cannot re-run your shell
history, and the claim is now load-bearing for decisions made without it.

**Worked instance.** Chunk 07B's change-log asserted that a catalogue written by
the pre-refactor code "was read back field-for-field by the new code, ordering
included". That was true — measured by standing up a worktree at HEAD, writing a
file with the old code and reading it with the new. It was still the wrong
artifact: unreproducible, naming neither the fields compared nor how the file was
produced. The Critic flagged the sentence, and the fix was not to soften it but to
convert the probe into a test that freezes the previous revision's DDL and inserts
as literals, so the on-disk contract is checked on every run.

**The rule:** when a verification is worth writing down, ask whether it is worth
*keeping* — if a future change could silently invalidate the claim, the check
belongs in the suite, not in the transcript. Prose records that a thing was true
once; a test records that it is still true. Two commits in a row corrected claims
of this shape (`e379529`, then this one), which is the signal that the authoring
habit, not the individual sentence, is what needs changing.

### The second corollary: a test one layer below the wiring passes when the wiring is gone

**Added 2026-07-27, found twice in one chunk.** A unit test proves a function
behaves. It does not prove anything *calls* it — and from that test's own output
the two cases are indistinguishable. So a component can be thoroughly tested and
entirely unwired, with a green suite either way, which is the exact silent-failure
shape this product exists to avoid.

**Two worked instances, in the same afternoon.** Chunk 08A's change-log claimed
"each constraint has a test that fails without its enforcement". Checking it —
removing each of nine enforcements in turn and re-running — showed eight going red
and one not: the description normaliser had thorough tests of its own, and nothing
asserted `add_artwork` ever called it, so deleting the call left the suite entirely
green. Then the Critic's fix for a different finding repeated it exactly:
`reconcile()` got five tests and its call site in `main()` got none, so deleting
that line also left everything green. The second one was caught by asking the same
question of the fix that had just been asked of the code.

**A third instance, one layer higher again, closed the pattern.** The binding
echoed `offset` back in its payload so a page could be resumed from its own
result — and the only assertion on it used `offset=0`, which is also the binding's
own default. That assertion holds if the argument is dropped on the floor. The
general form is sharper than "test the caller": **an assertion pinned at a value
that is also the default proves nothing about the path that produced it.** Pick a
value the code has to have carried.

**The rule:** for any behaviour that only matters because something invokes it —
a normaliser, a validator, a startup repair, a hook, an echoed argument — write
one test that enters through the caller, not through the callee, and pass it a
value no default could have produced. The cheap way to know whether you have:
**delete the call (or hard-code the value) and run the suite.** If it stays green,
the wiring is undefended. This is a different failure from the corollary above:
not a claim wider than its check, but a check aimed at the wrong layer.

## After a scripted mass edit, verify with a different detection method

**A check that shares its detection logic with the edit shares its blind spots.**
Verify a scripted bulk change with a method that keys on something the edit did
*not* key on — otherwise a clean check means only "the pattern I already thought of
matched", not "the change is correct".

**Worked instance (2026-07-20).** A chunk renumber rewrote 137 reference runs with
one regex anchored on `Chunks?\s+` adjacency. It silently missed
`Chunks 06 (verified library), 07 (display project), 10 …` — a parenthetical broke
the number run, so only the first number was remapped. Any verification regex I
would have written naturally would have anchored on the same adjacency and reported
clean. It was caught by sweeping for **bare two-digit numbers with no `Chunk`
prefix** — the one shape the original pass structurally could not see.

**The rule:** after a bulk edit, ask "what shape could my pattern not have
matched?" and search for *that*. Roster/invariant checks (is the set complete? do
all references resolve to something that exists?) are good second methods because
they test the outcome rather than the transformation.

## When an artifact works a rule on two cases, derive the rule from one and check the other

## An idempotence test that holds the inputs still tests the wrong half

## A backlog item's body is evidence about the day it was written — re-verify each item against the current tree before acting on it, because closed work goes on looking open, and a thorough body makes re-verification cheap rather than unnecessary

## A guard that lives only in code scheduled for deletion leaves with it — when fixing a defect in a retiring module, fix the surviving replacement too even where it is currently unreachable, because the reachability argument is about today and the deletion is about the code that stays

## Adding code to a repo means asking which guards were scoped to the old shape

## Prose explaining a distinction is not a mechanism recording it

## A negative claim needs the search that would have falsified it

## Prose that ships to a caller is behaviour, and needs a test aimed at it

**Assert the thing the sentence claims, not that the sentence is present.** A
notice describing an *ordering*, a *completeness* or a *remedy* is making a
checkable claim, and membership-and-count assertions pass under every wrong
wording of it. A truncation notice said "selectable ones first" while the rows
kept their ranking — describing how slots were allocated as though it described
what the caller receives — and its correction then claimed every choosable scan
was on the card, which is false once they alone outrun the cap. Both shipped past
tests asserting counts and membership. Position is what catches an ordering claim;
a second test for the other branch is what catches a completeness one.

## When a behaviour is retired, grep the sentences that justified it, not just the code

**A retired rule outlives its retirement in prose, and the code may cite that
prose as authority for the opposite of what it now does.** Replacing a best-first
cut left the rule stated in the constant's own rationale five lines above the new
function, and in the artifact — which a docstring then pointed at as "states the
requirement". Search on the *claim's words*, not on the identifier.

## A package's declared dependency floor is a claim; what it imports is the constraint

## Before answering the question a spec asks about a candidate, check that the candidate is one

## An index that under-claims its enforcement is defective, not conservatively safe

## A mutation test must prove it mutated, or its green is indistinguishable from a pass

**Extended 2026-08-03 with the two ways a sweep lies in the other direction**, both
found by running one: a mutation that changes no behaviour, and a `find` pattern
that matches twice. Each reports a survivor that is nobody's coverage gap and reads
exactly like a finding. `curation/tools/mutation_sweep.py` now refuses an ambiguous
pattern; the no-op case it cannot detect, so confirm your mutation breaks something
before writing a test for it.

## Treat a finding's recommendation as a checklist, and tick each item off in the file

**Fix the parts you were not already thinking about.** A finding named two
contradictory sentences in one state; I removed the one I had been editing, left
the other — it lived past an unconditional `return` I never looked at — and then
wrote a comment on my fix saying every such sentence was gone. **A partial fix
carrying a comment that claims completeness reads exactly like a complete one**, on
review and on re-reading, so nothing downstream catches it. Go back to the
finding's text after the edit and confirm each named item against the file.

## When you rewrite a test's assertions, re-read its name against what it now checks

**A dropped contract and an adjusted wording look identical in a diff; the test's
name is what tells them apart.** Rewriting assertions to match changed output is
routine, and in a batch of six such edits one of them was not a wording change at
all — it was `assert "all 0 scans" not in notice`, a guard against a specific bad
output, deleted in the commit that made that output reachable again. The test was
named `..._is_not_reassured_about_it` and afterwards enforced nothing about
reassurance. The name is the statement of intent that survives an edit to the
body, so a name that no longer describes the assertions is the signal a contract
was dropped rather than adjusted. Record any assertion you remove where a reader
will find it — one that nothing records is indistinguishable from one never written.

## Assert what must be absent, not only what must be present

**A conditional clause needs the case where it must not appear.** Two sweep
survivors in one function were both this: nothing checked that a card still
holding choosable scans does *not* announce none are open, and nothing checked
that a clause naming refused scans is absent when there are none — where the
unconditional version would have shipped "the 0 you have already turned down".
Present-only assertions pass under every over-firing bug, which is the whole class
a notice built from branches is prone to.

## A fixture that reaches the branch is not a fixture that can falsify its claim

**Build the member that would make the claim false, not just enough members to
execute the line.** Twice in one chunk a test reached the code and excluded the
only state where the code could be wrong: a crowd-out test with one survivor,
where the lone survivor is the *selected* instance and leads the order anyway; and
a branch about omitted scans built with nothing omitted of the kind whose ranking
was in question. Both passed, both proved nothing. Ask what single row, added to
this fixture, would make the assertion fail — if the answer is "none", the fixture
is the test's weakest part.

**The sharper form, when a branch is conditional:** work out what must be true for
control to arrive there at all. The branch claiming omitted scans ranked lowest
was reachable *only* when the slot set filled from survivors alone — which is
exactly when every rejected scan was omitted, and rejected scans outrank the rest.
Its precondition and its falsifier were the same fact.

## Run a new regression test against the unfixed code, not just the fixed code

**A test written from a defect's *description* can pass on both sides of the fix,
because the fixture never reaches the state described.** Written for a card that
dropped selectable scans when rejections filled it, with one survivor — and one
survivor is the *selected* instance, which leads the store's order and therefore
rode the top of even the broken slice. It passed against the unfixed code and
defended nothing. Two survivors reach it, because the instance that falls off is
the unselected alternate. The check is one mutation that restores the old
behaviour: if the new test still passes, the fixture is wrong, not the fix.

## A survivor says a branch is undefended, never that it deserves defending

**Before writing the test a survivor asks for, check whether the branch does
anything** — the reflex is to defend it, and twice on one surface the right answer
was to delete it. A guard can be inert (a particle filter whose work a neighbouring
rule already did) or actively harmful (a three-character token floor that excluded
initials as advertised *and* discarded every short surname, so `Wu Li` reduced to
nothing). Deleting both made the rule simpler and unbiased at once.

## A guard's comment names what it excludes, not what it silently breaks

**Treat an explanation as a claim about one category, never as coverage of the
rest.** The comment is written by whoever chose the guard, so it can only name the
cases they thought of — and it reads convincingly precisely because the category it
names is real. Prose cannot flag an omission its author did not make. Where the
claim is checkable in one line, check it rather than read it.

## A verify pass verifies findings, not intervals

**A fix that lands in the *base* of the reviewed interval is invisible to every
pass over that interval** — the finding stays undispositioned and the next pass,
starting later still, misses it for the same reason. Two consecutive passes did
exactly this. When a pass says nothing about a finding you expected it to settle,
check where the fix sits before concluding anything about the fix; naming the
finding explicitly in the pass's arguments is what closes it.

## A commit message is evidence about intent, never about content

**Count the hunks.** A message says what its author believed they did, which is the
thing under review — one claiming "three prose totals replaced" carried a diff with
two, and repeating the claim put a false resolution into the ledger for work that
was never done.

## A cap sized from one part of a result is not a cap

**When you bound a result with an arithmetic, name every term that scales with the
same N** — the one you leave out is the one that will dominate. Sizing a thumbnail
cap from image tokens alone left the rows, which scale with the same batch, to add
nearly as much again and push a full page past the client's warning threshold.

## A rule stated at one level does not enforce itself one level up

**When an artifact states a rule about a detail view, check what the *listing*
does with it.** "Shown, labelled, never hidden" governed the image list; the work
list carried one picture per row keyed on the selected instance, and a work with no
selection arrived with no picture — not withheld by any rule, just absent, and
indistinguishable to a curator from a work no picture exists for.

## A field whose only defence would be a test written to defend it is a field to delete

**When a sweep says nothing covers a field, ask whether the field earns a test
before writing one.** Two survivors here were a `run_id` duplicating a value the
same payload already carried under another name, and a read performed solely to
produce it.

## Governance you put where it cannot see is governance that did not run

**Match the structural form the tooling matches on** — a heading level, a tag, a
filename. Authoring a chunk as `####` where every other split chunk uses `###` made
the record linter return `chunk_graded: null`, and null is not zero: nothing about
the chunk's declared deliverables was checked, and the report said so quietly.

## A guard built from recurrences is scoped to where you looked, not to the failure

## A rule that could not be violated yet is a rule nobody has implemented

**When a chunk makes a previously impossible operation possible, treat every
artifact claim about that operation as unverified — the age of the sentence is
not evidence.** A guard whose violating case cannot arise has never been
exercised, so "written down since July" and "enforced" are indistinguishable
until the operation exists. Find them by writing the test the artifact's own
sentence describes, and expecting it to fail.

## An action is only usable if its arguments are obtainable from something built

**Before advertising an action, construct a real call to it using only surfaces
that ship — and if a test needs a service-layer call to build a tool argument,
that is the finding, not a convenience.** Withholding an action until it works is
half the bar; the other half is that a caller can reach its inputs. A test that
reaches past the surface for an id makes the whole suite blind to the gap.

## When a result gains a collection, name what bounds it before deciding it needs no cap

**Write the bound down as a comment, and the false ones announce themselves.** A
list added to a payload is unbounded until something specific bounds it, and the
near-miss is naming a mechanism that gates rather than caps — an approval
threshold computed *after* a list is recorded pauses the work without shortening
the list. Where a caller cannot page, truncation still beats a blown budget, and
the notice must not promise an affordance that does not exist.

## A test that indexes an unordered read is wrong even while it passes

**Key on identity, not position, whenever a store read promises no order — and
treat `caplog` the same way, since `at_level` scopes the level and not the
buffer.** Both failures look identical: green alone, red in the suite. Fixing one
as a fixture concern does not generalise; the rule belongs to the *data*, so the
next test written against the same read reintroduces it.

## Ratifying a norm creates retroactive obligations on ARTIFACTS, not just code

**When a norm is ratified, the artifacts written before it are as much in scope as
the code — and in a planning-stage product they are the *only* thing in scope.**
Re-derive every specification the norm now governs, before calling ratification done.

**What happened, 2026-07-20.** Three norms were ratified. For each, the Retroactivity
line read some version of *"no existing code has two planes — nothing to migrate"*,
which was true and useless. All four blocking Critic findings that followed were
norm-versus-predating-*artifact* conflicts:

- `data-model.md` still told the display plane to resolve `Theme → ThemeMembership →
  Artwork → TvBinding` — catalogue entities — hours after a norm was ratified saying
  the display plane "queries no curation database".
- `Rendition(kind='label')` still carried one panel's geometry in the catalogue,
  which that artifact's *own* Direction norm forbids and whose cited anti-pattern is
  the 2024 `_w648_h480` filename. Moving geometry from a filename into columns had
  fixed the *encoding* and left the *ownership* violation intact — which is how it
  survived a norm written to catch it.
- `api_contract.md` exposed `art_display(show_now|next)`, unimplementable the moment
  the manifest became the only channel.

**Root cause:** "retroactivity" was read as a code-migration question, because that
is what the word connotes and what the examples describe. In a product with zero
production code the field reads as trivially satisfied — so the one question it
exists to force never gets asked.

**What to do:** at ratification, list the artifacts the norm governs and re-read each
one *against* the norm. Specifications violate norms exactly the way code does, and a
spec violation is worse: it is the instruction a builder will faithfully follow.

**Related principle:** Complete Delivery — a decision whose consequences are not
propagated is not delivered. Also `docs/norms.md` § Birth, whose three retroactivity
outcomes (migrate / contain / grandfather) all read as code-shaped and may deserve an
artifact-shaped fourth reading.

## Platform and dependencies

See [platform-and-dependency-findings.md](artifacts/platform-and-dependency-findings.md)
for the full record established 2026-07-19. Summary:

- Python version is **per plane, not one number** (corrected 2026-07-20 — the
  product-wide "target 3.13" predates the two-plane split and kept resurfacing).
  **Display plane: 3.13** (matches Raspberry Pi OS Trixie), floor 3.12. _(Updated
  2026-08-04: this said "falling back to 3.12; verified working on 3.12, and 3.13 is
  an open assumption until a build proves it". A build proved it — the IT8951 stack
  builds and imports on 3.13/aarch64 — so the fallback contingency is discharged and
  3.12 is a floor rather than a landing site.)_
  **Curation plane: 3.14** on a uv-managed standalone build. _(Re-based
  2026-07-27 and again 2026-08-02: this said "with `3tears` unmodified", then that
  "the floor rests on `3tears-models`". Neither holds — that package moved to the
  opt-in `eval` group when discovery went to a first-party OpenRouter client, so
  no default dependency requires 3.14. What holds the floor is stated once, in
  `artifacts/project-preferences.md` § Language & Runtime; this entry points there
  rather than restating it, because restating it is what produced four
  simultaneously-stale copies.)_
- Hardware is a **Pi 4 Model B**, so `RPi.GPIO` works and none of the Pi 5 /
  RP1 / `rpi-lgpio` complications apply.
- Both display drivers are **dormant** (omni-epd 2024-11, IT8951 2023-11), and
  the IT8951 dependency is **unpinned** — pin or vendor it.
- The hardware surface is only ~119 lines (`display.py`, `spi_test.py`), so it
  belongs behind an interface. That is what keeps a frozen 2023 driver from
  dictating the project's Python version.

**This constraint turned out to be architecture-defining.** See below.

## The two-plane split is a choice, not a forced constraint

> **Corrected 2026-07-19.** This section previously read *"The Python version split
> is not negotiable"* and described the split as **forced** by an irreconcilable
> version conflict. An audit the same day proved otherwise, and the correction was
> carried into `product-brief.md`, `project-state.yaml`, and
> `3tears-integration-findings.md` — but not here, which left the project's
> learnings file asserting the opposite of its own architecture decision. Caught by
> Critic review on 2026-07-19.
>
> **The durable lesson is the one that generalises:** "forced by X" is a claim about
> X, and it needs the same verification as any other foreign-system claim. Recording
> a constraint as non-negotiable without auditing it is how a removable limit becomes
> permanent architecture.

Established 2026-07-19 during discovery; full record in
[3tears-integration-findings.md](artifacts/3tears-integration-findings.md).

Every 3tears package declares `requires-python = ">=3.14"`, and the e-paper driver
stack is pinned to **3.13/3.12** for the reasons above. Taken at face value these
cannot share an interpreter. **But the audit found 3.14 is required only by 16
mechanical source sites, with no third-party dependency imposing any floor above
3.10** — so the constraint is removable, and "forced" is not an honest rationale.

The split stands on its own merits:

- **Curation plane** — Python 3.14. Web UI, LLM discovery, image acquisition and
  preparation. **Runs on the Pi** (amended 2026-07-20 — previously "runs off the Pi").
- **Display plane** — Python 3.13 on the Pi 4. TV websocket, e-paper, and label
  rendering.

**Both planes run on the same Pi 4 (8 GB), sharing `ART_ROOT` and communicating
through exactly one file — the theme manifest.** The clause "it moves gigapixel
fetching and 4K compositing off a Pi 4" is **retired and must not be cited**;
nothing moved off it. That claim was also weaker than it read — the existing code
downsizes to 2048² before the LAB/k-means work, so peak memory is a few hundred MB.

It survives because the display plane **does not want 3tears at all** — it needs
`samsungtvws`, the e-paper driver, and nothing else that plane offers; three-tier
entities are of no use to it. *(Corrected 2026-08-06, when that plane was built:
this read "it needs an HTTP client, `samsungtvws`, PIL, and the e-paper driver".
It needs neither of the other two, and the HTTP client is now **forbidden** —
`tests/preferences/test_plane_isolation.py` fails the build on one, because the
only thing this plane could reach with a general client is the curation process,
which is the second channel the manifest-only norm exists to prevent. PIL went
the same way for a duller reason: the television is handed a path and streams the
file itself, so nothing here decodes an image. A dependency list written from a
design sketch is a guess until the code lands.)* Beyond that: it matches the upstream/derived data contract below,
it makes "e-paper behind an interface" a process boundary rather than a convention,
and it is what lets the display plane keep working when curation is down.

Co-location did not weaken the split, it made it cheaper: the *cost* was the
distributed-systems tax (network contract, sync, two deployments) and a shared
filesystem removes it, while the *benefit* — the wall staying lit through a curation
restart — matters more on one box, not less.

Relaxing 3tears to 3.13 remains worth doing on *its* merits, but it is no longer a
dependency of this product's architecture.

## 3tears can run with zero infrastructure

Also 2026-07-19, verified by reading the source — not assumed:

- **L2 (NATS) is optional by design.** `CollectionRegistry` initialises all tiers
  to `None`; `BaseCollection` guards every L2 use and has one-shot warning
  machinery for the missing-client case. Spam suppression for a path implies the
  path is expected.
- **L3 is pluggable.** The `DurableStore` protocol is explicitly documented as
  "the seam that makes a non-SQL durable backend possible", and scriob's
  `GitL3Backend` is a working precedent.
- **`3tears-models` needs no core at all** — only `media-contracts` and `observe`.
  **Still true as a fact; retired as an adoption argument on 2026-08-02, because
  "no core" is not "no weight".** Measured and declined on its install size; it
  is an optional dependency group now. `learnings-detail.md`,
  `openrouter-api-findings.md` § The install lands on the Pi.
- **`3tears-agent-memory` is the exception**: it depends on `pgvector`, so it
  genuinely requires Postgres. Deferring it is what keeps the curation plane
  infrastructure-free.

> The whole decision reduces to one question: do you want 3tears agent memory?
> No → zero infrastructure. Yes → Postgres. Nothing in between buys anything,
> because NATS only earns its keep across multiple pods.

**Corrected 2026-07-27 — "zero infrastructure" is true and was read as "zero
work".** L1 is a *named in-memory* SQLite database (`cache/sqlite.py` hardcodes a
`memdb` URI), and 3tears ships no SQLite `DurableStore` — only asyncpg. So the
tier that actually persists anything is always one you write yourself. The bullets
above are accurate about *infrastructure*; none of them was ever about *durability*,
and the gap between those two words survived three artifacts for a week.

**The general form, which is the reusable part:** "no infrastructure required" and
"no code required" are different claims, and a framework's optional-tier
documentation answers the first while sounding like it answers the second. When a
dependency is adopted for a capability, name the capability and find the code that
provides it — the absence of a shipped implementation is invisible in exactly the
material that advertises the seam.

## Data and cache contract

Established 2026-07-19. The `art/` tree is not one thing, and the two halves are
transported differently:

- **Upstream, expensive, device-independent** — `raw/`. Costs network fetches and
  real API spend to regenerate. See `learnings-detail.md`.
- **Derived, cheap, device-specific** — `ready/`, `thumbs/`, `tv-thumbs/`, `label/`.
  Rendered for a particular target geometry (4K for the TV, 1448x1072 for the
  e-paper). *(Annotated 2026-07-20: `label/` described the 2024 single-plane
  layout and is retired from the prospective ART_ROOT contract — labels render on
  the display plane, and any cache is display-side. The class rule stands;
  `boundary-patterns.md` carries the prospective contract.)*

  > **Narrowed 2026-08-02: "device-specific" is not one property, and reading it
  > as one caused a real mistake.** `boundary-patterns.md` § `ART_ROOT` filesystem
  > contract makes the distinction — each derived directory is device-specific in
  > a *different* way. `ready/` is composed for the television's panel; `label/`
  > for the e-paper's; and **`thumbs/`, the browser surface's cache added
  > 2026-08-01, is specific to nothing** — it is derived and cheap and belongs to
  > no device at all. Reading the class as uniform is what made `tv-thumbs/` look
  > like the right home for it, which is keyed by the television's own content
  > ids: per-device state, the class this catalogue exists to keep out. Recorded
  > here as well as there because a reader of this file alone would still conclude
  > every derived directory is device-specific.

The rule that falls out:

> Git carries the code and the `all.json` index. Rsync carries the upstream
> blobs. Derived artifacts are never transported at all — they regenerate
> per-device.

Derived artifacts must **not** be copied between machines even though it is
technically possible: they are rendered for whichever display was targeted, so
shipping them produces either wrong output or a cache that cannot be trusted.
Regenerating them on the target is cheap and correct.

`all.json` is already the right shape for this — a 68 KB index tracked in git
while the blobs stay out of it. The design is sound; it needs making explicit,
starting with hoisting the art root into configuration as a single `ART_ROOT`
(it was hardcoded to `/home/tvpi/art`, correctly outside the repo, but only
implicitly).

## At the moment of a fix, ask what the change now COVERS that it did not before — a wrapper added to translate a read will also catch the write beside it, and a claim added to one payload will be published by the branch that shares it

## A claim repeated in three artifacts is ONE piece of evidence copied twice — when a property is asserted in prose, verify it against the code before adding the third statement of it, because every later text inherits it from the earlier prose rather than from the behaviour

## When a module's docstring says it exists to stop two callers drifting, adding a caller is the moment to READ that docstring — the drift it warns about reappears in the new caller, and the escaping case will be the common path rather than the one being written

## When a fixture seeds a file at a path the code DERIVES, learn that path from an observed run instead of spelling it out — a rename leaves the fixture pointing at nothing, and the test stays green while the branch it guards goes undefended

## Known problems in the existing index

`all.json` conflates three separate concerns in one record, which the planned
pivot to canonical artwork identities plus a URL-resolution layer needs to
separate:

1. **Identity is the source URL.** If a museum site reorganises, identity
   breaks, and the same artwork cannot be sourced from two places.
2. **Per-device runtime state lives in the catalogue** — `tv_content_id` and
   `tv_content_thumb_md5` are facts about one specific television, and
   `label_file` embeds `_w648_h480`, geometry from a display that is no longer
   the target.
3. **Metadata is semi-structured** — `artist_details` is a newline-joined blob
   ("Charles Demuth\nAmerican, 1883-1935") needing parsing into artist,
   nationality, and lifespan.

Also unreconciled: **41 artworks in `all.json` but 46 files in `raw/`**, and
filenames encode identity in at least three mutually inconsistent conventions
(`Surname, Forename; Title; Year`, `Forename Surname - Title`, and at least one
`Title - Forename Surname` with the fields reversed).

## A comment that justifies code by naming a constraint is a CLAIM — check the constraint before inheriting the workaround, because a false reason usually sits on top of wrong behaviour

## A decision that DESCOPES something has to be walked back through every artifact that promised it — the promising artifacts are never the one you are editing when you make the call

## When a chunk is parked behind access it does not have, check which of its DEPENDENCIES actually need that access — a dependency inherits the parking by adjacency rather than by need, and one that gates the parked work is the cheapest thing to take early

## A claim about a live machine's current state decays silently — read the machine, never a comment that describes it, because when shell access is available the check costs one command and the assertion costs a wrong plan

## A sweep grep built from the text you just wrote searches for your own vocabulary — when retiring a claim, run the second pass with a pattern the OLD text would have produced, because the phrasings the diff removed are exactly the ones the new phrasings cannot match

## Reachability of an enum value is a property of the paths that ARRIVE at it, not of the site that looks most likely to set it — search for a route, never reason from one write site, or a value gets ruled out while a test covering its real path already passes

## A guard evaluated inside the filters it guards can manufacture the confidence it exists to withhold — range a safety check over the population the HAZARD lives in, never the narrowed one the feature reads, because the filter that makes the feature correct is the one that can hide the colliding case

## A computed value with no production reader is an unimplemented requirement — before calling a "report X separately" requirement done, grep the symbol and check that a caller outside `tests/` exists, because a property with tests and no consumer looks finished from inside and changes nothing a user sees

## A generated block's stale-looking state is evidence about the generator, not a defect to tidy — when a checkbox, index or table looks wrong, find what writes it before editing it, because hand-fixing derived output desynchronises it from its source and destroys the signal that something upstream is unset

## Closing a gap means sweeping the artifacts that assert the gap is open — grep for the absence you just removed, not only for the thing you just added, because a document saying "there is no X" reads as current guidance and sends the next builder to rebuild the debt you just paid

## Two verification passes that agree can both be vacuous — when a result is one you cannot derive, run the smallest thing that reproduces it by hand before believing either, because agreement between two runs of the same broken instrument is not corroboration

## A pytest exit code that is neither 0 nor 1 is not a verdict — any tool reading `returncode != 0` as "the test caught it" reports success for a run that collected nothing, and every opt-in marker in this repo makes that the DEFAULT outcome of naming such a test on the command line

## Running a generator tells you what it will DO, not whether its input is right — when derived output looks wrong, ask the generator AND then check the source tag against how every prior instance was tagged, because "no tag" reads identically as a deliberate state and as a missing one

## A sentence a UI shows is a claim about what the software can do, and needs the same verification as a docstring's claim about a guard — before writing "do X to fix this", grep for the endpoint and the control that would let a user do X, because the wording ships as a promise and a mutation check cannot tell a reachable assertion from a true one
## A docstring's safety argument is a claim about the code beside it — when a comment names a failure mode as unacceptable, the next thing written is the test proving it cannot happen, derived from the DOCSTRING rather than the diff, because stating a danger reads as defending against it and a mutation sweep only asks whether the lines you wrote are defended

## Two redundant defences look exactly like two undefended branches in a mutation sweep — when a survivor surprises you on a line you believe is load-bearing, check whether a SIBLING guard rescues the same input before writing anything, because the fix is a case per guard that the other cannot rescue, not a broader test

## A bug report's stated CAUSE is a hypothesis, held to the same standard of proof as its symptom — run the cheapest experiment that could refute it before building on it, because the symptom was observed while the cause was reasoned, and both get recorded in artifacts as though they were observed

## A grep that retires a claim must be scoped by the repository, never by the file type you found it in — run it with no `--include` and filter by eye, or state the scope you searched beside the claim you retired, because a scoped search is indistinguishable from an exhaustive one in its output

## A defect class found in one module is a question to ask of every module the same commit touches — grep the diff for the shape you just fixed before committing, because the fix is the cheapest moment to notice the sibling and having just fixed "this must never raise" does not prompt "can what I just wrote raise?"

## When a comment names a SYMBOL as the source of truth for a set, derive the test's inputs from that symbol — parametrise over the tuple/enum/registry the prose points at rather than retyping its members, because a hand-copied list makes the invariant true only for the members that existed when it was written, and the failure of the one added later is exactly the silent outcome the comment was warning about

## A test rewritten to accommodate a change needs the mutation check MORE than a new test does — after adjusting an assertion that your own change turned red, re-break the thing the test originally caught and confirm it still fails, because the pressure is to make it pass and the cheapest way to do that is to drop the assertion that was doing the work

## A dependency bump's evidence is the call sites, never the suite — before believing a version move, exercise the upstream API the code actually reaches in a clean interpreter, because a manifest no suite installs (`requirements.txt` here, which the root project does not declare) makes a green `pytest` a statement about versions that did not move

## Before calling a shared pinned upstream risky to bump, read the SIBLING lockfiles — when two projects in a repo pin the same git dependency, one plane's resolved lock is evidence about the other's, and the version you are afraid to move to may already be resolved and running next door

## A diagnostic whose "all clear" and "cannot tell" print the same line has retired the question it asks — when a check can be quiet for more than one reason, give each quiet state its own outcome naming which side said nothing, because a reader treats a pass as a measurement and the false one propagates into artifacts as evidence
