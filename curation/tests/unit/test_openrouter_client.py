"""The client reads what the live API actually sends, and tells the refusals apart.

Every fixture here is a response shape **measured** against the real provider
(`.prawduct/artifacts/openrouter-api-findings.md`), not one invented to match the
parser. That is the whole value: a fixture written from the parser's assumptions
would pass forever while the client mis-read production from its first call.

Driven through `httpx.MockTransport`, so the code under test is the real client
with its real request-building — only the socket is replaced.
"""

import json
from decimal import Decimal

import httpx
import pytest

from curation.discovery.openrouter import (
    BASE_URL,
    COMPLETION_TIMEOUT_SECONDS,
    KEY_TIMEOUT_SECONDS,
    KeyExhausted,
    OpenRouterClient,
    OpenRouterError,
    RequestUnaffordable,
)

# -- measured response shapes ---------------------------------------------------

#: A call that searched, with the decomposition the findings record to the cent:
#: a total of 0.00523535 whose upstream inference part is 0.00023535, leaving
#: exactly the $0.005 per-request search fee.
SEARCHED = {
    "model": "deepseek/deepseek-v4-flash",
    "choices": [
        {
            "finish_reason": "stop",
            "message": {
                "content": '{"strategy": "read as recent prize winners", "works": []}',
                "annotations": [
                    {
                        "type": "url_citation",
                        "url_citation": {
                            "url": "https://example.org/prize",
                            "title": "The 2026 prize",
                            "content": "An excerpt the model was given.",
                            "start_index": 0,
                            "end_index": 10,
                        },
                    }
                ],
            },
        }
    ],
    "usage": {
        "prompt_tokens": 1200,
        "completion_tokens": 300,
        "total_tokens": 1500,
        "cost": 0.00523535,
        "is_byok": False,
        "cost_details": {"upstream_inference_cost": 0.00023535},
    },
}

#: The same call without the plugin: no annotations at all, and the whole charge
#: is inference. Absence of the key is the signal, which is why it is absent here
#: rather than present and empty.
UNSEARCHED = {
    "model": "deepseek/deepseek-v4-flash",
    "choices": [{"finish_reason": "stop", "message": {"content": '{"works": []}'}}],
    "usage": {
        "prompt_tokens": 40,
        "completion_tokens": 20,
        "total_tokens": 60,
        "cost": 0.00002717,
        "cost_details": {"upstream_inference_cost": 0.00002717},
    },
}

#: A 400 raised by the **model provider** behind OpenRouter, measured 2026-08-12.
#: The outer `message` is the constant string "Provider returned error" — a null
#: content field, an image on an assistant turn and an unknown role all arrived
#: wearing it. What actually went wrong is inside `metadata.raw`, which is the
#: provider's own error body forwarded verbatim, still in its SSE `data:` frame.
PROVIDER_400 = {
    "error": {
        "message": "Provider returned error",
        "code": 400,
        "metadata": {
            "raw": 'data: {"error":{"code":"invalid_parameter_error","param":null,'
            '"message":"The content field is a required field.",'
            '"type":"invalid_request_error"},"id":"chatcmpl-1c1aada9"}\n\n',
            "provider_name": "Alibaba",
            "is_byok": False,
        },
    },
    "user_id": "user_2ntxh0Npiz",
}

#: A 400 from OpenRouter's **own** edge, measured in the same round. No `metadata`
#: at all, and `message` already says what is wrong. The two shapes have to be read
#: differently, and a reader written for either one alone loses the other.
EDGE_400 = {"error": {"message": 'Input required: specify "prompt" or "messages"', "code": 400}}


def client_over(handler, **kwargs) -> OpenRouterClient:
    """A real client whose socket is a function. Nothing else is substituted."""
    options = {"model": "deepseek/deepseek-v4-flash", "max_output_tokens": 8000} | kwargs
    return OpenRouterClient("sk-or-v1-test", client=httpx.Client(transport=httpx.MockTransport(handler)), **options)


def responding(payload: dict, status: int = 200):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload)

    return handler


# -- cost, which is the number the ceiling rests on -----------------------------


