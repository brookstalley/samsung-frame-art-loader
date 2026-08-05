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

## When a fixture seeds a file at a path the code DERIVES, learn that path from an observed run instead of spelling it out — a rename leaves the fixture pointing at nothing, and the test stays green while the branch it guards goes undefended

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

## A claim repeated in three artifacts is ONE piece of evidence copied twice — when a property is asserted in prose, verify it against the code before adding the third statement of it, because every later text inherits it from the earlier prose rather than from the behaviour

Chunk 18B published "regenerate spends nothing" in a tool tip, a parameter
description and an `api-contract.md` correction block, while
`PreparationService.prepare()` called the mat chooser *before* its
already-current branch — so the first call on every acquired work made a paid
vision call. Two Critic reviewers found it independently through different goals.

The confident sentence was the reason nobody re-checked. The free-re-render
property went into the module docstring early, and each later text was written
from that prose rather than from the code, so three statements agreed with each
other and none of them with the behaviour. Repetition reads as corroboration and
is not: the second and third statements carry no independent evidence at all.

The check that would have caught it is cheap and specific — before writing a
property into a *second* artifact, read the code path that makes it true. Not the
first statement of it, which is usually written while the code is in mind; the
second, which is written from the first.

## When a module's docstring says it exists to stop two callers drifting, adding a caller is the moment to READ that docstring — the drift it warns about reappears in the new caller, and the escaping case will be the common path rather than the one being written

`services/imaging.py` opens with "The one downscale this product does, so its two
callers cannot drift apart… the copies had already diverged on which exceptions
they name." Chunk 18B then added a third and fourth caller of the same decode —
the mat engine and the compositor — one translating Pillow's failures into a
named refusal and one letting them escape.

The escaping case was the *common* one, which is the part worth carrying. A work
that already has a mat skips the mat engine entirely and reaches the compositor
first, and every `set_mat()` does the same, so the path with no translation was
the path most calls took. The path that was correctly guarded was the rarer one.

This is the third consecutive chunk whose review turned up "the second caller of
the same idea" — 17B, 18A and 18B. The habit that closes it is not a checklist
item at review time but a reading habit at write time: a docstring that names a
past divergence is a warning addressed to whoever adds the next caller.

## At the moment of a fix, ask what the change now COVERS that it did not before — a wrapper added to translate a read will also catch the write beside it, and a claim added to one payload will be published by the branch that shares it

Chunk 18B's review ran to four rounds, and two of the middle ones found defects
in the previous round's *fix* rather than in the original work. The chain:
`regenerate` was documented as free while it paid for a first mat; the fix
threaded the cost through and wrapped `compose` in the decode translation; the
wrapper also caught `compose`'s **write**, so a full disk came back as "the image
could not be read", pointing at the museum for a fault on the host; fixing that
added caller-facing fields; the fields were asserted by nothing; asserting them
left the one notice state the join exists for unpinned; pinning that left the
separator unpinned, which a mutation then proved.

Every link was a small, correct-looking edit, and none was careless in isolation.
What they share is scope blindness at the moment of the fix: the thing named in
the finding got changed, and nothing asked what *else* the change now reached.
`reading()` was written to translate a decode and was applied to a function that
also writes. `cost_usd` was added to a payload and the service that produces it
was tested rather than the surface that publishes it.

One question at fix time closes most of it — not at review time, where it is the
reviewer's job anyway: **what does this change now cover that it did not before,
and which of those did I mean?** A wrapper covers everything inside it. A claim
in a tool tip covers every branch that returns that payload.

## A comment that justifies code by naming a constraint is a CLAIM — check the constraint before inheriting the workaround, because a false reason usually sits on top of wrong behaviour

**Two instances in one review round, and the second is why this is a rule rather
than an anecdote.**

Three `curation.config` imports sat at function scope in `services/container.py`,
explained as "config reads this package to compose its settings objects, so a
top-level import would close the loop". Walking config's module-scope import graph
takes about ten lines and shows no loop: it reaches `manifest.builder`,
`manifest.heartbeat`, `services.display_fit` and `services.runner`, and none of
those reaches `container`. The workaround was inherited by everyone who read it,
and it hid a container→config edge from anything reading the import graph.

