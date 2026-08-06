"""Deleting from the television reports what the television actually holds.

The library's async `delete_list` returns None whether it removed anything or
not, so every assertion here is about the wrapper distinguishing outcomes the
library cannot: gone, still listed, and unknown.

There is no `pytest-asyncio` in this project and these tests do not warrant
adding one — `asyncio.run` drives a coroutine perfectly well, and the legacy
modules these cover are retired once both planes exist.
"""

import asyncio
import logging

import pytest

from tv_delete import (
    UPLOADED_CATEGORY,
    DeleteNotConfirmed,
    delete_list_confirmed,
    describe_removal,
    forgettable_ids,
    remove_from_tv,
)


class FakeTv:
    """A television that honours some removals and not others.

    `honours` is the set of ids it will actually drop; anything else stays
    listed, which is exactly the silent failure the wrapper exists to catch. A
    real set gives no signal about which case it is in, so the fake models the
    outcome rather than the protocol.
    """

    def __init__(self, listed, honours=None, confirm_raises=None, delete_raises=None):
        self.listed = list(listed)
        self.honours = set(self.listed) if honours is None else set(honours)
        self.confirm_raises = confirm_raises
        self.delete_raises = delete_raises
        self.delete_calls: list[list[str]] = []
        self.available_calls: list[str | None] = []

    async def delete_list(self, content_ids):
        self.delete_calls.append(list(content_ids))
        if self.delete_raises is not None:
            raise self.delete_raises
        self.listed = [c for c in self.listed if not (c in content_ids and c in self.honours)]
        # The library returns None here regardless of outcome. That is the defect.
        return None

    async def available(self, category=None):
        self.available_calls.append(category)
        if self.confirm_raises is not None:
            raise self.confirm_raises
        return [{"content_id": c, "category_id": category or UPLOADED_CATEGORY} for c in self.listed]


def test_a_removal_the_television_honoured_reads_as_complete():
    tv = FakeTv(listed=["MY-C0002-1", "MY-C0002-2", "MY-C0002-3"])

    result = asyncio.run(delete_list_confirmed(tv, ["MY-C0002-1", "MY-C0002-2"]))

    assert result.complete
    assert result.deleted == ("MY-C0002-1", "MY-C0002-2")
    assert result.surviving == ()
    assert tv.listed == ["MY-C0002-3"]


def test_the_request_actually_carries_the_ids():
    """Without this, a wrapper that only ever read the list would pass every
    other test in this file — the TV would look correct because nothing had
    asked it to change."""
    tv = FakeTv(listed=["MY-C0002-1", "MY-C0002-2"])

    asyncio.run(delete_list_confirmed(tv, ["MY-C0002-1"]))

    assert tv.delete_calls == [["MY-C0002-1"]]
    assert tv.available_calls == [UPLOADED_CATEGORY]


def test_images_the_television_kept_are_named_not_counted_as_deleted():
    tv = FakeTv(listed=["MY-C0002-1", "MY-C0002-2"], honours=["MY-C0002-1"])

    result = asyncio.run(delete_list_confirmed(tv, ["MY-C0002-1", "MY-C0002-2"]))

    assert not result.complete
    assert result.surviving == ("MY-C0002-2",)
    assert result.deleted == ("MY-C0002-1",)


def test_a_partial_removal_warns_even_if_the_caller_ignores_the_result(caplog):
    """The return value can be dropped; the log line cannot. A caller that does
    not look must still leave a record naming the images that stayed."""
    tv = FakeTv(listed=["MY-C0002-1", "MY-C0002-2"], honours=[])

    with caplog.at_level(logging.WARNING):
        asyncio.run(delete_list_confirmed(tv, ["MY-C0002-1", "MY-C0002-2"]))

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "MY-C0002-1" in warnings[0].getMessage()
    assert "MY-C0002-2" in warnings[0].getMessage()


def test_a_removal_that_worked_says_nothing(caplog):
    tv = FakeTv(listed=["MY-C0002-1"])

    with caplog.at_level(logging.WARNING):
        asyncio.run(delete_list_confirmed(tv, ["MY-C0002-1"]))

    assert [r for r in caplog.records if r.levelno == logging.WARNING] == []


def test_an_unreadable_content_list_is_unknown_not_failure():
    """samsungtvws signals a timed-out art request by asserting on a None
    response, so AssertionError is the library's timeout rather than a broken
    assumption here — and the outcome is genuinely unknown, not failed."""
    tv = FakeTv(listed=["MY-C0002-1"], confirm_raises=AssertionError())

    with pytest.raises(DeleteNotConfirmed) as exc:
        asyncio.run(delete_list_confirmed(tv, ["MY-C0002-1"]))

    assert isinstance(exc.value.__cause__, AssertionError)
    assert tv.delete_calls == [["MY-C0002-1"]], "the request was still sent; only the confirmation failed"


