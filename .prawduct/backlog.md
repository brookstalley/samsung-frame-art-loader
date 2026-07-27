# Backlog — Samsung Frame Art Loader

> ## ⚠ SEVEN ITEMS WERE FILED HERE AFTER THIS FILE WAS FROZEN (found 2026-07-27)
>
> `project-state.yaml` records a 2026-07-19 cutover: the live backlog is **GitHub
> Issues** (`backlog_service_repo`), and this file is frozen history — "do not edit
> it, and do not read it as current state". Two later commits edited it anyway:
> `ba007cd` added **LEG-8H2P**, and `4508cd3` added **SEC-K3V9, ARC-7QN2, REL-M5X8,
> REL-2JH6, ARC-B4TD** and **TST-9WFC**. Six of those are Critic warnings the build
> plan says were "routed to the backlog" — routed, by the repo's own rule, into a
> file the tooling has been told not to read. They are invisible to
> `prawduct-hook backlog`, to `/prawduct:backlog pick`, and to the session briefing.
>
> **Two of them have no live tracking home at all and are worth reading now:**
> **REL-M5X8** — a mistyped `ART_ROOT` bootstraps a fresh, empty, healthy-looking
> catalogue and starts cleanly, which is this product's own defining failure shape;
> and **SEC-K3V9** — no Host/Origin validation on `/mcp`, whose blast radius grows
> when the only money-spending tool lands.
>
> **This note does not resolve it.** Re-filing them means creating public issues on
> the operator's repository, which is theirs to authorise; the alternative is
> unsetting `backlog_service_repo` and recording the reversal as a decision. Until
> one of those happens the seven items are recorded here, findable by this note, and
> not silently lost — which is the part that could be fixed without asking.


<!-- Structured backlog (Prawduct v1.7+). Managed with the `/backlog` skill:
     /backlog            summary + menu
     /backlog pick       what to work on next (filters + natural language)
     /backlog add        file a new item (searches for duplicates first)
     /backlog find <q>   search title/metadata/body
     /backlog list       tabular view (default: open, added within 90d)
     /backlog update ID  change metadata or status
     /backlog migrate    convert legacy unstructured items to this format

     Items move between the three sections below via `/backlog update ID status=...`.
     The framework never infers status from build plans or change logs — an agent
     or human makes the call explicitly (see backlog-system-requirements.md D4/§5).

== Item shape ==

  - **[PFX-XXXX]** One-line title
    `effort: M · impact: M · area: stop-hook · source: reflection · added: 2026-05-29 · status: open`

    Free-form body of any length — a single sentence or multi-paragraph analysis
    with file refs, fix-shape, and open questions. The author chooses what fits.

  ID format `[PFX-XXXX]`:
    PFX = 2–3 uppercase letters naming the work-space the item was filed from.
          Derive a sensible prefix from the item's area; reuse existing ones so
          related items share a prefix. Starter vocabulary (extend freely):
            STH stop-hook · CRT critic · SYN sync · LLM prompt/LLM · BKL backlog
            MIG migration · JNT janitor · MET methodology · DOC docs · TST tests
          A project may optionally declare its prefix vocabulary as
          `backlog_prefixes:` in project-state.yaml for validation — not required.
    XXXX = 4-char random alphanumeric (base36). Random IDs avoid cross-branch
           collisions; ~1.7M combinations per prefix.

  Metadata bar (one backticked, dot-separated line; required on new items):
    effort: S | M | L     S = <30 min · M = hours · L = multi-chunk
    impact: S | M | L     S = cosmetic · M = quality-of-life · L = user-felt/structural
    area:   <tag>         free-form topic tag; reuse existing tags to enable grouping
    source: builder | critic | reflection | janitor | user
    added:  YYYY-MM-DD
    status: open | promoted | shipped | dropped
  Optional, on the same line (distinct concepts — keep them straight):
    related:   PFX-XXXX, PFX-XXXX   cross-references to related items
    closes:    PFX-XXXX             this item supersedes another backlog item (item → item)
    closed-by: <chunk-id | scope/branch | tag>  what shipped this item (item → release), set on
                                    status=shipped; a handle that exists before the commit —
                                    never a bare commit SHA (dangles on --amend) or unassigned PR#
    reviewed:  YYYY-MM-DD           last-touched timestamp (auto-set on any update)
    accepted-by: @actor             soft claim "someone is on this" so others don't
                                    double-pick; pick/list exclude claimed items.
                                    Does NOT auto-expire; auto-cleared on ship/drop.
                                    Not a lock (backlog.md is eventually-consistent).
    stage: <lifecycle>              idea | research | requirements | design | ready.
                                    Where the item sits in the feature lifecycle;
                                    only `ready` is implementable. Absent/early =>
                                    pick routes to discovery/planning, not code.
    refs: <doc#section>, <doc>      links to governing artifacts (requirements /
                                    arch / design docs). Distinct from `related:`
                                    (which is item -> item).

  Legacy items (no metadata) remain valid — tools treat them as
  `effort: ? · impact: ? · area: untagged · status: open` and rank them lower.
  Run `/backlog migrate` to add structure at your own pace; nothing is forced. -->

