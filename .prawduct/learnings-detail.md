# Learnings — detail

Evidence and worked instances for the rules in `learnings.md`. Headings match that
file's exactly, so a rule and its evidence stay findable from either side: the index
carries the rule, this carries what happened.

Entries older than 2026-07-31 still keep their evidence inline in `learnings.md`.
That is the shape the record linter asks them to leave, and moving them is its own
piece of work rather than a side effect of adding a rule — tracked as issue #26.

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
