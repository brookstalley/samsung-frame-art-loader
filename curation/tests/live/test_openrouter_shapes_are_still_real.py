"""The recorded API findings, as a test rather than as prose.

`openrouter-api-findings.md` is a snapshot of a live probe. Prices and endpoint
shapes both move, and a document nobody re-runs quietly stops describing the
provider — so the durable form of a verification worth writing down is a test
that fails when the fact stops holding.

**Deselected by default.** These calls cost real money on the configured key and
need the network, so nothing in an ordinary run touches them. Run deliberately:

    uv run pytest -m live_api

Each test names the client behaviour that would break if its fact changed, so a
failure here reads as "the provider moved, and here is what now mis-parses"
rather than as an unexplained red.
"""

import os
from decimal import Decimal

import pytest

from curation.config import DEFAULT_DISCOVERY_MODEL, DEFAULT_DISCOVERY_SEARCH_ENGINE, DEFAULT_SEARCH_COST_USD
from curation.discovery.engine import WorkListRequest
from curation.discovery.openrouter import OpenRouterClient
from curation.discovery.phase_one import build_engine
from curation.persistence.discovery_records import InitiatedBy, RunStatus
from curation.services.runner import DiscoveryRunner

pytestmark = pytest.mark.live_api

KEY = os.environ.get("OPENROUTER_API_KEY")
needs_key = pytest.mark.skipif(not KEY, reason="OPENROUTER_API_KEY is not set")


@pytest.fixture(scope="module")
def client() -> OpenRouterClient:
    """Configured exactly as a deployment is, engine included.

    The engine is not incidental to what this file checks. Search bills per
    back-end, so a client left on the provider's default would measure a fee the
    product does not pay and report the price check green while the configured
    engine's price had moved.
    """
    return OpenRouterClient(
        KEY or "",
        model=DEFAULT_DISCOVERY_MODEL,
        max_output_tokens=2000,
        search_engine=DEFAULT_DISCOVERY_SEARCH_ENGINE,
    )


@needs_key
def test_a_generation_still_reports_its_own_cost_inline(client):
    """The client reads `usage.cost` from the completion itself.

    If this stopped arriving, per-run actual spend would have to be computed as
    tokens times a price table — the one arithmetic that omits the search fee,
    which is the component that can roughly double a run.
    """
    completion = client.complete(prompt="Reply with the single word: ready.")

    assert completion.cost_usd > 0, "no cost came back inline; the ledger would have to be computed"
    assert isinstance(completion.cost_usd, Decimal)
    assert completion.input_tokens > 0 and completion.output_tokens > 0
    assert completion.model_id


@needs_key
def test_the_web_fee_is_charged_per_request_and_not_per_result(client):
    """Breadth is free, which is why the engine asks for ten results.

    Two calls differing only in `max_results` must cost the same to search. If
    the fee ever starts scaling with results, this is the assumption behind
    `DISCOVERY_SEARCH_RESULTS` — and behind the per-run search cap's sizing —
    and it would need revisiting rather than silently costing more.
    """
    narrow = client.complete(prompt="Name one art prize awarded in 2026.", search_results=1)
    wide = client.complete(prompt="Name one art prize awarded in 2026.", search_results=10)

    assert narrow.searched and wide.searched, "no search ran, so this compared nothing"
    assert narrow.search_cost_usd == wide.search_cost_usd, (
        f"the search fee now scales with max_results ({narrow.search_cost_usd} vs {wide.search_cost_usd}); "
        "the per-run search cap is sized against a flat per-request fee"
    )
    assert narrow.search_cost_usd == Decimal(DEFAULT_SEARCH_COST_USD), (
        f"the per-search price moved from the configured {DEFAULT_SEARCH_COST_USD} to {narrow.search_cost_usd}; "
        "DISCOVERY_SEARCH_COST_USD and the recorded cost analysis both describe the old one"
    )


@needs_key
def test_a_search_returns_citations_carrying_their_excerpts(client):
    """Citations are how the client knows a search ran, rather than inferring it
    from a non-zero fee — and the excerpt is what makes a work traceable."""
    completion = client.complete(prompt="Name one art prize awarded in 2026.", search_results=5)

    assert completion.searched
    assert completion.citations, "annotations are the signal that a search happened"
    assert all(citation.url for citation in completion.citations)
    assert any(citation.content for citation in completion.citations)


