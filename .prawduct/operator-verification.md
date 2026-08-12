# Operator verification queue

Visual and live-integration work the operator has to look at with their own eyes.
An entry stays here until it is checked off; nothing here blocks a build, and
`operator_verification_required` is `false`, so this is a list rather than a gate.

**No screenshots are committed.** They are cheap to regenerate and would be stale
binaries in a public repo within a chunk. The command that produces them is in
each entry, which is the durable form.

## Pending

### The revised palette, now that it is in the stylesheet — added 2026-08-12

**Every pair passes AA in both schemes and that settles nothing you care about.**
The contrast test computes ratios; it cannot tell you whether the surface looks like
a gallery or like a beige office. `build-plan-curation-ux.md` Chunk 03 says as much
in one line — "a palette is the one thing a contrast test cannot approve on its own;
the question is whether it looks like a museum" — and that question is yours.

The light scheme is warm off-white with a near-black brown accent; the dark is a
warm near-black with an old-gold accent. Both were designed in the committed
prototype and had lived only there, hand-checked and ungoverned, since 2026-08-11.
Nothing was adjusted on the way in: every value is the prototype's.

Look at both, since the browser's own setting picks and there is no in-app toggle:

```sh
cd curation && uv run python -m curation
```

Open the prototype beside it — it is the reference for what this was supposed to
feel like, and it carries a 2,000-work corpus where the real collection is 41:

```
.prawduct/artifacts/prototypes/curation-ia-prototype.html
```

**Three things worth an opinion, because each is a judgement a test cannot make:**

1. **The accent in each scheme.** Light uses a near-black brown; dark uses an old
   gold. They are not the same hue rotated — the dark scheme's accent is doing more
   work, because a warm near-black surface gives it more room. Whether they read as
   one product in two lights is exactly the thing only a person can say.
2. **The status trio and its quiet backgrounds.** `--good`, `--warn`, `--crit` and
   their `-quiet` variants are new; nothing consumes them yet. They arrive for the
   masthead health indicator, which is the control that makes demoting Health from a
   tab to an indicator safe. They were verified against every surface by hand rather
   than by the test, because no rule references them — so they are the least-proven
   values here and the most worth a look once the indicator exists.
3. **The scrim.** A translucent black at 62% in light and 70% in dark, carrying
   `--scrim-text` over whatever image sits behind it. Worst case measured 4.96:1 in
   light. That clears AA over the extremes tested, but a scrim sits over *pictures*,
   and a painting is not a grey card.
4. **The error callout's marker, which is the one rule that changed rather than
   just its values.** It drew its left border from the accent, which worked while the
   accent was blue and body text was not. The revised palette is warm throughout, so
   that marker became a hairline in the text's own family — 1.05:1 against body text.
   It now draws from `--crit` instead, which is what that token is for and what the
   palette's own comment says status must do. **This is the one place the built
   surface looks different for a reason other than the new colours**, so it is the
   one worth checking reads as a warning rather than as decoration.

**Nothing on your wall changed.** This is the browser surface only; no rendition, no
mat, no manifest, no television.

### The clamped mats, on the seven works that were over the bar — added 2026-08-11

**The numbers are settled; the look is not, and only you can settle it.** Issue
#115 is fixed — the mechanical derivation can no longer produce a mat lighter than
the corpus's own lightest, so the 7 of 40 works that breached the bar are now 0 of
40. What that arithmetic cannot tell you is whether a mat pinned at the ceiling
*reads* well around those particular paintings. `nonfunctional-requirements.md`
§ Output Quality makes that bar explicitly subjective, so this is the same kind of
judgement as the 2026-08-03 corpus entry below.

**Nothing on your wall changed and nothing needs re-rendering.** Every one of the
40 works already carries a recorded mat colour, and existing choices are never
overwritten. This changes what a *newly acquired* work gets when no vision model
is asked — so the seven below are the evidence, not a pending repair.

The seven, with what the derivation used to answer and what a human chose in 2024:

```
  ...And the Home of the Brave   Demuth      human #27285b L* 18.8   was L* 59.5
  Sky above Clouds IV            O'Keeffe    human #2a3a5e L* 24.7   was L* 58.4
  Eggplant and Plums             Demuth      human #342547 L* 18.0   was L* 57.6
  Seascape                                   human #22394b L* 22.9   was L* 51.6
  Corpse and Mirror II           Johns       human #1c1c1c L* 10.3   was L* 50.8
  Kaldor Public Art Project 10   Koons       human #303045 L* 20.7   was L* 50.2
  Lozenge Composition            Mondrian    human #6b6b6b L* 45.2   was L* 61.3
```

Reproduce the measurement, which is free and touches nothing:

```sh
cd curation && uv run python tools/mat_masters.py ../all.json
```

**The specific question, and it is a real one.** The clamp puts a breaching work
at L\* 45.2 or darker — the corpus's lightest mat, which a human chose *once*, for
the Mondrian. (Darker, not exactly, when the work's own hue is one the panel cannot
show at that lightness: the colour goes down until it can, rather than losing its
hue and becoming a grey.) On the Mondrian 45.2 is arguably right. On the Johns,
whose human answer was L\* 10.3, a mat at 45.2 is still thirty-five points lighter
than the choice it replaces. The clamp fixes "too light to be in the corpus at all"; it
does not make the derivation choose the way you would. **If those read badly, say
so** — the answer is not a lower ceiling (that would be a number fitted to a
feeling) but that the derivation should not be the default where a vision model
can be asked, which is a live decision on #91.

### The announcement reaches both subscribers, at the set — added 2026-08-08

**This is Chunk 13A's Done-when step 0b, and it is the one thing between that
chunk and its `[x]`.** Everything else the chunk owed is built, swept and green.
The step exists because Chunk 12 was the only Foreign-API chunk that shipped
without a `verify-api`, and the seam this bundle touches is the one where getting
it wrong is silent: the television library keeps **one handler per event**, so a
label that subscribed by registering with the library would *replace* the
selection-confirmation handler, and every rotation would then report a wall that
would not move — while the label worked perfectly. The fan-out inside `SamsungTv`
is written against that constraint, read from library source and pinned by unit
tests over the handler. **No set has confirmed it.**

Needs the television awake and in art mode, and the display plane running against
it. Three things to see:

1. **A rotation still completes.** The daemon logs `rotation.selected` and the
   wall changes — that is the confirmation path resolving with a second subscriber
   attached, which is the whole question.
2. **The label follows.** The panel names the work the wall is showing. (With no
   panel attached, `label.failed` absent from the journal and
   `label_surface_working` in `display-heartbeat.json` are the proxy.)
3. **The remote is a curator too — added with the behaviour, 2026-08-08.** In art
   mode, pick a *different* work with the television's own remote, one the active
   theme carries. The label should follow within a poll interval rather than
   waiting for the next rotation. Then pick something from the set's own art store
   that this product never uploaded: the label should go **blank**, not keep the
   previous work's text. A confidently wrong label is worse than a stale one
   because the person in front of the wall cannot tell.

