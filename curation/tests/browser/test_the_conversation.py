"""The conversation screen, in a real browser, against a real server.

Two behaviours here are the chunk's own acceptance criteria and neither is
visible to a test that reads JSON:

- **committing a direction never navigates.** The commit card becomes the
  search's progress card and then becomes "N works ready to review", in place,
  with the transcript above it the whole time. A commit that navigated would
  turn the conversation into a wizard wearing a costume, and every route
  involved would still answer correctly.
- **a failed turn stays in the thread and is retryable.** The failure arrives as
  a 200 carrying the thread, so what is under test is that the client renders the
  question, says why it has no answer, and offers a way to ask again.

Routes are stubbed rather than seeded, per this suite's rule: the states worth
pinning here — a search that is mid-flight and then finished, a turn the model
refused and then answered — are ones a real server cannot be asked for on
purpose. The payloads are built from the API's own response models.
"""

import pytest
from payloads import (
    a_candidate,
    a_conversation_list,
    a_run,
    a_run_view,
    a_sample,
    a_suggestion,
    a_thread,
    a_turn,
    an_estimate,
)

from curation.persistence.discovery_records import RunStatus, TurnRole

CONVERSATION = "conversation-under-test"
RUN = "run-from-a-conversation"


def a_question(**overrides):
    return a_turn("Something calm for the living room.", turn_id="turn-1", ordinal=0, **overrides)


def an_answer(**overrides):
    fields = {
        "turn_id": "turn-2",
        "ordinal": 1,
        "role": TurnRole.SYSTEM.value,
        "suggested": [a_suggestion("Agnes Martin", samples=[a_sample("Untitled No. 5")])],
    }
    return a_turn("Agnes Martin's pale grids would hold that stillness.", **(fields | overrides))


def a_commit(**overrides):
    fields = {"turn_id": "turn-3", "ordinal": 2, "role": TurnRole.CURATOR.value, "committed_run_id": RUN}
    return a_turn("Agnes Martin", **(fields | overrides))


@pytest.fixture
def talking(ui):
    """A conversation with one question, one answer, and a picture to show."""
    ui.serve("**/api/estimate*", an_estimate())
    ui.serve("**/api/conversations", a_conversation_list())
    ui.serve(f"**/api/conversations/{CONVERSATION}", a_thread([a_question(), an_answer()]))
    return ui


def open_thread(ui) -> None:
    ui.open(f"#conversation/{CONVERSATION}")
    ui.page.wait_for_selector("#commit-card")


def test_the_thread_shows_what_was_said_and_a_picture_for_what_was_named(talking):
    talking.serve_image("**/iiif/**")
    open_thread(talking)

    assert "Something calm for the living room." in talking.text()
    assert "Agnes Martin's pale grids" in talking.text()
    assert "Untitled No. 5" in talking.text()
    # The picture actually decodes. A card whose `<img>` fails silently paints a
    # blank box, which is indistinguishable from a sample that carried no image
    # — a gap this suite has been burned by before.
    assert talking.page.evaluate("() => { const i = document.querySelector('.sample img'); return i.naturalWidth; }") > 0


