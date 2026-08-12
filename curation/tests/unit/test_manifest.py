"""The manifest build — what reaches the wall, what does not, and why.

Membership in the manifest *is* catalogue readiness, so this file is where that
rule is pinned. The exclusion assertions carry the weight: a builder that only
returned a list would pass every entry-count check here and still be an
incomplete implementation of the design it comes from, because a work can sit in
a theme and never reach the wall with nothing saying so.
"""

import json
import os
from dataclasses import replace

import pytest

from curation.manifest import builder
from curation.manifest.builder import (
    SCHEMA_MAJOR,
    ExclusionReason,
    write_atomically,
)
from curation.persistence.records import (
    FetchStatus,
    RenditionKind,
)
from curation.services.errors import ServiceError


@pytest.fixture
def theme_of(display):
    """A theme holding the given works, in the order given."""

    def _theme(*works, name="Late night"):
        theme = display.add_theme(name=name)
        for position, work in enumerate(works):
            display.add_to_theme(theme_id=theme.id, artwork_id=work.id, position=position)
        return theme

    return _theme


# -- readiness, one cause at a time --------------------------------------------


def test_a_work_with_everything_it_needs_reaches_the_wall(display, ready_work, theme_of, wall_id):
    work = ready_work()
    theme = theme_of(work)

    build = display.build_manifest(wall_id, theme.id)

    assert [entry.work_id for entry in build.entries] == [work.id]
    assert build.exclusions == []


def test_an_archived_work_leaves_the_manifest_but_stays_in_the_theme(service, display, ready_work, theme_of, wall_id):
    """Theme membership is curatorial; readiness is technical. Archiving moves one, not the other."""
    work = ready_work()
    theme = theme_of(work)
    service.archive_artwork(work.id)

    build = display.build_manifest(wall_id, theme.id)

    assert build.entries == []
    assert [exclusion.reason for exclusion in build.exclusions] == [ExclusionReason.ARCHIVED]
    # Still a member — the curator said it belongs here and nothing has unsaid it.
    assert [detail.artwork.id for detail in display.theme_works(theme.id)] == [work.id]


def test_a_work_with_no_acquired_original_is_excluded_and_named(display, ready_work, theme_of, wall_id):
    theme = theme_of(ready_work(original=False))

    build = display.build_manifest(wall_id, theme.id)

    assert build.entries == []
    assert [exclusion.reason for exclusion in build.exclusions] == [ExclusionReason.NO_ORIGINAL]
    assert "acquired" in build.exclusions[0].detail


def test_a_work_that_has_not_been_rendered_is_excluded_and_named(display, ready_work, theme_of, wall_id):
    theme = theme_of(ready_work(rendition=False))

    build = display.build_manifest(wall_id, theme.id)

    assert [exclusion.reason for exclusion in build.exclusions] == [ExclusionReason.NO_RENDITION]


def test_a_work_with_no_current_mat_colour_is_excluded_and_named(display, ready_work, theme_of, wall_id):
    theme = theme_of(ready_work(mat=False))

    build = display.build_manifest(wall_id, theme.id)

    assert [exclusion.reason for exclusion in build.exclusions] == [ExclusionReason.NO_MAT_COLOR]


def test_a_render_made_from_an_earlier_acquisition_is_excluded_as_stale(service, display, ready_work, theme_of, wall_id):
    """Re-acquiring leaves the old render in place, and showing it would put the previous image on the wall."""
    work = ready_work()
    theme = theme_of(work)
    source = service.list_sources(work.id)[0]
    service.record_original(
        artwork_id=work.id,
        source_id=source.id,
        path=f"raw/{work.id}.tif",
        width=6000,
        height=4000,
        byte_size=90_000_000,
        content_hash="hash-2",
        fetch_status=FetchStatus.OK,
    )

    build = display.build_manifest(wall_id, theme.id)

    assert build.entries == []
    assert [exclusion.reason for exclusion in build.exclusions] == [ExclusionReason.STALE_RENDITION]


