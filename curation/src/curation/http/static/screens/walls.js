/* The Walls — what is hanging right now, on each wall.
 *
 * The product's home, and the first of the three destinations.
 * `information-architecture.md` argues the case and records the counter-argument:
 * most sessions begin with an intention, so opening on a screen of pictures puts
 * a click in front of them. The answer is that this screen carries the live entry
 * points rather than being a dead end, and that the product's identity claim is
 * that it is a collection rather than a tool.
 *
 * **One wall is the degenerate case of many, never a special case.** There is one
 * section per wall and no single-wall layout for a second display to replace: with
 * one wall this is one section filling the screen and reads exactly as a
 * single-wall home would, and with three it is three of the same thing.
 *
 * **Every act here names its wall, in the control and in the confirmation.** Not
 * "Hang Winter" but "Hang Winter on the living room", and not "Next" but "Move
 * the living room on to the next work" — even while there is one wall and the
 * answer is obvious. A sentence that reads correctly today only because there is
 * one possible target is a sentence that silently becomes wrong.
 *
 * **Nothing on the wall has four named reasons, and they are four branches.** No
 * theme hung, an empty theme, a display plane that has never spoken, and a plane
 * this screen could not reach at all. Each states its own sentence and offers the
 * fix for that reason specifically, because the four lead to four different next
 * moves — one is "choose a theme", one is "put works in the theme you chose", one
 * is "go and look at the appliance", and one is "ask again". A single "nothing is
 * showing" would be true in all four cases and useful in none.
 *
 * The fourth is reached differently from the other three, and that shows in the
 * shape below: the first three are read off responses that *arrived*, and the
 * fourth is a request that did not. That is why it is the one whose sentence
 * names which of the two planes answered.
 *
 * **This screen does not poll**, and that is `core/status.js`'s decision applied
 * here rather than a gap. Mean time to detection on this surface is bounded by
 * how often the curator opens the page, repainting on every navigation is what
 * that bound already costs, and a background timer would add load to a Pi without
 * changing it. Should one ever be added it repaints through `refresh()` with no
 * argument: `refresh(true)` moves focus, and a poll that moves focus is the
 * recorded defect this client already shipped once, on the one screen with a
 * decision on it. This screen has a decision on it.
 */

import { api } from "../core/api.js";
import { absentImage, facts, table } from "../core/badges.js";
import { hangTheme } from "../core/hanging.js";
import { el, guard, render } from "../core/render.js";
import { go, refresh } from "../core/router.js";

export async function viewWalls(generation) {
  let walls;
  let themes;
  try {
    // The themes come along because hanging is an act against a named wall and
    // the theme control lives on this screen: a picker that had to be fetched
    // when it was opened would be a control that is not there when the curator
    // reaches for it.
    [walls, themes] = await Promise.all([api("/api/walls"), api("/api/themes")]);
  } catch (failure) {
    // The fourth reason, at the only scale it can be stated at when this is what
    // failed: with no wall list there is no wall to say it about.
    render(
      generation,
      heading(),
      ...unreachable(
        `The curation plane did not answer — ${failure.message} — so nothing can be said about any wall. The display plane was not asked.`,
      ),
    );
    return;
  }

  const beats = await heartbeats();
  const builds = await Promise.all(walls.walls.map(built));

  if (!walls.walls.length) {
    // Not one of the four, and stated rather than left as an empty page: a wall
    // is recorded when the plane first opens the catalogue, so none at all is a
    // fact about the deployment rather than about anybody's curation.
    render(
      generation,
      heading(),
      el("p", {
        class: "note",
        text: "No wall is recorded, so there is nowhere to hang anything. A wall is created when the plane first opens the catalogue.",
      }),
    );
    return;
  }

  const sections = walls.walls.map((wall, index) => wallSection(wall, builds[index], beats, themes.themes));
  render(generation, heading(), ...sections, walls.walls.some((wall) => !wall.theme) ? takeDownNote() : null);
}

/* The one heading on this surface set at `--text-3xl`, and the token's only use.
 * `design-direction.md` adds it "for the Walls screen's single large heading",
 * which is this one: the product's home saying so, at a size nothing else on the
 * client reaches. */
function heading() {
  return el("h2", { class: "walls-heading", text: "The Walls" });
}

/* The fact the MCP surface already states after an unhang, said here too: taking
 * a theme down rewrites no manifest, so the set goes on showing the picture. A
 * curator who read only "nothing is hanging" would take a successful take-down
 * for a failed one — the same inference `activate_theme`'s docstring cites when
 * it argues that hanging must publish immediately.
 *
 * Once, under every section, rather than once per wall: it is one fact about how
 * taking down works, not a property of any particular wall, and three empty rooms
 * would otherwise print it three times. `information-architecture.md` states the
 * general form — a qualifier that applies to every row is a footnote under the
 * block rather than a mark on each row. */
