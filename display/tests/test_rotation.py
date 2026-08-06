"""Host-driven rotation: the timer is this product's, and so is the order.

The television's own slideshow can only be scoped to a whole category — no
content-id list, no album, no playlist — so it cannot be made to show a theme.
Rotation is therefore a local timer calling `select_image`, and the set's
slideshow is switched off once so the two cannot fight.
"""

import logging
import random

from fakes import FakeTv

from display.daemon import Daemon
from display.manifest import Watcher
from display.state import DisplayState


async def test_it_shows_the_first_work_immediately(daemon: Daemon, tv: FakeTv, publish):
    publish(["w1", "w2"])

    await daemon.tick()

    assert tv.on_the_wall.name == "w1.jpg"


async def test_it_holds_a_work_for_the_manifest_s_interval(daemon: Daemon, tv: FakeTv, publish, clock):
    publish(["w1", "w2"], interval_seconds=180)
    await daemon.tick()

    clock.advance(179)
    await daemon.tick()
    assert len(tv.selected) == 1, "the wall moved before the interval was up"

    clock.advance(1)
    await daemon.tick()
    assert tv.on_the_wall.name == "w2.jpg"


async def test_the_rotation_wraps(daemon: Daemon, tv: FakeTv, publish, clock):
    publish(["w1", "w2"], interval_seconds=10)
    await daemon.tick()

    for _ in range(2):
        clock.advance(10)
        await daemon.tick()

    assert [path.name for path in (tv.holding[c] for c in tv.selected)] == ["w1.jpg", "w2.jpg", "w1.jpg"]


async def test_the_native_slideshow_is_disabled_once_and_survives_a_restart(
    settings, tv: FakeTv, state: DisplayState, clock, publish
):
    """Persisted rather than held in memory, because `Restart=always` makes
    restarts routine and the call is only correct to make once."""

    def a_daemon() -> Daemon:
        watcher = Watcher(settings.manifest_path, rotation_interval_fallback=180, shuffle_fallback=False)
        return Daemon(settings=settings, tv=tv, state=state, watcher=watcher, clock=clock.as_clock())

    publish(["w1"])
    first = a_daemon()
    await first.tick()
    await first.tick()
    assert tv.slideshow_disabled == 1

    await a_daemon().tick()

    assert tv.slideshow_disabled == 1


async def test_a_work_whose_render_is_missing_is_skipped_and_the_rotation_continues(
    daemon: Daemon, tv: FakeTv, publish, art_root, clock, caplog
):
    """Fatal-for-one-item. The wall going black is always worse than the wall
    being incomplete."""
    publish(["w1", "w2", "w3"], interval_seconds=10)
    (art_root / "ready" / "w2.jpg").unlink()
    await daemon.tick()

    clock.advance(10)
    with caplog.at_level(logging.WARNING):
        await daemon.tick()

    assert tv.on_the_wall.name == "w3.jpg", "the missing render stopped the rotation instead of being skipped"
    assert [r.__dict__.get("event") for r in caplog.records].count("rotation.render_missing") == 1


async def test_a_theme_whose_every_render_is_missing_does_not_spin(daemon: Daemon, tv: FakeTv, publish, art_root, caplog):
    """Bounded by the length of the list: a loop that can never succeed must end,
    or one pass never returns and the poll interval stops meaning anything."""
    publish(["w1", "w2"], renders=False)

    with caplog.at_level(logging.WARNING):
        await daemon.tick()

    assert tv.selected == []
    assert [r.__dict__.get("event") for r in caplog.records].count("rotation.render_missing") == 2


