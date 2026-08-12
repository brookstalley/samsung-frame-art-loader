"""Taste over real HTTP and over the mounted tool surface, and the delete that detaches.

Against a real uvicorn server rather than an in-process transport, per this
suite's standing rule: Starlette does not run a mounted sub-app's lifespan, so an
in-process test would pass against an application whose every MCP request fails.

**The acceptance criteria this file holds** are that the `inferred ⇒
source_turn_id` rule is enforced on the write path *only* — a judgment with a
null citation loads and renders — and that the spend ledger's month total is
provably unchanged by a conversation delete. The second is asserted as the same
number twice, across the delete, through the surface a person would actually read
it from. Reasoning about which rows moved is what a stored `ON DELETE` would
survive.
"""

import json
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest

from curation.discovery.conversation import Suggestion
from curation.persistence.discovery_records import SpendCategory


async def call(server_url: str, tool: str, **arguments) -> tuple[dict, bool]:
    """One MCP tool call over the mounted surface, as an agent would make it."""
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async with streamable_http_client(f"{server_url}/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool, arguments)
    return json.loads(result.content[0].text), bool(result.isError)


@pytest.fixture
def conversation_engine(conversation_engine):
    """The default engine, naming an artist so a turn has something to react to."""
    conversation_engine.suggested = (Suggestion(kind="artist", value="Agnes Martin"),)
    return conversation_engine


def started(server_url: str) -> str:
    response = httpx.post(f"{server_url}/api/conversations", timeout=20)
    response.raise_for_status()
    return response.json()["conversation"]["conversation_id"]


def say(server_url: str, conversation_id: str, text: str) -> dict:
    return httpx.post(f"{server_url}/api/conversations/{conversation_id}/turns", json={"text": text}, timeout=20).json()


def set_taste(server_url: str, **body) -> httpx.Response:
    return httpx.post(f"{server_url}/api/affinities", json=body, timeout=20)


def taste(server_url: str, **params) -> dict:
    return httpx.get(f"{server_url}/api/affinities", params=params, timeout=20).json()


@pytest.fixture
def a_thread(server_url):
    """A conversation that has spent, with an inferred judgment citing its answer."""
    conversation_id = started(server_url)
    view = say(server_url, conversation_id, "Something calm for the living room.")
    answered = view["turns"][-1]["turn_id"]
    written = set_taste(
        server_url,
        kind="artist",
        value="Agnes Martin",
        sentiment="loves",
        open_to_more=True,
        derivation="inferred",
        rationale="they asked for stillness, and said the room is pale",
        source_turn_id=answered,
    )
    written.raise_for_status()
    return conversation_id


# -- the taste routes ---------------------------------------------------------


def test_a_reaction_writes_a_stated_judgment_the_screen_can_read_back(server_url):
    """The write every reaction in a thread makes, at the boundary the client sees."""
    written = set_taste(server_url, kind="artist", value="Kandinsky", sentiment="loves", open_to_more=True)

    assert written.status_code == 200
    assert written.json()["derivation"] == "stated"
    assert written.json()["rationale"] is None
    listed = taste(server_url)
    assert listed["count"] == 1
    assert listed["affinities"][0]["value"] == "Kandinsky"
    assert listed["affinities"][0]["open_to_more"] is True


def test_the_two_fields_hold_meh_but_open_to_more(server_url):
    """Q13's example, written down. One warmth score cannot express it.

    "Tell me more" is `cool` and still open, which a single scalar renders as a
    low number indistinguishable from "never show me this again" — and the
    curator's honest lukewarm reaction would then blacklist an artist they
    explicitly asked to keep hearing about.
    """
    written = set_taste(server_url, kind="artist", value="Magritte", sentiment="cool", open_to_more=True).json()

    assert (written["sentiment"], written["open_to_more"]) == ("cool", True)


def test_setting_observed_over_http_is_refused_in_the_one_error_shape(server_url):
    response = set_taste(
        server_url,
        kind="artist",
        value="Kandinsky",
        sentiment="likes",
        open_to_more=True,
        derivation="observed",
        rationale="accepted four of their works",
    )

    assert response.status_code == 400
    assert "review" in response.json()["error"]


def test_forgetting_a_judgment_answers_with_what_was_forgotten(server_url):
    written = set_taste(server_url, kind="artist", value="Kandinsky", sentiment="declines", open_to_more=False).json()

    forgotten = httpx.delete(f"{server_url}/api/affinities/{written['affinity_id']}", timeout=20)

    assert forgotten.status_code == 200
    assert forgotten.json()["value"] == "Kandinsky"
    assert taste(server_url)["count"] == 0


def test_the_listing_narrows_by_kind(server_url):
    set_taste(server_url, kind="artist", value="Kandinsky", sentiment="loves", open_to_more=True)
    set_taste(server_url, kind="movement", value="Bauhaus", sentiment="declines", open_to_more=False)

    assert [entry["value"] for entry in taste(server_url, kind="artist")["affinities"]] == ["Kandinsky"]


async def test_the_tool_and_the_route_call_the_same_fields_the_same_things(server_url):
    """Parity, over the wire on both sides.

    Two surfaces that name one fact differently is how an agent and a click come
    to disagree about the same taste, and it is invisible to either surface's own
    tests.
    """
    set_taste(server_url, kind="artist", value="Kandinsky", sentiment="loves", open_to_more=True)

    payload, errored = await call(server_url, "art_taste", action="list")

    assert errored is False
    over_http = taste(server_url)["affinities"][0]
    assert payload["affinities"][0] == over_http


async def test_the_tool_refuses_observed_and_says_which_path_can_write_it(server_url):
    payload, errored = await call(
        server_url,
        "art_taste",
        action="set",
        kind="artist",
        value="Kandinsky",
        sentiment="likes",
        open_to_more=True,
        derivation="observed",
        rationale="accepted four of their works",
    )

    assert errored is True
    assert "review" in payload["error"]
    assert taste(server_url)["count"] == 0


# -- the delete that detaches -------------------------------------------------


async def test_the_month_total_is_the_same_number_across_the_delete(server_url, a_thread):
    """**The acceptance criterion, read off the figure somebody actually gets.**

    Through `art_discovery(action='spend')` — the only surface that reports a
    calendar month, and the one Q4 is answered from — rather than by summing the
    store, and asserted as one number against itself rather than reasoned about.
    A ledger whose totals fall because a transcript was tidied is a number that
    lies about the past.
    """
    now = datetime.now(UTC)
    before, _ = await call(server_url, "art_discovery", action="spend", year=now.year, month=now.month)
    assert Decimal(before["cost_usd"]) > 0, "the thread spent nothing, so this would pass against a cascade"

    deleted = httpx.delete(f"{server_url}/api/conversations/{a_thread}", timeout=20)
    assert deleted.status_code == 200

    after, _ = await call(server_url, "art_discovery", action="spend", year=now.year, month=now.month)
    assert Decimal(after["cost_usd"]) == Decimal(before["cost_usd"])


def test_the_judgment_stands_with_a_null_citation_and_still_renders(server_url, a_thread, services):
    """**The other acceptance criterion: the rule is on the write path only.**

    The count is asserted before the fields, because an assertion over a possibly
    empty list is vacuously true — and `all(a["source_turn_id"] is None …)` over
    an empty list is exactly what a cascade would produce.

    "Still renders" is asserted as the row coming back through the read the
    screen makes, with everything the screen draws present on it: a stored
    constraint would have refused the delete, and a read-side guard would have
    dropped the row here.
    """
    httpx.delete(f"{server_url}/api/conversations/{a_thread}", timeout=20).raise_for_status()

    listed = taste(server_url)
    assert listed["count"] == 1
    (standing,) = listed["affinities"]
    assert standing["source_turn_id"] is None
    assert standing["conversation_id"] is None
    # Not softened to `stated`, which would be the product claiming the curator
    # said something they never said.
    assert standing["derivation"] == "inferred"
    assert standing["rationale"] == "they asked for stillness, and said the room is pale"
    assert standing["sentiment"] == "loves"
    assert standing["open_to_more"] is True


def test_the_ledger_rows_keep_their_amounts_and_lose_only_the_citation(server_url, a_thread, services):
    """The rows behind the total, so a passing total cannot hide a rewrite."""
    store = services.discovery._store
    before = [(record.id, record.cost_usd, record.category) for record in store.list_spend_records()]
    assert before, "no spend was recorded, so this would pass against a cascade"

    httpx.delete(f"{server_url}/api/conversations/{a_thread}", timeout=20).raise_for_status()

    after = store.list_spend_records()
    assert [(record.id, record.cost_usd, record.category) for record in after] == before
    assert [record.conversation_turn_id for record in after] == [None] * len(after)
    assert after[0].category is SpendCategory.CONVERSATION_TOKENS


def test_the_response_names_the_consequence_rather_than_a_row_count(server_url, a_thread):
    """The IA's confirmation rule, at the boundary the dialog is written from.

    The counts are carried so a surface can qualify the sentence; the sentence is
    what a curator is asked to agree to, and it is about what they can no longer
    do rather than about how many rows moved.
    """
    body = httpx.delete(f"{server_url}/api/conversations/{a_thread}", timeout=20).json()

    assert body["conversation_id"] == a_thread
    assert body["affinities_detached"] == 1
    assert body["spend_records_detached"] == 1
    assert body["turns_deleted"] == 2
    assert "rebuilt" in body["description"]
    assert "no month total changes" in body["description"]


def test_the_thread_is_gone_and_the_list_no_longer_carries_it(server_url, a_thread):
    httpx.delete(f"{server_url}/api/conversations/{a_thread}", timeout=20).raise_for_status()

    assert httpx.get(f"{server_url}/api/conversations/{a_thread}", timeout=20).status_code == 400
    assert httpx.get(f"{server_url}/api/conversations", timeout=20).json()["count"] == 0


def test_deleting_an_unknown_conversation_is_refused_in_the_one_error_shape(server_url):
    response = httpx.delete(f"{server_url}/api/conversations/not-a-conversation", timeout=20)

    assert response.status_code == 400
    assert "No conversation with id" in response.json()["error"]
