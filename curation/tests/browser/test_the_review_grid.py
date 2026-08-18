"""The review grid: what it fetches, when, and what a verdict does to a card.

The most stateful screen in the product, and the one this harness was built ahead
of. Every behaviour below is one a test reading JSON cannot see: a disclosure
that fetches on open, a card that repaints in place while its neighbours are left
alone, a notice that has to survive that repaint, and a spending button that must
appear only when there is something to spend on.

Each is paired with the assertion that fails if it *over*-fires — alternates that
never load are as broken as alternates loaded thirty at a time, and a card that
repaints the whole grid loses the curator their scroll position on every verdict.
"""

import pytest
from payloads import (
    a_candidate,
    a_candidate_page,
    a_card,
    a_run,
    a_run_view,
    a_spend,
    a_verdict,
    an_artist,
    an_estimate,
    an_instance,
    an_instance_listing,
)

from curation.persistence.discovery_records import ResolutionStatus, RunStatus, Verdict, WorkProvenance

# At import time, not in a fixture. A marker deselection still *collects* this
# module, so the default run — which does not install the browser group — has to
# skip here rather than fail on the missing plugin.
pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

RUN_ID = "run-under-test"


@pytest.fixture
def grid(ui):
    """A finished run holding one work, with its picture and its alternates.

    The picture route is stubbed with real JPEG bytes rather than left to 404:
    every card requests one, and a failing request would put the error fallback
    on every test here for a reason belonging to the fixture.
    """
    ui.serve_image("**/api/candidate-images/*/preview")
    ui.serve(f"**/api/runs/{RUN_ID}/candidates*", a_candidate_page([a_card()]))
    ui.serve("**/api/candidates/work-1/images", an_instance_listing())
    ui.serve("**/api/candidates/work-1", a_card().model_dump(mode="json"))
    return ui


# -- the disclosure says what is behind it -----------------------------------


def test_the_scans_disclosure_does_not_promise_scans_the_curator_has_already_seen(grid):
    """The summary counts every scan, so it must not call them *other* scans.

    The panel behind this disclosure lists all of a work's scans, the one
    pictured on the card included. Labelling that "Other scans (1)" told a
    curator there was something new behind it and then showed them the picture
    they were already looking at — broken on every single-scan work, which in the
    corpus that surfaced it was nineteen of nineteen.

    Asserted on the rendered summary rather than on the count alone, because the
    count was never wrong: it matched the panel's contents exactly. The false
    word was the whole defect, and a test over `instances_held` would have passed
    throughout.
    """
    grid.open(f"#review/{RUN_ID}")
    grid.page.wait_for_selector("li.card")

    summary = grid.page.locator("li.card summary").first.inner_text()
    assert summary == "Scans (1)", summary
    assert "other" not in summary.lower(), f"the summary promises scans beyond the one pictured: {summary!r}"


# -- the alternates are fetched when opened, not with the grid ---------------


def test_the_alternates_are_not_fetched_until_they_are_opened(grid):
    """Thirty cards holding up to twelve scans each is a page nobody asked for.

    A curator opens the alternates for the few works whose first answer they
    doubt, so fetching every work's on paint would multiply the cost of the
    screen by the number of scans nobody looks at.
    """
    grid.open(f"#review/{RUN_ID}")
    grid.page.wait_for_selector("li.card")

    assert grid.requests_matching("/api/candidates/work-1/images") == []


def test_the_alternates_do_arrive_when_opened(grid):
    """The paired negative: lazy must not become never.

    Without this, a listener that silently failed to fire would leave the
    disclosure permanently showing "Loading the other scans…" — and the test
    above would pass, because it asserts an absence.
    """
    grid.open(f"#review/{RUN_ID}")
    grid.page.click("summary")

    grid.page.wait_for_selector("li.alternate")
    assert grid.requests_matching("/api/candidates/work-1/images")


def test_opening_the_alternates_shows_what_a_curator_chooses_between(grid):
    """The size on the wall is the whole reason the alternates are worth opening.

    Two scans of one painting look identical at card size; the inches are what
    separates a wall-filling scan from a postage stamp.
    """
    grid.serve(
        "**/api/candidates/work-1/images",
        an_instance_listing(
            [
                an_instance(image_id="image-1"),
                an_instance(
                    image_id="image-2",
                    is_selected=False,
                    fit={
                        "verdict": "below_floor",
                        "rendered_width": 900,
                        "rendered_height": 700,
                        "rendered_long_edge_inches": 7.4,
                    },
                ),
            ]
        ),
    )
    grid.open(f"#review/{RUN_ID}")
    grid.page.click("summary")
    grid.page.wait_for_selector("li.alternate")

    shown = grid.text()
    assert "would show at 27.4″" in shown
    assert "would show at 7.4″" in shown
    assert "on offer" in shown


def test_turning_a_scan_down_leaves_the_alternates_open(grid):
    """Choosing between scans is a sequence, not one act.

    Rejecting a scan repaints the card — the picture and the verdict both change
    — and rebuilding it closed would collapse the list the curator is working in
    on every click, costing a re-open and a second fetch to get back to where
    they were.

    **The repaint has to be waited for, and that is the whole difficulty.** The
    obvious version of this test clicks and then waits for an open disclosure,
    which matches instantly against the card that has not been replaced yet — so
    it passes whatever the repaint does with the state. The mutation sweep caught
    exactly that. The verdict badge is the signal that the new card has landed,
    so it is waited for first and the disclosure is asserted after.
    """
    wanting = a_candidate(verdict=Verdict.AWAITING_BETTER_IMAGE.value)
    grid.serve("**/api/candidate-images/image-1/reject", wanting.model_dump(mode="json"))
    grid.serve("**/api/candidates/work-1", a_card(work=wanting).model_dump(mode="json"))
    grid.open(f"#review/{RUN_ID}")
    grid.page.click("summary")
    grid.page.wait_for_selector("li.alternate")

    grid.page.click("button:has-text('Turn it down')")
    grid.page.wait_for_selector(".badge:has-text('wants a better scan')")

    # The card that is on the page now is the new one, so this reads the state
    # that was carried over rather than the one being replaced. The rows are
    # asserted as well as the open attribute: a disclosure carried open whose
    # listener never fires again shows "Loading the other scans…" for ever, which
    # is open and empty and looks exactly like a request that never came back.
    assert grid.page.locator("details[open]").count() == 1
    grid.page.wait_for_selector("details[open] li.alternate")


