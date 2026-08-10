"""The run view: its poll loop, its supersession, and the words it puts on a card.

This is the most stateful screen the product had when this harness was built, and
every behaviour below is one a test reading JSON cannot see. Two of them are
about what the page does *not* do — repaint, and poll twice — which is why each
is paired with the assertion that would fail if it stopped doing the thing at
all.
"""

import pytest
from payloads import a_candidate, a_candidate_page, a_card, a_run, a_run_view, a_spend, an_estimate

from curation.http.models import RunListOut
from curation.persistence.discovery_records import ResolutionStatus, RunStatus, UnresolvedReason, WorkProvenance

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
    # Half a poll of slack on top of the two being waited for: the second tick
    # lands at the very edge of a tighter window, and on a loaded CI runner an
    # edge is a flake.
    ui.page.wait_for_timeout(POLL_MS * 2 + POLL_MS // 2)

    # Two polls have been and gone. The button is still under the keyboard.
    assert ui.focused() == "Approve the list"
    # Not decoration: if no poll actually happened, focus surviving says nothing
    # at all, and this test would pass against a client that stopped polling.
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


# -- the costs panel --------------------------------------------------------


@pytest.fixture
def a_finished_run(ui):
    """A run that has stopped, which is the only state that fetches the rollup."""
    ui.serve("**/api/estimate?*", an_estimate())
    ui.serve(
        f"**/api/runs/{RUN_ID}",
        a_run_view(
            run=a_run(
                status=RunStatus.COMPLETED.value,
                is_terminal=True,
                completed_at="2026-08-05T10:05:00+00:00",
                actual_cost_usd="0.0134",
            ),
            works=[a_candidate()],
        ),
    )
    return ui


def test_a_family_total_that_cannot_be_read_says_so(a_finished_run):
    """The one figure with no second home must not go missing quietly.

    `facts` drops a null pair outright, so a failed rollup fetch used to remove
    the row with nothing in its place — leaving a panel whose largest number is
    what this run alone spent, which is exactly the reading the family total was
    added to prevent.
    """
    ui = a_finished_run
    ui.page.route(f"**/api/runs/{RUN_ID}/spend", lambda route: route.fulfill(status=503, body="{}"))

    ui.open(f"#run/{RUN_ID}")
    ui.page.wait_for_selector("#view dl.facts")

    shown = ui.text()
    assert "The total including every re-search could not be read" in shown
    # The panel survives the failure: the two figures beside it are read off the
    # run record and are still true, so losing the rollup must not cost them.
    assert "Spent by this run alone" in shown


def test_a_family_total_that_reads_fine_says_nothing(a_finished_run):
    """The paired negative — the notice appears on failure and not otherwise."""
    ui = a_finished_run
    ui.serve(f"**/api/runs/{RUN_ID}/spend", a_spend())

    ui.open(f"#run/{RUN_ID}")
    ui.page.wait_for_selector("#view dl.facts")

    shown = ui.text()
    assert "could not be read" not in shown
    assert "Spent including every re-search" in shown


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

    # The *resolution* badge beside it, which is a different element and was the
    # untested third of the reword. `RESOLUTION_WORDS` was changed from
    # present-tense claims about the work to statements about what the run found,
    # and only the `resolved` entry got a guard — the assertions above all
    # concern `unresolved_reason`, and they locate `span.badge[title]`, which
    # `resolutionBadge` does not set. So `"no image"` survived every suite.
    #
    # Both halves, because only the pair says the reword happened: the new
    # wording present proves it renders, and the old wording absent proves it is
    # gone rather than sitting beside it.
    assert "the run found none" in shown
    assert "no image" not in shown, (
        "a present-tense claim about the work is what the reword removed — `resolution_status` "
        "records what the run found, and only a resolution attempt recomputes it"
    )


# -- a watch that cannot recover --------------------------------------------


#: The client gives up after this many consecutive failures. Read from the module
#: under test would be better; it is a `const` in a script, so it is restated
#: here and `test_the_client_and_this_test_agree_on_the_limit` holds the pair
#: together rather than leaving two numbers to drift.
MAX_FAILURES = 5

#: What the service answers for a run id it does not know — the case that made
#: this necessary. A bookmarked `#run/<id>` outlives its run.
GONE = (400, {"error": "There is no run with that id."})


def test_the_client_and_this_test_agree_on_the_limit(ui):
    """Two numbers, one meaning. Asserted rather than assumed.

    If the client's limit rises and this one does not, the terminate test below
    waits too short a window and reports a stopped poll that is merely slow —
    green for the wrong reason, which is worse than red.
    """
    ui.open("")

    assert ui.page.evaluate("() => RUN_POLL_MAX_FAILURES") == MAX_FAILURES


def test_a_run_that_will_never_answer_stops_being_watched(ui):
    """The loop proved to terminate, rather than read to.

    Opening a stale bookmarked `#run/<id>` after the run is gone had the service
    answer 400, the catch re-arm, and the tab request that run every two seconds
    for as long as it stayed open — bounded only by navigation, with nothing on
    screen saying the watch was still retrying.

    Asserted on the request count across a window several polls longer than the
    limit, because that is the only thing that distinguishes a loop that stopped
    from one that is between ticks.
    """
    ui.serve(f"**/api/runs/{RUN_ID}", GONE)

    ui.page.goto(f"{ui.base_url}/#run/{RUN_ID}")
    ui.page.wait_for_selector("#error:not([hidden])")

    # Long enough for several more polls than the limit allows, so a loop that
    # merely slowed down would still be caught.
    ui.page.wait_for_timeout(POLL_MS * (MAX_FAILURES + 3))
    attempts = len(ui.requests_matching(f"/api/runs/{RUN_ID}"))

    assert attempts == MAX_FAILURES, f"{attempts} requests for a run that will never exist — the watch did not stop"


def test_a_watch_that_gave_up_says_so_rather_than_only_what_failed(ui):
    """ "The server answered 400" leaves a live page indistinguishable from a dead one.

    The curator needs two facts and the message used to carry one: what went
    wrong, and whether anything is still trying. Only the second tells them
    whether to keep looking at the screen.
    """
    ui.serve(f"**/api/runs/{RUN_ID}", GONE)

    ui.page.goto(f"{ui.base_url}/#run/{RUN_ID}")
    ui.page.wait_for_selector("#error:not([hidden])")
    ui.page.wait_for_timeout(POLL_MS * (MAX_FAILURES + 1))

    message = ui.page.inner_text("#error")
    assert "Gave up watching this run" in message
    assert "reload" in message, "saying it stopped without saying how to resume leaves the curator stuck"
    assert "There is no run with that id." in message, "the original fault must survive; it is the diagnosis"


def test_one_blip_does_not_end_the_watch(ui):
    """The behaviour the unconditional re-arm was right about, kept.

    A curator watching a live run through a single 502 must not be left on a
    stale page. The failure count exists to end a watch that *cannot* recover,
    and a fix that ended this one too would trade a rare annoyance for a common
    one.
    """
    ui.serve("**/api/estimate?*", an_estimate())
    ui.serve(
        f"**/api/runs/{RUN_ID}",
        [
            (502, {"error": "The server answered 502."}),
            a_run_view(run=a_run(status=RunStatus.RESOLVING_WORKS.value)),
        ],
    )

    ui.page.goto(f"{ui.base_url}/#run/{RUN_ID}")

    # The run's own content arriving is the recovery: it can only be painted by
    # a poll that the blip did not stop.
    ui.page.wait_for_selector("#view p.note")
    assert "Something by Dalí" in ui.text()
    assert ui.page.is_hidden("#error"), "a recovered watch must clear the message, not leave it accusing"


def test_a_success_clears_the_failure_count(ui):
    """Consecutive, not cumulative — asserted on the count itself.

    The behavioural version below is the one that matters, but it takes a window
    of several polls to become decisive and a shorter one leaves this exact
    mutation alive: a sweep that deleted the reset survived, because failures
    separated by successes had not yet added up to the limit inside the window
    being watched. This reads the count directly, so nothing rests on how long
    the test waited.
    """
    ui.serve("**/api/estimate?*", an_estimate())
    good = a_run_view(run=a_run(status=RunStatus.RESOLVING_WORKS.value))
    bad = (502, {"error": "The server answered 502."})
    ui.serve(f"**/api/runs/{RUN_ID}", [bad, bad, good])

    ui.page.goto(f"{ui.base_url}/#run/{RUN_ID}")
    ui.page.wait_for_selector("#view p.note")

    assert ui.page.evaluate("() => state.watch.failures") == 0, (
        "two failures then a success left the count standing — counted that way, a flaky "
        "connection exhausts the budget over a long session and stops a watch that is working"
    )


def test_failures_with_a_success_between_them_never_end_the_watch(ui):
    """The same rule as behaviour: a watch that keeps recovering is never ended.

    A flaky connection that fails four times, recovers, and fails four more must
    not be stopped — counted cumulatively it would be, on the sixth request.

    **The window is sized so that the two rules disagree inside it**, which is the
    part a shorter version got wrong: four-failure bursts separated by a success
    exhaust a cumulative budget at request six, so anything past six proves the
    count is consecutive rather than proving only that the test was impatient.
    """
    ui.serve("**/api/estimate?*", an_estimate())
    good = a_run_view(run=a_run(status=RunStatus.RESOLVING_WORKS.value))
    bad = (502, {"error": "The server answered 502."})
    ui.serve(f"**/api/runs/{RUN_ID}", [bad, bad, bad, bad, good, bad, bad, bad, bad, good])

    ui.page.goto(f"{ui.base_url}/#run/{RUN_ID}")
    ui.page.wait_for_selector("#view p.note")
    ui.page.wait_for_timeout(POLL_MS * 4 + 500)

    attempts = len(ui.requests_matching(f"/api/runs/{RUN_ID}"))

    assert attempts > 6, (
        f"only {attempts} requests — a cumulative count gives up on the sixth, so the watch "
        "was ended by failures that had a success between them"
    )


# -- the discovery listing's own truncation ---------------------------------


def _a_run_list(count: int, total: int) -> dict:
    """A `/api/runs` payload as the capped service now produces one."""
    return RunListOut(
        runs=[a_run(run_id=f"r{index}", intent=f"request {index}") for index in range(count)],
        count=count,
        total=total,
        truncated=total > count,
    ).model_dump(mode="json")


def test_a_truncated_search_list_says_how_much_history_it_is_not_showing(ui):
    """The signal the server gained and the client dropped for one commit.

    Capping `list_runs` bounded a payload that had grown with every search ever
    made. It also made "Searches (50)" over a history of four hundred a silently
    short list — indistinguishable from a complete one, which is how a curator
    concludes their older searches are gone. `total` and `truncated` were on the
    wire and nothing here read them.
    """
    ui.serve("**/api/runs*", _a_run_list(count=50, total=407))

    ui.open("#discovery")
    ui.page.wait_for_selector("h3:has-text('Searches')")

    text = ui.text()
    assert "50 of 407" in text
    assert "does not page" in text, "a note implying paging sends a curator to an affordance that does not exist"


def test_a_complete_search_list_says_nothing_about_truncation(ui):
    """Saying nothing is the honest answer when nothing was left behind."""
    ui.serve("**/api/runs*", _a_run_list(count=4, total=4))

    ui.open("#discovery")
    ui.page.wait_for_selector("h3:has-text('Searches')")

    text = ui.text()
    assert "Searches (4)" in text
    assert "of 4" not in text, "a complete list must not be dressed as a partial one"
    assert "does not page" not in text


def test_the_run_table_does_not_head_a_column_with_the_works_own_provenance(ui):
    """ "Where it came from" meant how a row entered the run; it reads as which museum holds it.

    Removed rather than renamed. The offered/asked-for distinction is real, and
    this table was its fourth statement — after the tally's separate counts, the
    run sentence, and the line directly above these rows. What a per-row badge
    added was which *particular* work was offered, on a screen where nothing is
    decided per work.

    Asserted on both halves: the misleading heading is gone, and the counts that
    carry the distinction are still there. Dropping the column and the counts
    together would have removed the fact rather than the fourth copy of it.
    """
    ui.serve("**/api/estimate?*", an_estimate())
    ui.serve(f"**/api/runs/{RUN_ID}", a_run_view(works=[a_candidate()]))

    ui.open(f"#run/{RUN_ID}")
    ui.page.wait_for_selector("table")

    text = ui.text()
    assert "Where it came from" not in text
    assert "asked for" in text and "offered by the collection" in text, (
        "the offered/asked-for distinction must survive its per-row copy being removed — "
        "it is what tells a curator the list is longer than the one they authorised"
    )


def test_the_review_card_still_says_which_works_were_offered(ui):
    """The distinction stays where the deciding happens.

    A curator judging a card may reasonably hold an offered work to a different
    standard: they did not ask for it. That is a per-work fact on the one surface
    where per-work decisions are made, which is exactly what the run table is not.
    """
    ui.serve("**/api/estimate?*", an_estimate())
    ui.serve(f"**/api/runs/{RUN_ID}", a_run_view(works=[a_candidate()]))
    ui.serve(
        f"**/api/runs/{RUN_ID}/candidates*",
        a_candidate_page([a_card(work=a_candidate(provenance="offered"))]),
    )

    ui.open(f"#review/{RUN_ID}")
    ui.page.wait_for_selector(".card")

    assert "offered" in ui.text()


def test_the_run_sentence_does_not_deny_the_works_listed_underneath_it(ui):
    """Issue #95's denial lived on this page too, and this is the page seen first.

    The review grid's version was the reported one, but the same claim — that the
    run named nothing it could confirm for those artists — was composed here, in
    the sentence printed directly above the table that lists those very works with
    their `not held` badges. Fixing one surface and not the other would have left
    the defect standing exactly where a curator meets it first, while the records
    said it was gone.

    "found no image for" is what all three surfaces say now. The third is the MCP
    run summary, pinned by its own assertion in
    `tests/unit/test_offered_works.py` — **not** by `test_surface_parity.py`,
    which an earlier version of this docstring claimed: that module pins field
    *names* and `_verdict_notice`, says nothing about `_run_notice`, and cannot
    reach `app.js` at all, so no parity test can ever cover this particular
    trio.
    """
    named = a_candidate(
        work_id="named",
        title="The Persistence of Memory",
        resolution_status=ResolutionStatus.UNRESOLVED.value,
        unresolved_reason=UnresolvedReason.NOT_HELD.value,
    )
    offered = a_candidate(
        work_id="gift",
        title="Lobster Telephone",
        provenance=WorkProvenance.OFFERED.value,
        offered_for_artist="Salvador Dalí",
        offered_artist_matched=25,
    )
    run = a_run(status=RunStatus.COMPLETED.value, is_terminal=True)
    ui.serve(f"**/api/runs/{RUN_ID}", a_run_view(run=run, works=[named, offered]))
    ui.open(f"#run/{RUN_ID}")
    ui.page.wait_for_selector("table")

    shown = ui.text()
    # Singular at a count of one. The first version of this assertion pinned
    # "1 more works" — a test can hold a grammatical bug still just as firmly as
    # it holds a behaviour, and this one did until a reviewer read the string.
    assert "the collection offered 1 more work by artists this run found no image for" in shown
    assert "1 more works" not in shown
    assert "could not confirm" not in shown, "the run view still denies work it lists directly below"

    # The column heading, over the cell that answers it. The run named none of
    # the offered works and that cell says so, so a heading asserting naming is
    # contradicted one column across — the same defect this change removes.
    # `all_text_contents`, not `all_inner_texts`: the header cells carry
    # `text-transform: uppercase`, and inner_text returns what the transform
    # renders rather than what the client wrote.
    headings = ui.page.locator("table th").all_text_contents()
    assert "Why it is here" in headings, headings
    assert "Why the run named it" not in headings
