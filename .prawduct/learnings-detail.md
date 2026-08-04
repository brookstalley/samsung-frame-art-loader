# Learnings — detail

Evidence and worked instances for the rules in `learnings.md`. Headings match that
file's exactly, so a rule and its evidence stay findable from either side: the index
carries the rule, this carries what happened.

Entries older than 2026-07-31 still keep their evidence inline in `learnings.md`.
That is the shape the record linter asks them to leave, and moving them is its own
piece of work rather than a side effect of adding a rule — tracked as issue #26.

## When an artifact works a rule on two cases, derive the rule from one and check the other

An artifact that illustrates a rule twice has stated it three times: once in prose
and once per case. Deriving the rule from one case and evaluating the other is a
free consistency check on the specification — and it is not a check anyone runs,
because a worked example reads as evidence rather than as a claim. So a
specification error can sit in one for months, cited as authority by whoever has
to build against it.

**Worked instance (2026-08-01).** `nonfunctional-requirements.md` § "The mat is
geometric, and the floor is physical" specifies the mat in inches with "the bottom
margin weighted larger than the top", and works the geometry twice — a 42" panel
and a 75" one. It gives no weighting factor, which is why this surfaced at all: a
box height cannot be computed from a direction, so the number had to come from
somewhere. Reading it back out of the 42" row gives 1.15, and that row then
reproduces exactly, to the pixel, including the rounding order (whole-pixel mat
first, bottom derived from the rounded top — carrying fractions to the end moves
the answer). Applying the same 1.15 to the 75" row gives 3546 x 1844 where the
artifact says 3546 x 1723. Its width matches and its height does not; 1723
implies a bottom weighting of 1.97.

**So at most one of the two rows was ever right, and the table had sat there since
July looking like arithmetic somebody had done.** It was cited as the
specification of an unbuilt component, which is the worst case: the next builder
follows it faithfully.

**Two things this is not.** It is not "check the maths" — the arithmetic in each
row is individually plausible and the error is only visible *across* rows. And it
is not caught by the sweep rules elsewhere in this file: nothing was amended, so
there was no decision to propagate and no claim to retire.

**The check, and it costs minutes:** when an artifact demonstrates a rule on more
than one case, derive the rule from one and evaluate the others against it. Where
the rule is arithmetic, do it in code and leave the code behind as a test keyed on
the artifact's own published figures — this table is now computed by
`Settings.tv_artwork_box` and pinned by `curation/tests/unit/test_config.py`, so
the artifact and the implementation can no longer drift apart in silence. A single
worked example has no such property and is worth correspondingly less; two is a
constraint.

## An idempotence test that holds the inputs still tests the wrong half

Re-running is only interesting because something may have changed since the last run; a test that re-runs over identical inputs proves the cheap half and leaves the reason for re-running uncovered.

**Worked instance (2026-08-01).** Chunk 10's seeder is required to be re-runnable.
Its `TestSeedingTwice` class covered two cases — the tree unchanged, and a render
arriving that had been missing — and both passed. The uncovered case was the one
the operation exists for: a **master replaced** between runs. There,
`record_rendition` re-stamped the existing render with the new master's hash, so
the old unregenerated render was declared current and `ExclusionReason.STALE_RENDITION`
could never fire again for any work a seed run had touched. The wall would show the
previous acquisition with nothing reporting it.

**The tell was in my own test names.** "Seeding twice does not grow the mat
history", "the second run creates nothing" — every one of them varied the *number
of runs* and held the *inputs* still. Idempotence is a claim about f(f(x)) = f(x)
for the x that actually occur, and the x that occurs on a second run is by
definition one that changed.

**The check:** for each re-run test, name what differs between run one and run two.
If the answer is "nothing", that is the trivial case, and at least one sibling test
has to change the input the operation reads.

## Adding code to a repo means asking which guards were scoped to the old shape

A mechanical guard silently narrows when the repo grows around it: it keeps passing, and the tree it no longer walks is the one nobody is watching.

**Worked instance (2026-08-01).** Two repo-level guards, both written before
`curation/` existed:

