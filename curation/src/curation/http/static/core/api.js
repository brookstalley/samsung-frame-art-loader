/* The fetch plumbing: one request helper and the two loops that page to the end.
 *
 * Everything that talks to `/api/*` goes through here, which is what keeps the
 * refusal-versus-fault distinction below written once rather than per screen.
 */

export async function api(path, options) {
  const response = await fetch(path, {
    headers: { "content-type": "application/json" },
    ...options,
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    // The service layer writes its refusals to be shown; anything else is a
    // fault, and saying which is which beats one apologetic sentence for both.
    const message =
      body && body.error
        ? body.error
        : `The server answered ${response.status} for ${path}.`;
    throw new Error(message);
  }
  return body;
}

/* Both the grid and the theme picker page through to the end rather than showing
 * the first page. The picker is the one that made this necessary: a truncated
 * grid is a visible short list, but a truncated picker means a curator simply
 * cannot put work 101 in a theme, and is told nothing about why.
 *
 * **THE JUSTIFICATION FOR THIS HAS BEEN RETIRED, AND THE BEHAVIOUR HAS NOT.**
 * This paragraph used to open "the design target is hundreds of works, so…".
 * `nonfunctional-requirements.md` moved that target to **thousands** on
 * 2026-08-10, and its own amendment calls fetching the whole catalogue
 * "indefensible at 4,000". So what is written below is a description of what this
 * file does, no longer an argument that it is right: the grid owes server-side
 * search, paging and virtualisation, which `information-architecture.md`
 * specifies and no chunk has built. The picker's reason above is unaffected and
 * still binds — whatever replaces this must still leave every work reachable.
 *
 * **No `limit` is sent**, which is the same rule `fetchAllCandidates` states
 * below and for the same reason. This asked for `limit=100` — a copy of the
 * service's `MAX_LIST_LIMIT` — until 2026-08-05, and that copy was a live break
 * waiting on an unrelated edit: `list_artworks` *refuses* a limit above its cap,
 * the refusal arrives as a 400, and `api()` throws. So the day anyone lowered
 * the catalogue's cap, the Collection grid — the default landing view at the
 * time — and the theme picker would have failed outright while the review grid,
 * which asks for nothing, kept paging.
 *
 * The cost is paid knowingly: the server's default page is smaller than its cap,
 * so this makes more round trips than asking for the maximum would. They are
 * against a loopback server on the same box. `PAGE_CEILING` no longer admits
 * "far more works than the design target" — at the amended target it is the
 * thing that will bite first, and `shortfallNote` is what keeps that visible
 * rather than silent until the paging work lands.
 *
 * `PAGE_CEILING` is a runaway guard, not a policy. If it is ever hit the caller
 * reports how many were left out, because a cap nobody mentions is the silent
 * omission this product exists to refuse. */
export const PAGE_CEILING = 50;

/* The chosen facet values, as `GET /api/works` spells them.
 *
 * **One repeated parameter per kind, never comma-joined.** That is the route's
 * own rule and its reason is the data: a facet value may itself contain a comma,
 * and a separator a value can hold is a parser that goes wrong on the catalogue
 * rather than on the request. A kind with nothing chosen contributes nothing, so
 * an unfiltered grid sends the request it always sent. */
function facetQuery(chosen) {
  let query = "";
  for (const kind of Object.keys(chosen || {})) {
    for (const value of chosen[kind] || []) {
      query += `&${encodeURIComponent(kind)}=${encodeURIComponent(value)}`;
    }
  }
  return query;
}

export async function fetchAllWorks(query = "", chosen = null) {
  const works = [];
  let total = 0;
  let truncated = false;
  // The facet groups come from the first page only. Every page recomputes them
  // identically — `list_artworks` answers the works and their counts in one read
  // scope precisely so the two cannot disagree — so keeping a later page's copy
  // would be the same numbers arrived at more slowly.
  let facets = [];
  // Sent to the server rather than filtered here. `GET /api/works` takes `q` and
  // searches the work's own text and its artist's name word-wise, over the whole
  // catalogue — where a client-side filter can only ever search what this screen
  // happened to load, and reports its count as though it had searched
  // everything. The facets are sent for the same reason, and for one more: the
  // counts beside the grid are computed by the service against exactly this
  // filter, and a client that narrowed locally would print them beside a
  // different set of works.
  const search = query ? `&q=${encodeURIComponent(query)}` : "";
  const narrowing = facetQuery(chosen);
  for (let page = 0; page < PAGE_CEILING; page += 1) {
    const body = await api(`/api/works?offset=${works.length}${search}${narrowing}`);
    total = body.total;
    if (page === 0) facets = body.facets || [];
    works.push(...body.works);
    // The stopping condition is what actually arrived, not what the server says
    // is left. A page that reports more while carrying nothing makes no
    // progress — the offset is derived from what came back, so asking again
    // sends the identical request. `PAGE_CEILING` would stop it either way, so
    // what this saves is forty-nine pointless round trips rather than a hang.
    if (!body.truncated || body.works.length === 0) return { works, total, truncated, facets };
    truncated = true;
  }
  return { works, total, truncated: works.length < total, facets };
}

/* Every work a run holds, paged through to the end.
 *
 * No `limit` is sent, so the server's own default and cap govern and the client
 * holds no copy of either. Asking for the cap explicitly would put the number in
 * two places, and the day the service lowered it the grid would ask for more
 * than it allows and be refused outright. */
export async function fetchAllCandidates(runId) {
  const works = [];
  let run = null;
  let total = 0;
  for (let page = 0; page < PAGE_CEILING; page += 1) {
    const body = await api(`/api/runs/${encodeURIComponent(runId)}/candidates?offset=${works.length}`);
    run = body.run;
    total = body.total;
    works.push(...body.works);
    // Same stopping condition as `fetchAllWorks`, and the same reason: a page
    // reporting more while carrying nothing makes no progress, so asking again
    // sends the identical request. The ceiling bounds it regardless; this is
    // what keeps a misbehaving page from costing fifty round trips.
    if (!body.truncated || body.works.length === 0) break;
  }
  return { run, works, total };
}