def test_the_alternates_of_an_untouched_card_start_closed(grid):
    """The paired negative: carrying the state over must not mean always open.

    A grid of thirty cards with every disclosure expanded is a page of stacked
    scan lists, and it would fetch every one of them on paint — the cost the lazy
    fetch above exists to avoid.
    """
    grid.open(f"#review/{RUN_ID}")
    grid.page.wait_for_selector("li.card")

    assert grid.page.locator("details[open]").count() == 0


def test_an_alternate_s_buttons_name_the_work_rather_than_its_id(grid):
    """A screen reader announcing "Use this scan for 8f2a-41c3…" names nothing.

    The row's whole purpose is choosing between scans of a painting, and the id
    is the one thing on the card that identifies it to nobody.

    **Two instances, and the second one is load-bearing.** "Use this one" is drawn
    only for a scan that is neither selected nor refused, so a listing holding
    just the selected instance renders one button and this test would cover half
    of what it claims — which is how the first version of it survived a mutation
    aimed squarely at that button's label.
    """
    grid.serve(
        "**/api/candidates/work-1/images",
        an_instance_listing([an_instance(image_id="image-1"), an_instance(image_id="image-2", is_selected=False)]),
    )
    grid.open(f"#review/{RUN_ID}")
    grid.page.click("summary")
    grid.page.wait_for_selector("li.alternate")

    labels = grid.page.locator("li.alternate button").evaluate_all("nodes => nodes.map(n => n.getAttribute('aria-label'))")
    assert len(labels) == 3, f"expected both actions on the choosable scan and one on the selected one: {labels}"
    for label in labels:
        assert "The Persistence of Memory" in label, label
        assert "work-1" not in label, label


# -- a verdict repaints one card, not the grid --------------------------------


def test_a_verdict_repaints_only_the_card_it_was_recorded_on(grid):
    """A grid that repainted whole would cost the curator their place in it.

    Thirty cards of images, re-fetched and re-laid-out on every accept, with the
    scroll position gone — on the screen a curator spends their whole session in.
    """
    grid.serve(
        f"**/api/runs/{RUN_ID}/candidates*",
        a_candidate_page(
            [
                a_card(work=a_candidate(work_id="work-1", title="The Persistence of Memory")),
                a_card(work=a_candidate(work_id="work-2", title="The Elephants")),
            ]
        ),
    )
    grid.serve("**/api/candidates/work-1/verdict", a_verdict())
    grid.serve("**/api/candidates/work-1", a_card(work=a_candidate(verdict=Verdict.ACCEPTED.value)).model_dump(mode="json"))
    grid.open(f"#review/{RUN_ID}")
    grid.page.wait_for_selector("li.card")

    neighbour = grid.page.locator("li.card[data-work='work-2']")
    handle = neighbour.element_handle()
    grid.page.click("li.card[data-work='work-1'] button:has-text('Accept')")
    grid.page.wait_for_selector("li.card[data-work='work-1'] .badge:has-text('accepted')")

    # The same DOM node, not an equal one: a whole-grid repaint replaces every
    # element, so identity is what tells "left alone" from "rebuilt identically".
    assert handle.evaluate("node => node.isConnected") is True
    assert grid.page.locator("li.card").count() == 2


def test_the_card_a_verdict_was_recorded_on_does_change(grid):
    """The paired negative: repainting nothing is not repainting narrowly.

    A curator who accepts a work and sees the card unchanged cannot tell the
    click from a click that failed.
    """
    grid.serve("**/api/candidates/work-1/verdict", a_verdict())
    grid.serve("**/api/candidates/work-1", a_card(work=a_candidate(verdict=Verdict.ACCEPTED.value)).model_dump(mode="json"))
    grid.open(f"#review/{RUN_ID}")
    grid.page.wait_for_selector("li.card")
    assert "accepted" not in grid.text()

    grid.page.click("button:has-text('Accept')")

    grid.page.wait_for_selector(".badge:has-text('accepted')")


def test_a_newly_minted_artist_notice_survives_the_repaint(grid):
    """The one part of a promotion a curator can neither see nor undo from it.

    It describes what the verdict just *did*, so it is nowhere in the card that
    replaces it — a repaint that dropped it would lose the only warning that a
    duplicate painter now sits in the catalogue.
    """
    grid.serve(
        "**/api/candidates/work-1/verdict",
        a_verdict(
            minted_artist=an_artist(name="Jacob van Ruisdael"),
            possible_duplicate_artists=[an_artist(artist_id="artist-2", name="Jacob Isaacksz van Ruisdael")],
            notice=(
                "A new artist 'Jacob van Ruisdael' was recorded, and the catalogue already holds "
                "'Jacob Isaacksz van Ruisdael'. They may be the same painter."
            ),
        ),
    )
    grid.serve("**/api/candidates/work-1", a_card(work=a_candidate(verdict=Verdict.ACCEPTED.value)).model_dump(mode="json"))
    grid.open(f"#review/{RUN_ID}")
    grid.page.wait_for_selector("li.card")

    grid.page.click("button:has-text('Accept')")
    grid.page.wait_for_selector(".badge:has-text('accepted')")

    assert "may be the same painter" in grid.text()


def test_an_acceptance_with_nothing_to_say_says_nothing(grid):
    """The paired negative — a notice on every card is a notice nobody reads."""
    grid.serve("**/api/candidates/work-1/verdict", a_verdict())
    grid.serve("**/api/candidates/work-1", a_card(work=a_candidate(verdict=Verdict.ACCEPTED.value)).model_dump(mode="json"))
    grid.open(f"#review/{RUN_ID}")
    grid.page.wait_for_selector("li.card")

    grid.page.click("button:has-text('Accept')")
    grid.page.wait_for_selector(".badge:has-text('accepted')")

    assert "may be the same painter" not in grid.text()


# -- a picture that is shown but is not on offer ------------------------------


