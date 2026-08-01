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
    AcquisitionMethod,
    MatMethod,
    RenditionKind,
    RightsStatus,
    SourceClass,
)
from curation.services.errors import ServiceError


@pytest.fixture
def ready_work(service):
    """A work with everything catalogue readiness asks for, and nothing more.

    A factory rather than a fixture row: nearly every test here removes exactly
    one of the four requirements, and the one that is missing is the point.
    """

    def _ready(title="Nighthawks", *, artist_id=None, original=True, rendition=True, mat=True, content_hash="hash-1"):
        work = service.add_artwork(title=title, artist_id=artist_id, date_created="1942", medium="Oil on canvas")
        source = service.add_source(
            artwork_id=work.id,
            url=f"https://museum.example/{work.id}",
            provider="artic",
            source_class=SourceClass.INSTITUTIONAL,
            acquisition_method=AcquisitionMethod.DEZOOMIFY,
            rights_status=RightsStatus.PUBLIC_DOMAIN,
            is_primary=True,
        )
        if original:
            service.record_original(
                artwork_id=work.id,
                source_id=source.id,
                path=f"raw/{work.id}.tif",
                width=6000,
                height=4000,
                byte_size=90_000_000,
                content_hash=content_hash,
            )
        if mat:
            service.record_mat_color(artwork_id=work.id, hex_rgb="#27285b", method=MatMethod.VISION_MODEL)
        if rendition and original:
            service.record_rendition(
                artwork_id=work.id,
                kind=RenditionKind.TV_DISPLAY,
                target_width=3840,
                target_height=2160,
                path=f"ready/{work.id}.jpg",
            )
        return work

    return _ready


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


def test_a_work_with_everything_it_needs_reaches_the_wall(display, ready_work, theme_of):
    work = ready_work()
    theme = theme_of(work)

    build = display.build_manifest(theme.id)

    assert [entry.work_id for entry in build.entries] == [work.id]
    assert build.exclusions == []


def test_an_archived_work_leaves_the_manifest_but_stays_in_the_theme(service, display, ready_work, theme_of):
    """Theme membership is curatorial; readiness is technical. Archiving moves one, not the other."""
    work = ready_work()
    theme = theme_of(work)
    service.archive_artwork(work.id)

    build = display.build_manifest(theme.id)

    assert build.entries == []
    assert [exclusion.reason for exclusion in build.exclusions] == [ExclusionReason.ARCHIVED]
    # Still a member — the curator said it belongs here and nothing has unsaid it.
    assert [detail.artwork.id for detail in display.theme_works(theme.id)] == [work.id]


def test_a_work_with_no_acquired_original_is_excluded_and_named(display, ready_work, theme_of):
    theme = theme_of(ready_work(original=False))

    build = display.build_manifest(theme.id)

    assert build.entries == []
    assert [exclusion.reason for exclusion in build.exclusions] == [ExclusionReason.NO_ORIGINAL]
    assert "acquired" in build.exclusions[0].detail


def test_a_work_that_has_not_been_rendered_is_excluded_and_named(display, ready_work, theme_of):
    theme = theme_of(ready_work(rendition=False))

    build = display.build_manifest(theme.id)

    assert [exclusion.reason for exclusion in build.exclusions] == [ExclusionReason.NO_RENDITION]


def test_a_work_with_no_current_mat_colour_is_excluded_and_named(display, ready_work, theme_of):
    theme = theme_of(ready_work(mat=False))

    build = display.build_manifest(theme.id)

    assert [exclusion.reason for exclusion in build.exclusions] == [ExclusionReason.NO_MAT_COLOR]


def test_a_render_made_from_an_earlier_acquisition_is_excluded_as_stale(service, display, ready_work, theme_of):
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
    )

    build = display.build_manifest(theme.id)

    assert build.entries == []
    assert [exclusion.reason for exclusion in build.exclusions] == [ExclusionReason.STALE_RENDITION]


def test_regenerating_the_render_returns_the_work_to_the_wall(service, display, ready_work, theme_of):
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
    )
    assert display.build_manifest(theme.id).entries == []

    service.record_rendition(
        artwork_id=work.id,
        kind=RenditionKind.TV_DISPLAY,
        target_width=3840,
        target_height=2160,
        path=f"ready/{work.id}.jpg",
    )

    build = display.build_manifest(theme.id)
    assert [entry.work_id for entry in build.entries] == [work.id]
    assert build.exclusions == []


def test_a_thumbnail_is_not_a_television_render(service, display, ready_work, theme_of):
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

    build = display.build_manifest(theme.id)

    assert [exclusion.reason for exclusion in build.exclusions] == [ExclusionReason.NO_RENDITION]


def test_every_member_is_accounted_for_as_an_entry_or_an_exclusion(display, ready_work, theme_of):
    """The property that makes the report trustworthy: nothing is silently dropped."""
    theme = theme_of(ready_work("Nighthawks"), ready_work("Chop Suey", original=False), ready_work("Automat", mat=False))

    build = display.build_manifest(theme.id)

    assert len(build.entries) == 1
    assert len(build.exclusions) == 2
    assert build.considered == 3
    assert {exclusion.title for exclusion in build.exclusions} == {"Chop Suey", "Automat"}


def test_an_exclusion_names_the_work_a_curator_would_look_for(display, ready_work, theme_of):
    """A reason nobody can act on is the silence this report exists to break."""
    work = ready_work("Chop Suey", original=False)
    theme = theme_of(work)

    exclusion = display.build_manifest(theme.id).exclusions[0]

    assert exclusion.work_id == work.id
    assert exclusion.title == "Chop Suey"
    assert exclusion.detail.endswith(".")


