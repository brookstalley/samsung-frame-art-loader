/* One discovery run, watched while it works.
 *
 * Contextual: opened from Discover — or from a re-search started on the review
 * grid — and it returns to the destination it was opened from.
 */

import { api } from "../core/api.js";
import { facts, reasonBadge, resolutionBadge, table } from "../core/badges.js";
import { agree, counted } from "../core/counting.js";
import { el, guard, render } from "../core/render.js";
import { backLink, go, refresh } from "../core/router.js";
import { state } from "../core/state.js";

/* What this run's state means, in a sentence.
 *
 * Composed here rather than taken from the MCP surface's notice, which is
 * written for a model — it names fields in backticks and tells the caller to
 * call status again, neither of which is true of a page with buttons on it. The
 * numbers are the part that must not be written twice, and they are not: every
 * figure below is read from the tally the server computed.
 *
 * THE RATE IS STATED OVER WHAT THE MODEL PROPOSED, NEVER OVER THE TOTAL. Works a
 * collection offered arrived carrying their own images, so counting them in the
 * numerator reports a retrieval rate the run never achieved — with twelve
 * offered works behind one unresolved proposal, "12 of 13" describes a run that
 * in fact resolved nothing it was asked for. */
/* An if-chain rather than an object literal like the badge maps in `core`, and
 * the asymmetry is a decision rather than an oversight: several of these branches
 * read the tally, the run kind and whether image resolution is wired, so a map
 * of bare strings could not hold them. The cost is that the checker which reads
 * those maps cannot parse this, so `test_every_run_status_is_named_in_the_client`
 * takes the weaker form of asserting each status value appears somewhere in the
 * client — enough to fail when a tenth state is added, which is the property
 * wanted. */
export function runSentence(view) {
  const run = view.run;
  const tally = view.tally;
  if (run.status === "resolving_works") {
    return "Working out which works match the intent.";
  }
  if (run.status === "awaiting_approval") {
    return `This run proposed ${counted(tally.proposed, "work")}, which is more than the threshold, so it stopped to ask. Nothing further is spent until you decide.`;
  }
  if (run.status === "resolving_images") {
    if (!view.image_resolution_available) {
      return `There ${agree(tally.proposed, "is", "are")} ${counted(tally.proposed, "work")} to find images for, but no image provider is configured in this deployment, so the run will stay here. Cancel it when you are done reading it.`;
    }
    if (run.kind === "resolve") {
      return `Looking again for images of the ${counted(tally.total, "work")} this re-search covers.`;
    }
    return `The work list of ${counted(tally.proposed, "work")} is settled, and the run is looking for an image of each.`;
  }
  if (run.status === "completed") {
    let sentence =
      run.kind === "resolve"
        ? `This re-search finished: ${tally.resolved} of the ${counted(tally.total, "work")} it covers ${agree(tally.total, "has", "have")} an image.`
        : `This run finished: ${tally.resolved_proposals} of ${counted(tally.proposed, "work")} it was asked for ${agree(tally.proposed, "has", "have")} an image.`;
    if (run.kind !== "resolve" && tally.offered) {
      // "found no image for" rather than "could not confirm". The run did name
      // works for those artists — they are in the table directly below this
      // sentence, badged `not held` — so a word that reads as "named nothing for"
      // is denied by the screen it is printed on. That was issue #95 on the
      // review grid, and it lived here too: the same claim, one surface over, on
      // the page a curator lands on first.
      sentence += ` Separately, the collection offered ${counted(tally.offered, "more work", "more works")} by artists this run found no image for. They are labelled below and are not what was asked for.`;
    }
    if (tally.unresolved) {
      sentence += ` ${tally.unresolved} could not be matched to any image and ${agree(tally.unresolved, "is", "are")} reported rather than dropped — each says which kind of nothing below.`;
    }
    if (tally.pending) {
      // Held apart from unresolved deliberately. "We looked and it is not
      // there" and "we could not look" lead to opposite actions, and merging
      // them tells a curator their painting does not exist because a museum was
      // briefly unreachable.
      sentence += ` ${tally.pending} could not be looked up at all — the image provider was unreachable for ${agree(tally.pending, "it", "them")}, which says nothing about whether ${agree(tally.pending, "it exists", "they exist")}.`;
    }
    return sentence;
  }
  if (run.status === "halted_by_budget") {
    return "The provider refused further spend, so this run stopped where it was. Retrying will fail the same way until the credit limit resets or is raised.";
  }
  if (run.status === "interrupted") {
    return "The process working on this run stopped underneath it — a restart or a crash, not a fault in the run. Start it again with the same intent.";
  }
  if (run.status === "failed") {
    return "This run hit an error and stopped. The server log has the details.";
  }
  if (run.status === "declined") {
    return "The work list was declined, so no images were looked for and nothing further was spent.";
  }
  if (run.status === "cancelled") {
    return "This run was cancelled. Anything already spent is still recorded.";
  }
  return `This run is ${run.status}.`;
}

