---
artifact: design-direction
version: 1
depends_on:
  - artifact: product-brief
  - artifact: information-architecture
last_validated: null
---

# Design Direction

Authored 2026-08-10, after the visual system had already been built and tested.
This artifact is therefore mostly **a record of decisions that already hold**, plus
the tokens the interface work added. Where it merely describes what the stylesheet
does, the stylesheet wins; where it states a rule, the rule binds.

## Direction

<!-- NOT YET RATIFIED. Proposed 2026-08-10 with this artifact. Enforcement row in
     project-preferences.md, which records it as proposed. The owner approved the
     design this norm describes; they have not been asked to ratify it as binding,
     and this artifact will not claim a signature it did not get. Ratifying it is
     one sentence from the owner. -->

**The stylesheet is the source of truth for token values, and this artifact is the
source of truth for the rules about them.** `curation/src/curation/http/static/app.css`
holds the values; `curation/tests/unit/test_design_tokens.py` reads that file,
computes every text and control pair in both colour schemes, and **refuses any
colour written outside the token blocks**.

> **Why:** a design artifact that restated hex values would be a second copy of a
> thing a test already enforces, and the copy is what goes stale. Naming the
> mechanism instead means the durable prose cannot drift from the value.
>
> **The load-bearing consequence:** a new colour token is not "added" until the
> test covers it. The token test has already narrowed itself once — two non-greedy
> regexes ate three quarters of the stylesheet, every component rule went
> unscanned, and a planted `#ff0000` reported clean. It now asserts its own scan
> scope. Any token added below must land inside that scope, or it is an unguarded
> colour wearing a token's name.
>
> **Status:** steady-state.

## Visual Identity

**Museum, not gadget** (`product-brief.md` § Identity). Three constraints, already
recorded at the top of the stylesheet and restated here because they are the whole
direction:

1. **WCAG 2.1 AA**, enforced by the token test rather than by care.
2. **Chrome never competes with the artwork.** This is an image-review tool whose
   job is judging colour, so surfaces are near-neutral with a slight warm cast — a
   gallery wall, not a screen — saturation stays low, and nothing but the images
   carries a strong hue.
3. **Colour is never the sole carrier of state.** Every state indicator pairs a
   glyph and a word with its colour, so it survives greyscale, colour blindness,
   and a curator who has turned the lights down.

The third is the one that decays quietest under new work, and the IA round already
caught it decaying: a masthead status indicator that dropped its label at phone
width, leaving a bare amber dot. The rule is not "add a label where convenient" —
it is that a state indicator with no word is a bug at every viewport.

## Colour

> **BOTH REVISED PALETTES ARE PROPOSALS, AND NEITHER IS IN `app.css` YET
> (2026-08-10).** The two sections below are written in the completed tense
> because they describe finished design decisions — but the values live only in
> `prototypes/curation-ia-prototype.html`. At the time of writing `app.css` still
> holds `--surface-1: #ffffff`, the light `--accent: #2f5068`, the dark `--accent:
> #9dc0da`, and no `--warn` at all.
>
> **So `var(--accent)` in the product today is blue, not bistre or gilt.** A
> builder styling the next screen from these sections would reach for a token that
> does not exist or get the colour the section says was replaced. They land, and
> this notice comes out, in the chunk that touches the stylesheet — at which point
> `test_design_tokens.py` covers them and this artifact's own Direction ("the
> stylesheet is the source of truth for token values") holds again rather than
> being contradicted by the paragraphs under it.
>
> Every value below was checked at AA by hand against the same formula the token
> test uses. That is weaker than the test and is not a substitute for it.

### The light scheme is a gallery wall, not a page *(revised 2026-08-10, proposed)*

The first light palette read as software. The operator's verdict — "very tech,
needs to be more museum; dark theme is good" — is recorded here with the diagnosis,
because "make it warmer" is not a rule anyone can apply twice.

**Two things were doing it, and neither was the warm cast the stylesheet already
had:**

- **Pure white cards on an off-white ground.** `--surface-1: #ffffff` against
  `--surface-0: #faf9f7` is the exact figure of every SaaS dashboard: content
  floating on a page. A gallery has no white; it has a wall, and things hang on it.
  **There is now no pure white in the light scheme at all** — the ground is warm
  plaster and the raised surface is paper.
