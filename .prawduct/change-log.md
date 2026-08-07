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

## 2026-08-07: The wall takes the television from whoever is watching it

<!-- prawduct: chunks=12 | scope=v1-build -->

**Why:** with the operator watching a programme and the daemon rotating normally,
a due rotation sent `select_image` and **the set switched itself into art mode**.
The picture they were watching was gone. That cell of the state map had read *not
tried — it would take the screen off whoever is watching*; it does exactly that,
and somebody watching television is a daily event rather than an edge case.

**The requirement did not exist, so it was written before the code** —
`nonfunctional-requirements.md` § Availability, "The television belongs to whoever
is using it". It outranks availability: a wall that is late is a smaller failure
than a television that interrupts the person watching it. The plane deliberately
does **not** turn a dark set on, which currently costs nothing since neither
`select_image` nor `set_artmode('on')` can wake one.

**One reading decides it.** `get_artmode` answers `off` for both a dark panel and
a programme, and `on` only for art mode, so a single check covers both states the
wall must not touch; `PowerState` cannot, reading `on` for a programme too. A no
freezes everything the existing still-wall path already freezes — no selection, no
advance through the theme, no directive consumed — which made this a second route
into tested behaviour rather than new machinery.

**Recovery is by the set's own announcement, not by waiting.** Subscribing to
`art_mode_changed` / `artmode_status` / `go_to_standby` / `wakeup` clears the
backoff, so switching a programme off brings the wall back on the next poll
instead of after a wait that has doubled its way to five minutes — which matters
because this transition happens every time somebody finishes watching something. A
reconnection counts as an announcement for the same reason. **The announcement is
never the answer**: it says "ask again", and the decision is always a fresh read,
so a missed one costs promptness and can never license a selection into a
programme.

### Also in this commit: both Critic blockers from the cumulative review

- **The rebind path was dead code against the real client.** `_call` drops and
  closes its connection on *any* failure, so `_rebind_or_reraise`'s first act —
  asking the set what it lists — would have raised "not connected" before reaching
  the television, and the whole mark-orphaned / re-upload branch could never run.
  It reconnects first now. **The double was what hid it**: `FakeTv` raised without
  clearing its connected flag, so the fake kept answering where the real client
  would have refused. The fake now models the refusal, which is what makes the fix
  provable — the mutation survived the first sweep until it did.
- **The pairing token could reach the journal at the default level.** The
  television client's logger was floored at INFO on the belief that the token is a
  DEBUG line; the pinned fork logs `New token %s` at **INFO**
  (`samsungtvws/connection.py:101`), so the floor permitted precisely the line it
  was written to stop, on any pairing, with nobody doing anything unusual. Floored
  at WARNING, with a regression test at the level that actually leaks it.

Eleven further findings were dispositioned in the same pass. Fixed: the daemon
now closes the art channel on *every* exit including an unexpected one (the set
holds an abandoned client's slot for minutes, so under `Restart=always` a crash
could lock the daemon out of its own television); README, `deploy/README.md`,
`operator-verification.md` and `platform-and-dependency-findings.md` no longer
carry the pre-hardware framing or the retired `ms.channel.timeOut` standby
signature this same work retired; the build plan now says plainly that the live
pass ran **from a development Mac, not the Pi**, and names the three things in it
still unobserved; a duplicated binding predicate became one function; an uncalled
accessor was deleted; the plane-isolation guard's comment now describes what its
resolver does. Six were accepted as facts with reasons.

**Twenty mutations across two batches, all caught.** Two survived their first
sweep and both were real: the reconnect above, and a recovery test whose clock
advanced by exactly one interval per loop, so the arithmetic agreed with the bug
it was meant to catch. That is the third time in two sessions a deliberately
written test could not have failed.

## 2026-08-07: The confirming read was reading the wrong thing, and the wall parked

<!-- prawduct: chunks=12 | scope=v1-build -->

**Why:** the entry below added a confirming read for selections, verified it
against a dark set, and shipped it. The first pass with the set in **art mode**
showed what that verification could not: `get_current` does not describe the wall,
so every real rotation was reported as a failure and the wall stopped on one
picture.

**What the hardware said.** `get_current_artwork` reports the *art-store slot* —
its replies carry `"content_type": "artstore"` — and it named the same id,
`SAM-F0222`, across every observation ever made against this set, in all three
states, before and after selections that visibly changed the picture. Measured in
art mode: the wall changed to the requested image, `image_selected` fired at
+1.04 s with `is_shown: "Yes"`, and 37 seconds of polling `get_current` never
moved. `get_slideshow_status.current_content_id` is empty while the slideshow is
off, which is the state this plane requires, so it is not an alternative. **There
is no reader on this firmware that answers "what is on the wall".**

**Why the dark-state verification could not catch it.** In the dark state the
wrong read *agrees with the failure* — it reports a wall that is not changing,
because it never changes. The one state it was tested in is precisely the one
where a value that means nothing and a value that means everything are
indistinguishable. The consequence in the room: the cursor only advances on a
confirmed show, so the daemon re-selected the same work on every backoff step and
the wall held one picture.

**What changed.** Confirmation is the set's own `image_selected` announcement,
which carries both halves the question needs — which image, and `is_shown` — and
which does not fire at all in the dark state, so it still catches the defect the
entry below found. Because it is *pushed*, **asking and confirming became one
operation** at the television seam (`show(content_id) -> bool`): a listener
registered after the request races an answer measured arriving in 0.49 s, and the
old two-call shape is what forced confirmation to be a poll after the fact.
`select_image` and `current_content_id` left the `TvClient` interface; the daemon
no longer owns a confirmation window.

A redundant selection is announced too, so the restart path that re-shows the
current picture confirms normally rather than reporting every restart as a stuck
wall — measured, because that path would otherwise have been the next thing to
break.

**The live pass then completed, and Chunk 12's three acceptance criteria are met
on the real set.** Three unattended rotations at the manifest's 180 s — Calder →
Hokusai → Klee, intervals 182 s and 181 s — each confirmed against the set and
each matching what the operator saw with their own eyes; the third with the
curation plane stopped; then a restart that re-showed the same picture without
moving the wall and carried on to the next work. Brightness was set from the
solar angle and the whole run logged five INFO lines and no WARNING or ERROR.
The theme's uploads — 39 of them, one per pass as designed — had gone up during
the earlier pass that afternoon, so this run had only bindings to read.

**Also measured, and recorded in `samsung-tv-state-findings.md`:** art mode
reports over the API after all — `get_artmode` answers `on`, which retires "it has
never returned `on` here" and makes it a real discriminator, while `PowerState`
still distinguishes only whether the panel is lit. And `ms.channel.timeOut` was
seen **in art mode**, after ~20 connect/close cycles and a SIGKILLed daemon that
never closed its socket; it is a connection-slot symptom, not the art-mode
signature two artifacts described. How many art-channel clients the set allows is
unquantified and matters for a Pi running `Restart=always`.

**Eight mutations, all caught** — including the arm-before-send ordering and the
`is_shown` check. One survived the first sweep: a duplicate announcement resolving
an already-resolved waiter, which would raise on the library's reader task and
silently end every future confirmation. Covered, then re-swept.

## 2026-08-07: The television takes selections and displays none of them

<!-- prawduct: chunks=12 | scope=v1-build -->

**Why:** the display plane met a real television for the first time, and the very
first pass reported showing a work the wall was not showing.

**What the hardware said.** With the set dark — `PowerState: standby`, art mode
`off` — `select_image` is accepted, raises nothing, emits none of the three
art-mode events, and changes nothing, indefinitely. Everything else in a rotation
works: the art channel opens in 2.4 s, and uploads, deletions, listings and
brightness all succeed. The one failure a return value cannot carry was the one
the daemon trusted a return value for, and it is the everyday condition of a set
somebody switched off rather than an edge case.

**What changed.** A selection is confirmed by reading back what the set says it
displays — the argument `remove()` already made, that reading state beats
believing a reply. "The set took it and displayed nothing" became its own outcome
rather than a failure to show one work, because the two want opposite responses:
a missing render means try the next work; a wall displaying nothing means try
none of them. Nothing is recorded as having been on the wall, the place in the
rotation is given back, a `show_now` is left unconsumed by the rule that already
survives an outage, and it is said once with the set's own art-mode flag, then
again on recovery.

**A defect introduced and caught in the same session.** Leaving the pin
unconsumed removed the only brake on the directive path, which has no timer where
rotation does — a select plus a confirming read every poll, all night. It backs
off now on the ladder an unreachable set already uses. Found by scrubbing the
diff, not by a test failing.

**The state map is new.** `samsung-tv-state-findings.md` records which call works
in which state, because the library's vocabulary misleads: `on()` and
`in_artmode()` both derive from REST `PowerState`, which says only whether the
panel is lit — the television state and art mode both report `on`. It retires a
claim this repo carried in two places (that standby refuses the handshake), and
it is honest about the gap that matters: **art mode has never been observed over
the API on this set**, `get_artmode` having answered `off` every time it has been
asked. The confirming read is proven to catch a dark wall and has never been seen
agreeing on a healthy one.

**Also settled by measurement:** the set advertises a brightness range of 0–10
and accepts −4, reading it straight back — so `TV_MIN_BRIGHTNESS=-4`, carried
forward from the 2024 plane on faith, is correct. And the dark state cannot be
left in software: `set_artmode('on')` returns cleanly and does nothing, and
Wake-on-LAN to the advertised MAC has no effect on a set reporting `networkType:
wired`.

**Critic:** 1 blocking, 13 warnings, 10 notes. The blocking one was right — the
two new methods sit in the one module with no double beneath it and no test
reached them; nine tests now do. The reviewers independently found the retry
flood, judging the commit before its fix. Chunk 12 remains open: the live pass
still needs art mode, and that is now the first thing to watch.

The composition root also got its first tests. `__main__.py` has two refusals to
start — a missing deployment value and a store written by a newer plane — and
both are read by somebody at a terminal, so both owe a non-zero exit, a sentence
on stderr and no traceback. A third holds that anything *other* than those two
keeps its traceback, because a bug wearing the same tidy two-line exit would send
whoever read it to the wrong file.

**Tests:** 150 / 1925 / 159. Nineteen mutations swept across four sweeps, all
caught — two only after the sweep exposed tests passing by coincidence, and one
after a second review round found the rotation half of the wall backoff
undefended while the directive half was covered.

## 2026-08-06: Two checks that reported on measurements they never took

<!-- prawduct: scope=v1-build -->

**Why:** The live `tv_api_check.py` run that cleared the 2026-08-06 dependency
bump passed nine checks and failed none, and two of those nine had measured
nothing. Neither said so. That is the fault worth naming above either bug: a
check whose "cannot tell" and "all clear" print the same line is worse than no
check, because it retires the question.

**The panel-size check was comparing `None` on every run since it was written.**
It read `modelName` from the art client's `get_device_info()`, which returns the
*art channel's* payload — `current_rotation_status`, `support_brightness_sensor`,
`resolution_type`, no `device` key at all. The `{"device": {"modelName": …}}`
shape belongs to the REST endpoint at `/api/v2/`, a different endpoint over a
different protocol. So the model was always `None`, `disagreement(None, …)`
returned `None`, and the check took its "neither side stated one" branch and
reported `ok`. It exists because a live deployment ran `TV_PANEL_DIAGONAL_INCHES=42`
against a 50" panel and mis-sized every judgement about whether a work belonged on
the wall — and `.env.example` ships that 42, so the misconfiguration it guards
against is the one a fresh clone starts in. The guard worked; nothing reached it.

The model now comes from `samsungtvws.rest.SamsungTVRest.rest_device_info()`, the
public synchronous client for that endpoint, and the note reports `modelName`
beside the `24_`-prefixed model year — the field the token handshake actually
turns on, which the comment beside it had asked for and the code had never
supplied.

**The structural half is `panel_check.not_compared()`**, and it is what stops the
next one. `disagreement()` is quiet in three unrelated states — the set named no
size, the deployment configured none, the two agree — and any caller reading only
that answer must either report a pass for all three or invent the distinction
itself. Now one function says whether a comparison was possible and the other
says how it came out; a caller that reports a pass without asking the first is
claiming a measurement it did not take. The tool prints three outcomes where it
printed two, and `not compared` names which side said nothing. An unset diagonal
says the built-in default is in use and unchecked, rather than "not set", which
reads as harmless and is not.

**The callback check could not name the event it was registered for**, and its
output looked as though it had. The library selects a callback by the *sub*-event
inside the message (`self.callbacks[sub_event]`) and invokes it with the *outer*
websocket message type, so all three art-channel callbacks are called with
`event="d2d_service_message"`. The recorder appended that first argument, so
every run reported the same constant whichever event fired — and the 2026-08-06
operator note read it at face value and concluded that *nothing* fired, a claim
its own "0 failed" line contradicted, since the check fails when none do. The
recorder now captures its trigger in a closure at registration. That is exact
precisely because selection is by sub-event.

**Six mutations of the new branches, all caught**; three suites green (150 / 134
/ 1925). The library's argument-order trap is written into
`platform-and-dependency-findings.md` rather than only fixed, because the display
plane registers no callback yet and is the next thing that will.

**`tv_api_check.py` still has no unit tests and still cannot have them here** —
it imports `samsungtvws`, which the root project deliberately does not install.
The decision that could be moved was moved: `panel_check` is importable by the
root suite and now carries both halves of the panel question. The two call-site
fixes were driven against the payloads the live run captured — fed the art
channel's, the panel line reads `not compared`; fed the REST payload against 42,
it fails with the full 104.9-against-88.1 warning — and the next run on the set is
what confirms them against a television.

## 2026-08-06: The display plane exists — and the guard that could not be written until it did

<!-- prawduct: chunks=12 | scope=v1-build -->

**Why:** Chunk 12. The wall is still driven by `tvart.py`; this is the plane that
replaces it — poll the manifest, keep the television holding what the manifest
lists, rotate over it, and execute the directives a curator's `next` and
`show_now` ride in on. **The chunk is not closed**: its acceptance calls for a
live pass on the Pi, and the television has been in standby all session.
Everything below is verified against a double.

**`tests/preferences/test_plane_isolation.py` finally exists**, and its
sequencing was the point rather than an accident of scheduling. The norm index
named that path as a live `Test` mechanism for three sessions while no such file
had ever existed; the correction that caught it also said why it could not be
written yet — a check over an empty package passes vacuously — and why it must
not wait, since the window in which display code exists unguarded is exactly the
window in which "just fetch the label text live" gets written and passes every
test. So it landed in the same commit as the plane's first modules. It follows
imports **transitively through this repository's own files**, which is the
difference between a guard and a formality: a direct-only check is evaded by one
shared helper, and the helper is where the import would actually land.
Third-party packages are deliberately not followed, and that is what makes the
television exemption structural — `samsungtvws` drags `aiohttp` in behind it, and
neither is display's import to answer for. Both halves were driven red on purpose
against the real tree before being trusted.

**Four things were settled at build that the artifacts had left open.**

*A restart re-shows the picture that is already up, rather than advancing.* The
acceptance criterion says a restart must neither re-execute the last directive
nor lose its place, and the first implementation read that as "resume after the
last work" — which advances the wall every time the unit bounces. Under
`Restart=always` that turns a crash loop into a strobing wall, which is much
worse than the alternative it was avoiding. Re-selecting what is showing is
idempotent and invisible; the place is kept because the *next* step is the work
after it. A `sync` mid-interval takes the opposite branch, because a running
process holding its place in memory would otherwise be handed a second full
interval on every catalogue edit.

*A directive is consumed after the attempt, never before.* Every path that acts
on one can find the television asleep, and a sequence marked acted-on during an
outage is a `show_now` the curator never gets — the manifest does not change, so
nothing would ever present it again. An attempt that *completes* and shows
nothing, such as a pin whose render is missing, is still an attempt and is
consumed; retrying that one every second fills the journal with a failure that
will not change until a file appears. Both halves are now in `api-contract.md`
§ How `art_display` reaches the display plane, which is where the question was
parked.

*Uploads are carried one per pass rather than done in a batch on adoption.* A
fresh install has an empty binding table and a theme of forty works at the better
part of ten seconds each. Uploading them all before the first `select_image`
leaves the wall on yesterday's picture for five minutes — and leaves a curator
pressing "next" with nothing happening for five minutes, against a poll interval
that is one second precisely because that wait is the one the product may not
have.

*The e-paper panel's geometry became configuration*, `EPD_PANEL_WIDTH_PX` and
`EPD_PANEL_HEIGHT_PX`, defaulting to the reference 1448×1072. It was a number in
prose, which is the standing the television's geometry had before it was hoisted,
and `operational-spec.md`'s own rule that nothing may hardcode either panel's
size reaches this one too.

**The television's two known lies are corrected at the seam and nowhere else.**
`upload()` reports failure on uploads that succeeded, and `delete_list()` never
reads its reply — so an upload is attributed by reading the set's own listing
back (the `image_date` this request stamped, plus a before-snapshot, because
either signal alone can be wrong), and a removal reports what the set holds
afterwards. Everything above the seam is written against an abstract `TvClient`
and never imports the fork, which is what keeps an unowned, four-months-static
upstream a swap rather than a rewrite.

**`display/` is a package now, and `[tool.uv] package = false` is gone.** Both of
that setting's recorded reasons were artefacts of the empty tree: hatchling
refuses a git-sourced direct reference unless told one is intended (one line), and
there was no package directory to build (there is one now). It had to change,
because `src/` layout and "never installed" cannot both hold — `python -m display`
finds nothing on the path.

The plane also brought the third `test_commands` entry, the third CI leg in
`suites.yml`, and a guard that the new leg needs no `--ignore` set — the
symmetric claim to the one the root leg already carried, written separately
because the plane that will grow an opt-in group first is this one, the moment
the e-paper panel arrives behind an optional install.

**The Critic round returned 0 blocking, 17 warning, 11 note, and the warnings
were worth having.** Four were live defects on paths a test double hides, and
they share a shape worth naming: *work that is owed and gets attempted exactly
once*. Reconciling the binding table against the set — which is what removes the
legacy uploads, this chunk's stated deliverable — was reachable only on the tick
a manifest first arrives, and that tick aborts when the set is asleep, which the
module's own docstring says is most of them. It is now owed until it settles. Its
three siblings: a selection the set refuses was read as an outage, so one image
deleted from the phone app would freeze the wall on a backoff retrying a dead id
for ever; a dropped client was abandoned without `close()`, leaking a websocket
and its reader task per transient error on a daemon that runs for months; and a
non-UTF-8 manifest raised `UnicodeDecodeError`, which is a `ValueError` and not an
`OSError`, so it escaped every frame and killed the process over exactly the kind
of malformed file that module exists to refuse.

**Two were log floods, and they are not a tidiness complaint.** A theme whose
renders are all missing walked its whole list once a second, because the rotation
timer was stamped on success rather than on the attempt; a work the set refuses to
accept was re-uploaded every pass, with a WARNING and a row rewritten each time.
journald rate-limits, and the lines it drops first are the ERRORs that are this
plane's only failure channel — a plane whose whole premise is that failure here is
silent.

**A mutation sweep ran over the plane's new branches and found what a green suite
could not.** Twenty-nine mutations, and the survivors were the interesting part:
one branch was *dead code* (brightness was clamped twice, so the inner clamp could
be deleted with no test objecting), one test asserted a rule against a set that was
already asleep — so the code under test never ran and the assertion passed for the
wrong reason — and the last survivor was `tv/samsung.py` having **no tests at
all**. That is the module holding every correction for the library's misreporting,
and the daemon suite runs against a double, so nothing reached it. It has eighteen
now, against a stubbed library: an upload that lands while reporting failure is
found by reading the set's own listing back, and a failed call is proven to close
the connection rather than abandon it.

The sweep tool needed two changes to reach this plane at all — a `--project` flag,
since it was hardwired to the curation root, and `-n0` made conditional on the
project actually having xdist, which display does not and which made pytest exit 4
and read as a broken suite.

**The verify round returned one blocking finding, and it was the right one to
catch: a security control with no test.** The clamp that stops the fork's DEBUG
line putting the television's pairing token in the journal had one caller and no
test, so `max`→`min` or a renamed constant would have passed the suite silently —
against a public repository whose very first chunk existed to undo that token
being committed. `display/tests/test_logs.py` now asserts the level *and* that the
token does not reach the stream.

**A question the operator asked about the library turned up a live defect nothing
was looking for.** Talking through what a device-driver interface would need
surfaced that `render_path` is `ready/{artwork_id}.jpg` and **stable across
re-renders**: a curator changing a mat colour rewrites the bytes under an
unchanged name, the binding still reads `uploaded`, and the television goes on
showing the old composition indefinitely with every record in the product
agreeing. `set_mat_color` and `regenerate` both shipped in 18B, so it is reachable
by ordinary use. The binding now carries a `render_fingerprint` — modification
time and size, not a hash, because the rotation reads it per entry per pass and
hashing forty 2 MB composites a second is real I/O on an SD card to answer a
question `stat` answers. That is `display-state.sqlite` schema 2, and it exercised
the widening step the store was built with rather than leaving it theoretical.

**Orphan removal also learned the difference between two failures that look
alike.** A set that answers and *keeps* an image has established the state of the
world — the outcome is already reported at WARNING — so reconciliation settles and
the next manifest re-arms it. A set nobody could get an answer out of leaves the
work owed, retried on a wait rather than every second. That distinction shipped
one commit before its test, which the round caught: restoring the old value passed
the whole suite, because nothing had ever produced a removal the set survived.

The direction that conversation was actually about — abstracting the display
device so the Samsung client becomes one driver among several — is filed as
**#102** rather than built. The seam is already most of the way there; what does
not generalise is the *shape* of the interface, whose upload-then-select-by-id
contract is a Frame artifact that no other device wants.

## 2026-08-06: The small-issue sweep — eleven closed, and the two guards that were guarding a copy

<!-- prawduct: scope=v1-build -->

**Why:** the backlog held seventeen `effort:S` items across nine unrelated areas,
and small items left grouped by nothing get worked one at a time forever. Grouped
by what they actually share, most of them turned out to be four pieces of work
rather than seventeen.

**Four closed without code.** #19's dead `uploaded_files = {}` had already gone
when `b49a4f5` rewrote `delete_all_uploaded` for a different fault — and the
lifecycle question that kept it from being fixed in place got answered on the way
past, `tv_content_id` being the bookkeeping. It closed without the Chunk 12
supersession it expected, that adoption having been descoped on evidence. #10
(the second-look shelf) was ruled won't-do: the operator is the only MCP caller.
#46 and #42 went upstream as prawduct#606 and #607, both re-verified against
v3.2.6 first — and #46 got *stronger* in the process. It was filed as facts that
fail to reach the ledger; `plugin/lib/ledger.py` is fail-closed on its kind
vocabulary, so there is no resolution kind for `ledger-append` to accept. A
design gap, not a dropped write.

