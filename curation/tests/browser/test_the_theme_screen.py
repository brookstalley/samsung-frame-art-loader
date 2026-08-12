"""The four acts that are a theme's own, in a real browser against a real server.

A theme's name, the order its works reach the wall in, where it hangs, and
whether it exists — none of it expressible as JSON, so neither Python suite runs
a line of it. Membership is edited here as well as from the grid: the grid is
where a theme gets built, and this is where a curator already looking at the
order drops one out of it.

**Two of these are debts this screen carried into the chunk that owns it.** Its
membership control read "Remove", which promises a *work* is gone when it is
still catalogued and in every other theme; and its hang button changed a room
with no question asked, while flow 6 makes activation the one act that gets one.
Both are asserted here, because both were invisible to every suite that existed.

**The reorder tests are a pair and neither is redundant.** One drives the real
server and proves the new order survives a reload; the other hands the client an
answer no catalogue would produce and proves the table shows *that*. A screen
that repainted optimistically, or that threw the answer away and read the order
back, passes the first and fails the second — and the first alone is what "the
reorder works" usually means.
"""

import pytest

# At import time, not in a fixture. A marker deselection still *collects* this
# module, so the default run — which does not install the browser group — has to
# skip here rather than fail on the missing plugin.
pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from payloads import a_catalogue_work, a_theme_detail  # noqa: E402  (after the skip guard)

#: Titles chosen so curated order and alphabetical order agree at the start —
#: which is what lets a moved row be told from an unmoved one by reading.
POLLOCKS = ("Autumn Rhythm", "Blue Poles", "Convergence")


@pytest.fixture
def winter(services, service):
    """A theme holding three works in a known order, hanging nowhere."""
    theme = services.display.add_theme(name="Winter")
    for position, title in enumerate(POLLOCKS):
        work = service.add_artwork(title=title)
        services.display.add_to_theme(theme_id=theme.id, artwork_id=work.id, position=position)
    return theme


def _titles(ui):
    """The member table's Title column, in the order it is painted."""
    return ui.page.locator("tbody tr td:nth-child(2)").all_inner_texts()


def _painted(ui):
    """Wait until the member table has arrived, which the first paint does not carry."""
    ui.page.wait_for_selector("tbody tr")


def _first_row_becomes(ui, title):
    """A wait that is false before the act and true only after it.

    The member table exists throughout a reorder, so waiting on the table, on a
    heading or on the panel waits for nothing and the assertions beneath read the
    order that was already there — which passes for exactly as long as the write
    happens to win a race nothing is holding open.
    """
    ui.page.wait_for_function(
        "(title) => { const cell = document.querySelector('tbody tr td:nth-child(2)');"
        " return cell && cell.textContent === title; }",
        arg=title,
    )


def _row_becomes(ui, index, title):
    """`_first_row_becomes` for a move that leaves the first row where it was."""
    ui.page.wait_for_function(
        "([index, title]) => { const cells = document.querySelectorAll('tbody tr td:nth-child(2)');"
        " return cells[index] && cells[index].textContent === title; }",
        arg=[index, title],
    )


def _count(ui):
    """The member count on the panel that has a member table — Winter's, in every fixture here."""
    return ui.page.locator(".panel", has=ui.page.locator("tbody tr")).locator("p.muted").first.inner_text()


def _labels(ui, selector):
    """Every accessible name matching the selector, which Playwright has no one call for."""
    return sorted(ui.page.locator(selector).evaluate_all("els => els.map((el) => el.getAttribute('aria-label'))"))


def _confirm(ui, label):
    ui.page.wait_for_selector("dialog.confirm[open]")
    ui.page.click(f"dialog.confirm .confirm-actions button:has-text('{label}')")


