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
 * has no repeated keys to use: `state.params` is a flat string map.
 *
 * **So the values are escaped before they are joined**, and unescaped after they
 * are split — which is what makes the pipe safe where the comma was not. A value
 * holding a literal pipe arrives here as `%7C` and survives the split whole; the
 * separator is the only bare pipe the string can contain. Choosing a rarer
 * character instead would have been the same bet the comma lost, just at longer
 * odds, and this needs no bet at all. `formatRoute` escapes the joined string
 * again on the way into the address and `parseRoute` unescapes it once on the way
 * out, so what `splitValues` sees is exactly what `joinValues` wrote. */
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

/* One escaped piece, or what was there.
 *
 * `decodeURIComponent` throws `URIError` on a malformed escape, and a hand-typed
 * or hand-truncated address is exactly where one comes from. A piece that will
 * not decode is used verbatim, which is wrong in a way the curator can see rather
 * than fatal in a way they cannot — the same trade `core/route.js` makes for the
 * same reason. Only `URIError` is swallowed. */
function decodeValue(piece) {
  try {
    return decodeURIComponent(piece);
  } catch (failure) {
    if (!(failure instanceof URIError)) throw failure;
    return piece;
  }
}

function splitValues(raw) {
  if (!raw) return [];
  return raw.split(FACET_SEPARATOR).filter(Boolean).map(decodeValue);
}

function joinValues(values) {
  return values.map((value) => encodeURIComponent(value)).join(FACET_SEPARATOR);
}

