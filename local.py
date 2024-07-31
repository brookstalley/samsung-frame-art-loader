import math
import datetime
import pytz
from tzlocal import get_localzone
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
    # local_time = dt.astimezone(pytz.timezone("UTC"))  # Assuming the dt is in UTC
    local_time = dt
    local_tz = get_localzone()

    print(f"local time is {local_time}")
    today = datetime.date.today()
    # Get the sunrise and sunset times in UTC
    sunrise_utc = sun.get_sunrise_time(time_zone=local_tz)
    sunset_utc = sun.get_sunset_time(time_zone=local_tz)

    # Convert the times to the local timezone
    sunrise = sunrise_utc.astimezone(local_tz)
    sunset = sunset_utc.astimezone(local_tz)
    # if the sunset is yesterday, add a day to sunset
    if sunset.date() < today:
        sunset = sunset + datetime.timedelta(days=1)

    # adjust sunrise two hours earlier and sunset two hours later to account for twilight
    sunrise = sunrise - datetime.timedelta(hours=2)
    sunset = sunset + datetime.timedelta(hours=2)

    print(f"adjusted sunrise is {sunrise}, sunset is {sunset}")

    # if local time is before sunrise. Use datetime.

    if datetime.datetime.now(local_tz) < sunrise or datetime.datetime.now(local_tz) > sunset:
        return 0

    # Calculate solar elevation angle
    elevation_angle = solar_elevation_angle(latitude, longitude, declination, local_time)

    # Scale elevation angle to brightness (0-10)
    brightness = scale_brightness(elevation_angle)

    return brightness
