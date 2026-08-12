"""Judging what a run brought back, in the browser, over real HTTP.

Against a real uvicorn server rather than an in-process transport, per the
suite's standing rule: Starlette does not run a mounted sub-app's lifespan, and
an in-process test would pass against an application that fails every MCP
request in production.

**The acceptance criterion this file exists to hold** is the full curator loop —
intent, estimate, review with images, accept, theme, wall — touching no
filesystem, no JSON file and no SSH. `test_the_whole_loop_closes_onto_the_wall`
is that criterion end to end; the rest pin the pieces it would be easy to break
without failing it.

**The pictures are the point, and they are asserted as bytes.** A review surface
that returns a row where an image belongs defeats the one safety control this
product has — `security-model.md` makes displaying the image the whole protection
for a household that never opted in — and a payload with a URL in it looks
identical either way. So the tests here fetch the picture route and decode what
comes back.
"""

import json
from io import BytesIO

import httpx
import pytest
from fakes import FakeImageSearch, a_decodable_jpeg, a_work, an_image
from PIL import Image

from curation.discovery.engine import WorkList
from curation.persistence.discovery_records import RunStatus, Verdict
from curation.services.container import Services
from curation.services.previews import PreviewSettings


@pytest.fixture
def http(server_url):
    """A client pointed at the booted server, with the timeout a Pi deserves."""
    with httpx.Client(base_url=server_url, timeout=30.0) as client:
        yield client


@pytest.fixture
def museum() -> FakeImageSearch:
    """A collection holding a good scan of one work and a tiny one of the other.

    The sizes are load-bearing. 6949 x 8400 clears this deployment's floor and
    900 x 700 does not, which is what makes one work resolvable and the other a
    below-floor instance that must still be *shown, labelled and selectable* —
    the rule `api-contract.md` states and the one a grid quietly hiding small
    scans would break.
    """
    holdings = {
        "The Elephants": (
            an_image("The Elephants", url="https://artic.edu/elephants", width=6949, height=8400),
            an_image("The Elephants", url="https://artic.edu/elephants-alternate", width=4000, height=5000),
        ),
        "Swans Reflecting Elephants": (
            an_image("Swans Reflecting Elephants", url="https://artic.edu/swans", width=900, height=700),
        ),
    }
    found = FakeImageSearch(holdings=holdings)
    found.preview_bytes = a_decodable_jpeg()
    return found


@pytest.fixture
def services(store, discovery_store, wall_settings, thumbnail_settings, settings, engine, museum) -> Services:
    """The whole plane, wired the way a deployment with an image provider is."""
    engine.result = WorkList(works=(a_work("The Elephants"), a_work("Swans Reflecting Elephants")))
    return Services.bind(
        catalogue=store,
        discovery=discovery_store,
        wall=wall_settings,
        thumbnails=thumbnail_settings,
        artwork_box=settings.tv_artwork_box,
        engine=engine,
        discovery_settings=settings.discovery_settings,
        image_search=museum,
        previews=PreviewSettings(art_root=settings.art_root, directory=settings.previews_path),
    )


def finished(http: httpx.Client, run_id: str) -> dict:
    """Follow a run to a terminal state the way the client does — by asking again.

    The browser surface answers immediately rather than holding the request open,
    so following a run is the caller's loop. Bounded by attempts rather than by a
    sleep, so a wedged run fails the test instead of slowing it.
    """
    for _ in range(400):
        view = http.get(f"/api/runs/{run_id}").json()
        if RunStatus(view["run"]["status"]).is_terminal:
            return view
    raise AssertionError(f"run {run_id} never finished: {view}")


def a_finished_run(http: httpx.Client, intent: str = "Dalí, elephants") -> str:
    """Commission a run from the surface and return its id once it has settled."""
    run_id = http.post("/api/runs", json={"intent": intent}).json()["run_id"]
    finished(http, run_id)
    return run_id


def card_for(page: dict, title: str) -> dict:
    return next(card for card in page["works"] if card["work"]["title"] == title)


