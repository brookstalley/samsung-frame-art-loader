"""The label: what it says, how it is arranged, and what it is drawn onto.

**A display device renders its own label** (`architecture.md` § Direction). What
crosses from curation is text; everything about how that text is arranged and
what it lands on is decided here, by the device that owns the surface. This
package is that decision split into the three parts the norm names, because they
have genuinely different lifetimes:

* **`metadata`** — what a label says, read off the manifest entry. Shared by
  every device, knows nothing about geometry or pixels, and changes only when
  curation changes what it publishes.
* **`layout`** — where that text goes on a surface of a given size. Pure
  arithmetic over measured text: no drawing, no device, no imaging library, so it
  is testable anywhere and is where the judgement about legibility lives.
* **`surface`** — a thing a laid-out label can be put onto, and the drivers that
  implement it. The e-paper panel is the first, not the only one: a display
  device may have a monitor and no e-ink at all, and draw its label into the mat
  area around the artwork instead.

**"This device has no label surface" is a configuration, not a fault.** A wall
whose device drives a television and nothing else is a supported deployment, and
nothing here may treat its absence as an error to report.

**Nothing in this package may stop the wall.** The television rotation is the
product; the label is an annotation of it. Every failure in here is caught by the
caller and reported, and the picture changes regardless — a panel that is broken,
missing, or slow leaves the wall rotating.
"""

from display.panel.layout import Block, Layout, Surface, lay_out
from display.panel.metadata import LabelText, read_label
from display.panel.surface import LabelSurface, SurfaceUnavailable

__all__ = [
    "Block",
    "LabelSurface",
    "LabelText",
    "Layout",
    "Surface",
    "SurfaceUnavailable",
    "lay_out",
    "read_label",
]
