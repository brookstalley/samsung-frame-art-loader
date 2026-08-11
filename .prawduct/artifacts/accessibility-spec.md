---
artifact: accessibility-spec
version: 1
depends_on:
  - artifact: design-direction
  - artifact: information-architecture
  - artifact: nonfunctional-requirements
last_validated: null
---

# Accessibility Specification

Authored 2026-08-11, the third and last of the human-interface artifacts. Like the
two before it, it is partly a record of what already holds and partly a statement
of what is owed; every requirement here is either **practised** (with the mechanism
named), **owed** (with what would close it), or **open** (with what could settle
it, and by whom).

## This product has three surfaces and the important one is not the browser

`design_decisions.accessibility_approach` settles the scoping question before any
requirement is written, and it is the opposite of the obvious answer:

| Surface | Who reads it | What accessibility means here |
|---|---|---|
| **The e-paper label** | Household members and guests, at standing distance, in whatever light the room has | **Legibility.** There is no interface to navigate — type size, contrast on a non-emissive panel, and line length *are* the whole story |
| **The curation browser** | One advanced operator, on a LAN | WCAG 2.1 AA — keyboard, focus, labels, contrast |
| **The television** | The same household members and guests | Nothing, deliberately. It is artwork on a wall |

> **The label outranks the browser, and this artifact is ordered to say so.** A
> specification that opened with WCAG and treated the panel as a footnote would be
> a truthful document about the lesser half. The browser has one user, who built
> the product and can change it; the label has every visitor to the house and no
> affordance to adapt it. `information-architecture.md` § Status originally
> described this artifact as "mostly a codification job — the token test, announced
> errors, and glyph+word+colour are already practised", which is an accurate
> description of the browser work and would have produced the wrong artifact.

---

## The e-paper label

The label is a physical reading surface with no controls, no zoom and no
alternative rendering. Whatever it draws is what a person gets, so every
requirement below is about the drawn result rather than about a mechanism.

### The panel must be driven at 16 grey levels, and the mode must be read back

**Practised** — `display/src/display/panel/epaper.py` sets `mode = "gray16"` and
asserts what the driver took.

This is an accessibility requirement rather than a driver detail, and the reason it
is stated here is that it is invisible to every reasonable check. Measured on the
wall's own panel 2026-08-04: `omni-epd`'s `waveshare_epd.it8951` driver comes up in
1-bit `bw`, and **`max_colors` reports 16 in both modes** — so the sanity check
anyone would write cannot tell them apart. Reading `mode` is the only honest test.

The 2024 implementation is the proof that this catches something real: it passed
`greyscale_bits=1` into a label renderer that never used it, so the wall rendered
1-bit type into a panel sitting in its 1-bit default, for years, with nothing
anywhere reporting it. **1-bit type on a non-emissive panel at standing distance is
the failure this whole section exists to prevent**, and it looks exactly like
success from every direction except standing in front of it.

### Type never shrinks to fit; content is dropped instead

**Practised** — `display/src/display/panel/layout.py`.

When the lines will not fit, the least identifying ones come off the bottom and the
survivors keep their size. Type that shrinks to fit has silently converted an
accessibility surface into a decorative one, and the failure is invisible to
everyone except the person who cannot read it.

Three properties of the rule, all of them load-bearing:

- **The ordering is the priority.** Lines arrive in wall-label order — title,
  artist, nationality, dates, date, medium, dimensions — which is also
  least-droppable first, so dropping from the end needs no second ranking to go
  stale against the first.
- **The first line is never dropped**, even when the title alone overflows. A
  surface too small for one title is a misconfigured device; returning an empty
  label would present that as a work with no name.
- **What was dropped is reported, not discarded.** The journal can then say the
  surface is too small for the corpus, rather than leaving somebody to notice
  missing dimensions by eye.

### Type sizes and the margin are not settled, and only the panel can settle them

**Open — and it is this artifact's one unmet requirement.**

