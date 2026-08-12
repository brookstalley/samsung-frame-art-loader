/* One intent-forming conversation: the thread, the turns, and the commit seam.
 *
 * Contextual, opened from Discover, and it returns there.
 *
 * THE SEAM IS THIS SCREEN'S HARD REQUIREMENT, NOT A POLISH ITEM. Committing a
 * direction never navigates: the commit card *becomes* the run's progress card
 * in place, and then becomes "12 works ready to review", with the transcript
 * above it the whole time. A commit that called `go("run", …)` — which is what
 * the direct-intent box on Discover does, correctly, because it has no
 * transcript to keep — would turn this conversation into a wizard wearing a
 * costume, which is the exact risk the flow was designed against.
 *
 * That is why every write here paints from its own response rather than
 * navigating or re-fetching: the POST that commits returns the whole thread with
 * a committed turn at the end of it, and painting that is the transform.
 */

import { api } from "../core/api.js";
import { confirmAct } from "../core/confirm.js";
import { el, guard, render } from "../core/render.js";
import { backLink, go, refresh } from "../core/router.js";
import { state } from "../core/state.js";
import { REACTIONS, recordReaction } from "../core/taste.js";

/* The same interval the run view uses, and for the same reasons: slow enough not
 * to hammer a Pi, fast enough that a curator watching a search does not wonder
 * whether the page is live. */
export const CONVERSATION_POLL_MS = 2000;

/* What each kind of suggestion is called, in the curator's words rather than the
 * enum's. The set is closed and is the same one an affinity is recorded against,
 * so a value with no entry here would be a bare token on the page. */
const KIND_WORDS = {
  artist: "Artist",
  movement: "Movement",
  era: "Era",
  subject: "Subject",
  medium: "Medium",
  palette: "Palette",
};

/* Who said a turn, for a reader rather than for the model. The product's two
 * roles, and there are only ever two. */
const SPEAKER = { curator: "You", system: "Curation" };

/* The next look at this conversation, if it is still the screen on show when the
 * timer comes round. Both conditions are checked at fire time rather than
 * cancelled on navigation — a stale timer that finds the world moved on simply
 * does nothing, which is one mechanism instead of a handle to clear on every
 * path out of the view. Copied in shape from the run view rather than imported
 * from it: a screen never imports another screen. */
function schedulePoll(conversationId, generation) {
  window.setTimeout(() => {
    if (state.poll === generation && state.view === "conversation" && state.detailId === conversationId) refresh();
  }, CONVERSATION_POLL_MS);
}

/* What the committed run's card says, composed from the run's own numbers.
 *
 * Only the states a curator watching from here can be in are given their own
 * sentence; everything else falls back to naming the status, because this card
 * is a summary with a way through to the run view, not a second run view. The
 * run screen is where a run is explained. */
export function commitSentence(view) {
  const run = view.run;
  const tally = view.tally;
  if (run.status === "completed") {
    const count = tally.resolved_proposals;
    return `${count} ${count === 1 ? "work is" : "works are"} ready to review.`;
  }
  if (run.status === "awaiting_approval") {
    return `This search proposed ${tally.proposed} works, which is more than the threshold, so it stopped to ask.`;
  }
  if (run.status === "resolving_works") return "Working out which works match this direction.";
  if (run.status === "resolving_images") return `The list of ${tally.proposed} works is settled; looking for an image of each.`;
  return `This search is ${run.status}. Open it to see what happened.`;
}

/* The direction a commit would search for, composed from what the last turn
 * named. The curator reads and edits it before committing — what gets searched
 * for is their decision, and a button that sent something they had not read is
 * the wizard this screen exists not to be. */
export function directionFrom(turns) {
  for (let index = turns.length - 1; index >= 0; index -= 1) {
    const named = turns[index].suggested.map((entry) => entry.value);
    if (named.length) return named.join(", ");
  }
  return "";
}

export async function viewConversation(conversationId, generation) {
  // Claimed at the top and re-checked after every await, exactly as the run view
  // does: a paint still in flight when a newer one starts must not land over it
  // or schedule a second poll chain beside its own.
  state.poll += 1;
  const pollGeneration = state.poll;
  const view = await api(`/api/conversations/${encodeURIComponent(conversationId)}`);
  if (state.poll !== pollGeneration) return;
  await paint(view, { conversationId, generation, pollGeneration });
}

