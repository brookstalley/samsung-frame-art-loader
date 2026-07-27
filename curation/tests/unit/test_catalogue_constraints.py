"""The catalogue's write-time rules, one section per rule.

These are the constraints the data model states, checked where the data model
says they are enforced: at write time, in the service layer. A rule applied on
the way out instead of on the way in is a rule the stored data can already
violate, and by then the violation is permanent.

Each section names the rule it covers and, where it is not obvious, the failure
that rule exists to prevent — because a test that only asserts the mechanism
stops explaining itself the moment somebody wonders whether the mechanism is
still wanted.
"""

import pytest

from curation.persistence.records import (
    AcquisitionMethod,
    MatMethod,
    RenditionKind,
    RightsStatus,
    SourceClass,
)
from curation.services.errors import ServiceError


def _work(service, title="Nighthawks"):
    return service.add_artwork(title=title)


def _source(service, artwork_id, *, url="https://museum.example/1", is_primary=False, rights=RightsStatus.PUBLIC_DOMAIN):
    return service.add_source(
        artwork_id=artwork_id,
        url=url,
        provider="artic",
        source_class=SourceClass.INSTITUTIONAL,
        acquisition_method=AcquisitionMethod.DEZOOMIFY,
        rights_status=rights,
        is_primary=is_primary,
    )


def _original(service, artwork_id, source_id, *, content_hash="sha256:aaa", byte_size=4096, path="originals/w1.tif"):
    return service.record_original(
        artwork_id=artwork_id,
        source_id=source_id,
        path=path,
        width=6000,
        height=4000,
        byte_size=byte_size,
        content_hash=content_hash,
    )


# -- 1. Exactly one theme is active -------------------------------------------
#
# The display plane syncs whatever the active theme holds. Two claimants, or
# none, and its target is a guess.


def test_the_first_theme_is_active_because_a_catalogue_with_none_has_no_sync_target(service):
    assert service.add_theme(name="American Modernists").is_active is True


def test_a_second_theme_does_not_displace_the_active_one_by_arriving(service):
    first = service.add_theme(name="American Modernists")
    second = service.add_theme(name="Surrealists")

    assert service.get_theme(first.id).is_active is True
    assert second.is_active is False


def test_activating_a_theme_stands_the_previous_one_down(service):
    first = service.add_theme(name="American Modernists")
    second = service.add_theme(name="Surrealists")

    service.activate_theme(second.id)

    assert service.get_theme(first.id).is_active is False
    assert service.get_theme(second.id).is_active is True
    assert [theme.is_active for theme in service.list_themes()].count(True) == 1


def test_activating_the_already_active_theme_leaves_exactly_one_active(service):
    only = service.add_theme(name="American Modernists")

    service.activate_theme(only.id)

    assert [theme.is_active for theme in service.list_themes()] == [True]


def test_the_active_theme_is_the_one_reported_as_active(service):
    service.add_theme(name="American Modernists")
    second = service.add_theme(name="Surrealists")
    service.activate_theme(second.id)

    assert service.active_theme().id == second.id


def test_a_catalogue_with_no_themes_has_no_active_one(service):
    assert service.active_theme() is None


# -- 2. Exactly one mat colour per work is current ----------------------------


def test_choosing_a_mat_colour_supersedes_the_previous_choice_without_deleting_it(service):
    work = _work(service)
    first = service.record_mat_color(artwork_id=work.id, hex_rgb="#27285B", method=MatMethod.VISION_MODEL)
    second = service.record_mat_color(artwork_id=work.id, hex_rgb="#1a1a1a", method=MatMethod.MANUAL)

    history = service.mat_color_history(work.id)

    assert [entry.id for entry in history] == [second.id, first.id]
    assert [entry.is_current for entry in history] == [True, False]
    assert service.current_mat_color(work.id).id == second.id


def test_a_work_with_no_mat_colour_has_no_current_one(service):
    assert service.current_mat_color(_work(service).id) is None


def test_two_works_each_keep_their_own_current_mat_colour(service):
    """The rule is per work; a choice for one must not stand another's down."""
    first = _work(service, "Nighthawks")
    second = _work(service, "Chop Suey")
    service.record_mat_color(artwork_id=first.id, hex_rgb="#27285b", method=MatMethod.VISION_MODEL)
    service.record_mat_color(artwork_id=second.id, hex_rgb="#1a1a1a", method=MatMethod.VISION_MODEL)

    assert service.current_mat_color(first.id) is not None
    assert service.current_mat_color(second.id) is not None


