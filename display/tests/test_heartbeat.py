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
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from display.heartbeat import (
    HEARTBEAT_FILENAME_TEMPLATE,
    INTERVAL_SECONDS,
    REPORTED_AT_KEY,
    Health,
    path_in,
    write,
)

#: The wall every heartbeat in this module is written for. A literal rather
#: than a real UUID because what the filename has to carry is *a* wall id, and
#: a readable one makes the assertions below say what they mean.
WALL = "living-room"
HEARTBEAT_FILENAME = HEARTBEAT_FILENAME_TEMPLATE.format(wall_id=WALL)

WHEN = datetime(2026, 8, 8, 3, 14, 15, tzinfo=UTC)


class TestTheContractWithCuration:
    """The two names a reader built before this writer depends on."""

    def test_it_is_written_where_curation_looks(self, tmp_path: Path):
        write(tmp_path, Health(), wall_id=WALL, reported_at=WHEN)

        assert (tmp_path / "display-heartbeat-living-room.json").is_file()
        assert HEARTBEAT_FILENAME_TEMPLATE == "display-heartbeat-{wall_id}.json"

    def test_the_instant_is_spelled_reported_at(self, tmp_path: Path):
        """A writer that called this `timestamp` would look down while running perfectly."""
        write(tmp_path, Health(), wall_id=WALL, reported_at=WHEN)

        document = json.loads((tmp_path / HEARTBEAT_FILENAME).read_text())

        assert REPORTED_AT_KEY == "reported_at"
        assert document["reported_at"] == WHEN.isoformat()

    def test_the_instant_carries_its_offset(self, tmp_path: Path):
        """An instant with no zone cannot be aged against `now` without guessing one."""
        write(tmp_path, Health(), wall_id=WALL, reported_at=WHEN)

        document = json.loads((tmp_path / HEARTBEAT_FILENAME).read_text())
        parsed = datetime.fromisoformat(document["reported_at"])

        assert parsed.tzinfo is not None
        assert parsed == WHEN


class TestWhatItSays:
    def test_the_state_it_is_given_reaches_the_document(self, tmp_path: Path):
        health = Health(
            manifest_schema="1.0",
            theme_id="0cee2750-7209-4ab2-92b0-c8c2ef0b9030",
            current_work_id="abe9fb42-c380-4d6b-aae6-4ef77deeb85c",
            announced_content_id="MY_F1201",
            television_reachable=True,
            television_showing_art=True,
            label_surface_working=True,
            last_error=None,
        )

        write(tmp_path, health, wall_id=WALL, reported_at=WHEN)
        document = json.loads((tmp_path / HEARTBEAT_FILENAME).read_text())

        assert document["manifest_schema"] == "1.0"
        assert document["current_work_id"] == "abe9fb42-c380-4d6b-aae6-4ef77deeb85c"
        assert document["announced_content_id"] == "MY_F1201"
        assert document["television_showing_art"] is True

    def test_a_plane_that_knows_nothing_yet_says_so_rather_than_inventing(self, tmp_path: Path):
        """Nulls, not zeroes and not `false`. "Not yet known" is a real answer here."""
        write(tmp_path, Health(), wall_id=WALL, reported_at=WHEN)

        document = json.loads((tmp_path / HEARTBEAT_FILENAME).read_text())

        assert document["manifest_schema"] is None
        assert document["television_reachable"] is None
        assert document["last_error"] is None

    def test_a_device_with_no_label_surface_is_not_a_broken_one(self, tmp_path: Path):
        """A valid configuration, so it reports null rather than false."""
        write(tmp_path, Health(label_surface_working=None), wall_id=WALL, reported_at=WHEN)

        document = json.loads((tmp_path / HEARTBEAT_FILENAME).read_text())

        assert document["label_surface_working"] is None

    def test_the_last_error_survives_a_good_pass(self, tmp_path: Path):
        """Held by the caller, so a plane failing every other minute cannot look fine."""
        write(tmp_path, Health(last_error="the television refused the art channel"), wall_id=WALL, reported_at=WHEN)

        document = json.loads((tmp_path / HEARTBEAT_FILENAME).read_text())

        assert document["last_error"] == "the television refused the art channel"

    def test_it_states_facts_and_never_a_verdict(self, tmp_path: Path):
        """No `healthy`, no `status`, no colour. The reader judges; this reports."""
        write(tmp_path, Health(), wall_id=WALL, reported_at=WHEN)

        document = json.loads((tmp_path / HEARTBEAT_FILENAME).read_text())

        assert not {"healthy", "status", "ok", "state", "severity"} & set(document)

    def test_non_ascii_survives_the_round_trip(self, tmp_path: Path):
        write(tmp_path, Health(last_error="could not render Natureza-morta com bromélia"), wall_id=WALL, reported_at=WHEN)

        document = json.loads((tmp_path / HEARTBEAT_FILENAME).read_text())

        assert "bromélia" in document["last_error"]


