"""Whether a model can actually *use* the five-tool surface, not just read it.

This is the half of `api-contract.md` § Validation that the contract tests
cannot answer. They assert the surface's shape, and that its flows compose when
driven by code that already knows the answer. Whether five noun-shaped tools
with an `action` parameter are navigable *by a model* is an empirical question,
and the artifact is explicit that it should be measured rather than argued
about: run verifiable operator prompts against the surface and compare accuracy,
tool-call count, and error rate.

**Deselected by default, and the reason is not cost.** These calls spend real
money, but the disqualifying property is non-determinism: a model may reach the
same goal by a different route on the next run, so a pass/fail gate here would
either flake or be so loose it asserted nothing. The scripted scenarios gate;
this measures. Run it with `-m llm_eval` when the tool surface changes —
especially when a *description* changes, since that is a behavioural change no
other test in this repo can see.

The assertions are therefore about **the end state, not the route**. A model
that reaches the goal in six calls instead of four has not failed; the call
count is recorded so that a surface getting harder to navigate shows up as a
trend rather than as a surprise. What fails is not reaching the goal at all, or
failing a call and never recovering.
"""

import os

import pytest

# Before importing the driver, which pulls langchain in through 3tears.
# Deselecting by marker still *collects* this module, so without this the
# default `uv run pytest` — which does not install the eval group — would fail
# at import rather than quietly skipping, and the opt-in would not be opt-in.
pytest.importorskip(
    "threetears.models",
    reason="the evaluation dependency group is not installed — run `uv sync --group eval`",
)

from driver import REFERENCE_CALLS, drive  # noqa: E402

pytestmark = pytest.mark.llm_eval

#: Cheap and tool-capable. The point is whether the *surface* is navigable, so
#: the weakest model that can hold a tool loop is the more honest instrument: a
#: frontier model papers over a confusing surface with inference, which is
#: exactly the defect this exists to expose. Overridable, because "does the next
#: model up also manage it" is the natural follow-up question.
MODEL_ID = os.environ.get("ART_EVAL_MODEL", "google/gemini-2.5-flash-lite")

#: A model gets more room than the scripted flow needs. Reading `help` first is
#: the documented first move and costs calls; punishing that would measure
#: obedience to the reference route rather than navigability.
CALL_BUDGET = REFERENCE_CALLS * 3


@pytest.fixture
def model():
    """A chat model through 3tears, or a skip naming the piece that is missing."""
    from threetears.models import create_chat_model

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        pytest.skip("OPENROUTER_API_KEY is unset, so no model can be reached")

    # `provider` is explicit rather than inferred. 3tears resolves a provider
    # from its capabilities registry, which does not carry these OpenRouter
    # model ids — verified against 0.22.5, where `get_capabilities` returns
    # None for them and resolution would fail without this argument.
    return create_chat_model(MODEL_ID, api_key=api_key, provider="openrouter")


async def test_a_model_puts_a_named_work_on_the_wall(server_url, ready_work, display, model):
    """The same goal the scripted flow reaches, pursued from one sentence.

    The prompt names the work and the outcome and nothing else — no tool names,
    no action names, no ids. Everything needed to get from "this painting" to an
    activated theme has to come off the surface itself.
    """
    work = ready_work(title="Wheatfield with Crows")

    outcome = await drive(
        server_url,
        model,
        goal=(
            "Put the painting 'Wheatfield with Crows' on the television, on its own, "
            "in a new theme called 'Late van Gogh'. Make that theme the one currently showing."
        ),
        budget=CALL_BUDGET,
    )

    # Read back through the service, not through the tools. Asking the surface
    # whether it did what it said would let a tool that reports a change it
    # never made pass its own examination.
    themes = {theme.name: theme for theme in display.list_themes()}
    assert "Late van Gogh" in themes, f"no theme by that name was created. {outcome}"

    theme = themes["Late van Gogh"]
    assert theme.is_active, f"the theme was created but never activated. {outcome}"

    held = [entry.artwork.id for entry in display.theme_works(theme.id)]
    assert held == [work.id], f"the theme does not hold exactly that work. {outcome}"


async def test_a_model_answers_a_question_the_catalogue_can_settle(server_url, seeded_titles, model):
    """A read-only goal, and the one that most directly measures the error model.

    `envelope.py` returns failures as results rather than protocol errors
    precisely so a model can self-correct from them, and every failure carries
    the valid set, an example, and a pointer to `help`. Whether that actually
    works is not something the repo can assert about itself.
    """
    outcome = await drive(
        server_url,
        model,
        goal="How many artworks are in the catalogue, and what are their titles?",
        budget=CALL_BUDGET,
    )

    assert outcome.answered, f"the model never produced a final answer. {outcome}"

    # The titles are the verifiable part. Accuracy is the measurement here, and
    # a surface that returns them under a key a model cannot find fails this
    # while passing every shape assertion in the contract suite.
    answer = outcome.answer.lower()
    missing = [title for title in seeded_titles if title.lower() not in answer]
    assert not missing, f"the answer omitted {missing}. {outcome}"

    # Recovery, not perfection: a failed call is fine, and is what the teaching
    # error exists for. Never recovering from one is the failure.
    if outcome.transcript.failures:
        assert outcome.transcript.calls[-1].succeeded, f"a call failed and the model never got back on track. {outcome}"
