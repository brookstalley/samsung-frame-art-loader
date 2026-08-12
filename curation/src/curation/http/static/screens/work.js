/* Work — one work at full size, what it is said to be, and the two acts that
 * take it out of circulation and put it back.
 *
 * Contextual: reached from a tile in Collection, a tile on a Wall, or a row in
 * Review, and it **returns to the destination it was opened from**. That is the
 * requirement `information-architecture.md` states under Back/escape, and the
 * back control here reads it off the address rather than naming a fixed parent —
 * this screen's route out used to be "← All works" whatever route in had been
 * taken.
 *
 * **The picture comes first and the label sits under it.** The governing rule is
 * that the artwork is the primary content on every screen that shows one and
 * chrome yields to it; a title above the image puts a line of interface between
 * the reader and the thing they opened.
 *
 * **There is no delete of a work here, and there is no route that could do one.**
 * `Artwork.status` is `accepted` or `archived`, restoration is permitted, and the
 * control therefore reads *Archive* with *Restore* as its undo. A button reading
 * "Remove" would promise the work was gone while it is in fact still catalogued,
 * still in every theme that held it, and one click from being back on the wall —
 * and a curator who learns that a confirmation overstates will read the next one
 * less carefully.
 */

import { api } from "../core/api.js";
import { facts, fitBadge, sourceBadge, statusBadge, table } from "../core/badges.js";
import { confirmAct } from "../core/confirm.js";
import { el, guard, render } from "../core/render.js";
import { backLink } from "../core/router.js";

/* The typed vocabulary a work is filed under, in the words a label uses.
 *
 * The six are `VocabularyKind`, which `Affinity.kind` shares — one set of terms
 * for what a work *is*, what the curator likes, and what discovery weights. A
 * kind with no entry here falls through to its raw token, which is why a unit
 * test reads this map against the enum: a seventh kind should arrive as a
 * failing test rather than as `date_range` printed on a museum label. */
const FACET_KIND_WORDS = {
  artist: "Artist",
  movement: "Movement",
  era: "Era",
  subject: "Subject",
  medium: "Medium",
  palette: "Palette",
};

/* Stated once, below the facts it qualifies.
 *
 * **Inferred is the rule, so the exception is what gets marked.** The wired
 * collection publishes no style field and its classification and period are
 * missing on ordinary spellings, so nearly every facet here was read off the
 * work by a model. A badge on each of those is a label on almost everything,
 * which is a label nobody reads — and it buries the rare value that carries a
 * museum's own authority.
 *
 * Below rather than above, because a rule that holds for every work must not
 * outrank the facts particular to this one; a museum label puts its
 * qualifications at the foot for the same reason. */
const DERIVATION_FOOTNOTE =
  "Every value above is inferred unless it carries ✓, which marks the few a source recorded.";

/* What a restore does and, just as importantly, when.
 *
 * **The MCP surface's own sentence, deliberately.** Two surfaces stating one
 * fact in different words is how a reader learns to trust neither, and the
 * agent-facing notice for `art_catalogue(action='restore')` already says this.
 * It is here at all because restoring is as silent at the wall as archiving is:
 * nothing republishes a manifest, so a curator who restored a work and watched
 * an unchanged wall would reasonably conclude the restore had failed.
 *
 * **And it says how to cause one**, which it did not until the operator ruled
 * that a hung work may stay on the television so long as some path exists to
 * push the update. Naming *when* without naming *how* leaves the curator holding
 * a fact they cannot act on, which is this product's characteristic failure
 * wearing a longer sentence. The remedy is phrased for both surfaces because
 * both say it: a curator re-hangs from the Walls screen, an agent calls
 * `activate`, and `activate_theme` syncs unconditionally either way.
 *
 * The literal lives in `mcp/bindings.py` and is asserted into this file by
 * `tests/unit/test_client_vocabulary.py`, so the two surfaces cannot drift into
 * saying one thing in two wordings. */
const RESTORE_CONSEQUENCE =
  "It is eligible for the wall again; a theme holding it will carry it at the next manifest build. Re-hanging a wall's current theme builds one.";