def test_a_mat_colour_that_is_not_a_hex_triplet_is_refused(service):
    work = _work(service)
    with pytest.raises(ServiceError, match="hex triplet"):
        service.record_mat_color(artwork_id=work.id, hex_rgb="dark blue", method=MatMethod.MANUAL)


# -- 3. At most one source per work is primary --------------------------------


def test_promoting_a_source_demotes_the_one_that_held_the_claim(service):
    work = _work(service)
    first = _source(service, work.id, url="https://museum.example/1", is_primary=True)
    second = _source(service, work.id, url="https://other.example/2")

    service.set_primary_source(second.id)

    primaries = [source.id for source in service.list_sources(work.id) if source.is_primary]
    assert primaries == [second.id]
    assert first.id not in primaries


def test_adding_a_source_as_primary_demotes_the_previous_primary(service):
    work = _work(service)
    _source(service, work.id, url="https://museum.example/1", is_primary=True)
    second = _source(service, work.id, url="https://other.example/2", is_primary=True)

    assert [source.id for source in service.list_sources(work.id) if source.is_primary] == [second.id]


def test_a_work_may_have_sources_and_no_primary_at_all(service):
    """Sources are found before one of them is chosen, so 'at most one' is the rule."""
    work = _work(service)
    _source(service, work.id, url="https://museum.example/1")
    _source(service, work.id, url="https://other.example/2")

    assert [source.is_primary for source in service.list_sources(work.id)] == [False, False]


def test_the_primary_source_leads_the_list(service):
    work = _work(service)
    _source(service, work.id, url="https://aaa.example/1")
    chosen = _source(service, work.id, url="https://zzz.example/2", is_primary=True)

    assert service.list_sources(work.id)[0].id == chosen.id


# -- 4. A rendition is stale when it no longer matches its original -----------
#
# The 2024 code expressed this imperatively, clearing the television's state
# whenever it regenerated an image — which worked only at the one call site that
# remembered to.


def test_a_rendition_is_born_current(service):
    work = _work(service)
    source = _source(service, work.id)
    _original(service, work.id, source.id)
    service.record_rendition(
        artwork_id=work.id, kind=RenditionKind.TV_DISPLAY, target_width=3840, target_height=2160, path="renders/w1.jpg"
    )

    assert [view.stale for view in service.list_renditions(work.id)] == [False]


def test_re_acquiring_the_original_makes_every_existing_rendition_stale(service):
    work = _work(service)
    source = _source(service, work.id)
    _original(service, work.id, source.id, content_hash="sha256:first")
    service.record_rendition(
        artwork_id=work.id, kind=RenditionKind.TV_DISPLAY, target_width=3840, target_height=2160, path="renders/w1.jpg"
    )
    service.record_rendition(
        artwork_id=work.id, kind=RenditionKind.THUMBNAIL, target_width=400, target_height=300, path="thumbs/w1.jpg"
    )

    _original(service, work.id, source.id, content_hash="sha256:second")

    assert [view.stale for view in service.list_renditions(work.id)] == [True, True]


def test_regenerating_a_rendition_makes_it_current_again(service):
    work = _work(service)
    source = _source(service, work.id)
    _original(service, work.id, source.id, content_hash="sha256:first")
    service.record_rendition(
        artwork_id=work.id, kind=RenditionKind.TV_DISPLAY, target_width=3840, target_height=2160, path="renders/w1.jpg"
    )
    _original(service, work.id, source.id, content_hash="sha256:second")

    service.record_rendition(
        artwork_id=work.id, kind=RenditionKind.TV_DISPLAY, target_width=3840, target_height=2160, path="renders/w1.jpg"
    )

    assert [view.stale for view in service.list_renditions(work.id)] == [False]
    # Regenerating replaced the row rather than adding a second answer to
    # "is the 4K render current".
    assert len(service.list_renditions(work.id)) == 1


def test_a_rendition_cannot_be_recorded_before_an_original_exists(service):
    work = _work(service)
    with pytest.raises(ServiceError, match="no acquired original"):
        service.record_rendition(
            artwork_id=work.id, kind=RenditionKind.TV_DISPLAY, target_width=3840, target_height=2160, path="renders/w1.jpg"
        )


