"""The seam where the library's misbehaviour is corrected, tested on its own.

**This is the module with no test double under it**, and the one that most needs
tests: everything here exists because the `samsungtvws` fork reports things that
are not so. The daemon suite runs against `FakeTv` and therefore proves nothing
about any of it — a mutation sweep on 2026-08-06 deleted the close-on-failure and
no test objected, because no test reached this file at all.

The library is stubbed rather than the network, so what is under test is exactly
the correction: given a client that returns None for an upload that landed, does
this module find the image; given one that raises mid-conversation, does it close
the connection it can no longer reason about.
"""

import asyncio
import json

import pytest
from samsungtvws.exceptions import ResponseError

from display.tv import TvRemovalUnconfirmed, TvUnavailable, TvUploadFailed
from display.tv.samsung import SamsungTv


class StubArt:
    """As much of `SamsungTVAsyncArt` as this seam touches, and no more."""

    def __init__(self) -> None:
        self.entries: list[dict] = []
        self.closed = 0
        self.selected: list[str] = []
        self.slideshow_duration: int | None = None
        self.brightness: list[int] = []
        #: What `upload` does. The library's real range: an id, None (which may or
        #: may not mean failure), or a raise.
        self.upload_returns: str | None = "MY-F0001"
        self.upload_raises: Exception | None = None
        #: What the set ends up holding, whatever `upload` said. This is the whole
        #: point: the two are independent in reality.
        self.upload_lands_as: str | None = None
        self.listing_raises: Exception | None = None
        self.delete_raises: Exception | None = None
        self.undeletable: set[str] = set()
        self.artmode_reply: object = "on"
        self.artmode_raises: Exception | None = None

        self.callbacks: dict[str, object] = {}
        self.select_raises: Exception | None = None
        #: Whether the set announces the selection at all. False is the dark set:
        #: the request is taken, nothing is raised, and no event is ever emitted.
        self.announces = True
        #: The `is_shown` flag on the announcement, as a string on the wire.
        self.announce_is_shown = "Yes"
        #: An id to announce instead of the one selected — the set echoing a
        #: selection somebody made with the remote.
        self.announce_content_id: str | None = None
        #: The `data` payload verbatim, for the shapes a set should not send.
        self.announce_payload: object | None = None
        #: Whether the announcement arrives *during* `select_image` rather than
        #: after it returns. The real set is asynchronous, so the scheduled route
        #: is the realistic one; the synchronous route is how a listener armed
        #: after the request would miss the answer, and is asserted below.
        self.announces_synchronously = False
        #: How many times the set announces the one selection. More than one is a
        #: duplicate event, which resolves an already-resolved waiter.
        self.announce_times = 1

    def set_callback(self, trigger: str, callback: object = None) -> None:
        if callback is None:
            self.callbacks.pop(trigger, None)
        else:
            self.callbacks[trigger] = callback

    def _announcement(self, content_id: str) -> dict:
        if self.announce_payload is not None:
            data = self.announce_payload
        else:
            data = json.dumps(
                {
                    "event": "image_selected",
                    "content_id": self.announce_content_id or content_id,
                    "is_shown": self.announce_is_shown,
                }
            )
        return {"event": "d2d_service_message", "data": data}

    def _fire(self, response: dict) -> None:
        handler = self.callbacks.get("image_selected")
        if handler is not None:
            handler("d2d_service_message", response)  # type: ignore[operator]

    def fire(self, trigger: str, data: dict) -> None:
        """Deliver one of the set's announcements to whoever subscribed to it."""
        handler = self.callbacks.get(trigger)
        if handler is not None:
            handler("d2d_service_message", {"event": "d2d_service_message", "data": json.dumps(data)})  # type: ignore[operator]

    async def start_listening(self) -> None:
        return None

    async def close(self) -> None:
        self.closed += 1

    async def available(self, category: str | None = None) -> list[dict]:
        if self.listing_raises is not None:
            raise self.listing_raises
        return list(self.entries)

    async def upload(self, file: str, **kwargs: object) -> str | None:
        if self.upload_lands_as is not None:
            self.entries.append({"content_id": self.upload_lands_as, "image_date": kwargs.get("date")})
        if self.upload_raises is not None:
            raise self.upload_raises
        return self.upload_returns

    async def delete_list(self, content_ids: list[str]) -> None:
        if self.delete_raises is not None:
            raise self.delete_raises
        self.entries = [e for e in self.entries if e["content_id"] in self.undeletable or e["content_id"] not in content_ids]

    async def select_image(self, content_id: str, show: bool = True) -> None:
        self.selected.append(content_id)
        if self.select_raises is not None:
            raise self.select_raises
        if not self.announces:
            return
        response = self._announcement(content_id)
        for _ in range(self.announce_times):
            if self.announces_synchronously:
                self._fire(response)
            else:
                asyncio.get_running_loop().call_soon(self._fire, response)

    async def set_slideshow_status(self, duration: int = 0, **kwargs: object) -> None:
        self.slideshow_duration = duration

    async def set_brightness(self, value: int) -> None:
        self.brightness.append(value)

    async def get_artmode(self) -> object:
        if self.artmode_raises is not None:
            raise self.artmode_raises
        return self.artmode_reply


