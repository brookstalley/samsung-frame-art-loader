/* Health — the observations the panel states, and the spend record.
 *
 * **Reachable, and not in the navigation.** `information-architecture.md` takes
 * it out on the grounds that an appliance-status panel must not be a peer of the
 * art in a product whose identity claim is "museum, not gadget", and the masthead
 * indicator in `core/status.js` is what makes that safe: it is always present, it
 * names what is wrong, and this screen is what it expands to.
 *
 * It has a real address, so a failure can link to it and a curator can bookmark
 * it — "not navigable-to" is a statement about the navigation, never about the
 * URL.
 *
 * **One heartbeat panel per wall.** The reading became one per wall because a
 * single observation for an installation with two rooms cannot name the room
 * that went quiet. One wall is the degenerate case of many here as everywhere
 * else on this surface: with one wall this is one panel and reads exactly as the
 * single-wall screen did, and there is no layout for a second display to
 * replace.
 */

import { api } from "../core/api.js";
import { facts } from "../core/badges.js";
import { el, render } from "../core/render.js";
import { backLink } from "../core/router.js";

/* The display plane's own report, whatever it chose to put in it.
 *
 * Rendered generically rather than as named rows, and that is the design rather
 * than laziness: `reported_at` is the only key the observability strategy makes
 * contract, and everything else is explicitly the writer's to shape. Naming TV
 * connectivity and panel state here would invent a second contract that plane
 * never agreed to — and a writer that spelled one differently would drop off the
 * panel in silence, which is the failure the one named key exists to prevent.
 *
 * So whatever arrives is shown. That is what gives the failure table's TV, panel
 * and last-error rows a reader at all. */
function reportedFacts(reported) {
  if (!reported) return null;
  const pairs = Object.entries(reported).map(([key, value]) => [
    key,
    // Objects and arrays would reach `facts` as "[object Object]", which is a
    // field displayed and unreadable — worse than one omitted, because it looks
    // like the panel is working.
    value !== null && typeof value === "object" ? JSON.stringify(value) : value,
  ]);
  return pairs.length ? facts(pairs) : null;
}

function heartbeatPanel(wall) {
  const name = wall.wall_name || "An unnamed wall";
  const reading = wall.heartbeat;
  if (!reading) {
    return el("div", { class: "panel wall-reading" }, [
      el("h3", { text: name }),
      el("p", { class: "note", text: "The health reading carries no heartbeat for this wall." }),
    ]);
  }
  // `wall-reading` as well as `panel`, and the extra class earns its place twice
  // over: `app.css` has a rule keyed on it that nothing was emitting after the
  // client split, and a test asking "is every wall named, and only walls" needs a
  // selector that means *a wall's panel* rather than *any panel on this screen* —
  // the backup and the geometry are panels too.
  return el("div", { class: "panel wall-reading" }, [
    // The wall's own name is the heading. "The display plane" was right while
    // there was one of it, and is a sentence that silently becomes wrong.
    el("h3", { text: name }),
    // An observation with its age, never a verdict. A green dot computed from
    // a file that may simply be young is how a health surface starts lying.
    el("p", { text: reading.description }),
    facts([
      ["Heartbeat file", reading.path],
      ["Last reported", reading.reported_at],
      // The exact figure beside the sentence's plain-language one. Not the
      // same fact twice in worse units: the sentence is what a curator reads,
      // and this is what an operator compares against the 60-second interval.
      ["Age", reading.age_seconds === null || reading.age_seconds === undefined ? null : `${reading.age_seconds.toFixed(0)} seconds`],
      ["Problem", reading.problem],
    ]),
    reading.absent
      ? el("p", {
          class: "muted",
          // States what absent *means*, not why it is absent. "The display
          // plane has not been built yet" would have been true the day this
          // was written and wrong the day that plane ships, with nothing to
          // catch it — a page asserting a fact about the project rather than
          // reporting one about the file in front of it.
          // "for this wall", not "here". Both chunks in this wave reworded this
          // sentence and the per-wall one is the survivor: with a panel per room
          // "here" has several possible referents and names none of them, which
          // is the exact ambiguity splitting the heartbeat per wall removed.
          text: "Nothing has ever written a heartbeat for this wall. Where no display is pointed at it, that is the correct reading rather than a fault.",
        })
      : null,
    reading.reported ? el("h4", { text: "What it reported" }) : null,
    reportedFacts(reading.reported),
  ]);
}

