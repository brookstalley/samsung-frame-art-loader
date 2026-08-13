/* What the client currently believes it is showing.
 *
 * One object, in one module, because three unrelated things read it and a copy
 * per module would be three answers to "which navigation is current": the
 * generation guard in `render.js`, the router, and the run view's poll chain.
 *
 * `painted` is what the polling screen currently on the page last put there —
 * the run view or the conversation — so a poll that finds nothing changed can
 * leave the DOM, and the focus in it, alone. Each writes its own shape, tagged
 * with the thing it was showing (`runId`, `conversationId`), and each compares
 * that tag before trusting the record, so a screen never reads the other's.
 * Cleared on every navigation, because leaving a view and coming back must
 * repaint even when the data is identical: the DOM it describes is gone by then.
 *
 * `params` is the fragment's `?key=value` state — a search query, an active
 * filter set, and the destination a contextual screen was opened from. It is
 * always an object, never null, so every reader can index it without a guard.
 *
 * **`watch` belongs to the run view alone, and it is the exception rather than
 * the precedent.** Everything else here is read by more than one module, which
 * is what earns a field a place in shared state; `watch` holds one screen's
 * poll bookkeeping and is written and read only by `screens/run.js`. It is here
 * because `test_the_run_view.py` reads `state.watch.failures` through the
 * published object, which is the one thing a screen-local variable could not
 * offer. The counter-example is deliberate and one directory along:
 * `screens/collection.js` keeps its `selected` set at module scope and says why
 * — it is not addressable, so nothing else can want it. A new screen's private
 * field goes there, not here, unless a test needs to see it.
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
