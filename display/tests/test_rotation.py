"""Host-driven rotation: the timer is this product's, and so is the order.

The television's own slideshow can only be scoped to a whole category — no
content-id list, no album, no playlist — so it cannot be made to show a theme.
Rotation is therefore a local timer calling `select_image`, and the set's
slideshow is switched off once so the two cannot fight.
"""

import logging
import random
from dataclasses import replace

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


async def test_a_theme_that_can_show_nothing_warns_once_an_interval_not_once_a_second(
    daemon: Daemon, tv: FakeTv, publish, clock, caplog
):
    """The other half of "does not spin", and the half that bites in production.

    Bounding one pass is not enough: the *timer* has to arm too. It was stamped
    only on a successful selection, so a theme that could show nothing looked like
    a process that had just started on every tick — forty works with a pruned
    image tree emitting forty WARNINGs a second, indefinitely. journald then
    rate-limits and starts dropping lines, and the ones it drops are the ERRORs
    that are this plane's only failure channel.
    """
    publish(["w1", "w2", "w3"], interval_seconds=60, renders=False)

    with caplog.at_level(logging.WARNING):
        for _ in range(10):
            await daemon.tick()
            clock.advance(1)

    missing = [r for r in caplog.records if r.__dict__.get("event") == "rotation.render_missing"]
    assert len(missing) == 3, "the whole theme was walked again on every poll"

    with caplog.at_level(logging.WARNING):
        clock.advance(60)
        await daemon.tick()

    assert len([r for r in caplog.records if r.__dict__.get("event") == "rotation.render_missing"]) == 6


async def test_a_new_manifest_is_tried_at_once_rather_than_waiting_out_the_interval(
    daemon: Daemon, tv: FakeTv, publish, art_root, clock
):
    """So a wall with nothing to show recovers when the renders arrive.

    Renders appearing normally comes with curation republishing, and making the
    wall sit out three minutes it has no reason to would be the timer above
    over-applied.
    """
    publish(["w1"], interval_seconds=180, renders=False)
    await daemon.tick()
    assert tv.selected == []

    (art_root / "ready" / "w1.jpg").write_bytes(b"a render, at last")
    publish(["w1"], sequence=1, interval_seconds=180)
    await daemon.tick()

    assert tv.on_the_wall.name == "w1.jpg"


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


# -- a television that takes selections and displays none of them --------------
#
# Observed on a real set on 2026-08-07 with its panel dark: `select_image`
# returned, raised nothing and emitted none of the three art-mode events, while
# what the set displayed did not change across repeated attempts over twelve
# seconds. Every call a daemon can make succeeded; the only thing that failed was
# the picture changing. These tests exist because the failure is invisible from
# the call, so nothing above the seam can infer it — it has to be read back.


async def test_a_selection_the_set_does_not_display_is_not_reported_as_shown(
    daemon: Daemon, tv: FakeTv, state: DisplayState, publish, caplog
):
    publish(["w1", "w2"])
    tv.displays_nothing_selected = True

    with caplog.at_level(logging.INFO):
        await daemon.tick()

    assert tv.selected, "the daemon never asked the set to show anything"
    assert tv.on_the_wall is None, "the fake put a picture up that the set never displayed"
    assert not [
        r for r in caplog.records if getattr(r, "event", None) == "rotation.selected"
    ], "the daemon reported a rotation the television did not perform"
    assert (
        state.last_selected_work_id is None
    ), "a work never displayed was recorded as the one on the wall, so a restart would re-show it"


async def test_a_wall_that_displays_nothing_ends_the_pass_rather_than_walking_the_theme(daemon: Daemon, tv: FakeTv, publish):
    """A missing render means try the next work; a dark wall means try no work.

    They were one boolean, and every remaining work would have been attempted
    against a set that displays none of them — forty selects and forty confirming
    reads per interval, with the whole rotation order consumed against a
    television showing nothing.
    """
    publish(["w1", "w2", "w3", "w4"])
    tv.displays_nothing_selected = True

    await daemon.tick()

    assert len(tv.selected) == 1, f"the pass tried {len(tv.selected)} works against a wall that displays none"


async def test_it_says_the_wall_is_not_changing_once_not_once_a_rotation(daemon: Daemon, tv: FakeTv, publish, clock, caplog):
    """A panel stays dark for hours. One line per rotation is a hundred a night
    saying the one thing that has not changed, and journald drops what it
    rate-limits — which would be the ERRORs this plane's only failure channel
    carries."""
    publish(["w1", "w2"], interval_seconds=10)
    tv.displays_nothing_selected = True
    tv.art_mode = "off"

    with caplog.at_level(logging.INFO):
        for _ in range(6):
            await daemon.tick()
            clock.advance(10)

    reports = [r for r in caplog.records if getattr(r, "event", None) == "rotation.wall_unchanged"]
    assert len(reports) == 1, f"the dark wall was reported {len(reports)} times"
    assert reports[0].art_mode == "off", "the one line an operator reads does not say why the wall is not changing"