def test_the_search_fee_is_the_charge_less_its_token_priced_part():
    """The two attributed figures must sum to what the account was debited.

    The provider bills one number and reports the inference share of it; the
    remainder is the search. Deriving it by subtraction rather than pricing it
    locally is what keeps the ledger tied to the bill — a fee computed from a
    configured rate would be a second opinion about money already spent.
    """
    completion = client_over(responding(SEARCHED)).complete(prompt="anything", search_results=10)

    assert completion.cost_usd == Decimal("0.00523535")
    assert completion.inference_cost_usd == Decimal("0.00023535")
    assert completion.search_cost_usd == Decimal("0.005"), "the per-request search fee, to the cent"
    assert completion.inference_cost_usd + completion.search_cost_usd == completion.cost_usd


def test_cost_is_never_a_binary_float():
    """Parsed as `Decimal` at the tokeniser, before a float can round it.

    `0.00523535` has no exact binary representation, so a body read by the
    ordinary JSON parser arrives already wrong — and no later conversion can
    recover the digits the provider actually sent.
    """
    completion = client_over(responding(SEARCHED)).complete(prompt="anything", search_results=10)

    assert isinstance(completion.cost_usd, Decimal)
    assert str(completion.cost_usd) == "0.00523535"
    assert completion.cost_usd != Decimal(0.00523535), "a float round-trip would have been accepted here"


def test_a_call_that_did_not_search_attributes_everything_to_tokens():
    completion = client_over(responding(UNSEARCHED)).complete(prompt="anything", search_results=0)

    assert not completion.searched
    assert completion.search_cost_usd == Decimal(0)
    assert completion.inference_cost_usd == completion.cost_usd


def test_a_route_reporting_no_breakdown_attributes_everything_to_tokens():
    """Rather than inventing a split for a number the provider never decomposed.

    Over-reporting tokens is visible in a ledger that still sums correctly;
    a fabricated search share would put a figure in the record that nothing
    said.
    """
    payload = json.loads(json.dumps(SEARCHED))
    del payload["usage"]["cost_details"]

    completion = client_over(responding(payload)).complete(prompt="anything", search_results=10)

    assert completion.cost_usd == Decimal("0.00523535")
    assert completion.inference_cost_usd == Decimal("0.00523535")
    assert completion.search_cost_usd == Decimal(0)


def test_a_negative_remainder_never_becomes_a_negative_spend_row():
    payload = json.loads(json.dumps(SEARCHED))
    payload["usage"]["cost_details"]["upstream_inference_cost"] = 9.9

    completion = client_over(responding(payload)).complete(prompt="anything", search_results=10)

    assert completion.search_cost_usd == Decimal(0)


# -- citations ------------------------------------------------------------------


def test_citations_carry_the_excerpt_the_model_was_given():
    """Which is what makes a discovered work traceable to a page, not to a claim."""
    completion = client_over(responding(SEARCHED)).complete(prompt="anything", search_results=10)

    assert completion.searched
    assert [citation.url for citation in completion.citations] == ["https://example.org/prize"]
    assert completion.citations[0].content == "An excerpt the model was given."


def test_annotations_of_another_kind_are_not_read_as_citations():
    payload = json.loads(json.dumps(SEARCHED))
    payload["choices"][0]["message"]["annotations"].append({"type": "file", "file": {"name": "x"}})

    completion = client_over(responding(payload)).complete(prompt="anything", search_results=10)

    assert len(completion.citations) == 1


# -- the two refusals, which mean opposite things -------------------------------


def test_exhaustion_is_403_and_says_what_clears_it():
    """The measured shape of a spent key. Its own type, because its answer is unique."""
    handler = responding(
        {"error": {"message": "Key limit exceeded (total limit). Manage it using https://openrouter.ai/keys", "code": 403}},
        status=403,
    )

    with pytest.raises(KeyExhausted) as raised:
        client_over(handler).complete(prompt="anything")

    assert "Key limit exceeded" in str(raised.value), "the provider's own words survive"
    assert "monthly reset" in str(raised.value)