- `tests/test_repo_hygiene.py` sets `SOURCE_TREES` and did not list
  `curation/tests` — 30 files carrying nearly all of the plane's coverage. That
  guard exists *because* a stock `.gitignore` rule once matched
  `curation/src/curation/manifest/` on a case-insensitive filesystem and nearly
  lost the only channel between the planes. The tree it could not see was exactly
  the kind of tree it was built for.
- `tests/test_config.py::test_no_source_file_carries_a_deployment_value` globbed
  only `*.py` at the repo root, so the norm `project-preferences.md` *names it the
  enforcement artifact for* did not reach `curation/src` at all — the plane that
  has to run unchanged on the Pi and on a dev Mac once the legacy modules retire.

Neither had a violation, so neither ever went red. A green guard and an absent
guard are indistinguishable from the outside, which is why this needs a habit
rather than vigilance.

**The check, when adding a directory or a plane:** grep the test tree for path
literals and globs (`glob(`, `rglob(`, `parent.parent`, tuple-of-trees constants)
and ask of each whether it reaches the new code. Then prove it — plant the exact
violation the guard names in a file under the new tree and watch it fail.

**Second recurrence, 2026-08-01, and it widens the rule: a guard can narrow
itself.** The first two instances narrowed because the repo grew around a scope
written earlier. These two narrowed on their own, with no repo change involved,
which means "check the guards when you add a tree" is a necessary habit and not a
sufficient one.

- A new test refused any colour written outside the stylesheet's token blocks. It
  cut those blocks out with two non-greedy regexes, and **the second one ate
  three quarters of the file**: the `:root` pattern removed the dark scheme's
  *nested* `:root` as well as the top-level one, leaving that media query with a
  single closing brace, so the pattern hunting for `}` `}` ran on to the end of
  the stylesheet. Every component rule went unscanned. Planting a literal
  `#ff0000` in a rule reported clean.
- A new test asserted that a failed thumbnail write leaves no partial file. Its
  fixture fed the encoder a file that is not an image — so `Image.open` raised
  *before* `save` had created anything, and the test passed with the cleanup
  deleted outright. **The fixture could not reach the guard the test was named
  after.**

Both were found by taking the `test-evidence record` prompt literally — "name the
change that would flip it, and confirm the fixture REACHES the subject" — rather
than by review.

**Third recurrence, same day, in the commit that added the rule below.** A new
test asserted that every state a badge can carry has a CSS block of its own — and
iterated a **hardcoded tuple of the five states that existed**. The tuple was
complete when typed, so the test was correct and useless in the one direction it
existed to guard: a sixth state added to the client leaves the tuple untouched and
the suite green. Deriving the list from `DisplayFit` and `ArtworkStatus`, both
closed enums, is one line, and planting a sixth verdict now turns it red. Caught
by the Critic, which is the tell that reading the rule is not the same as applying
it — I wrote "assert the scope as well as the finding" and shipped a guard whose
scope was a literal, in the same commit.

**What generalises: a guard's effective scope is invisible in its result.** Green
means "nothing was found in whatever I looked at", and the size of *whatever I
looked at* is exactly the thing no assertion states. So when a check computes its
own scope — a regex strip, a glob, a file list, a fixture that has to reach a
branch — assert the scope as well as the finding. The colour check now asserts
that what it scanned is more than half the stylesheet and contains six named
selectors; that second assertion is what makes the first one mean anything.

**Fourth recurrence, 2026-08-02, and it adds the failure mode above the code: the
stale scope got written up as a virtue.** Chunk 14A's network guard iterated a
literal list of three modules that may not import a transport — the three that
were the whole of discovery when it was written. Chunk 14B then added a client and
an engine, and the guard went on passing without covering either; a phase-2 engine
added above the seam in Chunk 16 would likewise have been unguarded. Its own
sibling eight lines above already did the correct thing (`rglob` over the package
with an allowlist and a non-vacuity assertion), so the pattern to copy was in the
same file.

