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

from curation.persistence.records import FetchStatus


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
        "set_mat_color",
        "regenerate",
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
        "set_mat_color",
        "regenerate",
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


async def test_an_unresolvable_provider_reaches_the_caller_with_its_remedy(server_url, services, monkeypatch):
    """The third raise-rather-record condition, and the reachable one.

    A catalogue holding Art Institute works with no ARTIC_USER_AGENT configured
    is an ordinary deployment, not a contrived one — it is what every seeded
    install starts as. Without this arm the refusal arrives through the generic
    handler as "failed unexpectedly", which is the outcome its two siblings above
    are translated to prevent, and the operational runbook promises a named one.
    """
    work, primary = _a_work_with_sources(services)
    # Exactly what the container builds when no image provider is configured.
    monkeypatch.setattr(services.acquisition, "_tile_targets", {})
    # Stated rather than looked up: a rule about wiring is not a rule about DNS.
    monkeypatch.setattr(services.acquisition, "_resolve", lambda _host: ["93.184.216.34"])

    payload, errored = await call(
        server_url, "art_catalogue", action="retry_acquisition", artwork_id=work.id, source_id=primary.id
    )

    assert errored is True
    assert "ARTIC_USER_AGENT" in payload["error"]
    # The remedy has to say the sources are fine, or its reader goes to the museum.
    assert "no source is at fault" in payload["error"]


async def test_an_unresolvable_provider_records_nothing_against_the_source(server_url, services, monkeypatch):
    """A wiring fault must leave no `failed` row on a source that is perfectly good."""
    work, primary = _a_work_with_sources(services)
    monkeypatch.setattr(services.acquisition, "_tile_targets", {})
    monkeypatch.setattr(services.acquisition, "_resolve", lambda _host: ["93.184.216.34"])

    await call(server_url, "art_catalogue", action="retry_acquisition", artwork_id=work.id, source_id=primary.id)

    refreshed = next(s for s in services.catalogue.list_sources(work.id) if s.id == primary.id)
    # Pinned to the value the fixture recorded, not merely "not FAILED" — which
    # would pass however the status moved.
    assert refreshed.last_fetch_status is FetchStatus.PARTIAL_TILES


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


def _a_work_with_an_original(services, settings, *, width=2400, height=1800):
    """A catalogued work holding real bytes, ready to be prepared.

    Real bytes because the mat engine and the compositor both decode them; a
    stand-in would make every assertion below depend on Pillow never being asked
    to open the file.
    """
    from PIL import Image

    from curation.persistence.records import AcquisitionMethod, RightsStatus, SourceClass

    catalogue = services.catalogue
    work = catalogue.add_artwork(title="Sky above Clouds")
    source = catalogue.add_source(
        artwork_id=work.id,
        url="https://gallery.example.com/sky.jpg",
        provider="gallery_site",
        source_class=SourceClass.CONTEMPORARY_WEB,
        acquisition_method=AcquisitionMethod.DIRECT_HTTP,
        rights_status=RightsStatus.UNKNOWN,
        is_primary=True,
    )
    originals = settings.art_root / "raw"
    originals.mkdir(parents=True, exist_ok=True)
    path = originals / f"{work.id}.jpg"
    Image.new("RGB", (width, height), (30, 60, 120)).save(path, format="JPEG", quality=90)
    catalogue.record_original(
        artwork_id=work.id,
        source_id=source.id,
        path=str(path.relative_to(settings.art_root)),
        width=width,
        height=height,
        byte_size=path.stat().st_size,
        content_hash="hash-one",
        fetch_status=FetchStatus.OK,
    )
    return work


async def test_set_mat_color_records_a_curators_colour_and_re_renders(server_url, services, settings):
    work = _a_work_with_an_original(services, settings)

    payload, errored = await call(server_url, "art_catalogue", action="set_mat_color", artwork_id=work.id, hex_rgb="#27285b")

    assert errored is False
    assert payload["success"] is True
    assert payload["hex_rgb"] == "#27285b"
    assert payload["method"] == "manual"
    assert (settings.art_root / payload["relative_path"]).is_file()


async def test_omitting_the_colour_asks_the_producer_and_says_which_one_answered(server_url, services, settings):
    # This deployment wires no model client, which is the keyless deployment
    # exactly — so the mechanical producer answers, and the notice is the only
    # thing that says the model did not. That silence is what the 2024 pipeline
    # shipped and what `method` exists to end.
    work = _a_work_with_an_original(services, settings)

    payload, errored = await call(server_url, "art_catalogue", action="set_mat_color", artwork_id=work.id)

    assert errored is False
    assert payload["method"] == "dominant_color_fallback"
    assert "did not choose this colour" in payload["notice"]


async def test_a_curators_colour_carries_no_fallback_notice(server_url, services, settings):
    work = _a_work_with_an_original(services, settings)

    payload, _ = await call(server_url, "art_catalogue", action="set_mat_color", artwork_id=work.id, hex_rgb="#6b6b6b")

    assert payload["notice"] is None


