"""The intent-forming engine, over a real client and a recorded transport.

Same arrangement as `test_mat_engine.py`: the real `OpenRouterConversation`
wrapping the real `OpenRouterClient`, with an `httpx.MockTransport` where the
socket would be. Nothing about the class under test is substituted.

**The bodies are the 2026-08-12 captures, with one documented edit.** The probe
sent no `response_format`, so its replies are prose; this engine asks for a JSON
envelope. So `answering_with` takes the capture verbatim and replaces exactly one
field — `choices[0].message.content` — leaving the usage block, the cost
notation, the finish reason and the provider's own extra keys untouched. Every
assertion below about money, tokens and truncation therefore runs against numbers
the API really sent.
"""

import json
import pathlib

import httpx
import pytest

from curation.discovery.conversation import (
    NO_CONVERSATION_KEY,
    ConversationFailure,
    OpenRouterConversation,
    Suggestion,
    ThreadTurn,
    UnavailableConversation,
)
from curation.discovery.openrouter import OpenRouterClient
from curation.persistence.discovery_records import SpendCategory, TurnRole

FIXTURES = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "openrouter_conversation"

A_REPLY = {
    "reply": "Agnes Martin's pale grids would hold that stillness.",
    "suggested": [{"kind": "artist", "value": "Agnes Martin"}, {"kind": "movement", "value": "Minimalism"}],
}


def answering_with(name: str, content):
    """The named capture, with only the reply's own text swapped in.

    `content` may be a mapping — encoded as the JSON envelope the schema asks
    for — or a string, for the cases about text that is not the envelope at all.
    """
    payload = json.loads((FIXTURES / f"{name}.json").read_text())
    body = json.loads(payload["body"])
    body["choices"][0]["message"]["content"] = content if isinstance(content, str) else json.dumps(content)
    sent: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(payload["status"], json=body)

    return handler, sent