`samsung-tv-state-findings.md` is the record — it currently says in its own words
that this is not verified against the set, and that sentence is what this entry
retires.

### The label's type sizes, at the panel — added 2026-08-07

**Status: answered 2026-08-11, and by a different route than this entry
anticipated.** It was written expecting somebody to judge three pixel values at
the panel. What happened instead is that the operator supplied the two physical
facts nobody had written down — a 6-inch panel read from 7 feet — and those made
the sizes *computable*. The judgement that remains is one calibrated angle
(12.4 arcminutes of cap height, read off a six-rung ladder at the viewing
position), and 13B-1 derives everything else from it. The provisional constants
this entry pointed at no longer exist.

**The trap it was written to avoid was real, and worse than it looked.** The
provisional `BODY_SIZE_PX = 26` gave a 2.5 arcminute cap at 7 feet against the 5
that 20/20 vision needs to resolve a letter at all — so the label was not merely
small, it was below the threshold of legibility, and had passed a hardware probe,
a review and a cutover in that state. Nothing could have caught it, because
nothing anywhere converted a pixel into the angle a person sees. That conversion
now exists, and `display/tests/test_type_floor.py` asserts in arcminutes.

**What is still worth a look at the panel, and it is smaller than this entry
was.** Whether 12.4′ is right in *bold* — the ladder was read in regular weight,
and stroke weight matters disproportionately on a reflective panel where contrast
rather than resolution is the limit, so the family name may reach the same comfort
a size step down. Worth measuring before spending the panel's budget on size that
weight could have bought.

```sh
cd display && uv sync --group raster            # once; the Pi and CI have it, this Mac cannot
cd display && uv run --group raster python tools/label_preview.py /tmp/label.png --cap-arcmin 11
```

The tool now prints arcminutes beside every pixel size, and says what the drop
rule took off — the half that is invisible in the image.

**One observation from the derived render** (1448×1072, the margin deriving to 65,
a fully populated Hokusai record): the identification block fills the panel and
**the medium and the dimensions drop**. That is the expected finding rather than a
regression — it is what the tombstone collapse in 13B-3 exists to reclaim, and it
is why the operator put 13B-3 ahead of 13B-2 in the build order.

### What 13B-3 changed on the panel, and the two things to look for — added 2026-08-11

**Run the preview before the daemon.** The label reorganised, so the next render
looks different in three ways at once and it is worth separating them by eye
rather than in a photograph of a rotating wall:

```sh
cd display && uv run --group raster python tools/label_preview.py /tmp/label.png
```

1. **The artist now leads and the title follows it.** Deliberate — the family
   name is what a passer-by scans at 7 feet, and a long title was consuming over
   half the panel. Not a regression.
2. **Name, nationality and dates are one line** where they were three. This is
   the ~260 px the collapse was for. Modelled against two real works it turns
   three dropped lines into one — but that was an arithmetic stand-in for the
   measurer, not Pango, so **the panel is what settles whether it is enough**.
3. **The whole identification line is set at the primary 12.4′ tier**, because
   the layout sizes by position and that line is now first. On a long name it
   wraps to three rows and eats roughly 90 px the floor would not have.

**The thing to judge, and it is a real question rather than a formality:** the
identification line reads `O'KEEFFE, Georgia, American, 1887–1986` — four
comma-separated parts, where the first comma means "inverted" and the others mean
"and". The argument for it holding together is that **weight** separates the
family name from the rest, not punctuation — and **13B-2 has not landed, so
nothing is bold yet.** What you will see is four undifferentiated parts. If it
reads badly *with* the bold capitals in place, the fallback is the name on its
own line, which costs about half the collapse's gain.

**Also worth a glance, and it is data rather than type:** two of the 31 seeded
artists carry something that is not a demonym in the nationality slot — Moche
reads `Moche, North coast, Peru` and Kandinsky's is a birthplace clause. Left as
the institution published them; correcting them is a curation-content call, and
this entry is where it is being put to you.

### The display daemon against the wall — added 2026-08-06

**Status: answered on 2026-08-07 — all three acceptance criteria met on the real
set, and the pass found a defect on the way.** Three unattended rotations at the
manifest's 180 s (Calder → Hokusai → Klee; intervals 182 s and 181 s), each
matching what the operator saw with their own eyes; the third with the curation
plane stopped; then a restart that re-showed the same picture without moving the
wall and carried on to the next work. Items 1, 3, 4 and 5 below are settled.

**What the pass found, because it is the reason this entry was worth keeping
open.** The confirming read shipped the day before was wrong in the direction
that stops the wall: `get_current` describes the art-store slot, not the display,
so every real rotation read as a failure and the wall parked on one picture.
Confirmation is now the set's own `image_selected` announcement. The read had
been verified against a *dark* set, where it agrees with the failure because it
never changes at all — which is why one state's worth of evidence proved nothing.

**Still owed here:** item 2 (`next` / `show_now` latency, which needs the curation
plane up), item 6 (brightness across a dusk), and item 9 (whether the five-minute
recovery ceiling reads as broken in the room).

**The television has to be in art mode, and what makes that hard to see is that
almost everything works without it.** This paragraph previously said that a set
in standby refuses the handshake and answers `ms.channel.timeOut`. **That is
wrong, and it was measured wrong on 2026-08-07**: with the set dark and reporting
`PowerState: standby`, both websocket channels opened, and uploads, deletions,
listings, brightness and the whole of `available()` worked. The daemon ran a full
pass against it — disabling the native slideshow, removing 41 orphans, uploading a
work — and the only thing that failed was the picture changing.

**So `PowerState` tells you whether the panel is lit and nothing more** — it
reads `on` for art mode and for somebody watching a channel alike. **`get_artmode`
is the discriminator**, answering `on` only in art mode, and the daemon now gates
every selection on it. The full map is `artifacts/samsung-tv-state-findings.md`;
read it before concluding anything is broken.

The consequence for whoever runs this: the set cannot be woken over the API
(`set_artmode('on')` returns cleanly and does nothing, and Wake-on-LAN to the
advertised MAC has no effect), so **someone has to be at the set** to put it into
art mode. `PowerState` is still worth reading first, as the cheapest thing that
distinguishes a dark panel from a lit one:

```sh
curl -s http://<TV_ADDRESS>:8001/api/v2/ | python3 -m json.tool | grep PowerState
```

**What remains here is the daemon itself.** The pin bump this entry used to ask
for first — the 2026-08-06 security work moving `aiohttp` 3.9.5 → 3.14.3 under
the television client, backed until then only by a call-site check in a clean
interpreter and a sibling lockfile resolving the same fork commit — **ran against
the set on 2026-08-06 and passed 9 checks, 0 failed**, on `aiohttp` 3.14.3,
`websockets` 16.1.1, `requests` 2.34.2 and the pinned fork. That is a measurement
on the hardware rather than a resolver argument, and it is recorded with its
numbers under the 2026-08-01 entry below. Rollback for the pins remains
`deploy/pi-freeze-2024.txt`.

