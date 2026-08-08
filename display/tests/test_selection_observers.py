"""Fanning out the set's selection announcements without unseating confirmation.

**The defect these exist to make impossible is silent and total.** The library
underneath keeps one handler per event, so a second subscriber registered
directly *replaces* the selection confirmation rather than joining it. Every
rotation then falls to its confirmation timeout and is reported as a wall that
would not move — while the new subscriber works perfectly, which is why nobody
would look at it. So the property under test is not "observers are called": it is
"observers are called **and** confirmation still resolves".

Driven through `SamsungTv._on_image_selected` directly rather than through a
socket. That method is the whole fan-out, it is synchronous, and reaching it the
long way would need a live television.
"""

import asyncio
import json

import pytest

from display.tv import SelectionAnnouncement
from display.tv.samsung import SamsungTv


def announcement(content_id: str, *, is_shown: bool = True) -> dict[str, str]:
    """One `image_selected` message in the shape the set puts on the wire."""
    return {"data": json.dumps({"content_id": content_id, "is_shown": "Yes" if is_shown else "No"})}


@pytest.fixture
def tv(tmp_path) -> SamsungTv:
    return SamsungTv(
        host="10.0.0.1",
        port=8002,
        token_file=tmp_path / "token",
        client_name="test",
        connect_timeout_seconds=1,
        upload_timeout_seconds=1,
        select_confirm_seconds=1,
    )


class TestTheFanOut:
    def test_an_observer_hears_an_announcement(self, tv: SamsungTv):
        heard: list[SelectionAnnouncement] = []
        tv.observe_selections(heard.append)

        tv._on_image_selected("image_selected", announcement("MY_F0001"))

        assert heard == [SelectionAnnouncement(content_id="MY_F0001", is_shown=True)]

    def test_every_observer_hears_it(self, tv: SamsungTv):
        first: list[SelectionAnnouncement] = []
        second: list[SelectionAnnouncement] = []
        tv.observe_selections(first.append)
        tv.observe_selections(second.append)

        tv._on_image_selected("image_selected", announcement("MY_F0002"))

        assert len(first) == 1
        assert first == second

    @pytest.mark.asyncio
    async def test_an_observer_does_not_cost_the_confirmation_its_event(self, tv: SamsungTv):
        """The whole reason this mechanism exists.

        Registered the way the library invites — `set_callback` — this observer
        would have replaced the confirmation handler and this future would never
        resolve.
        """
        waiter: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        tv._awaiting = ("MY_F0003", waiter)
        heard: list[SelectionAnnouncement] = []
        tv.observe_selections(heard.append)

        tv._on_image_selected("image_selected", announcement("MY_F0003"))

        assert waiter.done(), "the selection was never confirmed"
        assert waiter.result() is True
        assert len(heard) == 1

    @pytest.mark.asyncio
    async def test_an_observer_that_raises_does_not_cost_the_confirmation_either(self, tv: SamsungTv):
        """An observer is a stranger, and a broken one may not stop the wall.

        Confirmation is resolved *before* observers run, so this holds by
        construction — asserted anyway, because the ordering is the thing that
        makes it true and a later edit could reverse it without any other test
        noticing.
        """
        waiter: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        tv._awaiting = ("MY_F0004", waiter)

        def explode(_announcement: SelectionAnnouncement) -> None:
            raise RuntimeError("the label renderer fell over")

        tv.observe_selections(explode)

        tv._on_image_selected("image_selected", announcement("MY_F0004"))

        assert waiter.done()
        assert waiter.result() is True

    def test_one_broken_observer_does_not_cost_another_its_event(self, tv: SamsungTv):
        heard: list[SelectionAnnouncement] = []

        def explode(_announcement: SelectionAnnouncement) -> None:
            raise RuntimeError("first observer is broken")

        tv.observe_selections(explode)
        tv.observe_selections(heard.append)

        tv._on_image_selected("image_selected", announcement("MY_F0005"))

        assert len(heard) == 1, "a broken observer swallowed a later one's announcement"

    def test_an_announcement_nobody_here_asked_for_still_reaches_observers(self, tv: SamsungTv):
        """The case the old handler discarded, and the one an observer wants most.

        Somebody picking up the remote makes the set announce a selection this
        plane never made. There is no pending selection, so the handler used to
        return before parsing anything — which is precisely the news an observer
        exists to hear: the wall changed, and we did not do it.
        """
        heard: list[SelectionAnnouncement] = []
        tv.observe_selections(heard.append)
        assert tv._awaiting is None

        tv._on_image_selected("image_selected", announcement("SAM-F0222"))

        assert [a.content_id for a in heard] == ["SAM-F0222"]

    def test_the_sets_own_no_is_carried_through_rather_than_dropped(self, tv: SamsungTv):
        heard: list[SelectionAnnouncement] = []
        tv.observe_selections(heard.append)

        tv._on_image_selected("image_selected", announcement("MY_F0006", is_shown=False))

        assert heard == [SelectionAnnouncement(content_id="MY_F0006", is_shown=False)]


