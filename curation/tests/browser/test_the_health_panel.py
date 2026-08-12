"""The health panel with more than one wall, in a real browser.

**The panel is where "which wall is silent" is actually answered**, and neither
Python suite runs a line of the client that answers it. The JSON tests assert
that `GET /api/health` carries one reading per wall; whether the page puts the
room's *name* in front of a reader, or renders two indistinguishable blocks of
label/value pairs, is not expressible as JSON.

That distinction is the whole reason the heartbeat became one file per wall. One
shared file would have had the second display overwrite the first's report every
minute, so a wall that had gone dark read exactly like a wall that was fine — and
a panel that shows two readings without naming them reintroduces that at the last
step, on the surface built to prevent it.
"""

import json
from datetime import UTC, datetime, timedelta

import pytest

# At import time, not in a fixture. A marker deselection still *collects* this
# module, so the default run — which does not install the browser group — has to
# skip here rather than fail on the missing plugin.
pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)


@pytest.fixture
def two_walls(services):
    """The wall a fresh catalogue holds, and a study the curator recorded."""
    living_room = services.display.survey_walls()[0].wall
    return living_room, services.display.add_wall(name="Study")


def _reported(settings, wall, *, ago_seconds: float = 0.0) -> None:
    """Put a heartbeat where the display serving that wall would have put one."""
    settings.heartbeat_path(wall.id).write_text(
        json.dumps({"reported_at": (datetime.now(UTC) - timedelta(seconds=ago_seconds)).isoformat()}),
        encoding="utf-8",
    )


def test_the_panel_names_every_wall_it_is_reporting_on(ui, settings, two_walls):
    """Two rooms, two named readings — not two anonymous blocks of facts.

    The name is what makes a reading actionable: "the study has not reported"
    sends somebody into a room, and an age with no room attached does not.
    """
    living_room, study = two_walls
    _reported(settings, living_room)

    ui.open("#health")
    ui.page.wait_for_selector("h2:has-text('Health')")

    # `.wall-reading h3` since the client was split into modules: each wall's
    # reading became a panel of its own with its name as the heading, where it had
    # been an `h4` inside a shared "The walls" panel.
    #
    # **Set equality, not a subset.** This assertion was briefly relaxed to `<=`
    # while moving it to `.panel h3` — which selects the backup and geometry
    # panels too, so exactness was impossible there and the `==` half went with
    # it. That half is the one that catches a wall panel which should not exist:
    # a subset check passes against a screen naming a room that is not in the
    # catalogue. The selector, not the assertion, was what needed to change.
    headings = ui.page.locator(".wall-reading h3")
    assert set(headings.all_inner_texts()) == {living_room.name, study.name}


def test_the_summary_names_the_wall_that_has_gone_quiet(ui, settings, two_walls):
    """The sentence a reader takes away, with the room in it.

    Before the split this could only ever have said that *a* display plane had
    not reported, which on a two-room installation is a fact nobody can act on.
    """
    living_room, study = two_walls
    _reported(settings, living_room)

    ui.open("#health")
    ui.page.wait_for_selector(f".panel h3:has-text('{study.name}')")

    assert f"{study.name!r} has not reported" in ui.text()


def test_a_wall_that_has_never_reported_says_so_without_a_verdict(ui, settings, two_walls):
    """Absent is a true reading, and never a fault or a colour.

    A wall no display has been pointed at yet is the state of every second room
    between recording it and configuring the device, and it must read as that
    rather than as something broken.
    """
    living_room, study = two_walls
    _reported(settings, living_room, ago_seconds=4 * 24 * 60 * 60)

    ui.open("#health")
    # Wait on the wall that never reported: it is the one this test is about, and
    # waiting on the other would let the assertions run before its panel painted.
    ui.page.wait_for_selector(f".panel h3:has-text('{study.name}')")

    page = ui.text()
    assert "Nothing has ever written a heartbeat for this wall." in page
    # The age in the unit a person reads it in, on the wall that *did* report.
    assert "4 days ago" in page
    # Never a green dot. The panel states what was found and how long ago; whether
    # four days is alarming depends on whether that television was switched off on
    # purpose, which this plane does not know.
    assert not {"healthy", "degraded", "OK"} & set(page.split())
