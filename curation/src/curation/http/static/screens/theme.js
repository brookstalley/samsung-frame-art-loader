/* Theme — a saved selection over the collection, and the acts that are its own.
 *
 * **Contextual, not a destination.** `information-architecture.md` records the
 * change and the reason: a theme is a saved selection over the collection, not a
 * parallel noun, and promoting it to a peer of the collection is what forces a
 * curator to hold the mapping between the two in their head. What belongs here
 * is what is genuinely about the theme rather than about a work — its name, the
 * order its works reach the wall in, where it hangs, and whether it exists.
 *
 * **Membership is edited from the grid *and* here, and the duplication is
 * deliberate.** Putting works into a theme is organising, and organising happens
 * against the works being organised, which is why the collection screen carries
 * a selection and an "Add to theme" — that is the path a curator building a
 * theme takes. The picker and the per-row remove below are the other job: a
 * curator already looking at this theme's order, deciding one of these does not
 * belong, should not have to go and find it in a grid of everything to say so.
 *
 * **Every write repaints from the answer it was given.** `POST`/`DELETE` on a
 * theme's works return the resulting order and the delete returns the themes
 * that remain, so nothing here guesses where a work landed and then asks. The
 * one exception is deliberate and marked where it happens.
 */

import { api, fetchAllWorks } from "../core/api.js";
import { fitBadge, shortfallNote, table } from "../core/badges.js";
import { confirmAct } from "../core/confirm.js";
import { hangTheme } from "../core/hanging.js";
import { el, guard, render } from "../core/render.js";
import { backLink, go, refresh } from "../core/router.js";

export async function viewTheme(generation) {
  // The walls come along because hanging is an act against a named wall: a
  // theme panel cannot offer "put this up" without saying where, and it cannot
  // say where without knowing what the walls are called.
  const [themes, walls, works] = await Promise.all([api("/api/themes"), api("/api/walls"), fetchAllWorks()]);

  const name = el("input", { type: "text", id: "new-theme-name", required: true });
  const create = el("div", { class: "panel" }, [
    el("h3", { text: "New theme" }),
    el("div", { class: "row" }, [
      el("div", { class: "field" }, [el("label", { for: "new-theme-name", text: "Name" }), name]),
      el("button", {
        class: "action",
        type: "button",
        text: "Create",
        onclick: () =>
          guard(async () => {
            await api("/api/themes", { method: "POST", body: JSON.stringify({ name: name.value }) });
            await refresh();
          }),
      }),
    ]),
  ]);

  const panels = [el("p", {}, [backLink()]), el("h2", { text: "Themes" }), create];

  const shortfall = shortfallNote(works);
  if (shortfall) panels.push(shortfall);

  if (!walls.walls.length) {
    panels.push(
      el("p", { class: "note", text: "There are no walls, so nothing can be hung. A wall is created when the plane first opens the catalogue." }),
    );
  }

  /* The themes, in their own container so a delete can repaint them from the
   * answer it was given rather than reloading the screen. Nothing else on this
   * page changes when a theme goes: the refusal makes a hung theme undeletable,
   * so no wall's state can move, and no work is touched. */
  const list = el("div", { class: "stack" });
  const paintThemes = (placements) => {
    list.replaceChildren(
      ...(placements.length
        ? placements.map((placement) => themePanel(placement, walls.walls, works.works, paintThemes))
        : [el("p", { class: "muted", text: "No themes yet. Create one, then add works to it." })]),
    );
  };
  paintThemes(themes.themes);

  render(generation, ...panels, list);
}

