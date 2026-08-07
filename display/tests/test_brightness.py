"""The wall follows the sun, and the curve is asserted at named hours.

Time is a parameter to every function here, so a December dusk is a test rather
than a wait.
"""

from datetime import UTC, datetime, timedelta

import pytest

from display.brightness import solar_declination, sun_state, television_brightness

BOZEMAN = {"latitude": 45.68, "longitude": -111.04, "location_name": "Bozeman", "location_region": "USA"}


def at(month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, month, day, hour, minute, tzinfo=UTC)


class TestTheCurve:
    def test_the_sun_is_highest_at_solar_noon_in_summer(self):
        summer = sun_state(at(6, 21, 19), **BOZEMAN)  # ~solar noon at this longitude
        winter = sun_state(at(12, 21, 19), **BOZEMAN)

        assert summer.solar_angle_degrees > winter.solar_angle_degrees
        assert summer.relative_brightness > winter.relative_brightness

    def test_the_middle_of_the_night_is_dark(self):
        night = sun_state(at(6, 21, 8), **BOZEMAN)  # ~2am local

        assert night.relative_brightness == 0.0

    def test_brightness_never_goes_negative_below_the_horizon(self):
        """`cos(90 - angle)` goes negative under the horizon, and the floor is what
        makes night black rather than inverted."""
        for hour in range(24):
            assert sun_state(at(12, 21, hour), **BOZEMAN).relative_brightness >= 0.0

    def test_twilight_is_lifted_off_the_floor(self):
        """So the panel does not read as *off* while there is still light in the room."""
        deep_night = sun_state(at(6, 21, 8), **BOZEMAN)
        dawn = _first_lit_moment()

        assert deep_night.relative_brightness == 0.0
        assert dawn.relative_brightness > 0.0

    def test_declination_swings_between_the_tropics(self):
        angles = [solar_declination(day) for day in range(1, 366)]

        assert max(angles) == pytest.approx(23.44, abs=0.05)
        assert min(angles) == pytest.approx(-23.44, abs=0.05)

    def test_a_naive_datetime_is_refused_rather_than_answered_for_the_wrong_hour(self):
        with pytest.raises(TypeError):
            sun_state(datetime(2026, 6, 21, 12), **BOZEMAN)


def _first_lit_moment() -> object:
    """The first minute after deep night with any light in it.

    Found rather than hardcoded: dawn moves with the date and the latitude, and a
    fixed hour would be a test that only passes in Bozeman in June.
    """
    moment = at(6, 21, 8)
    for _ in range(24 * 60):
        moment += timedelta(minutes=1)
        state = sun_state(moment, **BOZEMAN)
        if state.relative_brightness > 0:
            return state
    raise AssertionError("the sun never came up")


class TestTheTelevisionScale:
    def test_it_maps_onto_the_set_s_own_range_which_is_not_zero_to_ten(self):
        assert television_brightness(0.0, minimum=-4, maximum=10) == -4
        assert television_brightness(1.0, minimum=-4, maximum=10) == 10
        assert television_brightness(0.5, minimum=-4, maximum=10) == 3

    def test_it_clamps_rather_than_letting_the_set_refuse_the_call(self):
        """The twilight lift can push the relative value above 1.0 just after
        sunrise, and a value off the end of the scale takes the whole call down."""
        assert television_brightness(1.15, minimum=-4, maximum=10) == 10
        assert television_brightness(-0.5, minimum=-4, maximum=10) == -4


class TestTheDaemonWritesOnlyOnChange:
    async def test_it_sets_brightness_on_the_first_pass(self, daemon, tv, publish):
        publish(["w1"])

        await daemon.tick()

        assert len(tv.brightness) == 1

    async def test_it_does_not_consult_the_sun_within_the_interval(self, daemon, tv, publish, clock):
        publish(["w1"])
        await daemon.tick()

        for _ in range(20):
            clock.advance(14)  # 280s in total, inside the 300s interval
            await daemon.tick()

        assert len(tv.brightness) == 1

    async def test_it_does_not_write_the_same_value_twice(self, daemon, tv, publish, clock):
        """Asserted across deep night, where the value is genuinely pinned.

        The first draft of this test ran across a June *sunrise* and failed
        correctly: the brightness really was changing every five minutes. Night is
        the window where a second write would be the code repeating itself rather
        than the sun moving.
        """
        clock.move_to(at(6, 21, 8))  # ~2am in Bozeman: hours from any light
        publish(["w1"])
        await daemon.tick()

        for _ in range(6):
            clock.advance(300)
            await daemon.tick()

        assert len(tv.brightness) == 1, "the same brightness was sent to the television repeatedly"
        assert tv.brightness == [-4]

    async def test_it_follows_the_sun_across_a_day(self, daemon, tv, publish, clock):
        publish(["w1"])
        await daemon.tick()

        for _ in range(48):
            clock.advance(1800)
            await daemon.tick()

        assert len(set(tv.brightness)) > 3, "the brightness never changed across a whole day"
        assert min(tv.brightness) >= -4
        assert max(tv.brightness) <= 10
