"""Interactive commands, which ride the manifest rather than a channel of their own.

The three semantics that do not follow from "it is a state file" are the three
tested hardest here: a restart must not re-execute the last jump, rapid commands
coalesce to one step, and a sequence that goes backwards is a restored catalogue
rather than an instruction.
"""

import logging

import pytest
from fakes import FakeTv

from display.daemon import Daemon
from display.state import DisplayState


async def test_a_first_start_adopts_the_sequence_without_acting(daemon: Daemon, tv: FakeTv, publish, state: DisplayState):
    """A device that has never acted takes what it finds as its baseline.

    Acting instead would execute, at install time, whatever `show_now` somebody
    issued last week — and `Restart=always` means "install time" happens often.
    """
    publish(["w1", "w2", "w3"], sequence=42, pinned_work_id="w3")

    await daemon.tick()

    assert state.last_acted_sequence == 42
    # Rotation still starts: baselining suppresses the *directive*, not the wall.
    assert len(tv.selected) == 1
    assert tv.on_the_wall.name == "w1.jpg"


async def test_a_restart_does_not_re_execute_the_last_directive(
    settings, tv: FakeTv, state: DisplayState, clock, publish, caplog
):
    """The whole reason the sequence is persisted, tested end to end.

    The first daemon acts on the jump; a second one, built over the same store
    against the same unchanged manifest, must not act on it again.

    Asserted on the directive rather than on how many `select_image` calls were
    made, because a restart legitimately re-selects the work already on the wall —
    see the rotation suite. What must not happen is the *directive* firing twice.
    """
    from display.manifest import Watcher

    def a_daemon() -> Daemon:
        watcher = Watcher(settings.manifest_path, rotation_interval_fallback=180, shuffle_fallback=False)
        return Daemon(settings=settings, tv=tv, state=state, watcher=watcher, clock=clock.as_clock())

    publish(["w1", "w2", "w3"], sequence=1)
    first = a_daemon()
    await first.tick()  # baselines at 1, shows w1

    publish(["w1", "w2", "w3"], sequence=2, pinned_work_id="w3")
    await first.tick()
    assert tv.on_the_wall.name == "w3.jpg"

    restarted = a_daemon()
    with caplog.at_level(logging.INFO):
        await restarted.tick()

    acted = [r for r in caplog.records if r.__dict__.get("event") == "directive.acted"]
    assert acted == [], "the restarted daemon executed a directive it had already acted on"
    assert state.last_acted_sequence == 2
    assert tv.on_the_wall.name == "w3.jpg", "the restart moved the wall"


async def test_rapid_directives_coalesce_into_one_step(daemon: Daemon, tv: FakeTv, publish):
    """Two `next` calls inside one poll interval advance the counter twice and are
    observed once, which is one step — the intended behaviour, not an approximation."""
    publish(["w1", "w2", "w3"], sequence=1)
    await daemon.tick()
    assert tv.on_the_wall.name == "w1.jpg"

    publish(["w1", "w2", "w3"], sequence=3)  # two `next` calls, one poll
    await daemon.tick()

    assert tv.on_the_wall.name == "w2.jpg"
    assert len(tv.selected) == 2


async def test_a_sequence_that_goes_backwards_re_baselines_without_acting(
    daemon: Daemon, tv: FakeTv, publish, state: DisplayState, caplog
):
    """A restored catalogue brings back an older counter. Replaying the pin it
    carried is exactly what this rule exists to prevent."""
    publish(["w1", "w2", "w3"], sequence=10)
    await daemon.tick()
    selections = len(tv.selected)

    publish(["w1", "w2", "w3"], sequence=4, pinned_work_id="w3")
    with caplog.at_level(logging.WARNING):
        await daemon.tick()

    assert len(tv.selected) == selections, "a regression was treated as a directive"
    assert state.last_acted_sequence == 4, "the older sequence was not adopted as the new baseline"
    assert [r.__dict__.get("event") for r in caplog.records].count("directive.regressed") == 1


async def test_after_a_regression_the_next_advance_is_acted_on(daemon: Daemon, tv: FakeTv, publish):
    """Re-baselining has to leave the mechanism armed, or one restore disables
    `next` until the counter climbs back past where it was."""
    publish(["w1", "w2"], sequence=10)
    await daemon.tick()
    publish(["w1", "w2"], sequence=4)
    await daemon.tick()

    publish(["w1", "w2"], sequence=5)
    await daemon.tick()

    assert tv.on_the_wall.name == "w2.jpg"


async def test_a_pin_the_theme_does_not_carry_warns_and_keeps_rotating(
    daemon: Daemon, tv: FakeTv, publish, caplog, state: DisplayState
):
    """`show_now` checks readiness, not theme membership, so this is the default
    path rather than a rare race: only this plane can decide what to do with a pin
    it cannot resolve, and stalling the wall is not it."""
    publish(["w1", "w2"], sequence=1)
    await daemon.tick()

    publish(["w1", "w2"], sequence=2, pinned_work_id="a-work-in-another-theme")
    with caplog.at_level(logging.WARNING):
        await daemon.tick()

    assert [r.__dict__.get("event") for r in caplog.records].count("directive.pin_unresolvable") == 1
    assert state.last_acted_sequence == 2, "an unresolvable pin must be consumed, or it warns every second"
    assert tv.on_the_wall.name == "w1.jpg", "the wall moved for a pin that could not be resolved"