async function paint(view, { conversationId, generation, pollGeneration }) {
  // The committed run is fetched from the run's own endpoint rather than
  // mirrored onto the conversation payload. Its `is_terminal` and its tally
  // already exist and are exactly the numbers "12 works ready to review" needs,
  // and a second copy of a run's state is a second copy free to go stale.
  let run = null;
  let runProblem = null;
  if (view.committed_run_id) {
    try {
      run = await api(`/api/runs/${encodeURIComponent(view.committed_run_id)}`);
    } catch (failure) {
      // Said rather than swallowed: a commit card that silently stopped showing
      // progress looks exactly like a search that is not running. Named, and
      // terminal. There is no watch-with-a-failure-count here the
      // way the run view has one, because there is nothing for one to protect: a
      // conversation whose committed run cannot be read has one broken thing in
      // it, and a card that retried silently for as long as the tab stayed open
      // would be the stale-page-that-looks-live failure wearing a spinner.
      runProblem =
        `The search this conversation started could not be read: ${failure.message} ` +
        "Reload the page to try reading it again.";
    }
    if (state.poll !== pollGeneration) return;
  }

  // Asked for only when there is a direction to offer, and it is the same flat
  // bound Discover shows: one model call plus the search allowance. There is no
  // intent-aware pricing anywhere in this product, and inventing one here would
  // put a figure on the card that nothing else could reproduce.
  let estimate = null;
  const direction = directionFrom(view.turns);
  if (run === null && direction) {
    try {
      estimate = await api("/api/estimate");
    } catch {
      // Deliberately silent, and the asymmetry with the run failure above is
      // the point: losing the price leaves the commit button unpriced, which the
      // card says in words below. Losing the run's progress leaves a card that
      // lies about what is happening.
      estimate = null;
    }
    if (state.poll !== pollGeneration) return;
  }

  /* A repaint that changes nothing is not free: `render` replaces the whole
   * subtree, so a keyboard user standing on "Search for this" loses it every two
   * seconds while a run is in flight. Compared against everything painted, not
   * just the run's status — a thread growing underneath a settled status is
   * exactly the change worth repainting for. */
  const body = JSON.stringify({ view, run, runProblem, estimate });
  if (state.painted !== null && state.painted.conversationId === conversationId && state.painted.body === body) {
    if (run !== null && !run.run.is_terminal) schedulePoll(conversationId, pollGeneration);
    return;
  }

  const said = el("textarea", { id: "say", rows: 3, required: true });
  const send = el("button", {
    class: "action",
    type: "button",
    text: "Say it",
    onclick: () =>
      guard(async () => {
        const next = await api(`/api/conversations/${encodeURIComponent(conversationId)}/turns`, {
          method: "POST",
          body: JSON.stringify({ text: said.value }),
        });
        await repaint(next, { conversationId, generation });
      }),
  });

  render(
    generation,
    el("p", {}, [backLink()]),
    el("h2", { text: "Working out what to look for" }),
    thread(view),
    // The whole of the retryable failed turn. The turn itself is already in the
    // transcript above — it never vanishes, because it was written before the
    // model was ever asked — and this is the account of why it has no answer and
    // the way to ask for one again.
    view.unanswered_turn_id ? unanswered(view, { conversationId, generation }) : null,
    // Present on every paint, empty or not. A live region has to exist in the
    // document before the content it announces is put into it, and a region
    // created-and-filled in one step announces nothing to a reader who was
    // already on the page.
    commitCard(view, { run, runProblem, estimate, direction, conversationId, generation }),
    el("div", { class: "panel" }, [
      el("h3", { text: "Say something" }),
      el("div", { class: "field" }, [el("label", { for: "say", text: "What are you after?" }), said]),
      el("div", { class: "row" }, [send]),
    ]),
    el("div", { class: "panel" }, [
      el("h3", { text: "Delete this conversation" }),
      el("p", {
        class: "muted",
        // Said before the button rather than only in the dialog, because this is
        // the one control on the surface whose act cannot be undone and a
        // curator should be able to decide not to press it without pressing it.
        text:
          "Everything said here would be destroyed. What was learned from it is kept — the judgments stand " +
          "and the spending is still recorded — but they stop saying which turn produced them.",
      }),
      el("div", { class: "row" }, [
        el("button", {
          class: "action quiet",
          type: "button",
          text: "Delete this conversation",
          onclick: () => guard(() => destroy(conversationId)),
        }),
      ]),
    ]),
  );

  state.painted = { conversationId, body };
  if (run !== null && !run.run.is_terminal) schedulePoll(conversationId, pollGeneration);
}

