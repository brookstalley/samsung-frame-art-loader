"""Archiving a work, and putting it back, in a real browser.

**The label is the deliverable.** `information-architecture.md` rules that
"Remove" is the wrong word for a work — the record survives, every theme holding
it survives, and restoration is one click away — so the control reads *Archive*
with *Restore* as its undo. That rule is only true if it is true on the page, and
no Python suite reads a line of the page.

**The confirmation is the other half, and it is the half that reaches the room.**
Archiving a work that a wall is showing takes a picture off it, and
`architecture.md` calls silence about that "precisely this product's
characteristic failure". So the question names the walls — and it names them by
building each wall's manifest, which is the only thing that can tell a picture
that is *hanging* from one that is merely in a hung theme and excluded from it.

The asymmetry is the point of most of this file: a sentence when there is a
consequence, no sentence at all when there is not. A confirmation that always
said something about walls would be indistinguishable from one that had never
looked.
"""

import pytest

# At import time, not in a fixture. A marker deselection still *collects* this
# module, so the default run — which does not install the browser group — has to
# skip here rather than fail on the missing plugin.
pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)


@pytest.fixture
def hang(services):
    """Put works in a theme and hang it on a wall, which is what "showing" means.

    Named for the act rather than for the fixtures it composes, because every
    test here is about the difference between a work that a room is showing and
    one that it is not.
    """

    def _hang(*works, wall_name=None, theme_name="Late night"):
        wall = services.display.add_wall(name=wall_name) if wall_name else services.display.survey_walls()[0].wall
        theme = services.display.add_theme(name=theme_name)
        for position, work in enumerate(works):
            services.display.add_to_theme(theme_id=theme.id, artwork_id=work.id, position=position)
        services.display.activate_theme(theme.id, wall_id=wall.id)
        return wall

    return _hang


def open_work(ui, work):
    ui.open(f"#work/{work.id}")
    ui.page.wait_for_selector("#view h2")


def ask(ui, label):
    """Press the circulation control and wait for the platform to make it modal."""
    ui.page.click(f"#view button:has-text('{label}')")
    ui.page.wait_for_selector("dialog.confirm[open]")


# -- the label -----------------------------------------------------------------


def test_the_control_reads_archive_and_is_styled_as_an_ordinary_act(ui, service):
    """Not `danger`, and there is no danger class in this stylesheet to reach for.

    Archive's whole point is that Restore exists. Dressing a cheap reversible act
    as a destructive one produces exactly the hesitation the IA argues the word
    "Remove" produces — and teaches the operator that this dialog means danger,
    which is the wrong lesson on the day one of them is not.
    """
    work = service.add_artwork(title="Chop Suey")
    open_work(ui, work)

    control = ui.page.locator("#view button", has_text="Archive")

    assert control.count() == 1
    assert control.inner_text() == "Archive"
    assert control.get_attribute("class") == "action"


@pytest.mark.parametrize("word", ["Remove", "Delete"])
def test_no_control_on_this_screen_offers_to_get_rid_of_the_work(ui, service, word):
    """The acceptance criterion, asserted where a curator would meet a violation."""
    work = service.add_artwork(title="Chop Suey")
    open_work(ui, work)

    assert ui.page.locator("#view button", has_text=word).count() == 0


def test_an_archived_work_offers_the_way_back(ui, service):
    """Restoration has to be discoverable, and this is the only place it is offered.

    A work whose only route back was an agent's tool call would be archived in
    practice as well as in status — the curator who archived it by mistake has
    nothing to press.
    """
    work = service.add_artwork(title="Chop Suey")
    service.archive_artwork(work.id)

    open_work(ui, work)

    control = ui.page.locator("#view button", has_text="Restore")
    assert control.count() == 1
    assert control.inner_text() == "Restore"


# -- the wall consequence ------------------------------------------------------


def test_the_confirmation_names_the_wall_that_is_showing_the_work(ui, ready_work, hang):
    """Which room loses the picture, evaluated from that wall's own manifest."""
    work = ready_work(title="Nighthawks")
    wall = hang(work)

    open_work(ui, work)
    ask(ui, "Archive")

    assert ui.page.inner_text(".confirm-title") == "Archive Nighthawks?"
    assert wall.name in ui.page.inner_text(".confirm-consequence")


def test_the_confirmation_says_how_to_make_the_room_catch_up(ui, ready_work, hang):
    """When *and* how, because the ruling that allows the delay rests on the how.

    Nothing in the archive path republishes a manifest, so the picture stays up
    until something rebuilds that wall. The operator ruled that acceptable on
    condition that a path exists to force one — which makes the remedy part of
    the sentence rather than a nicety, since a curator told only *when* is being
    handed a fact they cannot act on.

    Asserted apart from the wall-naming test above because they fail for
    different reasons: that one breaks when the evaluation is wrong, this one
    when a tidying edit shortens the sentence.
    """
    work = ready_work(title="Nighthawks")
    hang(work)

    open_work(ui, work)
    ask(ui, "Archive")

    consequence = ui.page.inner_text(".confirm-consequence")
    assert "next manifest build" in consequence
    assert "Re-hanging" in consequence


