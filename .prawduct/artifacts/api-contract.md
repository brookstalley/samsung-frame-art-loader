---
artifact: api-contract
version: 1
depends_on:
  - artifact: product-brief
  - artifact: data-model
last_validated: null
---

# API Contract

> **Status: operations decided 2026-07-19.** This artifact was deliberately
> incomplete on first authoring — the operations table was left empty because a tool
> surface is a contract external clients bind to, and guessing one into existence is
> the expensive kind of wrong. The granularity question has since been answered
> against three inputs: the operator's two production MCP servers
> (`cordyceps`, public and in wide use; `hallucinote`, private), Anthropic's
> published tool-design guidance, and the Model Context Protocol specification at
> revision `2025-11-25`. What remains open is named as open.

## Overview & Surface Type

Three surfaces, and they are not the same kind of thing:

| Surface | Consumers | Kind | Stability obligation |
|---|---|---|---|
| **MCP tool surface** | **External** — Claude Code, the in-UI agent, any MCP client | Model Context Protocol tools | **Real.** Clients bind to tool names, argument schemas, and result shapes. |
| **HTTP API** | Internal — the curation UI's direct controls | JSON over HTTP on the LAN | None. Shipped and deployed with its only consumer. |
| **curation↔display contract** | Internal — the display plane | Theme manifest: a versioned JSON document on a shared filesystem | **Bounded.** Additive changes are free; a breaking change bumps the major version, and display refuses an unrecognised major and keeps the manifest it has. |

> **Amended 2026-07-20.** This row read *"To be designed. None. Single consumer,
> deployed together."* — the blanket exemption `architecture.md` § Deployment &
> Version Skew explicitly recorded as owed an edit here, and which Critic findings
> flagged as still standing.
>
> The exemption was incompatible with the ratified availability norm:
> *deployed-together* and *survives-independently* cannot both be true without
> saying what display holds and how stale it may be. And skew is real even with
> both planes on one host — the two processes restart independently, so an upgrade
> leaves a window where new curation has written a manifest an old display is still
> reading, and a reboot mid-upgrade widens that to "until someone notices".
>
> The obligation is deliberately small rather than a full compatibility regime:
> without a version field the failure is a misparse rendering wrong art or a crash
> loop blanking the wall; with one, it is a logged refusal and yesterday's theme
> still on the wall.

### Transport: streamable HTTP, not stdio

**Decided, and effectively forced.** Claude Code runs on the operator's laptop
while the catalogue and `ART_ROOT` live on the curation host, reached over an
overlay network. stdio transport requires the client to *spawn* the server locally,
which cannot work across that boundary. So the MCP server is an ASGI application
served over streamable HTTP.

**It is mounted in the same application as the curation UI's HTTP API.** One
process, both surfaces binding the same in-memory service layer — which is what
makes the thin-binding norm below structurally easy to hold rather than a rule
someone has to remember. The alternative, a separate MCP process, would need its
own path to the catalogue and would reintroduce exactly the divergence the norm
exists to prevent. The cost accepted: the MCP surface goes down when the UI process
does. That is tolerable because both live on the curation plane, whose downtime is
already defined as invisible to the household (`product-brief.md` → Platform).

### The in-UI agent is an MCP client

**Decided 2026-07-19**, and it is the reason the surface has to be good rather than
merely present. Either way the agent must be taught a surface; MCP describes itself,
so the teaching is free. The stronger argument is scope: making the server the unit
of "an art library on a system" lets one agent manage several, which promotes
multiple libraries from an accommodate-only concern toward a design driver.

What this does **not** imply is routing the UI's own controls through MCP. Tool
results are shaped for a model to read; a UI wants typed, paginated, partial data,
and forcing it through MCP would produce either awkward results or a parallel read
path anyway. Location transparency belongs in the service layer, beneath both
surfaces.

