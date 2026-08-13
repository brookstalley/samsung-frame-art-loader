/* The one question this surface asks before it changes a wall.
 *
 * **The platform's own `<dialog>`, opened with `showModal()`, and that is the
 * whole reason for the choice.** Focus trapping, Escape to dismiss, inertness of
 * everything behind it and `aria-modal` semantics all come from the browser
 * rather than from code this product would have to maintain and keep correct
 * across a keyboard, a screen reader and a phone. A hand-rolled overlay is
 * roughly a hundred lines of exactly that, and every one of them is a line that
 * can silently stop working — a modal whose focus trap has quietly broken looks
 * identical to one whose has not.
 *
 * **Every act names its target, and the caller supplies the name.** "Hang Winter
 * in the living room?" rather than "Hang Winter?" — an installation with one
 * wall today has two next year, and a confirmation that omits the room is one a
 * curator cannot check before pressing the button. This module renders whatever
 * question it is handed; the naming rule binds whoever calls it.
 *
 * **The affirmative button carries the verb, and there is no danger styling.**
 * The acts that use this are ordinary and reversible — hang a theme, archive a
 * work, restore it — so a red button would teach the operator that this dialog
 * means danger, which is exactly the wrong lesson to have learned on the day one
 * of them is not.
 *
 * TEXT IS SET WITH textContent, NEVER innerHTML. The rule and its reasoning are
 * at `render.js`, and a title composed from a museum's own field for a work
 * reaches this dialog as readily as it reaches a card.
 */

import { el } from "./render.js";

/* `close(CONFIRMED)` is how the affirmative answer travels from a click to the
 * one place the promise settles. Escape and a dismissal leave `returnValue`
 * empty, so anything that is not this string is a no — which is the safe
 * direction for a value the platform can set without asking us. */
const CONFIRMED = "confirm";

/* Distinct ids per dialog, because `aria-labelledby` points at one. Two of these
 * only overlap while one is being torn down as the next opens, and a duplicated
 * id there resolves to whichever came first — a dialog labelled with the
 * previous question. */
let asked = 0;

export function confirmAct({ title, consequence, confirmLabel, cancelLabel = "Cancel" }) {
  asked += 1;
  const titleId = `confirm-title-${asked}`;
  const consequenceId = `confirm-consequence-${asked}`;

  // No element at all rather than an empty one: a `<p>` with nothing in it still
  // takes its margin, and an `aria-describedby` pointing at it gives a screen
  // reader a description that is silence.
  const described = Boolean(consequence);
  const description = described ? el("p", { class: "confirm-consequence", id: consequenceId, text: consequence }) : null;

  const cancel = el("button", { class: "action quiet", type: "button", text: cancelLabel });
  const affirm = el("button", { class: "action", type: "button", text: confirmLabel });

  const dialog = el(
    "dialog",
    {
      class: "confirm",
      "aria-labelledby": titleId,
      // `el` drops a null attribute, so an undescribed dialog carries no
      // `aria-describedby` rather than one pointing at nothing.
      "aria-describedby": described ? consequenceId : null,
    },
    [
      el("h2", { class: "confirm-title", id: titleId, text: title }),
      description,
      // Cancel first, so the keyboard's first stop and the reading order agree.
      el("div", { class: "confirm-actions" }, [cancel, affirm]),
    ],
  );

  return new Promise((resolve) => {
    let settled = false;

    /* One place the answer is decided, reached by every route out.
     *
     * `close` fires for a button, for Escape and for anything else that closes a
     * dialog, so routing all three through it is what makes a single settlement
     * a property of the shape rather than of care: a click landing in the same
     * frame as an Escape calls `close()` twice, and the second call on an
     * already-closed dialog is a no-op by the platform's own definition. The
     * flag is what makes that visible here instead of inherited from two
     * specifications a reader has to know — a promise ignores its second
     * `resolve`, but `remove()` and the `returnValue` read would run twice, and
     * a reader would be left working out that it did not matter.
     *
     * Removed from the document once it has settled: this is called repeatedly
     * over a session, and a page accumulating one closed dialog per question is
     * a page whose ids stop being unique and whose next `aria-labelledby` has
     * several candidates. */
    dialog.addEventListener("close", () => {
      if (settled) return;
      settled = true;
      const answer = dialog.returnValue === CONFIRMED;
      dialog.remove();
      resolve(answer);
    });

    // Cancel closes with no return value at all, which is precisely what Escape
    // leaves behind — so declining by button and declining by keystroke are the
    // same path rather than two that have to be kept agreeing.
    cancel.addEventListener("click", () => dialog.close());
    affirm.addEventListener("click", () => dialog.close(CONFIRMED));

    document.body.append(dialog);
    dialog.showModal();

    /* Focus starts on Cancel, not on the verb.
     *
     * A dialog appears under whatever the operator was already doing, and a
     * keypress in flight when it opens lands on whatever holds focus. The safe
     * default is the answer that changes nothing, so a stray Enter closes the
     * question rather than hanging a theme nobody had read the sentence about.
     *
     * **Stated rather than inherited, and a mutation sweep will report this line
     * as undefended.** `showModal()` already focuses the first focusable element
     * it finds, which is Cancel because Cancel is written first — so deleting
     * this call changes nothing today and no test can see it. What it buys is
     * that the guarantee stops depending on the order two buttons happen to sit
     * in: a consequence carrying a link, or an affirmative button moved to the
     * left for some future layout, would silently move the keyboard onto
     * something that is not the safe answer.
     *
     * Nothing here dismisses on a backdrop click, and that is the platform's
     * default rather than something suppressed: a click that misses the dialog
     * is not an answer to the question, and treating it as "no" trains the
     * operator that clicking away is how you decline. */
    cancel.focus();
  });
}