/* Destroy the thread, having said what that costs in the terms it costs it.
 *
 * **The one operation on this surface that genuinely destroys a record**, which
 * is why the confirmation names a consequence rather than a count. Archiving a
 * work keeps the row; deleting a theme is refused while it is hung; this is
 * gone. What the curator loses is not "three rows" — it is the ability to
 * rebuild the judgments this thread produced when the way the product reads a
 * conversation improves, and that is what the sentence says.
 *
 * It navigates afterwards, and that is not the wizard this screen refuses. The
 * commit stays because there is still a conversation to stay in; here there is
 * not, and a screen left pointing at a deleted thread would fail its next poll
 * with an error about something the curator meant to happen. */
async function destroy(conversationId) {
  const agreed = await confirmAct({
    title: "Delete this conversation?",
    consequence:
      "Everything said here is destroyed and cannot be recovered. What was learned from it stays — the " +
      "judgments about your taste and what the talking cost are both kept — but they will no longer say " +
      "which turn produced them, so they can never be rebuilt when this product gets better at reading a " +
      "conversation.",
    confirmLabel: "Delete it",
  });
  if (!agreed) return;
  await api(`/api/conversations/${encodeURIComponent(conversationId)}`, { method: "DELETE" });
  // Bumped so a poll already in flight cannot land a paint over the screen that
  // replaces this one, exactly as a write does.
  state.poll += 1;
  go("discover");
}

/* Paint a view that arrived from a write rather than from a poll.
 *
 * The generation is bumped first so that any poll already in flight is
 * superseded rather than allowed to land over the answer that was just paid
 * for. This is what makes the commit an in-place transform rather than a
 * navigation: the response to the POST *is* the next state of this screen. */
async function repaint(view, { conversationId, generation }) {
  state.poll += 1;
  await paint(view, { conversationId, generation, pollGeneration: state.poll });
}

function thread(view) {
  if (!view.turns.length) {
    return el("div", { class: "panel" }, [
      el("p", { class: "muted", text: "Nothing said yet. Describe the wall, the room, or the mood you are after." }),
    ]);
  }
  return el(
    "div",
    { class: "panel", id: "thread" },
    view.turns.map((turn) =>
      el("div", { class: "turn", "data-role": turn.role, "data-turn": turn.turn_id }, [
        el("p", { class: "turn-speaker", text: SPEAKER[turn.role] || turn.role }),
        // An empty string is what a turn that could not be answered holds, and
        // saying so beats an empty paragraph a reader would take for a gap.
        el("p", { class: turn.text ? null : "muted", text: turn.text || "No answer came back for this." }),
        turn.suggested.length
          ? el(
              "div",
              { class: "suggestions" },
              turn.suggested.map((entry) => suggestion(entry, turn.turn_id)),
            )
          : null,
      ]),
    ),
  );
}

/* One thing a turn named, the pictures found for it, and what to do about it.
 *
 * `data-suggestion-kind` / `data-suggestion-value` and `data-sample-title` were
 * left here by the chunk that built the thread, for the reaction controls to
 * attach to. This is that chunk, and they are now read: every reaction records a
 * judgment about the *suggestion* — the artist or movement the reply named — so
 * the value the affinity is keyed on comes off the enclosing block rather than
 * off the picture the curator happened to be looking at.
 *
 * **The reactions sit on each sample, and the affinity they write is about the
 * name above them.** That is the flow's own arrangement, and its reason is where
 * the curator's attention is: the judgment is formed looking at a picture, so
 * the control belongs beside the picture. The consequence is that three samples
 * offer three routes to one row, which is harmless — the write is an upsert on
 * (kind, value) — but is stated here so a reader does not go looking for the
 * per-picture judgment the data model deliberately cannot hold. */
