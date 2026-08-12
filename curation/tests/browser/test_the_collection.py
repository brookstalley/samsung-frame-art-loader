"""Collection's rails, its density control, and its three different empties.

`test_the_grid.py` beside this covers the grid's paging loop, its dead tiles and
where focus lands after a navigation — the behaviours the screen had before it
grew anything to narrow it with. This file covers what Collection became: a
density that is a control rather than a decision, two rails that filter, the
membership editing that happens against the works being organised, and the three
empty states that are three facts rather than one.

**The three empties get three tests, and each asserts the other two are absent.**
One test that finds "nothing here" satisfied by any of them is exactly the shape
that reads as coverage and is not: conflating the first two tells a curator with
3,000 works that they own nothing, and conflating the third with the second
reports the expected result of following a suggestion as a failed query.
"""

import pytest
from payloads import (
    a_catalogue_work,
    a_facet_group,
    a_facet_option,
    a_listing,
)

# At import time, not in a fixture. A marker deselection still *collects* this
# module, so the default run — which does not install the browser group — has to
# skip here rather than fail on the missing plugin.
pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)


#: The three headlines, so a test asserting one can assert the absence of the
#: others by name rather than by an "empty" class every branch would share.
NOTHING_HELD = "Nothing is held yet."
NOTHING_MATCHES = "Nothing held matches this filter."


def artist_headline(name: str) -> str:
    return f"Nothing by {name} yet."


# -- the three empties --------------------------------------------------------


def test_a_collection_holding_nothing_at_all_invites_the_curator_into_discover(ui):
    """The first empty: there is nothing, and the way out is acquiring something.

    Stubbed, and this is the one place in this file that has to be: `server_url`
    boots on `seeded_service`, so the real server this suite runs against always
    holds three works. An empty catalogue is a state it cannot be asked for.
    """
    ui.serve("**/api/works?*", a_listing([]))

    ui.open("#collection")
    ui.page.wait_for_selector(".empty")

    assert NOTHING_HELD in ui.text()
    assert NOTHING_MATCHES not in ui.text()
    assert "Nothing by" not in ui.text()
    # The invitation, not merely the statement: an empty state that names no next
    # move is a dead end with better wording.
    assert ui.page.locator("button:has-text('Go to Discover')").count() == 1


def test_a_filter_matching_nothing_names_the_filter_and_offers_a_way_out(ui):
    """The second empty: there is plenty, and this narrowing found none of it."""
    ui.open("#collection?q=aubergine")
    ui.page.wait_for_selector(".empty")

    assert NOTHING_MATCHES in ui.text()
    assert NOTHING_HELD not in ui.text()
    assert "Nothing by" not in ui.text()
    # The filter itself, said back. "No results" without saying what was asked
    # for leaves a curator guessing which narrowing did it.
    assert "the search “aubergine”" in ui.text()
    assert ui.page.locator("button:has-text('Show everything')").count() == 1


def test_filtering_to_one_artist_and_holding_none_says_so_as_a_normal_state(ui):
    """The third empty, and the one a conversation makes common.

    The artists a conversation surfaces are by definition ones the curator could
    not have named, so a collection holding nothing by them is the overwhelmingly
    common outcome. Reporting that as "nothing matches these filters" would be
    true and useless.
    """
    ui.open("#collection?artist=Wassily%20Kandinsky")
    ui.page.wait_for_selector(".empty")

    assert artist_headline("Wassily Kandinsky") in ui.text()
    assert NOTHING_HELD not in ui.text()
    assert NOTHING_MATCHES not in ui.text()
    # Named as normal rather than broken, and the offer is the search that would
    # actually find some — the collection holds none, so searching the collection
    # is not it.
    assert ui.page.locator("button:has-text('Look for some in Discover')").count() == 1


def test_an_artist_filter_with_a_search_beside_it_is_the_filter_empty(ui):
    """The pair that keeps the third empty from swallowing the second.

    "Nothing by Kandinsky yet" is a statement about the collection. With a search
    term also in force it would be a statement about the collection that the
    curator's own query might be the cause of, and the honest answer names both.
    """
    ui.open("#collection?artist=Wassily%20Kandinsky&q=aubergine")
    ui.page.wait_for_selector(".empty")

    assert NOTHING_MATCHES in ui.text()
    assert artist_headline("Wassily Kandinsky") not in ui.text()
    assert "the search “aubergine”" in ui.text()
    assert "artist “Wassily Kandinsky”" in ui.text()


# -- density ------------------------------------------------------------------


def test_the_default_at_the_prototype_scale_is_the_contact_sheet(ui):
    """Above a few hundred works the grid opens as pictures and nothing else.

    Stubbed at the total rather than seeded: the acceptance criterion is about
    2,000 works, seeding 2,000 rows costs minutes per test, and what is under
    test is the client's threshold — which reads `total` and nothing else.
    """
    ui.serve(
        "**/api/works?*",
        a_listing([a_catalogue_work(artwork_id="a", title="Nighthawks")], total=2000),
    )

    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid")

    assert ui.page.locator("ul.grid.contact-sheet").count() == 1
    assert ui.page.locator("li.tile").count() == 1
    # The paired negative: the catalogue card's own body must not be there, or
    # "contact sheet" would be a class name over the same tile.
    assert ui.page.locator("li.card").count() == 0