class TestTheGrid:
    def test_a_run_s_works_arrive_as_cards_with_a_picture_each(self, http):
        run_id = a_finished_run(http)
        page = http.get(f"/api/runs/{run_id}/candidates").json()

        assert {card["work"]["title"] for card in page["works"]} == {"The Elephants", "Swans Reflecting Elephants"}
        assert all(card["shown"] is not None for card in page["works"])
        assert all(card["shown"]["preview_available"] for card in page["works"])

    def test_the_picture_a_card_points_at_is_a_real_image(self, http):
        """Asserted as decodable bytes, not as a 200.

        A route that answered with an empty body, or with a TIFF declared as a
        JPEG, would pass every check short of opening what came back — and a
        review grid of blank boxes is the silent failure this product refuses.
        """
        run_id = a_finished_run(http)
        page = http.get(f"/api/runs/{run_id}/candidates").json()
        image_id = card_for(page, "The Elephants")["shown"]["image_id"]

        response = http.get(f"/api/candidate-images/{image_id}/preview")

        assert response.status_code == 200
        assert response.headers["content-type"] == "image/jpeg"
        assert Image.open(BytesIO(response.content)).format == "JPEG"

    def test_a_scan_too_small_for_the_wall_is_shown_and_labelled_rather_than_hidden(self, http):
        """The rule a grid that hid small scans would break, asserted on the card.

        A work whose every instance is below the floor has no selection at all —
        automatic choice withholds it deliberately — and it must still arrive
        pictured, so the curator can see that something was found and decide for
        themselves. `shown_is_on_offer` is what separates the two situations.
        """
        run_id = a_finished_run(http)
        page = http.get(f"/api/runs/{run_id}/candidates").json()
        card = card_for(page, "Swans Reflecting Elephants")

        assert card["shown"] is not None, "a below-floor instance was hidden rather than labelled"
        assert card["shown"]["preview_available"] is True
        assert card["shown_is_on_offer"] is False
        assert card["shown"]["fit"]["verdict"] == "below_floor"

    def test_every_instance_carries_the_size_it_would_show_at_on_this_wall(self, http):
        """The number a curator judges, since a thumbnail cannot convey resolution.

        900 px and 6949 px are the same picture in a card, and the only thing that
        separates them on screen is this figure.
        """
        run_id = a_finished_run(http)
        page = http.get(f"/api/runs/{run_id}/candidates").json()

        big = card_for(page, "The Elephants")["shown"]["fit"]["rendered_long_edge_inches"]
        small = card_for(page, "Swans Reflecting Elephants")["shown"]["fit"]["rendered_long_edge_inches"]
        assert big > small

    def test_a_card_says_which_kind_of_nothing_when_no_image_was_found(self, http, museum):
        """Chunk 21's whole point has to survive the trip to a card.

        A bare `unresolved` cannot tell a title nobody holds from a scan too small
        for the wall, and the two lead to opposite actions.
        """
        museum.holdings = {}
        run_id = a_finished_run(http)
        page = http.get(f"/api/runs/{run_id}/candidates").json()

        assert {card["work"]["unresolved_reason"] for card in page["works"]} == {"not_held"}
        assert all(card["shown"] is None for card in page["works"])
        assert all(card["instances_held"] == 0 for card in page["works"])

    def test_a_page_reports_what_it_left_off(self, http):
        run_id = a_finished_run(http)
        page = http.get(f"/api/runs/{run_id}/candidates", params={"limit": 1}).json()

        assert len(page["works"]) == 1
        assert page["total"] == 2
        assert page["truncated"] is True

    def test_a_limit_the_service_refuses_is_refused_here_too(self, http):
        """The cap belongs to the service, and the handler must not soften it.

        A binding that clamped an over-large limit instead of passing it on would
        be the handler deciding — and would answer a caller asking for a hundred
        pictures with forty, silently.
        """
        run_id = a_finished_run(http)
        response = http.get(f"/api/runs/{run_id}/candidates", params={"limit": 500})

        assert response.status_code == 400
        assert "limit must be between" in response.json()["error"]


