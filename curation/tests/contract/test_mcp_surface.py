"""The MCP tool surface, asserted against a real server over real HTTP.

This is the level that matters most on this product: the MCP surface is the
only one with external consumers, and the only one where a change that looks
cosmetic — rewording a description — is a real behavioural change.
"""

from importlib.metadata import version

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from curation.manifest.builder import ExclusionReason, assess
from curation.mcp.registry import DESCRIPTION_BUDGET_BYTES
from curation.mcp.tools import ART_DISPLAY, ART_THEME, TOOLS, TOOLS_BY_NAME
from curation.persistence.records import FetchStatus, VocabularyKind
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


async def test_exactly_the_tools_that_leave_the_machine_declare_an_open_world(tools):
    """`openWorldHint` is how a client decides a call warrants confirmation, so it
    has to describe reach rather than intent.

    **This test read `== {"art_discovery"}` and was named for the money tool until
    2026-08-03.** Those were the same set when it was written and are not now:
    `art_catalogue` gained `retry_acquisition`, which fetches an arbitrary museum
    URL, and then `set_mat_color`, which asks a vision model. The tool went on
    declaring a closed world through both, understating its reach to every client
    that reads the hint — and *this test passing* was part of why, because it
    asserted the old set rather than the property.

    Both sides are named below, so it still discriminates: the honest failure mode
    is a tool that grows an outward-reaching action and keeps a stale flag, and a
    one-sided assertion would not catch the reverse — a purely local tool marked
    open-world, which costs a confirmation prompt on every call forever.
    """
    open_world = {name for name, tool in tools.items() if tool.annotations.openWorldHint}

    # Reaches outside: discovery searches the web and queries museums; the
    # catalogue re-fetches images and asks a vision model for mat colours.
    assert open_world == {"art_discovery", "art_catalogue"}
    # Purely local: reviewing candidates, arranging themes and writing the
    # manifest all touch this machine's catalogue and its own filesystem.
    assert {"art_review", "art_theme", "art_display"} & open_world == set()


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
#:
#: **Every token must be distinct, and that is asserted below.** Two reasons
#: sharing one word silently satisfies the row for whichever is not actually named
#: — the first version of this table gave both rendition reasons "render", so a
#: stale render went unmentioned in the tip while this guard reported it covered.
_SHOW_NOW_TIP_PREPARES_FOR = {
    ExclusionReason.ARCHIVED: "archived",
    ExclusionReason.NO_ORIGINAL: "master image",
    ExclusionReason.NO_MAT_COLOR: "mat colour",
    ExclusionReason.NO_RENDITION: "television render",
    # A stale render is present rather than missing, so "render" alone does not
    # describe it and would be satisfied by the row above.
    ExclusionReason.STALE_RENDITION: "earlier acquisition",
}


def _exclusion_for(display, work):
    """What the readiness rule actually says about this work."""
    excluded = assess(display._gather(work.id))
    assert excluded is not None, "this work is displayable, so the row it stands for is untested"
    return excluded


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

    tokens = list(_SHOW_NOW_TIP_PREPARES_FOR.values())
    assert len(set(tokens)) == len(
        tokens
    ), f"two reasons share a token in this table, which makes one row pass on the other's word: {tokens}"

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
def test_each_documented_refusal_is_one_the_service_actually_raises(display, ready_work, reason, unready, wall_id):
    """The other half: the tip must not promise a refusal the code does not make.

    Driving the real service rather than reading the table above, so this pins
    tip text to behaviour rather than to itself. The state is asserted through
    `assess` — the reason, not a noun in the message — because two reasons can
    share a word and then this proves nothing about which one fired.
    """
    work = ready_work(**unready)

    excluded = _exclusion_for(display, work)
    assert excluded.reason is reason, "the fixture did not reach the state this row is about"

    with pytest.raises(ServiceError) as refused:
        display.show_work_now(wall_id, work.id)

    # The tip promises the refusal uses the same words sync uses for an
    # excluded work. That is the claim under test, not a shared noun.
    assert excluded.detail in str(refused.value)


