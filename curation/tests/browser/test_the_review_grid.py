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

from curation.persistence.discovery_records import ResolutionStatus, RunStatus, Verdict

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
