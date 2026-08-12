"""The navigation, in a real browser: three destinations, and what hangs off them.

`information-architecture.md` § Direction is the norm this file is the executed
half of. Its own enforcement note says the violation — a destination that names a
pipeline stage rather than an intention — "has no import signature and no grep",
so what a test *can* hold is asserted here and the judgement stays with the
Critic: that the navigation is these three and no more, that Health is reachable
and not in it, that a contextual screen returns where it was opened from, and
that the indicator which replaced the Health tab actually speaks.
"""

import pytest

# At import time, not in a fixture. A marker deselection still *collects* this
# module, so the default run — which does not install the browser group — has to
# skip here rather than fail on the missing plugin.
pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

#: What the navigation must offer, in order. The Walls first: the thing the
#: product exists to produce was the fourth item, behind three tabs about
#: producing it.
DESTINATIONS = ["The Walls", "Collection", "Discover"]


# -- three destinations, flat -------------------------------------------------


def test_the_navigation_is_the_three_destinations_and_nothing_else(ui, seeded_service):
    """Five pipeline-stage tabs became three things a curator sets out to do.

    The count is asserted as well as the labels, because the failure this norm
    exists to catch is *addition*: a sixth subsystem wanting a sixth entry for
    locally-good reasons. A test that only checked the three were present would
    pass against a navigation that had grown a fourth.
    """
    ui.open()
    ui.page.wait_for_selector("nav.destinations button")

    assert ui.page.locator("nav.destinations button").all_inner_texts() == DESTINATIONS


def test_no_entry_in_the_navigation_names_a_pipeline_stage(ui, seeded_service):
    """The acceptance criterion, as close to mechanical as it gets.

    The five it replaced were Works, Discovery, Themes, On the wall and Health —
    the pipeline's internal stages in pipeline order. Each was correct as the
    chunk that produced it, which is exactly why no per-chunk review caught the
    sum.
    """
    ui.open()
    ui.page.wait_for_selector("nav.destinations button")

    labels = ui.page.locator("nav.destinations button").all_inner_texts()
    for stage in ("Works", "Discovery", "Themes", "On the wall", "Health"):
        assert stage not in labels, f"{stage} is a stage of the pipeline, not something a curator sets out to do"


def test_the_navigation_is_flat(ui, seeded_service):
    """No hierarchy above the three, no drawer, no nesting.

    A `nav` holding a nested list or a disclosure is the shape the IA rules out
    in as many words, and it is the shape a fourth destination arrives wearing.
    """
    ui.open()
    ui.page.wait_for_selector("nav.destinations button")

    assert ui.page.locator("nav.destinations ul, nav.destinations details, nav.destinations nav").count() == 0


@pytest.mark.parametrize(("view", "heading"), [("walls", "The Walls"), ("collection", "works"), ("discover", "Discover")])
def test_each_destination_is_reachable_by_clicking_and_says_where_it_landed(ui, seeded_service, view, heading):
    ui.open()
    ui.page.wait_for_selector("nav.destinations button")

    ui.page.click(f"nav.destinations button[data-view='{view}']")
    ui.page.wait_for_selector(f"#view h2:has-text('{heading}')")

    assert ui.page.locator(f"nav.destinations button[data-view='{view}'][aria-current='page']").count() == 1


@pytest.mark.parametrize("view", ["walls", "collection", "discover"])
def test_each_destination_is_addressable(ui, seeded_service, view):
    """Reachable by clicking is not the requirement; every screen has a URL."""
    ui.open(f"#{view}")
    ui.page.wait_for_selector("#view h2")

    assert ui.page.locator(f"nav.destinations button[data-view='{view}'][aria-current='page']").count() == 1


def test_the_product_opens_on_the_walls(ui, seeded_service):
    """The thing the product exists to produce, rather than a tab about producing it."""
    ui.open()
    ui.page.wait_for_selector("#view h2")

    assert ui.page.inner_text("#view h2") == "The Walls"