/* Every wall's heartbeat, or the fact that the reading did not carry any.
 *
 * **The unreadable case is stated rather than thrown**, and that is the same
 * discipline the rest of this screen follows. This is the product's only
 * alerting surface: a payload it cannot read must produce a fact a curator can
 * act on, not an exception that reaches the error banner reading like the server
 * is down. The two lead to different next moves, and only one of them is true. */
function heartbeatPanels(health) {
  if (!Array.isArray(health.walls)) {
    return [
      el("div", { class: "panel" }, [
        el("h3", { text: "The walls" }),
        el("p", {
          class: "note",
          text: "This health reading carries no walls, so nothing can be said about what is showing them. That is a fault in the reading rather than in any wall.",
        }),
      ]),
    ];
  }
  if (health.walls.length === 0) {
    return [
      el("div", { class: "panel" }, [
        el("h3", { text: "The walls" }),
        el("p", { class: "note", text: "No wall is recorded, so there is no heartbeat to read." }),
      ]),
    ];
  }
  return health.walls.map(heartbeatPanel);
}

export async function viewHealth(generation) {
  const health = await api("/api/health");
  const box = health.artwork_box;
  render(
    generation,
    el("p", {}, [backLink()]),
    el("h2", { text: "Health" }),
    // The server's own summary of the readings below it. Shown as prose and
    // used for nothing else: it applies no threshold and reaches no verdict, so
    // deriving a state from it here would be inventing a judgement the plane
    // deliberately declined to make.
    health.description ? el("p", { class: "note", text: health.description }) : null,
    ...heartbeatPanels(health),
    el("div", { class: "panel" }, [
      el("h3", { text: "The backup" }),
      el("p", { text: health.backup.description }),
      facts([
        ["Backup record", health.backup.path],
        ["Last completed", health.backup.completed_at],
        ["Age", health.backup.age_seconds === null ? null : `${health.backup.age_seconds.toFixed(0)} seconds`],
        ["Problem", health.backup.problem],
      ]),
      health.backup.absent
        ? el("p", {
            class: "muted",
            // Says what the catalogue is worth and what an absent record means,
            // and deliberately stops there. "The backup job has not been built
            // yet" would be a claim about the project rather than about the file
            // in front of it, and would be wrong the day that job ships with
            // nothing to catch it — the same trap the heartbeat's note avoids.
            text: "No backup has recorded itself here. The catalogue is the irreplaceable asset — the images can all be fetched again — so this is the reading to watch.",
          })
        : null,
      health.backup.reported ? el("h4", { text: "What it recorded" }) : null,
      reportedFacts(health.backup.reported),
    ]),
    el("div", { class: "panel" }, [
      el("h3", { text: "This deployment's geometry" }),
      el("p", {
        class: "muted",
        text: "The space a work is rendered into on this television, after the mat. Every size shown in the grid is judged against it.",
      }),
      facts([
        ["Artwork box", `${box.width} × ${box.height} px`],
        ["Scale", `${box.pixels_per_inch.toFixed(1)} pixels per inch on the wall`],
        ["On the wall", `${(box.width / box.pixels_per_inch).toFixed(1)}″ × ${(box.height / box.pixels_per_inch).toFixed(1)}″`],
        ["Resolution floor", `${box.floor_inches}″ on the long edge`],
      ]),
    ]),
  );
}
