"""The questions this half of the catalogue exists to answer.

A persisted format is a lock-in decision, and its consumers' queries are its
requirements. The data model states twelve of them; six are about a work that has
already been accepted and are checked here. The other six are about the
pre-acceptance pipeline and belong with the entities that carry it.

Each test is named for its question and asks it the way the flow that needs it
would — not by reaching for a column, but by calling what the flow calls. A test
that read the row directly would pass even if no caller could ever get the
answer out.
"""

from curation.persistence.records import (
    AcquisitionMethod,
    FetchStatus,
    MatMethod,
    RenditionKind,
    RightsStatus,
    SourceClass,
)
from curation.services.display_fit import ArtworkBox, DisplayFit


def _make_showable(service, work):
    """Give a work everything readiness asks for, so the wall will accept a pin on it."""
    source = service.add_source(
        artwork_id=work.id,
        url="https://museum.example/figure-five",
        provider="artic",
        source_class=SourceClass.INSTITUTIONAL,
        acquisition_method=AcquisitionMethod.DEZOOMIFY,
        rights_status=RightsStatus.PUBLIC_DOMAIN,
        is_primary=True,
    )
    service.record_original(
        artwork_id=work.id,
        source_id=source.id,
        path="raw/figure-five.tif",
        width=6000,
        height=4000,
        byte_size=90_000_000,
        content_hash="hash-1",
        fetch_status=FetchStatus.OK,
    )
    service.record_mat_color(artwork_id=work.id, hex_rgb="#27285b", method=MatMethod.VISION_MODEL)
    service.record_rendition(
        artwork_id=work.id,
        kind=RenditionKind.TV_DISPLAY,
        target_width=3840,
        target_height=2160,
        path="ready/figure-five.jpg",
    )


#: The reference 42" deployment's artwork box, as worked out in the
#: non-functional requirements.
_BOX = ArtworkBox(width=3316, height=1597, pixels_per_inch=105.0, floor_inches=12.0)


def test_q1_which_works_belong_to_a_theme_so_the_display_plane_can_sync_them(service, display):
    hopper = service.add_artist(name="Edward Hopper", nationality="American", born=1882, died=1967)
    nighthawks = service.add_artwork(title="Nighthawks", artist_id=hopper.id)
    chop_suey = service.add_artwork(title="Chop Suey", artist_id=hopper.id)
    unplaced = service.add_artwork(title="Automat", artist_id=hopper.id)
    theme = display.add_theme(name="Hopper")

    # Two placed deliberately out of insertion order, one left unplaced.
    display.add_to_theme(theme_id=theme.id, artwork_id=nighthawks.id, position=2)
    display.add_to_theme(theme_id=theme.id, artwork_id=chop_suey.id, position=1)
    display.add_to_theme(theme_id=theme.id, artwork_id=unplaced.id)

    ordered = display.theme_works(theme.id)

    assert [entry.artwork.title for entry in ordered] == ["Chop Suey", "Nighthawks", "Automat"]
    # Attribution comes with it, because deciding what goes on the wall turns on it.
    assert all(entry.artist.name == "Edward Hopper" for entry in ordered)


def test_q1_a_work_can_be_moved_and_removed_without_touching_the_work_itself(service, display):
    first = service.add_artwork(title="Nighthawks")
    second = service.add_artwork(title="Chop Suey")
    theme = display.add_theme(name="Hopper")
    display.add_to_theme(theme_id=theme.id, artwork_id=first.id, position=1)
    display.add_to_theme(theme_id=theme.id, artwork_id=second.id, position=2)

    display.move_in_theme(theme_id=theme.id, artwork_id=second.id, position=0)
    assert [entry.artwork.title for entry in display.theme_works(theme.id)] == ["Chop Suey", "Nighthawks"]

    display.remove_from_theme(theme_id=theme.id, artwork_id=second.id)
    assert [entry.artwork.title for entry in display.theme_works(theme.id)] == ["Nighthawks"]
    # The work is still in the catalogue; only its membership went.
    assert service.get_artwork(second.id).artwork.title == "Chop Suey"


def _placed(service, display, *titles):
    """A theme holding these works, in this order, densely numbered from zero."""
    theme = display.add_theme(name="Hopper")
    for position, title in enumerate(titles):
        display.add_to_theme(theme_id=theme.id, artwork_id=service.add_artwork(title=title).id, position=position)
    return theme