# -- Health: reachable, and not navigable-to ----------------------------------


def test_health_is_not_in_the_navigation(ui, seeded_service):
    ui.open()
    ui.page.wait_for_selector("nav.destinations button")

    assert ui.page.locator("nav.destinations button[data-view='health']").count() == 0


def test_health_is_reached_by_the_indicator_that_replaced_its_tab(ui, seeded_service, a_health_reading):
    """The demotion is only safe because the indicator expands to it.

    An appliance-status panel that is out of the navigation and has no way in is
    not a demotion, it is a deletion.
    """
    ui.serve("**/api/health", a_health_reading())
    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid")

    ui.page.click("#status")
    ui.page.wait_for_selector("#view h2:has-text('Health')")

    assert "This deployment's geometry" in ui.text()


def test_health_still_has_an_address_of_its_own(ui, seeded_service, a_health_reading):
    """ "Not navigable-to" is a statement about the navigation, never about the URL.

    A failure has to be able to link to it, and a curator has to be able to
    bookmark it.
    """
    ui.serve("**/api/health", a_health_reading())
    ui.open("#health")
    ui.page.wait_for_selector("#view h2:has-text('Health')")

    assert "The living room" in ui.text()
    assert "The catalogue was last backed up" in ui.text()


def test_health_names_each_wall_rather_than_one_display_plane(ui, a_health_reading, a_wall_reading):
    """One reading for an installation with two rooms cannot name the room.

    That is the whole reason the heartbeat became one per wall, and the screen has
    to carry the distinction through: two panels, each headed by the wall it is
    about, with the silent one identifiable.
    """
    ui.serve(
        "**/api/health",
        a_health_reading(
            walls=[
                a_wall_reading(wall_id="wall-1", name="The living room"),
                a_wall_reading(wall_id="wall-2", name="The study", absent=True),
            ]
        ),
    )
    ui.open("#health")
    ui.page.wait_for_selector("#view h2:has-text('Health')")

    headings = ui.page.locator("#view .panel h3").all_inner_texts()
    assert "The living room" in headings
    assert "The study" in headings
    # "for this wall", not "here". Both wave-1 chunks reworded this sentence and
    # pinned their own wording; the per-wall one survives the merge, because with
    # a panel per room "here" has several possible referents and names none of
    # them — the ambiguity that splitting the heartbeat per wall removed.
    assert "Nothing has ever written a heartbeat for this wall" in ui.text()


def test_a_health_reading_the_screen_cannot_parse_is_stated_rather_than_thrown(ui):
    """The product's only alerting surface must not answer a bad payload with a stack trace.

    An exception here reaches the page's error banner reading like the server is
    down, which is a different fact leading to a different next move. Saying what
    the reading was missing is the honest answer, and it keeps the rest of the
    screen — the backup and the geometry — readable.
    """
    ui.serve(
        "**/api/health",
        {
            "backup": {
                "path": "/art/backup-receipt.json",
                "completed_at": "2026-08-12T03:00:00+00:00",
                "age_seconds": 22440.0,
                "absent": False,
                "problem": None,
                "description": "The catalogue was last backed up 6 hours ago.",
                "reported": None,
            },
            "artwork_box": {"width": 3840, "height": 2160, "pixels_per_inch": 72.0, "floor_inches": 20.0},
        },
    )
    ui.open("#health")
    ui.page.wait_for_selector("#view h2:has-text('Health')")

    assert "carries no walls" in ui.text()
    assert "The catalogue was last backed up" in ui.text()
    assert ui.page.locator("#error:not([hidden])").count() == 0


# -- the status indicator ------------------------------------------------------


def test_the_indicator_is_on_every_destination(ui, seeded_service):
    """Always present is the whole contract. An indicator you have to reach is a tab."""
    for view in ("walls", "collection", "discover"):
        ui.open(f"#{view}")
        ui.page.wait_for_selector("#view h2")
        assert ui.page.locator("#status").count() == 1, view


