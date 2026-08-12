/* Discover — asking for something new, and every search that has been asked.
 *
 * The third destination. `information-architecture.md` describes it as
 * "conversation, the runs it seeds, and the review of what they return — one
 * continuous place"; the conversation half and the in-place commit seam are a
 * later chunk's. What this chunk moved is the built discovery screen: the direct
 * intent box, which does not go away, and the run list.
 */

import { api } from "../core/api.js";
import { table } from "../core/badges.js";
import { el, guard, render } from "../core/render.js";
import { go } from "../core/router.js";

export async function viewDiscover(generation) {
  // Both in one round trip: the estimate exists to inform the decision being
  // made in the field beside it, so a screen that fetched it afterwards would
  // be showing a receipt.
  const [estimate, runs] = await Promise.all([api("/api/estimate"), api("/api/runs")]);

  const intent = el("textarea", { id: "intent", rows: 3, required: true });
  const start = el("button", {
    class: "action",
    type: "button",
    text: "Start the search",
    onclick: () =>
      guard(async () => {
        const run = await api("/api/runs", {
          method: "POST",
          body: JSON.stringify({ intent: intent.value }),
        });
        go("run", run.run_id);
      }),
  });

  const entry = el("div", { class: "panel" }, [
    el("h3", { text: "Ask for something" }),
    el("div", { class: "field" }, [
      el("label", { for: "intent", text: "What are you looking for?" }),
      intent,
    ]),
    el("p", {
      class: "note",
      // The price before the decision, and what it buys. Stated as a bound
      // rather than a typical figure, because a run may freely use the whole
      // allowance and an estimate it can exceed is not an estimate.
      text: `Asking costs at most $${estimate.estimated_cost_usd}. ${estimate.basis}`,
    }),
    el("div", { class: "row" }, [start]),
  ]);

  const panels = [el("h2", { text: "Discover" }), entry];

  if (!runs.runs.length) {
    panels.push(el("p", { class: "muted", text: "No searches yet. Ask for something above." }));
  } else {
    panels.push(
      el("div", { class: "panel" }, [
        // Both figures whenever they differ. The server caps this listing, and a
        // heading reading "Searches (50)" over a history of four hundred is a
        // silently short list — indistinguishable from a complete one, which is
        // how a curator concludes their older searches are gone. The count alone
        // was what this rendered for one commit, immediately after the cap was
        // added on the server and before anything here read `total`.
        el("h3", { text: runs.truncated ? `Searches (${runs.count} of ${runs.total})` : `Searches (${runs.count})` }),
        runs.truncated
          ? el("p", {
              class: "note",
              // No paging on this listing, so the note must not imply one. What
              // reaches an older run is opening it directly: the run view takes
              // an id in the fragment and is reachable from anywhere.
              text:
                `Showing the ${runs.count} most recent of ${runs.total} searches. ` +
                "Older ones are still here and still open at their own address; this list does not page.",
            })
          : null,
        table(
          "Every search, newest first. A re-search is a run too, and is listed here with its parent.",
          ["Asked for", "Kind", "State", "Started", "Open"],
          runs.runs.map((run) => [
            run.intent || "—",
            run.kind === "resolve" ? "re-search" : "search",
            run.status,
            run.started_at,
            el("button", {
              class: "action quiet",
              type: "button",
              text: "Open",
              "aria-label": `Open the search for ${run.intent || run.run_id}`,
              onclick: () => go("run", run.run_id),
            }),
          ]),
        ),
      ]),
    );
  }
  render(generation, ...panels);
}