def _order(display, theme):
    return [entry.artwork.title for entry in display.theme_works(theme.id)]


def test_q1_a_position_is_an_index_into_the_order_rather_than_a_number_in_a_column(service, display):
    """Moving a work *down* one place, which is the move that used to do nothing.

    `list_memberships` breaks a tie on `added_at`, so writing the number and
    stopping there put the moved work level with the work already at that
    position and sorted it ahead again, being the older row. Moving up worked and
    moving down did not — and the Theme screen's ↓ button had therefore never
    reordered anything, in a way no assertion about the write could see.

    Asserted downwards *and* upwards, because the defect was asymmetric: a test
    that only moved a work up passes against both implementations.
    """
    theme = _placed(service, display, "Autumn Rhythm", "Blue Poles", "Convergence")

    display.move_in_theme(
        theme_id=theme.id,
        artwork_id=display.theme_works(theme.id)[0].artwork.id,
        position=1,
    )
    assert _order(display, theme) == ["Blue Poles", "Autumn Rhythm", "Convergence"]

    display.move_in_theme(
        theme_id=theme.id,
        artwork_id=display.theme_works(theme.id)[2].artwork.id,
        position=0,
    )
    assert _order(display, theme) == ["Convergence", "Blue Poles", "Autumn Rhythm"]


def test_q1_the_order_is_renumbered_densely_so_the_index_sent_back_is_the_index_read(service, display, store):
    """What makes the round trip work: the surface reads a place off the list it was given.

    A move that left gaps or duplicates in the stored positions would keep
    answering correctly for one move and drift, and the drift is invisible — the
    order still reads sensibly right up until two rows tie and the wrong one
    wins.
    """
    theme = _placed(service, display, "Autumn Rhythm", "Blue Poles", "Convergence")

    display.move_in_theme(
        theme_id=theme.id,
        artwork_id=display.theme_works(theme.id)[0].artwork.id,
        position=2,
    )

    assert [membership.position for membership in store.list_memberships(theme.id)] == [0, 1, 2]
    assert _order(display, theme) == ["Blue Poles", "Convergence", "Autumn Rhythm"]


def test_q1_a_position_past_the_end_puts_the_work_last_rather_than_refusing(service, display):
    """The list a curator is moving within is the one they are looking at.

    There is no wrong answer to "put this last" worth a refusal, and a surface
    that had to know the length before it could ask would be holding a count it
    could only have got from the same list.
    """
    theme = _placed(service, display, "Autumn Rhythm", "Blue Poles")

    moved = display.move_in_theme(
        theme_id=theme.id,
        artwork_id=display.theme_works(theme.id)[0].artwork.id,
        position=99,
    )

    assert moved.position == 1
    assert _order(display, theme) == ["Blue Poles", "Autumn Rhythm"]


def test_q1_returning_a_work_to_unplaced_closes_the_gap_it_left(service, display, store):
    """Unplaced is a destination, not the end of the order, and the rest renumbers.

    Both halves matter. The work goes after everything placed because nobody has
    said where it belongs; and the works that stay keep a dense sequence, so the
    next move made against the list is made against the numbers actually stored.
    """
    theme = _placed(service, display, "Autumn Rhythm", "Blue Poles", "Convergence")

    display.move_in_theme(
        theme_id=theme.id,
        artwork_id=display.theme_works(theme.id)[0].artwork.id,
        position=None,
    )

    assert _order(display, theme) == ["Blue Poles", "Convergence", "Autumn Rhythm"]
    assert [membership.position for membership in store.list_memberships(theme.id)] == [0, 1, None]


