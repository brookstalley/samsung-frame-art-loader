"""How large type has to be for the person standing in front of it.

**A pixel is a fact about a panel; legibility is a fact about a person at a
distance.** This module is the conversion between the two, and it exists because
the product shipped without it: three artifacts reasoned carefully about which
pixel value the label should use while none of them asked how far away the reader
stands, and the answer that survived a hardware probe, a Critic round and a
cutover was **half the size at which a letter can be resolved at all**.

So the floor is *derived* rather than chosen, from two physical facts the
deployment states — the panel's diagonal and the distance it is read from —
against a minimum cap height in arcminutes that is a fact about human vision
rather than about any wall. Three consequences, all of them the reason:

* **A pixel floor is a claim about one panel at one distance.** A second device,
  with a different panel read from a different distance, gets a correct floor
  with nobody visiting it.
* **An adaptive layout needs a floor to adapt against.** An engine spending slack
  on more content or on larger type has to know what "too small" *is*, expressed
  in the reader's terms rather than the panel's.
* **It settles once.** The arcminute figures below are calibrated by eye, one
  time; every future deployment inherits them and supplies only its own geometry.

**This module holds no deployment value and imports nothing from this package.**
The geometry arrives as arguments, and the caller that has decided this device has
a panel is the one that reads `.env` — which is also what keeps this importable
from the layout tier without a cycle.
"""

import math
from dataclasses import dataclass
from typing import Final


class ViewingConditionsUnknown(Exception):
    """The deployment did not say how big its panel is, or how far away it is read.

    **Raised rather than defaulted, and that asymmetry is the whole point.** Every
    other unstated value in this plane takes a sensible default; a viewing distance
    must not, because a wrong distance produces silently illegible type — which is
    precisely the failure this module exists to prevent, and it looks like success
    from every direction except standing in front of the panel.

    The caller converts this into a surface that is unavailable with a named
    reason, never into a refusal to start: nothing about the label may stop the
    wall, and a device with no usable label surface is a supported configuration.
    """


#: One arcminute of visual angle, as a tangent. At the distances and angles in
#: play the small-angle approximation would be indistinguishable, but the exact
#: form costs nothing and does not have to be justified to the next reader.
ARCMINUTE_TANGENT: Final[float] = math.tan(math.radians(1 / 60))

#: The cap height, in arcminutes, of type this product calls comfortable to read
#: at a glance — the tier the identifying facts are set at.
#:
#: **Calibrated at the panel, not taken from the literature**, and the difference
#: mattered: the operator read a six-rung ladder from the viewing position in
#: normal room light and put "comfortable at a glance" here, "made out with
#: effort" one rung below (recorded in `accessibility-spec.md` as the squint
#: boundary precisely so that nobody aims at it), and "acceptable if a reader
#: steps closer" at the floor below. A defensible 10 arcminutes from the
#: legibility literature would have set this tier ~20% too small, and that error
#: is invisible to everyone except the person who cannot read it.
#:
#: **Conservative by an amount worth knowing**: the ladder was set in regular
#: weight, and stroke weight matters disproportionately on a reflective panel
#: where contrast rather than resolution is the limit. Bold type may reach the
#: same comfort a size step down.
COMFORTABLE_CAP_ARCMIN: Final[float] = 12.4

#: The absolute floor, in arcminutes: the size the operator called acceptable only
#: for a reader who steps closer. **Nothing optional is ever set below this.**
#:
#: That there are two of these is the two-distance label made numeric. Museum
#: practice sets the identification block for the approach and the extended text
#: for whoever walks up; the operator reached the same split independently, by
#: naming a size that was acceptable only closer to.
MINIMUM_CAP_ARCMIN: Final[float] = 8.8

#: A face's cap height as a fraction of its em, which is what converts a cap
#: height somebody can read into a type size something can be set at. **Stated
#: rather than measured**: it varies little across the text faces in scope, and a
#: floor that is a few percent conservative is harmless in the direction that
#: matters.
CAP_RATIO: Final[float] = 0.70

#: The clear border around the label, as a fraction of the largest type on it.
#:
#: **Derived rather than judged, because it cannot be picked independently.** A
#: border trades directly against how many lines survive the drop rule, so a
#: margin chosen without reference to the floor that decides how many lines there
#: are is a number in tension with one nobody compared it to. Anchoring it to the
#: primary tier makes the border scale with the type instead.
#:
#: **Half an em is the round number nearest the one observation there is.** The
#: 2026-08-11 panel work ran a 60 px border to keep the largest rung of the type
#: ladder clear of the bezel; against a primary tier of ~130 px that is 0.46, and
#: 0.5 reproduces it within a few pixels while scaling to the next device. It is
#: the one number here an operator might reasonably move, and moving it is one
#: constant rather than a revisit.
MARGIN_TO_PRIMARY_RATIO: Final[float] = 0.5