**CI was showing two green checks and neither watched the suites** (#82, #84,
#98). A workflow now runs both default suites and all three planes' lint on every
PR; a failing scheduled probe opens one issue per contract in the backlog the
operator already reads; and an *unfired* schedule is caught by measuring how long
since each tier last succeeded, per tier, because a healthy monthly run would
otherwise vouch for three missed Mondays.

Two corrections came out of the Critic round on that. The paid tier no longer
fails on never-run — the first version went red the moment it reached `main` with
the only remedies being to wait a month or spend real credit, and a check whose
green costs money is a check that gets ignored, taking the free tier's finding
down with it. And nothing created the `api-drift` label, so `gh issue create
--label` would have raised on the first real failure: the alerting path failing
exactly when needed.

**The guard was reading the wrong number, and only a CI leg could reveal it.**
pytest reports an `xfail` as `<skipped>` and counts it in the suite's `skipped`
attribute, so `assert_tests_ran.py` failed the new leg naming a dependency that
was never missing. An `xfail` is the opposite of an unprovisioned test. Nothing
had ever run a suite containing one in CI, so the defect had nowhere to show.

**One record, one shape** (#36, #100). The candidate-work seven keys were written
at four sites; three are now one function, and the fourth — the HTTP model — is
held to it by a test with a *named* exemption, where a stale exemption is itself
a failure. `architecture.md`'s per-surface-formatting entry is scoped rather than
amended away: it describes the artwork pair, which genuinely differs, and that
divergence is now asserted too, being the entry's only evidence.

**Two listings and a watch that could not stop** (#54, #83). `list_runs` returned
the whole history on both surfaces, growing with the number of runs *and* the
length of what people typed. The cap is the service's, so the two surfaces cannot
disagree about how much history exists. The run poll re-armed for ever on a
permanent failure: a stale bookmark had the tab asking for a run that will never
exist every two seconds, bounded only by navigation. Counted consecutively, not
cumulatively, and keyed by run id — the issue said generation, and `state.poll`
increments every poll, so a generation-keyed count would reset each tick and
never reach any threshold.

**Two silently-wrong deployment values** (#22, #75). A typo in `ART_ROOT` created
a directory, created an empty catalogue, and started cleanly. A marker file now
refuses that, and a directory already holding a catalogue counts as marked, so
the check cannot take a live install down. `TV_PANEL_DIAGONAL_INCHES` is now
checkable rather than merely documentable — a claim `.env.example` had carried
for two days before anything delivered it.

**Three rounds of the sweep, three findings, and one of them was the tool.**
Assertions written straight against a tree that already agrees can only ever be
seen to pass: `==` loosened to `<=` changed no test, and a single fabricated case
breaking two directions at once passed on whichever assertion fired first. Then
the sweep tool itself — with `-x` under xdist a failing test exits **2**, not 1,
so every *caught* mutation looked like the unclassifiable exit it refuses to
guess at, and a sweep aborted on its first real catch calling itself
misconfigured. `-n auto` is in this plane's `addopts`, so the invocation
`CLAUDE.md` documents could only complete when nothing was caught.

**The Critic's blocking finding was the same shape one level up.** The run-listing
cap was asserted against a helper that rebuilt `runs[:MAX_RUNS_LISTED]` — the
production expression, copied — so deleting the slice from the service left both
suites green. That slice is the whole of #54.

**Three rulings and two wordings, in the same sweep.** #40 asked the owner
whether four mechanical guards are norms this product states. One is: the TV
pairing token is never tracked, which has a real incident behind it and is a
secret in a public repo. The other three are recorded as deliberately uncovered,
in a section beside the index, because the alternative is that every Norm Health
sweep rediscovers them and asks again — and that section says plainly that a
guard listed there is still a guard. `test_persistence_boundary.py` is
deliberately *not* named as enforcement of the adjacent service-layer row:
naming an import check there would read as though a judgement-required norm were
mechanically enforced, when the violations it exists to catch are exactly what an
import check cannot see.

#93 removed the run table's provenance column rather than renaming it — "Where it
came from" meant how a row entered the run and reads as which museum holds the
work, and this table was the distinction's fourth statement. #99 answered what
the resolution badge describes: the run, and the words now say so ("the run found
an image"), which is what makes it consistent with "You have turned down
everything that was found for it" instead of contradicting it. Deriving the badge
from surviving instances was the other option and the one the issue leaned
toward; it would have made one badge mean two things on two screens, since the
run table's rows carry no instance data — which #99's own acceptance forbids.

#27 was not labelled and so was not in the seventeen. It is a small,
fully-specified refactor of the same family: `durable.py` states it holds no
domain concept and reached through the catalogue adapter for its error types. The
types moved to `persistence/errors.py`, `catalogue.py` re-exports them
permanently, and a guard now holds the seam — because a layering statement the
code contradicts in one line is precisely the kind that survives every
behavioural test.

**Two verify rounds, and each found the same shape one level up.** The first
review's blocking finding was that the run-listing cap was asserted against a
helper rebuilding the production expression. The second found the art-root guard
wired into startup with nothing testing the wiring — the fixture that lets the
other startup tests past the guard *marks* the root, so `prepare` returned at its
first branch in all seven and deleting the call from `main` broke nothing. A
function tested thoroughly and a call site tested not at all, twice.

The second round also caught a claim this session had written into the service
unit: that `curation.art_root` now covers a systemd-mis-parsed `ART_ROOT`. That
unit's `ExecStart` is `tvart.py`. The guard is real and governs a process that
file does not start, so the correction to R-15 had over-reached in exactly the
direction R-15 was about.

**Also corrected: the dotenv precedence flip had reached two of four sites.** The
service unit and the operational spec both still promised that `EnvironmentFile=`
was a presence guard rather than the value source, which inverted when
`override=True` was retired. systemd's parser now decides, and the two parsers
differ on quoting — so a mis-parsed `ART_ROOT` is live. What covers the worst
case is now a mechanism rather than a promise: the marker check above.

## 2026-08-05: The seven fixes the fix-or-file pass identified and did not do

<!-- prawduct: scope=v1-build -->

**Why:** the pass below classified seventeen `effort:S stage:ready` items and
closed five. Twelve met neither filing test, so seven remained — a fix waiting to
be done is not a backlog item, which is what the ratified preference says. No
`chunks=` tag: this closes backlog items, not a build-plan chunk.

Reconstructing which seven, since the pass recorded the counts and not the list:
of the items still open at that label, #46 and #42 are prawduct's own bugs (here
only because no bug inbox is configured) and #84, #83 and #82 each say in their
own body that the *decision* is the item — which is filing test (1) exactly. The
rest were the fixes: #44, #55, #45, #86, #25, #32, #85. The reconstruction is
checkable rather than asserted, because those five are precisely what stayed open
when these closed.

**Two defects were live, not latent.** `delete_all_uploaded` cleared every
`tv_content_id` while `DeleteResult.surviving` sat there naming which removals
the television had not honoured — and `sync_artsets_to_tv` picks upload
candidates by exactly "has no `tv_content_id`", so a survivor was uploaded again
as a duplicate onto a set with finite storage. And the rendition-currency rule
was written twice, with the manifest builder reaching past `CatalogueService`
into the store to feed its own copy; the review grid would badge a work current
while the wall silently dropped it. The tie-break beside it was a second live
disagreement: the builder took the newest television render, the thumbnail
service took the first current one the store returned, and the unique index on
`(artwork_id, kind, target_width, target_height)` makes two renders reachable.

**Three were guards that were not there.** A museum preview body was read whole
into memory with no bound, from a URL out of the museum's own JSON with redirects
followed — an unbounded allocation driven by a stranger, contained only by the
unit's `MemoryMax` to "curation dies". `acquisition.deployment_fault` was emitted
by the MCP binding, so the signal followed the caller: the first browser
acquisition route would have inherited the refusal and not the journal line.
And `dispatch`'s waived broad-except — the one thing standing between an
unexpected fault and a success envelope — was asserted by nothing.

**Two were the environment lying quietly.** `load_dotenv(override=True)` in both
planes meant an exported `ART_ROOT` was discarded rather than refused, so a
scratch run booted against the real catalogue and the wrong data looked exactly
like the right data. The stated reason — cached values "that pipenv loaded" —
was checked rather than inherited: there is no Pipfile and no other mention of
pipenv in the tree.

**What the round is worth recording for is a vacuous test caught by mutation
rather than by reading.** The tie-break test recorded its two renders widest
first, which makes the store's `(kind, target_width, …)` order and newest-first
coincide — so the *pre-fix* code passed it. Reading the test could not show that;
running the old code against it did. The fixture now records them the other way
round and asserts the two orders disagree, so a change to the store's `ORDER BY`
fails it loudly instead of quietly returning it to proving nothing. Every fix in
this batch was mutation-checked for the same reason, nineteen mutations in all,
and each was caught by a test that names the defect rather than by the suite at
large.

**A ceiling was measured rather than guessed.** `PREVIEW_MAX_BYTES` is 16 MiB
against five real Art Institute previews sampled at 89–193 KiB — not a prediction
of the largest legitimate preview, but the point past which a body has stopped
being one.

**Two decisions taken rather than asked.** #55's duplicate #51 is closed by the
same commit rather than merged, because the work is done and a redirect would
leave two open records of one fixed defect. And an unconfirmed television removal
now forgets nothing: it can cost a work its place on the set until the next
confirmed pass, where the opposite error costs storage on every run and is
invisible.

Artifacts followed the code in the same commits: `architecture.md`'s "inherits
the staleness rule" is now true and says since when, its Scaling Model gained the
preview as the second memory path, `observability-strategy.md` lost the limit
paragraph naming #86 as its own fix and gained `phase_two.preview_too_large`, and
`project-state.yaml` records the IA and interaction patterns the discovery half
brought — checked against `app.js`'s own `VIEWS` and `DETAIL_VIEWS` maps rather
than asserted.

## 2026-08-05: A fix-or-file pass, and the fence that shipped in the plane being deleted

<!-- prawduct: chunks=19B | scope=v1-build -->

**Why:** the strong-bias-towards-fixing preference was ratified with a retroactive
clause and nothing had exercised it. Seventeen open `effort:S stage:ready` items
were read and re-verified against the tree; twelve met neither filing test, three
carried a genuine undecided policy question, and two were prawduct's bugs sitting
here only because no bug inbox is configured.

**The pass found more by re-verifying than by fixing.** Two items (#37, #43) had
been fixed three days earlier by `53ec2d9` and never closed, so a triage that read
the bodies and stopped would have rebuilt shipped work. One (#39) was half-done,
and its code half had been solved *better* than the issue proposed — a `finally`
rather than the `except BaseException:` asked for. One (#32) named functions that
no longer exist while its defect stayed exactly where it was. **An issue body is
evidence about the day it was written, and this repo's own habit of writing
thorough ones is what made re-verification cheap rather than what made it
unnecessary.**

**The argument-injection fix and what the Critic then found wrong with it.** A URL
beginning with `-` reaches `dezoomify-rs` as a flag, and the argv list guarding
this call defeats shell metacharacters only — a different bug class with a
different guard. The ARTIC path composes its URL out of the museum's own
`config.iiif_url`, so the vector is real. Two guards landed in `image_utils.py`: a
scheme refusal, which closes the reachable case, and `--`, which does not depend on
the scheme check staying strict.

Both were proved by mutation, and `--` was checked against dezoomify-rs 2.18.1
rather than assumed from clap's documented behaviour. **The Critic's finding was
that all of it shipped in the plane Chunk 20 deletes** while
`curation/acquisition/dezoomify.py` — the one that survives — had no fence and a
comment calling its URL "the last option-free argument", which it is not: nothing
makes it option-free, and `staged` follows it. The curation plane was never
vulnerable (`check_fetchable` refuses a scheme-less string a caller earlier), and
that is precisely why the comment was worth fixing: **it credited the wrong
mechanism, so a reader learning the pattern here would have carried the wrong
lesson to the next call site.** Both planes now carry the fence and a comment
naming which guarantee is holding and where it lives.

**A blocking finding on commands nobody ran.** The new display-plane column in
`CLAUDE.md` taught `cd display && uv run ruff check .` and asserted it "runs
against an empty tree". It did not run at all: the manifest declared a hatchling
build backend, so `uv run` built the project first and hatchling refused the
git-pinned `samsungtvws` as a direct reference. `[tool.uv] package = false` makes
the plane what it actually is — an application a systemd unit starts, never a
wheel anything installs — and all three documented commands were then run rather
than predicted. **The prose had described the behaviour by reading the config**,
which is the same move the mutation-sweep section two headings below exists to
warn against.

`display/uv.lock` arrives with it, earlier than planned: Chunk 12 owed it, and
making the documented commands runnable produces one. Three unbounded dependencies
and a git-pinned fork are now actually pinned, which is what the lock was for.

**Also:** the black-formatting norm row said "both `pyproject.toml`s" with three
in the tree, and `README.md` and the norm index both said the display plane runs
3.12 on the Pi against a ratified 3.13 — in the two documents a newcomer
provisioning the Pi and a Norm Health sweep read first. One JPEG-fixture helper had
three byte-identical definitions and is now one. A supplement switched off in
configuration logged nothing, so "nothing was offered" read identically whether the
collection was empty, every candidate was declined, or the feature was off.

## 2026-08-05: A test that defended a copy of the branch it named

<!-- prawduct: chunks=19B | status=shipped | scope=v1-build -->

**Why:** the guard fix above left two demoted observations, and both were the same
shape as the defect they trailed — a claim stated more confidently than the code
supports.

The first was the scope check's docstring: "every line carrying the command
counts, whatever precedes it" is true of what the scan *collects* and false of
what it *checks*. The assertion reads the first token after the command on a
single line, so `uv run pytest \` with its arguments on the next line collects and
then passes on the backslash. No workflow here is written that way, and closing it
would need a line-joining pass — so the limit is written down rather than rounded
off, which is the whole lesson of the entry above.

The second was that the comment-skip branch had nothing defending it. Deleting it
turns no other test red, because the one comment in this repo carrying the command
is itself path-scoped and satisfies the assertion anyway.

**The fix for that second one was itself the defect it was closing.** The new test
re-implemented the scan loop in its own body instead of calling it, so deleting
the branch from the real scanner still turned nothing red while a fresh docstring
claimed the branch was covered. The Critic caught it by simulating exactly that
mutation, and rated it blocking. Both tests call `_ci_pytest_invocations` now —
one over `.github/workflows`, one over a written fixture — so there is a single
loop and mutating it is visible from both.

**What that cost, recorded because the rule it produced is about when to stop.** A
clean verify pass still carries demoted observations, and acting on them opens a
new evidence edge needing another pass. The rule that held for two rounds was:
take one only when the observation is a *false statement*, not a missing nicety.
The third round broke it — a merely-missing test was batched in beside a docstring
fix, got less care than a change taken on its own merits, and was the one that
failed. Adjacency is not a reason.

## 2026-08-05: The guard against a thrice-recurring defect could not see the documented form

<!-- prawduct: chunks=19B | status=shipped | scope=v1-build -->

**Why:** the second `verify-resolutions` came back clean, and its demoted
observations named a real hole in the guard added one commit earlier — together
with a docstring asserting the opposite of what the code did.

It matched two prefixes and claimed an invocation it did not match "would simply
not match the prefix and would be reported". It would not: an unmatched line
never enters the list, so it is skipped in silence. A coverage hole rather than a
loss of precision — and it sat exactly where `CLAUDE.md` points, since every
command that file documents is written `cd curation && uv run pytest …`, which
the prefixes missed, as would anything inside a `run: |` block.

**The shape is worth naming because it is this session's recurring one.** A guard
whose stated limitation is not its actual limitation cannot warn you: the
docstring said the failure mode was noisy (reported) when it was silent
(skipped), which is the difference between a check you can trust and one you only
believe. Verified the fix by dropping a probe workflow written in the documented
form and watching it fail, rather than by reading the matcher again.

`CLAUDE.md` now says the rest: the marker alone is right at a terminal and wrong
in a job, and the difference is which one has a guard reading the report.

## 2026-08-05: The Critic's findings on the review half, closed in one pass

<!-- prawduct: chunks=19B | status=shipped | scope=v1-build -->

**Why:** the cumulative round over five chunks returned 1 blocking, 7 warnings
and 9 notes across three reviewers. Nine fixed, six accepted, and five findings
filed against four issues — #26 took two of them (#5, #26, #81, #86).

**The blocking one was CI lying in the safe-looking direction.** All three
api-drift jobs ran `pytest -m live_*` unscoped, so collection reached four modules
whose opt-in groups are absent in CI, each landing an import skip — and the guard
fails on any skip. Every scheduled run would have gone red while every probe
passed, which is the alarm that cries wolf until nobody reads it. `browser.yml`
found and fixed the identical defect in this same bundle. Reproduced before
fixing, per this repo's own lesson about reasoning at a CI guard rather than
running it.

**A correction to something the previous session recorded as settled.** Its
handoff said a change-log entry with no `status=` tag is "release-pending by
design", and I repeated it in mine. Git says otherwise: all 23 prior chunks carry
`status=shipped`, written pre-merge on the feature branch. Five built chunks were
therefore showing as unstarted in the derived Status, and the tooling would have
taken Chunk 21 — finished — as the current one. Tagged, regenerated, and the note
that misled me corrected in place.

**The navigation guard, and a fix that was wrong in an instructive way.** Four
views paged through up to fifty round trips and painted unguarded, so clicking
away mid-load repainted the old view over the new one with the tab highlight and
the fragment both naming the new. My first attempt put the generation in a
module-level variable — which the *later* navigation overwrites, so the abandoned
paint reads the generation that superseded it and lands anyway. The guard passed
and did nothing. The test caught it; the value has to travel with the paint, so
`render` takes it as a required first argument and throws if a view omits it.

**Two mutations survived the sweep of that fix and neither was a defect.** One
reads `state.nav` a line later than the capture, which is the same value because
the thunk is invoked synchronously. The other removes `go()`'s own bump, which
`readHash` compensates on every path that changes the fragment — so the line is
load-bearing only when navigating to the view already displayed. Recorded in the
code rather than papered over with a white-box test, so the next reader does not
take the survivor for proof the line does nothing.

## 2026-08-05: The review half — the grid, its alternates, the verdict, the panel

<!-- prawduct: chunks=19B | status=shipped | scope=v1-build -->

**Why:** a curator could commission a run in the browser and not judge what it
brought back. The loop now closes onto the wall with no MCP client in it: intent,
estimate, review with images, accept, theme, wall.

**A binding for the re-search, added at the operator's call.** Turning a scan down
is one of the grid's own actions and it leaves the work `awaiting_better_image`,
where nothing looks again — `resolve_images` is what looks and had no HTTP
binding. Shipping the rejection without it would have made this chunk's own screen
a dead end escapable only from an MCP client. The grid says in words that nothing
is searching, because that is the fact a curator cannot see.

**The listing stops inlining pictures the browser discards.** Both surfaces call
the same review methods; the browser passes `pictures=False` and fetches each
picture by URL, so a page of the grid costs a `stat` per instance instead of a
re-encode — roughly half of what it cost on the machine this runs on. The two
readers have unrelated budgets: a model pays for a picture in context tokens, a
curator in pixels. The picture route re-encodes rather than serving the cached
file, because a preview's name on disk is derived from a URL and falls back to
`.jpg` for anything unrecognised — the suffix is not evidence of what the bytes
are.

**The health panel now has a reader for the document the display plane writes**,
which closes a finding carried against Chunk 19 since the plan was written: the
failure table maps TV, panel and last-error state onto that document and nothing
displayed it. Passed through untouched rather than unpacked into named fields —
`reported_at` is the only key that is contract, and inventing more would be a
second contract the writer never agreed to. Backup age ships against a receipt
nothing writes yet (`backup-status.json`, key `completed_at`, written only on
success): "no backup recorded" is a true observation, and it reports real ages the
moment Chunk 20's job lands. There is deliberately no budget balance.

**`get_health` left the known-departures table by conforming**, the first entry
there closed that way rather than by deletion. Assembling the panel's three
observations in the handler made *which signals the panel makes* a decision taken
in a binding, where the next one would have to be added in two places. The
heartbeat and the backup receipt now share one parser and one age-in-words, and
the panel states "4 days ago" rather than "345600 seconds ago" — which is the
wording `observability-strategy.md` specified and the code had never produced.

## 2026-08-05: The mutation sweep was reporting on runs that executed nothing

<!-- prawduct: chunks=19B | status=shipped | scope=v1-build -->

**Why:** found while trying to prove this chunk's browser tests could fail. The
sweep read any non-zero pytest exit as a caught mutation, and pytest exits **5**
when it collects no tests. Every opt-in suite here is deselected by a marker
expression in `addopts`, and naming such a test on the command line does not
select it — so a sweep over `tests/browser/` mutated the file, ran nothing, and
reported every mutation caught.

**Twenty-one mutations reported caught by runs that never executed a line of the
file they were applied to.** Re-run with the marker, two of the twenty-one
survived, and both were real: a card that asks for a picture the listing said is
absent, and the empty-page stopping condition in the paging loop. Neither test I
had written reached the branch it named.

The tool now runs the chosen tests once, unmutated, before sweeping, and refuses
to start unless they actually run and pass — which also catches an
already-red target set, where every mutation would be "caught" by the failure that
was already there. Anything other than a pass or a failure stops the sweep and
says which exit code it got. Extra pytest arguments pass through after a `--`.

**Chunk 23's recorded acceptance was reached the same way, and it was re-swept
rather than assumed.** Fourteen mutations over its six behaviours and their
over-fire pairs — `fetchAllWorks` termination, the shortfall note, the image
fallback, the focus move, poll suppression, paint supersession, the stale timer,
and the unresolved reason as words — **all fourteen caught** with the marker
passed through. That suite is genuinely covered; the evidence for it simply was
not evidence. Worth separating: a vacuous proof and a false claim are different
faults, and this was the first.

**One thing this cost, recorded because it nearly shipped.** A sweep rewrites the
file in place, so committing while one runs can capture a deliberate defect. It
did: a `git add -A` landed inside the window and put a mutated `app.js` and a
stray `.sweepbak` into a commit, with `git diff` against HEAD showing *identical*
because both sides were mutated. Caught by checking that every mutation's
`find` string was still present in the committed file, which is the check that
does not depend on a comparison. Do not run git and a sweep at the same time.

## 2026-08-05: The Critic's findings on the harness, closed in one pass

<!-- prawduct: chunks=23 | status=shipped | scope=v1-build -->

**Why:** the cumulative round returned 0 blocking, 6 warnings and 10 notes across
three reviewers. Ten fixed, four accepted, two filed (#83, #84).

**The one that was a real defect, and two reviewers found it independently.**
`viewRun` swallowed a failed family-spend fetch into a null, and `facts()` drops
null pairs — so the "Spent including every re-search" row vanished with no
message, leaving a costs panel whose largest figure is what the run *alone* spent.
That is precisely the misreading the family total was added to prevent, on a
surface whose own header states that a silent omission is what this product exists
to refuse. Twenty lines above, the same function argues at length for the opposite
treatment of the gate estimate. It now says so too. **The `state.painted`
asymmetry is deliberate and is commented as such**: the rollup is fetched only for
a run that has stopped, and a stopped run schedules no further poll, so
withholding the paint signature would enable a retry that cannot happen — the
sentence in the panel is the whole remedy. Two browser tests cover it, both proved
by mutation, which is the harness earning its keep in the same session it landed.

**The guard that had no guard.** `assert_tests_ran.py` is the only thing
distinguishing green-because-passing from green-because-skipped in every CI job
that runs a suite, and nothing tested it — the failure shape it exists to refuse,
one level up.
Nine tests now cover it, including both JUnit root shapes it handles by hand and a
check, derived from the workflow files rather than a written list, that every
workflow running pytest also calls it. Mutation found a weak one: asserting only
the exit code could not tell "no tests collected" from "nothing ran", two branches
that send an operator to opposite places, so it asserts the message.

**The artifact that described the absence.** `operator-verification.md` still read
"the client has no test runner ... none of them is executed by a test", and
invited reopening that trade if the surface kept growing logic of this kind. It
had, and the trade was settled the previous commit. The dangerous half was "that
decision stands": a builder starting 19B would have read it as live guidance and
skipped browser coverage, re-incurring the debt this chunk paid, in the very next
chunk. **Four artifacts describing what was built had been updated and the fifth,
describing its previous absence, was missed** — that asymmetry is now a learning,
because a document asserting "there is no X" cannot be found by grepping for X.

**Two coherence defects in the record.** `boundary-patterns.md` § Test Levels had
no row for `live_binary` at all and quoted an `addopts` value two markers out of
date; the quote is replaced by a pointer to `pyproject.toml`, since a copied
config value is only ever a second place to be wrong. And three documents said the
browser workflow runs "on every push" when it scopes push to `main` and relies on
`pull_request` — the workflow is right and the prose was wrong.

**The `[[slug]]` link syntax came back, and this repo had already closed that
exact defect once**, one file over, recorded in the 2026-08-04 verify round.
Neither link resolved and one pointed at a rule that has never been written. Both
now quote the referenced heading, which is this file family's own idiom. The
detail file was also still carrying the retired form of a rule as a live heading.

## 2026-08-05: The browser client gets executed, and the tests get proved

<!-- prawduct: chunks=23 | status=shipped | scope=v1-build -->

**Why:** `app.js` is the only human interface this product has, and neither
Python suite ran a line of it. Three defects had already reached a running
product through that gap — `replaceChildren` coercing a null and printing the
string "null", every image tile silently taking the shape of its own picture,
and a poll loop stealing the focus every two seconds from the one screen with a
decision on it. The first two were found by using the product and the third by
reading; none was visible to a test that reads JSON. Issue #30 said this stopped
being tolerable at Chunk 19, and 19A shipped first, so this pays that debt before
19B adds the review grid.

**The binding is Python, and that is a change to what was recorded.** The
operator's decision settled Playwright over the three cheaper options and named
its costs, one of which was "a second language's package manifest inside
`curation/`". Playwright publishes first-party Python bindings, so that cost is
simply not paid — verified by installing `pytest-playwright` on this repo's 3.14
before the choice was put rather than after. The harness is
`curation/tests/browser/` behind a `browser` marker: one language, one suite, one
command, and it reuses the suite's own server, catalogue and image fixtures
instead of rebuilding every state through the HTTP API. The decision entry, the
chunk's deliverables and `project-preferences.md` all record the amendment rather
than quietly reading the old words the new way. The other two costs stand.

**Deselected for a fourth reason, and it is none of the first three.** The live
suites are off because they spend money or need the network, and the evaluation
because it is non-deterministic. This one spends nothing, reaches nothing
foreign, and is entirely deterministic; what it needs is a ~200MB browser, which
is too much for a default `uv sync`. So its deselection is a packaging decision
rather than a statement about the tests, its dependency is an opt-in group of the
same shape as `eval`'s, and `.github/workflows/browser.yml` runs it on every pull
request and on pushes to `main` so that being off the default run does not become
never running — with `assert_tests_ran.py` behind it, because a suite that skipped
itself reports green and green-because-absent is indistinguishable from
green-because-passing in a checks list. Verified by installing without the group
and watching both modules skip with the command that fixes them, the default
suite's own count untouched.

**The CI leg was wrong when first written, and the guard is what said so.** `-m
browser` still *collects* the whole tests tree, so the evaluation module's
import-skip landed in the JUnit report, and `assert_tests_ran.py` reads any skip
as a provisioning failure — the job would have failed on every run. Found by
pointing the guard at a real report rather than by reasoning about it (it exited
1, naming the eval module), and fixed by scoping the invocation to
`tests/browser` as well as to the marker. Worth recording because the marker
alone looks sufficient and is not.

**What it covers is the client, with `/api` as its boundary.** Where a real
server can produce the state it does — paging runs against a real catalogue of
101 works and the real `truncated` flag, the image tests write a real file and
take it away, the focus move runs against the real routes. Routes are stubbed
only for states a server cannot be asked for deterministically: a poll that
changes nothing, a page that keeps insisting there is more, each unresolved
reason in turn. Stubbed payloads are built from the API's own response models
rather than hand-written dicts, so a response that changes shape cannot leave
these tests green against a page that has started to break.

**The acceptance was the mutation sweep, not a count of tests** — `tools/mutation_sweep.py`
drives `app.js` as readily as a Python file. All ten mutations are caught, and
each of the six behaviours was then re-checked against its own named test alone,
rather than against the suite, so no behaviour is covered only by a neighbour.

**The sweep found a test that could not have failed, which is the finding worth
carrying forward.** The check that a paint's generation still holds is made
after *every* await, and a run at the approval gate has two of them — so at the
gate the later check catches a stale paint even with the earlier one deleted, and
the test standing there passed against a client whose guard was gone. Only a run
in a state that fetches nothing else can falsify that claim. **And the mechanism
was not what the test's own name assumed:** what holds the poll rate down is the
check `scheduleRunPoll` makes when its timer *fires*, not the one the paint makes
when its answer lands. A superseded paint does still schedule; its timer then
finds the world moved on and does nothing. The paint-time check earns its place
somewhere else entirely — stopping a stale answer painting over the page a
curator has already moved on to — and that is now what its test asserts.

**One piece of bookkeeping in this branch was wrong and is reversed here.** The
Status checkboxes for 19A, 21 and 22 were sitting unchecked, and an earlier
commit on this branch ticked them as an oversight being tidied up. They are a
*derived view* — `views_enabled` is true, so `regen-views` writes that block from
the `status=` tag on each change-log entry, and an entry with no `status=` is
release-pending by design. Unchecked was correct, the tidy-up was hand-editing
generated output, and `regen-views` has put all four back (23 included). The
tagged entry above is how this chunk records that it landed; the box flips at
release, and nothing should ever flip it by hand.

## 2026-08-05: The live probes get a schedule, and a guard against passing for free

**Why:** the four `live_*` suites are the durable form of the
`*-api-findings.md` documents — each records a measurement the product is written
against, and a document nobody re-runs quietly stops describing the world. They
were correctly split by marker and deselected by default, and **nothing ever ran
them.** There is no CI in this repository at all, so the split was the whole of
the design and the trigger was missing.

**On push would have been the wrong trigger, and that is worth stating rather
than just not doing.** A museum API does not change because we committed: cost
would scale with our commit rate while information scales with the provider's,
so we would pay repeatedly to re-answer a question that moves monthly at most.
The two right triggers are on demand *scoped* — run `-m live_museum` when your
work touches that client, which already worked — and **scheduled**, which is what
this adds.

**Three jobs, not one stage, because the four markers do not cost the same.**
`live_museum` and `live_binary` are free and run weekly. `live_api` spends real
money and runs monthly, or on a dispatch that explicitly opts in — a manual run
must not spend by surprise because someone wanted to check the museum probes.
`llm_eval` is non-deterministic and gates nothing, so it stays on demand only.
Each marker gets its own job so a museum outage cannot mask the binary result.

**The load-bearing part is `.github/scripts/assert_tests_ran.py`, and the reason
is a trap the design walks straight into.** Every one of these tests skips itself
cleanly when its dependency is absent — `skipif(not OPENROUTER_API_KEY)`,
`pytest.skip("dezoomify-rs is not installed")` — which is right on a developer's
machine and is exactly wrong in CI. An expired secret or a failed install would
produce a completely green run that made no request and verified nothing, and a
scheduled job whose purpose is noticing change would report success for as long
as it stayed broken. So a skip in CI is read as a provisioning failure: the job
fails and names which dependency was missing.

**A hazard introduced by the xdist change three commits earlier, fixed here.**
`-n auto` is in `addopts`, and a `-m` on the command line replaces the marker
expression while leaving the parallelism in place — so `-m live_museum` alone
fires concurrent requests at a public museum API, which comes back as a rate
limit and is indistinguishable from the contract change the probe exists to
detect. Every live invocation now passes `-n0`, in the workflow and in the
documented local commands.

**`.github/scripts/*.py` waives `T20`**, a third kind of per-file carve-out in
the root ruff config: GitHub Actions raises annotations by reading `::error::`
lines off stdout, so `print()` there is the interface rather than a substitute
for logging. Written above the two existing groups rather than appended, because
that config's own comments make both lists load-bearing — one is dated debt, the
other hand-run tools, and this is neither. Recorded in the linting norm too.

**It will not fire until it reaches the default branch.** GitHub fires
`schedule` only for workflows on the default branch, so the first scheduled run
is the Monday after merge. Dispatch it once by hand after merging to prove the
wiring rather than waiting a week to discover a typo.

## 2026-08-05: The curation suite runs across cores

**Why:** ~118s with no hotspot to attack — roughly 67ms mean across the suite and
a slowest single test of 1.4s. The bulk is integration tests booting a real
uvicorn per class and waiting on it, and that wait is one this repo deliberately
will not remove: an in-process ASGI transport skips the mounted MCP lifespan and
would pass against an application that fails every real request. Parallelism is
the only lever that does not cost correctness.

**118s → 21s**, stable across four runs, `-n auto` in the curation plane's
`addopts`. The root suite is 52 tests in under two seconds and is left serial.

**One race closed first, because parallelism is what would have exposed it.**
`_free_port()` claimed a port from the OS, closed the socket, and handed uvicorn
the *number* — a window in which anything else on the machine can take it. One
suite alone almost never loses that race; eight workers booting servers
continuously from the same ephemeral range lose it regularly, and it would have
surfaced as an unexplained flake blamed on xdist rather than on the fixture.
uvicorn is now given port 0 and the port is read back off the socket it bound.
Nothing else needed isolating — `tmp_path` is per test and the catalogue is a
fresh sqlite file per test.

**A measurement recorded because it contradicts the obvious expectation.** The
mutation sweep is what you would most want this to accelerate: CLAUDE.md makes it
the acceptance evidence for every chunk and its cost is `(mutations + 1) × suite
time`. It does not help. The same ten-mutation sweep over two test files took
**67s serial against 65s parallel** — a narrow slice is dominated by per-run
worker startup, which `-n auto` adds rather than removes. The win is real only
when the slice is broad enough that each run pays something like the full-suite
cost. Both figures are in `CLAUDE.md` and `pyproject.toml` so nobody re-derives
them, and the first draft of that `pyproject.toml` comment claimed the sweep as
the main beneficiary before the measurement contradicted it.

## 2026-08-05: Chunk 19A — the run half of the browser surface

<!-- prawduct: chunks=19A | status=shipped | scope=v1-build -->

**Why:** discovery has been drivable only by an agent. Every operation a curator
needs to commission a search and watch it existed in the service layer and on the
MCP surface, and none of it was reachable from the browser — so the product's one
human interface could show what had already been accepted and nothing about how
it got there.

**What landed.** Eight routes and two screens. Intent entry with the estimate
above the button; the run view with its state in a sentence, its two tallies, its
works, its search usage and its approval gate. `GET /api/estimate`, `POST/GET
/api/runs`, `GET /api/runs/{id}`, approve/decline/cancel, and
`GET /api/runs/{id}/spend`. The routes are thin bindings over
`DiscoveryRunner` — every one is dispatch and formatting over a single service
call, which is the norm this surface has held since 10B.

**Two divergences from the MCP surface, both deliberate and both recorded in
`api-contract.md`.** `GET /api/runs/{id}` answers immediately where MCP's
`status` holds for up to 45 seconds: a model calls once and waits, a browser
polls, and because these handlers are synchronous a held request would occupy one
of Starlette's worker threads for the whole hold — starving the pool that serves
thumbnails. And the two surfaces compose their own prose while sharing their
arithmetic: the MCP notice names fields in backticks and says to call `status`
again, neither of which suits a page with buttons, but every figure on both comes
from a `RunView` property computed once. That split is aimed squarely at the
defect the previous chunk's review found — a run-level figure computed as
`len(works)` beside a view that counted provenance apart.

**`is_terminal` is on the wire rather than derived in the client.** A list of
finished status names written into the browser is the part that goes stale: a
tenth status would leave the page either polling a finished run forever or
abandoning a live one. **The mutation sweep found this branch undefended and it
was the only survivor of ten** — the value could be replaced with a constant and
nothing objected. Both directions are now asserted, because either constant
passes half the test.

**Two defects in this chunk's own client copy, found by reading the service back
rather than by a test.** The costs panel labelled the run's stored figure
"Estimated before starting"; it is written when phase 1 finishes and prices
*resolving the work list*, so a phase-2 number sat under a phase-1 heading. And
the approval gate — the actual point of decision for phase 2 — showed no estimate
at all, which is half of "the estimate at the point of decision" simply missing.
The gate now fetches it and shows the basis, which is the load-bearing half: the
figure is $0 because phase 2 asks museum APIs, and a bare zero beside an approve
button invites reading the gate as being about money when it is about the size of
the work list.

**Coverage:** 31 tests, and the acceptance criterion runs end to end against a
booted uvicorn (`test_the_run_half_runs_over_http`). A `tests/unit/test_client_vocabulary.py`
reads `app.js` and refuses a `UnresolvedReason` or `ResolutionStatus` member with
no words for a curator, so a sixth reason arrives as a failure rather than as a
raw diagnostic token on screen — the same bargain `test_design_tokens.py` strikes
with the stylesheet, and the only kind of check available for a client with no
build step. All ten mutations die.

**Hygiene fixed rather than stepped over:** `mcp/bindings.py` and one live test
carried black drift from before this chunk, and `api-contract.md` explained the
absence of write routes with "those belong to acquisition, which is not built" —
acquisition shipped 2026-08-03.

**What this chunk does not do**, so the omission is not read as an oversight: the
review grid, the verdict, image selection, and the health panel's completion are
Chunk 19B. Issue #2's component box stays open, because it names the grid as well
as intent entry and only 19B can close it.

**Critic — `rev-20260805T131544Z-6c659477`, cumulative over `dd0529a…de961bd`
(28 commits, three reviewers): 0 blocking, 7 warnings, 8 notes.** Ten fixed in
one pass, two filed, four accepted.

The one worth carrying forward is **this chunk failing a learning this same
branch added five days earlier**. `GET /api/runs/{id}/spend` shipped with no
production reader, and the figure only it carries — the family total including
every re-search descended from a run — reached no human surface, because the
costs panel read the run record's own direct spend. That is exactly "a computed
value with no production reader is an unimplemented requirement wearing the
costume of a finished one". **The learning was written, and the same shape
recurred in the next chunk anyway** — which is the second time this branch has
demonstrated that naming a failure in prose does not prevent its next instance.
The panel now reads it and the two figures are labelled apart.

Also fixed: the badge-block guard did not cover the run view's two new per-state
class axes, so a sixth `ResolutionStatus` would have painted identically to
`resolved` with the guard written to prevent that still green (R-1); `/discovery`
answered 200 and then rendered the Works grid, because routing read only the
fragment (R-3); `api.py` went from 12 handlers to 20 without adding a departure,
so "half the handlers" and "six of twelve" both became 50% against a real 30%
(R-4); a failed poll threw before it could reschedule, leaving a stale page that
read as current and never recovered (R-12); plus the README's tab list, a
presence check for `RunStatus`'s nine client sentences, a missing `date:`, and
the run-list bound written down.

**Filed rather than done, both moving code no chunk in flight is touching:**
[#80](https://github.com/brookstalley/samsung-frame-art-loader/issues/80),
extracting the collection supplement out of a 1,260-line runner that also owns
the worker threads, the wake protocol, the gate and pricing; and
[#81](https://github.com/brookstalley/samsung-frame-art-loader/issues/81),
offered works' previews having no reclaim path — twelve per run at `PENDING`,
reclaimable only on a terminal verdict, and 19A ships no verdict control, so
previews of works nobody asked for accumulate on the Pi's SD card.

**Issue #30 was settled mid-chunk and became its own chunk.** Its acceptance
required the client-coverage decision *before* Chunk 19, and 19A shipped first.
The operator chose Playwright against the real surface (recorded in
`technical_decisions.technology` with its costs); **Chunk 23** now sits between
19A and 19B to build it. The objection the issue records against a Node toolchain
is about the wrong thing and the decision says so: the Pi runs the product, not
the suite, and the shipped client stays one hand-written file with no build step.

## 2026-08-04: Chunk 22 — the collection's own answer when the gate refuses

<!-- prawduct: chunks=22 | status=shipped | scope=v1-build -->

**Why:** two real runs proposed eight works, resolved none, and told the curator
nothing about a collection that holds a great deal for their intent. A run may now
**additionally** offer works drawn from a wired collection, after the gate has
refused and never instead of it.

**A second seam rather than a wider one.** `CollectionBrowse` sits beside
`ImageSearch` because the two ask different questions: a search is given a work
and must judge whether what came back is it; a browse is given a facet, and
everything matching is by construction a work the collection holds under its own
name. There is nothing to judge, and a browse is never told which work failed —
so "no offered image is ever attached to a model-named work" holds structurally
rather than by rule.

**One POST covering every facet, and the shape is what makes fairness possible.** A named
`filters` aggregation gives each artist its own bucket with its own `top_hits`, so
the collection does the matching and labels it with the caller's own spelling.
That matters because the supply is wildly uneven — one real run's artists held 51,
12, 5 and 1 offerable works — and a single capped list ordered by a score this API
makes unreadable would have filled the whole allowance with one painter. Works are
taken round-robin across facets.

**The surname retry, and the trap under it.** A name the museum spells its own way
returns nothing, so an unambiguous surname may be retried — recovering the 24
works filed under "Vasily Kandinsky" from a run that said "Wassily". The check
that licenses it **must not inherit the browse's own filters**, and this was
measured rather than reasoned: the collection's one Antonio Martorell is a
`Graphic Design` the wall-type filter removes, so a filtered check sees only
Bernat Martorell, calls the surname unambiguous, and offers his painting to a run
that named Antonio. The unit test reproduces that asymmetry, so an implementation
that scopes it wrongly fails by offering a work rather than by looking wrong.

**The identity corpus found a defect on its first run.** Twenty real
(model proposed, museum returned) pairs, labelled by reading: the comparison
refuses "Yoshisuke Funasaka" against the museum's "Funasaka Yoshisuke" — the same
artist, family-name-first — and loses a genuine resolution. Not fixed here and
not silently dropped: the same function derives `work_dedup_key`, so sorting its
tokens changes the stored suppression key for most multi-token names, and
`attribution._near_misses` reads that key's last token as the surname. Filed as
issue #79 with an `xfail(strict=True)` holding the repro.

**Also:** the museum fake can now hold a work under a title other than the one
asked for, which the query-keyed shape could not express; the page token budget
was re-measured after `provenance` joined the row (10,842 full, 8,173 default,
both thresholds holding); and two findings Chunk 21 routed here are closed —
`architecture.md` named the wrong dependency as the cost of the fetch-path
widening, and `_iiif_base` had three callers and a docstring about one.

## 2026-08-04: Chunk 22 Step 0 — the artist facet, measured before it is built

<!-- prawduct: chunks=22 | status=shipped | scope=v1-build -->

**Why:** Chunk 22's whole mechanism rests on the model's artist field naming
artists the collection actually holds, and the evidence for that was n=2 with one
hit — both observed runs having named their artists in the intent text themselves.
The plan therefore gated the chunk on a live experiment. It ran; the claim holds;
the chunk keeps its shape and needs no facet-compile step. No code changed.

**The recorded intents could not be re-run, and the substitute is stronger.**
`phase_one_proposals.json` keeps slug labels, never the prompt texts, so
reconstructing them would have measured intents written after the fact while
reporting them as the originals. Instead: six thematic intents matching those
labels, each naming no artist, which makes every artist returned model-originated
by construction rather than by argument.

**Two measurements.** Provenance, paid, $0.0084 over six live phase-1 runs: the
model originated 12 distinct artists and the collection holds wall-appropriate,
floor-clearing work for 10. Reach, free and deterministic: 26 of the 29 artists
already in the corpus, 932 works, against a pipeline that resolves 5 of 51 named
works. Supply is abundant per *artist* and binding per *named work*, which is the
gap the chunk exists to fill.

**What Step 0 changed is the failure mode, not the verdict.** It is name-form
mismatch, not absent supply: "Wassily Kandinsky" returns nothing against the
collection's 24 "Vasily Kandinsky". The obvious repair is unsafe and was measured
rather than supposed — "Martorell" reaches two different artists, "Stella" four.
That is a requirement, not a build detail, so it was written into
`product-brief.md` and ratified before any design: a surname may be retried only
where the collection reports it reaching exactly one artist. Titian is refused by
that rule and the loss is taken deliberately, the alternative being a qualifier
vocabulary that drifts silently.

**Also settled:** the wall type set is Painting/Print/Drawing — measured to change
nothing across all 29 corpus artists — and the honest expectation is now measured
rather than predicted, both predictions having been too pessimistic (69 offerable
works for one real run, 4 for the other). Sixty-nine turns the per-run bound into
the primary selection mechanism, so it carries a stated round-robin rule rather
than an implicit one.

## 2026-08-04: #77 — a museum source's tile target, resolved rather than assumed

**Why:** no artic work could be acquired at all. `Source.url` records the object's
`api_link`, and the tile fetcher was handed that string — but `dezoomify-rs` needs
an IIIF **image service** URL, and the `image_id` that builds one was used once at
search time and never persisted. Recorded here late, and that is itself the
finding: this shipped across four commits with the architectural decisions written
into three artifacts and **no change-log entry**, in a bundle marked ready for
merge. Reconstructed from the diff at the Critic's prompting.

**The design decision, which was the open question in the issue.** Resolve at
*fetch* time through a **provider seam** rather than persisting a derived URL.
`ArticImageSearch.tile_url` asks `/artworks/{id}?fields=image_id` and joins
`data.image_id` to the response's own `config.iiif_url`, host-prefix-checked.
`Source.url` keeps the identity URL, which is what provenance means. Two
consequences follow and both are why this shape was chosen: **no migration** —
nothing persisted changes shape, so the 40 already-recorded artic sources are
fixed by the same code that fixes the next one — and the seam is the place a
second provider plugs in.

**A new module (`acquisition/tiles.py`), two new `ImageSearch` members
(`provider`, `tile_url`), and a required constructor argument.** `tile_targets` is
required with no default *deliberately*: an empty map is indistinguishable from a
correctly wired one right up to the moment a museum source fails, and by then the
failure looks like the museum's.

**A third raise-rather-record condition.** A provider in `RESOLUTION_REQUIRED`
with no resolver wired raises `TileTargetUnavailable` rather than recording a
`failed` row, because no source is at fault and a recorded failure would send
whoever reads it to the museum to look for a problem that is in the wiring. The
general rule is now stated in `architecture.md` rather than left as a list.

**A new operator prerequisite, which is the part most likely to bite.**
`ARTIC_USER_AGENT` now gates *acquiring* artic works that are already in the
catalogue, not just discovering new ones — the museum's API is open but asks
callers to identify themselves, and an object's image service can only be reached
by asking. A deployment that never set it acquires nothing from artic and the tool
result says so with the remedy.

**The security bound narrowed, and `security-model.md` says what carries the
weight instead.** The fetched URL is no longer one the deployment recorded, so
"we only fetch what we wrote down" no longer holds; the trusted-host prefix pin
plus re-running `check_fetchable` on the *resolved* address is what stands in its
place.

**Evidence:** verified against the live museum — the two masters that failed that
morning landed. A mutation sweep over the new branches caught all ten.

## 2026-08-04: Chunk 21 — which kind of nothing, and the artist out of the query

<!-- prawduct: chunks=21 | status=shipped | scope=v1-build -->

**Why:** two runs proposed works and resolved none of them with both suites green,
and nothing in the product could say why. This makes the failure diagnosable. It
does **not** meaningfully raise the resolution rate, and the measurement below says
so plainly rather than letting anyone hope otherwise.

**The RED live test first, because everything else widened what reaches the gate
it lost.** Issue #78: a nonsense query no longer scores 0.0 at the Art Institute.
Re-measured live — it returns ten real works at 54–70, *Nighthawks* at 57, with
`pagination.total` still the whole collection. So the zero-score pre-filter is
inert and **the identity comparison is the only thing between a garbage query and
a real painting**. The filter is kept (what it asserts is still true when it
fires) and demoted in prose from guard to correctness detail; the retraction is in
`artic-api-findings.md`, and the live test is re-aimed at the defence that
actually holds. The suite worked as designed: it went red on its own before
anything leaned on the stale belief.

**`unresolved_reason`, derived across two layers because neither can produce it
alone.** The engine returns its refusals beside its instances — a result it
discarded never becomes a row, so which gate turned it away is unrecoverable
downstream — and the store derives the rest from the rows the work holds. The
precedence rule is on the enum as a `depth` property rather than at the write
site, so a sixth member without one fails at definition instead of tying silently.

**`all_rejected` was missed on the first pass, and the reason generalises.** It was
ruled unreachable because rejecting an instance sets the *verdict*, not the
resolution status — true at the rejection, irrelevant, because the re-search that
finds nothing lands the same work at `unresolved` later. A test asserting that
whole path already existed. **Reachability was argued from the write site that sets
the value rather than from the paths that arrive at it.**

**The artist is out of the museum query, and the test that pinned it is replaced
rather than weakened.** The old contract said the artist "narrows" the query text.
Measured against the live API over eight Ellsworth Kelly paintings the museum
holds: the title alone retrieved **8 of 8**, the title with the artist appended
**6 of 8**, never better on any title. The replacement contract is stricter — the
request carries the title and *not* the artist — and a second test pins the half
that could have been lost quietly, that the artist still refuses a near match
above the seam. **This one is flagged for the Critic on purpose**: tests are
contracts here, and the argument that a test pinning a measured-false claim is a
recorded measurement rather than a contract should not be the builder's to accept.

**What it was worth, measured rather than claimed.** The resolution floor is now a
live test over the 51 distinct works in the real phase-1 corpus. It reads **5 of
51**, against the 4 recorded before the change. One work. That is the honest
result: the fold was a real defect and fixing it was never what moves this number.
What the five say is that supply is — four Japanese prints and one O'Keeffe, all
safely inside the public-domain boundary.

**Also:** the reason reaches the wire on all three shapes that carry
`resolution_status`, with the page re-measured because the row grew — a full
40-row page is **10,522 tokens** against its 25,000 cap, the default 30-row page
**7,933** against the 10,000 warning, both asserted by existing budget tests on a
live server. `observability-strategy.md`'s two-way split gains the third failure
mode it was structurally blind to: a record the query never retrieved emits no
event at all, so a run whose journal is all `not_the_work` should prompt a
question about the query, not about the results. And the claim that `unresolved`
means phase 1 invented the work is narrowed to `not_held` wherever it was asserted.

> **The sweep that closed that claim was incomplete, and the reason generalises.**
> It was a grep for three phrases — and those phrases came from the text this same
> diff had just written, so it structurally could not match the paraphrase the diff
> had *removed* from `phase_two.py`: "proposed something that does not exist".
> Three sites survived in that wording, one of them the docstring of the very
> function the chunk changed three lines lower. The Critic found them; the sweep
> could not have. **A grep built from the text you just wrote searches for your own
> vocabulary**, so the second pass has to use a pattern the earlier text would not
> have produced — here `grep -rn 'does not exist' curation/src curation/tests`,
> which is what found them. No corrected count replaces the old one on purpose: a
> count is a claim about a search, and the search is the part that proved
> unreliable.

**Evidence:** both default suites green (52 + 1647). The **live museum suite is
green at 10 passed**, having started this chunk at 1 failed. A ten-mutation sweep
over the new branches — the two confusable labels swapped in each direction, both
row-derived reasons swapped, precedence inverted, the reason dropped at the wire
and at the store, the artist folded back in — **caught all ten**.

## 2026-08-04: A run may offer works the curator did not name — three requirements and two chunks

**Why:** two real discovery runs proposed eight works and resolved none of them,
and no rule written anywhere said that was wrong. An eleven-agent investigation
measured the cause and the options; the operator ratified the requirement it
turned on. **No code changed — this is planning work.**

**The finding that reframed it.** Zero resolution is an *unspecified requirement*,
not a defect: `data-model.md` calls 34-of-40 "succeeded partially",
`observability-strategy.md` rules "a work the collection genuinely does not hold"
as the product working, and all eight works are in that class. But a real defect
sits underneath — the artist is folded into the free-text museum query, where its
tokens dominate scoring. Measured: three different Frank Stella titles return a
byte-identical top ten, and Ellsworth Kelly resolves **0 of 12** held works against
**10 of 12** title-only.

**What the evidence killed, and it killed the cheap options first.** Naming the
collection in the phase-1 prompt cannot work — a run whose intent already read
"held by the Art Institute of Chicago" resolved 0 of 5, and the search plugin
carries no domain restriction. Alias plumbing measured **zero lift** (4/51 → 4/51)
against the real fixture. Adding providers is not the fix either: the eight works
went to artic, the Met, Cleveland and Commons and every one returned nothing for
all eight. The partition is not which collection is wired — it is **copyright**,
and both runs asked for post-boundary work.

**Ratified by the operator, and both answers are recorded where their rules live.**
*A run may offer works the curator did not name* — adjacent, similar and derivative
works are welcome, bounded and labelled, offered only after the gate refuses. That
is `product-brief.md`'s own Vision ("works the curator has not seen and could not
have named") finally reaching phase 2. Scoped to **artist adjacency** for the first
build, because it is the only facet reproduced live; style, classification and
period miss on ordinary spellings, and relevance-ranking returns *American Gothic*
for a Dutch still-life query. And *rights: record, show, never gate or filter* —
constraint 13 extended to works the system chooses, with its honest cost stated.

**Three requirements written:**

- **`unresolved` must say which kind of nothing** (`data-model.md` § CandidateWork).
  One value per route to `unresolved`, none of them interchangeable, with a
  precedence rule stated rather than left to the write site: the *deepest* gate any
  record reached wins, because "the collection holds this, too small for your wall"
  is actionable and "something somewhere did not match" is not. **This narrows a
  claim the repo asserts in six places** — that `unresolved` means phase 1 may have
  invented the work — to `not_held` alone.

  **One route was missed on the first pass and is recorded rather than smoothed
  over.** `all_rejected` — the work holds instances, the curator turned down every
  one, and the re-search found nothing to add — was ruled unreachable because
  rejecting an instance sets the *verdict*, not the resolution status. True at the
  rejection and irrelevant: the re-search that finds nothing lands that same work
  at `unresolved` later, `data-model.md` said so already, and a test asserting the
  whole path existed throughout. **Reachability was argued from the write site that
  sets the value instead of from the paths that reach it**, which is the reusable
  half.
- **The resolution rate is a measured number with a floor** (`product-brief.md`
  § Success Criteria), over a fixed corpus, with the *test* as the authority for
  the figure and this repo's habit of naming tests that do not exist called out:
  the mechanism is recorded as **owed**, not described as live.
- **A run may offer the collection's own answer** (`product-brief.md` flow 2), with
  four conditions on every offered work and the seam that keeps "derivative" from
  becoming a loophole: a study offered *as itself* is welcome, the same object
  offered *as* the named work is the near-match the flow forbids.

**Also recorded:** `nonfunctional-requirements.md` § The Supply Horizon — the
measured post-boundary cliff, and the fact that the product today ships the
"museum/public-domain only" alternative that `project-state.yaml`'s integrations
decision **explicitly rejected**. Recorded rather than resolved, at the operator's
call. `api-contract.md` gains the row's new field *and the arithmetic owed with
it*: the 10,200-token page was measured without it and the ceiling already runs 2%
over.

**Two chunks planned, sequenced before the browser surface.** Chunk 21 makes the
failure diagnosable (and explicitly does *not* raise the rate — 4/51 → 5/51);
Chunk 22 is the substantive change. 21 first because without it nobody can tell
whether 22 worked. Chunk 22 carries a **step 0** that may reshape it: the claim
that the model's artist field is grounded rests on n=2 with 1 hit, since both
observed intents named their artists themselves.

## 2026-08-04: Two Critic rounds, and a finding that had to be partly retracted

<!-- prawduct: chunks=03,04,05 | status=shipped | scope=v1-build -->

**Why:** the bench round closed three chunks and then failed to sweep after
itself. Two Critic rounds and a backlog subagent found the same shape repeatedly —
a closure asserted in the artifact that owned it and nowhere else — plus one
finding that was over-claimed and is now partly withdrawn.

**The retraction first, because it is the one that would have cost someone time.**
`upload()` reporting failure on uploads that succeeded is real and stays: a
default-window upload failed twice, a wide-window upload succeeded, and an upload
that reported `None` was observed to have landed. **Three things recorded around
it were wrong.** The raise was attributed to an `assert data` "on the
acknowledgement" at `async_art.py:434` — that line is inside `get_thumbnail`, and
`upload()`'s acknowledgement path does not assert at all. The two failure shapes
were attributed to the argument form, which the source does not support. And
"8.39 s, 84% of the default" divided a whole-call wall-clock by a budget that
governs only part of it — a ratio never computable from what was measured. **The
raise site is now marked as needing one instrumented run rather than asserted.**
The lesson generalises: a measured behaviour and an explanation of it are separate
claims, and only the first was earned.

**The journal bound was aimed at a journal that does not exist.** Chasing the first
round's complaint about *evidence* — `systemd-analyze cat-config` proves a file
parses, not that a directive binds — turned up the reason it could not have bound:
Raspberry Pi OS ships `Storage=volatile`, so the journal is a tmpfs in RAM and
`SystemMaxUse=` governs a persistent journal this machine has none of. The drop-in
now sets `RuntimeMaxUse=` too, evidenced by journald's own startup line moving
from `max 156.1M` to `max 256M`. **Two standing facts fall out**: the journal does
not survive a reboot, which is exactly when it would be read; and logging never
wore the card, so `operational-spec.md`'s "exactly two" continuous-write paths were
one. `Storage=persistent` was **declined** — the operator accepted losing the
journal across a reboot rather than moving logging onto the card.

**A deferral rationale was withdrawn rather than defended.** The bench entry said
the upload defect could wait because the display binding does not exist and the
2024 loader is being retired. The loader is what runs the wall, `tvart.py:140`
passes no `timeout`, and `tvart.py:253` re-selects anything lacking a content id —
so the cost of leaving it is live duplicate uploads. It is still unfixed; the
honest reason is scope, not harmlessness.

**Swept, having been asserted in one place and not carried:** the 3.12 fallback
(decision line, norms row, learnings, an integration-findings file); the 42-inch
panel (three artifacts, two source files, two tests — worked examples deliberately
left at 42" because re-cutting them would lose the check that the arithmetic
reproduces); issues #9 and #13 recorded as open gates after closing; the build
plan's bench prose and confidence register; `deploy/README.md`, which both recorded
the resolver check and said it still needed doing.

**Filed rather than fixed:** issue #74 — correcting the panel diagonal does not
invalidate canvases already composed at the old one, because rendition staleness
compares pixels and both panels are 3840x2160. The blind spot is wider than the
diagonal: `MAT_WIDTH_INCHES` and `MAT_BOTTOM_WEIGHT` are equally unrecorded, so it
is a missing column in the staleness key rather than a one-off.

## 2026-08-04: The bench answered three chunks, and the television answered back

<!-- prawduct: chunks=03,04,05 | status=shipped | scope=v1-build -->

**Why:** three chunks had been parked behind bench access since the plan was
authored, each holding an assumption a later chunk depends on. A rebuilt Pi and a
live television closed all three in one sitting. No product code changed — the
deliverables are recorded findings, one deployment drop-in, and one packaging fix.

**The IT8951 assumption resolved positively, and the feared problem never
existed.** The driver builds from its pinned commit and imports on Python
3.13/aarch64 under uv's PEP 517 isolation. The premise — a 2023 `setup.py`
importing Cython without declaring it — does not hold at that commit, which
declares it properly. So the whole remediation branch the chunk budgeted for
(build-requires override, vendoring ~1,500 lines, re-pinning) is dead, and the
3.12 fallback can be retired.

**What actually blocks a rebuilt Pi is `python3-dev`, which nothing declared.**
The install fails building `rpi-gpio` — not IT8951 — with
`fatal error: Python.h: No such file or directory`, pointing a reader at the wrong
package entirely. Added to the apt line in `requirements.txt`, in a file whose own
comment says a dependency nothing declares is one nobody installs until an import
fails.

**The television verification found a defect worse than the one it was looking
for.** `upload()` returns falsy or raises a bare `AssertionError` on uploads that
*succeeded* — at the default `timeout=10`, observed twice, with the image on the
set while the caller is told it is not. *(The mechanism this paragraph originally
gave — a named raise site, an argument-form rule, and "8.39 s, 84% of the default"
— is retracted; see the entry above. The behaviour is unchanged.)* A retry loop turns that
into duplicates on the wall. Filed as issue #73. **This is live on the loader
running the wall today** — `tvart.py:140` passes no `timeout` and `tvart.py:253`
re-selects anything lacking a content id — so it is not deferred to a future plane,
only unfixed in this commit.

The generalisable rule, now stated where a builder will find it: **this library's
return values are not trustworthy in either direction — confirm against the
television's own content list.** Deletion already worked that way because
collapsing *failed* into *unconfirmable* was the original defect; upload has the
mirror-image bug and is owed the same treatment.

**Two of the three registered image-changed callbacks are dead wire**, established
by provoking a real selection rather than by reading source: only `image_selected`
fires. The other two are slideshow-advance events, and host-driven rotation never
advances the set's own slideshow — so the old/new API split this product worried
about costs it nothing.

**Detecting art mode turned out to need the answer nobody would guess.**
`PowerState` reports `'on'` for both art mode and normal TV, and `get_artmode()`
can only ever confirm the positive case because reaching it requires a call that
hangs when art mode is off. What works in both directions is the presence of an
`isHost: true` client in the art channel's connect frame — the set's own art
application. Recorded with the transitions explicitly marked as a sketch rather
than a map, because only one starting state was exercised.

**Firmware auto-update can be disabled, and is.** The set is held at 1310 with
1400 offered and declined; the standing recommendation is to stay, because the
update is one-way and every measured figure above is firmware-scoped. That closes
the last open question in `security-model.md` and turns the vendor risk from an
exposure into a decision. It does not lower the risk level: the vendor still owns
the capability, and un-taken firmware now accumulates.

**The journal is bounded on the machine**, at 256M, in a committed drop-in rather
than only on the box — which is how the last unit file came to exist nowhere but a
card. The reasoning behind the requirement was also corrected — though **not far
enough, and the follow-up commit reversed this paragraph's premise as well.** It
read that systemd caps its own default at 4G rather than growing with the disk. It
does, but that is beside the point: Raspberry Pi OS ships `Storage=volatile`, so
this journal is not on the filesystem at all, the `SystemMaxUse=` shipped here
bound nothing, and logging never wore the card. See the entry above.

**Corrected while here:** `TV_PANEL_DIAGONAL_INCHES` read 42 against a 50 inch
set — not a typo but an unchanged template default, which is the worse failure
because it produces a running system that quietly mis-sizes every judgement about
whether a work is big enough for the wall. The set names its own size in
`modelName`, so this is checkable rather than merely documentable — **though no
check was built or filed, so that sentence advertises a capability this commit did
not deliver.** Correcting the value also does not invalidate canvases already
composed at 42", which is issue #74.

**Not done:** the upload defect is filed rather than fixed. The original wording
here said the fix could wait because "the display plane's binding does not exist
yet" and the 2024 loader is scheduled for retirement — **that rationale is
withdrawn.** The loader is what runs the wall today and takes the defective path,
so the cost of leaving it is live duplicate uploads, not a deferred cleanup. It
remains unfixed in this commit; the reason is scope, not harmlessness. Two
requirements
also surfaced and were left unwritten rather than designed in passing: when a
display process should begin and suspend rotation, and whether the set can offer
any interaction of its own.

## 2026-08-04: The card stays, and the risk moves to the backup that does not exist

<!-- prawduct: status=shipped | scope=v1-build -->

<!-- No `chunks=`: this is issue #13's decision, recorded off-bench. Chunk 03 owns
     it as one of three deliverables and the other two need the bench, so the
     chunk is not shipped and no checkbox flips. -->

**Why:** issue #13 had blocked Chunk 03 since the plan was authored, and the
decision gates deployment paths rather than following them. It needed no hardware,
so it had no business waiting for bench access.

**Decided: the SD card stays** — no USB SSD, no SSD boot, no network storage.
`ART_ROOT` and `catalogue.sqlite` remain on the 128 GB card, and the NAS is the
backup destination only, which is the role `operational-spec.md` already gave it
on 2026-07-20.

**The reasoning is the write profile, not the medium's reputation**, and that
distinction is what the recorded rationale had to get right. The image tree is
additive and written once — works are added and rarely deleted or rebuilt — so
total bytes written is bounded by the size of the collection rather than by churn,
which puts a full card on the order of a hundred gigabytes across years. That is a
small fraction of any modern card's endurance. **What wears a card is small writes
that never stop, and this product has exactly two:** journald, capped by the
`SystemMaxUse=` deliverable Chunk 03 still owes, and the display heartbeat, which
had no stated cadence at all until this entry's other half.

*An earlier draft of this rationale leaned on free space — a 128 GB card holding
10 GB has enormous room to wear-level. The operator corrected the projection to
roughly 70% full, which weakens that argument considerably and leaves the
conclusion untouched, because the bound that matters is total writes and not
headroom. The artifact records the argument that survives.*

**`ART_ROOT` on network storage was raised and rejected**, and it is worth keeping
why, because "the NAS has RAID" is a good instinct that this layout defeats.
`catalogue_path` resolves to `art_root / catalogue.sqlite`, so moving `ART_ROOT`
moves the database — onto a filesystem where advisory locking is unreliable and
where WAL, the mode that would otherwise reduce the exposure, cannot run at all
because it requires shared memory between processes on one host. It would also put
the wall's uptime behind a second machine, since the display plane polls the
manifest and reads the image tree continuously, and it would rest the manifest and
heartbeat channels' atomic write-and-rename on semantics a network filesystem
decides rather than the kernel.

**The risk is now decided rather than closed, and the artifact says so.** The
decision accepts card death every few years, which makes the backup and restore
path this risk's entire mitigation instead of a complement to it — and issue #14 /
Chunk 20 is unbuilt and sits last in the build order. Writing "mitigated" would
have been the green dot this product's own observability strategy refuses. Nothing
on the Pi today survives the card.

**The heartbeat interval was undefined, and the storage decision is what made that
matter.** `observability-strategy.md` said the display plane writes its status
document "on a regular interval" and named no number; Chunk 13 owns the writer and
its entry named none either. On a Pi with no SSD that number *is* the wear budget,
and a writer borrowing the manifest poll's ~1 s cadence by symmetry would commit
~86,400 write-and-rename cycles a day to the card in perpetuity. Set to **60
seconds**, recorded as a vetoable decision at the point the contract is stated.
Bounded on the other side by the rotation interval — the document names the work
*currently* displayed, so a heartbeat slower than the wall would report works it
had already left. 60 s sits under the 180 s rotation default with margin. It costs
no fidelity because the panel reports heartbeat age absolutely rather than judging
it against a threshold, which is a property the health surface already committed
to for its own reasons.

## 2026-08-04: A retry cannot cost a work its image — the other half of the promise

<!-- prawduct: status=shipped | scope=v1-build -->

<!-- No `chunks=` on purpose: this entry is issue #67 and the review round that
     followed it, not a chunk's build. 18A and 18B carry their own entries and
     their own checkboxes; naming a chunk here would flip a box a second time or,
     worse, flip one for work nobody did. No `release=` either — this product
     tracks no version in the change-log and ships no release-notes view, so the
     only entry carrying one is the format example in this file's header. -->

**Why:** the surface told a curator that retrying a fetch was safe, and for one of
the two ways an attempt can end that was false. Issue #67, filed by this branch's
own cumulative review, impact L.

**Staging covered the fetch that fails; nothing covered the fetch that succeeds
partially.** A tiled fetch returning most of its tiles is a *normal outcome* — it
yields a usable image, `partial_tiles` is recorded, and the work goes on the wall —
so it arrived at promotion by the same path a complete fetch does and overwrote
whatever the work was displaying. `retry_acquisition`'s own tips made the trap:
one recommended retrying *after a partial fetch*, the next reassured that "a
failed attempt replaces nothing". Both true, and together they read as a promise
the code did not keep. `Source.last_fetch_status` was written and displayed the
whole time, and read by no decision.

**`Original.fetch_status` is a new column, and the obvious derivation is why.**
The temptation is to read the held image's quality off `Source.last_fetch_status`
for the source that produced it. That is wrong in a way that only shows up on the
third fetch: the column holds the source's *most recent* attempt, so one failed
re-fetch overwrites it to `failed` while the held original — protected by staging
— is still the complete image from before. A guard reading it would conclude "held
quality: failed", treat anything as an improvement, and let a partial overwrite a
complete master. The fact belongs to the bytes, not to the source.

Stored rather than derived, in a table whose one other stored-verdict candidate
was deliberately removed: `display_fit` came off `Original` because a verdict about
panel geometry goes wrong when the TV changes. `fetch_status` is a fact about an
event that already happened, which no later deployment can falsify — the same
footing `width` and `height` stand on. The artifact now says so at the row, because
a reader who has just absorbed the `display_fit` reasoning is owed the distinction.

**Three judgement calls, each recorded where its rule lives** (constraint 16,
`data-model.md`). The comparison reads **only** complete-versus-partial — pixel
count is not consulted, because a complete fetch from a smaller scan is a
legitimate re-acquisition and refusing it would second-guess a choice acceptance
already made. **Two partials replace each other freely**, since neither is
authoritative and no tile count survives into either row to compare; the
alternative freezes a work at the first gappy image it ever got. And **a null
`fetch_status` counts as complete** — every row a real deployment already holds is
null, including all 41 seeded works, and the permissive reading would surrender
exactly the corpus the mat engine is judged against.

**A refusal is not a failure, and the difference is load-bearing.** The new
`kept_held` outcome writes nothing at all: no `record_fetch`, so the source keeps
the status of the fetch that produced the image being kept — the very fact the next
comparison reads. Recording it as a failure would also stamp `failed` on a source
that answered correctly and send whoever read it to a museum that is working. The
tiles survive too, so asking again is still cheap.

**The seed records `None`, which is the honest answer rather than a gap.** It
adopts files the 2024 pipeline left on disk; it never fetched them and nothing
observed whether their tiles arrived. Writing `ok` would invent the fact, and
`partial_tiles` would mark the whole hand-tuned corpus replaceable. **A mutation
sweep found this branch undefended** — the seed's value was asserted by nothing,
and both wrong answers passed — which is the fifteenth mutation of fifteen and the
only survivor of the first pass.

**The api-contract gained a compatibility row it had been missing.** Adding a
*value* to a result field that reads as an enum is not the same as adding a field:
an unknown key is ignored, while an unknown value in a key the reader switches on
falls through every branch, so the caller proceeds as if nothing happened. It is
Additive here only because every outcome is paired with a `notice` in prose — a
client that understands no outcome values still relays a sentence. The rule now
states that condition rather than leaving the next person to guess.

**The cumulative round: 0 blocking, and the one it found in this fix was real.**
`rev-20260804T105746Z-fc44baaa` returned 19 findings over the whole 18A+18B+#67
bundle. **The tally below is the rendered one and supersedes any count in this
prose**: accepted 11, fixed 7, waived 1. An earlier draft of this paragraph read
"17 accepted, 2 filed, nine fixed", which sums past 19 — it was counting
dispositions and outcomes in one list. The renderer decomposes them, and eight
findings carry BOTH a disposition and a resolution fact from the verify round, so
the verify round's answer is the current one for those eight.

**Two of them were defects in the #67 fix itself**, which is the pattern this
branch keeps producing and is worth naming again. The guard refused on the
strength of the catalogue row alone and never checked the file was there — so a
row that outlived its bytes, which is the product's own documented restore state,
deadlocked: `retry_acquisition` answered `kept_held` while nothing was on disk and
`regenerate` said re-acquire it first, the two actions pointing at each other. And
the comment justifying the refusal path named the wrong row: it claimed skipping
`record_fetch` protected "the fact the next comparison reads", when the comparison
reads `Original.fetch_status` and `record_fetch` touches only the `Source`. **The
comment was wrong in a way that made the behaviour wrong too** — a refusal now
*does* record the attempt, because `last_fetch_status` means the source's most
recent attempt and skipping it left `sources` showing a date older than the retry
the curator had just been told to make.

**Three more were latent and cheap**, all against claims the code already made.
`dezoomify._discard` alone among its three siblings let an `OSError` escape, so a
failed unlink ended the whole acquisition pass — against that module's own
docstring promising one bad source never does. `_record_success` took `status` and
`outcome` as a pair that had to agree, making `status=ok, outcome=partial`
representable; `outcome` is derived now. And `set_mat` sent a curator's colour to
the strict parser while the model's went to the lenient one, so **the product
accepted `#ABC` from a model and refused it from a person**, on a parameter
documented only as "a hex triplet".

**One finding was a comment that taught a false pattern.** Three `curation.config`
imports in `services/container.py` were deferred to function scope to break an
import cycle. Walking config's module-scope import graph shows no such cycle — it
reaches `manifest.builder`, `manifest.heartbeat`, `services.display_fit` and
`services.runner`, and none of those reaches `container`. Hoisted, with the
correction recorded rather than the comment quietly deleted.

**Dispositions, rendered rather than hand-counted:**

**rev-20260804T105746Z-fc44baaa** — chunk 18B, 2026-08-04T11:20:12Z

| Finding | Severity | State | Detail |
|---|---|---|---|
| R-1 | warning | fixed | Fixed. The guard now tests art_root/relative_path before refusing, so a row that outlived its file no longer blocks the re-acquisition preparation reports as needed. Test + 2 mutations. |
| R-2 | warning | fixed | `brookstalley/samsung-frame-art-loader#69` — owner ruling: Renders as 'fixed' because the verify round verified this finding's OWN remedy (b) — it offered 'either record a SpendRecord, or record the deferral explicitly so the category has a stated owner instead of reading as implemented', and data-model.md § SpendRecord now carries that deferral. The finding is discharged; #69 is OPEN and this PR deliberately ships it open, tracking the code half, which was never what the finding required. Contrast R-15, the same filed-to-an-issue shape but WAIVED: there nothing in the tree changed at all, so the filing is the whole answer. |
| R-3 | note | accepted | Accepted, not fixed. Its trigger is a panel-geometry change, and the display chunks (12/13) are bench-blocked, so nothing can exercise the fix. Rendition records target pixels only, so covering the TV_PANEL_DIAGONAL_INCHES variant needs mat geometry on the row — a data-model change that belongs with the panel work rather than ahead of it. |
| R-4 | note | accepted | Accepted as covered, with the attribution corrected (2026-08-04, verify round): the three flagged lines are the pre-existing 'raw/' bullet under 'Data and cache contract', which this branch narrowed rather than authored — the narrative was there at the base. Either way the outcome stands: the file-wide problem is issue #26 (416 findings, stage:ready), which owns the move to learnings-detail.md, and fixing three lines here would leave 413. |
| R-5 | note | accepted | Accepted, and the asymmetry is defensible as it stands: the colour a curator asked for is recorded, and it applies once the work is acquired. The finding calls it genuinely ambiguous. Reversing the order would discard a stated preference because of a fetch that has not happened yet, which is the worse default for an append-only history. |
| R-6 | warning | fixed | Fixed. The diagram gains a PreparationService row with its MatEngine seam, and the DiscoveryEngine annotation no longer claims to be the seam every paid call sits behind. |
| R-7 | warning | fixed | Fixed, and the finding was right about the reasoning rather than only the wording. A refusal now DOES call record_fetch: last_fetch_status means the source's most recent attempt, and the guard reads Original.fetch_status, so recording it cannot weaken the guard and keeps the column's documented meaning true. Comment restated, test inverted, mutation-checked. |
| R-8 | warning | fixed | Fixed. Verified by walking config's module-scope import graph: curation.config does not reach services.container. The three imports are hoisted and the comment now records that the cycle never existed. |
| R-9 | warning | fixed | Fixed. Closed with the model, the date, the measured price and the trail, in the same shape as the limit_remaining entry closed earlier today. |
| R-10 | warning | fixed | Fixed. The four detail headings are now character-identical to their index rules; a script confirms zero detail headings without an index rule. |
| R-11 | note | accepted | Fixed. outcome is derived from status inside _record_success and the parameter is gone, so the mismatched pair is unrepresentable. Mutation-checked. |
| R-12 | note | accepted | The concrete half is fixed under R-1: _would_lower_quality now checks the file exists, so the dangling-row deadlock it describes is closed. The residual — making both services answer 'does the work really hold this' with one shape — is a refactor with no failing behaviour behind it now, and is better done when a third caller exists to say what the shape should be. |
| R-13 | note | accepted | Fixed. dezoomify._discard now catches OSError and logs, matching its two siblings, so an unlink failure no longer escapes tile_fetch and ends the pass against the module's own docstring. Test + 2 mutations. |
| R-14 | note | accepted | Fixed. set_mat normalises through format_hex(parse_hex(...)), so the product gives one answer to 'what is a hex colour' whoever asks. ColorError is translated to ServiceError so a malformed value stays a clean refusal. Two tests over the wire, 2 mutations. |
| R-15 | warning | waived | `brookstalley/samsung-frame-art-loader#70` |
| R-16 | note | accepted | Fixed. The cost row names the model, the date and the measured price, drops the dangling see-also, and retires the ai.py 5x-retry warning the new engine does not do. |
| R-17 | note | accepted | Fixed. The foreign-API register now states the argv invocation as it is and points at dezoomify-cli-findings.md, with the correction noted so a security re-derivation does not restart from a shell surface that never existed here. |
| R-18 | note | accepted | No action required — a clean cross-check result, recorded as evidence rather than as a defect. |
| R-19 | note | accepted | Acted on. #67 is closed as shipped against this branch with a ship-note; #60 and #11 were already closed. |

**19 findings** (8 warning, 11 note) — accepted: 11, fixed: 7, waived: 1.
**8 answered twice** — recorded as both resolved and dispositioned; check which answer is current.

**The verify round: 0 blocking, 0 warning.** `rev-20260804T122615Z-115f84e3`
read the delta and settled all eight prior warnings — **seven verified fixed,
one waived**: R-15 is confirmed *not* fixed (14 log sites under `acquisition/`,
none carrying `extra=`) and stands on the filing to #70, which is the honest
disposition rather than a claim the tree does not support. It checked the two
things most worth checking about the fixes themselves: that `record_fetch` on the
refusal path cannot weaken the guard — `last_fetch_status` is read by display
paths only, by no decision logic — and that hoisting the config import adds no
import-time side effect, `load_dotenv()` being called inside a function.

**Its two notes were both mine, and both were fixed rather than accepted.** The
`[[slug]]` cross-references I put in `learnings-detail.md` were a link syntax from
a different tool's conventions — the repo's only two, and neither resolved to
anything; they now quote the referenced rule by its heading, which is the file's
own idiom. And the R-4 disposition credited this branch with narrative it had only
narrowed: the three record-lint lines are the pre-existing `raw/` bullet. The
disposition **fact** is corrected and the table above re-rendered from it, rather
than the prose being edited to disagree with the record it was generated from.

Suite: **1599 curation + 52 root green**, in random and fixed order, plus the live
checks behind `-m live_api` and `-m live_binary`. Twenty-three mutations across the
two rounds, all caught.

## 2026-08-03: Preparation — a mat that says who chose it, and a bar the corpus states

<!-- prawduct: chunks=18B | status=shipped | scope=v1-build -->

**Why:** an acquired work was bytes on disk with no way to reach a wall. It now
gets a mat colour with recorded provenance and a 4K canvas composed against the
configured panel, and enters the manifest.

**The fallback is the point, not the model.** The 2024 pipeline substituted a
darkened dominant colour whenever the vision model failed and recorded nothing, so
a considered colour and a mechanical one were indistinguishable in the data
forever after. Every path through the new engine sets `MatColor.method`, and the
tool's own notice says out loud when the model did not choose. That matters more
than it sounds: an unenforced schema makes an unusable answer an ordinary Tuesday,
and probing produced empty content, content truncated mid-string, and a hex
triplet with no leading `#`.

**The compositor draws the box the config already computes**, recovering the
margins from it rather than recomputing them from inches and a weight. A second
derivation is the only way the canvas and the readiness verdict could disagree
about where the mat ends — by the pixel or two that rounding order moves, which no
test would have caught and no surface would have reported.

**Decisions settled at build:**

- **The vision model is `qwen/qwen3.7-flash`**, on the operator's stated
  criterion — cheapest that does the job, with evals deferred. Thirty-one probe
  calls over real corpus images: it answered every one usably where no other
  candidate did, and both cheaper models proposed a near-white mat over a Rothko
  and a Mondrian, which is the one failure that glares on an emissive panel.
- **`MAT_MAX_OUTPUT_TOKENS` is a correctness value.** A reservation that does not
  clear a model's *reasoning* budget returns empty content billed in full. It
  reads as a model failure and is a client misconfiguration, so the diagnostic
  names the setting rather than blaming the provider. Raised to 8,000 when a
  corpus run hit the ceiling intermittently at 2,000.
- **The corpus is `all.json`.** Chunk 06 deferred extracting the 41 colours to
  `tests/fixtures/mat_corpus.json`; this is the decision not to. A copy is a
  second place they live, free to drift silently from the one the seed reads.
  *(Propagated 2026-08-04, and worth recording as a miss: the decision reached
  the code and this entry and stopped there. `nonfunctional-requirements.md`
  § Output Quality still promised the file would be kept only "before the
  regression fixture is extracted", Chunk 06's entry still carried the fixture as
  a deliverable and as an acceptance criterion that could never come true, and
  issue #11 still instructed the next builder to create it. All four now agree.
  The shape to keep: a decision that DESCOPES something has to be walked back
  through every artifact that promised it, and the promising artifacts are never
  the one you are editing when you make the call.)*
- **The colour arithmetic is first-party.** 2024 reached CIE LAB through OpenCV,
  NumPy and scikit-image — three packages on a memory-capped Pi to do thirty
  lines. CIEDE2000 rather than Euclidean CIE76, because mats cluster in the dark
  low-chroma corner where the two disagree most, and the number is read by a
  person deciding whether an engine regressed. Verified against the published
  Sharma reference set.

**Found and fixed, from 18A:** `art_catalogue` declared `openWorldHint=false`
while `retry_acquisition` was already fetching arbitrary museum URLs — understated
to every client that reads the hint. The contract test that should have caught it
asserted the old *set of tools* rather than the property, so it passed. It now
names both sides. The generalisable shape: **an annotation is per tool, so adding
an action can falsify a flag the tool has carried correctly for months**, and
nothing in the new action's own review would look at that flag.

**Also found by its own guard:** `PreparationSettings` takes the panel and the
artwork box as two fields, and a mismatched pair yields a negative mat that pastes
the artwork off the canvas — written, recorded, carried into the manifest, first
visible on the wall. The guard added for it caught the mismatch in this repo's own
test on its first run.

**Not settled, and enqueued rather than assumed:** the acceptance criterion's
other half is "the operator's corpus look finds no regression", which is
explicitly subjective. A full run is done — 33 of 41 works compared, median
CIEDE2000 9.8, the engine's median lightness 20.8 against the corpus's 20.7, one
work over the darkness bar — and `tools/mat_corpus.py` regenerates the sheet.

**The review rounds are part of the record.** The cumulative pass returned 22
findings, one blocking, and two reviewers independently found the same top one:
`regenerate` was published as free in three places while the first call on every
acquired work minted a mat with a paid model call. The fix for *that* then
produced two more — a translation that swallowed `compose`'s write half, so a
full disk reported an unreadable original; and new caller-facing fields asserted
by nothing, on a surface that had just started claiming "every answer reports
cost_usd". Four acquisition findings were filed as issues #65–#68 rather than
widening this diff into Chunk 18A.

1573 curation + 52 root green, plus five live checks against the real API behind
`-m live_api`. Twenty mutations over the new branches, all caught; the single
survivor was a floor a zero-factor test could not reach, because `0.0 × L*` is
already zero.

## 2026-08-03: Acquisition, and a probe that rewrote the fetch path before it was written

<!-- prawduct: chunks=18A | status=shipped | scope=v1-build -->

**Chunk 18 was split into 18A and 18B** at the operator's call, at the seam the
data model already draws: everything in 18A produces an `Original`, everything in
18B consumes one. The halves share no foreign interface, no entity and no failure
mode, so neither Critic round reads the other's code — the same reason 08, 14 and
16 were split, and this chunk was larger than any of them.

**Three claims in the chunk entry were stale and were corrected rather than
inherited.** The bottom-weight carried finding had been settled on 2026-08-01
(`MAT_BOTTOM_WEIGHT`, pinned by `test_config.py`). "The legacy `shell=True`
invocation is not ported forward" described code that does not exist —
`image_utils.py` has been argv-based since `4fddf36`. And the acceptance criterion
ended "and reaches the wall", which nothing here can meet: the display plane is
Chunks 12 and 13, both bench-blocked. That half is descoped explicitly rather than
left as four fifths of a criterion that reads met.

**Step 0 changed the design rather than confirming it**, which is the thing worth
carrying forward. `dezoomify-cli-findings.md` records the probe against 2.18.1.
The load-bearing finding is that **exit codes classify nothing**: `0` also means
"read no input and wrote nothing", and `1` covers total failure and partial tiles
alike — the two outcomes the data model holds apart. So the fetch path classifies
on the produced file, which is the zero-byte guard answering both questions at
once. Two further behaviours would have been inherited as bugs: the saved-file
name is announced on **stderr**, where the 2024 code parses stdout and would
`IndexError` on every success, and the 2024 code **deletes a usable partial image**
on any non-zero exit, which made `partial_tiles` unrecordable in practice.

**The probe also fired a trigger this repo had written down in advance.**
`security-model.md` said its assessment must be *re-derived* if a tool fetches an
arbitrary URL. Acquisition does, with a binary whose input argument reads local
paths as readily as URLs and which reaches loopback. Bound 2 is re-derived rather
than extended: it no longer rests on the capability being absent, but on three
weaker properties — a fetch is reachable only through a URL a curator already
accepted, scheme and resolved host are checked before invocation, and the binary
never receives a shell or an inherited stdin. The residual an accepted-but-poisoned
candidate leaves is stated rather than implied.

**Hosts are judged by what they are, never by which they are.** A registry of
permitted hosts would make every new gallery a code change and quietly re-scope a
product whose provider vocabulary `data-model.md` deliberately leaves open, so the
check is "publicly routable" — loopback, link-local, RFC1918 and `.local` refused.

**Issue #60 is settled where its rule lives.** `art_catalogue(action='sources')` is
its own action rather than a field folded into `get`: folding was compatible and
would have cost no round trip, but `get` is the payload every list-then-detail hop
pulls and provenance is not what that hop is for. It reads through the same
`CatalogueService.list_sources()` the browser detail view uses, so no second
projection of "a work's sources" exists to drift.

**The carried finding about the caches is closed with a rule, not a chore.**
`tile-cache/` earns its disk only while a fetch might be resumed, so tiles are
cached per source and reclaimed the moment that work holds a complete image — and
kept when it does not, which is exactly when a retry wants them. `api-cache/`
needed no rule: nothing creates it. That second half corrected four artifacts and
`learnings.md`, all of which had been listing it as an upstream artifact to
transport.

**What the mutation sweep caught, and the one thing it got wrong.** Two of the new
tests could not fail: one asserted stdin was closed using a fake that returns
immediately under pytest either way, and one asserted a stale destination is
cleared using a fake that overwrites happily where the real binary refuses. Both
are now able to fail. The sweep then reported the IPv4-mapped-address unwrap as
unreachable, so it was removed — and `ipaddress` turns out to classify
`::ffff:8.8.8.8` as `is_reserved` on 3.12 and `is_global` on 3.14. The branch
defends against an interpreter change rather than an input, so no mutation over
inputs can kill it. Restored, with the reason written where the next reader finds
it before deleting it again.

**The Critic found five blockers, and the review round after the fix found a
sixth that the fix itself introduced.** R-1 and R-9 were the same defect from two
independent reviewers: a failed *retry* deleted the master the work was still
displaying while its `Original` row went on naming the file, and the surface
promised the opposite in two places. Both fetch paths now stage and the service
promotes only after the bytes measure as an image — one rule in one place, because
the guarantee had held on the direct path by accident of where staging happened to
live. The staging fix then named the staged file `<name>.partial`, and
**dezoomify-rs picks its output encoder from the extension**: probed at 2.18.1
that exits 1 with "was not recognized as an image format" and leaves a zero-byte
file, so every tiled fetch would have failed in the deployment against a green
suite. Staging is `<stem>.partial<suffix>` now.

**The gap that let it through is the durable lesson, and it is closed.** Every
stand-in for the binary is a shell script that writes to its last argument
whatever the argument is called, so no fake could ever witness a decision the
binary makes *from the filename*. `tests/live/test_dezoomify_contract_still_holds.py`
drives the real tool behind `-m live_binary`, beside the ARTIC and OpenRouter live
suites and on its own marker for the same reason they are separate: it costs
nothing but needs the network and the binary.

**Constraint 10 needed no code.** `description_markup` already existed in
`services/fields.py` and was already wired into `add_artwork` — a second one was
started before a truncated grep was noticed to have hidden the first. What the
constraint actually lacked was evidence, so the 41 real corpus descriptions are now
asserted to normalise and to **parse as XML**, which is Pango's real bar and what
no existing test checked.

## 2026-08-03: The verdict reaches the surface, and previews stop accumulating

<!-- prawduct: chunks=17B | status=shipped | scope=v1-build -->

**17B's remaining three deliverables**, closing the chunk the previous entry
deliberately left unchecked: `art_review`'s three write actions, the preview
sweep, and a harness scenario that runs the worked example end to end. The
acceptance criterion is met — a real MCP client turns an intent into a catalogued
work, and the two calls carrying pictures are the two immediately before the
verdict.

**What the surface owed was the tool half only.** Every rule the write actions
enforce already lived in the service layer with the discovery entities and was
already pinned by the unit suite: a verdict is final, `awaiting_better_image` is
reachable only by rejecting an instance, acceptance mints the artwork and promotes
every scan into a source. What could not exist until the actions did is the
property that is *about* the surface — that acceptance is one call past the
pictures. `ACCEPTANCE_ROUTE` asserts it, extending the review route rather than
restating it, so a shortcut that reached a verdict without a picture-bearing step
fails there rather than passing a copy of its own steps.

**Two interface decisions the contract had left open**, now recorded in
`api-contract.md` rather than only in a schema. `set_verdict` judges **one work
per call**: "explicit work ids" is satisfied by there being no action that omits
one, and the payload differs per work — an artwork id, a minted artist, its
near-misses — so a batch result would flatten those or invent a per-item envelope
this surface has nowhere else. `set_canonical` and `reject_image` take an
`image_id` and **nothing else**, because an instance already carries its work and
a `work_id` beside it would create a pair that can disagree and a rule about which
wins.

**The preview sweep is a sweep, and the decision `boundary-patterns.md` left open
is closed.** A periodic pass over terminal-verdict works, on a daemon thread
inside the application's lifespan, sweeping immediately at start and then hourly.
Immediately because a start-only sweep reclaims nothing on an always-on plane and
a wait-first loop reclaims nothing on one that keeps restarting — which is what an
SD-card-bound plane does when something goes wrong. It logs every pass whether or
not it took anything, so a sweep that has stopped is visible in the journal rather
than only in the free-space figure.

**The sweep found a rule the design needed and nothing had written down.** A
preview file is named by a digest of its **URL**, so the same museum scan resolved
for two candidate works is two rows over one file — ordinary whenever phase 1
proposes one painting under two titles. Deleting on the first work's verdict takes
the picture out from under a work still being judged, and the review card would
then report the file as unreadable when in fact the sweep removed it. The unit of
deletion is therefore the **path**, and a path survives while any work still under
review references it. Written into `data-model.md` beside the disposability rule,
with its corollary: a row must not outlive the file it names, so the file goes
first and `preview_path` is cleared after — an interruption strands a row the next
pass finishes, rather than bytes nothing references and nothing would ever reclaim.

**The mutation sweep found the one thing the diff did not.** `set_canonical`
returned `is_on_offer`, which could only ever be `true`: the call either makes the
instance the one on offer or raises, and a raise returns no payload. Replacing the
field with the constant killed no test, because there is no reachable state where
it differs. Removed rather than defended — the same call `InstanceListing` made
about its `run_id`, and for the same reason: a field whose only possible defence is
a test written to defend it is a field to delete. The test now asks the record
whether the instance is on offer, which is the claim worth making.

**The sweep ships half of what the decision promised, and the PR review is what
noticed.** Issue #29 — the item this chunk closes — asked for the sweep-vs-hook
decision *and* named the case a hook could never cover: a crash between writing a
preview and recording its row. `_references` derives every path from a
`CandidateImage.preview_path`, so a file no row names is invisible to it forever,
and nothing anywhere in the plane so much as lists that directory. The shipped
sweep therefore reclaims exactly the class an on-verdict hook would have, which is
not the argument that chose it. #62 carries the rest, at `stage: design` because
the obvious fix is wrong — a bare directory walk cannot tell an orphan from a file
a live run wrote seconds ago, and would delete previews out from under the writer.
`operational-spec.md` and `boundary-patterns.md` now name both things the sweep
does not reclaim rather than one, which matters most in the disk-headroom row an
operator reads while the card is filling.

**One acceptance-criterion clause is met below the wire, and that is stated rather
than glossed.** "Accepted works appear in the catalogue with sources … intact" is
asserted through the service, because **no action on `art_catalogue` returns
sources** — acquisition is their only consumer so far. Adding a reader would be
this chunk widening a different tool's contract on its own authority, so it is
filed instead. Everything else in the criterion runs over MCP.

## 2026-08-03: "A preview is re-fetchable" was false in four places

<!-- prawduct: chunks=17B | status=shipped | scope=v1-build -->

**Nothing re-fetches a preview, and four artifacts said otherwise.**
`PreviewCache.store` runs once — when phase 2 first records an instance — and a
re-search does not restore the file either, because `record_image` returns the
instance a work already holds for that URL without rewriting `preview_path`. So a
deleted preview costs its instance the inline picture for the rest of that work's
review. That is the difference between "disposable" meaning *losing one costs a
picture rather than a record* and meaning *it comes back*; every site had drifted
to the second.

It mattered most where an operator acts on it: the disk-headroom row told someone
on a filling SD card that hand-deleting `previews/` was "always safe", which is
how a curator loses the inline picture of every candidate still under review —
the picture `security-model.md` makes the whole of the review gate. Corrected in
`operational-spec.md` (twice — the runbook row and the backup section),
`boundary-patterns.md`, and `data-model.md`.

**Three sweeps, three sites short, and that is the entry worth reading.** The
first correction fixed one site. The Critic named a second in the same round and
the fix did not reach it. The PR reviewer found that second one still standing —
in the branch that had just added `learnings.md` entry 19, which is *about*
retiring a claim repo-wide — and running the grep it prescribed turned up two more
that nobody had named. `learnings.md` entry 20 records the tell: entry 19's lesson
was being applied as a check on a list already written, when a grep run *before*
the edits is the only one that finds the sites you were never going to think of. A
reviewer names a sample, not the set.

**Also corrected:** the sweep-vs-hook `[DECISION: …]` was qualified in
`boundary-patterns.md` and `operational-spec.md` and left verbatim at both of its
build-plan sites — the record that says the chunk is done, and so the one a reader
trusts to know whether it delivered. Both now name the unbuilt half and issue #62.

## 2026-08-03: The route assertion that counted polls

<!-- prawduct: chunks=17B | status=shipped | scope=v1-build -->

**A flake introduced by 17B's own acceptance scenario, found by running the merged
suite rather than by reading it.** The scenario watches a run until it finishes,
then asserted the whole call log equalled `ACCEPTANCE_ROUTE` — a fixed six-step
tuple with one `status`. The loop polls until terminal, so on a machine where
phase 2 answered on the second poll the log had seven entries and the test failed.
It passed on the branch and failed on the first full run after the merge, which is
the whole tell: nothing about the tree changed, only how busy the machine was.

**The sibling test already knew.** `test_a_curator_reaches_the_pictures_from_an_intent_alone`
asserts `steps[:2]` and the picture-bearing subset, never the whole tuple, for
exactly this reason — and the new test copied the route idea without the reason
behind its shape.

`Transcript.route` now collapses *adjacent* repeats, and the polling scenario
compares against that; `steps` stays the default for every scenario whose call
count is deterministic, because it is the stricter check. Only adjacent duplicates
fold, so a call re-entered after something else is still a second visit — an extra
required round trip remains the thing these routes catch.

**Three reviewers independently found the same two things, and both were about
what the fix was quiet on.** The fold is over the *rendered* step, which carries
the image count — so two `list_images` calls that returned different numbers of
pictures do not collapse. That is load-bearing rather than incidental: the review
gate lives in those counts, and a fold blind to them would let a route certify
that pictures arrived after they stopped. The test now carries a differing count
for exactly that reason; without it, reimplementing the fold on `(tool, action)`
passed. And what folding *gives up* is now stated where it is defined — a flow
genuinely requiring the same call twice in a row is indistinguishable from one
requiring it once, because nothing in a transcript can tell a poll from a needed
repetition. Such a scenario has to assert against `steps`.

## 2026-08-03: What the Critic round changed about 17B

<!-- prawduct: chunks=17B | status=shipped | scope=v1-build -->

Fourteen findings, thirteen fixed in one pass and one accepted. Three are worth
recording beyond the ledger, because each changed the design rather than tidying
it.

**Two reviewers found the same race independently, from opposite directions, and
it was real.** The sweep read its references and then unlinked, holding nothing
across the two. `PreviewCache.store` hands back a digest-named file it finds on
disk *without re-fetching*, so a resolve run for a work still under review could
attach a row to a path the pass had already judged reclaimable — and
`record_image` never rewrites `preview_path` for a URL its work already holds, so
that row would have named a deleted file for the rest of its review life. Exactly
the outcome the path-shaped unit of deletion was built to prevent, re-entered
through the write side instead of the verdict side. The pass now runs inside one
store transaction, which is the lock `record_image` takes, and
`DiscoveryService.transaction()` is exposed for that one caller.

**That narrowed the race and did not close it, which the verify pass caught and
this entry originally claimed otherwise.** The writer's own two halves straddle the
lock: `PreviewCache.store` checks the file with no lock at all, and `record_image`
takes one afterwards, so a resolve run can capture a path, have a whole sweep pass
delete it, and then write the row. Closing that means the row write verifying the
file inside the lock it already takes — a change to what the record layer depends
on, and one that quietly rewrites how a good deal of the suite seeds previews, so
it is filed rather than bolted on at the end of a review round. What did land is
that the consequence stops lying: a `preview_path` with no file behind it now reads
as an absent copy rather than an unreadable one, which is the difference between
sending a reader after the sweep and sending them after a corrupt download.

**The correction took two rounds, and the second one is recorded where it counts.**
The first pass listed the places claiming the race closed, fixed them, and was
short by one — `DiscoveryService.transaction()`'s docstring, the definition of what
that exposure buys and the exact API anyone would change to close the residual, so
the reader most in need of the corrected reasoning was the one still being
misinformed. That is `learnings.md` § "Retiring a claim is a repo-wide grep, not a
local edit", entry 19, which is where the recurrence log that makes the argument
lives. Restating the lesson here rather than pointing at it would be the same
mistake one level up.

**A named deliverable was not shipped, and the surface — not the contract — was
wrong.** `api-contract.md` requires the refusal of `verdict='awaiting_better_image'`
to name `reject_image`; what shipped was the schema's enum error, which enumerates
the valid set and names nothing. The service's teaching error is unreachable through
the only caller it has, because validation runs before dispatch by design. Fixed by
giving `Param` a `refused_hint` — a declarative pointer carried into the refusal
message — rather than by amending the contract to match the code. The direction
matters: a caller asking for that verdict has not mistyped a value, they want what
another action does, and an enumeration alone sends them away without it.

**The record half of the sweep had a weaker error posture than the file half.** A
read-only mount cost one file and the pass continued; a refused *write* escaped
`run` and cost every path after it, with no `SweepResult` to say how far it got.
Symmetrical now, and the asymmetry is the kind only a reader looking for it finds
— every test passed either way.

Also fixed: `architecture.md` had not heard of `PreviewSweep` or of the plane's
first timer-driven thread; `observability-strategy.md` had none of the six sweep
events, which for a periodic job is the difference between "it is running" and
silence; the review card told a swept work's curator that no copy was ever cached,
pointing diagnosis at phase 2 rather than at the sweep; `api-contract.md`'s own
new arity section said `set_canonical` takes an `image_id` "and nothing else"
while the shipped action also takes `rationale`; the recorded test evidence
predated every test in this chunk; and `possible_duplicate_artists` entered a
payload with its bound unnamed.

**Accepted, not fixed:** backlog reconciliation is dormant on the Issues backend.
That is a known interim state with a standing advisory, not a defect in this work.

## 2026-08-03: Who painted it, and the slot a refused scan yields

<!-- prawduct: status=shipped | scope=v1-build -->

**This entry carries no `chunks=` tag, deliberately.** `regen-views` derives the
build plan's `## Status` checkboxes from that tag, so tagging `chunks=17B` flipped
17B to shipped — which is false, and would tell the next session the remaining
work was done. The chunk stays unchecked until its acceptance criterion is met:
the worked example end to end over MCP, which needs the write actions. The scope
tag is enough for the rollup.

**Partial chunk, and the entry says so.** Two of 17B's four deliverables landed;
the three `art_review` write actions, the preview sweep and the harness scenarios
did not, so 17B stays unchecked. Nothing half-wired ships — the write actions are
absent from the surface rather than declared and broken, and
`_check_bindings_match_registry` raises at import on any mismatch.

**Why the artist:** acceptance minted an Artwork from the title alone and left
`proposed_artist` behind as free text, so **Q9 — who is the artist, for the
physical label — had no answer for anything discovery accepted**. It does now:
exact `artist_key()` equality against the artists already held, reusing the
normalisation `work_dedup_key` settled rather than inventing a second one.

**The decision the artifact handed over unsolved**, recorded in `data-model.md`:
a match must be certain, because the failure directions are not symmetric. A
duplicate `Artist` row is visible in the catalogue and mergeable later; a wrong
merge puts another painter's name on a physical label and leaves no trace a choice
was made. Every heuristic that would close the `Jacob Isaacksz van Ruisdael` /
`Jacob van Ruisdael` gap buys the merge direction to do it — reducing a name to
first and last tokens turns `Hans Holbein the Younger` into `hans younger`, which
`dedup.py` had already measured and rejected. So the split is taken deliberately
and made *visible*: minting a row while an existing one plausibly names the same
painter reports it, which `VerdictOutcome` carries.

**An empty key is not a key.** `artist_key` returns empty for a name that
normalises to nothing, meaning *unattributed*. Matching on it would attribute
every anonymous work in the catalogue to one artist named nothing — the worst
reachable merge, needing no two names to resemble each other. Pinned in both
layers.

**Why the slot budget:** the review card sliced the store's ranking, and
rejections gather at the *top* of it, because the scan a curator turns down is the
best one on offer and refusing it does not make the picture worse. Past a cardful
of rejections the card was entirely scans already refused, while the only ones
still choosable fell off the bottom — with no second way to reach their ids, since
`list_images` is the sole enumerator of a work's instances. Selectable instances
now claim the slots first; the rows keep their ranking, so the truncation notice
claims nothing about position and points at `rejected_for_this_work` instead.

**What the reviews caught that the tests did not.** A three-character floor on
name tokens, justified in its own comment as excluding initials, also discarded
every short surname — `Wu Li` reduced to nothing, so the duplicate notice silently
never fired for whole naming traditions while every European name looked correct.
A regression test that passed against the unfixed code, because its single
survivor was the selected instance and led the order anyway. And the cumulative
review found a live defect none of it reached: a work whose every scan fell below
the display floor could be accepted, minting an artwork whose every source was
non-primary — no record of which scan produced the original. Constraint 8 named
one selectionless state and the code had two.

**Verified:** both suites green (1240 passed, 0 failed) with the recorded evidence
tree equal to HEAD. Mutation sweeps over every branch this work added, including
the notice's three states and the acceptance guard. A cumulative Critic review
across correctness, design and sustainability returned 0 blocking with all eleven
findings dispositioned, and three verify passes since, all 0 blocking.

## 2026-08-03: The review surface, and the text that was half the picture budget

<!-- prawduct: chunks=17A | status=shipped | scope=v1-build -->

**Why:** the human gate has to show the image, and until now no surface did.
`security-model.md` § Content Appropriateness makes the review gate the whole
protection for the household — people with no interface who never opted in — and
its entire content is that the reviewing surface displays the picture. `art_review`
now answers `list_works`, `get_work` and `list_images`, each returning candidate
thumbnails inline as image content blocks beside the two things a thumbnail cannot
say: the fit verdict and the size the work would render at on this deployment's
wall.

**What the artifacts did not anticipate, found by measuring:** `api-contract.md`
sized the 400 px cap from the images alone — 40 works × ~160 tokens = 6,400,
comfortably inside the budget — and the *text* of the first listing shape came to
~7,000 on top, taking a full page past the threshold at which a client warns with
the images still innocent. Narrowing rows to what a caller needs in order to
choose, and moving the instance record behind `list_images`, brought the page to
10,200. **A cap sized from one component of a result is not a cap**, because
everything else scales with the same batch. Two thresholds got two knobs: the
ceiling is 40 against the 25,000 hard cap — where truncation takes the *pictures*
and leaves the rows, quietly turning this into the metadata listing the security
model forbids — and the default page is 30, at ~7,700, so a caller who asked for
nothing never trips the warning.

**A rule needed applying one level above where it was written.** "A below_floor
image is shown, labelled, and selectable — never hidden" governs the image
listing; a work whose only instances are below the floor has no selection, so a
listing row keyed on the selected instance carried no picture at all — not
withheld by any rule, just absent, and indistinguishable from a work no picture
exists for. Rows now fall back to the best surviving instance and report
`is_on_offer: false`.

**Image blocks correlate by position and nothing else**, so every row carries
`image_block_index`, null when it contributed none. The blocks are only the
instances that had a local copy, so block *n* is not row *n* the moment one
preview is missing — which is how the wrong picture gets accepted as the right
painting. Found by mutation: a constant index left every other assertion green.

**Four tests moved rather than being deleted.** `art_review` was the last unbuilt
tool and three tests used it as the *subject* of the unbuilt-tool mechanism, which
is unchanged and still covered — now against a synthetic record, so building a
tool never again silently retires it. A fourth was parametrised over the unbuilt
roster and had gone empty; an empty parametrisation skips rather than fails, so
the file kept a test that had stopped asserting anything.

**Also corrected, pre-existing:** `api-contract.md` said "three of the five tools
declare fewer actions than they list here" and the true count was two — stale
since before `art_discovery`'s last action landed, with nothing able to notice.
Replaced with the shape of the claim, since `action='help'` is what actually
answers it.

**The mutation sweep became a tool** (`curation/tools/mutation_sweep.py`) rather
than being re-derived from a session transcript for the third time. Its committed
lesson is a trap that cost real time here: rewriting a source file and running
pytest several times a second defeats CPython's `(mtime, size)` bytecode check, so
a mutation that leaves a line the same length runs against stale bytecode, never
executes, and reports as a survivor — indistinguishable from a finding.

## 2026-08-03: The list nothing bounded, and the race the guard only described

<!-- prawduct: chunks=16B | status=shipped | scope=v1-build -->

**Why:** the `verify-resolutions` pass confirmed all six prior warnings fixed and
found one more — created by the fix for the first. Putting the works on the run
view made `resolve_images` invokable and made `status` unbounded: **phase 1 is
deliberately uncapped** (`phase_one.py` is written for "you asked for Dalí and I
found 200 works") and the approval gate is computed *after* the whole list is
recorded, so it pauses a run without shortening it. The run that stops for a
human decision is therefore the broad one by construction, and the human decides
it by reading exactly this payload — ~12–16k tokens at 200 works, past the 10,000
at which a client warns.

`works.each` now caps at 100 and says what it left out, which is the rule
`api-contract.md` § Token budget already states: *truncation is always explicit, a
result that omits rows says so and says how many.* The cap is deliberately not
shared with the catalogue's list ceiling — that one bounds a limit a caller chose,
this one bounds a list nobody asked for the length of, and one number serving both
would move for two reasons. The notice names no way to fetch the rest, because
there is none; a paged listing of a run's works arrives with the review surface,
and promising an affordance that does not exist is what the withheld action was
withheld to avoid.

**The race is now closed rather than documented.** A work decided while its own
search ran still gained CandidateImage rows — reachable from no surface, since its
images became catalogue `Source`s at acceptance. `record_image` declines a work
whose verdict is terminal, on the same ground `reject_image` already refuses one:
a decided work's images are not under review. The runner also re-reads each work
as it reaches it, because the list is gathered before the first provider call and
is minutes stale by the last — that spares a provider call whose result could not
be applied, and it is what makes the docstring's claim true rather than nearly
true.

**Verified:** both suites green; counts in `.test-evidence.json`. Four more
branches deleted and watched go red, one of which needed a test written to be
observable at all. A new test also passed alone and failed in the suite by
assuming the order a run's works come back in — the same assumption already fixed
once in this file's fixture, reintroduced twelve tests later.

## 2026-08-03: An advertised action nothing could supply an argument to

<!-- prawduct: chunks=16B | status=shipped | scope=v1-build -->

**Why:** the cumulative Critic round over 16B returned 0 blocking, 6 warnings and
10 notes, and the correctness one was the finding the chunk most needed. 16B
advertised `resolve_images` with a required `work_ids` array, and **no built
surface produced a work id**: `art_review` owns any listing of candidate works
and is not built until Chunk 17, and a run reported its works as counts only. A
model reading `help` saw a fully described action with no path to invoke it — the
same promise-the-surface-cannot-keep that 14A withheld the action to avoid, one
level down. The suite could not see it because the integration test reached past
the tool for the id.

**What changed:** `RunView` carries the works themselves and derives its three
tallies from them, so the counts and the list cannot disagree; `status` returns
`works.each` with the id, title, artist and both statuses — enough to choose and
to act, and deliberately not a second review card, which belongs to Chunk 17 with
its images. The integration test takes the id off the surface now, so the gap
cannot re-open silently.

**The second finding it raised, which the first was hiding:** a re-search against
a work the curator had already decided reported it as *resolved*. Nothing was
written to that work — the terminal-verdict guard discarded the result, correctly
— so the run was claiming a change it did not make, and `_record_instance` had
already written candidate images onto a work whose images became catalogue
sources at acceptance, reachable from no surface at all. A decided work is now
not searched, and `WorkOutcome` replaces the boolean-with-a-null so
`verdict_stood` is counted apart from `resolved` on both the already-decided path
and the race.

**Four smaller ones.** The line announcing a dead run put its id in the message
text with no `run_id` field — invisible to the `jq 'select(.run_id == …)'` query
`logs.py` documents, so an operator reconstructing a run got every line except
the one saying it died, and `observability-strategy.md` tells that reader to read
the silence as a *second* defect. A failed preview publish stranded a
fixed-name `.partial` that nothing reclaims, on the one failure it handles — a
full disk. `architecture.md` promised a two-name network allowlist that has three
(now named rather than counted, since the list exists to be added to);
`project-preferences.md` counted 23 MCP bindings against 24. Plus a comment
sitting above the wrong field on an external contract surface, two stale
learnings cross-references, and the dead `uploaded_files` dict in `tvart.py`
whose comment asserted a clearing effect Python made a local rebind.

**Verified:** both suites green, with the counts in `.test-evidence.json` rather
than copied here where nothing would ever re-check them. The mutation sweep ran
twice more and found **three more undefended branches on the first pass** —
`verdict_stood`'s race path, the run-death line's `run_id`, and the partial's
unlink — all now red when broken. That is five undefended branches caught this
way across the chunk, and none of them by re-reading the diff.

## 2026-08-03: The re-search runs, and the rejection it defends against finally sticks

<!-- prawduct: chunks=16B | status=shipped | scope=v1-build -->

**Why:** `resolve_images` was fully specified and half built — coverage,
constraint 14, the parent link and the terminal-verdict guard all landed with 08B
and 16A — but nothing ran a resolve run and the action was withheld from the
surface. A curator who rejected a scan had no way to ask for a better one, so
`awaiting_better_image` was a dead end.

**What changed:** the runner half. `DiscoveryRunner.resolve_images` starts a
`kind='resolve'` run, registers it in flight before handing off, and returns its
handle at once — the third entry into phase 2 after the inline one and
`approve`'s. A re-search asks about **everything it covers**: coverage is the
scope a curator named, every covered work has been resolved once by definition,
and the discovery-run filter on "not yet resolved" would have skipped the whole
request while still holding the works against a second attempt. The action is
advertised for the first time, with the tips a model reads pinned to the refusals
the service actually makes. `art_discovery` is now whole at ten actions.

**The defect this chunk surfaced:** instance suppression was scoped to the row
carrying the rejection, not to the URL. A provider re-offering the same scan —
the normal case between two searches a minute apart — wrote a fresh row with a
null `rejected_at` and selected it, handing the curator back exactly what they
had turned down. Nothing before this could produce it, because nothing searched
twice. `record_image` now returns the instance a work already holds for a URL
rather than adding a second, and the rule is written as a corollary to constraint
7 in `data-model.md`.

**Two smaller things, recorded rather than glossed.** The registry gained an
`array` parameter type carrying its element type, because `work_ids` is the
surface's first list and a bare `{"type": "array"}` publishes nothing a model can
act on — elements are type-checked with the offending position named. And a
resolve run is priced at creation from the works it covers, because `estimate` on
one otherwise answered with a sentence about phase 1 finishing, which cannot
happen on a run that never had one.

**Verified:** both suites green (curation 1034 → 1067). Every new branch was
deleted in turn and the suite watched go red — eight for eight, two of which were
undefended on the first pass and are the reason the check was run. The product
was booted and driven by a real MCP client: `work_ids` publishes
`items: {type: string}`, `help` carries the action and its five tips, and the
three refusals answer in the words the tips promise.

## 2026-08-02: Discovery phase 2 — works become instances, and the near-match is refused

<!-- prawduct: chunks=16A | status=shipped | scope=v1-build -->

**Why:** A run that cleared the approval gate had nowhere to go. It settled its
work list, moved to `resolving_images`, and sat there — with `status` saying in
plain words that finding images was not wired up in this deployment. That
sentence is now deleted, and a run completes under its own power with one card's
worth of data per work.

**Chunk 16 was split into 16A and 16B** at the operator's call, at the seam
between turning works into instances and doing it a *second* time on request. One
Critic round over the whole would have read a diff comparable to 14A and 14B
combined. 16A meets the acceptance criterion the chunk states; 16B adds
`resolve_images` on top of the engine it builds.

**The verify-api probe ran first and changed the design rather than confirming
it** (`artic-api-findings.md`). Two findings did the work:

- **The Art Institute's relevance score cannot carry confidence.** Scores are not
  comparable between queries — two correct searches topped out at 3,362 and 122 —
  a nonsense query returns the *whole collection* rather than nothing, and asking
  for a painting the museum does not hold returns real works by real artists at
  comfortable scores. Asking for *The Persistence of Memory* surfaces *Ann-In
  Memory* by Joseph Cornell. **Ranking by that number attaches it to the request
  and reports success**, which is the "confident near-match" the data model
  forbids arriving through the most obvious implementation. So confidence is an
  identity comparison against the requested title and artist, derived from the
  same normalisation `work_dedup_key` is built from, and an artist disagreement
  disqualifies rather than deducts — the collection holds *American Gothic* by
  Grant Wood **and** by Elizabeth Layton.
- **The search response already carries the master's dimensions.**
  `thumbnail.width`/`height` describe the full image, verified equal to the IIIF
  `info.json` on separate works, so an instance is sized from the response that
  found it and the per-result round trip a careful implementation would have made
  is not needed. Every IIIF response is 843px wide whatever is asked for, which
  settles both the preview URL and `acquisition_method = dezoomify`.

**Phase 2 reaches museum APIs only (operator decision).** That comparison is free
and deterministic, so phase 2 spends nothing — which is what made the cost
correction below safe. A work no museum holds lands `unresolved`, already a
first-class outcome whose remedy is the re-search.

**The floor is an exclusion in the one function that decides selection**, not a
filter at recording time and not a deduction in the score. Recording-time
filtering would hide the instance, which the requirement forbids; a deduction
would still select it whenever nothing better existed, which is the case the
floor exists for. Every consequence then falls out of one rule: the instance is
stored and offered as an alternate, a work with only below-floor instances is
reported `unresolved`, a curator can still choose one by name, and **rejecting a
good scan does not fall through to a below-floor alternate** — which would hand
someone asking for something better the worst image on the card.

**The cost estimate is corrected, both halves at once.**
`DISCOVERY_PHASE1_INPUT_TOKENS` shipped at 490,000 against a measured 3,453, and
14B deliberately left it standing because phase 2's consumption was unmeasurable
and re-basing phase 1 alone would have traded a visible overstatement for an
invisible understatement. Phase 2 turned out to consume nothing, so both settled
together: a bounded run goes from **$0.127 to $0.01336**, and the phase-2 estimate
from `work_count x 2 searches` to **zero**.

**A consequence worth stating rather than glossing:** the token basis is no longer
input-dominated. Input is a measurement with headroom; output is the provider's
reservation, which a run cannot exceed. The old basis put output at 6% of tokens,
which is why "output price is nearly irrelevant to model choice" stood — it is not
irrelevant now, and the model table reorders, with Gemini 3.5 Flash Lite moving
from third to last on its $2.50/M output. The chosen model is cheapest on either
basis, so the decision is unaffected.

**Verified against the live API, not only against fakes.** Four real works resolve
at 0.95 confidence with previews on disk; *The Persistence of Memory* and an
invented title both land `unresolved`. Both suites green with evidence recorded
against this tree — the figure lives in `.test-evidence.json`, which is regenerated,
rather than being copied into prose that cannot notice when it stops being true.

**One thing found by writing the tests.** The first quality metric ranked on
rendered inches, and preferred a 2000x1500 landscape over a 6949x8400 portrait —
because the artwork box is wide, so a tall master is limited by its height and
renders shorter while having four times the resolution to spare.
`nonfunctional-requirements.md` had already said what isolates resolution is
whether the render is a downscale or a native-size paste; the metric now bands by
that verdict, and the case is pinned by a test.

## 2026-08-02: The review Chunk 15 never got, and the four findings that were one finding

**Why:** Chunk 15 shipped without a Critic review. One was dispatched — three
reviewers, a manifest, `.started` markers — and it died before any of them wrote a
finding, then a commit landed on top of the tree it had been reading. The
governance ledger's last review was still 14B's, so nothing recorded the gap; the
`.critic-findings.json` sitting in the directory was a different review of
different code, which is the failure mode where a stale file reads as a fresh
pass. Re-run against the real head, the review returned **0 blocking, 8 warnings,
8 notes**. All sixteen are dispositioned here in one pass.

**A remote API response could run shell on the loader host.** `get_dezoomify_file`
interpolated a URL into a string and ran it with `shell=True`, and on the ARTIC
path that URL is built from `metadata["config"]["iiif_url"]` and
`metadata["data"]["image_id"]` — fields of a remote document, replayed from
`api-cache/` on every later acquisition. The same function already sanitised the
*filename* it derived from that document, which is what made the unsanitised URL
easy to miss. Now an argv list with no shell. The build plan had barred this shape
from being ported forward at acquisition, but its reason named *future* discovery
URLs, so the live path that has been remote-tainted all along had no disposition
at all — a constraint scheduled for code that does not exist yet, while the code
running the wall kept the defect.

The test asserts the argv actually passed, not the absence of a crash, and the
first draft of it failed that bar in a way worth recording: `args.count(url) == 1`
passes against the *old* code too, because on a shell string that is a substring
count. Three of four tests failed against the defect and one passed. Every
assertion now goes through a helper that establishes the call received a list at
all, and all four fail without the fix.

**The MCP server told every client it only stages changes.** The shipped
instructions promised "an agent stages changes rather than completing them" while
`art_theme(action='activate')` and `art_display`'s sync/show_now/next all converge
the wall within about a second — this server's own tool descriptions say so. A
model reading that reports staged work to the curator and has in fact changed what
is hanging. Its other clause was the sentence `security-model.md` recorded as
VOIDED in 2026-07-19, re-asserted verbatim on the surface where an external
consumer reads it. Rewritten to what is true, in the form the security model
settled on: an agent can change the wall, and what the gate guarantees is that
acceptance rests on a person having seen the image — not on a surface being denied
a tool.

**Four of the eight warnings were the same defect wearing four hats**, and that is
the finding rather than any one of them. A 2026-08-02 amendment — `3tears-models`
confined to an opt-in test group when discovery went to a first-party OpenRouter
client — landed in the files that argued for it and was never swept. The reviewer
named five stale sites and a `pyproject.toml` contradicting itself fifty lines
apart. **The repo-wide grep found nine**, including a *test docstring* teaching the
retired claim to everyone who reads the suite, plus this project's own
`learnings.md` entry and a `project-state.yaml` decision record. That the sweep
prescribed by the learning "retiring a claim is a repo-wide grep, not a local edit"
was itself done locally enough to miss a third of the sites is the whole lesson,
and this is its fifth recurrence — the fourth for a Python-version claim
specifically.

So the fix is structural rather than another sweep: **what holds the 3.14 floor is
now stated once**, in `project-preferences.md` § Language & Runtime, and the other
eight sites point at it instead of restating it. A claim duplicated in nine places
drifts in nine places; a claim stated once cannot. The substance also changed and
is worth saying plainly — **no default dependency requires 3.14 any more.** The
only declared holder is a test-only package, so the two-plane split's first stated
reason now rests on the verified fact that the set resolves on 3.14.4, and
lowering the floor is a decision available to whoever wants it rather than a
correction. `architecture.md` says outright that this is the weakest of the
split's three legs.

**Two module docstrings stated a norm as a description of themselves.** `http/api.py`
opened "Every handler does three things and nothing else" while six of its twelve
handlers do more, and `mcp/bindings.py` stated the identical absolute while its
"get theme" binding composes two service calls. The known-departures table had
scoped itself to the HTTP file, so the owner's deferred fork — name the exceptions
or amend the norm — was posed against an undercount that omitted the MCP layer
entirely. Both docstrings now say the rule binds *and* that the file departs, which
is the only combination that neither licenses the next departure nor quietly
weakens the rule. The MCP layer's departure was measured rather than assumed: one
of twenty-three bindings, by AST.

**The documented way to run the tests did not work.** `CLAUDE.md`'s root column
gave `pytest tests`, `ruff check .`, `black .` — but those tools live in a
uv-only dependency group, so a fresh clone gets command-not-found or, worse, a
system-Python pytest resolving different dependencies and reporting a green suite
that means nothing. README.md points at this table as the authority. Both columns
now carry `uv run`.

**Smaller, same shape.** `observability-strategy.md` still listed
`limit_remaining` as a present, trustworthy spend signal: nothing calls the
reader, and the figure lags badly enough that it was observed reporting credit
while calls were already being refused — `operational-spec.md` corrected exactly
this on the same day and the sweep stopped there. `data-model.md`'s derivation
block still prescribed the bilingual rule the head commit had deleted, so the
decision record was teaching what the decision un-made; struck, and the merge risk
that *does* exist in the shipped code (the uninformative-title list is enumerated
and English-only, so `Landschaft (Studie)` reads as distinctive) is now recorded
beside the other residual risks instead of living only in a comment.
`deploy/README.md` now warns that installing `requirements.txt` resolves the
IT8951 driver to whatever master is — declaring `omni_epd` put its unpinned child
on the install path — and gives the SHA the wall ran. Documented rather than
pinned, because pinning a transitive git URL against the parent's own unpinned
declaration is resolver behaviour to verify on hardware, and the panel is off the
bench.

**The verify round then caught the sweep failing inside this very commit.** Seven
of eight warnings verified fixed; `limit_remaining` did not. The two sites the
finding named were corrected and four more were not — one of them 175 lines below
the new correction *in the same file*, and one a Chunk 19 deliverable in
`build-plan.md`, a file this commit was already editing for the unrelated
`3tears-models` sweep. The learning entry added here argues that attention has
stopped working as a remedy; it did not survive its own commit. That is the
eighteenth recurrence and the sharpest evidence yet, so it is recorded as such
rather than quietly folded into the fix.

**And the fix itself had overreached.** "Do not ship it as the budget signal" is
new normative content, asserted in an artifact that does not own the norm, against
a *ratified* corollary in `nonfunctional-requirements.md` § Direction naming
`limit_remaining` as where budget-left comes from. Two separable things had been
run together: **where the number comes from if shown** — the corollary, untouched,
still authority-not-local-tally — and **whether to show it at all**, which the
measurement bears on and which is nobody's call but the operator's. It is now an
open question with its three options recorded, the ratified norm carries a pointer
to it rather than an edit, and Chunk 19's deliverable says "whatever the question
resolves to" instead of naming the field. Amending a ratified norm to match one's
own conclusion is the tell this project's norm lifecycle exists to catch, and it
was caught.

Both suites green, evidence recorded against this tree rather than an earlier
session's — which was itself one of the warnings.

## 2026-08-02: Chunk 15 — the derivation and the engine, both decided by measurement

<!-- prawduct: chunks=15 | status=shipped | scope=v1-build -->

**Why:** two derivations the rest of discovery depends on were unmeasured guesses,
and the plan front-loaded them so they could not be settled implicitly three
different ways later.

**Cross-run suppression was working about a fifth of the time.** Measured against
128 proposals captured from 22 real runs: ask the same intent twice and the same
painting returns under a different name. Normalised artist plus title held **7 of
36** recurring works together; the derivation now shipped holds **29 of 36**. That
fraction is the share of a curator's rejections that keep working, so Q3 — the
question `data-model.md` calls the one most easily missed — was mostly unanswered.

**Neither of the two hazards named in advance was the one that bit.** The feared
false positive (bare "Untitled" repeated by one artist) barely occurs, because
real catalogue titles carry disambiguators the normalisation already preserved.
The dominant cause was unlisted: the same model, on the same intent, minutes
apart, appends a year.

**Two rules that scored better were rejected**, because the directions are not
symmetric. A split asks the curator about one painting twice — visible,
self-correcting. A merge silently withholds a painting nobody turned down. So
stripping any trailing parenthetical is out (it collapses Richter's hundreds of
`Abstraktes Bild`), and first-and-last artist names are out (`Hans Holbein the
Younger` becomes `hans younger`). A provenance-tail rule reached 31 of 36 and was
also rejected: it broke a work it had been holding.

**The engine comparison reversed its own premise.** `nonfunctional-requirements.md`
had argued cost could not discriminate, so engine choice had to be a quality
decision. Across sixteen holding-museum cases and a recency-bound intent, Exa,
Parallel and Perplexity scored identically. Quality did not discriminate; cost did,
four to one. Parallel is pinned. The model-tier half was measured too: both tiers
proposed only verifiable works, and the cheaper one proposed more.

**Three defects found by running it for real, none of which any test could have
caught.** Phase 1 leaked markdown citations into `proposed_title`, corrupting both
the review card and the identity derived from it. A truncated answer was reported
as the model emitting bad JSON when it had been cut off at the output reservation —
two of thirteen runs, with the actionable half of the diagnosis missing. And the
search engine was never pinned, so which back-end the product used was a side
effect of `DISCOVERY_MODEL`.

**The sweep found a defect the decision itself introduced.**
`DISCOVERY_SEARCH_COST_USD` still held the Exa price while the pinned engine bills
a fifth of it, which would have overstated search five-fold in the one figure a
curator authorises against. A test now holds the two settings together.

**Recorded honestly rather than flattered:** the corpus contains no two works any
candidate would wrongly unite, so its zero over-merges is absence of evidence, not
evidence of absence — the cases that would show one are pinned as separate unit
tests. The seven residual splits are two named shapes, asserted so the claim fails
rather than decays. No re-key migration shipped because no deployment holds
`CandidateWork` rows; the obligation stands for any that does.

## 2026-08-02: Discovery spends for the first time, and the ceiling is proven closed

<!-- prawduct: chunks=14B | status=shipped | scope=v1-build -->

**Why:** 14A built everything up to the seam and could not start a run. This is
what sits behind it: a first-party OpenRouter client written to measured response
shapes, the phase-1 engine that turns an intent into works, and the wiring that
replaces `unavailable_engine()` with a real one when a key is configured.

**A measurement decided the design before any of it was written.** The one gap
the plan named as outstanding — whether the web-search fee scales with
`max_results` — was probed first, because the per-run cap is sized against it. It
does not scale: the fee is **charged per request and identical at one, three,
five and ten results** ($0.00500000 to eight decimal places), while citations
scale one for one. **Breadth is free**, so `DISCOVERY_SEARCH_RESULTS` ships at 10
and the recorded cap needed no revision.

**Every run searches, and that is a decision rather than a default.** The
alternative — a trigger deciding per intent — fails in the one direction the
product cannot detect: a missed recency-bound intent returns real but pre-cutoff
works with nothing marking them stale. Measured, not argued: without the plugin
the default model answered *"No major art prize has been awarded in 2026 as of
2025"* and, asked for a work list, returned 2022–2024 winners describing them as
recent. Searching always costs a flat $0.005 — $0.30–0.90 a month against a $20
ceiling — and grounds non-recency intents into the bargain.

**`DiscoveryRun.strategy` finally has a writer.** It is the model's own account of
how the intent was read, so it lands when the work list settles rather than when
the run starts — nothing can know it before the intent has been read. The
now-unreachable `strategy` parameter on `start_discovery_run` was removed rather
than left as a second way to write one field.

**The two refusals are held apart, which is the whole of the ceiling in code.**
403 is exhaustion and raises `BudgetExhausted`; 402 arrives *with credit in the
account* — the provider reserves the maximum output a request could produce — and
must not halt a run that can still pay. `max_tokens` is therefore always sent, a
correctness requirement rather than a tuning knob.

**Proven, not assumed.** A key deliberately burned to its limit drives a real run
end to end to `halted_by_budget` with no spend recorded, in a live suite behind
`-m live_api` that also re-verifies inline `usage.cost`, the flat search fee,
citations, the key's monthly ceiling and strict structured output. That suite —
not the findings file's prose — is now the durable form of those findings.

**What it actually cost, and what the estimate said.** The first real run through
the booted plane proposed nine 2026 prize-winning works for **$0.0055882058**
(89% of it the search fee) against an estimate of **$0.127**. The prices are
right; `DISCOVERY_PHASE1_INPUT_TOKENS` is not — 490,000 assumed against 3,453
measured, because the plugin injects excerpts rather than pages. **Left standing
and recorded rather than re-based**: that figure is the cost analysis's *whole
run* basis while the code spends it on phase 1 alone, and phase 2's tokens are in
no estimate at all, so correcting phase 1 alone would trade a visible
overstatement for an invisible understatement. The decision belongs with Chunk 16,
which is the first point both halves can be measured.

**The curation plane holds its first secret**, so it gained the redaction the
norm requires and a startup-path guard driven off the declaration rather than off
a remembered list — verified by mutation in both directions.

**Critic resolutions (2 blocking, 4 warning and 4 notes fixed; 6 accepted, 1
filed as #45).** Both
blocking findings were undeclared dependencies, and neither would have failed a
test: `httpx` is imported by the new client but was declared only in `dev`,
resolving transitively through `mcp` — so an install works right up until `mcp`
stops vendoring it, at which point the *whole plane* fails at import rather than
just discovery. And `requirements.txt`, which `deploy/README.md` points a rebuilt
Pi at, was missing `astral`, `tzlocal`, `omni_epd`, `pycairo` and `PyGObject`
while still pinning `suntime`, which nothing imports; the apt prerequisites for
the two that need them are now documented beside them.

Three of the fixed findings are worth naming because each is a *record* that had
stopped describing the code. The spend-ceiling deliverable reached `.env.example`
but never `operational-spec.md`, so an operator doing a routine-operations pass
never met "verify the key still carries its $20 limit" — the one check separating
a capped deployment from an uncapped one. `boundary-patterns.md` still said
`art_discovery` answered only `help`, two chunks after eight real actions landed
on it — the exact stale-row failure that file's own preamble warns disarms the
consumer-impact check; its action list is now a pointer to `tools.py` rather than
a copy. And the 2026-08-02 decision to reach OpenRouter first-party was never
swept into `project-state.yaml` or the 3tears findings banner, both of which still
read as though `3tears-models` arrives with discovery — the reading that would
pull seven packages into the Pi's default install.

**Two mechanisms were fixed rather than their symptoms.** `uvicorn.run` now takes
`log_config=None`: its default attaches non-propagating *text* handlers, so the
startup banner, every access line and every ASGI traceback left the process as
plain text beside this plane's JSON — and `journalctl | jq`, the documented way to
reconstruct a run, aborts on the first such line. The engine-seam network guard
was **inverted**: it named three modules that may not import a transport, chosen
when those three were all of discovery, so a phase-2 engine added above the seam
would have been unguarded with nothing to show it. It now guards every module
except a two-name allowlist, verified by planting a violation in a module the old
form never named.

**Three product changes rode into the resolution commit and belong in this
record.** Each is argued at its site and tested, but a commit presented as
"resolutions" should not be where a reader first meets them. **`strategy` is now
on every `art_discovery` run payload** — a live external surface, so this is an
additive contract change: it was stored and read by nothing, which made it
write-only data on a field the data model says exists to explain results.
`api-contract.md` carries a dated entry, two booted-server tests cover it, and
the contract scenario asserts it on the run the gate approves.

> **That last clause is a correction, and the sentence it replaces is the reason
> to keep it visible.** This entry first recorded that the contract level was
> skipped because "nothing under `tests/contract/` asserts result shapes today,
> which is why the letter could not be followed cheaply." That was false — the
> contract suite asserts payload fields throughout, including the whole error
> envelope, through the same booted-server driver — and I wrote it having checked
> the directory rather than the claim. The damage of a false excuse is not the
> missing assertion but its reuse: `boundary-patterns.md` gates **any** MCP
> tool-surface change at that level, and a durable record saying the level cannot
> cheaply cover result shapes teaches the next person to skip it too.

**`_read_completion` no longer raises** on absent choices or
empty content: both arrive after the provider has billed, so an exception
travelled without the charge and the run recorded spending nothing — the judgement
moved to the engine, which fails carrying the spend. And **the client's
`httpx.Client` lost its `base_url`**, which every request ignored in favour of a
full URL.

## 2026-08-02: The refusal we designed against was the wrong one — exhaustion is 403

**Why:** The keys were provisioned and the over-limit path was finally driven,
which is the acceptance criterion the plan set for a reason: *"fails closed" is a
claim about a path nobody has executed until someone executes it.* Executing it
overturned an assumption carried in eight durable places.

**Exhaustion is `403`, not `402`.** `{"error": {"message": "Key limit exceeded
(total limit)…", "code": 403}}`. Every artifact and docstring said
`halted_by_budget` derives from a provider 402. A client watching only for 402
would never have recognised running out of money at all.

**The 402 is a real thing too, and it is worse than a wrong code — it is a
different condition.** It is a pre-flight affordability check priced against
`max_tokens`, and it arrives with credit still in the account: *"You requested up
to 32000 tokens, but can only afford 3333."* The arithmetic is exact — $0.25
remaining ÷ $75/M output = 3,333 — so OpenRouter reserves the maximum output a
request could produce and declines if that exceeds the balance. The very first
burn attempt returned 402 with `usage` still exactly `0`; nothing was spent.

Two consequences for the client that has not been built yet, which is the good
time to learn them. **`max_tokens` is a correctness requirement, not a tuning
knob** — left unset, the reservation is the model's ceiling and a nearly-empty
key refuses everything. And **the two refusals must not be collapsed**: 403 means
stop, 402 means ask for less and carry on.

**The `/key` lag stopped being an inference.** Mid-probe, `/key` reported
`usage 0.20634, limit_remaining 0.04366` — money apparently available — while
live calls were already being refused as limit-exceeded. The recorded lag,
caught in the act, and the sharpest possible argument for why that endpoint may
display a figure and never gate one.

**Also closed: `limit_reset`.** It reads `"monthly"` on a key configured with a
reset and `null` on one without — so the field names the period rather than
flagging a boolean, and the monthly behaviour the whole $20 analysis rests on is
observed rather than assumed.

**Swept as a grep, not a local edit** — the lesson from earlier the same day,
when exactly that shortcut left a stale dependency floor in two files. Corrected:
`engine.py`, `discovery.py`, `discovery_records.py`, `architecture.md`,
`data-model.md`, `nonfunctional-requirements.md`, `build-plan.md`, two test
fixtures, and a correction appended to the `project-state.yaml` decision record.
The change-log's own earlier entries were left alone: they record what was
believed when written, and rewriting them would falsify the record rather than
correct it.

**The restatement was the real defect.** One provider detail had been copied into
eight durable homes, so one wrong measurement became eight wrong claims. The
correction reduces the copies rather than just fixing them — the docstrings now
say "the provider refuses" and point at `openrouter-api-findings.md`, which is
the only place a status code appears.

## 2026-08-02: Discovery gets a surface, a seam, and a run id on every line

<!-- prawduct: chunks=14A | status=shipped | scope=v1-build -->

**Why:** `art_discovery` had been a reserved name since the surface was built —
it answered `help` and refused everything else. Eight of its ten actions are now
live over MCP, driving the run lifecycle that landed with the discovery entities,
and none of them can spend a cent: the paid part sits behind a narrow first-party
interface that this chunk defines and does not implement.

**The engine is a seam, and a deployment gets one that refuses.** Handing the
service layer a convincing test double would have made every acceptance criterion
demonstrable and the product a liar — invented works written into a real
catalogue with nothing distinguishing them from found ones. So the shipped engine
declares why it cannot run, `start` refuses *before* creating a run, and
`list_runs` stays empty. Nothing was attempted, so nothing is recorded as having
been. The fake that drives the tests lives under `tests/`, deliberately out of
reach of a deployment.

**A run's status can name a phase nothing advances, and the first long-poll did
not know that.** `status` was written to hold while the run sat in a
process-held state, which is the obvious reading and was wrong in a way that
failed silently: after phase 1 settles a work list the run truthfully sits in
`resolving_images`, image resolution is a later chunk, and so *every* status call
waited out the full 45 seconds to report something that had been true for
minutes. The only symptom was a slow surface — the integration suite took 238
seconds. Keying the hold on whether **this process has the run in hand** is both
correct and unable to go stale: a phase this process does not run is a phase it
does not register. The suite now takes 6. It also answers `interrupted` correctly
for free, since after a restart nothing is in flight.

**The whole MCP dispatch moved off the event loop** to make a 45-second hold
safe at all. On the loop it would stop every other request in the process, the
browser surface included. The synchronous service layer was already reached from
worker threads via HTTP — Starlette runs a synchronous endpoint in one — and the
catalogue is built for it, one connection behind a reentrant lock.

**The search cap has values, and they are a derivation rather than a preference.**
A flat 10 for phase 1 and 2 per work for phase 2: a twenty-work run is bounded at
50 searches, which at $0.005 is $0.25 — exactly the top of the search band the
cost analysis recorded — and a bounded run total of $0.327 against its recorded
$0.11–$0.33. `test_config.py` recomputes both from the shipped settings, so the
analysis and the code cannot drift apart quietly. An engine that *overruns* the
allowance fails its run rather than having its results trimmed: work bought
outside the bound was not authorised, and accepting it with a note attached makes
the breach a footnote on a paid bill.

**Curation logs JSON now, with `run_id` bound rather than passed.** The
correlation key rides a context variable and is stamped by a filter, so a module
that logs inside a run carries it without knowing runs exist — the alternative is
a discipline, and one forgotten call site defeats it. The first implementation
cleared every root handler to make configuration idempotent, which silently
disabled the test harness's own capture and failed as *"nothing was logged"*
rather than as *"your logging setup removed my handler"*. It now removes only its
own, and both halves are pinned.

**The provisional dedup key ships with tests asserting its known failures.**
Normalised artist and title. "Untitled" collides across genuinely different
paintings; a translated title splits one work in two. They pull in opposite
directions, which is why neither can be fixed by guessing — and a replacement
argued for later needs the current behaviour written down rather than
remembered. Writing those tests also found a real collision: a work with no
artist keyed identically to an artist actually named "Unattributed".

**"No code path can reach the network" is a test, not an assurance.** The three
modules behind the seam are parsed and refused any import that could open a
socket. Planted a violation and watched it fail before believing it.

**The review took three passes, and the shape of what each caught is the useful
part.** The cumulative round returned one blocking finding, seven warnings and
seven notes. The blocking one was a defect already fixed uncommitted — the
reviewer said so and told the builder to commit rather than rewrite. What the
following passes found was the *same defect twice more, migrating*: first the
guard covered the engine call but not the settling that followed it, so an
ordinary catalogue fault reproduced the identical hang one exception class over;
then, once guarded, the comment describing the guard claimed to survive a
sustained outage it cannot, because ending a run is itself a write. Each round
found a smaller version of the same thing, which is what a defect looks like on
the way out.

Two findings are worth carrying beyond this chunk. The `mcp>=1.27` floor had
never been checked against the code: `app.py` passes `session_idle_timeout`,
confirmed only at 1.28.1, so any resolve below the lock raised at application
build and every request failed. And closing it took two attempts — the finding
said *grep*, the first fix edited the three files already open, and `build-plan.md`
still carried the old floor in two places. This repo's own learning is that
retiring a claim is a repo-wide grep, not a local edit, and the finding quoting
it caught the builder doing the opposite.

## 2026-08-02: Backlog reconciled against the tree, and the flat-vs-package question closed

**Why:** Four backlog items were carrying claims about the tree that the tree had
stopped supporting, and the norm sweep's second deferred finding — a `(target)`
preference asking for a decision that discovery never made — was a five-minute
call left open for thirteen days. No product code changed.

**File organization is decided: per plane, not per repository.** The root plane
stays flat, the curation plane stays a `src/` package, the display plane becomes
one when it is created. The binding half is about additions rather than layout —
**nothing new is added at the root** — because that is the half that can be
violated. Converting the root plane to a package had stopped being a live option
before the decision was even owed: the build plan scheduled those modules for
deletion at the legacy retirement on the same day discovery closed, so from that
point the move was a refactor of code with a settled death date.

The row's Why was retired in place rather than dropped. It had run "the hardware
and TV boundaries need real interfaces regardless", and both got them — from the
two-plane split, not from any directory move: the theme manifest is the
curation→display interface, and the TV boundary became testable when `tv_delete`
took the client as a parameter instead of importing one. "Regardless" was the
wrong word, and saying so is the difference between closing the question and
deleting it.

**The row no longer quotes a module count, and that is the point.** The count had
already gone stale twice (13→14, and a line figure 19% under). It was load-bearing
only while the judgement was open; now that the norm forbids additions, the set can
only shrink, so *a root module count that has gone up is the violation* rather than
a doc-drift to sync. The tally became an invariant.

**Issue #5 was NOT closed, against a prior session's handoff, which prescribed
marking it shipped.** Eight of its nine acceptance boxes are met and verified. The
ninth is "Verified on the Pi (display plane still starts under systemd)", and no
record of that exists in the change log, the reflections, or the operator
verification queue. Closing it would have asserted a verification that never
happened — in an item whose whole subject is deployment values.

**That box is load-bearing, not ceremonial, and the check found why.** The config
hoist changed the deployment contract and the committed unit was never updated to
match: `deploy/samsung-frame-art-loader.service` passes no `EnvironmentFile=`,
while `config.py` has raised at import without five variables since 2026-07-27. It
depends entirely on a gitignored `.env` in its `WorkingDirectory`. Latent — a
running process does not re-import — but on the next restart, `Restart=always` with
default limits burns its burst allowance in about half a second and lands the unit
in `failed`, silently. `deploy/README.md` states this plainly and nothing tracked
it; it is now **issue #43**. Issue #37 was checked and does not cover it — that one
is the `Restart=always` guard missing from `operational-spec.md`, scoped to the new
unit Chunk 13 builds.

**Issue #33 carried four stale counts, not the one the handoff named.** The curation
plane's broad catches are three, not one — `mcp/server.py` plus `manifest/builder.py`
and `persistence/durable.py`, the latter two catching `BaseException`, which `BLE001`
flags as readily as `Exception` — so the estimate was understated threefold in both
places it appeared. The waived list read two and is four. Acceptance box 3 said six
unwaived root-plane catches while the issue's own Evidence section listed seven; the
Evidence was right. The fourth instance sat one section above the box, sourced from
the same list — found only because the count was recomputed rather than compared
against the adjacent line.

**Issue #24's scope had eroded into the thing it predicted.** It named the MCP layer
importing persistence directly; `http/api.py:51` now does the same, so the title is
widened to the surface layer. Its module path was also stale — the 07B split moved
the records to `curation.persistence.records`, leaving `catalogue.py` holding only
the store Protocol and its errors.

Issue #6's duplicated `prawduct` block was cleared. Low stakes alone — a closed
item's `added:` date — but the warning it tripped names no issue, so it was masking
any future instance behind a generic line.

## 2026-08-01: A model can be measured against the tool surface, and the surface can be navigated

<!-- prawduct: chunks=11 | status=shipped | scope=v1-build -->

**Why:** `api-contract.md` § Validation says the tool surface is measured, not
argued about, and draws a line the chunk entry had blurred: contract tests assert
the surface's **shape**, an evaluation harness asserts a model can **use** it.
The shape half already existed. This is the other two halves.

**Scenarios thread ids, and that is the whole design.** The runner drives real
product flows as a real MCP client, and every step passes an id the *previous*
step's envelope returned rather than one a fixture supplied. Two tools can each
pass their own tests and still disagree about the name of the thing they hand
each other; that defect is invisible from inside either one. Proven by mutation:
renaming the key `art_theme(add)` echoes back breaks two flows and nothing else.

**Every call now checks two envelope invariants**, so scenario coverage doubles
as coverage of them across the whole surface rather than wherever a unit test
happened to look — that `isError` agrees with the payload's `success` (derived in
`envelope.py` precisely so they cannot drift, with nothing asserting they hadn't),
and that the JSON text and `structuredContent` bodies match. Hard-coding
`isError=False` fails seven tests.

**The model half measures and deliberately does not gate.** It runs verifiable
operator prompts through `3tears-models` over OpenRouter, behind the `llm_eval`
marker, deselected by default. The reason is not cost — it is that a model may
reach the same goal by a different route next run, so a pass/fail gate here either
flakes or is loosened until it asserts nothing. It asserts the end state, not the
route, and reads results back through the service rather than through the tools
that were supposed to have changed them.

**The harness's own loop is tested with a scripted model**, free and
deterministic, because the first real run is the worst place to discover a bug in
it: a failure there is ambiguous between "the surface is hard to navigate", which
is the finding, and "the loop is broken", which is not. That test caught a real
defect — the driver's broad `except Exception` would have swallowed the envelope
invariant assertions and reported a contract violation as a model mistake. Narrowed
to `McpError`, and the narrowing is proven by mutation rather than assumed.

**A norm row claimed enforcement that never existed.** The manifest-channel row
named `tests/preferences/test_plane_isolation.py` as a live `Test` mechanism; no
such file has ever been written, and none could be — its subject is the `display/`
package, which Chunk 06 deferred. Corrected to Critic, and the test moved to Chunk
12, which creates that package. **This is the second such row in two sessions**,
after the broad-except row's linter claim; the recurrence is the finding, not
either instance.

**Descoped explicitly:** the plane-isolation half (issue #7) is Chunk 12's, and
issue #7 stays open. A guard walking an empty tree would have passed, which this
plan's own bar names as worse than no test.

**What the Critic caught: 2 blocking, 8 warnings, 10 notes** across three
reviewers, over the whole 89-commit bundle rather than this chunk alone. **Six
were fixed here** (`a4d4524`) — both blocking, plus four warnings. **Four
warnings were left standing and filed, not resolved:** no `security_settings`
or Origin check on the MCP session manager now that write actions and a second
unauthenticated `/api` surface exist; `activate_theme` committing before it
publishes, so a failed manifest write leaves the catalogue naming a theme the
wall is not showing; the duplicated Theme/Artist projections; and
`operational-spec.md`'s bare `Restart=always`. Said plainly because the first
draft of this paragraph counted only the six and read as a total — which would
have made the remaining four invisible in the record someone consults later.

The sharpest of the six was that the five tests proving
the evaluation driver works — deterministic, free, and the whole reason a real
run's failure is unambiguous — declared `langchain-core` only in the `eval`
group, while the canonical suite installs `dev`. So every one of them skipped in
the suite CI and the gates actually run: hand-written harness code, green, with
not one guard executed. **A test that cannot run is a weaker thing than a test
that cannot fail, and it looks identical from the summary line.** The same line
fixed the undeclared-import finding beside it. Also corrected: README and
CLAUDE.md still told a newcomer the browser interface was not built, and
`boundary-patterns.md` still read `Exists: no` for the HTTP API that Chunk 19
builds onto — both the same escalated "retiring a claim is a repo-wide grep"
learning, at its fifteenth and sixteenth recurrence.

**Verified against what would install, not what was readable.** `3tears-models` is
pinned `>=0.22.5,<0.23`; the checkout on this machine was 0.19.4, three minors
behind, and 3tears' own README says its public API shifts between minors. The
factory signature and the need for an explicit `provider="openrouter"` were both
checked against 0.22.5 in a scratch environment. **The model-driven suite has not
been run against a live model** — no `OPENROUTER_API_KEY` is set here — so its
tests are green only in the sense that they skip.

## 2026-08-01: The TV library moved two years forward, and deletion stopped being a guess

<!-- prawduct: chunks=05 | scope=v1-build -->

**Why:** The display plane's rotation design binds to this library's verified
behaviour, so the pin had to move before that plane is built. It carries no
`status=` because it is **not finished**: everything here comes from reading the
library's source and installing it, and what a television does is a separate
question that needs the set. `tv_api_check.py` is the scripted pass that answers
it, and until it runs green the new pins are unverified.

**What the verification found, past what the item anticipated.** The PyPI release
was never a candidate — it ships no async art client and no event callbacks at
all, so switching to it would have been a rewrite of the TV boundary rather than a
bump. `delete_list` is unchanged on the fork's master, byte for byte with the
two-year-old pin, so the bump does not fix it and the fallback fired. And
`upload()`'s new chunking is selected by argument *type*: a path streams, bytes do
not, and this product was reading files itself — so the bump alone would have
bought the new library and none of the benefit.

**Two costs nobody had priced.** The target imports `websockets.asyncio.client`,
which does not exist before websockets 13.0, while its own metadata still claims
`websockets>=10.2` — so this is a two-pin change that a resolver would have
allowed and an import would have failed. And building the art client now performs
blocking network I/O and raises when the set is unreachable, where the pin
deferred that to first use; the display daemon inherits that and cannot construct
one on its event loop.

**Deletion now reports what the set holds.** The new `tv_delete` verifies against
the television's own content list and keeps three outcomes apart — gone, still
listed, and unconfirmable — because collapsing them is the defect this replaces.
Images the set kept are a WARNING naming them, so the outcome cannot go
unreported even where a caller drops the result. The unconfirmable case has two
entry points that differ only in what it costs the caller:
`delete_list_confirmed` raises, and `remove_from_tv` logs an ERROR and carries on
— which is what the loader uses, because stopping there would skip the catalogue
save and every pending upload.

**Also found while verifying:** `requirements.txt` cannot stand up a working
legacy environment — `art.py` imports `cairo` and `gi`, and neither `pycairo` nor
`PyGObject` is listed, though both are in the Pi's recovered freeze. That surfaced
from actually installing the file rather than reading it.

> **Corrected 2026-08-02, then corrected again the same day — and the second
> correction is the one worth reading.** This paragraph named only the cairo/gi
> half of the gap: `astral`, `tzlocal` and `omni_epd` were missing too, and
> `suntime` was still pinned while imported by nothing. All of it is fixed in the
> 14B resolution commit, with the apt prerequisites documented beside the two
> packages that need them, and **issue #31 — which is where "filed rather than
> fixed" pointed — is closed by it.**
>
> The first correction claimed no such item had ever been filed, and that was
> wrong. #31 was open on the GitHub Issues backend the whole time; the search that
> "found" nothing read `.prawduct/backlog.md`, which this project froze when it
> moved backends. **The real lesson is not "a disposition pointed at nothing" but
> "a search read the wrong backlog and concluded the record was missing"** — the
> more useful one, and the same hazard the standing post-sync advisory names. A
> retraction written into an append-only log is worth more than a clean edit here:
> the failure mode being recorded is one an agent repeats.

## 2026-08-01: A browser can see the collection, build a theme, and read why a work is not on the wall

<!-- prawduct: chunks=10B | status=shipped | scope=v1-build -->

**Why:** Eleven chunks of catalogue, themes and manifests had no human surface. This
is the first one — `/` and `/api/*` over the services that already exist, rather
than waiting for the ones that do not. It takes the catalogue/theme/health third of
the full UI's scope and leaves the discovery two-thirds where they are, because
every one of those binds a service built later.

**The UI checkpoint was held first, and it found something.** Issue #2 was disposed
as tokens-now and component-inventory-deferred: its acceptance list asks for
components covering the candidate review grid and intent entry, and neither screen
is specified, which is why its own stage is `design`. Issue #10 was deferred, and
that one is forced rather than chosen — the second-look shelf shows works accepted
over MCP, `art_review` is declared and unbuilt, so a shelf built now would be a
surface with no producer. The third checkpoint question — does the UI scope still
match the built product — is what surfaced the defect below.

**`assess_display_fit` had no production caller, and could not have had one.** It
was built with tests in the manifest chunk; the review grid is specified to show its
verdict and the rendered size in inches. Nothing anywhere constructed the
`ArtworkBox` it takes, because the box needs a mat width and a resolution floor and
neither had ever reached the deployment surface — `nonfunctional-requirements.md`
specified both in physical units and `Settings` carried neither. Three values joined
`.env` (`MAT_WIDTH_INCHES`, `MAT_BOTTOM_WEIGHT`, `RESOLUTION_FLOOR_INCHES`), and the
resolved box is logged at startup beside the panel it came from.

**The mat's bottom weighting had never been given a number**, only a direction —
"weighted larger than the top". A box height cannot be computed from a direction, so
it had to be settled: 1.15, which is the factor that reproduces that artifact's own
42" worked example exactly (262 px of mat, a 3316 x 1597 box). Checking it against
the 75" row showed **that row is wrong** — its height implies a 1.97 weighting, so
at most one of the two could ever have been right. Corrected to 3546 x 1844, and
both rows are now asserted by tests rather than being arithmetic done once by hand.
The rounding order turned out to be part of the rule and is now stated: whole-pixel
mat first, bottom derived from the rounded top.

**Thumbnails are renditions, not a cache.** A grid of the real files is not a page —
the masters run to 47 megapixels and 40 MB. The downscaled copies are recorded as
`RenditionKind.THUMBNAIL`, which had been in the data model since the catalogue was
designed with nothing producing it, so they inherit the staleness rule that already
governs the television render instead of needing a second one. A replaced master
therefore regenerates the thumbnail rather than serving the previous acquisition —
and because that is only affordable if revalidating is cheap, the route answers a
conditional request with an empty 304 rather than the 1.28 MB below. `FileResponse`
sets an `ETag` and never reads one, so that comparison is the handler's own.
They live in a new `thumbs/`, deliberately **not** `tv-thumbs/` — that directory
holds images downloaded from the television keyed by `tv_content_id`, per-device
state of exactly the class this catalogue was rebuilt to keep out.

**Pillow arrives a chunk early**, named rather than slipped in. It was already this
plane's declared image dependency; nothing in the standard library decodes a JPEG.
Measured on the real corpus: 40 thumbnails in 6.6 s cold, 0.23 s warm, 1.28 MB
against ~1.2 GB of masters.

**The accessibility baseline is enforced, not claimed.** A test reads the real token
values out of the served stylesheet and computes every text and control pair in both
colour schemes against AA, and refuses any colour written outside the token blocks —
because "AA verified" is exactly the sentence that is true the day it is written and
false three edits later. Colour is never the sole carrier of state: every badge
pairs a distinct glyph with a distinct word.

**Resolving the review's own findings changed the surface further**, and the
record says so rather than describing the first version of it. The client now
pages the catalogue to the end instead of stopping at the API's 100-work cap —
which mattered because the theme picker shared that cap, so work 101 could not be
put in a theme at all and nothing said why. An archived work carries a badge of
its own, since the catalogue lists accepted and archived together and a card that
showed no difference was the same silence one screen earlier. A thumbnail that
fails to load falls back to the reason rather than a blank tile, and navigating
moves focus into the new view, without which the surface is not keyboard-navigable
at all.

**Running it found what the tests could not**, for the second chunk running. Two
defects were visible in the first screenshot and in no test: `replaceChildren`
coerces a null to the string "null" and printed the word on the page, and every
image tile silently returned to the shape of its own picture because a replaced
child at `height: 100%` inside a box sized by `aspect-ratio` is circular and the
browser resolves it by letting the content win.

**The verify pass then caught the same defect class inside the fix for it.**
R-4's remedy added an `If-None-Match` helper whose docstring described `*`
handling it did not implement — a false comment, one function after the one a
false comment had just been found in. Implemented and tested rather than deleted
from the docstring. Two notes were also taken: the archived badge was borrowing
the below-floor verdict's CSS class, so two unrelated states painted identically
and would have drifted together; and the client's new paging loop is control flow
no suite executes, which is filed as #30 rather than accepted, because Chunk 19
adds five more stateful screens and several of them spend money.

**One divergence was introduced and caught during the build.** Writing the browser's
"3 of 6 works are on the wall" sentence created a second hand-written version of the
tool surface's. Both now come from `ManifestBuild.summarise()`; only the pointer at
`not_displayable`, which is meaningless outside a tool result, stayed at the surface.
The shared version also fixed a case neither had: an empty theme previously read
"All 0 works in this theme are on the wall."

## 2026-08-01: The wall's own works, re-ingested — and the index read closely enough to argue with

<!-- prawduct: chunks=10 | status=shipped | scope=v1-build -->

**Why:** The v1 scope commits to seeding the new catalogue with the corpus the wall
is already running. Until this landed, no built path put a ready work in the
catalogue before Chunk 18, so the display chunks had nothing to put on a screen —
this is what makes their cutover acceptance executable.

**Counting the corpus changed the chunk.** The plan said 41 works; the index holds
41 records describing **40**. Two are the same painting — same URL, same master,
same title — differing only in the mat colour someone chose for it. Seeding both
would have put one painting in the catalogue twice, which is the thing a minted
identity exists to prevent. They collapse to one work; the operator's call was that
the later record wins and the earlier colour is dropped rather than kept as
superseded history, so the report names the discarded value. This also settles the
"41 records but 46 files in `raw/`" note that had sat unreconciled in learnings: 40
referenced masters plus 6 unreferenced files.

**The index's own parse of its artists is wrong often enough to distrust.** It
carries both the source's words (`artist_details`) and its reading of them, and the
two disagree: Brancusi's stored death year is 1952 where the source text says 1957.
Its parser only understood the newline form, so every parenthetical one — "Georgia
O'Keeffe (American, 1887–1986)" — yielded no nationality at all, as did "American,
born 1930". Reading the words instead and falling back to the stored fields
recovers nine of the fourteen missing nationalities. One record has no
`artist_details` at all and hides the whole clause in the artist's name; the year
is what tells that from an alternate name, so "Juan Gris (Spanish, 1887–1927)"
parses and "Mark Rothko (Marcus Rothkowitz)" is left alone.

**Three artifact claims did not survive contact with the code Chunk 09 built.** The
plan required the two works without physical dimensions to be *excluded* from the
manifest; the readiness rule asks for an original, a mat and a current render and
reads nothing about physical size, and `assess_display_fit` judges an original's
**pixel** size against a box built from panel geometry and a mat width in inches.
Excluding them would have taken two works off the wall that are showing today. The
plan also said those works "can get neither mat geometry nor a floor
classification" (both false) and pointed at an unknown-dimensions rule
`data-model.md` was said to owe (it owes none). Corrected in place, each with what
it said before.

**A measurement in the plan mixed units in a single sentence** — nationality and
`artist_details` counted per record, "8 have no lifespan" counted per distinct
artist. Recounted per work, and a missing *death* year deliberately earns no report
line: two of these artists are alive, and a report that lists complete works is one
people stop reading.

**Everything the catalogue records about a file is measured from the file.** Sizes
come from the JPEG frame header rather than from the index's copy of them, read
with the standard library — so no image dependency arrives a chunk early. The
reader was checked against all 41 masters: every measurement matched what the index
recorded.

**Running it found the bug the tests could not.** Every test one layer down wired
the service itself, so the command handing a *store* where a *service* belongs
stayed green all the way to the first real invocation. That is now covered by tests
that run the command, and the fix was verified by putting the defect back. Against
the real corpus: 40 works from 41 records, 40 masters hashed and measured, and a
second run creating nothing — no duplicate work, no second mat row.

## 2026-07-31: A theme reaches the wall, and says what did not come with it

<!-- prawduct: chunks=09 | status=shipped | scope=v1-build -->

**Why:** The inter-plane contract's producing half. Curation had a full data model
and no way to tell the display plane anything, so nothing the catalogue held could
reach a television. This chunk builds the manifest that will carry it, the theme
operations that shape it, and the directive that steers it.

**The carried finding was closed first, as its own commit** — the third time that
pattern has paid. 08B's review asked for the theme and display concern to come out
of `CatalogueService` before the chunk that grows it; `DisplayService` now owns
themes, membership, the standing directive and the manifest. Both it and
`DiscoveryService` hold the catalogue and neither is held by it: acceptance is a
promotion *into* the catalogue, a theme is a grouping *of* catalogue works. The
suite is the evidence that nothing changed — every test that ran before ran after,
none added and none removed, with
assertions untouched.

**What landed.** The manifest builder: atomic temp-and-rename, schema major 1,
rotation settings with a deployment fallback, label text but never label geometry,
and the directive block carried forward unchanged so a rebuild never reads as an
advance. `art_theme` and `art_display` live with thirteen actions. The TV panel's
physical geometry — never the e-paper panel's — enters configuration and is logged
at startup with the resolved `ART_ROOT`.

**The half that matters is the exclusion report.** Membership in the manifest *is*
catalogue readiness, which is what makes "the wall selects a work it cannot render"
structurally impossible; the price is that a work can sit in a theme and never
appear. So the build names every work it left out, with a cause a curator can act
on. A builder returning only a list would have passed every count assertion in the
suite and still been an incomplete implementation of the design.

**Three things the artifacts had left open, settled where the rule lives.** The
global rotation default is deployment config at 180s on shuffle, carried forward
from what the 2024 wall runs today rather than chosen. "The fetch succeeded" is not
a separate readiness check, because holding an original is what a succeeded fetch
produces — the other reading would take a work off the wall for a failed
*re*-acquisition. And activating a theme publishes it, which `api-contract.md`
already said and the first implementation did not do.

**The store gained a real widening step.** The rotation columns were the first
change to a table that files on disk already carry, and `CREATE TABLE IF NOT
EXISTS` does nothing at all to a table that exists. The intended shape is learned
by running the same DDL against an in-memory database, so SQLite parses the schema
rather than this code. Only additions; a `NOT NULL` addition with no default is
refused outright rather than half-applied.

**Four review rounds, and the last two were about prose that ships.** Two tool tips
described behaviour the service no longer had — `activate` said it did not publish,
`show_now` said only archived works were refused — and neither was visible to a
contract suite that pinned names, schemas and descriptions but never tip text. The
second fix is the recurrence rather than the instance: a table keyed on
`ExclusionReason` now asserts every cause is named in the tip and that its tokens
are distinct, and the service is driven to prove each documented refusal is one the
code actually makes. The first version of that guard shared a word between two
reasons and was green for a case it did not cover, which the next round caught.

`show_now` also widened to refuse any work that could not reach the wall, not only
an archived one: pinning an unrendered work wrote a directive naming something the
manifest does not carry, answered "the directive is written", and the wall never
moved.

## 2026-07-27: The discovery pipeline — five entities, two state machines, one repair

<!-- prawduct: chunks=08B | status=shipped | scope=v1-build -->

**Why:** The half of `data-model.md` that 08A did not carry: everything a work
goes through before it is accepted. Nothing could record what discovery proposed,
what the curator decided about a work or an image, what a run cost, or what to do
with a run whose process died — and the last of those was not a gap in coverage
but a hole in the model, because every terminal state a run had was one its own
process must write.

**The carried finding was closed first, as its own commit.** Two reviewers
independently called out `CatalogueService` — one class over nine entity families
and ~740 lines, about to gain five more. `DiscoveryService` now sits beside it and
a `Services` container binds the two; `create_app`, `dispatch` and the `Binding`
type no longer name a single service class. The helpers both services need moved
to where more than one entity already obeys a rule, so a candidate work and a
catalogued work refuse an empty title in the same words because it is the same
function. Splitting before adding meant the entity work was reviewed against the
shape it keeps rather than tangled with a refactor.

**What landed.** DiscoveryRun (both kinds, all nine statuses), CandidateWork,
CandidateImage, SpendRecord and the ResolveRunWork join — fourteen tables in the
catalogue file, up from nine. Constraints 7–9, 11, 14 and 15 enforced at write
time. Both state machines closed on their illegal edges. Acceptance as promotion.
Startup reconciliation. 405 curation tests, up from 285.

**Twenty mutations, and two of them stayed green.** Every enforcement was removed
in turn and the suite re-run — the same check that found a hole in 08A, run again
because the previous round is not evidence about this one. Eighteen went red.
Two did not, and both are the *same* species as 08A's: a behaviour tested one
layer below where its wiring lives.

- **The container's call to the discovery repair was referenced by no test.**
  `DiscoveryService.reconcile()` had six tests and every one of them passed with
  the call deleted from `Services.reconcile()`. This is 08A's constraint-10 defect
  exactly, one chunk later, in the code written by someone who had just written
  the learning about it.
- **The instance ranking passed because the store's listing order agreed with
  it.** Replacing `selection.best` with "take the first the store returned" left
  the suite green — the store orders a review card by confidence, the ranking
  orders by confidence, and the quality tie-break that separates them was never
  exercised. Two policies coinciding today is not one policy.

**`interrupted` had to exist before the double-spend guard could be safe.** A
work is refused to a new resolve run while any run covering it is non-terminal.
Every terminal state except `interrupted` is written by the run's own process — so
without startup reconciliation, one OOM kill would refuse those work ids for the
life of the catalogue, silently, on the only operation that spends money. The two
features are one feature, and the test that proves it kills a run mid-re-search
and then re-searches the work.

**`awaiting_approval` is excluded from that repair, and the reason is the deploy
step.** It advances when the *curator* approves, not when a process runs.
Reconciling it would let `systemctl restart` destroy a pending decision along with
the phase-1 spend already incurred to produce it, and curation is restarted
constantly during development.

**Two model gaps surfaced while implementing promotion, and were written down
rather than settled in code.** `data-model.md` says the candidate-side and
catalogue-side shapes mirror each other "so acceptance is a promotion rather than
a transformation" — and every `Source` field did have a counterpart except
`acquisition_method`, which is `NOT NULL`. So the claim was very nearly true and
the exception fell on the field that says how to fetch the bytes; a guess there
surfaces as a re-acquisition failing at the moment every derived file has already
been lost. It is now carried on `CandidateImage`, where the search that found the
instance is the only thing that knows it, and the artifact gained a field-by-field
promotion table so "mirror rather than transform" is checkable instead of
asserted. Separately, `DiscoveryRun.started_at` is narrowed from nullable: a row
is only created by starting a run and both entry states are active, so nullable
would have made every reader handle an absence that cannot occur.

**Ambiguity implemented literally and named rather than quietly narrowed.**
`api-contract.md` says rejecting an image moves the work to
`awaiting_better_image`, unconditionally. That includes rejecting an *alternate*
while the instance actually on offer is fine — arguably not what a curator means,
but the narrower rule is written nowhere and inventing it here would be inventing
a requirement. Implemented as specified, flagged for whoever revisits the review
flow.

**The cumulative round: 2 blocking, 9 warnings, 7 notes over 104 files.** Both
blocking findings were bookkeeping rather than code — a build-plan path missing
its `curation/` prefix, so the one mechanical pointer handed to whoever widens the
`themes` table resolved to nothing; and Chunk 06's "`r` renamed" deliverable,
never done and, unlike that chunk's three other shortfalls, never recorded. The
file is now `deploy/pi-freeze-2024.txt` and says what it is.

**One warning was against shipped behaviour and it was mine.** `fail_run` and
`halt_run_for_budget` refused only terminal states, so both were reachable from
`awaiting_approval` — and a test of mine was asserting one of the undrawn edges.
Resolved in both directions: phase 1 makes model calls and searches the web, so it
really can break and really can be refused credit, and `data-model.md` now draws
those endings from both working states; they are refused where nothing is
executing. `cancelled` stays available everywhere active, because wanting a run
gone is not declining it.

**The store was speaking one domain's language on both error paths.** `durable.py`
answered "it is already in the catalogue" for every table — including, after this
chunk, for a `CandidateWork`, which is precisely *not* in the catalogue, in a
message that reaches whoever asked. The rationale for that wording was written
when the store held one domain and was not revisited when it gained a second. A
layer that cannot see which table it refused must not name one.

**Two more retired claims that outlived their amendment**, both the shape
`learnings.md` already records as a repo-wide grep obligation: the 3tears
withdrawal was swept through the dependency lists but not through
`observability-strategy.md`, which still named `3tears-observe` as the source of
curation's structured logging — so the artifact calling structured logs the
primary signal rested on a package no manifest carries, and the log shape had no
owning chunk. It has one now. And `envelope.py` still opened with the "iff
`success` is false" reading its own `is_error()` does not implement.

**Deferred deliberately, and recorded rather than quietly dropped:**
`CatalogueService` is still 743 lines over nine entity families — 08B added a
sibling rather than decomposing it, which is what the carried task asked for and
not what it was worried about. Extracting the theme and display concern is now
Chunk 09's first task, landing immediately before the chunk that grows it, which
is the sequencing that just worked here. The MCP session table gained an idle
timeout (it had none, on an always-on unit with a `MemoryMax` cap). Three
findings about backlog routing need the operator: they turn on creating issues on
a public repository.

**Artifacts brought level with the code**, since both described a service layer
with one service in it: `architecture.md`'s internal-layering diagram (now two
services under a container, two adapters over one connection),
`boundary-patterns.md`'s service-layer and catalogue-schema entries (fourteen
tables, all fifteen constraints, both state machines), and the build plan's
project-structure comment, which still said persistence was "3tears L1
collections" — a claim 07B retired and this is the first pass to have touched the
line since.

## 2026-07-27: The accepted catalogue — five entities, nine rules, and the directive's home

<!-- prawduct: chunks=08A | status=shipped | scope=v1-build -->

**Why:** Chunk 08 as authored was the whole of `data-model.md` beyond the three
entities Chunk 07 proved — eleven entities, fifteen constraints, three state
machines and startup reconciliation, an estimated ~2,500 lines. That is one
Critic round over a diff large enough that review quality degrades, on the most
contract-setting chunk in the plan. **The operator chose to split it**, and the
line is the one the model already draws: the accepted catalogue here, the
pre-acceptance pipeline in 08B. Nothing is descoped — every entity, constraint,
state machine and acceptance question appears in exactly one half. The 07/07B
precedent is the evidence: two of that split's five defects were unreachable from
the smaller surface and were found only because the smaller surface was reviewed
on its own.

**What landed.** Five entities — Source, Original, Rendition, MatColor,
ThemeMembership — plus the Directive singleton, taking the catalogue file from
three tables to nine. The Artwork state machine (`archive`/`restore`, both
illegal edges refused). Constraints 1–6, 10, 12 and 13, each enforced at write
time in the service layer. `display_fit` as one service-layer function that
stores nothing.

**"Each constraint has a test that fails without it" was checked rather than
claimed, and the check found a hole.** Every one of the nine enforcements was
removed in turn and the suite re-run. Eight went red immediately. Constraint 10
did not: `description_markup` had thorough tests of its own, and nothing asserted
that `add_artwork` ever *called* it — so deleting the call from the service left
the suite entirely green. A normaliser nothing calls is the same defect as no
normaliser, and it looks identical from the normaliser's unit tests. Two tests
now cover the wiring, and the mutation re-run confirms they fail without it. This
is the previous cycle's learning applied forward: a claim about what the tests
pin is worth as much as the run that establishes it.

**Persistence gained a transaction seam, and it is conformance rather than
divergence.** Three of the rules span rows — exactly one theme active, exactly
one mat colour current, at most one primary source — and each is applied as a
clear-then-set pair. A pair interruptible between its halves leaves the catalogue
in the state the rule forbids: no active theme at all, and so no sync target for
the display plane. The matched framework contract threads a `conn` transaction
handle through every method for exactly this reason; this store has one
connection, so `transaction()` is the same capability with the handle implicit.

**A correction to what the previous entry claimed.** That entry said the durable
store matched the framework protocol's "decomposition, naming and argument
shape". The first two hold; the third does not, and did not when it was written —
the framework's signatures also carry `conn` and `cas`, and its `pk` is optional
where this one requires it. The module docstring now enumerates each difference
and why it is taken, instead of asserting a parity the code does not carry. This
is the fourth round in a row where the defect was a sentence claiming slightly
more than the thing it described.

**The carried finding is closed where it was raised.** The directive sequence was
pinned as catalogue-side by `architecture.md`, is restored by the exercised
restore path, and had no entity in `data-model.md` — an unmodelled part of a
persisted format is one the next chunk invents implicitly. It now has one, with
its singleton row seeded by the schema so no caller ever creates it. The pin's
clearing rule, which the finding also named as unstated, is settled and recorded:
`next` supersedes it, archiving the pinned work withdraws it **without advancing
the sequence**, and nothing else clears it — an advance on archive would fire a
directive nobody issued.

**Two gaps in `data-model.md` were found by implementing it and are now fixed
there, not just in code.** `MatColor` had no timestamp while the paragraph beneath
it required the history to be reviewable and reversible; "which colour did the new
model replace" has no answer in a set of rows with no order. And the Directive
entity above. Both are marked in the artifact as added at build.

**One test's assertion was inverted, deliberately.**
`test_a_theme_starts_inactive` asserted that a new theme is inactive. That
described `Theme.is_active` as it shipped in Chunk 07 — a column the build plan
explicitly recorded as having "no exactly-one enforcement behind it", deferred to
this chunk. Constraint 1 now governs it and says the opposite: a catalogue holding
themes with none active gives the display plane nothing to sync, and nothing
reports it. The test is renamed, keeps its location, and carries the reasoning for
the inversion in its own docstring.

**Two Theme columns were deliberately not added.** `rotation_interval_seconds`
and `shuffle` exist in the data model and are consumed by the theme manifest,
which Chunk 09 builds. Adding them here would be the first change that widens a
table an existing catalogue file already has — a migration to write rather than a
column to append quietly — and nothing reads them until that builder exists. They
land in Chunk 09 with the migration they need; a test asserts the current file
gains new *tables* on open, and says in its docstring that the next widening will
not have that luxury.

**Product verification found a defect the tests had not.** Driving a real
catalogue on disk showed the description normaliser dropping a `<script>` tag but
keeping its contents, so a scraped page's script source would have reached the
physical label as visible text. Unknown tags are unwrapped and their text kept —
right for `<span>`, wrong for code. Fixed, with tests for both the closed and the
unclosed case.

**Both suites pass**, the curation one having roughly doubled with this work. Ruff
and black clean. The real server was launched against a scratch `ART_ROOT` and
wrote a catalogue carrying all nine tables and its seeded directive row — verified
by reading the file the server itself wrote, not one a test wrote.

**The Critic ran `cumulative` over the whole branch: 0 blocking, 17 warnings, 10
notes.** It found one real defect in this chunk's own work, fixed here: **a
catalogue written before 08A upgrades into a permanent violation of the rule 08A
added.** The earlier revision created every theme inactive and shipped no way to
activate one, so such a file holds themes with none active — and nothing repaired
it, because the index the file carries states only "at most one", which zero
satisfies. `CatalogueService.reconcile()` now runs as the plane starts, promotes
the oldest theme, and logs one WARNING, because a silent condition being corrected
should say so. The read-compatibility fixture was complicit and is corrected too:
it wrote an *active* theme, a row shape the earlier revision could not produce, so
the only shape that actually exists on disk was the one nothing tested.

Also closed from that round, in this chunk's own code: `_detail` was dead and
byte-identical to `get_artwork`; an original exactly the size of the artwork box
was reported `matted_small` where both the data model and the enum's own docstring
call that `native`, now pinned from both sides; `pydantic` and `httpx` were
declared with no consumer in a manifest that states twice that the declared set
describes what the code imports; and `architecture.md` gained the two structural
patterns this bundle established — the persistence seam and the generated action
surface — plus the Decision Log entry the durable-tier answer had earned
everywhere except there.

**Ten of the seventeen warnings were one defect: artifacts describing the repo as
it was before this branch changed it.** Two still asserted the repo has no test
suite, in the bundle that established two. `project-preferences.md` — the norm
index, where staleness decides whether a rule is enforced by a linter or by a
human — still said "once ruff lands" for rows ruff now covers, still described the
pre-hoist `config.py`, and had no row at all for "no secret ever reaches a log
line". `security-model.md` still told an operator to schedule hardware access for
a coupling this branch removed. All swept, each with the retired sentence quoted
so the correction is legible rather than invisible.

That cluster is the repo's own escalated learning recurring inside the bundle that
recorded it — *"retiring a claim is a repo-wide grep, not a local edit"*. Two of
this chunk's own corrections were the same shape: the 07B parity claim was fixed
in the module but left standing in the canonical decision record and the build
plan, and the correction itself said "every framework method takes `conn`" when
`scan` does not.

**A second `verify-resolutions` pass then found the same defect class one round
later, in the fix for the first one.** `reconcile()` had five tests; the *call* to
it in `main()` had none, so deleting the line left the whole suite green — verbatim the
thing this entry had just described catching by mutation. The test that closes it
drives `main()` with uvicorn's run captured and reads the catalogue through a
second connection at the moment the server would start, so it pins the ordering as
well as the call; verified by removing the line and watching it go red. Two notes
from the same pass are closed with it: `ArtworkListing.limit` was set and never
read, and now names itself in the truncation notice, because "raise limit" is
advice a caller cannot act on without knowing what the limit currently is; and
`operational-spec.md` still opened its section with the retired 3.14 thesis in
bold, with the correction twenty-five lines below it and worded as though the
stale text were underneath.

**A third pass returned 0 blocking, 0 warning, 1 note, and the note found a real
edge the reworded message had sharpened.** Naming the limit made "raise limit"
concrete — and therefore wrong at the ceiling, where `MAX_LIST_LIMIT` is enforced
in both the service and the tool schema, so a caller at 100 was being told by name
to raise a number that returns an error. The notice now says "the maximum" and
points at `offset`, which is on the same action and does work. Pinned from both
sides of the ceiling.

**A fourth pass closed the last two, and both were the same defect walking
forward one step at a time.** Making the notice name the limit made it wrong at
the ceiling; fixing that made it recommend `offset` while its own counts still
ignored `offset`, so a caller who took the advice saw the identical sentence at
every page. The notice now reports the position — "showing 5-8 of 10" — and the
payload echoes the `limit` and `offset` that produced it, so a page describes its
own place in the set. The binding test that had been parked in the service-layer
file, whose docstring declares it independent of any surface, moved to a
`test_bindings.py` of its own; the binding layer is where the thin-binding norm is
enforced, and its tests living in a file that disclaims it is how that boundary
stops being legible. Nothing covered a truncated page at a non-zero offset; four
tests do now.

**A fifth pass found the same lesson a third time, one layer higher.** The
payload's new `offset` echo was asserted only at zero — which is also the
binding's own default, so the assertion held even if the argument were dropped on
the floor, and nothing anywhere passed a non-zero offset through the MCP surface.
That is the affordance the notice now steers a model into, and it was the one hop
never exercised. One integration call at `limit=1, offset=1` closes it, verified
against both mutations: dropping the argument and hard-coding the echo each turn
it red.

**One warning is recorded rather than resolved.** Seven backlog items were filed
into `.prawduct/backlog.md` after `project-state.yaml` declared it frozen and
repointed the live backlog at GitHub Issues, so the tooling cannot see them — two
of them, a mistyped `ART_ROOT` bootstrapping a healthy-looking empty install and
the missing Origin validation on `/mcp`, have no live tracking home at all.
Re-filing them means creating issues on a public repository, which is the
operator's call; the file now carries a note naming all seven so nothing is lost
while that decision is pending.

## 2026-07-27: The durable seam — persistence split, and the 3tears swap answered

<!-- prawduct: chunks=07B | status=shipped | scope=v1-build -->

**Why:** Chunk 08 widens the catalogue from three entities to fifteen. Whatever
shape the persistence layer has when that starts is the shape twelve new entities
get written against, so the backend question had to be settled first.

**The 3tears swap was scoped down to the durable tier, and the collection layer is
now deferred indefinitely rather than scheduled.** Reading the framework before
building against it retired the plan's target configuration and its stated reason
at once: L1 is a *named in-memory* database, so "L1-only SQLite" persists nothing
across a restart; 3tears ships no SQLite `DurableStore` (only asyncpg), so the
durable tier is this product's own code under every configuration; and collections
are async throughout with no query API, so adopting them converts three layers to
async — against the ratified "async at the I/O boundary, synchronous core" — while
listing still has to bypass the collection. The recorded reason to adopt anyway,
"the on-ramp to agents later", does not survive either: `3tears-models` depends
only on `media-contracts` and `observe`, never on `core`.

**What landed instead.** `persistence/durable.py` is a generic store — tables,
keys, rows — matching the `DurableStore` decomposition, naming and argument shape
so a future collection layer is an adapter rather than a rewrite. `sqlite.py` is
now the domain adapter above it, owning the schema, the record mapping, and the
ordering and paging that are product judgements rather than storage ones. No
framework dependency is taken, which also **withdraws** the develop-branch git
reference the previous record had accepted: an unreleased moving branch buys
nothing when no framework code is called.

**A refactor, held to that standard:** both suites pass, and **no pre-existing test
was modified or weakened** — the claim that matters about a refactor, and the one
that stays checkable against this commit forever. (Counts removed 2026-08-03: a
tally in durable prose goes stale, and these were three generations out.)

Two of the three acceptance criteria are now pinned by a test that fails when they
stop holding: read-compatibility with an older catalogue, and the rule that inside
`curation/src` only the durable store imports `sqlite3` — the latter a structural
test walking that tree, because a stray import in a service or a binding would
dissolve the seam while passing every behavioural test. (Tests are outside its
scope deliberately; one of them reaches for the driver to inspect a file
directly.) That is the same reason
`tests/test_repo_hygiene.py` exists, and the same reason it is worth doing now:
Chunk 08 writes twelve entities against this package. The third criterion — that
no existing test was modified — is a property of the diff rather than of a run,
and stays evidenced by review of the change set.

Read-compatibility with catalogues already on disk is carried by a standing test,
`test_a_catalogue_written_by_an_earlier_revision_still_reads`, not by prose: it
builds a file from the previous revision's DDL and INSERT statements, frozen as
literals so they cannot drift with the code, then reads it back through the
current `SqliteCatalogue`. What it asserts, precisely: every column of one artist
and one artwork; a second artist with all five optional columns null; a second
artwork carrying the other `ArtworkStatus` value and the absent instant; a second
theme carrying the false side of the integer-to-bool mapping; the case-insensitive
title and name orderings; and one unpaged total. It was mutation-checked in both
directions — dropping the case-insensitive sort and mis-mapping a single column
each turn it red.

**One behaviour did change, and "refactor" should not be read as covering it:** a
refused write now logs twice rather than once, because the split put the record's
identity and the SQL cause in different layers — `durable.py` journals the table
and the driver text, `sqlite.py` journals which record was refused. That is the
answer to a prior review's finding that the refusal line no longer named the
record; the message returned to the caller is unchanged.

**Five defects surfaced, all in code paths the split newly exposed** — four by
writing the tests the old code never had, the fifth by probing the new store
during review: a partial composite key answered `fetch_one`
with whichever row sorted first rather than refusing; an `ON CONFLICT` target that
is not the table's real key would have made `update` insert duplicates; `offset`
without `limit` was silently discarded, because SQLite takes no OFFSET without a
LIMIT; requiring the whole key on a *plain insert* was over-strict, since that
path reaches no key at all; and filtering for an unset column rendered `= NULL`,
which is never true in SQL, so a scan for "the rows with no artist" answered
"none" whether or not any existed. The constraint-refusal translation — which
decides whether a duplicate id and a missing artist read differently to a curator
— had never had a direct test in any form.

Four of the five are the same failure in different clothes: **an answer that is
wrong but shaped like a right one**, which no caller can detect. That is the class
this layer now refuses by construction, and it is why the split was worth doing
before twelve more entities were written onto it — the nullable-column bug was
unreachable from today's three entities and would have shipped inside Chunk 08.

The null fix then had to be **scoped to filters only**, which review caught before
it landed: the same rendering helper serves the key paths, and `IS NULL` on a key
column reintroduces exactly the failure it had just removed — SQLite does not
enforce NOT NULL on a `TEXT PRIMARY KEY`, so a null key component can match
several rows and `fetch_one` would return an arbitrary one. A null is a legitimate
filter value and an illegitimate key value; the store now says so explicitly.

**Found while verifying, and fixed here:** the change-log carried no tagged entries
at all, so `prawduct-hook regen-views` unchecked chunks 01, 02, 06 and 07 in the
build plan's derived Status block. The chunks below backfill that evidence.

## 2026-07-27: Chunk 07 — the walking skeleton, end to end

<!-- prawduct: chunks=07 | status=shipped | scope=v1-build -->

**Why:** Prove the layers connect — catalogue core, service layer, registry,
generated MCP tool over streamable HTTP — before anything widens onto them.

Landed across `4508cd3`, `bfafb70` and `e379529`. A real MCP client lists five
tools over HTTP and reads a seeded catalogue. The `final` Critic round returned 0
blocking, 21 warnings, 9 notes; fifteen were fixed in the same pass and verified by
two `verify-resolutions` deltas, and six were routed to the backlog. One contract
rule was retired rather than quietly broken — "an unknown *tool* stays a protocol
error" is not implementable on the official SDK, whose `call_tool` handler converts
every exception to a normal error result.

## 2026-07-27: Chunks 01, 02 and 06 — hygiene, deployment values, and the curation plane

<!-- prawduct: chunks=01,02,06 | status=shipped | scope=v1-build -->

**Why:** Clear the security and configuration debt blocking a build, and stand up
the plane Chunk 07 needs.

Landed in `ba007cd`. Collapsed into a single commit rather than six governed cycles
at the operator's direction — the ceremony was on track to cost more than the work,
and that stands as the working rule for mechanical chunks while contract-setting
ones keep the full treatment. Three deliberate deviations are recorded in the build
plan: no token rotation (the leaked token is expired), no `display/` project (not
needed until Chunk 12, and its dependency set is what Chunks 04–05 must verify on
hardware), and no mat regression fixture (consumed in Chunk 18).

## 2026-07-20: Last blocking finding closed; remaining warnings routed to their chunks

**Why:** R-10 was the last blocker and the only one needing an operator decision.
Closing it clears the plan to build.

**R-10 — `CandidateWork.verdict` had two writers and no rule between them.** The
curator writes it through `art_review`; a resolve run writes it on completion.
Nothing ordered them, so a resolve finishing after an accept wrote `pending` over
`accepted`, leaving a work with an `artwork_id` and a non-accepted verdict — a
combination nothing else in the model can produce or repair. Constraint 14 does
not cover it; that guards run *creation*, not the write at completion.

**Decided (operator, 2026-07-20): terminal verdicts win.** A resolve run writes
`pending` only if the work is still `awaiting_better_image` when it finishes;
otherwise its result is reported, not applied. The guard sits on the run's
completion write rather than on `set_verdict`, which stays available at all times
— **a curator must never be blocked on a background job.** The alternative
(refusing verdicts during a resolve) was rejected for that reason, and because an
interrupted run would strand the work.

The state machine also gained two edges it always had in practice: `set_verdict`
constrains its *target* value, never its source state, so `awaiting_better_image →
accepted` and `→ rejected` were reachable and unmodelled. Both are now drawn, and
Chunks 16 and 17 carry the tests.

**Remaining warnings routed, not dropped.** Per the operator's cadence decision —
build now, review at the checkpoints rather than every chunk — the twelve surviving
warnings were written into the chunks that own them, where a builder meets them,
rather than collected in a list nobody reads at the point of work:

| Finding | Owner |
|---|---|
| Mat worked examples imply two different bottom-weight rules | Chunk 18, before the mat engine |
| "No secret may ever reach a log line" has no mechanism | Chunk 02, which writes the startup logging |
| Chunk 13 has a Foreign API with no verify-api (04 verified the *build*, not the display surface) | Chunk 13, new step 0 |
| Directive sequence counter has no modelled home | Chunk 08 |
| Archiving a work has no specified manifest effect | Chunk 09 |
| Health panel omits the fields the failure table maps onto | Chunk 19 |
| `tile-cache/`, `api-cache/` have no lifecycle owner | Chunk 18 |
| Stale `deploy/README.md`; three wrong `depends_on` headers | Chunk 20 close-out |

R-6 (no test evidence) resolves when Chunk 02 lands the first suite; R-8 (tracked
token) is Chunk 01 and is why Chunk 01 is first; R-17/R-24 (revisit triggers for
the alpha and dormant pins) belong at the post-Chunk-06 checkpoint.

**No product code changed.**

## 2026-07-20: Second Critic round — two blocking closed, and one of my own claims retracted

**Why:** The review of the revised plan returned 3 blocking. Two are closed here;
the third (R-10) needs an operator decision and is not silently absorbed.

**R-1/R-21 (blocking) — the spend ceiling had no owner.** The v1 scope commits to
a "hard monthly LLM spend cap that fails closed" and the security model rates it
bound #1, *Strong*. Every chunk covered only the consumption half. Because the
ratified norm forbids an application-side ceiling, the unprovisioned key *was* the
absence of any ceiling. Chunk 14 now provisions the USD 20/month per-key limit,
adds `OPENROUTER_API_KEY` to `.env.example` (which still declared only the legacy
`OPENAI_KEY`), and — the part that matters — **proves the 402 fails closed with a
near-zero-limit key rather than asserting it**. `boundary-patterns.md` no longer
lists the ceiling as deployment config, which had invited the very
application-side enforcement the norm forbids.

**R-9 (blocking) — "panel geometry" named two different physical panels.** The TV
panel (physical inches; drives mat geometry and the resolution floor) and the
Waveshare e-paper HAT (1448×1072; drives label typesetting) were one config value,
and two artifacts concluded from the conflation that *display renders the mat* —
it does not; curation composes the mat into the `tv_display` rendition. That made
`architecture.md` self-contradictory and produced a false "two values must agree
across both planes" analysis. Separated: TV geometry is curation's alone, e-paper
geometry is display's alone, **neither is shared, so neither can drift** — the
cross-plane mismatch risk dissolves rather than needing mitigation. `ART_ROOT` is
again the only shared value. Swept through architecture, operational-spec, and
five build-plan sites.

**R-2 — a claim of mine, retracted.** Chunk 10 said all 41 legacy records carry
seven named fields, "verified 2026-07-20". I had measured four. Measured properly:
**14 of 41 have no nationality, 8 no lifespan, 8 no `artist_details` at all** — the
field the chunk's own unit test was written around — and 2 each lack medium and
physical dimensions. The chunk now states the real numbers and specifies the
consequences: Artist parsing falls back to the flat `artist` field, labels render
with dates absent, and the 2 dimensionless works seed with nulls and are reported
rather than excluded silently. The acceptance criterion changed too — it had
required an *empty* exclusion report, which the data cannot produce.

**R-4/R-18 — the uv workspace decision was mechanically impossible.** Recorded as
settled in two homes: "two projects in a uv workspace, each with its own
interpreter and its own lock". A uv workspace has one lockfile and one resolved
interpreter. Verified rather than reasoned: against uv 0.11.8, a workspace whose
members declare `>=3.14` and `==3.13.*` refuses to lock — *"error: Found
conflicting Python requirements"*. The decision's substance was always per-plane
interpreter and per-plane lock; only the mechanism was wrong, and it is amended to
two sibling projects. The build plan had hedged toward this; it is now settled with
evidence, so Chunk 06 builds a decided shape instead of rediscovering it.

**R-7, R-14 — two settled questions still written as open** (MCP resources in
`api-contract.md`; the curation host in `nonfunctional-requirements.md`, both
homes). The repo's signature defect, and cheap. `api-contract.md` is what an
implementer binds, so a live "open question" there invites re-opening settled
scope.

**R-19 — the sweep failure this session created.** Moving issue #8 upstream left
four stale pointers in `learnings.md` — the escalation document was the one home
its own remedy missed. Swept. `change-log.md` and `reflections.md` were left
alone deliberately: they are dated records, and rewriting them would falsify
history rather than correct a live claim.

**Still open — R-10 (blocking), for the operator.** `CandidateWork.verdict` has two
writers and an incomplete transition set: a resolve run completing after an accept
can write `pending` over `accepted`, leaving `artwork_id` set on a non-accepted
work. Fixing it is a behaviour decision, not a coherence fix, so it is not being
absorbed quietly.

**No product code changed.**

## 2026-07-20: Plan revised on review — seeding chunk added, governance check moved upstream

**Why:** A pre-build review of the Phase D plan against the open Critic round
found three things worth fixing before any code, and one worth moving out of the
product entirely.

**The blocking gap (Critic R-1, with R-9 as the same defect seen from the other
end):** the v1 scope commits in three places to a catalogue "seeded with the
existing 41 artworks", and no chunk implemented it. That was not a bookkeeping
miss — it made the display chunks unbuildable as written. Manifest membership
requires readiness, the only chunk producing originals/renders/mat colours was
18, and the cutover chunks accept on "theme on the wall" at 12–13. There was no
product path to any wall content. **New Chunk 10** owns the re-ingest, placed
after the manifest builder so seeding is proven by the manifest it produces.
`all.json` was checked before scoping it: all 41 records carry metadata,
`raw_file`, `mat_hexrgb`, and pixel dimensions, so the chunk is an ingest, not a
re-acquisition.

**A gap the Critic did not find:** all 41 records also carry `tv_content_id` —
the works are already uploaded to this TV. A fresh empty TvBinding table at
cutover would re-upload 41 4K images and orphan the existing set. Chunk 12 now
carries a TvBinding adoption path, verified against the TV's own list rather
than trusted, since a stale content id must re-upload normally.

**Issue #8 moved upstream, not dropped.** The decision-amendment
acknowledgement check was Chunk 01. It reads only prawduct's own data model
(`technical_decisions` markers, the `artifact_manifest` graph), so building it
here would have made this repo the maintainer of framework tooling while every
other prawduct repo re-solved it. Filed as `brookstalley/prawduct#136` with the
thirteen-recurrence evidence and the five cause classes; #8 is closed `dropped`
(not `shipped` — no work landed here). **The obligation it was to mechanize
still binds**: amendments sweep by hand per the learning, and Chunk 15 — the
plan's largest amendment burst — says so explicitly. Chunk 01's other
deliverable, the repo's first `tests/` bootstrap, moved to Chunk 02 rather than
leaving with it; that is the chunk where the first testable code appears.

**Renumbering:** with Chunk 01 gone and a new chunk at 10, old 02–10 shifted
down to 01–09 and old 11–20 kept their numbers. Done as one scripted pass over
137 reference runs, then audited — the pass missed one dependency line where a
parenthetical broke the number run (old Chunk 12's deps), caught by a bare-number
sweep. Roster, Status block, and every internal reference verified consistent;
`verify-chunk-refs` and `regen-views --check` both green. Nothing external
referenced the old numbers (no shipped chunks, no `chunks=` tags), which is why
renumbering was safe to do now and would not have been later.

**Critic R-14:** `build-plan` is now registered in `artifact_manifest` with the
edges its own front matter declares, and the "still owed" comment is struck.
Left unfixed, the plan — the most decision-dense artifact in the repo — stayed
invisible to exactly the dependency walk the repo relies on.

**Also fixed, being cheap and in the same place:** R-3 — the legacy dezoomify
`shell=True` invocation is now explicitly barred from being ported forward,
since discovery-sourced URLs are attacker-influenceable by the security model's
own reasoning; Chunk 18 requires argv-list invocation, scheme allowlisting, and
a test that asserts on the argv actually passed rather than on the absence of a
crash. R-2 — Chunk 18's verify-api step covered only the vision model while the
chunk declared dezoomify as a Foreign API too; step 0 now probes both, with
dezoomify's CLI contract captured from the installed binary rather than inferred
from the 2024 call site.

**Deliberately not fixed now:** R-6, R-7, R-8, R-11, R-12, R-13 are design
details that bind at the chunks that consume them (08/09/16/17), and are better
resolved with code in hand than by another artifact pass. R-5 (stale test
evidence) resolves itself when Chunk 02 lands the first suite. R-4 (the live
token) is Chunk 01 and is the reason it is Chunk 01.

**No product code changed.**

## 2026-07-20: Phase D — the v1 build plan authored

**Why:** Every artifact question was closed and the checkpoint review's spine was
endorsed; what remained was the plan itself. `artifacts/build-plan.md` (scope
`v1-build`) now carries twenty dependency-ordered chunks on the evidence-first
spine: groundwork at the hardware (issues #4, #5, #15, #16, plus the #9 and #3
verifications) → two-plane restructure → a walking skeleton through
catalogue/service/MCP → full catalogue and manifest → contract tests (#17, #7) →
display plane and cutover → discovery with its two spikes (#12, #18) → UI and the
exercised restore (#14) last. Issue #8's amendment-acknowledgement check is
Chunk 01, per the escalation argument (thirteen recurrences, none caught by the
author's own check). The plan declares `governed_by:` with per-norm dispositions
for the four norm-carrying artifacts — seeded with `prawduct-hook jurisdiction`,
curated to the artifacts that actually bind. Issue #6's four defects are
dispositioned in the plan (fix one now, two die with the rewrite, one deleted).
Requirements Confidence: Medium, with each named unknown tied to the early chunk
that resolves it; the operator's #13 storage decision is flagged as the one
pending input, gating Chunk 04.

**No code changed.**

## 2026-07-20: Checkpoint review landed; Critic cumulative round remediated

**Why:** The operator asked for a big-picture design checkpoint before Phase D.
The review's verdict — the design is right for the scope — landed with four
findings, each fixed in its single home: phase 1 is search-capable (a text-only
call cannot serve the Vision's own "recent award-winning work" example), the MCP
review gate's enforceable claim is "the image was there to see" rather than "a
human saw it", three directive-block semantics were pinned (monotonic sequence
across rebuilds, persisted last-acted-on value, latest-wins coalescing, plus a
regression re-baseline rule from Critic R-7), and `all.json` is retained as the
mat regression fixture. Nine backlog items filed (#10–#18), #3 and #8 annotated.

The Critic's cumulative round (1 blocking, 2 warnings, 8 notes) then found the
tenth and eleventh recurrences of the sweep-failure class: three surviving sites
of the retired "single consumer, deployed together" versioning exemption
(api-contract twice, `api_versioning_approach` in project-state — R-19's
enumeration partially consumed, again), and the rights decision's miss of
`security-model.md` plus a dangling pointer in `data-model.md`. All struck;
panel geometry's authoritative home clarified as configuration (not
display-state); `label/` retired from the prospective ART_ROOT contract; the
deploy/README `OnFailure=` prescription withdrawn as contradicting the recorded
alerting decision. Tally refreshed to eleven in learnings.md and issue #8 —
then verify-resolutions found recurrences twelve and thirteen *in the
remediation itself* (the gate-criterion amendment unswept to project-state's
goals and an api-contract quote; R-8's fourth enumerated home, the learnings
data-contract section, unconsumed). Both struck same day; **final tally
thirteen**, reconciled in learnings.md entries 11–12, this entry, and issue #8.

## 2026-07-20: Narrow the reconciliation rule, add `interrupted`, and sweep the sites the finding named

**Why:** `verify-resolutions` closed all six blocking findings from the previous
round but found the crash-lifecycle fix **over-reached**, then a further pass found
the correction had landed in only one of the three artifacts that carried the rule.

**The over-reach.** The edge was `any non-terminal ──▶ failed`, justified by "a run
only advances while its owning process is alive." True of `resolving_works` and
`resolving_images`; **false of `awaiting_approval`**, which advances when the
*curator* calls `approve` — durable, human-held state that is meant to outlive a
restart. As written, `systemctl restart` (the documented deploy step) would silently
destroy a pending approval and the phase-1 spend behind it, and curation restarts
constantly during development. **A rule justified by process liveness must apply only
to the states process liveness governs.**

**`interrupted` is now its own terminal state**, not a flavour of `failed`: "stopped
underneath it" and "something broke" call for different responses — re-run versus
investigate — which is the discriminator test already applied to `halted_by_budget`.
`api-contract.md` carries it, since an agent that can't tell them apart will either
retry a real fault forever or escalate a routine restart as a bug.

**The terminal-state count is now unstated.** It read "four" while listing five, then
"six" while another sentence 21 lines away still said four. A number maintained by
hand in prose gets it wrong; the rule doesn't need the count.

**The seventh recurrence, and its root cause is sharper than the previous six.** The
finding that produced the fix **named three files**. I fixed one. My pass-3 grep used
the literal strings from the artifact I'd edited, and `architecture.md` phrased the
same rule differently — the paraphrase blindness pass 2 exists to catch, which I
skipped because I believed passes 1 and 3 had covered it. `operational-spec.md` was
worse than stale: it told the operator that a non-terminal run with no work happening
means reconciliation is broken, which had become the exact description of a *healthy*
run waiting on the curator.

**Correction added to `learnings.md`: when a Critic finding lists files, that list
*is* the sweep set.** No graph walk was needed — the answer was handed over and a
third of it was used.

**Also:** the observability cross-reference was made true rather than deleted;
`resolve_images`'s operator-recovery row now distinguishes healthy-waiting from
stranded; constraint 14's "every terminal state is written by the run's own process"
corrected, since `interrupted` is precisely the exception; PEP 517 verification filed
as **issue #9** rather than claimed as "tracked".

**Files:** `data-model.md`, `architecture.md`, `operational-spec.md`,
`api-contract.md`, `observability-strategy.md`, `project-preferences.md`,
`project-state.yaml`, `learnings.md`.

## 2026-07-20: Address Critic findings — the crash lifecycle, the token order, flow 4, and a decision recorded in only one home

**Why:** Cumulative Critic (`rev-20260720T160759Z-cbc0d27e`, 3 reviewers) returned
6 blocking (4 distinct — two found independently by two reviewers each), 15 warning,
10 note.

**The security finding is the one to read.** `security-model.md` prescribed *rotate
first, then untrack*. That order creates a **second leak**: rotating while the file
is still tracked puts the freshly-issued token into a tracked file, and the next
`git add -A` commits it — this session alone ran that command eight times. The old
order was argued from *perception* ("untracking first looks like it's been dealt
with"), which honest prose already answers. Corrected to untrack → re-pair, and
`token_file` added to `.gitignore`.

**A hazard neither reviewer raised, found by checking the runtime:** `tvart.py` opens
`token_file` by *relative path*, and deployment is `git pull` — so the untracking
commit **deletes the file on the Pi** and breaks TV auth until re-pair. The two steps
must therefore happen in one sitting at the hardware, which is now recorded. The file
is deliberately **not** untracked in this commit for that reason: doing so unilaterally
would strand the Pi on next deploy.

**The lifecycle defect was self-inflicted, and that's the lesson.** The re-search
decision rejected a stored `resolving` verdict on the grounds that *"a crashed resolve
run would leave the work reading `resolving` forever with nothing to correct it"* —
then moved the truth to the run row **without re-asking that question of the run
row**. The defect moved with it and got worse: combined with constraint 14, a crash
left the covered works permanently un-re-searchable, silently, on the only tool that
spends money. `MemoryMax` on the curation unit exists to cause exactly that kill, and
a deploy is `systemctl restart` — routine, not exotic.

Fixed with **startup reconciliation**: every non-terminal run becomes `failed` when
curation starts. Chosen over timeouts or heartbeats because a run only advances while
its owning process lives and there is exactly one such process — so the inference is
total rather than heuristic, with no timer to tune and no liveness field to keep
fresh. `failed` being terminal is what releases the `ResolveRunWork` coverage.

**Flow 4** still had curation rendering the e-paper label in both `product-brief.md`
and `project-state.yaml` — instructing a builder straight into the geometry-in-the-
catalogue violation that `Rendition(kind='label')` was removed to prevent.

**A decision recorded in only one of its two homes.** "uv for both planes" was written
as DECIDED in `project-preferences.md` while `project-state.yaml` still said
"deliberately NOT decided here", with no `technical_decisions` entry at all. Now
recorded properly with alternatives. The claim that the PEP 517 verification item
"folds into" the existing IT8951 risk was also an overstatement — that risk is about
the interpreter version, not the build frontend — and is now tracked separately.

**Files:** `data-model.md`, `architecture.md`, `operational-spec.md`,
`security-model.md`, `product-brief.md`, `project-preferences.md`, `.gitignore`,
`project-state.yaml`.

**Deferred, not fixed (count as of 2026-07-20, `rev-20260720T164451Z-cde89172`):**
thirteen WARNING findings from `rev-20260720T160759Z-cbc0d27e` were open and recorded
as still present in the evidence store — among them panel geometry's two candidate homes, `constraint 8` vs
`api-contract.md` on what `reject_image` costs, the manifest `sequence` counter
having no persisted home, and the manifest exclusion report having no action or
result field. They are advisory at the PR gate; naming them here so the round is not
read as fully closed.

## 2026-07-20: Close the remaining decisions — mat geometry, resolution floor, rights, MCP resources, dependency manager

**Why:** Walked the operator through every decision still blocking progress. Open
questions went **6 → 3**, and none of the three remaining waits on them — all are
research items that block nothing.

**The mat geometry was never a filed question, and it blocked the filed one.** The
minimum-resolution question asked for a number. Adequacy is defined against the
artwork box, the box is defined by panel geometry and mat width — and mat geometry
was specified *nowhere*. Worse, the 2024 code contradicts the artifact: `data-model.md`
claims "the artwork sits inside a mat, the mat is the deliberate frame", but
`image.thumbnail((3840,2160))` makes the mat aspect-ratio residue, so a 16:9 source
gets **no mat at all**. The premise was aspirational and nothing implemented it.

**Decided: the mat is physical.** Specified in inches with the bottom margin weighted
larger than the top — the conservator's convention, since a true-centred image reads
as sitting low.

**Panel geometry is a deployment value, not a constant** — the operator's instruction,
because other people will run this on other panel sizes. That lands it under the
already-ratified "no hardcoded deployment values" norm and makes it the **second**
value both planes must agree on after `ART_ROOT` — with a quieter failure mode, and
therefore a worse one: nothing breaks, the mat is merely the wrong width.

**So the floor is a formula, not a number** — a minimum rendered size *in inches*,
scaling with the panel automatically. On a 42" (~105 ppi) a 12" floor is ~1260 px on
the long edge; on a 75" (~59 ppi) the same floor is ~708 px. **Below it, nothing is
silently dropped or silently accepted:** phase 2 won't auto-select a below-floor
instance, the grid shows it labelled with its rendered inches, and the curator may
take it anyway. All-below-floor lands at `resolution_status = unresolved`, which is
already first-class — the machinery landed earlier the same day.

The load-bearing detail: **a thumbnail cannot convey resolution.** 900 px and 6000 px
look identical in a review grid, so the "a human saw the artwork" gate does not by
itself prevent hanging a postage stamp. The rendered-inches figure is what makes that
judgement possible at all.

**`display_fit` is now derived, never stored — amending constraint 12.** A verdict
computed at acquisition is a stored judgement about a machine the curation plane
doesn't own, and it goes silently wrong when the TV changes. `width`/`height` stay
stored; they're panel-independent facts. Constraint 12's real intent — policy in one
place, not implicit in each renderer — is met by the service-layer norm ratified
hours earlier rather than by storage. **Third application of derived-not-stored**
after readiness and the re-search states.

**No upscaling**, so `display_fit`'s `upscaled` value is removed rather than
reserved — a declared state with no producer is the exact defect the re-search review
flagged this morning.

**Rights are display-only and gate nothing**, reframed as a provenance and
source-quality signal rather than a legal one: a holding institution's own
public-domain scan is usually the authoritative file. Reopen trigger recorded
(sharing/export, or the catalogue going public). **No MCP resources in v1** — tools
cover every read and adding resources later is purely additive. **uv for both planes**
in a workspace, with the IT8951 Cython build under PEP 517 isolation as a named
verification item folded into that driver's existing must-prove-early risk.

**Pass 3 of the sweep rule earned itself immediately** — re-reading my own edited
files caught `architecture.md` still asserting `ART_ROOT` was the only cross-plane
value, plus two stale consequence lists in `project-state.yaml`. That is the pass
whose absence caused the fourth and fifth recurrences.

**Files:** `data-model.md`, `nonfunctional-requirements.md`, `architecture.md`,
`operational-spec.md`, `api-contract.md`, `project-preferences.md`,
`project-state.yaml`.

## 2026-07-20: Address Critic findings — all 4 blocking, plus the sweep root cause

**Why:** Cumulative Critic (`rev-20260720T145500Z-2fcf2f8f`, 3 reviewers) returned
4 blocking / 13 warning / 13 note. **Two of the four blocking were defects I
introduced in this session's own commits**, which is worth stating plainly.

**R-10 — the coverage relation I assumed and never modelled.** I proposed the run
row as the fix for "nothing prevents double-submission", wrote constraint 14 to
enforce it, and never asked what data that constraint would read.
`CandidateWork.discovery_run_id` is provenance (**Q5**) and reusing it destroys
that; `parent_run_id` points at the originating run and a resolve run covers a
subset. Added **`ResolveRunWork`** — a join, deliberately, not a nullable column on
the work, because a column would be the stored-second-truth the readiness decision
rejects and would lose earlier attempts. Constraint 14, the "in flight" derivation,
and `status` reporting on a resolve run are all now answerable.

**R-2 — the sweep failed again, and the root cause is sharper than before.** The
sweep grep I ran *excluded the two files I was editing*, on the assumption that
editing a file handles it. So `data-model.md` § SpendRecord kept "re-search spend
attributes to the ORIGINATING run" — the exact rule I superseded 180 lines above it
in the same file, and whose twin I rewrote by hand in `api-contract.md`. **Plain
grep would have caught this; I removed it from grep's reach.** Correction recorded
in `learnings.md`: editing a file is not sweeping it, and the largest artifacts need
the sweep most.

**R-1 — a ratified norm violated by a numbered constraint.** Constraint 11
specified an application-side monthly spend sum driving `halted_by_budget`, which
is precisely what the provider-enforced ceiling norm forbids — and a numbered
constraint is what a builder implements. Rewritten to derive `halted_by_budget`
from a 402 and read remaining budget from `limit_remaining`; `SpendRecord` restated
as attribution and reporting only. Also fixed "calendar month" → UTC month, and
retired the "search may dominate token spend" claim resolved on 2026-07-20.

**R-3 — a norm binding four artifacts with no ratification. Now ratified by the
owner.** "Operation logic lives only in the service layer" was cited as binding and
Critic-enforced in four artifacts and leaned on five times in `project-state.yaml`,
with no decision record, no Direction home, and a circular pointer trail. Given a
Direction home in `architecture.md` with a dated marker; preferences row demoted to
a pointer. **Retroactivity was done artifact-shaped** — the correction from last
session's learning — and found no specified behaviour in violation.

**The structural cause of the repeat drift, found by the sustainability reviewer:**
both findings files sat under `artifact_manifest.findings` with **no `depends_on`
edges at all**, so the dependency-graph sweep the learning prescribes — and the
check proposed in issue #8 — could not reach the two documents carrying the most
raw decision text. That is why the retired product-wide Python target survived there
through four recurrences. Edges added; the stale target corrected in
`platform-and-dependency-findings.md`, `learnings.md`, and the retired "Pi 4
performance" rationale in `3tears-integration-findings.md`.

**Files:** `data-model.md`, `api-contract.md`, `architecture.md`,
`project-preferences.md`, `product-brief.md`, `platform-and-dependency-findings.md`,
`3tears-integration-findings.md`, `learnings.md`, `project-state.yaml`.

## 2026-07-20: Model the re-search — a run row, derived states, one entry point

**Why:** Three interacting defects the Critic raised on the one paid path, deferred
last session rather than patched because fixing any one alone moves the ambiguity
instead of removing it. They were right to be one question — fixing the first
largely dissolved the second.

**`resolve_images` now creates a `DiscoveryRun` with `kind='resolve'`.** It was a
paid, minutes-long operation creating no row at all, so the one tool the design says
is the only one that spends money had no handle to poll, no cancel, no cost of its
own, and no guard against the same work ids being submitted twice concurrently. A
resolve run enters directly at `resolving_images` and carries `parent_run_id`, so
`status`, `cancel`, `spend`, and `halted_by_budget` all work on it with no new
machinery.

**No new states — the run row *was* the missing state.** `awaiting_better_image` was
carrying "not yet re-searched", "re-search running", and "re-search found nothing"
as one value. The fix separates curator *intent* from job *state*: the verdict now
means only "the curator wants this work and this instance isn't good enough", which
doesn't change when a job starts or stops. Running derives from the run row; found-
nothing is `resolution_status = unresolved`. That follows the ratified derived-not-
stored readiness decision instead of re-litigating it — a stored `resolving` would be
a second truth beside the run row, and a crashed run would strand a work in it.

**Cost named rather than discovered later:** `resolution_status` is redefined from
"phase 2 found no credible instance" to "the latest attempt found none". Written down
explicitly, because a widened meaning nobody records is how the next drift starts.

**`set_verdict` no longer accepts `awaiting_better_image`.** Both paths reached it and
only `reject_image` set `rejected_at`, so a re-search could hand back the image just
rejected — the Q11 suppression failure reappearing on the instance scope. One entry
point makes it impossible rather than defended against.

**Swept by decision again**, and it found a dependent that names none of the changed
terms: the **per-run search cap** in `nonfunctional-requirements.md` now bounds each
*attempt* rather than a work's lifetime, because re-searches are runs. Accepted and
recorded — the monthly ceiling still bounds the aggregate and can't be multiplied by
creating runs. Also swept `observability-strategy.md`, where `run_id` now covers the
product's second paid fan-out, which previously logged with no correlation key.

**Also fixed, no pre-existing exception:** `api-contract.md` still listed the
`set_verdict` explicit-ids question as open after it was decided on 2026-07-20 — one
of the Critic's outstanding warnings.

**Files:** `data-model.md`, `api-contract.md`, `nonfunctional-requirements.md`,
`observability-strategy.md`, `project-state.yaml`.

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
