"""Renaming and deleting a theme over real HTTP, and the refusal that guards the delete.

Two routes that had no HTTP surface at all until this chunk: an agent could
rename a theme through `art_theme(action='update')` and delete one through
`art_theme(action='delete')`, and a curator with a browser could do neither.
`product-brief.md` item 8 makes parity the requirement, so the gap was the wrong
way round from the one parity usually guards against.

**What is asserted here is the binding, not the rule.** `DisplayService` already
holds the refusal and has its own tests; what none of them can see is whether the
route calls that method or writes a guard of its own — a second copy would pass
every service test while disagreeing with the tool surface the first time either
changed. So the refusal is asserted through the route, verbatim, and the sentence
below is the one `api-contract.md` § Deleting a theme records as normative.

**Two walls, not one.** The acceptance criterion for this work is a theme hung in
two rooms, because that is the case a single-wall assertion cannot tell apart: a
message that named only the first wall, or a guard that counted themes rather
than assignments, reads as correct against one wall and loses a room against two.

Against a real uvicorn server rather than an in-process transport, per the
suite's standing rule: Starlette does not run a mounted sub-app's lifespan, and
an in-process test would pass against an application that fails every MCP
request in production.
"""

import httpx
import pytest


@pytest.fixture
def http(server_url):
    """A client pointed at the booted server, with the timeout a Pi deserves."""
    with httpx.Client(base_url=server_url, timeout=30.0) as client:
        yield client


@pytest.fixture
def the_wall(http):
    """The wall a fresh deployment has, read off the surface rather than the store."""
    walls = http.get("/api/walls").json()["walls"]
    assert len(walls) == 1, f"a fresh deployment should serve exactly one wall, got {walls}"
    return walls[0]


def _theme(http, name):
    return http.post("/api/themes", json={"name": name}).json()


def _names(http):
    return [placement["theme"]["name"] for placement in http.get("/api/themes").json()["themes"]]


class TestRenamingATheme:
    def test_the_new_name_is_stored_and_answered_with(self, http):
        """`POST`, not `PATCH` — one surface with one spelling for "change this".

        The answer carries the theme so the screen repaints the name the
        catalogue now holds rather than the string it sent.
        """
        theme = _theme(http, "Late night")

        answer = http.post(f"/api/themes/{theme['theme_id']}", json={"name": "Winter"})

        assert answer.status_code == 200
        assert answer.json()["name"] == "Winter"
        assert _names(http) == ["Winter"]

    def test_the_answer_is_the_normalised_name_rather_than_the_one_sent(self, http):
        """Which is the whole reason the route answers with a body at all.

        The service trims, so a name typed with a trailing space is stored
        without one — and a screen painting its own input would show a name the
        catalogue does not hold, differing from the listing beside it.
        """
        theme = _theme(http, "Late night")

        answer = http.post(f"/api/themes/{theme['theme_id']}", json={"name": "  Winter  "})

        assert answer.json()["name"] == "Winter"
        assert _names(http) == ["Winter"]

    def test_a_name_with_nothing_in_it_is_refused_by_the_service(self, http):
        """The handler unpacks and calls; the rule stays one layer down.

        A field of spaces reads as present and displays as absent, which is why
        the service refuses it — and the refusal has to reach the browser rather
        than being caught by a check written here.
        """
        theme = _theme(http, "Late night")

        answer = http.post(f"/api/themes/{theme['theme_id']}", json={"name": "   "})

        assert answer.status_code == 400
        assert answer.json() == {"error": "name cannot be empty."}
        assert _names(http) == ["Late night"]

    def test_renaming_leaves_the_pace_the_theme_was_given(self, http, services):
        """The reason the request body cannot say anything but a name.

        `update_theme` distinguishes "leave this alone" from "clear it" with a
        sentinel, because `None` means "inherit the deployment default" for both
        rotation settings. A body whose optional fields defaulted to `None` would
        silently reset a theme's pace every time a curator fixed a typo.
        """
        theme = _theme(http, "Late night")
        services.display.update_theme(theme["theme_id"], rotation_interval_seconds=900, shuffle=True)

        http.post(f"/api/themes/{theme['theme_id']}", json={"name": "Winter"})

        after = services.display.get_theme(theme["theme_id"])
        assert (after.name, after.rotation_interval_seconds, after.shuffle) == ("Winter", 900, True)


