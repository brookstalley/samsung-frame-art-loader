"""The evaluation harness's own machinery, driven by a scripted model.

Unmarked and free: nothing here reaches a provider. The "model" is a stub that
emits a fixed sequence of tool calls, which makes the loop deterministic and
means these run in the ordinary suite whenever the eval group is installed.

They exist because the driver is code this repo wrote, and the first real run
is the worst possible place to discover a bug in it — a failure there is
ambiguous between "the surface is hard to navigate", which is the finding the
evaluation is for, and "the loop is broken", which is not a finding at all.
Everything the driver does that is not the model's doing is pinned here: that
the tools handed over are the server's own, that calls reach the real service
layer, that the transcript records them, that a bad tool name is survived, and
that a looping model is stopped.
"""

import pytest

pytest.importorskip(
    "langchain_core",
    reason="the evaluation dependency group is not installed — run `uv sync --group eval`",
)

from driver import drive  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402


class ScriptedModel:
    """A stand-in for a chat model that replays a fixed list of turns.

    Mirrors only the surface `drive` uses: `bind_tools` returns something with
    `ainvoke`. It records what it was offered, so a test can assert the driver
    handed over the server's real definitions rather than a reconstruction.
    """

    def __init__(self, turns):
        self._turns = list(turns)
        self.offered_tools = None
        self.prompts = []

    def bind_tools(self, tools):
        self.offered_tools = tools
        return self

    async def ainvoke(self, messages):
        self.prompts.append(messages)
        if not self._turns:
            return AIMessage(content="I have run out of scripted turns.")
        return self._turns.pop(0)


def _call(name, args, call_id="c1"):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}])


async def test_the_model_is_offered_the_servers_own_tool_definitions(server_url):
    """Not a reconstruction. A description edit has to reach the model."""
    model = ScriptedModel([AIMessage(content="Nothing to do.")])

    await drive(server_url, model, goal="Say nothing.", budget=4)

    offered = {tool["function"]["name"]: tool["function"] for tool in model.offered_tools}
    assert set(offered) == {"art_catalogue", "art_discovery", "art_display", "art_review", "art_theme"}

    # The description is the server's, carried through untouched — this is the
    # property that makes the evaluation able to see description drift at all.
    from curation.mcp import registry
    from curation.mcp.tools import TOOLS_BY_NAME

    assert offered["art_theme"]["description"] == registry.description(TOOLS_BY_NAME["art_theme"])
    assert offered["art_theme"]["parameters"] == registry.input_schema(TOOLS_BY_NAME["art_theme"])


async def test_a_tool_call_reaches_the_real_service_and_is_recorded(server_url, ready_work):
    """The loop's actual work: execute, feed the result back, record the call."""
    work = ready_work(title="The Starry Night")
    model = ScriptedModel([_call("art_catalogue", {"action": "list"}), AIMessage(content="One work.")])

    outcome = await drive(server_url, model, goal="List the works.", budget=4)

    assert outcome.transcript.steps == ["art_catalogue(action='list')"]
    assert not outcome.transcript.failures
    assert outcome.answer == "One work."

    # The result was fed back rather than dropped — the model's second turn saw
    # a tool message carrying the payload, which is what lets it answer at all.
    fed_back = str(model.prompts[-1])
    assert work.id in fed_back
    assert "The Starry Night" in fed_back


async def test_a_failing_call_is_recorded_and_the_run_continues(server_url):
    """A model's bad action is a measurement, not a crash."""
    model = ScriptedModel(
        [
            _call("art_theme", {"action": "sculpt"}),
            _call("art_theme", {"action": "list"}, call_id="c2"),
            AIMessage(content="Recovered."),
        ]
    )

    outcome = await drive(server_url, model, goal="List the themes.", budget=6)

    assert [call.succeeded for call in outcome.transcript.calls] == [False, True]
    assert len(outcome.transcript.failures) == 1
    assert outcome.answer == "Recovered."


async def test_a_tool_name_that_does_not_exist_is_survived(server_url):
    """The one failure the surface cannot answer with a teaching error."""
    model = ScriptedModel([_call("art_frame", {"action": "list"}), AIMessage(content="That tool is not there.")])

    outcome = await drive(server_url, model, goal="Use a tool that does not exist.", budget=4)

    assert len(outcome.transcript.calls) == 1
    assert outcome.transcript.calls[0].succeeded is False
    assert outcome.answered, "the run did not survive an unknown tool name"


async def test_a_looping_model_is_stopped_at_the_budget(server_url):
    """The failure a confusing surface provokes, and it must not hang the suite."""
    model = ScriptedModel([_call("art_catalogue", {"action": "list"}, call_id=f"c{n}") for n in range(20)])

    outcome = await drive(server_url, model, goal="Loop forever.", budget=3)

    assert outcome.stopped_on_budget
    assert len(outcome.transcript.calls) <= 3
    assert "STOPPED" in str(outcome)
