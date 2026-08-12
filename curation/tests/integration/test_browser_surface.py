"""The browser surface, driven the way a browser drives it.

Against a real uvicorn server rather than an in-process transport, per the
suite's standing rule: Starlette does not run a mounted sub-app's lifespan, and
an in-process test would pass against an application that fails every MCP
request in production.

**The acceptance criterion this file exists to hold** is that a curator, touching
no filesystem, no JSON file and no SSH, can see the works with their images,
build a theme, put it on the wall, and read exactly why any work is absent from
the manifest that results. `test_the_whole_curatorial_loop_runs_over_http` is
that criterion end to end; the rest pin the pieces it would be easy to break
without failing it.
"""

import json
import pathlib
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from curation.http.pages import STATIC_DIR
from curation.persistence.backup import BACKUP_RECEIPT_FILENAME
from curation.persistence.records import (
    AcquisitionMethod,
    FetchStatus,
    MatMethod,
    RenditionKind,
    RightsStatus,
    SourceClass,
)


@pytest.fixture
def http(server_url):
    """A client pointed at the booted server, with the timeout a Pi deserves."""
    with httpx.Client(base_url=server_url, timeout=30.0) as client:
        yield client


@pytest.fixture
def wall(http):
    """The wall this deployment has, read off the surface rather than the store.

    Every act that changes a wall names one, so a browser test that reached
    around the API for the id would be exercising a flow no browser can take —
    the client has to be able to get here from `GET /api/walls` alone.
    """
    walls = http.get("/api/walls").json()["walls"]
    assert len(walls) == 1, f"a fresh deployment should serve exactly one wall, got {walls}"
    return walls[0]


def card_for(listing: dict, artwork_id: str) -> dict:
    """Pick a work out of a listing by identity, never by title.

    The catalogue orders by title and tie-breaks on a UUID, and the seeded
    fixture holds a `Nighthawks` of its own — so a test that looked its work up
    by name would pass or fail on which uuid happened to sort first.
    """
    return next(work for work in listing["works"] if work["artwork_id"] == artwork_id)


@pytest.fixture
def hold(service, settings, decodable_jpeg):
    """Give a work a master on disk, and optionally the rest of what the wall needs.

    Writes real files, because every question this surface answers about a work —
    can it be shown, how large would it appear, is its render current — is a
    question about the tree as well as the catalogue.
    """

    def _hold(title, *, width=6000, height=4000, rendered=False, mat=False, content_hash=None):
        artwork = service.add_artwork(title=title, date_created="1942", medium="Oil on canvas")
        source = service.add_source(
            artwork_id=artwork.id,
            url=f"https://museum.example/{artwork.id}",
            provider="artic",
            source_class=SourceClass.INSTITUTIONAL,
            acquisition_method=AcquisitionMethod.DEZOOMIFY,
            rights_status=RightsStatus.PUBLIC_DOMAIN,
            is_primary=True,
        )
        relative = f"raw/{artwork.id}.jpg"
        decodable_jpeg(settings.art_root / relative, width=width, height=height)
        service.record_original(
            artwork_id=artwork.id,
            source_id=source.id,
            path=relative,
            width=width,
            height=height,
            byte_size=(settings.art_root / relative).stat().st_size,
            content_hash=content_hash or f"hash-{artwork.id}",
            fetch_status=FetchStatus.OK,
        )
        if mat:
            service.record_mat_color(artwork_id=artwork.id, hex_rgb="#27285b", method=MatMethod.VISION_MODEL)
        if rendered:
            rendered_path = f"ready/{artwork.id}.jpg"
            decodable_jpeg(settings.art_root / rendered_path, width=3840, height=2160)
            service.record_rendition(
                artwork_id=artwork.id,
                kind=RenditionKind.TV_DISPLAY,
                target_width=3840,
                target_height=2160,
                path=rendered_path,
            )
        return artwork

    return _hold


