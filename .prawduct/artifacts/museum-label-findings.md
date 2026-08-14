# Museum labels: what the convention is, and where each source puts the maker

**What this is.** The wall label this product sets is a museum tombstone, and
this project has now reasoned its way to the same conventions from first
principles three times — once when the ordering was chosen (13B-3), once when the
biography left the name's line at the panel, and once when an "open question"
about an unattributed work turned out to have a settled answer nobody had looked
up. This document records the convention **and its sources**, so the next reading
is a lookup rather than a rediscovery.

**Written 2026-08-13**, from published label-writing guidance and from the
collection APIs this product actually consumes. Museum labelling practice is not
fast-moving — none of this is expected to drift — but the *API field mappings* in
§ Where each source puts the maker are a foreign contract and belong to
`api-drift.yml`'s world rather than to this one's.

## The tombstone, in the two forms it takes

**There are two orderings, not one, and which applies depends on whether a person
made the work.** Both are quoted verbatim from the North Carolina Museum of Art's
label-writing guidance, the second attributed there to their curator of ancient
art.

| Modern and contemporary | Ancient / culture-attributed |
|---|---|
| Artist's name, year born | **Culture** (e.g. Cycladic) |
| City/location born, where they live now or year of death | Place of origin (if known) |
| **Title** | Date and/or time period |
| Date | Material(s) |
| Medium | Credit line |
| Credit line | |

**The maker leads in both.** That is the single rule the two forms share, and it
is the one this product's `accessibility-spec.md` reached independently and
ratified as "the artist outranks the work". A culture is not a fallback for a
missing artist — **it occupies the maker slot**, and it leads for the same reason
a name does.

**The title does not appear at all in the ancient form**, because an object like
`Water Jar` or `Stirrup Spout Vessel` is named descriptively by the museum rather
than titled by its maker.

**That it is nonetheless printed, below the culture, is inference and not
source.** The guidance quoted above simply omits it, and no source consulted
shows a culture-attributed wall label with its object name in place. What *is*
sourced is the rule the omission cannot contradict — the maker leads — so a
descriptive name set after the culture is the reading consistent with both forms.
If this ever needs to be firmer than inference, the check is a photograph of a
real label, not another guidance document.

**Whatever is not known is not printed, and nothing is invented to fill the
slot.** Wikipedia's summary of the general rule — a label "should identify the
creator, title, date, location, and materials of the work, **insofar as these can
be known**" — is the same rule this product already holds as "an unknown artist is
a fact about the record, not a reason to guess at one". It is why mapping an
absent maker to the literal word `Unknown` is wrong: it prints a non-fact in the
position the label's largest type is reserved for.

## What this settled, and what it corrected

**`Japanese` above `Water Jar` is the convention, not a defect.**
`accessibility-spec.md` § The label's content model carried an open question
saying museums "print the reverse for an unattributed work — title first, culture
and period after it". That is not what they print. The question is closed by the
table above, and the ordering the engine already produces is correct.

**A single web page will appear to contradict this — it does not.** The Art
Institute's object page for `Hydria (Water Jar)` renders `Hydria (Water Jar)` /
`Date: about 300 BCE` / `Artist: Greek; possibly Apulia or Campania, Italy` —
title first. That is web-page genre, where the object's name is the page heading
and the fields below it are a details list. It is not a wall label, and this
product sets a wall label. Recorded here because it is the first thing a
re-investigation will find.

## Where each source puts the maker

**The two collections this product draws on model a culture-attributed work
differently, and neither matches the other.** This is the mapping that decides
whether the label leads with a maker at all.

| | Art Institute of Chicago | Metropolitan Museum |
|---|---|---|
| Person's name | `artist_title` | `artistDisplayName` |
| Maker as printed | `artist_display` | `artistDisplayName` + `artistDisplayBio` |
| Culture | **`artist_display`, in the maker slot** | **`culture`, its own field** |
| When no person is known | `artist_title` is `null`; `artist_display` carries the culture | `artistDisplayName` is `""`; `culture` may or may not be set |

**The Art Institute puts the culture where the artist goes.** Observed
2026-08-13 through the public API:

```
artist_title: null   artist_display: "Japan"
artist_title: null   artist_display: "India\nNagapattinam, Tamil Nadu"
artist_title: null   artist_display: "Central Ethiopia\nEastern and Southern Africa"
artist_title: null   artist_display: "Greek; possibly Apulia or Campania, Italy"
```

**17,144 of its objects have no `artist_title`** — a count taken 2026-08-13 from a
`must_not exists` query, and cited because the order of magnitude is the point:
this is most of Arts of Asia and Arts of Africa, not an edge case. The figure
will drift and nothing reads it; re-run the query rather than trusting it.

**The Met keeps culture in its own field**, and will leave *both* empty: the
`Sphinx of Hatshepsut` has `artistDisplayName: ""` and `culture: ""`, carrying
only `period: "New Kingdom"`. A consumer that expects a culture wherever a name is
missing will find nothing here.

**A work with no maker of any kind is therefore real**, and the label engine's
handling of it — the identification tier withheld, everything set at the floor —
is the honest answer rather than a gap. What is *not* real, on either source, is a
culture recorded as a nationality against an empty name: that shape only arises
from a mapping that drops the maker.

## The consumer this product got wrong

**`curation/src/curation/discovery/artic.py` reads `artist_title` and never
`artist_display`.** For every object in the count above, the product records no
maker and the culture is discarded entirely — it does not even survive as a
nationality. The museum said the maker is `Japan`; the catalogue says the maker is
unknown.

The correct mapping follows from the table: **when `artist_title` is absent, the
culture in `artist_display` is the maker**, and belongs in the name field where
the label will lead with it. It is not a nationality — `artist_nationality` holds
what the institution printed *about a person*, which is why `display_nationality`
exists beside it.

Filed rather than fixed with this document, because it is curation-plane work and
this was written on a display-plane branch.