**Only the MCP surface carries a versioning obligation.** The original
"none — internal-only" decision still holds for the other two, and re-deriving it
per surface is the point: a blanket policy would either over-engineer the internal
pair or under-protect the external one.

Built on the **official `mcp` SDK** (`mcp>=1.27`), not `3tears-mcp` — that package
would drag NATS in via `3tears-epoch`, and its RBAC-gated server has nothing to
gate in a single-principal product. See `project-state.yaml` →
`technical_decisions.technology`.

## Operations

### The framing that was wrong

This artifact previously posed the choice as intention-shaped tools versus
fine-grained primitives, and claimed the coarse option made the Dalí request "one
call". **It cannot be one call, for two independent reasons already committed
elsewhere.** Phase 2 of discovery takes minutes, so a blocking call is the wrong
shape regardless of granularity. And review requires a human, so — as
`product-brief.md` says plainly — an agent cannot literally finish the request; it
stages works and the wall changes when the curator looks. The most a coarse tool
can do is *start* something. That is a much smaller claim than the one this
artifact made, and it dissolves most of the supposed trade.

### The surface

**Five tools, each a noun, each dispatching on a required `action` string.** This
follows the pattern proven in the operator's two production servers: cordyceps
exposes 7 tools with 5–30 actions each; hallucinote exposes 13. Both sit inside the
1–15 range Anthropic's MCP-authoring guidance identifies as the point where one
tool per action stops paying and consolidation starts.

| Tool | Actions | Notes |
|---|---|---|
| `art_discovery` | `estimate`, `start`, `status`, `approve`, `decline`, `cancel`, `resolve_images`, `list_runs`, `spend`, `help` | **The only tool that spends money.** |
| `art_review` | `list_works`, `get_work`, `list_images`, `set_canonical`, `set_verdict`, `reject_image`, `help` | Returns thumbnails; see Inputs & Outputs. Never spends. |
| `art_catalogue` | `list`, `get`, `archive`, `restore`, `retry_acquisition`, `set_mat_color`, `regenerate`, `help` | |
| `art_theme` | `list`, `get`, `create`, `update`, `delete`, `add`, `remove`, `reorder`, `activate`, `help` | `activate` changes the wall immediately. |
| `art_display` | `status`, `sync`, `show_now`, `next`, `help` | Every action goes through the theme manifest — see below. |

### What the review surface must show about an image

`list_images` and `get_work` carry two derived values per candidate image, both
computed by the service layer rather than stored (`data-model.md` → Original):

- **`display_fit`** — `native`, `matted_small`, or `below_floor`, computed from the
  image's pixel dimensions against the configured panel geometry and mat width.
- **The rendered physical size**, in inches, on the configured panel — *"would show
  at 8.6 inches"*. This is the number a curator can actually judge. **A thumbnail
  cannot convey resolution**: a 900 px image and a 6000 px image look identical in a
  review grid, which is exactly why the review gate ("a human saw the artwork")
  does not by itself protect against hanging a postage stamp.

A `below_floor` image is **shown, labelled, and selectable** — never auto-selected
by phase 2, and never hidden. The curator may take it anyway; that judgement is the
product.

**`rights_status` is returned alongside**, as a provenance and source-quality
signal. It gates nothing (`data-model.md` constraint 13).

### How `art_display` reaches the display plane

**Corrected 2026-07-20 (Critic R-17).** This tool's actions were specified before
the manifest-only channel was ratified, and `show_now`/`next` were left with no
route to the plane that would execute them — unimplementable as written, and tool
names are frozen, so it was cheap to settle now and expensive later.

Every action resolves against the manifest. **The curation plane never sends the
display plane a command; it writes desired state, and display converges on it.**