function workPath(artworkId) {
  return `/api/works/${encodeURIComponent(artworkId)}`;
}

export async function viewWork(artworkId, generation) {
  paint(await api(workPath(artworkId)), generation);
}

/* Draw the whole screen from one dossier.
 *
 * Separate from the fetch because archive and restore answer with the same
 * dossier `GET /api/works/{id}` does — so the act repaints from what the server
 * actually recorded rather than from the client's opinion of what it asked for.
 *
 * `focusAction` is how the keyboard survives that repaint. The act's own button
 * is replaced by its opposite, and a screen that rebuilt itself under a focused
 * control would drop focus to `<body>`, leaving the next Tab at the top of the
 * page. This is not a poll — the accessibility rule that a poll must never move
 * focus is about paints the curator did not ask for, and this one is the direct
 * answer to a button they pressed. */
function paint(detail, generation, focusAction = false) {
  const work = detail.work;
  const image = work.image.available
    ? el("img", {
        class: "detail-image",
        src: `${workPath(work.artwork_id)}/thumbnail`,
        alt: work.artist ? `${work.title}, by ${work.artist.name}` : work.title,
      })
    : el("p", { class: "note", text: work.image.note || "No image held." });
  const action = circulationControl(work, generation);

  const panels = [
    el("p", {}, [backLink()]),
    el("div", { class: "panel" }, [
      image,
      el("div", { class: "card-footer" }, [statusBadge(work), fitBadge(work), sourceBadge(work)]),
      work.fit_note ? el("p", { class: "muted", text: work.fit_note }) : null,
    ]),
    el("div", { class: "panel" }, [
      el("h2", { text: work.title }),
      facts([
        ["Artist", work.artist ? work.artist.name : null],
        ["Nationality", work.artist ? work.artist.nationality : null],
        ["Lifespan", work.artist ? work.artist.lifespan_text : null],
        ["Date", work.date_created],
        ["Medium", work.medium],
        ["Dimensions", work.dimensions],
        ["Rights", work.rights],
        // No "Status" row, and its absence is the rule rather than an omission.
        // A screen states a fact once: the badge above the title already says
        // `archived` when that is true and says nothing when it is not, which is
        // the same inversion the derivation footnote uses. A second, plainer copy
        // three lines below would invite the reader to look for the difference
        // between them, and one of the two would eventually be the stale one.
        ["Description", work.description],
      ]),
      el("div", { class: "row" }, [action]),
    ]),
    facetPanel(detail.facets),
  ];

  panels.push(
    el("div", { class: "panel" }, [
      el("h3", { text: "The master image" }),
      detail.original
        ? facts([
            ["File", detail.original.relative_path],
            ["Pixels", `${detail.original.width} × ${detail.original.height}`],
            ["Size", `${(detail.original.byte_size / 1048576).toFixed(1)} MB`],
            ["Content hash", detail.original.content_hash],
          ])
        : el("p", { class: "muted", text: "No master image has been acquired for this work yet." }),
    ]),
  );

  panels.push(
    el("div", { class: "panel" }, [
      el("h3", { text: "Where it can be obtained" }),
      detail.sources.length
        ? table(
            "Every recorded source, the primary one first.",
            ["Provider", "Rights", "Primary", "Last fetch", "URL"],
            detail.sources.map((s) => [
              s.provider,
              s.rights_status,
              s.is_primary ? "yes" : "no",
              s.last_fetch_status,
              s.url,
            ]),
          )
        : el("p", { class: "muted", text: "No sources are recorded." }),
    ]),
  );

  panels.push(
    el("div", { class: "panel" }, [
      el("h3", { text: "What has been rendered" }),
      detail.renditions.length
        ? table(
            "A rendition is stale when the master it was made from is no longer the master this work holds.",
            ["Kind", "Target", "File", "State"],
            detail.renditions.map((r) => [
              r.kind,
              `${r.target_width} × ${r.target_height}`,
              r.relative_path,
              r.stale ? "▲ stale — needs regenerating" : "● current",
            ]),
          )
        : el("p", { class: "muted", text: "Nothing has been rendered for this work yet." }),
    ]),
  );

  panels.push(matPanel(detail.mat_colors));

  render(generation, ...panels);
  // Only if the paint actually landed. `render` declines a paint whose
  // navigation has been superseded, and focusing a control that was never put on
  // the page would move the keyboard onto a detached node.
  if (focusAction && document.contains(action)) action.focus();
}

