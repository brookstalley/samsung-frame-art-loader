"""The MCP tool surface, asserted against a real server over real HTTP.

This is the level that matters most on this product: the MCP surface is the
only one with external consumers, and the only one where a change that looks
cosmetic — rewording a description — is a real behavioural change.
"""

from importlib.metadata import version

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from curation.manifest.builder import ExclusionReason
from curation.mcp.registry import DESCRIPTION_BUDGET_BYTES
from curation.mcp.tools import ART_DISPLAY, TOOLS
from curation.services.errors import ServiceError

#: A regression here silently renames the entire MCP tool surface for every
#: client. Tool names are a frozen contract: never renamed, never removed.
FROZEN_TOOL_NAMES = {
    "art_catalogue",
    "art_discovery",
    "art_display",
    "art_review",
    "art_theme",
}


@pytest.fixture
async def tools(server_url):
    async with streamable_http_client(f"{server_url}/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
    return {tool.name: tool for tool in listed.tools}


async def test_the_server_boots_and_a_real_client_completes_the_handshake(server_url):
    # The mounted MCP server has no lifespan of its own — Starlette does not
    # run a mounted sub-app's. If the host application failed to drive the
    # session manager, every request below would raise "Task group is not
    # initialized" instead of answering.
    async with streamable_http_client(f"{server_url}/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            result = await session.initialize()

    assert result.serverInfo.name == "samsung-frame-art-loader"
    # The server reports its own version. Left unset the SDK reports its own,
    # so a client asking what it is talking to learns the protocol library's
    # version instead of the product's.
    assert result.serverInfo.version == version("curation")


async def test_the_five_tool_names_are_exactly_these(tools):
    assert set(tools) == FROZEN_TOOL_NAMES


async def test_the_registry_and_the_wire_agree_on_the_tool_list(tools):
    assert set(tools) == {tool.name for tool in TOOLS}


async def test_every_description_fits_the_clients_budget(tools):
    # Claude Code truncates a tool description at 2 KB. Past that the action
    # menu is cut mid-word and the model chooses from a list it cannot see.
    oversized = {
        name: len(tool.description.encode())
        for name, tool in tools.items()
        if len(tool.description.encode()) > DESCRIPTION_BUDGET_BYTES
    }

    assert oversized == {}


async def test_every_tool_declares_its_annotations(tools):
    # Omitted annotations default to the worst case — destructive and
    # open-world — which costs a confirmation prompt on every call.
    for name, tool in tools.items():
        assert tool.annotations is not None, name
        assert tool.annotations.title, name
        assert tool.annotations.readOnlyHint is not None, name
        assert tool.annotations.destructiveHint is not None, name
        assert tool.annotations.openWorldHint is not None, name


async def test_only_the_money_tool_reaches_the_open_world(tools):
    open_world = {name for name, tool in tools.items() if tool.annotations.openWorldHint}

    assert open_world == {"art_discovery"}


async def test_every_tool_requires_an_action_and_nothing_else(tools):
    for name, tool in tools.items():
        assert tool.inputSchema["required"] == ["action"], name
        assert "action" in tool.inputSchema["properties"], name


async def test_every_tool_offers_help_in_its_action_enum(tools):
    for name, tool in tools.items():
        assert "help" in tool.inputSchema["properties"]["action"]["enum"], name


async def test_every_description_lists_the_actions_the_schema_allows(tools):
    # Prose and schema cannot drift: both are generated from one record, and
    # this is the assertion that says so.
    for name, tool in tools.items():
        for action in tool.inputSchema["properties"]["action"]["enum"]:
            assert action in tool.description, f"{name} description omits {action!r}"


# -- a tip is contract text, and must not describe a narrower rule than the code --
#
# Two tips in two consecutive review rounds claimed behaviour the service did not
# have: `activate` said it did not publish when it does, and `show_now` said only
# archived works were refused after the refusal widened. Both were invisible to
# the assertions above, which pin schema and description but never tip text — and
# the tip is the sentence a model reads before deciding whether to call.

#: The word a caller reading the tip would recognise, per cause `show_now` can
#: refuse for. Deliberately not the whole sentence: the tip summarises, and
#: pinning it verbatim would make every wording improvement a failure. What must
#: hold is that no cause is missing from the tip altogether.
_SHOW_NOW_TIP_PREPARES_FOR = {
    ExclusionReason.ARCHIVED: "archived",
    ExclusionReason.NO_ORIGINAL: "master image",
    ExclusionReason.NO_MAT_COLOR: "mat colour",
    ExclusionReason.NO_RENDITION: "render",
    ExclusionReason.STALE_RENDITION: "render",
}


def _show_now_tips() -> str:
    action = next(entry for entry in ART_DISPLAY.actions if entry.name == "show_now")
    return " ".join(action.tips).lower()


def test_every_reason_show_now_can_refuse_for_is_named_in_its_tip():
    """A new exclusion cause must not silently outrun the text that documents it.

    This fails the moment someone adds a sixth `ExclusionReason`, which is the
    point: readiness widened once already and the tip did not follow.
    """
    missing = [reason for reason in ExclusionReason if reason not in _SHOW_NOW_TIP_PREPARES_FOR]
    assert not missing, f"exclusion reasons with no entry in this table: {missing}"

    tips = _show_now_tips()
    for reason, expected in _SHOW_NOW_TIP_PREPARES_FOR.items():
        assert expected in tips, f"the show_now tip does not prepare a caller for {reason.value!r}"


@pytest.mark.parametrize(
    ("reason", "unready"),
    [
        (ExclusionReason.NO_ORIGINAL, {"original": False}),
        (ExclusionReason.NO_MAT_COLOR, {"mat": False}),
        (ExclusionReason.NO_RENDITION, {"rendition": False}),
    ],
)
def test_each_documented_refusal_is_one_the_service_actually_raises(display, ready_work, reason, unready):
    """The other half: the tip must not promise a refusal the code does not make.

    Driving the real service rather than reading the table above, so this pins
    tip text to behaviour rather than to itself.
    """
    work = ready_work(**unready)

    with pytest.raises(ServiceError) as refused:
        display.show_work_now(work.id)

    assert _SHOW_NOW_TIP_PREPARES_FOR[reason] in str(refused.value).lower()


def test_an_archived_work_is_refused_in_the_words_the_tip_uses(service, display, ready_work):
    work = ready_work()
    service.archive_artwork(work.id)

    with pytest.raises(ServiceError) as refused:
        display.show_work_now(work.id)

    assert "archived" in str(refused.value).lower()


def test_a_stale_render_is_refused_in_the_words_the_tip_uses(service, display, ready_work):
    work = ready_work()
    source = service.list_sources(work.id)[0]
    service.record_original(
        artwork_id=work.id,
        source_id=source.id,
        path=f"raw/{work.id}.tif",
        width=6000,
        height=4000,
        byte_size=90_000_000,
        content_hash="a-later-acquisition",
    )

    with pytest.raises(ServiceError) as refused:
        display.show_work_now(work.id)

    assert "render" in str(refused.value).lower()
