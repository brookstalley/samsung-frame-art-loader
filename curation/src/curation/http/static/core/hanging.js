/* Putting a theme on a wall — the one act the IA gives a confirmation contract to.
 *
 * **In `core/` because two screens perform the identical act.** The Theme screen
 * offers "Hang on the living room" beside a theme; the Walls screen offers a
 * theme picker beside a wall. Same question, same endpoint, same sentence — and
 * `screens/` modules may not import each other (`architecture.md` § Components &
 * Responsibilities), so shared vocabulary lives here or it lives twice. It lived
 * twice until Critic review found it, down to the wording of the question, which
 * is the shape this repository has already been bitten by once: a sentence
 * duplicated across two files with a comment in each saying they must match and
 * nothing checking it.
 *
 * **The sentence matters more than the request does.** Hanging is the act flow 6
 * singles out for a confirmation, because it is the one that changes what other
 * people in the house see. A change made to the question in one screen and not
 * the other ships two different questions for one act, and the curator has no
 * way to know which one they answered.
 *
 * **The preview is fetched at the moment the question is asked**, never taken
 * from whatever the screen last painted: the consequence sentence is a statement
 * about the manifest that would result now, and a stale one would promise a wall
 * something a rebuild is about to contradict.
 *
 * **What each screen does afterwards is theirs**, which is the only thing that
 * genuinely differed — the Theme screen leaves for the Walls screen to show the
 * result, the Walls screen repaints in place. That is the parameter.
 */

import { api } from "./api.js";
import { confirmAct } from "./confirm.js";

/* Ask, and hang if the answer is yes.
 *
 * Returns whether it hung, so a caller can tell a declined question from a
 * completed one without inferring it from the screen not having changed.
 *
 * The question names the theme *and* the wall even while there is one wall. A
 * sentence that reads correctly today only because there is a single possible
 * target is the last place a mistake could have been caught, and it silently
 * stops being true when the second display arrives. */
export async function hangTheme({ themeId, themeName, wall, then }) {
  const preview = await api(
    `/api/manifest?wall_id=${encodeURIComponent(wall.wall_id)}&theme_id=${encodeURIComponent(themeId)}`,
  );
  const confirmed = await confirmAct({
    title: `Hang ${themeName} on ${wall.name}?`,
    consequence: `${preview.summary} Everyone in the house sees ${wall.name} change.`,
    confirmLabel: "Hang",
  });
  if (!confirmed) return false;

  await api(`/api/themes/${encodeURIComponent(themeId)}/activate`, {
    method: "POST",
    body: JSON.stringify({ wall_id: wall.wall_id }),
  });
  await then();
  return true;
}
