/* Theme — a saved selection over the collection, and the act of hanging it.
 *
 * **Contextual, not a destination.** `information-architecture.md` records the
 * change and the reason: a theme is a saved selection over the collection, not a
 * parallel noun, and promoting it to a peer of the collection is what forces a
 * curator to hold the mapping between the two in their head. The rail inside
 * Collection and the single-theme screen are a later chunk's; what this chunk
 * moved is the built themes screen, off the navigation and onto a real address.
 */

import { api, fetchAllWorks } from "../core/api.js";
import { fitBadge, shortfallNote, table } from "../core/badges.js";
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

  if (!themes.themes.length) {
    panels.push(el("p", { class: "muted", text: "No themes yet. Create one, then add works to it." }));
  }

  const shortfall = shortfallNote(works);
  if (shortfall) panels.push(shortfall);

  if (!walls.walls.length) {
    panels.push(
      el("p", { class: "note", text: "There are no walls, so nothing can be hung. A wall is created when the plane first opens the catalogue." }),
    );
  }

  for (const placement of themes.themes) {
    panels.push(themePanel(placement, walls.walls, works.works));
  }
  render(generation, ...panels);
}

function themePanel(placement, walls, allWorks) {
  const theme = placement.theme;
  const hangingOn = placement.hanging_on;
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

  const refreshMembers = async () => {
    const detail = await api(`/api/themes/${encodeURIComponent(theme.theme_id)}`);
    body.replaceChildren(memberList(theme.theme_id, detail.works, refreshMembers));
  };
  guard(refreshMembers);

  return el("div", { class: "panel" }, [
    el("h3", {}, [
      el("span", { text: theme.name }),
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
    theme.description ? el("p", { class: "muted", text: theme.description }) : null,
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
            await api(`/api/themes/${encodeURIComponent(theme.theme_id)}/works`, {
              method: "POST",
              body: JSON.stringify({ artwork_id: picker.value }),
            });
            await refreshMembers();
          }),
      }),
      // One button per wall, named for that wall. There is no single-wall
      // shortcut to replace when a second display arrives, which is the whole
      // point: with one wall this reads "Hang on the living room" and with three
      // it reads as three choices, and neither is a different layout.
      ...walls
        .filter((wall) => !hangingOn.some((hung) => hung.wall_id === wall.wall_id))
        .map((wall) =>
          el("button", {
            class: "action",
            type: "button",
            text: `Hang on ${wall.name}`,
            onclick: () =>
              guard(async () => {
                await api(`/api/themes/${encodeURIComponent(theme.theme_id)}/activate`, {
                  method: "POST",
                  body: JSON.stringify({ wall_id: wall.wall_id }),
                });
                go("walls");
              }),
          }),
        ),
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

function memberList(themeId, works, after) {
  if (!works.length) {
    return el("p", { class: "muted", text: "This theme holds no works yet." });
  }
  const rows = works.map((work, index) => {
    const move = (position) =>
      guard(async () => {
        await api(
          `/api/themes/${encodeURIComponent(themeId)}/works/${encodeURIComponent(work.artwork_id)}/position`,
          { method: "POST", body: JSON.stringify({ position }) },
        );
        await after();
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
      el("button", {
        class: "action quiet",
        type: "button",
        text: "Remove",
        "aria-label": `Remove ${work.title} from this theme`,
        onclick: () =>
          guard(async () => {
            await api(
              `/api/themes/${encodeURIComponent(themeId)}/works/${encodeURIComponent(work.artwork_id)}`,
              { method: "DELETE" },
            );
            await after();
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
    ["#", "Title", "Artist", "Size on the wall", "Order and removal"],
    rows,
  );
}