## Open

<!-- Items available to pick up. -->

- **[LEG-8H2P]** `tvart.py` "clear the uploaded files list" clears nothing — a silent no-op
  `effort: S · impact: M · area: legacy-tv · source: builder · added: 2026-07-27 · status: open · stage: research · related: TVW-4Q7M`

  Found by ruff (F841) while landing Chunks 01/02/06, in the delete-all path:

      logging.info(f"Deleted {len(available_art)} uploaded images")
      # Clear the list of uploaded filenames
      uploaded_files = {}

  The assignment binds a **local** and is discarded at function exit. The
  persisted upload list at `config.upload_list_path` is never touched, so after
  deleting every image from the TV the on-disk record still claims they are
  uploaded. That is the same silent-failure class the product exists to correct —
  nothing errors, and the state is wrong.

  **Not fixed in place, deliberately.** The correct behaviour depends on the
  upload-list lifecycle (is the file the source of truth, or is `tv_content_id`
  on each `ArtFile`?), and the two disagree here — the loop directly above sets
  `art_file.tv_content_id = None` on every file, which may already be the real
  bookkeeping, making this line vestigial rather than broken. Guessing between
  "delete the file", "write `{}` to it", and "remove the line" would be a coin
  flip in code that gets deleted at Chunk 20.

  Resolve it wherever it is cheapest: either when the TV binding moves to
  `display-state.sqlite` (Chunk 12 supersedes this entirely — TvBinding with an
  explicit `upload_status` is designed to make exactly this defect impossible),
  or in ten minutes on the legacy path if it starts biting before then. Most
  likely outcome is `closed-by: chunk-12` with no legacy fix at all.

- **[CUI-WT3K]** Establish a real design system for the curation web UI (Claude design tooling, not ad-hoc styling)
  `effort: L · impact: L · area: curation-ui · source: user · added: 2026-07-19 · status: open · stage: design · refs: project-state.yaml#design_decisions`

  The curation web UI is the product's only human interface and has **no visual
  precedent in this repo** — the 2024 product had no visual surface at all, and
  `design_decisions.visual_direction` is currently "deferred to design". Left
  alone, that gap gets filled by ad-hoc per-page styling as screens get built,
  which is the failure this item exists to prevent.

  Do it deliberately instead: use Claude's design tooling to produce an actual
  design system — tokens (colour, type scale, spacing, radius, elevation),
  component inventory, and light/dark handling — before the UI accumulates
  one-off CSS. Then build screens against it.

  Constraints already decided in project-state that the system must satisfy:
  - **WCAG 2.1 AA baseline** — keyboard navigation, visible focus, meaningful
    labels, sufficient contrast (`design_decisions.accessibility_approach`).
  - **Chrome must never compete with the artwork.** This is an image-review tool
    whose whole job is judging colour; UI surfaces must sit at a contrast and
    saturation that recedes behind the candidate images.
  - **Colour is never the sole carrier of state.** Accept/reject in a candidate
    grid needs a non-colour indicator.
  - Single advanced operator, short leisure-time sessions — the UI must not feel
    like sysadmin work, and must not be condescending.

  Out of scope: the Frame TV art-mode output (no chrome by hard constraint) and
  the e-paper label panel (16-level greyscale, non-emissive, legibility-at-distance
  is its own design problem). Three output surfaces, only one of them gets this
  design system.

  Stage is `design`, not `ready`: `information_architecture` and
  `interaction_patterns` are both still empty in project-state, so the screens
  this system dresses aren't specified yet. Sequencing question to settle when
  picked up — whether the design system leads (tokens first, screens against it)
  or lags one screen (build the first real screen, extract the system from it).