def test_the_indicator_names_which_wall_went_quiet(ui, a_health_reading, a_wall_reading):
    """Colour is never the sole carrier — and here nor is the glyph.

    "Something is wrong somewhere" is a sentence a curator cannot act on, and it
    is what a single aggregated heartbeat could say. The reading is per wall so
    that this one names the room, and the other room is not implicated.
    """
    ui.serve(
        "**/api/health",
        a_health_reading(
            walls=[
                a_wall_reading(wall_id="wall-1", name="The living room"),
                a_wall_reading(wall_id="wall-2", name="The study", absent=True),
            ]
        ),
    )
    ui.open("#collection")
    ui.page.wait_for_selector("#status[data-state='unwell']")

    indicator = ui.page.locator("#status")
    words = indicator.inner_text()
    assert "The study has not reported" in words
    assert "The living room" not in words, "the wall that is reporting was named as a problem"
    # Three carriers, and the glyph is the one a stylesheet cannot supply.
    assert indicator.locator(".glyph").count() == 1


def test_the_indicator_says_well_when_every_observation_is_well(ui, a_health_reading):
    """The paired negative: an indicator that always warns is one nobody reads.

    Stubbed rather than seeded, because "the backup ran and the display plane is
    reporting" is a state a test deployment cannot be asked for — there is no
    display plane, by design.
    """
    ui.serve("**/api/health", a_health_reading())
    ui.open("#collection")
    ui.page.wait_for_selector("#status[data-state='well']")

    assert ui.page.inner_text("#status").strip().endswith("Well")


def test_the_indicator_takes_its_state_from_the_readings_and_not_from_the_summary(ui, a_health_reading, a_wall_reading):
    """The aggregate's `description` is a summary, never a fourth signal.

    It applies no threshold and reaches no verdict, deliberately: whether four
    minutes is late depends on whether that television was switched off on
    purpose, which the curation plane does not know. A client that read the words
    would be inventing the judgement the plane declined to make — so a cheerful
    sentence over a silent wall must not turn the indicator green.
    """
    ui.serve(
        "**/api/health",
        a_health_reading(
            walls=[a_wall_reading(name="The study", absent=True)],
            description="Every wall has reported.",
        ),
    )
    ui.open("#collection")
    ui.page.wait_for_selector("#status[data-state='unwell']")

    assert "The study has not reported" in ui.page.inner_text("#status")


def test_the_indicator_names_a_reading_that_could_not_be_read(ui, a_health_reading, a_wall_reading):
    """`absent` and `unreadable` are different answers, and the indicator keeps them apart.

    Nothing has ever written one is a normal state on a fresh deployment; a file
    that exists and will not parse is a fault, and the observation records the two
    separately for exactly that reason. An indicator that read only `absent` would
    report a corrupted receipt as well.
    """
    ui.serve(
        "**/api/health",
        a_health_reading(walls=[a_wall_reading(name="The study", problem="Expecting value: line 1 column 1")]),
    )
    ui.open("#collection")
    ui.page.wait_for_selector("#status[data-state='unwell']")

    words = ui.page.inner_text("#status")
    assert "The study's heartbeat cannot be read" in words
    assert "has not reported" not in words, "an unreadable file was reported as a silent one"


def test_the_indicator_names_a_backup_that_has_never_run(ui, a_health_reading, a_backup_reading):
    """The catalogue is the irreplaceable asset, and its absence is the reading to watch.

    Held apart from the wall readings because it is a different subject: a wall
    going quiet costs an evening's pictures, and no backup costs everything.
    """
    ui.serve("**/api/health", a_health_reading(backup=a_backup_reading(absent=True)))
    ui.open("#collection")
    ui.page.wait_for_selector("#status[data-state='unwell']")

    assert "The catalogue has never been backed up" in ui.page.inner_text("#status")