def test_a_work_hanging_in_two_rooms_names_both(ui, ready_work, hang):
    """One wall is the degenerate case of many, and the sentence does not switch.

    A confirmation that named the first room it found would be silent about the
    second — the same silence, arrived at by being nearly right.
    """
    work = ready_work(title="Nighthawks")
    first = hang(work)
    second = hang(work, wall_name="Study", theme_name="Small hours")

    open_work(ui, work)
    ask(ui, "Archive")

    consequence = ui.page.inner_text(".confirm-consequence")
    assert first.name in consequence
    assert second.name in consequence


def test_a_work_no_wall_is_showing_gets_no_sentence_about_walls(ui, ready_work, hang):
    """The other branch, and the reason the sentence is worth reading when it appears.

    A room is hanging a theme; this work is not in it. `confirmAct` renders no
    description element for an empty consequence, so the question is the title
    alone — which is the difference between a confirmation that says nothing
    because there is nothing to say and one that says nothing because it never
    looked.
    """
    hanging = ready_work(title="Nighthawks")
    work = ready_work(title="Chop Suey", content_hash="hash-2")
    hang(hanging)

    open_work(ui, work)
    ask(ui, "Archive")

    assert ui.page.inner_text(".confirm-title") == "Archive Chop Suey?"
    assert ui.page.locator(".confirm-consequence").count() == 0


def test_a_work_in_a_hung_theme_that_the_wall_cannot_show_is_not_a_consequence(ui, ready_work, hang):
    """Membership is not hanging, and only the manifest knows the difference.

    This work is in the theme the room is showing and has no rendition, so the
    build puts it in that wall's *exclusions* and never on its wall. Archiving it
    costs the room nothing, and a confirmation that answered from theme
    membership would name a wall that was never showing the picture — teaching
    the curator that these sentences are guesses.
    """
    work = ready_work(title="Nighthawks", rendition=False)
    hang(work)

    open_work(ui, work)
    ask(ui, "Archive")

    assert ui.page.locator(".confirm-consequence").count() == 0


def test_a_room_with_nothing_hanging_is_not_asked_and_does_not_break_the_question(ui, ready_work, hang, services):
    """The manifest route refuses a wall with nothing on it, and correctly.

    There is no theme to evaluate, and a room showing nothing cannot lose a
    picture — so it is skipped rather than asked. Asking it would turn every
    archive in a house with one empty room into a refusal the curator cannot act
    on, with no dialog at all.
    """
    work = ready_work(title="Nighthawks")
    wall = hang(work)
    services.display.add_wall(name="The empty room")

    open_work(ui, work)
    ask(ui, "Archive")

    consequence = ui.page.inner_text(".confirm-consequence")
    assert wall.name in consequence
    assert "The empty room" not in consequence
    assert ui.page.locator("#error:not([hidden])").count() == 0


# -- the act -------------------------------------------------------------------


def test_declining_the_question_leaves_the_work_where_it_was(ui, ready_work, hang, service):
    """The caller owns the act, and a "no" is an answer rather than a delay."""
    work = ready_work(title="Nighthawks")
    hang(work)

    open_work(ui, work)
    ask(ui, "Archive")
    ui.page.click(".confirm-actions button:has-text('Cancel')")
    ui.page.wait_for_selector("dialog.confirm", state="detached")

    assert service.get_artwork(work.id).artwork.status == "accepted"
    assert ui.page.locator("#view button", has_text="Archive").count() == 1


def test_confirming_archives_the_work_and_the_screen_becomes_its_own_undo(ui, ready_work, hang, service):
    """Repainted from the answer the server gave, with the keyboard on the new control.

    The button the curator pressed is replaced by its opposite, so a screen that
    rebuilt itself under a focused control would drop focus to the body and leave
    the next Tab at the top of the page. This is the direct result of a press
    rather than a poll, which is the distinction the focus rule turns on.
    """
    work = ready_work(title="Nighthawks")
    hang(work)

    open_work(ui, work)
    ask(ui, "Archive")
    ui.page.click(".confirm-actions button:has-text('Archive')")
    ui.page.wait_for_selector("#view button:has-text('Restore')")

    assert service.get_artwork(work.id).artwork.status == "archived"
    assert ui.focused() == "Restore"
    assert ui.page.locator(".badge", has_text="archived").count() == 1