| Action | What curation does | What display does |
|---|---|---|
| `status` | Reads the display plane's heartbeat file | Nothing — it wrote the heartbeat already |
| `sync` | Rebuilds and rewrites the manifest from the active theme | Picks up the new manifest on its next poll and reconciles |
| `show_now(work_id)` | Increments the manifest's directive `sequence` and sets `pinned_work_id` | Jumps to that work, then continues rotating from there |
| `next` | Increments the directive `sequence` with no pin | Steps to the next work in the list |

Two consequences worth stating because they surprise:

- **These actions are not synchronous confirmations.** They return "the directive
  is written", not "the wall changed". Actual latency is bounded by display's poll
  interval (~1 s). A result claiming the TV has changed would be asserting
  something curation cannot observe — the same false-success pattern this contract
  already refuses elsewhere.
- **If the display plane is down, the directives queue harmlessly.** The manifest
  holds the latest desired state; display converges whenever it comes back. There
  is no command to be lost, because there is no command — only state.

### Rejecting an image does not re-search — that is a separate, paid call

`art_review(action='reject_image')` marks the instance rejected and moves the work
to `awaiting_better_image`. It does **not** go looking for a replacement.
`art_discovery(action='resolve_images', work_ids=[...])` does, and it is the paid
operation.

**This split exists to keep the money boundary intact.** Letting `reject_image`
trigger a search inline would put a cost inside `art_review` and break the premise
the whole gating design rests on — that exactly one tool spends. It also means a
curator can reject several images while reviewing and re-resolve them in one batch,
rather than firing a search per click.

**`resolve_images` returns a run handle, exactly like `start` (decided 2026-07-20).**
It creates a `DiscoveryRun` with `kind='resolve'` and `parent_run_id` set to the run
that originally proposed the works, and returns immediately with its id. It is a
paid operation that takes minutes; it previously created no row, which left the one
tool that spends money without a handle to poll, a `cancel`, a cost of its own, or
any guard against the same ids being submitted twice concurrently. `status`,
`cancel`, and `spend` accept a resolve run id with no special-casing.

**It refuses work ids already covered by an in-flight resolve run**, naming them in
the error rather than silently deduplicating — a curator who double-submitted should
find out, not be quietly corrected. Coverage is recorded in `ResolveRunWork`
(`data-model.md`), which is also what lets `status` on a resolve run report *which*
works it is resolving rather than only that it is running.

Spend from a re-search attributes to the **resolve run**, which is what having a row
is for, and rolls up to the originating run through `parent_run_id` so "what did
asking for Dalí cost?" stays answerable. **This supersedes the earlier rule that
re-search spend attributed directly to the originating run** — that rule existed
only because there was no other row to attribute it to. The originating run still
never reopens: a `completed` run stays completed. See `data-model.md` → SpendRecord.

### `set_verdict` cannot set `awaiting_better_image`

Rejecting an *instance* is `reject_image`'s job, and it is the only way into
`awaiting_better_image`. `set_verdict` accepts `accepted` and `rejected` only, and
returns an error naming `reject_image` when asked for `awaiting_better_image`.

**Both paths used to reach that state and only `reject_image` set `rejected_at`** —
so a work sent there via `set_verdict` had no suppressed instance, and the re-search
could legitimately hand back the image the curator had just turned down. That is the
suppression failure **Q11** exists to prevent, reappearing on the instance scope
instead of the work scope. One entry point makes it impossible rather than
defended against, and it matches the boundary the tools already draw: `set_verdict`
is work-scoped, and "this scan is not good enough" is a judgement about an instance.

### Why not split reads from writes

Anthropic's connector Directory review criteria require read and write tools to be
separate, and would reject a tool that multiplexes both. **That rule is not binding
here** — this product will never be listed — and the operator's own servers
demonstrably do multiplex (`gh_canvas` carries `add`/`delete`/`move` alongside
`list`/`info`).

The mechanism behind the rule is real, though: a multiplexed tool cannot honestly
declare `readOnlyHint: true`, and Claude Code auto-approves read-only tools while
prompting on everything else. For a single operator that cost is retired by
allowlisting the server once.