def engine_over(handler) -> OpenRouterConversation:
    return OpenRouterConversation(
        OpenRouterClient(
            "sk-or-v1-test",
            model="qwen/qwen3.7-flash",
            max_output_tokens=2000,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
    )


def a_thread(*texts: str) -> list[ThreadTurn]:
    """Turns alternating from the curator, which is what a real thread looks like."""
    return [
        ThreadTurn(role=TurnRole.CURATOR if index % 2 == 0 else TurnRole.SYSTEM, text=text) for index, text in enumerate(texts)
    ]


def test_a_turn_carries_the_thread_and_a_standing_instruction():
    handler, sent = answering_with("c2", A_REPLY)
    engine_over(handler).answer(a_thread("Something calm.", "Rothko would suit.", "Anyone else?"))

    roles = [message["role"] for message in sent[0]["messages"]]
    assert roles == ["system", "user", "assistant", "user"]
    assert sent[0]["messages"][0]["content"].startswith("You are helping one person")
    assert sent[0]["messages"][-1]["content"] == "Anyone else?"


def test_reasoning_is_switched_off_on_every_turn():
    """A correctness value, not a preference — see the module docstrings."""
    handler, sent = answering_with("c2", A_REPLY)
    engine_over(handler).answer(a_thread("Something calm."))

    assert sent[0]["reasoning"] == {"enabled": False}
    assert sent[0]["response_format"]["json_schema"]["name"] == "conversation_reply"


def test_a_long_thread_is_trimmed_from_the_head_and_never_from_the_tail():
    """The cost dial, and the one way trimming could be wrong.

    Every turn resends the whole history and is billed for it, so a bound is
    needed; dropping the newest turn to keep an older one would answer the wrong
    question, which is the failure a head-trim cannot have.
    """
    handler, sent = answering_with("c2", A_REPLY)
    engine = OpenRouterConversation(
        OpenRouterClient(
            "sk-or-v1-test",
            model="qwen/qwen3.7-flash",
            max_output_tokens=2000,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        ),
        history_turns=2,
    )
    engine.answer(a_thread("first", "second", "third", "fourth"))

    carried = [message["content"] for message in sent[0]["messages"][1:]]
    assert carried == ["third", "fourth"]


def test_a_turn_that_failed_travels_forward_as_an_empty_string():
    """The stored empty turn must not become the provider's `null` on the way out."""
    handler, sent = answering_with("c2", A_REPLY)
    engine_over(handler).answer([*a_thread("Something calm."), ThreadTurn(role=TurnRole.SYSTEM, text="")])

    assert sent[0]["messages"][-1] == {"role": "assistant", "content": ""}


def test_a_turn_reports_what_it_named_and_what_it_cost():
    handler, _ = answering_with("c2", A_REPLY)
    reply = engine_over(handler).answer(a_thread("Something calm."))

    assert reply.text == "Agnes Martin's pale grids would hold that stillness."
    assert list(reply.suggested) == [
        Suggestion(kind="artist", value="Agnes Martin"),
        Suggestion(kind="movement", value="Minimalism"),
    ]
    (charge,) = reply.spend
    assert charge.category is SpendCategory.CONVERSATION_TOKENS
    # The provider's own figure for the whole call, from the capture. One row,
    # because no search was made and a `web_search` row would price nothing.
    assert str(charge.cost_usd) == "0.00001896"
    assert (charge.input_tokens, charge.output_tokens) == (528, 24)


def test_a_suggestion_of_an_unknown_kind_is_dropped_rather_than_stored():
    """A value no surface has words for is a diagnostic label waiting to be shown."""
    handler, _ = answering_with(
        "c2", {"reply": "Something.", "suggested": [{"kind": "vibe", "value": "calm"}, {"kind": "artist", "value": "Klee"}]}
    )
    reply = engine_over(handler).answer(a_thread("Something calm."))

    assert list(reply.suggested) == [Suggestion(kind="artist", value="Klee")]


def test_a_reply_with_unreadable_suggestions_is_still_a_reply():
    """The sentence is what the curator reads; the index beside it is decoration."""
    handler, _ = answering_with("c2", {"reply": "Agnes Martin.", "suggested": "not a list"})
    reply = engine_over(handler).answer(a_thread("Something calm."))

    assert reply.text == "Agnes Martin."
    assert reply.suggested == ()


def test_a_turn_truncated_mid_answer_fails_and_carries_its_bill():
    """The retryable failure, and the reason the ledger must still get the row.

    A truncated envelope is well-formed right up to where it was cut, so it
    arrives as a decode error rather than as prose — and it was billed. A month
    total that omitted exactly the failures would under-report by what they cost.
    """
    handler, _ = answering_with("truncated_no_reasoning", '{"reply": "The Hudson River School was the first Ameri')
    with pytest.raises(ConversationFailure) as failure:
        engine_over(handler).answer(a_thread("Tell me about the Hudson River School."))

    assert "stopped on 'length'" in str(failure.value)
    assert "CONVERSATION_MAX_OUTPUT_TOKENS" in str(failure.value)
    (charge,) = failure.value.spend
    assert str(charge.cost_usd) == "0.00000222"


def test_a_turn_whose_budget_went_on_reasoning_fails_and_carries_its_bill():
    """The dominant failure mode the probe found: empty content, billed in full."""
    handler, _ = answering_with("a1", "")
    with pytest.raises(ConversationFailure) as failure:
        engine_over(handler).answer(a_thread("Suggest a direction."))

    (charge,) = failure.value.spend
    assert charge.cost_usd > 0


def test_a_provider_refusal_reaches_the_caller_with_the_provider_s_reason():
    """The failed turn's message names what was wrong, which it did not before."""
    payload = json.loads((FIXTURES / "null_content_echo.json").read_text())

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(payload["status"], text=payload["body"], headers={"content-type": "application/json"})

    with pytest.raises(ConversationFailure) as failure:
        engine_over(handler).answer(a_thread("Something calm."))

    assert "The content field is a required field" in str(failure.value)
    # Nothing was generated, so nothing was billed — which is what makes asking
    # again safe rather than a second charge.
    assert failure.value.spend == ()


def test_a_deployment_with_no_key_refuses_and_names_what_fixes_it():
    """Refuses rather than falling back, unlike the mat engine, and deliberately.

    A mat has an honest mechanical producer; a reply to "what would suit a calm
    wall" has none, and anything invented here would sit in a transcript beside
    real replies with nothing to tell them apart.
    """
    with pytest.raises(ConversationFailure) as failure:
        UnavailableConversation(NO_CONVERSATION_KEY).answer(a_thread("Something calm."))

    assert "OPENROUTER_API_KEY" in str(failure.value)
    assert UnavailableConversation(NO_CONVERSATION_KEY).unavailable_reason == NO_CONVERSATION_KEY
