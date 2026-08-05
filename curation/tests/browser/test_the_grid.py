"""The catalogue grid: its paging loop, its dead tiles, and where focus lands.

These are the three behaviours the client carried with no executed coverage at
all, and they are here in that order. Each is paired with the assertion that
would fail if the behaviour over-fired — a loop that stops is only correct if it
also collected everything, and a focus move that always fires steals focus from
a freshly loaded page.
"""

import pytest
from payloads import a_catalogue_work, a_listing

# At import time, not in a fixture. A marker deselection still *collects* this
# module, so the default run — which does not install the browser group — has to
# skip here rather than fail on the missing plugin.
pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)


# -- the paging loop --------------------------------------------------------


@pytest.fixture
def a_catalogue_past_one_page(service, seeded_service):
    """101 works — one more than `MAX_LIST_LIMIT`, so exactly two pages.

    One over the cap rather than comfortably over it: the second page holding a
    single work is what catches an off-by-one that drops or repeats the boundary
    row, which a round 200 would render invisible.
    """
    for number in range(98):
        service.add_artwork(title=f"Study number {number:03d}")
    return 101


def test_the_grid_pages_through_a_catalogue_larger_than_one_page(ui, a_catalogue_past_one_page):
    """Every work arrives, across as many requests as that takes."""
    ui.open("#works")
    ui.page.wait_for_selector("h2")

    assert ui.page.inner_text("h2") == f"{a_catalogue_past_one_page} works"
    assert ui.page.locator("ul.grid li.card").count() == a_catalogue_past_one_page

    # The count alone passes against a server that ignored the cap and answered
    # in one page, which would leave the loop this test exists for unexecuted.
    # Asserting the requests is what pins that it actually paged.
    pages = ui.requests_matching("/api/works?")
    assert len(pages) == 2
    assert "offset=0" in pages[0]
    assert "offset=100" in pages[1]


def test_the_grid_says_nothing_is_missing_when_nothing_is(ui, a_catalogue_past_one_page):
    """The shortfall note is absent when every work arrived.

    The paired negative: a note that always renders would report a catalogue as
    truncated whenever it is not, and the test above would pass regardless.
    """
    ui.open("#works")
    ui.page.wait_for_selector("ul.grid")

    assert "are held and are not on this page" not in ui.text()


def test_the_grid_stops_when_a_page_comes_back_empty(ui):
    """A server insisting there is always more must not loop forever.

    `truncated` alone is not a stopping condition — a server that keeps saying
    "more" while returning nothing would spin until the tab died. The loop stops
    on what actually arrived, and this is the only way to ask it to prove that.
    """
    ui.serve(
        "**/api/works?*",
        [
            a_listing([a_catalogue_work(artwork_id="a", title="First")], total=50, truncated=True),
            a_listing([], total=50, truncated=True, offset=1),
        ],
    )
    ui.open("#works")
    ui.page.wait_for_selector("ul.grid")

    # Two requests and no more: the second answered empty, and that ended it.
    assert len(ui.requests_matching("/api/works?")) == 2
    assert ui.page.locator("ul.grid li.card").count() == 1


def test_the_grid_reports_what_the_runaway_guard_left_out(ui):
    """When `PAGE_CEILING` bites, the page says how many are missing.

    A list that stops short in silence is indistinguishable from a catalogue
    holding no more, which is the exact silence this product exists to refuse.
    """
    ui.serve(
        "**/api/works?*",
        a_listing([a_catalogue_work(artwork_id="a", title="Endless")], total=999, truncated=True),
    )
    ui.open("#works")
    # Scoped to the view: the shell carries a permanently-present `p.note` of its
    # own for errors, so an unscoped match waits on the wrong element and times
    # out against a page that painted correctly.
    ui.page.wait_for_selector("#view p.note")

    # The guard is 50 pages, and this stub hands back one work per page.
    assert len(ui.requests_matching("/api/works?")) == 50
    assert ui.page.inner_text("h2") == "50 of 999 works"
    assert "949 more are held and are not on this page" in ui.text()


# -- a tile whose image has gone --------------------------------------------


def test_a_tile_whose_image_cannot_be_loaded_says_so(ui, work_with_an_image):
    """Availability was true when the listing was built; the file can go after.

    Without the error handler the tile paints as a blank box — silent, and
    indistinguishable from a work that simply has no image.
    """
    work_with_an_image(title="Nighthawks")
    ui.page.route("**/thumbnail", lambda route: route.fulfill(status=404, body="gone"))

    ui.open("#works")
    ui.page.wait_for_selector(".card-image-absent")

    assert "Its image could not be loaded just now." in ui.text()
    # The broken image must be gone, not merely covered: an <img> left in place
    # is still announced, and still draws the browser's own broken-image glyph.
    assert ui.page.locator("ul.grid img").count() == 0


def test_a_tile_whose_image_loads_keeps_its_picture(ui, work_with_an_image):
    """The paired negative — the fallback fires on error and not otherwise."""
    work_with_an_image(title="Nighthawks")

    ui.open("#works")
    ui.page.wait_for_selector("ul.grid img")

    assert "Its image could not be loaded just now." not in ui.text()


# -- where the keyboard lands -----------------------------------------------


def test_navigating_moves_focus_into_the_view(ui, seeded_service):
    """Without this the surface is not keyboard-navigable at all.

    Navigation replaces the whole view, destroying whatever was focused and
    leaving focus on <body> — so the next Tab starts again from the top of the
    page, above the navigation the user just used.
    """
    ui.open("#works")
    ui.page.wait_for_selector("ul.grid")

    ui.page.click("nav.tabs button[data-view='themes']")
    ui.page.wait_for_selector("#new-theme-name")

    assert ui.focused() == "view"


def test_the_first_paint_does_not_steal_focus(ui, seeded_service):
    """The paired negative: a page that grabs focus on load is its own bug.

    A focus move written to fire unconditionally would pass the test above and
    fail a reader who has just arrived, so this asserts what must be absent.
    """
    ui.open("#works")
    ui.page.wait_for_selector("ul.grid")

    assert ui.focused() != "view"
