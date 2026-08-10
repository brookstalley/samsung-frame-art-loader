"""The two shapes the daemon's episodes are built from.

Tested directly rather than only through the daemon because the daemon exercises
each of them along one path — the path that happened to be written first — and
the edges that bite are the ones no caller reaches today: an episode ended that
never began, a ladder held past its ceiling, a recovery that has to put the next
failure back at the bottom rung rather than halfway up it.
"""

from display.episodes import Backoff, ReportOnce


class TestReportOnce:
    def test_the_first_sighting_is_an_edge_and_the_rest_are_not(self):
        condition = ReportOnce()

        assert condition.begin() is True
        assert condition.begin() is False
        assert condition.begin() is False

    def test_it_knows_it_is_being_lived_through(self):
        condition = ReportOnce()
        assert condition.reported is False

        condition.begin()

        assert condition.reported is True

    def test_ending_a_reported_episode_is_an_edge(self):
        condition = ReportOnce()
        condition.begin()

        assert condition.end() is True
        assert condition.reported is False

    def test_ending_an_episode_that_never_began_is_not(self):
        """The ordinary case, and the one that would spam a recovery line.

        Most passes end nothing. A caller that logged unconditionally would
        announce the television coming back on every poll it had never left.
        """
        condition = ReportOnce()

        assert condition.end() is False

    def test_it_can_be_lived_through_more_than_once(self):
        condition = ReportOnce()

        assert condition.begin() is True
        assert condition.end() is True
        assert condition.begin() is True
        assert condition.end() is True


class Ticking:
    """A monotonic source the test drives by hand.

    Deliberately not stepped by a multiple of any interval under test: a clock
    advanced by exactly the wait cannot distinguish `>=` from `>`, and this
    repository has been bitten by that three times.
    """

    def __init__(self) -> None:
        self.elapsed = 1000.0

    def __call__(self) -> float:
        return self.elapsed

    def advance(self, seconds: float) -> None:
        self.elapsed += seconds


class TestBackoff:
    def test_nothing_is_held_before_anything_fails(self):
        clock = Ticking()

        ladder = Backoff(minimum=5, maximum=300, monotonic=clock)

        assert ladder.is_due() is True

    def test_the_first_hold_waits_the_minimum(self):
        """The rung a recovery must return to, and the one an off-by-one skips."""
        clock = Ticking()
        ladder = Backoff(minimum=5, maximum=300, monotonic=clock)

        assert ladder.hold() == 5

    def test_each_hold_waits_longer_than_the_last(self):
        clock = Ticking()
        ladder = Backoff(minimum=5, maximum=300, monotonic=clock)

        assert [ladder.hold() for _ in range(4)] == [5, 10, 20, 40]

    def test_the_wait_stops_doubling_at_the_ceiling(self):
        """Unbounded doubling is a wall that stays blank into the next morning."""
        clock = Ticking()
        ladder = Backoff(minimum=5, maximum=20, monotonic=clock)

        assert [ladder.hold() for _ in range(5)] == [5, 10, 20, 20, 20]

    def test_a_held_ladder_is_not_due_until_the_wait_has_run(self):
        clock = Ticking()
        ladder = Backoff(minimum=5, maximum=300, monotonic=clock)
        ladder.hold()

        assert ladder.is_due() is False

        clock.advance(4.5)
        assert ladder.is_due() is False

        clock.advance(1.25)
        assert ladder.is_due() is True

    def test_clearing_forgets_the_wait_and_the_rung_together(self):
        """Both halves, because forgetting only the wait is the subtler bug.

        A ladder that resumes at the bottom rung but keeps its deadline leaves
        the wall waiting out an outage that has already ended; one that drops the
        deadline but stays high on the ladder makes the next unrelated blip wait
        minutes.
        """
        clock = Ticking()
        ladder = Backoff(minimum=5, maximum=300, monotonic=clock)
        ladder.hold()
        ladder.hold()

        ladder.clear()

        assert ladder.is_due() is True
        assert ladder.hold() == 5

    def test_the_wait_it_will_apply_next_is_readable(self):
        clock = Ticking()
        ladder = Backoff(minimum=5, maximum=300, monotonic=clock)

        assert ladder.seconds == 5
        ladder.hold()
        assert ladder.seconds == 10
