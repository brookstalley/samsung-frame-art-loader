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