class TestTheAlternates:
    def test_a_work_s_other_scans_are_reachable_from_its_card(self, http):
        run_id = a_finished_run(http)
        page = http.get(f"/api/runs/{run_id}/candidates").json()
        work_id = card_for(page, "The Elephants")["work"]["work_id"]

        listing = http.get(f"/api/candidates/{work_id}/images").json()

        assert listing["held"] == 2
        assert {instance["url"] for instance in listing["instances"]} == {
            "https://artic.edu/elephants",
            "https://artic.edu/elephants-alternate",
        }
        assert [instance["is_selected"] for instance in listing["instances"]] == [True, False]

    def test_choosing_an_alternate_moves_which_scan_the_work_stands_on(self, http):
        run_id = a_finished_run(http)
        page = http.get(f"/api/runs/{run_id}/candidates").json()
        work_id = card_for(page, "The Elephants")["work"]["work_id"]
        listing = http.get(f"/api/candidates/{work_id}/images").json()
        alternate = next(instance for instance in listing["instances"] if not instance["is_selected"])

        chosen = http.post(
            f"/api/candidate-images/{alternate['image_id']}/select",
            json={"rationale": "the crop is kinder to the frame"},
        ).json()

        assert chosen["image_id"] == alternate["image_id"]
        assert chosen["selection_rationale"] == "the crop is kinder to the frame"
        after = http.get(f"/api/candidates/{work_id}/images").json()
        assert [i["image_id"] for i in after["instances"] if i["is_selected"]] == [alternate["image_id"]]

    def test_turning_a_scan_down_keeps_the_work_and_keeps_the_scan_on_the_card(self, http):
        """Rejecting an *image* must never read as rejecting the painting.

        The work moves to `awaiting_better_image` — the verdict an accept/reject
        binary cannot express — and the refused scan stays listed and labelled,
        because it is the evidence of a judgement already made. A card that
        dropped it would leave a curator wondering why a re-search returned fewer
        instances than before.
        """
        run_id = a_finished_run(http)
        page = http.get(f"/api/runs/{run_id}/candidates").json()
        work_id = card_for(page, "The Elephants")["work"]["work_id"]
        listing = http.get(f"/api/candidates/{work_id}/images").json()
        selected = next(instance for instance in listing["instances"] if instance["is_selected"])

        work = http.post(f"/api/candidate-images/{selected['image_id']}/reject").json()

        assert work["verdict"] == str(Verdict.AWAITING_BETTER_IMAGE)
        after = http.get(f"/api/candidates/{work_id}/images").json()
        refused = next(i for i in after["instances"] if i["image_id"] == selected["image_id"])
        assert refused["rejected"] is True
        assert refused["is_selected"] is False
        assert after["held"] == 2, "the refused scan was dropped rather than labelled"

    def test_a_rejected_scan_cannot_be_chosen_again(self, http):
        run_id = a_finished_run(http)
        page = http.get(f"/api/runs/{run_id}/candidates").json()
        work_id = card_for(page, "The Elephants")["work"]["work_id"]
        listing = http.get(f"/api/candidates/{work_id}/images").json()
        selected = next(instance for instance in listing["instances"] if instance["is_selected"])
        http.post(f"/api/candidate-images/{selected['image_id']}/reject")

        response = http.post(f"/api/candidate-images/{selected['image_id']}/select", json={})

        assert response.status_code == 400
        assert "rejected" in response.json()["error"]