def test_committing_a_direction_transforms_the_card_in_place(talking):
    """The chunk's hard requirement, asserted as the thing that could break it.

    The address, the view and the transcript are all checked *after* the commit,
    because every one of them survives if — and only if — the commit painted
    rather than navigated.
    """
    talking.serve(
        f"**/api/conversations/{CONVERSATION}/commit",
        a_thread([a_question(), an_answer(), a_commit()]),
    )
    # The thread as the server would answer it after the commit landed, from the
    # second read on. Without this the poll would fetch a conversation that never
    # committed anything and the card would fall back to the offer — which is
    # what a server would only ever do if the commit had not been written.
    talking.serve(
        f"**/api/conversations/{CONVERSATION}",
        [a_thread([a_question(), an_answer()]), a_thread([a_question(), an_answer(), a_commit()])],
    )
    talking.serve(
        f"**/api/runs/{RUN}",
        [
            a_run_view(a_run(run_id=RUN, status=RunStatus.RESOLVING_WORKS.value, intent="Agnes Martin")),
            a_run_view(
                a_run(run_id=RUN, status=RunStatus.COMPLETED.value, is_terminal=True, intent="Agnes Martin"),
                works=[a_candidate()],
            ),
        ],
    )
    open_thread(talking)
    before = talking.page.url

    talking.page.click("text=Search for this")
    talking.page.wait_for_selector("text=Working out which works match this direction")

    # Still here: same address, same screen, same transcript above the card.
    assert talking.page.url == before
    assert talking.page.evaluate("() => state.view") == "conversation"
    assert "Something calm for the living room." in talking.text()
    assert (
        talking.page.evaluate(
            "() => { const t = document.getElementById('thread'), c = document.getElementById('commit-card');"
            " return t.compareDocumentPosition(c) & Node.DOCUMENT_POSITION_FOLLOWING ? 'card below' : 'card above'; }"
        )
        == "card below"
    )

    # And the same card becomes the finished one, still without moving.
    talking.page.wait_for_selector("text=ready to review", timeout=10_000)
    assert talking.page.url == before
    assert talking.page.evaluate("() => state.view") == "conversation"
    assert "Something calm for the living room." in talking.text()


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (RunStatus.AWAITING_APPROVAL, "This search proposed 1 work, which is more than the threshold"),
        (RunStatus.RESOLVING_IMAGES, "The list of 1 work is settled"),
        (RunStatus.COMPLETED, "1 work is ready to review"),
    ],
)
def test_the_commit_card_agrees_with_itself_at_a_count_of_one(talking, status, expected):
    """The fifth surface that says this, and the one #113 did not name.

    The issue listed four — the run view, the MCP notice, the runner's estimate
    and the manifest summary — and this card is a fifth, composing its own
    sentences from the same tally.

    **All three of the card's counted sentences, because only two of them were
    broken.** The `completed` sentence already carried a working ternary; the
    `awaiting_approval` and `resolving_images` ones hard-coded the plural, and
    they are the lines the fix changed. A first version of this test asserted
    only the `completed` one — pinning the branch that was already right, while
    its docstring claimed to be the reason the defect was gone. Reverting either
    real fix left it green.

    `awaiting_approval` is reachable at one work: `config.py` permits an
    `approval_threshold` of zero.
    """
    talking.serve(
        f"**/api/conversations/{CONVERSATION}/commit",
        a_thread([a_question(), an_answer(), a_commit()]),
    )
    talking.serve(
        f"**/api/conversations/{CONVERSATION}",
        [a_thread([a_question(), an_answer()]), a_thread([a_question(), an_answer(), a_commit()])],
    )
    talking.serve(
        f"**/api/runs/{RUN}",
        a_run_view(
            a_run(
                run_id=RUN,
                status=status.value,
                is_terminal=status is RunStatus.COMPLETED,
                intent="Agnes Martin",
            ),
            works=[a_candidate()],
        ),
    )
    open_thread(talking)
    talking.page.click("text=Search for this")

    talking.page.wait_for_selector(f"text={expected}")
    assert "1 works" not in talking.text()


def test_the_commit_card_offers_a_direction_before_anything_is_committed(talking):
    open_thread(talking)

    card = talking.page.inner_text("#commit-card")
    # The direction is in the field rather than in the card's text, because it is
    # editable: what would be searched for is the curator's decision, and a card
    # that only printed it would be asking them to approve something they cannot
    # change.
    assert talking.page.input_value("#direction") == "Agnes Martin"
    # The bound, said as a bound. A price a search may exceed is not a price.
    assert "Searching costs at most $" in card


