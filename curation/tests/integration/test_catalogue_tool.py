"""A real MCP client calling the catalogue tool against a seeded catalogue.

The whole slice runs here: client → HTTP → mounted MCP server → registry
dispatch → binding → service → SQLite, and back.

Each call opens its own session on purpose. It keeps the client's task group
entered and exited in one task — the alternative, a long-lived session held
open by a fixture, tears down in a different task and trips anyio's cancel
scope — and it exercises the server's session handling once per assertion
rather than once per module.
"""

import json

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def call(server_url: str, tool: str, **arguments) -> tuple[dict, bool]:
    """Call a tool over real HTTP; return its payload and the protocol's error flag."""
    async with streamable_http_client(f"{server_url}/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool, arguments)
    return json.loads(result.content[0].text), bool(result.isError)


async def test_listing_returns_the_seeded_works(server_url, seeded_titles):
    payload, errored = await call(server_url, "art_catalogue", action="list")

    assert errored is False
    assert payload["success"] is True
    assert {work["title"] for work in payload["artworks"]} == set(seeded_titles)
    assert payload["total"] == 3


async def test_a_listing_carries_the_artist_a_curator_judges_by(server_url):
    payload, _ = await call(server_url, "art_catalogue", action="list")
    by_title = {work["title"]: work for work in payload["artworks"]}

    assert by_title["The Persistence of Memory"]["artist"] == "Salvador Dalí"
    assert by_title["Nighthawks"]["artist"] is None


async def test_a_truncated_listing_says_so_and_gives_the_total(server_url):
    payload, _ = await call(server_url, "art_catalogue", action="list", limit=1)

    assert payload["truncated"] is True
    assert payload["total"] == 3
    assert payload["notice"] == "showing 1 of 3 at limit 1; raise limit or narrow with status to see the rest"


async def test_a_complete_listing_carries_no_truncation_notice(server_url):
    payload, _ = await call(server_url, "art_catalogue", action="list")

    assert payload["truncated"] is False
    assert payload["notice"] is None


async def test_getting_a_work_returns_the_full_record_with_its_artist(server_url, seeded_titles):
    listed, _ = await call(server_url, "art_catalogue", action="list")
    demuth = next(work for work in listed["artworks"] if work["title"] == seeded_titles[0])

    payload, errored = await call(server_url, "art_catalogue", action="get", artwork_id=demuth["artwork_id"])

    assert errored is False
    artwork = payload["artwork"]
    assert artwork["title"] == seeded_titles[0]
    assert artwork["date_created"] == "1928"
    assert artwork["medium"] == "Oil, graphite, ink and gold leaf on paperboard"
    assert artwork["artist"]["name"] == "Charles Demuth"
    assert artwork["artist"]["born"] == 1883


async def test_help_works_without_arguments_and_without_the_catalogue(server_url):
    payload, errored = await call(server_url, "art_catalogue", action="help")

    assert errored is False
    assert {action["action"] for action in payload["actions"]} == {"list", "get", "help"}


async def test_help_is_available_on_a_tool_whose_actions_are_not_built(server_url):
    payload, errored = await call(server_url, "art_theme", action="help")

    assert errored is False
    assert payload["available"] is False
    assert [action["action"] for action in payload["actions"]] == ["help"]


# -- errors teach, and they arrive as tool results ----------------------------


async def test_an_unknown_action_is_an_error_result_that_enumerates_the_valid_set(server_url):
    payload, errored = await call(server_url, "art_catalogue", action="lst")

    # A known tool failing is information the model can act on, so it comes
    # back as a tool result with isError set — not a protocol error.
    assert errored is True
    assert payload["success"] is False
    assert payload["error"] == "Unknown action: 'lst'"
    assert payload["valid_actions"] == ["list", "get", "help"]
    assert payload["example"] == "art_catalogue(action='help')"
    assert payload["hint"].startswith("Use art_catalogue(action='help')")


async def test_the_error_flag_is_derived_from_the_payload_not_set_beside_it(server_url):
    ok_payload, ok_errored = await call(server_url, "art_catalogue", action="list")
    bad_payload, bad_errored = await call(server_url, "art_catalogue", action="lst")

    assert (ok_payload["success"], ok_errored) == (True, False)
    assert (bad_payload["success"], bad_errored) == (False, True)


async def test_a_missing_required_parameter_names_it_and_shows_a_correct_call(server_url):
    payload, errored = await call(server_url, "art_catalogue", action="get")

    assert errored is True
    assert "requires 'artwork_id'" in payload["error"]
    assert payload["required_parameters"] == ["artwork_id"]
    assert payload["example"].startswith("art_catalogue(action='get'")


async def test_an_invalid_status_reports_the_values_that_would_work(server_url):
    payload, errored = await call(server_url, "art_catalogue", action="list", status="archive")

    assert errored is True
    assert payload["valid_values"] == {"status": ["accepted", "archived"]}


async def test_a_limit_beyond_the_cap_reports_the_bounds(server_url):
    payload, errored = await call(server_url, "art_catalogue", action="list", limit=500)

    assert errored is True
    assert payload["parameter_range"] == {"limit": {"minimum": 1, "maximum": 100}}


async def test_an_unknown_work_is_reported_as_a_failure_never_an_empty_success(server_url):
    payload, errored = await call(server_url, "art_catalogue", action="get", artwork_id="does-not-exist")

    assert errored is True
    assert payload["success"] is False
    assert "does-not-exist" in payload["error"]


async def test_an_unbuilt_tool_refuses_its_action_and_says_what_it_does_answer(server_url):
    payload, errored = await call(server_url, "art_theme", action="create")

    assert errored is True
    assert "not available yet" in payload["error"]
    assert payload["valid_actions"] == ["help"]


async def test_an_unknown_tool_is_reported_with_the_names_that_do_exist(server_url):
    payload, errored = await call(server_url, "art_catalog", action="list")

    assert errored is True
    assert payload["error"] == "Unknown tool: 'art_catalog'"
    assert set(payload["valid_tools"]) == {
        "art_catalogue",
        "art_discovery",
        "art_display",
        "art_review",
        "art_theme",
    }
    # The hint must name something callable. This is the one error raised
    # before any tool is identified, so the default pointer would name the
    # server — and a model following it makes a second unknown-tool call.
    assert "samsung-frame-art-loader" not in payload["hint"]
    assert "valid_tools" in payload["hint"]
