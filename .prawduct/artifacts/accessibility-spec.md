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

## Direction

The two norms this artifact carries, stated where the convention says a norm
lives. Everything below is the requirement detail they bind; **these two
sentences are the part that leads the code**, and a departure from either is a
decision to record rather than something to sync the prose to.

1. **The e-paper label is legible at standing distance.** The panel is driven at
   16 grey levels with the mode read back rather than assumed, and **type never
   shrinks below the floor — content is dropped instead, except for the three
   facts that identify the work, which shrink rather than vanish.** *(RATIFIED
   2026-08-11 by the operator, and amended by the same ruling: the flat clause
   became two tiers. § Type never shrinks to fit carries which content is in
   which tier and what follows from it — this sentence is the rule, that section
   is its detail. `open_questions` closed on the same date; the clause could not
   be ratified before the floor it refers to existed, and by then it existed.)*
2. **WCAG 2.1 AA on the curation browser, and colour is never the sole carrier of
   state.** Ratified; the decision it implements is
   `design_decisions.accessibility_approach`.

> **This section was added 2026-08-11 by Critic R-2, and its absence was a real
> gap rather than a formatting one.** `project-preferences.md`'s norm index points
> every other row at "`X` § Direction"; both accessibility rows pointed into this
> artifact's body instead, because there was no Direction to point at. A
> `governed_by` or jurisdiction walk therefore could not reach either norm — it
> would find the artifact and no rule in it, which is indistinguishable from an
> artifact that binds nothing.

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

> **The requirement's origin is `nonfunctional-requirements.md` § Output Quality**,
> which states the same thing in the same terms and is where it was first written.
> This section is where it is *specified* — practised, owed or open, with the
> mechanism named — and the two agree today. **Whoever settles the type sizes at
> the panel has three files to sweep, not one:** that NFR paragraph,
> `design_decisions.accessibility_approach` in `project-state.yaml`, and this
> section. Named here because a requirement with three prose homes is one that goes
> stale in two of them.

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

### Type never shrinks to fit, except for the facts that identify the work

**Practised** — `display/src/display/panel/layout.py`. The optional tier's drop
rule was built first; **the mandatory tier landed 2026-08-13 with the fill
model**, and with it the journal event the tier is conditional on
(`label.shrunk`, a warning rather than an info line — a dropped medium is the
engine working, and type below the floor is a deployment that cannot show this
corpus legibly).

Which tier a fact belongs to is carried on the fact itself
(`display/src/display/panel/content.py`), so nothing downstream infers it from a
position. Guarded by `display/tests/test_label_layout.py` for what the rules are
and by `display/tests/test_label_properties.py` for the claim that they always
hold — nine independently optional fields is 512 content shapes, and both defects
this replaced were about *which* fields a record happened to have rather than
about any one line.

When the lines will not fit, the least identifying ones come off the bottom and the
survivors keep their size. Type that shrinks to fit has silently converted an
accessibility surface into a decorative one, and the failure is invisible to
everyone except the person who cannot read it.

**Ratified with an amendment 2026-08-11, and the amendment is a second tier.**
The flat rule collided with itself: this section said the first line is never
dropped even when the title alone overflows, and § The label's content model said
nothing is ever set below the floor. A long title at the floor satisfies neither,
and nothing said which rule yielded. The operator's ruling splits the content
instead of picking a winner:

| Tier | What is in it | What happens when it will not fit |
|---|---|---|
| **Mandatory** | The artist's family name, the artist's given name, and the work's title when it has one | **Shrinks, as far as needed, below the floor if that is what it takes.** Never dropped, never wrapped where a size reduction can be avoided |
| **Optional** | Nationality, life dates, the work's date, medium, dimensions, commentary — **and nothing here is mandatory** | **Dropped, at full size.** Never set below the floor |

> **This table was the norm and not the code until 2026-08-13. All three gaps
> are closed; kept as the record of what a position-based engine could not
> express**, because that is the argument for the tier living on the fact.
>
> - **Nothing shrank — the mandatory tier had no guard at all.** The engine
>   dropped from the end at a fixed size, so a title that would not fit came off
>   rather than reducing. *Closed:* mandatory facts shrink by a uniform factor
>   until they fit, and the shrink is journalled.
> - **Two optional facts had become undroppable and were set at the *primary*
>   tier.** Nationality and life dates were joined into the identification line,
>   which was index 0 — the one line the engine never dropped and the one it
>   sized largest. *Closed by the fill model, and by the ladder rather than by
>   per-run sizes:* they are now ordinary candidates that drop when they will not
>   fit, and when the name takes its second line they follow it at the floor. A
>   line still carries one size — **the sizing half of this gap was closed by
>   arrangement, not by giving a run its own size**, which would have meant a
>   renderer change for a case the ladder already answers.
> - **The title had moved into the droppable region.** `lay_out` protected only
>   the first line; after the tombstone collapsed, that was the identification
>   block rather than the title. *Closed:* protection follows the tier, so the
>   title is safe wherever it is set.

Four properties of the rule, all of them load-bearing:

- **Priority is the tier first and the reading position second, and it is
  derived rather than carried.** This said "the ordering *is* the priority" and
  it stopped being true when the tombstone collapsed: facts arrive in *reading*
  order, and the title is set below the nationality while being admitted before
  it. Deriving priority from the tier and the position keeps the old property
  that mattered — there is still no second ranking free to go stale against the
  first — while letting the two orderings differ. (This said "in wall-label
  order" until 13B-3, which was already no longer the same thing: the artist
  leads and the identification block is one line, both departures from wall-label
  convention recorded in § The label's content model.)
- **The mandatory tier is what a label is for.** A label that cannot say who made
  the work and what it is called identifies nothing, and an unreadably small name
  is still a name somebody can walk closer to read. That is the trade the operator
  took, and it is the opposite of the trade the optional tier takes.
- **A shrink is reported exactly like a drop**, and this is the condition the
  amendment rests on. The reason the flat rule existed is that illegible type
  fails invisibly; admitting a shrink re-opens that hole unless the journal names
  it. A panel routinely setting names at 20 px is a misconfigured device, and
  nobody will ever discover that by eye at 7 feet.
- **What was dropped is reported, not discarded.** The journal can then say the
  surface is too small for the corpus, rather than leaving somebody to notice
  missing dimensions by eye.

### The type floor is derived from viewing distance, not chosen for a panel

**Practised** — `display/src/display/panel/legibility.py`, built 2026-08-11 as
13B-1. It replaces the settlement below rather than answering it. Settled
2026-08-11 with the operator, at the panel, once the two physical facts were
known: the reference panel is **6 inches diagonal at 1448×1072**, which is
**~300 PPI**, and it is read from **7 feet**.

Those two numbers make the legibility floor computable instead of judged, and the
arithmetic is exact:

```
px_per_arcmin = ppi × distance_inches × tan(1′)
size_px       = (cap_arcmin ÷ CAP_RATIO) × px_per_arcmin
```

**The two cap heights are named here exactly as the code names them**, and that
is a correction rather than a formality: this section used to call the calibrated
angle `min_cap_arcmin`, while the code has **`COMFORTABLE_CAP_ARCMIN` (12.4′)**
for the primary tier and a *separate* **`MINIMUM_CAP_ARCMIN` (8.8′)** for the
floor. The whole recalibration story is that the operator settles one angle and
every deployment inherits it — so the person doing that would read `min_cap`,
grep for it, find `MINIMUM_CAP_ARCMIN`, and move the absolute floor instead of the
tier they meant, with every test still green because each asserts a constant
against itself.

On the reference wall that is **7.34 px per arcminute** of visual angle. The
consequence measured on 2026-08-11 is why this section exists: the provisional
`BODY_SIZE_PX = 26` gives a cap height of **2.5 arcminutes at 7 feet**, against
the **5 arcminutes** that 20/20 vision needs to resolve a letter at all. The
provisional type was not merely small — it was below the threshold of legibility,
and every check the product had passed while it was.

**Three reasons this is derived rather than settled as pixels:**

- **A pixel floor is a claim about one panel at one distance.** The norm below
  already says nothing may reason about a panel's geometry anywhere but on that
  panel; a hardcoded floor quietly breaks that for the newest mechanism. A second
  device with a different panel at a different distance gets a correct floor with
  no second visit.
- **The fill rule needs a floor to mean something.** An engine that spends slack
  on more content, or on larger type, has to know what "too small" *is*. Without
  a floor expressed in the reader's terms there is nothing to adapt against.
- **It settles once and stays settled.** `COMFORTABLE_CAP_ARCMIN` is a fact about human
  vision, not about this wall, so it never needs re-judging. The operator
  calibrates it once by eye; every future deployment inherits it and supplies only
  its own distance.

**Calibrated at the panel 2026-08-11, and these are the settled numbers.** The
operator read a six-row ladder (160/130/110/92/76/64 px) from the viewing position
in normal room light and reported three things:

| Reading | px | Cap height | What it settles |
|---|---|---|---|
| Comfortable at a glance | 130 | **12.4′** | `COMFORTABLE_CAP_ARCMIN`, the primary tier |
| Made out with effort | 110 | 10.5′ | Not a target — the squint boundary, recorded so nobody aims at it |
| Acceptable if a reader steps closer | 92 | **8.8′** | The absolute floor; nothing is set below it, ever |

**So there are two floors, and that is the two-distance label made numeric.**
Museum practice sets the identification block for the approach and the extended
text for whoever walks up; the operator reached the same split independently, by
naming a size acceptable only when closer. The family name carries the primary
tier at 12.4′ and everything else steps down to the 8.8′ floor.

**The primary tier goes to the leading line when that line identifies the work,
and since 13B-3 that line is the artist.** The layout tier sets the first composed
line at 12.4′ and everything below it at the 8.8′ floor, and
`LabelText.candidates()` puts the identification block first — so the family name
carries the primary tier and everything else steps down.

**The condition is not decoration, and it was added 2026-08-13 because the
unconditional form shipped a defect.** A record with *no name at all* still opens
with an identification line — a bare nationality, or bare life dates — because
that block composes from whatever of the three it has. Sizing by position alone
therefore set a demonym at 12.4′ and demoted the work's own title to the floor
beneath it: an optional fact claiming to identify the work, which is this
section's own rule read backwards. So the tier is withheld when nothing on the
leading line is mandatory, and such a label is set at the floor throughout.

> **That leaves an open question, and it is the ordering rather than the
> sizing.** A nameless identification line leading the title is a 13B-3 decision
> the fill model did not revisit: `Water Jar` is set beneath `Japanese`, and
> museums print the reverse for an unattributed work — title first, culture and
> period after it. Withholding the tier stops the label claiming something false;
> it does not make the order right. The consequence a reader should expect is
> that a record like this shows small type and a lot of white. **Left to the
> panel visit rather than decided here**, because it changes what the label
> *says* and not how it fits, and because the corpus holds two of these against
> thirty-one records that are unaffected.

**What the primary tier lands on is the whole identification line, not the family
name alone, and that costs height** — `FAMILY, Given, Nationality, Dates` at
130 px wraps to three rows on this panel where the name alone would take one.
**13B-4 answered it with the ladder rather than with per-run sizes:** when that
line will not hold, the family name takes a line of its own at 12.4′ and
everything that shared it follows at the floor, which is where nationality and
dates were always meant to be set. A line still carries one size. Giving a *run*
its own size would have meant changing the renderer and the measurer for a case
arrangement already answers, and it would have set the name and its demonym at
two sizes on one line — which is a typographic decision nobody has taken.

**Net, the collapse still wins, and by more than it costs — modelled 2026-08-11,
not measured.** Running `lay_out` over two real seeded works with an *arithmetic*
stand-in for the measurer (0.5 em advance, 1.2 line height — **not Pango, so the
figures do not transfer and are here for direction only**), the reordered and
collapsed label drops **one** line where the old one dropped two and three:
Hokusai's *Great Wave* kept its date and medium instead of losing date, medium
and dimensions, and the O'Keeffe kept its medium. The wrapped identification
block eats roughly 90 px that the floor would not have — real, and smaller than
the ~260 px the collapse returns. **The panel is what settles this**, and it is
on the operator's list for the next look.

**The measured number is larger than the derived one**, which is the argument for
having measured it. A defensible 10′ taken from legibility literature would have
set the primary tier ~20% too small, and that error is invisible to everyone
except the person who cannot read it.

**The ladder was set in regular weight, so this floor is conservative.** Stroke
weight matters disproportionately on a reflective panel, where contrast rather
than resolution is the limit, and the family name is *to be* set bold. Bold
may reach the same comfort a size step down — worth measuring before spending
the panel's budget on size that weight could have bought.

`CAP_RATIO` is the face's cap height as a fraction of its em — ~0.70 for the text
faces this product sets. It is stated rather than measured because it varies
little across the faces in scope, and because a floor that is 3% conservative is
harmless in the direction that matters.

**Deployment values, not constants:** panel diagonal and viewing distance are
`.env` values like every other geometry fact — `EPD_PANEL_DIAGONAL_INCHES` and
`EPD_VIEWING_DISTANCE_INCHES`, inches for both so that neither has to be
remembered as feet. **They are the only two settings in the display plane with no
default**, and that asymmetry is the rule rather than an oversight: everything
else there falls back to the reference wall's number, which is right, because a
wrong poll interval or brightness is visible.

**The margin derives from the primary tier at half an em, and that ratio is a
decision this build had to make rather than one it inherited.** The amendment
above said the margin derives with the floor and did not say by what rule. Three
things settle it: a border cannot be picked independently of the floor, since it
trades directly against how many lines survive the drop rule; anchoring it to the
primary tier is what makes it scale to the next device; and the one observation
there is — the panel work ran a 60 px border to keep the largest rung of the type
ladder off the bezel — puts the ratio at 0.46 against a 130 px tier, so 0.5 is the
round number nearest it and lands at 65. **That reconciles the note below about
the measurements having been taken at 60 while the code shipped 40**: neither
number survives, and the one that replaces them is within a few pixels of the one
the operator actually looked at. It is the one number here an operator might
reasonably move, and moving it is one constant rather than another panel visit.

**`EPD_MARGIN_PX` survives as an override, not as a default.** It is for the
surface whose border is a physical fact rather than a typographic choice — the
device drawing its label into the mat area around an artwork does not get to
choose where the picture ends. `.env.example` leaves it commented, because a
`.env` is copied once and lived in, and a value written there would override the
derivation forever on every deployment that copied the file.

**A deployment that states neither loses its label, not its wall.** Guessing a
distance is the one thing that must not happen — a wrong distance gives silently
illegible type, which is precisely the failure this section exists to prevent, and
it looks like success from every direction. But refusing to *start* over it would
break two rules this package already holds: nothing in the label package may stop
the wall, and a device with no label surface is a supported configuration rather
than a fault. So an underived floor makes the label surface unavailable with a
named reason — the same path a missing panel driver takes, reported through
`surface_error` and visible on the health surface — and the television keeps
rotating.

### The label's content model, and the fill rule that adapts it

**Requested by the operator 2026-08-11 and written here before it was built,
because it is a set of decisions and not a layout tweak.**

**Practised.** 13B-3 built the *content model* — the ordering, the one-line
identification block, the stored name parts and the commentary field, all in
`display/src/display/panel/metadata.py` and carried there by the manifest.
**13B-2 built the typography on 2026-08-13**: a line is a tuple of styled runs
(`display/src/display/panel/styling.py`), the family name is set bold and
capitalised, titles are set in italic, and the renderer applies Pango attributes
over byte ranges. **13B-4 built the fill model and the name ladder the same
day** — `display/src/display/panel/content.py` for what a fact is and
`layout.py` for what survives.

**The styling cost room, the ladder gave it back, and both figures are from the
same instrument.** Measured on the reference wall 2026-08-13 with the preview's
Hokusai sample, through real Pango: the capitals took the identification line
from 262 px to **393 px** — two wrapped rows to three, because capitals are wider
than the letters they replace — and the medium dropped as a result. With the
ladder, the same record sets `KATSUSHIKA` on its own line at the 12.4′ tier and
`Hokusai, Japanese, 1760–1849` beneath it at the floor, which is **269 px** for
the pair; the medium is back on the panel and only the dimensions and the
commentary come off. That is the ladder doing exactly what it was owed for —
giving the family name its own line before it gives up its size — and it is why
the capitals were kept rather than withdrawn when they first cost a line.

**Two decisions this build had to make rather than inherit**, both consequences
of composing two rules this section states separately:

- **The inverted name and the one-line tombstone compose into one line, not
  two.** `FAMILY, Given` already spends a comma as its inversion marker, and
  running nationality and dates onto the same line spends two more — so
  `O'KEEFFE, Georgia, American, 1887–1986` is four comma-separated parts where a
  reader might expect the first comma to mean something different from the
  others. It is set that way anyway, because the alternative — the name on its
  own line — reclaims ~130 px instead of ~260 px, and the ~260 is the figure that
  makes optional content fit at all. **What disambiguates the first comma is
  weight, not punctuation**: the family name is set bold and capitalised, so the
  eye takes `O'KEEFFE` and then the rest, rather than four equal parts. **Built
  2026-08-13**, and it is still the first thing to look at when the operator next
  stands in front of the panel — a PNG can show that the right words are heavy,
  and only the panel can show whether the weight does the disambiguating work at
  7 feet in reflected light.
- **A single known name part stands alone rather than being padded out of
  `name`.** An artist with a family name and no given name sets just the family
  name; the whole string is used only when *neither* part is known. Combining
  them would produce "Rembrandt, Rembrandt Harmenszoon van Rijn", which is the
  same name twice.

**Built 2026-08-11 as 13B-3**, with the tests in
`display/tests/test_label_metadata.py` § TestWhoMadeIt.

**The artist outranks the work.** The 2024-era ordering led with the title, and on
a 6-inch panel that is what wastes it: measured on the panel, "Under the Well of
the Great Wave off Kanagawa" at a legible size consumed **502 px of 952 usable** in
four wrapped lines, and drove the year, the medium and the dimensions off the
bottom. Leading with the family name inverts that — seven characters where there
were forty-four — and the same content then fits at a *larger* body size. The
ordering the operator asked for and the ordering the panel can hold are the same
ordering, which is the reason to trust it.

**The artist's name is set as `FAMILY, Given`** — family name in bold capitals,
given name in normal weight and case, on one line: `ANDERS, Joseph`.

**One line is the preference, not the requirement.** Ruled 2026-08-11: the name
block gives up its line before it gives up its size, and gives up its size last of
all. Three steps, taken in order, each only when the one before it fails:

1. `FAMILY, Given` on **one line** at the target size.
2. **Two lines** — family, then given — each at the target size, taken when one
   line would have forced a reduction. Sizes are then independent, which is what
   lets a long family name cost only itself.
3. **Shrink**, below the floor if that is what it takes, when even a single name
   on its own line will not hold at that size. Reported, per the tier table above.

The ordering is the same instinct as the drop rule it sits under — spend layout
before you spend legibility — and it is why the ladder is stated as a preference
with fallbacks rather than as a fixed number of lines. A layout engine told "two
lines" would break `ANDERS, Joseph` for every short name on the wall; one told
"one line" would shrink Toulouse-Lautrec to fit a break it could have taken for
free.

**Built 2026-08-13. Two things it had to settle rather than inherit:**

- **"Each at the target size" is the primary tier and then the floor**, not the
  primary tier twice. That is what makes step 2 *cheaper* than step 1 rather than
  more expensive — a second line at 12.4′ costs more height than the wrapped row
  it saved, and the whole point of the step is that a long family name costs only
  itself. On the reference record it is the difference between 393 px and 269 px,
  and it is what put the medium back on the panel.
- **When step 3 is reached, both arrangements are shrunk and the larger answer
  wins.** Step 2 exists to *avoid* a reduction; once one is unavoidable it has
  failed at its job, and the question reverts to which arrangement stays most
  legible. Choosing the arrangement that was shorter at full size would answer a
  different question — the two come within a few percent of each other — and
  "gives up its size last of all" is the ordering this whole ladder is.

#### Amended 2026-08-13 at the panel: the biography leaves the name's line

**The first sitting against real ink refused the arrangement above**, and the two
things it refused are the two this amendment changes. The operator read the
reference record at the wall and reported the identification block as four rows:
`KATSUSHIKA,` / `Hokusai, Japanese` / `1760–1849`, then the title. Every fact on
it had been broken across a row boundary by the line breaker, and the first comma
— the inversion marker the bold was chosen to disambiguate — was left stranded at
the end of a row where no weight could do that job.

**Two separate faults produced it, and only one of them was a coding error.**

- **The step-2 trigger was stated as "when one line would have forced a
  reduction", and wrapping is not a reduction.** A joined name that wraps to
  three rows costs more height than the broken arrangement and reads worse, but
  it triggers neither a shrink nor an overflow, so nothing above asked for the
  ladder and the engine had no reason to take it. The trigger is now **wrapping
  or reduction, whichever comes first**: the name block gives up its line as soon
  as keeping it would break the name across rows.
- **Nationality and dates were riding the name's line and its tier.** Step 2 put
  the family name alone and let *everything that shared the line* follow at the
  floor — so the given name was demoted along with the biography, and at step 1
  the biography was promoted to the identification tier along with the name. The
  operator's reading of it was that the lifespan was "too large, equal with the
  name", which is exactly what a shared tier means.

**The block is now two blocks with two tiers, and the ladder governs only the
first.**

1. **The name** — `FAMILY, Given` — at the identification tier, on one line when
   it fits, broken to `FAMILY` / `Given` when it would wrap. **Both parts keep
   the identification tier when it breaks**: the given name is part of the name,
   and dropping it to the floor would set it as biography.
2. **The biography** — `Nationality, dates` — **always** at the floor, on its own
   line, never joined to the name and never promoted.

That is the museum tombstone, and it is what the operator reached independently
at the panel. It also makes the two decisions above compose rather than fight:
the first comma is now the only comma on its line, so the bold is disambiguating
a name rather than competing with a list.

**Measured across the whole corpus at the wall's own font**, at the identification
tier against a 1382 px measure: `O'KEEFFE, Georgia` 1290 and `KANDINSKY, Vasily`
1323 hold one line; `WRIGHT, Frank Lloyd` 1422 and `KATSUSHIKA, Hokusai` 1531 take
the break. Every biography line fits at the floor with room to spare —
`Japanese, 1760–1849` 993, `American, 1887–1986` 1015 — with one exception, which
is the next entry.

**Measure at the wall, not at a workstation.** The numbers in the paragraphs above
this amendment were taken through Pango on a development Mac, and the wall
resolves a different face: at the same declared size its rows are 108 px where the
Mac's are 93. That difference alone decided whether the ladder was taken, which is
how an arrangement that measured correctly everywhere it was checked reached the
panel wrong. Every figure in this amendment is from the panel's own machine.

- **This needs a real field, not a heuristic. Built 2026-08-11.** `Artist`
  carries `name` as one string; the surname heuristic in `discovery/artic.py` is
  documented there as unreliable, and it is wrong for "Titian (Tiziano
  Vecellio)", for "van Gogh", and for every name whose family part is not the
  last word. The catalogue gained `family_name` and `given_name`; the manifest
  carries them; the panel sets them. A work whose artist has neither falls back
  to `name`, unstyled — an unknown artist is a fact about the record, not a
  reason to guess at one.

  **Where the split for the seeded corpus comes from: a written table, not a
  rule** (`curation/src/curation/seed/names.py`). Thirty-one names, each with its
  parts spelled out, because this corpus alone defeats every heuristic in a
  different way — "Frank Lloyd Wright" defeats last-word, "Georgia O'Keeffe"
  defeats first-word, "Katsushika Hokusai" inverts the Western order it appears
  to follow, and "Moche" is a culture with no parts at all. A table can also say
  *nothing* about a name it does not carry, which is the behaviour a guess cannot
  have: seeding reports such an artist to the curator and leaves the row unsplit.

  **The backfill rides the ordinary seeding run rather than a command of its
  own.** Every artist row in the deployed catalogue predates these fields, and
  re-running the seed is already the documented way to fill in what an earlier
  run could not. It compares before writing, so a second run writes nothing, and
  it touches only the two fields no source ever supplied — an artist's
  nationality, dates and biography came from the holding institution and are not
  this table's to overwrite.

  **The nationality needs the same treatment, and for the same reason.
  Required 2026-08-13.** `artist_nationality` holds whatever the holding
  institution printed, which is prose and not a demonym: this corpus carries
  `North coast, Peru` and `Born Moscow (formerly Russian Empire, now Russia)`.
  The second one sets a biography line **2982 px** wide at the floor against a
  1382 px measure — over twice the panel — so it wraps to three rows whatever the
  ladder does, and no arrangement of the name can rescue it. The label needs a
  short form, and the catalogue is where a curator decides one.

  So `Artist` gains **`display_nationality`**, nullable, carried by the manifest
  and read by the panel, **falling back to `nationality` when unset** — a record
  nobody has shortened keeps exactly the label it has today, which is the same
  contract the name parts got. It is populated from the seed table beside the
  name parts, and backfilled by the same ordinary seeding run, because a curator
  editing thirty-one rows by hand is the thing the table exists to avoid.

  **It is a display form, not a correction.** `nationality` keeps what the museum
  said; `display_nationality` is what the wall has room for. Kandinsky is
  `Russian` on the panel and still `Born Moscow (formerly Russian Empire, now
  Russia)` in the catalogue, because the long form is the provenance and the
  short one is typography. Nothing derives one from the other — a rule that
  turned that birthplace clause into `Russian` would be inventing a fact about a
  person, which is precisely what the name table exists so that nothing does.
