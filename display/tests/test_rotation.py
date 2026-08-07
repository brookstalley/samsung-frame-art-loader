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
# the call: nothing above the seam can infer it, and the set's silence — no
# `image_selected` announcement — is the only thing that distinguishes it from a
# rotation that worked.


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
    against a set that displays none of them — forty selects per interval, each
    waiting out the whole confirmation window, with the entire rotation order
    consumed against a television showing nothing.
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
    # Art mode stays *on*: a set that says it is showing art and then does not
    # change is the only route left to this branch, now that a set reporting art
    # mode off is never asked to select at all.
    tv.displays_nothing_selected = True

    with caplog.at_level(logging.INFO):
        for _ in range(6):
            await daemon.tick()
            clock.advance(10)

    reports = [r for r in caplog.records if getattr(r, "event", None) == "rotation.wall_unchanged"]
    assert len(reports) == 1, f"the still wall was reported {len(reports)} times"
    assert reports[0].art_mode == "on", "the one line an operator reads does not say what the set claims about itself"


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


async def test_a_set_that_says_it_took_the_image_and_is_not_showing_it_is_believed(daemon: Daemon, tv: FakeTv, publish, caplog):
    """The set has two ways of not moving the wall, and both mean the same thing.

    It can stay silent, which is the dark panel, or it can announce the selection
    while saying `is_shown: "No"`. The second is the one a daemon that merely
    counted announcements would get wrong, reporting a rotation from the set's own
    word that it had not performed one.
    """
    publish(["w1", "w2"])
    tv.admits_not_showing = {"MY-F0001"}

    with caplog.at_level(logging.INFO):
        await daemon.tick()

    assert tv.selected, "the daemon never asked the set to show anything"
    assert not [
        r for r in caplog.records if getattr(r, "event", None) == "rotation.selected"
    ], "the set said it was not showing the image and the daemon reported it as shown"
    assert [r for r in caplog.records if getattr(r, "event", None) == "rotation.wall_unchanged"]


# -- the television belongs to whoever is using it -----------------------------
#
# Measured on a real set on 2026-08-07, with the operator watching a programme: a
# due rotation sent `select_image`, the set **switched itself into art mode**, and
# the picture they were watching was gone. It is not a polite refusal like the
# dark state's, and somebody watching television is a daily event rather than an
# edge case. So nothing reaches the wall unless the set says it is showing art —
# and `get_artmode` is what says so, reading `off` for both a dark panel and a
# programme, and `on` only for art mode.


async def test_a_television_somebody_is_watching_is_left_alone(daemon: Daemon, tv: FakeTv, publish, caplog):
    publish(["w1", "w2"])
    tv.art_mode = "off"

    with caplog.at_level(logging.INFO):
        await daemon.tick()

    assert tv.selected == [], "the daemon took the screen off whoever was watching"
    assert [r for r in caplog.records if getattr(r, "event", None) == "rotation.wall_not_ours"]


async def test_the_theme_does_not_advance_while_the_set_is_somebody_else_s(daemon: Daemon, tv: FakeTv, publish, clock):
    """The place is kept, not consumed.

    An evening of television would otherwise walk the whole theme against a wall
    nobody could see, and the first picture of the morning would be wherever that
    happened to land.
    """
    publish(["w1", "w2", "w3", "w4"], interval_seconds=10)
    tv.art_mode = "off"

    for _ in range(4):
        await daemon.tick()
        clock.advance(10)

    tv.art_mode = "on"
    await daemon.tick()

    assert tv.on_the_wall.name == "w1.jpg", "an evening of television walked the theme forward"


async def test_the_wall_comes_back_the_moment_the_set_announces_art_mode(daemon: Daemon, tv: FakeTv, publish, clock, caplog):
    """Recovery is by the set's own announcement, not by waiting out the backoff.

    Without this, switching off a programme would leave the wall blank for the
    remainder of a wait that has doubled its way up to five minutes — and unlike
    a panel left dark overnight, this transition happens every time somebody
    finishes watching something.
    """
    # **A long interval and a short pause, deliberately.** With the two equal, a
    # daemon that wrongly spent the interval while the wall was not its own would
    # still look right here — the elapsed time would have covered the loss
    # exactly. That arithmetic-agrees-with-the-bug shape is what a sweep catches
    # and a reading does not, and it caught this test.
    publish(["w1", "w2"], interval_seconds=180)
    tv.art_mode = "off"
    for _ in range(6):
        await daemon.tick()
        clock.advance(5)
    assert tv.selected == []

    # The set says it has changed, and the clock barely moves: the point is that
    # none of the remaining wait — neither the backoff nor the rotation interval —
    # has to elapse before the picture comes back.
    tv.art_mode = "on"
    tv.art_mode_announced = True
    with caplog.at_level(logging.INFO):
        await daemon.tick()

    assert tv.on_the_wall.name == "w1.jpg", "the wall waited out a backoff the set had already ended"
    assert [r for r in caplog.records if getattr(r, "event", None) == "rotation.wall_returned"]


async def test_it_says_the_wall_is_not_ours_once_not_once_a_rotation(daemon: Daemon, tv: FakeTv, publish, clock, caplog):
    """Somebody watches television for hours. A line per attempt would bury the
    ERRORs that are this plane's only failure channel."""
    publish(["w1", "w2"], interval_seconds=10)
    tv.art_mode = "off"

    with caplog.at_level(logging.INFO):
        for _ in range(6):
            await daemon.tick()
            clock.advance(10)

    reports = [r for r in caplog.records if getattr(r, "event", None) == "rotation.wall_not_ours"]
    assert len(reports) == 1, f"a television in use was reported {len(reports)} times"


async def test_asking_whether_the_wall_is_ours_is_not_done_once_a_second(daemon: Daemon, tv: FakeTv, publish, clock):
    """The check costs a request, and the poll interval is one second.

    Backing off is what makes a gate on every rotation affordable; without it an
    evening of television is tens of thousands of round trips at the set.
    """
    publish(["w1", "w2"], interval_seconds=10)
    tv.art_mode = "off"

    for _ in range(30):
        await daemon.tick()
        clock.advance(1)

    assert tv.art_mode_reads < 10, f"the set was asked {tv.art_mode_reads} times in thirty seconds"


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


async def test_the_rotation_timer_does_not_re_ask_a_wall_the_backoff_is_holding_off(daemon: Daemon, tv: FakeTv, publish, clock):
    """The other half of the wait, and the half that bites in the deployment.

    The two timers are independent: rotation comes due on the manifest's interval,
    the wall's wait on a ladder that doubles to five minutes. Once the ladder is
    longer than the interval — which is the shipped case, 300 against 180 — every
    rotation in between would ask a television already known to be ignoring
    selections, which is the flood the ladder exists to stop.
    """
    publish(["w1", "w2"], interval_seconds=1)
    tv.displays_nothing_selected = True

    await daemon.tick()  # attempt, then wait 5
    clock.advance(5)
    await daemon.tick()  # attempt, then wait 10
    attempts = len(tv.selected)
    assert attempts == 2, "the ladder did not let the second attempt through"

    # Rotation is due on every one of these; the wall's wait is not up until t=15.
    for _ in range(9):
        clock.advance(1)
        await daemon.tick()

    assert len(tv.selected) == attempts, "the rotation timer asked a wall the backoff was holding off"
