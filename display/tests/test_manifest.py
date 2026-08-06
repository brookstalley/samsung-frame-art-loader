"""What this plane will and will not act on, and what it keeps when it refuses."""

import json
import logging
import os
from pathlib import Path

import pytest
from conftest import write_manifest

from display.manifest import (
    SUPPORTED_SCHEMA_MAJOR,
    ManifestUnreadable,
    ManifestVersionUnsupported,
    Watcher,
    parse,
)

FALLBACKS = {"rotation_interval_fallback": 180, "shuffle_fallback": True}


def a_document(**overrides: object) -> dict:
    document: dict = {
        "schema": {"major": 1, "minor": 0},
        "theme": {"id": "t1", "name": "A theme"},
        "rotation": {"interval_seconds": 90, "shuffle": False},
        "directive": {"sequence": 7, "pinned_work_id": None},
        "entries": [{"work_id": "w1", "render_path": "ready/w1.jpg", "label": {"title": "One"}}],
    }
    document.update(overrides)
    return document


def a_watcher(art_root: Path) -> Watcher:
    return Watcher(art_root / "theme-manifest.json", **FALLBACKS)


class TestParsing:
    def test_it_reads_what_curation_writes(self):
        manifest = parse(json.dumps(a_document()), **FALLBACKS)

        assert manifest.schema_major == 1
        assert manifest.theme_name == "A theme"
        assert manifest.rotation_interval_seconds == 90
        assert manifest.shuffle is False
        assert manifest.directive_sequence == 7
        assert [entry.work_id for entry in manifest.entries] == ["w1"]
        assert manifest.entries[0].label == {"title": "One"}

    def test_an_unknown_major_is_refused_by_version_and_not_by_shape(self):
        """A future major is *expected* to be shaped differently.

        Reporting "entries is missing" for a document whose own version says this
        reader should not be reading it sends whoever finds the line looking for a
        bug in the writer.
        """
        future = {"schema": {"major": SUPPORTED_SCHEMA_MAJOR + 1, "minor": 0}, "everything": "else"}

        with pytest.raises(ManifestVersionUnsupported) as refusal:
            parse(json.dumps(future), **FALLBACKS)

        assert refusal.value.major == SUPPORTED_SCHEMA_MAJOR + 1

    def test_an_unknown_minor_is_accepted_because_additive_changes_are_free(self):
        document = a_document(schema={"major": 1, "minor": 99})
        document["entries"][0]["something_new"] = "ignored"

        manifest = parse(json.dumps(document), **FALLBACKS)

        assert manifest.schema_minor == 99
        assert manifest.entries[0].work_id == "w1"

    @pytest.mark.parametrize(
        "document",
        [
            pytest.param("not json at all", id="not-json"),
            pytest.param(json.dumps([1, 2, 3]), id="not-an-object"),
            pytest.param(json.dumps({"entries": []}), id="no-schema"),
            pytest.param(json.dumps(a_document(entries="lots")), id="entries-not-a-list"),
            pytest.param(json.dumps(a_document(entries=[{"render_path": "ready/x.jpg"}])), id="entry-without-work-id"),
            pytest.param(json.dumps(a_document(entries=[{"work_id": "w1"}])), id="entry-without-render-path"),
            pytest.param(json.dumps(a_document(directive={"pinned_work_id": None})), id="no-sequence"),
            pytest.param(json.dumps(a_document(directive={"sequence": "3"})), id="sequence-not-an-integer"),
            pytest.param(json.dumps(a_document(directive={"sequence": 1, "pinned_work_id": 5})), id="pin-not-a-string"),
        ],
    )
    def test_a_malformed_manifest_is_refused_rather_than_guessed_at(self, document):
        with pytest.raises(ManifestUnreadable):
            parse(document, **FALLBACKS)

    def test_a_missing_sequence_is_refused_where_a_missing_pace_falls_back(self):
        """The asymmetry is the point, so it is asserted rather than left to reading.

        A pace this deployment does not know has a right answer it does know. A
        sequence has none: inventing one re-baselines the directive mechanism
        against a number the writer never published, which silently disarms
        `next` and `show_now` instead of reporting a broken file.
        """
        no_pace = parse(json.dumps(a_document(rotation={})), **FALLBACKS)
        assert no_pace.rotation_interval_seconds == 180
        assert no_pace.shuffle is True

        with pytest.raises(ManifestUnreadable):
            parse(json.dumps(a_document(directive={})), **FALLBACKS)

    def test_a_nonsense_interval_falls_back_rather_than_stopping_the_wall(self):
        manifest = parse(json.dumps(a_document(rotation={"interval_seconds": 0, "shuffle": True})), **FALLBACKS)

        assert manifest.rotation_interval_seconds == 180