- **Bold is a Pango attribute over a byte range, never markup. Built
  2026-08-13.** `metadata.py` escapes nothing on purpose: a 2024 label passed
  description text to Pango markup and a title containing `<` produced mangled
  type or a parse failure. Styling a run by wrapping it in `<b>` would
  reintroduce that exact defect on the exact surface it was fixed for. Runs carry
  their own weight and case; the renderer applies attributes to ranges.

  **Bytes, and the corpus is what makes that load-bearing.** Pango's attribute
  indices are byte offsets into the UTF-8 the layout was set with, and a
  character count is invisible on `O'Keeffe` and wrong on everything else — an en
  dash spends three bytes, so every life date on this wall already contains one.
  What a character offset produces is a run of the wrong length set in the wrong
  weight, with nothing raising. Guarded by `display/tests/test_label_styling.py`
  (the offsets, including a capital that changes byte length) and by
  `display/tests/raster/test_pango.py` § TestTheStylingReachesTheType, which
  checks a style over non-ASCII text against a reference that uses no indices at
  all.

  **Case is the one styling fact the renderer is not asked for.** Pango can
  transform case only from 1.50, and pinning the label's most important run to a
  version floor for what `str.upper` does exactly would buy nothing — so the run
  declares `CAPITALS` and the transform is applied where the string is built.
  `Run.text` keeps the recorded spelling. What reads it today is the preview's
  report, and `layout.dropped` — which is how a line that came off reaches the
  `label.truncated` journal event as the catalogue spells it rather than in
  capitals. **A line that was *placed* is not journalled at all**, so the claim
  stops there deliberately: `Block.text` exists for the report and for tests, and
  naming the journal as its reader would be describing a caller that does not
  exist. A label is not the place a person's name loses its capitals for good.

