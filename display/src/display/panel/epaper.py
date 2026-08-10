"""The e-paper panel, as a surface a label can be put on.

The first implementation of `LabelSurface`, and — per `architecture.md`
§ Direction — deliberately not the only one it is written for: it holds a
rasterizer rather than being one, so a device with a monitor and no e-ink can
reuse the typesetting and supply its own delivery.

**The driver library is imported in one function at the bottom, not at the top.**
Everything in this module except that function runs against any object with the
five verbs omni-epd exposes, which is what lets the rules below — the greyscale
mode, the rotation, the conversion of a silent failure into a raised one — be
tested on a machine with no panel, no SPI and no ability to install the driver at
all. A module-level import would have moved all of it onto hardware.

**Three rules here are corrections applied at the seam**, each recorded from
measurement against the real panel on 2026-08-04
(`platform-and-dependency-findings.md` § The e-paper panel):

* The driver comes up in **1-bit `bw`** unless told otherwise, and `max_colors`
  reports 16 in *both* modes — so the mode is set explicitly and then read back,
  and the read-back is on `mode`. Every legibility claim this product makes
  assumes 16 grey levels, and the 2024 plane shipped 1-bit type past every check
  a reasonable person would have thought to run.
* `display()` returns `None` on success and on failure alike, so nothing here
  reads a return value as confirmation; a failure is a raised
  `SurfaceUnavailable` or it is nothing.
* There is **no partial refresh**. Every label change is a full frame at 1.5–1.9 s,
  which is why `LabelSurface.show` warns that it blocks and why the daemon calls
  it from its own task rather than from the television client's reader.
"""

import logging
from typing import Final, Protocol, runtime_checkable

from PIL import Image

from display.panel.layout import Geometry, Layout, Measure
from display.panel.raster import Raster, Rasterizer
from display.panel.surface import LabelSurface, SurfaceUnavailable

log = logging.getLogger(__name__)

#: The mode this panel must be driven in, in omni-epd's spelling. Not a setting:
#: the sixteen grey levels are what the label's antialiased type is made of, and a
#: deployment that turned them off would be turning off the legibility this
#: product's accessibility posture rests on.
GREYSCALE_MODE: Final[str] = "gray16"

#: How far the rendered label is turned before it reaches the panel. **180 is the
#: reference wall's value, carried forward from the 2024 plane that runs it
#: today** — that panel is mounted with its ribbon at the top, and a device that
#: did not turn the image would show the label upside down. It is configuration
#: rather than a constant because the next device's mounting is the next device's
#: business.
DEFAULT_ROTATE_DEGREES: Final[int] = 180

#: The turns this surface knows how to make. **90 and 270 are refused rather than
#: half-supported**: they exchange the panel's width and height, so the layout
#: above would have to be arranged against the swapped geometry to come out
#: right, and quietly accepting one here would produce a label laid out for a
#: landscape panel and drawn onto a portrait one.
SUPPORTED_ROTATIONS: Final[frozenset[int]] = frozenset({0, 180})


@runtime_checkable
class Epd(Protocol):
    """omni-epd's device surface, written down so this module does not take `Any`.

    **A structural protocol rather than the library's own class**, because naming
    that class here would import it — which is the one thing this module is
    arranged not to do. These are the members this surface *requires*: `clear`
    exists on the library's object too and is unused, since every label replaces
    the last.

    `mode` is a read-write attribute and both directions matter: the driver comes
    up in one bit, and reading it back is the only honest check that it took the
    greyscale it was given.

    **`width` and `height` are read off the object without being declared here**,
    which is deliberate rather than an omission. Not every driver omni-epd wraps
    reports its own geometry, and a panel that does not is a panel this product
    still drives — it just cannot be told that `.env` disagrees with it. Requiring
    them would turn a missing courtesy into a device that will not open.
    """

    mode: str

    def prepare(self) -> None: ...

    def display(self, image: Image.Image) -> None: ...

    def sleep(self) -> None: ...

    def close(self) -> None: ...