function themePanel(placement, walls, allWorks, repaintThemes) {
  const theme = placement.theme;
  const hangingOn = placement.hanging_on;
  // The name is read back from every rename rather than kept as the value that
  // was typed: `update_theme` trims, so a name entered with a trailing space is
  // stored without one, and a heading painted from the input would show a name
  // the catalogue does not hold. It is also what the membership controls say —
  // "Remove from Winter" — so a stale copy would be wrong in two places.
  let currentName = theme.name;

  const heading = el("span", { text: currentName });
  const picker = el("select", { id: `add-${theme.theme_id}` });
  for (const work of allWorks) {
    picker.append(
      el("option", {
        value: work.artwork_id,
        text: work.artist ? `${work.title} — ${work.artist.name}` : work.title,
      }),
    );
  }

  const body = el("div", { class: "stack" }, [el("p", { class: "muted", text: "Loading works…" })]);
  /* **How many works are in here, said in words rather than left to be counted.**
   * `information-architecture.md` § Information Hierarchy makes the count this
   * screen's secondary content, and the numbered column is not it: a curator
   * deciding whether a theme is worth hanging wants the size, and reading the
   * last row's number is arithmetic performed on a table that may not be on
   * screen. Repainted with the list rather than rendered once, because an add
   * and a remove both change it and both answer with the new order. */
  const count = el("span", { class: "muted" });
  // Held rather than only rendered, so a rename can relabel the membership
  // controls without asking the server for an order it has already been given.
  let members = [];
  const paintMembers = (works) => {
    members = works;
    count.textContent = members.length === 1 ? "1 work" : `${members.length} works`;
    body.replaceChildren(memberList(theme.theme_id, currentName, members, paintMembers));
  };
  // The one read here that is a read: nothing has answered with this theme's
  // works yet, because the listing this panel was built from does not carry them.
  guard(async () => paintMembers((await api(`/api/themes/${encodeURIComponent(theme.theme_id)}`)).works));

  const rename = el("input", {
    type: "text",
    id: `rename-${theme.theme_id}`,
    value: currentName,
    "aria-label": `Name of ${currentName}`,
  });
  const renameButton = el("button", {
    class: "action quiet",
    type: "button",
    text: "Rename",
    "aria-label": `Rename ${currentName}`,
    onclick: () =>
      guard(async () => {
        const renamed = await api(`/api/themes/${encodeURIComponent(theme.theme_id)}`, {
          method: "POST",
          body: JSON.stringify({ name: rename.value }),
        });
        currentName = renamed.name;
        heading.textContent = currentName;
        rename.value = currentName;
        nameTheControls();
        // The membership controls name the theme they remove from, so they
        // are repainted too — a table still offering "Remove from Winter"
        // under a heading that reads "Late night" is one a curator has to
        // work out which of the two to believe.
        paintMembers(members);
      }),
  });
  const deleteButton = el("button", {
    class: "action quiet",
    type: "button",
    text: "Delete",
    "aria-label": `Delete ${currentName}`,
    onclick: () => guard(() => remove(theme.theme_id, currentName, repaintThemes)),
  });
  /* **Every theme on this screen renders the same three controls, so the visible
   * words cannot tell them apart.** A curator reading the panel has the heading
   * above to go on; somebody moving through the form controls one at a time hears
   * "Name, edit text" and "Rename" and "Delete" once per theme, with the panel
   * they belong to reconstructible only from the reading order — on a control that
   * destroys something. `accessibility-spec.md` asks a control to name what it acts
   * on, and the membership table in this same panel already does ("Remove Blue
   * Poles from Winter"). Re-applied after a rename for the reason the membership
   * controls are repainted: a label naming a theme by its old name is worse than
   * one naming no theme at all. */
  const nameTheControls = () => {
    rename.setAttribute("aria-label", `Name of ${currentName}`);
    renameButton.setAttribute("aria-label", `Rename ${currentName}`);
    deleteButton.setAttribute("aria-label", `Delete ${currentName}`);
  };
  const renameRow = el("div", { class: "row" }, [
    el("div", { class: "field" }, [
      el("label", { for: `rename-${theme.theme_id}`, text: "Name" }),
      rename,
    ]),
    renameButton,
    deleteButton,
  ]);

  return el("div", { class: "panel" }, [
    el("h3", {}, [
      heading,
      // Hanging carries a glyph and the words beside any colour — and the words
      // name the walls, because "on the wall" reads correctly today only while
      // there is one of them.
      hangingOn.length
        ? el("span", { class: "badge", style: "margin-left: 0.5rem" }, [
            el("span", { class: "glyph", text: "●", "aria-hidden": true }),
            el("span", { text: `on ${hangingOn.map((wall) => wall.name).join(", ")}` }),
          ])
        : null,
    ]),
    // Below the heading rather than inside it: the heading is the theme's name,
    // and a count spliced into it becomes part of the name everywhere a heading
    // is read back — including by anything listing the themes on this screen.
    el("p", { class: "muted" }, [count]),
    theme.description ? el("p", { class: "muted", text: theme.description }) : null,
    renameRow,
    el("div", { class: "row" }, [
      el("div", { class: "field" }, [
        el("label", { for: `add-${theme.theme_id}`, text: "Add a work" }),
        picker,
      ]),
      el("button", {
        class: "action quiet",
        type: "button",
        text: "Add",
        onclick: () =>
          guard(async () => {
            const detail = await api(`/api/themes/${encodeURIComponent(theme.theme_id)}/works`, {
              method: "POST",
              body: JSON.stringify({ artwork_id: picker.value }),
            });
            paintMembers(detail.works);
          }),
      }),
      // One button per wall, named for that wall. There is no single-wall
      // shortcut to replace when a second display arrives, which is the whole
      // point: with one wall this reads "Hang on the living room" and with three
      // it reads as three choices, and neither is a different layout.
      //
      // **The walls this theme is already on are not offered here, and that
      // filter is load-bearing rather than tidiness.** Hanging what is already
      // hanging republishes the manifest, which is the path a curator takes when
      // an archive has left a picture up — and that path lives on the Walls
      // screen, whose picker lists every theme including the one showing. This
      // screen offers the rooms this theme is *not* in; teaching Walls the same
      // filter would delete the only republish route there is.
      ...walls
        .filter((wall) => !hangingOn.some((hung) => hung.wall_id === wall.wall_id))
        .map((wall) =>
          el("button", {
            class: "action",
            type: "button",
            text: `Hang on ${wall.name}`,
            onclick: () => guard(() => hang(theme.theme_id, currentName, wall)),
          }),
        ),
      // **Unconfirmed, and that is a decision.** Flow 6 makes activation the act
      // that gets a question, because it is the one that changes what other
      // people in the house see. Taking a theme down rewrites no manifest, so
      // the room goes on showing exactly what it was showing; what changes is
      // which theme the catalogue says belongs there, and the undo is the hang
      // button that reappears in its place.
      ...hangingOn.map((wall) =>
        el("button", {
          class: "action quiet",
          type: "button",
          text: `Take down from ${wall.name}`,
          onclick: () =>
            guard(async () => {
              await api(`/api/walls/${encodeURIComponent(wall.wall_id)}/theme`, { method: "DELETE" });
              await refresh();
            }),
        }),
      ),
    ]),
    body,
  ]);
}