def test_a_work_with_no_scan_on_offer_says_accepting_will_be_refused(grid):
    """A picture on a card reads as something acceptable, and here it is not.

    Every scan below the floor means no selection at all, so the service refuses
    the acceptance. Without this the curator sees a picture, presses Accept, and
    gets an error naming a state the screen never mentioned.
    """
    grid.serve(
        f"**/api/runs/{RUN_ID}/candidates*",
        a_candidate_page([a_card(shown=an_instance(is_selected=False), shown_is_on_offer=False)]),
    )
    grid.open(f"#review/{RUN_ID}")
    grid.page.wait_for_selector("li.card")

    assert "No scan is on offer for this work" in grid.text()


def test_a_work_standing_on_a_scan_says_nothing_of_the_kind(grid):
    """The paired negative: a warning on every card trains the eye past it."""
    grid.open(f"#review/{RUN_ID}")
    grid.page.wait_for_selector("li.card")

    assert "No scan is on offer" not in grid.text()


# -- the re-search --------------------------------------------------------


def test_nothing_offers_to_spend_when_no_scan_has_been_turned_down(grid):
    """A button that spends and would do nothing is worse than no button."""
    grid.open(f"#review/{RUN_ID}")
    grid.page.wait_for_selector("li.card")

    assert "Look again for these" not in grid.text()


def test_a_work_waiting_for_a_better_scan_is_offered_a_re_search(grid):
    """The dead end this binding exists to close, at the point a curator hits it.

    Rejecting a scan records a judgement and starts no search. A page that stayed
    silent would leave the curator waiting for one that is never coming.
    """
    grid.serve(
        f"**/api/runs/{RUN_ID}/candidates*",
        a_candidate_page([a_card(work=a_candidate(verdict=Verdict.AWAITING_BETTER_IMAGE.value))]),
    )
    grid.open(f"#review/{RUN_ID}")
    grid.page.wait_for_selector("li.card")

    shown = grid.text()
    assert "1 work is waiting for a better scan" in shown
    assert "Nothing is looking for one" in shown
    assert "it spends" in shown


def test_the_re_search_asks_only_for_the_works_that_are_waiting(grid):
    """A re-search over works nobody turned down spends on answers already held.

    The list is what the button sends, so a filter written wrongly is money —
    and it is invisible in any assertion about what the page displays.
    """
    grid.serve(
        f"**/api/runs/{RUN_ID}/candidates*",
        a_candidate_page(
            [
                a_card(work=a_candidate(work_id="settled", verdict=Verdict.PENDING.value)),
                a_card(work=a_candidate(work_id="wanting", verdict=Verdict.AWAITING_BETTER_IMAGE.value)),
            ]
        ),
    )
    grid.serve("**/api/runs/resolve", a_run(run_id="resolve-run", kind="resolve").model_dump(mode="json"))
    grid.serve("**/api/runs/resolve-run", a_run_view(run=a_run(run_id="resolve-run", kind="resolve")))
    grid.serve("**/api/estimate?*", an_estimate())
    grid.serve("**/api/runs/resolve-run/spend", a_spend())

    sent = []
    grid.page.on("request", lambda request: sent.append(request) if request.url.endswith("/api/runs/resolve") else None)

    grid.open(f"#review/{RUN_ID}")
    grid.page.wait_for_selector("li.card")
    grid.page.click("button:has-text('Look again for these')")
    grid.page.wait_for_url("**/#run/resolve-run")

    assert len(sent) == 1
    assert sent[0].post_data_json == {"work_ids": ["wanting"]}


# -- the offer tracks the verdicts recorded on the page it sits on ------------
#
# The three below are one defect seen from three sides: the panel used to be
# derived once, at paint, from the page the grid was built from. Every verdict
# after that reached one card and nothing else, so the panel went on describing
# the run as it arrived rather than as the curator had left it.


def test_the_offer_to_re_search_appears_when_a_scan_is_turned_down(grid):
    """The state the curator reaches by working, not the one the page loaded in.

    A grid that opens with nothing waiting is the normal way into this: the
    curator turns a scan down *because* they want a better one. Deriving the
    panel once meant the one screen that could tell them nothing is looking
    stayed silent exactly when it had something to say.

    The badge is waited for rather than the panel, for the reason the disclosure
    test states: it is the signal that the replacement card has landed, so
    asserting on it first keeps this from matching against the pre-repaint page.
    """
    wanting = a_candidate(verdict=Verdict.AWAITING_BETTER_IMAGE.value)
    grid.serve("**/api/candidate-images/image-1/reject", wanting.model_dump(mode="json"))
    grid.serve("**/api/candidates/work-1", a_card(work=wanting).model_dump(mode="json"))
    grid.open(f"#review/{RUN_ID}")
    grid.page.wait_for_selector("li.card")
    assert "Look again for these" not in grid.text()

    grid.page.click("summary")
    grid.page.wait_for_selector("li.alternate")
    grid.page.click("button:has-text('Turn it down')")
    grid.page.wait_for_selector(".badge:has-text('wants a better scan')")

    shown = grid.text()
    assert "1 work is waiting for a better scan" in shown
    assert "Look again for these" in shown


def test_the_re_search_spends_on_a_work_turned_down_after_the_page_loaded(grid):
    """The half of this that costs money rather than credibility.

    A stale panel under-*counts*, and the count is the visible symptom — but the
    list the button posts is the same stale array, so the curator pays for a run
    covering fewer works than they just marked and gets back a run that is not
    the one they asked for. No assertion about rendered text reaches it.

    Both works are asserted, in the order the page holds them: a fix that
    re-derived the list from the newly-turned-down card alone would send one id
    and satisfy every count on screen.
    """
    already = a_candidate(work_id="work-2", title="The Elephants", verdict=Verdict.AWAITING_BETTER_IMAGE.value)
    turned_down = a_candidate(verdict=Verdict.AWAITING_BETTER_IMAGE.value)
    grid.serve(f"**/api/runs/{RUN_ID}/candidates*", a_candidate_page([a_card(), a_card(work=already)]))
    grid.serve("**/api/candidate-images/image-1/reject", turned_down.model_dump(mode="json"))
    grid.serve("**/api/candidates/work-1", a_card(work=turned_down).model_dump(mode="json"))
    grid.serve("**/api/runs/resolve", a_run(run_id="resolve-run", kind="resolve").model_dump(mode="json"))
    grid.serve("**/api/runs/resolve-run", a_run_view(run=a_run(run_id="resolve-run", kind="resolve")))
    grid.serve("**/api/estimate?*", an_estimate())
    grid.serve("**/api/runs/resolve-run/spend", a_spend())

    sent = []
    grid.page.on("request", lambda request: sent.append(request) if request.url.endswith("/api/runs/resolve") else None)

    grid.open(f"#review/{RUN_ID}")
    grid.page.wait_for_selector("li.card")
    assert "1 work is waiting for a better scan" in grid.text()

    grid.page.click("li.card[data-work='work-1'] summary")
    grid.page.wait_for_selector("li.alternate")
    grid.page.click("li.card[data-work='work-1'] button:has-text('Turn it down')")
    grid.page.wait_for_selector("li.card[data-work='work-1'] .badge:has-text('wants a better scan')")

    assert "2 works are waiting for a better scan" in grid.text()

    grid.page.click("button:has-text('Look again for these')")
    grid.page.wait_for_url("**/#run/resolve-run")

    assert len(sent) == 1
    assert sent[0].post_data_json == {"work_ids": ["work-1", "work-2"]}


