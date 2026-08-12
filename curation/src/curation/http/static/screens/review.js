/* Review — judging one run's candidates.
 *
 * The product's highest-stakes screen: accepting spends money and acquires,
 * rejecting suppresses a work from future runs. Contextual, opened from a run.
 */

import { api, fetchAllCandidates } from "../core/api.js";
import {
  absentImage,
  facts,
  fitBadge,
  REASON_SENTENCES,
  reasonBadge,
  resolutionBadge,
  shortfallNote,
} from "../core/badges.js";
import { el, guard, render } from "../core/render.js";
import { go } from "../core/router.js";

/* What the curator has decided about a work, in words.
 *
 * `pending` is absent on purpose: an undecided work is the ordinary case and
 * shows no badge, the same way an accepted catalogue work shows no status badge.
 * A badge on every card would make the two decided states harder to pick out,
 * not easier. The vocabulary test knows about the omission. */
const VERDICT_GLYPHS = { accepted: "✓", rejected: "✗", awaiting_better_image: "◑" };

const VERDICT_WORDS = {
  accepted: "accepted",
  rejected: "rejected",
  awaiting_better_image: "wants a better scan",
};

function verdictBadge(work) {
  const glyph = VERDICT_GLYPHS[work.verdict];
  if (!glyph) return null;
  return el("span", { class: `badge badge-${work.verdict}` }, [
    el("span", { class: "glyph", text: glyph, "aria-hidden": true }),
    el("span", { text: VERDICT_WORDS[work.verdict] || work.verdict }),
  ]);
}

/* The curator authorised a work list of a stated size, and a wired collection may
 * add to it. Labelled on every row rather than counted only in the summary: an
 * offered work is not what was asked for, and a grid that renders the two alike
 * invites accepting one as though it were. */
function provenanceBadge(work) {
  const offered = work.provenance === "offered";
  return el("span", { class: offered ? "badge badge-offered" : "badge" }, [
    el("span", { class: "glyph", text: offered ? "◈" : "◆", "aria-hidden": true }),
    el("span", { text: offered ? "offered" : "asked for" }),
  ]);
}

/* The picture for one instance, or what stands in for it.
 *
 * The card knows before it asks — the listing carries `preview_available` — so a
 * work whose picture was reclaimed never requests bytes that are not there. The
 * error handler is for the narrow race where the file goes away in between, and
 * for a museum's file that will not decode: the listing reports that one as
 * available, because nothing has read the bytes yet. */
function instanceImage(instance, alt) {
  if (!instance.preview_available) {
    return el("div", { class: "card-image" }, [absentImage(instance.preview_note)]);
  }
  const image = el("img", {
    src: `/api/candidate-images/${encodeURIComponent(instance.image_id)}/preview`,
    alt: alt || "",
    loading: "lazy",
  });
  image.addEventListener("error", () => {
    image.replaceWith(absentImage("Its picture could not be loaded just now."));
  });
  return el("div", { class: "card-image" }, [image]);
}

function instanceStateBadges(instance) {
  return [
    instance.rejected
      ? el("span", { class: "badge badge-refused" }, [
          el("span", { class: "glyph", text: "⊘", "aria-hidden": true }),
          el("span", { text: "turned down" }),
        ])
      : null,
    instance.is_selected
      ? el("span", { class: "badge badge-on_offer" }, [
          el("span", { class: "glyph", text: "★", "aria-hidden": true }),
          el("span", { text: "on offer" }),
        ])
      : null,
  ];
}

/* One alternate scan, with what a curator needs to choose between it and the
 * others: the picture, the size it would hang at, where it came from, and the
 * two things they can do about it. */