class TestReordering:
    def test_a_move_takes_effect_and_survives_a_reload(self, ui, winter):
        """The order is the theme's, so it has to be the catalogue's and not the page's.

        The reload is the half that matters: a table that reordered itself and
        told nobody looks identical until the curator comes back to it.
        """
        ui.open("#theme")
        _painted(ui)
        assert _titles(ui) == list(POLLOCKS)

        ui.page.click("button[aria-label='Move Autumn Rhythm later']")
        _first_row_becomes(ui, "Blue Poles")
        assert _titles(ui) == ["Blue Poles", "Autumn Rhythm", "Convergence"]

        ui.open("#theme")
        _painted(ui)
        assert _titles(ui) == ["Blue Poles", "Autumn Rhythm", "Convergence"]

    def test_a_work_added_through_this_screen_can_then_be_moved(self, ui, winter, service):
        """The whole round trip through the doors a curator actually uses.

        Every other test here starts from a fixture that hands `add_to_theme` an
        explicit dense position, and the Add button posts an artwork and nothing
        else — so the shape those fixtures build is one no browser can produce.
        While an add left the work unplaced, the list this table renders and the
        list the service renumbered were different lists, and a move against a
        theme built this way either did nothing or sent the work the wrong way.
        Adding first is what makes this test able to see that.
        """
        service.add_artwork(title="Number 1")
        ui.open("#theme")
        _painted(ui)

        ui.page.select_option(f"#add-{winter.id}", label="Number 1")
        ui.page.click("button:has-text('Add')")
        ui.page.wait_for_function("() => document.querySelectorAll('tbody tr').length === 4")
        assert _titles(ui) == [*POLLOCKS, "Number 1"]

        # Waiting on a row that is *not* already what it will become — the first
        # row never changes here, so waiting on it would wait for nothing and the
        # assertion below would read the order that was already on screen.
        ui.page.click("button[aria-label='Move Number 1 earlier']")
        _row_becomes(ui, 2, "Number 1")
        assert _titles(ui) == ["Autumn Rhythm", "Blue Poles", "Number 1", "Convergence"]

        # And back down, which is the direction that had never worked.
        ui.page.click("button[aria-label='Move Number 1 later']")
        _row_becomes(ui, 2, "Convergence")
        assert _titles(ui) == ["Autumn Rhythm", "Blue Poles", "Convergence", "Number 1"]

    def test_the_table_is_painted_from_the_answer_and_not_from_the_move_it_sent(self, ui, winter):
        """`POST .../position` answers with the resulting order precisely so this is possible.

        The stub answers with a list no catalogue on this server holds, so three
        different implementations are told apart in one assertion: a client that
        swapped the rows itself would show the three Pollocks reordered, one that
        threw the answer away and read the order back would show them unmoved,
        and only one that repaints from the response shows what is below.

        Which is not a quibble about round trips. The service clamps and
        renumbers a position, so where a work actually lands is its answer to
        give — a screen that predicts it is right until the day it is not, and
        wrong silently.
        """
        ui.open("#theme")
        _painted(ui)

        ui.serve(
            "**/api/themes/*/works/*/position",
            a_theme_detail([a_catalogue_work(artwork_id="only-1", title="Only what the answer said")]),
        )
        ui.page.click("button[aria-label='Move Autumn Rhythm later']")
        _first_row_becomes(ui, "Only what the answer said")

        assert _titles(ui) == ["Only what the answer said"]

    def test_the_ends_of_the_order_offer_no_move_that_would_do_nothing(self, ui, winter):
        """The first work cannot go earlier and the last cannot go later.

        A disabled control rather than an absent one: the row keeps its shape, so
        the buttons do not shuffle sideways as a work reaches the end of the list
        and land somewhere else under a curator's cursor.
        """
        ui.open("#theme")
        _painted(ui)

        assert ui.page.is_disabled("button[aria-label='Move Autumn Rhythm earlier']")
        assert ui.page.is_disabled("button[aria-label='Move Convergence later']")
        assert ui.page.is_enabled("button[aria-label='Move Autumn Rhythm later']")
        assert ui.page.is_enabled("button[aria-label='Move Convergence earlier']")


