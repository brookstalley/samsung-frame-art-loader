/* The masthead status indicator — always present, and never silent.
 *
 * **This is the contract that makes demoting Health safe.**
 * `information-architecture.md` § Navigation Structure takes Health out of the
 * navigation, on the stated grounds that an appliance-status panel must not sit
 * at the same rank as the art — and it says in as many words that the demotion
 * is safe "only because the indicator is always present and speaks up". A silent
 * indicator is worse than the tab it replaced: the tab at least admitted you had
 * to go and look.
 *
 * **It states no verdict of its own, and compares no age to a threshold.**
 * `services/health.py` is emphatic about why: six days is alarming for a nightly
 * job and unremarkable for a destination that is usually asleep, and nothing
 * here knows which deployment it is on. The same argument runs per wall — four
 * minutes is late for a television that should be showing something and correct
 * for one switched off on purpose, and the curation plane does not know which.
 * So this reads only the two facts each observation already records — that a
 * file could not be read (`problem`), and that nothing has ever written one
 * (`absent`) — and names them. "Well" means "no observation reports either",
 * which is a statement about the observations rather than a claim about the
 * appliance.
 *
 * **`description` is not read here, deliberately.** The aggregate carries a
 * summary sentence composed by the server, and it is a summary of the readings
 * beside it rather than a fourth signal: it applies no threshold and uses no
 * verdict word, so a client deriving a colour by looking for one would be
 * inventing a judgement out of prose. The state comes from the readings.
 *
 * **It does not poll**, and that is the same decision the health panel already
 * made: this surface is the product's only alerting mechanism and its mean time
 * to detection is bounded by how often the curator opens the page. Repainting on
 * every navigation is what that bound already costs; a background timer would
 * add load to a Pi without changing it.
 *
 * **It names which wall.** That is the whole reason the heartbeat became one
 * reading per wall: a single observation for an installation with two rooms
 * cannot say which room went quiet, and "something is wrong somewhere" is a
 * sentence a curator cannot act on.
 *
 * A reading it cannot find is never treated as a reading that was fine. A green
 * dot computed from nothing is precisely the failure this product exists to
 * refuse, and it is the failure mode a shape change produces — so an aggregate
 * whose parts are missing makes the indicator say so out loud.
 */

import { api } from "./api.js";
import { el } from "./render.js";
import { go } from "./router.js";

export function statusReading(health) {
  if (!health) {
    return { well: false, words: "The health reading could not be fetched" };
  }
  const troubles = [];

  // Per wall, in the order `GET /api/walls` gives them, so no surface holds a
  // second ordering of the same list.
  if (!Array.isArray(health.walls)) {
    troubles.push("The health reading carries no walls");
  } else if (health.walls.length === 0) {
    // A wall is created when the plane first opens the catalogue, so none is a
    // state worth saying out loud rather than reporting as well: nothing can be
    // shown at all, and no heartbeat is missing to say so.
    troubles.push("No wall is recorded");
  } else {
    for (const wall of health.walls) {
      // Named, because a wall with no name is still a wall that has gone quiet,
      // and dropping it would make the indicator silent about exactly one room.
      const name = wall.wall_name || "An unnamed wall";
      const reading = wall.heartbeat;
      if (!reading) troubles.push(`${name} carries no heartbeat`);
      else if (reading.problem) troubles.push(`${name}'s heartbeat cannot be read`);
      else if (reading.absent) troubles.push(`${name} has not reported`);
    }
  }

  const backup = health.backup;
  if (!backup) troubles.push("The health reading carries no backup");
  else if (backup.problem) troubles.push("The backup record cannot be read");
  else if (backup.absent) troubles.push("The catalogue has never been backed up");

  if (!troubles.length) return { well: true, words: "Well" };
  return { well: false, words: troubles.join(" · ") };
}

/* Glyph as well as colour, and the word as well as the glyph — the same rule
 * every badge on this surface follows, on the one element that is on every
 * screen. `data-state` is what the stylesheet colours from, so the colour is a
 * third carrier rather than the only one. */
function paint(reading) {
  const indicator = document.getElementById("status");
  indicator.dataset.state = reading.well ? "well" : "unwell";
  indicator.replaceChildren(
    el("span", { class: "glyph", text: reading.well ? "●" : "▲", "aria-hidden": true }),
    el("span", { text: reading.words }),
  );
}

/* Read the panel and say what it said.
 *
 * The failure is caught here rather than left to `guard`, and the difference
 * matters: `guard` writes to the page's error banner, and a health check that
 * could not run is not a refusal of whatever the curator just did. It is a fact
 * about the indicator, and it belongs in the indicator. */
export async function paintStatus() {
  let health = null;
  try {
    health = await api("/api/health");
  } catch (failure) {
    paint({ well: false, words: `The health reading could not be fetched: ${failure.message}` });
    return;
  }
  paint(statusReading(health));
}

export function installStatus() {
  document.getElementById("status").addEventListener("click", () => go("health"));
}