What remains worth isolating is not reads-versus-writes but **the operation that
spends money**, and that falls on a tool boundary anyway: `art_discovery` is the
only tool with a cost, so it can be gated independently without splitting anything
else. Note the consequence — because MCP annotations are per *tool*, not per
action, an operation needing its own confirmation must be its own tool. That is the
real constraint on how far consolidation can go.

### Argument shape

**`action` first and required; every other parameter flat and optional.** Not a
discriminated union — the union of all actions' parameters is *flattened* onto one
schema, with per-action validation at dispatch. hallucinote's rationale for this is
worth carrying: a nested `params: {...}` envelope is agent-hostile, and a wire-level
discriminated union forces callers to widen to `str` anyway because the valid set is
runtime data.

**The tool definitions are generated from a registry, not hand-maintained.** One
record per action carries its description, parameters, example, and tips; the wire
schema, the argument validation, the `help` output, and the error messages are all
derived from it. This is what makes them provably consistent instead of consistent
by discipline, and it is the single most transferable thing from the operator's
existing servers.

### Help is an action, not a tool

**Every tool answers `action='help'`**, returning its action menu with per-action
required/optional parameters, a worked example, and tips. It must work with no other
arguments and without touching the catalogue.

Two reasons this beats a dedicated `help` tool: it keeps the tool count down, and —
because help is generated from the same registry as the schema — help cannot drift
from the contract. There is also a hard client constraint behind it: **Claude Code
truncates tool descriptions and server instructions at 2KB each**, so the description
cannot carry the detail. Put the action menu in the description and the depth behind
`help`.

## Inputs & Outputs

**Provenance binds.** Tool results must carry enough for the curator to reconstruct
what an agent did. A `DiscoveryRun` records `initiated_by`, every candidate work
carries its `rationale`, and every candidate image carries its
`selection_rationale` — so "why did forty Dalí candidates appear, and why this scan"
is answerable after the fact, not just during.

### Images are returned inline, and this departs from the operator's other servers

**Decided 2026-07-19.** `art_review` returns candidate thumbnails as image content
blocks.

This is a deliberate departure worth recording, because both of the operator's
production MCP servers do the opposite: cordyceps writes captures to disk and
returns `{filePath, width, height, hint: "Use Read tool to view image"}`;
hallucinote returns absolute paths to its audio captures and reports. Neither ever
emits an image block.

**That pattern does not transfer, because both of those servers are local.**
cordyceps binds `127.0.0.1`; hallucinote is stdio. A returned path works because
client and server share a filesystem. Ours do not — the curation host is reached
over an overlay network, so a path it returns is meaningless on the client. Worse,
it fails by returning a plausible-looking result the client cannot act on.

This requirement is not a preference. `product-brief.md` makes "a curator never
accepts a work without having seen its image" a success criterion, and the review
gate's whole justification is content appropriateness — which only a person looking
at the picture can judge.

### Token budget

Claude Code caps MCP tool output at **25,000 tokens** and warns above 10,000. A
server may raise its own ceiling via `_meta["anthropic/maxResultSizeChars"]` up to
500,000 characters, but **that applies to text only — images do not benefit.**

Image cost is approximately `(width × height) / 750` tokens:

| Thumbnail | Per image | × 40 works |
|---|---|---|
| 256×256 | ~87 | ~3,500 |
| 400×300 | ~160 | ~6,400 |
| 512×512 | ~350 | ~14,000 |

**Thumbnails are capped at 400px on the long edge**, which keeps a full 40-work
batch comfortably inside the budget. That resolution is sufficient for the judgement
the gate exists to make; it is *not* sufficient for judging mat colour, which
happens after acceptance on a real screen.

Truncation is always explicit. A result that omits rows says so and says how many —
never a silent cut.

### Long-running operations: start, then poll

**Discovery must not block.** `art_discovery(action='start')` returns a run handle
immediately; `action='status'` polls it.

