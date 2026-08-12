/* Collection — everything acquired, in one place.
 *
 * One of the three destinations. The grid, the rails and the three empty states
 * `information-architecture.md` specifies are a later chunk's; what moved here in
 * the navigation reshape is the works grid exactly as it was, plus the half of
 * the masthead search that has to land somewhere.
 */

import { fetchAllWorks } from "../core/api.js";
import { absentImage, fitBadge, shortfallNote, sourceBadge, statusBadge } from "../core/badges.js";
import { el, render } from "../core/render.js";
import { go } from "../core/router.js";
import { clearSearchLink } from "../core/search.js";
import { state } from "../core/state.js";

function cardImage(work) {
  if (!work.image.available) {
    return el("div", { class: "card-image" }, [absentImage(work.image.note)]);
  }
  const image = el("img", {
    src: `/api/works/${encodeURIComponent(work.artwork_id)}/thumbnail`,
    // Empty on purpose. The button around it is already named "Open <title>",
    // and the card's own text carries artist, date and medium — describing the
    // picture here as well would make every card announce its title twice.
    alt: "",
    loading: "lazy",
  });
  // Availability was true when the listing was built, and a file can go away
  // between then and the fetch. Without this the tile renders as a blank box —
  // silent, which is the failure mode this whole product exists to refuse.
  image.addEventListener("error", () => {
    image.replaceWith(absentImage("Its image could not be loaded just now."));
  });
  return el(
    "button",
    {
      class: "card-image",
      type: "button",
      "aria-label": `Open ${work.title}`,
      onclick: () => go("work", work.artwork_id),
    },
    [image],
  );
}

function workCard(work) {
  return el("li", { class: "card" }, [
    cardImage(work),
    el("div", { class: "card-body" }, [
      el("h3", { class: "card-title" }, [
        el("button", { type: "button", text: work.title, onclick: () => go("work", work.artwork_id) }),
      ]),
      el("p", { class: "card-artist", text: work.artist ? work.artist.name : "Artist unrecorded" }),
      el("p", {
        class: "card-meta",
        text: [work.date_created, work.medium].filter(Boolean).join(" · ") || " ",
      }),
      el("div", { class: "card-footer" }, [statusBadge(work), fitBadge(work), sourceBadge(work)]),
    ]),
  ]);
}

export async function viewCollection(generation) {
  const query = (state.params.q || "").trim();
  // The search goes to the server, which is what makes the count in the heading
  // below a statement about the catalogue rather than about this screen's first
  // page. It filtered client-side for exactly as long as it had to: the comment
  // here said the retrieval layer was `GET /api/works`'s to grow and that a dead
  // control was worse than a partial one, which was true when it was written and
  // stopped being true when `q` landed in the same wave.
  const page = await fetchAllWorks(query);
  if (!query) {
    const heading = el("h2", {
      text: page.works.length === page.total ? `${page.total} works` : `${page.works.length} of ${page.total} works`,
    });
    render(generation, heading, shortfallNote(page), el("ul", { class: "grid" }, page.works.map(workCard)));
    return;
  }

  const found = page.works;
  render(
    generation,
    // `page.total` is the server's count over the whole catalogue, so this says
    // how many works match rather than how many of the ones already loaded do.
    el("h2", {
      text: found.length === page.total ? `${page.total} works matching “${query}”` : `${found.length} of ${page.total} works matching “${query}”`,
    }),
    shortfallNote(page),
    // Named rather than rendered as an empty grid. "Nothing matched" and "the
    // collection is empty" are different facts and lead to different next moves,
    // and only one of them has a way out worth offering.
    found.length
      ? el("ul", { class: "grid" }, found.map(workCard))
      : el("div", { class: "stack" }, [
          el("p", { class: "muted", text: `Nothing held matches “${query}”.` }),
          el("div", { class: "row" }, [clearSearchLink("Show everything")]),
        ]),
  );
}
