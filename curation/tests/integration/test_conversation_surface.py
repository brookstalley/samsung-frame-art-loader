"""Intent-forming over real HTTP, and the seam onto a real threaded run.

Against a real uvicorn server rather than an in-process transport, per the
suite's standing rule: Starlette does not run a mounted sub-app's lifespan, and
an in-process test would pass against an application that fails every MCP
request in production.

**The acceptance criteria this file holds** are that committing a direction
answers with the conversation rather than the run — the shape that lets the
client transform its card in place instead of navigating — and that what a
conversation spent turns up in the month total. The rest pin the pieces it would
be easy to break without failing either.
"""

from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
from fakes import a_collection_holding

from curation.discovery.conversation import ConversationFailure, Suggestion
from curation.persistence.discovery_records import InitiatedBy, RunStatus, SpendCategory


async def call(server_url: str, tool: str, **arguments) -> tuple[dict, bool]:
    """One MCP tool call over the mounted surface, as an agent would make it."""
    import json

    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async with streamable_http_client(f"{server_url}/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool, arguments)
    return json.loads(result.content[0].text), bool(result.isError)


@pytest.fixture
def conversation_engine(conversation_engine):
    """The default engine, naming an artist so a turn has something to offer."""
    conversation_engine.suggested = (Suggestion(kind="artist", value="Agnes Martin"),)
    return conversation_engine


def started(server_url: str) -> str:
    response = httpx.post(f"{server_url}/api/conversations", timeout=20)
    response.raise_for_status()
    return response.json()["conversation"]["conversation_id"]


def say(server_url: str, conversation_id: str, text: str | None = None) -> dict:
    response = httpx.post(
        f"{server_url}/api/conversations/{conversation_id}/turns",
        json={} if text is None else {"text": text},
        timeout=20,
    )
    return response.json() | {"_status": response.status_code}


def test_a_turn_answers_with_the_thread_and_what_it_named(server_url):
    conversation_id = started(server_url)

    view = say(server_url, conversation_id, "Something calm for the living room.")

    assert view["_status"] == 200
    assert [turn["role"] for turn in view["turns"]] == ["curator", "system"]
    assert view["turns"][1]["suggested"][0] == {"kind": "artist", "value": "Agnes Martin", "samples": []}
    assert view["failure"] is None
    assert view["unanswered_turn_id"] is None


def test_a_turn_shows_the_pictures_the_collection_holds(
    store, discovery_store, wall_settings, thumbnail_settings, settings, engine, conversation_engine
):
    """Samples are the free museum browse, not a second paid lookup."""
    from curation.services.container import Services

    services = Services.bind(
        catalogue=store,
        discovery=discovery_store,
        display_settings=wall_settings,
        thumbnails=thumbnail_settings,
        artwork_box=settings.tv_artwork_box,
        engine=engine,
        discovery_settings=settings.discovery_settings,
        collection=a_collection_holding(**{"Agnes Martin": ["Untitled No. 5", "Friendship"]}),
        conversation_engine=conversation_engine,
    )
    view = services.conversation.speak(services.conversation.start().conversation.id, "Something calm.")

    _suggestion, samples = view.turns[-1].suggested[0]
    assert [sample.title for sample in samples] == ["Untitled No. 5", "Friendship"]
    assert all(sample.image_url and sample.image_url.startswith("https://") for sample in samples)


async def test_a_turn_writes_a_conversation_tokens_row_that_reaches_the_month_total(server_url, services):
    """`conversation_tokens` ships with its producer, and the month total sees it.

    Read through `art_discovery(action='spend')` — the only surface that reports
    a calendar month, and the one Q4 is answered from — rather than by summing
    the store, so what is asserted is the figure somebody actually gets.
    """
    now = datetime.now(UTC)
    before, _ = await call(server_url, "art_discovery", action="spend", year=now.year, month=now.month)

    view = say(server_url, started(server_url), "Something calm.")

    after, _ = await call(server_url, "art_discovery", action="spend", year=now.year, month=now.month)
    assert Decimal(after["cost_usd"]) == Decimal(before["cost_usd"]) + Decimal("0.00001896")
    assert after["scope"] == "month"
    (record,) = [row for row in services.discovery._store.list_spend_records() if row.conversation_turn_id]
    assert record.category is SpendCategory.CONVERSATION_TOKENS
    assert record.conversation_turn_id == view["turns"][-1]["turn_id"]
    assert record.discovery_run_id is None


def test_a_turn_that_could_not_be_answered_is_a_200_carrying_the_thread(server_url, conversation_engine):
    """The failed turn stays, and the client is given something to render.

    A 400 would carry no thread, so the browser would show a sentence with the
    curator's question nowhere on screen — which is exactly the "silently
    vanishes" this chunk forbids.
    """
    conversation_engine.error = ConversationFailure("the model could not be reached")
    conversation_id = started(server_url)

    view = say(server_url, conversation_id, "Something calm.")

    assert view["_status"] == 200
    assert view["failure"] == "the model could not be reached"
    assert [turn["text"] for turn in view["turns"]] == ["Something calm."]
    assert view["unanswered_turn_id"] == view["turns"][0]["turn_id"]


def test_retrying_sends_no_text_and_appends_no_second_question(server_url, conversation_engine):
    conversation_engine.error = ConversationFailure("the model could not be reached")
    conversation_id = started(server_url)
    say(server_url, conversation_id, "Something calm.")

    conversation_engine.error = None
    view = say(server_url, conversation_id)

    assert [turn["text"] for turn in view["turns"]] == ["Something calm.", conversation_engine.reply]
    assert view["unanswered_turn_id"] is None


def test_retrying_an_answered_thread_is_refused_rather_than_spending_again(server_url, services):
    """The lost-response window, closed by the transcript rather than by a key."""
    conversation_id = started(server_url)
    say(server_url, conversation_id, "Something calm.")
    spent = len(services.discovery._store.list_spend_records())

    again = say(server_url, conversation_id)

    assert again["_status"] == 400
    assert "nothing to retry" in again["error"]
    assert len(services.discovery._store.list_spend_records()) == spent


def test_committing_answers_with_the_conversation_and_never_with_the_run(server_url):
    """The seam, at the boundary the client sees.

    A response shaped like a run is a response a client navigates to. What comes
    back is the transcript with a committed turn at the end of it, which is what
    the commit card repaints itself from without going anywhere.
    """
    conversation_id = started(server_url)
    say(server_url, conversation_id, "Something calm.")

    committed = httpx.post(
        f"{server_url}/api/conversations/{conversation_id}/commit", json={"intent": "Agnes Martin"}, timeout=20
    ).json()

    assert committed["conversation"]["conversation_id"] == conversation_id
    assert "run_id" not in committed
    seam = committed["turns"][-1]
    assert (seam["role"], seam["text"]) == ("curator", "Agnes Martin")
    assert seam["committed_run_id"] == committed["committed_run_id"]
    # And the run really was started, with the words the curator committed.
    run = httpx.get(f"{server_url}/api/runs/{committed['committed_run_id']}", timeout=20).json()
    assert run["run"]["intent"] == "Agnes Martin"
    assert run["run"]["initiated_by"] == InitiatedBy.WEB_UI.value


def test_a_run_started_from_discover_is_on_no_conversation_turn(server_url, services):
    """The other half of the seam's claim: it is set only where it happened."""
    run = httpx.post(f"{server_url}/api/runs", json={"intent": "Something by Dalí"}, timeout=20).json()

    conversations = httpx.get(f"{server_url}/api/conversations", timeout=20).json()
    assert conversations["count"] == 0
    assert all(
        turn.committed_run_id != run["run_id"]
        for conversation in services.conversation.list_conversations()
        for turn in services.discovery._store.list_conversation_turns(conversation.id)
    )
    assert RunStatus(run["status"]) is not None


def test_the_conversation_list_is_ordered_by_the_last_thing_said(server_url):
    first = started(server_url)
    second = started(server_url)
    say(server_url, first, "Something calm.")

    listed = httpx.get(f"{server_url}/api/conversations", timeout=20).json()

    assert listed["count"] == 2
    assert listed["conversations"][0]["conversation_id"] == first
    assert {entry["conversation_id"] for entry in listed["conversations"]} == {first, second}


def test_an_unknown_conversation_is_refused_in_the_one_error_shape(server_url):
    response = httpx.get(f"{server_url}/api/conversations/not-a-conversation", timeout=20)

    assert response.status_code == 400
    assert "No conversation with id" in response.json()["error"]
