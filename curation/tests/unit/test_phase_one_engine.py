"""Phase 1 over a real client whose socket is a function.

The client is exercised for real — its request building, its status-code
mapping, its cost arithmetic — and only the network is replaced. An engine
tested against a mocked *client* would be testing this module's idea of the
provider rather than the provider's measured shapes.
"""

import json
from decimal import Decimal

import httpx
import pytest

from curation.discovery.engine import BudgetExhausted, EngineFailure, WorkListRequest
from curation.discovery.openrouter import OpenRouterClient
from curation.discovery.phase_one import OpenRouterEngine
from curation.persistence.discovery_records import SpendCategory

ANSWER = {
    "strategy": "Read as prize winners announced in the past year; searched for 2026 award announcements.",
    "works": [
        {"title": "Landscape", "artist": "Robert Fielding", "rationale": "Won Hadley's Art Prize 2026."},
        {"title": "Marmelade", "artist": "Paolo Almario", "rationale": "Won the State of the ART(ist) Grand Prize 2026."},
    ],
}


def responding(answer: dict, *, searched: bool = True, cost: str = "0.00523535", inference: str = "0.00023535"):
    """A provider that returns `answer` with the measured cost decomposition."""

    def handler(request: httpx.Request) -> httpx.Response:
        message: dict = {"content": json.dumps(answer)}
        if searched:
            message["annotations"] = [
                {"type": "url_citation", "url_citation": {"url": "https://example.org/p", "title": "t", "content": "c"}}
            ]
        return httpx.Response(
            200,
            json={
                "model": "deepseek/deepseek-v4-flash",
                "choices": [{"finish_reason": "stop", "message": message}],
                "usage": {
                    "prompt_tokens": 1200,
                    "completion_tokens": 300,
                    "cost": float(cost),
                    "cost_details": {"upstream_inference_cost": float(inference)},
                },
            },
        )

    return handler


