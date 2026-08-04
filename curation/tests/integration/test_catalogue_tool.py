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


# -- provenance and the acquisition actions, over the wire ---------------------


def _a_work_with_sources(services):
    """A catalogued work with two sources, one of them primary and fetched.

    Built through the service the surface itself uses, so the test's setup cannot
    disagree with what the catalogue would hold in production.
    """
    from curation.persistence.records import AcquisitionMethod, FetchStatus, RightsStatus, SourceClass

    catalogue = services.catalogue
    work = catalogue.add_artwork(title="Fog Horn")
    primary = catalogue.add_source(
        artwork_id=work.id,
        url="https://www.artic.edu/iiif/2/abc/info.json",
        provider="artic",
        source_class=SourceClass.INSTITUTIONAL,
        acquisition_method=AcquisitionMethod.DEZOOMIFY,
        rights_status=RightsStatus.PUBLIC_DOMAIN,
        is_primary=True,
        confidence=0.94,
        selection_rationale="the only scan at gallery resolution",
    )
    catalogue.add_source(
        artwork_id=work.id,
        url="https://gallery.example.com/fog-horn.jpg",
        provider="gallery_site",
        source_class=SourceClass.CONTEMPORARY_WEB,
        acquisition_method=AcquisitionMethod.DIRECT_HTTP,
        rights_status=RightsStatus.UNKNOWN,
    )
    # A partial fetch, because it is the outcome most easily mistaken for an
    # error and the one a caller most needs to read back.
    catalogue.record_fetch(primary.id, status=FetchStatus.PARTIAL_TILES)
    return work, primary


async def test_an_mcp_caller_can_read_where_a_work_came_from(server_url, services):
    work, primary = _a_work_with_sources(services)

    payload, errored = await call(server_url, "art_catalogue", action="sources", artwork_id=work.id)

    assert errored is False
    assert payload["success"] is True
    assert payload["artwork_id"] == work.id
    assert payload["count"] == 2
    by_id = {source["source_id"]: source for source in payload["sources"]}
    held = by_id[primary.id]
    assert held["url"] == "https://www.artic.edu/iiif/2/abc/info.json"
    assert held["provider"] == "artic"
    assert held["source_class"] == "institutional"
    assert held["acquisition_method"] == "dezoomify"
    assert held["rights_status"] == "public_domain"
    assert held["is_primary"] is True
    assert held["confidence"] == 0.94
    assert held["selection_rationale"] == "the only scan at gallery resolution"
    # The outcome the data model calls normal, surviving all the way out.
    assert held["last_fetch_status"] == "partial_tiles"
    assert held["last_fetched_at"] is not None


async def test_the_other_source_is_listed_and_is_not_primary(server_url, services):
    work, _ = _a_work_with_sources(services)

    payload, _errored = await call(server_url, "art_catalogue", action="sources", artwork_id=work.id)

    alternates = [source for source in payload["sources"] if not source["is_primary"]]
    assert [source["provider"] for source in alternates] == ["gallery_site"]
    # Never fetched, which is a different fact from "fetched and failed".
    assert alternates[0]["last_fetch_status"] is None


async def test_a_work_with_no_source_says_so_rather_than_returning_a_bare_empty_list(server_url, services):
    work = services.catalogue.add_artwork(title="Untraceable")

    payload, errored = await call(server_url, "art_catalogue", action="sources", artwork_id=work.id)

    assert errored is False
    assert payload["sources"] == []
    assert "nothing to re-acquire it from" in payload["notice"]


async def test_sources_for_an_unknown_work_is_an_error_result(server_url):
    payload, errored = await call(server_url, "art_catalogue", action="sources", artwork_id="not-a-work")

    assert errored is True
    assert payload["success"] is False


