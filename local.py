from astral import LocationInfo
from astral.sun import sun, dawn, dusk

import config
from dataclasses import dataclass
from datetime import datetime
import logging
import math
from typing import Optional
import tzlocal

logging.basicConfig(format="%(levelname)s:%(message)s", level=logging.INFO)


# A dataclass to hold the sun's information
@dataclass
class SunInfo:
    at_datetime: datetime
    at_latitude: float
    at_longitude: float
    noon: Optional[datetime] = (None,)
    sunrise: Optional[datetime] = None
    sunset: Optional[datetime] = None
    civil_twilight_morning: Optional[datetime] = None
    civil_twilight_evening: Optional[datetime] = None
    solar_angle: Optional[float] = None
    brightness: Optional[float] = None

    def __str__(self):
        return (
            f"SunInfo(at_time={self.at_datetime}, at_latitude={self.at_latitude}, "
            f"at_longitude={self.at_longitude}, sunrise={self.sunrise}, sunset={self.sunset}, noon={self.noon}, "
            f"civil_twilight_morning={self.civil_twilight_morning}, civil_twilight_evening={self.civil_twilight_evening}, "
            f"solar angle={self.solar_angle}, brightness={self.brightness})"
        )


def calculate_solar_declination(day_of_year):
    # Approximate calculation of solar declination angle in degrees
    return 23.44 * math.cos(math.radians(360 / 365 * (day_of_year + 10)))


def perceived_brightness(weather_condition="clear"):
    timezone_name = tzlocal.get_localzone_name()
    timezone = tzlocal.get_localzone()

    # print(f"Timezone: {timezone_name}, {timezone}")
    # Get the current time
    current_time = datetime.now(tz=timezone)

    latitude = config.latitude
    longitude = config.longitude

    location = LocationInfo(name="Seattle", region="United States", latitude=latitude, longitude=longitude)
    s = sun(location.observer, date=current_time, tzinfo=timezone, dawn_dusk_depression=12.0)

    solar_noon = s["noon"]

    delta = current_time - solar_noon
    delta_hours = delta.total_seconds() / 3600

    # Calculate hour angle
    hour_angle = delta_hours * 15  # 15 degrees per hour

    # Calculate solar declination
    day_of_year = current_time.timetuple().tm_yday
    declination = calculate_solar_declination(day_of_year)

    # Calculate solar angle
    solar_angle = math.degrees(
        math.asin(
            math.sin(math.radians(latitude)) * math.sin(math.radians(declination))
            + math.cos(math.radians(latitude)) * math.cos(math.radians(declination)) * math.cos(math.radians(hour_angle))
        )
    )

    # Simplified brightness calculation based on solar angle
    # Add an adjustment that scales from 0 two hours before sunrise to 0.2 at sunrise,
    # stays 0.2 all day, and then scales back to 0 two horus after sunset
    if current_time < s["dawn"] or current_time > s["dusk"]:
        adjustment_pct = 0
        # adjustment is 0 if we're two hours before dawn and scales to 0.2 at dawn
    elif current_time >= s["sunrise"] and current_time <= s["sunset"]:
        adjustment_pct = 1.0
    else:
        # we are either between dawn and sunrise, or between sunset and dusk
        # scale adjustment from 0 to 1 between dawn and sunrise, and then back to 0 between sunset and dusk
        if current_time < s["sunrise"]:
            adjustment_pct = (current_time - s["dawn"]).total_seconds() / (s["sunrise"] - s["dawn"]).total_seconds()
        else:
            adjustment_pct = 1 - (current_time - s["sunset"]).total_seconds() / (s["dusk"] - s["sunset"]).total_seconds()
    dawn_dusk_adjustment = 0.2 * adjustment_pct
    brightness = max(0, dawn_dusk_adjustment + math.cos(math.radians(90 - solar_angle)))

    # Adjust for weather conditions (simplified)
    weather_adjustments = {"clear": 1.0, "partly cloudy": 0.8, "cloudy": 0.5, "rain": 0.3, "storm": 0.1}

    brightness *= weather_adjustments.get(weather_condition, 1.0)

    suninfo: SunInfo = SunInfo(
        at_datetime=current_time,
        at_latitude=latitude,
        at_longitude=longitude,
        noon=s["noon"],
        sunrise=s["sunrise"],
        sunset=s["sunset"],
        civil_twilight_morning=s["dawn"],
        civil_twilight_evening=s["dusk"],
        solar_angle=solar_angle,
        brightness=brightness,
    )

    return suninfo
