/* Building nodes, writing them to the page, and saying when that failed.
 *
 * TEXT IS SET WITH textContent, NEVER innerHTML. Titles, descriptions and
 * provider names come from museum sites this product does not control, and
 * `<img src=x onerror=...>` inside a work's title is the whole of that attack.
 * The one exception would be description markup, which the catalogue reduces to
 * <i>/<b> at ingest — and it is not taken here either, because a UI that starts
 * trusting one field is a UI someone extends to the next one.
 */

import { state } from "./state.js";

export function showError(message) {
  const box = document.getElementById("error");
  box.textContent = message;
  box.hidden = false;
}

export function clearError() {
  const box = document.getElementById("error");
  box.hidden = true;
  box.textContent = "";
}

export function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "text") node.textContent = value;
    else if (key === "class") node.className = value;
    else if (key === "onclick") node.addEventListener("click", value);
    // `true` spells itself differently either side of the ARIA boundary, and
    // getting it wrong is silent. An HTML boolean attribute — `checked`,
    // `disabled`, `hidden` — is true by being present, so the empty string is
    // right. An `aria-*` state takes the literal word: `aria-hidden=""` is not a
    // valid token, so it is treated as unset and the thing stays announced.
    // Every glyph in this client was written `"aria-hidden": true`, so until this
    // line every badge read its shape aloud beside the word it accompanies —
    // "black circle native", "circled division slash archived".
    else node.setAttribute(key, value === true ? (key.startsWith("aria-") ? "true" : "") : String(value));
  }
  for (const child of [].concat(children)) {
    if (child) node.append(child);
  }
  return node;
}

/* Write a view's nodes to the page, unless the curator has moved on.
 *
 * `generation` is `state.nav` as it stood when this paint began, and passing it
 * is not ceremony: every view here awaits at least one request and three page
 * through up to fifty, so a paint routinely completes after the view it belongs
 * to is gone — and `replaceChildren` would put it over whatever replaced it,
 * with the destination highlight and the fragment both naming the other screen.
 * A stale screen that looks live is the class of defect this client has shipped
 * three times.
 *
 * Taken as an argument rather than read from a shared variable, which is what
 * this was first written as. A module-level "currently painting" is overwritten
 * by the LATER navigation, so the abandoned paint reads the generation that
 * superseded it and lands anyway — the guard passes and does nothing. A test
 * caught that; the value has to travel with the paint that captured it.
 *
 * It is also why the argument comes first and is required: a view that forgets
 * it passes a DOM node where a number belongs, and the check below throws
 * instead of silently painting whatever it was handed. */
export function render(generation, ...nodes) {
  if (typeof generation !== "number") {
    throw new TypeError("render() takes the navigation generation first; a view that omits it cannot be superseded.");
  }
  if (generation !== state.nav) return;
  const view = document.getElementById("view");
  // Filtered, not passed straight through: `replaceChildren` coerces a null to
  // the *string* "null" and puts it on the page, so an omitted optional panel
  // renders as the word null rather than as nothing.
  view.replaceChildren(...nodes.filter(Boolean));
}

/* Run something that talks to the server, and say so when it refuses.
 *
 * Failures are announced, not only shown: a curator who learns about a refused
 * operation by noticing a colour is a curator who misses it. */
export async function guard(work) {
  try {
    await work();
    clearError();
  } catch (failure) {
    showError(failure.message);
  }
}