def test_the_offer_is_announced_to_a_curator_who_cannot_see_it_appear(grid):
    """Appearing silently is the sighted-only half of this binding.

    The offer's whole job is to tell a curator that nothing is looking for a
    better scan. A curator working by screen reader turns a scan down, the panel
    appears below the heading they are nowhere near, and without a live region
    they are told nothing at all — the same dead end this exists to close, for
    the people least able to spot it.

    The region is asserted to be on the page *before* the offer arrives, because
    that is the part that is easy to get wrong and impossible to see: a
    `role="status"` element created and filled in the same breath announces
    nothing. `status` rather than `alert` — polite, since an offer is news
    rather than an emergency.
    """
    wanting = a_candidate(verdict=Verdict.AWAITING_BETTER_IMAGE.value)
    grid.serve("**/api/candidate-images/image-1/reject", wanting.model_dump(mode="json"))
    grid.serve("**/api/candidates/work-1", a_card(work=wanting).model_dump(mode="json"))
    grid.open(f"#review/{RUN_ID}")
    grid.page.wait_for_selector("li.card")

    region = grid.page.locator("[role='status']")
    assert region.count() == 1, "the live region must already exist, empty, before anything is put in it"
    assert region.inner_text().strip() == ""

    grid.page.click("summary")
    grid.page.wait_for_selector("li.alternate")
    grid.page.click("button:has-text('Turn it down')")
    grid.page.wait_for_selector(".badge:has-text('wants a better scan')")

    assert "waiting for a better scan" in region.inner_text()


def test_the_offer_is_not_re_announced_when_no_verdict_moved(grid):
    """A live region rewritten for nothing reads itself out for nothing.

    Every repaint reports its verdict, including the repaints that change none —
    choosing between two scans of a work is the common one, and a curator doing
    it by screen reader would hear the whole offer again on each pick. Node
    identity is the assertion because it is what "not rewritten" means: equal
    text rebuilt into a new element is exactly what re-announces.
    """
    grid.serve(
        f"**/api/runs/{RUN_ID}/candidates*",
        a_candidate_page(
            [
                a_card(work=a_candidate(work_id="waiting", verdict=Verdict.AWAITING_BETTER_IMAGE.value)),
                a_card(work=a_candidate(work_id="other")),
            ]
        ),
    )
    grid.serve("**/api/candidates/other/images", an_instance_listing(work=a_candidate(work_id="other")))
    grid.serve("**/api/candidates/other/verdict", a_verdict())
    grid.serve(
        "**/api/candidates/other",
        a_card(work=a_candidate(work_id="other", verdict=Verdict.ACCEPTED.value)).model_dump(mode="json"),
    )
    grid.open(f"#review/{RUN_ID}")
    grid.page.wait_for_selector("li.card[data-work='waiting']")

    panel = grid.page.locator("[role='status'] .panel")
    handle = panel.element_handle()

    # A verdict on a work that was never waiting, and is not waiting now: the
    # set the offer describes is identical either side of this click.
    grid.page.click("li.card[data-work='other'] button:has-text('Accept')")
    grid.page.wait_for_selector("li.card[data-work='other'] .badge:has-text('accepted')")

    assert handle.evaluate("node => node.isConnected") is True, "the offer was rebuilt though nothing it describes changed"
    assert "1 work is waiting for a better scan" in grid.text()


def test_the_offer_withdraws_when_the_last_waiting_work_is_settled(grid):
    """The paired negative, and the other way a verdict reaches the panel.

    A work leaves `awaiting_better_image` through the card's own buttons, not
    through the alternates — so this covers the second caller of the repaint the
    panel listens to. Leaving the offer standing would invite a curator to spend
    on a work they had just settled, which is the same defect facing the other
    way: a button that spends and would do nothing.
    """
    grid.serve(
        f"**/api/runs/{RUN_ID}/candidates*",
        a_candidate_page([a_card(work=a_candidate(verdict=Verdict.AWAITING_BETTER_IMAGE.value))]),
    )
    grid.serve("**/api/candidates/work-1/verdict", a_verdict())
    grid.serve("**/api/candidates/work-1", a_card(work=a_candidate(verdict=Verdict.ACCEPTED.value)).model_dump(mode="json"))
    grid.open(f"#review/{RUN_ID}")
    grid.page.wait_for_selector("li.card")
    assert "Look again for these" in grid.text()

    grid.page.click("button:has-text('Accept')")
    grid.page.wait_for_selector(".badge:has-text('accepted')")

    assert "Look again for these" not in grid.text()


# -- paging through the run's works -------------------------------------------


def test_the_grid_pages_through_to_the_end(ui):
    """A run wider than one page must not present as a run that size.

    The service pages this listing where the run view's own work list is not
    paged, so the grid is the surface that has to walk it — and a grid that
    stopped at the first page would show thirty of two hundred works with nothing
    saying so.
    """
    ui.serve_image("**/api/candidate-images/*/preview")
    ui.serve(
        f"**/api/runs/{RUN_ID}/candidates*",
        [
            a_candidate_page([a_card(work=a_candidate(work_id="w1", title="First"))], total=2, truncated=True),
            a_candidate_page([a_card(work=a_candidate(work_id="w2", title="Second"))], total=2, offset=1),
        ],
    )
    ui.open(f"#review/{RUN_ID}")
    ui.page.wait_for_selector("li.card")

    assert ui.page.locator("li.card").count() == 2
    assert "First" in ui.text()
    assert "Second" in ui.text()