/* Hanging, asked about before it happens.
 *
 * **The consequence is evaluated, not predicted.** `GET /api/manifest` takes a
 * wall and a theme and answers what that pairing would put up without writing
 * anything, so the sentence in the dialog is the build's own summary — including
 * the case where the answer is that the theme holds nothing displayable, which
 * is exactly what a curator wants to be told before pressing the button rather
 * than after.
 *
 * **Both the theme and the wall are named**, even in a house with one wall. A
 * question that reads correctly today only because there is one possible target
 * is the last place a mistake could have been caught.
 *
 * The wall view is where this lands, and it repaints from the manifest the
 * activation published rather than from the preview above it: the preview said
 * what *would* happen, and what did is a different question. */
/* Leaves for the Walls screen, which is where the result of this act is. The
 * question, the preview and the request are `core/hanging.js`'s — the Walls
 * screen asks the same one, and one act must not have two wordings. */
const hang = (themeId, themeName, wall) =>
  hangTheme({ themeId, themeName, wall, then: async () => go("walls") });

/* Deleting a theme — the one act on this screen that destroys something.
 *
 * **Confirmed, unlike taking a theme down, because there is no undo.** A theme
 * is a grouping and its works survive it, which is what the question says: a
 * curator who believes they are about to lose the pictures will hesitate over an
 * act that is cheap, and one who does not know the grouping is gone for good
 * will perform it without reading.
 *
 * **The count is read at the moment the question is asked** rather than taken
 * from whatever this panel last painted, for the same reason the hang preview is
 * fetched: the sentence is a statement about the catalogue now.
 *
 * **The refusal is the server's and is shown as it was written.** A theme
 * hanging anywhere cannot be deleted, and the message names the rooms and both
 * ways out of it; `guard` puts that sentence in front of the curator unchanged.
 * Nothing here predicts the refusal from `hanging_on` — a second copy of the
 * rule would be a second thing to keep true, and it would be wrong about a theme
 * somebody hung from another tab a moment ago. */