def test_an_unaffordable_request_is_402_and_is_not_exhaustion():
    """402 arrives with credit in the account, so it must not read as "stop".

    The provider reserves the maximum output the request could produce and
    declines when that reservation exceeds the balance. Collapsing this into
    exhaustion would halt runs that can still pay.
    """
    handler = responding(
        {
            "error": {
                "message": "This request requires more credits, or fewer max_tokens. You requested up to "
                "32000 tokens, but can only afford 3333.",
                "code": 402,
            }
        },
        status=402,
    )

    with pytest.raises(RequestUnaffordable) as raised:
        client_over(handler).complete(prompt="anything")

    assert not isinstance(raised.value, KeyExhausted), "402 must never be read as a spent key"
    assert "can only afford 3333" in str(raised.value), "the arithmetic that explains it is quoted through"
    assert "DISCOVERY_MAX_OUTPUT_TOKENS" in str(raised.value), "and it names the setting that fixes it"


def test_any_other_failure_is_a_plain_error():
    with pytest.raises(OpenRouterError) as raised:
        client_over(responding({"error": {"message": "Rate limited"}}, status=429)).complete(prompt="anything")

    assert not isinstance(raised.value, (KeyExhausted, RequestUnaffordable))
    assert "429" in str(raised.value)


def test_an_unreachable_provider_is_an_error_not_a_crash():
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    with pytest.raises(OpenRouterError, match="Could not reach OpenRouter"):
        client_over(refuse).complete(prompt="anything")


# -- a refusal has two authors, and only one of them is OpenRouter --------------


def test_a_provider_400_names_what_the_provider_actually_objected_to():
    """The diagnosable half of a provider refusal is not in `error.message`.

    Every provider-side 400 measured carries the same outer string, so a client
    reading only that reports one message for a null content field, a misplaced
    image and an unknown role alike — three different mistakes with three
    different fixes, indistinguishable to whoever has to act on them.
    """
    with pytest.raises(OpenRouterError) as raised:
        client_over(responding(PROVIDER_400, status=400)).complete(prompt="anything")

    message = str(raised.value)
    assert "The content field is a required field." in message, "the provider's actual objection reaches the caller"
    assert "Alibaba" in message, "and says which provider made it, since the route decides that"


def test_the_upstream_body_is_read_rather_than_pasted_in_whole():
    """Stripping the stream framing is the difference between a sentence and a dump.

    Asserting only that the cause *appears* cannot see this: the unparsed body
    contains the same sentence as a substring, so a client that pasted the whole
    SSE frame in would satisfy that check while handing a curator a wall of JSON.
    Found by `tools/mutation_sweep.py` — deleting the strip changed nothing until
    this test named what the strip is for.
    """
    with pytest.raises(OpenRouterError) as raised:
        client_over(responding(PROVIDER_400, status=400)).complete(prompt="anything")

    message = str(raised.value)
    assert "The content field is a required field." in message
    assert "invalid_parameter_error" not in message, "the provider's envelope is read, not quoted"
    assert "data:" not in message, "and its stream framing never reaches a human"


def test_a_provider_refusal_with_no_body_still_says_which_provider_refused():
    """Naming the provider is worth something even when it explained nothing.

    The route decides which provider serves a request, so "Alibaba refused and
    gave no reason" points at a retry on a different route; a bare "Provider
    returned error" points nowhere at all.
    """
    payload = json.loads(json.dumps(PROVIDER_400))
    payload["error"]["metadata"].pop("raw")

    with pytest.raises(OpenRouterError) as raised:
        client_over(responding(payload, status=400)).complete(prompt="anything")

    assert "Alibaba" in str(raised.value)


def test_an_edge_400_keeps_its_own_message_when_there_is_no_upstream_body():
    """OpenRouter's own refusals say what is wrong in the place they always did.

    The guard against fixing the provider shape by breaking this one: these
    carry no `metadata`, and reading the upstream body must stay optional.
    """
    with pytest.raises(OpenRouterError) as raised:
        client_over(responding(EDGE_400, status=400)).complete(prompt="anything")

    assert 'Input required: specify "prompt" or "messages"' in str(raised.value)