def test_q2_which_work_the_wall_is_on_so_the_label_can_match_it(service, display, wall_id):
    """The catalogue's half of the answer: what hangs on the wall, its order, and the pin.

    The display plane owns which entry it has reached; what it needs from here is
    the theme that wall is showing, the order to rotate through, and the label
    text for whichever work that lands on. The pin is the one case where the
    catalogue names a specific work.
    """
    demuth = service.add_artist(name="Charles Demuth", nationality="American", born=1883, died=1935)
    figure_five = service.add_artwork(
        title="I Saw the Figure 5 in Gold",
        artist_id=demuth.id,
        date_created="1928",
        medium="Oil, graphite, ink and gold leaf on paperboard",
        dimensions="90.2 x 76.2 cm",
    )
    _make_showable(service, figure_five)
    theme = display.add_theme(name="American Modernists")
    display.add_to_theme(theme_id=theme.id, artwork_id=figure_five.id, position=1)

    display.activate_theme(theme.id, wall_id=wall_id)
    display.show_work_now(wall_id, figure_five.id)

    assert display.hanging_on(wall_id).id == theme.id
    directive = display.read_directive(wall_id)
    assert directive.pinned_work_id == figure_five.id

    # Every field the physical label renders is reachable from that id.
    detail = service.get_artwork(directive.pinned_work_id)
    assert detail.artwork.title == "I Saw the Figure 5 in Gold"
    assert detail.artwork.date_created == "1928"
    assert detail.artwork.medium.startswith("Oil, graphite")
    assert detail.artwork.dimensions == "90.2 x 76.2 cm"
    assert (detail.artist.name, detail.artist.nationality, detail.artist.born, detail.artist.died) == (
        "Charles Demuth",
        "American",
        1883,
        1935,
    )


def test_q6_a_work_can_be_re_acquired_from_scratch_after_every_derived_file_is_lost(service):
    """Two institutions hold it, so one reorganising its site does not end the work."""
    work = service.add_artwork(title="The Persistence of Memory")
    moma = service.add_source(
        artwork_id=work.id,
        url="https://www.moma.org/collection/works/79018",
        provider="moma",
        source_class=SourceClass.INSTITUTIONAL,
        acquisition_method=AcquisitionMethod.API,
        rights_status=RightsStatus.IN_COPYRIGHT,
        is_primary=True,
        selection_rationale="The holding institution's own page.",
    )
    service.add_source(
        artwork_id=work.id,
        url="https://artsandculture.google.com/asset/xyz",
        provider="google_arts",
        source_class=SourceClass.INSTITUTIONAL,
        acquisition_method=AcquisitionMethod.DEZOOMIFY,
        rights_status=RightsStatus.UNKNOWN,
    )

    sources = service.list_sources(work.id)

    # Everything a fetch needs is on the row: where, how, and which one was used.
    assert [source.id for source in sources][0] == moma.id
    assert {source.acquisition_method for source in sources} == {AcquisitionMethod.API, AcquisitionMethod.DEZOOMIFY}
    assert sources[0].selection_rationale == "The holding institution's own page."
    assert all(source.url.startswith("https://") for source in sources)


def test_q7_what_mat_colour_was_chosen_and_on_what_basis(service):
    work = service.add_artwork(title="Nighthawks")
    service.record_mat_color(
        artwork_id=work.id,
        hex_rgb="#8a8a8a",
        method=MatMethod.DOMINANT_COLOR_FALLBACK,
        reason="The vision model did not answer.",
    )
    chosen = service.record_mat_color(
        artwork_id=work.id,
        hex_rgb="#27285b",
        method=MatMethod.VISION_MODEL,
        lab_l=18.4,
        lab_a=9.1,
        lab_b=-29.7,
        reason="Picks up the deep blue of the window glass.",
        model_id="anthropic/claude-3.5-sonnet",
    )

    current = service.current_mat_color(work.id)

    assert current.hex_rgb == chosen.hex_rgb
    assert current.method is MatMethod.VISION_MODEL
    assert current.model_id == "anthropic/claude-3.5-sonnet"
    assert current.reason.startswith("Picks up")
    assert (current.lab_l, current.lab_a, current.lab_b) == (18.4, 9.1, -29.7)

    # And the fallback that came before it is still visible as a fallback, which
    # is the thing the 2024 pipeline made invisible.
    history = service.mat_color_history(work.id)
    assert [entry.method for entry in history] == [MatMethod.VISION_MODEL, MatMethod.DOMINANT_COLOR_FALLBACK]


