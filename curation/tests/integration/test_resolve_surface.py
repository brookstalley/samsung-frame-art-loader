"""The re-search driven by a real MCP client over real HTTP, on the threaded path.

Entered through the tool rather than the runner, for the same reason phase 2 is:
what cannot be checked on the calling thread is whether a re-search actually
advances *behind* the handle a client is holding, and whether the surface's own
long-poll is what tells the client it finished.

This is also where the acceptance criterion lives. A rejected image is
re-searched, the second submission of the same ids is refused by name, and the
parent run's cost includes what the re-search spent — all of it through the tool
a model would call.
"""

import json
from decimal import Decimal

import pytest
from fakes import FakeImageSearch, a_work, an_image

from curation.discovery.engine import WorkList
from curation.persistence.discovery_records import RunKind, RunStatus, SpendCategory, Verdict
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
    """Poll the surface's own long-poll until the run stops moving."""
    for _ in range(8):
        payload, _errored = await call(server_url, "art_discovery", action="status", run_id=run_id)
        if RunStatus(payload["status"]).is_terminal:
            return payload
    raise AssertionError(f"run {run_id} never finished: {payload}")


@pytest.fixture
def museum() -> FakeImageSearch:
    return FakeImageSearch(holdings={"The Elephants": (an_image("The Elephants", url="https://artic.edu/first-scan"),)})


@pytest.fixture
def services(store, discovery_store, wall_settings, thumbnail_settings, settings, engine, museum) -> Services:
    """The whole plane, wired the way a deployment with ARTIC_USER_AGENT set is."""
    engine.result = WorkList(works=(a_work("The Elephants"),))
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


async def a_work_needing_a_better_scan(server_url: str, services: Services):
    """Run discovery, then turn down the instance it found. The acceptance criterion's setup.

    **The work id comes off the surface**, not out of the service. Reaching past
    the tool for it would leave every test here passing while a real client had
    no way to obtain the one argument `resolve_images` requires — which is
    exactly the gap that hid for a whole chunk. Rejecting the image still goes
    through the service, because `art_review` owns `reject_image` and is not
    built yet; that one is a stated dependency rather than a hidden hole.
    """
    started, errored = await call(server_url, "art_discovery", action="start", intent="Dalí, elephants")
    assert errored is False, started
    payload = await finished(server_url, started["run_id"])
    work_id = payload["works"]["each"][0]["work_id"]
    work = services.discovery.get_candidate_work(work_id)
    services.discovery.reject_image(services.discovery.list_candidate_images(work.id)[0].id)
    return started["run_id"], work


async def test_a_client_can_obtain_the_work_ids_the_actions_taking_one_require(server_url):
    """An advertised action whose argument nothing yields is one a model cannot invoke.

    `resolve_images` takes work ids and this is the only built surface that
    produces them, so a run reporting counts alone would leave a fully described
    action with no reachable path to it — the model either fabricates an id or
    stalls. The counts and the works are both here, and the counts are derived
    from the works so the two cannot disagree.
    """
    started, _ = await call(server_url, "art_discovery", action="start", intent="Dalí, elephants")

    payload = await finished(server_url, started["run_id"])

    works = payload["works"]
    assert len(works["each"]) == works["total"] == 1
    only = works["each"][0]
    assert only["work_id"] and only["title"] == "The Elephants"
    assert only["verdict"] and only["resolution_status"]
    # The id is usable as sent, which is the whole claim.
    handle, errored = await call(server_url, "art_discovery", action="resolve_images", work_ids=[only["work_id"]])
    assert errored is False, handle


# -- the acceptance criterion ----------------------------------------------------


async def test_a_rejected_image_can_be_re_searched_over_the_wire(server_url, services, museum):
    """The whole point of the action: a curator asks again and gets a different scan."""
    _, work = await a_work_needing_a_better_scan(server_url, services)
    museum.holdings = {"The Elephants": (an_image("The Elephants", url="https://artic.edu/better-scan"),)}

    handle, errored = await call(server_url, "art_discovery", action="resolve_images", work_ids=[work.id])

    assert errored is False, handle
    assert handle["kind"] == RunKind.RESOLVE
    assert handle["status"] == RunStatus.RESOLVING_IMAGES
    assert "handle, not a result" in handle["notice"]

    payload = await finished(server_url, handle["run_id"])

    assert payload["status"] == RunStatus.COMPLETED
    assert payload["works"]["resolved"] == 1
    settled = services.discovery.get_candidate_work(work.id)
    assert settled.verdict is Verdict.PENDING, "the work is back in front of the curator"
    selected = [image for image in services.discovery.list_candidate_images(work.id) if image.is_selected]
    assert [image.url for image in selected] == ["https://artic.edu/better-scan"]


async def test_the_second_submission_of_the_same_ids_is_refused_and_names_them(server_url, services):
    """Refused rather than deduplicated: a curator who double-submitted should find out."""
    _, work = await a_work_needing_a_better_scan(server_url, services)
    # A live re-search started directly, so its coverage is still held when the
    # second submission arrives. Going through the tool twice would race the
    # first run to completion and test nothing.
    services.discovery.start_resolve_run(candidate_work_ids=[work.id], initiated_by="web_ui")

    refusal, errored = await call(server_url, "art_discovery", action="resolve_images", work_ids=[work.id])

    assert errored is True
    assert "The Elephants" in refusal["error"]
    assert work.id in refusal["error"]