class TestTheClientIsServed:
    def test_the_root_returns_the_shell(self, http):
        response = http.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "<title>Curation</title>" in response.text

    def test_a_deep_link_survives_a_reload(self, http):
        """In-page navigation writes a fragment, but a bookmark is a real path."""
        for path in ("/walls", "/collection", "/discover", "/theme", "/health"):
            assert http.get(path).status_code == 200, path

    def test_the_addresses_the_surface_used_to_answer_to_still_answer(self, http):
        """The three destinations renamed four paths, and the old ones were bookmarkable.

        They have been real, reloadable URLs since the client was built, and the
        client maps each onto the screen that took over its job. A 404 here is a
        curator told their bookmark is gone when in fact the screen moved.
        """
        for path in ("/works", "/discovery", "/themes", "/manifest"):
            assert http.get(path).status_code == 200, path

    def test_the_stylesheet_and_every_client_module_are_served(self, http):
        """The client is a tree of ES modules, and the browser fetches each by URL.

        `app.js` alone passing means nothing now: it is an import list, and a
        `core/` or `screens/` module the static mount does not serve is a page
        that loads and renders nothing — the silent failure this suite exists to
        catch, one directory lower than it used to live.
        """
        css = http.get("/static/app.css")
        assert css.status_code == 200
        assert "--surface-0" in css.text

        static = pathlib.Path(STATIC_DIR)
        modules = sorted(path.relative_to(static).as_posix() for path in static.rglob("*.js"))
        assert len(modules) > 1, "the client was read as one file; this check would prove nothing"
        for module in modules:
            assert http.get(f"/static/{module}").status_code == 200, module

    def test_an_unknown_api_path_is_not_answered_with_the_shell(self, http):
        """A catch-all that returned HTML here would reach a client as unparseable JSON."""
        response = http.get("/api/nothing-here")
        assert response.status_code == 404
        assert "<title>" not in response.text


class TestTheWorkGrid:
    def test_every_held_work_is_listed_with_the_size_it_would_appear_at(self, http, hold):
        artwork = hold("Chop Suey")
        card = card_for(http.get("/api/works").json(), artwork.id)
        assert card["fit"]["verdict"] in {"native", "matted_small", "below_floor"}
        # A thumbnail cannot convey resolution — the rendered size is what a
        # curator actually judges, so it may never be absent from a card.
        assert card["fit"]["rendered_long_edge_inches"] > 0

    def test_a_small_work_is_shown_and_labelled_rather_than_hidden(self, http, hold):
        """Below the floor is a warning, never a filter. The curator may still take it."""
        artwork = hold("A postage stamp", width=300, height=200)
        card = card_for(http.get("/api/works").json(), artwork.id)
        assert card["fit"]["verdict"] == "below_floor"
        assert card["image"]["available"] is True

    def test_a_work_with_no_master_carries_a_reason_rather_than_an_empty_field(self, http, seeded_service):
        """A card with no size must not read like a card whose work is small."""
        held = seeded_service.list_artworks().entries[0].artwork
        card = card_for(http.get("/api/works").json(), held.id)
        assert card["fit"] is None
        assert "No master image" in card["fit_note"]
        assert card["image"]["available"] is False
        assert "No master image" in card["image"]["note"]

    def test_a_card_says_whether_it_is_showing_the_wall_render_or_the_master(self, http, hold):
        rendered = hold("Rendered", rendered=True)
        master_only = hold("Master only")
        listing = http.get("/api/works").json()
        assert card_for(listing, rendered.id)["image"]["source_kind"] == "tv_display"
        assert card_for(listing, master_only.id)["image"]["source_kind"] == "original"

    def test_a_page_describes_its_own_place_in_the_set(self, http, hold):
        for index in range(4):
            hold(f"Work {index}")
        page = http.get("/api/works", params={"limit": 2, "offset": 1}).json()
        assert len(page["works"]) == 2
        assert page["offset"] == 1
        assert page["limit"] == 2
        assert page["truncated"] is True
        assert page["total"] >= 7