def test_regenerating_the_render_returns_the_work_to_the_wall(service, display, ready_work, theme_of, wall_id):
    """The exclusion is a state, not a verdict — the multi-hop step that proves it clears."""
    work = ready_work()
    theme = theme_of(work)
    source = service.list_sources(work.id)[0]
    service.record_original(
        artwork_id=work.id,
        source_id=source.id,
        path=f"raw/{work.id}.tif",
        width=6000,
        height=4000,
        byte_size=90_000_000,
        content_hash="hash-2",
        fetch_status=FetchStatus.OK,
    )
    assert display.build_manifest(wall_id, theme.id).entries == []

    service.record_rendition(
        artwork_id=work.id,
        kind=RenditionKind.TV_DISPLAY,
        target_width=3840,
        target_height=2160,
        path=f"ready/{work.id}.jpg",
    )

    build = display.build_manifest(wall_id, theme.id)
    assert [entry.work_id for entry in build.entries] == [work.id]
    assert build.exclusions == []


def test_a_thumbnail_is_not_a_television_render(service, display, ready_work, theme_of, wall_id):
    """The wall needs the 4K presentation with the mat composed in, not any derived image."""
    work = ready_work(rendition=False)
    theme = theme_of(work)
    service.record_rendition(
        artwork_id=work.id,
        kind=RenditionKind.THUMBNAIL,
        target_width=400,
        target_height=300,
        path=f"tv-thumbs/{work.id}.jpg",
    )

    build = display.build_manifest(wall_id, theme.id)

    assert [exclusion.reason for exclusion in build.exclusions] == [ExclusionReason.NO_RENDITION]


def test_every_member_is_accounted_for_as_an_entry_or_an_exclusion(display, ready_work, theme_of, wall_id):
    """The property that makes the report trustworthy: nothing is silently dropped."""
    theme = theme_of(ready_work("Nighthawks"), ready_work("Chop Suey", original=False), ready_work("Automat", mat=False))

    build = display.build_manifest(wall_id, theme.id)

    assert len(build.entries) == 1
    assert len(build.exclusions) == 2
    assert build.considered == 3
    assert {exclusion.title for exclusion in build.exclusions} == {"Chop Suey", "Automat"}


def test_an_exclusion_names_the_work_a_curator_would_look_for(display, ready_work, theme_of, wall_id):
    """A reason nobody can act on is the silence this report exists to break."""
    work = ready_work("Chop Suey", original=False)
    theme = theme_of(work)

    exclusion = display.build_manifest(wall_id, theme.id).exclusions[0]

    assert exclusion.work_id == work.id
    assert exclusion.title == "Chop Suey"
    assert exclusion.detail.endswith(".")


# -- the document ---------------------------------------------------------------


def test_the_manifest_carries_the_label_text_but_no_label_geometry(service, display, ready_work, theme_of, wall_id):
    """Label text crosses to the display plane; how it is set does not."""
    hopper = service.add_artist(
        name="Edward Hopper", nationality="American", born=1882, died=1967, family_name="Hopper", given_name="Edward"
    )
    theme = theme_of(ready_work(artist_id=hopper.id, commentary="Painted in a Greenwich Village studio."))

    label = display.build_manifest(wall_id, theme.id).entries[0].label

    assert label["title"] == "Nighthawks"
    assert label["artist"] == "Edward Hopper"
    # The whole name AND its parts: a panel setting the family name in bold
    # capitals needs the parts, and a work whose artist has none has only the
    # whole — so dropping either shape makes one of the two unlabelable.
    assert label["artist_family_name"] == "Hopper"
    assert label["artist_given_name"] == "Edward"
    assert label["artist_nationality"] == "American"
    assert label["artist_dates"] == "1882–1967"
    assert label["date_created"] == "1942"
    assert label["medium"] == "Oil on canvas"
    assert label["commentary"] == "Painted in a Greenwich Village studio."
    assert not any(key in label for key in ("font", "font_size", "panel_width", "panel_height"))