@needs_key
def test_the_key_reports_a_monthly_ceiling(client):
    """The ceiling is this key's own setting — the product enforces nothing.

    An uncapped key would mean there is no spend limit at all, which is a
    deployment fault this is the only mechanical check for.
    """
    status = client.key_status()

    assert status.limit_usd is not None, "the key is UNCAPPED: the product's entire spend ceiling is missing"
    assert status.resets == "monthly", f"the key's limit resets {status.resets!r}, not monthly"
    assert status.remaining_usd is not None


@needs_key
def test_the_default_model_still_exists_and_takes_a_strict_schema(client):
    """The engine depends on strict structured output to parse without defending
    against prose. A model that stopped honouring it would fail every run."""
    completion = client.complete(
        prompt="Name one famous painting.",
        schema={
            "type": "object",
            "properties": {"title": {"type": "string"}},
            "required": ["title"],
            "additionalProperties": False,
        },
    )

    import json

    assert json.loads(completion.content)["title"]


@needs_key
def test_a_recency_bound_intent_resolves_to_real_post_cutoff_works():
    """The whole reason phase 1 searches, end to end through the real engine.

    A text-only call answers this from before the model's cutoff and says so
    confidently. That failure is invisible in the result — the works are real,
    merely old — so it is worth an explicit check that searching changed the
    answer rather than merely cost money.
    """
    engine = build_engine(KEY or "", model=DEFAULT_DISCOVERY_MODEL, max_output_tokens=8000, search_results=10)

    produced = engine.enumerate_works(WorkListRequest(intent_text="recent award-winning art", search_allowance=10))

    assert produced.works, "phase 1 found nothing at all"
    assert produced.strategy, "the run has no account of how it read the intent"
    assert produced.searches_used == 1
    assert all(work.title and work.rationale for work in produced.works)
    # The point of searching: at least one work whose reason cites a year past
    # the model's training cutoff. Without the web plugin this model answers
    # with 2022-2024 winners and describes them as recent.
    assert any("2026" in work.rationale or "2025" in work.rationale for work in produced.works), (
        "no proposed work cites a post-cutoff year, which is what searching is for: "
        f"{[work.rationale for work in produced.works]}"
    )


# -- the ceiling, proven rather than assumed ------------------------------------

#: A key deliberately burned to its limit, kept exhausted so the refusal path can
#: be driven for real. `OPENROUTER_THROWAWY_KEY` is the historical name of the
#: same key and is accepted so an already-provisioned environment works unchanged.
EXHAUSTED = os.environ.get("OPENROUTER_EXHAUSTED_KEY") or os.environ.get("OPENROUTER_THROWAWY_KEY")


@pytest.mark.skipif(not EXHAUSTED, reason="no exhausted key provisioned")
def test_a_spent_key_halts_a_real_run_for_budget(services, settings):
    """The product's most important safety property, end to end.

    The ceiling is a provider-side credit limit and nothing in this repository
    enforces it, so "it fails closed" is a claim about how a real refusal
    travels: provider 403 → `KeyExhausted` → `BudgetExhausted` → a run recorded
    as `halted_by_budget`. Every link is unit-tested; this drives all of them
    against a key that is genuinely out of money.

    Distinguishable from a failed run by design — an agent that could not tell
    them apart would keep paying to be told it has no money.
    """
    engine = build_engine(EXHAUSTED, model=DEFAULT_DISCOVERY_MODEL, max_output_tokens=2000, search_results=10)
    runner = DiscoveryRunner(services.discovery, engine, settings.discovery_settings, spawn=lambda work: work())

    run = runner.start(intent_text="anything at all", initiated_by=InitiatedBy.MCP_CLIENT)

    settled = services.discovery.get_run(run.id)
    assert settled.status is RunStatus.HALTED_BY_BUDGET, f"a spent key left the run {settled.status}"
    assert settled.status.is_terminal, "a halted run must not look like one still working"


@pytest.mark.skipif(not EXHAUSTED, reason="no exhausted key provisioned")
def test_a_spent_key_records_no_spend_because_nothing_was_generated(services, settings):
    """The refusal arrives before any tokens exist, so a charge would be invented."""
    engine = build_engine(EXHAUSTED, model=DEFAULT_DISCOVERY_MODEL, max_output_tokens=2000, search_results=10)
    runner = DiscoveryRunner(services.discovery, engine, settings.discovery_settings, spawn=lambda work: work())

    run = runner.start(intent_text="anything at all", initiated_by=InitiatedBy.MCP_CLIENT)

    assert services.discovery.run_cost(run.id).direct == Decimal(0)