class TestThumbnails:
    def test_a_thumbnail_is_served_as_a_jpeg(self, http, hold):
        artwork = hold("Automat")
        response = http.get(f"/api/works/{artwork.id}/thumbnail")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/jpeg"
        assert response.content.startswith(b"\xff\xd8")

    def test_a_thumbnail_is_far_smaller_than_the_master_it_came_from(self, http, hold, settings):
        """The whole reason this route exists: a grid of the real files is not a page."""
        artwork = hold("Automat", width=4000, height=3000)
        master = (settings.art_root / f"raw/{artwork.id}.jpg").stat().st_size
        assert len(http.get(f"/api/works/{artwork.id}/thumbnail").content) < master / 4

    def test_a_thumbnail_revalidates_rather_than_being_held_for_a_fixed_window(self, http, hold):
        """A cached copy of a replaced master is a superseded acquisition on screen."""
        artwork = hold("Automat")
        response = http.get(f"/api/works/{artwork.id}/thumbnail")
        assert "no-cache" in response.headers["cache-control"]

    def test_a_work_with_no_image_refuses_with_the_reason_shown_on_its_card(self, http, seeded_service):
        empty = next(work for work in seeded_service.list_artworks().entries)
        response = http.get(f"/api/works/{empty.artwork.id}/thumbnail")
        assert response.status_code == 400
        assert "No master image" in response.json()["error"]


class TestWorkDetail:
    def test_the_detail_view_carries_what_the_grid_does_not(self, http, hold):
        artwork = hold("Automat", rendered=True, mat=True)
        detail = http.get(f"/api/works/{artwork.id}").json()
        assert detail["work"]["title"] == "Automat"
        assert detail["original"]["width"] == 6000
        assert [source["provider"] for source in detail["sources"]] == ["artic"]
        assert {rendition["kind"] for rendition in detail["renditions"]} == {"tv_display"}
        assert detail["mat_colors"][0]["hex_rgb"] == "#27285b"

    def test_a_rendition_says_whether_it_still_matches_the_master(self, http, hold, service, settings, decodable_jpeg):
        artwork = hold("Automat", rendered=True)
        source = service.list_sources(artwork.id)[0]
        replacement = f"raw/{artwork.id}-2.jpg"
        decodable_jpeg(settings.art_root / replacement)
        service.record_original(
            artwork_id=artwork.id,
            source_id=source.id,
            path=replacement,
            width=1600,
            height=1200,
            byte_size=10,
            content_hash="a-new-acquisition",
            fetch_status=FetchStatus.OK,
        )
        detail = http.get(f"/api/works/{artwork.id}").json()
        assert [rendition["stale"] for rendition in detail["renditions"]] == [True]

    def test_an_unknown_work_is_refused_with_a_message_written_to_be_shown(self, http):
        response = http.get("/api/works/not-a-work")
        assert response.status_code == 400
        assert "not-a-work" in response.json()["error"]


def _every_key(payload) -> set[str]:
    """Every field name anywhere in a response, however deeply nested.

    Scanning the raw text instead is what the first version of the budget check
    did, and it matched the temporary directory pytest names after the test
    itself — so a check about the payload was reading the filesystem.
    """
    if isinstance(payload, dict):
        return set(payload) | {key for value in payload.values() for key in _every_key(value)}
    if isinstance(payload, list):
        return {key for item in payload for key in _every_key(item)}
    return set()