def test_the_indicator_refuses_to_report_well_from_a_reading_it_did_not_take(ui, a_health_reading):
    """A green dot computed from nothing is this product's characteristic failure in a costume.

    `GET /api/health`'s shape is another chunk's to change — it changed once
    during this very work — and the indicator has no field name of its own to
    fall back on. What it must never do is treat an observation it cannot find as
    an observation that was fine.
    """
    reading = a_health_reading()
    del reading["walls"]
    ui.serve("**/api/health", reading)
    ui.open("#collection")
    ui.page.wait_for_selector("#status[data-state='unwell']")

    assert "carries no walls" in ui.page.inner_text("#status")


def test_a_deployment_with_no_wall_at_all_is_not_reported_as_well(ui, a_health_reading):
    """A wall is created when the plane first opens the catalogue, so none is a state.

    Nothing can be shown at all, and there is no missing heartbeat to say so —
    which is exactly the shape of silence an empty list would sail through.
    """
    ui.serve("**/api/health", a_health_reading(walls=[]))
    ui.open("#collection")
    ui.page.wait_for_selector("#status[data-state='unwell']")

    assert "No wall is recorded" in ui.page.inner_text("#status")


def test_a_health_reading_that_cannot_be_fetched_does_not_read_as_well(ui):
    """And it does not take the screen underneath it down either.

    The indicator's own failure is not a refusal of whatever the curator just
    did, so it says so in the indicator rather than in the page's error banner.
    """
    ui.serve("**/api/health", [(503, {"error": "the panel is unavailable"})])
    ui.open("#collection")
    ui.page.wait_for_selector("#status[data-state='unwell']")

    assert "could not be fetched" in ui.page.inner_text("#status")
    # The grid still painted, and nothing shouted at the curator about it.
    assert ui.page.locator("#error:not([hidden])").count() == 0


# -- a contextual screen returns where it was opened from ---------------------


@pytest.fixture
def one_work(service, seeded_service):
    """The catalogue's first work, whichever it is."""
    return service.list_artworks(limit=1).entries[0].artwork


def test_a_work_opened_from_collection_returns_to_collection(ui, one_work):
    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid li.card")

    ui.page.click("ul.grid li.card .card-title button")
    # The back link, not a heading: Collection has an `h2` of its own, so waiting
    # for one after the click waits for nothing and everything below reads the
    # grid rather than the work. Only a contextual screen draws a way back, which
    # makes its arrival the fact that the work opened — and what it *says* is
    # still the assertion.
    ui.page.wait_for_selector("#view button:has-text('←')")

    back = ui.page.locator("#view button", has_text="←").first
    assert back.inner_text() == "← Collection"
    back.click()
    ui.page.wait_for_selector("ul.grid")
    assert ui.page.locator("nav.destinations button[data-view='collection'][aria-current='page']").count() == 1


def test_the_same_work_opened_from_the_walls_returns_to_the_walls(ui, one_work):
    """The requirement, and the failure it replaces.

    The route out of a detail screen used to be a fixed parent — "← All works",
    whatever route in had been taken — so a Work reached from anywhere but the
    grid sent the curator somewhere they had not been. Nothing about the work
    changes here; only where it was opened from.
    """
    ui.open(f"#work/{one_work.id}?from=walls")
    ui.page.wait_for_selector("#view h2")

    back = ui.page.locator("#view button", has_text="←").first
    assert back.inner_text() == "← The Walls"
    back.click()
    ui.page.wait_for_selector("#view h2:has-text('The Walls')")


def test_the_destination_a_work_was_opened_from_stays_lit(ui, one_work):
    """A contextual screen is *in* the destination it came from, and says so."""
    ui.open(f"#work/{one_work.id}?from=walls")
    ui.page.wait_for_selector("#view h2")

    assert ui.page.locator("nav.destinations button[data-view='walls'][aria-current='page']").count() == 1


