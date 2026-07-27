# Backlog — Samsung Frame Art Loader

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

## Promoted

<!-- Items currently being addressed in an active build plan. /backlog pick
     skips these by default (work is already in flight). -->

## Archive

<!-- Shipped and dropped items, kept for searchability. Never deleted. -->