def test_a_work_with_no_artist_still_produces_a_legible_label(display, ready_work, theme_of, wall_id):
    """Unattributed works are real; a label that failed on one would take it off the wall."""
    theme = theme_of(ready_work())

    label = display.build_manifest(wall_id, theme.id).entries[0].label

    assert label["title"] == "Nighthawks"
    assert label["artist"] is None
    assert label["artist_dates"] is None


def test_the_written_manifest_is_json_the_display_plane_can_parse(display, ready_work, theme_of, wall_settings, wall_id):
    theme = theme_of(ready_work())

    display.sync(wall_id, theme.id)

    document = json.loads(wall_settings.manifest_path(wall_id).read_text())
    assert document["schema"]["major"] == SCHEMA_MAJOR
    assert document["theme"]["name"] == theme.name
    assert [entry["render_path"] for entry in document["entries"]] == [f"ready/{document['entries'][0]['work_id']}.jpg"]


def test_the_manifest_does_not_carry_the_exclusions(display, ready_work, theme_of, wall_settings, wall_id):
    """They are curation's report about its own catalogue, not something display can use."""
    theme = theme_of(ready_work("Nighthawks"), ready_work("Chop Suey", original=False))

    build = display.sync(wall_id, theme.id)

    assert len(build.exclusions) == 1
    document = json.loads(wall_settings.manifest_path(wall_id).read_text())
    assert "exclusions" not in document
    assert len(document["entries"]) == 1


def test_entries_follow_the_curated_order(display, ready_work, theme_of, wall_id):
    first = ready_work("Nighthawks")
    second = ready_work("Chop Suey")
    theme = theme_of(first, second)

    build = display.build_manifest(wall_id, theme.id)

    assert [entry.work_id for entry in build.entries] == [first.id, second.id]


# -- rotation settings ----------------------------------------------------------


def test_a_theme_that_expressed_no_pace_inherits_the_deployment_default(display, ready_work, theme_of, wall_settings, wall_id):
    theme = theme_of(ready_work())

    build = display.build_manifest(wall_id, theme.id)

    assert build.rotation_interval_seconds == wall_settings.rotation_interval_seconds
    assert build.shuffle == wall_settings.shuffle


def test_a_themes_own_pace_wins_over_the_default(store, display, ready_work, theme_of, wall_settings, wall_id):
    """Seeded through the store: nothing writes these yet, and the manifest is their only reader."""
    theme = theme_of(ready_work())
    # Values no default could produce, so a field read from the wrong place shows.
    store.update_theme(replace(theme, rotation_interval_seconds=931, shuffle=not wall_settings.shuffle))

    build = display.build_manifest(wall_id, theme.id)

    assert build.rotation_interval_seconds == 931
    assert build.shuffle is (not wall_settings.shuffle)


# -- the directive rides along unchanged ----------------------------------------


def test_a_rebuild_carries_the_sequence_forward_rather_than_resetting_it(display, ready_work, theme_of, wall_id):
    """A reset would read to the display plane as an advance, firing a jump nobody issued."""
    theme = theme_of(ready_work())
    display.step_display(wall_id)
    display.step_display(wall_id)

    first = display.build_manifest(wall_id, theme.id)
    second = display.build_manifest(wall_id, theme.id)

    assert first.directive_sequence == 2
    assert second.directive_sequence == 2


def test_switching_themes_carries_the_sequence_forward(display, ready_work, theme_of, wall_id):
    """The counter is the catalogue's, not the theme's — a per-theme one would reset on every switch."""
    first = theme_of(ready_work("Nighthawks"), name="Late night")
    second = theme_of(ready_work("Chop Suey"), name="Daylight")
    display.step_display(wall_id)

    display.activate_theme(second.id, wall_id=wall_id)
    build = display.build_manifest(wall_id, second.id)

    assert build.theme.id == second.id
    assert build.directive_sequence == 1
    assert display.build_manifest(wall_id, first.id).directive_sequence == 1