class TestTheMembershipControl:
    def test_it_names_the_theme_the_work_is_leaving_rather_than_saying_remove(self, ui, winter):
        """ "Remove" alone promises the work is gone, and it is not.

        `information-architecture.md` rules the bare word out for a work: there
        is no delete of one, the work stays catalogued and stays in every other
        theme, and a curator who believes removal is destructive hesitates over
        something cheap. Naming the theme is the fix that stays true — borrowing
        "Archive" would say something false about the catalogue instead.
        """
        ui.open("#theme")
        _painted(ui)

        assert ui.page.locator("tbody button", has_text="Remove").all_inner_texts() == (["Remove from Winter"] * len(POLLOCKS))
        # Nothing anywhere on the screen says the bare word.
        assert ui.page.locator("button", has_text="Remove").count() == len(POLLOCKS)
        # And the accessible name says which work as well as which theme, since
        # three identically labelled buttons are three identical announcements.
        assert [
            ui.page.locator("tbody button", has_text="Remove").nth(index).get_attribute("aria-label")
            for index in range(len(POLLOCKS))
        ] == [f"Remove {title} from Winter" for title in POLLOCKS]

    def test_removing_a_work_leaves_the_rest_in_order(self, ui, winter):
        """And repaints from the answer, which is the same shape a move gets back."""
        ui.open("#theme")
        _painted(ui)

        ui.page.click("button[aria-label='Remove Blue Poles from Winter']")
        _first_row_becomes(ui, "Autumn Rhythm")
        ui.page.wait_for_function("() => document.querySelectorAll('tbody tr').length === 2")

        assert _titles(ui) == ["Autumn Rhythm", "Convergence"]

    def test_the_theme_says_how_many_works_it_holds(self, ui, winter):
        """The count `information-architecture.md` makes this screen's secondary content.

        The numbered column is not it: reading the last row's number is
        arithmetic performed on a table, and a curator deciding whether a theme
        is worth hanging wants the size stated. It follows a removal because an
        add and a remove both answer with the new order, so a count painted once
        would be wrong on the second glance rather than absent.
        """
        ui.open("#theme")
        _painted(ui)
        assert _count(ui) == "3 works"

        ui.page.click("button[aria-label='Remove Blue Poles from Winter']")
        ui.page.wait_for_function("() => document.querySelectorAll('tbody tr').length === 2")

        assert _count(ui) == "2 works"

    def test_one_work_is_not_one_works(self, ui, winter):
        """The count is read, so it is written the way it is read."""
        ui.open("#theme")
        _painted(ui)

        for title in ("Blue Poles", "Convergence"):
            ui.page.click(f"button[aria-label='Remove {title} from Winter']")
        ui.page.wait_for_function("() => document.querySelectorAll('tbody tr').length === 1")

        assert _count(ui) == "1 work"


class TestRenaming:
    def test_the_controls_that_act_on_a_theme_say_which_theme(self, ui, winter, services):
        """Three themes, three identical panels, and one of these buttons destroys something.

        `accessibility-spec.md` asks a control to name what it acts on, and the
        membership table in this same panel already does. These three did not:
        somebody moving through the form controls one at a time heard "Name, edit
        text", "Rename", "Delete" once per theme with nothing distinguishing
        them, and had to reconstruct which panel they were in from reading order.
        Two themes rather than one, because with one theme every naming scheme
        including no scheme at all announces unambiguously.
        """
        services.display.add_theme(name="Late night")
        ui.open("#theme")
        _painted(ui)

        assert _labels(ui, "button[aria-label^='Rename ']") == ["Rename Late night", "Rename Winter"]
        assert _labels(ui, "button[aria-label^='Delete ']") == ["Delete Late night", "Delete Winter"]
        assert ui.page.get_attribute(f"#rename-{winter.id}", "aria-label") == "Name of Winter"

    def test_the_accessible_names_follow_the_new_name_too(self, ui, winter):
        """A control announcing a theme by its old name is worse than one naming none.

        The visible words on these three never change, so nothing on screen shows
        this going stale — which is exactly why it would.
        """
        ui.open("#theme")
        _painted(ui)

        ui.page.fill("#rename-" + winter.id, "Late night")
        ui.page.click("button[aria-label='Rename Winter']")
        ui.page.wait_for_selector("h3:has-text('Late night')")

        assert ui.page.locator("button[aria-label='Delete Late night']").count() == 1
        assert ui.page.locator("button[aria-label='Delete Winter']").count() == 0
        assert ui.page.get_attribute(f"#rename-{winter.id}", "aria-label") == "Name of Late night"

    def test_the_heading_and_the_membership_controls_both_follow_the_new_name(self, ui, winter):
        """Two places name the theme, and a rename that moved one is worse than neither.

        A table still offering "Remove from Winter" under a heading reading
        "Late night" leaves a curator working out which of the two to believe.
        """
        ui.open("#theme")
        _painted(ui)

        ui.page.fill("#rename-" + winter.id, "Late night")
        ui.page.click("button:has-text('Rename')")
        ui.page.wait_for_selector("h3:has-text('Late night')")

        assert ui.page.locator("button", has_text="Remove from Late night").count() == len(POLLOCKS)
        assert ui.page.locator("button", has_text="Remove from Winter").count() == 0

    def test_the_field_shows_the_name_the_catalogue_stored_rather_than_the_one_typed(self, ui, winter):
        """The service trims, so the two differ — and the field is where it shows.

        A screen painting its own input would leave the field reading " Late
        night " beside a heading and a listing that both say "Late night", and
        the next rename would send the untrimmed string back.
        """
        ui.open("#theme")
        _painted(ui)

        ui.page.fill("#rename-" + winter.id, "  Late night  ")
        ui.page.click("button:has-text('Rename')")
        ui.page.wait_for_selector("h3:has-text('Late night')")

        assert ui.page.input_value("#rename-" + winter.id) == "Late night"

    def test_a_name_with_nothing_in_it_is_refused_in_the_servers_words(self, ui, winter):
        """The rule lives in the service, and its refusal reaches the curator unchanged."""
        ui.open("#theme")
        _painted(ui)

        ui.page.fill("#rename-" + winter.id, "   ")
        ui.page.click("button:has-text('Rename')")
        ui.page.wait_for_selector("#error:not([hidden])")

        assert ui.page.inner_text("#error") == "name cannot be empty."
        assert ui.page.locator("h3", has_text="Winter").count() == 1


