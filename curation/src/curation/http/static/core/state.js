/* What the client currently believes it is showing.
 *
 * One object, in one module, because three unrelated things read it and a copy
 * per module would be three answers to "which navigation is current": the
 * generation guard in `render.js`, the router, and the run view's poll chain.
 *
 * `painted` is what the run view last put on the page, so a poll that finds
 * nothing changed can leave the DOM — and the focus in it — alone. Cleared on
 * every navigation, because leaving a view and coming back must repaint even
 * when the data is identical: the DOM it describes is gone by then.
 *
 * `params` is the fragment's `?key=value` state — a search query, an active
 * filter set, and the destination a contextual screen was opened from. It is
 * always an object, never null, so every reader can index it without a guard.
 */
export const state = {
  view: "walls",
  detailId: null,
  params: {},
  nav: 0,
  poll: 0,
  painted: null,
  watch: null,
};