The new part is what I did with the green. I wrote into `architecture.md`: *"The
network guard's list did not grow, and that is the point."* **The unchanged list
was evidence of nothing, and I recorded it as evidence of correctness** — in a
durable artifact, where the next reader would have inherited it as a design
property rather than a gap. A literal-scope guard makes "it still passes" and "it
stopped covering anything new" the same observation, and prose is where that
ambiguity gets resolved in the wrong direction.

**So the habit extends: when you find yourself writing that a guard's scope
*didn't need to change*, that is the sentence to distrust.** Either the guard
derives its scope — in which case there is nothing to say — or it does not, in
which case an unchanged list beside new code is the defect, not the reassurance.
Now inverted to an allowlist over the whole package, proven by planting a
violation in a module the old form never named.

## Prose explaining a distinction is not a mechanism recording it

Careful prose about why two things differ reads as if the difference is handled. It
is not: the mechanism that records the difference is a marker, a test, a column or
a type, and the prose is free to describe one that was never wired.

**Three instances in one session (2026-08-02), which is why it is a rule and not an
anecdote.** All three were caught by review rather than by me.

- A docstring asserted the phase-2 ordering was universal while the chunk
  description required it to vary by `source_class`. The descope was defensible and
  I had reasoned it through — nothing produces the other source class — but nothing
  anywhere recorded that reasoning, which is exactly the difference between a
  descope and a silent drop.
- `PreviewCache.store` said "every failure path here reports absence rather than
  raising". Two of its failure paths raised. The sentence was the enforcement.
- The free museum live-suite carried a docstring arguing at length that it costs
  nothing, on a marker whose own registered description reads "Costs money, needs
  OPENROUTER_API_KEY" — so its instruction to run `-m live_api` would spend real
  credit. **The distinction was explained correctly and filed on the wrong side of
  itself.**

**The tell is writing the words "unlike", "rather than", or "for a different
reason".** Each one asserts a distinction, and each is worth one question: what
would go red if this stopped being true? For the marker that was a second marker;
for the contract, a test per branch; for the descope, a dated deferral with a named
reopen trigger.

**The check:** after writing prose that explains why something differs, name the
mechanism carrying the difference. If the answer is "this paragraph", the
difference is undefended — and prose is the one artifact that cannot notice when it
stops being true.

## A negative claim needs the search that would have falsified it

"There is no X" cannot be checked against the evidence that produced it: *I looked and found nothing* and *I looked in the wrong place* are the same observation. So before writing one down, name the search that would have found an X and confirm it covers where an X would actually live.

**Two instances, 2026-08-02, both inside Critic-resolution prose and both caught
by the next review.**

- Resolving a finding about `requirements.txt`, I wrote that no backlog item had
  ever been filed for the gap — so the old "filed rather than fixed" disposition
  "pointed at a record that did not exist". **Issue #31 was open the whole time.**
  The search read `.prawduct/backlog.md`, which this project froze when it moved
  to the GitHub Issues backend — a fact recorded in the *same review* I was
  resolving, as a separate finding.
- Recording why a new MCP result field shipped without a contract test, I wrote
  that "nothing under `tests/contract/` asserts result shapes today, which is why
  the letter could not be followed cheaply". That suite asserts payload fields
  throughout, including the whole error envelope, through the same booted-server
  driver the new assertion would use. I checked the directory rather than the
  claim.

**Why this is worse than an ordinary wrong fact: a false negative usually arrives
as a *reason*.** Both of these were justifications for a decision, written into
durable records. A wrong assertion gets corrected when someone trips over it; a
wrong reason gets **reused** — the second was already licensing the next skip of a
gate that exists to catch producer/consumer disagreements across an external
surface, and the next person would have skipped it on my authority.

**Same shape as a literal-scope guard, one layer up.** There, green means "nothing
was found in whatever I looked at" and the size of *whatever I looked at* is what
no assertion states. Here, prose makes the identical claim with no assertion at
all. The remedy is the same: state the scope, not just the finding. "No item on
the Issues backend (`gh issue list --state all --search …`)" is checkable; "no
backlog item was ever written" is not.

**Cheapest sufficient checks, both under ten seconds:** for a backlog claim, query
the live backend named in `backlog_service_repo` rather than any file; for a
"nothing tests X" claim, grep for the assertion shape rather than looking at the
directory.