@pytest.fixture
def art() -> StubArt:
    return StubArt()


@pytest.fixture
async def tv(art: StubArt, tmp_path) -> SamsungTv:
    """Connected the way production connects, not by assigning the client in.

    **`connect` is what subscribes to the set's announcements**, so a fixture
    that reached past it would leave every selection here confirmed by a
    subscription the daemon never makes — and the one test that checks the
    registration would be the only thing standing between that and a green
    suite. Going through it costs a thread hop and buys the guarantee.
    """
    client = SamsungTv(
        host="10.0.0.1",
        port=8002,
        token_file=tmp_path / "token_file",
        client_name="tvpi-test",
        connect_timeout_seconds=1.0,
        upload_timeout_seconds=5.0,
        # Short because four tests below deliberately wait it out. Production's
        # window is seconds; nothing here depends on the number, only on it
        # elapsing.
        select_confirm_seconds=0.05,
    )
    client._construct = lambda: art  # the constructor is the blocking network I/O
    await client.connect()
    return client


class TestUploadIsConfirmedAgainstTheSet:
    async def test_an_id_the_library_returns_is_taken_at_its_word(self, tv: SamsungTv, art: StubArt, tmp_path):
        art.upload_returns = "MY-F0007"

        assert await tv.upload(tmp_path / "a.jpg") == "MY-F0007"

    async def test_an_upload_that_landed_while_reporting_nothing_is_found(self, tv: SamsungTv, art: StubArt, tmp_path):
        """The defect this whole module exists for.

        The image is on the wall and the caller is told it is not — worse than a
        plain failure, because it lies in the safe-looking direction and a caller
        that retries duplicates the picture.
        """
        art.upload_returns = None
        art.upload_lands_as = "MY-F0042"

        assert await tv.upload(tmp_path / "a.jpg") == "MY-F0042"

    async def test_an_upload_that_landed_while_raising_is_also_found(self, tv: SamsungTv, art: StubArt, tmp_path):
        art.upload_raises = AssertionError()  # this library's spelling of a timeout
        art.upload_lands_as = "MY-F0043"

        assert await tv.upload(tmp_path / "a.jpg") == "MY-F0043"

    async def test_an_upload_that_truly_failed_raises(self, tv: SamsungTv, art: StubArt, tmp_path):
        art.upload_returns = None
        art.upload_lands_as = None

        with pytest.raises(TvUploadFailed):
            await tv.upload(tmp_path / "a.jpg")

    async def test_an_id_that_was_already_there_is_not_claimed(self, tv: SamsungTv, art: StubArt, tmp_path):
        """Attribution is against a before-snapshot, so a work this upload did not
        create is never bound to it — that would put somebody else's picture under
        this work's id, which is worse than reporting a failure."""
        art.entries = [{"content_id": "MY-OLD-1", "image_date": "whenever"}]
        art.upload_returns = None
        art.upload_lands_as = None

        with pytest.raises(TvUploadFailed):
            await tv.upload(tmp_path / "a.jpg")

    async def test_two_arrivals_at_once_are_attributed_by_marker(self, tv: SamsungTv, art: StubArt, tmp_path):
        """A second image appearing from elsewhere must not steal the attribution.

        The `image_date` this request stamped is what tells them apart; the
        single-new-id shortcut would otherwise pick whichever was listed first.
        """
        art.upload_returns = None
        art.upload_lands_as = "MY-MINE"

        async def upload(file: str, **kwargs: object) -> None:
            art.entries.append({"content_id": "MY-SOMEONE-ELSES", "image_date": "1999:01:01 00:00:00"})
            art.entries.append({"content_id": "MY-MINE", "image_date": kwargs.get("date")})
            return None

        art.upload = upload  # type: ignore[method-assign]

        assert await tv.upload(tmp_path / "a.jpg") == "MY-MINE"