def test_an_archived_work_is_refused_in_the_words_the_tip_uses(service, display, ready_work, wall_id):
    work = ready_work()
    service.archive_artwork(work.id)

    excluded = _exclusion_for(display, work)
    assert excluded.reason is ExclusionReason.ARCHIVED

    with pytest.raises(ServiceError) as refused:
        display.show_work_now(wall_id, work.id)

    assert excluded.detail in str(refused.value)
    assert "archived" in str(refused.value).lower()


def test_a_stale_render_is_refused_in_the_words_the_tip_uses(service, display, ready_work, wall_id):
    """Re-acquiring leaves the previous render in place, and it is no longer of this image."""
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
        fetch_status=FetchStatus.OK,
    )

    # On the reason, not on "render": NO_RENDITION's message says "rendered" too,
    # so a noun match would pass on the wrong exclusion entirely.
    excluded = _exclusion_for(display, work)
    assert excluded.reason is ExclusionReason.STALE_RENDITION

    with pytest.raises(ServiceError) as refused:
        display.show_work_now(wall_id, work.id)

    assert excluded.detail in str(refused.value)
    assert "earlier acquisition" in str(refused.value).lower()


# -- the wall a refusal turns on must be in the text that documents it ----------
#
# `delete_theme` refused before this chunk and refuses after it, and the *reason*
# changed underneath: "the active theme, while another exists" became "a theme
# hanging on any wall". A refusal that changes without its tip changing is the
# drift the guards above exist for, and it has now happened twice on this file's
# watch, so the delete tip gets the same treatment `show_now`'s did.

#: What every cause `delete_theme` can refuse for must be recognisable by in the
#: tip. One cause today, which is the whole shape of the generalisation: the
#: theme-count clause went away, so a table with a `last theme` row in it would be
#: documenting a rule the code no longer has.
_DELETE_TIP_PREPARES_FOR = {"hung on a wall": ("hanging", "wall")}

#: Words the retired rule used, which must not survive anywhere in this tool's
#: prose. Asserting the absence rather than only the presence: a tip can name the
#: new rule and go on stating the old one beside it, and a caller reading both
#: learns a rule the service will not honour.
_RETIRED_SINGLE_WALL_PHRASES = (
    "the active theme",
    "while another exists",
    "whichever is oldest",
    "exactly one theme is active",
    "and the only one",
)


def _tool_prose(record) -> str:
    """Every sentence a client can read off one tool record."""
    parts = [record.summary]
    for action in record.actions:
        parts.extend([action.description, *action.tips])
    return " ".join(parts).lower()


def test_the_delete_tip_states_the_refusal_the_service_actually_makes(display, wall_id, ready_work):
    """Driven through the real service, so the tip is pinned to behaviour.

    The check runs both ways round. The tip has to prepare a caller for the
    refusal that fires, and the service has to actually fire it — a tip promising
    a refusal nobody makes is the same defect wearing the other face.
    """
    theme = display.add_theme(name="Late night")
    display.add_to_theme(theme_id=theme.id, artwork_id=ready_work().id)
    display.activate_theme(theme.id, wall_id=wall_id)

    with pytest.raises(ServiceError) as refused:
        display.delete_theme(theme.id)

    action = next(entry for entry in ART_THEME.actions if entry.name == "delete")
    tips = " ".join(action.tips).lower()
    for cause, tokens in _DELETE_TIP_PREPARES_FOR.items():
        for token in tokens:
            assert token in tips, f"the delete tip does not prepare a caller for {cause!r}"
    # And the tip's remedy is one the surface offers: an instruction naming an
    # action that does not exist is worse than none.
    assert {entry.name for entry in ART_THEME.actions} >= {"activate", "unhang"}
    assert "unhang" in tips
    # The message itself, whole, the same treatment the `unhang` notice gets and
    # for the same reason: `api-contract.md` calls this sentence normative and
    # asks two things of it — that it names the walls, and that it offers *both*
    # ways out. A substring check on the wall's name leaves the remedy clause
    # deletable with the suite still green, and the remedy is the half § Errors
    # teach actually binds. The wall's name is read off the service rather than
    # written as a literal, because the default happens to be "The wall": a
    # hardcoded copy would pass on the name while asserting nothing about a wall
    # being named at all, and would fail the day the default is reconfigured.
    assert str(refused.value) == (
        f"Theme 'Late night' is hanging on {display.get_wall(wall_id).name!r}. Hang another theme there first, "
        "or take this one down, so that what those walls show next is a choice rather than whatever was on "
        "them before."
    )