def test_any_library_error_on_the_read_is_the_same_unknown_outcome():
    """Not only the library's assert. Its error taxonomy is not stable and is
    not ours — a subset named here is a subset that escapes as an abort."""

    class ResponseError(Exception):
        pass

    tv = FakeTv(listed=["MY-C0002-1"], confirm_raises=ResponseError("get_content_list failed with error number 3"))

    with pytest.raises(DeleteNotConfirmed) as exc:
        asyncio.run(delete_list_confirmed(tv, ["MY-C0002-1"]))

    assert isinstance(exc.value.__cause__, ResponseError), "the original must survive as the cause"


def test_a_removal_request_the_set_refuses_is_unknown_too():
    """The set answering `event: error` to the removal itself raises before the
    confirming read ever runs. It is the same finding: nobody can say what the
    set holds, and it must not escape as an abort through the caller."""

    class ResponseError(Exception):
        pass

    tv = FakeTv(listed=["MY-C0002-1"], delete_raises=ResponseError("delete_image_list failed with error number 3"))

    with pytest.raises(DeleteNotConfirmed):
        asyncio.run(delete_list_confirmed(tv, ["MY-C0002-1"]))

    assert tv.available_calls == [], "the read is unreachable once the request itself raised"


def test_a_refused_removal_request_does_not_stop_the_caller(caplog):
    """A refusal reaches the caller by a different door from an unreadable list,
    and an earlier version of this guard covered only the second — so a refused
    removal aborted the housekeeping pass before it could save or upload."""

    class ResponseError(Exception):
        pass

    tv = FakeTv(listed=["MY-C0002-1"], delete_raises=ResponseError("delete_image_list failed with error number 3"))

    with caplog.at_level(logging.ERROR):
        result = asyncio.run(remove_from_tv(tv, ["MY-C0002-1"]))

    assert result is None
    assert [r for r in caplog.records if r.levelno == logging.ERROR]


def test_nothing_to_remove_does_not_touch_the_television():
    """An empty batch is the common case on a settled wall. The library's
    `available` asserts on an empty response, so a pointless round trip is a
    real failure risk and not only a wasted one."""
    tv = FakeTv(listed=["MY-C0002-1"])

    result = asyncio.run(delete_list_confirmed(tv, []))

    assert result.complete
    assert result.requested == ()
    assert tv.delete_calls == []
    assert tv.available_calls == []


def test_repeated_ids_are_asked_for_once_and_reported_in_order():
    tv = FakeTv(listed=["MY-C0002-2", "MY-C0002-1"], honours=[])

    result = asyncio.run(delete_list_confirmed(tv, ["MY-C0002-2", "MY-C0002-1", "MY-C0002-2"]))

    assert tv.delete_calls == [["MY-C0002-2", "MY-C0002-1"]]
    assert result.requested == ("MY-C0002-2", "MY-C0002-1")
    assert result.surviving == ("MY-C0002-2", "MY-C0002-1")


def test_other_artwork_on_the_television_is_not_mistaken_for_a_survivor():
    tv = FakeTv(listed=["MY-C0002-1", "MY-C0002-9"])

    result = asyncio.run(delete_list_confirmed(tv, ["MY-C0002-1"]))

    assert result.complete
    assert result.surviving == ()


def test_the_confirming_read_is_scoped_to_the_category_asked_for():
    tv = FakeTv(listed=["MY-C0004-1"])

    asyncio.run(delete_list_confirmed(tv, ["MY-C0004-1"], category="MY-C0004"))

    assert tv.available_calls == ["MY-C0004"]


def test_an_unconfirmable_removal_does_not_stop_the_caller(caplog):
    """The housekeeping pass has a catalogue save and pending uploads after it.
    Raising there would cost all of them to prevent some leftover images."""
    tv = FakeTv(listed=["MY-C0002-1"], confirm_raises=AssertionError())

    with caplog.at_level(logging.ERROR):
        result = asyncio.run(remove_from_tv(tv, ["MY-C0002-1"]))

    assert result is None
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1, "not stopping the caller must not mean saying nothing"
    assert "could not be confirmed" in errors[0].getMessage()


def test_a_confirmable_removal_passes_the_result_through():
    tv = FakeTv(listed=["MY-C0002-1", "MY-C0002-2"], honours=["MY-C0002-1"])

    result = asyncio.run(remove_from_tv(tv, ["MY-C0002-1", "MY-C0002-2"]))

    assert result is not None
    assert result.deleted == ("MY-C0002-1",)
    assert result.surviving == ("MY-C0002-2",)


def test_the_sentence_for_an_unknown_outcome_does_not_claim_a_count():
    """ "Confirmed 0 of 5" asserts the set kept all five. Nobody knows that."""
    unknown = describe_removal(None, 5)

    assert "could not confirm" in unknown
    assert "confirmed 0" not in unknown.lower()


def test_the_sentence_for_a_known_outcome_reports_the_confirmed_count():
    tv = FakeTv(listed=["MY-C0002-1", "MY-C0002-2"], honours=["MY-C0002-1"])
    result = asyncio.run(remove_from_tv(tv, ["MY-C0002-1", "MY-C0002-2"]))

    assert describe_removal(result, 2) == "the TV confirmed 1 of 2 image(s) removed"


