"""A television that is asleep, and a curation plane that is gone.

Neither is an incident. The set is asleep most of the time, and the ratified norm
says this plane's ability to show art never depends on the other one being
reachable — so "curation stopped" has to be indistinguishable, from here, from
"curation has nothing new to say".
"""

import logging

from fakes import FakeTv

from display.daemon import Daemon
from display.state import DisplayState


async def test_killing_curation_changes_nothing(daemon: Daemon, tv: FakeTv, publish, clock, art_root, caplog):
    """The acceptance criterion, made mechanical.

    Nothing here stands in for the curation process, and that is the test: with
    the manifest file frozen where it is, the wall goes on rotating forever.
    """
    publish(["w1", "w2", "w3"], interval_seconds=10)
    await daemon.tick()

    # Curation is gone. Its manifest is not.
    with caplog.at_level(logging.WARNING):
        for _ in range(6):
            clock.advance(10)
            await daemon.tick()

    assert len(tv.selected) == 7
    assert [record.levelno for record in caplog.records] == []


async def test_a_manifest_that_never_arrives_is_waited_on_quietly(daemon: Daemon, tv: FakeTv, caplog):
    with caplog.at_level(logging.WARNING):
        for _ in range(3):
            await daemon.tick()

    assert tv.selected == []
    assert tv.connects == 0, "a plane with nothing to show opened a connection to the television"
    assert [record.levelno for record in caplog.records] == []


async def test_an_asleep_television_backs_off_and_reports_once(daemon: Daemon, tv: FakeTv, publish, caplog):
    """One WARNING a second until morning buries every other line in the journal."""
    publish(["w1"])
    tv.unavailable = True

    with caplog.at_level(logging.WARNING):
        waits = [await daemon.tick() for _ in range(5)]

    unavailable = [r for r in caplog.records if r.__dict__.get("event") == "tv.unavailable"]
    assert len(unavailable) == 1
    assert waits == [5.0, 10.0, 20.0, 40.0, 80.0], "the backoff did not widen"


async def test_the_backoff_is_bounded(daemon: Daemon, tv: FakeTv, publish, settings):
    publish(["w1"])
    tv.unavailable = True

    waits = [await daemon.tick() for _ in range(12)]

    assert max(waits) == settings.tv_retry_max_seconds


async def test_recovery_is_logged_and_resets_the_backoff(daemon: Daemon, tv: FakeTv, publish, settings, caplog):
    """The pair of lines is what gives an outage a length in the journal."""
    publish(["w1"])
    tv.unavailable = True
    await daemon.tick()
    await daemon.tick()

    tv.unavailable = False
    with caplog.at_level(logging.INFO):
        await daemon.tick()

    assert "tv.recovered" in {r.__dict__.get("event") for r in caplog.records}
    tv.unavailable = True
    assert await daemon.tick() == settings.tv_retry_min_seconds


async def test_the_wall_is_shown_as_soon_as_the_set_comes_back(daemon: Daemon, tv: FakeTv, publish):
    publish(["w1", "w2"])
    tv.unavailable = True
    await daemon.tick()
    assert tv.selected == []

    tv.unavailable = False
    await daemon.tick()

    assert tv.on_the_wall.name == "w1.jpg"


async def test_a_manifest_published_while_the_set_is_asleep_is_still_adopted(
    daemon: Daemon, tv: FakeTv, publish, state: DisplayState
):
    """The manifest is local file I/O and cannot fail on account of the television.

    A set that is asleep must not stop this plane from *knowing* what it will show
    when the set comes back — otherwise a theme switched at midnight is lost.
    """
    publish(["w1"])
    tv.unavailable = True
    await daemon.tick()

    publish(["w2"], sequence=1)
    await daemon.tick()

    tv.unavailable = False
    await daemon.tick()

    assert tv.on_the_wall.name == "w2.jpg"