def test_the_refusal_no_longer_fires_for_the_rule_it_used_to(display, wall_id):
    """The other half of the generalisation: a theme that hangs nowhere is deletable.

    It was refused while it was the active theme and another existed, and that
    clause is gone — so a second theme, unhung, deletes even though a theme is
    hanging elsewhere in the catalogue.
    """
    hanging = display.add_theme(name="Late night")
    spare = display.add_theme(name="Daylight")
    display.activate_theme(hanging.id, wall_id=wall_id)

    display.delete_theme(spare.id)

    assert [theme.id for theme in display.list_themes()] == [hanging.id]


def test_the_last_theme_becomes_deletable_by_being_taken_down(display, wall_id):
    """The route the tip points at has to work, or the refusal is a dead end.

    Deleting the last theme was permitted even while active, ratified 2026-08-11
    *because* there was no way to take one down — so a curator could never empty
    the catalogue. The refusal is absolute now, and this is what pays for that.
    """
    only = display.add_theme(name="Late night")
    display.activate_theme(only.id, wall_id=wall_id)

    with pytest.raises(ServiceError):
        display.delete_theme(only.id)

    display.clear_wall(wall_id)
    display.delete_theme(only.id)

    assert display.list_themes() == []


#: Every way `add_wall` can refuse, and a word a caller reading the tip would
#: recognise it by. The wall creator is the newest write on this tool and the
#: only one that was shipped with tips naming no refusal at all — this table is
#: what stops a third cause arriving the same way.
_ADD_WALL_TIP_PREPARES_FOR = {"a blank name": "empty", "a name already taken": "taken"}


def test_the_add_wall_tips_state_the_refusals_the_service_actually_makes(display):
    """Both refusals driven through the real service, like the delete tip above.

    A model reads the tips, not the docstring, and it reaches this action with a
    name a human said out loud — which is exactly how a duplicate arrives. The
    check runs both ways: the tip must prepare the caller, and the service must
    actually refuse, because a tip promising a refusal nobody makes teaches the
    same wrong lesson.
    """
    action = next(entry for entry in ART_DISPLAY.actions if entry.name == "add_wall")
    tips = " ".join(action.tips).lower()
    for cause, token in _ADD_WALL_TIP_PREPARES_FOR.items():
        assert token in tips, f"the add_wall tip does not prepare a caller for {cause!r}"

    with pytest.raises(ServiceError) as blank:
        display.add_wall(name="   ")
    assert "empty" in str(blank.value)

    display.add_wall(name="Study")
    with pytest.raises(ServiceError) as duplicate:
        display.add_wall(name="Study")
    assert "Study" in str(duplicate.value)


@pytest.mark.parametrize("record", TOOLS, ids=lambda record: record.name)
def test_no_tool_still_teaches_the_single_wall_rule_it_replaced(record):
    """Retiring a rule is a sweep of the sentences that taught it, not a local edit.

    The prose is the contract a model reads, and a retired rule left in it is
    indistinguishable from a live one to the only reader that matters.
    """
    prose = _tool_prose(record)
    surviving = [phrase for phrase in _RETIRED_SINGLE_WALL_PHRASES if phrase in prose]

    assert not surviving, f"{record.name} still teaches the retired single-wall rule: {surviving}"


