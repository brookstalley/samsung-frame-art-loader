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
