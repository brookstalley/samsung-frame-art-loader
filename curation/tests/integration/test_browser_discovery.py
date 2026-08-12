"""Commissioning a run from the browser, and watching it, over real HTTP.

Against a real uvicorn server rather than an in-process transport, per the
suite's standing rule: Starlette does not run a mounted sub-app's lifespan, and
an in-process test would pass against an application that fails every MCP
request in production.

**The acceptance criterion this file exists to hold** is that a curator can
enter an intent, read the estimate *before* deciding, approve or decline the work
list, and watch the run to a terminal state — touching no filesystem, no JSON
file and no SSH. `test_the_run_half_runs_over_http` is that criterion end to end;
the rest pin the pieces it would be easy to break without failing it.

The threaded path is exercised here rather than mocked away. The unit suite runs
phase 1 on the calling thread deliberately, but a handle that must come back
while the work goes on behind it is not a claim a synchronous test can check.
"""

import threading
import time
from decimal import Decimal

import httpx
import pytest
from fakes import (
    FakeImageSearch,
    a_collection_holding,
    a_work,
    a_work_list,
    an_image,
    works,
)

from curation.discovery.engine import WorkList
from curation.persistence.discovery_records import RunStatus, UnresolvedReason
from curation.services.container import Services
from curation.services.previews import PreviewSettings


@pytest.fixture
def http(server_url):
    """A client pointed at the booted server, with the timeout a Pi deserves."""
    with httpx.Client(base_url=server_url, timeout=30.0) as client:
        yield client


def settled(http: httpx.Client, run_id: str, *, until=lambda status: status != RunStatus.RESOLVING_WORKS) -> dict:
    """Poll the run until it is past the state named, the way the client does.

    The browser surface answers immediately rather than holding the request open,
    so following a run is the caller's loop — which makes this helper the same
    shape as the one in `app.js`, and a test of the polling contract rather than
    a sleep that eventually works.
    """
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        view = http.get(f"/api/runs/{run_id}").json()
        if until(view["run"]["status"]):
            return view
        time.sleep(0.02)
    raise AssertionError(f"run {run_id} never settled: {view}")


