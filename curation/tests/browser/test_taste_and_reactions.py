"""Taste, the reactions that fill it, and the control that leaves the thread.

Three behaviours here are the chunk's own and none is visible to a test that
reads JSON:

- **a reaction beside a sample writes a judgment about the name above it**, as
  the curator's own words, and says so without redrawing the picture they were
  looking at;
- **"go to <artist>'s work" leaves the thread** and lands on Collection filtered
  to that artist, where holding none of them is reported as a normal state
  rather than as a failed query. That empty state is Collection's own and is
  covered in `test_the_collection.py`; what is covered here is the route into
  it, which is the thing that makes it common;
- **Taste is not a fourth destination.** The navigation is derived from the
  route table, so registering the screen without a `destination` is what keeps
  the three destinations three — and only a browser can see the buttons.
"""

import json

import pytest
from payloads import a_conversation_list, a_sample, a_suggestion, a_taste, a_thread, a_turn, an_affinity, an_estimate

from curation.persistence.discovery_records import AffinityDerivation, AffinitySentiment, TurnRole

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

CONVERSATION = "conversation-under-test"
ANSWER_TURN = "turn-2"


def a_question(**overrides):
    return a_turn("Something calm for the living room.", turn_id="turn-1", ordinal=0, **overrides)


def an_answer(**overrides):
    fields = {
        "turn_id": ANSWER_TURN,
        "ordinal": 1,
        "role": TurnRole.SYSTEM.value,
        "suggested": [a_suggestion("Agnes Martin", samples=[a_sample("Untitled No. 5")])],
    }
    return a_turn("Agnes Martin's pale grids would hold that stillness.", **(fields | overrides))


@pytest.fixture
def talking(ui):
    """A conversation with one question, one answer, and a picture to react to."""
    ui.serve("**/api/estimate*", an_estimate())
    ui.serve("**/api/conversations", a_conversation_list())
    ui.serve(f"**/api/conversations/{CONVERSATION}", a_thread([a_question(), an_answer()]))
    return ui


def open_thread(ui) -> None:
    ui.open(f"#conversation/{CONVERSATION}")
    ui.page.wait_for_selector("#commit-card")


# -- reacting to a sample -----------------------------------------------------


def test_reacting_to_a_sample_records_a_stated_judgment_about_the_name(talking):
    """The write, and what it is a write *about*.

    An affinity is keyed on (kind, value), so a reaction beside a picture records
    a judgment about the artist the reply named rather than about the picture —
    which the data model deliberately cannot hold. The body is read off the real
    request, because "a POST happened" would pass against one that sent the
    sample's title as the value.
    """
    written = []
    talking.page.route("**/api/affinities", lambda route: _capture(route, written))
    open_thread(talking)

    talking.page.click(".sample button:has-text('more like this')")
    # The control's own confirmation, which exists only after the write returns —
    # so it is a wait for the new state rather than for something already true.
    talking.page.wait_for_selector("text=more like this — recorded")

    assert len(written) == 1
    assert written[0]["kind"] == "artist"
    assert written[0]["value"] == "Agnes Martin"
    assert written[0]["derivation"] == AffinityDerivation.STATED.value
    assert written[0]["sentiment"] == AffinitySentiment.LOVES.value
    assert written[0]["open_to_more"] is True
    # The turn it was said beside, so a judgment can be traced back to what was
    # on screen when it was made.
    assert written[0]["source_turn_id"] == ANSWER_TURN


def test_declining_and_asking_for_more_are_different_pairs_of_the_two_fields(talking):
    """The two-fields rule, at the only place a control could collapse it.

    "Tell me more" is `cool` and **still open** — the curator's own "meh on
    Magritte, but open to learning more". A single warmth score would render it
    as a low number indistinguishable from "not this", and the honest lukewarm
    reaction would blacklist an artist they explicitly asked to keep hearing
    about.
    """
    written = []
    talking.page.route("**/api/affinities", lambda route: _capture(route, written))
    open_thread(talking)

    talking.page.click(".sample button:has-text('not this')")
    talking.page.wait_for_selector("text=not this — recorded")
    talking.page.click(".sample button:has-text('tell me more')")
    talking.page.wait_for_selector("text=tell me more — recorded")

    assert [(body["sentiment"], body["open_to_more"]) for body in written] == [("declines", False), ("cool", True)]


