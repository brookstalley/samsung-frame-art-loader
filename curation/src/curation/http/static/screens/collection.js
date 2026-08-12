/* Collection — everything acquired, in one place, with the organising beside it.
 *
 * One of the three destinations, and the one that has to survive thousands of
 * works. `information-architecture.md` § Information Hierarchy is what this
 * implements: the grid of images is the primary content, the counts and the
 * active filters are secondary, and the rails that narrow it sit beside the works
 * rather than in another tab — a theme stopped being a destination when the
 * navigation was reshaped, and this is where it went.
 *
 * Four things here are decisions rather than layout, and each is written down at
 * the place it takes effect:
 *
 *   - **Density is a control, not a decision.** Contact sheet and catalogue, with
 *     the default chosen from how much there is and the choice held in the
 *     address so a reload and a shared link both land on it.
 *   - **A control never offers a dead end.** Every facet option carries the count
 *     it would select, and an option that would select nothing is disabled rather
 *     than removed — a vocabulary that shrinks as filters are applied reads as
 *     data loss.
 *   - **Three empty states, not one.** Nothing held, nothing matching a filter,
 *     and nothing by one named artist are three different facts leading to three
 *     different next moves.
 *   - **Organising happens against the works being organised.** The theme rail
 *     filters the grid; membership is edited from the grid, in place, without
 *     leaving the screen.
 *
 * What is deliberately NOT here: archiving a work (it is an act against one work,
 * whose confirmation has to name which walls lose the picture, and it lives on the
 * Work screen this grid links to) and reordering a theme (which is about the theme
 * rather than about the works, and lives on the Theme screen).
 */

import { api, fetchAllWorks } from "../core/api.js";
import { absentImage, fitBadge, shortfallNote, sourceBadge, statusBadge } from "../core/badges.js";
import { el, guard, render } from "../core/render.js";
import { go } from "../core/router.js";
import { clearSearchLink } from "../core/search.js";
import { state } from "../core/state.js";

/* The typed vocabulary, in vocabulary order, and the words the rail puts on it.
 *
 * The same six `VocabularyKind` carries on the server, and the order is the
 * enum's: the response returns all six every time, so the rail renders what it is
 * given rather than deciding what exists. */
const FACET_KINDS = ["artist", "movement", "era", "subject", "medium", "palette"];

const FACET_LABELS = {
  artist: "Artist",
  movement: "Movement",
  era: "Era",
  subject: "Subject",
  medium: "Medium",
  palette: "Palette",
};

const CONTACT = "contact";
const CATALOGUE = "catalogue";

/* Above this many works the grid opens as a contact sheet.
 *
 * [ASSUMPTION] "A few hundred" is what `information-architecture.md` says and it
 * is explicitly a guess there, to be set from a real thousands-scale corpus. It
 * is one constant with the guess recorded at its site rather than a threshold
 * spread through the grid, so replacing it with a measurement is one edit.
 *
 * The reason for the rule is not the number: per-tile chrome that reads as
 * informative at 41 works reads as noise at 4,000 and competes with the art. */
const CATALOGUE_CEILING = 300;

/* Several values within one facet kind travel in the fragment separated by this.
 *
 * **On the wire there is no separator at all** — `GET /api/works` takes one
 * repeated parameter per kind (`?movement=Baroque&movement=Rococo`) precisely
 * because a facet value may contain a comma, and a separator a value can hold is
 * a parser that goes wrong on the data rather than on the request. The fragment
 * has no repeated keys to use: `state.params` is a flat string map. A pipe is
 * chosen over a comma for the same reason the wire refuses one, and it is a
 * fragment-level spelling only — nothing downstream of `facetsFor` sees it. */
const FACET_SEPARATOR = "|";

/* How many skeleton tiles stand in for the grid while it loads. About a
 * screenful at the contact sheet's tile size: fewer leaves the page looking
 * finished and short, more paints a screen of grey the curator scrolls. */
const SKELETON_TILES = 12;

/* Which works the curator has ticked, and the navigation that was current when
 * they did.
 *
 * Module-level rather than in `state`, because it is not addressable: a selection
 * is a thing being done, not a place. It is cleared when the generation changes,
 * which is exactly a navigation — the works on screen have changed, so a
 * selection over the old ones would silently act on works nobody can see. A
 * repaint within one navigation keeps it. */