```sh
cd display && uv run python -m display
```

**What to watch for, each being a behaviour chosen against a plausible
alternative:**

1. **The wall rotates the active theme**, and the first picture appears in
   seconds rather than minutes — uploads are carried one per pass precisely so
   the wall is not blank while forty works go up.
2. **`next` and `show_now` land within about a second.** That is the poll
   interval's whole justification; if it feels slow, the number is wrong.
3. **A restart neither moves the wall nor loses its place.** Stop the process and
   start it: the same picture should still be there, and the *next* rotation
   should go to the work after it. This one was got wrong in the first
   implementation and is the most likely to be got wrong again.
4. **Killing curation changes nothing.** Stop the curation plane and leave the
   wall alone for a few rotations.
5. **The legacy uploads are gone from the set**, and the works the manifest names
   are the only things in the user-upload category. A fresh binding table treats
   everything already on the television as an orphan — that is intended, and it
   is the one step that is not reversible from here.
6. **Brightness follows the sun.** Worth looking at across a dusk rather than at
   one instant; the curve is ported from the 2024 plane and should not read as a
   change to anyone living with it.

**These three need a person at the set**, which is the whole reason this entry
cannot be closed from a desk:

7. **A rotation the set performs is confirmed against the set's own word.**
   *Settled 2026-08-07.* The daemon waits for the television's `image_selected`
   announcement — which names the image and carries `is_shown` — before claiming
   to have shown anything, and every rotation of that pass matched what the
   operator could see. The earlier read this entry described, `get_current`, was
   removed: it reports the art-store slot rather than the wall, so it denied real
   rotations and parked the wall on one picture.
8. **Then switch the set off and leave the daemon running.** Expect exactly one
   INFO — `the television is not in art mode; leaving the wall alone until it is`
   — and then silence, not a line per interval. A set that is off is never asked
   to select at all now: selecting on a lit set that is showing a *programme*
   switches it into art mode and takes the screen off whoever is watching, so
   nothing reaches the wall unless `get_artmode` says art mode is on.
9. **Switch it back on, and time how long the wall takes to come back.** Expect
   one `the television is changing what it displays again`, and the wall to
   resume **on the work it was deferred at**, not somewhere further along the
   theme. **Expected to be about a second, and that is the thing to check.** The
   backoff ladder still runs to 300 s, but the set *announces* its own art-mode
   transitions and that announcement clears the wait — so switching the panel on
   should bring the wall back on the next poll rather than after a wait that has
   doubled its way up. If it instead takes minutes, the announcement is not
   arriving and the ladder is doing the work: say so, because the fix is then a
   different one from lowering the ceiling.

`artifacts/samsung-tv-state-findings.md` is the map of which call works in which
state, and carries its own list of what is still unmeasured — what
`select_image` does to somebody watching television, whether `KEY_POWER` lights
the panel, and how many art-channel clients the set allows at once. If you are at
the set anyway, those are cheap to settle and nothing else can settle them.

### The review half — the grid, its alternates, the panel — added 2026-08-05

**What to look at.** The review grid reached from a finished run ("Review these
works"), the alternates behind a card, and the Health tab. This is the screen a
curator spends their session in, and the tests hold that every figure on it is
right; what they cannot hold is whether judging thirty paintings on it is
pleasant or a chore.

**Free to look at if a run already exists**, which it will if you looked at the
run half. Nothing on this screen spends — accepting, rejecting and choosing a
scan are all local — with one exception named on the screen itself: "Look again
for these" starts a re-search, which does spend.

```sh
cd curation
uv run python -m curation
# then open the CURATION_PORT from .env — http://127.0.0.1:8770/ as shipped
# → Discovery → open a finished run → "Review these works"
```

**Specific things worth an opinion, because each was a judgement call:**

1. **The alternates are a disclosure on the card, not a screen of their own.**
   The choice is between the picture on the card and the ones behind it, and a
   curator who had to navigate away would be choosing from memory. The cost is
   that opening one pushes every card below it down the page. A side panel or a
   modal would trade differently.
2. **A "Why (optional)" field on every card.** It is what makes a rejection say
   *why* — a studio copy rather than merely "no" — and it is also a text input on
   thirty cards, which is a lot of furniture. It could be revealed only when
   Reject is pressed, at the cost of a second click on the commonest path.
3. **A work whose every scan is below the floor still shows a picture**, with a
   note saying accepting will be refused until a scan is chosen. The alternative
   — hiding it — is the one thing the contract forbids, but the note is doing
   real work and it may not be doing enough of it.
4. **The health panel prints the display plane's reported document as raw
   key/value rows.** Nothing writes one yet, so today it is invisible; it will
   read machine-ish when Chunk 13 lands. Deliberate — only `reported_at` is
   contract, so naming the other fields here would invent a second one — but if
   it reads badly in practice that is worth knowing before the writer exists.
5. **Backup age says "No backup has recorded itself here"**, permanently, until
   Chunk 20. It is a true observation and the panel's whole contract is stating
   those. Say if it reads as a defect rather than as a fact.

**The operator walked this on 2026-08-05.** Against a corpus of 40 accepted works
— all rendered for the first time that day — and the 19-work Dali run. Findings
below; each was checked against the code or the catalogue before being written
down, and which ones are defects rather than preferences is stated rather than
left to the reader.

*On the five questions above:* only **#5** was answered — the backup line reads as
a fact, not a defect, and stays. #4 was not reachable (nothing writes a heartbeat
yet, so the panel shows the absence sentence rather than the key/value rows the
question is about); re-ask it when Chunk 13 lands. #1 was answered *against* the
current design, by #C below. #2 and #3 went unremarked.

**Confirmed defects — verified, not merely reported:**

- **A. `Other scans (N)` counts the scan already on the card.** The disclosure is
  labelled from `instances_held`, which is every instance the work holds
  *including the one pictured above it*. Every work in the Dali run holds exactly
  one, so nineteen cards invite a curator to open "Other scans (1)" and find
  nothing they had not already seen. The operator guessed this from the screen and
  the catalogue confirms it: one instance per work, and it is the selected one.
  Either the count drops the shown instance or the label stops saying "other" —
  and the two are not equivalent, because a curator uses the number to decide
  whether opening it is worth the scroll.