def test_only_a_directive_advances_the_sequence(display, ready_work, theme_of, wall_settings, wall_id):
    theme = theme_of(ready_work())
    display.sync(wall_id, theme.id)
    before = json.loads(wall_settings.manifest_path(wall_id).read_text())["directive"]["sequence"]

    display.sync(wall_id, theme.id)
    assert json.loads(wall_settings.manifest_path(wall_id).read_text())["directive"]["sequence"] == before

    display.step_display(wall_id)
    display.sync(wall_id, theme.id)
    assert json.loads(wall_settings.manifest_path(wall_id).read_text())["directive"]["sequence"] == before + 1


def test_the_manifest_carries_a_standing_pin(display, ready_work, theme_of, wall_settings, wall_id):
    work = ready_work()
    theme = theme_of(work)
    display.show_work_now(wall_id, work.id)

    display.sync(wall_id, theme.id)

    assert json.loads(wall_settings.manifest_path(wall_id).read_text())["directive"]["pinned_work_id"] == work.id


# -- writing ---------------------------------------------------------------------


def test_no_reader_ever_observes_a_partial_manifest(tmp_path, monkeypatch):
    """Atomicity is the whole concurrency-control story between the planes.

    Observed *during* the write rather than between writes, which is the only
    version of this that can fail: reading before and after would pass just as
    happily against a write straight to the destination. The hook fires while
    the new document is being serialised, and at that moment the destination must
    still hold the previous one whole — a reader polling this path can never be
    handed a truncated file, which would parse as invalid JSON rather than as
    absent and leave the display plane with no good answer.
    """
    path = tmp_path / "theme-manifest.json"
    write_atomically(path, {"entries": [{"work_id": "first"}]})

    observed = []
    real_dump = builder.json.dump

    def dump_and_peek(document, stream, **kwargs):
        # Mid-write: whatever a poller reads right now.
        observed.append(path.read_text())
        return real_dump(document, stream, **kwargs)

    monkeypatch.setattr(builder.json, "dump", dump_and_peek)
    write_atomically(path, {"entries": [{"work_id": "x" * 5000}]})

    assert observed, "the write did not go through the hook, so this asserted nothing"
    assert json.loads(observed[0])["entries"] == [{"work_id": "first"}]
    # And once the rename lands, the new document is there whole.
    assert json.loads(path.read_text())["entries"] == [{"work_id": "x" * 5000}]


def test_writing_leaves_no_temporary_files_behind(tmp_path):
    """A temp file per sync in ART_ROOT would accumulate where the display plane polls."""
    path = tmp_path / "theme-manifest.json"

    for _ in range(5):
        write_atomically(path, {"entries": []})

    assert sorted(os.listdir(tmp_path)) == ["theme-manifest.json"]


def test_a_failed_write_leaves_the_previous_manifest_in_place(tmp_path):
    """The wall keeps running off the last good manifest; a half-written one would stop it."""
    path = tmp_path / "theme-manifest.json"
    write_atomically(path, {"entries": [{"work_id": "first"}]})

    class Unserialisable:
        pass

    with pytest.raises(TypeError):
        write_atomically(path, {"entries": Unserialisable()})

    assert json.loads(path.read_text())["entries"] == [{"work_id": "first"}]
    assert sorted(os.listdir(tmp_path)) == ["theme-manifest.json"]


def test_the_manifest_directory_is_created_if_it_does_not_exist(tmp_path):
    """A fresh deployment has no ART_ROOT yet, and a sync must not be the thing that fails."""
    path = tmp_path / "art" / "theme-manifest.json"

    write_atomically(path, {"entries": []})

    assert json.loads(path.read_text()) == {"entries": []}


# -- refusals ---------------------------------------------------------------------


def test_pinning_a_work_that_cannot_reach_the_wall_is_refused_with_its_reason(display, ready_work, wall_id):
    """The one path that could write a directive nothing can carry out.

    Answering "the directive is written" and then never moving the wall is the
    silence the exclusion report exists to break — arriving through the action
    that did not consult readiness. The refusal carries the same sentence the
    manifest build would have given, so the curator learns what to fix.
    """
    work = ready_work(rendition=False)

    with pytest.raises(ServiceError, match="has a master image but has not been rendered"):
        display.show_work_now(wall_id, work.id)

    # And nothing was written: a refused directive must not move the counter.
    assert display.read_directive(wall_id).sequence == 0
    assert display.read_directive(wall_id).pinned_work_id is None


