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
 * product counts, and is passed explicitly where it is not.
 *
 * Exported although `counted` is its only caller here, and not for a test: this
 * module has none of its own — nothing in the repo runs JavaScript units, and
 * every line of it is reached through the browser suite. It is exported because
 * `counting.py` exports it and is imported directly by callers there, so an
 * unexported twin would be the two halves quietly diverging; and because a
 * sentence needing the noun without the number in front of it is the next call
 * site rather than a hypothetical one. */
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

/* Agreement for "N of M works …" — the shape where the nearest count is the wrong one.
 *
 * The Python half carries the reasoning. In short: English agrees the verb with
 * the head of the subject, and in "1 of the 5 works" the head is *1* — "one of
 * the five works **has** an image". The `5` is the number printed immediately
 * before the verb, which is why keying `agree` on it reads right and shipped "1
 * of the 2 works it covers **have** an image".
 *
 * Zero is the exception and is why this is a function rather than advice to pass
 * the numerator: "0 of 3 works" is *none of the three* and takes the plural,
 * "0 of 1 work" is *none of the one* and takes the singular. */
export function agreePartitive(part, whole, singular, plural) {
  return agree(part === 0 ? whole : part, singular, plural);
}
