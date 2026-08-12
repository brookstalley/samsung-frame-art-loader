"""The multi-turn half of the OpenRouter client, against what the API really sent.

**Every response body here is a capture**, taken from a 2026-08-12 probe of the
live API — 41 real calls, `qwen/qwen3.7-flash` routed to Alibaba — and stored
verbatim under `tests/fixtures/openrouter_conversation/`. They are served as
*text* rather than as re-encoded dictionaries, which matters for exactly one
reason and it is the reason the client exists: costs arrive in both fixed and
scientific notation (`0.00001896`, `6.6E-7`), and the client's
`json.loads(..., parse_float=Decimal)` is what keeps either from becoming a
binary float. A fixture handing over an already-converted `Decimal` would skip
the conversion being relied on.

The request half is asserted through a recording transport, because three of the
claims this chunk stands on are properties of what is *sent* and are invisible in
any response: the whole history travels, an image never rides an assistant turn,
and a failed turn is resent as `""` and never as `null`. Each of those is a real
400 if it is got wrong, and each of those 400s is in the captures too.
"""

import json
import pathlib

import httpx
import pytest

from curation.discovery.openrouter import Message, OpenRouterClient, OpenRouterError

FIXTURES = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "openrouter_conversation"


def capture(name: str):
    """One recorded exchange as `(status, body-text)`, exactly as it arrived."""
    payload = json.loads((FIXTURES / f"{name}.json").read_text())
    return payload["status"], payload["body"]


def client_over(handler, **kwargs) -> OpenRouterClient:
    """A real client whose socket is a function. Nothing else is substituted."""
    options = {"model": "qwen/qwen3.7-flash", "max_output_tokens": 2000} | kwargs
    return OpenRouterClient("sk-or-v1-test", client=httpx.Client(transport=httpx.MockTransport(handler)), **options)


def answering(name: str):
    """A transport that replays one capture and records what was asked of it."""
    status, body = capture(name)
    sent: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(status, text=body, headers={"content-type": "application/json"})

    return handler, sent


A_THREAD = (
    Message(role="system", text="You are helping a curator choose art."),
    Message(role="user", text="Something calm for the living room."),
    Message(role="assistant", text="Rothko's colour fields would suit that."),
    Message(role="user", text="Name one other artist in that vein."),
)


def test_the_whole_history_is_sent_in_order():
    """The claim a conversation is built on, and one no response could show.

    The provider keeps no thread state — measured: there is no thread id and no
    `previous_response_id` — so a client that sent only the newest question would
    get sensible-looking answers to a conversation that never happened.
    """
    handler, sent = answering("c2")
    client_over(handler).complete_thread(messages=A_THREAD)

    assert [message["role"] for message in sent[0]["messages"]] == ["system", "user", "assistant", "user"]
    assert sent[0]["messages"][-1]["content"] == "Name one other artist in that vein."


def test_a_failed_turn_is_resent_as_an_empty_string_and_never_as_null():
    """The finding that decides how a failed turn is stored.

    A truncated turn comes back from the provider as `content: null`. Feeding
    that back is a 400 — *"The content field is a required field"* — while
    `content: ""` is accepted and answered normally. Both measured, twice, on two
    different histories. So a thread carrying a failed turn forward has to carry
    it as the empty string, and nothing in this client can express the null.
    """
    handler, sent = answering("c2")
    client_over(handler).complete_thread(
        messages=[Message(role="user", text="Tell me about the Hudson River School."), Message(role="assistant", text="")]
    )

    carried = sent[0]["messages"][1]
    assert carried["content"] == ""
    assert carried["content"] is not None


def test_an_image_may_not_ride_an_assistant_turn():
    """Refused where the mistake is made, rather than by the provider later.

    Measured: an `image_url` part in an assistant message is a 400 — *"An
    incorrect modal `image` was entered … or was placed in the wrong position"*.
    A sample the model should look at again rides the curator's next turn.
    """
    from curation.discovery.openrouter import ImageAttachment

    picture = ImageAttachment(base64_data="/9j/4AAQ", media_type="image/jpeg")
    with pytest.raises(ValueError, match="only travel on a user turn"):
        Message(role="assistant", text="Here is one.", image=picture)
    # And the same shape on a user turn is fine, which is what makes the refusal
    # above about position rather than about images.
    assert Message(role="user", text="What about this?", image=picture).wire()["content"][1]["type"] == "image_url"


def test_a_role_the_provider_does_not_know_is_refused_here():
    """The product's own `curator`/`system` pair never reaches the wire.

    Measured: `curator` is a 400 reading *"curator is not one of ['system',
    'assistant', 'user', 'tool', 'function']"*. Translating above this seam is
    what keeps that from being a network round trip to discover.
    """
    with pytest.raises(ValueError, match="message role is one of"):
        Message(role="curator", text="Something calm.")


def test_reasoning_can_be_switched_off_and_is_absent_unless_asked_for():
    """The parameter that separates a billed empty answer from an answer.

    On an open-ended prompt the routed model spent its entire reservation on
    reasoning before emitting a character — ten calls, three reservation sizes,
    every one empty and every one billed. `{"enabled": false}` fixed it at a
    twenty-seventh of the cost. The client could not express the key at all
    until this method existed.
    """
    handler, sent = answering("c2")
    client = client_over(handler)
    client.complete_thread(messages=A_THREAD, reasoning={"enabled": False})
    client.complete_thread(messages=A_THREAD)

    assert sent[0]["reasoning"] == {"enabled": False}
    assert "reasoning" not in sent[1]