Three client facts force this, all verified rather than assumed:

1. **MCP's own Tasks primitive is unusable here.** SEP-1686 landed in spec revision
   `2025-11-25` marked experimental, and Claude Code closed the request to support
   it as *not planned*. Declaring `execution.taskSupport: "required"` would break
   Claude Code outright. `"optional"` is safe and forward-looking; `"required"` is
   not.
2. **Claude Code aborts a call that goes silent.** No response and no progress
   notification for 5 minutes on HTTP transport ends the call.
3. **A call still running after 2 minutes is auto-backgrounded** by Claude Code
   (≥ 2.1.212). Start-and-poll is correct either way, and does not depend on that
   version.

hallucinote reaches the same conclusion independently and supplies a calibrated
number: its status action long-polls for 45s, sized to sit under a 60s tool timeout.

> **Amended 2026-07-20 — a "must" withdrawn.** Point 2 previously continued: *"So
> the server **must** emit `notifications/progress` during phase 2 — this is what
> keeps the connection alive, not a nicety."* That is withdrawn on two findings from
> reading the SDK.
>
> **It can silently do nothing.** `Context.report_progress` no-ops when the client
> did not send a `progressToken` (`mcp/server/fastmcp/server.py:1170-1173`). A
> keep-alive that depends on client behaviour we do not control, and fails
> invisibly, cannot be the thing a design rests on.
>
> **It is unnecessary.** The run handle returns immediately, so the only long call
> is the status long-poll capped at 45 s — nowhere near either threshold. Nothing
> is ever idle long enough to need keeping alive. The start-and-poll shape was
> already doing the whole job.
>
> Corroboration: neither of the operator's production servers emits progress
> notifications at all. hallucinote backgrounds work behind a blocking `status`
> action; cordyceps is stateless JSON with no SSE stream, so mid-call
> server-to-client notifications are structurally impossible there. Both reached
> polling independently.
>
> Progress notifications remain **permitted as a UX nicety** where a client does
> send a token. They are not a correctness dependency, and nothing may be designed
> as though they were.

### Partial success is the normal case

A run that resolves 34 of 40 works succeeded partially. Bulk actions return a
per-item breakdown rather than a single verdict — the shape cordyceps uses for its
bulk operations: `{success: failed == 0, changedCount, failedCount, results[],
error}`, where `results[]` carries a per-id outcome. Unresolvable items are
*reported as failures*, never silently skipped.

## Error Model

**Envelope: decided 2026-07-19.** Errors are returned as **tool results with
`isError: true`**, never as JSON-RPC protocol errors — with one exception: an
unknown *tool* stays a protocol error, because the client addressed something that
does not exist. Everything past that point concerns a known tool, and a known tool's
failure is information the model should be able to act on. The MCP specification
supports this directly: execution errors are meant to "contain actionable feedback
that language models can use to self-correct and retry", and clients SHOULD feed
them back to the model.

`isError` is **derived from the payload**, not set by hand at each call site — a
result is an error iff its `success` field is boolean `false`. Both of the
operator's servers do this, and the reason is that a hand-set flag drifts from the
body it is supposed to describe.

### Errors teach

Every error carries four things: **what was wrong**, the **enumerated valid set**,
a **correct example**, and a pointer to `action='help'`. Worked shape:

```json
{ "success": false,
  "error": "Unknown action: 'aprove'",
  "valid_actions": ["list_works", "get_work", "set_verdict", "..."],
  "example": "art_review(action='set_verdict', work_id='...', verdict='accepted')",
  "hint": "Use art_review(action='help') to see all actions with their parameters." }
```

**No fuzzy nearest-match suggestions.** Neither production server implements "did
you mean" — there is no Levenshtein or close-match logic in either. The substitute
is always to enumerate the full valid set inline, which is more useful to a model
than a single guess and cannot mislead.

