"""The heartbeat this plane writes, and the atomicity curation's polling needs.

The cross-plane half — that both planes spell the filename and the instant the
same way — is asserted by `tests/preferences/test_heartbeat_contract.py` in the
repository-root suite, which reads both sources with AST. It lives there because
neither plane can import the other: the isolation guard forbids display reaching
into curation, and rightly, since that is the second channel the whole norm
exists to prevent. What is pinned here is the shape; what is pinned there is the
agreement.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from display.heartbeat import HEARTBEAT_FILENAME, INTERVAL_SECONDS, REPORTED_AT_KEY, Health, path_in, write

WHEN = datetime(2026, 8, 8, 3, 14, 15, tzinfo=UTC)


class TestTheContractWithCuration:
    """The two names a reader built before this writer depends on."""

    def test_it_is_written_where_curation_looks(self, tmp_path: Path):
        write(tmp_path, Health(), reported_at=WHEN)

        assert (tmp_path / "display-heartbeat.json").is_file()
        assert HEARTBEAT_FILENAME == "display-heartbeat.json"

    def test_the_instant_is_spelled_reported_at(self, tmp_path: Path):
        """A writer that called this `timestamp` would look down while running perfectly."""
        write(tmp_path, Health(), reported_at=WHEN)

        document = json.loads((tmp_path / HEARTBEAT_FILENAME).read_text())

        assert REPORTED_AT_KEY == "reported_at"
        assert document["reported_at"] == WHEN.isoformat()

    def test_the_instant_carries_its_offset(self, tmp_path: Path):
        """An instant with no zone cannot be aged against `now` without guessing one."""
        write(tmp_path, Health(), reported_at=WHEN)

        document = json.loads((tmp_path / HEARTBEAT_FILENAME).read_text())
        parsed = datetime.fromisoformat(document["reported_at"])

        assert parsed.tzinfo is not None
        assert parsed == WHEN


class TestWhatItSays:
    def test_the_state_it_is_given_reaches_the_document(self, tmp_path: Path):
        health = Health(
            manifest_version=7,
            theme_id="0cee2750-7209-4ab2-92b0-c8c2ef0b9030",
            current_work_id="abe9fb42-c380-4d6b-aae6-4ef77deeb85c",
            announced_content_id="MY_F1201",
            television_reachable=True,
            television_showing_art=True,
            label_surface_working=True,
            last_error=None,
        )

        write(tmp_path, health, reported_at=WHEN)
        document = json.loads((tmp_path / HEARTBEAT_FILENAME).read_text())

        assert document["manifest_version"] == 7
        assert document["current_work_id"] == "abe9fb42-c380-4d6b-aae6-4ef77deeb85c"
        assert document["announced_content_id"] == "MY_F1201"
        assert document["television_showing_art"] is True

    def test_a_plane_that_knows_nothing_yet_says_so_rather_than_inventing(self, tmp_path: Path):
        """Nulls, not zeroes and not `false`. "Not yet known" is a real answer here."""
        write(tmp_path, Health(), reported_at=WHEN)

        document = json.loads((tmp_path / HEARTBEAT_FILENAME).read_text())

        assert document["manifest_version"] is None
        assert document["television_reachable"] is None
        assert document["last_error"] is None

    def test_a_device_with_no_label_surface_is_not_a_broken_one(self, tmp_path: Path):
        """A valid configuration, so it reports null rather than false."""
        write(tmp_path, Health(label_surface_working=None), reported_at=WHEN)

        document = json.loads((tmp_path / HEARTBEAT_FILENAME).read_text())

        assert document["label_surface_working"] is None

    def test_the_last_error_survives_a_good_pass(self, tmp_path: Path):
        """Held by the caller, so a plane failing every other minute cannot look fine."""
        write(tmp_path, Health(last_error="the television refused the art channel"), reported_at=WHEN)

        document = json.loads((tmp_path / HEARTBEAT_FILENAME).read_text())

        assert document["last_error"] == "the television refused the art channel"

    def test_it_states_facts_and_never_a_verdict(self, tmp_path: Path):
        """No `healthy`, no `status`, no colour. The reader judges; this reports."""
        write(tmp_path, Health(), reported_at=WHEN)

        document = json.loads((tmp_path / HEARTBEAT_FILENAME).read_text())

        assert not {"healthy", "status", "ok", "state", "severity"} & set(document)

    def test_non_ascii_survives_the_round_trip(self, tmp_path: Path):
        write(tmp_path, Health(last_error="could not render Natureza-morta com bromélia"), reported_at=WHEN)

        document = json.loads((tmp_path / HEARTBEAT_FILENAME).read_text())

        assert "bromélia" in document["last_error"]


class TestWritingItSafely:
    def test_it_replaces_the_previous_one(self, tmp_path: Path):
        write(tmp_path, Health(manifest_version=1), reported_at=WHEN)
        write(tmp_path, Health(manifest_version=2), reported_at=WHEN)

        document = json.loads((tmp_path / HEARTBEAT_FILENAME).read_text())

        assert document["manifest_version"] == 2

    def test_no_temporary_file_is_left_behind(self, tmp_path: Path):
        write(tmp_path, Health(), reported_at=WHEN)

        assert [p.name for p in tmp_path.iterdir()] == [HEARTBEAT_FILENAME]

    def test_a_reader_never_sees_a_partial_document(self, tmp_path: Path):
        """Curation polls this on its own schedule, so a truncating write would
        show it half a file — which it correctly reports as this plane being
        broken. Asserted by reading between every write in a long run."""
        for version in range(25):
            write(tmp_path, Health(manifest_version=version), reported_at=WHEN)
            document = json.loads((tmp_path / HEARTBEAT_FILENAME).read_text())
            assert document["manifest_version"] == version

    def test_a_failure_to_write_is_raised_rather_than_swallowed(self, tmp_path: Path):
        """The caller knows a heartbeat is an annotation; this module does not."""
        missing = tmp_path / "no-such-directory"

        with pytest.raises(OSError):
            write(missing, Health(), reported_at=WHEN)

    def test_a_failed_write_leaves_no_temporary_file_in_a_live_root(self, tmp_path: Path):
        (tmp_path / HEARTBEAT_FILENAME).write_text('{"reported_at": "2026-08-08T00:00:00+00:00"}\n')
        # A directory where the heartbeat belongs: the rename cannot succeed, so
        # the write fails after the temp file exists.
        blocked = tmp_path / "blocked"
        blocked.mkdir()
        (blocked / HEARTBEAT_FILENAME).mkdir()

        with pytest.raises(OSError):
            write(blocked, Health(), reported_at=WHEN)

        assert not (blocked / f"{HEARTBEAT_FILENAME}.tmp").exists()


class TestTheInterval:
    def test_it_is_slower_than_the_wall_would_be_and_faster_than_a_rotation(self):
        """Both bounds, because each has a different failure and both are silent.

        Faster and this becomes an unbounded small-write source on the SD card the
        catalogue shares. Slower than the rotation default and it names works the
        wall has already left.
        """
        assert INTERVAL_SECONDS == 60.0
        assert INTERVAL_SECONDS > 1.0, "at the poll interval this would be ~86,400 writes a day, forever"
        assert INTERVAL_SECONDS < 180.0, "slower than the default rotation would report works already gone"


def test_the_path_is_derived_from_the_art_root(tmp_path: Path):
    assert path_in(tmp_path) == tmp_path / HEARTBEAT_FILENAME
