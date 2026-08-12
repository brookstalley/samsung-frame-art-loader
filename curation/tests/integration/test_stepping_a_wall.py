"""The two acts the Walls screen performs, over HTTP, against a real server.

`POST /api/directives` is the route this chunk added, and it closed the one gap
where a screen action had an MCP action and no HTTP route at all: an agent could
tell a wall to move on and a curator standing in front of the television could
not. Everything it asserts is about *which wall* — a directive stopped being a
singleton so that a `next` in the living room does not step the study, and a
route that answered correctly for one wall while quietly stepping both would look
identical from a single-wall deployment.

Activation is here for the same reason and not because it is new: the wall it
publishes to is the half no unit test of `activate_theme` can see, because the
evidence is a file on disk named for a wall.
"""

import json

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


def _wall_named(http, name):
    return next(wall for wall in http.get("/api/walls").json()["walls"] if wall["name"] == name)


class TestSteppingAWall:
    def test_a_step_advances_the_named_walls_sequence_and_answers_with_it(self, http, the_wall):
        """The counter the display plane watches, moved by one and reported back.

        The answer carries the wall as well as the number: a directive is a row
        per wall, and a bare counter is what it looked like while it was a
        singleton.
        """
        before = the_wall["directive_sequence"]

        response = http.post("/api/directives", json={"wall_id": the_wall["wall_id"]})

        assert response.status_code == 200
        assert response.json() == {
            "wall_id": the_wall["wall_id"],
            "sequence": before + 1,
            "pinned_work_id": None,
        }
        assert _wall_named(http, the_wall["name"])["directive_sequence"] == before + 1

    def test_a_step_leaves_every_other_walls_counter_alone(self, http, the_wall):
        """The whole reason the directive stopped being a singleton.

        A `next` aimed at the living room that stepped the study is one counter
        being asked a question it cannot answer — and on a one-wall deployment
        the two behaviours are indistinguishable, which is why this is asserted
        with two.
        """
        study = http.post("/api/walls", json={"name": "The study"}).json()

        http.post("/api/directives", json={"wall_id": the_wall["wall_id"]})

        assert _wall_named(http, "The study")["directive_sequence"] == study["directive_sequence"]
        assert _wall_named(http, the_wall["name"])["directive_sequence"] == the_wall["directive_sequence"] + 1

    def test_a_step_clears_a_standing_pin(self, http, services, ready_work, the_wall):
        """Moving on and standing on a pinned work are contradictory instructions.

        A sequence that advanced with the pin still set would read to the display
        plane as "jump to that work again" rather than as "move on", so the two
        cannot both be in force.
        """
        work = ready_work()
        services.display.show_work_now(the_wall["wall_id"], work.id)
        assert _wall_named(http, the_wall["name"])["pinned_work_id"] == work.id

        assert http.post("/api/directives", json={"wall_id": the_wall["wall_id"]}).json()["pinned_work_id"] is None
        assert _wall_named(http, the_wall["name"])["pinned_work_id"] is None

    def test_a_step_at_a_wall_that_does_not_exist_is_refused_in_words(self, http):
        """The service's own message reaches whoever asked, as every refusal does."""
        response = http.post("/api/directives", json={"wall_id": "no-such-wall"})

        assert response.status_code == 400
        assert "no-such-wall" in response.json()["error"]


class TestActivationPublishesToTheNamedWallOnly:
    def test_hanging_writes_the_named_walls_manifest_and_no_others(self, http, settings, ready_work, the_wall):
        """One manifest per wall, and hanging touches exactly one of them.

        The evidence is on disk rather than in the response, because the file is
        what a display plane actually reads — a route that answered with the
        right wall's build while writing the installation's single manifest would
        pass every assertion made over JSON.
        """
        work = ready_work(title="Automat")
        theme = http.post("/api/themes", json={"name": "Late night"}).json()
        http.post(f"/api/themes/{theme['theme_id']}/works", json={"artwork_id": work.id})
        study = http.post("/api/walls", json={"name": "The study"}).json()

        published = http.post(f"/api/themes/{theme['theme_id']}/activate", json={"wall_id": the_wall["wall_id"]}).json()

        assert published["wall_id"] == the_wall["wall_id"]
        assert settings.manifest_path(the_wall["wall_id"]).is_file()
        assert not settings.manifest_path(study["wall_id"]).exists()
        # And the wall that was not named goes on hanging nothing, which is the
        # half a curator would notice second and an agent first.
        assert _wall_named(http, "The study")["theme"] is None

    def test_a_second_wall_hangs_the_same_theme_without_disturbing_the_first(self, http, settings, ready_work, the_wall):
        """Two walls may hang one theme, and that must not require duplicating it.

        The first wall's published file is compared before and after, because the
        failure worth catching is a second activation rewriting it — which is
        what one manifest for the installation did, silently.
        """
        work = ready_work(title="Automat")
        theme = http.post("/api/themes", json={"name": "Late night"}).json()
        http.post(f"/api/themes/{theme['theme_id']}/works", json={"artwork_id": work.id})
        study = http.post("/api/walls", json={"name": "The study"}).json()
        http.post(f"/api/themes/{theme['theme_id']}/activate", json={"wall_id": the_wall["wall_id"]})
        first = json.loads(settings.manifest_path(the_wall["wall_id"]).read_text(encoding="utf-8"))

        http.post(f"/api/themes/{theme['theme_id']}/activate", json={"wall_id": study["wall_id"]})

        assert json.loads(settings.manifest_path(the_wall["wall_id"]).read_text(encoding="utf-8")) == first
        assert settings.manifest_path(study["wall_id"]).is_file()
        themes = http.get("/api/themes").json()["themes"]
        hanging = next(entry for entry in themes if entry["theme"]["theme_id"] == theme["theme_id"])
        assert sorted(where["name"] for where in hanging["hanging_on"]) == ["The study", the_wall["name"]]
