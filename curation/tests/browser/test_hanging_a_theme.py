"""Hanging a theme, in a real browser, against a real server.

The theme panel is where the single-wall assumption was most visible in the
client: one "Put on the wall" button, and a badge that said "on the wall" with no
room to say which. Neither is expressible as JSON, so neither Python suite runs a
line of it — this does.

**These tests are here rather than in a screen chunk because the client changed
in this one.** Chunks 04, 05 and 09 rebuild these screens; until they do, this is
the only executed coverage the per-wall controls have.
"""

import pytest

# At import time, not in a fixture. A marker deselection still *collects* this
# module, so the default run — which does not install the browser group — has to
# skip here rather than fail on the missing plugin.
pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)


@pytest.fixture
def a_theme(services):
    """One theme, hanging nowhere. What a curator has just after creating one."""
    return services.display.add_theme(name="Late night")


def test_the_control_names_the_wall_it_would_hang_on(ui, a_theme):
    """ "Hang on the living room", never "Put on the wall".

    A label that reads correctly today only because there is one possible target
    is a sentence that silently becomes wrong, and the label is the last place a
    curator can catch a mistake before the room changes.
    """
    ui.open("#theme")
    ui.page.wait_for_selector(".panel")

    walls = ui.page.locator("button", has_text="Hang on ")
    assert walls.count() == 1
    assert walls.first.inner_text() == "Hang on The wall"


def test_a_second_wall_becomes_a_second_choice_rather_than_a_different_screen(ui, a_theme, services):
    """One wall is the degenerate case of many, and the layout does not switch.

    The single-wall rendering is the many-wall rendering with one entry in it, so
    a second display adds a button rather than replacing a control.
    """
    services.display.add_wall(name="Study")

    ui.open("#theme")
    ui.page.wait_for_selector(".panel")

    offered = ui.page.locator("button", has_text="Hang on ")
    assert sorted(offered.all_inner_texts()) == ["Hang on Study", "Hang on The wall"]


def test_hanging_reports_back_by_naming_the_wall_rather_than_a_colour(ui, a_theme, services):
    """The badge carries a glyph and the wall's own name beside any colour.

    Two claims in one, and both matter: colour is never the sole carrier of
    state, and "on the wall" is not a thing that can be said once there is more
    than one.
    """
    services.display.add_wall(name="Study")
    ui.open("#theme")
    ui.page.wait_for_selector(".panel")

    ui.page.click("text=Hang on Study")
    # Through the confirmation, which this screen gained when the chunk that owns
    # it adopted `core/confirm.js`: activation is the one act that changes what
    # other people in the house see, and flow 6 requires it be asked about. What
    # the question says is asserted in `test_the_theme_screen.py`; here it is the
    # gate between the click and the write.
    ui.page.wait_for_selector("dialog.confirm[open]")
    ui.page.click("dialog.confirm .confirm-actions button:has-text('Hang')")
    # Waited on the wall view the hang lands on, not on a heading. The theme
    # screen already has an `h2`, so waiting for one waits for nothing — and the
    # reload below is then free to overtake the POST, after which the theme is
    # not hanging anywhere and the badge this test is about never appears. The
    # walls screen is painted only once the activate has come back, which is
    # exactly the fact the reload needs to be true.
    ui.page.wait_for_selector("section.wall")

    ui.open("#theme")
    ui.page.wait_for_selector(".badge")
    badge = ui.page.locator(".badge").first
    assert "on Study" in badge.inner_text()
    assert badge.locator(".glyph").count() == 1
    # And the wall it is not on is still offered, so hanging it in both rooms is
    # a second click rather than a different screen.
    assert ui.page.locator("button", has_text="Hang on ").all_inner_texts() == ["Hang on The wall"]


