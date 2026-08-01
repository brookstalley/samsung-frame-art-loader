---
artifact: security-model
version: 1
depends_on:
  - artifact: product-brief
  - artifact: data-model
  - artifact: api-contract
last_validated: null
---

# Security Model

One principal, one household, no PII, no payment surface, no multi-tenancy. Most
of a conventional security model does not apply here, and generating it anyway
would be template worship. What this document covers is the four things that are
genuinely live:

1. **Credentials**, because the repository is public and one is already committed.
2. **Prompt injection**, because discovery feeds attacker-influencable web text to
   an agent holding mutating, money-spending tools.
3. **Content appropriateness**, because the household never opted in to what
   appears on the wall.
4. **The trust boundary**, because it is carried entirely by the network layer,
   which is a real decision with real consequences if it ever changes.

## Trust Boundary

**The network layer carries the entire trust boundary.** Both surfaces — the MCP
endpoint and the UI's HTTP API — are LAN-only, reached remotely over an overlay
network (Tailscale/VPN). The application performs no authentication, no
authorisation, no TLS termination, and no rate limiting.

This is a recorded decision, not an omission
(`technical_decisions.integrations`, 2026-07-19). For a single-principal household
tool it is the proportionate answer, and it is what keeps this document short.

**What it means concretely:** anyone who is on the overlay network is the curator,
with full authority over every operation. There is no lesser role, no read-only
mode, and no audit distinction between principals because there is only one.

**The consequence that must not be forgotten:** the day this surface becomes
reachable from the public internet, *every* control in this document is void and
the model must be rebuilt from scratch — authentication, authorisation, rate
limiting, TLS, and abuse prevention all become real requirements simultaneously.
That is not a gradual degradation; it is a cliff. Any change that exposes the
curation plane publicly is a structural characteristic flip and triggers the full
re-derivation protocol, not a patch.

**`initiated_by` is provenance, not authorisation.** Every surface has identical
authority. An agent-initiated run and a UI-initiated run are subject to the same
gates, because branching authority on the caller would reintroduce exactly the
parity split MCP exists to prevent.

## Credentials and Secrets

### Inventory

| Secret | Held by | Exposure if leaked |
|---|---|---|
| OpenRouter API key | curation plane | **Real money.** Bounded by the per-key credit limit, which is the same control that bounds a runaway agent |
| Samsung TV pairing token | display plane | LAN-scoped. Lets a LAN-present attacker drive the TV |
| Museum API keys, if any | curation plane | Negligible; the ARTIC API is free and public |

The display plane holds no credential except the TV pairing token, and the
curation plane holds no device credentials. That falls out of the topology rather
than being separately enforced.

### The repository is public

`brookstalley/samsung-frame-art-loader` is a **public** GitHub repository. This is
the single most important fact in this document, because it converts "don't commit
secrets" from hygiene into a hard requirement with an audience.

**A secret must never appear in source, in a committed config file, in a test
fixture, or in a log line that could be pasted into an issue.** Deployment values
already have a Critic-enforced norm keeping them out of source
(`project-preferences.md`); secrets are the same rule with a worse failure mode.

### `token_file` was a leak, and it is closed — 2026-07-27