**Log the full exception operator-side; ship the message only to the client.**
Stack traces are for the journal, not the tool result.

**These constraints were already decided and continue to bind:**

1. **`halted_by_budget` is a distinguishable outcome, not a generic failure.** An
   agent must be able to tell "you are out of money" from "the fetch failed" —
   the first means stop, the second means retry. Collapsing them makes a spend cap
   that fails closed behave, to an agent, like a transient error worth retrying.
2. **Partial success must be expressible.** Partial dezoomify tile fetches are
   normal, and a run that acquires 30 of 40 works succeeded partially. An
   ok/fail binary would force one of two lies.
3. **Never report success on a failed operation.** This is the product's existing
   defect pattern — `upload_file` catches every exception, logs, and returns
   having recorded a null content id while the retry loop sets `success = True`.
   The contract must make that shape impossible rather than merely discouraged.
4. **Errors are typed and specific.** A broad catch at a tool boundary needs
   `# prawduct:allow prawduct/broad-except -- reason`.

## Versioning

**Decided 2026-07-19: no version negotiation. Tool names are a frozen contract;
actions are the unit of evolution; changes are additive-only.**

This decision was **reopened, not silently amended**. The original — no versioning,
internal-only — carried the revisit trigger *"any consumer not deployed from this
repo"*, and the MCP requirement fired it the same day it was written. Preserving
that history matters: the trigger doing its job is the evidence the mechanism works.

### Why no scheme

**The specification has nothing to offer here.** Tool semantic versioning (SEP-1575,
proposed 2025-09-29) remains a dormant proposal, sponsored by nobody and adopted
into no spec revision. There is no standard for versioned tools to conform to, so
"adopt the standard" is not an available choice.

What the protocol *does* provide is `notifications/tools/list_changed`, which Claude
Code honours by refreshing its tool list automatically. Combined with the fact that
every client here is the operator's own, that makes evolution genuinely cheap — a
breaking change is recoverable in a way a public API's would not be.

### The rules

| Change | Verdict |
|---|---|
| Add a tool | Additive. Safe. |
| Add an action to a tool | Additive. Safe. **This is the intended growth path.** |
| Add an optional parameter | Additive. Safe. |
| Add a **required** parameter | Breaking. Add it optional with a default instead. |
| Add a field to a result | Additive — readers tolerate unknown keys, the discipline `3tears` already uses for its `--json` envelopes. |
| Remove or rename a **tool** | **Not permitted.** |
| Remove or rename an **action** | Breaking. Announce, then retire with the retirement noted inline at the old name's site. |
| Change a tool or action **description** | **Treat as breaking.** |

**Tool names never change.** hallucinote states the rule as *"stable surface — never
rename, only alias"* and enforces it at import time; cordyceps pins its seven tool
names in an explicit test whose comment reads *"a regression here silently renames
the entire MCP tool surface for every client."* Both learned it the same way:
cordyceps' one consolidation to unified tools required follow-up sweeps through
prompts, guides, and a stale tool count in its own documentation.

**That last row is the non-obvious one.** A description change alters tool-selection
probability even when the JSON Schema is untouched, so a "harmless wording fix" can
change which tool a model reaches for. This is sound reasoning rather than a
measured finding, and it is flagged as such — but it has a concrete consequence:
descriptions belong under the same review and evaluation discipline as schemas, not
treated as prose.

## Deprecation & Compatibility

**Announce, retire, and annotate — no compatibility shims.**

The asymmetry that licenses this: these MCP clients are **not** anonymous third
parties. They are the operator's own Claude Code sessions and the in-UI agent. A
breaking change means telling one person and updating one config, not a migration
window for strangers.

- **Retired actions are annotated inline** at the site that replaced them, naming
  what went and why. hallucinote does exactly this, carrying a ticket id in the
  comment and restating it in the tool description.