async def test_an_unreadable_colour_is_an_error_result_rather_than_a_crash(server_url, services, settings):
    """The refusal has to survive the trip as a *result*, not an exception.

    The assertions moved from the message's wording to what a caller can act on,
    because the wording changed for a reason worth keeping: a curator's spelling
    is now read by the same lenient parser the model's answer goes through, so
    `#abc` is accepted from both rather than from the model alone, and the refusal
    that reaches here is that parser's. Its message is the better one — it quotes
    the value back and shows a well-formed example — and pinning the old substring
    would pin the surface to the parser that no longer runs.
    """
    work = _a_work_with_an_original(services, settings)

    payload, errored = await call(server_url, "art_catalogue", action="set_mat_color", artwork_id=work.id, hex_rgb="octarine")

    assert errored is True
    assert payload["success"] is False
    # Names the value that was wrong, and shows what a right one looks like.
    assert "octarine" in payload["error"]
    assert "#27285b" in payload["error"]


async def test_a_colour_a_person_spells_loosely_is_accepted_like_the_models_own(server_url, services, settings):
    """The other half of joining the two readers, asserted over the wire.

    Before this the product took `#ABC` from a vision model and refused it from a
    curator, on a parameter documented only as "a hex triplet".
    """
    work = _a_work_with_an_original(services, settings)

    payload, errored = await call(server_url, "art_catalogue", action="set_mat_color", artwork_id=work.id, hex_rgb="#ABC")

    assert errored is False
    assert payload["success"] is True
    # Normalised to the one spelling the catalogue compares by, so re-choosing the
    # colour already in force still reads as no change rather than as history.
    assert payload["hex_rgb"] == "#aabbcc"


async def test_regenerate_composes_the_canvas_and_reports_where_it_went(server_url, services, settings):
    work = _a_work_with_an_original(services, settings)

    payload, errored = await call(server_url, "art_catalogue", action="regenerate", artwork_id=work.id)

    assert errored is False
    assert payload["outcome"] == "prepared"
    assert payload["fit"] == "native"
    assert (settings.art_root / payload["relative_path"]).is_file()


async def test_regenerating_a_current_canvas_reports_unchanged_rather_than_redoing_it(server_url, services, settings):
    # The multi-hop half: the second call's answer depends on what the first one
    # left behind, which is the whole of what "already current" means.
    work = _a_work_with_an_original(services, settings)
    await call(server_url, "art_catalogue", action="regenerate", artwork_id=work.id)

    payload, errored = await call(server_url, "art_catalogue", action="regenerate", artwork_id=work.id)

    assert errored is False
    assert payload["outcome"] == "unchanged"
    # No fresh assessment to report, and repeating a stored one would answer a
    # question this call did not ask.
    assert payload["fit"] is None


async def test_force_re_renders_a_canvas_that_is_already_current(server_url, services, settings):
    work = _a_work_with_an_original(services, settings)
    await call(server_url, "art_catalogue", action="regenerate", artwork_id=work.id)

    payload, _ = await call(server_url, "art_catalogue", action="regenerate", artwork_id=work.id, force=True)

    assert payload["outcome"] == "prepared"


async def test_a_work_rendered_below_the_floor_says_so_without_refusing(server_url, services, settings):
    # Not a refusal: the curator may have chosen this instance knowing it was
    # small, and the requirement is explicit that such a work is rendered rather
    # than hidden. But a canvas reported as composed with no mention of it would
    # let a work quietly appear as a postage stamp in an enormous mat.
    work = _a_work_with_an_original(services, settings, width=400, height=300)

    payload, errored = await call(server_url, "art_catalogue", action="regenerate", artwork_id=work.id)

    assert errored is False
    assert payload["outcome"] == "prepared"
    assert payload["fit"] == "below_floor"
    assert "below the configured floor" in payload["notice"]
    assert (settings.art_root / payload["relative_path"]).is_file()


async def test_regenerating_a_work_with_no_original_is_an_error_result_naming_the_remedy(server_url, services):
    work = services.catalogue.add_artwork(title="Unacquired")

    payload, errored = await call(server_url, "art_catalogue", action="regenerate", artwork_id=work.id)

    assert errored is True
    assert "acquire it first" in payload["error"]


async def test_a_prepared_work_enters_the_manifest(server_url, services, settings):
    # The acceptance criterion, end to end: an acquired work renders to 4K and
    # enters the manifest. The manifest excludes a work with no rendition, so
    # this is the one check that the two halves actually meet.
    work = _a_work_with_an_original(services, settings)
    theme = services.display.add_theme(name="Everything")
    services.display.add_to_theme(theme_id=theme.id, artwork_id=work.id)
    services.display.activate_theme(theme.id)

    # Excluded before it is rendered, which is what makes the assertion after it
    # mean something: the work is in the theme throughout, so the only thing that
    # changes between these two builds is the canvas.
    before = services.display.build_manifest()
    assert work.id in {excluded.work_id for excluded in before.exclusions}

    payload, errored = await call(server_url, "art_catalogue", action="regenerate", artwork_id=work.id)
    build = services.display.build_manifest()

    assert errored is False
    assert work.id in {entry.work_id for entry in build.entries}
    assert work.id not in {excluded.work_id for excluded in build.exclusions}
    assert payload["relative_path"] in {entry.render_path for entry in build.entries}