class TestHanging:
    def test_the_room_is_not_changed_until_the_question_has_been_answered(self, ui, winter, services):
        """Flow 6's one confirmation, on the screen that had none at all.

        The dialog names the theme *and* the wall, even in a house with one wall:
        a question that reads correctly today only because there is one possible
        target is the last place a mistake could have been caught.
        """
        wall = services.display.survey_walls()[0].wall
        ui.open("#theme")
        _painted(ui)

        ui.page.click(f"button:has-text('Hang on {wall.name}')")
        ui.page.wait_for_selector("dialog.confirm[open]")

        assert ui.page.inner_text("dialog.confirm .confirm-title") == f"Hang Winter on {wall.name}?"
        assert f"Everyone in the house sees {wall.name} change." in ui.page.inner_text("dialog.confirm .confirm-consequence")
        assert services.display.hanging_on(wall.id) is None

    def test_the_consequence_is_the_builds_own_summary_rather_than_a_guess(self, ui, winter, services):
        """Evaluated with `GET /api/manifest`, which answers without writing.

        The works here hold no images, so the honest answer is that none of them
        would reach the wall — which is exactly what a curator wants to be told
        before pressing the button rather than after. A sentence composed on the
        client could only have said "3 works".
        """
        wall = services.display.survey_walls()[0].wall
        preview = services.display.build_manifest(wall.id, winter.id)

        ui.open("#theme")
        _painted(ui)
        ui.page.click(f"button:has-text('Hang on {wall.name}')")
        ui.page.wait_for_selector("dialog.confirm[open]")

        assert ui.page.inner_text("dialog.confirm .confirm-consequence").startswith(preview.summarise())

    def test_declining_leaves_the_wall_alone(self, ui, winter, services):
        """Escape is a no, and a no here means nothing was published."""
        wall = services.display.survey_walls()[0].wall
        ui.open("#theme")
        _painted(ui)

        ui.page.click(f"button:has-text('Hang on {wall.name}')")
        ui.page.wait_for_selector("dialog.confirm[open]")
        ui.page.keyboard.press("Escape")
        ui.page.wait_for_selector("dialog.confirm", state="detached")

        assert services.display.hanging_on(wall.id) is None
        # Still offered, so declining left the screen able to try again.
        assert ui.page.locator("button", has_text=f"Hang on {wall.name}").count() == 1

    def test_confirming_hangs_it_and_lands_on_the_wall_it_changed(self, ui, winter, services):
        """The wall view repaints from the manifest that was published, not from the preview.

        Waited on the wall section rather than on a heading: the theme screen
        already carries an `h2`, so a heading wait would match instantly and the
        assertions below would read the state from before the click.
        """
        wall = services.display.survey_walls()[0].wall
        ui.open("#theme")
        _painted(ui)

        ui.page.click(f"button:has-text('Hang on {wall.name}')")
        _confirm(ui, "Hang")
        ui.page.wait_for_selector("section.wall")

        assert services.display.hanging_on(wall.id).id == winter.id