The costlier one had the same shape. A comment on the refused-promotion branch of
`AcquisitionService._record_success` said omitting `record_fetch` avoided
overwriting "the fact the next comparison reads". The next comparison reads
`Original.fetch_status`; `record_fetch` writes only the `Source` row and cannot
affect the guard at all. **The wrong reason was not a documentation slip — it was
load-bearing.** The behaviour it justified was also wrong: skipping the write left
`sources` reporting a fetch date older than the retry the curator had just been
told to make, on the very outcome whose notice sends them to that read. Correcting
the comment meant correcting the code.

That is the asymmetry worth carrying. A comment that merely describes can be
stale harmlessly. A comment that *justifies* is the record of a decision, so when
its premise is false the decision was made on that false premise — and the code is
suspect, not just the sentence. Distinct from the rule "A guard's comment names
what it excludes, not what it silently breaks", which is about what a *true*
comment leaves out; this is about the comment that is not true.

## A decision that DESCOPES something has to be walked back through every artifact that promised it — the promising artifacts are never the one you are editing when you make the call

**Chunk 18B was explicitly delegated the call on whether to extract the 41
hand-tuned mat colours into `tests/fixtures/mat_corpus.json`, and decided not to.**
The decision reached the code — a test docstring — and the chunk's own change-log
entry, and stopped there. Three artifacts kept promising the opposite for a day:
`nonfunctional-requirements.md` said `all.json` must survive only "before the
regression fixture is extracted", Chunk 06 still carried the fixture as a
deliverable and as an acceptance criterion that could never come true, and the
backlog item asking for the extraction was still open and still `stage:ready`.

**The mechanism is positional, which is what makes it recur.** You make a descope
decision while editing the thing you decided *not* to build — a test, a module, the
chunk you are in. Every artifact that promised the thing is somewhere else by
construction: an earlier chunk's entry, a requirements section written months
before, a backlog item filed by someone else. Nothing you are looking at while
deciding contains the promise, so nothing prompts the sweep.

The residue is worse than an ordinary stale doc. A landed chunk asserting an
acceptance criterion that can never come true reads to an auditor as a missed
deliverable, and an open backlog item instructs the next person to build the thing
the product decided against — with the reasoning nowhere they will look.

The check is one grep on the *thing's name* at the moment of deciding, not later:
every artifact naming it, plus the backlog. Sibling of the rule "When a behaviour
is retired, grep the sentences that justified it, not just the code", which covers
retiring a behaviour that exists; this covers retiring one that never will.

## When a chunk is parked behind access it does not have, check which of its DEPENDENCIES actually need that access — a dependency inherits the parking by adjacency rather than by need, and one that gates the parked work is the cheapest thing to take early

**2026-08-04.** Issue #13 — the SD-card storage decision — was Chunk 03's sole
declared dependency, marked "blocking for this chunk only" when the plan was
authored on 2026-07-20. Chunk 03 is bench-gated, so it moved with the hardware
block every time the bench lapsed: parked on 2026-07-20, unparked 2026-07-31,
re-parked 2026-08-02 with 05, 04, 12 and 13.

**The decision itself never needed the bench.** It is a choice between storage
media, answerable from the write profile and the existing artifacts, and the
operator settled it in one exchange with no hardware present. It sat parked for
two weeks because the *chunk* it blocked was parked, not because anything about
the decision required waiting.

The failure is that the plan's own re-sequencing rule operates on chunks, and a
dependency has no position of its own — it moves wherever the chunk sits. Nothing
was written down that was wrong; the parking was simply never questioned, because
the thing that needed questioning was one level below what the rule ranges over.

**The tell was in the chunk entry the whole time.** Chunk 03's `Depends on:` line
named an *operator decision*, not a hardware step — and its own description said
the decision "determines the paths later chunks bake into deployment", which is an
argument for taking it as early as possible rather than as late. A dependency whose
description explains why it must come first, sitting in a chunk parked to the back,
is the shape to look for.

**Generalises past bench access.** The same reasoning covers any access
constraint — a credential, a staging environment, a third party's availability. Ask
of each dependency whether it needs the thing being waited for, or is merely
adjacent to work that does.

## A measured behaviour and an explanation of it are separate claims

Verified against a foreign API 2026-08-04. An upload defect was correctly measured
— two failures at the client's default timeout, one of them returning `None` with
the image demonstrably on the television, and a success at an explicit wide timeout
— and then given a mechanism: a named source line for the raise, a rule about which
argument form fails how, and a percentage of the timeout budget. **None of the
three was supported by the library's source.** The line cited was inside a
different method; the acknowledgement path returns rather than asserting; the
argument branch selects only a chunker; and the percentage divided a whole-call
wall-clock by a budget governing part of it.