def test_the_three_outcomes_read_differently():
    """A partial removal and an unknown one must not produce the same sentence —
    they are the two the old code collapsed into one."""
    tv_all = FakeTv(listed=["MY-C0002-1"])
    tv_none = FakeTv(listed=["MY-C0002-1"], honours=[])

    complete = describe_removal(asyncio.run(remove_from_tv(tv_all, ["MY-C0002-1"])), 1)
    kept = describe_removal(asyncio.run(remove_from_tv(tv_none, ["MY-C0002-1"])), 1)
    unknown = describe_removal(None, 1)

    assert len({complete, kept, unknown}) == 3


def test_the_reason_reaches_the_log_and_not_only_the_chain(caplog):
    """`str()` of an exception never renders `__cause__`, and an unattended
    loader is read through its journal. Without the cause in the message every
    failure reads alike — including a defect in this repo, which would look like
    a television that timed out and be continued past."""

    class ResponseError(Exception):
        pass

    tv = FakeTv(listed=["MY-C0002-1"], confirm_raises=ResponseError("error number 3"))

    with caplog.at_level(logging.ERROR):
        asyncio.run(remove_from_tv(tv, ["MY-C0002-1"]))

    logged = "\n".join(r.getMessage() for r in caplog.records if r.levelno == logging.ERROR)
    assert "ResponseError" in logged, "the cause's type must survive into the log line"
    assert "error number 3" in logged


def test_a_defect_in_this_repo_is_not_dressed_up_as_a_television_fault(caplog):
    """The cost of catching every cause is that they all look alike unless the
    message says otherwise. A TypeError is ours, not the set's."""
    tv = FakeTv(listed=["MY-C0002-1"], confirm_raises=TypeError("available() got an unexpected keyword"))

    with caplog.at_level(logging.ERROR):
        asyncio.run(remove_from_tv(tv, ["MY-C0002-1"]))

    logged = "\n".join(r.getMessage() for r in caplog.records if r.levelno == logging.ERROR)
    assert "TypeError" in logged


# -- what local state may forget after a removal --------------------------------
#
# The other half of the same defect. `delete_all_uploaded` cleared every
# `tv_content_id` regardless of what the set confirmed, and `sync_artsets_to_tv`
# selects upload candidates with exactly the test "has no tv_content_id" — so a
# survivor was marked never-uploaded and uploaded again, as a duplicate, onto a
# set with finite storage. The survivors were already being computed and warned
# about; nothing consumed them.


def test_only_the_ids_the_television_confirmed_gone_may_be_forgotten():
    """The regression test for the defect itself."""
    tv = FakeTv(listed=["MY-C0002-1", "MY-C0002-2", "MY-C0002-3"], honours=["MY-C0002-1", "MY-C0002-3"])

    result = asyncio.run(remove_from_tv(tv, ["MY-C0002-1", "MY-C0002-2", "MY-C0002-3"]))

    assert forgettable_ids(result) == frozenset({"MY-C0002-1", "MY-C0002-3"})
    assert "MY-C0002-2" not in forgettable_ids(result), "an image the TV still holds was marked not-uploaded"


def test_a_removal_nobody_could_confirm_forgets_nothing():
    """Clearing on no evidence is the same mistake made more quietly.

    It errs towards leaving an image marked uploaded, which costs a work its
    place on the set until the next confirmed pass — where the other error costs
    storage on every run and is invisible.
    """
    assert forgettable_ids(None) == frozenset()


def test_a_removal_the_television_honoured_in_full_forgets_all_of_it():
    """The ordinary case still has to work, or the fix trades one bug for another.

    Without this, refusing to forget anything at all would pass the two above.
    """
    tv = FakeTv(listed=["MY-C0002-1", "MY-C0002-2"])

    result = asyncio.run(remove_from_tv(tv, ["MY-C0002-1", "MY-C0002-2"]))

    assert forgettable_ids(result) == frozenset({"MY-C0002-1", "MY-C0002-2"})


def test_the_clearing_loop_keeps_a_survivor_marked_uploaded():
    """The rule applied the way `delete_all_uploaded` applies it.

    A copy of that loop, and deliberately so: the root suite cannot import
    `tvart` — it pulls in PIL and `samsungtvws`, which are legacy runtime
    dependencies this project does not install (see `pyproject.toml`). So what
    is asserted here is the *rule*, which is why the rule was moved into
    `forgettable_ids` rather than left inline where nothing could reach it.
    Mutating the loop in `tvart.py` will not turn this red; mutating the rule it
    calls will.
    """

    class _ArtFile:
        def __init__(self, tv_content_id):
            self.tv_content_id = tv_content_id

    tv = FakeTv(listed=["MY-C0002-1", "MY-C0002-2"], honours=["MY-C0002-1"])
    art_files = [_ArtFile("MY-C0002-1"), _ArtFile("MY-C0002-2"), _ArtFile(None)]

    forgettable = forgettable_ids(asyncio.run(remove_from_tv(tv, ["MY-C0002-1", "MY-C0002-2"])))
    for art_file in art_files:
        if art_file.tv_content_id in forgettable:
            art_file.tv_content_id = None

    assert [art_file.tv_content_id for art_file in art_files] == [None, "MY-C0002-2", None]