def test_restoring_says_which_act_it_is_and_what_the_wall_will_do(ui, ready_work, service):
    """The undo asks too, and its sentence is about *when* the room changes.

    Nothing here republishes a manifest, so a curator who restored a work and
    watched an unchanged wall would reasonably conclude the restore had failed.
    """
    work = ready_work(title="Nighthawks")
    service.archive_artwork(work.id)

    open_work(ui, work)
    ask(ui, "Restore")

    assert ui.page.inner_text(".confirm-title") == "Restore Nighthawks?"
    consequence = ui.page.inner_text(".confirm-consequence")
    assert "next manifest build" in consequence
    assert "Re-hanging" in consequence

    ui.page.click(".confirm-actions button:has-text('Restore')")
    ui.page.wait_for_selector("#view button:has-text('Archive')")

    assert service.get_artwork(work.id).artwork.status == "accepted"


def test_a_refused_archive_is_announced_rather_than_silently_ignored(ui, service):
    """The catalogue's own sentence, in the surface's one failure channel.

    The work is archived out from under the open screen — which is what a second
    tab, or an agent over MCP, does — so the button the curator presses is
    offering an act the service will refuse.
    """
    work = service.add_artwork(title="Chop Suey")
    open_work(ui, work)
    service.archive_artwork(work.id)

    ask(ui, "Archive")
    ui.page.click(".confirm-actions button:has-text('Archive')")
    ui.page.wait_for_selector("#error:not([hidden])")

    assert "already archived" in ui.page.inner_text("#error")


# -- what the work is said to be -----------------------------------------------


def test_only_the_sourced_facet_is_marked_and_the_default_is_a_footnote(ui, service):
    """Inferred is the rule, so the rule is stated once and the exception is marked.

    Nearly every facet in this catalogue was read off the work by a model — the
    wired collection publishes no style field at all — so a badge on each of
    those is a label on almost everything, which is a label nobody reads. The
    mark is a tick rather than a word because an annotation must not outrank the
    value it qualifies, and the word survives for assistive technology so neither
    shape nor colour carries this alone.
    """
    work = service.add_artwork(title="Chop Suey")
    service.record_facet(artwork_id=work.id, kind="movement", value="Precisionism", derivation="sourced")
    service.record_facet(artwork_id=work.id, kind="subject", value="diner", derivation="inferred")

    open_work(ui, work)

    movement = ui.page.locator(".facets dt:has-text('Movement') + dd")
    subject = ui.page.locator(".facets dt:has-text('Subject') + dd")
    assert movement.locator(".sourced").count() == 1
    assert subject.locator(".sourced").count() == 0
    # The word, for the reader who cannot see a tick, and the tick hidden from
    # them so the mark is announced once rather than as "check mark sourced".
    assert "sourced" in movement.text_content()
    assert movement.locator(".tick").get_attribute("aria-hidden") == "true"


def test_the_footnote_sits_below_the_facts_it_qualifies(ui, service):
    """A rule holding for every work must not outrank the facts of this one.

    It sat above them first. A museum label puts its qualifications at the foot
    for the same reason, and the position is the whole of the correction.
    """
    work = service.add_artwork(title="Chop Suey")
    service.record_facet(artwork_id=work.id, kind="era", value="20th c.", derivation="inferred")

    open_work(ui, work)

    panel = ui.page.locator(".panel", has=ui.page.locator("dl.facets"))
    text = panel.inner_text()
    assert "inferred unless it carries ✓" in text
    assert text.index("20th c.") < text.index("inferred unless it carries ✓")


def test_a_work_with_no_facets_gets_no_footnote_about_them(ui, service):
    """A default stated under an empty list is a rule about nothing."""
    work = service.add_artwork(title="Chop Suey")

    open_work(ui, work)

    assert ui.page.locator("dl.facets").count() == 0
    assert "inferred unless" not in ui.text()


# -- the fact stated once ------------------------------------------------------


def test_the_status_is_stated_by_the_badge_and_not_again_as_a_row(ui, service):
    """A screen states a fact once; two copies invite a search for the difference.

    The badge marks the exception and says nothing when a work is in circulation,
    which is the same inversion the derivation footnote uses — and the control
    below the facts already names which direction is available.
    """
    work = service.add_artwork(title="Chop Suey")
    service.archive_artwork(work.id)

    open_work(ui, work)

    assert ui.page.locator(".badge", has_text="archived").count() == 1
    assert ui.page.locator("dl.facts dt", has_text="Status").count() == 0


def test_the_mat_shows_its_colour_and_nothing_else(ui, ready_work):
    """The record keeps the method and the date; the label does not show them.

    That history exists so "the new model picked a worse colour" stays answerable
    and reversible, and so the engine's silent fallback to a darkened dominant
    colour is visible in the data. It is a diagnostic question asked rarely, and
    putting its answer on every work's label is putting the audit trail where the
    label goes. **Nothing about this reduces what is stored.**
    """
    work = ready_work(title="Nighthawks")

    open_work(ui, work)

    swatch = ui.page.locator(".mat .mat-swatch")
    assert swatch.count() == 1
    assert "#27285b" in ui.page.inner_text(".mat")
    assert "vision_model" not in ui.text()
    assert ui.page.locator("table caption", has_text="Superseded").count() == 0