class TestRemovalIsConfirmedAgainstTheSet:
    async def test_a_removal_reports_what_the_set_holds_afterwards(self, tv: SamsungTv, art: StubArt):
        art.entries = [{"content_id": "MY-1"}, {"content_id": "MY-2"}]

        outcome = await tv.remove(["MY-1"])

        assert outcome.complete
        assert outcome.removed == ("MY-1",)

    async def test_an_image_the_set_keeps_is_reported_surviving_not_removed(self, tv: SamsungTv, art: StubArt):
        art.entries = [{"content_id": "MY-1"}]
        art.undeletable = {"MY-1"}

        outcome = await tv.remove(["MY-1"])

        assert not outcome.complete
        assert outcome.surviving == ("MY-1",)

    async def test_a_refused_removal_is_unconfirmable_rather_than_failed(self, tv: SamsungTv, art: StubArt):
        """The library discards the reply, so "refused" and "worked" are the same
        return value. Reporting either would be a guess."""
        art.delete_raises = ResponseError("no")

        with pytest.raises(TvRemovalUnconfirmed):
            await tv.remove(["MY-1"])

    async def test_a_removal_whose_readback_fails_is_unconfirmable(self, tv: SamsungTv, art: StubArt):
        art.entries = [{"content_id": "MY-1"}]
        art.listing_raises = OSError("gone")

        with pytest.raises(TvRemovalUnconfirmed):
            await tv.remove(["MY-1"])

    async def test_removing_nothing_asks_the_set_nothing(self, tv: SamsungTv, art: StubArt):
        art.delete_raises = ResponseError("should not be called")

        assert (await tv.remove([])).complete


class TestFailureLeavesNothingBehind:
    async def test_a_failed_call_closes_the_client_it_can_no_longer_reason_about(self, tv: SamsungTv, art: StubArt):
        """**Closed, not merely dropped.**

        Several of these arrive over a healthy socket, and `close()` is what ends
        both the session and the reader task `start_listening` spawned. Abandoning
        the reference leaves that task holding the connection against collection —
        one leak per transient error, on a daemon that runs for months.
        """
        art.listing_raises = ResponseError("no")

        with pytest.raises(TvUnavailable):
            await tv.listed_content_ids()

        assert art.closed == 1, "the client was abandoned rather than closed"

    async def test_a_failed_call_forces_the_next_pass_to_reconnect(self, tv: SamsungTv, art: StubArt):
        art.listing_raises = ResponseError("no")
        with pytest.raises(TvUnavailable):
            await tv.listed_content_ids()

        with pytest.raises(TvUnavailable, match="not connected"):
            await tv.show("MY-1")

    async def test_every_library_exception_arrives_as_one_type(self, tv: SamsungTv, art: StubArt):
        """The daemon's response is the same to all of them, and branching on the
        library's internals is what the seam exists to avoid."""
        for failure in (OSError("x"), AssertionError(), KeyError("k"), ResponseError("r")):
            tv._art = art
            art.listing_raises = failure
            with pytest.raises(TvUnavailable):
                await tv.listed_content_ids()


class TestConnecting:
    async def test_a_set_that_never_opens_the_art_channel_says_so_in_those_terms(self, tv: SamsungTv, art: StubArt, tmp_path):
        """It is the one failure a person can fix by picking up the remote, so the
        message names it rather than reporting a timeout."""

        async def never_returns() -> None:
            await asyncio.sleep(10)

        art.start_listening = never_returns  # type: ignore[method-assign]
        tv._art = None
        # The constructor is what does blocking network I/O, so it is the seam a
        # test replaces — `connect` still runs its own thread hop and its own
        # ceiling, which is what is under test here.
        tv._construct = lambda: art  # type: ignore[method-assign]

        with pytest.raises(TvUnavailable, match="art mode"):
            await tv.connect()

        assert art.closed == 1, "the half-open connection was left behind"

    async def test_connecting_twice_is_free(self, tv: SamsungTv, art: StubArt):
        await tv.connect()

        assert art.closed == 0