function takeDownNote() {
  return el("p", { class: "note", text: "A wall goes on showing what it was showing until a theme is hung." });
}

/* Every wall's last observation, or the fact that the reading did not arrive.
 *
 * Caught here rather than left to `guard`, for `core/status.js`'s reason: a
 * health read that failed is not a refusal of anything the curator did, and
 * putting it in the page's error banner would report it as one. It is a fact
 * about what this screen can say, and it belongs in the wall it cannot speak for.
 */
async function heartbeats() {
  try {
    const health = await api("/api/health");
    // `walls` absent or the wrong shape leaves every wall with no reading, which
    // lands in the silent branch rather than in a green one. A wall reported as
    // well because its observation could not be found is precisely the failure
    // this product exists to refuse.
    const readings = Array.isArray(health.walls) ? health.walls : [];
    return { byWall: new Map(readings.map((reading) => [reading.wall_id, reading.heartbeat])) };
  } catch (failure) {
    return { failure: failure.message };
  }
}

/* What a theme is putting on one wall, or why that could not be asked.
 *
 * A wall with nothing hanging is asked nothing — the route would refuse, and
 * correctly, because there is no theme to evaluate. */
async function built(wall) {
  if (!wall.theme) return {};
  try {
    return { manifest: await api(`/api/manifest?wall_id=${encodeURIComponent(wall.wall_id)}`) };
  } catch (failure) {
    return { failure: failure.message };
  }
}

/* Which of the four reasons this wall is showing nothing for, or that it is not.
 *
 * **Ordered by what the curator would do about it**, which is the whole point of
 * naming them apart. A wall with no theme is told to hang one whatever the
 * display plane is doing; a theme holding no works is told to fill it. Only once
 * a populated theme is published does whether anything is actually on the wall
 * become a question about the appliance.
 *
 * **`entries.length === 0` with `considered` above zero is deliberately not a
 * fifth reason.** That is a theme whose works were all excluded, and the "Not
 * showing" panel below answers it per work and by name — which is a better answer
 * than any single sentence here could give. */
function reasonFor(wall, build, beats) {
  if (!wall.theme) return "no-theme";
  if (build.failure) return "unreachable";
  if (build.manifest.considered === 0) return "empty-theme";
  if (beats.failure) return "unreachable";
  const beat = beats.byWall.get(wall.wall_id);
  if (!beat || beat.absent || beat.problem) return "silent";
  return "hanging";
}

function wallSection(wall, build, beats, themes) {
  const manifest = build.manifest;
  const reason = reasonFor(wall, build, beats);
  return el("section", { class: "wall" }, [
    // `h3` for the wall and `h4` for its panels, so the nesting survives a second
    // wall: with two walls hung, sibling `h3`s would give a reader navigating by
    // heading six headings in a row and no signal for which counts belong to
    // which room. The single-wall view read correctly by accident, having only
    // one room's worth of headings to confuse.
    el("h3", { class: "wall-title", text: manifest ? `${wall.name}: ${manifest.theme.name}` : wall.name }),
    // The server's own sentence about how much of the theme reached the wall,
    // and not repeated when a reason below is about to say the same thing in
    // more useful words: a screen states a fact once, and two copies of one fact
    // invite the reader to look for the difference between them.
    manifest && reason !== "empty-theme" ? el("p", { class: "note", text: manifest.summary }) : null,
    ...emptiness(reason, wall, build, beats),
    controls(wall, themes, reason, manifest),
    ...(manifest ? manifestPanels(manifest) : []),
  ]);
}

/* The four reasons, dispatched. Each is its own function below, and that is not
 * decoration: they are four branches with four texts and four fixes, and a
 * dispatch that fell through to a shared sentence would be the single "nothing is
 * showing" this screen exists not to say. */
function emptiness(reason, wall, build, beats) {
  if (reason === "no-theme") return noThemeHung(wall);
  if (reason === "empty-theme") return emptyTheme(wall, build.manifest);
  if (reason === "silent") return planeSilent(wall, beats.byWall.get(wall.wall_id));
  if (reason === "unreachable") return unreachable(cannotReach(wall, build, beats));
  return [];
}

/* Reason one: no theme has been hung here.
 *
 * The fix is the theme control in this wall's own section, a few lines below —
 * so the sentence points at it rather than sending the curator to another screen
 * for the one act this screen is named for. */
function noThemeHung(wall) {
  return [
    el("p", {
      class: "muted",
      text: `Nothing is hanging on ${wall.name}. Choose a theme below and hang it there.`,
    }),
  ];
}

