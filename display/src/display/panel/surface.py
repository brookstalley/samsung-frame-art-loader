"""A thing a label can be put onto, and what goes wrong with one.

The third tier. **Deliberately not named for e-ink**: the first implementation
drives a 1448×1072 e-paper panel, and a display device may instead have a monitor
and no panel at all, drawing its label into the mat area around the artwork
(`architecture.md` § Direction). A seam called `EpaperPanel` would have made that
device a rewrite; this one it can implement.

**The interface is deliberately tiny.** Two verbs and a geometry. Everything
about what a label says and how it is arranged is settled before anything here is
called, so a new device implements drawing and nothing else.

**Failure is always an exception here, never a return value.** That is not a
style preference — it is a correction applied at the seam, in the same spirit as
the television client's. `omni-epd`'s `display()` returns `None` on success and
on failure alike, so a caller reading its return learns nothing; the driver below
must turn that into a raised `SurfaceUnavailable` or the panel's failure mode
becomes a label that is silently months out of date beside a picture that keeps
changing.
"""

from abc import ABC, abstractmethod

from display.panel.layout import Layout, Measure, Surface


class SurfaceUnavailable(Exception):
    """The label could not be put on the surface.

    One type for every cause, for the reason the television's `TvUnavailable`
    has one: the caller's response is the same to all of them — say so once,
    carry on rotating the wall — and branching on which would encode a driver's
    internals into the loop that exists to be independent of them.
    """


class LabelSurface(ABC):
    """Something a laid-out label can be drawn onto.

    An abstract base rather than a structural protocol, matching `TvClient` and
    for the same reason: the test double subclasses it, so a verb added here
    fails the double loudly at import instead of leaving it quietly behind.
    """

    @property
    @abstractmethod
    def geometry(self) -> Surface:
        """The surface's own size and margin, for the layout tier to arrange within.

        A property of the device rather than a constant anywhere else: this is the
        one place that knows how big this particular panel or window is.
        """

    @property
    @abstractmethod
    def measure(self) -> Measure:
        """How this surface measures text, for the layout tier to arrange with.

        **On the surface rather than beside it, because only the surface knows.**
        Line breaking depends on the real face at the real size, so the numbers
        must come from whatever will actually draw — and a caller that had to
        build a measurer itself would be constructing the rasterizer outside this
        seam, which is the seam not existing.

        A caller therefore needs nothing but this object: ask for `geometry`, lay
        out against `measure`, hand the result to `show`.
        """

    @abstractmethod
    def show(self, layout: Layout) -> None:
        """Draw this label, replacing whatever was there.

        Raises `SurfaceUnavailable` if it could not be drawn. Returning normally
        means the surface accepted it — as strongly as the device can say so,
        which for e-paper is "the driver did not raise", since the panel offers
        no read-back.

        **May block for seconds.** A full-frame e-paper refresh was measured at
        1.5–1.9 s, and there is no partial refresh on that driver — every change,
        even one character, is a whole frame. Callers must not run this anywhere
        that a second of latency matters, and specifically not on the television
        client's reader task.
        """

    @abstractmethod
    def close(self) -> None:
        """Release the device. Never raises — this runs on the way out."""