- **[TVW-4Q7M]** Update the pinned samsungtvws fork SHA — stale upload() and unconfirmable delete_list
  `effort: M · impact: L · area: tv-api · source: user · added: 2026-07-19 · status: open · stage: design · refs: project-state.yaml#foreign_apis`

  `requirements.txt:15` pins the Samsung art API client to a fork SHA that is
  roughly two years behind master:

      samsungtvws @ git+https://github.com/NickWaterton/samsung-tv-ws-api.git@fa37fffd7a9f8e82147c0883f18bebcd67fd8ff8

  Two concrete defects verified against the pinned source on 2026-07-19 (recorded
  in `project-state.yaml` under `foreign_apis`):

  - **`upload()` buffers whole files in memory** and lacks the `timeout` and
    `CHUNK_SIZE` parameters that master has since added. This product uploads 4K
    composited images, so the reliability improvements are exactly the ones it
    needs and exactly the ones the pin excludes.
  - **async `delete_list` has no `return` statement**, so it always yields `None`
    and deletion can never be confirmed. The sync path returns a value the async
    path does not. `delete_list` is the library's *only* removal verb, so an
    unconfirmable delete is the single most consequential silent failure on the TV
    interface — another instance of the silent-failure pattern this product is
    already correcting elsewhere.

  What does **not** change: category semantics (one user-upload category,
  MY-C0002), slideshow scoping, and the old/new API version split are all
  unchanged between the pin and master, so the design decisions taken on top of
  them — host-driven rotation, no native slideshow — still hold. This is a
  reliability item, not a redesign trigger.

  Stage is `design`, not `ready`, because the target is undecided and the second
  defect may not be fixable by bumping at all:
  - Three candidate targets — the PyPI `samsungtvws` release (shipped 2026-05-28),
    the fork's current master, or continuing to pin a fork SHA. The fork exists
    for a reason (explicit LS03A/B/C/D support); confirm PyPI carries it before
    treating the release as the default.
  - **Verify at pick-up whether `delete_list`'s missing return is still present
    upstream.** If it is, bumping does not fix it and the work needs either an
    upstream PR or a local wrapper that confirms deletion independently — a
    different shape of change than a version bump.
  - The upgrade touches a live TV interface with asymmetric failure modes
    (`tvart.py`'s dual-callback registration is correct today), so it needs a
    real-hardware verification pass, not just a green install.

- **[SEC-K3V9]** DNS-rebinding protection is off on `/mcp` — no Host or Origin validation
  `effort: M · impact: L · area: security · source: critic · added: 2026-07-27 · status: open · stage: design · related: ARC-7QN2 · refs: api-contract.md#security`

  `create_app` builds `StreamableHTTPSessionManager(app=mcp_server)` with no
  `security_settings`. mcp 1.28.1 defaults `enable_dns_rebinding_protection=False`,
  so neither the `Host` nor the `Origin` header is validated on any request. The
  MCP spec requires Origin validation precisely for locally-bound HTTP servers:
  a page the operator visits can rebind to the bind address, at which point the
  request is same-origin and CORS never applies.

  Bounded today — only read actions are built and there is no auth surface — but
  `art_discovery`, the spend-incurring tool, lands on this same endpoint in
  Chunk 14. The blast radius grows before anything else about the endpoint does.

  Fix is one constructor argument:
  `TransportSecuritySettings(allowed_hosts=..., allowed_origins=...)` derived
  from `Settings`. **Couples to ARC-7QN2** — the allowed-hosts list is a function
  of what the plane binds, so decide the two together rather than in sequence.

  Stage is `design` because the alternative is legitimate: accept the exposure
  and record a dated decision in `api-contract.md § Security`, which does not
  currently consider this vector at all. Either outcome is fine; leaving the
  section silent is not.

- **[ARC-7QN2]** The loopback default contradicts the recorded transport decision
  `effort: M · impact: L · area: architecture · source: critic · added: 2026-07-27 · status: open · stage: design · related: SEC-K3V9 · refs: api-contract.md#transport, security-model.md#trust-boundary, architecture.md`

  `config.py` defaults `CURATION_HOST` to `127.0.0.1`. But `api-contract.md
  § Transport` chose streamable HTTP over stdio *because* the client (Claude Code
  on the operator's laptop) reaches the curation host over an overlay network —
  and `security-model.md § Trust Boundary` and `architecture.md:204` both repeat
  that reasoning.

  A loopback bind answers on neither the LAN nor the tailnet address. So a fresh
  checkout, followed exactly as documented, yields a plane that no MCP client can
  reach. The documentation and the default disagree, and the default wins
  silently.

  Two ways to close it, and the choice is the work:
  - Bind the overlay interface by default and record the exposure decision, or
  - Record the missing piece — a `tailscale serve` style proxy fronting loopback —
    in `operational-spec.md`, and fix `.env.example`'s reasoning, which currently
    reads as a flat contradiction of the security model.

  Whichever is chosen sets the `allowed_hosts` list SEC-K3V9 needs, so settle
  them in one pass.

- **[REL-M5X8]** A mistyped `ART_ROOT` self-heals into an empty, healthy-looking install
  `effort: S · impact: M · area: reliability · source: critic · added: 2026-07-27 · status: open · stage: design`

  `__main__.main()` calls `settings.art_root.mkdir(parents=True, exist_ok=True)`
  and then opens the catalogue, and `SqliteCatalogue.__init__` runs
  `CREATE TABLE IF NOT EXISTS`. Both steps are individually reasonable; composed,
  they mean a **typo in `ART_ROOT` creates a fresh directory, creates a fresh
  empty catalogue, and starts cleanly**. The operator gets a working plane with
  an empty collection instead of an error.

  This lands squarely on the product's recorded "failure is silent by
  construction" characteristic — the thing this product exists to correct.

  Stage is `design` because the fix is a product-behaviour decision, not a
  mechanical change: does first run bootstrap implicitly (and if so, how does it
  distinguish itself from a typo — a marker file, an explicit `init` verb, a
  non-empty-directory check), or does the plane refuse to start against a
  directory it did not previously know about?

- **[REL-2JH6]** The MCP session table is unbounded — sessions never expire
  `effort: S · impact: M · area: reliability · source: critic · added: 2026-07-27 · status: open · stage: ready`

  `StreamableHTTPSessionManager` is constructed with no `session_idle_timeout`,
  so sessions never expire. Each one leaks an instance plus a live task for the
  lifetime of the process.

  This is an always-on plane running under a `MemoryMax` cap, so the leak has a
  hard ceiling it will eventually reach — the failure mode is the unit getting
  OOM-killed, not gradual slowdown. Fix is to pass an idle timeout; choosing the
  value is the only judgement call.

- **[ARC-B4TD]** The MCP layer imports the persistence package directly
  `effort: M · impact: M · area: architecture · source: critic · added: 2026-07-27 · status: open · stage: design · refs: boundary-patterns.md`

  Domain records (`Artist`, `Artwork`) and the `ArtworkStatus` wire enum are
  homed in `curation.persistence.catalogue`. As a result `mcp/bindings.py` and
  `mcp/tools.py` both import the persistence package — bindings to render
  results, tools to build the status `choices`.

  The recorded boundary is that persistence is reached only through the service
  layer. This is import-level coupling rather than an actual data path (no
  binding calls a store), so nothing is broken today; but it puts the storage
  package in the MCP layer's import graph, which is how the boundary erodes
  without anyone deciding to erode it.

  Shape to consider: a domain module that the service layer and the surfaces
  both depend on, leaving `persistence` free to depend on it too. Stage is
  `design` because that is a module-layout decision with knock-on effects for
  every surface added later, not a rename.

- **[TST-9WFC]** The waived broad-except path in `dispatch()` is asserted by nothing
  `effort: S · impact: M · area: test-coverage · source: critic · added: 2026-07-27 · status: open · stage: ready`

  `server.dispatch`'s `except Exception` carries a
  `prawduct:allow prawduct/broad-except` waiver and converts an unexpected fault
  into a teaching failure result rather than letting it surface as a success. No
  test exercises it.

  Its sibling path — the unbound-action branch — became structurally unreachable
  when Chunk 07's fix round added the import-time registry↔BINDINGS
  reconciliation. That was the better fix (make the state impossible rather than
  test for it), but it leaves the waived catch itself uncovered, and a waiver on
  an unasserted path is exactly the combination that rots.

  Test to write: force a binding to raise, then assert the envelope reports
  `isError` **and** that no internal detail (traceback, exception text, file
  path) reaches the wire.

## Promoted

<!-- Items currently being addressed in an active build plan. /backlog pick
     skips these by default (work is already in flight). -->

## Archive

<!-- Shipped and dropped items, kept for searchability. Never deleted. -->