/* Reason two: a theme is hung and holds no works.
 *
 * A different state from "the theme's works were all excluded", and the fix is
 * different too: there is nothing to exclude, and nothing to diagnose. */
function emptyTheme(wall, manifest) {
  return [
    el("p", {
      class: "note",
      text: `${manifest.theme.name} holds no works yet, so nothing is on ${wall.name}.`,
    }),
    el("div", { class: "row" }, [
      el("button", {
        class: "action quiet",
        type: "button",
        text: `Add works to ${manifest.theme.name}`,
        onclick: () => go("theme"),
      }),
    ]),
  ];
}

/* Reason three: this plane published, and no display has said anything back.
 *
 * **A reading that arrived**, which is what separates this from reason four: the
 * curation plane answered, and what it answered with is that the display plane
 * has not spoken. Both an absent heartbeat and one that cannot be read land here
 * — a corrupt report is still the display plane failing to speak, the wall is
 * equally dark either way, and the fix is the same: go and read the observation
 * in full. What differs is the sentence, because "nothing has ever been written"
 * and "something was written and cannot be parsed" send an operator to different
 * places on the appliance. */
function planeSilent(wall, beat) {
  return [
    el("p", { class: "note", text: silence(wall, beat) }),
    el("div", { class: "row" }, [
      el("button", {
        class: "action quiet",
        type: "button",
        text: `Open the reading for ${wall.name}`,
        onclick: () => go("health"),
      }),
    ]),
  ];
}

function silence(wall, beat) {
  if (!beat) {
    return `The health reading carries no heartbeat for ${wall.name}, so nothing here can say whether a display is serving it.`;
  }
  if (beat.problem) {
    return `${wall.name}'s heartbeat cannot be read: ${beat.problem}. What is published below is what a display would pick up, and nothing confirms one has.`;
  }
  return `No display has ever reported for ${wall.name}. What is published below is waiting to be picked up; until something reports, nothing here can say the wall is showing it.`;
}

/* Reason four: a plane could not be reached, and the sentence says which one did
 * answer.
 *
 * The only fix that can be offered is to ask again, and it is offered rather than
 * left to the curator to work out that reloading is a thing they may do. A link
 * to the health screen would be worse than nothing here: the reading it shows is
 * the one that could not be fetched. */
function unreachable(words) {
  return [
    el("p", { class: "note", text: words }),
    el("div", { class: "row" }, [
      el("button", {
        class: "action quiet",
        type: "button",
        text: "Ask again",
        // No argument, so the repaint does not move focus. See the file header.
        onclick: () => guard(() => refresh()),
      }),
    ]),
  ];
}

function cannotReach(wall, build, beats) {
  if (build.failure) {
    return `The curation plane answered for the walls and refused ${wall.name}'s build — ${build.failure} — so nothing here can say what is on this wall. The display plane was not asked.`;
  }
  return `The curation plane answered for ${wall.name}, and the reading that speaks for the display plane did not — ${beats.failure} — so nothing here can say whether anything is on the wall.`;
}

/* Change the theme, and move on to the next work: this screen's two acts.
 *
 * **A picker rather than a button per theme**, which is the opposite of the
 * choice `screens/theme.js` makes for walls, and for the reason stated there: a
 * button per target suits a small set, and the themes are the side that grows. It
 * carries the wall's name on its label as well as on the button, so a curator
 * tabbing into the control knows which room it belongs to without reading upward.
 *
 * **No take-down control here, deliberately.** The IA's action list for this
 * screen is change theme, next, and open work; taking down lives on the theme,
 * where it exists to make a theme deletable. It would also read wrong here: a
 * take-down rewrites no manifest, so pressing it on the screen whose whole job is
 * to say what is on the wall would leave the section reading "nothing is hanging"
 * while the television went on showing the pictures. Changing the theme is the
 * act on this screen that actually changes the wall. */