- **No compatibility shims for wire-shape breaks.** hallucinote's precedent is a
  strict version handshake with a documented per-call bypass, on the reasoning that
  the cost of a false positive (re-run the install) is tiny against a false negative
  (silent "unknown action" errors). That trade holds here for the same reason.
- **The 12-month deprecation window the MCP project uses for its own features is a
  precedent, not a rule that binds servers.** It is disproportionate for one
  operator and is not adopted.

## Surface Inventory & Stability Tiers

The MCP surface is the only one needing tiers; the HTTP API and the curation↔display
contract ship with their only consumers.

| Element | Tier | Meaning |
|---|---|---|
| Tool names (the five above) | **Frozen** | Never renamed or removed. Pinned by test. |
| `action` values | **Stable** | Additive; retirement is announced and annotated. |
| Required parameters | **Stable** | New ones must be optional with a default. |
| Optional parameters | **Additive** | May be added freely. |
| Result fields | **Additive** | Readers tolerate unknown keys. |
| Tool and action descriptions | **Stable** | Changing one is a behavioural change; see Versioning. |

**Annotations are mandatory on every tool**, because their defaults are worst-case:
omit them and MCP assumes `destructiveHint: true` and `openWorldHint: true`, which
costs the operator a confirmation prompt on every call. Each tool declares `title`
plus honest `readOnlyHint` / `destructiveHint`.

## Conventions

**One binding norm already governs this artifact** — `architecture.md` § Direction,
ratified by the owner 2026-07-20, with its enforcement row in
`project-preferences.md`:

> **Operation logic lives ONLY in the service layer. MCP tools and HTTP handlers
> are thin bindings and contain no business logic.**

This is what makes the chosen architecture safe. UI controls call HTTP, agents
call MCP — two entry points, one implementation. A handler that validates,
orders, or decides is a violation; a handler that unpacks arguments, calls one
service method, and formats the result is the norm.

Without it, "MCP at parity with the web UI" degrades into two implementations of
every operation that diverge invisibly — an agent and a click producing different
results, with no test that would catch it.

**The registry gives that norm a structural home.** hallucinote separates
declarative action records (schema, description, example, tips — no logic) from
handlers (the work). That split *is* this norm, expressed as a directory boundary
rather than a rule someone has to remember: an action record that contains a
decision is visibly in the wrong file. Adopting the same shape here means the norm
is enforced by where code lives, not only by review.

**Consolidation is vertical, never horizontal.** A tool may do several internal
steps to serve one operator intention. What it may not become is a generic
multiplexer — an `art_request(method=..., path=...)` passthrough is the
anti-pattern Anthropic's Directory review rejects outright, and it would put routing
logic in the binding, which the norm above forbids.

## Security

**Trust model:** the network layer carries it. The MCP server is LAN-only, reached
remotely via an overlay network (Tailscale/VPN). No authentication, no TLS
termination, no rate limiting in the application — proportionate for a
single-principal household tool, and recorded as a decision in
`project-state.yaml` → `technical_decisions.integrations`.

**`initiated_by` is provenance, not authorisation.** Every surface has identical
authority. Agent-initiated runs queue candidates for the same reason UI-initiated
runs do — the review gate is universal, not a restriction on agents. Branching
authority on the caller would reintroduce the parity split MCP exists to prevent.

**The real exposure is prompt injection, and it is bounded — but less tightly than
this artifact previously claimed.**

Discovery reads arbitrary gallery sites, prize pages, and artist portfolios —
attacker-influencable text — and feeds it to an agent whose tools mutate the
catalogue and spend money.

> **A bound was voided on 2026-07-19 and is corrected here rather than quietly
> dropped.** This section used to open with *"Agents cannot auto-accept. Every
> addition stops at curator review."* That was true while the review gate was
> withheld from the MCP surface. It is no longer: `art_review(action='set_verdict')`
> exists, decided the same day, because the gate's real content is that a human
> *saw the artwork* — not that a surface was denied a tool. An injected
> instruction now has a verdict tool within reach.
>
> Leaving the old sentence in place would have been the worse outcome: a future
> reader would have taken a stale guarantee as current and built on it.