const selected = new Set();
let selectionGeneration = -1;

/* -- reading the address ---------------------------------------------------- */

function facetsFor(params) {
  const chosen = {};
  for (const kind of FACET_KINDS) {
    const raw = params[kind];
    chosen[kind] = raw ? raw.split(FACET_SEPARATOR).filter(Boolean) : [];
  }
  return chosen;
}

function anyFacetChosen(chosen) {
  return FACET_KINDS.some((kind) => chosen[kind].length);
}

/* The address that results from turning one facet value on or off.
 *
 * Choosing a facet leaves a theme behind, for the reason stated at
 * `themeIsShowing`: the two narrowings cannot be composed by the server, so
 * offering them together would mean one of them silently doing nothing. */
function withFacet(chosen, kind, value) {
  const values = chosen[kind].includes(value)
    ? chosen[kind].filter((held) => held !== value)
    : [...chosen[kind], value];
  return { ...state.params, theme: "", [kind]: values.join(FACET_SEPARATOR) };
}

/* Whether the theme rail's filter is the one actually in force.
 *
 * **A theme and a facet/text filter cannot both apply**, and that is a fact about
 * the API rather than a preference: a theme's works come from
 * `GET /api/themes/{id}` and a filtered catalogue from `GET /api/works`, and
 * neither route can express the other's narrowing. Intersecting them here would
 * be worse than not offering it — every facet count beside the grid would then be
 * a number about the whole catalogue printed next to a grid holding a theme's
 * slice of it, which is exactly the promise-you-cannot-keep the facet rules
 * exist to forbid.
 *
 * So one wins, the search wins, and the screen says so where the theme rail is.
 * The rail's own chips clear everything else, so choosing a theme always works;
 * this branch is for an address that arrived carrying both. */
function themeIsShowing(query, chosen) {
  return Boolean(state.params.theme) && !query && !anyFacetChosen(chosen);
}

/* Which density to draw, given how much there is.
 *
 * The address wins when it names one, which is what "remembered and part of the
 * addressable state" buys: a reload and a link both land where the curator left
 * off, and back undoes a density change like any other navigation. `localStorage`
 * would remember it too and would not be addressable, which is the half that
 * matters — every other consequential state on this surface is in the fragment. */
function resolveDensity(total) {
  const named = state.params.density;
  if (named === CONTACT || named === CATALOGUE) return named;
  return total > CATALOGUE_CEILING ? CONTACT : CATALOGUE;
}

/* -- the tiles -------------------------------------------------------------- */