/* Slow enough not to hammer a Pi, fast enough that a curator watching a run does
 * not wonder whether the page is live. The server answers immediately rather
 * than holding the request open, so this interval is the whole of the latency. */
export const RUN_POLL_MS = 2000;

/* How many consecutive failures end the watch, and why a count rather than a
 * backoff curve.
 *
 * Two things actually happen here, and neither is the case backoff is for. A
 * blip — one 502, a request caught by a service restart — recovers within a tick
 * or two. A permanent condition — a bookmarked `#run/<id>` for a run that no
 * longer exists, which the service answers 400 — never recovers, and every retry
 * is identical. Backoff optimises the case in between, a long outage that comes
 * good, and there is no such case here: this server is on the same box in the
 * same house as the browser, so if it is unreachable for minutes the whole page
 * is dead and reloading is the natural move, not waiting out a curve.
 *
 * Five, because the realistic multi-second interruption is the operator
 * restarting the curation service while watching a run, and five attempts at
 * two-second spacing rides out about ten seconds of that. A stale bookmark fails
 * all five inside those ten seconds and then stops, instead of asking for a run
 * that will never exist every two seconds for as long as the tab stays open. */
export const RUN_POLL_MAX_FAILURES = 5;

/* Consecutive failures for the run currently being watched.
 *
 * Keyed by run id rather than by poll generation, though the issue that produced
 * it said generation: `state.poll` increments on *every* poll, so a
 * generation-keyed count would reset itself each tick and never reach any
 * threshold. What has to survive a tick is the watch, and what identifies a
 * watch is which run it is on — so opening a different run starts fresh, and a
 * success anywhere clears it. */
function noteWatchFailure(runId) {
  if (state.watch === null || state.watch.runId !== runId) state.watch = { runId, failures: 0 };
  state.watch.failures += 1;
  return state.watch.failures;
}

function noteWatchSuccess(runId) {
  state.watch = { runId, failures: 0 };
}

/* The next look at a run, if this view is still the one on screen when it comes
 * round. Both conditions are checked at fire time rather than cancelled on
 * navigation: a stale timer that finds the world moved on simply does nothing,
 * which is one mechanism instead of a handle to remember to clear on every path
 * out of the view. */
function scheduleRunPoll(runId, generation) {
  window.setTimeout(() => {
    if (state.poll === generation && state.view === "run" && state.detailId === runId) refresh();
  }, RUN_POLL_MS);
}

