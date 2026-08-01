"""The Artwork state machine, and the display directive that rides alongside it.

An artwork has exactly two states and four edges, two of which are refusals. It
never carries a pending or rejected state: everything before acceptance is a
candidate, which is a separate entity with its own verdict, so there is no second
lifecycle here to drift out of step with that one.

The directive is tested with the lifecycle because the two meet: a pin naming a
work that has been taken out of circulation is an instruction the display plane
can never carry out.
"""

import logging
from datetime import UTC, datetime, timedelta

import pytest

from curation.manifest.builder import MANIFEST_FILENAME
from curation.manifest.heartbeat import HEARTBEAT_FILENAME
from curation.persistence.file import open_catalogue_file
from curation.persistence.records import ArtworkStatus, MatMethod, Theme
from curation.persistence.sqlite import SqliteCatalogue
from curation.services.catalogue import CatalogueService
from curation.services.display import DisplayService, WallSettings
from curation.services.errors import ServiceError


def _display(store, tmp_path, *, catalogue=None):
    """A display service over an explicitly opened store, wired as the entry point wires one."""
    return DisplayService(
        store,
        catalogue or CatalogueService(store),
        WallSettings(
            manifest_path=tmp_path / MANIFEST_FILENAME,
            heartbeat_path=tmp_path / HEARTBEAT_FILENAME,
            rotation_interval_seconds=180,
            shuffle=True,
        ),
    )


def test_a_work_can_be_taken_out_of_circulation_and_brought_back(service):
    work = service.add_artwork(title="Nighthawks")

    archived = service.archive_artwork(work.id)
    assert archived.status is ArtworkStatus.ARCHIVED
    assert service.get_artwork(work.id).artwork.status is ArtworkStatus.ARCHIVED

    restored = service.restore_artwork(work.id)
    assert restored.status is ArtworkStatus.ACCEPTED
    assert service.get_artwork(work.id).artwork.status is ArtworkStatus.ACCEPTED


def test_archiving_an_archived_work_is_refused_rather_than_ignored(service):
    work = service.add_artwork(title="Nighthawks")
    service.archive_artwork(work.id)

    with pytest.raises(ServiceError, match="already archived"):
        service.archive_artwork(work.id)


def test_restoring_a_work_that_was_never_archived_is_refused(service):
    work = service.add_artwork(title="Nighthawks")

    with pytest.raises(ServiceError, match="not archived"):
        service.restore_artwork(work.id)


def test_archiving_an_unknown_work_names_the_id_it_could_not_find(service):
    with pytest.raises(ServiceError, match="No artwork with id 'nope'"):
        service.archive_artwork("nope")


def test_archiving_keeps_the_record_and_its_mat_history(service):
    """Archiving is removal from circulation, not deletion — that is the whole point.

    The mat colours are the expensive part: each one cost a model call, and the
    hand-tuned ones are this product's quality corpus.
    """
    work = service.add_artwork(title="Nighthawks")
    service.record_mat_color(artwork_id=work.id, hex_rgb="#27285b", method=MatMethod.VISION_MODEL)
    service.record_mat_color(artwork_id=work.id, hex_rgb="#1a1a1a", method=MatMethod.MANUAL)

    service.archive_artwork(work.id)

    assert len(service.mat_color_history(work.id)) == 2
    assert service.current_mat_color(work.id).hex_rgb == "#1a1a1a"


def test_an_archived_work_moves_between_the_status_listings(service):
    work = service.add_artwork(title="Nighthawks")
    service.archive_artwork(work.id)

    assert service.list_artworks(status="accepted").total == 0
    assert service.list_artworks(status="archived").total == 1
    # "The whole catalogue" still means both.
    assert service.list_artworks().total == 1


# -- the display directive -----------------------------------------------------


def test_a_fresh_catalogue_has_a_directive_at_the_start(display):
    directive = display.read_directive()

    assert (directive.sequence, directive.pinned_work_id) == (0, None)