def test_a_work_becomes_pinnable_once_it_is_displayable(display, service, ready_work, wall_id):
    """The refusal is a state, not a verdict about the work."""
    work = ready_work(rendition=False)
    with pytest.raises(ServiceError):
        display.show_work_now(wall_id, work.id)

    service.record_rendition(
        artwork_id=work.id,
        kind=RenditionKind.TV_DISPLAY,
        target_width=3840,
        target_height=2160,
        path=f"ready/{work.id}.jpg",
    )

    assert display.show_work_now(wall_id, work.id).pinned_work_id == work.id


def test_an_unrendered_work_cannot_be_made_into_an_entry(service):
    """The guard on the one path that would put a broken entry in the manifest.

    `assess` is what keeps this unreachable; the raise is what makes a caller
    that skipped it fail loudly here rather than take the wall down to a missing
    file later.
    """
    work = service.add_artwork(title="Nighthawks")
    inputs = builder.WorkInputs(artwork=work, artist=None, original=None, tv_rendition=None, mat_color=None)

    with pytest.raises(ValueError, match="no television render"):
        builder.entry_for(inputs)


def test_building_for_a_wall_with_nothing_hanging_is_refused_rather_than_writing_an_empty_manifest(display, wall_id):
    """An empty manifest would read as "show nothing", which is not what "nothing hung yet" means.

    The refusal names the wall, because with two of them "nothing is hanging" is
    not an answer a curator can act on without knowing where.
    """
    with pytest.raises(ServiceError, match="Nothing is hanging on"):
        display.build_manifest(wall_id)


def test_building_for_an_unknown_wall_names_the_id_it_could_not_find(display):
    with pytest.raises(ServiceError, match="No wall with id 'nope'"):
        display.build_manifest("nope")


def test_building_an_unknown_theme_names_the_id_it_could_not_find(display, wall_id):
    with pytest.raises(ServiceError, match="No theme with id 'nope'"):
        display.build_manifest(wall_id, "nope")


# -- one manifest per wall -------------------------------------------------------


