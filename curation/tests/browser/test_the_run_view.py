"""The run view: its poll loop, its supersession, and the words it puts on a card.

This is the most stateful screen the product had when this harness was built, and
every behaviour below is one a test reading JSON cannot see. Two of them are
about what the page does *not* do — repaint, and poll twice — which is why each
is paired with the assertion that would fail if it stopped doing the thing at
all.
"""

import pytest
from payloads import a_candidate, a_run, a_run_view, a_spend, an_estimate

from curation.persistence.discovery_records import ResolutionStatus, RunStatus, UnresolvedReason

# At import time, not in a fixture. A marker deselection still *collects* this
# module, so the default run — which does not install the browser group — has to
# skip here rather than fail on the missing plugin.
pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

RUN_ID = "run-under-test"

#: The client polls every two seconds. Windows below are expressed in whole
#: polls so they survive a change to that interval being read here rather than
#: recomputed by hand at each call site.
POLL_MS = 2000


@pytest.fixture
def at_the_gate(ui):
    """A run stopped at the approval gate, with the estimate the gate fetches.

    The gate is the state worth holding the harness at: it is the one screen with
    a decision on it, it is the only state that fetches a second endpoint mid-
    paint, and it is where a curator actually stands still long enough for a
    repaint to cost them something.
    """
    ui.serve(f"**/api/runs/{RUN_ID}", a_run_view(works=[a_candidate()]))
    ui.serve("**/api/estimate?*", an_estimate())
    return ui


# -- a poll that changes nothing --------------------------------------------


def test_a_poll_that_changes_nothing_leaves_the_focus_alone(at_the_gate):
    """The defect this whole harness was moved up the order for.

    `render` replaces the entire view, which destroys whatever the keyboard user
    was standing on. Tabbing to "Approve the list" and pausing to read lost the
    focus two seconds later, every time, on the one screen whose whole job is to
    be decided on.
    """
    ui = at_the_gate
    ui.open(f"#run/{RUN_ID}")
    ui.page.wait_for_selector("button:has-text('Approve the list')")

    ui.page.focus("button:has-text('Approve the list')")
    ui.page.wait_for_timeout(POLL_MS * 2 + 500)

    # Two polls have been and gone. The button is still under the keyboard.
    assert ui.focused() == "Approve the list"
    assert len(ui.requests_matching(f"/api/runs/{RUN_ID}")) >= 3


def test_a_poll_that_changes_something_does_repaint(ui):
    """The paired negative: suppression must not become never repainting.

    A run whose work list fills in underneath a settled status is exactly the
    change worth repainting for, and a signature check written too broadly would
    leave the page frozen while the run moved on.
    """
    ui.serve("**/api/estimate?*", an_estimate())
    ui.serve(
        f"**/api/runs/{RUN_ID}",
        [
            a_run_view(works=[a_candidate(work_id="w1", title="First")]),
            a_run_view(
                works=[
                    a_candidate(work_id="w1", title="First"),
                    a_candidate(work_id="w2", title="Second arrival"),
                ]
            ),
        ],
    )
    ui.open(f"#run/{RUN_ID}")
    ui.page.wait_for_selector("td:has-text('First')")

    assert "Second arrival" not in ui.text()
    ui.page.wait_for_selector("td:has-text('Second arrival')", timeout=POLL_MS * 3)


# -- two paints racing ------------------------------------------------------


def test_two_concurrent_paints_leave_only_one_poll_chain(at_the_gate):
    """Pressing a button while a poll is mid-request must not double the rate.

    Each paint schedules the next look at the run, so two chains do not merely
    duplicate one request — they double the request rate on every tick
    thereafter, for as long as the page stays open.

    What holds the rate down is the check `scheduleRunPoll` makes when the timer
    *fires*, not the one the paint makes when its answer lands: a superseded
    paint still schedules, and its timer then finds the world moved on and does
    nothing. The paint-time check earns its place elsewhere, and the test below
    is what pins it.
    """
    ui = at_the_gate
    ui.open(f"#run/{RUN_ID}")
    ui.page.wait_for_selector("button:has-text('Approve the list')")

    before = len(ui.requests_matching(f"/api/runs/{RUN_ID}"))
    # A second paint started while the first is still the one on screen — the
    # same collision as pressing Approve during a poll, without the timing
    # dependence of actually racing a click against one.
    ui.page.evaluate("() => { refresh(); refresh(); }")

    ui.page.wait_for_timeout(POLL_MS * 3 + 500)
    polls = len(ui.requests_matching(f"/api/runs/{RUN_ID}")) - before

    # Two immediate paints, then one chain ticking three times. A second chain
    # would add three more, so this sits either side of the two outcomes.
    assert polls <= 6, f"{polls} requests in three polls — a second chain is running"
    assert polls >= 3, f"only {polls} requests — the poll chain stopped altogether"