def test_the_same_geometry_in_a_different_kind_is_a_different_rendition(service):
    work = _work(service)
    source = _source(service, work.id)
    _original(service, work.id, source.id)
    service.record_rendition(
        artwork_id=work.id, kind=RenditionKind.TV_DISPLAY, target_width=400, target_height=300, path="renders/w1.jpg"
    )
    service.record_rendition(
        artwork_id=work.id, kind=RenditionKind.THUMBNAIL, target_width=400, target_height=300, path="thumbs/w1.jpg"
    )

    assert len(service.list_renditions(work.id)) == 2


# -- 5. An original is never zero bytes ---------------------------------------


@pytest.mark.parametrize("byte_size", [0, -1])
def test_a_zero_length_original_is_refused_as_the_failed_download_it_is(service, byte_size):
    work = _work(service)
    source = _source(service, work.id)

    with pytest.raises(ServiceError, match="failed download"):
        _original(service, work.id, source.id, byte_size=byte_size)


def test_an_original_with_no_pixels_is_refused(service):
    work = _work(service)
    source = _source(service, work.id)

    with pytest.raises(ServiceError, match="positive width and height"):
        service.record_original(
            artwork_id=work.id, source_id=source.id, path="originals/w1.tif", width=0, height=4000, byte_size=1, content_hash="h"
        )


def test_an_original_must_belong_to_the_source_it_names(service):
    """A source of a different work would make the provenance chain a lie."""
    first = _work(service, "Nighthawks")
    second = _work(service, "Chop Suey")
    other_source = _source(service, second.id)

    with pytest.raises(ServiceError, match="belongs to a different artwork"):
        _original(service, first.id, other_source.id)


# -- 6. Every stored path is relative to ART_ROOT ------------------------------


@pytest.mark.parametrize("path", ["/home/tvpi/art/originals/w1.tif", "/originals/w1.tif"])
def test_an_absolute_original_path_is_refused(service, path):
    work = _work(service)
    source = _source(service, work.id)

    with pytest.raises(ServiceError, match="must be relative to ART_ROOT"):
        _original(service, work.id, source.id, path=path)


def test_an_original_path_that_climbs_out_of_the_art_root_is_refused(service):
    work = _work(service)
    source = _source(service, work.id)

    with pytest.raises(ServiceError, match="climbs out of it"):
        _original(service, work.id, source.id, path="../elsewhere/w1.tif")


def test_an_absolute_rendition_path_is_refused_too(service):
    work = _work(service)
    source = _source(service, work.id)
    _original(service, work.id, source.id)

    with pytest.raises(ServiceError, match="must be relative to ART_ROOT"):
        service.record_rendition(
            artwork_id=work.id, kind=RenditionKind.TV_DISPLAY, target_width=3840, target_height=2160, path="/renders/w1.jpg"
        )


def test_a_stored_path_is_normalised_rather_than_kept_as_written(service):
    work = _work(service)
    source = _source(service, work.id)

    stored = _original(service, work.id, source.id, path="./originals//w1.tif")

    assert stored.relative_path == "originals/w1.tif"


# -- 13. Rights status is recorded for every source ----------------------------
#
# "We did not check" and "we checked and could not tell" are different facts and
# only the second is honest as `unknown`, so absence is not a permitted value.


def test_a_source_records_unknown_rights_rather_than_leaving_them_unset(service):
    work = _work(service)

    source = _source(service, work.id, rights=RightsStatus.UNKNOWN)

    assert source.rights_status is RightsStatus.UNKNOWN


def test_a_source_with_no_rights_status_is_refused(service):
    work = _work(service)

    with pytest.raises(ServiceError, match="Unknown rights_status"):
        _source(service, work.id, rights=None)


def test_an_invalid_rights_status_names_the_ones_that_are_valid(service):
    work = _work(service)

    with pytest.raises(ServiceError, match="in_copyright, public_domain, unknown"):
        _source(service, work.id, rights="probably fine")


def test_rights_gate_nothing(service):
    """An in-copyright source is recorded and used exactly like any other.

    The corpus is deliberately in-copyright, the display is a private household
    one, and the value is a provenance signal rather than a legal gate — so a
    filter here would contradict a decision already made.
    """
    work = _work(service)
    source = _source(service, work.id, rights=RightsStatus.IN_COPYRIGHT, is_primary=True)

    _original(service, work.id, source.id)

    assert service.get_original(work.id) is not None
    assert service.list_sources(work.id)[0].is_primary is True