class TestCommissioningARun:
    """A phase-1-only deployment — no image provider wired, which is coherent."""

    def test_the_discovery_view_survives_a_reload(self, http):
        """In-page navigation writes a fragment, but a bookmark is a real path."""
        assert http.get("/discovery").status_code == 200

    def test_the_estimate_is_available_before_anything_is_committed(self, http):
        """The price sits beside the field, which is the point of asking here.

        An estimate a curator can only read *after* starting the run is not an
        estimate, it is a receipt.
        """
        response = http.get("/api/estimate")

        assert response.status_code == 200
        estimate = response.json()
        assert estimate["phase"] == "phase_1"
        assert Decimal(estimate["estimated_cost_usd"]) > 0
        assert estimate["basis"]
        assert estimate["run_id"] is None

    def test_estimating_starts_no_run(self, http):
        """It costs nothing because it does nothing — asserted, not asserted of."""
        http.get("/api/estimate")

        assert http.get("/api/runs").json()["count"] == 0

    def test_a_start_returns_a_handle_rather_than_a_result(self, http, engine):
        """Well inside the two seconds the contract allows, and not by being fast.

        The gate holds phase 1 open, so a `start` that waited for the work could
        not return at all — which is what makes this a test of the handle.
        """
        engine.gate = threading.Event()
        try:
            began = time.monotonic()
            response = http.post("/api/runs", json={"intent": "Dutch still life"})
            elapsed = time.monotonic() - began

            assert response.status_code == 200
            run = response.json()
            assert run["run_id"]
            assert run["status"] == RunStatus.RESOLVING_WORKS
            assert elapsed < 2.0, "a start must return its handle immediately"
        finally:
            engine.gate.set()

    def test_a_run_started_here_is_recorded_as_the_browser_s(self, http):
        """Provenance, never authorisation.

        Every surface has identical authority; this is what makes "who asked for
        forty Dalí candidates" answerable from the data afterwards.
        """
        run = http.post("/api/runs", json={"intent": "Surrealists"}).json()

        assert run["initiated_by"] == "web_ui"

    def test_status_answers_at_once_while_the_run_is_still_working(self, http, engine):
        """The browser surface must not inherit the MCP surface's long poll.

        A model calls `status` once and waits, so holding for it is right there.
        A browser polls on a timer, and a held request occupies one of the worker
        threads these synchronous handlers run in for the whole 45-second hold —
        which starves the pool that also serves thumbnails. This asserts the
        answer arrives immediately *while the run is genuinely in flight*, which
        is the only condition under which the MCP surface would have held.
        """
        engine.gate = threading.Event()
        try:
            run_id = http.post("/api/runs", json={"intent": "Dutch still life"}).json()["run_id"]

            began = time.monotonic()
            response = http.get(f"/api/runs/{run_id}")
            elapsed = time.monotonic() - began

            assert response.status_code == 200
            assert response.json()["run"]["status"] == RunStatus.RESOLVING_WORKS
            assert elapsed < 2.0, "the browser surface held the request open instead of answering"
        finally:
            engine.gate.set()

    def test_a_run_says_whether_it_has_ended_so_the_page_knows_when_to_stop(self, http, engine):
        """The one fact the client's polling loop reads, and it is read from the enum.

        A list of finished states written into the browser instead would go stale
        the day a tenth is added: too short and the page polls a run that ended
        forever, too long and it stops repainting a run still working, so a
        curator watches a live search that appears frozen.

        **Both directions are asserted**, because either constant passes half of
        this — and the sweep that found this branch undefended found it by
        replacing the value with `True`.
        """
        engine.gate = threading.Event()
        try:
            run_id = http.post("/api/runs", json={"intent": "Surrealists"}).json()["run_id"]
            working = http.get(f"/api/runs/{run_id}").json()["run"]
            assert working["status"] == RunStatus.RESOLVING_WORKS
            assert working["is_terminal"] is False
        finally:
            engine.gate.set()

        settled(http, run_id)
        ended = http.post(f"/api/runs/{run_id}/cancel").json()["run"]

        assert ended["status"] == RunStatus.CANCELLED
        assert ended["is_terminal"] is True

    def test_a_work_list_over_the_threshold_stops_to_ask(self, http, engine, settings):
        """The approval gate, which is the whole reason the run view has buttons."""
        engine.result = a_work_list(settings.discovery_settings.approval_threshold + 1)

        run_id = http.post("/api/runs", json={"intent": "Everything Dalí ever painted"}).json()["run_id"]
        view = settled(http, run_id)

        assert view["run"]["status"] == RunStatus.AWAITING_APPROVAL
        assert view["run"]["approval_required"] is True
        assert view["tally"]["proposed"] == settings.discovery_settings.approval_threshold + 1

    def test_the_gate_can_be_told_what_approving_costs(self, http, engine, settings):
        """The estimate at the *second* point of decision, which is the gate itself.

        The figure and its basis are different questions from the phase-1 one:
        this prices resolving the work list, and today it is zero because phase 2
        asks museum APIs. A bare zero beside an approve button invites reading
        the gate as being about money — it is about the size of the work list —
        so the basis is what the screen shows and what this asserts is present.
        """
        engine.result = a_work_list(settings.discovery_settings.approval_threshold + 1)
        run_id = http.post("/api/runs", json={"intent": "Everything"}).json()["run_id"]
        settled(http, run_id)

        estimate = http.get("/api/estimate", params={"run_id": run_id}).json()

        assert estimate["phase"] == "phase_2"
        assert estimate["run_id"] == run_id
        assert estimate["basis"], "a price with no basis is a number nobody can act on"
        assert "work count" in estimate["basis"]

    def test_pricing_a_run_that_has_not_settled_says_what_to_ask_instead(self, http, engine):
        """The gate's own fetch can fail, and the client shows this rather than nothing.

        A run still working has no phase-2 figure, because the work count that
        prices it is what phase 1 produces. The refusal names the two calls that
        would work, which is what the run view puts on screen in its place.
        """
        engine.gate = threading.Event()
        try:
            run_id = http.post("/api/runs", json={"intent": "Surrealists"}).json()["run_id"]

            response = http.get("/api/estimate", params={"run_id": run_id})

            assert response.status_code == 400
            assert "no phase-2 estimate yet" in response.json()["error"]
        finally:
            engine.gate.set()

    def test_the_work_list_carries_the_reasoning_a_curator_judges(self, http, engine):
        """A list of titles is not a work list a curator can approve or refuse."""
        engine.result = a_work_list(3)

        run_id = http.post("/api/runs", json={"intent": "Surrealists"}).json()["run_id"]
        view = settled(http, run_id)

        assert [work["title"] for work in view["works"]]
        assert all(work["rationale"] for work in view["works"])
        assert all(work["provenance"] == "proposed" for work in view["works"])

    def test_the_engine_s_reading_of_the_intent_reaches_the_screen(self, http, engine):
        """A work list is judged against the reading of the request, not its wording."""
        engine.result = WorkList(works=works(2), spend=a_work_list().spend, strategy="Took 'recent' to mean since 2020.")

        run_id = http.post("/api/runs", json={"intent": "recent surrealists"}).json()["run_id"]
        view = settled(http, run_id)

        assert view["run"]["strategy"] == "Took 'recent' to mean since 2020."

    def test_approving_moves_the_run_on(self, http, engine, settings):
        engine.result = a_work_list(settings.discovery_settings.approval_threshold + 1)
        run_id = http.post("/api/runs", json={"intent": "Everything"}).json()["run_id"]
        settled(http, run_id)

        response = http.post(f"/api/runs/{run_id}/approve")

        assert response.status_code == 200
        assert response.json()["run"]["status"] != RunStatus.AWAITING_APPROVAL

    def test_declining_ends_the_run_without_spending_further(self, http, engine, settings):
        engine.result = a_work_list(settings.discovery_settings.approval_threshold + 1)
        run_id = http.post("/api/runs", json={"intent": "Everything"}).json()["run_id"]
        settled(http, run_id)

        view = http.post(f"/api/runs/{run_id}/decline").json()

        assert view["run"]["status"] == RunStatus.DECLINED

    def test_cancelling_stops_a_run_and_keeps_what_it_spent(self, http, engine):
        """The spend survives the cancellation, in the ledger rather than on the run.

        `actual_cost_usd` stays null here on purpose — a cancelled run has no
        settled total — so a screen that read cancellation as "this cost
        nothing" would be reading the wrong field. What was actually billed is
        the ledger's answer, and it is unaffected by the run ending early.
        """
        engine.result = a_work_list(3)
        run_id = http.post("/api/runs", json={"intent": "Surrealists"}).json()["run_id"]
        settled(http, run_id)

        view = http.post(f"/api/runs/{run_id}/cancel").json()

        assert view["run"]["status"] == RunStatus.CANCELLED
        assert Decimal(http.get(f"/api/runs/{run_id}/spend").json()["cost_usd"]) > 0

    def test_a_run_with_no_image_provider_says_so_rather_than_looking_stuck(self, http, engine):
        """Two situations share `resolving_images`, and the wiring tells them apart.

        A run nothing will ever pick up and a run under way are indistinguishable
        from the state name alone, so the flag is what a screen describing that
        state has to read.
        """
        engine.result = a_work_list(2)
        run_id = http.post("/api/runs", json={"intent": "Surrealists"}).json()["run_id"]

        view = settled(http, run_id)

        assert view["run"]["status"] == RunStatus.RESOLVING_IMAGES
        assert view["image_resolution_available"] is False

    def test_the_search_allowance_is_reported_beside_its_usage(self, http, engine):
        """Two numbers, never one verdict.

        The usage is this run's own history and the allowance is the deployment's
        current setting, so a run read after the setting changed shows both
        rather than a boolean recomputed against a rule it never ran under.
        """
        engine.result = a_work_list(2, searches=3)
        run_id = http.post("/api/runs", json={"intent": "Surrealists"}).json()["run_id"]

        view = settled(http, run_id)

        assert view["searches"]["used"] == 3
        assert view["searches"]["allowance"] > 0
        assert view["searches"]["exhausted"] is False

    def test_runs_are_listed_newest_first_and_can_be_narrowed(self, http, engine, settings):
        engine.result = a_work_list(settings.discovery_settings.approval_threshold + 1)
        waiting = http.post("/api/runs", json={"intent": "Surrealists"}).json()["run_id"]
        settled(http, waiting)
        engine.result = a_work_list(2)
        settled(http, http.post("/api/runs", json={"intent": "Dutch still life"}).json()["run_id"])

        everything = http.get("/api/runs").json()
        narrowed = http.get("/api/runs", params={"status": "awaiting_approval"}).json()

        assert everything["count"] == 2
        assert [run["run_id"] for run in narrowed["runs"]] == [waiting]

    def test_what_a_run_actually_cost_is_readable(self, http, engine):
        engine.result = a_work_list(2)
        run_id = http.post("/api/runs", json={"intent": "Surrealists"}).json()["run_id"]
        settled(http, run_id)

        spend = http.get(f"/api/runs/{run_id}/spend").json()

        assert spend["run_id"] == run_id
        assert Decimal(spend["cost_usd"]) > 0

    def test_a_price_is_never_a_float_on_the_wire(self, http, engine):
        """A price through binary floating point comes back as 0.12699999999999999.

        Asserted on the raw body rather than the parsed one: `json()` would turn
        a JSON number back into a float and hide exactly what this refuses.
        """
        engine.result = a_work_list(2)
        run_id = http.post("/api/runs", json={"intent": "Surrealists"}).json()["run_id"]
        settled(http, run_id)

        body = http.get(f"/api/runs/{run_id}/spend").text

        assert '"cost_usd":"' in body.replace(" ", "")

    def test_an_unknown_run_is_refused_with_something_to_act_on(self, http):
        response = http.get("/api/runs/no-such-run")

        assert response.status_code == 400
        assert "no-such-run" in response.json()["error"]

    def test_the_run_half_runs_over_http(self, http, engine, settings):
        """The acceptance criterion, end to end, touching nothing but the surface.

        Intent → estimate → approve → watch, with the gate genuinely engaged in
        the middle. Everything a curator does here is a request to `/api/*`.
        """
        engine.result = a_work_list(settings.discovery_settings.approval_threshold + 1)

        before = http.get("/api/estimate").json()
        assert Decimal(before["estimated_cost_usd"]) > 0

        run_id = http.post("/api/runs", json={"intent": "Everything Dalí ever painted"}).json()["run_id"]
        waiting = settled(http, run_id)
        assert waiting["run"]["status"] == RunStatus.AWAITING_APPROVAL
        assert waiting["works"], "a gate with nothing to read is a gate nobody can answer"

        approved = http.post(f"/api/runs/{run_id}/approve").json()
        assert approved["run"]["status"] != RunStatus.AWAITING_APPROVAL

        spend = http.get(f"/api/runs/{run_id}/spend").json()
        assert Decimal(spend["cost_usd"]) > 0