class TestWatching:
    def test_it_reports_a_manifest_once_and_then_stays_quiet(self, art_root: Path):
        write_manifest(art_root, a_document())
        watcher = a_watcher(art_root)

        assert watcher.poll() is not None
        assert watcher.poll() is None
        assert watcher.poll() is None

    def test_a_rewrite_is_picked_up(self, art_root: Path):
        write_manifest(art_root, a_document())
        watcher = a_watcher(art_root)
        watcher.poll()

        write_manifest(art_root, a_document(directive={"sequence": 8, "pinned_work_id": None}))

        adopted = watcher.poll()
        assert adopted is not None
        assert adopted.directive_sequence == 8

    def test_a_refused_manifest_leaves_the_last_good_one_in_place(self, art_root: Path, caplog):
        write_manifest(art_root, a_document())
        watcher = a_watcher(art_root)
        good = watcher.poll()

        write_manifest(art_root, {"schema": {"major": 99, "minor": 0}})

        with caplog.at_level(logging.ERROR):
            assert watcher.poll() is None
        assert watcher.current is good
        assert "manifest.version_refused" in {record.__dict__.get("event") for record in caplog.records}

    def test_a_refusal_is_logged_once_per_file_rather_than_once_per_poll(self, art_root: Path, caplog):
        """At one poll a second, a repeated refusal would write 86,400 identical
        ERROR lines a day — which is how the *next* fault becomes unfindable."""
        write_manifest(art_root, {"schema": {"major": 99, "minor": 0}})
        watcher = a_watcher(art_root)

        with caplog.at_level(logging.ERROR):
            for _ in range(5):
                watcher.poll()

        refusals = [record for record in caplog.records if record.__dict__.get("event") == "manifest.version_refused"]
        assert len(refusals) == 1

    def test_a_manifest_that_has_never_appeared_is_not_an_error(self, art_root: Path, caplog):
        """A plane that has not published yet is a normal state on a fresh install,
        and this one holding still until it does is the availability norm working."""
        watcher = a_watcher(art_root)

        with caplog.at_level(logging.DEBUG):
            for _ in range(3):
                assert watcher.poll() is None

        levels = {record.levelno for record in caplog.records}
        assert logging.WARNING not in levels
        assert logging.ERROR not in levels
        assert len([r for r in caplog.records if r.__dict__.get("event") == "manifest.absent"]) == 1

    def test_two_writes_in_the_same_filesystem_tick_are_both_seen(self, art_root: Path):
        """`sync` and a `next` can land inside one second, and a coarse mtime would
        hide the second one forever — the wall would stop responding with nothing
        in the journal to say why."""
        target = art_root / "theme-manifest.json"
        write_manifest(art_root, a_document())
        watcher = a_watcher(art_root)
        watcher.poll()
        before = target.stat()

        second = a_document(directive={"sequence": 9, "pinned_work_id": None})
        second["entries"].append({"work_id": "w2", "render_path": "ready/w2.jpg", "label": {}})
        write_manifest(art_root, second)
        # Put the mtime back where it was, which is what a filesystem with
        # one-second resolution does to two writes inside one tick.
        os.utime(target, ns=(before.st_atime_ns, before.st_mtime_ns))

        adopted = watcher.poll()
        assert adopted is not None
        assert adopted.directive_sequence == 9