def test_reacting_does_not_redraw_the_thread_under_the_curator(talking):
    """A judgment is recorded elsewhere and nothing in the transcript changes.

    A page that repainted here would move the picture the curator was looking at
    out from under the button they had just pressed — the same defect the run
    view's poll suppression exists to prevent, arriving through a write instead
    of a poll.
    """
    talking.page.route("**/api/affinities", lambda route: _capture(route, []))
    open_thread(talking)
    before = talking.page.evaluate("() => document.querySelector('.sample figcaption').textContent")

    talking.page.click(".sample button:has-text('more like this')")
    talking.page.wait_for_selector("text=more like this — recorded")

    assert talking.page.evaluate("() => document.querySelector('.sample figcaption').textContent") == before
    assert "Agnes Martin's pale grids" in talking.text()


def test_the_control_that_leaves_the_thread_is_kept_apart_from_the_three(talking):
    """The IA's own arrangement, asserted structurally rather than by eye.

    The three reactions record taste and stay; "go to <artist>'s work" navigates.
    Sitting it among them would put a control that loses the curator's place in a
    row of controls that do not, and the only way to find that out is to press
    it. Asserted as containment, because a stylesheet rule could be edited away
    while the markup went on claiming the separation.
    """
    open_thread(talking)

    assert talking.page.locator(".reactions button").count() == 3
    assert talking.page.locator('.reactions button:has-text("Go to Agnes Martin\'s work")').count() == 0
    assert talking.page.locator('.departure button:has-text("Go to Agnes Martin\'s work")').count() == 1


def test_going_to_an_artists_work_lands_on_the_normal_empty_state(talking):
    """The route the conversation makes common, followed end to end.

    The artists a conversation surfaces are by definition ones the curator could
    not have named, so a collection holding none of them is the overwhelmingly
    common outcome of pressing this. Collection says so as a statement about the
    collection — "Nothing by Agnes Martin yet" — rather than as a failed query,
    and this is the test that the button actually arrives there: the fragment it
    writes has to be the one Collection reads its artist filter out of.
    """
    open_thread(talking)

    talking.page.click(".departure button")
    # The empty state's own headline, which the conversation screen never
    # renders — so this waits for the landing rather than for something the
    # departing screen already had.
    talking.page.wait_for_selector("text=Nothing by Agnes Martin yet.")

    assert "artist=Agnes" in talking.page.url
    assert "That is the normal answer, not a failed search" in talking.text()
    assert talking.page.locator("button:has-text('Look for some in Discover')").count() == 1


# -- the Taste screen ---------------------------------------------------------


def test_taste_is_reachable_and_is_not_a_fourth_destination(ui):
    """Chunk 04's acceptance criterion, still true after a screen was added.

    The navigation is *derived* from the route table — the router filters on
    `destination` — so this is what says the new entry was registered without
    one. A comment claiming it would not have failed.
    """
    ui.serve("**/api/affinities*", a_taste([an_affinity()]))
    ui.open("#taste")
    ui.page.wait_for_selector(".affinity")

    labels = ui.page.locator("nav.destinations button").all_text_contents()
    assert labels == ["The Walls", "Collection", "Discover"]
    assert "Taste" not in labels


def test_every_judgment_shows_where_it_came_from(ui):
    """The screen's whole reason to exist.

    A taste model that cannot say where a judgment came from is one the curator
    can only argue with, never fix — so the derivation is on the row rather than
    behind a hover, and the model's own rationale is beside it where there is
    one.
    """
    ui.serve(
        "**/api/affinities*",
        a_taste(
            [
                an_affinity("Agnes Martin"),
                an_affinity(
                    "Kandinsky",
                    derivation=AffinityDerivation.INFERRED.value,
                    rationale="they asked for stillness, and said the room is pale",
                    source_turn_id=ANSWER_TURN,
                    conversation_id=CONVERSATION,
                ),
            ]
        ),
    )
    ui.open("#taste")
    ui.page.wait_for_selector(".affinity")

    assert "You said this" in ui.text()
    assert "Read out of something you said" in ui.text()
    assert "they asked for stillness, and said the room is pale" in ui.text()


def test_a_judgment_whose_conversation_was_deleted_renders_without_a_dead_link(ui):
    """**The acceptance criterion, from the screen's side.**

    An `inferred` row with a null `source_turn_id` is what a deleted conversation
    leaves behind, and it is a legal state the curator themselves caused. It has
    to render — a screen that dropped it would hide a judgment still shaping what
    they are offered — and it must not offer a way through to a thread that is
    not there.
    """
    ui.serve(
        "**/api/affinities*",
        a_taste(
            [
                an_affinity(
                    "Kandinsky",
                    derivation=AffinityDerivation.INFERRED.value,
                    rationale="they asked for stillness",
                    source_turn_id=None,
                    conversation_id=None,
                )
            ]
        ),
    )
    ui.open("#taste")
    ui.page.wait_for_selector(".affinity")

    assert "Kandinsky" in ui.text()
    assert "Read out of something you said" in ui.text()
    assert "they asked for stillness" in ui.text()
    assert ui.page.locator("button:has-text('See the conversation')").count() == 0