export async function viewRun(runId, generation) {
  // Claimed at the top and checked after every await. This paint supersedes any
  // earlier one, and an earlier one still in flight must not paint over it or
  // schedule a second timer beside its own — pressing Approve while a poll is
  // mid-request is enough to have two running, and two chains double the request
  // rate on every tick thereafter.
  state.poll += 1;
  const pollGeneration = state.poll;
  let view;
  try {
    view = await api(`/api/runs/${encodeURIComponent(runId)}`);
  } catch (failure) {
    // One blip must not end the watch. Without re-arming, the throw leaves the
    // last paint on screen looking current, `guard` writes a message naming a
    // URL, and no further poll is ever scheduled — so a curator watching a live
    // run through a single 502 is left with a stale page that never recovers
    // and never says it stopped.
    //
    // But re-arming unconditionally has no notion of *consecutive* failures, so
    // it did the same thing for a permanent one. Opening a stale bookmarked
    // `#run/<id>` after the run is gone had the service answer 400, the catch
    // re-arm, and the tab request that run every two seconds for as long as it
    // stayed open — bounded only by navigation, with nothing on screen saying
    // the watch was still retrying.
    if (noteWatchFailure(runId) >= RUN_POLL_MAX_FAILURES) {
      // Say the watch stopped, not only what failed. The two are different
      // facts and only one of them tells the curator what to do next: a message
      // naming a 400 leaves a live page indistinguishable from a dead one.
      throw new Error(
        `${failure.message} Gave up watching this run after ${RUN_POLL_MAX_FAILURES} attempts — ` +
          "reload the page to start watching again."
      );
    }
    // Re-arm first, then re-throw so the message is still shown: the next tick
    // repaints and clears it if the blip has passed.
    scheduleRunPoll(runId, pollGeneration);
    throw failure;
  }
  if (state.poll !== pollGeneration) return;
  // A reachable run resets the count, so a watch is only ever ended by failures
  // with nothing between them. Recorded here rather than after the paint: what
  // the count is about is whether the server answered, and it just did.
  noteWatchSuccess(runId);
  const run = view.run;
  const tally = view.tally;

  /* A poll that repaints an unchanged view is not free: `render` replaces the
   * whole subtree, which destroys whatever the keyboard user was standing on —
   * so tabbing to "Approve" and pausing to read loses the focus two seconds
   * later, every time, on the one screen whose whole job is to be decided on.
   * Nothing changed means nothing to touch. Compared against the payload rather
   * than against the status alone, because a work list filling in underneath a
   * settled status is exactly the change worth repainting for. */
  const body = JSON.stringify(view);
  if (state.painted !== null && state.painted.runId === runId && state.painted.body === body) {
    if (!run.is_terminal) scheduleRunPoll(runId, pollGeneration);
    return;
  }

  // The gate is the point of decision for phase 2, so its price and what that
  // price is made of belong beside the buttons rather than on a costs panel
  // further down. Asked for only at the gate: every other state either has no
  // decision pending or has already spent whatever it was going to.
  let gateEstimate = null;
  let gateEstimateProblem = null;
  if (run.status === "awaiting_approval") {
    // A failure to price must not cost the curator their approve button — the
    // estimate explains a decision, it is not the decision. But it is said
    // rather than swallowed: a gate that silently stops showing a price looks
    // exactly like a gate whose price is nothing.
    try {
      gateEstimate = await api(`/api/estimate?run_id=${encodeURIComponent(runId)}`);
    } catch (failure) {
      gateEstimateProblem = `The cost of approving could not be read: ${failure.message}`;
    }
    if (state.poll !== pollGeneration) return;
  }

  /* What asking for this actually cost, all in. The run record carries only its
   * OWN spend, so a run billed little whose re-searches cost ten times more
   * reads as cheap from the run alone — and "what did asking for Dalí cost" is
   * the family total, which lives nowhere else. Fetched once the run has
   * stopped: while it is still working the figure is mid-flight, and a total
   * that climbs under a heading saying what something cost invites reading a
   * partial as a final. */
  let familySpend = null;
  let familySpendProblem = null;
  if (run.is_terminal) {
    try {
      familySpend = await api(`/api/runs/${encodeURIComponent(runId)}/spend`);
    } catch (failure) {
      // Said, not swallowed — the same call the gate estimate makes above, for
      // the same reason. Losing the rollup must not cost the curator the costs
      // panel, and it must not do so in silence either: this is the only place
      // the family total appears, so a panel that quietly drops the row leaves
      // "Spent by this run alone" reading as what asking cost, which is the
      // exact misreading that row was added to prevent.
      familySpendProblem = `The total including every re-search could not be read: ${failure.message}`;
    }
    if (state.poll !== pollGeneration) return;
  }

  const decisions = el("div", { class: "row" }, [
    run.status === "awaiting_approval"
      ? el("button", {
          class: "action",
          type: "button",
          text: "Approve the list",
          onclick: () => guard(async () => {
            await api(`/api/runs/${encodeURIComponent(runId)}/approve`, { method: "POST" });
            await refresh();
          }),
        })
      : null,
    run.status === "awaiting_approval"
      ? el("button", {
          class: "action quiet",
          type: "button",
          text: "Decline it",
          onclick: () => guard(async () => {
            await api(`/api/runs/${encodeURIComponent(runId)}/decline`, { method: "POST" });
            await refresh();
          }),
        })
      : null,
    run.is_terminal
      ? null
      : el("button", {
          class: "action quiet",
          type: "button",
          text: "Cancel this run",
          onclick: () => guard(async () => {
            await api(`/api/runs/${encodeURIComponent(runId)}/cancel`, { method: "POST" });
            await refresh();
          }),
        }),
  ]);

  const panels = [
    el("p", {}, [backLink()]),
    el("h2", { text: run.intent || "Re-search" }),
    el("div", { class: "panel" }, [
      el("p", { class: "note", text: runSentence(view) }),
      // The engine's own reading of the request, beside the request. A work list
      // is judged against how the intent was read rather than against its
      // wording, which is what makes a surprising list explicable.
      run.strategy ? el("p", { class: "muted", text: `How it read the request: ${run.strategy}` }) : null,
      // What approving commits to, in the place the commitment is made. The
      // basis is the load-bearing half: the figure is currently zero because
      // phase 2 asks museum APIs, and a bare "$0" beside an approve button
      // invites the reading that the gate is about money. It is about the size
      // of the work list, and the basis says so.
      gateEstimate
        ? el("p", { class: "muted", text: `Approving costs $${gateEstimate.estimated_cost_usd}. ${gateEstimate.basis}` })
        : null,
      gateEstimateProblem ? el("p", { class: "note", text: gateEstimateProblem }) : null,
      decisions,
    ]),
    el("div", { class: "panel" }, [
      el("h3", { text: "What it cost" }),
      facts([
        // Named for what it actually is. This figure is written when phase 1
        // finishes and the work count is known, so it prices *resolving the work
        // list* — labelling it as the estimate made before starting would put
        // the phase-1 price under a heading describing phase 2.
        ["Estimated to find the images", run.estimated_cost_usd === null ? null : `$${run.estimated_cost_usd}`],
        // Labelled as this run's own, because that is what it is: the record
        // carries `run_cost(run_id).direct`. Left unqualified it reads as the
        // whole cost of having asked, which it is not the moment a re-search
        // descends from it.
        ["Spent by this run alone", run.actual_cost_usd === null ? null : `$${run.actual_cost_usd}`],
        // The family total — what asking for this cost altogether, re-searches
        // included. A run billed little whose re-searches cost ten times more is
        // exactly the case the two figures exist to keep apart, and it is the
        // only place this number appears.
        [
          "Spent including every re-search",
          familySpend === null ? null : `$${familySpend.cost_usd}`,
        ],
        // Two numbers, never a verdict: the usage is this run's history and the
        // allowance is the deployment's setting as it stands now.
        ["Searches used", `${view.searches.used} of an allowance of ${view.searches.allowance}`],
      ]),
      // The row's absence, said out loud. `facts` drops a null pair entirely, so
      // without this the total simply is not there — and a panel showing only
      // what this run spent, with nothing to say a figure is missing, is read as
      // the whole cost of having asked.
      familySpendProblem ? el("p", { class: "note", text: familySpendProblem }) : null,
    ]),
  ];

  panels.push(
    el("div", { class: "panel" }, [
      el("h3", { text: `Works (${tally.total})` }),
      // The way from watching a run to judging what it brought back. Offered
      // only once the run holds works: a button onto an empty grid is a promise
      // the next screen cannot keep.
      view.works.length
        ? el("p", {}, [
            el("button", {
              class: "action",
              type: "button",
              text: "Review these works",
              onclick: () => go("review", runId),
            }),
          ])
        : null,
      el("p", {
        class: "muted",
        // Both counts, always, including when the collection offered nothing —
        // a line that appeared only when there was a supplement would train a
        // reader to read its absence as "these are all what I asked for".
        text: `${tally.proposed} asked for, ${tally.offered} offered by the collection on top of them.`,
      }),
      view.works.length
        ? table(
            "Every work this run holds, asked-for and offered together. The counts above say how many of each.",
            // NO PROVENANCE COLUMN, and its removal is the fix rather than a
            // simplification. It was headed "Where it came from" and meant *how
            // this row entered the run* — named by the model, or volunteered by
            // a wired collection. In an art catalogue that phrase reads as the
            // work's own provenance: which museum holds it. On the one screen
            // where a curator is scanning titles and artists, the heading
            // pointed at the wrong fact entirely.
            //
            // Renaming it was the obvious repair and the wrong one. The
            // distinction is real and load-bearing — a curator authorised a list
            // of a stated size and the supplement adds to it — but this table is
            // the fourth place it is stated, after the tally's separate counts,
            // the run sentence, and the line directly above these rows. What it
            // adds per row is which *particular* work was offered, and nothing
            // on this screen is decided per work: the deciding happens on the
            // review card, where the badge stays.
            // "Why it is here", not "Why the run named it". This table is
            // deliberately every work the run holds, asked-for and offered
            // together — and the run named none of the offered ones, whose cell
            // in this very column now says so in as many words. A heading that
            // asserts naming above a cell that denies it is the defect this whole
            // change exists to remove, one column apart instead of one page.
            ["Title", "Artist", "Image", "Why it is here"],
            view.works.map((work) => [
              work.title,
              work.artist || "—",
              el("div", { class: "stack-tight" }, [resolutionBadge(work), reasonBadge(work)]),
              work.rationale,
            ]),
          )
        : el("p", { class: "muted", text: "This run has not settled on any works yet." }),
    ]),
  );

  render(generation, ...panels);

  // Recorded only when the paint is one worth leaving alone. A gate whose price
  // could not be read is not: the run itself is unchanged, so every later poll
  // would match the signature and the failure sentence would sit there until
  // something else about the run moved. Not recording it is what makes the next
  // poll try the price again.
  //
  // The family total's failure is deliberately NOT held out the same way, and
  // the asymmetry is the point rather than an oversight: it is fetched only for
  // a run that has stopped, and a stopped run schedules no further poll, so
  // there is no next attempt for withholding the signature to enable. The
  // sentence in the panel is the whole of that remedy.
  if (gateEstimateProblem === null) state.painted = { runId, body };

  // Poll only while there is something still to wait for. `is_terminal` comes
  // from the server rather than from a list of finished states written here,
  // which would go stale the day a tenth state is added and leave this polling
  // a finished run forever.
  if (!run.is_terminal) scheduleRunPoll(runId, pollGeneration);
}