def test_a_multi_turn_answer_is_read_by_the_reader_that_already_existed():
    """The response half needed nothing, and this is the assertion that says so.

    Every field below comes off the same `_read_completion` the single-shot path
    has always used, against a real multi-turn image-bearing response.
    """
    handler, _ = answering("c2")
    completion = client_over(handler).complete_thread(messages=A_THREAD)

    assert completion.content.startswith("Yes, its ethereal subject")
    assert completion.model_id == "qwen/qwen3.7-flash"
    assert str(completion.cost_usd) == "0.00001896"
    assert (completion.input_tokens, completion.output_tokens) == (528, 24)
    assert completion.finish_reason == "stop"
    # No search plugin was sent, so the whole charge is inference and nothing
    # would produce a spurious `web_search` row.
    assert completion.search_cost_usd == 0
    assert completion.searched is False


def test_a_truncated_turn_keeps_its_partial_answer_and_its_bill():
    """`finish_reason` is the only signal separating a usable turn from a cut one.

    The cost here is `6.6E-7` in one of its details — scientific notation, which
    is why the fixture is served as text. A body re-encoded from Python would
    have lost the case.
    """
    handler, _ = answering("truncated_no_reasoning")
    completion = client_over(handler).complete_thread(messages=A_THREAD)

    assert completion.finish_reason == "length"
    assert completion.content == "The Hudson River School was the first American art movement, emerging"
    assert str(completion.cost_usd) == "0.00000222"


def test_a_turn_whose_whole_budget_went_on_reasoning_reads_as_empty_and_billed():
    """`content: null` becomes `""`, and the charge still travels.

    The `or ""` in the response reader is load-bearing on this route rather than
    defensive: without it a `None` reaches a `Completion` typed `str`, and the
    turn stored from it is the null the *next* request is refused for.
    """
    handler, _ = answering("a1")
    completion = client_over(handler).complete_thread(messages=A_THREAD)

    assert completion.content == ""
    assert completion.finish_reason == "length"
    assert completion.cost_usd > 0


def test_a_provider_refusal_says_what_was_actually_wrong():
    """The three lines this chunk made necessary.

    OpenRouter wraps a routed provider's 400 as `error.message = "Provider
    returned error"` and puts the cause in `error.metadata.raw`. Three distinct
    400s in the probe reached the caller as that one string — which is tolerable
    for a caller that retries nothing, and not for a failed turn a curator is
    being asked to retry.
    """
    handler, _ = answering("null_content_echo")
    with pytest.raises(OpenRouterError) as refusal:
        client_over(handler).complete_thread(messages=A_THREAD)

    assert "Provider returned error" in str(refusal.value)
    assert "The content field is a required field" in str(refusal.value)


def test_a_misplaced_image_refusal_says_which_modal_and_where():
    """The second of the three 400s, so the unwrapping is not fitted to one body."""
    handler, _ = answering("assistant_image")
    with pytest.raises(OpenRouterError) as refusal:
        client_over(handler).complete_thread(messages=A_THREAD)

    assert "incorrect modal" in str(refusal.value)


def test_a_refusal_from_the_edge_has_no_metadata_and_is_quoted_as_it_stands():
    """The other error shape, and why unwrapping must not assume the first one.

    OpenRouter's own edge puts the cause directly in `error.message` and sends no
    `metadata` at all. Pinning both is what stops the unwrapping from being fixed
    for one shape and broken for the other.
    """
    handler, _ = answering("empty_history")
    with pytest.raises(OpenRouterError) as refusal:
        client_over(handler).complete_thread(messages=A_THREAD)

    message = str(refusal.value)
    assert 'Input required: specify "prompt" or "messages"' in message
    # Nothing appended: there was no upstream body to unwrap, and inventing a
    # separator would put a colon on the end of every edge refusal.
    assert message.endswith('Input required: specify "prompt" or "messages"')


def test_an_empty_thread_is_refused_before_it_reaches_the_provider():
    """The edge 400 above, made unreachable from this method.

    A request the provider would refuse for having no messages is a request this
    client should never send, and the local refusal names the caller's mistake
    instead of quoting a provider's true sentence about it.
    """
    handler, sent = answering("c2")
    with pytest.raises(ValueError, match="at least one message"):
        client_over(handler).complete_thread(messages=[])
    assert sent == []


def test_the_single_shot_path_still_sends_exactly_what_it_did():
    """`complete` now delegates, and the shape it produces must not have moved.

    Phase 1 and the mat call both go through it, and both were measured against
    the body it built — one user message, the prompt as a bare string, no
    `reasoning` key at all.
    """
    handler, sent = answering("c2")
    client_over(handler).complete(prompt="Name a work.")

    assert sent[0]["messages"] == [{"role": "user", "content": "Name a work."}]
    assert "reasoning" not in sent[0]
    assert sent[0]["max_tokens"] == 2000
    assert sent[0]["usage"] == {"include": True}