## Prose that ships to a caller is behaviour, and needs a test aimed at it

When a behaviour changes, the sweep has to reach the sentences that describe it to the caller — a tool tip, a `help` payload, an error hint — not only the artifacts and the docstrings; and where a tip states a rule the code enforces, pin them to each other with a test keyed on the enum of causes.

**A tool tip, a `help` payload, an error hint — anything the consumer reads before
deciding what to call — drifts exactly like code and is checked like documentation,
which is to say not at all.** When a behaviour changes, the sweep has to reach the
sentences that describe it to the caller, not only the artifacts and the docstrings.

**Worked instance (2026-07-31), and it recurred within one chunk.** Chunk 09
changed `art_theme(action='activate')` to publish the manifest. The service
docstring, the binding, `api-contract.md`, the acceptance criteria and a new test
all said so; the action's own tip still read "It does not itself rewrite the
manifest — call `art_display(action='sync')`". The Critic caught it. In the *same
commit that fixed it*, `show_now`'s refusal widened from archived-only to the whole
readiness rule — and its tip was missed the same way, caught by the next round.

Two things made both invisible. The tips are the one text with no assertion behind
them: `test_mcp_surface.py` pinned tool names, annotations, schemas and that every
declared action appears in the description, so a wrong *tip* was the one drift the
contract suite could not see. And a tip reads as commentary while functioning as
contract — this surface's primary consumer is a model, which acts on the tip and
never sees the docstring.

**The rule:** when a refusal, a precondition, or a side effect changes, grep the
tool records for the old rule as part of the same change — the artifacts are not
the end of the sweep. And where a tip states a rule the code enforces, **pin them
to each other**: enumerate the causes the code can raise, assert each is named in
the tip, and drive the real service to prove each documented refusal is one it
actually makes. A table keyed on the enum fails the day a sixth cause is added,
which is the day the tip would otherwise have gone quietly stale. See
`test_every_reason_show_now_can_refuse_for_is_named_in_its_tip`.

## A package's declared dependency floor is a claim; what it imports is the constraint

`install_requires` (or its equivalent) is written by hand and nothing checks it
against the code beside it. A resolver honours the metadata, so a package whose
declared floor is lower than its real one installs cleanly and fails at import —
after the resolver has already reported success. The declared floor is evidence
about what the author believed; the import statements are the constraint.

**Worked instance (2026-08-01).** The `samsungtvws` fork's target revision imports
`websockets.asyncio.client` and `websockets.protocol.State`, neither of which
exists before websockets 13.0. Its `setup.py` declares `websockets>=10.2`. This
repo pinned `websockets==12.0` — a version that satisfies the declaration and
cannot run the code. The whole dependency set resolved, and `import samsungtvws`
raised `ModuleNotFoundError: No module named 'websockets.asyncio'`.

Nothing about the item that scoped the bump would have surfaced it: it was framed
as replacing one pin, and no amount of reading `delete_list` and `upload()` — the
two functions named — reaches an import line in a different module. What surfaced
it was diffing the *whole* library between the pinned revision and the target,
including files the item never mentioned. `async_connection.py` is where the
websockets API is touched, and it is not a file anyone had reason to open.

**The rule:** when moving a pin, diff every module in the package, not the
functions the ticket names, and read the import lines first — they are the only
part of a dependency's metadata that cannot be wrong. Then install the exact
proposed set and import it, because a resolver reporting success is a statement
about the metadata rather than about the code.

## Before answering the question a spec asks about a candidate, check that the candidate is one

A well-written spec narrows the work by naming the question that decides it. That
is usually a gift and occasionally a trap: the question presupposes a frame, and
if the frame is wrong the answer is wrong in a way that looks thorough. The check
costs one command — list what the candidate actually contains — and it runs before
the question, not after.