What actually bounds the exposure now, in descending order of strength:

1. **The spend cap fails closed.** A poisoned page cannot run up an unbounded bill.
   This bound is unchanged and is the strongest one.
2. **Tool authority stays narrow** — no filesystem access, no shell, no arbitrary
   fetch. The blast radius stays inside the catalogue.
3. **Acceptance is visible and fully reversible.** It changes the wall, which is the
   most conspicuous surface the product has; archive restores.
4. **The curator is present in the session** that issued the request, and the
   accepted set is enumerated in the transcript.

Bounds 3 and 4 are materially weaker than "cannot", and are stated as such. Bound 4
in particular is a property of how the operator works, not something the system
enforces.

**One design consequence follows, DECIDED 2026-07-20: `set_verdict` requires
explicit work ids and refuses a bare "accept everything pending."**

It does not stop a determined injection — an agent can enumerate first — but that
was never the bar. The bar is that **the accepted set appears in the transcript
where the curator sees it.** Given the review gate's durable justification is
content appropriateness rather than spend, the ids being visible at the moment of
acceptance *is* the gate doing its job; an `accept_all` that leaves no record of
what "all" was would hollow it out while looking identical in the happy path.

Accepted cost: friction on the legitimate "accept them all" path, which is the
common case after a good run. The curation UI can still offer a select-all
affordance — it simply sends the ids, which is what a UI naturally has anyway.

Worth stating plainly: the realistic worst case is a poisoned page steering
candidate selection, burning budget, or getting an unwanted image onto the wall
until someone looks. Annoying and visible, not a breach. There is no PII, no
multi-tenancy, and no payment surface.

## Conditional Patterns

**Pagination and filtering.** Listing actions take a `limit` with a sane default and
a filter appropriate to the entity. A truncated result says so explicitly and gives
the total — `"showing 20 of 84; narrow the filter"` — never a silent cut. Both of
the operator's servers enforce this and cordyceps' own comment names the reason:
items that cannot be handled are *reported as failures, not silently skipped*.

**Bulk operations** return the per-item shape described under Inputs & Outputs.

**Summary then detail.** Listing actions return the fields needed to decide;
`get_*` returns the full record. This is the cheapest lever on token cost and it is
why `art_review(action='list_works')` returns one thumbnail per work rather than
every instance found.

## Open Questions

Carried in `project-state.yaml` → `open_questions`; restated here so this artifact
is self-contained:

- Whether the MCP surface should expose *resources* in addition to tools. The
  specification's split is about *control* — who decides when something enters
  context — not about mutability, and it never says read-only operations must be
  resources. Anthropic's own guidance says a tool is right when the result depends
  on parameters the model chooses, which covers every read here. A stable browsable
  artifact (the active theme, display state) may still earn a resource later.

## Validation

The tool surface is **measured, not argued about**. Anthropic's published method is
to write verifiable operator prompts, run them against the surface, and compare
accuracy, tool-call count, token consumption, and error rate — and it explicitly
names workflow-versus-atomic granularity and namespacing as things to *test* rather
than deduce.

This matters more here than usual, because the repo currently has **no test suite at
all** (recorded as a known departure in `project-preferences.md`, and blocking for
medium+ work). An MCP evaluation harness is a strong candidate for the first testing
investment: it is simultaneously a contract test for the tool surface — the thing
that catches the description-drift problem the Versioning section flags — and the
only way to know whether this consolidation is right *for this product* rather than
in general.

Both production servers already do the narrower version of this. cordyceps pins its
tool names in a test; hallucinote boots a real server and asserts `list_tools()`
output against its registry, including that prose and code cannot drift — it tests
that the tool count quoted in its README matches the registry.