**The fill rule: everything above the floor, in priority order, and slack is
spent on content.** A fixed hierarchy handles the corpus badly — an anonymous
untitled work leaves most of the panel empty while a long-titled attributed one
overflows. So the engine is given candidates with a priority and a role, and:

- **Nothing optional is set below the floor, ever.** The tier table in § Type
  never shrinks to fit outranks everything here: optional content drops at full
  size, mandatory content shrinks rather than vanishing. The floor is derived
  rather than provisional.
- **The mandatory tier is admitted before the fill rule runs**, not by it. Family
  name, given name and the title when there is one are not candidates competing
  for room; they are the room the rest competes for what is left of. This is what
  makes "nothing else is mandatory" affordable — with four of the six tombstone
  facts droppable, the slack below stops being a crisis and becomes a per-work
  answer. **The figure that slack was quoted at is gone** — see the note under
  § The label's content model: the ~66 px was measured before the family name was
  set in bold capitals, which cost 131 px on the reference record. What the fill
  model tunes against is a measurement it takes after the ladder decides how many
  lines the name gets, not a number written down here.
- **Optional content is admitted only if it fits at the floor.** Commentary is the
  first thing to go and the last thing admitted, because it is the only line that
  identifies nothing.

  **A fact that will not fit is passed over, not a stop signal — decided at
  build, 2026-08-13, and it is a departure worth reading.** Taken strictly,
  "commentary is the first thing to go" means the engine stops at the first
  refusal, which would make the drop set a clean suffix of the priority order.
  It is not built that way, because the facts differ in *size* as well as in
  rank and the corpus makes that concrete: Kandinsky's nationality is a 48-character
  birthplace clause, and an engine that stopped there would drop his dates, his
  date, his medium and his dimensions to a fact that merely came first. So each
  fact is tried and the ones that will not fit are passed over. The cost is that
  a label can show its dimensions with its medium missing; the journal names
  every fact that came off either way, which is what keeps that auditable rather
  than mysterious.