def test_a_page_that_says_there_is_more_and_carries_nothing_is_not_asked_again(ui):
    """The stopping condition is what arrived, not what the server claims is left.

    A server answering `truncated` over an empty page makes no progress, and
    asking it again cannot change that: the offset does not move, because nothing
    came back to move it. The ceiling would eventually stop the loop — so this is
    forty-nine pointless round trips on a Pi rather than a hang, which is the
    correction this test also pins, since the comment beside the guard used to
    claim it prevented an infinite loop.
    """
    ui.serve_image("**/api/candidate-images/*/preview")
    ui.serve(f"**/api/runs/{RUN_ID}/candidates*", a_candidate_page([], total=5, truncated=True))
    ui.open(f"#review/{RUN_ID}")
    ui.page.wait_for_selector("#view p.muted")

    assert len(ui.requests_matching(f"/api/runs/{RUN_ID}/candidates")) == 1
    assert "settled on no works" in ui.text()


def test_a_listing_that_keeps_insisting_there_is_more_still_terminates(ui):
    """The paired negative: a loop that walks to the end must also be able to stop.

    A server answering `truncated` forever — a bug, or a page whose offset is
    ignored — would spin this loop until the tab died. The runaway guard is what
    stops it, and what it left out is then reported rather than hidden.
    """
    ui.serve_image("**/api/candidate-images/*/preview")
    ui.serve(
        f"**/api/runs/{RUN_ID}/candidates*",
        a_candidate_page([a_card()], total=9999, truncated=True),
    )
    ui.open(f"#review/{RUN_ID}")
    ui.page.wait_for_selector("li.card")

    assert "more are held and are not on this page" in ui.text()


# -- the verdict, in words ----------------------------------------------------


@pytest.mark.parametrize("verdict", [v for v in Verdict if v is not Verdict.PENDING])
def test_every_decided_verdict_reaches_the_page_as_words_and_a_glyph(grid, verdict):
    """Parametrised over the enum rather than a list written here.

    A fifth verdict arrives as a failure in this test, which is the only thing
    stopping it reaching a curator's card as `awaiting_third_opinion`-shaped
    noise on the screen whose whole job is telling them what they are looking at.

    **The check is for an underscore, not for the token.** Two of these verdicts
    are their own English word — a card reading "accepted" is exactly right — so
    asserting the value is absent would fail against a correct client. What marks
    a diagnostic label is that it is snake_case, which no rendered phrase here is,
    and that is the property a fifth member would break.

    The glyph is asserted beside the word because colour is never the sole
    carrier of state, and a stylesheet cannot supply one.
    """
    grid.serve(
        f"**/api/runs/{RUN_ID}/candidates*",
        a_candidate_page([a_card(work=a_candidate(verdict=verdict.value))]),
    )
    grid.open(f"#review/{RUN_ID}")
    grid.page.wait_for_selector("li.card")

    badge = grid.page.locator(f"li.card span.badge-{verdict.value}")
    assert badge.count() == 1, f"the {verdict.value} verdict has no badge of its own on the card"
    words = badge.inner_text().strip()
    assert words, f"{verdict.value} reached the page with no words"
    assert "_" not in words, f"the raw token {verdict.value!r} reached the page"
    assert badge.locator("span.glyph").inner_text().strip(), f"{verdict.value} reached the page with no glyph"


def test_an_undecided_work_carries_no_verdict_badge(grid):
    """The paired negative: the ordinary case is shown by the absence of a badge.

    A badge on every card is what makes the two decided states hard to pick out,
    and `pending` is deliberately excluded from the words the client has — so a
    badge appearing here would be the raw token.
    """
    grid.open(f"#review/{RUN_ID}")
    grid.page.wait_for_selector("li.card")

    assert "pending" not in grid.text()


# -- a picture that will not load ---------------------------------------------


def test_a_picture_that_fails_to_load_says_so_rather_than_leaving_a_blank(ui):
    """The listing reports a file it has not read, so this race is real.

    A museum's undecodable JPEG is `preview_available` until something opens it.
    Without the fallback the card paints an empty box — silent, which is the
    failure this product exists to refuse.
    """
    ui.serve(f"**/api/runs/{RUN_ID}/candidates*", a_candidate_page([a_card()]))
    ui.page.route("**/api/candidate-images/*/preview", lambda route: route.fulfill(status=400, body="{}"))

    ui.open(f"#review/{RUN_ID}")
    ui.page.wait_for_selector("li.card")

    ui.page.wait_for_selector(".card-image-absent")
    assert "could not be loaded" in ui.text()


def test_a_reclaimed_picture_is_named_rather_than_requested(ui):
    """A decided work's preview is deleted on purpose, and the card knows.

    This is the case `preview_available` exists for: the work *has* an instance,
    so the card renders one — and the bytes are gone. Without the check the card
    requests them, gets a refusal, and falls back to "could not be loaded just
    now", which sends the curator looking for a bad download instead of telling
    them the truth. The listing already carries the reason; the card shows it.

    Distinct from the test below, which is a work with no instance at all and
    never reaches this branch. Both were needed: the sweep killed the guard and
    only this one noticed.
    """
    ui.serve(
        f"**/api/runs/{RUN_ID}/candidates*",
        a_candidate_page(
            [
                a_card(
                    shown=an_instance(
                        preview_available=False,
                        preview_note="This work was accepted, so its cached copy was reclaimed.",
                    )
                )
            ]
        ),
    )
    ui.open(f"#review/{RUN_ID}")
    ui.page.wait_for_selector("li.card")

    assert ui.requests_matching("/api/candidate-images/") == []
    assert "its cached copy was reclaimed" in ui.text()
    assert "could not be loaded" not in ui.text()