class TestHealth:
    #: Every observation the panel makes carries these five and nothing that
    #: resembles a judgement — no status, no ok/degraded, no colour. Asserted as a
    #: whole set rather than by naming the fields that must be absent, because the
    #: failure to catch is a *new* field nobody thought to forbid.
    OBSERVATION_FIELDS = {"path", "age_seconds", "absent", "problem", "description", "reported"}

    def test_the_panel_states_an_observation_and_never_a_verdict(self, http):
        health = http.get("/api/health").json()
        assert health["heartbeat"]["absent"] is True
        assert "has not reported yet" in health["heartbeat"]["description"]
        assert set(health["heartbeat"]) == self.OBSERVATION_FIELDS | {"reported_at"}

    def test_the_panel_reports_what_the_display_plane_said_about_itself(self, http, settings):
        """The failure table maps TV, panel and last-error state onto this document.

        Until it reached the payload those rows named a signal nothing displayed —
        a monitoring plan whose evidence lived only in a file no surface opened.
        Handed through untouched rather than unpacked into named fields, because
        `reported_at` is the only key the strategy makes contract and inventing
        more here would be a second contract the writer never agreed to.
        """
        settings.heartbeat_path.write_text(
            json.dumps(
                {
                    # The keys the display plane's writer actually emits. They were
                    # invented here — `tv_connected` — while no writer existed, and
                    # a fixture naming a field nothing produces is how a surface
                    # gets built against a document that never arrives. The two
                    # planes cannot import each other, so what holds them together
                    # is `tests/preferences/test_heartbeat_contract.py`.
                    "reported_at": datetime.now(UTC).isoformat(),
                    "television_reachable": False,
                    "last_error": "the television refused the pairing token",
                    # And one key no writer emits, because pass-through of the
                    # unrecognised is the actual property under test: the reader
                    # hands the whole object over rather than unpacking fields it
                    # knows, so a writer may add one without a curation release.
                    "some_future_field": 17,
                }
            ),
            encoding="utf-8",
        )
        heartbeat = http.get("/api/health").json()["heartbeat"]
        assert heartbeat["absent"] is False
        assert heartbeat["reported"]["television_reachable"] is False
        assert heartbeat["reported"]["last_error"] == "the television refused the pairing token"
        assert heartbeat["reported"]["some_future_field"] == 17

    def test_an_age_is_stated_in_the_unit_a_person_reads_it_in(self, http, settings):
        """ "345600 seconds ago" is a conversion the reader has to do themselves.

        On the one surface built so they would not have to, and for the failure it
        exists to catch — a plane that has been down since Tuesday.
        """
        settings.heartbeat_path.write_text(
            json.dumps({"reported_at": (datetime.now(UTC) - timedelta(days=4)).isoformat()}),
            encoding="utf-8",
        )
        assert "4 days ago" in http.get("/api/health").json()["heartbeat"]["description"]

    def test_the_panel_says_plainly_that_no_backup_has_ever_been_recorded(self, http):
        """A true observation before the backup job exists, which is why it ships first.

        The alternative — building this alongside the job — is what left the two
        entries waiting on each other, and an absent reading is exactly what this
        panel's contract is for: it states what was found, and nothing is a
        finding.
        """
        backup = http.get("/api/health").json()["backup"]
        assert backup["absent"] is True
        assert backup["age_seconds"] is None
        assert "nothing has written one yet" in backup["description"]
        assert set(backup) == self.OBSERVATION_FIELDS | {"completed_at"}

    def test_a_recorded_backup_is_reported_with_its_age(self, http, settings):
        """The moment a writer lands, this reports real ages with nothing to wire.

        Written against the contract Chunk 20's job will meet — the receipt's
        filename and its `completed_at` key — so a job that spelled either
        differently fails here rather than reporting a fresh backup for ever.
        """
        receipt = settings.art_root / BACKUP_RECEIPT_FILENAME
        receipt.write_text(
            json.dumps(
                {
                    "completed_at": (datetime.now(UTC) - timedelta(days=6)).isoformat(),
                    "destination": "nas.lan:/volume1/backups/catalogue-2026-08-05.sqlite",
                }
            ),
            encoding="utf-8",
        )
        backup = http.get("/api/health").json()["backup"]
        assert backup["absent"] is False
        assert "6 days ago" in backup["description"]
        assert backup["reported"]["destination"].endswith("catalogue-2026-08-05.sqlite")

    def test_no_budget_balance_appears_anywhere_on_the_panel(self, http):
        """Settled 2026-08-04, and asserted because the temptation recurs.

        `limit_remaining` reads non-zero while calls are already being refused, so
        it fails by inversion rather than by staleness — and stating its age, this
        panel's whole remedy for a stale figure, would not warn about the case
        that bites. A future edit that adds it back has to delete this test, which
        is the point at which the decision gets reopened rather than forgotten.
        """
        named = _every_key(http.get("/api/health").json())
        assert not [key for key in named if any(word in key for word in ("limit", "credit", "balance", "budget"))]
        # And the panel is three observations, not four. The check above would
        # pass for a balance carried under a name that dodges those four words.
        assert set(http.get("/api/health").json()) == {"heartbeat", "backup", "artwork_box"}

    def test_the_panel_shows_the_geometry_every_size_in_the_grid_is_judged_against(self, http):
        box = http.get("/api/health").json()["artwork_box"]
        # The reference 42" 4K panel with the shipped 2.5" mat: 3840 less two
        # mats of 262 px, and 2160 less a top mat plus a bottom weighted 1.15x.
        assert box["width"] == 3316
        assert box["height"] == 1597
        assert box["floor_inches"] == 12.0