/* What this work is said to be, in the vocabulary the collection filters by. */
function facetPanel(facets) {
  if (!facets.length) return null;
  // `facts` as well as `facets`, so it inherits the two-column grid every other
  // labelled list on this screen is drawn in — one list of facts about a work
  // should not be laid out two ways because one of them carries a mark.
  const list = el("dl", { class: "facts facets" });
  // Grouped by kind rather than one row per facet: a work with three subjects is
  // three claims of one kind, and three "Subject" terms down the left would read
  // as three different questions. Ordered by the vocabulary rather than by what
  // the store happened to return, so two works read in the same order.
  const known = Object.keys(FACET_KIND_WORDS);
  // Anything the client has no word for still goes on the page, after the six it
  // does. A kind this map has not caught up with is a fact about the work, and
  // dropping it silently is worse than printing its raw token.
  const unknown = [...new Set(facets.map((facet) => facet.kind))].filter((kind) => !(kind in FACET_KIND_WORDS));
  for (const kind of [...known, ...unknown]) {
    const held = facets.filter((facet) => facet.kind === kind);
    if (!held.length) continue;
    list.append(el("dt", { text: FACET_KIND_WORDS[kind] || kind }), el("dd", {}, facetValues(held)));
  }
  return el("div", { class: "panel" }, [
    el("h3", { text: "What this work is" }),
    list,
    el("p", { class: "note", text: DERIVATION_FOOTNOTE }),
  ]);
}

/* One kind's values, each with the mark that only the rare sourced one carries.
 *
 * A tick rather than the bordered word this was first drawn as: an annotation is
 * read after the value it qualifies and must be quieter than it, and a boxed
 * "sourced" beside a one-word value outranked its own subject. The word survives
 * for assistive technology, so neither colour nor shape is the sole carrier of a
 * distinction that decides how much authority a value has. */
function facetValues(held) {
  const nodes = [];
  for (const facet of held) {
    if (nodes.length) nodes.push(", ");
    nodes.push(el("span", { class: "facet-value", text: facet.value }));
    if (facet.derivation === "sourced") {
      nodes.push(
        el("span", { class: "sourced" }, [
          // The string, not the boolean. `el` renders a `true` as an empty
          // attribute — right for `hidden`, and wrong for an ARIA state, where
          // an empty value is invalid and falls back to *not* hidden. Every
          // other glyph in this client passes the boolean and is therefore
          // announced as "check mark sourced"; that is a one-line fix in `el`
          // and it belongs to whoever can make it without three screens being
          // rebuilt around it at the same time.
          el("span", { class: "tick", text: "✓", "aria-hidden": "true" }),
          el("span", { class: "visually-hidden", text: "sourced" }),
        ]),
      );
    }
  }
  return nodes;
}

/* The mat shows its colour and nothing else.
 *
 * `MatColor` keeps the method, the model and the date it was derived, and must —
 * that record is what makes "the new model picked a worse colour" answerable and
 * reversible, and what makes the engine's silent fallback to a darkened dominant
 * colour visible at all. But that is a diagnostic question asked rarely, and the
 * superseded-choices table that stood here put the audit trail where the label
 * goes. **Nothing about this reduces what is stored.** */
function matPanel(matColors) {
  const current = matColors.find((mat) => mat.is_current);
  return el("div", { class: "panel" }, [
    el("h3", { text: "Mat colour" }),
    current
      ? el("p", { class: "mat" }, [
          // The swatch is the only place in this client that puts data in a style
          // attribute, and it is safe because the catalogue refuses a mat colour
          // that is not `#rrggbb` on the way in. The hex is printed beside it, so
          // the colour is never the sole carrier.
          el("span", { class: "mat-swatch", style: `background: ${current.hex_rgb}` }),
          el("span", { text: current.hex_rgb }),
        ])
      : el("p", { class: "muted", text: "No mat colour has been chosen for this work." }),
  ]);
}

