/* Saying a count out loud, with the words around it agreeing with it.
 *
 * The browser half of `curation/src/curation/counting.py`, which carries the
 * reasoning. Duplicated across the language boundary because `screens/run.js`
 * composes its own sentences rather than printing the MCP surface's notice —
 * that notice names fields in backticks and tells the caller to call status
 * again, neither of which is true of a page with buttons on it — so the two
 * sets of sentences are genuinely different text about the same numbers.
 *
 * It lives in `core/` because `architecture.md` § Components & Responsibilities
 * allows a screen to import from `core/` and forbids it importing another
 * screen. A private copy inside `run.js` is what the file had before this: one
 * correct inline ternary and six sentences without it.
 */

/* The form of a noun that agrees with `count` — `work`, `works`.
 *
 * `plural` defaults to suffixing an `s`, which is right for every noun this
 * product counts, and is passed explicitly where it is not. */
export function noun(count, singular, plural = null) {
  if (count === 1) return singular;
  return plural === null ? `${singular}s` : plural;
}

/* A count and its noun — `1 work`, `12 works`. */
export function counted(count, singular, plural = null) {
  return `${count} ${noun(count, singular, plural)}`;
}

/* The word elsewhere in the sentence that has to agree — `is`/`are`, `them`/`it`.
 *
 * No default plural, unlike `noun`: verb agreement in English is not
 * suffixation, so a default could only be wrong, and wrong in the direction
 * that looks right until somebody reads the output. "1 work ... are reported"
 * is what a noun-only fix leaves behind, and it is what this argument's absence
 * makes hard to write. */
export function agree(count, singular, plural) {
  return count === 1 ? singular : plural;
}