**Status: remediated.** The Samsung TV pairing token had been committed since
`e825276`. It was untracked and gitignored in `ba007cd` (issue #4, closed), and
the operator confirmed **the leaked token had already expired**, so the re-pair
that rotation would normally require was not needed. Both halves matter: untracking
alone would not have closed it.

**The residue is honest and permanent.** The expired token is still in git history,
which is public and cloned. That is not fixable by any future commit and does not
need to be: an expired LAN-scoped token authenticates nothing.

**The rule this leaves behind, which still binds.** The remediation for a leaked
credential is *rotation*, not deletion — the sequence below is the one to follow
if a **live** token is ever committed again. It is kept because the reasoning is
what makes the next incident cheap, not because this incident is open.

**Honest severity: low, and deliberately not inflated.** The token is LAN-scoped
— an attacker needs to already be on the household network to use it, and an
attacker already on the household LAN can reach the TV's pairing flow anyway. The
realistic worst case was someone changing what is on a television. While it was
open it was recorded as unfixed rather than quietly downgraded, because "we decided
it was fine" and "we forgot" look identical in six months — and it is now recorded
as closed with the evidence, for the same reason.

**Order of operations — CORRECTED 2026-07-20 (Critic R-1). Untrack first, then
rotate.** This artifact previously prescribed the reverse, and that order creates a
*second* leak: rotating while the file is still tracked puts the freshly-issued
token into a tracked file, where the next `git add -A` commits it. This repository
is developed with frequent `git add -A`, so that window is not theoretical.

The old order was argued from *perception* — that untracking first "creates the
impression it has been dealt with". That concern is real but is answered by honest
prose, which this section already carries. It is not worth a second exposure.

1. **`git rm --cached token_file`, add it to `.gitignore`, commit.** Costs nothing
   in security terms — the old token is already public in history — and guarantees
   the replacement is never tracked. *(Done 2026-07-27.)*
2. **Re-pair against the TV** (physical access required). The new token is written
   to an untracked path and never enters git. *(Not needed for this incident: the
   leaked token was confirmed already expired. Required for any live one.)*

> **The operational hazard this note described is gone (2026-07-27), and the
> remediation sequence it prescribed must not be followed.** It read: `token_file`
> is read at runtime by relative path (`tvart.py`), so because deployment is
> `git pull`, the commit that untracks it **deletes it on the Pi** — meaning untrack
> and re-pair had to be done in one sitting, with hardware access.
>
> That coupling was removed by the config hoist: the token now resolves under
> `ART_ROOT` (`config.tv_token_file`, passed explicitly at both call sites in
> `tvart.py`), which is outside the checkout. Untracking it therefore does not
> delete it on the Pi, and the two steps are independent. **An operator following
> the old sequence would be scheduling hardware access for a problem that no longer
> exists** — which is why this is corrected here rather than quietly deleted.
>
> The relative-path load was itself an instance of the hardcoded-deployment-value
> departure recorded in `project-preferences.md`. That departure is closed.

**What this does not fix:** the token remains in git history, which is public and
cloned. Only rotation invalidates it. Untracking is hygiene for the *next* token,
never remediation for this one.

## Prompt Injection

This is the product's most interesting exposure and the one most easily
overstated in either direction.

**The mechanism.** Discovery reads arbitrary gallery sites, prize pages, artist
portfolios, and search results — text an attacker can influence — and feeds it to
an agent whose tools mutate the catalogue and spend money. There is no way to
build the product's core feature without this exposure existing.

**A guarantee was voided on 2026-07-19 and is not restored here.** This model used
to rest on *"agents cannot auto-accept; every addition stops at curator review."*
That stopped being true when `art_review(action='set_verdict')` was placed on the
MCP surface — a deliberate decision, because the review gate's real content is
that *a human saw the artwork*, not that a surface was denied a tool. An injected
instruction now has a verdict tool within reach.

What bounds the exposure now, **in descending order of strength, with the weak
ones labelled as weak**:

| # | Bound | Strength |
|---|---|---|
| 1 | **The spend cap fails closed**, enforced by OpenRouter server-side rather than by our code | **Strong.** A poisoned page cannot run up an unbounded bill, and it cannot be bypassed by a bug in our metering |
| 2 | **Tool authority is narrow** — no filesystem access, no shell, no arbitrary fetch. Blast radius stays inside the catalogue | **Strong.** Structural |
| 3 | **A per-run search cap** bounds a single runaway run, not just the month | **Moderate.** Bounds cost and loop length, not content |
| 4 | **Acceptance is visible and fully reversible** — it changes the wall, the most conspicuous surface the product has, and archive restores | **Weak as prevention.** It is detection and recovery, not prevention |
| 5 | **`set_verdict` requires explicit ids**, so the accepted set is enumerated in the transcript | **Weak.** An agent can enumerate first. It buys visibility, not refusal |
| 6 | **The curator is present** in the session that issued the request | **Weakest.** This is a property of how the operator works, not something the system enforces |

**Bounds 4–6 are materially weaker than "cannot" and are stated as such.** The
honest summary: the realistic worst case is a poisoned page steering candidate
selection, burning budget, or getting an unwanted image onto the wall until
someone looks. **Annoying and visible, not a breach.** There is no PII to exfiltrate,
no tenancy to cross, no payment surface to abuse, and no credential the agent can
reach.

**What would change this assessment.** If any of the following land, this section
must be re-derived rather than extended:

- A tool that reads or writes the filesystem outside ART_ROOT, or that fetches an
  arbitrary URL on request.
- Unattended or scheduled discovery with no curator in the session — this removes
  bounds 4 and 6 simultaneously, which are the two that depend on a human being
  around.
- Any credential becoming reachable from a tool.

## Content Appropriateness

**This is a safety concern, not a security one, and it is the one with a real
victim.** It is documented here because nothing else owns it.

Discovery searches the open web, so a mis-aimed intent or a poisoned page can
surface work that is explicit, disturbing, or simply wrong for a living room. The
consequence lands on the household persona — **people with no interface, who never
opted in, and who see whatever is on the wall.**

It fires without an adversary. An honest search returning honest results the
curator would not have chosen is the common case; prompt injection is the rare one.

**The control is the review gate, and its content is that the reviewing surface
shows the image.** Not that a surface is withheld — that framing was tried and
voided. Every surface on which a work can be accepted must display the image
first, including an agent's.

Two things follow that must not be traded away later:

- **A curator accepting on a title and a rationale alone is this control's failure
  mode, not its mitigation.** An MCP tool result that returns candidate metadata
  without the thumbnail defeats the gate while appearing to honour it. This is
  precisely why candidate thumbnails are returned inline as image content blocks.
- **The gate must not be relaxed on convenience grounds.** The spend argument for
  relaxing it is void anyway — spend is already capped by a stronger control — so
  any future proposal to skip review is trading the only protection the household
  has for a saved click.
- **What the MCP surface can and cannot enforce, stated exactly (added
  2026-07-20).** Returning the thumbnail inline guarantees that the *model* saw
  the image and that it is present in the transcript at the moment of acceptance.
  It cannot guarantee a *human* looked — rendering depends on the client, and
  looking depends on the curator. So the gate has two strengths: the web UI
  enforces "a human saw it"; MCP enforces "it was there to see". This is the same
  shape as bounds 4–6 under Prompt Injection — visibility, not refusal — and is
  recorded so the product brief's success criterion is not read as a stronger
  guarantee than the surface can carry. A backstop is filed as backlog work, not
  committed design: a "recently accepted over MCP" shelf in the curation UI, so
  everything accepted agent-side gets a guaranteed second human look on the next
  visit.

## Data Privacy

Almost nothing to say, which is itself worth recording so a future reader does not
assume it was overlooked.

- **No PII.** No accounts, no user records, no analytics, no telemetry leaving the
  device. One operator, no personal data about anyone.
- **No third-party data sharing.** Data flows outward only to OpenRouter (prompts
  and, for mat colour, artwork thumbnails) and to museum APIs (ordinary requests).
- **Artwork thumbnails go to a model provider.** Worth noting rather than hiding:
  mat-colour selection sends a downsized artwork image to OpenRouter. The images
  are public museum works, so the disclosure is nil, but the data flow is real and
  should not be discovered later as a surprise.
- **Logs must not contain secrets.** The one live rule in this section, and it has
  teeth because the repo is public and log excerpts get pasted into issues. Owned
  by `observability-strategy.md`.

## Abuse Prevention

**Not applicable, deliberately.** There is one principal on a private overlay
network. There is no registration, no untrusted user input, no shared resource to
exhaust on anyone else's behalf, and no rate limiting because there is nobody to
limit. The only "abuse" vector is an unbounded agent loop spending money, which is
handled as a cost control (`nonfunctional-requirements.md` § Direction), not as an
abuse control.

## Supply Chain

**Curation's CPython does not come from Debian.** The 2026-07-20 interpreter
decision installs a uv-managed standalone build (`uv python install 3.14`), because
Trixie ships 3.13 and `3tears` requires 3.14. The security consequence is a
patching one, not a trust one: **`apt upgrade` does not patch curation's
interpreter.** CPython fixes reach it only via `uv python upgrade`, on Astral's
republish cadence rather than Debian's security cadence. The procedure is in
`operational-spec.md` § Routine Operations; the point recorded here is that a
CPython CVE is now a two-plane action where an operator would reasonably assume one.

The display plane is unaffected — it runs the system 3.13 and is patched by `apt`
like anything else.

This is a narrowing of an already-accepted surface rather than a new one. Both
planes install PyPI wheels into venvs, which is a far larger volume of third-party
code than the interpreter, and that was accepted when the dependency set was
chosen. No dependency pinning or provenance policy has been decided — for a
single-principal LAN appliance that is a defensible position, but it is a position,
not an oversight.

## Open

- **Licence and rights enforcement — no longer open; this entry had gone stale.**
  Decided 2026-07-20: rights gate nothing. `rights_status` is a display-only
  provenance and source-quality signal, with named reopen triggers (sharing,
  export, or the catalogue becoming public). Decision and rationale live in
  `data-model.md` constraint 13; this entry is corrected rather than deleted
  because a reader of this document alone would have re-opened a settled question.
- **Whether TV auto-update can be disabled.** Not strictly security, but it is the
  vendor-controlled capability the whole product rests on, and Samsung has already
  removed art mode from some units.