- **Slack is spent on content before it is spent on type.** A label set enormous
  with three of its six facts dropped is worse than one set comfortably with all
  six, and the panel measurement above is what makes that concrete rather than a
  matter of taste. Growth toward a preferred size happens only once no further
  candidate can be admitted.

  **Growth is a promotion between the two tiers, and only the identifying facts
  take it — decided at build, 2026-08-13.** There is nowhere else for a growing
  line to land: the calibration settled two readings and the rung between them is
  the squint boundary, recorded so that nothing aims at it. And an optional fact
  set at the identification tier would be claiming it identifies the work, which
  is the two-distance label read backwards — the identification block is for the
  approach and everything else is for whoever walks up.
- **What was dropped is still reported, and so is anything set below the floor.**
  An engine that adapts silently is one whose omissions nobody can audit. The
  shrink report is the stronger of the two: a missing dimension is visible to
  anybody who looks at the panel, and type that got quietly smaller is visible to
  nobody except the person who cannot read it.

> **Every panel measurement in this section was taken at a 60 px margin**, while
> the code then shipped 40 — a wider border was used to keep the largest type
> clear of the bezel, so the 952 px usable figure and the budgets built on it
> described a margin the deployment did not run. **Reconciled 2026-08-11 by
> 13B-1**, which retired both: the border now derives at half the primary tier,
> which is 65 px on this panel and leaves 942 px usable. The figures in this
> section are therefore within ~1% of what the deployment actually runs — close
> enough that the reasoning built on them stands, and stated so that the 952 is
> not later mistaken for a current measurement.