**Two Critic rounds passed it.** The second explicitly listed the wrong percentage
as evidence the finding had been *properly filed*. What caught it was a backlog
subagent reading the pinned source to do an unrelated task and noticing that a line
number did not say what the prose said it did.

The failure was not carelessness about the measurement, which was sound and still
stands. It is that an inference and an observation went into the same paragraph in
the same voice, after which nothing downstream could separate them. Foreign APIs
make this worse: their source is right there, so an explanation feels checkable
even when nobody checked it.

**The tell** is a mechanism written in the same voice as the measurement: if the
behaviour was observed and the cause was reasoned, they cannot honestly share a
sentence.

## Do not trust a foreign client's return value in either direction — confirm against the system itself

This product's television client is wrong in both directions, which is what makes
the rule general rather than a note about one bug. Deletion could not confirm
removal — the library's only removal verb discards the response and always yields
`None`. Upload reports failure on uploads that succeeded, at its default
acknowledgement window. The consequences are opposite and both are bad: the first
cannot tell *failed* from *unconfirmable*, and the second turns a retry loop into
duplicate content on a device with finite storage.

The answer was already in this repository before the rule was written. The
confirm-deletion wrapper built for the first defect — ask, read the category back,
raise only when neither outcome can be established — is exactly the shape the
second one needs. It generalises to every verb on a boundary whose library is
unowned and unmaintained.

**Why the read-back generalises.** It is one extra read against a system you are
already connected to, and it is the only thing that survives a library that is
wrong in both directions — which this one is.

## A claim about a live machine's current state decays silently — read the machine, never a comment that describes it

Config comments, deploy docs and prior findings record what a box looked like when
someone last looked. The box gets reimaged, users get renamed and trees get emptied
without touching a single line of the text that describes them.

The worked instance: the operator was told the 41 masters were on the Pi at
`/home/tvpi/art`, taken from a **comment in `.env`** and stated as an observation.
There was no `tvpi` user on that machine and the art tree was empty — the card had
been rebuilt under the SD-card decision. Working SSH access was one command away.

This is the same shape as the adjacent rule about inferences and observations
entering a sentence in the same voice, with one difference worth keeping separate:
a code comment's claim may stay true indefinitely, while an environment claim decays
on its own and gives no signal when it does.

## A guard evaluated inside the filters it guards can manufacture the confidence it exists to withhold — range a safety check over the population the HAZARD lives in, never the narrowed one the feature reads, because the filter that makes the feature correct is the one that can hide the colliding case

Chunk 22, 2026-08-04. A browse offers works by artists a run named, and retries an
unmatched name on its surname *only where the collection reports that surname
naming one artist* — the rule exists because surnames collide and offering one
artist's work under another's name is a misattribution nothing downstream catches.

The natural implementation asks that question in the same request as the browse,
inheriting its filters. Measured against the live API, that is exactly wrong: the
Art Institute holds one Antonio Martorell (a `Graphic Design`, which the
wall-appropriate type filter removes) and one Bernat Martorell painting. Filtered,
the check sees a single artist and licenses the retry; unfiltered, it sees both and
refuses. **The filter that makes the feature correct is the filter that makes its
guard wrong**, because it hides one of the two colliding artists.

Generalises past this case: a check that answers "is this unambiguous?" must range
over the space the ambiguity lives in. Narrowing first does not make the check
cheaper, it makes it answer a different question — and the wrong answer is the
confident one. The unit test reproduces the asymmetry (the fake responds
differently depending on whether the request carries the type filter), so an
implementation that scopes it wrongly fails by offering a work rather than by
looking wrong.

## A computed value with no production reader is an unimplemented requirement — before calling a "report X separately" requirement done, grep the symbol and check that a caller outside `tests/` exists, because a property with tests and no consumer looks finished from inside and changes nothing a user sees

Chunk 22, 2026-08-04, and **all three Critic reviewers found it independently** —
correctness, design and sustainability — which is the strongest signal this review
process has produced.