class TestDeletingATheme:
    def test_an_unhung_theme_goes_and_the_answer_is_what_remains(self, http):
        """Read-back-after-mutate, and the read-back is the list it was deleted from."""
        kept = _theme(http, "Late night")
        going = _theme(http, "Winter")

        answer = http.delete(f"/api/themes/{going['theme_id']}")

        assert answer.status_code == 200
        assert [placement["theme"]["theme_id"] for placement in answer.json()["themes"]] == [kept["theme_id"]]
        assert _names(http) == ["Late night"]

    def test_the_last_theme_goes_too_as_long_as_it_hangs_nowhere(self, http):
        """The catalogue can be emptied, which is the ruling the refusal was softened for.

        Until `unhang` existed the refusal carried an exception for the last
        theme, because refusing absolutely would have made it undeletable
        forever. The exception is retired and the operation replaced it: a theme
        that hangs nowhere deletes however few of them there are.
        """
        only = _theme(http, "Late night")

        answer = http.delete(f"/api/themes/{only['theme_id']}")

        assert answer.status_code == 200
        assert answer.json()["themes"] == []

    def test_the_works_a_deleted_theme_held_are_still_in_the_catalogue(self, http, service):
        """A theme is a grouping. Deleting one destroys the grouping and nothing else.

        This is what the confirmation on the screen promises, and a delete that
        cascaded into the works would make that sentence a lie in the one
        direction a curator cannot undo.
        """
        work = service.add_artwork(title="Chop Suey")
        theme = _theme(http, "Late night")
        http.post(f"/api/themes/{theme['theme_id']}/works", json={"artwork_id": work.id})

        http.delete(f"/api/themes/{theme['theme_id']}")

        assert work.id in {entry["artwork_id"] for entry in http.get("/api/works").json()["works"]}

    def test_a_theme_hanging_in_two_rooms_is_refused_in_the_words_the_contract_wrote(self, http, the_wall):
        """The acceptance criterion, and the sentence asserted whole rather than by substring.

        Every clause is load-bearing and each fails differently. Naming the walls
        is what makes the message actionable once "the wall" identifies nothing;
        *both* remedies are offered because hanging something else is a remedy in
        its own right rather than a longer road to taking this down; and the
        closing clause says why the refusal exists at all — a wall that goes dark
        should do so because a curator took the picture down, not as a side
        effect of tidying the catalogue.

        Asserted as one string because a substring check over a paraphrase passes
        while the half a curator needs is missing.
        """
        study = http.post("/api/walls", json={"name": "The study"}).json()
        theme = _theme(http, "Winter")
        for wall in (the_wall, study):
            http.post(f"/api/themes/{theme['theme_id']}/activate", json={"wall_id": wall["wall_id"]})

        answer = http.delete(f"/api/themes/{theme['theme_id']}")

        assert answer.status_code == 400
        assert answer.json() == {
            "error": (
                "Theme 'Winter' is hanging on 'The study', 'The wall'. Hang another theme there first, or take "
                "this one down, so that what those walls show next is a choice rather than whatever was on them "
                "before."
            )
        }
        assert _names(http) == ["Winter"]

    def test_taking_it_down_from_one_of_two_walls_is_not_enough(self, http, the_wall):
        """The count that matters is assignments, not themes — and not "any wall is free".

        A guard that stopped refusing once *some* wall had been cleared would
        pass every single-wall test and blank the room still holding it. The
        message narrows to the wall that is left, which is the other half: a
        refusal naming a room the theme has already left is one a curator has no
        move against.
        """
        study = http.post("/api/walls", json={"name": "The study"}).json()
        theme = _theme(http, "Winter")
        for wall in (the_wall, study):
            http.post(f"/api/themes/{theme['theme_id']}/activate", json={"wall_id": wall["wall_id"]})

        http.delete(f"/api/walls/{study['wall_id']}/theme")
        answer = http.delete(f"/api/themes/{theme['theme_id']}")

        assert answer.status_code == 400
        assert "hanging on 'The wall'." in answer.json()["error"]
        assert "The study" not in answer.json()["error"]

    def test_the_route_the_refusal_names_is_the_one_that_resolves_it(self, http, the_wall):
        """The remedy has to be an operation that exists and that the curator can reach.

        Two walls cleared by the two ways out the message offers — one theme hung
        in its place, one taken down — and only then does the delete go through.
        Without this the refusal could name remedies that do not resolve it, which
        is what the previous message did the day a theme could hang in two rooms.
        """
        study = http.post("/api/walls", json={"name": "The study"}).json()
        theme = _theme(http, "Winter")
        other = _theme(http, "Late night")
        for wall in (the_wall, study):
            http.post(f"/api/themes/{theme['theme_id']}/activate", json={"wall_id": wall["wall_id"]})

        # "Hang another theme there first" on one wall, "take this one down" on the other.
        http.post(f"/api/themes/{other['theme_id']}/activate", json={"wall_id": the_wall["wall_id"]})
        http.delete(f"/api/walls/{study['wall_id']}/theme")

        answer = http.delete(f"/api/themes/{theme['theme_id']}")

        assert answer.status_code == 200
        assert _names(http) == ["Late night"]

    def test_a_refused_delete_leaves_the_rooms_showing_what_they_were_showing(self, http, the_wall):
        """The refusal is a refusal, not a partial delete.

        A guard that raised after removing the membership rows would leave the
        theme on the wall with nothing in it, which is the failure a wall keeps
        no record of: the manifest is not rewritten, so the room looks fine until
        the next build.
        """
        work = http.get("/api/works").json()["works"][0]
        theme = _theme(http, "Winter")
        http.post(f"/api/themes/{theme['theme_id']}/works", json={"artwork_id": work["artwork_id"]})
        http.post(f"/api/themes/{theme['theme_id']}/activate", json={"wall_id": the_wall["wall_id"]})

        assert http.delete(f"/api/themes/{theme['theme_id']}").status_code == 400

        detail = http.get(f"/api/themes/{theme['theme_id']}").json()
        assert [entry["artwork_id"] for entry in detail["works"]] == [work["artwork_id"]]
        hanging = http.get("/api/walls").json()["walls"][0]["theme"]
        assert hanging["theme_id"] == theme["theme_id"]