def test_a_paint_superseded_in_flight_never_reaches_the_page(ui):
    """A curator who moves on must not have the page they left painted over them.

    The paint claims a generation before its request goes out and checks it again
    when the answer lands. Without that check a run's answer arriving after the
    curator navigated away paints that run's works into whatever replaced it —
    the id in the fragment saying one thing and the page showing another.

    Driven by superseding the paint directly rather than by racing a real click
    against a real response, because the defect is a *lost race* and a test that
    had to win one to see it would report a green that meant only that the
    machine was fast that time.
    """
    ui.serve("**/api/estimate?*", an_estimate())
    ui.serve(f"**/api/runs/{RUN_ID}", a_run_view(run=a_run(status=RunStatus.RESOLVING_WORKS.value)))
    ui.serve(
        "**/api/runs/left-behind",
        a_run_view(run=a_run(run_id="left-behind", intent="A run left behind", status=RunStatus.RESOLVING_WORKS.value)),
    )

    ui.open(f"#run/{RUN_ID}")
    ui.page.wait_for_selector("#view p.note")

    # A paint begins, and something supersedes it before its answer lands — which
    # is what navigating away does, expressed without the timing.
    ui.page.evaluate("() => { const painting = viewRun('left-behind'); state.poll += 1; return painting; }")

    assert "A run left behind" not in ui.text()
    assert "Something by Dalí" in ui.text()


def test_leaving_the_run_view_stops_its_polling(at_the_gate):
    """A run page left behind must not keep repainting under what replaced it."""
    ui = at_the_gate
    ui.open(f"#run/{RUN_ID}")
    ui.page.wait_for_selector("button:has-text('Approve the list')")

    ui.page.click("nav.tabs button[data-view='health']")
    ui.page.wait_for_selector("h2:has-text('Health')")

    settled = len(ui.requests_matching(f"/api/runs/{RUN_ID}"))
    ui.page.wait_for_timeout(POLL_MS * 2 + 500)

    assert len(ui.requests_matching(f"/api/runs/{RUN_ID}")) == settled


# -- which kind of nothing --------------------------------------------------


@pytest.mark.parametrize("reason", list(UnresolvedReason))
def test_an_unresolved_work_says_which_kind_of_nothing(ui, reason):
    """Every reason reaches the page as words, and never as its raw token.

    Parametrised over the enum rather than over a list written here: a sixth
    reason added to `UnresolvedReason` arrives as a failure in this test, which
    is the only thing that stops it reaching a curator's card as
    `identity_refused`-shaped noise.
    """
    ui.serve("**/api/estimate?*", an_estimate())
    ui.serve(f"**/api/runs/{RUN_ID}/spend", a_spend())
    ui.serve(
        f"**/api/runs/{RUN_ID}",
        a_run_view(
            run=a_run(status=RunStatus.COMPLETED.value, is_terminal=True, completed_at="2026-08-05T10:05:00+00:00"),
            works=[
                a_candidate(
                    resolution_status=ResolutionStatus.UNRESOLVED.value,
                    unresolved_reason=reason.value,
                )
            ],
        ),
    )
    ui.open(f"#run/{RUN_ID}")
    ui.page.wait_for_selector("table")

    shown = ui.text()
    assert reason.value not in shown, f"the raw token {reason.value!r} reached the page"

    # Both halves of the badge, read off the one element: the short phrase it
    # shows, and the sentence behind it saying what that phrase means. A badge
    # with an empty title looks correct in a screenshot and tells a curator
    # nothing about which kind of nothing they are looking at.
    badge = ui.page.locator("#view span.badge[title]").filter(has=ui.page.locator("span.glyph", has_text="▲"))
    assert badge.count() == 1
    assert badge.inner_text().strip(), f"{reason.value} reached the page with no words"

    sentence = badge.get_attribute("title")
    assert sentence, f"{reason.value} reached the page with no sentence behind it"
    assert sentence.endswith("."), f"the sentence for {reason.value} is not one: {sentence!r}"
