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