class TestWhatIsNotAnAnnouncement:
    """Unreadable messages reach nobody, rather than reaching everyone as blanks."""

    @pytest.mark.parametrize(
        ("response", "why"),
        [
            ({}, "no data at all"),
            ({"data": "not json"}, "data that will not parse"),
            ({"data": json.dumps([1, 2, 3])}, "a list where an object belongs"),
            ({"data": json.dumps({"is_shown": "Yes"})}, "no content id"),
            ({"data": json.dumps({"content_id": "", "is_shown": "Yes"})}, "an empty content id"),
            ({"data": json.dumps({"content_id": 17, "is_shown": "Yes"})}, "a content id that is not a string"),
        ],
    )
    def test_nothing_is_fanned_out(self, tv: SamsungTv, response: dict, why: str):
        heard: list[SelectionAnnouncement] = []
        tv.observe_selections(heard.append)

        tv._on_image_selected("image_selected", response)

        assert heard == [], f"{why} was passed on as though it were an announcement"

    @pytest.mark.asyncio
    async def test_an_unreadable_message_leaves_the_selection_waiting(self, tv: SamsungTv):
        """It falls to its timeout, which reports the wall unchanged — the safe direction."""
        waiter: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        tv._awaiting = ("MY_F0007", waiter)

        tv._on_image_selected("image_selected", {"data": "not json"})

        assert not waiter.done()


class TestConfirmationIsStillItself:
    """The behaviour the fan-out was threaded through, unchanged."""

    @pytest.mark.asyncio
    async def test_an_announcement_for_another_id_does_not_resolve_this_one(self, tv: SamsungTv):
        waiter: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        tv._awaiting = ("MY_F0008", waiter)

        tv._on_image_selected("image_selected", announcement("SAM-F0222"))

        assert not waiter.done(), "somebody else's selection resolved this one"

    @pytest.mark.asyncio
    async def test_an_already_settled_selection_is_left_alone(self, tv: SamsungTv):
        waiter: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        waiter.set_result(True)
        tv._awaiting = ("MY_F0009", waiter)

        tv._on_image_selected("image_selected", announcement("MY_F0009", is_shown=False))

        assert waiter.result() is True


class TestSubscribingTwiceIsSubscribingOnce:
    """**The list is per client object and lives as long as the process**, while
    the library callbacks it fans out from are re-registered on every
    reconnection. A caller that reasonably re-subscribed after a drop would
    otherwise be told twice per announcement for the rest of the daemon's life —
    and what follows an announcement here is a full-frame e-paper redraw, so a
    duplicate is one and a half seconds of the panel drawing what it just drew.
    """

    def test_the_same_observer_registered_twice_is_told_once(self, tv: SamsungTv):
        heard = []

        tv.observe_selections(heard.append)
        tv.observe_selections(heard.append)

        tv._on_image_selected("image_selected", announcement("tv-1"))

        assert len(heard) == 1, "one announcement reached a re-subscribed observer twice"

    def test_two_different_observers_are_both_told(self, tv: SamsungTv):
        """The guard must reject duplicates, not second subscribers — collapsing
        those is the original defect wearing different clothes."""
        first, second = [], []

        tv.observe_selections(first.append)
        tv.observe_selections(second.append)

        tv._on_image_selected("image_selected", announcement("tv-1"))

        assert len(first) == 1 and len(second) == 1


class TestTheDoubleMatchesTheClientOnThisSeam:
    """A fake that is *stricter* than the thing it stands in for is the direction
    that hurts: a test describing behaviour the product really has fails, and the
    obvious fix is to weaken the test rather than the double.

    `SamsungTv._tell_observers` isolates each observer, on the grounds that they
    are strangers to each other and this runs on the socket's reader task.
    `FakeTv.announce` did not, until this was noticed.
    """

    def test_a_raising_observer_does_not_cost_a_later_one_its_announcement(self):
        from fakes import FakeTv

        tv = FakeTv()
        heard = []

        tv.observe_selections(_explode)
        tv.observe_selections(heard.append)

        tv.announce("tv-1", is_shown=True)

        assert heard, "a raising observer took a later one's announcement with it"
        assert tv.observer_failures == 1, "the failure was hidden rather than isolated"


def _explode(_announcement) -> None:
    raise RuntimeError("the label renderer fell over")