**Worked instance (2026-08-01).** The chunk said: *"confirm the PyPI release
carries the fork's LS03A/B/C/D support before preferring it."* A careful answer to
that question would have compared model-support tables and reported a verdict. The
first thing done instead was `tar tzf` on the release's sdist, which showed no
`async_art.py` at all — the PyPI package ships a synchronous art client with no
event callbacks, and this product's entire TV boundary is built on the async one.
PyPI was never a candidate on any grounds, and the LS03 comparison would have been
an elaborate answer to a question that could not have mattered.

The premise turned out to be doubly off: `LS03` appears nowhere in either
codebase. It is a README label. The fork's real generation handling is a branch on
model *year* in `remote.py` — from 2024, mint a pairing token before the art
channel will accept one. Both the question's frame and its vocabulary came from a
README rather than from source, which is the tell worth carrying: **a premise
sourced from documentation deserves the same verification as the answer.**

## An index that under-claims its enforcement is defective, not conservatively safe

An index that names a mechanism it does not have is the obvious defect: it grants
false confidence. The inverse — a row saying `Critic` while a real test guards the
norm — feels like the safe direction, because nobody is misled into relaxing.

It is not safe. **The pointer runs both ways: the index protects the artifact as
much as the artifact enforces the norm.** A test no row names is a test a refactor
can delete, or rename, or quietly narrow, with nothing to notice — which is how an
unrecorded mechanism becomes a phantom mechanism, and the row that was merely
modest becomes the row that lies. Audit both directions: for every row, does the
named mechanism exist; and for every enforcement artifact, does a row name it.

**Worked instance (2026-08-01).** The Norm Health sweep found the "no secret ever
reaches a log line" row recording Mechanism `Critic`, artifact `—`, while
`tests/test_config.py::test_startup_logging_never_emits_a_secret` had guarded the
norm's highest-risk path since `ba007cd` on 2026-07-27 — the same bundle that
added the norm. The index recorded no mechanism from the moment the mechanism
existed. Mutation-proven live: making `redacted_config` return the raw key fails
it. The row is now `Test (startup config path) + Critic (everywhere else)`, split
so the judgement half — an object logged for context whose repr contains a token —
stays where no test can reach.

Two rows in this same index had already been found claiming enforcement they did
not have, which is why the sweep ran at all. This is the third failure mode of the
same artifact and the only one nobody was looking for.

**The reverse direction is unswept, and two probes into it have each found
something.** The rule above prescribes auditing *both* directions; the sweep that
produced it ran only rows→artifacts. **What follows is two worked instances, not
a completed audit** — the wording here matters, because a future session that
reads "swept, one finding, filed" will not re-run it.

*First probe, prompted by a Critic note.* `tests/test_repo_hygiene.py` — three
guards, among them `test_the_tv_token_is_not_tracked`, whose docstring records
the reason ("it was committed to a public repo once") — named by no norm row,
with no norm statement anywhere in the index for either thing it enforces.

*Second probe, prompted by the next Critic round, after the first was written up
as though it were the answer.* `curation/tests/unit/test_persistence_boundary.py`
is the same shape one plane over: an AST import check with a named exception set,
guarding that the storage driver stays inside the persistence package. Its
docstring states the norm, explains that "the failure mode is invisible by
construction, so it gets a mechanical guard rather than vigilance", and **cites
`tests/test_repo_hygiene.py` as its precedent** — so the two unnamed guards
already knew about each other, and the index knew about neither. **That is three
consecutive failures of this rule against its own tree, two of them found by
review rather than by the sweep that was looking.**

The reverse sweep needs judgement, not a blanket check: the index names a
handful of test artifacts and the suites hold many times that, nearly all
correctly unnamed because they verify behaviour rather than enforce a norm. What
belongs in the index is the test whose *purpose* is a norm — which is a reading,
not a pattern match, and is why this direction resists the mechanical guard the
forward direction accepted. Tracked as issue #40.

*(The count that stood here is deliberately gone. It read "38 of the repo's 40
test files" and was right when written — but two agents measured it an hour apart
and got 40 and 39, because the boundary is genuinely ambiguous: an untracked new
file counts or does not, and the hand-run operator tools are test-named without
being suite files. A tally that needs three caveats to be true is a tally that
will be quoted without them.)*