def test_a_judgment_that_still_has_its_thread_offers_the_way_back(ui):
    """The other half, so the test above discriminates rather than merely denies."""
    ui.serve(
        "**/api/affinities*",
        a_taste(
            [
                an_affinity(
                    "Kandinsky",
                    derivation=AffinityDerivation.INFERRED.value,
                    rationale="they asked for stillness",
                    source_turn_id=ANSWER_TURN,
                    conversation_id=CONVERSATION,
                )
            ]
        ),
    )
    ui.open("#taste")
    ui.page.wait_for_selector(".affinity")

    assert ui.page.locator("button:has-text('See the conversation')").count() == 1


def test_correcting_a_judgment_writes_it_as_the_curators_own_words(ui):
    """The correction path, and the provenance it writes.

    A correction made here is the curator saying so, whatever the row said
    before. Writing it as anything weaker would let the product go on attributing
    to a model a judgment the person overruled by hand, and a later rebuild would
    act on that.
    """
    written = []
    reads = [
        # The row being corrected carries a turn, deliberately: without one, a
        # correction that copied the old provenance across would send the same
        # null as a correct one and this test would pass against it. A mutation
        # sweep found exactly that.
        a_taste(
            [
                an_affinity(
                    "Kandinsky",
                    derivation=AffinityDerivation.INFERRED.value,
                    rationale="a guess",
                    source_turn_id=ANSWER_TURN,
                    conversation_id=CONVERSATION,
                )
            ]
        ),
        a_taste([an_affinity("Kandinsky", sentiment=AffinitySentiment.DECLINES.value, open_to_more=False)]),
    ]
    ui.page.route("**/api/affinities**", lambda route: _taste_route(route, reads, written))
    ui.open("#taste")
    ui.page.wait_for_selector(".affinity")

    ui.page.click("button:has-text('Not this')")
    # The repainted row, which says the opposite of what the first payload did —
    # so it is false before the click and true only after the correction lands.
    ui.page.wait_for_selector("text=Not to be offered again unless you say otherwise.")

    assert len(written) == 1
    assert written[0]["derivation"] == AffinityDerivation.STATED.value
    assert written[0]["sentiment"] == AffinitySentiment.DECLINES.value
    # And it does not carry the overruled judgment's turn across. A row citing a
    # turn that did not produce the judgment stored on it is indistinguishable
    # afterwards from real provenance, and a later rebuild would act on it.
    assert written[0]["source_turn_id"] is None


def test_forgetting_a_judgment_asks_first_and_says_what_is_lost(ui):
    """Not recoverable, so the dialog names the consequence rather than the row.

    And the distinction the screen exists to make: forgetting leaves the product
    knowing *nothing*, which is a different state from being told to leave a
    thing alone.
    """
    ui.page.route("**/api/affinities**", lambda route: _taste_route(route, [a_taste([an_affinity("Kandinsky")])], []))
    ui.open("#taste")
    ui.page.wait_for_selector(".affinity")

    ui.page.click("button:has-text('Forget this')")
    ui.page.wait_for_selector("dialog.confirm")

    assert "Forget Kandinsky?" in ui.page.inner_text("dialog.confirm")
    assert "stop knowing anything about Kandinsky" in ui.page.inner_text("dialog.confirm")
    assert "“Not this”" in ui.page.inner_text("dialog.confirm")


def test_declining_the_forget_destroys_nothing(ui):
    """Asking is only a guard if the answer is read.

    A mutation sweep deleted the `if (!agreed) return;` and every assertion above
    still passed: they all describe the *question*, and none of them describes
    what happens when the curator says no. This is the one that does — and it is
    the harder direction to get right, because the dialog's own text is what a
    test naturally reaches for.
    """
    deleted = []
    ui.page.route("**/api/affinities**", lambda route: _taste_route(route, [a_taste([an_affinity("Kandinsky")])], [], deleted))
    ui.open("#taste")
    ui.page.wait_for_selector(".affinity")

    ui.page.click("button:has-text('Forget this')")
    ui.page.wait_for_selector("dialog.confirm")
    ui.page.keyboard.press("Escape")
    # The dialog removes itself from the document once it settles, so its absence
    # is a state that is true only after the decline.
    ui.page.wait_for_selector("dialog.confirm", state="detached")

    assert deleted == []
    assert "Kandinsky" in ui.text()


def test_a_taste_nobody_has_expressed_says_what_would_create_one(ui):
    """The screen's empty state, which is not a "no results".

    There is nothing to clear and no filter to blame — there is a thing the
    curator has not done yet, so the state names it and offers the way to it.
    """
    ui.serve("**/api/affinities*", a_taste())
    ui.open("#taste")
    ui.page.wait_for_selector(".empty")

    assert "Nothing is known about your taste yet." in ui.text()
    assert ui.page.locator("button:has-text('Start a conversation in Discover')").count() == 1


