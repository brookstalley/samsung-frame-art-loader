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


async def test_recovery_is_logged_and_resets_the_backoff(daemon: Daemon, tv: FakeTv, publish, settings, clock, caplog):
    """The pair of lines is what gives an outage a length in the journal."""
    publish(["w1", "w2"], interval_seconds=10)
    tv.unavailable = True
    await daemon.tick()
    await daemon.tick()

    tv.unavailable = False
    with caplog.at_level(logging.INFO):
        await daemon.tick()

    assert "tv.recovered" in {r.__dict__.get("event") for r in caplog.records}

    # The clock has to move for the *next* failure to happen at all: the backoff
    # is only observable through a pass that has something to say to the set, and
    # the test below is why that is not a wrinkle in this test.
    tv.unavailable = True
    clock.advance(10)
    assert await daemon.tick() == settings.tv_retry_min_seconds


async def test_a_daemon_with_nothing_to_say_does_not_discover_the_set_is_gone(
    daemon: Daemon, tv: FakeTv, publish, settings, clock
):
    """And that is right, not a gap.

    Between rotations there is no call to make: the manifest has not changed, the
    directive has not advanced, the theme is fully uploaded, and the wall is
    holding a picture the television owns. A liveness poll would be traffic bought
    to learn something nothing is waiting on — and the outage is discovered by the
    next pass that actually needs the set, which is the pass that could not have
    proceeded anyway.
    """
    publish(["w1", "w2"], interval_seconds=1000)
    await daemon.tick()
    for _ in range(3):
        await daemon.tick()
    calls_before = tv.connects

    tv.unavailable = True
    waits = [await daemon.tick() for _ in range(5)]

    assert waits == [settings.poll_interval_seconds] * 5, "an idle pass went to the television to check on it"
    assert tv.connects == calls_before


async def test_the_wall_is_shown_as_soon_as_the_set_comes_back(daemon: Daemon, tv: FakeTv, publish):
    publish(["w1", "w2"])
    tv.unavailable = True
    await daemon.tick()
    assert tv.selected == []

    tv.unavailable = False
    await daemon.tick()

    assert tv.on_the_wall.name == "w1.jpg"


async def test_orphan_removal_owed_during_an_outage_happens_when_the_set_returns(
    daemon: Daemon, tv: FakeTv, publish, state: DisplayState
):
    """The declared deliverable, on the path it is most likely to be needed.

    Removing what the binding table cannot account for was reachable from exactly
    one place — the tick a manifest is first seen on — and the watcher reports a
    manifest once. A set asleep on that tick aborted the pass and the work was
    never attempted again, so on a fresh install the legacy uploads the chunk
    exists to clear would have stayed on the television for ever. Owing the work
    until it is done, rather than attempting it when the news arrives, is the fix.
    """
    from pathlib import Path

    tv.holding["MY-LEGACY-1"] = Path("/gone/legacy-1.jpg")
    tv.unavailable = True
    publish(["w1"])

    await daemon.tick()
    assert "MY-LEGACY-1" in tv.holding, "the fake let a call through while unavailable"

    tv.unavailable = False
    await daemon.tick()

    assert "MY-LEGACY-1" not in tv.holding, "orphan removal was dropped rather than deferred"


async def test_a_reconciliation_interrupted_halfway_is_still_owed(daemon: Daemon, tv: FakeTv, publish, clock, settings):
    """Cleared on the far side of the call, so a set that goes away during it does
    not leave the work recorded as done — and retried on a wait, not on every poll.

    The wait matters as much as the owing: an unconfirmable removal left owed and
    ungated would ask the set again every second, which is the unbounded cadence
    this loop guards against twice elsewhere.
    """
    from pathlib import Path

    tv.holding["MY-LEGACY-1"] = Path("/gone/legacy-1.jpg")
    tv.removal_unconfirmable = True
    publish(["w1"])
    await daemon.tick()
    assert "MY-LEGACY-1" in tv.holding

    tv.unavailable = True
    await daemon.tick()
    tv.unavailable = False
    tv.removal_unconfirmable = False

    removals_before = len(tv.removed)
    await daemon.tick()
    assert len(tv.removed) == removals_before, "an unconfirmable removal was retried on the very next poll"

    clock.advance(settings.tv_retry_max_seconds)
    await daemon.tick()

    assert "MY-LEGACY-1" not in tv.holding


async def test_a_removal_the_set_refuses_settles_instead_of_being_asked_for_ever(
    daemon: Daemon, tv: FakeTv, publish, clock, settings
):
    """A *known* refusal is an answer, and asking again learns nothing.

    The distinction this pins is between two outcomes that both fail to remove
    anything. When the set answers and keeps the image, the state of the world is
    established — it is already reported at WARNING by the client — so
    reconciliation is done and the next manifest re-arms it. When nobody could
    establish what the set holds, the work stays owed and is retried on a wait.

    Written because the previous commit changed this line from `outcome.complete`
    to `True` with nothing exercising it: the whole suite passed with the old value
    restored, because no test had ever produced a removal the set survived.
    """
    from pathlib import Path

    tv.holding["MY-STUBBORN"] = Path("/gone/stubborn.jpg")
    tv.unremovable = {"MY-STUBBORN"}
    publish(["w1"])

    await daemon.tick()
    assert "MY-STUBBORN" in tv.holding, "the fake removed an image it was told to keep"
    asked = len(tv.removed)

    clock.advance(settings.tv_retry_max_seconds + 1)
    for _ in range(3):
        await daemon.tick()

    assert len(tv.removed) == asked, "an answered refusal was re-asked; that outcome was already established"


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