## A mutation test must prove it mutated, or its green is indistinguishable from a pass

Mutation is how you tell "the test exists" from "the mechanism works", and it is
the only check worth recording in an enforcement index. But a mutation that
silently fails to apply produces a green suite that looks exactly like a verified
guard — the failure mode the mutation was run to rule out, now hiding inside the
instrument. **Assert the mutation landed before trusting what the suite says
about it**, and abort rather than report.

Corollary on reverting: `git checkout <path>` is only a safe "undo my mutation"
idiom on a file with no other uncommitted changes. On a file being edited for real
work it discards that work too.

**Worked instance (2026-08-01).** During the Norm Health sweep, a mutation meant
to make `config.py` leak a secret targeted a string literal that does not exist —
the redaction is a loop over `_SECRET_KEYS`, not the line searched for. The file
was unchanged, `pytest tests/test_config.py` reported 9 passed, and that green was
a hair from being written up as "the guard holds". The redo carried
`assert old in s, "aborting rather than reporting a false pass"`. In the same
session the revert for a different mutation was `git checkout` on an artifact
carrying every edit of the sweep; the sandbox classifier refused the command, and
the redo used a checksummed backup instead.

This is the third consecutive session in which the measurement apparatus carried
the defect class it was built to measure — the prior one being an
`except Exception` in the evaluation driver that would have swallowed the envelope
invariants and reported a contract violation as a low score.

## A cap sized from one part of a result is not a cap

`api-contract.md` sized the review surface's 400 px thumbnail cap from image
tokens: 40 works x ~160 = 6,400, "comfortably inside the budget". The arithmetic
was right and the conclusion was wrong, because the *rows* scale with the same 40.
The first listing shape measured ~7,000 tokens of text on top of the 6,400,
putting a full page past the 10,000 at which the client warns with the images
still innocent. Narrowing rows to what a caller needs in order to choose — moving
the instance record behind a second action — brought the page to 10,200.

The general form: a bound justified by a calculation is only as good as the terms
the calculation names. Ask what else grows with the same N. The tell here was that
the artifact's own table listed only image costs, and nobody had ever multiplied
the row.

Two thresholds turned out to want two knobs rather than one compromise: the page
*ceiling* is sized against the hard cap, where truncation would take the pictures
and leave the rows; the *default* page is sized against the warning, so a caller
who asked for nothing never trips it.

## A rule stated at one level does not enforce itself one level up

`api-contract.md` says a below-floor image is "shown, labelled, and selectable —
never hidden", in a section about what the *image* listing must show. The work
listing carries one picture per row, and the obvious choice — the selected
instance — has no answer for a work where nothing was selected, which is exactly
the below-floor case. Those rows arrived with no picture at all.

Nothing was violated by the letter of the rule; it simply did not reach. The
failure was caught as a test expectation I had written wrongly, which is the cheap
way to meet it — the test asserted two image blocks and got one, and the reason
was the product's rather than the test's.

## A field whose only defence would be a test written to defend it is a field to delete

Two mutation survivors in the review surface were `run_id` on `get_work` — beside a
work already carrying `discovery_run_id`, one fact under two names in one payload —
and `run_id` on `list_images`, which cost a `get_run` per call to report a run the
caller necessarily already knew, having arrived with a work id from a run-scoped
listing.

The reflex on a survivor is to write the missing test. The question to ask first is
what the field is for. Both were deleted, along with the wrapper dataclass that
existed only to carry one of them.

## Governance you put where it cannot see is governance that did not run

Chunk 17A and 17B were authored as `#### Chunk 17A:` / `#### Chunk 17B:` nested
under an `### Chunk 17:`, while every other split chunk in the same file — 07B,
08A, 08B, 14A, 14B, 16A, 16B — uses `###`. The record linter matches the h3 form,
so both were invisible to it and `chunk-ref-missing` came back `null`.

**Null is not zero.** The check did not pass; it did not run, and nothing about the
chunk's declared deliverables was graded. The Critic caught it by hand and found
two real deliverable gaps in the same breath — one of them a deliverable I had
dropped without saying so.