def test_an_upstream_body_in_an_unrecognised_framing_is_passed_through_not_dropped():
    """The framing is the provider's own, so it is free to stop being JSON.

    Passing it through unparsed is worse to read and strictly better than the
    alternative, which is a caller told only that something returned an error.
    """
    payload = json.loads(json.dumps(PROVIDER_400))
    payload["error"]["metadata"]["raw"] = "upstream exploded, and not in JSON"

    with pytest.raises(OpenRouterError) as raised:
        client_over(responding(payload, status=400)).complete(prompt="anything")

    assert "upstream exploded" in str(raised.value)


# -- the budget for connecting is not the budget for generating -----------------


def timing(recorder, payload=UNSEARCHED):
    """A transport that records the timeout httpx was handed for each request."""

    def handler(request: httpx.Request) -> httpx.Response:
        recorder.append(request.extensions.get("timeout"))
        return httpx.Response(200, json=payload)

    return handler


def test_a_dead_address_family_cannot_consume_the_whole_completion_budget():
    """Connecting is bounded far more tightly than generating, and must be.

    httpx has no Happy Eyeballs: it tries the addresses `getaddrinfo` returns in
    order, and this provider publishes AAAA records. On a network whose IPv6 path
    is black-holed the first attempt is to an address that will never answer, and
    a single timeout value makes that attempt cost the *whole* generation budget
    before IPv4 is tried at all — measured at ~150 seconds against 0.02 over IPv4.

    So the contract is the split itself, not either number: generation keeps its
    minutes, and a dead address is abandoned in seconds.
    """
    seen: list = []

    client_over(timing(seen)).complete(prompt="anything")

    timeout = seen[0]
    assert timeout["read"] == COMPLETION_TIMEOUT_SECONDS, "generation keeps its full budget"
    assert timeout["connect"] <= 10, "and a connection that will never answer is given up on in seconds"


def test_the_key_endpoint_bounds_connecting_the_same_way():
    """It backs a display figure, so it has even less business waiting minutes."""
    seen: list = []
    client = client_over(timing(seen, payload={"data": {"usage": 1}}))

    client.key_status()

    assert seen[0]["read"] == KEY_TIMEOUT_SECONDS
    assert seen[0]["connect"] <= 10


def test_an_answer_with_no_choices_is_returned_with_its_cost_rather_than_raised():
    """Same rule as an empty completion, for the same reason: it was billed.

    A malformed 2xx is still a charge on the account, so the cost has to travel
    back for the caller to record before it decides the answer is unusable.
    """
    payload = json.loads(json.dumps(SEARCHED))
    payload["choices"] = []

    completion = client_over(responding(payload)).complete(prompt="anything")

    assert completion.content == ""
    assert completion.cost_usd == Decimal("0.00523535")


def test_an_empty_completion_is_returned_with_its_cost_rather_than_raised():
    """The call was billed before anyone could see the answer was unusable.

    Raising here would carry no cost with it, so the run that paid would record
    having spent nothing — the under-reporting the whole spend path exists to
    prevent. Judging the content belongs to the caller; reporting the charge
    belongs here.
    """
    payload = json.loads(json.dumps(SEARCHED))
    payload["choices"][0]["message"]["content"] = ""
    payload["choices"][0]["finish_reason"] = "length"

    completion = client_over(responding(payload)).complete(prompt="anything")

    assert completion.content == ""
    assert completion.finish_reason == "length", "the caller needs to be able to explain it"
    assert completion.cost_usd == Decimal("0.00523535"), "the charge survives an unusable answer"


# -- what actually goes on the wire ---------------------------------------------


def sent_body(*, client_options: dict | None = None, **kwargs) -> dict:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, json=SEARCHED)

    client_over(handler, **(client_options or {})).complete(**kwargs)
    return captured


def test_the_output_reservation_is_always_sent():
    """Never omitted: unset means the model's own maximum is reserved, and a
    nearly empty key then refuses everything at full credit."""
    assert sent_body(prompt="anything")["max_tokens"] == 8000


def test_cost_reporting_is_always_requested():
    """Without it the response carries no cost, and the only remaining route to a
    run's actual spend is tokens times a price table — the one arithmetic that
    omits the search fee entirely."""
    assert sent_body(prompt="anything")["usage"] == {"include": True}