class TestTheWholeLoop:
    def test_the_whole_curatorial_loop_runs_over_http(self, http, hold, wall):
        """Chunk 10B's acceptance criterion, start to finish.

        See the works, build a theme, put it on the wall, and read exactly why a
        work that is in the theme is not on the wall.
        """
        ready = hold("Chop Suey", rendered=True, mat=True)
        no_mat = hold("Chosen but unmatted", rendered=True)
        no_render = hold("Acquired but unrendered", mat=True)

        works = http.get("/api/works").json()["works"]
        assert {ready.id, no_mat.id, no_render.id} <= {work["artwork_id"] for work in works}

        theme = http.post("/api/themes", json={"name": "Late night"}).json()
        for artwork in (ready, no_mat, no_render):
            added = http.post(f"/api/themes/{theme['theme_id']}/works", json={"artwork_id": artwork.id})
            assert added.status_code == 200
        assert [work["artwork_id"] for work in added.json()["works"]] == [ready.id, no_mat.id, no_render.id]

        activated = http.post(f"/api/themes/{theme['theme_id']}/activate", json={"wall_id": wall["wall_id"]})
        assert activated.status_code == 200
        published = activated.json()

        assert [entry["artwork_id"] for entry in published["entries"]] == [ready.id]
        # The half a list-only view drops silently, and the reason this criterion
        # says "exactly why" rather than "which".
        excluded = {exclusion["artwork_id"]: exclusion for exclusion in published["exclusions"]}
        assert excluded[no_mat.id]["reason"] == "no_mat_color"
        assert "No mat colour has been chosen" in excluded[no_mat.id]["detail"]
        assert excluded[no_render.id]["reason"] == "no_rendition"
        assert "not been rendered for the television" in excluded[no_render.id]["detail"]
        assert published["summary"] == "1 of 3 works in this theme are on the wall; 2 are not currently displayable."

        # And the standing view of the wall agrees with what activation returned.
        standing = http.get("/api/manifest", params={"wall_id": wall["wall_id"]}).json()
        assert standing["theme"]["theme_id"] == theme["theme_id"]
        # Named, so a confirmation built from this response says which room —
        # even while there is one wall and the answer looks obvious.
        assert (standing["wall_id"], standing["wall_name"]) == (wall["wall_id"], wall["name"])
        assert [entry["artwork_id"] for entry in standing["entries"]] == [ready.id]
        assert len(standing["exclusions"]) == 2

    def test_activating_a_theme_publishes_the_manifest_the_display_plane_reads(self, http, hold, settings, wall):
        """Activation changes the wall, so it must write the file, not only the row."""
        artwork = hold("Automat", rendered=True, mat=True)
        theme = http.post("/api/themes", json={"name": "Late night"}).json()
        http.post(f"/api/themes/{theme['theme_id']}/works", json={"artwork_id": artwork.id})
        http.post(f"/api/themes/{theme['theme_id']}/activate", json={"wall_id": wall["wall_id"]})
        assert settings.manifest_path.is_file()


class TestThemeOrder:
    @pytest.fixture
    def theme_with_three(self, http, hold):
        works = [hold(f"Work {index}") for index in range(3)]
        theme = http.post("/api/themes", json={"name": "Evening"}).json()
        for artwork in works:
            http.post(f"/api/themes/{theme['theme_id']}/works", json={"artwork_id": artwork.id})
        return theme["theme_id"], [artwork.id for artwork in works]

    def test_a_work_can_be_moved_and_the_new_order_comes_back(self, http, theme_with_three):
        theme_id, ids = theme_with_three
        response = http.post(f"/api/themes/{theme_id}/works/{ids[2]}/position", json={"position": 0})
        assert [work["artwork_id"] for work in response.json()["works"]] == [ids[2], ids[0], ids[1]]

    def test_a_work_can_be_removed_and_the_rest_keep_their_order(self, http, theme_with_three):
        theme_id, ids = theme_with_three
        response = http.request("DELETE", f"/api/themes/{theme_id}/works/{ids[1]}")
        assert [work["artwork_id"] for work in response.json()["works"]] == [ids[0], ids[2]]

    def test_the_theme_listing_names_the_walls_each_theme_hangs_on(self, http, theme_with_three, wall):
        """A boolean could say "on the wall"; only a list can say which, and how many."""
        theme_id, _ = theme_with_three
        http.post(f"/api/themes/{theme_id}/activate", json={"wall_id": wall["wall_id"]})

        themes = http.get("/api/themes").json()["themes"]

        hung = {entry["theme"]["theme_id"]: entry["hanging_on"] for entry in themes}
        assert [where["wall_id"] for where in hung[theme_id]] == [wall["wall_id"]]
        assert [where["name"] for where in hung[theme_id]] == [wall["name"]]
        # And every other theme says plainly that it hangs nowhere, which is an
        # ordinary state rather than an absent field.
        assert all(hung[other] == [] for other in hung if other != theme_id)


