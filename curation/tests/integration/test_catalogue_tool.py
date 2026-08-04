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
    assert (payload["limit"], payload["offset"]) == (1, 0)
    assert (
        payload["notice"] == "showing 1-1 of 3 at limit 1; raise limit or page with offset, or narrow with status to see the rest"
    )


async def test_paging_with_offset_works_through_the_tool_and_the_page_says_where_it_is(server_url):
    """The one hop the notice steers a model into, exercised end to end.

    Asserting the echoed `offset` at zero proves nothing: zero is also the
    binding's default, so that assertion holds even if the argument were dropped
    on the floor. This passes a non-zero one through the real surface and checks
    it comes back — and that the page reports a different position than the first,
    which is the whole reason it reports one.
    """
    payload, _ = await call(server_url, "art_catalogue", action="list", limit=1, offset=1)

    assert (payload["limit"], payload["offset"]) == (1, 1)
    assert payload["truncated"] is True
    assert payload["count"] == 1
    assert payload["notice"].startswith("showing 2-2 of 3")
    # A different work from the one the first page held, so the offset reached the
    # query rather than only the payload.
    first_page, _ = await call(server_url, "art_catalogue", action="list", limit=1)
    assert payload["artworks"][0]["artwork_id"] != first_page["artworks"][0]["artwork_id"]


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
    assert {action["action"] for action in payload["actions"]} == {
        "list",
        "get",
        "sources",
        "archive",
        "restore",
        "retry_acquisition",
        "help",
    }


async def test_help_reports_exactly_the_actions_a_tool_actually_serves(server_url):
    # The rule that made a build-status column unnecessary: `help` answers the
    # as-built question, so a model reading the menu cannot be steered at
    # something that does not exist. Asserted here as an ordered list against a
    # tool that grew in two stages — the reads first, the writes after — because
    # what an incomplete surface looked like was exactly this, minus the last
    # three, and nothing in a payload distinguishes "not built" from "not
    # listed". `_check_bindings_match_registry` is the structural half at import;
    # this is the half a client can see.
    payload, errored = await call(server_url, "art_review", action="help")

    assert errored is False
    assert payload["available"] is True
    assert [action["action"] for action in payload["actions"]] == [
        "list_works",
        "get_work",
        "list_images",
        "set_canonical",
        "set_verdict",
        "reject_image",
        "help",
    ]


# -- errors teach, and they arrive as tool results ----------------------------


async def test_an_unknown_action_is_an_error_result_that_enumerates_the_valid_set(server_url):
    payload, errored = await call(server_url, "art_catalogue", action="lst")

    # A known tool failing is information the model can act on, so it comes
    # back as a tool result with isError set — not a protocol error.
    assert errored is True
    assert payload["success"] is False
    assert payload["error"] == "Unknown action: 'lst'"
    assert payload["valid_actions"] == [
        "list",
        "get",
        "sources",
        "archive",
        "restore",
        "retry_acquisition",
        "help",
    ]
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


async def test_an_action_a_tool_does_not_serve_is_refused_with_the_set_it_does(server_url):
    # An action that exists in the designed surface but has not been built is
    # indistinguishable, to a caller, from one that never will be — and both
    # deserve the same answer: here is what this tool actually takes. Written as
    # an invariant over the advertised set rather than against a hardcoded list,
    # so building the rest of `art_review` moves the assertion with the surface
    # instead of failing it.
    advertised, _ = await call(server_url, "art_review", action="help")
    served = [action["action"] for action in advertised["actions"]]

    payload, errored = await call(server_url, "art_review", action="no_such_action")

    assert errored is True
    assert payload["error"] == "Unknown action: 'no_such_action'"
    assert payload["valid_actions"] == served


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