## A guard built from recurrences is scoped to where you looked, not to the failure

**When repeated instances justify a mechanical guard, derive its scope from the
failure *mode*, not from where the instances were found.** N recurrences in one
place are two facts wearing one coat: the failure is real, *and* that is where
you happened to be looking. Only the first is about the defect. Write the failure
in one sentence, then ask where else that sentence is true — those places are
unguarded, and they are where the next instance appears.

This is the sibling of "adding code to a repo means asking which guards were
scoped to the old shape", and the difference is the whole point. There, a guard
was correctly scoped and **narrowed** as the repo grew around it. Here the guard
never narrowed and never will: it was born scoped to its evidence, which was
narrower than its subject from the first line.

**Worked instance (2026-08-02, the first stamped Norm Health sweep).** Three
prior sweeps had each found the norm index asserting enforcement it did not have
— a row naming ruff rules selected in neither `pyproject.toml`, a row naming a
test file that had never existed, a row whose carve-out list fell three hours
behind the config. The third built `tests/preferences/test_norm_index.py`, which
resolves every test artifact the index names and refuses to scan a table it can
no longer parse. Good guard. Mutation-verified in both directions.

Its scope is **one column of one table** — the Enforcement artifact column — and
its docstring says so deliberately, because the Why column legitimately discusses
artifacts that do not exist.

The next sweep found five instances of the same failure and **not one of them was
in that column**:

- § Tooling described `r`, an extensionless freeze file at the repo root, and
  asked that it "should be renamed to say so". The rename had shipped; the path
  had not resolved for a week.
- § Tooling placed the `dezoomify-rs` configuration in `config.py`, where it has
  never been — it is a literal in `image_utils.py`.
- § Code Style said `image_utils.py` annotates 8 return types. The AST says 9.
- § Architecture Patterns said async was confined to the TV boundary and
  instructed the reader to "keep it that way". Four modules said otherwise, and
  had since before the sentence was written.
- The broad-except row claimed curation had exactly one broad catch, in its
  **Why** column — the same table, the same row, one cell outside the guard.

The failure mode was never "the Enforcement column names a file that is not
there". It was **"this artifact asserts something about the tree and nothing
counted it"** — and that sentence is true of every cell and every bullet in the
document.

**The direction is not random, and the exception is what makes it legible.**
Three of the four countable claims understated the gap they were arguing about:
19 print() calls where there were 39; "the only broad catch" where there were
three; five service-layer departures where the AST says six — that last one
written into `project-state.yaml` *during this sweep*, by the agent writing this
entry, and caught only by re-counting before trusting it. The fourth ran the
other way: `image_utils.py` was said to annotate 8 return types and annotates 9,
so the code was better than its description.

That is the tell. The three that drifted were **arguments** — each number was
doing rhetorical work in a sentence about how bad something was, and each landed
on the figure that felt right while the argument was being written. The one that
drifted the other way was **inventory**: nobody was arguing anything with it, so
it simply went stale when a function gained an annotation. Both fail; only the
first fails in a direction. Distrust a number hardest when it is load-bearing for
a claim you are making, because that is when you are least likely to go and count.

**The check.** Every one of these was findable by counting — `grep -c`, an AST
walk, `git show <commit>:<file>`. None needed judgment. Careful prose review will
not catch them, twice over: it reads for sense rather than arithmetic, and two
sessions of it did not. Before asserting a quantity or a location about the tree
in a durable artifact, run the command that produces it, in that moment. Prefer
the invariant that cannot go stale; where a number is unavoidable, compute it as
you write it and never copy one from an adjacent line.

## 3tears can run with zero infrastructure

### `3tears-models` needs no core — and that stopped being the argument

The 2026-07-19 reading of the source was right and remains right: the package
imports no 3tears core. What changed on 2026-08-02 is that "no core" was being
used as "nearly free to adopt", and the measurement said otherwise — it pulls
`3tears-observe`, `3tears-media-contracts`, `anthropic`, `langchain-anthropic`,
`langchain-openai`, `langchain-openrouter` and `jsonschema` into the default
install, which is the heaviest install in the repo. It was declined on exactly
that weight and now sits in its own dependency group that nothing in the default
run imports.