def test_the_default_at_a_small_collection_is_the_catalogue(ui):
    """The paired negative, against the real server's three works.

    A default written as a constant would pass the test above and hand a curator
    with forty works a wall of anonymous thumbnails.
    """
    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid")

    assert ui.page.locator("ul.grid.contact-sheet").count() == 0
    assert ui.page.locator("li.card").count() == 3


def test_a_density_in_the_address_survives_a_reload_and_a_link(ui):
    """The whole of "remembered": the address is the memory.

    Opening the fragment *is* following a link; reloading is the other half. Both
    have to land on the density the curator chose rather than on the one the size
    of the collection would have picked.
    """
    ui.open("#collection?density=contact")
    ui.page.wait_for_selector("ul.grid")
    assert ui.page.locator("ul.grid.contact-sheet").count() == 1

    ui.page.reload()
    ui.page.wait_for_selector("ul.grid")

    assert ui.page.locator("ul.grid.contact-sheet").count() == 1
    assert ui.page.locator("li.card").count() == 0


def test_choosing_a_density_writes_it_into_the_address(ui):
    """A control whose state is not in the URL is a control no link carries."""
    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid")

    ui.page.click("button:has-text('Contact sheet')")
    ui.page.wait_for_selector("ul.grid.contact-sheet")

    assert "density=contact" in ui.page.url


# -- the loading state and the grid's geometry --------------------------------


def test_the_loading_state_stands_in_at_the_grid_s_own_geometry(ui):
    """Skeleton tiles, at the size of the tiles they are standing in for.

    Held open rather than raced: the placeholder exists for a slow answer, and a
    test that had to win a race would report a green meaning only that the
    machine was slow enough that time.
    """
    held = []
    ui.page.route("**/api/works?*", lambda route: held.append(route))

    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid-skeleton")

    tiles = ui.page.locator("ul.grid-skeleton > li")
    assert tiles.count() > 0
    # It stands in for the grid; it must not answer to the grid's own name, or
    # every wait in this suite would be satisfied by a page holding no works.
    assert ui.page.locator("ul.grid").count() == 0
    # And it says nothing to a screen reader: twelve empty tiles announced as
    # list items is noise over the announcement that matters.
    assert ui.page.get_attribute("ul.grid-skeleton", "aria-hidden") == "true"

    for route in held:
        route.abort()


def test_the_tiles_do_not_reflow_as_the_pictures_arrive(ui, work_with_an_image):
    """The defect this client has already shipped: a grid of art that jumps.

    Three works of three different shapes. If a tile took the shape of its own
    picture the three would differ, and every one of them would change height at
    the moment its image decoded.
    """
    work_with_an_image(title="A tall one", width=800, height=1600)
    work_with_an_image(title="A wide one", width=1600, height=600)
    work_with_an_image(title="A square one", width=1200, height=1200)

    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid li.card")

    def heights():
        return ui.page.eval_on_selector_all(
            "ul.grid li.card .card-image",
            "nodes => nodes.map(node => Math.round(node.getBoundingClientRect().height))",
        )

    before = heights()
    ui.page.wait_for_function(
        "() => Array.from(document.querySelectorAll('ul.grid img')).every(img => img.complete && img.naturalWidth > 0)"
    )
    after = heights()

    assert len(before) == 6, "the three seeded works and the three with pictures did not all render"
    # Within a pixel, not identical to the pixel: the columns are fractional, so
    # a box sized by `aspect-ratio` lands on either side of a rounding boundary.
    # A tile taking the shape of its own picture would differ by hundreds.
    assert max(after) - min(after) <= 1, f"tiles took the shape of their own pictures: {after}"
    assert before == after, f"the grid reflowed as the images arrived: {before} then {after}"


# -- the facet rail -----------------------------------------------------------


def a_page_with_facets():
    return a_listing(
        [a_catalogue_work(artwork_id="a", title="Nighthawks")],
        total=1,
        facets=[
            a_facet_group(
                "movement",
                [a_facet_option("Baroque", 51), a_facet_option("Rococo", 0)],
            ),
        ],
    )


def test_a_facet_option_that_would_select_nothing_is_disabled_and_still_counted(ui):
    """Disabled, not hidden — and the count inside the control's own name.

    A disabled control is skipped by the tab sequence, so a count living in
    adjacent text is a count a screen-reader user never hears. And a vocabulary
    that shrank as filters were applied would read as the collection having lost
    values rather than as an empty intersection.
    """
    ui.serve("**/api/works?*", a_page_with_facets())

    ui.open("#collection")
    ui.page.wait_for_selector(".facet-option")

    rococo = ui.page.locator("button.facet-option", has_text="Rococo")
    assert rococo.count() == 1, "a zero-count option was hidden rather than disabled"
    assert rococo.is_disabled()
    assert rococo.inner_text() == "Rococo (0)"

    baroque = ui.page.locator("button.facet-option", has_text="Baroque")
    assert baroque.is_enabled()
    assert baroque.inner_text() == "Baroque (51)"