async def test_a_restart_keeps_the_picture_and_then_carries_on_from_it(settings, tv: FakeTv, state: DisplayState, clock, publish):
    """A restart must not lose its place — and must not move the wall either.

    `Restart=always` makes restarts routine, so a daemon that advanced on start
    would turn a crash loop into a strobing wall. Re-selecting what is already
    showing is idempotent and invisible; the place is kept because the *next*
    step is the work after it.
    """

    def a_daemon() -> Daemon:
        watcher = Watcher(settings.manifest_path, rotation_interval_fallback=180, shuffle_fallback=False)
        return Daemon(settings=settings, tv=tv, state=state, watcher=watcher, clock=clock.as_clock())

    publish(["w1", "w2", "w3"], interval_seconds=10)
    first = a_daemon()
    await first.tick()
    clock.advance(10)
    await first.tick()
    assert tv.on_the_wall.name == "w2.jpg"

    restarted = a_daemon()
    await restarted.tick()
    assert tv.on_the_wall.name == "w2.jpg", "the restart moved the wall"

    clock.advance(10)
    await restarted.tick()
    assert tv.on_the_wall.name == "w3.jpg", "the restart lost its place in the rotation"


async def test_repeated_restarts_do_not_walk_the_rotation_forward(settings, tv: FakeTv, state: DisplayState, clock, publish):
    """The crash-loop case stated on its own, because it is the one that is ugly
    in the room rather than merely wrong in the store."""

    def a_daemon() -> Daemon:
        watcher = Watcher(settings.manifest_path, rotation_interval_fallback=180, shuffle_fallback=False)
        return Daemon(settings=settings, tv=tv, state=state, watcher=watcher, clock=clock.as_clock())

    publish(["w1", "w2", "w3"], interval_seconds=180)
    await a_daemon().tick()

    for _ in range(10):
        await a_daemon().tick()

    assert {path.name for path in (tv.holding[c] for c in tv.selected)} == {"w1.jpg"}


async def test_a_sync_mid_interval_does_not_hand_the_current_work_a_second_turn(daemon: Daemon, tv: FakeTv, publish, clock):
    """The other half of the rule above: a running process holding its place must
    carry on past the current work when the manifest is rewritten under it."""
    publish(["w1", "w2", "w3"], interval_seconds=100)
    await daemon.tick()
    assert tv.on_the_wall.name == "w1.jpg"

    clock.advance(50)
    publish(["w1", "w2", "w3"], sequence=1, interval_seconds=100)  # a `sync` rewrite
    await daemon.tick()

    clock.advance(50)
    await daemon.tick()

    assert tv.on_the_wall.name == "w2.jpg", "a catalogue edit gave the current work a second interval"


async def test_shuffle_uses_every_work_before_repeating_one(settings, tv: FakeTv, state: DisplayState, clock, publish):
    """A shuffle that can show the same work twice before showing another reads as
    a broken shuffle to the household, whatever the mathematics says."""
    works = [f"w{n}" for n in range(8)]
    publish(works, interval_seconds=10, shuffle=True)
    watcher = Watcher(settings.manifest_path, rotation_interval_fallback=180, shuffle_fallback=False)
    daemon = Daemon(settings=settings, tv=tv, state=state, watcher=watcher, clock=clock.as_clock(), rng=random.Random(1234))

    await daemon.tick()
    for _ in range(len(works) - 1):
        clock.advance(10)
        await daemon.tick()

    shown = [tv.holding[content_id].stem for content_id in tv.selected]
    assert sorted(shown) == sorted(works)


async def test_shuffle_reorders_on_each_pass(settings, tv: FakeTv, state: DisplayState, clock, publish):
    """Shuffling once and keeping the order gives the household the same
    "random" sequence every day."""
    works = [f"w{n}" for n in range(6)]
    publish(works, interval_seconds=10, shuffle=True)
    watcher = Watcher(settings.manifest_path, rotation_interval_fallback=180, shuffle_fallback=False)
    daemon = Daemon(settings=settings, tv=tv, state=state, watcher=watcher, clock=clock.as_clock(), rng=random.Random(7))

    await daemon.tick()
    for _ in range(len(works) * 2 - 1):
        clock.advance(10)
        await daemon.tick()

    shown = [tv.holding[content_id].stem for content_id in tv.selected]
    assert sorted(shown[: len(works)]) == sorted(works)
    assert sorted(shown[len(works) :]) == sorted(works)
    assert shown[: len(works)] != shown[len(works) :], "the second pass repeated the first pass's order"
