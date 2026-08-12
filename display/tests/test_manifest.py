"""What this plane will and will not act on, and what it keeps when it refuses."""

import json
import logging
import os
from pathlib import Path

import pytest
from conftest import WALL_ID, write_manifest

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


def a_watcher(art_root: Path, wall_id: str = WALL_ID) -> Watcher:
    """A watcher over one wall's manifest — the only file it will ever open."""
    return Watcher(art_root / f"theme-manifest-{wall_id}.json", **FALLBACKS)


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

    def test_a_manifest_that_is_not_valid_utf8_is_refused_rather_than_fatal(self, art_root: Path, caplog):
        """`UnicodeDecodeError` is a `ValueError`, not an `OSError`.

        So it escaped the read's own except clause and every frame above it,
        taking the daemon down over exactly the kind of malformed file this
        module exists to refuse — a truncated write from a filesystem that lost
        power mid-`replace` produces it.
        """
        write_manifest(art_root, a_document())
        watcher = a_watcher(art_root)
        good = watcher.poll()

        (art_root / f"theme-manifest-{WALL_ID}.json").write_bytes(b'{"schema": {"major": 1}, "entries": [], "\xff\xfe": 1}')

        with caplog.at_level(logging.ERROR):
            assert watcher.poll() is None
        assert watcher.current is good
        assert "manifest.not_text" in {r.__dict__.get("event") for r in caplog.records}

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
        target = art_root / f"theme-manifest-{WALL_ID}.json"
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


class TestAnUnreadableManifestIsSaidOnce:
    """The third instance of a class this plane has fixed twice already.

    The faults that reach the `OSError` arm do not clear on their own — EIO from a
    failing card, EACCES, ESTALE on a dropped mount — so at a one-second poll an
    unguarded WARNING is 86,400 identical lines a day, into a journal that
    rate-limits and whose dropped lines are the ERRORs this plane depends on.
    """

    def test_a_persistent_stat_failure_is_reported_once(self, tmp_path, caplog, monkeypatch):
        path = tmp_path / "theme-manifest.json"
        path.write_text("{}")
        watcher = Watcher(path, rotation_interval_fallback=180, shuffle_fallback=False)

        def unreadable(*_args, **_kwargs):
            raise OSError(5, "Input/output error")

        monkeypatch.setattr(Path, "stat", unreadable)
        with caplog.at_level(logging.WARNING):
            for _ in range(20):
                watcher.poll()

        reports = [r for r in caplog.records if getattr(r, "event", None) == "manifest.unstatable"]
        assert len(reports) == 1, f"an unreadable manifest was reported {len(reports)} times"

    def test_the_recovery_is_said_too(self, tmp_path, caplog, monkeypatch):
        """Otherwise the WARNING stands unresolved in the journal for ever."""
        path = tmp_path / "theme-manifest.json"
        path.write_text("{}")
        watcher = Watcher(path, rotation_interval_fallback=180, shuffle_fallback=False)

        real_stat = Path.stat
        broken = True

        def sometimes(self, *args, **kwargs):
            if broken:
                raise OSError(5, "Input/output error")
            return real_stat(self, *args, **kwargs)

        monkeypatch.setattr(Path, "stat", sometimes)
        watcher.poll()
        broken = False
        with caplog.at_level(logging.INFO):
            watcher.poll()

        assert [r for r in caplog.records if getattr(r, "event", None) == "manifest.statable"]


class TestOneManifestPerWall:
    """A display serves one room, and cannot read another's.

    **The mechanism is the path, not a check.** Each wall's manifest is
    `theme-manifest-<wall id>.json`, and this process stats exactly the one its
    `WALL_ID` names — so the other rooms' documents are files it never opens.
    That is what makes "the wall shows another room's pictures" structurally
    impossible rather than defended against, and it is why the decision was one
    file per wall instead of one file with a section per wall.

    It matters because a shared file's other failure was silent in both
    directions: curation publishing the study's theme would overwrite the living
    room's document, and the living room's display had no way to notice that the
    file it was reading had stopped being about it.
    """

    def test_it_adopts_the_manifest_for_the_wall_it_serves(self, art_root: Path):
        write_manifest(art_root, a_document(), wall_id=WALL_ID)

        adopted = a_watcher(art_root, WALL_ID).poll()

        assert adopted is not None
        assert adopted.directive_sequence == 7

    def test_a_manifest_for_a_wall_it_does_not_serve_is_not_acted_on(self, art_root: Path, caplog):
        """Published for the study; this device serves the living room.

        Not adopted, and — the half that matters — reported as *absent* rather
        than as anything having gone wrong. A device waiting for a manifest that
        has not been published yet is an ordinary state, and another room's file
        sitting beside it does not change what this one is waiting for.
        """
        write_manifest(art_root, a_document(), wall_id="study")

        with caplog.at_level(logging.INFO):
            assert a_watcher(art_root, WALL_ID).poll() is None

        assert "manifest.absent" in {record.__dict__.get("event") for record in caplog.records}

    def test_a_rewrite_of_another_wall_does_not_wake_this_one(self, art_root: Path):
        """The reason the decision names the mtime poll.

        A shared file would make every wall's display re-read and re-derive on
        every other wall's change, at a poll a second — and would make "the
        manifest's sequence" ambiguous exactly where the coalescing and
        sequence-regression rules need it to be a single number.
        """
        write_manifest(art_root, a_document(), wall_id=WALL_ID)
        watcher = a_watcher(art_root, WALL_ID)
        watcher.poll()

        for sequence in range(8, 12):
            write_manifest(art_root, a_document(directive={"sequence": sequence, "pinned_work_id": None}), wall_id="study")

        assert watcher.poll() is None
        assert watcher.current is not None
        assert watcher.current.directive_sequence == 7


async def test_the_daemon_shows_its_own_walls_theme_and_ignores_another_walls(daemon, tv, art_root: Path):
    """End to end over the double: two manifests in one art root, one wall each.

    The living room's display is driven by the living room's document and by
    nothing else — the study's is present, newer, and names entirely different
    works, and none of them reach the television.
    """
    write_manifest(art_root, a_document(entries=[_entry("mine")]), wall_id=WALL_ID)
    write_manifest(art_root, a_document(entries=[_entry("not-mine")]), wall_id="study")
    for work_id in ("mine", "not-mine"):
        (art_root / "ready" / f"{work_id}.jpg").write_bytes(b"not really a jpeg")

    await daemon.tick()

    assert tv.on_the_wall.name == "mine.jpg"
    assert [path.name for path in (tv.holding[content] for content in tv.selected)] == ["mine.jpg"]


async def test_a_daemon_whose_wall_has_no_manifest_shows_nothing_rather_than_someone_elses(daemon, tv, art_root: Path):
    """A manifest for an unknown wall is not acted on — it is not a fallback.

    A device pointed at a wall nothing has published for waits, exactly as it
    waits on a fresh install. Reaching for whatever manifest *is* there would
    turn a mistyped `WALL_ID` from a wall that never lights up into a wall
    showing another room's pictures, which is the failure that has no symptom.
    """
    write_manifest(art_root, a_document(entries=[_entry("not-mine")]), wall_id="study")
    (art_root / "ready" / "not-mine.jpg").write_bytes(b"not really a jpeg")

    await daemon.tick()

    assert tv.selected == []


def _entry(work_id: str) -> dict:
    return {"work_id": work_id, "render_path": f"ready/{work_id}.jpg", "label": {"title": work_id}}