def engine_over(handler, *, search_results: int = 10) -> OpenRouterEngine:
    client = OpenRouterClient(
        "sk-or-v1-test",
        model="deepseek/deepseek-v4-flash",
        max_output_tokens=8000,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    return OpenRouterEngine(client, search_results=search_results)


def asked(intent: str = "recent award-winning art", allowance: int = 10) -> WorkListRequest:
    return WorkListRequest(intent_text=intent, search_allowance=allowance)


# -- what comes back ------------------------------------------------------------


def test_an_intent_becomes_works_with_their_reasons():
    produced = engine_over(responding(ANSWER)).enumerate_works(asked())

    assert [work.title for work in produced.works] == ["Landscape", "Marmelade"]
    assert produced.works[0].artist == "Robert Fielding"
    assert produced.works[0].rationale == "Won Hadley's Art Prize 2026."


def test_the_strategy_comes_back_as_the_engines_own_account():
    """It explains the list, so it is what the model said rather than a sentence
    assembled from settings — which would describe the configuration instead."""
    produced = engine_over(responding(ANSWER)).enumerate_works(asked())

    assert produced.strategy == ANSWER["strategy"]


def test_an_empty_strategy_is_absent_rather_than_a_blank_string():
    produced = engine_over(responding({**ANSWER, "strategy": "   "})).enumerate_works(asked())

    assert produced.strategy is None


def test_an_unattributed_work_carries_no_artist_rather_than_an_empty_name():
    """The schema must ask for `artist` as a string to stay strict, so "unknown"
    arrives as an empty one — and an empty string would key the dedup differently
    from an absence."""
    answer = {"strategy": "s", "works": [{"title": "Untitled", "artist": "", "rationale": "It matches."}]}

    produced = engine_over(responding(answer)).enumerate_works(asked())

    assert produced.works[0].artist is None


# -- searching ------------------------------------------------------------------


def test_every_run_searches_when_the_allowance_permits_it():
    """No per-intent trigger. A trigger that guessed wrong would fail silently,
    returning confidently pre-cutoff works with nothing marking them stale."""
    sent: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        sent.update(json.loads(request.content))
        return responding(ANSWER)(request)

    engine_over(handler).enumerate_works(asked(intent="Dalí's most famous works"))

    assert sent["plugins"] == [{"id": "web", "max_results": 10}], "even an intent with no time element searches"


def test_one_call_spends_one_search_of_the_allowance():
    produced = engine_over(responding(ANSWER)).enumerate_works(asked(allowance=10))

    assert produced.searches_used == 1, "the bound is on fan-out; this engine makes one request"


def test_an_allowance_of_zero_produces_a_genuinely_text_only_run():
    """A deployment that forbids searching gets a run that does not search,
    rather than a setting nothing honours."""
    sent: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        sent.update(json.loads(request.content))
        return responding(ANSWER, searched=False)(request)

    produced = engine_over(handler).enumerate_works(asked(allowance=0))

    assert "plugins" not in sent
    assert produced.searches_used == 0
    assert [entry.category for entry in produced.spend] == [SpendCategory.DISCOVERY_TOKENS]


# -- what it cost ---------------------------------------------------------------


def test_spend_splits_into_the_two_categories_that_bill_differently():
    produced = engine_over(responding(ANSWER)).enumerate_works(asked())

    by_category = {entry.category: entry for entry in produced.spend}
    assert by_category[SpendCategory.DISCOVERY_TOKENS].cost_usd == Decimal("0.00023535")
    assert by_category[SpendCategory.DISCOVERY_TOKENS].input_tokens == 1200
    assert by_category[SpendCategory.WEB_SEARCH].cost_usd == Decimal("0.005")
    assert by_category[SpendCategory.WEB_SEARCH].units == 1


def test_the_recorded_rows_sum_to_exactly_what_the_provider_charged():
    """The ledger ties to the bill. Any other arrangement gives the month two
    answers, and the one this product would report is the one nobody reconciles."""
    produced = engine_over(responding(ANSWER)).enumerate_works(asked())

    assert sum(entry.cost_usd for entry in produced.spend) == Decimal("0.00523535")


def test_the_model_actually_used_is_attributed_the_spend():
    produced = engine_over(responding(ANSWER)).enumerate_works(asked())

    assert all(entry.model_id == "deepseek/deepseek-v4-flash" for entry in produced.spend)


# -- failures, and which one this was -------------------------------------------


def test_a_spent_key_is_reported_as_exhaustion():
    handler = lambda request: httpx.Response(403, json={"error": {"message": "Key limit exceeded (total limit)."}})  # noqa: E731

    with pytest.raises(BudgetExhausted):
        engine_over(handler).enumerate_works(asked())


def test_an_unaffordable_request_is_a_failure_but_never_exhaustion():
    """It arrives with credit still in the account. Reporting it as exhaustion
    would halt a run that can still pay, and halted-by-budget is the one state a
    curator reads as "stop asking"."""
    handler = lambda request: httpx.Response(  # noqa: E731
        402, json={"error": {"message": "This request requires more credits, or fewer max_tokens."}}
    )

    with pytest.raises(EngineFailure) as raised:
        engine_over(handler).enumerate_works(asked())

    assert not isinstance(raised.value, BudgetExhausted)


def test_a_refusal_before_generation_carries_no_spend():
    """Nothing was produced and nothing was billed, so recording a charge would
    invent one."""
    handler = lambda request: httpx.Response(403, json={"error": {"message": "Key limit exceeded."}})  # noqa: E731

    with pytest.raises(BudgetExhausted) as raised:
        engine_over(handler).enumerate_works(asked())

    assert raised.value.spend == ()


def test_an_answer_that_cannot_be_read_still_reports_what_it_cost():
    """The call was billed before anyone tried to parse it. A failure path that
    dropped the spend would under-report the month by exactly what the failures
    cost — which is why the seam's exception carries it."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "deepseek/deepseek-v4-flash",
                "choices": [{"finish_reason": "stop", "message": {"content": "not json at all"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.001, "cost_details": {}},
            },
        )

    with pytest.raises(EngineFailure) as raised:
        engine_over(handler).enumerate_works(asked())

    assert sum(entry.cost_usd for entry in raised.value.spend) == Decimal("0.001")


# -- unusable entries -----------------------------------------------------------


@pytest.mark.parametrize(
    ("entry", "why"),
    [
        ({"title": "", "artist": "A", "rationale": "r"}, "no title"),
        ({"title": "T", "artist": "A", "rationale": "  "}, "no rationale"),
    ],
)
def test_a_work_the_record_layer_would_refuse_is_dropped_not_fatal(entry, why):
    """One malformed row must not cost a run its whole list of good works.

    The record layer refuses both of these, so passing one through would fail
    the run — while dropping it keeps every real work the curator paid for.
    """
    answer = {"strategy": "s", "works": [entry, ANSWER["works"][0]]}

    produced = engine_over(responding(answer)).enumerate_works(asked())

    assert [work.title for work in produced.works] == ["Landscape"], why


def test_an_answer_naming_no_works_is_an_empty_list_not_a_failure():
    """ "Nothing matched" is a real answer to a narrow intent, and a run that
    reports it honestly is not a run that broke."""
    produced = engine_over(responding({"strategy": "Found nothing matching.", "works": []})).enumerate_works(asked())

    assert produced.works == ()
    assert produced.strategy == "Found nothing matching."


# -- availability ---------------------------------------------------------------


def test_an_engine_holding_a_client_is_available():
    """A client cannot be built without a key, so holding one is the whole test
    of readiness. The keyless case is the entry point's, not this engine's."""
    assert engine_over(responding(ANSWER)).unavailable_reason is None