# -- the document ---------------------------------------------------------------


def test_the_manifest_carries_the_label_text_but_no_label_geometry(service, display, ready_work, theme_of):
    """Label text crosses to the display plane; how it is set does not."""
    hopper = service.add_artist(name="Edward Hopper", nationality="American", born=1882, died=1967)
    theme = theme_of(ready_work(artist_id=hopper.id))

    label = display.build_manifest(theme.id).entries[0].label

    assert label["title"] == "Nighthawks"
    assert label["artist"] == "Edward Hopper"
    assert label["artist_nationality"] == "American"
    assert label["artist_dates"] == "1882–1967"
    assert label["date_created"] == "1942"
    assert label["medium"] == "Oil on canvas"
    assert not any(key in label for key in ("font", "font_size", "panel_width", "panel_height"))


def test_a_work_with_no_artist_still_produces_a_legible_label(display, ready_work, theme_of):
    """Unattributed works are real; a label that failed on one would take it off the wall."""
    theme = theme_of(ready_work())

    label = display.build_manifest(theme.id).entries[0].label

    assert label["title"] == "Nighthawks"
    assert label["artist"] is None
    assert label["artist_dates"] is None


def test_the_written_manifest_is_json_the_display_plane_can_parse(display, ready_work, theme_of, wall):
    theme = theme_of(ready_work())

    display.sync(theme.id)

    document = json.loads(wall.manifest_path.read_text())
    assert document["schema"]["major"] == SCHEMA_MAJOR
    assert document["theme"]["name"] == theme.name
    assert [entry["render_path"] for entry in document["entries"]] == [f"ready/{document['entries'][0]['work_id']}.jpg"]


def test_the_manifest_does_not_carry_the_exclusions(display, ready_work, theme_of, wall):
    """They are curation's report about its own catalogue, not something display can use."""
    theme = theme_of(ready_work("Nighthawks"), ready_work("Chop Suey", original=False))

    build = display.sync(theme.id)

    assert len(build.exclusions) == 1
    document = json.loads(wall.manifest_path.read_text())
    assert "exclusions" not in document
    assert len(document["entries"]) == 1


def test_entries_follow_the_curated_order(display, ready_work, theme_of):
    first = ready_work("Nighthawks")
    second = ready_work("Chop Suey")
    theme = theme_of(first, second)

    build = display.build_manifest(theme.id)

    assert [entry.work_id for entry in build.entries] == [first.id, second.id]


# -- rotation settings ----------------------------------------------------------


def test_a_theme_that_expressed_no_pace_inherits_the_deployment_default(display, ready_work, theme_of, wall):
    theme = theme_of(ready_work())

    build = display.build_manifest(theme.id)

    assert build.rotation_interval_seconds == wall.rotation_interval_seconds
    assert build.shuffle == wall.shuffle


def test_a_themes_own_pace_wins_over_the_default(store, display, ready_work, theme_of, wall):
    """Seeded through the store: nothing writes these yet, and the manifest is their only reader."""
    theme = theme_of(ready_work())
    # Values no default could produce, so a field read from the wrong place shows.
    store.update_theme(replace(theme, rotation_interval_seconds=931, shuffle=not wall.shuffle))

    build = display.build_manifest(theme.id)

    assert build.rotation_interval_seconds == 931
    assert build.shuffle is (not wall.shuffle)


# -- the directive rides along unchanged ----------------------------------------


def test_a_rebuild_carries_the_sequence_forward_rather_than_resetting_it(display, ready_work, theme_of):
    """A reset would read to the display plane as an advance, firing a jump nobody issued."""
    theme = theme_of(ready_work())
    display.step_display()
    display.step_display()

    first = display.build_manifest(theme.id)
    second = display.build_manifest(theme.id)

    assert first.directive_sequence == 2
    assert second.directive_sequence == 2


def test_switching_themes_carries_the_sequence_forward(display, ready_work, theme_of):
    """The counter is the catalogue's, not the theme's — a per-theme one would reset on every switch."""
    first = theme_of(ready_work("Nighthawks"), name="Late night")
    second = theme_of(ready_work("Chop Suey"), name="Daylight")
    display.step_display()

    display.activate_theme(second.id)
    build = display.build_manifest(second.id)

    assert build.theme.id == second.id
    assert build.directive_sequence == 1
    assert display.build_manifest(first.id).directive_sequence == 1


def test_only_a_directive_advances_the_sequence(display, ready_work, theme_of, wall):
    theme = theme_of(ready_work())
    display.sync(theme.id)
    before = json.loads(wall.manifest_path.read_text())["directive"]["sequence"]

    display.sync(theme.id)
    assert json.loads(wall.manifest_path.read_text())["directive"]["sequence"] == before

    display.step_display()
    display.sync(theme.id)
    assert json.loads(wall.manifest_path.read_text())["directive"]["sequence"] == before + 1


def test_the_manifest_carries_a_standing_pin(display, ready_work, theme_of, wall):
    work = ready_work()
    theme = theme_of(work)
    display.show_work_now(work.id)

    display.sync(theme.id)

    assert json.loads(wall.manifest_path.read_text())["directive"]["pinned_work_id"] == work.id


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


def test_building_with_no_active_theme_is_refused_rather_than_writing_an_empty_manifest(display):
    """An empty manifest would read as "show nothing", which is not what "no theme yet" means."""
    with pytest.raises(ServiceError, match="No theme is active"):
        display.build_manifest()


def test_building_an_unknown_theme_names_the_id_it_could_not_find(display):
    with pytest.raises(ServiceError, match="No theme with id 'nope'"):
        display.build_manifest("nope")
