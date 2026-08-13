/* Reading and writing the address bar — the only client module with no DOM in it.
 *
 * Held apart from `router.js` deliberately. Everything else about navigation
 * touches `window`, `document` or the route table's render functions, and none
 * of that can be exercised without a browser; the *parsing* is a pure function
 * over two strings, and it is the part that grew a grammar in this chunk. So it
 * lives where `node` can import it and a unit test can drive it directly —
 * `curation/tests/unit/test_route_parsing.py` does exactly that.
 *
 * The grammar, which is the whole of this file's contract:
 *
 *     #<view>[/<id>][?<key>=<value>&…]
 *
 * `information-architecture.md` § Navigation Structure requires that "every
 * screen and every consequential state (a search query, an active filter set, a
 * run, a conversation) is addressable". The query half is what this chunk added:
 * before it the fragment could carry a view and an id and nothing else, so a
 * search and a filter set had nowhere to live and a contextual screen had no way
 * to record which destination it was opened from.
 */

/* The fragments the surface answered to before the three destinations existed.
 *
 * Kept rather than dropped, and the reason is not nostalgia: `pages.py` has been
 * serving `/works`, `/discovery`, `/themes` and `/manifest` as real paths since
 * the client was built, the IA promises an agent can link to a screen, and a
 * bookmark that 404s teaches a curator the collection moved. Each maps onto the
 * screen that took over its job, so an old address arrives at the new screen
 * rather than at the default one.
 *
 * They are aliases, never destinations: `formatRoute` never writes one, so
 * following an old link rewrites the address bar to the new spelling. */
export const FRAGMENT_ALIASES = {
  works: "collection",
  manifest: "walls",
  discovery: "discover",
  themes: "theme",
};

export function resolveAlias(head) {
  return FRAGMENT_ALIASES[head] || head;
}

/* Decode one `%`-escaped piece, or hand back what was there.
 *
 * `decodeURIComponent` throws `URIError` on a malformed escape, and a hand-typed
 * or hand-truncated URL is exactly where one comes from. Throwing here would
 * take the whole client down on boot — `readHash` runs before anything is
 * painted — so a piece that will not decode is used verbatim, which is wrong in
 * a way the curator can see rather than fatal in a way they cannot.
 *
 * Only `URIError` is swallowed. Anything else is a fault in this file and is
 * allowed to surface. */
function decode(piece) {
  try {
    return decodeURIComponent(piece);
  } catch (failure) {
    if (!(failure instanceof URIError)) throw failure;
    return piece;
  }
}

/* The `?key=value` tail, as a plain object.
 *
 * `URLSearchParams` would do this, and is not used for one reason: it decodes
 * `+` as a space. That is correct for a form-encoded *query string* and wrong
 * for a fragment, where `+` is an ordinary character — so a bookmarked search
 * for "Rothko + Newman" would come back as two spaces and quietly find nothing.
 * Everything this file writes is `encodeURIComponent`'d, which spells a space
 * `%20`, so the pair round-trips.
 *
 * A key with no `=` is kept with an empty value rather than dropped: `?matted`
 * is a filter someone will write by hand, and silently discarding it is the
 * failure mode this whole surface refuses. */
function parseParams(query) {
  const params = {};
  if (!query) return params;
  for (const pair of query.split("&")) {
    if (!pair) continue;
    const equals = pair.indexOf("=");
    const key = decode(equals === -1 ? pair : pair.slice(0, equals));
    if (!key) continue;
    params[key] = equals === -1 ? "" : decode(pair.slice(equals + 1));
  }
  return params;
}

/* Where an address points, given what the surface knows how to render.
 *
 * `routes` is the router table — `{ <view>: { detail: bool, … } }` — passed in
 * rather than imported, which is what keeps this file free of everything else.
 *
 * The fallbacks are in the order a reader would guess, and each is there for a
 * defect that happened:
 *
 *   1. the fragment, if it names a screen this surface has;
 *   2. otherwise the path, so the deep links `pages.py` serves open the screen
 *      they name — without this every one of them fell through to the default
 *      view, which is worse than a 404 because it looks like it worked;
 *   3. otherwise `fallback`, the product's home.
 *
 * An id is taken only for a route that says it takes one, and a route that takes
 * one is not entered without it: `#work` with no id would otherwise render the
 * work detail for `null`. */
export function parseRoute(fragment, routes, { path = "", fallback = "walls" } = {}) {
  const raw = String(fragment || "").replace(/^#/, "");
  const mark = raw.indexOf("?");
  const locator = mark === -1 ? raw : raw.slice(0, mark);
  const params = parseParams(mark === -1 ? "" : raw.slice(mark + 1));

  const slash = locator.indexOf("/");
  const head = resolveAlias(slash === -1 ? locator : locator.slice(0, slash));
  const tail = slash === -1 ? null : decode(locator.slice(slash + 1));
  const entry = routes[head];

  if (entry && entry.detail && tail !== null && tail !== "") return { view: head, id: tail, params };
  if (entry && !entry.detail) return { view: head, id: null, params };

  const typed = resolveAlias(String(path || "").replace(/^\//, ""));
  if (routes[typed] && !routes[typed].detail) return { view: typed, id: null, params };
  return { view: fallback, id: null, params };
}

/* The address for a screen and its state — the only place a fragment is written.
 *
 * Keys are sorted, which is not cosmetic. `go` compares the fragment it composed
 * against the one in the address bar to decide whether navigating is a
 * `hashchange` or a repaint, so two spellings of the same state would make an
 * identical navigation look like a new one and repaint the screen underneath a
 * curator mid-scroll.
 *
 * An empty, null or undefined value is omitted rather than written as `key=`.
 * A cleared search field is the state "no search", and `?q=` is a search for
 * nothing — the grid would answer them differently and only one of them is what
 * the curator did. */
export function formatRoute(view, id = null, params = {}) {
  let address = `#${view}`;
  if (id !== null && id !== undefined && id !== "") address += `/${encodeURIComponent(id)}`;
  const keys = Object.keys(params || {})
    .filter((key) => params[key] !== null && params[key] !== undefined && params[key] !== "")
    .sort();
  if (keys.length) {
    address += `?${keys.map((key) => `${encodeURIComponent(key)}=${encodeURIComponent(params[key])}`).join("&")}`;
  }
  return address;
}