def test_where_a_work_was_opened_from_is_in_the_address(ui, one_work):
    """Which is what makes browser back do this natively, and a link carry it."""
    ui.open("#walls")
    ui.page.wait_for_selector("#view h2")
    ui.page.evaluate(f"() => go('work', {one_work.id!r})")
    ui.page.wait_for_selector("#view h2")

    assert ui.page.evaluate("() => window.location.hash") == f"#work/{one_work.id}?from=walls"


def test_the_default_opener_is_left_out_of_the_address(ui, one_work):
    """A parameter that says what its absence already says is noise in a copied URL.

    A Work opened from Collection is the ordinary case, and `?from=collection`
    changes nothing — a missing opener resolves to exactly that. The parameter
    earns its place only when it carries information.
    """
    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid li.card")
    ui.page.evaluate(f"() => go('work', {one_work.id!r})")
    ui.page.wait_for_selector("#view h2")

    assert ui.page.evaluate("() => window.location.hash") == f"#work/{one_work.id}"


def test_browser_back_leaves_a_work_for_the_destination_it_was_opened_from(ui, one_work):
    """Every contextual screen is a real URL, so the browser's own back does this."""
    ui.open("#walls")
    ui.page.wait_for_selector("#view h2:has-text('The Walls')")
    ui.page.evaluate(f"() => go('work', {one_work.id!r})")
    ui.page.wait_for_selector("#view h2")

    ui.page.go_back()
    ui.page.wait_for_selector("#view h2:has-text('The Walls')")


def test_a_work_reached_with_no_opener_still_has_a_way_out(ui, one_work):
    """A bookmark and an agent's link carry no opener, and must not be a dead end."""
    ui.open(f"#work/{one_work.id}")
    ui.page.wait_for_selector("#view h2")

    assert ui.page.locator("#view button", has_text="←").first.inner_text() == "← Collection"


# -- the persistent search affordance -----------------------------------------


def test_the_search_box_is_on_every_destination(ui, seeded_service):
    """Persistent because at thousands of works it is the primary way in, and a
    retrieval mechanism you must first navigate to is one more step on the most
    frequent action."""
    for view in ("walls", "collection", "discover"):
        ui.open(f"#{view}")
        ui.page.wait_for_selector("#view h2")
        assert ui.page.locator("#search-form input#search").count() == 1, view


def test_searching_from_anywhere_lands_in_the_collection(ui, seeded_service):
    ui.open("#walls")
    ui.page.wait_for_selector("#view h2:has-text('The Walls')")

    ui.page.fill("#search", "Nighthawks")
    ui.page.press("#search", "Enter")
    ui.page.wait_for_selector("#view h2:has-text('matching')")

    assert ui.page.locator("nav.destinations button[data-view='collection'][aria-current='page']").count() == 1


def test_a_search_is_in_the_address_and_narrows_the_grid(ui, service, seeded_service):
    """Addressable state, and the affordance actually doing something.

    A search box that navigates and changes nothing is a dead control, which
    teaches a curator the collection cannot be searched.
    """
    service.add_artwork(title="A singular study of nothing")

    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid li.card")
    everything = ui.page.locator("ul.grid li.card").count()

    ui.page.fill("#search", "singular study")
    ui.page.press("#search", "Enter")
    ui.page.wait_for_selector("#view h2:has-text('matching')")

    assert ui.page.evaluate("() => window.location.hash") == "#collection?q=singular%20study"
    found = ui.page.locator("ul.grid li.card").count()
    assert found == 1
    assert found < everything, "the search matched everything, so it cannot have narrowed anything"