function suggestion(entry, turnId) {
  return el("div", { class: "suggestion", "data-suggestion-kind": entry.kind, "data-suggestion-value": entry.value }, [
    el("p", { class: "suggestion-name" }, [
      // Glyph, word and value, so the kind survives greyscale and a reader who
      // has turned the lights down. Never colour alone anywhere on this surface.
      el("span", { class: "glyph", "aria-hidden": "true", text: "◆" }),
      el("span", { class: "muted", text: `${KIND_WORDS[entry.kind] || entry.kind}: ` }),
      el("span", { text: entry.value }),
    ]),
    entry.samples.length
      ? el(
          "div",
          { class: "samples" },
          entry.samples.map((sample) =>
            el("figure", { class: "sample", "data-sample-title": sample.title }, [
              // A sample with no picture still says what it is. A collection
              // record can carry no preview, and a blank box is how a curator
              // concludes the product is broken.
              sample.image_url
                ? el("img", {
                    src: sample.image_url,
                    alt: `${sample.title}${sample.artist ? `, ${sample.artist}` : ""}`,
                    loading: "lazy",
                  })
                : el("p", { class: "muted", text: "No picture travels with this record." }),
              el("figcaption", { text: sample.artist ? `${sample.title} — ${sample.artist}` : sample.title }),
              reactions(entry, turnId),
            ]),
          ),
        )
      : // A suggestion the collection holds no picture for still gets its
        // reactions. The name is what a judgment is about, and a curator who
        // recognises a movement they dislike should not have to wait for a
        // picture of it before saying so.
        reactions(entry, turnId),
    departure(entry),
  ]);
}

/* The three reactions, and the fourth control kept away from them.
 *
 * **The three record taste and stay in the thread.** They write an `Affinity`
 * with `derivation='stated'` — the curator saying so directly — rather than
 * leaving the model to infer one from prose, and each is a different pair of the
 * two fields taste is held in. "Tell me more" is the one worth reading twice: it
 * is cool *and still open*, which is the sentence the two-field design exists
 * for.
 *
 * The page does not repaint after one. The judgment is recorded elsewhere and
 * nothing in the transcript changes — a thread that redrew itself under a
 * curator who pressed a button beside a picture would move the picture. What
 * confirms it is the control's own state, below. */
function reactions(entry, turnId) {
  return el(
    "div",
    // Announced rather than only shown: the confirmation below is a change of
    // label on a control the curator has just left, and a reader who is not
    // looking at it would otherwise get no acknowledgement at all.
    { class: "reactions", "aria-live": "polite" },
    Object.keys(REACTIONS).map((reaction) => {
      const control = el("button", {
        class: "action quiet",
        type: "button",
        text: reaction,
        // The value in the accessible name, because the visible label is shared
        // by every sample on the page: a screen reader moving through a turn
        // that named three artists would otherwise hear "not this" nine times
        // with nothing saying what "this" is.
        "aria-label": `${reaction}: ${entry.value}`,
        onclick: () =>
          guard(async () => {
            await recordReaction({ kind: entry.kind, value: entry.value, reaction, sourceTurnId: turnId });
            // Said, not merely styled, and said in the past tense so it reads as
            // a record rather than as an offer. `aria-live` on the row is what
            // carries it to a reader who is not looking at the button.
            control.textContent = `${reaction} — recorded`;
            control.disabled = true;
          }),
      });
      return control;
    }),
  );
}

/* "Go to <artist>'s work" — the one control here that leaves the thread.
 *
 * **Kept visually apart from the three reactions because it is a different kind
 * of act.** The reactions record taste and stay; this one navigates, filtering
 * Collection to the artist. Sitting it among them would put a control that loses
 * the curator's place in a row of controls that do not, and the only way to find
 * that out is to press it.
 *
 * Offered for artists only, and that is the vocabulary's doing rather than a
 * simplification: Collection filters by facet kind, and "go to Surrealism's
 * work" would be a filter on a kind the grid can take — but the artists a
 * conversation surfaces are the ones this control exists for, and an artist is
 * the only kind whose samples came from the collection at all.
 *
 * Where it lands is usually nowhere, and that is expected: the artists a
 * conversation names are by definition ones the curator could not have named, so
 * a collection holding none of them is the ordinary outcome. Collection says so
 * as a normal state rather than as a failed query. */
function departure(entry) {
  if (entry.kind !== "artist") return null;
  return el("div", { class: "row departure" }, [
    el("button", {
      class: "action quiet",
      type: "button",
      text: `Go to ${entry.value}'s work`,
      // `encodeURIComponent` before the value goes in, because a facet in the
      // fragment is escaped once by whoever writes it and once more by
      // `core/route.js` — Collection unescapes both on the way back out, which
      // is how a value holding the separator survives the trip. The one call is
      // duplicated from Collection's own `joinValues` rather than shared,
      // because a screen never imports another screen; the browser test that
      // follows this button into the empty state is what holds the two together.
      onclick: () => go("collection", null, { artist: encodeURIComponent(entry.value) }),
    }),
  ]);
}