def test_discover_offers_the_way_into_taste(ui):
    """The IA's entry point, which is the only one the navigation does not give."""
    ui.open("#discover")
    ui.page.wait_for_selector("#intent")

    ui.page.click("button:has-text('See what this product thinks you like')")
    ui.page.wait_for_selector("text=What this product thinks you like")

    assert ui.page.url.endswith("#taste")


# -- deleting a conversation --------------------------------------------------


def test_deleting_a_conversation_asks_first_and_names_what_is_lost(talking):
    """The one act on this surface that genuinely destroys a record.

    The confirmation states a consequence in the curator's terms — the judgments
    can never be rebuilt — rather than a row count, and it says what *survives*,
    because a sentence about destruction that did not would read as a cascade.
    """
    open_thread(talking)

    talking.page.click(".panel button:has-text('Delete this conversation')")
    talking.page.wait_for_selector("dialog.confirm")

    said = talking.page.inner_text("dialog.confirm")
    assert "Delete this conversation?" in said
    assert "cannot be recovered" in said
    assert "never be rebuilt" in said
    assert "what the talking cost are both kept" in said


def test_declining_the_delete_leaves_the_thread_where_it_was(talking):
    """Escape and Cancel are the same path, and neither destroys anything."""
    calls = []
    talking.page.route(
        f"**/api/conversations/{CONVERSATION}",
        lambda route: _record_delete(route, calls),
    )
    open_thread(talking)

    talking.page.click(".panel button:has-text('Delete this conversation')")
    talking.page.wait_for_selector("dialog.confirm")
    talking.page.keyboard.press("Escape")
    # The dialog is removed from the document once it settles, so its absence is
    # the state that is true only after the decline.
    talking.page.wait_for_selector("dialog.confirm", state="detached")

    assert calls == []
    assert "Agnes Martin's pale grids" in talking.text()


def test_agreeing_deletes_the_thread_and_leaves_the_screen(talking):
    """It navigates, and that is not the wizard this screen refuses.

    The commit stays because there is still a conversation to stay in. Here there
    is not, and a screen left pointing at a deleted thread fails its next poll
    with an error about something the curator meant to happen.
    """
    calls = []
    talking.page.route(
        f"**/api/conversations/{CONVERSATION}",
        lambda route: _record_delete(route, calls),
    )
    open_thread(talking)

    talking.page.click(".panel button:has-text('Delete this conversation')")
    talking.page.wait_for_selector("dialog.confirm")
    talking.page.click("dialog.confirm button:has-text('Delete it')")
    # Discover's own intent box, which the conversation screen does not have.
    talking.page.wait_for_selector("#intent")

    assert calls == ["DELETE"]
    assert talking.page.url.endswith("#discover")


def _capture(route, written):
    """Answer an affinity write, recording the body the client actually sent."""
    written.append(json.loads(route.request.post_data))
    body = an_affinity(json.loads(route.request.post_data)["value"]).model_dump(mode="json")
    route.fulfill(status=200, content_type="application/json", body=json.dumps(body))


def _taste_route(route, reads, written, deleted=None):
    """One handler for , because reads and writes share the URL.

    Playwright matches a route by address and not by method, so a read stub and a
    write stub over the same path race: whichever was registered last answers
    both, and the test either sees no write or paints an affinity list from the
    response to a POST. Dispatching on the method here is what keeps a screen
    that reads back after writing testable at all — and the read list advances
    per GET, so "what the screen showed after the correction" is expressible.
    """
    if route.request.method == "POST":
        _capture(route, written)
        return
    if route.request.method == "DELETE":
        if deleted is not None:
            deleted.append(route.request.url)
        route.fulfill(status=200, content_type="application/json", body=json.dumps(an_affinity().model_dump(mode="json")))
        return
    body = reads[min(len(written), len(reads) - 1)]
    route.fulfill(status=200, content_type="application/json", body=json.dumps(body))


def _record_delete(route, calls):
    """Answer the conversation route, noting a DELETE and serving the thread otherwise."""
    if route.request.method == "DELETE":
        calls.append("DELETE")
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "conversation_id": CONVERSATION,
                    "turns_deleted": 2,
                    "affinities_detached": 0,
                    "spend_records_detached": 1,
                    "runs_unattributed": 0,
                    "description": "The conversation and everything said in it are gone.",
                }
            ),
        )
        return
    route.fulfill(
        status=200,
        content_type="application/json",
        body=json.dumps(a_thread([a_question(), an_answer()])),
    )