function instanceRow(instance, title, after) {
  const act = (path, body) =>
    guard(async () => {
      await api(path, { method: "POST", body: JSON.stringify(body || {}) });
      await after();
    });
  return el("li", { class: "alternate" }, [
    instanceImage(instance, ""),
    el("div", { class: "alternate-body" }, [
      el("div", { class: "card-footer" }, [fitBadge(instance, "size unrecorded"), ...instanceStateBadges(instance)]),
      facts([
        ["Provider", instance.provider],
        ["Confidence", instance.confidence.toFixed(2)],
        ["Rights", instance.rights_status],
        ["Why this one", instance.selection_rationale],
        // Shown as text rather than as a link. The URL comes from a museum this
        // product does not control, and a rendered anchor is one click from
        // navigating a curator's browser to an attacker-chosen address on a page
        // that otherwise touches nothing outside the LAN.
        ["Where it lives", instance.url],
      ]),
      instance.preview_note ? el("p", { class: "muted", text: instance.preview_note }) : null,
      el("div", { class: "row" }, [
        instance.rejected || instance.is_selected
          ? null
          : el("button", {
              class: "action quiet",
              type: "button",
              text: "Use this one",
              // Named by the work, never by its id. A screen reader announcing
              // "Use this scan for 8f2a-41c3…" names the one thing on the card
              // that identifies nothing, on a row whose whole purpose is
              // choosing between scans of a painting the curator can see.
              "aria-label": `Use this scan for ${title}`,
              onclick: () => act(`/api/candidate-images/${encodeURIComponent(instance.image_id)}/select`),
            }),
        instance.rejected
          ? null
          : el("button", {
              class: "action quiet",
              type: "button",
              text: "Turn it down",
              "aria-label": `Turn down this scan for ${title}`,
              onclick: () => act(`/api/candidate-images/${encodeURIComponent(instance.image_id)}/reject`),
            }),
      ]),
    ]),
  ]);
}

/* What a capped card is not showing, said out loud.
 *
 * Composed here rather than taken from the MCP surface's notice, which is the
 * same call `runSentence` made and for the same reason: that one names tool
 * calls in backticks and offers a caller an action. The figures are the part
 * that must not be written twice, and they are not — `held` and
 * `shows_every_choosable_instance` are the server's. */
function instancesNote(listing) {
  if (!listing.truncated) return null;
  const omitted = listing.held - listing.instances.length;
  return el("p", {
    class: "note",
    text: listing.shows_every_choosable_instance
      ? `This work holds ${listing.held} scans; ${omitted} already turned down are not shown. Every scan you can still choose is here.`
      : `This work holds ${listing.held} scans and ${omitted} are not shown, including some you could still choose. Turning down what is here is what brings the rest within reach.`,
  });
}

async function alternatesPanel(workId, after) {
  const listing = await api(`/api/candidates/${encodeURIComponent(workId)}/images`);
  if (!listing.instances.length) {
    return el("p", { class: "muted", text: "No scans were found for this work, so there is nothing to choose between." });
  }
  return el("div", { class: "stack" }, [
    instancesNote(listing),
    el("ul", { class: "alternates" }, listing.instances.map((instance) => instanceRow(instance, listing.work.title, after))),
  ]);
}

/* Why a card carries no picture — two states the producer distinguishes and this
 * client used to flatten into one sentence.
 *
 * `CandidateCardOut.shown` is null both when nothing was ever found and when the
 * curator turned every scan down, and its own docstring points at the pair that
 * tells them apart. Reading only `shown` told a curator "No scan was found for
 * this work" directly above a disclosure listing the scans they had just
 * rejected, beside a badge still reading "has an image" — because rejecting an
 * image deliberately does not rewrite `resolution_status`. Three parts of one
 * card disagreeing, and the MCP surface said the opposite for the same work.
 *
 * The badge half of that is settled: `RESOLUTION_WORDS` now says "the run found
 * an image", which is what the column always meant and is consistent with the
 * sentence below rather than contradicting it.
 *
 * **It names no way back, because there is none, and an earlier version of this
 * fix invented one.** It read "Restore one from the scans below to judge it
 * again", which was false three times over: every row in that panel renders its
 * controls as null once rejected, no restore endpoint exists, and
 * `discovery.select_image` refuses a rejected instance *on purpose* — its
 * docstring makes the refusal a requirement, so that a rejection survives the
 * next re-search. Inventing an instruction the product forbids is the same
 * defect this function exists to fix, so it is recorded rather than quietly
 * deleted.
 *
 * The sentence is `REASON_SENTENCES.all_rejected` rather than a second string
 * saying the same thing, so this state reads identically wherever a curator
 * meets it. */
