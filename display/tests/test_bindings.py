"""What this television holds, what this device believes, and the gap between them.

Two defects shape everything here. The 2024 loader recorded a successful upload
with no content id, so a failure read as a success; and the television's single
user-upload category means anything this device cannot account for is an image
nobody will ever remove if this process does not.
"""

import logging
import sqlite3
from pathlib import Path

import pytest
from fakes import FakeTv

from display.daemon import Daemon
from display.state import DisplayState, UploadStatus


class TestTheStoreRefusesTheOldDefect:
    def test_a_row_cannot_claim_an_upload_without_naming_its_id(self, state: DisplayState):
        """The 2024 defect made unwritable rather than merely avoided.

        That version caught every exception, logged, and still reported success —
        recording no content id while its retry loop set `success = True`. Here
        the write itself is refused.
        """
        with pytest.raises(sqlite3.IntegrityError):
            state._connection.execute(
                "INSERT INTO tv_binding (id, artwork_id, tv_content_id, uploaded_at, upload_status) "
                "VALUES ('1', 'w1', NULL, '2026-01-01T00:00:00+00:00', 'uploaded')"
            )

    def test_a_failed_upload_is_a_different_state_from_never_having_tried(self, state: DisplayState):
        assert state.binding_for("w1") is None

        failed = state.record_upload_failure("w1")

        assert failed.upload_status is UploadStatus.FAILED
        assert failed.is_on_the_television is False
        assert state.binding_for("w1") is not None, "a failed upload left no trace to distinguish it from an untried one"

    def test_a_store_from_before_the_fingerprint_column_is_widened_not_rebuilt(self, settings, clock):
        """The migration path, exercised rather than assumed.

        A store written by the version before `render_fingerprint` existed must
        open, keep its rows, and gain the column. It must also survive being
        reopened — but see the comment below for what that second open does and
        does not prove, since the two are easy to conflate and only one of them is
        what this test buys.
        """
        path = settings.state_path
        old = sqlite3.connect(path)
        old.executescript("""
            CREATE TABLE tv_binding (
                id TEXT PRIMARY KEY, artwork_id TEXT NOT NULL UNIQUE, tv_content_id TEXT,
                tv_thumb_md5 TEXT, uploaded_at TEXT NOT NULL, upload_status TEXT NOT NULL
            );
            CREATE TABLE daemon_state (key TEXT PRIMARY KEY, value TEXT);
            INSERT INTO tv_binding VALUES ('1', 'w1', 'MY-OLD', NULL, '2026-01-01T00:00:00+00:00', 'uploaded');
            PRAGMA user_version = 1;
            """)
        old.commit()
        old.close()

        # Opened twice because a store must survive being reopened, not because the
        # second pass reaches the `ALTER`: the first stamps `user_version`, so the
        # second returns at the version guard. What covers the ALTER's idempotency
        # is the column-list check, which every fresh store in this suite exercises.
        for _ in range(2):
            with DisplayState(path, now=lambda: clock.as_clock().now()) as store:
                binding = store.binding_for("w1")
                assert binding.tv_content_id == "MY-OLD", "an existing row was lost by the widening"
                assert binding.render_fingerprint is None, "a row from before the column claimed a fingerprint"

    def test_an_upload_replaces_the_failure_before_it(self, state: DisplayState):
        state.record_upload_failure("w1")

        state.record_upload("w1", "MY-F0001")

        binding = state.binding_for("w1")
        assert binding.upload_status is UploadStatus.UPLOADED
        assert binding.tv_content_id == "MY-F0001"
        assert len(state.bindings()) == 1, "the retry left a second row for the same work"