class EpaperSurface(LabelSurface):
    """An e-paper panel driven through omni-epd, with a rasterizer to draw for it.

    `epd` is anything exposing omni-epd's device surface — `mode`, `prepare`,
    `display`, `sleep`, `close`. It is passed in rather than opened here so this
    class can be exercised without hardware; `open_panel` below is what produces
    a real one.
    """

    def __init__(
        self,
        *,
        epd: Epd,
        rasterizer: Rasterizer,
        geometry: Geometry,
        rotate_degrees: int = DEFAULT_ROTATE_DEGREES,
    ) -> None:
        if rotate_degrees not in SUPPORTED_ROTATIONS:
            raise SurfaceUnavailable(
                f"a rotation of {rotate_degrees} degrees is not one this surface makes "
                f"({sorted(SUPPORTED_ROTATIONS)}) — a quarter turn exchanges the panel's width and "
                "height, so the label would have to be laid out against the swapped geometry"
            )
        self._epd = epd
        self._rasterizer = rasterizer
        self._geometry = geometry
        self._rotate_degrees = rotate_degrees
        self._set_greyscale_mode()
        self._warn_if_the_panel_disagrees_about_its_size()

    def _set_greyscale_mode(self) -> None:
        """Ask for sixteen grey levels, then check we were given them.

        **Set and read back, because asking is not getting.** The driver's default
        is one bit, and the obvious sanity check — `max_colors` — reports 16
        either way, so a panel silently running in `bw` would pass it. Reading
        `mode` is the only honest test, and a panel that will not take the mode is
        refused here rather than left to draw 1-bit type nobody notices until they
        are standing in front of it.
        """
        try:
            self._epd.mode = GREYSCALE_MODE
            taken = self._epd.mode
        # A Cython SPI driver's failures are not an enumerable set, and every one
        # of them means the same thing to this caller: this device has no panel.
        except Exception as exc:  # prawduct:allow prawduct/broad-except -- see above
            raise SurfaceUnavailable(f"the panel would not take a mode ({exc})") from exc
        if taken != GREYSCALE_MODE:
            raise SurfaceUnavailable(
                f"the panel is in {taken!r} rather than {GREYSCALE_MODE!r}; its sixteen grey levels are "
                "what the label's type is made of, and one bit would be legible only close up"
            )

    def _warn_if_the_panel_disagrees_about_its_size(self) -> None:
        """Say so if the driver reports a size the deployment did not configure.

        **Warns rather than refuses**, the same call `panel_check` makes about the
        television's diagonal and for the same reason: a wrong size gives a label
        that looks wrong, while a refusal gives no label at all, and no label is
        the worse of the two for a surface whose whole posture is that it may
        never stop the wall. The operator gets the two numbers and can fix `.env`.
        """
        reported = (getattr(self._epd, "width", None), getattr(self._epd, "height", None))
        configured = (self._geometry.width_px, self._geometry.height_px)
        if None in reported or reported == configured:
            return
        log.warning(
            "the panel reports %dx%d but EPD_PANEL_WIDTH_PX/HEIGHT_PX say %dx%d; the label is laid out "
            "for the configured size, so fix .env unless the driver is wrong about the panel",
            reported[0],
            reported[1],
            configured[0],
            configured[1],
            extra={"event": "panel.size_disagrees"},
        )

    @property
    def geometry(self) -> Geometry:
        """The configured panel, not the driver's report.

        Configuration wins because the layout has to be arranged before anything
        is drawn and `operational-spec.md` § Configuration makes the panel a
        deployment value; the driver's own answer is compared against it at
        construction and any disagreement is said out loud there.
        """
        return self._geometry

    @property
    def measure(self) -> Measure:
        return self._rasterizer.measure

    def show(self, layout: Layout) -> None:
        """Typeset this label and put the whole frame on the panel.

        **Blocks for seconds** — 1.5–1.9 s measured, and no partial refresh exists
        for this driver, so even a one-character change is a whole frame.
        """
        try:
            # **Typesetting is inside the guard, not before it.** The rasterizer
            # is a text stack reached through C bindings, and a font map that
            # cannot be built raises something with no relation to anything the
            # driver throws. Leaving it outside would make this method's promise —
            # a failure here is a `SurfaceUnavailable` — true only of the half of
            # its work that touches hardware, and the caller catches that one type.
            image = _as_image(self._rasterizer.render(layout), self._rotate_degrees)
            self._epd.prepare()
            # No return value is read. `display()` answers `None` whether it
            # worked or not, so the only thing that distinguishes the two is
            # whether it raised — which is what this converts.
            self._epd.display(image)
            self._epd.sleep()
        # The driver stack raises SPI, GPIO and Cython errors that share no base
        # class, and the text stack above adds GLib's; the caller answers all of
        # them the same way: say so once, and keep rotating the wall.
        except Exception as exc:  # prawduct:allow prawduct/broad-except -- see above
            raise SurfaceUnavailable(f"the panel refused a frame ({exc})") from exc

    def close(self) -> None:
        """Release the panel. Never raises — this runs on the way out.

        A failure here is logged and dropped rather than propagated, because the
        only caller is shutdown: raising would turn a panel that cannot be closed
        into a daemon that does not close its television connection either, and
        the set holds an abandoned art channel for minutes.
        """
        try:
            self._epd.close()
        # This runs on the shutdown path, where anything raised would cost the
        # television its clean disconnect.
        except Exception as exc:  # prawduct:allow prawduct/broad-except -- see above
            log.warning("the panel did not close cleanly (%s)", exc, extra={"event": "panel.close_failed"})


def _as_image(raster: Raster, rotate_degrees: int) -> Image.Image:
    """The rendered bytes as the greyscale image omni-epd's `display()` takes.

    Rotation happens here rather than in the rasterizer because it is a fact about
    how this panel is screwed to a wall, not about how the label is typeset — the
    same rendering hangs the other way up on a device mounted the other way up.
    """
    image = Image.frombytes("L", (raster.width_px, raster.height_px), raster.pixels)
    return image.rotate(rotate_degrees) if rotate_degrees else image


def open_panel(device_name: str) -> Epd:
    """Open the named omni-epd device, or say why not.

    **The only place the driver library is named**, and the only thing in this
    module that needs it installed. `device_name` is omni-epd's own identifier —
    `waveshare_epd.it8951` on the reference wall, `omni_epd.mock` on a machine
    with no panel attached.
    """
    try:
        from omni_epd import displayfactory  # noqa: PLC0415 -- deliberately local: see the module docstring

        return displayfactory.load_display_driver(device_name)
    # Covers the library being absent (ImportError) and the device being
    # unopenable (EPDNotFoundError, and whatever the driver raises below it).
    # One outcome here: this device has no panel it can draw on.
    except Exception as exc:  # prawduct:allow prawduct/broad-except -- see above
        raise SurfaceUnavailable(f"could not open the e-paper device {device_name!r} ({exc})") from exc