`product-brief.md` required that works a collection offers "count against a per-run
bound reported separately from the proposed count". `RunView.proposed_count` and
`RunView.offered_count` were written, and unit-tested, and read by nothing. Every
run-level figure still counted `len(works)`, so for the chunk's own acceptance
scenario — one proposed work unresolved, twelve offered — the MCP surface reported
`{"total": 13, "resolved": 12}` and the sentence a curator reads said "12 of 13
works have an image": a resolution rate the run had not achieved, on the same
surface the resolution floor had just been made load-bearing on.

The failure mode is specific and worth naming apart from forgetting. The
requirement's *mechanism* was implemented and its *consequence* was not — and
because the properties carried tests, the work looked complete from the inside.
Tests over a value prove the value is right; they say nothing about whether
anything asks for it. Four separate records asserted the reporting existed,
including the comment directly above the two unused properties.

**"Name the surface that displays it" was the first form of this check, and it
failed twice** — naming a surface is something you can do from memory while
looking at the wrong thing. The form that holds is mechanical and takes seconds:
**grep the symbol; if every hit is in `tests/`, it is not implemented.**

## A generated block's stale-looking state is evidence about the generator, not a defect to tidy — when a checkbox, index or table looks wrong, find what writes it before editing it, because hand-fixing derived output desynchronises it from its source and destroys the signal that something upstream is unset

Chunk 23, 2026-08-05. Three chunks had landed with their `## Status` boxes
unticked in `build-plan.md`, which read exactly like bookkeeping nobody got round
to, and a commit ticked them. It was not: `views_enabled` is true, so that block
is regenerated from the `status=` tag on each change-log entry, and an entry
carrying no `status=` is release-pending **by design**. The boxes were right and
the tidy-up was wrong — a commit that edited generated output to match an
assumption, on a file whose own header says not to.

The tell was available before the edit and cost one read: **the file said so.**
`change-log.md`'s header documents the tag format and ends "Don't hand-edit them
— add/update a tagged entry here and run `prawduct-hook regen-views`." The edit
was made without reading the header of the file that generates the thing being
edited.

**The rule generalises past this one mechanism.** Anything that looks like drift
in a derived artifact — a checkbox, a rollup, a release-notes section, an index —
is a question about its generator: is the source tag missing, or is the state
genuinely release-pending? Both answers are useful and neither is "edit the
output". Run the generator and read what it says: `regen-views` reported
`4 chunk(s) flipped — unshipped [19A, 21, 22, 23]`, which is the mechanism
stating its own reasoning in one line.

Neighbouring rule, quoted by its heading rather than linked: "a guard's effective
scope is invisible in its result — when a check computes its own scope, assert
the scope as well as the finding". Both are cases where a result's meaning
depends on machinery the reader did not look at.

## Closing a gap means sweeping the artifacts that assert the gap is open — grep for the absence you just removed, not only for the thing you just added, because a document saying "there is no X" reads as current guidance and sends the next builder to rebuild the debt you just paid

Chunk 23, 2026-08-05, found by the Critic. The chunk gave the browser client its
first executed coverage, and four artifacts were updated to describe the new
harness — `CLAUDE.md`, `boundary-patterns.md`, `project-preferences.md` and the
recorded technology decision. A fifth was missed, and it was the one that
mattered most: `operator-verification.md` still read "The client has no test
runner — 10B decided against a Node toolchain on a Pi ... and that decision
stands — so the Python suite verifies every byte the server sends and nothing the
browser does with it", and named the three behaviours as reasoned-but-untested
that the same commit had just put under test.

**Two wrong actions followed from it, and the second is the expensive one.** The
operator would perform a manual check believing it was the only control. And a
builder starting the next chunk would read "that decision stands" as live
guidance and add the review grid's client logic with no browser coverage —
re-incurring, in the very next chunk, the debt this one was created to pay.

**The asymmetry is why it is easy to miss.** Updating the artifacts that describe
what you built is prompted by the building: you have just written the thing, so
you go and write it down. Nothing prompts you to find the documents that describe
its *previous absence*, because those documents do not mention your new work by
name — they cannot, and that is exactly what makes them unsearchable by the
obvious search. Grepping for `playwright` or `browser` found the four artifacts
that already knew; it could never have found the fifth.

**The check:** when a chunk closes a known gap, search for the gap's own
vocabulary as the artifacts phrased it — "no test runner", "not covered",
"decided against", "today it is", "if this keeps growing" — and for any artifact
that invited the trade to be reopened. An entry that says "this is worth
reopening if X" has to be revisited the moment X happens, and it is the entry
least likely to be looking back at you.
