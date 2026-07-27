"""The service layer's behaviour, independent of any surface."""

import pytest

from curation.persistence.catalogue import ArtworkStatus
from curation.services.errors import ServiceError


def test_a_work_enters_the_catalogue_already_accepted(service):
    artwork = service.add_artwork(title="Nighthawks")

    assert artwork.status is ArtworkStatus.ACCEPTED
    assert artwork.accepted_at is not None


def test_a_works_identity_is_minted_not_derived(service):
    first = service.add_artwork(title="Nighthawks")
    second = service.add_artwork(title="Nighthawks")

    # Same title, same everything a source could key on — two works, because
    # identity is internal and never derived from what a source called it.
    assert first.id != second.id


def test_getting_a_work_resolves_its_artist(seeded_service):
    listed = seeded_service.list_artworks().entries
    with_artist = next(entry for entry in listed if entry.artist is not None)

    detail = seeded_service.get_artwork(with_artist.artwork.id)

    assert detail.artist is not None
    assert detail.artist.name == with_artist.artist.name


def test_an_unattributed_work_resolves_to_no_artist(seeded_service):
    nighthawks = _by_title(seeded_service, "Nighthawks")

    assert seeded_service.get_artwork(nighthawks.artwork.id).artist is None


def test_getting_an_unknown_work_names_the_id_it_could_not_find(service):
    with pytest.raises(ServiceError, match="No artwork with id 'nope'"):
        service.get_artwork("nope")


def test_a_work_cannot_point_at_an_artist_that_does_not_exist(service):
    with pytest.raises(ServiceError, match="No artist with id"):
        service.add_artwork(title="Nighthawks", artist_id="nope")


def test_listing_reports_the_total_not_just_the_page(seeded_service):
    listing = seeded_service.list_artworks(limit=2)

    assert len(listing.entries) == 2
    assert listing.total == 3
    assert listing.truncated is True


def test_a_complete_page_is_not_reported_as_truncated(seeded_service):
    listing = seeded_service.list_artworks()

    assert listing.total == 3
    assert listing.truncated is False


def test_the_last_page_of_a_paged_listing_is_not_truncated(seeded_service):
    listing = seeded_service.list_artworks(limit=2, offset=2)

    assert len(listing.entries) == 1
    assert listing.truncated is False


def test_paging_never_repeats_or_skips_a_work(seeded_service):
    first = seeded_service.list_artworks(limit=2, offset=0)
    second = seeded_service.list_artworks(limit=2, offset=2)

    ids = [entry.artwork.id for entry in (*first.entries, *second.entries)]
    assert len(set(ids)) == 3


def test_listing_filters_by_status(seeded_service):
    assert seeded_service.list_artworks(status="accepted").total == 3
    assert seeded_service.list_artworks(status="archived").total == 0


def test_an_unknown_status_names_the_valid_ones(service):
    with pytest.raises(ServiceError, match="accepted, archived"):
        service.list_artworks(status="archive")


@pytest.mark.parametrize("limit", [0, -1, 101])
def test_a_limit_outside_the_bounds_is_refused(service, limit):
    with pytest.raises(ServiceError, match="limit must be between"):
        service.list_artworks(limit=limit)


def test_a_negative_offset_is_refused(service):
    with pytest.raises(ServiceError, match="offset cannot be negative"):
        service.list_artworks(offset=-1)


def test_a_blank_title_is_refused_rather_than_stored(service):
    with pytest.raises(ServiceError, match="title cannot be empty"):
        service.add_artwork(title="   ")


def test_themes_round_trip(service):
    theme = service.add_theme(name="American Modernists", description="Precisionists and their neighbours")

    assert service.get_theme(theme.id) == theme
    assert [existing.name for existing in service.list_themes()] == ["American Modernists"]


def test_two_themes_cannot_share_a_name(service):
    service.add_theme(name="American Modernists")

    with pytest.raises(ServiceError, match="Could not store theme"):
        service.add_theme(name="American Modernists")


def test_a_theme_starts_inactive(service):
    assert service.add_theme(name="American Modernists").is_active is False


def _by_title(service, title):
    return next(entry for entry in service.list_artworks().entries if entry.artwork.title == title)
