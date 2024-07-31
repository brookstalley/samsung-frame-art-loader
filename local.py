from astral import LocationInfo
from astral.sun import sun, dawn, dusk

import config
from dataclasses import dataclass
from datetime import datetime
import ephem
import logging
from typing import Optional
import tzlocal

logging.basicConfig(format="%(levelname)s:%(message)s", level=logging.INFO)


# A dataclass to hold the sun's information
@dataclass
class SunInfo:
    at_time: datetime
    at_latitude: float
    at_longitude: float
    sunrise: Optional[datetime] = None
    sunset: Optional[datetime] = None
    civil_twilight_morning: Optional[datetime] = None
    civil_twilight_evening: Optional[datetime] = None
    declination: Optional[float] = None
    relative_brightness: Optional[float] = None

    def __str__(self):
        return (
            f"SunInfo(at_time={self.at_time}, at_latitude={self.at_latitude}, "
            f"at_longitude={self.at_longitude}, sunrise={self.sunrise}, sunset={self.sunset}, "
            f"civil_twilight_morning={self.civil_twilight_morning}, civil_twilight_evening={self.civil_twilight_evening}, "
            f"declination={self.declination}, relative_brightness={self.relative_brightness})"
        )


def current_sun() -> SunInfo:
    timezone = tzlocal.get_localzone_name()

    # Get the current time
    current_time = datetime.now(tz=tzlocal.get_localzone())

    # Get today's date
    today = datetime.now().date()
    latitude = config.latitude
    longitude = config.longitude

    # Create a LocationInfo object
    location = LocationInfo(name="Current Location", region="Region", timezone=timezone, latitude=latitude, longitude=longitude)

    suninfo = SunInfo(at_time=current_time, at_latitude=latitude, at_longitude=longitude)

    # Calculate sunrise, sunset, and twilight times
    s = sun(location.observer, date=today, tzinfo=tzlocal.get_localzone())

    # Extract times
    suninfo.sunrise = s["sunrise"]
    suninfo.sunset = s["sunset"]
    suninfo.civil_twilight_morning = s["dawn"]
    suninfo.civil_twilight_evening = s["dusk"]

    # Create an observer using ephem
    observer = ephem.Observer()
    observer.lat = str(latitude)
    observer.lon = str(longitude)
    observer.date = current_time

    # Create the sun object using ephem
    sun_ephem = ephem.Sun(observer)

    # Extract the sun's declination
    declination = sun_ephem.dec

    # Convert declination to degrees
    declination_degrees = declination * 180.0 / ephem.pi
    suninfo.declination = declination_degrees
    if current_time < suninfo.civil_twilight_morning or current_time > suninfo.civil_twilight_evening:
        suninfo.relative_brightness = 0.0
    else:
        # we know civil twilight means the declination will be between -6.0 degrees and 90 degrees. Scale that to 0.0 to 1.0
        suninfo.relative_brightness = (declination_degrees + 6.0) / 96.0

    return suninfo