class TestTheReSearch:
    def test_a_curator_can_ask_for_better_scans_from_the_browser(self, http):
        """The dead end this binding exists to close.

        Turning a scan down leaves the work `awaiting_better_image`, and nothing
        looks again on its own. Without a binding here, a curator who used the
        grid's own reject button could only escape it from an MCP client.
        """
        run_id = a_finished_run(http)
        page = http.get(f"/api/runs/{run_id}/candidates").json()
        work_id = card_for(page, "The Elephants")["work"]["work_id"]
        listing = http.get(f"/api/candidates/{work_id}/images").json()
        http.post(f"/api/candidate-images/{listing['instances'][0]['image_id']}/reject")

        resolve = http.post("/api/runs/resolve", json={"work_ids": [work_id]}).json()

        assert resolve["kind"] == "resolve"
        assert resolve["parent_run_id"] == run_id
        # A re-search is a run, which is what lets the run view follow it with
        # nothing special to know.
        assert http.get(f"/api/runs/{resolve['run_id']}").status_code == 200

    def test_the_re_search_records_that_a_click_asked_for_it(self, http):
        """Provenance, never authorisation: every surface has identical authority.

        Recorded so "who asked for this" is answerable from the data afterwards,
        the same way starting a run records it.
        """
        run_id = a_finished_run(http)
        page = http.get(f"/api/runs/{run_id}/candidates").json()
        work_id = card_for(page, "The Elephants")["work"]["work_id"]

        resolve = http.post("/api/runs/resolve", json={"work_ids": [work_id]}).json()

        assert resolve["initiated_by"] == "web_ui"

    def test_a_re_search_of_nothing_is_refused_rather_than_started(self, http):
        response = http.post("/api/runs/resolve", json={"work_ids": []})
        assert response.status_code == 400