@dataclass(frozen=True, slots=True)
class TypeScale:
    """The two sizes a given reader, at a given distance, can actually resolve.

    **Two rather than three, and the missing one is deliberate.** The calibration
    settled exactly two readings worth aiming at; the rung between them is the
    squint boundary, and a hierarchy that interpolated a middle tier would be
    aiming type at the size the operator named as the one that takes effort.

    Carried as a parameter beside `Geometry` rather than held as constants
    anywhere, for the reason geometry is: the deployment may hold several devices
    whose panels differ, and one of them may draw its label into the mat area
    around an artwork rather than onto a panel at all.
    """

    #: The identification tier — the leading, most identifying line.
    primary_px: int
    #: The floor. Everything else is set here, and nothing optional goes below it.
    floor_px: int


def pixels_per_inch(*, width_px: int, height_px: int, diagonal_inches: float) -> float:
    """This panel's resolution, from the two numbers a datasheet actually gives.

    Panels are sold by diagonal and pixel count, never by PPI, so this is the
    arithmetic that keeps the deployment stating things it can look up rather than
    a derived number it would have to compute correctly by hand.
    """
    return math.hypot(width_px, height_px) / diagonal_inches


def pixels_per_arcminute(*, ppi: float, viewing_distance_inches: float) -> float:
    """How many pixels one arcminute of the reader's visual field covers.

    The bridge between the panel's units and the reader's: everything above is
    stated in arcminutes because that is the unit in which "can this be read"
    has an answer, and everything below is in pixels because that is what gets
    set.
    """
    return ppi * viewing_distance_inches * ARCMINUTE_TANGENT


def type_scale_for(
    *,
    width_px: int,
    height_px: int,
    diagonal_inches: float | None,
    viewing_distance_inches: float | None,
) -> TypeScale:
    """The sizes this deployment must set type at, or say why it cannot be known.

    Raises `ViewingConditionsUnknown` when either physical fact is missing or
    unusable. **There is no fallback on purpose** — see that exception.
    """
    if diagonal_inches is None or viewing_distance_inches is None:
        missing = " and ".join(
            name
            for name, value in (
                ("EPD_PANEL_DIAGONAL_INCHES", diagonal_inches),
                ("EPD_VIEWING_DISTANCE_INCHES", viewing_distance_inches),
            )
            if value is None
        )
        raise ViewingConditionsUnknown(
            f"this device has a panel configured but {missing} is not set, so how large its type "
            "would have to be to be readable cannot be worked out. Set it in .env — guessing a "
            "distance produces type that is illegible without anything reporting it"
        )
    if diagonal_inches <= 0 or viewing_distance_inches <= 0:
        # A zero is as unusable as an absence and arrives the same way — somebody
        # typed the key and left the value empty, or wrote a placeholder. It gets
        # the same answer rather than a division by zero or a floor of nothing.
        raise ViewingConditionsUnknown(
            f"EPD_PANEL_DIAGONAL_INCHES is {diagonal_inches} and EPD_VIEWING_DISTANCE_INCHES is "
            f"{viewing_distance_inches}; both have to be real positive measurements before the "
            "label's type size means anything"
        )

    per_arcmin = pixels_per_arcminute(
        ppi=pixels_per_inch(width_px=width_px, height_px=height_px, diagonal_inches=diagonal_inches),
        viewing_distance_inches=viewing_distance_inches,
    )
    floor_px = _em_for(MINIMUM_CAP_ARCMIN, per_arcmin)
    return TypeScale(
        # **The primary tier can never be below the floor**, which is not a
        # tautology the two constants already guarantee. They are calibrated by
        # eye and `label_preview.py` patches the comfortable one to try a
        # candidate — so a recalibration that put it under the minimum would
        # silently invert the hierarchy AND set the most identifying line below
        # the one size this module exists to hold. Clamped rather than raised,
        # because the answer is never in doubt: the floor is the floor.
        primary_px=max(_em_for(COMFORTABLE_CAP_ARCMIN, per_arcmin), floor_px),
        floor_px=floor_px,
    )


def margin_for(scale: TypeScale) -> int:
    """The clear border a label at this scale gets. See `MARGIN_TO_PRIMARY_RATIO`."""
    return round(scale.primary_px * MARGIN_TO_PRIMARY_RATIO)


def _em_for(cap_arcmin: float, pixels_per_arcmin: float) -> int:
    """The type size whose caps subtend this angle.

    At least one pixel, because a surface so small or so distant that the answer
    rounds to zero is a misconfigured device — and a size of zero would be a
    label that draws nothing, which reports the misconfiguration as a work with
    no name.
    """
    return max(1, round((cap_arcmin / CAP_RATIO) * pixels_per_arcmin))