function absentScanReason(card) {
  if (card.instances_held > 0 && card.instances_surviving === 0) {
    return REASON_SENTENCES.all_rejected;
  }
  return "No scan was found for this work.";
}

/* One proposed work, as the thing a curator decides about.
 *
 * `notice` is carried across a repaint rather than shown from a fresh fetch,
 * because it describes what the verdict just *did* — minting an artist who may
 * duplicate one already held — and that is not a property of the work anybody
 * could read back off it afterwards.
 *
 * `onVerdict` is how anything outside this card learns that one was recorded,
 * and it is deliberately required rather than defaulted to a no-op: a caller
 * that forgets it gets a TypeError on the first verdict, where a silent default
 * would leave the re-search offer quietly describing a page that had moved on —
 * which is the defect this argument exists to close. */
function candidateCard(card, notice, alternatesOpen = false, onVerdict) {
  const work = card.work;
  const node = el("li", { class: "card", "data-work": work.work_id });

  const repaint = async (message) => {
    const fresh = await api(`/api/candidates/${encodeURIComponent(work.work_id)}`);
    // Announced on every repaint rather than from the verdict buttons alone,
    // because this is the one path both ways of settling a work pass through:
    // the card's own Accept and Reject, and choosing or turning down a scan in
    // the alternates below, which reaches here as `after`.
    onVerdict(work.work_id, fresh.work.verdict);
    // The disclosure's state is carried over, because choosing between scans is
    // a sequence rather than one act: a curator turning one down is usually
    // about to turn down or choose another. Rebuilding the card closed would
    // collapse the list they are working in, on every click, and cost a second
    // fetch to get back to where they were.
    node.replaceWith(candidateCard(fresh, message, disclosure.open, onVerdict));
  };

  const reason = el("input", { type: "text", id: `reason-${work.work_id}` });
  const decide = (verdict) =>
    guard(async () => {
      const outcome = await api(`/api/candidates/${encodeURIComponent(work.work_id)}/verdict`, {
        method: "POST",
        body: JSON.stringify({ verdict, reason: reason.value || null }),
      });
      await repaint(outcome.notice);
    });

  const alternates = el("div", { class: "stack" }, [el("p", { class: "muted", text: "Loading this work's scans…" })]);
  // **"Scans", not "other scans", and the count is deliberately every scan the
  // work holds.** The panel below lists all of them — the one pictured on the
  // card included, because seeing which is currently selected is half of
  // choosing between them. Labelling that "Other scans (1)" promised a curator
  // something new behind a disclosure whose single entry was the picture they
  // were already looking at, which is a promise every single-scan work broke.
  // The count matches the panel's contents; making the *word* true was the fix,
  // because subtracting the shown scan from the number would have made the
  // summary disagree with what opening it reveals.
  const disclosure = el("details", {}, [
    el("summary", { text: `Scans (${card.instances_held})` }),
    alternates,
  ]);
  // Fetched when it is opened rather than with the grid: a thirty-work page
  // would otherwise carry up to twelve instances each, and a curator opens the
  // alternates for the few works whose first answer they doubt.
  disclosure.addEventListener("toggle", () => {
    if (disclosure.open) guard(async () => alternates.replaceChildren(await alternatesPanel(work.work_id, () => repaint(null))));
  });
  // Opening it here fires `toggle`, which is what fetches the list — so a
  // carried-over disclosure loads rather than restoring the placeholder.
  //
  // The order relative to the listener above does not matter, and the comment
  // here used to claim it did. `toggle` is dispatched asynchronously, so a
  // listener attached after the property is set still receives it; the mutation
  // sweep proved the claim false by swapping the two lines and watching every
  // test pass. Left in this order because it reads better, not because anything
  // depends on it.
  if (alternatesOpen) disclosure.open = true;

  node.append(
    card.shown ? instanceImage(card.shown, work.artist ? `${work.title}, by ${work.artist}` : work.title) : el("div", { class: "card-image" }, [absentImage(absentScanReason(card))]),
    el("div", { class: "card-body" }, [
      el("h3", { class: "card-title", text: work.title }),
      el("p", { class: "card-artist", text: work.artist || "Artist unrecorded" }),
      el("div", { class: "card-footer" }, [
        verdictBadge(work),
        provenanceBadge(work),
        resolutionBadge(work),
        reasonBadge(work),
        card.shown ? fitBadge(card.shown, "size unrecorded") : null,
      ]),
      el("p", { class: "card-meta", text: work.rationale }),
      // The picture is not the one a verdict would accept on, and saying so is
      // the difference between a curator understanding the refusal and being
      // surprised by it. Accepting really is refused in this state — the service
      // will not record a work with no primary source — so the card says which
      // action reaches the way out.
      card.shown && !card.shown_is_on_offer
        ? el("p", {
            class: "note",
            text: "No scan is on offer for this work. The picture is what was found, shown so you can judge it — accepting is refused until you choose one from the scans below.",
          })
        : null,
      notice ? el("p", { class: "note", text: notice }) : null,
      el("div", { class: "row" }, [
        el("div", { class: "field" }, [
          el("label", { for: `reason-${work.work_id}`, text: "Why (optional)" }),
          reason,
        ]),
        el("button", { class: "action", type: "button", text: "Accept", "aria-label": `Accept ${work.title}`, onclick: () => decide("accepted") }),
        el("button", { class: "action quiet", type: "button", text: "Reject", "aria-label": `Reject ${work.title}`, onclick: () => decide("rejected") }),
      ]),
      disclosure,
    ]),
  );
  return node;
}