async def test_regenerate_reports_what_it_spent_even_when_that_is_nothing(server_url, services, settings):
    """**The claim the surface now publishes**: "every answer reports cost_usd".
    A field present only on the paying path is indistinguishable from one nobody
    emitted, so the zero has to be there too — and this deployment wires no model
    client, which is exactly the path that spends nothing."""
    work = _a_work_with_an_original(services, settings)

    payload, errored = await call(server_url, "art_catalogue", action="regenerate", artwork_id=work.id)

    assert errored is False
    assert payload["cost_usd"] == "0"


async def test_regenerate_says_when_it_chose_the_mat_mechanically(server_url, services, settings):
    """A work's mat is usually chosen on the `regenerate` that follows acquisition,
    not on `set_mat_color` — `acquire` does not prepare. So the notice that says
    the vision model did not choose has to appear on this action too, or the
    silent-fallback failure `MatColor.method` exists to end comes back on the
    action most works actually go through."""
    work = _a_work_with_an_original(services, settings)

    payload, _ = await call(server_url, "art_catalogue", action="regenerate", artwork_id=work.id)

    assert payload["method"] == "dominant_color_fallback"
    assert "not by the vision model" in payload["notice"]


async def test_a_second_regenerate_carries_no_fallback_notice(server_url, services, settings):
    """The discriminating half. Without it the assertion above would pass on a
    notice that was always present, and the below-floor test's substring match
    would accept the fallback sentence silently prepended or silently gone."""
    work = _a_work_with_an_original(services, settings)
    await call(server_url, "art_catalogue", action="regenerate", artwork_id=work.id)

    payload, _ = await call(server_url, "art_catalogue", action="regenerate", artwork_id=work.id)

    assert payload["outcome"] == "unchanged"
    assert payload["notice"] is None


async def test_the_below_floor_notice_stands_alone_once_a_mat_is_already_chosen(server_url, services, settings):
    """Pins which sentences a below-floor answer carries, rather than asserting a
    substring that a second sentence could appear beside unnoticed."""
    work = _a_work_with_an_original(services, settings, width=400, height=300)
    await call(server_url, "art_catalogue", action="regenerate", artwork_id=work.id)

    payload, _ = await call(server_url, "art_catalogue", action="regenerate", artwork_id=work.id, force=True)

    assert payload["fit"] == "below_floor"
    assert "not by the vision model" not in payload["notice"]
    assert payload["notice"].startswith("This work renders at about")


async def test_set_mat_color_reports_its_cost_too(server_url, services, settings):
    work = _a_work_with_an_original(services, settings)

    payload, _ = await call(server_url, "art_catalogue", action="set_mat_color", artwork_id=work.id, hex_rgb="#27285b")

    assert payload["cost_usd"] == "0"


async def test_a_first_regenerate_of_a_below_floor_work_carries_both_sentences(server_url, services, settings):
    """**The state the join exists for, and the only one that needed it.** A work
    that is both below the floor and having its mat chosen for the first time
    produces two notices, and `_regenerate_notice` joins them. Asserted together
    because either sentence alone passes the two tests beside this one — which is
    how a join can be written, shipped, and never exercised."""
    work = _a_work_with_an_original(services, settings, width=400, height=300)

    payload, errored = await call(server_url, "art_catalogue", action="regenerate", artwork_id=work.id)

    assert errored is False
    assert payload["fit"] == "below_floor"
    assert "not by the vision model" in payload["notice"]
    assert "below the configured floor" in payload["notice"]
    # In that order: what happened to the mat, then what it means for the wall.
    assert payload["notice"].index("not by the vision model") < payload["notice"].index("below the configured floor")
    # And separated, which asserting each sentence and their order does not
    # cover: without the join's space the two run together mid-word, and every
    # other assertion here passes on the result.
    assert " This work renders at about" in payload["notice"]


async def test_an_unchanged_regenerate_reports_a_cost_too(server_url, services, settings):
    """The `unchanged` branch returns its own payload, so "every answer reports
    cost_usd" is two claims rather than one — and only the `prepared` half was
    asserted."""
    work = _a_work_with_an_original(services, settings)
    await call(server_url, "art_catalogue", action="regenerate", artwork_id=work.id)

    payload, _ = await call(server_url, "art_catalogue", action="regenerate", artwork_id=work.id)

    assert payload["outcome"] == "unchanged"
    assert payload["cost_usd"] == "0"