`layout.py` carries `TITLE_SIZE_PX = 40`, `ARTIST_SIZE_PX = 32`,
`BODY_SIZE_PX = 26`, and `display/src/display/config.py` carries
`DEFAULT_EPD_MARGIN_PX = 40`. **All four are provisional placeholders and must not
be quoted as measurements.** The operator's 2026-08-04 look at the real panel
killed the 2024 `"Sans 18"` and narrowed the live range to roughly the mid-20s
through the low-40s — but it was rendered with PIL/DejaVu, and this product
typesets with Pango. Different rasterizer, different face, different metrics: a
size that looked right there does not transfer.

The margin belongs to the same judgement rather than to a separate one, because a
border trades directly against how many lines survive the drop rule.

**What closes it:** a second look at the panel, rendering through the product's own
Pango path. This is the same bench visit Chunk 13A's Done-when step 0b is waiting
on. Whoever settles the numbers replaces the provisional notes as well as the
values — a settled number under a note calling it provisional is worse than either.

### Line length has no bound, and needs one

**Owed.** `design_decisions.accessibility_approach` names three things that carry
legibility — type size at reading distance, contrast on a non-emissive panel, and
**line length** — and the first two have mechanisms while the third has none.
Layout wraps to the full text width, so on a 1448px panel a body line at 26px runs
far past the measure at which continuous text stays comfortable to read.

No number is stated here, deliberately: a characters-per-line bound depends on the
face and the size, and both are open above. **It is settled by the same panel visit
and in the same act**, and it is recorded now so that visit closes three things
rather than two.

### Nothing may reason about a panel's geometry anywhere but on that panel

**Practised, and it is a ratified norm** — *"A display device renders its own
label, and the label travels as metadata"* (`architecture.md` § Direction, ratified
2026-08-07, enforcement row in `project-preferences.md`).

Its accessibility content is easy to miss: several devices may carry panels of
different sizes, and the 2024 plane's baked-in 648×480 is the anti-pattern being
retired. Geometry arrives as a parameter; `config.py` defaults to the reference
1448×1072 and every value is overridable. **A device with no label surface at all
is a configuration, not a fault** — which matters here because a household adding a
display without a panel must not read as a broken one.

### The panel has no brightness control, and that is why the rest of this matters

The label surface is non-emissive: there is no backlight to raise and no ambient
adaptation available to it. `display/src/display/brightness.py` follows the sun,
but it maps onto **the television's** scale — the panel is not in that loop. So the
panel's legibility in a dim room is entirely a function of the 16 levels, the type
size and the measure. There is no runtime lever that compensates for getting them
wrong.

---

## The curation browser

**Target: WCAG 2.1 AA**, a recorded decision
(`design_decisions.accessibility_approach`), with one domain-specific caution that
outranks convention: this is an image-review tool whose whole job is judging
colour, so chrome must never sit at a contrast that competes with the artwork.

### Contrast is computed, not claimed

**Practised, and mechanically enforced** — `curation/tests/unit/test_design_tokens.py`.

The test reads the real token values out of the served stylesheet and computes the
ratios, in **both** colour schemes, against WCAG 2.1's own luminance definition. A
colour nudged to look nicer fails the suite instead of quietly failing a reader.

**Two floors, and the difference is not a loophole.** Text is held to 4.5:1 —
nothing on this surface is large enough to claim AA's 3:1 relief. Control
boundaries and state indicators are held to 3:1 per WCAG 1.4.11. The decorative
rule between a card and the page (`--border`) is unchecked on purpose; controls use
`--border-strong`, which is checked. Holding a decorative divider to a control's
floor would put a hard line around every picture on a surface whose whole
constraint is that chrome recedes behind the artwork.

Three further properties worth knowing, because each is a defect the test already
caught or would catch:

- **No colour may be written outside the token blocks** — hex, `rgb()` and `hsl()`
  alike. A literal in a component rule is a colour the contrast tests cannot see,
  which is exactly how an unreviewed colour reaches a page whose accessibility is
  "verified".
- **The test asserts its own scan scope.** Its first version stripped the token
  blocks with two non-greedy regexes, ate three quarters of the stylesheet, and
  reported clean against a planted `#ff0000`. It now proves it read most of the
  file and names specific selectors that must be inside what it scanned.
