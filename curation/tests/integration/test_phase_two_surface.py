"""Phase 2 driven by a real MCP client over real HTTP, on the threaded path.

Entered through the tool rather than the runner on purpose. The unit suite runs
phase 2 on the calling thread, deliberately; what cannot be checked that way is
whether a run actually advances *behind* the handle a client is holding — a
`start` that returns in milliseconds and a `status` that later reports a
completed run with images on disk.

The `services` fixture is overridden here so the plane is wired with an image
provider. Everywhere else it is not, which is the shipped default when
`ARTIC_USER_AGENT` is unset and the configuration most of the suite has no
business departing from.
"""

import json

import pytest
from fakes import FakeImageSearch, a_work, an_image

from curation.discovery.engine import WorkList
from curation.persistence.discovery_records import ResolutionStatus, RunStatus
from curation.services.container import Services
from curation.services.previews import PreviewSettings


async def call(server_url: str, tool: str, **arguments) -> tuple[dict, bool]:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async with streamable_http_client(f"{server_url}/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool, arguments)
    return json.loads(result.content[0].text), bool(result.isError)


async def finished(server_url: str, run_id: str) -> dict:
    """Poll the surface's own long-poll until the run stops moving.

    A client's loop, not a sleep — which is what makes this a test of the hold
    rather than a test that waiting long enough eventually works.
    """
    for _ in range(8):
        payload, _errored = await call(server_url, "art_discovery", action="status", run_id=run_id)
        if RunStatus(payload["status"]).is_terminal:
            return payload
    raise AssertionError(f"run {run_id} never finished: {payload}")


@pytest.fixture
def museum() -> FakeImageSearch:
    """A collection holding one of the two works the run proposes."""
    return FakeImageSearch(
        holdings={
            "The Elephants": (
                an_image("The Elephants", width=6949, height=8400),
                an_image("The Elephants", width=3000, height=2200),
            )
        }
    )


@pytest.fixture
def services(store, discovery_store, wall_settings, thumbnail_settings, settings, engine, museum) -> Services:
    """The whole plane, wired the way a deployment with ARTIC_USER_AGENT set is."""
    engine.result = WorkList(
        works=(
            a_work("The Elephants"),
            # A work the collection does not hold, so the run has an unresolved
            # outcome to report as well as a resolved one.
            a_work("The Persistence of Memory"),
        )
    )
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


async def test_a_run_resolves_its_images_behind_the_handle_and_completes(server_url, settings):
    """The acceptance criterion, over the wire: one card's worth of data per work."""
    started, errored = await call(server_url, "art_discovery", action="start", intent="Dalí, elephants")
    assert errored is False, started
    run_id = started["run_id"]

    payload = await finished(server_url, run_id)

    assert payload["status"] == RunStatus.COMPLETED
    assert payload["works"]["resolved"] == 1
    assert payload["works"]["unresolved"] == 1
    assert "unresolved" in payload["notice"]


async def test_the_completed_run_carries_a_selected_instance_its_alternates_and_a_rationale(server_url, services):
    started, _ = await call(server_url, "art_discovery", action="start", intent="Dalí, elephants")
    await finished(server_url, started["run_id"])

    works = {work.proposed_title: work for work in services.discovery.list_candidate_works(started["run_id"])}
    images = services.discovery.list_candidate_images(works["The Elephants"].id)

    assert len(images) == 2, "the losing instance is retained as an alternate"
    selected = [image for image in images if image.is_selected]
    assert len(selected) == 1
    assert selected[0].estimated_width == 6949
    assert selected[0].selection_rationale
    assert "The Elephants" in selected[0].selection_rationale


async def test_previews_are_on_disk_when_the_run_finishes(server_url, services, settings):
    """Review must not depend on a museum being reachable, so the bytes are local."""
    started, _ = await call(server_url, "art_discovery", action="start", intent="Dalí, elephants")
    await finished(server_url, started["run_id"])

    works = {work.proposed_title: work for work in services.discovery.list_candidate_works(started["run_id"])}
    images = services.discovery.list_candidate_images(works["The Elephants"].id)

    cached = [settings.art_root / image.preview_path for image in images if image.preview_path]
    assert len(cached) == 2
    assert all(path.is_file() and path.stat().st_size > 0 for path in cached)
    assert all(path.is_relative_to(settings.previews_path) for path in cached)


async def test_the_work_no_collection_holds_is_named_rather_than_dropped(server_url, services):
    """A confident near-match here would launder the one signal that phase 1 erred."""
    started, _ = await call(server_url, "art_discovery", action="start", intent="Dalí, elephants")
    await finished(server_url, started["run_id"])

    results = services.discovery.run_results(started["run_id"])

    assert [work.proposed_title for work in results.unresolved] == ["The Persistence of Memory"]
    assert results.unresolved[0].resolution_status is ResolutionStatus.UNRESOLVED
    assert services.discovery.list_candidate_images(results.unresolved[0].id) == []


async def test_the_status_notice_no_longer_claims_resolution_is_unwired(server_url):
    """The sentence this chunk owed a deletion to, checked at the surface that carried it."""
    started, _ = await call(server_url, "art_discovery", action="start", intent="Dalí, elephants")
    payload = await finished(server_url, started["run_id"])

    assert "not wired up" not in payload["notice"]
    assert "no image provider is configured" not in payload["notice"]


async def test_resolving_costs_nothing_and_the_run_says_so(server_url):
    """Phase 2 asks open museum APIs, so approving a work list spends no more."""
    started, _ = await call(server_url, "art_discovery", action="start", intent="Dalí, elephants")
    run_id = started["run_id"]
    await finished(server_url, run_id)

    spend, errored = await call(server_url, "art_discovery", action="spend", run_id=run_id)

    assert errored is False
    # The engine's phase-1 spend is recorded; phase 2 added nothing to it, so the
    # run's own cost and its cost including descendants are the same figure.
    assert spend["cost_usd"] == spend["run_direct_cost_usd"]
    # And the pre-run estimate a curator would have authorised against says zero
    # for the resolving half, in words as well as in the number.
    estimate, _ = await call(server_url, "art_discovery", action="estimate", run_id=run_id)
    assert estimate["estimated_cost_usd"] == "0"
    assert "free" in estimate["basis"]
