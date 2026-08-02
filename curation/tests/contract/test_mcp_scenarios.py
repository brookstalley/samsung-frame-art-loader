"""Whether the five consolidated tools compose into the flows the product is for.

The surface tests beside this file pin shape. These pin *navigation*: that a
caller starting from nothing can reach a stated goal, and that each tool hands
the next one something it can actually use. Every id below comes out of the
previous call's envelope rather than out of a fixture, because two tools that
disagree about a field name both pass their own tests and fail together only
here.

The rosters are derived from the registry, never typed out. A literal list is
complete on the day it is written and green forever afterwards — including the
day a sixth tool or a new action arrives with nothing exercising it.
"""

import pytest
from fakes import a_work_list
from scenarios import DISCOVERY_ROUTE, REFERENCE_ROUTE, connect

from curation.mcp.registry import HELP_ACTION
from curation.mcp.tools import TOOLS

#: Every tool, by name, as the registry holds them. Parametrising from this is
#: what makes a newly-registered tool arrive already covered.
TOOL_NAMES = [tool.name for tool in TOOLS]

#: The tools registered but not yet wired: they answer `help` and say why.
UNBUILT = [tool.name for tool in TOOLS if not tool.available]


async def test_a_work_can_be_put_on_the_wall_through_the_tools_alone(server_url, ready_work):
    """The core flow, start to finish, using nothing but what the surface returns.

    This is the claim the five-tool consolidation makes: a caller who knows the
    goal and none of the ids can get there. Every argument below is threaded out
    of a previous response.
    """
    work = ready_work(title="Sunday Afternoon on the Island of La Grande Jatte")

    async with connect(server_url) as caller:
        listing = await caller.ok("art_catalogue", "list")
        chosen = next(entry for entry in listing["artworks"] if entry["artwork_id"] == work.id)

        # A name no default could have produced, so the assertion below cannot
        # pass against a theme the service invented on its own.
        created = await caller.ok("art_theme", "create", name="Pointillism, briefly")
        theme_id = created["theme"]["theme_id"]

        added = await caller.ok("art_theme", "add", theme_id=theme_id, artwork_id=chosen["artwork_id"])
        assert added["artwork_id"] == work.id

        published = await caller.ok("art_theme", "activate", theme_id=theme_id)

        assert published["theme"]["name"] == "Pointillism, briefly"
        assert published["theme"]["is_active"] is True
        on_the_wall = [entry["artwork_id"] for entry in published["on_the_wall"]]
        assert on_the_wall == [work.id], f"after {caller.transcript}"

    # The goal is reached by exactly the reference route. Asserting it is what
    # makes a regression in navigability — an extra required round trip — fail
    # here rather than become a slowly worsening number nobody reads. The route
    # lives in `scenarios.py` because the model-driven evaluation sizes its call
    # budget from it, and a second copy would drift while both stayed true.
    assert tuple(caller.transcript.steps) == REFERENCE_ROUTE


async def test_a_work_that_cannot_be_shown_is_reported_rather_than_dropped(server_url, seeded_titles):
    """The seeded works have no rendition, so the wall cannot show them.

    The failure this guards is silence: a builder that returned only what it
    could show would produce a shorter list and no explanation, and the caller
    would have no way to tell "nothing matched" from "everything was excluded".
    """
    async with connect(server_url) as caller:
        listing = await caller.ok("art_catalogue", "list")
        created = await caller.ok("art_theme", "create", name="Everything, unrendered")
        theme_id = created["theme"]["theme_id"]

        for entry in listing["artworks"]:
            await caller.ok("art_theme", "add", theme_id=theme_id, artwork_id=entry["artwork_id"])

        published = await caller.ok("art_theme", "activate", theme_id=theme_id)

    assert published["on_the_wall"] == []
    excluded = {entry["title"]: entry for entry in published["not_displayable"]}
    assert set(excluded) == set(seeded_titles)

    for title, entry in excluded.items():
        assert entry["reason"], f"{title} was excluded with no reason"
        assert entry["detail"], f"{title}'s exclusion reason carries no explanation"

    # The count of works considered is reported even though none reached the
    # wall — the number a caller needs to know the theme was not simply empty.
    assert published["considered"] == len(seeded_titles)


@pytest.mark.parametrize("tool", TOOL_NAMES)
async def test_help_answers_on_every_tool(server_url, tool):
    """`help` is the documented first move, on the surface's own instructions.

    If it failed on any tool, the first thing a model is told to do would be the
    first thing that breaks — and the tool would have no other way to explain
    itself, since the action menu lives behind exactly this call.
    """
    async with connect(server_url) as caller:
        payload = await caller.ok(tool, HELP_ACTION)

    assert payload["tool"] == tool
    assert payload["actions"], f"{tool}(action='help') listed no actions"


@pytest.mark.parametrize("tool", TOOL_NAMES)
async def test_an_unknown_action_teaches_the_whole_valid_set(server_url, tool):
    """An error names what was wrong, enumerates the alternatives, and shows a call.

    The enumeration is asserted against the registry rather than against itself,
    so error text cannot drift away from the actions the tool really serves —
    the drift that would send a model to an action that does not exist.
    """
    record = next(known for known in TOOLS if known.name == tool)

    async with connect(server_url) as caller:
        payload = await caller.call(tool, "sculpt")

    assert payload["success"] is False
    assert "sculpt" in payload["error"]
    assert payload["valid_actions"] == list(record.action_names)
    assert payload["example"] == f"{tool}(action='help')"
    assert tool in payload["hint"]