**Museum tombstone conventions, checked rather than assumed** — the operator asked
to be corrected on these 2026-08-11, and was on the first one:

- **Nationality is the adjectival demonym, not the country.** "Katsushika Hokusai,
  Japanese, 1760–1849" — the term modifies the *artist*, not the work's origin,
  and that is the practice at the Art Institute, the Met, MoMA and the National
  Gallery. Country names belong to a different slot on a label: place of birth or
  death, and credit lines.

  **"No data change follows" was wrong, and 13B-3 found out by running it.** That
  claim rested on the Art Institute's `artist_display` always supplying the
  adjectival form. Reading all 31 seeded artists back out of a freshly seeded
  catalogue, **two do not**: Moche stores `North coast, Peru` — a place, for a
  record that is a culture rather than a person — and Vasily Kandinsky stores
  `Born Moscow (formerly Russian Empire, now Russia)`, which is a birthplace
  clause with no demonym in it at all. Both reach the panel today as the middle
  of the identification line: `Moche, North coast, Peru`.

  **Left as stored, deliberately, and not silently.** Neither is *wrong* — they
  are what the holding institution published, and the label printing them is the
  label being honest about its record. Correcting them means either editing
  catalogue content by hand or teaching the seed parser to tell a demonym from a
  birthplace clause, and the second is a rule that would need its own ruling
  about what to store when it cannot tell. Both are curation-content work rather
  than a type-floor change, so this section records the exception instead of the
  build inventing an answer for it. **The number is 2 of 31, not a rounding
  error, and it is the kind of thing only a run finds** — the assertion above had
  been read past by every review it went through.
- **The tombstone is one line, not three. Collapsed 2026-08-11 by 13B-3.** Name,
  nationality and life dates are conventionally set as a single run —
  `Katsushika Hokusai, Japanese, 1760–1849`. This product emitted them as three
  lines, which spent three line-boxes and their leading on one fact. **On the
  reference panel that is worth ~260 px**, against the slack measured at the time
  (~66 px, before the capitals took 131 px of it back — § The label's content
  model carries the current figure), so
  it is the single change that decides whether optional content fits at all —
  which is why it was built *before* the fill model rather than as an input to
  it: tuning a fill rule against the un-collapsed numbers would have tuned it
  against figures that were about to move by four times the slack.

  **It is `LabelText.identification`, and it composes rather than concatenates**:
  an artist with no dates, or no nationality, or neither, yields a shorter line
  rather than a line with holes in it, and a work with none of the three yields
  no identification line at all and opens with its title.
- **Titles are set in italic**, including *Untitled*. Another styled run, so it
  landed with the bold-capitals work rather than behind it — **built 2026-08-13**.