class TestDeleting:
    def test_the_question_says_the_works_survive_and_the_grouping_does_not(self, ui, winter):
        """Which is the fact a curator needs and cannot infer from the word "Delete".

        One who believes they are about to lose three paintings will hesitate
        over something cheap; one who does not know the grouping is gone for good
        will do it without reading.
        """
        ui.open("#theme")
        _painted(ui)

        ui.page.click("button:has-text('Delete')")
        ui.page.wait_for_selector("dialog.confirm[open]")

        assert ui.page.inner_text("dialog.confirm .confirm-title") == "Delete Winter?"
        assert ui.page.inner_text("dialog.confirm .confirm-consequence") == (
            "The 3 works it holds stay in the collection. Only the grouping goes, and it cannot be brought back."
        )

    def test_declining_leaves_the_theme_where_it_was(self, ui, winter):
        ui.open("#theme")
        _painted(ui)

        ui.page.click("button:has-text('Delete')")
        ui.page.wait_for_selector("dialog.confirm[open]")
        ui.page.keyboard.press("Escape")
        ui.page.wait_for_selector("dialog.confirm", state="detached")

        assert ui.page.locator("h3", has_text="Winter").count() == 1

    def test_confirming_removes_the_panel_by_repainting_from_what_remains(self, ui, winter, services):
        """`DELETE /api/themes/{id}` answers with the themes that are left.

        Nothing else on this page can have changed — the refusal makes a hung
        theme undeletable, so no wall moved and no work was touched — which is
        what lets the list repaint from the answer instead of reloading the
        screen.
        """
        ui.open("#theme")
        _painted(ui)

        ui.page.click("button:has-text('Delete')")
        _confirm(ui, "Delete")
        ui.page.wait_for_selector("text=No themes yet.")

        assert ui.page.locator(".panel h3", has_text="Winter").count() == 0
        assert [theme.name for theme in services.display.list_themes()] == []

    def test_the_themes_that_are_left_are_the_ones_the_answer_named(self, ui, winter, services):
        """The other half of repainting from the response, and the half that can be wrong.

        With one theme, "repaint from the answer" and "repaint from nothing"
        produce the identical empty screen — so a client that threw the body away
        passes the test above. Two themes is the smallest state that tells them
        apart: the one that survives has to still be on the page, with its
        controls, without the screen having gone back to the server for a listing
        it was just handed.
        """
        services.display.add_theme(name="Late night")
        ui.open("#theme")
        _painted(ui)
        assert sorted(ui.page.locator(".panel h3").all_inner_texts()) == ["Late night", "New theme", "Winter"]

        # Winter's Delete, not Late night's — named, so choosing it needs nothing
        # about the panel it sits in.
        ui.page.click("button[aria-label='Delete Winter']")
        _confirm(ui, "Delete")
        ui.page.wait_for_selector("h3:has-text('Winter')", state="detached")

        assert sorted(ui.page.locator(".panel h3").all_inner_texts()) == ["Late night", "New theme"]
        assert ui.page.locator("text=No themes yet.").count() == 0

    def test_a_theme_hanging_in_two_rooms_refuses_and_says_what_to_do_about_it(self, ui, winter, services):
        """The acceptance criterion, met where a curator actually meets it.

        Two walls rather than one, because that is the case a single wall cannot
        tell apart: a message naming only the first room, or a guard counting
        themes rather than assignments, reads as correct against one wall and
        loses a room against two. The sentence is the server's own — nothing on
        this screen predicts the refusal from what it knows about hanging, which
        would be a second copy of the rule and would be wrong about a theme hung
        from another tab a moment ago.
        """
        the_wall = services.display.survey_walls()[0].wall
        study = services.display.add_wall(name="The study")
        services.display.activate_theme(winter.id, wall_id=the_wall.id)
        services.display.activate_theme(winter.id, wall_id=study.id)

        ui.open("#theme")
        _painted(ui)

        ui.page.click("button:has-text('Delete')")
        _confirm(ui, "Delete")
        ui.page.wait_for_selector("#error:not([hidden])")

        assert ui.page.inner_text("#error") == (
            "Theme 'Winter' is hanging on 'The study', 'The wall'. Hang another theme there first, or take "
            "this one down, so that what those walls show next is a choice rather than whatever was on them "
            "before."
        )
        # Refused, not partly done: the theme is still there and still hanging in
        # both rooms.
        assert ui.page.locator(".panel h3", has_text="Winter").count() == 1
        assert [wall.name for wall in services.display.walls_hanging(winter.id)] == ["The study", "The wall"]
