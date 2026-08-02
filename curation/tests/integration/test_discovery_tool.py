"""The discovery surface, driven by a real MCP client over real HTTP.

Entered through the tool rather than the service on purpose. Every behaviour
below has service-level tests that would pass with the binding deleted — the
question here is whether anything actually calls them, which is the shape of
defect where a fully tested feature does nothing at all.

**This is also where the threaded path is exercised.** The unit suite runs phase
1 on the calling thread, deliberately; a handle that must come back inside two
seconds while the work goes on behind it is not a claim a synchronous test can
check, and neither is a status call that holds until there is something to say.
"""

import asyncio
import json
import time

import pytest
from fakes import a_work_list, spent, works

from curation.discovery.engine import BudgetExhausted, WorkList
from curation.persistence.discovery_records import RunStatus


async def call(server_url: str, tool: str, **arguments) -> tuple[dict, bool]:
    """Call a tool over real HTTP; return its payload and the protocol's error flag."""
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async with streamable_http_client(f"{server_url}/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool, arguments)
    return json.loads(result.content[0].text), bool(result.isError)


async def a_run(server_url, intent="Surrealist paintings with strong blues") -> str:
    payload, errored = await call(server_url, "art_discovery", action="start", intent=intent)
    assert errored is False, payload
    return payload["run_id"]


async def settled(server_url, run_id: str) -> dict:
    """Poll until the run is no longer being worked on, then return its status.

    Uses the surface's own long-poll rather than a sleep, which is what a client
    does — and what makes this a test of the hold rather than a test that waiting
    long enough eventually works.
    """
    for _ in range(5):
        payload, _errored = await call(server_url, "art_discovery", action="status", run_id=run_id)
        if payload["status"] not in {RunStatus.RESOLVING_WORKS, RunStatus.RESOLVING_IMAGES}:
            return payload
        if payload["status"] == RunStatus.RESOLVING_IMAGES:
            return payload
    raise AssertionError(f"run {run_id} never settled: {payload}")


# -- the surface is live ---------------------------------------------------------


async def test_every_declared_action_is_reachable_over_the_wire(server_url):
    """The tool is no longer a reserved name answering only `help`.

    Derived from the registry rather than typed out: a list written by hand is
    complete on the day it is written and green forever after, including the day
    a ninth action arrives with nothing exercising it.
    """
    from curation.mcp.registry import HELP_ACTION
    from curation.mcp.tools import ART_DISCOVERY

    payload, errored = await call(server_url, "art_discovery", action=HELP_ACTION)

    assert errored is False
    assert payload["available"] is True
    assert payload["note"] is None
    declared = {action["action"] for action in payload["actions"]}
    assert declared == set(ART_DISCOVERY.action_names)
    assert "resolve_images" not in declared, "a re-search is not built; advertising it would be a promise"


async def test_a_start_returns_a_handle_rather_than_a_result(server_url, engine):
    """Well inside the two seconds the contract allows, and not by being fast.

    The gate holds phase 1 open, so a `start` that waited for the work could not
    return at all — which is what makes this a test of the handle rather than of
    a quick fake.
    """
    import threading

    engine.gate = threading.Event()
    try:
        began = time.monotonic()
        payload, errored = await call(server_url, "art_discovery", action="start", intent="Dutch still life")
        elapsed = time.monotonic() - began

        assert errored is False
        assert payload["run_id"]
        assert payload["status"] == RunStatus.RESOLVING_WORKS
        assert elapsed < 2.0, "a discovery call must return its handle immediately"
        assert "status" in payload["notice"], "the handle should say how to follow the run"
    finally:
        engine.gate.set()


async def test_status_holds_while_a_run_is_being_worked_on_and_answers_when_it_changes(server_url, engine):
    """The long-poll is what keeps a client from polling in a tight loop."""
    import threading

    engine.gate = threading.Event()
    run_id = await a_run(server_url)

    async def release_shortly() -> None:
        await asyncio.sleep(0.3)
        engine.gate.set()

    began = time.monotonic()
    held, released = await asyncio.gather(
        call(server_url, "art_discovery", action="status", run_id=run_id),
        release_shortly(),
    )
    elapsed = time.monotonic() - began

    payload, errored = held
    assert errored is False
    # It waited for the change rather than answering "still working" at once,
    # and it did not sit out the full hold once the change arrived.
    assert 0.3 <= elapsed < 20.0, f"status returned after {elapsed:.2f}s"
    assert payload["status"] != RunStatus.RESOLVING_WORKS


async def test_status_on_a_run_that_is_waiting_for_a_person_answers_at_once(server_url, engine):
    """Holding there would make a caller wait to be told a thing that was
    already true and was not going to change on its own."""
    engine.result = a_work_list(26)
    run_id = await a_run(server_url)
    await settled(server_url, run_id)

    began = time.monotonic()
    payload, _ = await call(server_url, "art_discovery", action="status", run_id=run_id)

    assert payload["status"] == RunStatus.AWAITING_APPROVAL
    assert time.monotonic() - began < 5.0


# -- the gate --------------------------------------------------------------------


async def test_a_run_crosses_the_gate_at_the_configured_threshold_and_waits(server_url, engine):
    """Twenty-six works against a threshold of twenty-five stops for approval."""
    engine.result = a_work_list(26)
    run_id = await a_run(server_url)

    payload = await settled(server_url, run_id)

    assert payload["status"] == RunStatus.AWAITING_APPROVAL
    assert payload["approval_required"] is True
    assert payload["works"]["total"] == 26
    assert "more than the configured threshold" in payload["notice"]
    # The figure the gate is authorising against is on the record, not
    # recomputed when somebody asks.
    assert payload["estimated_cost_usd"] == "0.260"


async def test_a_run_inside_the_threshold_does_not_stop_to_ask(server_url, engine):
    engine.result = a_work_list(25)
    run_id = await a_run(server_url)

    payload = await settled(server_url, run_id)

    assert payload["status"] == RunStatus.RESOLVING_IMAGES
    assert payload["approval_required"] is False


async def test_a_waiting_run_can_be_approved_over_the_surface(server_url, engine):
    engine.result = a_work_list(26)
    run_id = await a_run(server_url)
    await settled(server_url, run_id)

    payload, errored = await call(server_url, "art_discovery", action="approve", run_id=run_id)

    assert errored is False
    assert payload["status"] == RunStatus.RESOLVING_IMAGES


async def test_a_waiting_run_can_be_declined_and_nothing_further_is_spent(server_url, engine):
    engine.result = a_work_list(26)
    run_id = await a_run(server_url)
    await settled(server_url, run_id)
    before, _ = await call(server_url, "art_discovery", action="spend", run_id=run_id)

    payload, errored = await call(server_url, "art_discovery", action="decline", run_id=run_id)
    after, _ = await call(server_url, "art_discovery", action="spend", run_id=run_id)

    assert errored is False
    assert payload["status"] == RunStatus.DECLINED
    assert after["cost_usd"] == before["cost_usd"]


async def test_a_run_can_be_cancelled_and_says_its_spend_is_kept(server_url, engine):
    engine.result = a_work_list(26)
    run_id = await a_run(server_url)
    await settled(server_url, run_id)

    payload, errored = await call(server_url, "art_discovery", action="cancel", run_id=run_id)

    assert errored is False
    assert payload["status"] == RunStatus.CANCELLED
    assert "still recorded" in payload["notice"] or payload["actual_cost_usd"] is not None


# -- an agent can tell the endings apart -----------------------------------------


@pytest.mark.parametrize(
    ("outcome", "expected", "must_say"),
    [
        ("halted", RunStatus.HALTED_BY_BUDGET, "not a transient error"),
        ("failed", RunStatus.FAILED, "worth investigating"),
        ("interrupted", RunStatus.INTERRUPTED, "nothing to investigate"),
    ],
)
async def test_the_three_bad_endings_are_distinguishable_by_returned_state_alone(
    server_url, services, engine, outcome, expected, must_say
):
    """Out of money, broken, and restarted underneath it are three things.

    The correct response to each differs — stop, investigate, and simply run it
    again — so an agent that could not tell them apart would either retry a real
    fault forever or escalate a routine deploy restart as a bug.
    """
    if outcome == "halted":
        engine.error = BudgetExhausted("The provider returned 402.", spend=spent())
        run_id = await a_run(server_url)
        payload = await settled(server_url, run_id)
    elif outcome == "failed":
        engine.error = RuntimeError("the model returned something unparseable")
        run_id = await a_run(server_url)
        payload = await settled(server_url, run_id)
    else:
        # A run whose process stopped underneath it: left mid-flight, then found
        # by the reconciliation a restart runs. That is the only signal a run
        # died, because a dying process cannot report its own death.
        import threading

        engine.gate = threading.Event()
        run_id = await a_run(server_url)
        services.reconcile()
        engine.gate.set()
        payload, _ = await call(server_url, "art_discovery", action="status", run_id=run_id)

    assert payload["status"] == expected
    assert payload["success"] is True, "a run that ended badly is still a successful read of that run"
    assert must_say in payload["notice"]


# -- estimate and spend -----------------------------------------------------------


async def test_estimate_answers_two_different_questions_by_arity(server_url, engine):
    engine.result = a_work_list(26)

    asking, errored = await call(server_url, "art_discovery", action="estimate")
    assert errored is False
    assert asking["phase"] == "phase_1"
    assert asking["run_id"] is None
    # One model call at the shipped prices plus the whole ten-search allowance.
    assert asking["estimated_cost_usd"] == "0.127"

    run_id = await a_run(server_url)
    await settled(server_url, run_id)
    resolving, errored = await call(server_url, "art_discovery", action="estimate", run_id=run_id)

    assert errored is False
    assert resolving["phase"] == "phase_2"
    assert resolving["run_id"] == run_id
    assert resolving["estimated_cost_usd"] == "0.260"


async def test_estimating_is_the_one_action_that_spends_nothing(server_url):
    payload, _ = await call(server_url, "art_discovery", action="estimate")
    month_before, _ = await call(server_url, "art_discovery", action="spend")

    await call(server_url, "art_discovery", action="estimate")
    month_after, _ = await call(server_url, "art_discovery", action="spend")

    assert "spend" in payload["notice"]
    assert month_after["cost_usd"] == month_before["cost_usd"]


async def test_spend_reports_a_run_and_a_month(server_url):
    run_id = await a_run(server_url)
    await settled(server_url, run_id)

    per_run, errored = await call(server_url, "art_discovery", action="spend", run_id=run_id)
    assert errored is False
    assert per_run["scope"] == "run"
    # The fake charges $0.08 of tokens and one search at $0.005.
    assert per_run["cost_usd"] == "0.085"
    assert per_run["run_direct_cost_usd"] == "0.085"

    per_month, errored = await call(server_url, "art_discovery", action="spend")
    assert errored is False
    assert per_month["scope"] == "month"
    assert per_month["cost_usd"] == "0.085"


async def test_spend_refuses_a_run_and_a_month_at_once_rather_than_choosing(server_url):
    run_id = await a_run(server_url)

    payload, errored = await call(server_url, "art_discovery", action="spend", run_id=run_id, year=2026, month=8)

    assert errored is True
    assert "one run or about one month" in payload["error"]


# -- the search cap ---------------------------------------------------------------


async def test_a_run_reports_what_it_used_of_its_search_allowance(server_url, engine):
    engine.result = WorkList(works=works(4), spend=spent(searches=6))
    run_id = await a_run(server_url)

    payload = await settled(server_url, run_id)

    assert payload["searches"]["used"] == 6
    # Ten flat for phase 1, plus two per work for the four works it found.
    assert payload["searches"]["allowance"] == 18
    assert payload["searches"]["exhausted"] is False


async def test_an_engine_that_overran_its_allowance_is_a_failure_not_a_footnote(server_url, engine):
    """The cap is what makes a pre-run estimate a bound rather than a guess."""
    engine.result = WorkList(works=works(3), spend=spent(searches=11))
    run_id = await a_run(server_url)

    payload = await settled(server_url, run_id)

    assert payload["status"] == RunStatus.FAILED
    assert payload["works"]["total"] == 0
    # The searches were made and billed, whether or not their results were kept.
    assert payload["searches"]["used"] == 11


# -- listing ----------------------------------------------------------------------


async def test_runs_can_be_listed_and_narrowed_to_one_state(server_url, engine):
    engine.result = a_work_list(26)
    waiting = await a_run(server_url, intent="Surrealists")
    await settled(server_url, waiting)

    engine.result = a_work_list(2)
    small = await a_run(server_url, intent="Dutch still life")
    await settled(server_url, small)

    everything, errored = await call(server_url, "art_discovery", action="list_runs")
    assert errored is False
    assert everything["count"] == 2

    narrowed, errored = await call(server_url, "art_discovery", action="list_runs", status="awaiting_approval")
    assert errored is False
    assert [run["run_id"] for run in narrowed["runs"]] == [waiting]
    assert narrowed["runs"][0]["intent"] == "Surrealists"


async def test_an_unknown_run_state_is_refused_with_the_valid_set(server_url):
    payload, errored = await call(server_url, "art_discovery", action="list_runs", status="nearly_done")

    assert errored is True
    assert "awaiting_approval" in json.dumps(payload["valid_values"])


# -- correlation -------------------------------------------------------------------


async def test_a_line_emitted_inside_a_run_carries_that_runs_id(server_url, runner, services, engine, caplog):
    """The correlation key reaches the journal through the real code path.

    Driven through the runner rather than by binding the context by hand,
    because what is being checked is that the plane's own logging *is* bound —
    a test that set the context itself would prove only that the filter works.
    """
    import logging

    from curation.logs import RunCorrelationFilter
    from curation.persistence.discovery_records import InitiatedBy

    caplog.handler.addFilter(RunCorrelationFilter())
    with caplog.at_level(logging.INFO):
        run = runner.start(intent_text="Surrealist paintings", initiated_by=InitiatedBy.MCP_CLIENT)

    correlated = [record for record in caplog.records if getattr(record, "run_id", None) == run.id]
    assert correlated, "no log line carried the run id"
    assert {getattr(record, "event", None) for record in correlated} >= {"run.started", "run.work_list_ready"}
