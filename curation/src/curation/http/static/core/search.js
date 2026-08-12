/* The persistent search affordance.
 *
 * `information-architecture.md` § Navigation Structure requires search to be in
 * the masthead rather than inside a screen, and gives the reason: at thousands of
 * works it is the primary retrieval mechanism, "and a retrieval mechanism you
 * must first navigate to is one more step on the most frequent action".
 *
 * Searching is a **navigation**, not a mode. It writes `?q=` into the fragment
 * and goes to Collection, which means a search is bookmarkable, sendable, and —
 * because it lands in the history like every other navigation — undone by the
 * browser's own back button rather than by a Clear control the curator has to
 * find.
 */

import { el } from "./render.js";
import { go } from "./router.js";
import { state } from "./state.js";

/* The field shows the search that is currently in the address bar.
 *
 * Skipped while the field has focus. A curator mid-word is the one person whose
 * text must not be replaced by the state a repaint thinks is current, and a
 * repaint happens on every navigation — including the one the typing is about to
 * cause. */
export function paintSearch() {
  const field = document.getElementById("search");
  const current = state.params.q || "";
  if (document.activeElement !== field && field.value !== current) field.value = current;
}

export function installSearch() {
  const form = document.getElementById("search-form");
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const query = document.getElementById("search").value.trim();
    // Filters already in the address survive a search made from Collection, and
    // do not follow one made from anywhere else: narrowing what you are looking
    // at is a different act from starting a search over the whole collection,
    // and carrying a rail's state onto the second would silently hide most of
    // the answers.
    const params = state.view === "collection" ? { ...state.params, q: query } : { q: query };
    go("collection", null, params);
  });
}

/* The way out of a search, offered where the emptiness is. Written here beside
 * the affordance it undoes rather than in the screen, so the two cannot come to
 * disagree about what clearing a search means. */
export function clearSearchLink(text = "Clear the search") {
  return el("button", {
    class: "action quiet",
    type: "button",
    text,
    onclick: () => go("collection", null, { ...state.params, q: "" }),
  });
}
