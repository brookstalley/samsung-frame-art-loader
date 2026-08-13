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

import json

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


PROTOTYPE_SCALE = 2000


def test_the_prototype_scale_opens_as_a_contact_sheet_and_stays_legible(ui, service, seed_the_served_catalogue):
    """The chunk's acceptance criterion, against a real catalogue rather than a number.

    The threshold test above stubs `total` behind one work, which is the right
    shape for pinning a branch and cannot answer this: legibility is a claim about
    two thousand tiles actually laid out by a real browser, and a stub renders
    one. `build_large_catalogue` exists precisely so the claim can be measured.

    **It also reports what a stub hid.** `fetchAllWorks` stops at `PAGE_CEILING`
    pages and the server's default page is `DEFAULT_LIST_LIMIT`, so the grid can
    reach 1,250 works and no further — at the prototype's scale the runaway guard
    bites. That is a known debt, recorded in `core/api.js`, and the thing this
    test pins is that it bites *audibly*: the heading says how many of how many,
    and the note says how many are held and not shown. A grid that stopped short
    in silence is the failure this product exists to refuse, and it would look
    exactly like a collection of 1,250.
    """
    seed_the_served_catalogue(size=PROTOTYPE_SCALE)
    # Asked rather than assumed: `server_url` boots on `seeded_service`, so the
    # catalogue this server holds is the seeded three plus what was just built.
    # A hard-coded total would be a test asserting against its own arithmetic.
    held = service.list_artworks(limit=1).total
    assert held >= PROTOTYPE_SCALE

    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid li.tile")

    # The default at this scale is the contact sheet — image only, uniform tiles.
    assert ui.page.locator("ul.grid.contact-sheet").count() == 1
    assert ui.page.locator("li.card").count() == 0

    shown = ui.page.locator("ul.grid li.tile").count()
    assert 0 < shown < held, "the guard did not bite, so this test is no longer about what it says"
    assert ui.page.inner_text("h2") == f"{shown} of {held} works"
    assert f"{held - shown} more are held and are not on this page" in ui.text()

    # Legible: every tile the same size, and big enough to judge a picture in.
    # Sampled rather than measured over every tile — a thousand
    # `getBoundingClientRect` calls tell you nothing the first fifty do not.
    boxes = ui.page.eval_on_selector_all(
        "ul.grid li.tile .card-image",
        "nodes => nodes.slice(0, 50).map(n => { const r = n.getBoundingClientRect();"
        " return [Math.round(r.width), Math.round(r.height)]; })",
    )
    widths = {box[0] for box in boxes}
    heights = {box[1] for box in boxes}
    assert max(widths) - min(widths) <= 1, f"tiles were not uniform across a row: {sorted(widths)}"
    assert max(heights) - min(heights) <= 1, f"tiles were not uniform down the grid: {sorted(heights)}"
    assert min(widths) >= 100, f"a contact sheet at this scale collapsed to {min(widths)}px tiles"


# -- the loading state and the grid's geometry --------------------------------


def test_the_loading_state_does_not_guess_a_geometry_it_cannot_know(ui):
    """No skeleton until the total is in, because the total is what sizes it.

    The density default is a function of how many works there are, and nothing
    knows that until the first page answers. A placeholder painted before then can
    only guess — and an earlier draft of this screen guessed contact sheet, which
    is wrong for every collection under a few hundred works and so jumped from
    twelve small tiles to N wide cards on the commonest path there is.
    """
    held = []
    ui.page.route("**/api/works?*", lambda route: held.append(route))

    ui.open("#collection")
    ui.page.wait_for_selector("#view h2")

    assert "Loading the collection" in ui.text()
    assert ui.page.locator("ul.grid-skeleton").count() == 0, "the placeholder guessed a geometry it could not know"
    assert ui.page.locator("ul.grid").count() == 0

    for route in held:
        route.abort()