- **`FAMILY, Given` is an index convention, not a wall-label one.** Wall labels use
  natural order; inverted order belongs to catalogues and artist indexes. The
  operator chose it deliberately for a rotating display, where the family name is
  the token a passer-by scans at 7 feet — **recorded as a departure taken
  knowingly**, not as a convention followed.

**Commentary does not fit at 7 feet on this panel, and that is a finding rather
than a tuning target.** With the identification block set at the floor there is
no slack at all against the ~130 px a further line needs — the ~66 px this
sentence quoted was measured before the family name was set in bold capitals,
which took 131 px of it and then some.

**Still true after 13B-4, and now measured with the commentary present rather
than reasoned about.** Running the preview over the reference record — Hokusai,
every field populated, commentary included — the panel holds the name across two
lines, the title, the date and the medium, and drops **the dimensions and the
commentary**. So the finding stands: commentary does not fit at 7 feet on this
panel for a record like this one. What the ladder bought back was the medium,
which the capitals had cost.

The fill rule is what makes it a per-work answer instead of a global one: the
works with short names and no title will have room, and the ones that do not will
drop it. **The paragraph this replaced reasoned to the same conclusion by
arithmetic against a 131 px figure**, and is not kept, because the measurement it
was standing in for now exists.

**The field exists and nothing writes to it yet, which is stated here rather than
discovered later.** 13B-3 added `commentary` to the work, carried it through the
manifest and made the panel read it — but works enter this catalogue only by
seeding and, later, by acquisition, and neither has a commentary to supply: the
2024 index carries the holding institution's `description`, which is paragraphs
long and is emphatically not this. So every work on the wall today has a null
commentary and the line simply does not appear. A writer for it belongs to the
curation surface, which has no plan yet; building one here would have been a
requirement nobody stated. **What the field buys before it has a writer** is that
the panel's last-and-first-dropped candidate exists for 13B-4 to model against,
rather than being added after the fill rule was tuned without it.

### The four provisional numbers, and what became of them

**Closed 2026-08-11 by 13B-1. Kept as a record of how they failed**, because the
way they failed is the reason the sections above are written the way they are.

`display/src/display/panel/layout.py` carried `TITLE_SIZE_PX = 40`,
`ARTIST_SIZE_PX = 32` and `BODY_SIZE_PX = 26`; `display/src/display/config.py`
carried `DEFAULT_EPD_MARGIN_PX = 40`. **None of the four exists any more**, and
none of them was ever a measurement. The operator's 2026-08-04 look at the real
panel killed the 2024 `"Sans 18"` and narrowed the live range to roughly the
mid-20s through the low-40s — but it was rendered with PIL/DejaVu while this
product typesets with Pango, so a size that looked right there did not transfer.

**Three sizes became two, and that is the part worth carrying forward.** The
calibration settled exactly two readings worth setting type at; the rung between
them is the one the operator reported as taking effort, so a middle tier would be
type aimed at a boundary somebody had recorded in order to avoid it. The old
title/artist/body split had no such reasoning under it — three numbers in
descending order, chosen because a hierarchy wants three.

**What replaces them is not four numbers but one calibrated angle**
(`COMFORTABLE_CAP_ARCMIN`) with a floor below it, converted per device. The
operator settles that angle once, by eye; every deployment after this one states
its own geometry and gets its own pixels.

**Closed 2026-08-11 by the panel visit and 13B-1**, which is where the notes were
replaced along with the values — a settled number left under a note calling it
provisional is worse than either, and that is why this section was rewritten
rather than deleted.

> **All three are one judgement and one visit**, which is why 13B carries them as a
> single deliverable. A margin trades directly against how many lines survive the
> drop rule, and a measure depends on the face and the size — none of the three can
> be settled without the other two in front of you.
>
> *13B's deliverable list named only the type size until 2026-08-11. That was the
> real exposure and not a wording problem: the deliverable list is what a builder
> ticks, so the chunk would have closed with `DEFAULT_EPD_MARGIN_PX = 40` and an
> unbounded measure still carrying their provisional notes — and repeating the
> panel visit is the expensive part. Recording the gap in this artifact was not
> enough; it is now in the plan, where it gets ticked.*

### Line length has a bound, and this panel will stop reaching it

**Practised** — `MEASURE_EM` in `display/src/display/panel/layout.py`, added
2026-08-11. `design_decisions.accessibility_approach` names three things that
carry legibility — type size at reading distance, contrast on a non-emissive
panel, and **line length** — and the third had no mechanism at all. Layout wrapped
to the full text width, so a body line ran as far as the panel allowed.

**The bound is in ems, not characters.** The readable range is conventionally
quoted in characters (roughly 45–75), but the layout tier is handed a measurer and
never a face, so counting characters requires exactly the approximation that tier
exists to refuse. A multiple of the line's own type size is the same rule in the
one unit available there, and it scales the title and the body together instead of
pinning one and distorting the other. The bound only ever narrows: a device
smaller than the measure is a device whose margins still win.

**It is now inert on this wall, as 13B-1 predicted it would be.** At the derived
sizes, 30 em is ~2760 px at the floor against 1318 px of usable width, so the
panel's own edge always governs first and the bound narrows nothing here. Before
the derivation it did bind, at the placeholder sizes, which is why this paragraph
used to be written the other way round.

That is not dead code and it is not a reason to drop it: the norm is
device-independent, and a device drawing its label into the mat area around an
artwork on a wide monitor is exactly where a measure has to exist. **A rule
deleted for being unexercised on one device is a rule the next device does not
get.** But nobody should read `MEASURE_EM` as a control doing something on the
reference panel, because it is not — which is why its own tests exercise it on a
surface wide enough for it to bite rather than on this one.

### Nothing may reason about a panel's geometry anywhere but on that panel