/* Archive, or Restore — whichever this work's status leaves available.
 *
 * One control rather than two, because the two acts are the two directions of
 * one state machine and offering the unavailable one would be offering a
 * refusal. `.action`, not `.quiet` and not anything alarming: this is an
 * ordinary reversible act, and there is no danger class in this stylesheet to
 * reach for. */
function circulationControl(work, generation) {
  const archived = work.status !== "accepted";
  return el("button", {
    class: "action",
    type: "button",
    text: archived ? "Restore" : "Archive",
    onclick: () => guard(() => (archived ? restore(work, generation) : archive(work, generation))),
  });
}

async function archive(work, generation) {
  const agreed = await confirmAct({
    title: `Archive ${work.title}?`,
    consequence: wallConsequence(await wallsShowing(work.artwork_id)),
    confirmLabel: "Archive",
  });
  if (!agreed) return;
  paint(await api(`${workPath(work.artwork_id)}/archive`, { method: "POST" }), generation, true);
}

async function restore(work, generation) {
  const agreed = await confirmAct({
    title: `Restore ${work.title}?`,
    consequence: RESTORE_CONSEQUENCE,
    confirmLabel: "Restore",
  });
  if (!agreed) return;
  paint(await api(`${workPath(work.artwork_id)}/restore`, { method: "POST" }), generation, true);
}

/* Which walls are showing this work, asked of the walls themselves.
 *
 * **Evaluated, never predicted.** `GET /api/manifest` builds a wall's manifest
 * without writing it, applying the same five exclusion rules the real build
 * applies — so a work that is in a hung theme but has no rendition is in that
 * wall's *exclusions* and not on its wall, and archiving it costs that room
 * nothing. A client that answered this from theme membership would name a wall
 * that was never showing the picture, which is a confirmation teaching the
 * curator that its sentences are guesses.
 *
 * **Per wall, because the manifest is per wall.** Two rooms hang different
 * themes and are asked separately. A wall with nothing hanging is not asked at
 * all — the route refuses one, and correctly: there is no theme to evaluate, and
 * a room showing nothing cannot lose a picture.
 *
 * The same two-request shape the Walls screen uses. It is written here rather
 * than shared because a `core/` module is what two callers earn, and these two
 * want different answers out of the same reads — that screen renders every
 * manifest, this one asks a single yes-or-no of each. */
async function wallsShowing(artworkId) {
  const walls = await api("/api/walls");
  const hung = walls.walls.filter((wall) => wall.theme);
  const builds = await Promise.all(
    hung.map(async (wall) => [wall, await api(`/api/manifest?wall_id=${encodeURIComponent(wall.wall_id)}`)]),
  );
  return builds
    .filter(([, manifest]) => manifest.entries.some((entry) => entry.artwork_id === artworkId))
    .map(([wall]) => wall.name);
}

/* The sentence that names which walls lose the picture, or no sentence at all.
 *
 * **The empty string is a real answer and not a degenerate one.** `confirmAct`
 * renders no description element for it, which is the difference between a
 * confirmation that says nothing about the wall because there is nothing to say
 * and one that says nothing because it never looked.
 *
 * **It says when, because nothing here republishes a manifest.** Archiving
 * changes the catalogue; the wall goes on showing the file it was last given
 * until that wall's manifest is next built. "Takes it off the wall" would be the
 * more satisfying sentence and would be a promise this product does not keep.
 *
 * **And it says how**, for the reason `RESTORE_CONSEQUENCE` records: the
 * operator's ruling that the picture may stay up rests on a path existing to
 * push the update, and a curator who is not told the path does not have one. The
 * remedy is worded to survive more than one wall — these names can be walls
 * hanging *different* themes, so it cannot say "that theme". */
function wallConsequence(names) {
  if (!names.length) return "";
  const walls = names.length === 1 ? names[0] : `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
  const showing = names.length === 1 ? "is showing" : "are showing";
  const losing = names.length === 1 ? "loses" : "lose";
  return `${walls} ${showing} this work, and ${losing} it at the next manifest build. Re-hanging a wall's current theme builds one. It stays in the theme, and Restore brings it back.`;
}
