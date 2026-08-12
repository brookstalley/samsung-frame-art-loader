/* The pieces more than one screen draws: badges, fact lists, tables, notes.
 *
 * The rule for what belongs here is exactly "two screens use it". A presenter
 * with one caller stays in that caller's module, because a `core/` that collects
 * everything shared-looking becomes the single file the split exists to end.
 *
 * **A badge always carries a glyph and a word beside its colour**, so every
 * state survives greyscale, colour blindness, and a dimmed room —
 * `accessibility-spec.md`'s rule that colour is never the sole carrier.
 */

import { el } from "./render.js";

const FIT_GLYPHS = {
  native: "●", // filled circle
  matted_small: "◇", // open diamond
  below_floor: "▲", // triangle
};

const FIT_WORDS = {
  native: "native",
  matted_small: "matted small",
  below_floor: "below floor",
};

/* How large this would hang, or why that cannot be said.
 *
 * One function for a held work and for a candidate scan. Both carry the same
 * `fit`/`fit_note` pair and the same rule — a thing whose dimensions nobody
 * recorded must not read like a thing known to be small — so the only real
 * difference is what to call the absence, and that is the argument. Two copies
 * were written first, and their comment claimed "same rule, different shape"
 * when the shapes were identical; the size wording then lived in two places on
 * the one surface whose whole justification is stating it. */
export function fitBadge(sized, absentWord = "no size known") {
  if (!sized.fit) {
    return el("span", { class: "badge badge-unknown", title: sized.fit_note || "" }, [
      el("span", { class: "glyph", text: "—", "aria-hidden": true }),
      el("span", { text: absentWord }),
    ]);
  }
  const verdict = sized.fit.verdict;
  const inches = sized.fit.rendered_long_edge_inches.toFixed(1);
  return el("span", { class: `badge badge-${verdict}` }, [
    el("span", { class: "glyph", text: FIT_GLYPHS[verdict] || "●", "aria-hidden": true }),
    // The number is the point: a thumbnail cannot convey resolution, so the size
    // it would actually appear at on the wall is what a curator judges.
    el("span", { text: `${FIT_WORDS[verdict] || verdict} — would show at ${inches}″` }),
  ]);
}

export function sourceBadge(work) {
  if (!work.image.available) return null;
  const rendered = work.image.source_kind === "tv_display";
  return el("span", { class: "badge" }, [
    el("span", { class: "glyph", text: rendered ? "▣" : "□", "aria-hidden": true }),
    el("span", { text: rendered ? "wall render" : "master image" }),
  ]);
}

/* Shown only when a work is out of circulation. An archived work is still
 * listed — the catalogue lists accepted and archived together, because that is
 * what "everything we hold" means — and with no badge it looks exactly like a
 * work that is on the wall. */
export function statusBadge(work) {
  if (work.status === "accepted") return null;
  // Its own class, not `below_floor`'s: catalogue status and display fit are
  // unrelated axes, and sharing a class would make an archived work and a
  // too-small work paint identically.
  return el("span", { class: "badge badge-archived" }, [
    el("span", { class: "glyph", text: "⊘", "aria-hidden": true }),
    el("span", { text: work.status }),
  ]);
}

export function absentImage(note) {
  return el("div", { class: "card-image-absent", text: note || "No image held." });
}

export function facts(pairs) {
  const list = el("dl", { class: "facts" });
  for (const [term, value] of pairs) {
    if (value === null || value === undefined || value === "") continue;
    list.append(el("dt", { text: term }), el("dd", { text: String(value) }));
  }
  return list;
}

export function table(caption, headers, rows) {
  return el("table", {}, [
    el("caption", { text: caption }),
    el("thead", {}, [el("tr", {}, headers.map((h) => el("th", { scope: "col", text: h })))]),
    el("tbody", {}, rows.map((cells) => el("tr", {}, cells.map((c) => (c instanceof Node ? el("td", {}, [c]) : el("td", { text: c === null || c === undefined ? "—" : String(c) }))))),
    ),
  ]);
}

/* Only ever shown when the runaway guard actually bit. Named rather than
 * silent: a list that stops short without saying so is indistinguishable from a
 * catalogue that holds no more. */
export function shortfallNote(page) {
  if (page.works.length >= page.total) return null;
  return el("p", {
    class: "note",
    text: `Showing ${page.works.length} of ${page.total}; ${page.total - page.works.length} more are held and are not on this page.`,
  });
}

/* Which kind of nothing an unresolved work came back with, in words a curator
 * acts on. The enum values are diagnostic labels; only one of them ("not held")
 * suggests the work may not exist, and a screen showing the raw value leaves
 * that distinction to be guessed.
 *
 * Every member of UnresolvedReason must appear here — a test reads this map and
 * the enum and fails when they disagree, so a sixth reason arrives as a failure
 * rather than as a raw token on a card. */
export const REASON_SENTENCES = {
  not_held: "No wired collection holds it — this is the one reason that suggests the work may not exist.",
  identity_refused: "Something was found under this title, but its artist did not match, so it was refused.",
  size_unknown: "A scan was found, but nothing said how large it is, so it could not be judged.",
  below_floor: "Every scan found is too small to show on this wall at a size worth looking at.",
  all_rejected: "You have turned down everything that was found for it.",
};

const REASON_WORDS = {
  not_held: "not held",
  identity_refused: "wrong artist",
  size_unknown: "size unknown",
  below_floor: "too small",
  all_rejected: "all turned down",
};

export function reasonBadge(work) {
  if (!work.unresolved_reason) return null;
  const value = work.unresolved_reason;
  return el("span", { class: "badge badge-unknown", title: REASON_SENTENCES[value] || "" }, [
    el("span", { class: "glyph", text: "▲", "aria-hidden": true }),
    el("span", { text: REASON_WORDS[value] || value }),
  ]);
}

const RESOLUTION_GLYPHS = { resolved: "●", unresolved: "▲", pending: "◌" };

/* What `resolution_status` says, in the tense it actually holds.
 *
 * **The column describes the RUN's outcome, not the card's current state**, and
 * these words now say so. That is the answer to "does this badge describe the run
 * or the card", and it is written here rather than only in a decision record
 * because the words are the whole of the fix.
 *
 * They used to read "has an image" — present tense, a claim about the work right
 * now — beside a card that could also read "You have turned down everything that
 * was found for it." Each true, together contradictory: only a resolution
 * *attempt* recomputes this column, so turning down the last surviving instance
 * leaves it reading `resolved` until the next re-search.
 *
 * The rejection model is deliberate and settled — `discovery.reject_image` does
 * not rewrite `resolution_status`, and `_accept` asks the images rather than this
 * column for exactly that reason. So the column was right and the wording was
 * wrong, and rewording is what makes the two parts of that card consistent.
 *
 * **Chosen over deriving the badge from surviving instances**, which was the
 * other real option. That would have made the badge mean *the card's* state on
 * the review grid while the run table — whose rows carry no instance data — went
 * on meaning the run's, so one badge would have said two things on two screens.
 * These words mean the same on the grid, in the run table, and beside the raw
 * `resolution_status` an agent reads over MCP. */
const RESOLUTION_WORDS = {
  resolved: "the run found an image",
  unresolved: "the run found none",
  pending: "not looked up",
};

export function resolutionBadge(work) {
  const status = work.resolution_status;
  return el("span", { class: `badge badge-${status}` }, [
    el("span", { class: "glyph", text: RESOLUTION_GLYPHS[status] || "●", "aria-hidden": true }),
    el("span", { text: RESOLUTION_WORDS[status] || status }),
  ]);
}