def test_the_search_is_the_catalogue_s_and_not_this_screen_s(ui, service, seeded_service):
    """The query goes to the server, which searches more than the grid holds.

    This screen filtered client-side over title and artist for exactly as long as
    there was no server-side search to send the query to. `GET /api/works` grew
    `q` in the same wave as this chunk, and it searches six fields — the medium
    among them — over the whole catalogue rather than over whatever one screen
    happened to load.

    Medium is the field that tells the two apart: a client-side filter reading
    title and artist cannot find this work however many pages it fetched, so this
    test fails the moment the search stops being the catalogue's. The count in
    the heading is the second half of the same claim — it is a statement about
    the catalogue, not about this page.
    """
    service.add_artwork(title="Untitled", medium="Tempera on panel")

    ui.open("#collection?q=Tempera")
    ui.page.wait_for_selector("#view h2:has-text('matching')")

    assert ui.page.locator("ul.grid li.card").count() == 1
    # "1 work", not "1 works". The heading pluralises as of the chunk that gave
    # the grid its rails: a theme holding one work made the old wording visible
    # often enough to fix, and this line is the copy it was asserting.
    assert ui.page.inner_text("#view h2") == "1 work matching \u201cTempera\u201d"


def test_a_search_finds_a_work_by_its_artist(ui, seeded_service):
    """Attribution is the first thing anyone judges a work by, so it is searchable.

    The seeded work is "The Persistence of Memory", which holds none of the
    letters of the artist searched for — so a search reading only the title
    cannot pass this, which is the point.
    """
    ui.open("#collection?q=Dal%C3%AD")
    ui.page.wait_for_selector("ul.grid li.card")

    assert ui.page.locator("ul.grid li.card").count() == 1
    assert "The Persistence of Memory" in ui.text()


def test_a_search_that_matches_nothing_says_so_and_offers_the_way_back(ui, seeded_service):
    """An empty grid with no sentence reads as an empty collection."""
    ui.open("#collection?q=nothingwhatevermatchesthis")
    # The empty state itself, rather than the heading above it: Collection's
    # loading placeholder is an `h2` too, so waiting on one could return before
    # the search had answered. Same assertion, sounder wait.
    ui.page.wait_for_selector("#view .empty")

    assert "Nothing held matches" in ui.text()
    ui.page.click("#view button:has-text('Show everything')")
    ui.page.wait_for_selector("ul.grid li.card")


def test_a_bookmarked_search_reopens_with_the_box_filled_in(ui, seeded_service):
    """Otherwise the grid is narrowed and the control that narrowed it is blank —
    a curator seeing a short collection with no visible reason."""
    ui.open("#collection?q=study")
    ui.page.wait_for_selector("#view h2:has-text('matching')")

    assert ui.page.input_value("#search") == "study"


def test_browser_back_undoes_a_search(ui, seeded_service):
    """A search is a navigation, so the way out of one is the way out of any of them."""
    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid")
    everything = ui.page.locator("ul.grid li.card").count()

    ui.page.fill("#search", "study")
    ui.page.press("#search", "Enter")
    ui.page.wait_for_selector("#view h2:has-text('matching')")

    ui.page.go_back()
    # The searched screen holds no grid at all — nothing seeded matches — so
    # waiting on one is what distinguishes the repaint from the stale DOM.
    ui.page.wait_for_selector("ul.grid li.card")
    assert ui.page.locator("ul.grid li.card").count() == everything


# -- the addresses the surface used to answer to ------------------------------


@pytest.mark.parametrize(
    ("old", "now", "heading"),
    [
        ("#works", "collection", "works"),
        ("#manifest", "walls", "The Walls"),
        ("#discovery", "discover", "Discover"),
    ],
)
def test_a_bookmark_from_before_the_reshape_opens_the_screen_that_took_over(ui, seeded_service, old, now, heading):
    ui.open(old)
    ui.page.wait_for_selector(f"#view h2:has-text('{heading}')")

    # And the address bar is corrected, so what a curator copies out of it is
    # what this surface would produce.
    assert ui.page.evaluate("() => window.location.hash") == f"#{now}"