def test_the_skeleton_stands_at_the_tile_geometry_the_grid_will_have(ui):
    """ "Skeletons occupy the final geometry" — asserted as tile boxes, not as classes.

    Two pages, the second held open, so the placeholder is on screen long enough
    to be measured against the grid that replaces it. Held rather than raced: the
    skeleton exists for a slow answer, and a test that had to win a race would
    report a green meaning only that the machine was slow that time.

    The tile's own width and height are what is compared. A placeholder that drew
    faithful tiles and then spanned the whole page while the grid sat beside a
    13rem rail would pass a class check and fail a reader's eyes.
    """
    answered = {"count": 0}
    held = []
    first = a_listing(
        [a_catalogue_work(artwork_id="a", title="First")],
        total=2000,
        truncated=True,
    )

    def handler(route):
        answered["count"] += 1
        if answered["count"] == 1:
            route.fulfill(status=200, content_type="application/json", body=json.dumps(first))
        else:
            held.append(route)

    ui.page.route("**/api/works?*", handler)

    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid-skeleton > li")
    # 2,000 works is above the threshold, so the placeholder is the contact sheet
    # the grid will be — the density is read from the same total by the same
    # function, which is what makes the two agree by construction.
    assert ui.page.locator("ul.grid-skeleton.contact-sheet").count() == 1
    # It says nothing to a screen reader: twelve empty tiles announced as list
    # items is noise over the announcement that matters.
    assert ui.page.get_attribute("ul.grid-skeleton", "aria-hidden") == "true"

    box = "n => { const r = n.getBoundingClientRect(); return [Math.round(r.width), Math.round(r.height)]; }"
    skeleton_tile = ui.page.eval_on_selector("ul.grid-skeleton > li", box)

    # The paging loop has to have asked for a second page before it can be
    # released; waiting on the condition rather than on a duration.
    for _ in range(200):
        if held:
            break
        ui.page.wait_for_timeout(50)
    assert held, "the paging loop never asked for a second page"

    for route in held:
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(a_listing([], total=2000, truncated=False, offset=1)),
        )
    ui.page.wait_for_selector("ul.grid > li")

    grid_tile = ui.page.eval_on_selector("ul.grid > li", box)
    assert skeleton_tile == grid_tile, f"the skeleton stood at {skeleton_tile} and the grid arrived at {grid_tile}"


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