def test_a_hung_theme_can_be_taken_down_from_the_wall_it_is_on(ui, a_theme, services):
    """The route out of the delete refusal, exercised where a curator meets it.

    A theme hanging anywhere is undeletable, and this button is what makes that
    absolute rule survivable rather than a dead end.
    """
    wall = services.display.survey_walls()[0].wall
    services.display.activate_theme(a_theme.id, wall_id=wall.id)

    ui.open("#theme")
    ui.page.wait_for_selector(".badge")

    ui.page.click(f"text=Take down from {wall.name}")
    ui.page.wait_for_selector("button:has-text('Hang on ')")

    assert ui.page.locator(".badge").count() == 0
    assert services.display.hanging_on(wall.id) is None


def test_a_wall_with_nothing_hanging_says_so_instead_of_showing_an_empty_manifest(ui, a_theme):
    """The wall view names the wall and the fix, rather than rendering nothing.

    An empty table under a heading reads as "the theme is empty"; this state is
    "no theme has been chosen", and the two lead to different actions.
    """
    ui.open("#walls")
    ui.page.wait_for_selector("h2")

    assert "Nothing is hanging on The wall" in ui.text()
    # And the fact the MCP surface states after an unhang, which the human
    # surface withheld: taking a theme down rewrites no manifest, so the set goes
    # on showing the picture. Without this line the empty wall reads as a failed
    # take-down, and the curator's next move is to do it again.
    assert "goes on showing what it was showing until a theme is hung" in ui.text()


def test_the_take_down_note_is_said_once_however_many_walls_are_empty(ui, services):
    """One fact about how taking down works, not a property of any wall.

    It reads as a caption under the list of empty rooms; repeated per room it
    reads as three separate warnings about three separate problems. Two empty
    walls is the smallest state that can tell the two renderings apart, and
    without this test the note could be moved back inside the loop with the
    suite still green — which is exactly where it started.
    """
    services.display.add_wall(name="Study")

    ui.open("#walls")
    ui.page.wait_for_selector("h2")

    assert ui.page.locator("p", has_text="goes on showing what it was showing").count() == 1
    # Both rooms are named, so the one note is standing for two walls rather
    # than one of them having gone missing.
    assert "Nothing is hanging on The wall" in ui.text()
    assert "Nothing is hanging on Study" in ui.text()


def test_each_walls_panels_nest_under_that_wall_rather_than_beside_it(ui, a_theme, services):
    """Two hung walls, and a reader navigating by heading can still tell the rooms apart.

    The wall view renders one section per wall, each with its own Showing / Not
    showing / How it rotates panels. When every one of those was an `h3` the
    single-wall case read correctly by accident — with two walls hung it is six
    sibling headings in a row and no structural signal for which counts belong to
    which room. Asserted rather than left to the eye because nothing else
    executes this markup: `accessibility-spec.md` states no heading rule, so this
    test is the rule.
    """
    # Read before the study exists, because walls come back ordered by name and
    # "Study" would displace the migration's wall from position zero — after
    # which this index would hang the theme in the same room twice and the test
    # would assert nothing about nesting.
    the_wall = services.display.survey_walls()[0].wall
    study = services.display.add_wall(name="Study")
    services.display.activate_theme(a_theme.id, wall_id=the_wall.id)
    services.display.activate_theme(a_theme.id, wall_id=study.id)

    ui.open("#walls")
    ui.page.wait_for_selector("h3")

    # One h3 per wall, and every panel heading a rank below it.
    assert sorted(ui.page.locator("h3").all_inner_texts()) == ["Study: Late night", "The wall: Late night"]
    assert ui.page.locator("h3.wall-title").count() == 2
    assert ui.page.locator(".panel h3").count() == 0
    assert ui.page.locator(".panel h4").count() == 6
    # And with nothing empty there is no take-down note: a caption with nothing
    # to caption. This is the other half of the guard the sibling test above
    # exercises, and without it the guard could be deleted with the suite green.
    assert ui.page.locator("p", has_text="goes on showing what it was showing").count() == 0