/* The offer to look again, over the works currently waiting for a better scan.
 *
 * `waiting` is a function rather than the list itself, so the button reads the
 * set again at the moment it is clicked rather than closing over the one this
 * paint was built from. **A mutation sweep survives replacing that call with the
 * captured list, and that is expected rather than a gap to close**: the map is
 * only ever written by the callback that repaints this panel in the same breath,
 * so the two are equal on every path that exists today and no test can tell them
 * apart. It is kept because the failures either side of it are not the same
 * size — a stale count misinforms a curator, a stale list *spends*, and
 * `/api/runs/resolve` bills for exactly the ids in this body. Reading at click
 * time is what keeps that spend correct without it resting on the panel's
 * render bookkeeping being right, which is the coupling that produced the
 * defect this function was extracted to fix. */
function reSearchOffer(waiting) {
  const works = waiting();
  // Offered only when there is something to re-search. A button that spends
  // and would do nothing is worse than no button: it invites a curator to pay
  // for a run over an empty list.
  if (works.length === 0) return null;
  return el("div", { class: "panel" }, [
    el("h3", { text: "Scans you turned down" }),
    el("p", {
      class: "muted",
      // Says that nothing is looking, which is the fact a curator cannot
      // see. Rejecting a scan records a judgement; it does not start a
      // search, and a page that stayed silent would leave them waiting for
      // one that is never coming.
      text: `${works.length} ${works.length === 1 ? "work is" : "works are"} waiting for a better scan. Nothing is looking for one — a re-search is what looks, and it spends.`,
    }),
    el("div", { class: "row" }, [
      el("button", {
        class: "action",
        type: "button",
        text: "Look again for these",
        onclick: () =>
          guard(async () => {
            const run = await api("/api/runs/resolve", {
              method: "POST",
              body: JSON.stringify({ work_ids: waiting() }),
            });
            go("run", run.run_id);
          }),
      }),
    ]),
  ]);
}