function facetsFor(params) {
  const chosen = {};
  for (const kind of FACET_KINDS) chosen[kind] = splitValues(params[kind]);
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
  return { ...state.params, theme: "", [kind]: joinValues(values) };
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
 * Always drawn where it can do something, at both densities, rather than revealed
 * on hover with the rest of the contact sheet's metadata: a control that only
 * exists once you are pointing at it is one a keyboard cannot find. And **not
 * drawn at all where it cannot** — with no theme to put a work into, a tick on
 * every tile is a control with nothing behind it, which is the same dead end the
 * facet rail is forbidden from offering. */
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
function workCard(work, selection) {
  return el("li", { class: "card", "data-artwork": work.artwork_id }, [
    selection ? selectBox(work, selection.settle) : null,
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
function contactTile(work, selection) {
  const status = statusBadge(work);
  return el("li", { class: "tile", "data-artwork": work.artwork_id }, [
    selection ? selectBox(work, selection.settle) : null,
    status ? el("div", { class: "tile-status" }, [status]) : null,
    cardImage(work),
    el("div", { class: "tile-caption" }, [
      el("span", { class: "tile-title", text: work.title }),
      el("span", { class: "tile-artist", text: work.artist ? work.artist.name : "Artist unrecorded" }),
    ]),
  ]);
}

/* -- the loading state ------------------------------------------------------ */

/* Tiles at the geometry the real ones will have — which means this is painted
 * only once that geometry is known.
 *
 * **The skeleton never guesses the density**, and an earlier draft of this screen
 * did: it drew a contact sheet whenever the address named nothing, while the
 * default below a few hundred works resolves to the catalogue. Every visit to a
 * small collection then jumped from twelve small tiles to N wide cards — the
 * reflow the rule exists to prevent, on the commonest path.
 *
 * The total is what decides the density and the first page is what carries it, so
 * the placeholder waits for that page. What it costs is that a collection
 * arriving in one round trip gets no skeleton at all, which is right: there is
 * nothing to wait through. What it buys is that the skeleton, whenever it is on
 * screen, is standing at the geometry the grid will occupy. */
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
  return el(
    "ul",
    {
      // Not `.grid`, though it lays out identically: a loading placeholder that
      // answers the selector the real grid answers is one every test and every
      // reader has to tell apart by its contents.
      class: density === CONTACT ? "grid-skeleton contact-sheet" : "grid-skeleton",
      "aria-hidden": true,
    },
    tiles,
  );
}

/* The whole screen, with the parts that are not known yet left blank.
 *
 * **The tiles are inside the same two-column layout the grid will be inside**,
 * which is the other half of standing at the final geometry: a placeholder that
 * spans the full page and is then replaced by a grid beside a 13rem rail has
 * tiles of a different size, however faithfully the tiles themselves were drawn.
 * The rail is empty because the vocabulary is a request that has not answered;
 * its column is a fixed width, so its contents arriving move nothing.
 *
 * The density control is real rather than a placeholder — the density is the one
 * thing that *is* known here, and a control that works while the pictures load is
 * better than a grey rectangle the same size. */
function skeletonScreen(density) {
  return [
    el("h2", { text: "Loading the collection…" }),
    el("div", { class: "collection" }, [
      el("aside", { class: "rails", "aria-hidden": true }),
      el("div", { class: "collection-main" }, [
        el("div", { class: "toolbar" }, [densityControl(density)]),
        skeletonGrid(density),
      ]),
    ]),
  ];
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

/* One theme in the rail: the filter, and the way to the theme itself.
 *
 * **Two acts, so two controls with two names.** Filtering the grid to a theme's
 * members and opening the theme are different things — one narrows what is on
 * this screen, the other leaves it — and a single chip whose behaviour depended
 * on where you clicked, or on a modifier, is a control whose action can only be
 * discovered by performing it. That is the failure this pair exists to avoid,
 * and it is an accessibility one before it is a usability one: a screen reader
 * announces one control with one name, so a hidden second act is not merely
 * undiscoverable there, it is unreachable.
 *
 * The filter keeps the theme's name as its whole label and its `aria-pressed`,
 * which is the toggle it has always been. The opener names the theme too —
 * "Open Winter" — because the rail renders one per theme and "Open" nine times
 * in a row tells a reader moving control by control nothing at all. */
function themeChip(placement, activeId) {
  const isShowing = placement.theme.theme_id === activeId;
  return el("span", { class: "theme-chip-pair" }, [
    el("button", {
      class: "theme-chip",
      type: "button",
      "aria-pressed": isShowing ? "true" : "false",
      text: placement.theme.name,
      onclick: () =>
        go(
          "collection",
          null,
          // Everything else goes: a theme is not composable with a search or a
          // facet, and a chip that appeared to do nothing because a search was
          // still in the address would be the worst of both.
          isShowing
            ? { density: state.params.density }
            : { density: state.params.density, theme: placement.theme.theme_id },
        ),
    }),
    el("button", {
      class: "action quiet theme-chip-open",
      type: "button",
      text: "Open",
      "aria-label": `Open ${placement.theme.name}`,
      onclick: () => go("theme", placement.theme.theme_id),
    }),
  ]);
}

function themeRail(themes, showingTheme) {
  const activeId = showingTheme ? state.params.theme : "";
  const chips = themes.map((placement) => themeChip(placement, activeId));
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

function uncheck(grid, artworkId) {
  const box = grid.querySelector(`[data-artwork="${CSS.escape(artworkId)}"] input.tile-select`);
  if (box) box.checked = false;
}

function clearSelection(grid) {
  selected.clear();
  for (const box of grid.querySelectorAll("input.tile-select")) box.checked = false;
}

/* Adding and removing membership from the grid, with the selection multi-select.
 *
 * **Nothing here repaints the screen**, and that is the rule rather than an
 * optimisation: a curator standing on "Add to theme" who is handed a new page has
 * lost their place and their focus. The outcome is announced in a live region and
 * the tiles that left are taken out one at a time.
 *
 * **There is no bulk route, so this is a loop, and a loop can stop halfway.**
 * `POST /api/themes/{id}/works` takes one work and the store refuses a work the
 * theme already holds, so the two things that make a partial edit unrecoverable
 * are both dealt with before the loop starts: what the theme already has is read
 * and skipped, and each work leaves the selection as it lands. A refusal partway
 * therefore leaves exactly the works that did not go still ticked, with the
 * button still live — the retry is pressing it again, and it does not re-send
 * what already succeeded.
 *
 * Returns `null` when there is nothing a selection could be used for, which is
 * what keeps the tick off every tile in a collection with no themes. */
function membershipControls({ themes, showingTheme, grid, heading, recount, whenEmpty }) {
  // The theme being shown is not offered: every work on screen is already in it,
  // so the only thing that control could do is refuse. Excluding it is also what
  // stops the picker's own default being a one-click error.
  const addable = themes.filter((placement) => !(showingTheme && placement.theme.theme_id === state.params.theme));
  if (!addable.length && !showingTheme) return null;

  // Focusable, and focused when an edit completes. Finishing the edit disables
  // the button the curator is standing on, and a browser blurs a control it
  // disables — which drops the keyboard to the top of the document, several
  // hundred tiles above where the work was happening. The outcome sentence is
  // where focus belongs: it is what just happened, and Tab continues from the
  // toolbar into the grid.
  const announcement = el("p", { class: "muted selection-status", "aria-live": "polite", tabindex: "-1" });

  const picker = addable.length
    ? el("select", { id: "add-to-theme", "aria-label": "Theme to add the selected works to" })
    : null;
  for (const placement of addable) {
    picker.append(el("option", { value: placement.theme.theme_id, text: placement.theme.name }));
  }

  const add = picker ? el("button", { class: "action", type: "button", text: "Add to theme" }) : null;
  const remove = showingTheme
    ? el("button", { class: "action quiet", type: "button", text: "Remove from this theme" })
    : null;

  const say = (words) => {
    // Not rewritten unchanged: a live region reassigned the same sentence
    // announces it again, which trains a listener to tune the region out.
    if (announcement.textContent !== words) announcement.textContent = words;
  };

  const settle = () => {
    if (add) add.disabled = selected.size === 0;
    if (remove) remove.disabled = selected.size === 0;
    say(selected.size === 0 ? "No works selected." : `${selected.size} selected.`);
  };

  if (add) {
    add.addEventListener("click", () =>
      guard(async () => {
        const themeId = picker.value;
        const name = picker.options[picker.selectedIndex].text;
        const asked = selected.size;
        // Read before writing. The store refuses a work the theme already holds,
        // and a loop that discovered that halfway through would have applied half
        // the edit and reported a refusal.
        const detail = await api(`/api/themes/${encodeURIComponent(themeId)}`);
        const held = new Set(detail.works.map((work) => work.artwork_id));
        const wanted = [...selected].filter((artworkId) => !held.has(artworkId));
        const already = asked - wanted.length;
        let added = 0;
        try {
          for (const artworkId of wanted) {
            await api(`/api/themes/${encodeURIComponent(themeId)}/works`, {
              method: "POST",
              body: JSON.stringify({ artwork_id: artworkId }),
            });
            added += 1;
            selected.delete(artworkId);
            uncheck(grid, artworkId);
          }
        } catch (failure) {
          settle();
          say(`Added ${added} of ${wanted.length} to ${name}. The rest are still selected, so pressing Add again retries only those.`);
          announcement.focus();
          // Rethrown so `guard` shows the server's own words for the refusal.
          // The sentence above says how far it got; only the server can say why
          // it stopped.
          throw failure;
        }
        clearSelection(grid);
        settle();
        if (!wanted.length) say(`All ${already} ${already === 1 ? "was" : "were"} already in ${name}.`);
        else {
          const carried = already ? ` ${already} ${already === 1 ? "was" : "were"} already in it.` : "";
          say(`Added ${added} ${added === 1 ? "work" : "works"} to ${name}.${carried}`);
        }
        announcement.focus();
      }),
    );
  }

  if (remove) {
    remove.addEventListener("click", () =>
      guard(async () => {
        const themeId = state.params.theme;
        const going = [...selected];
        let removed = 0;
        try {
          for (const artworkId of going) {
            await api(`/api/themes/${encodeURIComponent(themeId)}/works/${encodeURIComponent(artworkId)}`, {
              method: "DELETE",
            });
            removed += 1;
            selected.delete(artworkId);
            const tile = grid.querySelector(`[data-artwork="${CSS.escape(artworkId)}"]`);
            if (tile) tile.remove();
          }
        } finally {
          settle();
          // The heading counted what was there before the removal, and a count
          // that no longer matches the tiles under it is the silent lie this
          // surface exists to refuse. Both figures are the tile count: a theme
          // comes whole rather than paged, so shown and held cannot differ.
          heading.textContent = recount(grid.children.length);
          // A theme whose last member has just gone is empty, and an empty grid
          // with no sentence reads as a broken screen rather than as a theme
          // holding nothing.
          if (!grid.children.length) whenEmpty();
        }
        say(`Removed ${removed} ${removed === 1 ? "work" : "works"} from this theme.`);
        announcement.focus();
      }),
    );
  }

  settle();
  return { settle, node: el("div", { class: "selection" }, [announcement, picker, add, remove]) };
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
    !query &&
    !showingTheme &&
    artists.length === 1 &&
    !FACET_KINDS.filter((kind) => kind !== "artist").some((kind) => chosen[kind].length);

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
        el("button", {
          class: "action quiet",
          type: "button",
          text: "Show everything",
          onclick: () => go("collection", null, { density: state.params.density }),
        }),
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
      el("button", {
        class: "action",
        type: "button",
        text: "Show everything",
        onclick: () => go("collection", null, { density: state.params.density }),
      }),
      query ? clearSearchLink("Clear only the search") : null,
    ]),
  ]);
}

function filterPhrase(query, chosen, showingTheme, themeName) {
  const parts = [];
  if (query) parts.push(`the search “${query}”`);
  if (showingTheme) parts.push(`the theme “${themeName}”`);
  for (const kind of FACET_KINDS) {
    if (chosen[kind].length) {
      parts.push(`${FACET_LABELS[kind].toLowerCase()} ${chosen[kind].map((value) => `“${value}”`).join(" or ")}`);
    }
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

  // Said, not drawn. How much there is decides the density and the density
  // decides the geometry, so a placeholder painted before the first page has
  // answered can only guess — see `skeletonGrid` for what that cost when it did.
  // The heading is the one thing that can be painted now, and it is the same
  // element the real heading replaces, so it holds its own place.
  render(generation, el("h2", { text: "Loading the collection…" }));

  // The themes come along on every paint because the rail is part of the screen,
  // not part of the theme filter: a curator has to see the themes in order to
  // choose one, and adding to a theme needs their names.
  const [themeList, page] = await Promise.all([
    api("/api/themes"),
    // The search and the facets go to the server, which is what makes the count
    // in the heading a statement about the catalogue rather than about this
    // screen's first page.
    showingTheme
      ? themePage(state.params.theme)
      : fetchAllWorks(query, chosen, (first) => {
          // Only when there is more to come. A collection that arrives whole in
          // one round trip has nothing to wait through, and the tiles it would
          // stand in for are already on their way.
          if (first.truncated) render(generation, ...skeletonScreen(resolveDensity(first.total)));
        }),
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
  const selection = membershipControls({
    themes,
    showingTheme,
    grid,
    heading,
    recount,
    whenEmpty: () => grid.replaceWith(emptyState(query, chosen, showingTheme, themeName)),
  });
  for (const work of page.works) {
    grid.append(density === CONTACT ? contactTile(work, selection) : workCard(work, selection));
  }
  render(
    generation,
    heading,
    collectionLayout(themes, page, chosen, showingTheme, density, selection, [shortfallNote(page), grid]),
  );
}

/* The rails beside the works, and the toolbar above them. One function so the
 * populated screen and each empty one cannot come to disagree about where the
 * controls live — an empty grid that also loses its filters is an empty state a
 * curator cannot get out of. */
function collectionLayout(themes, page, chosen, showingTheme, density, selection, main) {
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
      el("div", { class: "toolbar" }, [densityControl(density), selection ? selection.node : null]),
      ...main,
    ]),
  ]);
}