- **B. Seven `proposed_title` values are corrupted, and it is the data, not the
  rendering.** They end mid-citation on a dangling open parenthesis — *"The
  Persistence of Memory (1931) - cited from blog.artsper.com ("*.

  **Fixed 2026-08-05, and the cause was ours rather than the model's.** This
  entry first read "nothing in this codebase truncates a title, so phase 1's
  model emitted them this way", which was wrong: `clean_name` did it. The model
  wrote an ordinary bare citation — `- cited from blog.artsper.com
  (https://blog.artsper.com/en/a-closer-look/dali/)` — and the rule that strips a
  URL was greedy to the next space, so it ate the bracket that *closed* the
  citation and left the one that opened it. Feeding that exact string to
  `clean_name` reproduced the stored value character for character. The
  hypothesis was checkable in one command and was not checked before it was
  written down.

  **The visible half was the smaller half.** `work_dedup_key` is derived from the
  same cleaned title, so each of the seven keyed as a different painting from the
  same work proposed cleanly — a rejection would not have suppressed the work it
  was about, silently, which is the failure a curator cannot see. Both halves are
  repaired at startup and both are pinned by tests.

**Requirements the walkthrough surfaced — none of them designed here:**

- **C. The alternates disclosure is unusable in a grid column.** This answers
  question #1 above with a failure rather than an opinion: expanding "other scans"
  crams the alternates into the narrow column the card occupies. The disclosure
  shape is the problem, not its contents.

- **D. An accepted work should be pictured as it will hang** — the composed
  render, mat and mat colour included, rather than the bare image. The preview a
  curator judges by should be the thing the television shows.

- **E. Mat colour has no control on any human surface.** `set_mat` and
  `choose_mat` exist as services and as MCP tools, so an agent can do what a
  curator cannot. What is asked for is re-running the AI choice, plus one-press
  black and one-press off-white — the two neutrals a curator reaches for without
  wanting a judgement made about them.

- **F. The run table should show a thumbnail where it says "has an image".** *(Open — issue #92, re-scoped S -> M on 2026-08-06; the run view's rows carry no instance reference, so the thumbnail needs a payload decision. The words it quotes now read "the run found an image", per issue #99.)* On
  the run detail view the Image column renders the words `has an image`; the
  review grid beside it shows the picture. A curator scanning a run is asking
  *which* image, and the answer is already on disk.

- **G. "Where it came from" is not understood.** *(Resolved 2026-08-06, issue
  #93.)* It headed the run table's provenance column and meant *how this row
  entered the run* — asked for by the model, or offered by the collection on top.
  In an art catalogue that phrase reads as the work's own provenance, which
  museum holds it.

  **The column is gone rather than renamed**, which is a correction to the
  sentence above: it was *not* "doing necessary work" on that screen. The
  offered/asked-for distinction is necessary, and this table was its fourth
  statement — after the tally's separate counts, the run sentence, and the line
  directly above the rows. What the per-row badge added was which *particular*
  work was offered, on a screen where nothing is decided per work. The badge
  stays on the review card, where the deciding happens.

- **H. A per-work preview of the e-paper card** would be welcome once that card
  exists. Depends on Chunk 13; recorded here so it is not rediscovered.

- **I. The offered-work sentence contradicted the screen it was printed on.**
  *(Fixed 2026-08-10 — see the annotation at the end of this entry. What follows
  is the observation as it was recorded on 2026-08-05, in the tense it was found
  in, because it is the evidence rather than a description of the product.)*

  Every offered card read *"…an artist this run named but could not confirm a work
  for"*, while seven works the run named for that same artist sat on the same
  page. The Dali run holds 7 `proposed` and 12 `offered`; the seven are real
  proposals — *The Persistence of Memory*, *Lobster Telephone*, *Metamorphosis of
  Narcissus* and four more — and each is badged `not held`. So the sentence is
  true only under a narrow reading of *confirm* ("resolved to a work the
  collection holds"), and nothing on the screen teaches that reading. The
  operator's objection was that the works say "Salvador Dalí" right underneath;
  the sharper version is that the run demonstrably *did* name works for the
  artist, and the sentence appears to deny it.

  `_offer_rationale`'s docstring anticipates the near miss — it notes the artist
  named is the run's spelling while the work carries the collection's own
  attribution — so the collision was seen from the writing end and judged
  survivable. Seen from the reading end, on a page carrying both halves at once,
  it is not.

  **A second unexplained number sits beside it.** The sentence says *"one of 25
  works it holds"* and twelve cards appear, because `offered_works_per_run` caps
  the offer at twelve. Each number is honest alone; together, and split across
  two views, they invite a curator to go looking for thirteen missing works. Any
  rewording should carry the cap or drop the total.

  Repetition compounds all of it: this is one identical 30-word sentence printed
  twelve times down a single page, carrying per-*group* information on a per-card
  line.

  **FIXED 2026-08-10 by issue #95 — and the fix is not visible on an old run.**
  The paragraphs above are kept in the past tense they were written in, as the
  record of what was seen; `_offer_rationale`, the function they reason from, no
  longer exists. Offered works now store the query that produced them
  (`offered_for_artist`, `offered_artist_matched`) and the review grid says it
  once above that query's works, reconciled against what the run offered.

  **To verify, start a fresh run — do not reopen the 2026-08-05 Dali run.** Rows
  written before this change keep their old sentence in `rationale` and carry no
  query, so that run renders the old wording and collapses into a single unnamed
  group: the defect, apparently unchanged. There is no backfill, by the operator's
  decision of 2026-08-10 that old runs need not be preserved and the database may
  be zeroed. What to look for on a new run: the denial gone (the page says the run
  found no *image* for the works it named), one sentence per artist rather than one
  per card, and the holdings total reconciled with what the run offered.

  **A fourth check, and it is the one here that needs eyes rather than a test.**
  (Not "no test can make": the *scoping* half — that a card title inside a group
  is styled the same as one outside it — is arithmetic, and a browser test now
  compares the computed margins. What follows is the judgement half, which is
  yours.) Each artist's
  offers sit in their own block with a heading above them — look at whether the
  groups are visually separated from the works the run named and from each other,
  and whether the heading reads as a heading rather than as browser-default bold.
  The browser suite asserts the heading's *text* and the group's attributes, and
  both are correct whether or not a single line of that block's styling exists;
  this bundle shipped with none of it until a reviewer read the page as a page.

## Decisions taken during the 2026-08-05 walkthrough

**The mat policy, settled with the operator against the corpus rather than in the
abstract.** Recorded here because it changes what item **E** above asks for, and a
reader finding E alone would build the wrong thing.

- **Every work always has a mat**, and the non-AI default is the **existing
  dominant-colour derivation** (Pillow median-cut), not off-white. Off-white was
  the operator's opening proposal and was withdrawn on evidence: the 41 hand-tuned
  2024 mats run L\* 6.7–45.2 with a median of 20.7, `nonfunctional-requirements.md`
  § Output Quality makes that corpus the regression bar, and
  `test_mat_corpus.py`'s `CORPUS_MAX_LIGHTNESS = 50.0` enforces it. The named
  failure mode — a pale work competing with a lighter mat — is the reason the bar
  exists. The mechanical fallback is free, deterministic, already built, and lands
  in the region the corpus occupies.

  **The last clause was measured on 2026-08-10 and is false** — see the amendment
  below. Kept in place rather than edited, because it is the belief the decision
  was taken on, and a reader who finds only a corrected sentence cannot tell that
  the premise was ever checked. The decision itself survives; its precondition
  does not.
- **Black and off-white become presets a curator presses**, so choosing one is a
  judgement someone made rather than something applied silently to forty works.
  **Superseded 2026-08-10 — see the amendment below:** the values are `#222222`
  and `#6b6b6b`, off-white is withdrawn a second time and pure black was never in
  the corpus. Marked inline because this bullet reads as an instruction to build.
- **The AI becomes an opt-in button that offers several candidate colours** shown
  against the work, with nothing applied until the curator picks one. The current
  choice stays current until then. This makes the spend buy options rather than a
  fait accompli, and it is the control that must say on itself that it spends.
- **Existing mats are never overwritten** — already true today and not a change:
  `prepare(force=True)` re-renders without re-choosing, and `mat_colors` keeps
  every choice with one marked current.
- **Consequence to retire deliberately:** a guaranteed default means the
  `NO_MAT_COLOR` exclusion can never fire again, so that branch and its reason
  become dead and should be removed rather than left looking live.

## Decisions taken 2026-08-10, on measurement rather than at a walkthrough

**These amend the 2026-08-05 mat policy above and close the discovery items #90
and #91 were filed to open.** They came out of measuring the claims the earlier
session recorded, against the operator's own `ART_ROOT` — which is why they are
dated separately rather than folded into the walkthrough that could not have
known them.

- **The mechanical derivation is fixed before it is promoted to the default.**
  Paired against the hand-tuned mat for the same painting it is lighter on 31 of
  40 works (median +15.2 L\*) and breaches `CORPUS_MAX_LIGHTNESS` on 7, where the
  human breached it on none — full figures in `nonfunctional-requirements.md`
  § Output Quality. Two changes, both measured: **clamp** the derived lightness to
  the corpus ceiling (takes 7/40 over the bar to 0), and **merge perceptually
  identical clusters** before taking the largest (takes a re-encode flipping the
  answer from 5/25 works to 2/25 — median-cut splits one perceptual colour across
  clusters and then loses the vote to a smaller rival, which is what puts teal on
  an Albers whose orange covers more of it).
- **The two presets are `#222222` and `#6b6b6b`, and off-white is withdrawn a
  second time.** Both values are the corpus's own; the reasoning is in
  `nonfunctional-requirements.md` § Output Quality, recorded there rather than
  here because it is a standing quality rule and not a meeting outcome.
- **The AI button offers three candidates, each composed against the work**, with
  nothing recorded until one is picked. Swatches were rejected: a mat is judged by
  how it reads *around* a picture, and a 40px square is not that judgement. Three
  rather than five because the tail candidates would not be chosen and five
  composed canvases is a lot of page for one decision.
- **The review grid keeps the bare candidate scan** — finding **D** is answered
  "no" for that surface, deliberately. At review time nothing is acquired and no
  mat exists, so an "as it will hang" preview would have to derive a mat from the
  480px museum preview; measured, that differs visibly from the master's answer on
  5 of 25 works, one of them flipping orange to teal. The judgement the review
  grid exists for is *which painting, and is this scan good enough* — the mat
  judgement belongs on the work detail, after acceptance, where the real composed
  canvas is.
- **Finding D's actual cause is a caching defect, not a missing feature.** The
  works grid and the work detail already ask for the composed canvas, and
  `sourceBadge` already distinguishes it from the master. What breaks is that a
  thumbnail's freshness is tested against the *original*'s hash, and composing a
  canvas does not change the original — so a thumbnail made before the first
  preparation is never regenerated, and the card serves the bare master under a
  badge reading "wall render". That is issue #90 now.

### The run half of the browser surface — added 2026-08-05

**What to look at.** The Discovery tab: entering an intent with the estimate
beside the field, the approval gate, and the run view while a run is working and
after it has finished. The tests hold that every figure is correct; what they
cannot hold is whether the screen makes the decision it is asking for an easy one.

**This look costs money, and here is exactly how much.** A real run spends about
**$0.013** — the phase-1 model call plus its search allowance. Everything except
starting a run is free to look at: the estimate, the run list, and any run
already in the catalogue. If you would rather not spend, the first two are still
worth an opinion and the third can be read against a run from an earlier session.

```sh
cd curation
uv run python -m curation
# then open the CURATION_PORT from .env — http://127.0.0.1:8770/ as shipped
# → the Discovery tab
```

Without `OPENROUTER_API_KEY` set, starting a run is refused with a sentence
saying why, which is itself worth seeing once — it is the first thing a fresh
deployment does.

**Specific things worth an opinion, because each was a judgement call:**

1. **The estimate sits above the button, not beside the result.** It reads
   "Asking costs at most $0.01336. One model call plus up to 10 web searches,
   which is the most phase 1 may use. Bounded, not typical." A ceiling rather
   than a typical figure, because a run may use the whole allowance. Two
   opinions wanted: does a bound read as reassuring or as evasive, and are five
   decimal places on a hundredth of a dollar precision or noise? The figure is a
   `Decimal` for good reasons and rendering fewer digits is a display choice
   nothing else depends on.
2. **A second estimate appears at the approval gate**, because that is where the
   phase-2 decision is actually made. It reads "Approving costs $0. Resolving
   the N works this run proposed. Phase 2 asks museum APIs, which are free, and
   identifies works locally — so approving this run spends nothing further. The
   gate is on the work count, not the price." The basis is doing the work there;
   a bare "$0" beside an approve button would invite reading the gate as being
   about money.
3. **Two badges per work: where it came from, and whether it got an image.**
   Offered works — the ones a wired collection volunteered rather than ones the
   model named — carry a 2px dashed border and the word "offered", against the
   plain border and "asked for" of the rest. The whole design rests on a curator
   seeing that difference *without reading*, because accepting an offered work
   believing you asked for it is the failure this labelling exists to prevent.
   Can you? Two badges sit in one cell and this is the densest thing on the
   screen; if it reads as clutter, say so.
4. **An unresolved work's reason is a badge with the sentence in its tooltip.**
   "too small", "wrong artist", "not held". Only "not held" suggests the work may
   not exist. Is the short word enough on its own, or does the distinction that
   matters need to be on the page rather than on hover? A tooltip is invisible on
   a touch screen and to anyone not hunting for it, which is the argument against
   the current choice.
5. **The page polls every two seconds and stops when the run ends.** Watch a run
   from `resolving_works` through to a terminal state. Does it feel live, or does
   it feel like it is doing nothing? Two seconds was chosen against a Pi's
   modesty, not measured against a curator's patience.

   **A test makes this check now, and it is still worth making by hand once.**
   On a run sitting at the approval gate, press Tab until "Approve the list" has
   the focus ring, then take your hands off the keyboard for ten seconds and
   press Enter. It must approve. A repaint on each poll would have thrown the
   focus away silently, so what you are checking is that the page leaves the DOM
   alone when nothing about the run changed. Do the same on a run that *is*
   changing — focus will legitimately move there, and that is the cost of the
   view being live.

   **What covers this, corrected 2026-08-05.** This paragraph used to read "the
   client has no test runner … none of them is executed by a test", and invited
   reopening that trade if the surface kept growing logic of this kind. It did,
   and the trade was reopened and settled: the client is executed by a real
   browser against a real server in `curation/tests/browser/` (marker `browser`).
   The focus check above, the supersession of an in-flight repaint, and the
   polling are each executed — by `test_a_poll_that_changes_nothing_leaves_the_focus_alone`,
   `test_a_paint_superseded_in_flight_never_reaches_the_page`,
   `test_two_concurrent_paints_leave_only_one_poll_chain` and
   `test_leaving_the_run_view_stops_its_polling`. **The no-build-step decision
   this entry named is untouched** — it governs the *shipped* client, which is
   still one hand-written file served as-is; what landed is a dev and CI harness.

   **So the honest limit has moved rather than gone.** No browser test judges
   whether the screen is legible, whether the layout holds at the window size you
   actually use, whether two badges in one cell read as dense or as clutter, or
   whether the decision this page asks for is an easy one to make. Those are what
   this entry exists to collect, and they are why it is still Pending.
6. **The searches table prints raw ISO timestamps** — `2026-08-05T13:14:25.812…`
   — because that is what the rest of this surface does (the health panel shows
   `reported_at` the same way) and inventing a date format for one table would
   make it the odd one out. It is still the worst-reading thing on the screen,
   and the run list is the one place a curator scans many of them at once. If
   you want them humanised, that is a convention decision for the whole surface
   rather than a fix here, and it is yours to make.
7. **The completed sentence rates over what the model proposed.** "This run
   finished: 1 of 3 works it was asked for have an image", with the offered works
   named in a separate clause. The alternative — one merged count — reads better
   and reports a resolution rate the run never achieved. Confirm the honest
   version is legible enough to keep.

### The mat corpus look — is the new engine at least as good as 2024? — added 2026-08-03

**This is the product's stated quality bar and no test can settle it.**
`nonfunctional-requirements.md` § Output Quality says mat colour must be at least
as good as the 2024 implementation, that the bar is explicitly subjective, and
that an engine scoring well on any metric while producing visibly worse mats on
the 41-work corpus has failed. So the suite holds the one property the corpus
states unambiguously — every one of the 41 is darker than mid-grey — and this
entry holds the rest.

A full run is already done and its numbers are worth having before you look:

- **33 of the 41 compared.** The other eight are held outside the Art Institute
  and the tool only resolves `artic.edu` URLs; it names them at the end rather
  than quietly reporting 33 as the corpus.
- **Median CIEDE2000 distance to the 2024 colour: 9.8** (min 1.0, max 34.9).
- **The central tendency is the same.** New mats have a median LAB lightness of
  20.8 against the corpus's 20.7 — the engine lands in the region 2024 landed in.
- **One of 33 crossed the darkness bar** — a Rothko given `#8a7a6a` (L\* 52.2)
  where 2024 chose `#1c1818`. Two more sit just under it.
- **Zero mechanical fallbacks**, after the output reservation was raised.
- **It cost $0.0024.**

Regenerate the sheet and compare each pair by eye:

```
cd curation
uv run python tools/mat_corpus.py ../all.json --out /tmp/mat-corpus
open /tmp/mat-corpus/corpus.jpg          # 2024 on the left, the engine on the right
```

**Three specific pairs are worth your attention first**, because they are where
the engine and 2024 most disagree and where I think 2024 may be the better
choice:

1. **Untitled (Purple, White, and Red)** — the one over the bar. `#8a7a6a`
   against 2024's near-black `#1c1818`.
2. **Sky above Clouds IV** — `#4a7c9d` against `#2a3a5e`. The work is pale and
   the lighter mat competes with it; this is the failure mode the bar exists for,
   arriving just *under* the bar at L\* 49.9.
3. **...And the Home of the Brave** — `#4a5d75` against the deep indigo
   `#27285b`. Debatable rather than wrong.

**One thing to know before reading the numbers as a baseline:** the model is not
deterministic. The same work asked twice gives different colours — this work drew
`#27285b`, exactly the 2024 colour, on an earlier run and `#4a5d75` on the full
one. So a corpus run is a sample of the engine's behaviour, not a fixed output,
and a single bad pair is weaker evidence than a pattern across several.

If the verdict is "worse than 2024", the cheapest levers in order: the prompt in
`acquisition/mat.py` (`MAT_PROMPT` — its guidance is deliberately carried over
from 2024's, so it is the least likely culprit), then `MAT_MODEL` in `.env`,
which was chosen on cost among models that cleared the bar rather than on taste.
`art_catalogue(action='set_mat_color', ...)` overrides any individual work
permanently, and the previous colour is never discarded.


### A curator can see the candidate images in their own client — added 2026-08-03

**Visual, and it is the one thing this chunk's tests cannot prove.** Chunk 17A
returns candidate thumbnails as MCP image content blocks. The suite asserts the
blocks are present, correctly sized, and correctly correlated to their rows — but
what a *client* does with them is the client's business, and the whole safety
argument (`security-model.md` § Content Appropriateness) rests on the picture
actually being visible at the moment of judgement. A block that every test
accepts and Claude Code renders as a broken box would satisfy the suite and
defeat the gate.

Point a real MCP client at the running plane and look:

```
art_discovery(action='list_runs')                  # take a run_id
art_review(action='list_works', run_id='<that>')   # expect: pictures, inline
art_review(action='list_images', work_id='<one>')  # expect: the alternates
```

What to check with your eyes, beyond "images appeared":

- **The pictures render inline**, not as attachments or placeholders.
- **Each work's picture is its own.** Rows carry `image_block_index`; a client
  that reorders or drops a block would pair the wrong scan with the wrong
  painting, and nothing below the wire can detect that.
- **A work with no local copy still lists**, with `preview_note` saying why —
  rather than vanishing or rendering blank.
- **The size beside each picture is legible and useful.** `renders_at_inches` is
  the number a thumbnail cannot convey, and it is what stops a postage stamp
  reaching the wall; if it reads as noise in a real client, say so — the
  presentation is worth changing.

Verified so far *without* a real client: the plane was booted from its own entry
point against a scratch tree on 2026-08-03 and a real MCP client session returned
1 text + 2 image blocks, each index resolving to a decodable 400x400-box JPEG,
with the below-floor work pictured and marked `is_on_offer: false`.

### The loader unit starts clean with its declared `EnvironmentFile=` — added 2026-08-02

> **DISCHARGED 2026-08-11, by the cutover rather than by running this item.** The
> question this was kept for — does an un-prefixed `EnvironmentFile=` start clean
> on the real machine — is answered, on the units that matter. Both
> `display.service` and `curation.service` declare it un-prefixed against
> `/opt/samsung-frame-art-loader/.env` and both came up clean on the first
> `systemctl enable --now`, curation logging its resolved configuration and
> display its startup line. Neither refused to start, which was the risk.
>
> **The unit named below is not the unit that was tested.** As predicted, the file
> under test became a different one: this item describes the 2024 loader, which is
> retired and will never be installed again. What follows is left as the record of
> a question that was owed and is not any more — do not run it. The properties it
> was written to protect are now asserted mechanically for both live units in
> `tests/test_repo_hygiene.py`, which is the durable form of this check.

**Not visual — this needs the Pi, and it is quick.** The unit now declares
`EnvironmentFile=/home/tvpi/source/samsung-frame-art-loader/.env` un-prefixed and
sets `StartLimitIntervalSec=0` / `RestartSec=10`. Everything about that was
established by reading systemd's documentation; whether *this* unit on *this*
machine starts under it has not been observed, and the un-prefixed directive is
precisely the kind of change that turns a working unit into one that refuses to
start if the path is wrong by a character.

The wall is running now, so do this at a moment when a brief outage is fine:

```sh
sudo cp deploy/samsung-frame-art-loader.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart samsung-frame-art-loader
systemctl status samsung-frame-art-loader          # expect: active (running)
```

**Then prove the guard actually guards**, which is the half that cannot be
checked by reading:

```sh
sudo systemctl stop samsung-frame-art-loader
mv .env .env.parked && sudo systemctl start samsung-frame-art-loader
systemctl status samsung-frame-art-loader          # expect: refuses to start, names the .env path
mv .env.parked .env && sudo systemctl restart samsung-frame-art-loader
```

The second command is expected to fail — that is the pass condition. What to
record is **whether the error names the path**, since "failed to start" without it
would leave the operator no better off than before. Check acceptance box 3 on
issue #43 with the status output pasted in.

**If the path is wrong**, the fix is the `EnvironmentFile=` line, not a rollback:
the checkout's absolute paths are machine-specific and already flagged as such in
`deploy/README.md`.

### The samsungtvws move, against the live television — added 2026-08-01

**Status: the television half is answered; the Pi half is not.** The 2026-08-06
run reached the set and passed, so what the library does against real hardware is
no longer an open question. It ran from a **macOS client against a hand-built
virtualenv holding only the television-path pins** — because nothing in this repo
installs `requirements.txt` on a Mac: that file carries `omni_epd`, `pycairo` and
`PyGObject`, none of which build there, and the root project declares only
`python-dotenv`, so `uv run python tv_api_check.py` fails at `import samsungtvws`.
**So `pip install -r requirements.txt` on the Pi remains unverified**, and that is
the half of this entry still owing. The pins are proven against the television;
they are not proven to install on the machine that will run them.

**Not visual — this one needs the hardware, not your eyes.** The library pin and
`websockets` both moved, and every claim behind the move comes from reading
source. What a television does is a separate question, and this is the only thing
that answers it.

On the Pi, with the set awake:

```sh
pip install -r requirements.txt          # the new pins
python tv_api_check.py --image "$ART_ROOT/ready/<a 4K composite>.jpg"
```

To reproduce the client-only run anywhere else, build the television-path pins
into a throwaway environment rather than reaching for `requirements.txt`:

```sh
uv venv --python 3.12 /tmp/tvcheck && VIRTUAL_ENV=/tmp/tvcheck uv pip install \
  "aiohttp==3.14.3" "async_timeout==4.0.3" "websockets==16.1.1" \
  "requests==2.34.2" "python-dotenv==1.2.2" \
  "samsungtvws @ git+https://github.com/NickWaterton/samsung-tv-ws-api.git@fe95ef1d784cd32f49bf9a07ec479576574eea07"
/tmp/tvcheck/bin/python tv_api_check.py --image "$ART_ROOT/ready/<any real JPEG>.jpg"
```

> **`ready/` is empty on the rebuilt card and the 2024 composites are gone with
> the old one** (2026-08-04), so there is no 4K composite to point this at. Any
> real JPEG the set will accept proves the same thing — this checks what the
> *television* does with an upload, not what the renderer produced. Use a
> bench file, or run it after the first work is prepared.

It uploads one image, watches which callback the set emits, removes that image
and confirms the removal — touching nothing else on the wall — and exits non-zero
if any check fails. Paste its output onto issue #3; the last three acceptance
boxes there are exactly what it measures.

**Four numbers worth recording from the run**, because each is an input to the
display daemon rather than a pass/fail. **Run 2026-08-06 from a macOS client
against the set in art mode: 9 checks, 0 failed.** What it measured:

1. **How long construction blocks: 4.53s**, against the tool's own 15s ceiling.
   It makes a REST call and, on 2024-or-later panels, a token round trip, all
   inside `__init__` — and this set is a 2024 panel, so the token trip is on the
   path. **The daemon cannot construct a client on its event loop**; 4.5 seconds
   of blocking I/O in an async loop stalls every other thing that loop owes,
   including the poll interval the `next`/`show_now` responsiveness depends on.
   A thread or an executor is a design constraint here, not a tuning choice.
2. **Which callback events this set emits: the run could not say, and its output
   looked as though it had.** Three are registered: `slideshow_image_changed`
   and `auto_rotation_image_changed` are the same notion under two spellings, and
   the wrong one fails silently, so both go on; `image_selected` is the
   acknowledgement of the request the script itself made. The report read
   `fired: d2d_service_message`, which **is not one of the three** — it is the
   outer websocket message type the library passes to every art-channel callback,
   whichever sub-event selected it. So what the run establishes is only that **at
   least one of the three fired** within 5s of `select_image`; the check fails
   when none do, and this run had no failures. Which one was unrecoverable from
   the output. *(Second defect fixed in the same pass as the model one below: the
   recorder now captures the trigger it was registered under, so a run names the
   event. This entry originally read the output at face value and concluded that
   nothing fired — a claim its own "0 failed" line contradicted.)*

   **Nothing here disturbs the earlier instrumented finding** that only
   `image_selected` fires, at +2.15s, and that the two rotation spellings are
   slideshow-advance events a host-driven wall never provokes
   (`platform-and-dependency-findings.md`). The next run is what confirms it from
   the tool rather than from a probe.
3. **The reported model and API version: `QN50LS03DAFXZA` (`24_PONTUSM_FTV`),
   API `5.0.1.0`** — the new half of the verb split, so `slideshow_*`. The model
   came from `/api/v2/` by hand, **not from the tool, which reported "model: not
   reported" against a set that names itself perfectly well** — see the defect
   note below.
4. **Upload seconds against file size: 2.2 MB in 3.0s**, first byte to
   acknowledgement, streamed by path. The comparison against the old
   whole-file-in-memory route is the reason the pin moved.

**A defect this run exposed, which is why item 3 above needed a hand check.**
`check_identity` reads the model from `get_device_info()`, but on the async art
client that is the *art channel's* payload — `current_rotation_status`,
`support_brightness_sensor`, `resolution_type` and so on, with **no model and no
`device` key at all**. The `{"device": {"modelName": …}}` shape the code destructures
is what the *REST* endpoint returns. So `model` is always `None`, and the cost is
not the cosmetic note: `panel_check.disagreement(None, …)` returns `None`, so the
**panel size check silently takes its "neither side stated one" branch and passes
without measuring anything**. That check exists because a live deployment ran 42"
against this 50" panel and mis-sized every judgement about whether a work belonged
on the wall — and `.env.example` still ships `TV_PANEL_DIAGONAL_INCHES=42`, so
the misconfiguration it guards against is the one a fresh clone starts in.
Confirmed by hand that the public `SamsungTVAsyncRest.rest_device_info()` returns
the expected shape, and that `disagreement("QN50LS03DAFXZA", 42.0)` produces the
full warning — the guard works; nothing was reaching it.

**Fixed, in two halves, and the second is the one that generalises.** The model
now comes from `samsungtvws.rest.SamsungTVRest.rest_device_info()` — the public
synchronous client for the `/api/v2/` route, which is where that shape lives, at
the configured `TV_PORT` rather than a literal (the library reads the scheme off
the port: `https` on 8002, `http` on 8001, and both serve the route) — and the
note reports `modelName` and the `24_`-prefixed model year
together, since the year is what the token handshake turns on. The second half is
that **`panel_check` now answers two questions instead of one**: `not_compared()`
says whether a comparison was possible, and `disagreement()` says how it came
out. A caller that reads only the second reports a pass for "they agree" and for
"one side said nothing" alike, which is the conflation that let a check comparing
`None` look satisfied. Driven against both captured payloads: fed the art
channel's, the panel line now reads `[note] panel size: not compared — no model
name was read from this television`; fed the REST payload against
`TV_PANEL_DIAGONAL_INCHES=42`, it fails with the full 104.9-against-88.1 warning.
(It says "was read" rather than "the television reported none" on purpose: on the
path where the REST endpoint does not answer, nothing ever asked the set, and the
failing `model` check above the line carries that reason.)

**What that leaves for the next run on the set**, and it is small: the REST read
itself has only been exercised against a captured payload, so the live pass
should confirm the `model` note names the set and the `panel size` line is an
`ok` or a `FAIL` — **never a `not compared`**. A `not compared` from a television
that answered everything else is the same defect wearing its new name, and now it
says so on the line rather than needing a hand check.

**The art channel's payload is worth having anyway**, because two fields bear on
the daemon: `support_brightness_sensor: "TRUE"` (the set has its own sensor,
which the ported sun-following curve is in addition to, not instead of) and
`current_rotation_status: 1`.

> **Picked up 2026-08-07 as issue #107**, after the operator found the wall
> reading bright on an overcast afternoon while the sun curve had it at 8–9 —
> which is exactly the case a solar angle cannot see. `get_artmode_settings`
> reports the sensor is switched **off** (`brightness_sensor_setting: "off"`),
> and the library exposes `set_brightness_sensor_setting`.
>
> **The flag above says a sensor exists; it is not a reading.** Nothing here has
> ever fetched an ambient *value*, which is why the first step is establishing
> whether one can be read at all. If the sensor only drives the set's own
> auto-brightness, the honest answer is to stop writing `set_brightness`
> altogether rather than to blend the two — a different design, not a variant.

**If it fails, the rollback is `deploy/pi-freeze-2024.txt`** and nothing else has
changed on the Pi — the new pins only take effect on an install.

### The first browser surface — added 2026-08-01

**What to look at.** The four sections and a work detail view, over the real
corpus. What matters is the judgement a test cannot make: does the chrome recede
behind the artwork, or compete with it? That is the whole visual constraint, and
it is subjective by nature.

**How to bring it up over the real works, without touching the deployed tree:**

> **Corrected 2026-08-04, and the correction itself expired 2026-08-06.**
>
> The recipe below replaced one that set `ART_ROOT` in the environment, on the
> grounds that **`ART_ROOT` could not be overridden that way**: `config.py`
> called `load_dotenv(override=True)`, and `find_dotenv()` walks up from *that
> module's own file*, so the checkout's `.env` won over the environment no matter
> what was exported. The old recipe seeded the real `ART_ROOT` while printing
> that it had — which reads as success, the first line being the only tell.
> Verified by running it.
>
> **That `override=True` has since been retired**, precisely because discarding
> an exported value in silence is the failure shape this product exists to
> correct. An exported `ART_ROOT` now wins, so the recipe the 2026-08-04 note
> declared impossible would work today. The recipe below is kept anyway: it does
> not depend on which way the precedence runs, which is the property worth having
> in a document somebody follows months later.

```sh
# The masters, read-only behind a symlink, inside the ART_ROOT `.env` names.
# One `rm ~/samsung-art/raw` undoes it; nothing is copied.
ln -sfn ~/art/raw "$(grep '^ART_ROOT=' .env | cut -d= -f2-)/raw"
cd curation
uv run python -m curation.seed ../all.json   # re-runnable; fills in what was absent
uv run python -m curation
# then open the CURATION_PORT from .env — http://127.0.0.1:8770/ as shipped
```

To serve a *second* copy on another port without disturbing the first, change
`CURATION_PORT` in `.env` — for the same reason, it is not settable per command.

`~/art` on the dev Mac holds `raw/` and no `ready/`, so every work will show its
master image and the wall view will report every work as `no_rendition`. **That is
correct, not a fault** — and as of 2026-08-04 it is also permanent for these
works: the Pi was rebuilt and the 2024 renditions were on the old card, so
`ready/` exists nowhere. Re-rendering the corpus is real work, not a missing
symlink. To see a mixed
manifest, give a few works a rendition first; the wall view is the section most
worth seeing with both states in it.

**Specific things worth an opinion, because each was a judgement call:**

1. **Card density and the fixed 4:3 image box.** Works are letterboxed inside it
   rather than cropped to fill, so a tall work leaves large empty margins. The
   alternative — cropping — is the one thing an art tool must not do, but the
   margins are a real cost and a different aspect box would trade differently.
2. **The serif for work titles** against a sans for chrome. Intended as a museum
   label; it may read as fussy at grid size.
3. **The badge row on each card** — fit verdict and image source, plus a third
   on an archived work. Two or three badges is a lot of furniture under a
   picture. They are there because a thumbnail cannot convey resolution, so
   "would show at 15.2 inches" is the number a curator actually judges by, and
   because an archived work that looked identical to a live one would be the kind
   of silence this product exists to refuse.
4. **`no_rendition` and the other reasons appear as the raw domain words**, with
   the sentence beside them. Deliberate: the tool surface returns the same words,
   so a curator and an agent share one vocabulary. It reads slightly machine-y.
5. **Dark and light.** Both are authored; the browser's own setting picks. There
   is no in-app toggle — say if you want one, since an image-review tool arguably
   deserves the ability to pin the surround while judging colour.

**One decision explicitly awaiting a veto** (`nonfunctional-requirements.md` §
The mat is geometric): the mat's bottom margin is now 1.15x the top. The
weighting had only ever been stated as a direction, and a box height cannot be
computed from a direction. 1.15 is the factor that reproduces that artifact's own
42-inch worked example, so it is inference rather than invention — but it is a
subtle weighting, and a more pronounced one is taste, not correctness. It is
`MAT_BOTTOM_WEIGHT` in `.env`, so overruling it is a one-line change.