class TestUploading:
    async def test_a_work_is_uploaded_before_it_is_shown(self, daemon: Daemon, tv: FakeTv, publish, state: DisplayState):
        publish(["w1"])

        await daemon.tick()

        binding = state.binding_for("w1")
        assert binding.is_on_the_television
        assert tv.holding[binding.tv_content_id].name == "w1.jpg"

    async def test_an_upload_that_fails_is_recorded_and_the_work_skipped(
        self, daemon: Daemon, tv: FakeTv, publish, state: DisplayState, caplog
    ):
        publish(["w1", "w2"])
        tv.refuse_uploads = True

        with caplog.at_level(logging.WARNING):
            await daemon.tick()

        assert tv.selected == [], "a work was shown that is not on the television"
        assert state.binding_for("w1").upload_status is UploadStatus.FAILED
        assert "binding.upload_failed" in {r.__dict__.get("event") for r in caplog.records}

    async def test_the_theme_fills_in_behind_the_first_picture(self, daemon: Daemon, tv: FakeTv, publish, state):
        """Uploads are carried one per pass rather than done in a batch.

        A fresh install with forty works and ten seconds an upload would leave the
        wall on yesterday's picture — and a curator pressing "next" with nothing
        happening — for five minutes, against a poll interval that is one second
        precisely because that wait is the one the product may not have.
        """
        publish(["w1", "w2", "w3", "w4"], interval_seconds=3600)

        await daemon.tick()
        assert len(tv.holding) == 2, "the first pass should show one work and carry one more"

        for _ in range(5):
            await daemon.tick()

        assert len(tv.holding) == 4
        assert len(tv.selected) == 1, "filling the theme in moved the wall"

    async def test_a_work_that_keeps_failing_is_not_retried_every_second(
        self, daemon: Daemon, tv: FakeTv, publish, state: DisplayState, clock, settings, caplog
    ):
        """A reachable set refusing one image is not the same fault as an asleep one.

        Only the second backs off with the connection. Without a wait of its own,
        the first costs a round trip, a WARNING and a rewritten row **every poll**
        — an unbounded small-write source on the SD card the observability
        strategy sizes writes for, and a journal whose rate limiter then drops the
        lines that matter.
        """
        publish(["w1"], interval_seconds=3600)
        tv.refuse_uploads = True

        with caplog.at_level(logging.WARNING):
            for _ in range(20):
                await daemon.tick()
                clock.advance(1)

        failures = [r for r in caplog.records if r.__dict__.get("event") == "binding.upload_failed"]
        assert len(failures) == 1, "a failing upload was retried on every pass"
        assert state.binding_for("w1").upload_status is UploadStatus.FAILED

    async def test_a_work_that_failed_is_tried_again_once_the_wait_is_up(
        self, daemon: Daemon, tv: FakeTv, publish, state: DisplayState, clock, settings
    ):
        """The wait is a wait, not a giving up: whatever was wrong may be fixed."""
        publish(["w1"], interval_seconds=3600)
        tv.refuse_uploads = True
        await daemon.tick()
        assert state.binding_for("w1").upload_status is UploadStatus.FAILED

        tv.refuse_uploads = False
        clock.advance(settings.upload_retry_seconds + 1)
        await daemon.tick()

        assert state.binding_for("w1").is_on_the_television

    async def test_a_re_rendered_work_is_sent_again(
        self, daemon: Daemon, tv: FakeTv, publish, art_root, state: DisplayState, clock
    ):
        """**The wall showing a composition the catalogue no longer holds.**

        `render_path` is `ready/{artwork_id}.jpg` and stable across re-renders, so
        a curator changing a mat colour rewrites the bytes under an unchanged name.
        Without a fingerprint the binding still reads `uploaded` and the television
        goes on showing the old picture indefinitely — and nothing in the product
        would ever say so, because every record agrees. `set_mat_color` and
        `regenerate` are live actions, so this is ordinary use.
        """
        publish(["w1"], interval_seconds=10)
        await daemon.tick()
        first = state.binding_for("w1").tv_content_id

        (art_root / "ready" / "w1.jpg").write_bytes(b"a different composition entirely")
        clock.advance(10)
        await daemon.tick()

        rebound = state.binding_for("w1")
        assert rebound.tv_content_id != first, "the television was never told the render changed"
        assert tv.holding[rebound.tv_content_id].read_bytes() == b"a different composition entirely"

    async def test_a_work_whose_render_is_untouched_is_not_sent_again(
        self, daemon: Daemon, tv: FakeTv, publish, state: DisplayState, clock
    ):
        """The other half, and the one that costs money if wrong: a fingerprint
        that changed spuriously would re-upload the whole theme every pass."""
        publish(["w1"], interval_seconds=10)
        await daemon.tick()
        first = state.binding_for("w1").tv_content_id

        for _ in range(5):
            clock.advance(10)
            await daemon.tick()

        assert state.binding_for("w1").tv_content_id == first
        assert len(tv.holding) == 1

    async def test_a_work_already_on_the_television_is_not_uploaded_again(self, daemon: Daemon, tv: FakeTv, publish, clock):
        publish(["w1", "w2"], interval_seconds=10)
        await daemon.tick()
        clock.advance(10)
        await daemon.tick()
        uploads = len(tv.holding)

        for _ in range(3):
            clock.advance(10)
            await daemon.tick()

        assert len(tv.holding) == uploads