class TestOneManifestPerWall:
    """Each wall gets its own document, and one room's rewrite leaves the rest alone.

    **This is the property the per-file decision was made for.** Change detection
    on the display side is an mtime poll at about a second, so a shared file
    would wake every wall's display on every other wall's change — and would make
    "the manifest's sequence" ambiguous exactly where the coalescing and
    sequence-regression rules need it to be a single number. Per file also leaves
    a display plane unable to read a wall it does not serve: it stats one path.

    Until 2026-08-12 there was one file for the installation, so hanging a theme
    on a second wall overwrote the first's manifest and handed the running
    television the wrong room's pictures — silently, since a display had no way to
    notice the document had stopped being about it.
    """

    @pytest.fixture
    def two_walls(self, display, wall_id):
        """The wall a fresh catalogue holds, and a second the curator recorded."""
        return wall_id, display.add_wall(name="The study").id

    def test_each_wall_gets_its_own_document(self, display, ready_work, theme_of, wall_settings, two_walls):
        living_room, study = two_walls
        theirs = theme_of(ready_work("Nighthawks"), name="Late night")
        ours = theme_of(ready_work("The Elephants"), name="Surrealists")

        display.activate_theme(theirs.id, wall_id=living_room)
        display.activate_theme(ours.id, wall_id=study)

        assert json.loads(wall_settings.manifest_path(living_room).read_text())["theme"]["name"] == "Late night"
        assert json.loads(wall_settings.manifest_path(study).read_text())["theme"]["name"] == "Surrealists"

    def test_one_walls_rewrite_does_not_touch_another_walls_file(self, display, ready_work, theme_of, wall_settings, two_walls):
        """**The mtime, not just the contents.** A display polls the file's mtime
        at about a second, so touching another wall's file at all is a wall woken
        — and re-deriving — for a change that was never about it."""
        living_room, study = two_walls
        theme = theme_of(ready_work("Nighthawks"))
        display.activate_theme(theme.id, wall_id=living_room)
        display.activate_theme(theme.id, wall_id=study)
        untouched = wall_settings.manifest_path(study)
        before = untouched.stat()

        for _ in range(3):
            display.step_display(living_room)
            display.sync(living_room)

        after = untouched.stat()
        assert (after.st_mtime_ns, after.st_size) == (before.st_mtime_ns, before.st_size)

    def test_two_walls_run_independent_directive_sequences(self, display, ready_work, theme_of, wall_settings, two_walls):
        """A `next` in the living room does not step the study.

        The counters were already per wall in the catalogue; this is the half
        that reaches the display plane, and without it both rooms read one
        number — so an advance meant for one would fire a jump in the other.
        """
        living_room, study = two_walls
        theme = theme_of(ready_work("Nighthawks"))
        display.activate_theme(theme.id, wall_id=living_room)
        display.activate_theme(theme.id, wall_id=study)

        display.step_display(living_room)
        display.step_display(living_room)
        display.sync(living_room)
        display.step_display(study)
        display.sync(study)

        assert json.loads(wall_settings.manifest_path(living_room).read_text())["directive"]["sequence"] == 2
        assert json.loads(wall_settings.manifest_path(study).read_text())["directive"]["sequence"] == 1

    def test_a_pin_reaches_one_wall_and_not_the_other(self, display, ready_work, theme_of, wall_settings, two_walls):
        """Multi-hop: the pin is written, published, and *absent* from the neighbour."""
        living_room, study = two_walls
        work = ready_work("Nighthawks")
        theme = theme_of(work)
        display.activate_theme(theme.id, wall_id=living_room)
        display.activate_theme(theme.id, wall_id=study)

        display.show_work_now(living_room, work.id)
        display.sync(living_room)

        assert json.loads(wall_settings.manifest_path(living_room).read_text())["directive"]["pinned_work_id"] == work.id
        assert json.loads(wall_settings.manifest_path(study).read_text())["directive"]["pinned_work_id"] is None

    def test_the_one_wall_case_is_what_it_was_apart_from_the_filename(
        self, display, ready_work, theme_of, wall_settings, wall_id
    ):
        """The acceptance criterion, asserted rather than assumed.

        A one-wall installation is the degenerate case of this design, and the
        only thing that changed for it is where the file is written. The document
        itself carries no wall — the *filename* is what names it, which is what
        keeps a display unable to open a room it does not serve rather than
        merely unwilling to act on it. Two answers to "which wall is this" could
        disagree; one cannot.
        """
        theme = theme_of(ready_work("Nighthawks"))

        display.activate_theme(theme.id, wall_id=wall_id)

        published = wall_settings.manifest_path(wall_id)
        assert published.name == f"theme-manifest-{wall_id}.json"
        document = json.loads(published.read_text())
        assert set(document) == {"schema", "generated_at", "theme", "rotation", "directive", "entries"}
        assert [entry["work_id"] for entry in document["entries"]] == [theme_works(display, theme.id)[0]]

    def test_the_heartbeat_is_read_per_wall_too(self, display, wall_settings, two_walls):
        """Health has to be able to name which wall is silent.

        One shared heartbeat could not: the second display would overwrite the
        first's report every minute, so a wall that had gone dark would read
        exactly like a wall that was fine.
        """
        living_room, study = two_walls
        wall_settings.heartbeat_path(living_room).write_text(
            json.dumps({"reported_at": "2026-08-12T00:00:00+00:00"}), encoding="utf-8"
        )

        # Read through the survey, which is what both surfaces call. There was a
        # single-wall `wall_status` beside it whose only callers were these two
        # lines; a second service-level answer to "has this wall reported" is one
        # more thing that can disagree with the first, and it was removed rather
        # than given a test of its own.
        reported = {reading.wall.id: reading.heartbeat.absent for reading in display.survey_wall_status()}

        assert reported == {living_room: False, study: True}


def theme_works(display, theme_id) -> list[str]:
    return [detail.artwork.id for detail in display.theme_works(theme_id)]
