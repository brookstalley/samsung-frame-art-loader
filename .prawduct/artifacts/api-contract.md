---
artifact: api-contract
version: 1
depends_on:
  - artifact: product-brief
  - artifact: data-model
last_validated: null
---

# API Contract

> **Status: partial by design.** This artifact exists because
> `exposes_programmatic_interface` flipped to `both` on 2026-07-19 and a contract
> is now owed. What is **decided** is recorded below. What is **open** is named as
> open rather than invented — a tool surface is a contract external clients bind
> to, and guessing one into existence is the expensive kind of wrong. The
> operations table stays empty until the granularity question is answered.

## Overview & Surface Type

Three surfaces, and they are not the same kind of thing:

| Surface | Consumers | Kind | Stability obligation |
|---|---|---|---|
| **MCP tool surface** | **External** — Claude Code, the in-UI agent, any MCP client | Model Context Protocol tools | **Real.** Clients bind to tool names, argument schemas, and result shapes. |
| **HTTP API** | Internal — the curation UI's direct controls | JSON over HTTP on the LAN | None. Shipped and deployed with its only consumer. |
| **curation↔display contract** | Internal — the display plane | To be designed | None. Single consumer, deployed together. |

**Only the MCP surface carries a versioning obligation.** The original
"none — internal-only" decision still holds for the other two, and re-deriving it
per surface is the point: a blanket policy would either over-engineer the internal
pair or under-protect the external one.

Built on the **official `mcp` SDK** (`mcp>=1.27`), not `3tears-mcp` — that package
would drag NATS in via `3tears-epoch`, and its RBAC-gated server has nothing to
gate in a single-principal product. See `project-state.yaml` →
`technical_decisions.technology`.

## Operations

**Open — see `project-state.yaml` → `open_questions`.**

The requirement is parity with the web UI "or more", and the worked example is:

> "point Claude Code at the server and say *add all of Salvador Dalí's most famous
> works*"

That is an **intention**, not a CRUD call — which is the crux of the open
question. Two candidate shapes, with a real trade:

- **Intention-shaped tools** (`discover_and_add`, `switch_theme`, `review_pending`)
  — match how an agent actually thinks, fewer round trips, and the Dalí request is
  one call. But coarse tools hide their failure modes and are harder to compose
  into something the designer did not anticipate.
- **Fine-grained tools** (`create_discovery_run`, `list_candidates`,
  `set_verdict`, `add_to_theme`) — composable, honest about partial failure, and
  an agent can do things nobody designed for. But the Dalí request becomes an
  orchestration the agent has to get right, and every step is a chance to stop
  halfway.

The likely answer is both, layered — fine-grained primitives with a few
intention-shaped tools composed over them — but that is a design decision, not an
inference to make here.

## Inputs & Outputs

Deferred with the operations. One constraint already binds: **tool results must
carry enough provenance for the curator to reconstruct what an agent did.** A
`DiscoveryRun` records `initiated_by`, and every candidate carries its `rationale`
and source — so "why did forty Dalí candidates appear" is answerable after the
fact, not just during.

## Error Model

**Envelope: undecided. These constraints are decided and bind whatever is chosen:**

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

**Undecided, and reopened rather than silently amended.**

The original decision — no versioning, internal-only — was recorded on 2026-07-19
with the revisit trigger *"any consumer not deployed from this repo."* The MCP
requirement fired that trigger the same day. Recording it as **reopened** matters:
the trigger doing its job is evidence the mechanism works, and overwriting the
decision would erase that.

What needs deciding before the first tool ships:

- How a tool is **added** (additive, presumably safe) versus **removed** or
  **renamed** (breaking for every bound client).
- Whether argument schemas may gain **required** fields (breaking) or only
  optional ones (additive).
- Whether result shapes are **additive-only** — the discipline `3tears` uses for
  its `--json` envelopes, where readers tolerate unknown keys.

A plausible landing point, given one operator and a handful of clients: no version
negotiation, additive-only evolution, and removals announced rather than
versioned. But that is a decision to take deliberately, not a default to drift
into.

## Deprecation & Compatibility

Deferred with versioning. The asymmetry worth carrying into that decision: this
product's MCP clients are **not** anonymous third parties — they are the operator's
own Claude Code sessions and the in-UI agent. That makes a breaking change
recoverable in a way a public API's would not be, and argues for a lighter policy
than the external-consumer label might suggest.

## Surface Inventory & Stability Tiers

Empty until operations are defined. When populated, the MCP surface is the only
one needing tiers.

## Conventions

**One binding norm already governs this artifact** — recorded in
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

**The real exposure is prompt injection, and it is bounded.** Discovery reads
arbitrary gallery sites, prize pages, and artist portfolios — attacker-influencable
text — and feeds it to an agent whose tools mutate the catalogue and spend money.
Three things bound it:

1. **Agents cannot auto-accept.** Every addition stops at curator review.
2. **The spend cap fails closed.** A poisoned page cannot run up an unbounded bill.
3. **Tool authority stays narrow** — no filesystem access, no shell, no arbitrary
   fetch. The blast radius stays inside the catalogue.

Worth stating plainly: the realistic worst case is a poisoned page steering
candidate selection or burning budget. Annoying and visible, not a breach. There
is no PII, no multi-tenancy, and no payment surface.

## Conditional Patterns

**Not applicable** — no pagination, filtering, or bulk-operation conventions can be
specified before the operations exist. Revisit with the operations table.