class TestRefusalsReachTheCurator:
    def test_a_refused_operation_returns_the_service_message(self, http):
        response = http.post("/api/themes/nope/works", json={"artwork_id": "also-nope"})
        assert response.status_code == 400
        assert "nope" in response.json()["error"]

    def test_asking_for_the_wall_with_no_active_theme_says_so(self, http, wall):
        response = http.get("/api/manifest", params={"wall_id": wall["wall_id"]})
        assert response.status_code == 400
        assert response.json()["error"]

    def test_a_duplicate_theme_name_is_refused_rather_than_silently_accepted(self, http):
        http.post("/api/themes", json={"name": "Evening"})
        response = http.post("/api/themes", json={"name": "Evening"})
        assert response.status_code == 400


class TestStateThatIsEasyToHide:
    def test_an_archived_work_still_lists_and_says_it_is_archived(self, http, hold, service):
        """The catalogue lists accepted and archived together — that is what "everything we hold" means.

        So the surface has to carry the difference. A card that shows an archived
        work exactly as it shows a live one is the same silence the exclusion
        report exists to break, one screen earlier.
        """
        artwork = hold("Withdrawn")
        service.archive_artwork(artwork.id)
        card = card_for(http.get("/api/works").json(), artwork.id)
        assert card["status"] == "archived"

    def test_a_status_filter_reaches_the_catalogue(self, http, hold, service):
        """Asserted through a value no default produces: the filter is optional and omitting it lists both."""
        live = hold("Still here")
        gone = hold("Withdrawn")
        service.archive_artwork(gone.id)

        archived = http.get("/api/works", params={"status": "archived"}).json()
        ids = {work["artwork_id"] for work in archived["works"]}
        assert gone.id in ids
        assert live.id not in ids

    def test_an_archived_work_leaves_the_wall_with_its_reason_stated(self, http, hold, service, wall):
        artwork = hold("Withdrawn", rendered=True, mat=True)
        theme = http.post("/api/themes", json={"name": "Late night"}).json()
        http.post(f"/api/themes/{theme['theme_id']}/works", json={"artwork_id": artwork.id})
        service.archive_artwork(artwork.id)

        published = http.post(f"/api/themes/{theme['theme_id']}/activate", json={"wall_id": wall["wall_id"]}).json()
        assert published["entries"] == []
        assert published["exclusions"][0]["reason"] == "archived"
        # Membership is curatorial and survives archiving: the work stays in the
        # theme and simply stops being shown.
        assert published["considered"] == 1