def a_page_with_facets(*options):
    return a_listing(
        [a_catalogue_work(artwork_id="a", title="Nighthawks")],
        total=1,
        facets=[
            a_facet_group(
                "movement",
                list(options) or [a_facet_option("Baroque", 51), a_facet_option("Rococo", 0)],
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

    # **Armed before the click, and waited on.** This asserted on the recorded
    # request list after waiting for the address bar, which is a different event:
    # `go` writes `location.hash` synchronously and the fetch is issued from the
    # `hashchange` task after it, so the wait could return before the request
    # existed. It did — reliably at module scope and not at suite scope, which is
    # the worst kind of green. Waiting for the request itself is both correct and
    # a stronger claim: the test now fails if no narrowed request is ever sent,
    # rather than if none had been sent yet.
    def a_narrowed_works_request(request):
        return "/api/works?" in request.url and "movement=" in request.url

    with ui.page.expect_request(a_narrowed_works_request) as narrowed:
        ui.page.click("button.facet-option:has-text('Baroque')")

    assert "movement=Baroque" in narrowed.value.url
    assert all("movement=Baroque" in url for url in ui.requests_matching("/api/works?") if "movement=" in url)


def test_a_facet_value_holding_the_separator_survives_the_address(ui):
    """The fragment joins several values with a pipe; a value may contain one.

    That is the failure the wire's own rule is about — a facet value may hold a
    comma, so the route takes one repeated parameter per kind rather than a
    comma-joined list — and picking a rarer character for the fragment would only
    have made the same bet at longer odds. The values are escaped before they are
    joined, so the separator is the only bare pipe the string can hold, and this
    is the test that says so: one value, one parameter, both halves intact.
    """
    ui.serve("**/api/works?*", a_page_with_facets(a_facet_option("Ochre | Umber", 7)))

    ui.open("#collection")
    ui.page.wait_for_selector(".facet-option")

    def a_narrowed_works_request(request):
        return "/api/works?" in request.url and "movement=" in request.url

    with ui.page.expect_request(a_narrowed_works_request) as narrowed:
        ui.page.click("button.facet-option:has-text('Ochre')")

    # One parameter carrying the whole value, not two carrying half each.
    assert narrowed.value.url.count("movement=") == 1
    assert "movement=Ochre%20%7C%20Umber" in narrowed.value.url

    # And the address round-trips it: pressing the same option again *removes* it.
    # That is the assertion that actually exercises the escaping — if the pipe had
    # been lost the client would read two values back out of one, not recognise
    # the option as chosen, and add a second copy instead of clearing it.
    def a_works_request(request):
        return "/api/works?" in request.url

    with ui.page.expect_request(a_works_request) as again:
        ui.page.click("button.facet-option:has-text('Ochre')")

    assert "movement=" not in again.value.url, "choosing the value twice added a second copy instead of clearing it"


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


def test_a_collection_with_no_themes_draws_no_tick_it_cannot_act_on(ui, seeded_service):
    """A control with nothing behind it is the dead end the facet rules forbid.

    With no theme to put a work into, a selection can do nothing — so there is no
    toolbar for it and no checkbox on every tile. The paired positive is every
    membership test above, each of which has a theme and finds the tick.
    """
    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid li.card")

    assert ui.page.locator("input.tile-select").count() == 0
    assert ui.page.locator(".selection").count() == 0


def test_the_theme_being_shown_is_not_offered_as_somewhere_to_add(ui, a_theme_holding_one_work):
    """Every work on screen is already in it, so that control could only refuse.

    The picker defaulting to the first theme is what made this reachable in one
    move: showing a theme, pressing Add, and being told the work is already there.
    """
    theme, _works = a_theme_holding_one_work

    ui.open(f"#collection?theme={theme.id}")
    ui.page.wait_for_selector("ul.grid li.card")

    assert ui.page.locator("#add-to-theme").count() == 0
    assert ui.page.locator("button:has-text('Remove from this theme')").count() == 1


def test_adding_a_work_the_theme_already_holds_is_not_an_error(ui, display, a_theme_holding_one_work):
    """The store refuses a duplicate, so the loop must not walk into one.

    Selecting a work already in the theme alongside one that is not would, with a
    naive loop, apply part of the edit and then report a refusal — a half-applied
    change with nothing saying which half. What the theme already holds is read
    first and skipped, and the sentence says so rather than staying quiet about it.
    """
    theme, works = a_theme_holding_one_work

    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid li.card")
    ui.page.check(f"li.card[data-artwork='{works[0].id}'] input.tile-select")
    ui.page.check(f"li.card[data-artwork='{works[1].id}'] input.tile-select")
    ui.page.select_option("#add-to-theme", theme.id)
    ui.page.click("button:has-text('Add to theme')")
    ui.page.wait_for_selector(".selection-status:has-text('Added 1 work to Baroque. 1 was already in it.')")

    assert ui.page.locator("#error").is_hidden(), "a duplicate in the selection was reported as a failure"
    assert len(display.theme_works(theme.id)) == 2


def test_a_refusal_partway_through_leaves_exactly_the_works_that_did_not_go(ui, display, a_theme_holding_one_work):
    """The loop can stop halfway, and what it leaves behind has to be the retry.

    Reading the theme first removes the refusal the client can foresee; it cannot
    remove the one it cannot — here the second work is deleted from the catalogue
    between that read and its own write. Two half-states are then available and
    both are wrong: a selection cleared, which loses the record of which works did
    not go, and a selection left whole, which carries the work that already landed
    back into the retry. Exactly the works that did not go stay ticked, and the
    retry sends exactly those.

    **Only the refusal is stubbed.** Accepting one write and refusing the next is
    what no server can be asked for on purpose; both other writes go to the real
    route, so what the theme holds after each press is the store's own answer
    rather than this test's — and the read in front of the retry is filtering
    against a theme that really did take one work and really did not take the
    other.
    """
    theme, works = a_theme_holding_one_work
    refusal = f"No artwork with id {works[2].id!r} is in the catalogue."
    writes = []

    def refuse_the_second_write(route):
        writes.append(json.loads(route.request.post_data)["artwork_id"])
        if len(writes) == 2:
            route.fulfill(status=400, content_type="application/json", body=json.dumps({"error": refusal}))
        else:
            route.continue_()

    ui.page.route(f"**/api/themes/{theme.id}/works", refuse_the_second_write)

    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid li.card")
    ui.page.check(f"li.card[data-artwork='{works[1].id}'] input.tile-select")
    ui.page.check(f"li.card[data-artwork='{works[2].id}'] input.tile-select")
    ui.page.select_option("#add-to-theme", theme.id)
    # The live region holds one sentence, and before the click it is this one — so
    # the outcome waited for below is text only the refusal can have produced.
    assert "2 selected." in ui.text()

    ui.page.click("button:has-text('Add to theme')")
    ui.page.wait_for_selector(".selection-status:has-text('Added 1 of 2 to Baroque.')")

    # Read whole rather than by substring: how far the loop got and what pressing
    # Add again will do are one sentence, and a client that dropped the second
    # half would leave the curator to guess whether retrying repeats the work.
    assert ui.page.inner_text(".selection-status") == (
        "Added 1 of 2 to Baroque. The rest are still selected, so pressing Add again retries only those."
    )

    # Why it stopped is the server's sentence, not one composed here: the failure
    # is rethrown precisely so the banner can carry the server's own words beside
    # the region's account of how far the loop got.
    ui.page.wait_for_selector(f'#error:has-text("{refusal}")')

    # Exactly the work that did not go, and only it. Clearing the selection and
    # leaving it whole both satisfy "something is ticked"; neither is this.
    assert ui.page.locator("input.tile-select:checked").count() == 1
    assert ui.page.locator(f"li.card[data-artwork='{works[2].id}'] input.tile-select").is_checked()
    assert writes == [works[1].id, works[2].id]
    assert {held.artwork.id for held in display.theme_works(theme.id)} == {works[0].id, works[1].id}

    # The retry is pressing the same button, so it has to still be pressable.
    assert ui.page.is_enabled("button:has-text('Add to theme')")
    ui.page.click("button:has-text('Add to theme')")
    ui.page.wait_for_selector(".selection-status:has-text('Added 1 work to Baroque.')")

    # The clause that matters: one further write, carrying the work that was
    # refused and not the one that landed. Whole again rather than by substring —
    # a retry that offered the landed work back would be skipped by the read in
    # front of the loop and say so, and " 1 was already in it." is the only trace
    # of a selection that was never reduced.
    assert writes == [works[1].id, works[2].id, works[2].id]
    assert ui.page.inner_text(".selection-status") == "Added 1 work to Baroque."
    assert ui.page.locator("input.tile-select:checked").count() == 0
    assert {held.artwork.id for held in display.theme_works(theme.id)} == {work.id for work in works}


def test_removing_a_theme_s_last_member_leaves_a_sentence_not_a_blank(ui, a_theme_holding_one_work):
    """An empty grid with nothing said is indistinguishable from a broken screen."""
    theme, works = a_theme_holding_one_work

    ui.open(f"#collection?theme={theme.id}")
    ui.page.wait_for_selector("ul.grid li.card")
    ui.page.check(f"li.card[data-artwork='{works[0].id}'] input.tile-select")
    ui.page.click("button:has-text('Remove from this theme')")
    ui.page.wait_for_selector(".empty")

    assert NOTHING_MATCHES in ui.text()
    assert "the theme \u201cBaroque\u201d" in ui.text()
    assert ui.page.inner_text("h2") == "0 works in \u201cBaroque\u201d"


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
