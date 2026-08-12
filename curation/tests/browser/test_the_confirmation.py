"""The surface's one confirmation question, in a real browser.

**This is the level, not a level.** `core/confirm.js` is a wrapper around the
platform's `<dialog>`, and every behaviour worth pinning about it belongs to the
platform rather than to the wrapper: that `showModal()` traps focus, that Escape
closes and fires `cancel`/`close`, that a click on the backdrop does *not*
dismiss unless somebody opts into it. None of that exists outside a browser, so a
harness that stubbed the element would assert the stub's manners and report green
about a dialog that could not be escaped from.

The behaviours here are the ones a caller is entitled to rely on. Two chunks are
being built against this signature at once, so what these tests hold is a
contract between them and not a description of one screen: the question renders
as it was given, the keyboard starts on the safe answer, dismissal is a "no", a
misdirected click is not an answer at all, and the page does not accumulate a
dialog per question asked.

The module is driven by importing it in the page rather than through a screen,
deliberately — no screen calls it yet, and a test routed through the first caller
to arrive would pin that screen's wording into the shared module's suite.
"""

import pytest

# At import time, not in a fixture. A marker deselection still *collects* this
# module, so the default run — which does not install the browser group — has to
# skip here rather than fail on the missing plugin.
pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

#: The question the product's own rule produces: the act, and the wall it lands
#: on. A confirmation that said only "Hang Winter?" would be unreadable in a
#: house with two rooms, and every act that changes a wall names which.
TITLE = "Hang Winter in the living room?"
CONSEQUENCE = "The living room panel will show Winter's 14 works. The study is unaffected."
CONFIRM_LABEL = "Hang"

#: Start the question and leave its promise running, recording the answer on
#: `window` when it settles.
#:
#: The `await import(...)` is what makes this a test of the shipped module rather
#: than of a copy: the browser fetches the same file the server serves, from the
#: same path `app.js` would import it by. The inner promise is deliberately not
#: awaited — `confirmAct` does not settle until somebody answers, and awaiting it
#: here would hang the evaluation that has to return before the test can press
#: anything.
_ASK = """
async ({ question, slot }) => {
  const { confirmAct } = await import("/static/core/confirm.js");
  window[slot] = "unsettled";
  confirmAct(question).then((answer) => { window[slot] = answer; });
}
"""


def _ask(ui, *, slot="__answer", open_dialogs=1, title=TITLE, consequence=CONSEQUENCE, confirm_label=CONFIRM_LABEL):
    """Open the dialog and wait until the platform has actually made it modal.

    `slot` names where this question's answer lands, so a test may have more than
    one in flight; `open_dialogs` is how many should be showing once it is up,
    which is what makes the wait mean "this one opened" rather than "one of them
    is still there".
    """
    question = {"title": title, "consequence": consequence, "confirmLabel": confirm_label}
    ui.page.evaluate(_ASK, {"question": question, "slot": slot})
    ui.page.wait_for_function(
        "(count) => document.querySelectorAll('dialog.confirm[open]').length === count",
        arg=open_dialogs,
    )


def _answer(ui, slot="__answer"):
    """What the promise resolved to, or the string `unsettled` if it has not."""
    return ui.page.evaluate("(slot) => window[slot]", slot)


def _settles(ui, slot="__answer"):
    ui.page.wait_for_function("(slot) => window[slot] !== 'unsettled'", arg=slot)
    return _answer(ui, slot)


def _labelled_by(ui, attribute, *, nth=0):
    """The text of the element the `nth` dialog's `attribute` points at.

    Resolved through the id rather than read off the element directly, because
    the failure worth catching is an `aria-labelledby` naming an id that is not
    there — which is the same to a screen reader as no label at all, and which
    looks perfectly correct in the markup.

    **Resolved from the document, not from within the dialog**, which is the half
    that makes it able to fail: a screen reader looks an id up over the whole
    page, so two dialogs sharing one would announce the first one's words under
    the second one's question. A lookup scoped to the dialog finds the right
    element every time and would report that as correct.
    """
    return ui.page.evaluate(
        """({ attribute, nth }) => {
             const dialog = document.querySelectorAll("dialog.confirm")[nth];
             const id = dialog.getAttribute(attribute);
             if (!id) return null;
             const target = document.getElementById(id);
             return target ? target.textContent : "no element carries that id";
           }""",
        {"attribute": attribute, "nth": nth},
    )


def test_the_dialog_asks_the_question_it_was_given(ui):
    """The act, its target and what will change — as the caller wrote them.

    The title is the caller's because the wall-naming rule is the caller's: this
    module cannot know which room a theme is being hung in, and a wrapper that
    composed the sentence itself would have to.
    """
    ui.open()
    _ask(ui)

    assert ui.page.inner_text("dialog.confirm .confirm-title") == TITLE
    assert ui.page.inner_text("dialog.confirm .confirm-consequence") == CONSEQUENCE


def test_the_dialog_is_named_and_described_by_its_own_words(ui):
    """A modal a screen reader announces as "dialog" and nothing else is unusable.

    Both attributes are resolved through the ids they name rather than merely
    asserted present, since an id pointing at nothing announces exactly as much
    as an absent attribute and reads as correct.
    """
    ui.open()
    _ask(ui)

    assert _labelled_by(ui, "aria-labelledby") == TITLE
    assert _labelled_by(ui, "aria-describedby") == CONSEQUENCE


