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
        #: What the set answers when asked what it is displaying. The real shape,
        #: as recorded from the deployment's own television.
        self.current_reply: object = {
            "event": "get_current_artwork",
            "content_id": "MY-F0001",
            "content_type": "artstore",
        }
        self.current_raises: Exception | None = None
        self.artmode_reply: object = "on"
        self.artmode_raises: Exception | None = None

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

    async def set_slideshow_status(self, duration: int = 0, **kwargs: object) -> None:
        self.slideshow_duration = duration

    async def set_brightness(self, value: int) -> None:
        self.brightness.append(value)

    async def get_current(self) -> object:
        """What the set says it is displaying — including the shapes it should not send.

        Typed as `object` because the point of the tests below is what this seam
        does with a reply that is not the documented one: the library asserts on
        an empty answer and passes anything else straight through.
        """
        if self.current_raises is not None:
            raise self.current_raises
        return self.current_reply

    async def get_artmode(self) -> object:
        if self.artmode_raises is not None:
            raise self.artmode_raises
        return self.artmode_reply


@pytest.fixture
def art() -> StubArt:
    return StubArt()


@pytest.fixture
def tv(art: StubArt, tmp_path) -> SamsungTv:
    client = SamsungTv(
        host="10.0.0.1",
        port=8002,
        token_file=tmp_path / "token_file",
        client_name="tvpi-test",
        connect_timeout_seconds=1.0,
        upload_timeout_seconds=5.0,
    )
    client._art = art  # already connected; `connect` itself is exercised below
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
            await tv.select_image("MY-1")

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


# -- the confirming read ------------------------------------------------------
#
# The read the whole selection-confirmation design rests on. It has to answer
# three ways rather than two: the id it was given, a *different* id, or nothing
# it can vouch for — and the daemon treats the third as agreement, because a set
# that declines to describe its own display must not stop a working wall. That
# choice is only safe if "declines" is genuinely distinguished here.


async def test_it_reports_the_id_the_set_names(tv: SamsungTv, art: StubArt):
    art.current_reply = {"event": "get_current_artwork", "content_id": "MY-F0007", "content_type": "mypicture"}

    assert await tv.current_content_id() == "MY-F0007"


async def test_it_reports_an_id_that_is_not_the_one_we_asked_for(tv: SamsungTv, art: StubArt):
    """The case the design exists for: the set displaying something else.

    Returned verbatim rather than compared here — the seam reports what the
    television says, and the loop is what decides whether that is agreement.
    """
    art.current_reply = {"event": "get_current_artwork", "content_id": "SAM-F0222", "content_type": "artstore"}

    assert await tv.current_content_id() == "SAM-F0222"


@pytest.mark.parametrize(
    "reply",
    [
        pytest.param("not a mapping at all", id="reply is not a dict"),
        pytest.param({"event": "get_current_artwork"}, id="no content_id in it"),
        pytest.param({"content_id": ""}, id="content_id is empty"),
        pytest.param({"content_id": 12345}, id="content_id is not a string"),
    ],
)
async def test_an_answer_it_cannot_vouch_for_is_no_answer(tv: SamsungTv, art: StubArt, reply: object):
    """Each of these would otherwise be compared against a content id, and a
    comparison against a value whose meaning nobody knows is worse than none."""
    art.current_reply = reply

    assert await tv.current_content_id() is None


async def test_a_set_that_goes_away_mid_read_is_an_outage_not_a_disagreement(tv: SamsungTv, art: StubArt):
    """`TvUnavailable`, not None. The two want opposite responses: an outage holds
    the wall and reconnects, while "cannot say" lets the rotation stand."""
    art.current_raises = ResponseError("the set stopped answering")

    with pytest.raises(TvUnavailable):
        await tv.current_content_id()
    assert art.closed == 1, "the connection was kept after a failure nobody can reason about"


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