function unanswered(view, { conversationId, generation }) {
  return el("div", { class: "panel" }, [
    el("p", {
      class: "note error",
      // `role="alert"` rather than colour and position alone: a curator who
      // learns a turn failed by noticing a red line is a curator who misses it.
      role: "alert",
      // The reason is the account of *this* attempt and is absent after a
      // reload, when all that survives is the transcript's own fact — a question
      // with no answer under it. Both readings say the same actionable thing.
      text: view.failure || "That question has not been answered yet.",
    }),
    el("div", { class: "row" }, [
      el("button", {
        class: "action",
        type: "button",
        text: "Ask again",
        onclick: () =>
          guard(async () => {
            // No text. Retrying asks for the answer to the question already in
            // the thread rather than re-sending the question, which is what
            // keeps pressing this twice from buying two answers: once a turn has
            // been answered there is nothing outstanding, and the server says so
            // instead of spending again.
            const next = await api(`/api/conversations/${encodeURIComponent(conversationId)}/turns`, {
              method: "POST",
              body: JSON.stringify({}),
            });
            await repaint(next, { conversationId, generation });
          }),
      }),
    ]),
  ]);
}

function commitCard(view, { run, runProblem, estimate, direction, conversationId, generation }) {
  const children = [el("h3", { text: "Search for a direction" })];
  if (run !== null) {
    const finished = run.run.status === "completed";
    children.push(
      el("p", {}, [
        el("span", { class: "glyph", "aria-hidden": "true", text: run.run.is_terminal ? "●" : "◌" }),
        el("span", { text: ` ${commitSentence(run)}` }),
      ]),
      el("p", { class: "muted", text: `Searching for: ${run.run.intent || "—"}` }),
      el("div", { class: "row" }, [
        // The one navigation this screen makes, and it is the curator choosing
        // to act on the result rather than the commit taking them somewhere.
        // Offered only once there is something to review: a button onto an empty
        // grid is a promise the next screen cannot keep.
        finished && run.works.length
          ? el("button", {
              class: "action",
              type: "button",
              text: "Review these works",
              onclick: () => go("review", run.run.run_id),
            })
          : null,
        el("button", {
          class: "action quiet",
          type: "button",
          text: "Open the search",
          onclick: () => go("run", run.run.run_id),
        }),
      ]),
    );
  } else if (direction) {
    const intent = el("textarea", { id: "direction", rows: 2, required: true, text: direction });
    children.push(
      el("p", { class: "muted", text: "This is what would be searched for. Change it if it is not quite right." }),
      el("div", { class: "field" }, [el("label", { for: "direction", text: "The direction to search for" }), intent]),
      el("p", {
        class: "note",
        // Stated as a bound rather than a typical figure, because a search may
        // freely use its whole allowance and an estimate it can exceed is not
        // one. The absence of a price is said out loud rather than left blank.
        text: estimate
          ? `Searching costs at most $${estimate.estimated_cost_usd}. ${estimate.basis}`
          : "The cost of searching could not be read just now. Committing still starts a search.",
      }),
      el("div", { class: "row" }, [
        el("button", {
          class: "action primary",
          type: "button",
          text: "Search for this",
          onclick: () =>
            guard(async () => {
              const next = await api(`/api/conversations/${encodeURIComponent(conversationId)}/commit`, {
                method: "POST",
                body: JSON.stringify({ intent: intent.value }),
              });
              // Painted, never navigated. This one line is the seam.
              await repaint(next, { conversationId, generation });
            }),
        }),
      ]),
    );
  } else {
    children.push(
      el("p", {
        class: "muted",
        text: "Once this conversation names an artist or a movement, the search it would run is offered here.",
      }),
    );
  }
  if (runProblem) children.push(el("p", { class: "note", text: runProblem }));
  // `aria-live` so the card's transformation is announced rather than only seen.
  // The no-op suppression above is what stops a poll re-announcing content the
  // region already holds, which is a defect rather than a nicety.
  return el("div", { class: "panel", id: "commit-card", "aria-live": "polite" }, children);
}