- **A blue accent.** `#2f5068` was chosen desaturated so it would sit behind a
  painting, and it does — but blue is what software uses for "interactive", and a
  museum's own accent is ink. The accent is now a **warm bistre**, the colour of a
  printed label. Primary buttons read as letterpress rather than as calls to
  action.

### The dark scheme is a wood-panelled study *(revised 2026-08-10, second pass, proposed)*

The dark scheme survived the first revision untouched and then failed the same
test one round later: *"still a bit too trendy tech, suspiciously like Claude's
colours."* The reference the operator gave is the useful part — **a wood-panelled
study with paintings and warm lighting** — and the diagnosis mirrors the light
scheme's almost exactly.

**Near-neutral charcoal with a single pale-blue accent is the default shape of
every dark UI.** `--surface-0: #161513` was warm only barely, and `--accent:
#9dc0da` was the same move the light scheme's `#2f5068` was making: blue standing
for "interactive". Two changes, both small:

- **The neutrals carry walnut rather than charcoal.** More red in the ground, and
  the text warms from `#f5f3ef` toward `#f4ece0` — lamplight on paper rather than
  white on grey.
- **The accent is gilt.** `#ccad66` — a brass fitting, a frame, a lamp — not a
  hyperlink. It is the dark-scheme sibling of light's bistre ink: in a lit room
  the label is dark on paper, in a dark room the fitting is bright on wood.

**`--warn` moved with it**, pushed orange to `#e0964a`. Gilt and amber are
neighbours by nature and remain close in lightness; what actually keeps them apart
is the standing rule that every state indicator pairs a glyph and a word with its
colour. Recorded rather than solved, because it is the kind of thing a later
palette edit will re-collide.

> **Both schemes were revised on the same diagnosis, one round apart, which is
> itself the finding.** In both, the identity was being carried by warm neutrals
> and undone by a blue accent — and in both, the accent was the part that had been
> reasoned about most carefully and defended in a comment. The lesson worth
> keeping: *a colour chosen for a good reason can still be the wrong colour,* and
> the tell was that it looked like other software rather than like the subject.

Two consequences worth stating, because they are easy to miss:

- **The accent can no longer distinguish a link from body text**, being near-black.
  Links carry an underline. This is the older convention and the better one.
- **Ground-to-card contrast dropped on purpose.** Tiles should read as work hung on
  a wall, not as cards stacked on a page, so the border does more and the
  background difference does less.

### Tokens the IA work added

Values live in the stylesheet. What this artifact adds is **the tokens the IA work
requires and the existing set does not have**, with the reasoning:

| Token | Role | Why it is not an existing token |
|---|---|---|
| `--good`, `--warn`, `--crit` | Semantic status | The accent means "this is a control". Status must be distinguishable from interactivity, so it cannot be the accent — and the existing per-state badge colours are specific to fit verdicts and image states, not to appliance health |
| `--good-quiet`, `--warn-quiet`, `--crit-quiet` | Status backgrounds | A status *ground* needs to sit under text at AA, which the foreground values cannot do |
| `--scrim`, `--scrim-text` | Type over artwork | The Walls screen and the contact sheet lay text on an unknown image. No surface token can serve this: the ground is a painting, so contrast has to come from the scrim rather than from the palette |

**Saturation on the status trio stays low deliberately.** A healthy appliance must
never shout on a page full of paintings, and the semantic hues are the only place
besides the accent where a hue appears at all.

**These three pairs must clear AA against the surfaces they sit on, in both
schemes, and are not exempt from the token test.** They are stated here as
requirements rather than as measurements, because the measurement belongs to the
test.

## Typography

Unchanged, and it is a considered pairing rather than a default:

- `--font-label` — `ui-serif, Georgia` — for headings, work titles and anything in
  the voice of a museum label.
- `--font-ui` — `system-ui` — for chrome, controls and data.

**No webfont, and this is a decision.** The curation plane is a loopback service on
a Pi with no build step; a font file is a payload to serve, a licence to track, and
a silent fallback when it fails. The serif/sans split does the identity work
without one, and a system serif on the operator's machines is a real serif.