**Practised, and it is a ratified norm** — *"A display device renders its own
label, and the label travels as metadata"* (`architecture.md` § Direction, ratified
2026-08-07, enforcement row in `project-preferences.md`).

Its accessibility content is easy to miss: several devices may carry panels of
different sizes, and the 2024 plane's baked-in 648×480 is the anti-pattern being
retired. Geometry arrives as a parameter; `display/src/display/config.py` defaults to the reference
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

The mechanism covers the part a machine can see. `curation/tests/unit/test_design_tokens.py` derives
every state a badge can carry **from the enums rather than from a written-out
list**, and asserts that each has a CSS block of its own and that no two states of
one axis are pixel-identical — a block copy-pasted for a new verdict with only the
selector changed would otherwise make a rejection look like an acceptance in
greyscale. `curation/tests/unit/test_client_vocabulary.py` asserts that every enum value the server can
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
- **So do labelled controls whose visible words repeat across sibling panels** —
  *"Delete Winter"*, not *"Delete"*. Amended 2026-08-12 after Critic review found
  the Theme screen emitting an identical `Name` field and bare `Rename`/`Delete`
  buttons once per theme: the words were not the problem, the repetition was.
  Somebody moving through the form controls one at a time hears the same three
  announcements N times and can only reconstruct which panel they are in from
  reading order — on a control that destroys something. The original rule said
  *icon-only* because that is where the product had met the problem; the thing it
  was protecting is a control being distinguishable from its siblings, and a
  visible word shared by every sibling fails that as completely as no word at all.
  *(My reading of what the rule was for, ratified by nobody — challenge it if the
  repetition ever turns out to be the cheaper thing to live with.)*
  Where the name can change under the control, re-apply it when it does: a button
  announcing a theme by its old name is worse than one announcing no theme, and
  nothing on screen shows it going stale because the visible words never move.

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

### A confirmation is the platform's `<dialog>`, and there is exactly one of them

**Ruled by the operator 2026-08-12, on a gap this artifact had left open.** The IA
requires a confirmation in at least three places — activation names the wall and
the consequence, archive names which walls lose the picture, and flow 6 makes
activation the one act that changes what other people in the house see — while
neither this artifact nor `design-direction.md` said what a confirmation *is*. Two
chunks needed one at the same time, which is how the silence was found.

**The mechanism is `<dialog>` with `showModal()`, wrapped once in `core/confirm.js`.**
Focus trapping, `Escape` to dismiss, background inertness and `aria-modal`
semantics are then the browser's rather than ours — on a surface with no build step
and no framework, a hand-rolled modal is a focus bug waiting for the one operator
who uses this to hit it. The rules that are *not* free, and are therefore asserted
in the browser suite:

- **Initial focus is the cancel control, never the affirmative one.** A keypress
  that arrives before the sentence has been read must not commit the act.
- **A backdrop click dismisses nothing.** `Escape` is the deliberate exit and is
  the only one; an accidental click outside the dialog resolves the question
  neither way.
- **The dialog leaves the DOM once it settles**, so a screen that confirms twice
  does not accumulate a second one behind the first.
- The title carries the act *and its target* — "Hang Winter in the living room?",
  never "Hang Winter?" — because the governing rule that every act names its wall
  is enforced by what the caller passes, and a confirmation is the last place it
  could be dropped.

**No `danger` styling, and no such class exists to reach for.** The acts that use
this are ordinary and reversible: archive's whole point is that `Restore` exists,
and dressing it as destructive would produce exactly the hesitation over a cheap
act that the IA argues the word "Remove" produces.

Three things the build surfaced that are worth holding, because each is invisible
when it is wrong:

- **Every dialog mints its own ids, and that is an accessibility requirement
  rather than tidiness.** `aria-labelledby` resolves document-wide, so two
  overlapping confirmations sharing one id announce the *older* question above the
  newer question's buttons — while every id still resolves to a real element, so
  the markup inspects clean. Nothing stops two calls overlapping; the platform
  stacks them, `Escape` settles only the topmost, and the one beneath stays
  unanswered.
- **"Initial focus is Cancel" is the one rule here no test can defend**, because
  the platform's own first-focusable default already lands there — Cancel is
  written first. The explicit call survives a mutation sweep only by surviving it,
  and it is kept anyway: it makes the guarantee independent of DOM order rather
  than a coincidence of it, and a link in a consequence or a relaid-out button row
  would break the coincidence silently. Same disposition `MEASURE_EM` carries
  above.
- **Focus restoration on close is inherited and unasserted.** The browser returns
  focus to whatever held it before `showModal()`, and the dialog is removed in the
  `close` handler — after that restoration, which is the ordering that makes it
  work. Nothing tests it, and it would break without a symptom a suite would see.

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
2.25rem default that clears WCAG 2.2 AA's 24px floor. **`curation/src/curation/http/static/app.css` contains no
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
| Every server enum has a client sentence | Test, reads the served `app.js` | `curation/tests/unit/test_client_vocabulary.py` |
| The panel runs at 16 levels | Test — the mode is set, and a panel that quietly stays in one bit is refused | `display/tests/test_epaper.py` |
| Content drops rather than shrinking | Test, against an injected measurer so it runs without a font | `display/tests/test_label_layout.py` |
| Glyph actually distinguishes state | **Critic judgment.** No test can see this | `/prawduct:critic` |
| Focus lands where it should, and a poll does not steal it | **Browser suite**, `-m browser` — a real Chromium against a booted server | `curation/tests/browser/` |
| Type size, margin and measure at reading distance | **The operator, at the panel.** Nothing else can | Chunk 13B, `Visual change: yes` |

**The last row is the one to watch.** It is the only requirement in this artifact
that no machine can close, on the surface this artifact says matters most.