def test_a_work_the_run_found_nothing_for_says_so_without_asking_for_a_picture(ui):
    """No request at all, rather than a request that fails.

    The card knows before it asks — the listing carries `preview_available` — and
    a grid that requested bytes for every pictureless work would spend a round
    trip per card to be told what it was already holding.
    """
    ui.serve(
        f"**/api/runs/{RUN_ID}/candidates*",
        a_candidate_page(
            [
                a_card(
                    work=a_candidate(
                        resolution_status=ResolutionStatus.UNRESOLVED.value,
                        unresolved_reason="not_held",
                    ),
                    shown=None,
                )
            ]
        ),
    )
    ui.open(f"#review/{RUN_ID}")
    ui.page.wait_for_selector("li.card")

    assert ui.requests_matching("/api/candidate-images/") == []
    assert "No scan was found for this work." in ui.text()
    # Chunk 21's point, still standing at the far end of the pipe.
    assert "not_held" not in ui.text()
    assert "not held" in ui.text()


def test_a_work_whose_every_scan_was_turned_down_is_not_told_nothing_was_found(ui):
    """The other reason a card carries no picture, and it reads oppositely.

    `shown` is null in two states — nothing was ever found, and the curator
    rejected all of it — and the producer distinguishes them with
    `instances_surviving`, saying so in its own docstring. Flattening both into
    "No scan was found for this work" put that sentence directly above a
    disclosure listing the scans just turned down, beside a badge still reading
    "has an image", because rejecting an image deliberately does not rewrite
    `resolution_status`. Three parts of one card disagreeing, and the MCP surface
    answering the opposite for the same work.

    The counts are set explicitly because `a_card` derives both from `shown`, so
    its defaults cannot express a work that holds scans and shows none — which is
    exactly why nothing caught this.
    """
    ui.serve(
        f"**/api/runs/{RUN_ID}/candidates*",
        a_candidate_page(
            [
                a_card(
                    work=a_candidate(resolution_status=ResolutionStatus.RESOLVED.value),
                    shown=None,
                    instances_held=5,
                    instances_surviving=0,
                )
            ]
        ),
    )
    ui.open(f"#review/{RUN_ID}")
    ui.page.wait_for_selector("li.card")

    assert "You have turned down everything that was found for it." in ui.text()
    assert "No scan was found for this work." not in ui.text()
    # The third disagreeing part, now settled. `resolution_status` describes what
    # the RUN found and rejecting an image deliberately does not rewrite it — so
    # the column was right and "has an image" was the wrong tense for it. The
    # badge and the sentence now say compatible things about the same card.
    assert "the run found an image" in ui.text()
    assert "has an image" not in ui.text(), (
        "a present-tense badge beside 'you have turned down everything that was found for it' "
        "is the contradiction this card had three of"
    )
    # **No way back is offered, because there is none.** An earlier version of
    # this fix told the curator to "restore one from the scans below"; every row
    # there renders its controls as null once rejected, no restore endpoint
    # exists, and `select_image` refuses a rejected instance on purpose so that a
    # rejection survives the next re-search. Asserted as an absence because a
    # sentence promising an impossible action is the defect this test guards.
    assert "estore" not in ui.text(), "the card offers a way back that the product does not have"


# -- getting there and back ---------------------------------------------------


def test_the_run_view_offers_the_way_into_the_grid(ui):
    """A screen reachable only by typing its fragment is a screen nobody finds."""
    ui.serve("**/api/estimate?*", an_estimate())
    ui.serve(f"**/api/runs/{RUN_ID}/spend", a_spend())
    ui.serve(
        f"**/api/runs/{RUN_ID}",
        a_run_view(
            run=a_run(status=RunStatus.COMPLETED.value, is_terminal=True, completed_at="2026-08-05T10:05:00+00:00"),
            works=[a_candidate()],
        ),
    )
    ui.serve_image("**/api/candidate-images/*/preview")
    ui.serve(f"**/api/runs/{RUN_ID}/candidates*", a_candidate_page([a_card()]))

    ui.open(f"#run/{RUN_ID}")
    ui.page.click("button:has-text('Review these works')")

    ui.page.wait_for_selector("li.card")
    assert ui.page.url.endswith(f"#review/{RUN_ID}")


def test_a_run_holding_no_works_offers_no_way_into_an_empty_grid(ui):
    """The paired negative: a button onto nothing is a promise the next screen breaks."""
    ui.serve("**/api/estimate?*", an_estimate())
    ui.serve(f"**/api/runs/{RUN_ID}/spend", a_spend())
    ui.serve(
        f"**/api/runs/{RUN_ID}",
        a_run_view(run=a_run(status=RunStatus.COMPLETED.value, is_terminal=True), works=[]),
    )

    ui.open(f"#run/{RUN_ID}")
    ui.page.wait_for_selector("#view p.note")

    assert "Review these works" not in ui.text()


# -- the collection's offers say why they are there, once per query ------------


def _offer(work_id, title, *, artist="Salvador Dalí", matched=25):
    """One offered work, as the supplement writes it: its query and that query's total."""
    return a_card(
        work=a_candidate(
            work_id=work_id,
            title=title,
            provenance=WorkProvenance.OFFERED.value,
            offered_for_artist=artist,
            offered_artist_matched=matched,
        )
    )


def test_the_offer_does_not_deny_the_works_the_same_page_shows_the_run_naming(grid):
    """The sentence that read as false to the only person who could check it.

    An artist reaches the supplement by having *any* named work come back without
    an image, and the run's named works sit on this very page badged `not held`.
    The old wording called them "an artist this run named but could not confirm a
    work for", which is true only under a reading of *confirm* that the page
    never teaches — so twelve cards denied the seven works above them.

    What the run failed to do was find an **image**. The page says that now, in
    those terms, and this test pins the words rather than the field: the defect
    was entirely in the words.
    """
    grid.serve(
        f"**/api/runs/{RUN_ID}/candidates*",
        a_candidate_page(
            [
                a_card(
                    work=a_candidate(
                        work_id="named",
                        title="The Persistence of Memory",
                        resolution_status=ResolutionStatus.UNRESOLVED.value,
                        unresolved_reason="not_held",
                    )
                ),
                _offer("gift-1", "Lobster Telephone"),
            ]
        ),
    )
    grid.open(f"#review/{RUN_ID}")
    grid.page.wait_for_selector("li.card")

    shown = grid.text()
    assert "found no image for 1 work it named by this artist" in shown
    assert "could not confirm a work for" not in shown, "the page still denies work it is showing"