class TestTheVerdict:
    def test_accepting_promotes_the_work_into_the_catalogue(self, http):
        run_id = a_finished_run(http)
        page = http.get(f"/api/runs/{run_id}/candidates").json()
        work_id = card_for(page, "The Elephants")["work"]["work_id"]

        verdict = http.post(f"/api/candidates/{work_id}/verdict", json={"verdict": "accepted"}).json()

        assert verdict["work"]["verdict"] == "accepted"
        assert verdict["artwork_id"] is not None
        assert http.get(f"/api/works/{verdict['artwork_id']}").status_code == 200

    def test_a_rejection_carries_the_curator_s_reason(self, http):
        run_id = a_finished_run(http)
        page = http.get(f"/api/runs/{run_id}/candidates").json()
        work_id = card_for(page, "Swans Reflecting Elephants")["work"]["work_id"]

        verdict = http.post(
            f"/api/candidates/{work_id}/verdict",
            json={"verdict": "rejected", "reason": "a studio copy, not the painting"},
        ).json()

        assert verdict["work"]["verdict"] == "rejected"
        assert verdict["artwork_id"] is None

    def test_a_terminal_verdict_is_final_and_the_refusal_says_so(self, http):
        run_id = a_finished_run(http)
        page = http.get(f"/api/runs/{run_id}/candidates").json()
        work_id = card_for(page, "The Elephants")["work"]["work_id"]
        http.post(f"/api/candidates/{work_id}/verdict", json={"verdict": "accepted"})

        response = http.post(f"/api/candidates/{work_id}/verdict", json={"verdict": "rejected"})

        assert response.status_code == 400
        assert "final" in response.json()["error"]

    def test_awaiting_better_image_is_refused_here_and_the_refusal_names_the_way_in(self, http):
        """One entry into that verdict, so it and the scan's suppression cannot part."""
        run_id = a_finished_run(http)
        page = http.get(f"/api/runs/{run_id}/candidates").json()
        work_id = card_for(page, "The Elephants")["work"]["work_id"]

        response = http.post(f"/api/candidates/{work_id}/verdict", json={"verdict": "awaiting_better_image"})

        assert response.status_code == 400
        assert "rejecting an image" in response.json()["error"]

    def test_a_newly_minted_artist_that_may_duplicate_a_held_one_is_said_out_loud(self, http, service, engine, museum):
        """The one part of a promotion a curator can neither see nor undo from it.

        A duplicate artist row looks exactly like a painter newly encountered, so
        the near-miss is reported at the moment it happens rather than left in a
        field nobody re-reads.

        Its own painter rather than the module's Dalí, and that is the fixture
        doing real work: the seeded catalogue holds `Salvador Dalí` *exactly*, so
        accepting one of this module's works matches a held artist and mints
        nothing — which is correct behaviour and the wrong setup for this test.
        The pair here is `attribution`'s own worked example: two forms of one
        painter that share a surname and key apart, which is the split this
        product takes on purpose and reports rather than hides.
        """
        held = service.add_artist(name="Jacob Isaacksz van Ruisdael")
        engine.result = WorkList(works=(a_work("Winter Landscape", artist="Jacob van Ruisdael"),))
        museum.holdings = {
            "Winter Landscape": (an_image("Winter Landscape", artist="Jacob van Ruisdael", url="https://artic.edu/winter"),)
        }
        run_id = a_finished_run(http, intent="Dutch winter scenes")
        page = http.get(f"/api/runs/{run_id}/candidates").json()
        work_id = card_for(page, "Winter Landscape")["work"]["work_id"]

        verdict = http.post(f"/api/candidates/{work_id}/verdict", json={"verdict": "accepted"}).json()

        assert verdict["minted_artist"]["name"] == "Jacob van Ruisdael"
        assert [artist["name"] for artist in verdict["possible_duplicate_artists"]] == [held.name]
        assert "may be the same painter" in verdict["notice"]

    def test_an_acceptance_that_matched_a_held_painter_says_nothing_about_artists(self, http):
        """The other side, and the reason the notice is worth reading when it appears.

        A near-miss reported on every acceptance would train a curator to skip the
        one sentence that matters. The seeded catalogue holds this painter, so
        acceptance matches rather than mints and there is nothing to say.
        """
        run_id = a_finished_run(http)
        page = http.get(f"/api/runs/{run_id}/candidates").json()
        work_id = card_for(page, "The Elephants")["work"]["work_id"]

        verdict = http.post(f"/api/candidates/{work_id}/verdict", json={"verdict": "accepted"}).json()

        assert verdict["minted_artist"] is None
        assert verdict["possible_duplicate_artists"] == []
        assert verdict["notice"] is None

    def test_the_picture_is_refused_with_words_once_a_decided_work_loses_it(self, http, services):
        """A reclaimed preview is not a corrupt one, and the two go different places.

        The sweep deletes a decided work's previews on purpose. Reporting that as
        unreadable would send whoever asks looking for a bad download.
        """
        run_id = a_finished_run(http)
        page = http.get(f"/api/runs/{run_id}/candidates").json()
        card = card_for(page, "The Elephants")
        image_id = card["shown"]["image_id"]
        http.post(f"/api/candidates/{card['work']['work_id']}/verdict", json={"verdict": "accepted"})
        services.sweep.run()

        response = http.get(f"/api/candidate-images/{image_id}/preview")

        assert response.status_code == 400
        assert "reclaimed" in response.json()["error"]

    def test_a_card_for_a_decided_work_stops_promising_a_picture(self, http, services):
        """The card knows before it asks, which is what keeps it from painting a blank box."""
        run_id = a_finished_run(http)
        page = http.get(f"/api/runs/{run_id}/candidates").json()
        card = card_for(page, "The Elephants")
        http.post(f"/api/candidates/{card['work']['work_id']}/verdict", json={"verdict": "accepted"})
        services.sweep.run()

        repainted = http.get(f"/api/candidates/{card['work']['work_id']}").json()

        assert repainted["shown"]["preview_available"] is False
        assert "reclaimed" in repainted["shown"]["preview_note"]


