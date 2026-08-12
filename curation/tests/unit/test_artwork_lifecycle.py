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

from curation.persistence.file import open_catalogue_file
from curation.persistence.records import (
    AcquisitionMethod,
    ArtworkStatus,
    FetchStatus,
    MatMethod,
    RenditionKind,
    RightsStatus,
    SourceClass,
    Theme,
)
from curation.persistence.sqlite import SqliteCatalogue
from curation.services.catalogue import CatalogueService
from curation.services.display import DisplayService, DisplaySettings
from curation.services.errors import ServiceError


def _a_showable_work(catalogue):
    """A work the directive will accept a pin on — one that could reach the wall."""
    work = catalogue.add_artwork(title="Nighthawks")
    source = catalogue.add_source(
        artwork_id=work.id,
        url="https://museum.example/nighthawks",
        provider="artic",
        source_class=SourceClass.INSTITUTIONAL,
        acquisition_method=AcquisitionMethod.DEZOOMIFY,
        rights_status=RightsStatus.PUBLIC_DOMAIN,
        is_primary=True,
    )
    catalogue.record_original(
        artwork_id=work.id,
        source_id=source.id,
        path="raw/nighthawks.tif",
        width=6000,
        height=4000,
        byte_size=90_000_000,
        content_hash="hash-1",
        fetch_status=FetchStatus.OK,
    )
    catalogue.record_mat_color(artwork_id=work.id, hex_rgb="#27285b", method=MatMethod.VISION_MODEL)
    catalogue.record_rendition(
        artwork_id=work.id,
        kind=RenditionKind.TV_DISPLAY,
        target_width=3840,
        target_height=2160,
        path="ready/nighthawks.jpg",
    )
    return work


