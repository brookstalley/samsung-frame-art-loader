/* Work — one work at full size, with its sources, renditions and mat history.
 *
 * Contextual: reached from a tile in Collection, a tile on a Wall, or a row in
 * Review, and it **returns to the destination it was opened from**. That is the
 * requirement `information-architecture.md` states under Back/escape, and the
 * back control here reads it off the address rather than naming a fixed parent —
 * this screen's route out used to be "← All works" whatever route in had been
 * taken.
 */

import { api } from "../core/api.js";
import { facts, fitBadge, sourceBadge, statusBadge, table } from "../core/badges.js";
import { el, render } from "../core/render.js";
import { backLink } from "../core/router.js";

export async function viewWork(artworkId, generation) {
  const detail = await api(`/api/works/${encodeURIComponent(artworkId)}`);
  const work = detail.work;
  const image = work.image.available
    ? el("img", {
        class: "detail-image",
        src: `/api/works/${encodeURIComponent(work.artwork_id)}/thumbnail`,
        alt: work.artist ? `${work.title}, by ${work.artist.name}` : work.title,
      })
    : el("p", { class: "note", text: work.image.note || "No image held." });

  const panels = [
    el("p", {}, [backLink()]),
    el("h2", { text: work.title }),
    el("div", { class: "panel" }, [
      image,
      el("div", { class: "card-footer" }, [statusBadge(work), fitBadge(work), sourceBadge(work)]),
      work.fit_note ? el("p", { class: "muted", text: work.fit_note }) : null,
    ]),
    el("div", { class: "panel" }, [
      el("h3", { text: "The work" }),
      facts([
        ["Artist", work.artist ? work.artist.name : null],
        ["Nationality", work.artist ? work.artist.nationality : null],
        ["Lifespan", work.artist ? work.artist.lifespan_text : null],
        ["Date", work.date_created],
        ["Medium", work.medium],
        ["Dimensions", work.dimensions],
        ["Rights", work.rights],
        ["Status", work.status],
        ["Description", work.description],
      ]),
    ]),
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

  panels.push(
    el("div", { class: "panel" }, [
      el("h3", { text: "Mat colours" }),
      detail.mat_colors.length
        ? table(
            "Superseded choices are kept, so a worse pick can be answered for and reversed.",
            ["Colour", "How chosen", "State", "Reason"],
            detail.mat_colors.map((m) => [
              m.hex_rgb,
              m.method,
              m.is_current ? "● current" : "superseded",
              m.reason,
            ]),
          )
        : el("p", { class: "muted", text: "No mat colour has been chosen for this work." }),
    ]),
  );

  render(generation, ...panels);
}