def test_stepping_on_advances_the_sequence_and_carries_no_pin(display):
    first = display.step_display()
    second = display.step_display()

    assert (first.sequence, second.sequence) == (1, 2)
    assert second.pinned_work_id is None


def test_showing_a_work_now_advances_the_sequence_and_pins_it(service, display):
    work = service.add_artwork(title="Nighthawks")

    directive = display.show_work_now(work.id)

    assert directive.sequence == 1
    assert directive.pinned_work_id == work.id


def test_stepping_on_clears_a_standing_pin(service, display):
    """A step that left the pin in place would read as "jump there again"."""
    work = service.add_artwork(title="Nighthawks")
    display.show_work_now(work.id)

    directive = display.step_display()

    assert directive.sequence == 2
    assert directive.pinned_work_id is None


def test_archiving_the_pinned_work_withdraws_the_pin(service, display):
    work = service.add_artwork(title="Nighthawks")
    display.show_work_now(work.id)

    service.archive_artwork(work.id)

    assert display.read_directive().pinned_work_id is None


def test_withdrawing_a_pin_does_not_advance_the_sequence(service, display):
    """The display plane acts every time the number goes up.

    Archiving a work is not an instruction to it, so an advance here would fire a
    directive nobody issued — and the work it would step to is unrelated to the
    one that was archived.
    """
    work = service.add_artwork(title="Nighthawks")
    display.show_work_now(work.id)
    before = display.read_directive().sequence

    service.archive_artwork(work.id)

    assert display.read_directive().sequence == before


def test_archiving_some_other_work_leaves_the_pin_alone(service, display):
    pinned = service.add_artwork(title="Nighthawks")
    other = service.add_artwork(title="Chop Suey")
    display.show_work_now(pinned.id)

    service.archive_artwork(other.id)

    assert display.read_directive().pinned_work_id == pinned.id


def test_an_archived_work_cannot_be_pinned(service, display):
    work = service.add_artwork(title="Nighthawks")
    service.archive_artwork(work.id)

    with pytest.raises(ServiceError, match="out of circulation"):
        display.show_work_now(work.id)


def test_pinning_an_unknown_work_is_refused(display):
    with pytest.raises(ServiceError, match="No artwork with id 'nope'"):
        display.show_work_now("nope")


def test_theme_activity_never_touches_the_sequence(service, display):
    """Only `next` and `show_now` advance it; a theme switch rewrites the list.

    A switch that advanced the counter would look to the display plane exactly
    like a curator pressing "next" at the same moment.
    """
    display.step_display()
    before = display.read_directive()

    first = display.add_theme(name="American Modernists")
    second = display.add_theme(name="Surrealists")
    display.activate_theme(second.id)
    work = service.add_artwork(title="Nighthawks")
    display.add_to_theme(theme_id=first.id, artwork_id=work.id)

    assert display.read_directive() == before


def test_the_sequence_survives_the_process_that_advanced_it(tmp_path):
    """Monotonic for the life of the catalogue, not for the life of the process.

    The counter is stored catalogue-side precisely so that a restart — which
    `Restart=always` makes routine — cannot reset it. A reset reads to the
    display plane as an advance, which fires a directive nobody issued.
    """
    path = tmp_path / "catalogue.sqlite"
    first_store = SqliteCatalogue(open_catalogue_file(path))
    first_catalogue = CatalogueService(first_store)
    first = _display(first_store, tmp_path, catalogue=first_catalogue)
    work = first_catalogue.add_artwork(title="Nighthawks")
    first.step_display()
    first.show_work_now(work.id)
    first_store.close()

    reopened_store = SqliteCatalogue(open_catalogue_file(path))
    try:
        reopened = _display(reopened_store, tmp_path)
        assert reopened.read_directive().sequence == 2
        assert reopened.read_directive().pinned_work_id == work.id
        assert reopened.step_display().sequence == 3
    finally:
        reopened_store.close()