def test_a_failed_turn_stays_in_the_thread_and_can_be_asked_again(ui):
    """The failure is rendered from the 200 that carries it, and never lost.

    The second answer proves the retry actually happened: an "Ask again" that
    only cleared the message would leave the same screen behind.
    """
    ui.serve("**/api/estimate*", an_estimate())
    ui.serve("**/api/conversations", a_conversation_list())
    ui.serve(f"**/api/conversations/{CONVERSATION}", a_thread([a_question()]))
    ui.serve(
        f"**/api/conversations/{CONVERSATION}/turns",
        [
            a_thread(
                [a_question()],
                failure="OpenRouter returned HTTP 400: Provider returned error: the content field is required.",
            ),
            a_thread([a_question(), an_answer()]),
        ],
    )
    open_thread(ui)

    ui.page.click("text=Say it")
    # Waited on the reason, not on the bare live region. This thread opens on a
    # question nothing has answered, so the unanswered panel — `role="alert"`,
    # "Ask again" and all — is on the page *before* the click; a wait on the role
    # alone therefore returns without the POST having been answered, and the
    # assertions below read the screen as it was beforehand. It passed for as
    # long as the fetch happened to win that race and stopped the day a heavier
    # test ran ahead of it. The `role` stays in the selector because announcing
    # the reason, rather than only showing it, is half of what this pins.
    ui.page.wait_for_selector("#view [role=alert]:has-text('the content field is required')")

    # The question is still on screen, the reason is stated, and there is a way on.
    assert "Something calm for the living room." in ui.text()
    assert "the content field is required" in ui.text()
    assert ui.page.is_visible("text=Ask again")

    ui.page.click("text=Ask again")
    ui.page.wait_for_selector("text=Agnes Martin's pale grids")
    assert not ui.page.is_visible("text=Ask again")


def test_asking_again_sends_no_text_of_its_own(ui):
    """Retrying asks for the answer, never re-sends the question.

    This is the whole of the client's half of not double-spending: a retry that
    posted the text again would append a second copy of the question and buy a
    second answer for it.
    """
    ui.serve("**/api/estimate*", an_estimate())
    ui.serve("**/api/conversations", a_conversation_list())
    ui.serve(f"**/api/conversations/{CONVERSATION}", a_thread([a_question()], failure=None))
    ui.serve(f"**/api/conversations/{CONVERSATION}/turns", a_thread([a_question(), an_answer()]))
    sent: list[str] = []
    ui.page.on("request", lambda request: sent.append(request.post_data or "") if request.method == "POST" else None)
    open_thread(ui)

    ui.page.click("text=Ask again")
    ui.page.wait_for_selector("text=Agnes Martin's pale grids")

    assert sent == ["{}"]


def test_a_poll_that_changes_nothing_leaves_the_focus_alone(talking):
    """Binding on every live region this product adds, and this is one.

    A repaint replaces the whole subtree, so a keyboard user standing on a
    control loses it — every two seconds, on the screen whose whole job is to be
    watched.
    """
    talking.serve(
        f"**/api/conversations/{CONVERSATION}",
        a_thread([a_question(), an_answer(), a_commit()]),
    )
    talking.serve(
        f"**/api/runs/{RUN}",
        a_run_view(a_run(run_id=RUN, status=RunStatus.RESOLVING_WORKS.value, intent="Agnes Martin")),
    )
    open_thread(talking)
    talking.page.focus("#say")

    talking.page.wait_for_timeout(5_000)

    assert talking.focused() == "say"
    # And the polls genuinely happened — a screen that stopped watching would
    # pass the focus assertion for the wrong reason.
    assert len(talking.requests_matching(f"/api/runs/{RUN}")) >= 3


def test_a_finished_search_stops_being_watched(talking):
    """Polling is driven by the server's own `is_terminal`, never by a status list."""
    talking.serve(
        f"**/api/conversations/{CONVERSATION}",
        a_thread([a_question(), an_answer(), a_commit()]),
    )
    talking.serve(
        f"**/api/runs/{RUN}",
        a_run_view(
            a_run(run_id=RUN, status=RunStatus.COMPLETED.value, is_terminal=True, intent="Agnes Martin"),
            works=[a_candidate()],
        ),
    )
    open_thread(talking)
    talking.page.wait_for_selector("text=ready to review")
    settled = len(talking.requests_matching(f"/api/runs/{RUN}"))

    talking.page.wait_for_timeout(5_000)

    assert len(talking.requests_matching(f"/api/runs/{RUN}")) == settled


def test_discover_offers_the_way_in_and_lists_the_threads(ui):
    """The conversation is reachable, and the direct-intent box does not go away."""
    ui.serve("**/api/conversations", a_conversation_list())
    ui.open("#discover")
    ui.page.wait_for_selector("text=Talk it through first")

    assert "Ask for something" in ui.text()
    assert "Conversations (1)" in ui.text()