class TestTheRestOfTheSurface:
    async def test_the_native_slideshow_is_switched_off_rather_than_shortened(self, tv: SamsungTv, art: StubArt):
        await tv.disable_native_slideshow()

        assert art.slideshow_duration == 0

    async def test_a_listing_that_is_not_a_list_is_refused(self, tv: SamsungTv, art: StubArt):
        async def nonsense(category: str | None = None) -> str:
            return "not a list"

        art.available = nonsense  # type: ignore[method-assign]

        with pytest.raises(TvUnavailable):
            await tv.listed_content_ids()


# -- confirming that a selection reached the wall -----------------------------
#
# The set announces a selection by emitting `image_selected`; there is no reader
# on this firmware that answers "what is on the wall". `get_current_artwork` was
# used for a day and reports the art-store slot instead — it named the same id
# for days while the wall visibly changed — so the whole design rests on the
# event, and on listening for it from before the request goes out.


async def test_a_selection_the_set_announces_is_reported_shown(tv: SamsungTv, art: StubArt):
    assert await tv.show("MY-F0007") is True
    assert art.selected == ["MY-F0007"]


async def test_a_set_that_announces_nothing_reports_the_wall_unchanged(tv: SamsungTv, art: StubArt):
    """The defect this path exists for, and the one no return value can carry.

    With its panel dark this television takes the request, raises nothing and
    emits no event, while uploads, removals and brightness all keep working. It
    is reported as a wall that did not move, not as an outage.
    """
    art.announces = False

    assert await tv.show("MY-F0007") is False


async def test_a_set_that_admits_it_is_not_showing_is_not_believed_to_be(tv: SamsungTv, art: StubArt):
    """`is_shown` is read rather than the announcement merely being counted."""
    art.announce_is_shown = "No"

    assert await tv.show("MY-F0007") is False


async def test_an_announcement_about_another_image_does_not_confirm_ours(tv: SamsungTv, art: StubArt):
    """The set echoes selections nobody here made — somebody using the remote.

    Resolving on any announcement would report the wrong work as the one on the
    wall, and the daemon records what it believes is displayed.
    """
    art.announce_content_id = "SAM-F0222"

    assert await tv.show("MY-F0007") is False


async def test_the_announcement_is_caught_even_when_it_arrives_during_the_request(tv: SamsungTv, art: StubArt):
    """Why selecting and confirming are one call rather than two.

    The real set has been measured announcing 0.49 s after the request, so a
    caller that registered its listener *after* `select_image` returned would be
    racing it — and would report a working wall as stuck. Arming first is what
    this asserts: the stub fires the event before the request even returns.
    """
    art.announces_synchronously = True

    assert await tv.show("MY-F0007") is True


async def test_the_same_announcement_arriving_twice_is_harmless(tv: SamsungTv, art: StubArt):
    """A duplicate event must not raise out of the handler.

    It runs on the library's reader task, so an exception there is delivered to
    nobody who could act on it and takes the socket's reader down with it — the
    connection then looks alive while no announcement ever arrives again, and
    every selection for the rest of the daemon's life reports the wall unchanged.
    """
    art.announces_synchronously = True
    art.announce_times = 2

    assert await tv.show("MY-F0007") is True


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param("not json at all", id="payload is not json"),
        pytest.param(json.dumps(["a", "list"]), id="payload is not a mapping"),
        pytest.param(json.dumps({"event": "image_selected"}), id="no content_id in it"),
    ],
)
async def test_an_announcement_it_cannot_read_confirms_nothing(tv: SamsungTv, art: StubArt, payload: object):
    """Unreadable is treated as unheard, which falls to the timeout and reports
    the wall unchanged — the safe direction, since claiming a picture is up when
    it is not is the whole defect."""
    art.announce_payload = payload

    assert await tv.show("MY-F0007") is False


async def test_a_set_that_goes_away_mid_selection_is_an_outage_not_a_still_wall(tv: SamsungTv, art: StubArt):
    """`TvUnavailable`, not False. The two want opposite responses: an outage
    holds the wall and reconnects, while a still wall backs off and says why."""
    art.select_raises = ResponseError("the set stopped answering")

    with pytest.raises(TvUnavailable):
        await tv.show("MY-F0007")
    assert art.closed == 1, "the connection was kept after a failure nobody can reason about"


async def test_a_late_announcement_resolves_nothing_after_the_attempt_is_over(tv: SamsungTv, art: StubArt):
    """The waiting slot is cleared on every route out.

    A set that answers after the window has closed must not have its reply
    applied to whatever selection came next — which is what a slot left in place
    across attempts would do.
    """
    art.announces = False
    assert await tv.show("MY-F0007") is False

    art._fire(art._announcement("MY-F0007"))  # the set, answering far too late

    assert tv._awaiting is None