def test_the_search_plugin_is_attached_only_when_results_are_asked_for():
    assert "plugins" not in sent_body(prompt="anything", search_results=0)
    assert sent_body(prompt="anything", search_results=10)["plugins"] == [{"id": "web", "max_results": 10}]


def test_an_unpinned_engine_sends_no_engine_key_at_all():
    """Absent and "whatever the default is" must stay the same request.

    Sending a name for the default would be this code asserting which back-end
    the provider resolves to, which it does not know: the default follows the
    *model*, taking its native search where one exists and Exa where none does.
    """
    plugin = sent_body(prompt="anything", search_results=10)["plugins"][0]

    assert "engine" not in plugin


def test_a_pinned_engine_travels_with_the_search():
    """What makes one search comparable to another.

    Unpinned, the back-end is chosen by whichever model is configured, so
    changing the model silently changes the search — and a measurement taken
    across that change would read as a quality difference in the wrong variable.
    """
    plugin = sent_body(client_options={"search_engine": "parallel"}, prompt="anything", search_results=10)["plugins"][0]

    assert plugin == {"id": "web", "max_results": 10, "engine": "parallel"}


def test_a_pinned_engine_is_not_sent_when_nothing_is_being_searched():
    """The engine names how to search, so it is meaningless on a call that does
    not — and a plugin block on a searchless call could bill for one."""
    assert "plugins" not in sent_body(client_options={"search_engine": "parallel"}, prompt="anything", search_results=0)


def test_the_client_reports_which_engine_it_pinned():
    """A measurement of search quality has to be able to name what it measured."""
    assert client_over(responding(SEARCHED)).search_engine is None
    assert client_over(responding(SEARCHED), search_engine="exa").search_engine == "exa"


def test_a_schema_is_sent_in_strict_mode():
    body = sent_body(prompt="anything", schema={"type": "object", "properties": {}})

    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["strict"] is True


def test_the_key_travels_as_a_bearer_token_and_the_url_is_the_provider():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("Authorization")
        seen["url"] = str(request.url)
        return httpx.Response(200, json=SEARCHED)

    client_over(handler).complete(prompt="anything")

    assert seen["auth"] == "Bearer sk-or-v1-test"
    assert seen["url"] == f"{BASE_URL}/chat/completions"


# -- construction refuses what the provider would refuse later ------------------


@pytest.mark.parametrize("reservation", [0, -1])
def test_a_non_positive_output_reservation_is_refused_at_construction(reservation):
    """Caught here rather than as a 402 after a round trip, because there is no
    reading of "reserve nothing" that the provider will accept."""
    with pytest.raises(ValueError, match="max_output_tokens"):
        OpenRouterClient("sk-or-v1-test", model="m", max_output_tokens=reservation)


def test_a_client_without_a_key_is_refused():
    with pytest.raises(ValueError, match="API key"):
        OpenRouterClient("", model="m", max_output_tokens=100)


# -- the key endpoint, which is display-only ------------------------------------


def test_key_status_reads_the_ceiling_as_exact_money():
    """The measured `/key` shape, including the monthly reset this product's key
    carries. Read for display only: it lags by minutes, so it may never gate."""
    handler = responding(
        {
            "data": {
                "limit": 20,
                "usage": 2.7168e-05,
                "limit_remaining": 19.999972832,
                "limit_reset": "monthly",
                "is_free_tier": False,
            }
        }
    )

    status = client_over(handler).key_status()

    assert status.limit_usd == Decimal("20")
    assert status.remaining_usd == Decimal("19.999972832")
    assert status.resets == "monthly"
    assert isinstance(status.usage_usd, Decimal)


def test_an_uncapped_key_reports_no_limit_rather_than_zero():
    """`null` means uncapped, and zero would mean the opposite of that."""
    status = client_over(responding({"data": {"limit": None, "usage": 1.5, "limit_remaining": None}})).key_status()

    assert status.limit_usd is None
    assert status.remaining_usd is None
    assert status.usage_usd == Decimal("1.5")