class TestOrphans:
    async def test_an_upload_the_binding_table_cannot_account_for_is_removed(self, daemon: Daemon, tv: FakeTv, publish, caplog):
        """A fresh install clears the set, and that is the correct behaviour.

        Images uploaded by a previous generation are not assets to adopt: nothing
        joins them to a work, so adopting one would bind a work to a picture that
        is not the render its manifest entry names.
        """
        tv.holding["MY-LEGACY-1"] = Path("/gone/legacy-1.jpg")
        tv.holding["MY-LEGACY-2"] = Path("/gone/legacy-2.jpg")
        publish(["w1"])

        with caplog.at_level(logging.INFO):
            await daemon.tick()

        assert "MY-LEGACY-1" not in tv.holding
        assert "MY-LEGACY-2" not in tv.holding
        assert tv.removed == [("MY-LEGACY-1", "MY-LEGACY-2")]

    async def test_a_work_the_manifest_still_names_is_never_removed(self, daemon: Daemon, tv: FakeTv, publish, clock):
        publish(["w1", "w2"], interval_seconds=10)
        for _ in range(4):
            await daemon.tick()
            clock.advance(10)
        held_before = set(tv.holding)

        publish(["w1", "w2"], sequence=1, interval_seconds=10)  # a `sync` rewrite
        await daemon.tick()

        assert set(tv.holding) == held_before
        assert tv.removed == []

    async def test_a_binding_the_set_no_longer_lists_is_re_uploaded(
        self, daemon: Daemon, tv: FakeTv, publish, state: DisplayState, caplog
    ):
        """Somebody removed it from the phone app. Selecting the stale id would
        fail against the set, so the row is marked orphaned and re-uploaded."""
        publish(["w1"])
        await daemon.tick()
        vanished = state.binding_for("w1").tv_content_id
        del tv.holding[vanished]

        publish(["w1"], sequence=1)
        with caplog.at_level(logging.WARNING):
            await daemon.tick()
            await daemon.tick()

        assert "binding.orphaned" in {r.__dict__.get("event") for r in caplog.records}
        rebound = state.binding_for("w1")
        assert rebound.is_on_the_television
        assert rebound.tv_content_id != vanished
        assert rebound.tv_content_id in tv.holding

    async def test_a_binding_the_set_refuses_mid_rotation_is_rebound_rather_than_retried_forever(
        self, daemon: Daemon, tv: FakeTv, publish, state: DisplayState, clock, caplog
    ):
        """The wall-freezing case, and the reason a refusal is not read as an outage.

        Somebody removes one image from the phone app. The manifest does not
        change, so nothing re-checks the binding — and a daemon that treated the
        refusal as "the television is asleep" would back off and retry the same
        doomed id forever, with the wall stuck on the previous picture.
        """
        publish(["w1", "w2"], interval_seconds=10)
        await daemon.tick()
        await daemon.tick()
        stale = state.binding_for("w2").tv_content_id
        del tv.holding[stale]  # removed from the phone app; no manifest rewrite

        clock.advance(10)
        with caplog.at_level(logging.WARNING):
            await daemon.tick()

        assert tv.on_the_wall.name == "w2.jpg", "the wall froze on a binding the set had forgotten"
        assert state.binding_for("w2").tv_content_id != stale
        assert "binding.orphaned" in {r.__dict__.get("event") for r in caplog.records}

    async def test_a_refusal_the_set_cannot_explain_is_still_an_outage(
        self, daemon: Daemon, tv: FakeTv, publish, state: DisplayState, clock, settings
    ):
        """The other side of that judgement, so the fix cannot swallow a real fault.

        If the set still lists the id it just refused, the binding is not the
        problem and inventing a re-upload would paper over whatever is.
        """
        publish(["w1"], interval_seconds=10)
        await daemon.tick()
        content_id = state.binding_for("w1").tv_content_id

        clock.advance(10)
        tv.refuse_selection_of.add(content_id)  # still listed, still refused
        wait = await daemon.tick()

        assert wait == settings.tv_retry_min_seconds, "a refusal the set could not explain was not treated as an outage"
        assert state.binding_for("w1").tv_content_id == content_id, "a live binding was thrown away"

    async def test_an_unconfirmable_removal_is_reported_as_unknown_and_retried(self, daemon: Daemon, tv: FakeTv, publish, caplog):
        """The library discards the reply to a removal, so claiming either outcome
        would be a guess. Unknown is reported as unknown."""
        tv.holding["MY-LEGACY-1"] = Path("/gone/legacy-1.jpg")
        tv.removal_unconfirmable = True
        publish(["w1"])

        with caplog.at_level(logging.WARNING):
            await daemon.tick()

        assert "MY-LEGACY-1" in tv.holding
        assert "tv.orphan_removal_unconfirmed" in {r.__dict__.get("event") for r in caplog.records}

        tv.removal_unconfirmable = False
        publish(["w1"], sequence=1)
        await daemon.tick()
        assert "MY-LEGACY-1" not in tv.holding, "the next adoption did not try again"