The shape worth keeping is not the dependency list, which will move. It is that
**a true fact can be the surviving half of a retired argument**, and a reader of
the index alone would have reconstructed the conclusion the measurement killed.
Superseding a decision means marking the evidence that supported it, not only
recording the new decision somewhere else — the evidence is what the next reader
reasons from. Found by Critic cross-check (`rev-20260803T032431Z-f8474689` R-13),
not by the sweep that followed the decision.

## Data and cache contract

**`tile-cache/` is on neither side of this contract** *(classified 2026-08-03,
when acquisition was built)*. It is transient working space holding the tiles of
a **partial** download so a retry can resume, and it is removed per source as
soon as that work holds a complete image. Transporting it would carry the debris
of an interrupted fetch to another machine. `api-cache/`, which the 2024
`config.py` names, has no producer at all: the curation plane asks museums over
HTTP and caches nothing on disk.

**Narrowed 2026-08-03, when acquisition was actually built.** The upstream list
had named `raw/`, `tile-cache/` and `api-cache/`, and only the first belongs.

`tile-cache/` is **transient working space**, not an upstream artifact. It holds a
*partial* fetch's tiles so a retry can resume without re-downloading what already
arrived, and it is reclaimed per source the moment that work holds a complete
image. Transporting it would carry the debris of an interrupted download to
another machine, which is the opposite of what the upstream class means.

`api-cache/` has **no producer at all**. It exists only in the 2024 root-plane
`config.py`; the curation plane asks museums over HTTP and caches no response on
disk. It had been listed in five places as something to transport.

The general shape is worth keeping: a directory named in a contract is not
evidence that anything creates it, and "upstream vs derived" has a third case —
working space, which is neither transported nor regenerated because it is only
ever meaningful mid-operation.

## A test that SPELLS a path the code DERIVES is disarmed by the next rename

The failure has two halves and the second is what makes it dangerous. A fixture
that writes its seed to a path the code *computes* — a staged name, a cache key,
a derived filename — stops reaching the code the moment that computation changes.
The rename itself looks correct in review, and the suite stays green, because a
test whose setup no longer lands anywhere the code reads simply exercises the
empty case and passes.

So after a rename the question is not "do the tests still pass" but "does
anything still *reach* what they claim to guard". A green suite answers the first
and is silent on the second.

**Found 2026-08-03, by a Critic round reviewing the fix from the round before it.**

A wrapper staged its fetches at `<name>.partial`. That turned out to be
deployment-fatal — the binary picks its output encoder from the file extension —
so the staging expression changed to `<stem>.partial<suffix>`. One test seeded
debris at the staged path to prove a stale file gets cleared before a retry, and
it spelled that path by hand: `work.jpg.partial`.

After the rename the code staged at `work.partial.jpg`. The seeded debris now sat
somewhere nothing looked. The test's fake refused to overwrite only if its output
already existed; it no longer did, so the fake never refused, the run succeeded,
and **the test passed identically with the clearing branch deleted outright** —
which its own comment said had to be impossible.

Nothing flagged it. The rename touched no test file, so no diff review had reason
to look; the suite was green; and a mutation sweep run *before* the rename had
found the branch defended, because it was.

**The fix that generalises is not "update the string".** The test now performs one
ordinary run and takes the staged path off the result, then seeds debris there. It
cannot be disarmed by a rename, because it never claims to know the name. The name
itself is pinned by a separate, single-purpose assertion — which is the right split:
one test owns the naming rule, and the other owns the clearing branch and merely
needs *a* staged path.

**Where to apply it.** Any fixture that seeds, deletes or asserts on a path the
production code computes. Derived filenames, cache keys, staging suffixes, temp
names. If the test and the code both spell the same rule, they are two copies of
it, and the copy in the test is the one nothing enforces.

**The tell at review time**: a test comment that says "this would pass if X were
removed" beside a fixture built from a literal the code also builds. That comment
is a claim about coverage, and a hand-written path is exactly what makes it stop
being true without anyone noticing.