async def test_the_parent_runs_cost_includes_what_the_re_search_spent(server_url, services):
    """ "What did asking for this cost" has to survive the spend moving to another row."""
    parent_id, work = await a_work_needing_a_better_scan(server_url, services)
    before, _ = await call(server_url, "art_discovery", action="spend", run_id=parent_id)

    handle, _ = await call(server_url, "art_discovery", action="resolve_images", work_ids=[work.id])
    await finished(server_url, handle["run_id"])
    services.discovery.record_spend(
        category=SpendCategory.IMAGE_RESEARCH,
        cost_usd=Decimal("0.40"),
        discovery_run_id=handle["run_id"],
    )

    after, _ = await call(server_url, "art_discovery", action="spend", run_id=parent_id)

    assert Decimal(after["cost_usd"]) == Decimal(before["cost_usd"]) + Decimal("0.40")
    assert after["run_direct_cost_usd"] == before["run_direct_cost_usd"], "the parent was not billed for it"
    # And the re-search's own handle answers about itself, with no special-casing.
    mine, _ = await call(server_url, "art_discovery", action="spend", run_id=handle["run_id"])
    assert Decimal(mine["cost_usd"]) == Decimal("0.40")


# -- an interrupted re-search ----------------------------------------------------


async def test_an_interrupted_re_search_frees_the_works_it_was_covering(server_url, services):
    """The double-spend guard must not become a permanent block when a process dies.

    Every terminal state but `interrupted` is written by the run's own process,
    which a killed process cannot do — so without the repair these ids stay
    refused for the life of the catalogue, on the only operation that spends.
    """
    _, work = await a_work_needing_a_better_scan(server_url, services)
    abandoned = services.discovery.start_resolve_run(candidate_work_ids=[work.id], initiated_by="web_ui")

    services.discovery.reconcile()

    assert services.discovery.get_run(abandoned.id).status is RunStatus.INTERRUPTED
    handle, errored = await call(server_url, "art_discovery", action="resolve_images", work_ids=[work.id])
    assert errored is False, handle
    assert await finished(server_url, handle["run_id"])


# -- the surface describes itself honestly ---------------------------------------


async def test_a_finished_re_search_reports_itself_as_one(server_url, services):
    """`status` takes a re-search's id with no special-casing, and says which kind it is.

    The wording each kind gets while it is *working* is a pure function of the
    view, checked in `test_bindings.py` where both branches are reachable
    without racing a run to completion.
    """
    _, work = await a_work_needing_a_better_scan(server_url, services)

    handle, _ = await call(server_url, "art_discovery", action="resolve_images", work_ids=[work.id])
    payload = await finished(server_url, handle["run_id"])

    assert payload["kind"] == RunKind.RESOLVE
    assert payload["parent_run_id"] is not None
    assert "work list" not in handle["notice"], "the handle describes a re-search, not a phase-1 result"


@pytest.mark.parametrize(
    ("sent", "says"),
    [("not-a-list", "must be an array"), ([42], "must be an array of string")],
)
async def test_work_ids_must_be_a_list_of_ids_and_the_refusal_says_so(server_url, sent, says):
    """The wire schema is what a model reads before calling; it has to reject the near-misses.

    The element check is the one that matters over the wire: a JSON client that
    sends the right shape with the wrong contents gets an error about what it
    sent rather than one from whatever tried to use the values.
    """
    refusal, errored = await call(server_url, "art_discovery", action="resolve_images", work_ids=sent)

    assert errored is True
    assert says in refusal["error"]


async def test_every_reason_resolve_images_can_refuse_for_is_named_in_its_tips(server_url, services):
    """Tips are read before a call is made, so a tip stating a rule is behaviour.

    Each refusal here is driven through the real service rather than asserted
    from the tip's wording, so a rule the code stops enforcing takes the tip with
    it instead of leaving prose that quietly became false.
    """
    from curation.mcp.tools import ART_DISCOVERY

    tips = " ".join(ART_DISCOVERY.action("resolve_images").tips)
    _, work = await a_work_needing_a_better_scan(server_url, services)
    other, _ = await call(server_url, "art_discovery", action="start", intent="Hopper, diners")
    await finished(server_url, other["run_id"])
    elsewhere = services.discovery.list_candidate_works(other["run_id"])[0]

    # Checked before anything holds coverage, so this is the refusal it reaches
    # rather than the one below arriving first.
    mixed, errored = await call(server_url, "art_discovery", action="resolve_images", work_ids=[work.id, elsewhere.id])
    assert errored is True
    assert "one discovery run" in mixed["error"] and "one discovery run" in tips

    services.discovery.start_resolve_run(candidate_work_ids=[work.id], initiated_by="web_ui")
    covered, errored = await call(server_url, "art_discovery", action="resolve_images", work_ids=[work.id])
    assert errored is True
    assert "pay twice" in covered["error"] and "pay twice" in tips