#: Every action that changes one wall. Written out rather than derived from the
#: parameter lists, because deriving it from what the code declares would make
#: this test agree with any answer the code gave — including an action that
#: quietly stopped naming a wall.
_ACTS_ON_ONE_WALL = {
    ("art_theme", "activate"),
    ("art_theme", "unhang"),
    ("art_display", "sync"),
    ("art_display", "show_now"),
    ("art_display", "next"),
}


@pytest.mark.parametrize(("tool_name", "action_name"), sorted(_ACTS_ON_ONE_WALL))
def test_every_act_against_a_wall_names_which_wall(tool_name, action_name):
    """Required even while there is one wall and the answer is obvious.

    An action that guessed the wall is worse here than on the web surface, where
    a confirmation dialog could at least catch it. The example is asserted too:
    it is what a model copies, and one that omitted the parameter would teach a
    call the schema refuses.
    """
    record = TOOLS_BY_NAME[tool_name]
    action = next(entry for entry in record.actions if entry.name == action_name)

    wall = next((param for param in action.params if param.name == "wall_id"), None)
    assert wall is not None, f"{tool_name}(action={action_name!r}) does not take a wall"
    assert wall.required, f"{tool_name}(action={action_name!r}) makes the wall optional"
    assert "wall_id=" in action.example, f"{tool_name}(action={action_name!r})'s example omits the wall"


def test_the_walls_action_is_where_every_wall_id_comes_from(tools):
    """An action is only usable if its arguments are obtainable from something built.

    Five actions require a `wall_id` and nothing else on the surface returns one,
    so this listing is load-bearing rather than a convenience — and the actions
    that need it say where to get it.
    """
    assert "walls" in tools["art_display"].inputSchema["properties"]["action"]["enum"]

    for tool_name, action_name in sorted(_ACTS_ON_ONE_WALL):
        record = TOOLS_BY_NAME[tool_name]
        action = next(entry for entry in record.actions if entry.name == action_name)
        wall = next(param for param in action.params if param.name == "wall_id")
        pointer = " ".join([wall.description, *action.tips]).lower()
        assert "walls" in pointer, f"{tool_name}(action={action_name!r}) never says where a wall id comes from"


def test_a_parameter_that_is_required_by_some_actions_is_described_neutrally(tools):
    """Every action's parameters are flattened onto one wire schema, and only the
    first description survives.

    `run_id` is required by `status`, `approve`, `decline` and `cancel`, and
    optional to `estimate` and `spend`. A description written for either case is
    published as though it governed both — so one that said "omit this for the
    cost of a new question" would be telling a model that omitting it is
    meaningful on the four actions where it is simply an error. What each action
    does with the parameter belongs in that action's own description and tips.
    """
    published = tools["art_discovery"].inputSchema["properties"]["run_id"]["description"]

    assert "omit" not in published.lower(), f"run_id's published description assumes one action's arity: {published!r}"
    assert "run" in published.lower()


def test_every_facet_kind_the_collection_filters_by_is_a_parameter_of_the_listing(tools):
    """The browser and the tool surface offer the same filters, or one of them lies.

    `GET /api/works` takes one repeatable parameter per facet kind, named from
    `VocabularyKind`; `art_catalogue(action='list')` declares its six by hand,
    because the useful half of each description is an example of that kind's
    *values* and the enum does not carry those. Hand-written means it can drift,
    and a seventh kind reaching the vocabulary and not this tuple would be a
    filter a curator could apply and a model could not — the exact
    agent-and-a-click disagreement the shared service layer exists to prevent.
    """
    published = tools["art_catalogue"].inputSchema["properties"]
    listing = next(action for action in TOOLS_BY_NAME["art_catalogue"].actions if action.name == "list")
    declared = {param.name for param in listing.params}

    for kind in VocabularyKind:
        assert str(kind) in declared, f"art_catalogue(action='list') takes no {kind} filter"
        assert published[str(kind)]["type"] == "array", f"{kind} is not published as a repeatable filter"
        assert published[str(kind)]["items"] == {"type": "string"}
    assert "q" in declared, "the listing offers facets and no free text"