/* The offered works, bucketed by the browse query that produced each.
 *
 * Keyed on `offered_for_artist`, which is the *run's* spelling of the artist —
 * the same string `proposed_artist` carries on the works the run named, so the
 * two halves of a group can be counted against each other below. The work's own
 * `artist` is the collection's attribution and is deliberately not used: it
 * differs, verbatim and on purpose.
 *
 * A work whose query is unknown buckets under `null` rather than being skipped.
 * Skipping would drop it off the page altogether — the review surface silently
 * showing fewer works than the run holds, which is a worse defect than the one
 * this grouping exists to fix. */
function offeredGroups(cards) {
  const groups = new Map();
  for (const card of cards) {
    const artist = card.work.offered_for_artist || null;
    if (!groups.has(artist)) {
      groups.set(artist, { artist, matched: card.work.offered_artist_matched, cards: [] });
    }
    groups.get(artist).cards.push(card);
  }
  return [...groups.values()];
}

/* What one offered group says, once, above its own works.
 *
 * `product-brief.md` requires a curator to be able to tell being offered one work
 * out of four hundred from being offered one out of one, and — as amended for
 * issue #95 — requires it said here rather than restated on every card.
 *
 * **Every number is counted from something the reader can see, or named as what
 * it is.** `shown` counts the cards actually rendered, so it cannot disagree with
 * the page the way a server-composed total did. `matched` is the collection's
 * holdings, stated as holdings and reconciled against the per-run bound in the
 * same breath — the old sentence put "one of 25 works it holds" beside twelve
 * cards and left the gap unexplained.
 *
 * **The first clause counts the unresolved works only, and that is not
 * pedantry.** An artist reaches this supplement by having *any* named work come
 * back unresolved, so they may well have others that resolved perfectly well.
 * "found an image for none of them" would be false for exactly those artists —
 * the same shape of false-on-the-page-that-shows-both claim this issue exists to
 * remove. When no such work is on the page the clause is omitted rather than
 * printed with a zero. */
function offeredGroupSentence(group, allCards) {
  const named = group.artist
    ? allCards.filter(
        (card) =>
          card.work.provenance !== "offered" &&
          card.work.artist === group.artist &&
          card.work.resolution_status === "unresolved",
      ).length
    : 0;
  const shown = group.cards.length;
  const matched = group.matched;
  const works = (n) => `${n} ${n === 1 ? "work" : "works"}`;

  const clauses = [];
  if (named > 0) clauses.push(`This run found no image for ${works(named)} it named by this artist.`);
  if (typeof matched !== "number") {
    // No holdings count recorded — say nothing about a total rather than guess
    // one, which is the failure this whole change is undoing.
    clauses.push(`The collection offered ${works(shown)} it holds by them.`);
  } else if (shown < matched) {
    // Says that these are a subset and stops there. Naming the per-run bound as
    // the *cause* of the gap is a claim this surface cannot support: a group also
    // comes up short when works were declined for rendering below the display
    // floor, and on a re-search page where the bound is never reached at all. The
    // reconciliation the requirement asks for is that the two numbers not appear
    // to disagree — which "what this run offered" delivers without inventing a
    // reason for the difference.
    clauses.push(`The collection holds ${works(matched)} by them; these ${shown} are what this run offered.`);
  } else {
    clauses.push(`These are all ${works(matched)} the collection holds by them.`);
  }
  return clauses.join(" ");
}