def test_q8_which_renditions_exist_for_which_geometry_and_are_they_current(service):
    work = service.add_artwork(title="Nighthawks")
    source = service.add_source(
        artwork_id=work.id,
        url="https://museum.example/1",
        provider="artic",
        source_class=SourceClass.INSTITUTIONAL,
        acquisition_method=AcquisitionMethod.DEZOOMIFY,
        rights_status=RightsStatus.PUBLIC_DOMAIN,
        is_primary=True,
    )
    service.record_original(
        artwork_id=work.id,
        source_id=source.id,
        path="originals/nighthawks.tif",
        width=9000,
        height=5000,
        byte_size=421_337_216,
        content_hash="sha256:first",
        fetch_status=FetchStatus.OK,
    )
    service.record_rendition(
        artwork_id=work.id, kind=RenditionKind.TV_DISPLAY, target_width=3840, target_height=2160, path="renders/nighthawks.jpg"
    )
    service.record_rendition(
        artwork_id=work.id, kind=RenditionKind.THUMBNAIL, target_width=400, target_height=225, path="thumbs/nighthawks.jpg"
    )

    views = service.list_renditions(work.id)

    # Geometry is columns, so the question is answerable at all — the 2024 design
    # encoded it in the filename, where nothing could query it.
    by_geometry = {(view.rendition.kind, view.rendition.target_width, view.rendition.target_height): view for view in views}
    assert set(by_geometry) == {(RenditionKind.TV_DISPLAY, 3840, 2160), (RenditionKind.THUMBNAIL, 400, 225)}
    assert all(view.stale is False for view in views)

    # Re-acquire, and both answers change without either row being touched.
    service.record_original(
        artwork_id=work.id,
        source_id=source.id,
        path="originals/nighthawks.tif",
        width=9600,
        height=5400,
        byte_size=500_000_000,
        content_hash="sha256:second",
        fetch_status=FetchStatus.OK,
    )
    assert all(view.stale is True for view in service.list_renditions(work.id))


def test_q8_whether_a_held_original_is_large_enough_is_answered_without_storing_a_verdict(service):
    """The same fact, judged against two panels, gives two answers and stores neither."""
    work = service.add_artwork(title="A small press image")
    source = service.add_source(
        artwork_id=work.id,
        url="https://gallery.example/press.jpg",
        provider="gallery_site",
        source_class=SourceClass.CONTEMPORARY_WEB,
        acquisition_method=AcquisitionMethod.DIRECT_HTTP,
        rights_status=RightsStatus.IN_COPYRIGHT,
        is_primary=True,
    )
    service.record_original(
        artwork_id=work.id,
        source_id=source.id,
        path="originals/press.jpg",
        width=800,
        height=600,
        byte_size=98_304,
        content_hash="sha256:press",
        fetch_status=FetchStatus.OK,
    )

    assessment = service.display_fit(work.id, box=_BOX)

    assert assessment.fit is DisplayFit.BELOW_FLOOR
    assert round(assessment.rendered_long_edge_inches, 1) == 7.6

    bigger_wall = ArtworkBox(width=3546, height=1723, pixels_per_inch=58.7, floor_inches=12.0)
    assert service.display_fit(work.id, box=bigger_wall).fit is DisplayFit.MATTED_SMALL


def test_q9_who_the_artist_is_for_the_physical_label(service):
    """The 2024 record held one blob and re-parsed it with a regex on every read."""
    demuth = service.add_artist(
        name="Charles Demuth",
        nationality="American",
        born=1883,
        died=1935,
        biography="A precisionist from Lancaster.",
    )
    work = service.add_artwork(title="I Saw the Figure 5 in Gold", artist_id=demuth.id)

    artist = service.get_artwork(work.id).artist

    assert (artist.name, artist.nationality, artist.born, artist.died) == ("Charles Demuth", "American", 1883, 1935)


def test_q9_an_artist_whose_dates_cannot_be_parsed_keeps_the_text_that_was_given(service):
    """ "Active 1620s" is a real answer; a null year is not the same fact."""
    anonymous = service.add_artist(name="Master of the Blue Jeans", lifespan_text="active 1650s")
    work = service.add_artwork(title="The Barber", artist_id=anonymous.id)

    artist = service.get_artwork(work.id).artist

    assert (artist.born, artist.died) == (None, None)
    assert artist.lifespan_text == "active 1650s"


def test_q9_an_unattributed_work_has_no_artist_rather_than_an_empty_one(service):
    work = service.add_artwork(title="Nighthawks")

    assert service.get_artwork(work.id).artist is None