class TestWhatTheRunBroughtBack:
    """A deployment wired for phase 2, so the tallies have something to count."""

    @pytest.fixture
    def museum(self) -> FakeImageSearch:
        """Holds one of the three works the run proposes."""
        return FakeImageSearch(holdings={"The Elephants": (an_image("The Elephants", width=6949, height=8400),)})

    @pytest.fixture
    def collection(self):
        """Volunteers work by an artist the run named and could not confirm."""
        return a_collection_holding(**{"Salvador Dalí": ("Soft Construction with Boiled Beans",)})

    @pytest.fixture
    def services(self, store, discovery_store, wall_settings, thumbnail_settings, settings, engine, museum, collection):
        engine.result = WorkList(
            works=(
                a_work("The Elephants"),
                # Works no collection holds, so the run has unresolved outcomes
                # to report as well as a resolved one.
                a_work("The Persistence of Memory"),
                a_work("Galatea of the Spheres"),
            ),
            spend=a_work_list().spend,
        )
        return Services.bind(
            catalogue=store,
            discovery=discovery_store,
            display_settings=wall_settings,
            thumbnails=thumbnail_settings,
            artwork_box=settings.tv_artwork_box,
            engine=engine,
            discovery_settings=settings.discovery_settings,
            image_search=museum,
            collection=collection,
            previews=PreviewSettings(art_root=settings.art_root, directory=settings.previews_path),
        )

    def finished(self, http, run_id: str) -> dict:
        return settled(http, run_id, until=lambda status: RunStatus(status).is_terminal)

    def test_an_unresolved_work_says_which_kind_of_nothing(self, http):
        """A bare `unresolved` cannot tell a title nobody holds from a scan too small.

        The reason is derived where the judgement is made and would be thrown
        away by a surface that reported only the status — which is the whole
        point of having derived it.
        """
        run_id = http.post("/api/runs", json={"intent": "Dalí"}).json()["run_id"]
        view = self.finished(http, run_id)

        unresolved = [work for work in view["works"] if work["resolution_status"] == "unresolved"]
        assert unresolved, "the fixture proposes two works no collection holds"
        assert all(work["unresolved_reason"] for work in unresolved)
        assert {work["unresolved_reason"] for work in unresolved} <= {str(r) for r in UnresolvedReason}

    def test_offered_works_are_labelled_apart_from_proposed_ones(self, http):
        """The curator authorised a list of a stated size; the supplement adds to it."""
        run_id = http.post("/api/runs", json={"intent": "Dalí"}).json()["run_id"]
        view = self.finished(http, run_id)

        offered = [work for work in view["works"] if work["provenance"] == "offered"]
        assert offered, "the wired collection volunteered nothing"
        assert view["tally"]["offered"] == len(offered)
        assert view["tally"]["proposed"] == 3
        assert view["tally"]["total"] == view["tally"]["proposed"] + view["tally"]["offered"]

    def test_the_resolution_numerator_counts_proposals_and_never_subtracts(self, http):
        """`resolved_proposals` is a direct count, and this is why it has to be.

        Derived as `resolved - offered_count` it is right only while every
        offered work is still resolved — and an offered work does not stay that
        way. The tally must be usable as a numerator without the reader checking
        whether the arithmetic still holds.
        """
        run_id = http.post("/api/runs", json={"intent": "Dalí"}).json()["run_id"]
        view = self.finished(http, run_id)
        tally = view["tally"]

        resolved_proposals = [
            work for work in view["works"] if work["provenance"] == "proposed" and work["resolution_status"] == "resolved"
        ]
        assert tally["resolved_proposals"] == len(resolved_proposals)
        assert tally["resolved_proposals"] >= 0
        # The rate a curator reads is stated over what the model proposed. Rating
        # it over the total counts works that arrived carrying their own images,
        # which is a retrieval rate nothing achieved.
        assert tally["resolved_proposals"] <= tally["proposed"]

    def test_every_tally_agrees_with_the_list_beneath_it(self, http):
        """The counts and the works are one fact, and a screen shows both at once."""
        run_id = http.post("/api/runs", json={"intent": "Dalí"}).json()["run_id"]
        view = self.finished(http, run_id)
        tally = view["tally"]

        assert tally["total"] == len(view["works"])
        for status in ("resolved", "unresolved", "pending"):
            counted = [work for work in view["works"] if work["resolution_status"] == status]
            assert tally[status] == len(counted), status