# -- repairing a catalogue that predates a rule --------------------------------


def _legacy_catalogue_with_no_active_theme(path):
    """A catalogue as the revision before the exactly-one-active rule wrote one.

    That revision's `add_theme` took no `is_active` argument and it shipped no way
    to activate a theme, so every theme it ever wrote was inactive. Built through
    the store rather than through the service, because the service is exactly what
    will not produce this state any more.
    """
    catalogue = SqliteCatalogue(open_catalogue_file(path))
    moment = datetime(2026, 7, 20, 9, 30, tzinfo=UTC)
    catalogue.add_theme(Theme(id="t-late", name="Late night", created_at=moment + timedelta(days=1)))
    catalogue.add_theme(Theme(id="t-early", name="Daylight", created_at=moment))
    return catalogue


def test_a_catalogue_whose_themes_are_all_inactive_is_repaired_on_start(tmp_path, caplog):
    """The rule postdates files already on disk, so it has to be brought to them.

    Nothing else repairs this: the index the file carries says only "at most one",
    which zero satisfies, and a catalogue nobody adds a theme to would stay in the
    forbidden state indefinitely — with the display plane given no sync target and
    nothing reporting it.
    """
    catalogue = _legacy_catalogue_with_no_active_theme(tmp_path / "catalogue.sqlite")
    try:
        display = _display(catalogue, tmp_path)
        assert display.active_theme() is None

        with caplog.at_level(logging.WARNING):
            display.reconcile()

        # The oldest theme, so every machine opening the same file makes the same
        # choice rather than following whatever the listing happened to return.
        assert display.active_theme().id == "t-early"
        assert [theme.is_active for theme in display.list_themes()].count(True) == 1
        assert "none active" in caplog.text
        assert "Daylight" in caplog.text
    finally:
        catalogue.close()


def test_reconciling_a_healthy_catalogue_changes_nothing_and_says_nothing(tmp_path, caplog):
    """A repair that logged on every start would train the operator to ignore it."""
    catalogue = SqliteCatalogue(open_catalogue_file(tmp_path / "catalogue.sqlite"))
    try:
        display = _display(catalogue, tmp_path)
        first = display.add_theme(name="American Modernists")
        display.add_theme(name="Surrealists")

        with caplog.at_level(logging.WARNING):
            display.reconcile()

        assert display.active_theme().id == first.id
        assert caplog.text == ""
    finally:
        catalogue.close()


def test_reconciling_an_empty_catalogue_is_not_a_repair(tmp_path, caplog):
    """No themes is not the forbidden state — there is nothing to be active."""
    catalogue = SqliteCatalogue(open_catalogue_file(tmp_path / "catalogue.sqlite"))
    try:
        display = _display(catalogue, tmp_path)
        with caplog.at_level(logging.WARNING):
            display.reconcile()

        assert display.active_theme() is None
        assert caplog.text == ""
    finally:
        catalogue.close()


def test_adding_a_theme_to_a_catalogue_with_none_active_promotes_it(tmp_path):
    """The condition is "none is active", not "there are none", so this repairs too."""
    catalogue = _legacy_catalogue_with_no_active_theme(tmp_path / "catalogue.sqlite")
    try:
        display = _display(catalogue, tmp_path)

        added = display.add_theme(name="Precisionists")

        assert added.is_active is True
        assert [theme.is_active for theme in display.list_themes()].count(True) == 1
    finally:
        catalogue.close()


def test_the_repair_reaches_the_file(tmp_path):
    path = tmp_path / "catalogue.sqlite"
    catalogue = _legacy_catalogue_with_no_active_theme(path)
    _display(catalogue, tmp_path).reconcile()
    catalogue.close()

    reopened = SqliteCatalogue(open_catalogue_file(path))
    try:
        assert _display(reopened, tmp_path).active_theme().id == "t-early"
    finally:
        reopened.close()