function cardImage(work) {
  if (!work.image.available) {
    return el("div", { class: "card-image" }, [absentImage(work.image.note)]);
  }
  const image = el("img", {
    src: `/api/works/${encodeURIComponent(work.artwork_id)}/thumbnail`,
    // Empty on purpose. The button around it is already named "Open <title>",
    // and the tile's own text carries artist, date and medium — describing the
    // picture here as well would make every tile announce its title twice.
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

/* The tick that puts a work in a selection.
 *
 * Always drawn, at both densities, rather than revealed on hover with the rest of
 * the contact sheet's metadata. A control that only exists once you are pointing
 * at it is a control a keyboard cannot find and a curator does not know is there,
 * and hidden controls are the accessibility failure this surface keeps a rule
 * about. The caption may hide; the control may not. */
function selectBox(work, onChange) {
  const box = el("input", {
    type: "checkbox",
    class: "tile-select",
    checked: selected.has(work.artwork_id),
    "aria-label": `Select ${work.title}`,
  });
  box.addEventListener("change", () => {
    if (box.checked) selected.add(work.artwork_id);
    else selected.delete(work.artwork_id);
    onChange();
  });
  return box;
}

/* The catalogue tile: the built card, unchanged in shape. */
function workCard(work, onChange) {
  return el("li", { class: "card", "data-artwork": work.artwork_id }, [
    selectBox(work, onChange),
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

/* The contact-sheet tile: the picture, and the words behind hover and focus.
 *
 * **On focus as well as on hover**, which the CSS does with `:focus-within` — a
 * keyboard has no hover, so metadata that appeared only under a pointer would not
 * exist for half the people using this.
 *
 * The archived badge is the one thing that does NOT hide with the caption. A
 * badge is not metadata about the work, it is a mark on an exception: a work out
 * of circulation that looks identical to one on the wall until you point at it is
 * the silence `statusBadge` was written to end. */
function contactTile(work, onChange) {
  const status = statusBadge(work);
  return el("li", { class: "tile", "data-artwork": work.artwork_id }, [
    selectBox(work, onChange),
    status ? el("div", { class: "tile-status" }, [status]) : null,
    cardImage(work),
    el("div", { class: "tile-caption" }, [
      el("span", { class: "tile-title", text: work.title }),
      el("span", { class: "tile-artist", text: work.artist ? work.artist.name : "Artist unrecorded" }),
    ]),
  ]);
}

/* -- the loading state ------------------------------------------------------ */

/* Tiles at the geometry the real ones will have, so nothing moves when they
 * arrive. The skeleton reads the density from the address alone: the computed
 * default needs the total, which is what has not arrived yet. That costs nothing
 * where it would be visible — a skeleton is on screen for as long as the paging
 * loop runs, which is many round trips at the scale whose default is the contact
 * sheet, and a single round trip at the scale whose default is not. */
function skeletonGrid(density) {
  const tiles = [];
  for (let index = 0; index < SKELETON_TILES; index += 1) {
    tiles.push(
      el("li", { class: density === CONTACT ? "tile skeleton" : "card skeleton" }, [
        el("div", { class: "card-image" }),
        density === CONTACT ? null : el("div", { class: "card-body" }, [el("p", { class: "skeleton-line" })]),
      ]),
    );
  }
  return el("ul", {
    // Not `.grid`, though it lays out identically: a loading placeholder that
    // answers the selector the real grid answers is one every test and every
    // reader has to tell apart by its contents.
    class: density === CONTACT ? "grid-skeleton contact-sheet" : "grid-skeleton",
    "aria-hidden": true,
  }, tiles);
}

/* -- the rails -------------------------------------------------------------- */

function facetRail(groups, chosen) {
  const rails = [];
  for (const kind of FACET_KINDS) {
    const group = groups.find((candidate) => candidate.kind === kind);
    // A kind with no values anywhere in the catalogue has no vocabulary to
    // offer. That is not the disabled-not-hidden rule, which is about an option
    // whose count has fallen to nothing under the current filter — this kind has
    // never had one, and six empty controls would be six dead ends.
    if (!group || !group.options.length) continue;
    rails.push(
      el("div", { class: "rail" }, [
        el("h3", { text: FACET_LABELS[kind] || kind }),
        el(
          "ul",
          { class: "rail-options" },
          group.options.map((option) => el("li", {}, [facetOption(kind, option, chosen)])),
        ),
        // How much the cap left out, rather than a list that ends and implies the
        // vocabulary does too.
        group.truncated
          ? el("p", {
              class: "rail-note",
              text: `Showing ${group.options.length} of ${group.total_values}. Search for a value the list does not reach.`,
            })
          : null,
      ]),
    );
  }
  return rails;
}

function facetOption(kind, option, chosen) {
  // The count is inside the control's own text, not beside it. A disabled control
  // is skipped by the tab sequence, so a count living in adjacent text is a count
  // a screen-reader user never hears — and the count is the whole difference
  // between a filter and a guess.
  return el("button", {
    class: "facet-option",
    type: "button",
    "aria-pressed": option.selected ? "true" : "false",
    // Disabled, never hidden: a vocabulary that shrank as filters were applied
    // would read as the collection having lost values rather than as an empty
    // intersection.
    disabled: option.disabled,
    text: `${option.value} (${option.count})`,
    onclick: () => go("collection", null, withFacet(chosen, kind, option.value)),
  });
}

function themeRail(themes, showingTheme) {
  const activeId = showingTheme ? state.params.theme : "";
  const chips = themes.map((placement) =>
    el("button", {
      class: "theme-chip",
      type: "button",
      "aria-pressed": placement.theme.theme_id === activeId ? "true" : "false",
      text: placement.theme.name,
      onclick: () =>
        go(
          "collection",
          null,
          // Everything else goes: a theme is not composable with a search or a
          // facet, and a chip that appeared to do nothing because a search was
          // still in the address would be the worst of both.
          placement.theme.theme_id === activeId
            ? { density: state.params.density }
            : { density: state.params.density, theme: placement.theme.theme_id },
        ),
    }),
  );
  return el("div", { class: "rail" }, [
    el("h3", { text: "Themes" }),
    themes.length
      ? el("div", { class: "theme-chips" }, chips)
      : el("p", { class: "rail-note", text: "No themes yet." }),
    el("p", {}, [
      el("button", {
        class: "action quiet",
        type: "button",
        text: themes.length ? "Manage themes" : "Create a theme",
        onclick: () => go("theme"),
      }),
    ]),
  ]);
}

/* -- the toolbar: density, and editing membership in place ------------------- */

function densityControl(density) {
  const button = (value, label) =>
    el("button", {
      class: "density-option",
      type: "button",
      "aria-pressed": density === value ? "true" : "false",
      text: label,
      onclick: () => go("collection", null, { ...state.params, density: value }),
    });
  return el("div", { class: "density", role: "group", "aria-label": "Grid density" }, [
    button(CONTACT, "Contact sheet"),
    button(CATALOGUE, "Catalogue"),
  ]);
}

/* Adding and removing membership from the grid, with the selection multi-select.
 *
 * **Nothing here repaints the screen**, and that is the rule rather than an
 * optimisation: a curator standing on "Add to theme" who is handed a new page has
 * lost their place and their focus, and a poll or an update that moves focus is a
 * defect this surface has already shipped once. The outcome is announced in a
 * live region and the tiles that left are taken out one at a time.
 *
 * There is no bulk route. `POST /api/themes/{id}/works` takes one work, so a
 * selection of six is six calls, in order, and the first refusal stops the rest
 * and is shown — a half-applied edit reported as success is not something this
 * product does. */
function membershipControls(themes, showingTheme, grid, heading, recount) {
  // Focusable, and focused when an edit completes. Finishing the edit disables
  // the button the curator is standing on, and a browser blurs a control it
  // disables — which drops the keyboard to the top of the document, several
  // hundred tiles above where the work was happening. The outcome sentence is
  // where focus belongs: it is what just happened, and Tab continues from the
  // toolbar into the grid.
  const announcement = el("p", { class: "muted selection-status", "aria-live": "polite", tabindex: "-1" });
  const picker = el("select", { id: "add-to-theme", "aria-label": "Theme to add the selected works to" });
  for (const placement of themes) {
    picker.append(el("option", { value: placement.theme.theme_id, text: placement.theme.name }));
  }

  const add = el("button", { class: "action", type: "button", text: "Add to theme" });
  const remove = showingTheme
    ? el("button", { class: "action quiet", type: "button", text: "Remove from this theme" })
    : null;

  const say = (words) => {
    // Not rewritten unchanged: a live region reassigned the same sentence
    // announces it again, which trains a listener to tune the region out.
    if (announcement.textContent !== words) announcement.textContent = words;
  };

  const settle = () => {
    add.disabled = selected.size === 0;
    if (remove) remove.disabled = selected.size === 0;
    say(selected.size === 0 ? "No works selected." : `${selected.size} selected.`);
  };

  add.addEventListener("click", () =>
    guard(async () => {
      const themeId = picker.value;
      const name = picker.options[picker.selectedIndex].text;
      const count = selected.size;
      for (const artworkId of [...selected]) {
        await api(`/api/themes/${encodeURIComponent(themeId)}/works`, {
          method: "POST",
          body: JSON.stringify({ artwork_id: artworkId }),
        });
      }
      clearSelection(grid);
      settle();
      say(`Added ${count} ${count === 1 ? "work" : "works"} to ${name}.`);
      announcement.focus();
    }),
  );

  if (remove) {
    remove.addEventListener("click", () =>
      guard(async () => {
        const themeId = state.params.theme;
        const going = [...selected];
        for (const artworkId of going) {
          await api(
            `/api/themes/${encodeURIComponent(themeId)}/works/${encodeURIComponent(artworkId)}`,
            { method: "DELETE" },
          );
        }
        for (const artworkId of going) {
          const tile = grid.querySelector(`[data-artwork="${CSS.escape(artworkId)}"]`);
          if (tile) tile.remove();
        }
        selected.clear();
        settle();
        // The heading counted what was there before the removal, and a count that
        // no longer matches the tiles under it is the silent lie this surface
        // exists to refuse. Both figures are the tile count: a theme comes whole
        // rather than paged, so what is shown and what is held cannot differ.
        heading.textContent = recount(grid.children.length);
        say(`Removed ${going.length} ${going.length === 1 ? "work" : "works"} from this theme.`);
        announcement.focus();
      }),
    );
  }

  settle();
  return { settle, node: el("div", { class: "selection" }, [announcement, picker, add, remove]) };
}

function clearSelection(grid) {
  selected.clear();
  for (const box of grid.querySelectorAll("input.tile-select")) box.checked = false;
}

/* -- the three empty states -------------------------------------------------- */

/* Which nothing this is.
 *
 * Three branches with three texts, because they are three different facts and
 * they lead to three different next moves. Conflating the first two tells a
 * curator with 3,000 works that they own nothing; conflating the third with the
 * second reports the expected result of following a suggestion as a failed query,
 * and the conversation makes that one common — the artists it surfaces are by
 * definition ones the curator could not have named. */
function emptyState(query, chosen, showingTheme, themeName) {
  const artists = chosen.artist;
  const onlyAnArtist =
    !query && !showingTheme && artists.length === 1 && !FACET_KINDS.filter((kind) => kind !== "artist").some((kind) => chosen[kind].length);

  if (onlyAnArtist) {
    return el("div", { class: "stack empty" }, [
      el("h3", { text: `Nothing by ${artists[0]} yet.` }),
      el("p", {
        class: "muted",
        text:
          "That is the normal answer, not a failed search: the collection holds what has been acquired, " +
          "not everything that exists. Discover is where more comes from.",
      }),
      el("div", { class: "row" }, [
        el("button", { class: "action", type: "button", text: "Look for some in Discover", onclick: () => go("discover") }),
        el("button", { class: "action quiet", type: "button", text: "Show everything", onclick: () => go("collection", null, { density: state.params.density }) }),
      ]),
    ]);
  }

  if (!query && !showingTheme && !anyFacetChosen(chosen)) {
    return el("div", { class: "stack empty" }, [
      el("h3", { text: "Nothing is held yet." }),
      el("p", {
        class: "muted",
        text: "The collection fills from Discover: ask for something, judge what comes back, and what you accept lands here.",
      }),
      el("div", { class: "row" }, [
        el("button", { class: "action", type: "button", text: "Go to Discover", onclick: () => go("discover") }),
      ]),
    ]);
  }

  return el("div", { class: "stack empty" }, [
    el("h3", { text: "Nothing held matches this filter." }),
    // The filter itself, named. "No results" without saying what was asked for
    // leaves a curator guessing which of three narrowings did it.
    el("p", { class: "muted", text: `The filter is ${filterPhrase(query, chosen, showingTheme, themeName)}.` }),
    el("div", { class: "row" }, [
      // "Show everything" rather than "Clear the filter", and the wording is a
      // contract rather than a preference: it is what the way out of a search has
      // been called since the search landed, and it says where the control goes
      // rather than what it undoes. It drops every narrowing, which is the only
      // honest reading of the words.
      el("button", { class: "action", type: "button", text: "Show everything", onclick: () => go("collection", null, { density: state.params.density }) }),
      query ? clearSearchLink("Clear only the search") : null,
    ]),
  ]);
}

function filterPhrase(query, chosen, showingTheme, themeName) {
  const parts = [];
  if (query) parts.push(`the search “${query}”`);
  if (showingTheme) parts.push(`the theme “${themeName}”`);
  for (const kind of FACET_KINDS) {
    if (chosen[kind].length) parts.push(`${FACET_LABELS[kind].toLowerCase()} ${chosen[kind].map((value) => `“${value}”`).join(" or ")}`);
  }
  return parts.join(", and ");
}

/* -- the heading ------------------------------------------------------------- */

/* What is on screen and what is held, in one sentence.
 *
 * `page.total` is the server's count over everything the filter selects, so the
 * two figures differ exactly when the runaway guard bit — and saying both is what
 * keeps a short list from reading as a complete one. */
function headingText(shown, total, query, showingTheme, themeName) {
  // A theme holding one work read "1 works", which the grid could get away with
  // while the only number it ever printed was a whole catalogue's.
  const noun = total === 1 ? "work" : "works";
  const counted = shown === total ? `${total} ${noun}` : `${shown} of ${total} ${noun}`;
  if (query) return `${counted} matching “${query}”`;
  if (showingTheme) return `${counted} in “${themeName}”`;
  return counted;
}

/* -- the screen -------------------------------------------------------------- */

async function themePage(themeId) {
  const detail = await api(`/api/themes/${encodeURIComponent(themeId)}`);
  // Shaped like a works page so the grid, the heading and `shortfallNote` read
  // one thing. A theme's works come whole rather than paged, and it offers no
  // facets — the counts beside a theme would be counts over the catalogue.
  return { works: detail.works, total: detail.works.length, truncated: false, facets: [], theme: detail.theme };
}

export async function viewCollection(generation) {
  if (generation !== selectionGeneration) {
    selected.clear();
    selectionGeneration = generation;
  }

  const query = (state.params.q || "").trim();
  const chosen = facetsFor(state.params);
  const showingTheme = themeIsShowing(query, chosen);

  // Painted before anything is asked for, at the geometry the answer will have.
  render(generation, skeletonGrid(state.params.density === CATALOGUE ? CATALOGUE : CONTACT));

  // The themes come along on every paint because the rail is part of the screen,
  // not part of the theme filter: a curator has to see the themes in order to
  // choose one, and adding to a theme needs their names.
  const [themeList, page] = await Promise.all([
    api("/api/themes"),
    // The search and the facets go to the server, which is what makes the count
    // in the heading a statement about the catalogue rather than about this
    // screen's first page.
    showingTheme ? themePage(state.params.theme) : fetchAllWorks(query, chosen),
  ]);

  // `ThemeListOut` wraps its list; the rail wants the placements themselves.
  const themes = themeList.themes;
  const themeName = showingTheme ? page.theme.name : "";
  const density = resolveDensity(page.total);
  const heading = el("h2", { text: headingText(page.works.length, page.total, query, showingTheme, themeName) });
  const recount = (count) => headingText(count, count, query, showingTheme, themeName);

  if (!page.works.length) {
    render(
      generation,
      heading,
      collectionLayout(themes, page, chosen, showingTheme, density, null, [
        emptyState(query, chosen, showingTheme, themeName),
      ]),
    );
    return;
  }

  const grid = el("ul", { class: density === CONTACT ? "grid contact-sheet" : "grid" });
  const membership = themes.length
    ? membershipControls(themes, showingTheme, grid, heading, recount)
    : null;
  const onChange = membership ? membership.settle : () => {};
  for (const work of page.works) {
    grid.append(density === CONTACT ? contactTile(work, onChange) : workCard(work, onChange));
  }
  render(
    generation,
    heading,
    collectionLayout(themes, page, chosen, showingTheme, density, membership, [shortfallNote(page), grid]),
  );
}

/* The rails beside the works, and the toolbar above them. One function so the
 * populated screen and each empty one cannot come to disagree about where the
 * controls live — an empty grid that also loses its filters is an empty state a
 * curator cannot get out of. */
function collectionLayout(themes, page, chosen, showingTheme, density, membership, main) {
  const rails = [themeRail(themes, showingTheme)];
  if (showingTheme) {
    rails.push(
      el("p", {
        class: "rail-note",
        text: "Facets and the search narrow the whole collection, so they are not offered while a theme is showing. Clear the theme to use them.",
      }),
    );
  } else {
    rails.push(...facetRail(page.facets, chosen));
  }
  // Stated rather than silent: an address carrying both narrowings gets the one
  // that is in force and a sentence saying which.
  if (state.params.theme && !showingTheme) {
    rails.push(
      el("p", {
        class: "rail-note",
        text: "A theme in this address is set aside while a search or a facet is narrowing the collection.",
      }),
    );
  }
  return el("div", { class: "collection" }, [
    el("aside", { class: "rails", "aria-label": "Filters" }, rails),
    el("div", { class: "collection-main" }, [
      el("div", { class: "toolbar" }, [densityControl(density), membership ? membership.node : null]),
      ...main,
    ]),
  ]);
}