async def test_connecting_subscribes_to_the_announcement(art: StubArt, tmp_path):
    """Registered per connection, not once per process.

    A failed call abandons the client, so the next attempt is a new object; a
    subscription made against the old one would leave every later selection
    unconfirmable for the life of the daemon.
    """
    tv = SamsungTv(
        host="10.0.0.1",
        port=8002,
        token_file=tmp_path / "token_file",
        client_name="tvpi-test",
        connect_timeout_seconds=1.0,
        upload_timeout_seconds=5.0,
        select_confirm_seconds=0.05,
    )
    tv._construct = lambda: art  # type: ignore[method-assign]

    await tv.connect()

    assert "image_selected" in art.callbacks


# -- whether the wall is ours to change ---------------------------------------
#
# Selecting on a set showing a programme switches it into art mode and takes the
# screen off the person watching, so this is a permission question and it is
# answered conservatively: only a plain `on` is a yes.


@pytest.mark.parametrize(
    "reply, expected",
    [
        pytest.param("on", True, id="the set says it is showing art"),
        pytest.param("off", False, id="a programme, or a dark panel"),
        pytest.param("", False, id="an empty answer"),
        pytest.param({"value": "on"}, False, id="a shape this seam cannot read"),
        pytest.param(None, False, id="no answer at all"),
    ],
)
async def test_only_a_plain_yes_lets_the_wall_be_touched(tv: SamsungTv, art: StubArt, reply: object, expected: bool):
    """A wall that waits is late; a wall that does not is an interruption."""
    art.artmode_reply = reply

    assert await tv.showing_art() is expected


async def test_a_set_that_cannot_be_asked_is_an_outage_not_a_refusal(tv: SamsungTv, art: StubArt):
    """`TvUnavailable`, not False. Holding the wall and reconnecting is a
    different response from leaving somebody's television alone."""
    art.artmode_raises = ResponseError("the set stopped answering")

    with pytest.raises(TvUnavailable):
        await tv.showing_art()


async def test_an_art_mode_announcement_is_reported_once_and_then_cleared(tv: SamsungTv, art: StubArt):
    """An edge, not a state. It says "ask again", and asking is what settles it —
    so a second read of the same announcement would license a second free attempt
    at a wall that may still not be ours."""
    art.fire("art_mode_changed", {"event": "art_mode_changed", "status": "on"})

    assert tv.art_mode_announcement_pending() is True
    assert tv.art_mode_announcement_pending() is False


@pytest.mark.parametrize("announcement", ["art_mode_changed", "artmode_status", "go_to_standby", "wakeup"])
async def test_every_way_the_set_mentions_art_mode_counts(tv: SamsungTv, art: StubArt, announcement: str):
    """None of these payloads is parsed, so all four can share one handler — which
    is why the set's spelling cannot be got wrong here."""
    tv.art_mode_announcement_pending()  # clear the one connecting leaves behind
    art.fire(announcement, {"event": announcement})

    assert tv.art_mode_announcement_pending() is True


async def test_connecting_counts_as_an_announcement(art: StubArt, tmp_path):
    """A reconnection is news: the set may have entered art mode while this plane
    could not hear it, and otherwise the wall sits out a wait whose reason has
    gone."""
    tv = SamsungTv(
        host="10.0.0.1",
        port=8002,
        token_file=tmp_path / "token_file",
        client_name="tvpi-test",
        connect_timeout_seconds=1.0,
        upload_timeout_seconds=5.0,
        select_confirm_seconds=0.05,
    )
    tv._construct = lambda: art  # type: ignore[method-assign]

    await tv.connect()

    assert tv.art_mode_announcement_pending() is True


async def test_the_art_mode_flag_is_passed_through(tv: SamsungTv, art: StubArt):
    art.artmode_reply = "off"

    assert await tv.reported_art_mode() == "off"


async def test_a_failure_to_read_the_art_mode_flag_is_swallowed(tv: SamsungTv, art: StubArt):
    """It runs only where something has already gone wrong, and a diagnostic that
    can raise replaces the report of the real fault with a report of itself."""
    art.artmode_raises = ResponseError("no answer")

    assert await tv.reported_art_mode() is None


async def test_an_art_mode_reply_that_is_not_a_string_is_no_reply(tv: SamsungTv, art: StubArt):
    art.artmode_reply = {"value": "on"}

    assert await tv.reported_art_mode() is None