- **A dark scheme missing a token inherits the light one**, which is how a dark
  page grows a white card. Every token must be overridden.

> **Consequence, from `design-direction.md` § Direction:** a new colour token is
> not "added" until this test covers it, and it must land inside the asserted scan
> scope. The revised palettes are the live example — they exist only in
> `prototypes/curation-ia-prototype.html`, which the test does not read, so every
> revised colour is currently **hand-checked and ungoverned**.

### Colour is never the sole carrier of state

**Practised, and only half of it is mechanical.** This is the split to respect
rather than paper over.

The mechanism covers the part a machine can see. `test_design_tokens.py` derives
every state a badge can carry **from the enums rather than from a written-out
list**, and asserts that each has a CSS block of its own and that no two states of
one axis are pixel-identical — a block copy-pasted for a new verdict with only the
selector changed would otherwise make a rejection look like an acceptance in
greyscale. `test_client_vocabulary.py` asserts that every enum value the server can
send has a sentence in the client, so no raw token leaks onto a screen.

**What no test can see is whether the glyph actually distinguishes anything.** That
half is judgment and stays with Critic review, per this repo's own enforcement
index. This artifact must not be read as claiming a test covers it.

The requirement itself, from `design-direction.md`: **glyph + word + colour, never
fewer than all three.** The named hard case is the one the accessibility decision
calls out by name — accept and reject in a candidate grid need a non-colour
indicator, because that grid is where a mistake spends money and suppresses a work.

**A state indicator with no word is a bug at every viewport**, not at some. The IA
round caught exactly that decaying: a masthead status indicator that dropped its
label at phone width, leaving a bare amber dot. The rule is not "add a label where
convenient".

### Keyboard and focus

**Practised:**

- A skip link to `#view` is the first focusable element, and `#view` carries
  `tabindex="-1"` so it can receive the jump.
- `:focus-visible` draws a 2px outline at 2px offset, in a `--focus` token whose
  contrast against the surfaces it appears on is one of the pairs the token test
  computes. Focus visibility is therefore not a matter of care.
- Icon-only controls carry `aria-label` naming the work they act on — *"Move
  Composition VIII earlier"*, not *"Move earlier"*.

**The one focus rule that is about correctness rather than convention: a poll must
never move focus.** The built surface shipped a two-second poll that stole focus on
the single screen with a decision on it. This binds every live region the IA adds —
the run progress card, the masthead status indicator, the conversation thread.

There is a second, quieter half of the same rule: **a live region must not be
rewritten with content it already holds.** The review view repaints its re-search
offer only when a work's *membership* of the waiting set moved, not merely when a
verdict changed, because rewriting a live region re-announces it — a curator
working by screen reader would otherwise hear the whole offer read out again for a
verdict that did not concern it.

### Announcement and semantics

**Practised:** `lang="en"` on the document; a `<nav>` labelled *Sections*; failures
announced through a `role="alert"` banner rather than shown as a colour; the
re-search offer as a `role="status"` region, polite rather than assertive because
an offer appearing is news and not an emergency.

**One mechanism worth stating as a rule, because it is the usual way this is got
wrong:** a live region has to exist in the document *before* the content it
announces is put into it. An element created and filled in the same breath
announces nothing. The review view keeps its region on the page whether or not it
holds anything — measured at 0px with no margins when empty, so it costs no space.

**Images:** decorative thumbnails carry `alt=""`; where the image is the content it
carries the work and its artist. There is no third state — an image with a missing
alt attribute is a filename read aloud.

### What the IA adds that is not yet practised

**Owed.** These are requirements on the work that reshapes the surface, not
descriptions of it.

