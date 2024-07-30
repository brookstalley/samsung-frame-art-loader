import math
from datetime import datetime, timedelta
import pytz
from suntime import Sun


def calculate_relative_brightness(dt, latitude, longitude) -> float:
    def solar_declination(day_of_year):
        return 23.44 * math.cos(math.radians((360 / 365.24) * (day_of_year - 81)))

    def solar_elevation_angle(latitude, longitude, declination, time_utc):
        time_offset = (time_utc.hour + time_utc.minute / 60 + time_utc.second / 3600 + longitude / 15) % 24
        solar_hour_angle = 15 * (time_offset - 12)
        latitude_rad = math.radians(latitude)
        declination_rad = math.radians(declination)
        elevation_angle = math.degrees(
            math.asin(
                math.sin(latitude_rad) * math.sin(declination_rad)
                + math.cos(latitude_rad) * math.cos(declination_rad) * math.cos(math.radians(solar_hour_angle))
            )
        )
        return elevation_angle

    def scale_brightness(elevation_angle):
        if elevation_angle <= 0:
            return 0.0
        elif elevation_angle >= 90:
            return 10.0
        return elevation_angle / 90.0

    # Calculate solar declination
    day_of_year = dt.timetuple().tm_yday
    declination = solar_declination(day_of_year)

    # Get local sunrise and sunset times
    sun = Sun(latitude, longitude)
    local_time = dt.astimezone(pytz.timezone("UTC"))  # Assuming the dt is in UTC
    sunrise = sun.get_sunrise_time(local_time).astimezone(pytz.timezone("UTC"))
    sunset = sun.get_sunset_time(local_time).astimezone(pytz.timezone("UTC"))

    if local_time < sunrise or local_time > sunset:
        return 0

    # Calculate solar elevation angle
    elevation_angle = solar_elevation_angle(latitude, longitude, declination, local_time)

    # Scale elevation angle to brightness (0-10)
    brightness = scale_brightness(elevation_angle)

    return brightness