async function remove(themeId, themeName, repaintThemes) {
  const detail = await api(`/api/themes/${encodeURIComponent(themeId)}`);
  const held = detail.works.length;
  const confirmed = await confirmAct({
    title: `Delete ${themeName}?`,
    consequence: held
      ? `The ${held} ${held === 1 ? "work it holds stays" : "works it holds stay"} in the collection. Only the grouping goes, and it cannot be brought back.`
      : "It holds no works. The grouping cannot be brought back.",
    confirmLabel: "Delete",
  });
  if (!confirmed) return;
  const remaining = await api(`/api/themes/${encodeURIComponent(themeId)}`, { method: "DELETE" });
  repaintThemes(remaining.themes);
}

function memberList(themeId, themeName, works, paint) {
  if (!works.length) {
    return el("p", { class: "muted", text: "This theme holds no works yet." });
  }
  const rows = works.map((work, index) => {
    // The answer to the move is what the list becomes, so the table is repainted
    // from it. A second read would be the same order arrived at more slowly, and
    // repainting from the *sent* position would be optimism: the service clamps
    // and renumbers, so where a work lands is its answer to give.
    const move = (position) =>
      guard(async () => {
        const detail = await api(
          `/api/themes/${encodeURIComponent(themeId)}/works/${encodeURIComponent(work.artwork_id)}/position`,
          { method: "POST", body: JSON.stringify({ position }) },
        );
        paint(detail.works);
      });
    const controls = el("div", { class: "row" }, [
      el("button", {
        class: "action quiet",
        type: "button",
        text: "↑",
        "aria-label": `Move ${work.title} earlier`,
        disabled: index === 0,
        onclick: () => move(index - 1),
      }),
      el("button", {
        class: "action quiet",
        type: "button",
        text: "↓",
        "aria-label": `Move ${work.title} later`,
        disabled: index === works.length - 1,
        onclick: () => move(index + 1),
      }),
      // **The label says which collection the work is leaving.** "Remove" alone
      // promises the work is gone, and `information-architecture.md` rules that
      // out for a *work*: there is no delete of one, archive is the word, and a
      // curator who believes removal is destructive hesitates over something
      // cheap. This control removes a work from a *theme* — the work stays
      // catalogued, stays in every other theme, and is put back by adding it —
      // so the honest fix is to name the theme rather than to borrow Archive,
      // which would say something false about the catalogue.
      el("button", {
        class: "action quiet",
        type: "button",
        text: `Remove from ${themeName}`,
        "aria-label": `Remove ${work.title} from ${themeName}`,
        onclick: () =>
          guard(async () => {
            const detail = await api(
              `/api/themes/${encodeURIComponent(themeId)}/works/${encodeURIComponent(work.artwork_id)}`,
              { method: "DELETE" },
            );
            paint(detail.works);
          }),
      }),
    ]);
    return [String(index + 1), work.title, work.artist ? work.artist.name : "—", fitBadge(work), controls];
  });
  return table(
    "In curated order. Position decides what the wall shows first.",
    // The last column is named rather than left blank: an empty `th` is
    // announced as an empty column header, which tells a screen-reader user
    // nothing about the three buttons in every row beneath it.
    ["#", "Title", "Artist", "Size on the wall", "Order and membership"],
    rows,
  );
}