export async function viewReview(runId, generation) {
  const page = await fetchAllCandidates(runId);

  /* One answer to "which works are waiting for a better scan", held for as long
   * as this view is on screen.
   *
   * The grid repaints a card in place and leaves its neighbours alone — see
   * `candidateCard`, where that choice is argued — so a verdict changes one node
   * and nothing around it. Deriving the offer from `page.works` gave the screen
   * two answers to this question: the offer's, fixed at paint, and the grid's,
   * current. They diverge on a transition reachable from this very page, and the
   * offer is the one that spends. */
  const verdicts = new Map(page.works.map((card) => [card.work.work_id, card.work.verdict]));
  const isWaiting = (verdict) => verdict === "awaiting_better_image";
  const waiting = () => [...verdicts].filter(([, verdict]) => isWaiting(verdict)).map(([workId]) => workId);

  /* Always on the page, whether or not it holds anything.
   *
   * Two things need that. A run can arrive with nothing waiting and reach a work
   * waiting through the curator's own next click, so an offer built only when the
   * first paint found one could never appear. And a live region has to exist
   * *before* the content it announces is put into it — a `role="status"` element
   * created and filled in the same breath announces nothing, which is the usual
   * way this is got wrong. Empty, it is an empty div: measured at 0px high with
   * no margins, so it costs no space either.
   *
   * `status` rather than the error banner's `alert` because an offer appearing is
   * news, not an emergency: polite waits for a pause instead of interrupting. */
  const offer = el("div", { role: "status" });
  const paintOffer = () => {
    const panel = reSearchOffer(waiting);
    offer.replaceChildren(...(panel ? [panel] : []));
  };
  paintOffer();

  const noteVerdict = (workId, verdict) => {
    const was = isWaiting(verdicts.get(workId));
    verdicts.set(workId, verdict);
    // Repainted only when this work's *membership* moved — not merely when its
    // verdict did. The offer depends on nothing else, so accepting a work that
    // was never waiting leaves it word for word identical, and rewriting a live
    // region re-announces it: a curator working by screen reader would hear the
    // whole offer read out again for a verdict that did not concern it.
    // Comparing verdicts instead of membership looks equivalent and is not; the
    // test that accepts an unrelated work is what says so.
    if (was !== isWaiting(verdict)) paintOffer();
  };

  const gridOf = (cards) => el("ul", { class: "grid" }, cards.map((card) => candidateCard(card, null, false, noteVerdict)));

  /* The works the run named, then the collection's offers under their own
   * queries. Two sections rather than one list, because the sentence each offer
   * group carries is about the group — putting it anywhere else is what this
   * change is undoing.
   *
   * The offers are gathered here rather than left in arrival order, which
   * interleaves artists: `_round_robin` takes one work per artist per pass so a
   * bound of twelve reaches every artist rather than filling up on the first.
   * That spread is a choice about *which* works are offered and survives being
   * displayed in any order — its own docstring says the spread is the point, not
   * the order within a facet. */
  const offered = page.works.filter((card) => card.work.provenance === "offered");
  const named = page.works.filter((card) => card.work.provenance !== "offered");

  const panels = [
    // Back to the run rather than to a destination: Review is opened from one
    // particular search and the way out is that search, which is a screen and
    // not a place in the navigation.
    el("p", {}, [
      el("button", { class: "action quiet", type: "button", text: "← The search", onclick: () => go("run", runId) }),
    ]),
    el("h2", { text: page.run.intent || "Re-search" }),
    // The catalogue grid's own helper: `fetchAllCandidates` returns the
    // `{works, total}` shape it takes, and a second copy of the sentence is how
    // one grid comes to word truncation differently from the other.
    shortfallNote(page),
    offer,
    page.works.length ? null : el("p", { class: "muted", text: "This run settled on no works, so there is nothing to review." }),
    named.length ? gridOf(named) : null,
    // Each group in its own element rather than as three loose siblings. The
    // requirement is an *association* — this sentence belongs to these works —
    // and flat siblings leave that expressible only by document order, which no
    // assertion can hold and a screen reader does not convey. It also gives the
    // browser tests something to scope to: page-wide text matching passes on two
    // groups whose sentences have been swapped.
    ...offeredGroups(offered).map((group) =>
      el("section", {
        class: "offer-group",
        // The query, as an attribute rather than only as heading prose. A card's
        // own artist is the collection's attribution and differs from the query
        // on purpose, so matching a group by visible text finds the wrong one —
        // which is exactly what happened to the test written that way.
        "data-offer-artist": group.artist,
        "aria-label": group.artist ? `Offered by the collection: ${group.artist}` : "Offered by the collection",
      }, [
        el("h3", { text: group.artist ? `Offered by the collection — ${group.artist}` : "Offered by the collection" }),
        el("p", { class: "muted", text: offeredGroupSentence(group, page.works) }),
        gridOf(group.cards),
      ]),
    ),
  ];
  render(generation, ...panels);
}