def _display(store, tmp_path, *, catalogue=None):
    """A display service over an explicitly opened store, wired as the entry point wires one."""
    return DisplayService(
        store,
        catalogue or CatalogueService(store),
        DisplaySettings(art_root=tmp_path, rotation_interval_seconds=180, shuffle=True),
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


def test_a_fresh_catalogue_has_a_directive_at_the_start(display, wall_id):
    directive = display.read_directive(wall_id)

    assert (directive.sequence, directive.pinned_work_id) == (0, None)


def test_stepping_on_advances_the_sequence_and_carries_no_pin(display, wall_id):
    first = display.step_display(wall_id)
    second = display.step_display(wall_id)

    assert (first.sequence, second.sequence) == (1, 2)
    assert second.pinned_work_id is None


def test_showing_a_work_now_advances_the_sequence_and_pins_it(ready_work, display, wall_id):
    work = ready_work()

    directive = display.show_work_now(wall_id, work.id)

    assert directive.sequence == 1
    assert directive.pinned_work_id == work.id


def test_stepping_on_clears_a_standing_pin(ready_work, display, wall_id):
    """A step that left the pin in place would read as "jump there again"."""
    work = ready_work()
    display.show_work_now(wall_id, work.id)

    directive = display.step_display(wall_id)

    assert directive.sequence == 2
    assert directive.pinned_work_id is None


def test_archiving_the_pinned_work_withdraws_the_pin(service, ready_work, display, wall_id):
    work = ready_work()
    display.show_work_now(wall_id, work.id)

    service.archive_artwork(work.id)

    assert display.read_directive(wall_id).pinned_work_id is None


def test_withdrawing_a_pin_does_not_advance_the_sequence(service, ready_work, display, wall_id):
    """The display plane acts every time the number goes up.

    Archiving a work is not an instruction to it, so an advance here would fire a
    directive nobody issued — and the work it would step to is unrelated to the
    one that was archived.
    """
    work = ready_work()
    display.show_work_now(wall_id, work.id)
    before = display.read_directive(wall_id).sequence

    service.archive_artwork(work.id)

    assert display.read_directive(wall_id).sequence == before


def test_archiving_some_other_work_leaves_the_pin_alone(service, ready_work, display, wall_id):
    pinned = ready_work()
    other = service.add_artwork(title="Chop Suey")
    display.show_work_now(wall_id, pinned.id)

    service.archive_artwork(other.id)

    assert display.read_directive(wall_id).pinned_work_id == pinned.id


def test_an_archived_work_cannot_be_pinned(service, ready_work, display, wall_id):
    work = ready_work()
    service.archive_artwork(work.id)

    with pytest.raises(ServiceError, match="archived"):
        display.show_work_now(wall_id, work.id)


def test_pinning_an_unknown_work_is_refused(display, wall_id):
    with pytest.raises(ServiceError, match="No artwork with id 'nope'"):
        display.show_work_now(wall_id, "nope")


def test_theme_activity_never_touches_the_sequence(service, display, wall_id):
    """Only `next` and `show_now` advance it; a theme switch rewrites the list.

    A switch that advanced the counter would look to the display plane exactly
    like a curator pressing "next" at the same moment.
    """
    display.step_display(wall_id)
    before = display.read_directive(wall_id)

    first = display.add_theme(name="American Modernists")
    second = display.add_theme(name="Surrealists")
    display.activate_theme(second.id, wall_id=wall_id)
    work = service.add_artwork(title="Nighthawks")
    display.add_to_theme(theme_id=first.id, artwork_id=work.id)

    assert display.read_directive(wall_id) == before


def test_the_sequence_survives_the_process_that_advanced_it(tmp_path):
    """Monotonic for the life of the wall, not for the life of the process.

    The counter is stored catalogue-side precisely so that a restart — which
    `Restart=always` makes routine — cannot reset it. A reset reads to the
    display plane as an advance, which fires a directive nobody issued.
    """
    path = tmp_path / "second-catalogue.sqlite"
    first_store = SqliteCatalogue(open_catalogue_file(path))
    first_catalogue = CatalogueService(first_store)
    first = _display(first_store, tmp_path, catalogue=first_catalogue)
    # Read from the file this test opened rather than taken from the shared
    # fixture: the wall's id is a UUID minted when the file was established, so
    # another file's wall is a different wall.
    wall_id = first_store.list_walls()[0].id
    work = _a_showable_work(first_catalogue)
    first.step_display(wall_id)
    first.show_work_now(wall_id, work.id)
    first_store.close()

    reopened_store = SqliteCatalogue(open_catalogue_file(path))
    try:
        reopened = _display(reopened_store, tmp_path)
        assert [wall.id for wall in reopened_store.list_walls()] == [wall_id]
        assert reopened.read_directive(wall_id).sequence == 2
        assert reopened.read_directive(wall_id).pinned_work_id == work.id
        assert reopened.step_display(wall_id).sequence == 3
    finally:
        reopened_store.close()


# -- nothing is ever hung by anything but a curator -----------------------------
#
# This section asserted the opposite until 2026-08-12, and the reversal is a
# ruling rather than a relaxation. `reconcile` promoted the oldest theme when
# none was active, and `add_theme` promoted a new one for the same reason: a
# catalogue with themes and none active left the display plane no sync target.
# With more than one wall that rule hangs the same theme in every room unbidden,
# and "a wall with nothing on it" is now a designed state rather than a broken
# one — so the promotion is dropped and these are what is left to hold.


def _catalogue_with_unhung_themes(path):
    """Two themes, neither hanging anywhere. The ordinary state of a fresh catalogue."""
    catalogue = SqliteCatalogue(open_catalogue_file(path))
    moment = datetime(2026, 7, 20, 9, 30, tzinfo=UTC)
    catalogue.add_theme(Theme(id="t-late", name="Late night", created_at=moment + timedelta(days=1)))
    catalogue.add_theme(Theme(id="t-early", name="Daylight", created_at=moment))
    return catalogue


def test_a_catalogue_of_unhung_themes_stays_that_way_across_a_restart(tmp_path, caplog):
    """Nothing promotes a theme automatically, and opening the file is not an exception.

    With N walls there is no defensible answer to which theme belongs on a wall
    the curator has not hung anything on — so the honest answer is the empty one,
    and it is silent, because there is nothing wrong to report. Opening the file
    is where the repair used to be reachable from, which is why the restart is
    the interesting moment rather than an incidental one.

    (`Services.reconcile` is the other half of this and is asserted where the
    container is: a display repair that no longer exists cannot be entered here.)
    """
    path = tmp_path / "catalogue.sqlite"
    _catalogue_with_unhung_themes(path).close()
    # The restart is the moment under test, and `caplog` has been capturing since
    # the call phase began — including the line the migration writes when the
    # helper above creates the file, which is a different event with its own
    # tests. Without this, the assertion below is about everything this function
    # has said rather than about opening the file.
    caplog.clear()

    with caplog.at_level(logging.WARNING, logger="curation"):
        catalogue = SqliteCatalogue(open_catalogue_file(path))
    try:
        display = _display(catalogue, tmp_path)
        assert display.hanging_on(catalogue.list_walls()[0].id) is None
        assert [theme.id for theme in display.list_themes()] == ["t-early", "t-late"]
        # Scoped to this plane's own loggers rather than to everything the
        # process said: the claim is that *curation* reported no repair, and a
        # bare emptiness check makes any library's warning fail this test for a
        # reason that has nothing to do with hanging.
        assert [record.message for record in caplog.records if record.name.startswith("curation.")] == []
    finally:
        catalogue.close()


def test_adding_a_theme_to_a_catalogue_with_nothing_hanging_hangs_nothing(tmp_path):
    """The condition used to be "none is active", which made this a second repair path."""
    catalogue = _catalogue_with_unhung_themes(tmp_path / "catalogue.sqlite")
    try:
        display = _display(catalogue, tmp_path)

        added = display.add_theme(name="Precisionists")

        assert display.walls_hanging(added.id) == []
        assert display.hanging_on(catalogue.list_walls()[0].id) is None
    finally:
        catalogue.close()


def test_what_a_curator_hung_reaches_the_file_and_survives_a_reopen(tmp_path):
    """The other half of the same claim: a deliberate hang is durable.

    Dropping the promotion means the assignment row is the only thing that can
    put a theme on a wall, so it is the only thing that can put one back after a
    restart.
    """
    path = tmp_path / "catalogue.sqlite"
    catalogue = _catalogue_with_unhung_themes(path)
    wall_id = catalogue.list_walls()[0].id
    _display(catalogue, tmp_path).activate_theme("t-early", wall_id=wall_id)
    catalogue.close()

    reopened = SqliteCatalogue(open_catalogue_file(path))
    try:
        assert _display(reopened, tmp_path).hanging_on(wall_id).id == "t-early"
    finally:
        reopened.close()