Scale is 1.25 from a 16px base, `--text-xs` through `--text-2xl`, plus `--text-3xl`
added for the Walls screen's single large heading.

## Spacing & Layout

4px base, `--space-1` … `--space-8`. Content max-width 96rem. Radii stay crisp —
`--radius-sm: 2px`, `--radius-md: 4px` — because *a museum label is not a pill*.

**Breakpoints**, as the IA's three shapes:

| Bound | What changes |
|---|---|
| ≥ 60rem | Full layout. Theme rail vertical and sticky |
| 40–60rem | Rail becomes a horizontal scroller of pill filters; work detail stacks |
| < 40rem | Destinations move to a bottom bar; masthead keeps search and status only; grid at two columns |

**Every element in the masthead after the destinations must be allowed to
compress** (`flex: 0 1 auto; min-width: 0`), and long labels ellipsize. This is
stated as a rule because its absence is a defect the built surface already has —
five non-wrapping tabs overflow a 375px viewport — and the prototype reproduced the
same failure at *tablet* width the moment the status label grew. A masthead whose
items cannot shrink will overflow again the next time a word gets longer.

**Touch targets are keyed on the pointer, not the viewport.** `@media (pointer:
coarse)` raises control heights to 2.75rem (44px). The 2.25rem default clears WCAG
2.2 AA's 24px floor, but 44px is what every touch platform assumes, and a small
window on a desktop still has a mouse — so viewport width is the wrong signal.

## Component Patterns

- **Buttons** — `.btn` default, `.primary` for the one committing action on a
  screen, `.quiet` for dismissals, `.danger` for removal. At most one primary per
  screen region: if two things are primary, neither is.
- **Badges** — glyph + word + colour, never fewer than all three.
- **Cards** — paper, not UI: 1px border, `--shadow-1`, 4px radius. The elevation is
  barely there on purpose.
- **Tiles** — two densities (contact sheet, catalogue) per `information-architecture.md`
  § Information Hierarchy. **Uniform row height in both**, which is a layout
  decision made for a behavioural reason: a grid of art that reflows as images
  arrive is the opposite of the identity, and the built client has already shipped
  that bug.
- **Skeletons** occupy the final geometry rather than approximating it.

## Motion & Transitions

**Almost none, and that is the direction rather than an omission.** Opacity on
hover-revealed metadata (120ms), width on a progress bar, nothing else. No screen
transitions, no scroll-triggered reveals, no entrance animation on a grid of
paintings.

`prefers-reduced-motion: reduce` collapses every duration to ~0. Note that this
covers the skeleton pulse, which is the only ambient animation in the product.

**The one motion rule that is about correctness rather than taste: a poll must
never move focus.** The built surface shipped a two-second poll that stole focus on
the single screen with a decision on it. Every live region added by the IA work —
the run progress card, the status indicator, the conversation thread — updates
without touching focus.

## Platform Conventions

Web conventions, responsive, no platform-native affordances. Two deliberate
departures:

- **No swipe gestures for judging**, though a phone review queue is the canonical
  place for them. Accepting acquires and spends; rejecting suppresses a work from
  every future run. Neither is cleanly reversible, so both stay explicit labelled
  controls on every viewport (`information-architecture.md` flow 3).
- **No pull-to-refresh.** The surfaces that change on their own already poll and
  repaint from the response.

## Open questions

- **The dark-scheme pattern differs between the prototype and the product.** The
  prototype uses the three-state form (bare `:root`, a guarded
  `prefers-color-scheme` block, and an explicit `[data-theme]` stamp) because it
  offers a manual toggle. `app.css` uses the simple two-state form, which is
  correct while the product has no toggle. **If the product ever gains one, it must
  move to the three-state form** — a token defined only inside a media query never
  applies in the un-stamped state, and the page renders one theme's text on the
  other theme's ground.
- **Whether the semantic trio should replace any existing badge colours.** The fit
  and image-state badges predate it and have their own values; leaving both is
  defensible today and becomes two vocabularies for one idea if it persists.