| Requirement | Why it is not automatic |
|---|---|
| Every new live region announces without moving focus, and is not rewritten unchanged | The client has exactly one `role="status"` region today and no `aria-live` anywhere. The IA adds at least three |
| Contact-sheet metadata is available on **focus**, not only on hover | The IA's default density above a few hundred works puts metadata on hover. Hover-only metadata does not exist for a keyboard |
| A zero-count facet option is **disabled and still perceivable**, with its count in the accessible name | Disabled controls are skipped by the tab sequence, so a count that lives only in adjacent text is a count a screen-reader user never hears. The IA's rule is disabled-not-hidden precisely so the vocabulary does not appear to shrink |
| The masthead compresses without overflowing, and no element loses its word | Five non-wrapping tabs already overflow a 375px viewport, and the prototype reproduced the same failure at tablet width the moment the status label grew |
| Skeletons occupy the final geometry | A grid that reflows as images arrive is a vestibular and cognitive cost as well as an aesthetic one, and the built client has already shipped that bug |
| Every screen and consequential state is addressable | Back and escape are then the browser's, natively, rather than reimplemented — which is the accessible behaviour by default |

### Touch targets — stated, and not yet in the stylesheet

**Owed, with the same status as the revised palettes.** `design-direction.md`
requires control heights of 2.75rem (44px) under `@media (pointer: coarse)`, with a
2.25rem default that clears WCAG 2.2 AA's 24px floor. **`app.css` contains no
`pointer: coarse` block and no control height**, verified 2026-08-11 — so the rule
is a proposal today and is recorded as one here rather than as a practice.

The keying is the part worth preserving when it lands: **on the pointer, not the
viewport.** A small window on a desktop still has a mouse, so viewport width is the
wrong signal.

### Reduced motion

**Practised.** `@media (prefers-reduced-motion: reduce)` sets every transition and
animation to none. It covers the skeleton pulse, which is the product's only
ambient animation — there is deliberately almost no motion here: opacity on
hover-revealed metadata, width on a progress bar, and nothing else. No screen
transitions and no entrance animation on a grid of paintings.

### Two platform conventions are deliberately refused

Both are recorded in `design-direction.md` and both are accessibility decisions as
much as design ones:

- **No swipe gestures for judging, on any viewport.** A phone review queue is the
  canonical place for them, but accepting acquires and spends while rejecting
  suppresses a work from every future run — neither is cleanly reversible, and a
  gesture has no discoverable label, no keyboard equivalent and no confirmation.
- **No pull-to-refresh.** The surfaces that change on their own already poll.

### Not applicable, so the absences read as decisions

No localisation requirements (`en` only, one operator). No onboarding flow — the
empty states carry the work one would do, and a first-run wizard for the person who
built the product is the condescension `product-brief.md` warns against. No
accounts, so no authentication accessibility. No native mobile app, so no Dynamic
Type, VoiceOver or TalkBack platform work beyond what a responsive web page gets
for free.

---

## The television

**No accessibility affordances, by deliberate design.** The set displays the
artwork and nothing else: no overlay, no caption, no status. Adding any of them
would put chrome on the one surface whose entire purpose is that there is none —
and the label exists precisely so the identifying information has a home that is
not the picture.

Stated here so the absence reads as a decision rather than as an oversight, which
is the same reason `information-architecture.md` § Boundaries lists it.

---

## Verification

| Requirement | How it is checked | Where |
|---|---|---|
| Contrast, both schemes, both floors | Test — computed from the served stylesheet | `curation/tests/unit/test_design_tokens.py` |
| No colour outside the token blocks | Test, with an asserted scan scope | same file |
| Every badge state has a distinct block | Test, derived from the enums | same file |
| Every server enum has a client sentence | Test, reads `app.js` | `curation/tests/unit/test_client_vocabulary.py` |
| The panel runs at 16 levels | Test — the mode is set, and a panel that quietly stays in one bit is refused | `display/tests/test_epaper.py` |
| Content drops rather than shrinking | Test, against an injected measurer so it runs without a font | `display/tests/test_label_layout.py` |
| Glyph actually distinguishes state | **Critic judgment.** No test can see this | `/prawduct:critic` |
| Focus lands where it should, and a poll does not steal it | **Browser suite**, `-m browser` — a real Chromium against a booted server | `curation/tests/browser/` |
| Type size, margin and measure at reading distance | **The operator, at the panel.** Nothing else can | Chunk 13A Done-when step 0b |

**The last row is the one to watch.** It is the only requirement in this artifact
that no machine can close, on the surface this artifact says matters most.