def test_choosing_a_facet_narrows_at_the_server_as_its_own_parameter(ui):
    """The filter goes to the server, spelled the way the route spells it.

    One repeated parameter per kind, never comma-joined: a facet value may itself
    contain a comma, and a separator a value can hold is a parser that goes wrong
    on the catalogue rather than on the request.
    """
    ui.serve("**/api/works?*", a_page_with_facets())

    ui.open("#collection")
    ui.page.wait_for_selector(".facet-option")
    ui.page.click("button.facet-option:has-text('Baroque')")
    ui.page.wait_for_function("() => window.location.hash.includes('movement=Baroque')")

    narrowed = [url for url in ui.requests_matching("/api/works?") if "movement=" in url]
    assert narrowed, "choosing a facet sent no narrowed request"
    assert all("movement=Baroque" in url for url in narrowed)


# -- the theme rail, and membership edited in place ---------------------------


@pytest.fixture
def a_theme_holding_one_work(display, seeded_service):
    """A real theme with one of the three seeded works in it."""
    theme = display.add_theme(name="Baroque")
    works = [entry.artwork for entry in seeded_service.list_artworks().entries]
    display.add_to_theme(theme_id=theme.id, artwork_id=works[0].id)
    return theme, works


def test_a_theme_chip_filters_the_grid_to_its_members(ui, a_theme_holding_one_work):
    """Themes stopped being a destination and became a rail that filters."""
    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid li.card")
    assert ui.page.locator("ul.grid li.card").count() == 3

    ui.page.click("button.theme-chip:has-text('Baroque')")
    ui.page.wait_for_function("() => document.querySelectorAll('ul.grid li.card').length === 1")

    assert "in “Baroque”" in ui.page.inner_text("h2")


def test_membership_is_edited_from_the_grid_without_leaving_it(ui, display, a_theme_holding_one_work):
    """Organising happens in the collection, against the works being organised."""
    theme, works = a_theme_holding_one_work

    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid li.card")

    ui.page.check(f"li.card[data-artwork='{works[1].id}'] input.tile-select")
    ui.page.check(f"li.card[data-artwork='{works[2].id}'] input.tile-select")
    assert "2 selected." in ui.text()

    ui.page.select_option("#add-to-theme", theme.id)
    ui.page.click("button:has-text('Add to theme')")
    ui.page.wait_for_selector(".selection-status:has-text('Added 2 works to Baroque.')")

    # Still on the screen it started on, with the same works under it.
    assert ui.page.url.endswith("#collection")
    assert ui.page.locator("ul.grid li.card").count() == 3
    # And the server really holds it, rather than the page having said so.
    assert len(display.theme_works(theme.id)) == 3


def test_editing_membership_does_not_drop_the_keyboard_to_the_top_of_the_page(ui, display, a_theme_holding_one_work):
    """The curator is standing on the control they just pressed.

    An edit that repainted the screen would destroy it, and finishing the edit
    disables it — either way the keyboard lands back on the document, several
    hundred tiles above where the work was happening. Focus goes to the outcome
    sentence instead, which is inside the toolbar the curator is using.
    """
    theme, works = a_theme_holding_one_work

    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid li.card")
    ui.page.check(f"li.card[data-artwork='{works[1].id}'] input.tile-select")
    ui.page.select_option("#add-to-theme", theme.id)
    ui.page.click("button:has-text('Add to theme')")
    ui.page.wait_for_selector(".selection-status:has-text('Added 1 work to Baroque.')")

    assert ui.focused() == "Added 1 work to Baroque."


def test_removing_from_a_theme_takes_the_tiles_out_and_says_what_is_left(ui, display, a_theme_holding_one_work):
    """The count over the grid must not outlive the tiles it counted."""
    theme, works = a_theme_holding_one_work
    display.add_to_theme(theme_id=theme.id, artwork_id=works[1].id)

    ui.open(f"#collection?theme={theme.id}")
    ui.page.wait_for_selector("ul.grid li.card")
    assert ui.page.locator("ul.grid li.card").count() == 2

    ui.page.check(f"li.card[data-artwork='{works[0].id}'] input.tile-select")
    ui.page.click("button:has-text('Remove from this theme')")
    ui.page.wait_for_function("() => document.querySelectorAll('ul.grid li.card').length === 1")

    assert ui.page.inner_text("h2") == "1 work in “Baroque”"
    assert len(display.theme_works(theme.id)) == 1


def test_a_repaint_that_is_not_a_navigation_does_not_move_focus(ui):
    """The rule that binds every live region here, asserted at its own level.

    `refresh()` is what a poll would call — the same repaint, without the
    navigation that earns a focus move. A view that always focused itself would
    take the keyboard away from whatever the curator was standing on, every
    time.
    """
    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid")

    ui.page.focus("button.density-option[aria-pressed='false']")
    ui.page.evaluate("() => refresh()")
    ui.page.wait_for_selector("ul.grid")

    assert ui.focused() != "view"