function controls(wall, themes, reason, manifest) {
  if (!themes.length) {
    return el("div", { class: "row wall-controls" }, [
      el("p", { class: "muted", text: "No theme has been created yet, so there is nothing to hang here." }),
      el("button", { class: "action", type: "button", text: "Create a theme", onclick: () => go("theme") }),
    ]);
  }

  const pickerId = `hang-${wall.wall_id}`;
  const picker = el("select", { id: pickerId });
  for (const placement of themes) {
    picker.append(el("option", { value: placement.theme.theme_id, text: placement.theme.name }));
  }

  return el("div", { class: "row wall-controls" }, [
    el("div", { class: "field" }, [
      el("label", { for: pickerId, text: `Theme for ${wall.name}` }),
      picker,
    ]),
    el("button", {
      class: "action",
      type: "button",
      text: `Hang on ${wall.name}`,
      onclick: () => guard(() => hang(wall, themes, picker.value)),
    }),
    // Only where something is actually up. Stepping a wall that is showing
    // nothing writes a directive nobody can act on, and offering it would say
    // this screen thinks there is something to move on from.
    //
    // **Both halves are load-bearing, and the second was the bug.** The reason
    // answers whether a display has spoken for this wall; the manifest answers
    // whether there is anything for a step to advance through. A theme whose
    // works were *all* excluded is not one of the four reasons — `considered`
    // counts entries plus exclusions, so it reads as hanging — and it published
    // an empty rotation. Gating on the reason alone put this button beside
    // "Nothing in this theme is currently displayable", which is precisely the
    // case the sentence above rules out.
    reason === "hanging" && manifest.entries.length ? nextButton(wall) : null,
  ]);
}

/* Hanging: the one act in this product that changes what other people in the
 * house see, and the reason this screen has a confirmation at all.
 *
 * **The consequence is evaluated, not predicted.** `GET /api/manifest` takes a
 * theme and answers what it would put on this wall without writing anything, so
 * the sentence in the dialog is the build's own summary rather than a guess
 * composed here — including the case where the answer is "this theme holds no
 * works yet", which is exactly the thing a curator would want to be told before
 * pressing the button rather than after.
 *
 * **The wall repaints from the published manifest rather than from optimism.**
 * The refresh after the write re-reads everything; nothing here assumes the
 * activation put up what the preview said it would. */
/* Repaints in place, because the result of this act is on this screen. The
 * question, the preview and the request are `core/hanging.js`'s — the Theme
 * screen asks the same one, and one act must not have two wordings. */
function hang(wall, themes, themeId) {
  const chosen = themes.find((placement) => placement.theme.theme_id === themeId);
  return hangTheme({ themeId, themeName: chosen.theme.name, wall, then: refresh });
}

/* Moving one wall on, and only that wall.
 *
 * **Unconfirmed, and that is a decision rather than an oversight.** Flow 6 names
 * activation as the one act that gets a confirmation, and it is the one that
 * replaces everything on a wall. A step advances by one work in a rotation that
 * was going to advance by itself anyway, and is undone by pressing it again. A
 * dialog in front of it would teach the curator to dismiss dialogs. */
function nextButton(wall) {
  return el("button", {
    class: "action quiet",
    type: "button",
    text: `Move ${wall.name} on to the next work`,
    onclick: () =>
      guard(async () => {
        await api("/api/directives", {
          method: "POST",
          body: JSON.stringify({ wall_id: wall.wall_id }),
        });
        await refresh();
      }),
  });
}

function manifestPanels(manifest) {
  return [
    el("div", { class: "panel" }, [
      el("h4", { text: `Showing (${manifest.entries.length})` }),
      // The pictures, not a list of paths. The artwork is the primary content on
      // every screen that shows one, and this is the screen the product exists
      // to produce — a table of render paths under this heading was an inventory
      // of the wall rather than a view of it.
      manifest.entries.length
        ? el("ul", { class: "hanging" }, manifest.entries.map(hungWork))
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

/* One work as it hangs: the picture, then its label.
 *
 * The image carries the work and its artist in its `alt`, because here the image
 * is the content rather than a thumbnail beside it — `accessibility-spec.md` is
 * explicit that there is no third state. That is also why it is not wrapped in a
 * button: an `aria-label` on the button would replace the alt text entirely, and
 * the picture would be announced as "Open Nighthawks" and nothing about what it
 * is. The title below is the control instead. */
function hungWork(entry) {
  const image = el("img", {
    src: `/api/works/${encodeURIComponent(entry.artwork_id)}/thumbnail`,
    alt: entry.artist ? `${entry.title}, ${entry.artist}` : entry.title,
    loading: "lazy",
  });
  // A file can go away between the manifest being built and this fetch. Without
  // this the tile renders as a blank box — silent, which is the failure mode this
  // whole product exists to refuse.
  image.addEventListener("error", () => {
    image.replaceWith(absentImage("Its image could not be loaded just now."));
  });
  return el("li", { class: "hung" }, [
    el("div", { class: "card-image" }, [image]),
    // `h5`, a rank below the panel's `h4`, so a reader navigating by heading gets
    // the works nested inside the wall's Showing section rather than beside it.
    el("h5", { class: "card-title" }, [
      el("button", { type: "button", text: entry.title, onclick: () => go("work", entry.artwork_id) }),
    ]),
    el("p", { class: "card-artist", text: entry.artist || "Artist unrecorded" }),
  ]);
}