@pytest.mark.parametrize("tool", UNBUILT)
async def test_a_tool_that_is_not_built_yet_says_so(server_url, tool):
    """Distinct from an unknown action, and the difference is the whole point.

    These tools are registered with no actions, so a real action name would
    otherwise come back as "unknown action" — telling a caller the action is
    wrong when the truth is that the tool does not serve it yet.
    """
    async with connect(server_url) as caller:
        payload = await caller.call(tool, "start")

    assert payload["success"] is False
    assert "not available yet" in payload["error"]
    # Naming the action it refused proves the refusal is about availability
    # rather than a generic rejection of anything this tool is sent.
    assert "start" in payload["error"]


async def test_a_curator_can_jump_the_wall_to_one_work_and_step_off_it(server_url, ready_work):
    """`show_now` pins a work out of turn; `next` releases it back to rotation.

    Driven through the same threading rule as the flow above — the work reaches
    `show_now` as the id `add` echoed back, not as a fixture attribute.
    """
    work = ready_work(title="A Bar at the Folies-Bergère")

    async with connect(server_url) as caller:
        created = await caller.ok("art_theme", "create", name="One work, pinned")
        theme_id = created["theme"]["theme_id"]
        added = await caller.ok("art_theme", "add", theme_id=theme_id, artwork_id=work.id)
        await caller.ok("art_theme", "activate", theme_id=theme_id)

        pinned = await caller.ok("art_display", "show_now", artwork_id=added["artwork_id"])
        assert pinned["pinned_work_id"] == work.id

        stepped = await caller.ok("art_display", "next")

    assert stepped["pinned_work_id"] is None, "stepping on should release the pin"
    # The sequence advances, which is how the display plane knows the directive
    # it is holding is stale. Equal sequences would leave the wall on the pin.
    assert stepped["sequence"] > pinned["sequence"]


async def test_a_run_can_be_priced_started_watched_and_approved_through_the_tools_alone(server_url, engine):
    """The money flow, start to finish, using nothing but what the surface returns.

    Threaded like the flow above: the run id reaches `status` and `approve` as
    the value `start` actually returned. That is what fails when one action names
    it `run_id` and another expects `id` — a defect invisible from inside either
    action's own tests.
    """
    engine.result = a_work_list(26)

    async with connect(server_url) as caller:
        quoted = await caller.ok("art_discovery", "estimate")
        # Priced before anything is committed to, which is the whole point of
        # the action leading this route.
        assert quoted["phase"] == "phase_1"

        started = await caller.ok("art_discovery", "start", intent="Surrealist paintings with strong blues")
        run_id = started["run_id"]

        watched = await caller.ok("art_discovery", "status", run_id=run_id)
        assert watched["status"] == "awaiting_approval"
        assert watched["works"]["total"] == 26

        approved = await caller.ok("art_discovery", "approve", run_id=run_id)

    assert approved["run_id"] == run_id
    assert approved["status"] == "resolving_images"
    assert tuple(caller.transcript.steps) == DISCOVERY_ROUTE


async def test_the_price_a_run_is_approved_against_is_the_one_it_was_quoted(server_url, engine):
    """A gate authorising against a figure nobody saw is not a gate.

    The two `estimate` calls answer different questions — what asking costs, and
    what resolving what was found costs — and the second is the number the
    approval is actually about, so it has to be readable before approving rather
    than reconstructible afterwards.
    """
    engine.result = a_work_list(26)

    async with connect(server_url) as caller:
        started = await caller.ok("art_discovery", "start", intent="Surrealist paintings")
        run_id = started["run_id"]
        waiting = await caller.ok("art_discovery", "status", run_id=run_id)
        quoted = await caller.ok("art_discovery", "estimate", run_id=run_id)
        approved = await caller.ok("art_discovery", "approve", run_id=run_id)

    assert quoted["phase"] == "phase_2"
    assert quoted["estimated_cost_usd"] == waiting["estimated_cost_usd"]
    assert approved["estimated_cost_usd"] == quoted["estimated_cost_usd"]


async def test_a_declined_run_leaves_the_month_where_phase_one_left_it(server_url, engine):
    """Declining stops the spending that had not happened yet, and only that.

    What phase 1 already cost stays on the books: a run the curator refused
    still made the model call that produced the list they refused.
    """
    engine.result = a_work_list(26)

    async with connect(server_url) as caller:
        started = await caller.ok("art_discovery", "start", intent="Surrealist paintings")
        run_id = started["run_id"]
        await caller.ok("art_discovery", "status", run_id=run_id)
        before = await caller.ok("art_discovery", "spend")

        declined = await caller.ok("art_discovery", "decline", run_id=run_id)
        after = await caller.ok("art_discovery", "spend")

    assert declined["status"] == "declined"
    assert after["cost_usd"] == before["cost_usd"] != "0"


async def test_the_wall_admits_that_nothing_has_reported(server_url):
    """No display plane runs in a test, and `status` says exactly that.

    The dangerous answer here is a cheerful one. `status` reads a heartbeat file
    the display plane writes; with no plane running there is nothing to read,
    and a status that omitted the distinction would let a curator believe the
    wall is showing a theme that in fact reached no hardware at all.
    """
    async with connect(server_url) as caller:
        payload = await caller.ok("art_display", "status")

    assert payload["display_plane_has_reported"] is False
    assert payload["reported_at"] is None
    assert payload["observation"], "status returned no human-readable observation"
