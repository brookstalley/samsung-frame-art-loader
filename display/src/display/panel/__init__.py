"""The label: what it says, how it is arranged, and what it is drawn onto.

**A display device renders its own label** (`architecture.md` § Direction). What
crosses from curation is text; everything about how that text is arranged and
what it lands on is decided here, by the device that owns the surface. This
package is that decision split into the parts the norm names — three tiers, and
the derivation that sizes them — because they have genuinely different lifetimes:

* **`metadata`** — what a label says, read off the manifest entry. Shared by
  every device, knows nothing about geometry or pixels, and changes only when
  curation changes what it publishes.
* **`layout`** — where that text goes on a surface of a given size. Pure
  arithmetic over measured text: no drawing, no device, no imaging library, so it
  is testable anywhere and is where the judgement about *arrangement* lives.
* **`legibility`** — how large that text has to be for the person standing in
  front of it. Split out from `layout` rather than folded into it because it
  answers a different question, in different units: a pixel is a fact about a
  panel, while being readable is a fact about a reader at a distance, and this
  product once shipped type at half the resolvable size precisely because nothing
  anywhere converted between the two.
* **`styling`** — how a run of text is set, and the one vocabulary all of the
  above share. Not a tier of its own: it is the words the three tiers use to
  agree, held apart from each of them so that the renderer does not import "what
  a label says" in order to learn what bold means.
* **`content`** — what a label's facts *are*: which of them identify the work and
  so may shrink rather than vanish, and which are set on a line of their own.
  Held apart from `metadata` and `layout` for the reason `styling` is — the first
  decides which fact is which, the second decides what survives the surface, and
  neither is the other's to import for it.
* **`surface`** — a thing a laid-out label can be put onto, and the drivers that
  implement it. The e-paper panel is the first, not the only one: a display
  device may have a monitor and no e-ink at all, and draw its label into the mat
  area around the artwork instead.
* **`corpus`** — real records off the wall, chosen for the ways they break the
  rules above. **The one module here the daemon never imports**, and it is here
  rather than beside the tests because the other reader is
  `tools/label_preview.py`, which draws them on the panel and is the only
  instrument that can settle legibility.

**"This device has no label surface" is a configuration, not a fault.** A wall
whose device drives a television and nothing else is a supported deployment, and
nothing here may treat its absence as an error to report.

**Nothing in this package may stop the wall.** The television rotation is the
product; the label is an annotation of it. Every failure in here is caught by the
caller and reported, and the picture changes regardless — a panel that is broken,
missing, or slow leaves the wall rotating.
"""

from display.panel.content import Candidate, Tier
from display.panel.layout import Block, Extent, Geometry, Layout, Measure, lay_out
from display.panel.legibility import TypeScale, ViewingConditionsUnknown, margin_for, type_scale_for
from display.panel.metadata import LabelText, read_label
from display.panel.raster import Raster, Rasterizer
from display.panel.styling import Case, Line, Run, Slant, Weight, plain, set_text
from display.panel.surface import LabelSurface, SurfaceUnavailable

#: **The drivers are deliberately absent from this list.** `panel.pango` needs a
#: text stack and `panel.epaper` needs a panel driver, neither of which installs
#: on every machine this package is imported on; re-exporting them here would make
#: `import display.panel` — which the daemon does on every device, panel or not —
#: fail wherever those are missing. They are imported by name, from the one place
#: that has decided this device has a panel.
__all__ = [
    "Block",
    "Candidate",
    "Case",
    "Extent",
    "LabelSurface",
    "LabelText",
    "Layout",
    "Line",
    "Measure",
    "Raster",
    "Rasterizer",
    "Geometry",
    "Run",
    "Slant",
    "SurfaceUnavailable",
    "Tier",
    "TypeScale",
    "ViewingConditionsUnknown",
    "Weight",
    "lay_out",
    "margin_for",
    "plain",
    "read_label",
    "set_text",
    "type_scale_for",
]