class TestWritingItSafely:
    def test_it_replaces_the_previous_one(self, tmp_path: Path):
        write(tmp_path, Health(manifest_schema="1.0"), wall_id=WALL, reported_at=WHEN)
        write(tmp_path, Health(manifest_schema="2.0"), wall_id=WALL, reported_at=WHEN)

        document = json.loads((tmp_path / HEARTBEAT_FILENAME).read_text())

        assert document["manifest_schema"] == "2.0"

    def test_no_temporary_file_is_left_behind(self, tmp_path: Path):
        write(tmp_path, Health(), wall_id=WALL, reported_at=WHEN)

        assert [p.name for p in tmp_path.iterdir()] == [HEARTBEAT_FILENAME]

    def test_a_reader_never_sees_a_partial_document(self, tmp_path: Path):
        """Curation polls this on its own schedule, so a truncating write would
        show it half a file — which it correctly reports as this plane being
        broken. Asserted by reading between every write in a long run."""
        for version in range(25):
            write(tmp_path, Health(manifest_schema=f"1.{version}"), wall_id=WALL, reported_at=WHEN)
            document = json.loads((tmp_path / HEARTBEAT_FILENAME).read_text())
            assert document["manifest_schema"] == f"1.{version}"

    def test_the_bytes_reach_the_disk_before_the_rename_does(self, tmp_path: Path, monkeypatch):
        """The durability half, which has no observable behaviour to assert on.

        **A mechanism test, deliberately, and the only honest kind here.** On an
        SD-card Pi with no UPS a rename can land before the bytes it renames do,
        leaving a heartbeat that exists, is the right size, and is empty — a
        failure that appears only after a power cut, which is exactly when
        somebody reads this file to find out what happened. Nothing about that is
        reproducible in a test process, so what is pinned is the *ordering* the
        guarantee rests on: fsync happens, and it happens before the rename.

        Written because a mutation sweep removed the fsync and every other test
        still passed — the branch was defended by nobody.
        """
        events: list[str] = []
        real_fsync, real_replace = os.fsync, os.replace
        monkeypatch.setattr(os, "fsync", lambda fd: (events.append("fsync"), real_fsync(fd))[1])
        monkeypatch.setattr(os, "replace", lambda src, dst: (events.append("replace"), real_replace(src, dst))[1])

        write(tmp_path, Health(), wall_id=WALL, reported_at=WHEN)

        assert events == ["fsync", "replace"], "the heartbeat was renamed into place without being flushed to disk first"

    def test_a_failure_to_write_is_raised_rather_than_swallowed(self, tmp_path: Path):
        """The caller knows a heartbeat is an annotation; this module does not."""
        missing = tmp_path / "no-such-directory"

        with pytest.raises(OSError):
            write(missing, Health(), wall_id=WALL, reported_at=WHEN)

    def test_a_failed_write_leaves_no_temporary_file_in_a_live_root(self, tmp_path: Path):
        (tmp_path / HEARTBEAT_FILENAME).write_text('{"reported_at": "2026-08-08T00:00:00+00:00"}\n')
        # A directory where the heartbeat belongs: the rename cannot succeed, so
        # the write fails after the temp file exists.
        blocked = tmp_path / "blocked"
        blocked.mkdir()
        (blocked / HEARTBEAT_FILENAME).mkdir()

        with pytest.raises(OSError):
            write(blocked, Health(), wall_id=WALL, reported_at=WHEN)

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


def test_the_path_is_derived_from_the_art_root_and_the_wall(tmp_path: Path):
    assert path_in(tmp_path, WALL) == tmp_path / "display-heartbeat-living-room.json"


def test_two_walls_report_into_two_files(tmp_path: Path):
    """The property one shared heartbeat could not have.

    Health has to be able to name *which* wall is silent. With one file the
    second display would overwrite the first's report every minute, so a wall
    that had gone dark would read exactly like a wall that was fine.
    """
    write(tmp_path, Health(theme_id="winter"), wall_id="living-room", reported_at=WHEN)
    write(tmp_path, Health(theme_id="summer"), wall_id="study", reported_at=WHEN)

    living = json.loads(path_in(tmp_path, "living-room").read_text())
    study = json.loads(path_in(tmp_path, "study").read_text())

    assert (living["theme_id"], study["theme_id"]) == ("winter", "summer")
