/* The three reactions, and the one call that records any of them.
 *
 * **In `core/` because two screens perform the identical act.** A curator
 * reacting to a sample in a conversation and a curator correcting a row on the
 * Taste screen are writing the same judgment about the same thing, and a copy of
 * this table in each would be two products: a "not this" that means one thing in
 * a thread and something else on the screen listing what the thread produced is
 * a taste model nobody can predict. `screens/` modules never import each other
 * (`architecture.md` § Components & Responsibilities), so shared vocabulary
 * lives here or it lives twice.
 *
 * **This is where the two-fields rule is paid for.** "Tell me more" is not a
 * third warmth — it is `cool` with `open_to_more` still true, which is the
 * curator's own "meh on Magritte, but open to learning more". A single warmth
 * score would render that as a low number indistinguishable from "never show me
 * this again", and the honest lukewarm reaction would silently blacklist an
 * artist they explicitly asked to keep hearing about. Declining is the only one
 * of the three that closes the door.
 */

import { api } from "./api.js";

/* Each reaction as the pair of fields it writes.
 *
 * Keyed by the words the interface uses, so the control's label and the judgment
 * it records cannot come apart. A fourth reaction is an entry here and a button
 * wherever the three are drawn — never a fourth spelling of one of these. */
export const REACTIONS = {
  "more like this": { sentiment: "loves", open_to_more: true },
  "not this": { sentiment: "declines", open_to_more: false },
  "tell me more": { sentiment: "cool", open_to_more: true },
};

/* Record one reaction against one thing, as the curator's own words.
 *
 * **Always `stated`, whoever is reacting and whatever the row said before.** A
 * reaction is the curator saying so directly — that is the whole reason the
 * controls exist rather than leaving the model to infer taste from prose — and
 * writing it as anything weaker would let the product go on attributing to a
 * model a judgment the person made by hand.
 *
 * `sourceTurnId` is passed where there is one, and its absence is not a defect:
 * a correction made on the Taste screen has no turn behind it, and `stated`
 * needs none because the curator's own words are the whole provenance.
 *
 * An upsert on (`kind`, `value`), so there is nothing to fetch first and
 * pressing a reaction twice records one judgment. */
export function recordReaction({ kind, value, reaction, sourceTurnId = null }) {
  return api("/api/affinities", {
    method: "POST",
    body: JSON.stringify({
      kind,
      value,
      derivation: "stated",
      source_turn_id: sourceTurnId,
      ...REACTIONS[reaction],
    }),
  });
}
