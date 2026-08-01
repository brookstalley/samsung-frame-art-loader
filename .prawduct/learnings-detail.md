# Learnings — detail

Evidence and worked instances for the rules in `learnings.md`. Headings match that
file's exactly, so a rule and its evidence stay findable from either side: the index
carries the rule, this carries what happened.

Entries older than 2026-07-31 still keep their evidence inline in `learnings.md`.
That is the shape the record linter asks them to leave, and moving them is its own
piece of work rather than a side effect of adding a rule — tracked as issue #26.

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
