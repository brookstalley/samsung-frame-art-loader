"""Panel brightness that follows the sun rather than the clock.

A winter afternoon and a summer evening are not the same room, and a fixed
schedule gets both wrong: it dims a bright June evening and blazes through a
December dusk. The wall has run on solar position since 2024 and this is that
behaviour carried across, not redesigned — the numbers below are the ones the
household is used to living with.

The shape is: solar elevation gives a relative brightness of 0..1, a dawn/dusk
term lifts the twilight hour off the floor so the wall does not go black while
there is still light in the room, and the result is mapped onto the television's
own scale, which is **-4 to 10** rather than any of the ranges one would guess.

**Two knobs from the 2024 code are deliberately not carried.** A weather
adjustment took a condition string and scaled the result — but nothing in this
product knows the weather, every caller passed "clear", and "clear" is a
multiplier of 1.0; a parameter with one reachable value is dead code that reads
as a feature. And a "scale 0.8 up to 1.0" correction was written as a division by
a constant 1.0, so it multiplied by one. Neither removal changes a single
brightness value; both were left in place would-be mysteries.

Everything here is a pure function of an instant and a place. The clock is a
parameter, so the whole curve is testable at any hour of any year without
waiting for one.
"""

import logging
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from astral import LocationInfo
from astral.sun import sun

log = logging.getLogger(__name__)

#: How far below the horizon counts as twilight, in degrees. 12° is nautical
#: twilight — the 2024 value, kept because it is what the wall's dusk behaviour
#: was tuned against, not because 12 is special.
_TWILIGHT_DEPRESSION: Final[float] = 12.0

#: How much of the scale the twilight lift is worth at its fullest. Small on
#: purpose: it exists to keep the panel from reading as *off* while there is
#: still light in the room, not to make dusk look like noon.
_TWILIGHT_LIFT: Final[float] = 0.15


@dataclass(frozen=True)
class SunState:
    """Where the sun is, and what that is worth as a fraction of full brightness."""

    at: datetime
    solar_angle_degrees: float
    #: 0.0 at and below the horizon, rising towards 1.0 with the sun overhead.
    #: Not clamped at the top: this latitude never reaches 1.0, and clamping a
    #: value that cannot occur only hides the day it does.
    relative_brightness: float


def solar_declination(day_of_year: int) -> float:
    """The sun's declination for a day of the year, in degrees.

    The standard approximation — good to well under a degree, which is far finer
    than a fifteen-step brightness scale can express.
    """
    return 23.44 * math.sin(math.radians((360 / 365) * (day_of_year - 81)))


def sun_state(now: datetime, *, latitude: float, longitude: float, location_name: str, location_region: str) -> SunState:
    """Where the sun is at `now`, seen from this deployment's own coordinates.

    `now` must be timezone-aware: the twilight comparisons below are against
    astral's own aware datetimes, and mixing a naive one in raises rather than
    quietly answering for the wrong hour.
    """
    location = LocationInfo(name=location_name, region=location_region, latitude=latitude, longitude=longitude)
    today = sun(location.observer, date=now, tzinfo=now.tzinfo, dawn_dusk_depression=_TWILIGHT_DEPRESSION)

    hours_from_noon = (now - today["noon"]).total_seconds() / 3600
    hour_angle = hours_from_noon * 15  # The earth turns 15° an hour.
    declination = solar_declination(now.timetuple().tm_yday)

    solar_angle = math.degrees(
        math.asin(
            math.sin(math.radians(latitude)) * math.sin(math.radians(declination))
            + math.cos(math.radians(latitude)) * math.cos(math.radians(declination)) * math.cos(math.radians(hour_angle))
        )
    )

    # Elevation to brightness. `cos(90 - angle)` is `sin(angle)`, written the long
    # way in 2024; below the horizon it goes negative, and the floor is what makes
    # night black rather than inverted.
    brightness = max(0.0, math.cos(math.radians(90 - solar_angle)))
    brightness += _TWILIGHT_LIFT * _twilight_fraction(now, today)

    return SunState(at=now, solar_angle_degrees=solar_angle, relative_brightness=brightness)


def _twilight_fraction(now: datetime, today: dict[str, datetime]) -> float:
    """How much of the twilight lift applies at this instant, 0..1.

    Full between sunrise and sunset, nothing outside dawn..dusk, and a straight
    ramp across each twilight so the panel changes smoothly rather than stepping
    at the horizon.
    """
    if now < today["dawn"] or now > today["dusk"]:
        return 0.0
    if today["sunrise"] <= now <= today["sunset"]:
        return 1.0
    if now < today["sunrise"]:
        return (now - today["dawn"]).total_seconds() / (today["sunrise"] - today["dawn"]).total_seconds()
    return 1 - (now - today["sunset"]).total_seconds() / (today["dusk"] - today["sunset"]).total_seconds()


def television_brightness(relative_brightness: float, *, minimum: int, maximum: int) -> int:
    """Map 0..1 onto the television's own scale, which is not 0..100 and not 0..10.

    Clamped at both ends rather than trusted: the twilight lift can push the
    relative value above 1.0 just after sunrise, and a value off the end of the
    set's scale is refused by the television rather than saturated by it — which
    would take the whole call down over an arithmetic edge.
    """
    span = maximum - minimum
    value = round(max(0.0, min(1.0, relative_brightness)) * span) + minimum
    return max(minimum, min(maximum, value))