async def test_a_pin_continues_the_rotation_from_the_pinned_work(daemon: Daemon, tv: FakeTv, publish, clock):
    publish(["w1", "w2", "w3", "w4"], sequence=1, interval_seconds=180)
    await daemon.tick()

    publish(["w1", "w2", "w3", "w4"], sequence=2, pinned_work_id="w3")
    await daemon.tick()
    assert tv.on_the_wall.name == "w3.jpg"

    clock.advance(180)
    await daemon.tick()

    assert tv.on_the_wall.name == "w4.jpg", "rotation did not continue from the pin"


async def test_a_directive_is_not_consumed_while_the_television_is_asleep(
    daemon: Daemon, tv: FakeTv, publish, state: DisplayState
):
    """An outage must delay a jump, never eat it.

    The manifest does not change when a directive fails, so a sequence marked
    acted-on during an outage is a `show_now` the curator never gets — nothing
    would ever present it again.
    """
    publish(["w1", "w2", "w3"], sequence=1)
    await daemon.tick()

    tv.unavailable = True
    publish(["w1", "w2", "w3"], sequence=2, pinned_work_id="w3")
    await daemon.tick()
    assert state.last_acted_sequence == 1, "the directive was consumed against a television that never heard it"

    tv.unavailable = False
    await daemon.tick()

    assert tv.on_the_wall.name == "w3.jpg"
    assert state.last_acted_sequence == 2


async def test_a_next_is_not_consumed_when_the_set_drops_mid_step(daemon: Daemon, tv: FakeTv, publish, state: DisplayState):
    """The unpinned branch's version of the rule, in the only window it can bite.

    **Finding this window took two attempts and a mutation sweep**, and the shape
    of it is worth keeping. A directive always arrives on a manifest rewrite, and
    a rewrite is an adoption, and an adoption reconciles with the set *before* the
    directive is looked at — so a television that is already asleep fails there and
    the directive is simply not reached, surviving for free on the pass after the
    set comes back.

    What is left is the genuine race: the set answers at the top of the pass and is
    gone by the selection. That is what this reproduces, and it is the only thing
    the statement order in `_act_on_directive` protects. A sweep that swapped those
    two statements survived two earlier tests written against an already-asleep
    set, both of which passed because the code under test never ran.
    """
    publish(["w1", "w2", "w3"], sequence=1)
    await daemon.tick()
    assert tv.on_the_wall.name == "w1.jpg"
    doomed = state.binding_for("w2").tv_content_id

    # The set still lists the image and refuses to show it: alive at the top of
    # the pass, gone by the selection.
    tv.refuse_selection_of.add(doomed)
    publish(["w1", "w2", "w3"], sequence=2)
    await daemon.tick()
    assert state.last_acted_sequence == 1, "the step was consumed against a television that never performed it"

    tv.refuse_selection_of.clear()
    await daemon.tick()

    # **It lands on w3, not w2, and that is the design rather than a near miss.**
    # The cursor moves past a work before it is shown, so one whose selection
    # failed is stepped over exactly as a missing render is — the alternative is a
    # `next` that keeps returning to the work that just would not display. What
    # the rule protects is that the step *happens at all*: with the sequence
    # consumed before the attempt, the wall would still be on w1.
    assert tv.on_the_wall.name == "w3.jpg", "the directive was lost to a momentary drop"
    assert state.last_acted_sequence == 2


async def test_a_pin_whose_render_is_missing_is_still_consumed(
    daemon: Daemon, tv: FakeTv, publish, state: DisplayState, art_root
):
    """An attempt that completes and shows nothing is still an attempt.

    Distinct from the outage above: this one will not change until a file
    appears, so retrying it every second fills the journal to no purpose.
    """
    publish(["w1", "w2"], sequence=1)
    await daemon.tick()
    (art_root / "ready" / "w2.jpg").unlink()

    publish(["w1", "w2"], sequence=2, pinned_work_id="w2", renders=False)
    await daemon.tick()

    assert state.last_acted_sequence == 2
    assert tv.on_the_wall.name == "w1.jpg"


@pytest.mark.parametrize("sequence", [0, 1])
async def test_the_sequence_zero_baseline_is_not_special(daemon: Daemon, publish, state: DisplayState, sequence: int):
    """Zero is a real sequence, and `None` is the only "never acted" value.

    Conflating them would make a fresh catalogue's first `next` invisible.
    """
    publish(["w1"], sequence=sequence)

    await daemon.tick()

    assert state.last_acted_sequence == sequence


async def test_a_directive_is_not_consumed_by_a_wall_that_displays_nothing(
    daemon: Daemon, tv: FakeTv, publish, state: DisplayState
):
    """The same rule as an outage, reached by a route that raises nothing.

    A television whose panel is dark takes `select_image`, returns cleanly and
    goes on displaying what it had — so the jump did not happen while every call
    reported success. Consuming the sequence here would evaporate the curator's
    pin: the manifest does not change when a directive fails, so nothing would
    ever present it again, and the wall would come back on some other picture.
    """
    publish(["w1", "w2", "w3"], sequence=1)
    await daemon.tick()

    tv.displays_nothing_selected = True
    publish(["w1", "w2", "w3"], sequence=2, pinned_work_id="w3")
    await daemon.tick()
    assert state.last_acted_sequence == 1, "the directive was consumed against a wall that never changed"

    tv.displays_nothing_selected = False
    await daemon.tick()

    assert tv.on_the_wall.name == "w3.jpg", "the pin was not honoured once the wall started changing again"
    assert state.last_acted_sequence == 2
