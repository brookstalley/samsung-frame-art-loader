"""The curator's whole loop, driven by a real MCP client over real HTTP.

Entered through the tool surface rather than the service on purpose. Every
behaviour here has service-level tests that pass with the binding deleted — the
question this file answers is whether anything actually calls them, which is the
shape of defect where a fully tested feature does nothing at all.

The arguments carry values no default could produce for the same reason: an
assertion pinned at a value that is also the default proves nothing about the
path that produced it.
"""

import json

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from curation.persistence.records import (
    AcquisitionMethod,
    FetchStatus,
    MatMethod,
    RenditionKind,
    RightsStatus,
    SourceClass,
)


async def call(server_url: str, tool: str, **arguments) -> tuple[dict, bool]:
    """Call a tool over real HTTP; return its payload and the protocol's error flag."""
    async with streamable_http_client(f"{server_url}/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool, arguments)
    return json.loads(result.content[0].text), bool(result.isError)


@pytest.fixture
async def wall(server_url):
    """The wall this deployment has, obtained the way a caller must obtain it.

    Through `art_display(action='walls')` rather than out of the store: every act
    against a wall names one, so a test that reached around the surface for the id
    would be exercising a call no MCP client could make.
    """
    payload, _ = await call(server_url, "art_display", action="walls")
    return payload["walls"][0]["wall_id"]


async def _a_theme(server_url, name="American Modernists"):
    payload, _ = await call(server_url, "art_theme", action="create", name=name)
    return payload["theme"]["theme_id"]


async def _the_works(server_url):
    payload, _ = await call(server_url, "art_catalogue", action="list")
    return {work["title"]: work["artwork_id"] for work in payload["artworks"]}


# -- themes ---------------------------------------------------------------------


async def test_a_theme_can_be_created_and_read_back_through_the_surface(server_url):
    payload, errored = await call(server_url, "art_theme", action="create", name="American Modernists")

    assert errored is False
    assert payload["theme"]["name"] == "American Modernists"

    listed, _ = await call(server_url, "art_theme", action="list")
    assert [theme["name"] for theme in listed["themes"]] == ["American Modernists"]
    # It hangs nowhere until somebody hangs it. The listing says so rather than
    # leaving a caller to infer it from an absent field.
    assert listed["themes"][0]["hanging_on"] == []


async def test_works_can_be_placed_in_a_theme_and_come_back_in_curated_order(server_url):
    theme_id = await _a_theme(server_url)
    works = await _the_works(server_url)

    # Positions chosen so the curated order is not the alphabetical one the
    # catalogue listing would have produced on its own.
    await call(server_url, "art_theme", action="add", theme_id=theme_id, artwork_id=works["Nighthawks"], position=0)
    await call(
        server_url,
        "art_theme",
        action="add",
        theme_id=theme_id,
        artwork_id=works["I Saw the Figure 5 in Gold"],
        position=1,
    )

    payload, errored = await call(server_url, "art_theme", action="get", theme_id=theme_id)

    assert errored is False
    assert [work["title"] for work in payload["works"]] == ["Nighthawks", "I Saw the Figure 5 in Gold"]


async def test_reordering_moves_a_work_through_the_surface(server_url):
    theme_id = await _a_theme(server_url)
    works = await _the_works(server_url)
    await call(server_url, "art_theme", action="add", theme_id=theme_id, artwork_id=works["Nighthawks"], position=0)
    await call(
        server_url,
        "art_theme",
        action="add",
        theme_id=theme_id,
        artwork_id=works["I Saw the Figure 5 in Gold"],
        position=1,
    )

    # Moved past the other rather than onto its position: positions are not
    # required to be unique, so "swap by claiming the same number" is not what
    # this action does, and asserting it would be asserting the tie-break.
    await call(server_url, "art_theme", action="reorder", theme_id=theme_id, artwork_id=works["Nighthawks"], position=7)

    payload, _ = await call(server_url, "art_theme", action="get", theme_id=theme_id)
    assert [work["title"] for work in payload["works"]] == ["I Saw the Figure 5 in Gold", "Nighthawks"]


async def test_works_sharing_a_position_fall_back_to_the_order_they_were_added(server_url):
    """Positions are curator-defined and not required to be unique.

    Two works can legitimately hold the same one, and the order then has to come
    from somewhere. Insertion order is the answer that does not surprise anyone,
    and pinning it here means it stays an answer rather than becoming whatever
    the storage layer happens to return.
    """
    theme_id = await _a_theme(server_url)
    works = await _the_works(server_url)
    await call(server_url, "art_theme", action="add", theme_id=theme_id, artwork_id=works["Nighthawks"], position=3)
    await call(
        server_url,
        "art_theme",
        action="add",
        theme_id=theme_id,
        artwork_id=works["I Saw the Figure 5 in Gold"],
        position=3,
    )

    payload, _ = await call(server_url, "art_theme", action="get", theme_id=theme_id)

    assert [work["title"] for work in payload["works"]] == ["Nighthawks", "I Saw the Figure 5 in Gold"]


async def test_a_work_returned_to_unplaced_sorts_after_the_placed_ones(server_url):
    theme_id = await _a_theme(server_url)
    works = await _the_works(server_url)
    await call(server_url, "art_theme", action="add", theme_id=theme_id, artwork_id=works["Nighthawks"], position=0)
    await call(
        server_url,
        "art_theme",
        action="add",
        theme_id=theme_id,
        artwork_id=works["I Saw the Figure 5 in Gold"],
        position=1,
    )

    # Omitting `position` is how a caller says "unplaced" — the curator has
    # expressed no order for this one, which is a real state and not an error.
    await call(server_url, "art_theme", action="reorder", theme_id=theme_id, artwork_id=works["Nighthawks"])

    payload, _ = await call(server_url, "art_theme", action="get", theme_id=theme_id)
    assert [work["title"] for work in payload["works"]] == ["I Saw the Figure 5 in Gold", "Nighthawks"]


async def test_removing_a_work_from_a_theme_leaves_the_work_in_the_catalogue(server_url, seeded_titles):
    theme_id = await _a_theme(server_url)
    works = await _the_works(server_url)
    await call(server_url, "art_theme", action="add", theme_id=theme_id, artwork_id=works["Nighthawks"])

    payload, errored = await call(server_url, "art_theme", action="remove", theme_id=theme_id, artwork_id=works["Nighthawks"])

    assert errored is False
    theme, _ = await call(server_url, "art_theme", action="get", theme_id=theme_id)
    assert theme["works"] == []
    catalogue, _ = await call(server_url, "art_catalogue", action="list")
    assert {work["title"] for work in catalogue["artworks"]} == set(seeded_titles)


async def test_a_themes_rotation_settings_survive_the_round_trip(server_url):
    """Values no default could produce, so a field dropped in the binding would show."""
    theme_id = await _a_theme(server_url)

    payload, errored = await call(
        server_url,
        "art_theme",
        action="update",
        theme_id=theme_id,
        rotation_interval_seconds=931,
        shuffle=False,
    )

    assert errored is False
    assert payload["theme"]["rotation_interval_seconds"] == 931
    assert payload["theme"]["shuffle"] is False

    listed, _ = await call(server_url, "art_theme", action="list")
    assert listed["themes"][0]["rotation_interval_seconds"] == 931


async def test_updating_one_field_does_not_clear_the_others(server_url):
    """The sentinel's whole reason: null is meaningful, so absent cannot mean null."""
    theme_id = await _a_theme(server_url)
    await call(server_url, "art_theme", action="update", theme_id=theme_id, rotation_interval_seconds=931)

    payload, _ = await call(server_url, "art_theme", action="update", theme_id=theme_id, name="Precisionists")

    assert payload["theme"]["name"] == "Precisionists"
    assert payload["theme"]["rotation_interval_seconds"] == 931


async def test_activating_a_theme_puts_it_on_the_wall_rather_than_arming_a_later_sync(server_url, wall_settings, wall):
    """A curator who chose a theme and saw nothing happen would think this was broken."""
    first = await _a_theme(server_url, name="American Modernists")
    second = await _a_theme(server_url, name="Surrealists")

    payload, errored = await call(server_url, "art_theme", action="activate", theme_id=second, wall_id=wall)

    assert errored is False
    # The result names the wall, so a caller reporting back can say which room.
    assert payload["wall"]["wall_id"] == wall

    listed, _ = await call(server_url, "art_theme", action="list")
    hung = {theme["theme_id"]: [entry["wall_id"] for entry in theme["hanging_on"]] for theme in listed["themes"]}
    assert hung[second] == [wall]
    assert hung[first] == []

    # The manifest is what the wall reads, so this is where "on the wall" is true.
    assert json.loads(wall_settings.manifest_path(wall).read_text())["theme"]["id"] == second


async def test_activating_publishes_exactly_the_readiness_filtered_theme(server_url, wall_settings, service, wall):
    """The chunk's acceptance criterion, end to end: a switch is a filtered publish.

    One work made displayable and two left short, so the manifest and the report
    have to disagree with the membership list in exactly the way the design says.
    """
    theme_id = await _a_theme(server_url)
    works = await _the_works(server_url)
    for artwork_id in works.values():
        await call(server_url, "art_theme", action="add", theme_id=theme_id, artwork_id=artwork_id)

    ready = works["Nighthawks"]
    source = service.add_source(
        artwork_id=ready,
        url="https://museum.example/nighthawks",
        provider="artic",
        source_class=SourceClass.INSTITUTIONAL,
        acquisition_method=AcquisitionMethod.DEZOOMIFY,
        rights_status=RightsStatus.PUBLIC_DOMAIN,
        is_primary=True,
    )
    service.record_original(
        artwork_id=ready,
        source_id=source.id,
        path="raw/nighthawks.tif",
        width=6000,
        height=4000,
        byte_size=90_000_000,
        content_hash="hash-1",
        fetch_status=FetchStatus.OK,
    )
    service.record_mat_color(artwork_id=ready, hex_rgb="#27285b", method=MatMethod.VISION_MODEL)
    service.record_rendition(
        artwork_id=ready,
        kind=RenditionKind.TV_DISPLAY,
        target_width=3840,
        target_height=2160,
        path="ready/nighthawks.jpg",
    )

    payload, errored = await call(server_url, "art_theme", action="activate", theme_id=theme_id, wall_id=wall)

    assert errored is False
    assert [entry["artwork_id"] for entry in payload["on_the_wall"]] == [ready]
    assert len(payload["not_displayable"]) == 2
    assert payload["considered"] == 3
    # Exact-match, not a substring: this sentence is the only place a caller is
    # told how much of the theme is missing, and a substring assertion is blind
    # to exactly the drift that matters — a clause added, dropped, or doubled.
    assert payload["notice"] == (
        "1 of 3 works in this theme are on the wall; 2 are not currently displayable. "
        "See not_displayable for each one and why."
    )

    # And the file the display plane reads carries exactly that one work.
    document = json.loads(wall_settings.manifest_path(wall).read_text())
    assert [entry["work_id"] for entry in document["entries"]] == [ready]
    assert document["entries"][0]["render_path"] == "ready/nighthawks.jpg"
    assert document["entries"][0]["label"]["title"] == "Nighthawks"


async def test_deleting_a_theme_that_is_hanging_somewhere_is_refused_and_names_the_wall(server_url, wall):
    """A wall losing its picture has to be a choice, and the curator has to know which wall.

    Refused whether or not another theme exists — that clause went with the
    promotion it guarded against. What the refusal owes instead is the room's own
    name, so a curator with three walls knows which one is in the way.
    """
    hanging = await _a_theme(server_url, name="American Modernists")
    await _a_theme(server_url, name="Surrealists")
    await call(server_url, "art_theme", action="activate", theme_id=hanging, wall_id=wall)

    payload, errored = await call(server_url, "art_theme", action="delete", theme_id=hanging)

    assert errored is True
    walls, _ = await call(server_url, "art_display", action="walls")
    assert walls["walls"][0]["name"] in payload["error"]
    listed, _ = await call(server_url, "art_theme", action="list")
    assert len(listed["themes"]) == 2


async def test_a_theme_taken_down_becomes_deletable(server_url, wall):
    """The route out of the refusal, exercised through the surface that offers it.

    Deleting the last theme used to be permitted *because* nothing could take one
    down. `unhang` is what pays for the refusal being absolute, so it has to work
    from the same place the tip points at.
    """
    only = await _a_theme(server_url, name="American Modernists")
    await call(server_url, "art_theme", action="activate", theme_id=only, wall_id=wall)

    _, refused = await call(server_url, "art_theme", action="delete", theme_id=only)
    assert refused is True

    _, errored = await call(server_url, "art_theme", action="unhang", wall_id=wall)
    assert errored is False

    _, errored = await call(server_url, "art_theme", action="delete", theme_id=only)
    assert errored is False
    listed, _ = await call(server_url, "art_theme", action="list")
    assert listed["themes"] == []


async def test_taking_down_does_not_republish_or_advance_the_wall(server_url, wall, wall_settings):
    """Taking a theme down is not an instruction to the display plane.

    The wall goes on showing what it was showing — publishing an empty manifest
    would blank it as a side effect of tidying up — and the counter does not move,
    because an advance here would fire a directive nobody issued.
    """
    theme_id = await _a_theme(server_url)
    await call(server_url, "art_theme", action="activate", theme_id=theme_id, wall_id=wall)
    published = wall_settings.manifest_path(wall).read_text()
    before, _ = await call(server_url, "art_display", action="walls")

    payload, errored = await call(server_url, "art_theme", action="unhang", wall_id=wall)

    assert errored is False
    # Exact-match: this sentence is the only thing telling a caller the wall did
    # not go blank, and a substring check is blind to a clause being dropped.
    assert payload["notice"] == (
        "Nothing is hanging there now. The wall goes on showing what it was showing until a theme is hung."
    )
    assert wall_settings.manifest_path(wall).read_text() == published
    after, _ = await call(server_url, "art_display", action="walls")
    assert after["walls"][0]["directive"]["sequence"] == before["walls"][0]["directive"]["sequence"]
    assert after["walls"][0]["hanging"] is None


async def test_taking_down_a_wall_holding_nothing_is_refused(server_url, wall):
    payload, errored = await call(server_url, "art_theme", action="unhang", wall_id=wall)

    assert errored is True
    assert "nothing to take down" in payload["error"]


async def test_a_step_on_one_wall_leaves_another_where_it_was(server_url, wall):
    """The reason the directive stopped being a singleton.

    One counter cannot say which display an advance was meant for, so a `next`
    aimed at the living room stepped every wall in the house.
    """
    added, errored = await call(server_url, "art_display", action="add_wall", name="Study")
    assert errored is False
    study = added["wall"]["wall_id"]

    stepped, _ = await call(server_url, "art_display", action="next", wall_id=wall)

    assert stepped["wall_id"] == wall
    listed, _ = await call(server_url, "art_display", action="walls")
    sequences = {entry["wall_id"]: entry["directive"]["sequence"] for entry in listed["walls"]}
    assert sequences[wall] == 1
    assert sequences[study] == 0


async def test_two_walls_may_hang_the_same_theme(server_url, wall):
    """No duplication, which is the property the removed boolean could not have."""
    added, _ = await call(server_url, "art_display", action="add_wall", name="Study")
    study = added["wall"]["wall_id"]
    theme_id = await _a_theme(server_url)

    await call(server_url, "art_theme", action="activate", theme_id=theme_id, wall_id=wall)
    await call(server_url, "art_theme", action="activate", theme_id=theme_id, wall_id=study)

    listed, _ = await call(server_url, "art_theme", action="list")
    assert len(listed["themes"]) == 1
    assert {entry["wall_id"] for entry in listed["themes"][0]["hanging_on"]} == {wall, study}


async def test_a_theme_that_is_not_on_the_wall_can_be_deleted(server_url):
    await _a_theme(server_url, name="American Modernists")
    spare = await _a_theme(server_url, name="Surrealists")

    payload, errored = await call(server_url, "art_theme", action="delete", theme_id=spare)

    assert errored is False
    listed, _ = await call(server_url, "art_theme", action="list")
    assert [theme["name"] for theme in listed["themes"]] == ["American Modernists"]


async def test_deleting_the_last_theme_leaves_the_wall_showing_what_it_had(server_url, wall_settings, wall):
    """Tidying the catalogue must not blank the wall as a side effect.

    Same posture as curation being stopped entirely: the display plane runs off
    the last manifest indefinitely, which is normal operation rather than
    degradation. Publishing an empty manifest here would be this plane reaching
    over and turning the art off.
    """
    theme_id = await _a_theme(server_url)
    await call(server_url, "art_display", action="sync", wall_id=wall, theme_id=theme_id)
    before = wall_settings.manifest_path(wall).read_text()

    payload, errored = await call(server_url, "art_theme", action="delete", theme_id=theme_id)

    assert errored is False
    listed, _ = await call(server_url, "art_theme", action="list")
    assert listed["themes"] == []
    assert wall_settings.manifest_path(wall).read_text() == before


async def test_deleting_a_theme_with_works_in_it_leaves_the_works_alone(server_url, seeded_titles):
    await _a_theme(server_url, name="American Modernists")
    spare = await _a_theme(server_url, name="Surrealists")
    works = await _the_works(server_url)
    await call(server_url, "art_theme", action="add", theme_id=spare, artwork_id=works["Nighthawks"])

    _, errored = await call(server_url, "art_theme", action="delete", theme_id=spare)

    assert errored is False
    catalogue, _ = await call(server_url, "art_catalogue", action="list")
    assert {work["title"] for work in catalogue["artworks"]} == set(seeded_titles)


# -- the wall -------------------------------------------------------------------


async def test_status_says_plainly_that_the_display_plane_has_never_reported(server_url):
    """The display plane does not exist yet, and the honest answer is to say so.

    Not a zero, not a green light: both would read as a reading. This is the
    state a fresh deployment is in, and it has to be legible rather than
    look like a healthy wall.

    **And it names the wall**, which is what one heartbeat per wall bought: with
    two rooms the useful sentence is "the study has not reported", and one shared
    file could only ever have said that *something* had not.
    """
    payload, errored = await call(server_url, "art_display", action="status")

    assert errored is False
    [reading] = payload["walls"]
    assert reading["display_plane_has_reported"] is False
    assert reading["age_seconds"] is None
    assert "has not reported yet" in reading["observation"]
    assert payload["observation"] == (
        f"{reading['wall_name']!r} has not reported. "
        "Each wall's own reading says whether nothing was ever written or what could not be read."
    )


async def test_sync_names_every_work_that_will_not_be_on_the_wall(server_url, wall):
    """The seeded works have no originals, so a sync puts none of them up.

    That is the whole design under test: membership in the manifest IS
    readiness, and the cost of it is that a work can sit in a theme and never
    appear. This is where the product refuses to be silent about that.
    """
    theme_id = await _a_theme(server_url)
    works = await _the_works(server_url)
    for artwork_id in works.values():
        await call(server_url, "art_theme", action="add", theme_id=theme_id, artwork_id=artwork_id)

    payload, errored = await call(server_url, "art_display", action="sync", wall_id=wall, theme_id=theme_id)

    assert errored is False
    assert payload["on_the_wall"] == []
    assert payload["considered"] == 3
    assert {entry["reason"] for entry in payload["not_displayable"]} == {"no_original"}
    assert {entry["title"] for entry in payload["not_displayable"]} == set(works)
    assert payload["notice"] == (
        "0 of 3 works in this theme are on the wall; 3 are not currently displayable. "
        "See not_displayable for each one and why."
    )


async def test_an_empty_theme_syncs_and_says_so_rather_than_failing(server_url, wall):
    theme_id = await _a_theme(server_url)

    payload, errored = await call(server_url, "art_display", action="sync", wall_id=wall, theme_id=theme_id)

    assert errored is False
    assert payload["on_the_wall"] == []
    assert payload["not_displayable"] == []
    assert payload["considered"] == 0
    # The sentence this test's own name promises. Without it the empty case is
    # the one branch of the notice nothing reads — and it is the branch that
    # used to say "All 0 works in this theme are on the wall."
    assert payload["notice"] == "This theme holds no works yet, so nothing is on the wall."
    # No pointer at a field that is empty: there is nothing to look at.
    assert "not_displayable" not in payload["notice"]


async def test_sync_reports_the_pace_the_wall_will_run_at(server_url, wall):
    theme_id = await _a_theme(server_url)
    await call(server_url, "art_theme", action="update", theme_id=theme_id, rotation_interval_seconds=931, shuffle=False)

    payload, _ = await call(server_url, "art_display", action="sync", wall_id=wall, theme_id=theme_id)

    assert payload["rotation"] == {"interval_seconds": 931, "shuffle": False}


async def test_sync_writes_the_manifest_the_display_plane_reads(server_url, wall_settings, wall):
    theme_id = await _a_theme(server_url)

    await call(server_url, "art_display", action="sync", wall_id=wall, theme_id=theme_id)

    document = json.loads(wall_settings.manifest_path(wall).read_text())
    assert document["theme"]["id"] == theme_id
    assert document["schema"]["major"] == 1


async def test_next_writes_a_directive_and_does_not_claim_the_wall_changed(server_url, wall):
    payload, errored = await call(server_url, "art_display", action="next", wall_id=wall)

    assert errored is False
    assert payload["sequence"] == 1
    assert payload["pinned_work_id"] is None
    assert "not a confirmation" in payload["notice"]


async def test_show_now_pins_the_work_and_the_sequence_advances_once_per_call(server_url, ready_work, wall):
    work = ready_work("Automat")

    first, _ = await call(server_url, "art_display", action="show_now", wall_id=wall, artwork_id=work.id)
    second, _ = await call(server_url, "art_display", action="next", wall_id=wall)

    assert first["pinned_work_id"] == work.id
    assert first["sequence"] == 1
    # A step supersedes the pin: an advance with the pin still set would read as
    # "jump there again" rather than "move on".
    assert second["sequence"] == 2
    assert second["pinned_work_id"] is None


async def test_the_directive_reaches_the_manifest(server_url, wall_settings, ready_work, wall):
    """The one hop that makes a directive real: it has to be in the file display polls."""
    theme_id = await _a_theme(server_url)
    work = ready_work("Automat")
    await call(server_url, "art_display", action="show_now", wall_id=wall, artwork_id=work.id)

    await call(server_url, "art_display", action="sync", wall_id=wall, theme_id=theme_id)

    directive = json.loads(wall_settings.manifest_path(wall).read_text())["directive"]
    assert directive["sequence"] == 1
    assert directive["pinned_work_id"] == work.id


async def test_a_theme_with_nothing_missing_says_so_in_full(server_url, service, ready_work, wall):
    """The clean branch of the notice, which nothing else reads.

    It exists precisely so that "12 of 12" is what makes "9 of 12" legible — a
    message that appeared only on trouble would train a reader to take its
    absence as reassurance. Pinned exact-match, and asserted to carry no pointer
    at an empty field.
    """
    theme_id = await _a_theme(server_url)
    for title in ("Automat", "Chop Suey"):
        work = ready_work(title)
        await call(server_url, "art_theme", action="add", theme_id=theme_id, artwork_id=work.id)

    payload, errored = await call(server_url, "art_display", action="sync", wall_id=wall, theme_id=theme_id)

    assert errored is False
    assert payload["not_displayable"] == []
    assert payload["considered"] == 2
    assert payload["notice"] == "All 2 works in this theme are on the wall."
    assert "not_displayable" not in payload["notice"]


async def test_syncing_twice_does_not_advance_the_sequence(server_url, wall_settings, wall):
    """A rebuild that advanced would fire a jump nobody issued, on every sync."""
    theme_id = await _a_theme(server_url)
    await call(server_url, "art_display", action="next", wall_id=wall)

    await call(server_url, "art_display", action="sync", wall_id=wall, theme_id=theme_id)
    await call(server_url, "art_display", action="sync", wall_id=wall, theme_id=theme_id)

    assert json.loads(wall_settings.manifest_path(wall).read_text())["directive"]["sequence"] == 1


async def test_showing_an_archived_work_is_refused_rather_than_pinned(server_url, service, wall):
    """An archived work is out of circulation, so a pin naming one can never be carried out."""
    works = await _the_works(server_url)
    service.archive_artwork(works["Nighthawks"])

    payload, errored = await call(server_url, "art_display", action="show_now", wall_id=wall, artwork_id=works["Nighthawks"])

    assert errored is True
    assert "archived" in payload["error"]
