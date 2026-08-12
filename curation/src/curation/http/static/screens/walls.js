/* The Walls — what is hanging right now, on each wall.
 *
 * The product's home, and the first of the three destinations.
 * `information-architecture.md` argues the case and records the counter-argument:
 * most sessions begin with an intention, so opening on a screen of pictures puts
 * a click in front of them. The answer is that this screen carries the live entry
 * points rather than being a dead end, and that the product's identity claim is
 * that it is a collection rather than a tool.
 *
 * The screen this chunk moved is the built manifest view. The Walls screen the IA
 * describes — each wall's hanging work large, the theme control, what is next —
 * is a later chunk's, and arrives in this file.
 */

import { api } from "../core/api.js";
import { facts, table } from "../core/badges.js";
import { el, render } from "../core/render.js";
import { go } from "../core/router.js";

export async function viewWalls(generation) {
  // One section per wall, with one wall the degenerate case rather than a
  // special one: there is no single-wall layout here for a second display to
  // replace. A wall with nothing hanging is asked nothing — the route would
  // refuse, and correctly, because there is no theme to evaluate.
  const walls = await api("/api/walls");
  const hung = walls.walls.filter((wall) => wall.theme);
  const builds = await Promise.all(
    hung.map(async (wall) => [wall, await api(`/api/manifest?wall_id=${encodeURIComponent(wall.wall_id)}`)]),
  );

  const panels = [el("h2", { text: "The Walls" })];
  const empty = walls.walls.filter((candidate) => !candidate.theme);
  for (const wall of empty) {
    panels.push(el("p", { class: "muted", text: `Nothing is hanging on ${wall.name}.` }));
  }
  // The fact the MCP surface already states after an unhang, said here too:
  // taking a theme down rewrites no manifest, so the set goes on showing the
  // picture. A curator who read only the lines above would take a successful
  // take-down for a failed one — the same inference `activate_theme`'s docstring
  // cites when it argues that hanging must publish immediately.
  //
  // Once, after the list, rather than once per wall: it is one fact about how
  // taking down works, not a property of any particular wall, and three empty
  // rooms would otherwise print it three times. It is the MCP binding's own
  // sentence with "The wall" widened to "A wall", because here it stands under a
  // list rather than after one wall's take-down — two surfaces stating one fact
  // in different words is how a reader learns to trust neither.
  if (empty.length) {
    panels.push(
      el("p", {
        class: "note",
        text: "A wall goes on showing what it was showing until a theme is hung.",
      }),
      // The way out of the empty state, offered here rather than named in the
      // sentence above. That sentence used to end "Hang a theme from Themes",
      // which pointed at a tab this chunk removed — a screen that names a
      // destination the navigation no longer has is worse than one that names
      // none, because the reader goes looking.
      el("div", { class: "row" }, [
        el("button", { class: "action", type: "button", text: "Choose a theme to hang", onclick: () => go("theme") }),
      ]),
    );
  }
  for (const [wall, manifest] of builds) {
    panels.push(...manifestPanels(wall, manifest));
  }
  render(generation, ...panels);
}

function manifestPanels(wall, manifest) {
  return [
    // `h3` for the wall and `h4` for its panels, so the nesting survives a
    // second wall: with two walls hung, sibling `h3`s would give a reader
    // navigating by heading four headings in a row and no signal for which
    // counts belong to which room. The single-wall view read correctly by
    // accident, having only one room's worth of headings to confuse.
    el("h3", { class: "wall-title", text: `${wall.name}: ${manifest.theme.name}` }),
    el("p", { class: "note", text: manifest.summary }),
    el("div", { class: "panel" }, [
      el("h4", { text: `Showing (${manifest.entries.length})` }),
      manifest.entries.length
        ? table(
            "Every work the display plane is being asked to show, in order.",
            ["Title", "Artist", "Render"],
            manifest.entries.map((e) => [e.title, e.artist, e.render_path]),
          )
        : el("p", { class: "muted", text: "Nothing in this theme is currently displayable." }),
    ]),
    el("div", { class: "panel" }, [
      // Never omitted when empty: a section that appeared only on trouble would
      // train a reader to take its absence as "everything is fine".
      el("h4", { text: `Not showing (${manifest.exclusions.length})` }),
      manifest.exclusions.length
        ? table(
            "Every work this theme holds that is not on the wall, and exactly why.",
            ["Title", "Reason", "What is missing"],
            manifest.exclusions.map((x) => [x.title, x.reason, x.detail]),
          )
        : el("p", { class: "muted", text: "Every work in this theme reached the wall." }),
    ]),
    el("div", { class: "panel" }, [
      el("h4", { text: "How it rotates" }),
      facts([
        ["Interval", `${manifest.rotation_interval_seconds} seconds`],
        ["Order", manifest.shuffle ? "shuffled" : "as curated"],
        ["Directive sequence", manifest.directive_sequence],
        ["Pinned work", manifest.pinned_work_id],
      ]),
    ]),
  ];
}