def test_the_offer_says_its_query_once_rather_than_on_every_card(grid):
    """One thirty-word sentence, twelve times down a page, is what this replaced.

    The fact is about the *query* — which artist, and how many works the
    collection holds by them — so it belongs where that query's works are, said
    once. `product-brief.md`'s offered-works bullet was amended to require
    exactly that, and this is the assertion that the amendment is honoured.
    """
    grid.serve(
        f"**/api/runs/{RUN_ID}/candidates*",
        a_candidate_page([_offer(f"gift-{n}", f"Offered work {n}") for n in range(1, 5)]),
    )
    grid.open(f"#review/{RUN_ID}")
    grid.page.wait_for_selector("li.card")

    assert grid.page.locator("li.card").count() == 4
    assert grid.text().count("The collection holds") == 1, "the query's fact is repeated per card"


def test_the_offer_reconciles_what_the_collection_holds_with_what_one_run_shows(grid):
    """Twenty-five holdings beside twelve cards, with nothing explaining the gap.

    Each number was honest alone and no view reconciled them, which invites a
    curator to hunt for thirteen works that were never coming. The count of cards
    is derived from the cards themselves, so it cannot drift from the page the way
    a total composed on the server did.
    """
    grid.serve(
        f"**/api/runs/{RUN_ID}/candidates*",
        a_candidate_page([_offer(f"gift-{n}", f"Offered work {n}") for n in range(1, 4)]),
    )
    grid.open(f"#review/{RUN_ID}")
    grid.page.wait_for_selector("li.card")

    group = grid.page.locator("section.offer-group")
    assert group.count() == 1
    assert "The collection holds 25 works by them; these 3 are what this run offered." in group.inner_text()


def test_the_offer_reconciliation_agrees_over_a_single_offered_work(grid):
    """ "these 1 are" is "1 works" with an extra word in it.

    The demonstrative agrees as well as the verb, and this sentence carries both.
    The test above shows three offered works, where every spelling is right; one
    offered work out of a collection holding several is the ordinary case, and it
    is where the two diverge.
    """
    grid.serve(f"**/api/runs/{RUN_ID}/candidates*", a_candidate_page([_offer("gift-1", "The only offered work")]))
    grid.open(f"#review/{RUN_ID}")
    grid.page.wait_for_selector("li.card")

    said = grid.page.locator("section.offer-group").inner_text()
    assert "this 1 is what this run offered" in said
    assert "these 1 are" not in said


def test_a_card_truncated_by_one_scan_says_so_in_the_singular(grid):
    """The omitted count is what agrees, and a card is often truncated by one.

    Every other test of this note omits several, where the plural is right. The
    noun goes through the same helper as the verb even though the truncation
    guard already puts `held` at two or more — a reader should not have to prove
    that to trust the sentence.
    """
    grid.serve("**/api/candidates/work-1/images", an_instance_listing([an_instance(image_id="image-1")], held=2))
    grid.open(f"#review/{RUN_ID}")
    grid.page.click("summary")
    grid.page.wait_for_selector("li.alternate")

    said = grid.text()
    assert "This work holds 2 scans; 1 already turned down is not shown" in said
    assert "1 already turned down are not shown" not in said


def test_a_card_withholding_one_choosable_scan_says_so_in_the_singular(grid):
    """The other branch of the same note, and the state it describes is ordinary.

    `_fill` keeps `MAX_INSTANCES_LISTED` survivors — twelve — so a work holding
    thirteen scans with none turned down shows twelve and withholds one the
    curator could still have chosen. That is where this sentence's count is one.

    Nothing here names the choosable flag: `surviving_held` at thirteen against
    twelve shown is what puts the card in that state, and the fixture derives the
    rest. Setting the flag by hand is how this branch stayed unreachable, since
    every fixture that did not think to set it claimed the card was complete.
    """
    grid.serve(
        "**/api/candidates/work-1/images",
        an_instance_listing(
            [an_instance(image_id=f"image-{n}") for n in range(1, 13)],
            held=13,
            surviving_held=13,
        ),
    )
    grid.open(f"#review/{RUN_ID}")
    grid.page.click("summary")
    grid.page.wait_for_selector("li.alternate")

    said = grid.text()
    assert "This work holds 13 scans and 1 is not shown, including some you could still choose" in said
    assert "and 1 are not shown" not in said


def test_an_offer_that_is_the_whole_of_what_is_held_claims_no_cap(grid):
    """The paired negative: a bound that did not bite must not be described as one.

    Saying "as many as one run offers" when every work the collection holds is on
    the page tells a curator that more exist. Two of them do not.
    """
    grid.serve(
        f"**/api/runs/{RUN_ID}/candidates*",
        a_candidate_page([_offer("gift-1", "Lobster Telephone", matched=1)]),
    )
    grid.open(f"#review/{RUN_ID}")
    grid.page.wait_for_selector("li.card")

    shown = grid.text()
    assert "These are all 1 work the collection holds by them." in shown
    assert "what this run offered" not in shown, "a subset was described where every held work is present"