async def test_the_wall_coming_back_is_reported_and_rotation_resumes(daemon: Daemon, tv: FakeTv, publish, clock, caplog):
    publish(["w1", "w2"], interval_seconds=10)
    tv.displays_nothing_selected = True
    await daemon.tick()

    with caplog.at_level(logging.INFO):
        tv.displays_nothing_selected = False
        clock.advance(10)
        await daemon.tick()

    assert tv.on_the_wall is not None, "rotation did not resume when the set started displaying again"
    assert [
        r for r in caplog.records if getattr(r, "event", None) == "rotation.wall_recovered"
    ], "the wall came back and nothing said so, so the WARNING above it stands unresolved in the log"


async def test_a_deferred_work_is_the_one_that_appears_when_the_wall_comes_back(daemon: Daemon, tv: FakeTv, publish, clock):
    """The place is given back rather than consumed. A television that displayed
    nothing has not shown that work, so the wall coming back should show it —
    not the one after it."""
    # Four works and two dark passes, chosen so that a cursor which *was*
    # consumed lands somewhere else. Three of each made the theme wrap exactly
    # back to the right answer, and the test passed with the restore deleted — a
    # mutation sweep is what caught it.
    publish(["w1", "w2", "w3", "w4"], interval_seconds=10)
    tv.displays_nothing_selected = True

    for _ in range(2):
        await daemon.tick()
        clock.advance(10)

    tv.displays_nothing_selected = False
    await daemon.tick()

    assert tv.on_the_wall.name == "w1.jpg", "an evening of a dark panel walked the theme forward"


async def test_a_set_that_will_not_say_what_it_displays_is_taken_at_its_word(daemon: Daemon, tv: FakeTv, publish, caplog):
    """Silence is not disagreement. Treating an unanswered question as a failure
    would stop rotation on a working television, and an incomplete wall beats a
    dark one."""
    publish(["w1", "w2"])
    tv.will_not_say_what_it_displays = True

    with caplog.at_level(logging.INFO):
        await daemon.tick()

    assert [
        r for r in caplog.records if getattr(r, "event", None) == "rotation.selected"
    ], "rotation stopped because the set declined to describe its own display"
    assert not [r for r in caplog.records if getattr(r, "event", None) == "rotation.wall_unchanged"]


async def test_a_set_that_agrees_late_is_confirmed_rather_than_failed(settings, tv: FakeTv, state: DisplayState, clock, publish):
    """A real set acknowledges a selection about two seconds after the request,
    so a single immediate read would report every successful rotation as a
    failure. This is the one test that exercises the window's duration."""
    publish(["w1", "w2"])
    settings = replace(settings, select_confirm_seconds=2.0)
    watcher = Watcher(settings.manifest_path, rotation_interval_fallback=180, shuffle_fallback=False)
    daemon = Daemon(settings=settings, tv=tv, state=state, watcher=watcher, clock=clock.as_clock())

    tv.answer_after_reads = 2
    await daemon.tick()

    assert tv.on_the_wall.name == "w1.jpg", "a set that took a moment to agree was called a failure"


async def test_the_backoff_starts_over_once_the_set_behaves_again(daemon: Daemon, tv: FakeTv, publish, clock):
    """Otherwise unrelated dark spells compound.

    The wait doubles while the set ignores selections, which is right for one
    evening with the panel off. Carrying the grown wait past a recovery would
    mean the third brief spell in a week backing off five minutes — a wall that
    takes longer and longer to come back for no reason anyone could observe.
    """
    publish(["w1", "w2"], interval_seconds=1)
    tv.displays_nothing_selected = True

    await daemon.tick()  # attempt, then wait 5
    clock.advance(5)
    await daemon.tick()  # attempt, then wait 10

    tv.displays_nothing_selected = False
    clock.advance(10)
    await daemon.tick()
    assert tv.on_the_wall is not None, "the set started behaving and the wall did not come back"

    tv.displays_nothing_selected = True
    clock.advance(1)
    await daemon.tick()  # attempt, and the wait must be the floor again
    attempts = len(tv.selected)

    clock.advance(5)
    await daemon.tick()

    assert len(tv.selected) > attempts, "the wait carried its grown value across a recovery"