class TestThumbnailRevalidation:
    def test_a_conditional_request_is_answered_with_an_empty_304(self, http, hold):
        """`no-cache` is only affordable if revalidation is cheap.

        `FileResponse` sets an ETag and never reads one — only `StaticFiles`
        compares them, and these files are generated rather than served from a
        directory. Without the check in the handler this returns 200 and the
        whole image, so every repaint of the grid re-downloads every thumbnail.
        """
        artwork = hold("Automat")
        first = http.get(f"/api/works/{artwork.id}/thumbnail")
        etag = first.headers["etag"]

        again = http.get(f"/api/works/{artwork.id}/thumbnail", headers={"If-None-Match": etag})
        assert again.status_code == 304
        assert again.content == b""
        assert again.headers["cache-control"] == first.headers["cache-control"]

    def test_a_stale_validator_gets_the_new_image_rather_than_a_304(self, http, hold, service, settings, decodable_jpeg):
        """The half that matters: revalidating must not confirm a superseded picture."""
        artwork = hold("Automat", width=1600, height=1200)
        stale_etag = http.get(f"/api/works/{artwork.id}/thumbnail").headers["etag"]

        source = service.list_sources(artwork.id)[0]
        replacement = f"raw/{artwork.id}-2.jpg"
        decodable_jpeg(settings.art_root / replacement, width=600, height=1500)
        service.record_original(
            artwork_id=artwork.id,
            source_id=source.id,
            path=replacement,
            width=600,
            height=1500,
            byte_size=(settings.art_root / replacement).stat().st_size,
            content_hash="a-new-acquisition",
            fetch_status=FetchStatus.OK,
        )

        response = http.get(f"/api/works/{artwork.id}/thumbnail", headers={"If-None-Match": stale_etag})
        assert response.status_code == 200
        assert response.content != b""

    def test_a_recomposed_canvas_reaches_the_browser_rather_than_revalidating_clean(
        self, http, hold, service, settings, decodable_jpeg
    ):
        """The trigger the mat controls will rest on, end to end.

        The sibling above changes the *master*, which moves the content hash and
        so is visible to the catalogue's inherited staleness rule. Setting a mat
        colour moves nothing that rule can see: same original, same path, same
        geometry. So this is the case where a validator a browser is holding must
        stop matching because of the thumbnail's own rule and nothing else — and
        `no-cache` means the browser asks every time, so a 304 here is a curator
        looking at the colour they just replaced.
        """
        artwork = hold("Automat", rendered=True, mat=True)
        rendered = f"ready/{artwork.id}.jpg"
        stale_etag = http.get(f"/api/works/{artwork.id}/thumbnail").headers["etag"]

        # What pressing a mat preset amounts to: recompose in place, re-record.
        decodable_jpeg(settings.art_root / rendered, width=3840, height=2160, color=(200, 190, 170))
        service.record_rendition(
            artwork_id=artwork.id,
            kind=RenditionKind.TV_DISPLAY,
            target_width=3840,
            target_height=2160,
            path=rendered,
        )

        response = http.get(f"/api/works/{artwork.id}/thumbnail", headers={"If-None-Match": stale_etag})
        assert response.status_code == 200, "the browser was told its picture of the old mat is still current"
        assert response.headers["etag"] != stale_etag

    def test_a_wildcard_validator_matches_whatever_is_held(self, http, hold):
        """`*` matches any current representation, per RFC 9110.

        By the time the route answers, the file exists — so there is a current
        representation and the answer is 304. Tested because the first version of
        this helper documented the case and did not implement it.
        """
        artwork = hold("Automat")
        http.get(f"/api/works/{artwork.id}/thumbnail")

        response = http.get(f"/api/works/{artwork.id}/thumbnail", headers={"If-None-Match": "*"})
        assert response.status_code == 304
        assert response.content == b""

    def test_a_weak_validator_matches_the_strong_tag_it_was_derived_from(self, http, hold):
        """A conditional GET performs a weak comparison, so `W/"x"` and `"x"` are one tag."""
        artwork = hold("Automat")
        etag = http.get(f"/api/works/{artwork.id}/thumbnail").headers["etag"]

        response = http.get(f"/api/works/{artwork.id}/thumbnail", headers={"If-None-Match": f"W/{etag}"})
        assert response.status_code == 304

    def test_an_unrelated_validator_gets_the_image(self, http, hold):
        """The negative case, so the three above are not passing for the wrong reason."""
        artwork = hold("Automat")
        response = http.get(f"/api/works/{artwork.id}/thumbnail", headers={"If-None-Match": '"not-this-one"'})
        assert response.status_code == 200
        assert response.content.startswith(b"\xff\xd8")

    def test_a_browser_offering_several_validators_still_matches(self, http, hold):
        """A client that has seen two versions of a URL sends both tags."""
        artwork = hold("Automat")
        etag = http.get(f"/api/works/{artwork.id}/thumbnail").headers["etag"]

        offered = f'"something-older", {etag}'
        assert http.get(f"/api/works/{artwork.id}/thumbnail", headers={"If-None-Match": offered}).status_code == 304