def test_two_queries_are_two_groups_rather_than_one_run_of_cards(grid):
    """Each query's works sit under their own heading, with their own numbers.

    A single offered block would put one artist's holdings total above another
    artist's works — the per-group fact landing on the wrong group, which is the
    same class of error as landing it on every card.
    """
    grid.serve(
        f"**/api/runs/{RUN_ID}/candidates*",
        a_candidate_page(
            [
                _offer("dali-1", "Lobster Telephone", artist="Salvador Dalí", matched=25),
                _offer("kelly-1", "Spectrum IV", artist="Ellsworth Kelly", matched=400),
            ]
        ),
    )
    grid.open(f"#review/{RUN_ID}")
    grid.page.wait_for_selector("li.card")

    # Scoped to each group rather than matched across the page: two groups whose
    # sentences had been swapped would satisfy every page-wide assertion, and the
    # association between a query and its numbers is the whole requirement.
    # Selected by the QUERY, not by visible text. A card carries the collection's
    # own attribution, which differs from the query the brief requires verbatim —
    # so `has_text="Salvador Dalí"` matched both groups, the Kelly one through its
    # card's artist line. The attribute is the only unambiguous handle.
    dali = grid.page.locator("section.offer-group[data-offer-artist='Salvador Dalí']")
    kelly = grid.page.locator("section.offer-group[data-offer-artist='Ellsworth Kelly']")
    assert dali.count() == 1 and kelly.count() == 1

    # The visible heading, not only the attribute. Rescoping these assertions to
    # `data-offer-artist` removed the last assertion on rendered heading text —
    # after which deleting the artist's name from the h3 would leave the whole
    # browser suite green while putting #95's symptom back, hidden behind an
    # attribute nobody can see.
    # `h3:not(.card-title)` because a card's own title is an h3 too — the group
    # heading and the works it heads are the same rank in the markup, which is
    # worth its own look and is recorded as such rather than changed in passing.
    assert "Offered by the collection — Salvador Dalí" in dali.locator("h3:not(.card-title)").inner_text()
    assert "Offered by the collection — Ellsworth Kelly" in kelly.locator("h3:not(.card-title)").inner_text()

    assert "holds 25 works" in dali.inner_text()
    assert "holds 400 works" not in dali.inner_text(), "one query's holdings total sits above another's works"
    assert "holds 400 works" in kelly.inner_text()
    assert dali.locator("li.card[data-work='dali-1']").count() == 1
    assert kelly.locator("li.card[data-work='kelly-1']").count() == 1


def test_an_offer_whose_query_was_never_recorded_still_reaches_the_page(grid):
    """Grouping must not become a filter.

    Bucketing offers by their query invites the version that skips one with no
    query recorded — and a review surface quietly showing fewer works than the run
    holds is a worse defect than the mislabelling this grouping fixes, because
    nothing on the page shows the absence. It gets the heading without a name and
    a sentence that claims no total it does not have.
    """
    grid.serve(
        f"**/api/runs/{RUN_ID}/candidates*",
        a_candidate_page(
            [
                a_card(
                    work=a_candidate(
                        work_id="orphan",
                        title="Lobster Telephone",
                        provenance=WorkProvenance.OFFERED.value,
                    )
                )
            ]
        ),
    )
    grid.open(f"#review/{RUN_ID}")
    grid.page.wait_for_selector("li.card")

    assert grid.page.locator("li.card[data-work='orphan']").count() == 1
    shown = grid.text()
    assert "The collection offered 1 work it holds by them." in shown
    assert "The collection holds" not in shown, "a total was invented for a group that recorded none"


def test_the_offer_counts_only_the_named_works_that_found_no_image(grid):
    """An artist reaches the supplement without *all* their works having failed.

    The selection is "any named work came back unresolved", so an artist may have
    others that resolved perfectly well. Counting every named work — or saying
    "none of them" — would be false for exactly those artists, which is the same
    shape of claim, on the same page, that this whole change removes. The fixture
    is the mixed case: two named works, one resolved, one not.
    """
    grid.serve(
        f"**/api/runs/{RUN_ID}/candidates*",
        a_candidate_page(
            [
                a_card(work=a_candidate(work_id="found", title="The Elephants")),
                a_card(
                    work=a_candidate(
                        work_id="missing",
                        title="The Persistence of Memory",
                        resolution_status=ResolutionStatus.UNRESOLVED.value,
                        unresolved_reason="not_held",
                    )
                ),
                _offer("gift-1", "Lobster Telephone"),
            ]
        ),
    )
    grid.open(f"#review/{RUN_ID}")
    grid.page.wait_for_selector("li.card")

    shown = grid.text()
    assert "found no image for 1 work it named by this artist" in shown
    assert "2 works it named" not in shown, "a work the run did find an image for was counted as a failure"


def test_an_offer_with_nothing_named_beside_it_claims_no_failed_works(grid):
    """The paired negative: the clause is omitted, not printed with a zero.

    A re-search grid, or a page whose named works are not in view, leaves nothing
    to count. "found no image for 0 works it named" is the sentence a guard that
    fires on every group produces, and it is worse than silence.
    """
    grid.serve(
        f"**/api/runs/{RUN_ID}/candidates*",
        a_candidate_page([_offer("gift-1", "Lobster Telephone")]),
    )
    grid.open(f"#review/{RUN_ID}")
    grid.page.wait_for_selector("li.card")

    shown = grid.text()
    assert "found no image for" not in shown, "a failure clause was printed for works that are not there"
    assert "The collection holds 25 works by them;" in shown, "the holdings clause must still stand alone"


def test_the_group_heading_rule_does_not_reach_the_cards_inside_the_group(grid):
    """A heading rule scoped with a descendant selector re-margins the works it heads.

    `.offer-group h3` is more specific than `.card-title` and declared later, so
    the descendant form silently won on every card title inside a group: offered
    works' titles sat further from their artist line than the named works' did, on
    the same page, for no reason a reader could find. It shipped that way and a
    reviewer reading the selector caught it — `>` is the whole fix.

    **Asserted on computed style because nothing else can see it.** Every other
    check here reads text or attributes, and all of them are correct whichever
    selector is written. The judgement half of the styling — does the heading read
    as a heading, are the groups separated — is the operator's, and stays in
    `operator-verification.md`; this is the half a machine can hold.
    """
    grid.serve(
        f"**/api/runs/{RUN_ID}/candidates*",
        a_candidate_page(
            [
                a_card(work=a_candidate(work_id="named", title="The Persistence of Memory")),
                _offer("gift-1", "Lobster Telephone"),
            ]
        ),
    )
    grid.open(f"#review/{RUN_ID}")
    grid.page.wait_for_selector("section.offer-group li.card")

    margins = grid.page.evaluate("""() => {
             const titles = [...document.querySelectorAll('li.card h3.card-title')];
             const of = (list) => list.map((n) => getComputedStyle(n).marginBottom);
             return {
               inside: of(titles.filter((n) => n.closest('.offer-group'))),
               outside: of(titles.filter((n) => !n.closest('.offer-group'))),
             };
           }""")

    assert margins["inside"], "the fixture must put a card inside an offer group"
    assert margins["outside"], "and one outside, or there is nothing to compare against"
    assert set(margins["inside"]) == set(
        margins["outside"]
    ), f"a card title is styled differently for sitting inside an offer group: {margins}"