class TestTheWholeLoop:
    def test_the_whole_loop_closes_onto_the_wall(self, http, hold_master):
        """Chunk 19B's acceptance criterion, start to finish.

        Intent, estimate, review with images, accept, theme, wall — every id
        threaded out of the previous response, and nothing touched but HTTP. The
        one thing standing in for work this chunk does not own is the master
        image acquisition would fetch after acceptance; everything else is the
        surface answering for itself.

        The wall comes out of the surface like every other id: hanging is an act
        against a named wall, so a loop that reached around the API for it would
        be closing onto a wall no browser could have found.
        """
        wall = http.get("/api/walls").json()["walls"][0]

        estimate = http.get("/api/estimate").json()
        assert estimate["phase"] == "phase_1"

        run_id = http.post("/api/runs", json={"intent": "Dalí, elephants"}).json()["run_id"]
        finished(http, run_id)

        page = http.get(f"/api/runs/{run_id}/candidates").json()
        card = card_for(page, "The Elephants")
        picture = http.get(f"/api/candidate-images/{card['shown']['image_id']}/preview")
        assert Image.open(BytesIO(picture.content)).format == "JPEG"

        accepted = http.post(f"/api/candidates/{card['work']['work_id']}/verdict", json={"verdict": "accepted"}).json()
        artwork_id = accepted["artwork_id"]

        hold_master(artwork_id)

        theme = http.post("/api/themes", json={"name": "Elephants"}).json()
        http.post(f"/api/themes/{theme['theme_id']}/works", json={"artwork_id": artwork_id})
        manifest = http.post(f"/api/themes/{theme['theme_id']}/activate", json={"wall_id": wall["wall_id"]}).json()

        assert [entry["artwork_id"] for entry in manifest["entries"]] == [artwork_id]
        assert manifest["wall_id"] == wall["wall_id"]


@pytest.fixture
def hold_master(service, settings, decodable_jpeg, services):
    """Give an accepted work the master, render and mat the wall requires.

    Acquisition and preparation are Chunk 18's, and a loop test that stopped at
    acceptance would leave the last two steps — theme and wall — asserting
    against a work the manifest correctly excludes. This is the seam where the
    two chunks meet, standing in for a fetch this test has no business making.
    """
    from curation.persistence.records import (
        AcquisitionMethod,
        FetchStatus,
        MatMethod,
        RenditionKind,
        RightsStatus,
        SourceClass,
    )

    def _hold(artwork_id: str, *, width: int = 6000, height: int = 4000) -> None:
        source = service.add_source(
            artwork_id=artwork_id,
            url=f"https://museum.example/{artwork_id}",
            provider="artic",
            source_class=SourceClass.INSTITUTIONAL,
            acquisition_method=AcquisitionMethod.DEZOOMIFY,
            rights_status=RightsStatus.PUBLIC_DOMAIN,
            is_primary=True,
        )
        relative = f"raw/{artwork_id}.jpg"
        decodable_jpeg(settings.art_root / relative, width=width, height=height)
        service.record_original(
            artwork_id=artwork_id,
            source_id=source.id,
            path=relative,
            width=width,
            height=height,
            byte_size=(settings.art_root / relative).stat().st_size,
            content_hash=f"hash-{artwork_id}",
            fetch_status=FetchStatus.OK,
        )
        rendered = f"ready/{artwork_id}.jpg"
        decodable_jpeg(settings.art_root / rendered, width=3840, height=2160)
        service.record_rendition(
            artwork_id=artwork_id,
            kind=RenditionKind.TV_DISPLAY,
            target_width=3840,
            target_height=2160,
            path=rendered,
        )
        service.record_mat_color(artwork_id=artwork_id, hex_rgb="#2b2b2b", method=MatMethod.VISION_MODEL)

    return _hold


def test_the_receipt_contract_the_backup_job_will_meet_is_written_down(settings):
    """The panel reads one key, and a job spelling it differently reports for ever.

    Both ends are ours, unlike the heartbeat's, so this cannot drift across
    planes — but it can drift across chunks, and the reader shipped first.
    """
    from curation.persistence import backup

    receipt = settings.art_root / backup.BACKUP_RECEIPT_FILENAME
    receipt.write_text(json.dumps({"completed_at": "2026-08-05T10:00:00+00:00"}), encoding="utf-8")

    assert backup.read(receipt).completed_at is not None
    receipt.write_text(json.dumps({"timestamp": "2026-08-05T10:00:00+00:00"}), encoding="utf-8")
    reading = backup.read(receipt)
    assert reading.completed_at is None
    assert "completed_at" in reading.problem