class TestWhatTheWallSummaryClaims:
    """All three branches of the one sentence both surfaces state.

    It is shared code, so a change here changes what an agent is told as well as
    what a curator reads — and prose that ships to a caller is behaviour.
    """

    def test_an_empty_theme_says_it_is_empty_rather_than_reporting_zero_of_zero(self, http, wall):
        theme = http.post("/api/themes", json={"name": "Nothing yet"}).json()
        published = http.post(f"/api/themes/{theme['theme_id']}/activate", json={"wall_id": wall["wall_id"]}).json()

        assert published["summary"] == "This theme holds no works yet, so nothing is on the wall."
        assert published["considered"] == 0

    def test_a_theme_with_nothing_missing_states_the_full_count(self, http, hold, wall):
        """ "2 of 2" is what makes "1 of 2" legible, so the clean case is stated too."""
        theme = http.post("/api/themes", json={"name": "All good"}).json()
        for title in ("Automat", "Chop Suey"):
            artwork = hold(title, rendered=True, mat=True)
            http.post(f"/api/themes/{theme['theme_id']}/works", json={"artwork_id": artwork.id})

        published = http.post(f"/api/themes/{theme['theme_id']}/activate", json={"wall_id": wall["wall_id"]}).json()

        assert published["summary"] == "All 2 works in this theme are on the wall."
        assert published["exclusions"] == []

    def test_the_browser_summary_carries_no_pointer_at_a_tool_result_field(self, http, hold, wall):
        """The shared sentence stops at the counts; `not_displayable` is the MCP surface's word.

        A browser has no field by that name, so a summary naming one would be
        telling a curator to look at something that is not on their screen.
        """
        theme = http.post("/api/themes", json={"name": "Mixed"}).json()
        artwork = hold("Unrendered", mat=True)
        http.post(f"/api/themes/{theme['theme_id']}/works", json={"artwork_id": artwork.id})

        published = http.post(f"/api/themes/{theme['theme_id']}/activate", json={"wall_id": wall["wall_id"]}).json()

        assert "not_displayable" not in published["summary"]
        assert published["summary"] == "0 of 1 works in this theme are on the wall; 1 are not currently displayable."


class TestPagingPastTheCatalogueCap:
    """The API caps a page at 100 and the catalogue target is thousands of works.

    The client pages to the end. These pin the server half of that contract —
    that `offset` is honoured and `truncated` is truthful — because the client's
    loop is only correct if those two are.

    The target moved from hundreds to thousands on 2026-08-10, which makes both
    assertions matter more rather than less: whatever replaces the client's
    fetch-everything loop with real paging rests on the same two guarantees, and
    a `truncated` that lies is worse the further the catalogue outruns one page.
    """

    def test_offset_returns_the_next_works_rather_than_the_same_ones(self, http, hold):
        held = sorted(hold(f"Work {index:02d}").id for index in range(6))
        first = http.get("/api/works", params={"limit": 3, "offset": 0}).json()
        second = http.get("/api/works", params={"limit": 3, "offset": 3}).json()

        assert len(first["works"]) == 3
        assert not ({w["artwork_id"] for w in first["works"]} & {w["artwork_id"] for w in second["works"]})
        assert len(held) == 6

    def test_paging_to_the_end_reaches_every_work_exactly_once(self, http, hold):
        """The client's loop, run against the real surface.

        With a page size of 2 over nine works this makes five requests, the last
        of which must report `truncated` false — the condition the loop stops on.
        A `truncated` that stayed true would spin forever.
        """
        for index in range(6):
            hold(f"Work {index:02d}")

        seen, total, pages = [], None, 0
        while pages < 50:
            body = http.get("/api/works", params={"limit": 2, "offset": len(seen)}).json()
            total = body["total"]
            seen.extend(work["artwork_id"] for work in body["works"])
            pages += 1
            if not body["truncated"] or not body["works"]:
                break

        assert len(seen) == total, "paging stopped before the end"
        assert len(set(seen)) == len(seen), "a work was returned on two pages"
        assert total >= 9

    def test_the_last_page_reports_itself_as_complete(self, http, hold):
        """`truncated` is what the client stops on, so a wrong one is an infinite loop."""
        hold("Only one more")
        total = http.get("/api/works", params={"limit": 1}).json()["total"]
        last = http.get("/api/works", params={"limit": 1, "offset": total - 1}).json()

        assert last["truncated"] is False
        assert len(last["works"]) == 1