async def test_archiving_and_restoring_round_trips_over_the_wire(server_url, services):
    work, _ = _a_work_with_sources(services)

    archived, errored = await call(server_url, "art_catalogue", action="archive", artwork_id=work.id)
    assert errored is False
    assert archived["artwork"]["status"] == "archived"
    assert "Nothing is deleted" in archived["notice"]

    listed, _ = await call(server_url, "art_catalogue", action="list", status="archived")
    assert work.id in {entry["artwork_id"] for entry in listed["artworks"]}

    restored, errored = await call(server_url, "art_catalogue", action="restore", artwork_id=work.id)
    assert errored is False
    assert restored["artwork"]["status"] == "accepted"


async def test_archiving_an_archived_work_is_an_error_result_that_says_why(server_url, services):
    work, _ = _a_work_with_sources(services)
    await call(server_url, "art_catalogue", action="archive", artwork_id=work.id)

    payload, errored = await call(server_url, "art_catalogue", action="archive", artwork_id=work.id)

    assert errored is True
    assert "already archived" in payload["error"]


async def test_retry_acquisition_reaches_the_service_and_reports_its_outcome(server_url, services):
    # This deployment wires no HTTP transport, so the fetch cannot succeed — and
    # that is the point: the action is exercised end to end and its failure is a
    # structured outcome rather than a crash, which is what the surface promises.
    work, _ = _a_work_with_sources(services)
    direct = next(s for s in services.catalogue.list_sources(work.id) if not s.is_primary)

    payload, errored = await call(
        server_url, "art_catalogue", action="retry_acquisition", artwork_id=work.id, source_id=direct.id
    )

    assert errored is False
    assert payload["success"] is True
    assert payload["artwork_id"] == work.id
    assert payload["source_id"] == direct.id
    assert payload["outcome"] == "failed"
    assert "replaces nothing" in payload["notice"]


async def test_a_failed_retry_is_readable_afterwards_through_sources(server_url, services):
    # The multi-hop half: the outcome of one action has to be visible to the read
    # that a curator would use to decide what to do next.
    work, _ = _a_work_with_sources(services)
    direct = next(s for s in services.catalogue.list_sources(work.id) if not s.is_primary)
    await call(server_url, "art_catalogue", action="retry_acquisition", artwork_id=work.id, source_id=direct.id)

    payload, _ = await call(server_url, "art_catalogue", action="sources", artwork_id=work.id)

    after = {source["source_id"]: source for source in payload["sources"]}[direct.id]
    assert after["last_fetch_status"] == "failed"
    assert after["last_fetched_at"] is not None


async def test_retry_acquisition_on_a_work_with_no_source_is_an_error_result(server_url, services):
    work = services.catalogue.add_artwork(title="Untraceable")

    payload, errored = await call(server_url, "art_catalogue", action="retry_acquisition", artwork_id=work.id)

    assert errored is True
    assert "no source" in payload["error"]


async def test_a_missing_tile_binary_reaches_the_caller_with_its_remedy(server_url, services, monkeypatch):
    # The two conditions acquisition raises for rather than records are the two no
    # source is at fault in. A caller told only "failed unexpectedly" would go and
    # look at the museum, so each names what actually fixes it.
    from dataclasses import replace

    work, primary = _a_work_with_sources(services)
    monkeypatch.setattr(
        services.acquisition,
        "_settings",
        replace(services.acquisition._settings, tile_binary="/nonexistent/dezoomify-rs"),
    )

    payload, errored = await call(
        server_url, "art_catalogue", action="retry_acquisition", artwork_id=work.id, source_id=primary.id
    )

    assert errored is True
    assert "deployment problem" in payload["error"]
    assert "DEZOOMIFY_PATH" in payload["error"]


async def test_a_full_disk_reaches_the_caller_with_its_remedy(server_url, services, monkeypatch):
    from dataclasses import replace

    work, primary = _a_work_with_sources(services)
    monkeypatch.setattr(
        services.acquisition,
        "_settings",
        replace(services.acquisition._settings, min_free_bytes=2**62),
    )

    payload, errored = await call(
        server_url, "art_catalogue", action="retry_acquisition", artwork_id=work.id, source_id=primary.id
    )

    assert errored is True
    assert "did not start" in payload["error"]
    assert "MIN_FREE_BYTES" in payload["error"]