def test_a_question_with_no_consequence_renders_no_description_at_all(ui):
    """An empty element is worse than none: it takes space and describes silence.

    A caller may have nothing to add beyond the question — the act is its own
    consequence — and the dialog has to read as deliberate rather than as one
    with a paragraph missing.
    """
    ui.open()
    _ask(ui, consequence="")

    assert ui.page.locator("dialog.confirm .confirm-consequence").count() == 0
    assert ui.page.locator("dialog.confirm[aria-describedby]").count() == 0
    # The question itself is untouched by the absence.
    assert ui.page.inner_text("dialog.confirm .confirm-title") == TITLE


def test_the_keyboard_starts_on_the_answer_that_changes_nothing(ui):
    """Cancel, never the verb.

    A dialog opens under whatever the operator was already doing, and a keypress
    already in flight lands on whatever holds focus. Starting on the affirmative
    button makes a stray Enter into an act; starting on Cancel makes it into a
    dismissal, which is the direction a mistake should go.
    """
    ui.open()
    _ask(ui)

    assert ui.focused() == "Cancel"


def test_escape_is_a_no(ui):
    """The platform's dismissal, resolved as a refusal rather than left hanging.

    A promise that never settles on Escape is the defect this is written against:
    the dialog goes away, the operator believes they declined, and the caller is
    still awaiting an answer it will never get.
    """
    ui.open()
    _ask(ui)

    ui.page.keyboard.press("Escape")

    assert _settles(ui) is False


def test_cancelling_is_a_no(ui):
    ui.open()
    _ask(ui)

    ui.page.click("dialog.confirm .confirm-actions button:has-text('Cancel')")

    assert _settles(ui) is False


def test_confirming_is_a_yes(ui):
    ui.open()
    _ask(ui)

    ui.page.click(f"dialog.confirm .confirm-actions button:has-text('{CONFIRM_LABEL}')")

    assert _settles(ui) is True


def test_a_click_outside_the_dialog_is_not_an_answer(ui):
    """A misdirected click must not decide anything, in either direction.

    Light dismissal is the convention this deliberately does not take: the click
    that lands beside a dialog is usually the one aimed at what the dialog
    covered, and reading it as "no" teaches the operator that clicking away is
    how you decline — a habit that costs them the day the same reflex meets a
    dialog which reads it as "yes".

    The proof is in two parts, and the second is the one that cannot pass by
    accident: the question is still unanswered *and* still live, which is shown
    by going on to answer it.
    """
    ui.open()
    _ask(ui)

    # Top-left of the viewport: the modal is centred, so this lands on the
    # backdrop, which the platform reports as a click on the dialog itself.
    ui.page.mouse.click(5, 5)

    assert _answer(ui) == "unsettled"
    assert ui.page.locator("dialog.confirm[open]").count() == 1

    ui.page.click(f"dialog.confirm .confirm-actions button:has-text('{CONFIRM_LABEL}')")
    assert _settles(ui) is True


def test_the_dialog_leaves_the_page_when_it_has_been_answered(ui):
    """Answered and gone, not answered and hidden.

    A closed `<dialog>` left in the document is invisible and still real: its ids
    are still taken, its buttons are still in the tree, and the accumulation is
    silent because nothing on the page looks different.
    """
    ui.open()
    _ask(ui)

    ui.page.click(f"dialog.confirm .confirm-actions button:has-text('{CONFIRM_LABEL}')")
    assert _settles(ui) is True

    assert ui.page.locator("dialog.confirm").count() == 0


def test_asking_twice_leaves_one_dialog_carrying_the_second_question(ui):
    """The repeat case, which is the ordinary one — this is a session's worth of acts.

    Two assertions, because two different defects hide here. A dialog left behind
    makes the count wrong; ids reused across dialogs make the count right and the
    *label* wrong, with the second question announced under the first one's
    words.
    """
    ui.open()
    _ask(ui)
    ui.page.keyboard.press("Escape")
    assert _settles(ui) is False

    second = "Archive Composition VIII?"
    _ask(ui, title=second, consequence="", confirm_label="Archive")

    assert ui.page.locator("dialog.confirm").count() == 1
    assert _labelled_by(ui, "aria-labelledby") == second


def test_two_questions_asked_at_once_are_each_announced_as_themselves(ui):
    """Nothing stops a second question arriving before the first is answered.

    `confirmAct` is called and left running, so two of them overlapping is a
    state the surface can reach without anybody deciding to support it — a poll
    landing, a second control pressed, two screens sharing this module. The
    platform stacks the dialogs and traps the keyboard in the newer one, which is
    right; what is not free is the labelling. Ids are looked up across the whole
    document, so two dialogs built from one id would announce the older
    question's words above the newer question's buttons, and every id would still
    resolve to a real element.

    The answers stay attached to their own questions too: the keystroke settles
    the dialog it was aimed at and leaves the one beneath it still asking.
    """
    ui.open()
    _ask(ui, slot="__first")

    second = "Archive Composition VIII?"
    _ask(ui, slot="__second", open_dialogs=2, title=second, consequence="", confirm_label="Archive")

    assert _labelled_by(ui, "aria-labelledby", nth=0) == TITLE
    assert _labelled_by(ui, "aria-labelledby", nth=1) == second

    ui.page.keyboard.press("Escape")

    assert _settles(ui, "__second") is False
    assert _answer(ui, "__first") == "unsettled"
    assert ui.page.locator("dialog.confirm[open]").count() == 1
