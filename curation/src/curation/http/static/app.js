/* The browser client. It renders what /api/* returns and decides nothing.
 *
 * No framework and no build step, deliberately: this is one operator's tool on
 * a private network, and a toolchain here would be a second thing to keep
 * running on a Pi for no gain a curator can see.
 *
 * TEXT IS SET WITH textContent, NEVER innerHTML. Titles, descriptions and
 * provider names come from museum sites this product does not control, and
 * `<img src=x onerror=...>` inside a work's title is the whole of that attack.
 * The one exception would be description markup, which the catalogue reduces to
 * <i>/<b> at ingest — and it is not taken here either, because a UI that starts
 * trusting one field is a UI someone extends to the next one.
 */

/* `painted` is what the run view last put on the page, so a poll that finds
 * nothing changed can leave the DOM — and the focus in it — alone. Cleared on
 * every navigation, because leaving a view and coming back must repaint even
 * when the data is identical: the DOM it describes is gone by then. */
const state = { view: "works", detailId: null, nav: 0, poll: 0, painted: null };

/* -- plumbing -------------------------------------------------------------- */

async function api(path, options) {
  const response = await fetch(path, {
    headers: { "content-type": "application/json" },
    ...options,
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    // The service layer writes its refusals to be shown; anything else is a
    // fault, and saying which is which beats one apologetic sentence for both.
    const message =
      body && body.error
        ? body.error
        : `The server answered ${response.status} for ${path}.`;
    throw new Error(message);
  }
  return body;
}

/* The catalogue caps a page at 100 (MAX_LIST_LIMIT), and the design target is
 * hundreds of works — so both the grid and the theme picker page through to the
 * end rather than showing the first hundred. The picker is the one that made
 * this necessary: a truncated grid is a visible short list, but a truncated
 * picker means a curator simply cannot put work 101 in a theme, and is told
 * nothing about why.
 *
 * `PAGE_CEILING` is a runaway guard, not a policy. If it is ever hit the caller
 * reports how many were left out, because a cap nobody mentions is the silent
 * omission this product exists to refuse. */
const PAGE_SIZE = 100;
const PAGE_CEILING = 50;

async function fetchAllWorks() {
  const works = [];
  let total = 0;
  let truncated = false;
  for (let page = 0; page < PAGE_CEILING; page += 1) {
    const body = await api(`/api/works?limit=${PAGE_SIZE}&offset=${works.length}`);
    total = body.total;
    works.push(...body.works);
    // The stopping condition is what actually arrived, not what the server says
    // is left. A page that reports more while carrying nothing makes no
    // progress — the offset is derived from what came back, so asking again
    // sends the identical request. `PAGE_CEILING` would stop it either way, so
    // what this saves is forty-nine pointless round trips rather than a hang.
    if (!body.truncated || body.works.length === 0) return { works, total, truncated };
    truncated = true;
  }
  return { works, total, truncated: works.length < total };
}

function showError(message) {
  const box = document.getElementById("error");
  box.textContent = message;
  box.hidden = false;
}

function clearError() {
  const box = document.getElementById("error");
  box.hidden = true;
  box.textContent = "";
}

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "text") node.textContent = value;
    else if (key === "class") node.className = value;
    else if (key === "onclick") node.addEventListener("click", value);
    else node.setAttribute(key, value === true ? "" : String(value));
  }
  for (const child of [].concat(children)) {
    if (child) node.append(child);
  }
  return node;
}

/* Write a view's nodes to the page, unless the curator has moved on.
 *
 * `generation` is `state.nav` as it stood when this paint began, and passing it
 * is not ceremony: every view here awaits at least one request and three page
 * through up to fifty, so a paint routinely completes after the view it belongs
 * to is gone — and `replaceChildren` would put it over whatever replaced it,
 * with the tab highlight and the fragment both naming the other view. A stale
 * screen that looks live is the class of defect this client has shipped three
 * times.
 *
 * Taken as an argument rather than read from a shared variable, which is what
 * this was first written as. A module-level "currently painting" is overwritten
 * by the LATER navigation, so the abandoned paint reads the generation that
 * superseded it and lands anyway — the guard passes and does nothing. A test
 * caught that; the value has to travel with the paint that captured it.
 *
 * It is also why the argument comes first and is required: a view that forgets
 * it passes a DOM node where a number belongs, and the check below throws
 * instead of silently painting whatever it was handed. */
function render(generation, ...nodes) {
  if (typeof generation !== "number") {
    throw new TypeError("render() takes the navigation generation first; a view that omits it cannot be superseded.");
  }
  if (generation !== state.nav) return;
  const view = document.getElementById("view");
  // Filtered, not passed straight through: `replaceChildren` coerces a null to
  // the *string* "null" and puts it on the page, so an omitted optional panel
  // renders as the word null rather than as nothing.
  view.replaceChildren(...nodes.filter(Boolean));
}

/* -- shared pieces --------------------------------------------------------- */

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
 * A badge always carries a glyph and a word beside its colour, so the state
 * survives greyscale, colour blindness, and a dimmed room.
 *
 * One function for a held work and for a candidate scan. Both carry the same
 * `fit`/`fit_note` pair and the same rule — a thing whose dimensions nobody
 * recorded must not read like a thing known to be small — so the only real
 * difference is what to call the absence, and that is the argument. Two copies
 * were written first, and their comment claimed "same rule, different shape"
 * when the shapes were identical; the size wording then lived in two places on
 * the one surface whose whole justification is stating it. */
function fitBadge(sized, absentWord = "no size known") {
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

function sourceBadge(work) {
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
function statusBadge(work) {
  if (work.status === "accepted") return null;
  // Its own class, not `below_floor`'s: catalogue status and display fit are
  // unrelated axes, and sharing a class would make an archived work and a
  // too-small work paint identically.
  return el("span", { class: "badge badge-archived" }, [
    el("span", { class: "glyph", text: "⊘", "aria-hidden": true }),
    el("span", { text: work.status }),
  ]);
}

function absentImage(note) {
  return el("div", { class: "card-image-absent", text: note || "No image held." });
}

function cardImage(work) {
  if (!work.image.available) {
    return el("div", { class: "card-image" }, [absentImage(work.image.note)]);
  }
  const image = el("img", {
    src: `/api/works/${encodeURIComponent(work.artwork_id)}/thumbnail`,
    // Empty on purpose. The button around it is already named "Open <title>",
    // and the card's own text carries artist, date and medium — describing the
    // picture here as well would make every card announce its title twice.
    alt: "",
    loading: "lazy",
  });
  // Availability was true when the listing was built, and a file can go away
  // between then and the fetch. Without this the tile renders as a blank box —
  // silent, which is the failure mode this whole product exists to refuse.
  image.addEventListener("error", () => {
    image.replaceWith(absentImage("Its image could not be loaded just now."));
  });
  return el(
    "button",
    {
      class: "card-image",
      type: "button",
      "aria-label": `Open ${work.title}`,
      onclick: () => go("work", work.artwork_id),
    },
    [image],
  );
}

function workCard(work) {
  return el("li", { class: "card" }, [
    cardImage(work),
    el("div", { class: "card-body" }, [
      el("h3", { class: "card-title" }, [
        el("button", { type: "button", text: work.title, onclick: () => go("work", work.artwork_id) }),
      ]),
      el("p", { class: "card-artist", text: work.artist ? work.artist.name : "Artist unrecorded" }),
      el("p", {
        class: "card-meta",
        text: [work.date_created, work.medium].filter(Boolean).join(" · ") || " ",
      }),
      el("div", { class: "card-footer" }, [statusBadge(work), fitBadge(work), sourceBadge(work)]),
    ]),
  ]);
}

function facts(pairs) {
  const list = el("dl", { class: "facts" });
  for (const [term, value] of pairs) {
    if (value === null || value === undefined || value === "") continue;
    list.append(el("dt", { text: term }), el("dd", { text: String(value) }));
  }
  return list;
}

function table(caption, headers, rows) {
  return el("table", {}, [
    el("caption", { text: caption }),
    el("thead", {}, [el("tr", {}, headers.map((h) => el("th", { scope: "col", text: h })))]),
    el("tbody", {}, rows.map((cells) => el("tr", {}, cells.map((c) => (c instanceof Node ? el("td", {}, [c]) : el("td", { text: c === null || c === undefined ? "—" : String(c) }))))),
    ),
  ]);
}

/* -- views ----------------------------------------------------------------- */

async function viewWorks(generation) {
  const page = await fetchAllWorks();
  const heading = el("h2", {
    text: page.works.length === page.total ? `${page.total} works` : `${page.works.length} of ${page.total} works`,
  });
  const note = shortfallNote(page);
  render(generation, heading, note, el("ul", { class: "grid" }, page.works.map(workCard)));
}

/* Only ever shown when the runaway guard actually bit. Named rather than
 * silent: a list that stops short without saying so is indistinguishable from a
 * catalogue that holds no more. */
function shortfallNote(page) {
  if (page.works.length >= page.total) return null;
  return el("p", {
    class: "note",
    text: `Showing ${page.works.length} of ${page.total}; ${page.total - page.works.length} more are held and are not on this page.`,
  });
}

async function viewWork(artworkId, generation) {
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
    el("p", {}, [el("button", { class: "action quiet", type: "button", text: "← All works", onclick: () => go("works") })]),
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

async function viewThemes(generation) {
  const [themes, works] = await Promise.all([api("/api/themes"), fetchAllWorks()]);

  const name = el("input", { type: "text", id: "new-theme-name", required: true });
  const create = el("div", { class: "panel" }, [
    el("h3", { text: "New theme" }),
    el("div", { class: "row" }, [
      el("div", { class: "field" }, [el("label", { for: "new-theme-name", text: "Name" }), name]),
      el("button", {
        class: "action",
        type: "button",
        text: "Create",
        onclick: () =>
          guard(async () => {
            await api("/api/themes", { method: "POST", body: JSON.stringify({ name: name.value }) });
            await refresh();
          }),
      }),
    ]),
  ]);

  const panels = [el("h2", { text: "Themes" }), create];

  if (!themes.themes.length) {
    panels.push(el("p", { class: "muted", text: "No themes yet. Create one, then add works to it." }));
  }

  const shortfall = shortfallNote(works);
  if (shortfall) panels.push(shortfall);

  for (const theme of themes.themes) {
    panels.push(themePanel(theme, works.works));
  }
  render(generation, ...panels);
}

function themePanel(theme, allWorks) {
  const picker = el("select", { id: `add-${theme.theme_id}` });
  for (const work of allWorks) {
    picker.append(
      el("option", {
        value: work.artwork_id,
        text: work.artist ? `${work.title} — ${work.artist.name}` : work.title,
      }),
    );
  }

  const body = el("div", { class: "stack" }, [el("p", { class: "muted", text: "Loading works…" })]);

  const refreshMembers = async () => {
    const detail = await api(`/api/themes/${encodeURIComponent(theme.theme_id)}`);
    body.replaceChildren(memberList(theme.theme_id, detail.works, refreshMembers));
  };
  guard(refreshMembers);

  return el("div", { class: "panel" }, [
    el("h3", {}, [
      el("span", { text: theme.name }),
      // Active state carries a glyph and the word beside any colour.
      theme.is_active
        ? el("span", { class: "badge", style: "margin-left: 0.5rem" }, [
            el("span", { class: "glyph", text: "●", "aria-hidden": true }),
            el("span", { text: "on the wall" }),
          ])
        : null,
    ]),
    theme.description ? el("p", { class: "muted", text: theme.description }) : null,
    el("div", { class: "row" }, [
      el("div", { class: "field" }, [
        el("label", { for: `add-${theme.theme_id}`, text: "Add a work" }),
        picker,
      ]),
      el("button", {
        class: "action quiet",
        type: "button",
        text: "Add",
        onclick: () =>
          guard(async () => {
            await api(`/api/themes/${encodeURIComponent(theme.theme_id)}/works`, {
              method: "POST",
              body: JSON.stringify({ artwork_id: picker.value }),
            });
            await refreshMembers();
          }),
      }),
      theme.is_active
        ? null
        : el("button", {
            class: "action",
            type: "button",
            text: "Put on the wall",
            onclick: () =>
              guard(async () => {
                await api(`/api/themes/${encodeURIComponent(theme.theme_id)}/activate`, { method: "POST" });
                go("manifest");
              }),
          }),
    ]),
    body,
  ]);
}

function memberList(themeId, works, after) {
  if (!works.length) {
    return el("p", { class: "muted", text: "This theme holds no works yet." });
  }
  const rows = works.map((work, index) => {
    const move = (position) =>
      guard(async () => {
        await api(
          `/api/themes/${encodeURIComponent(themeId)}/works/${encodeURIComponent(work.artwork_id)}/position`,
          { method: "POST", body: JSON.stringify({ position }) },
        );
        await after();
      });
    const controls = el("div", { class: "row" }, [
      el("button", {
        class: "action quiet",
        type: "button",
        text: "↑",
        "aria-label": `Move ${work.title} earlier`,
        disabled: index === 0,
        onclick: () => move(index - 1),
      }),
      el("button", {
        class: "action quiet",
        type: "button",
        text: "↓",
        "aria-label": `Move ${work.title} later`,
        disabled: index === works.length - 1,
        onclick: () => move(index + 1),
      }),
      el("button", {
        class: "action quiet",
        type: "button",
        text: "Remove",
        "aria-label": `Remove ${work.title} from this theme`,
        onclick: () =>
          guard(async () => {
            await api(
              `/api/themes/${encodeURIComponent(themeId)}/works/${encodeURIComponent(work.artwork_id)}`,
              { method: "DELETE" },
            );
            await after();
          }),
      }),
    ]);
    return [String(index + 1), work.title, work.artist ? work.artist.name : "—", fitBadge(work), controls];
  });
  return table(
    "In curated order. Position decides what the wall shows first.",
    // The last column is named rather than left blank: an empty `th` is
    // announced as an empty column header, which tells a screen-reader user
    // nothing about the three buttons in every row beneath it.
    ["#", "Title", "Artist", "Size on the wall", "Order and removal"],
    rows,
  );
}

async function viewManifest(generation) {
  const manifest = await api("/api/manifest");
  const panels = [
    el("h2", { text: `On the wall: ${manifest.theme.name}` }),
    el("p", { class: "note", text: manifest.summary }),
    el("div", { class: "panel" }, [
      el("h3", { text: `Showing (${manifest.entries.length})` }),
      manifest.entries.length
        ? table(
            "Every work the display plane is being asked to show, in order.",
            ["Title", "Artist", "Render"],
            manifest.entries.map((e) => [e.title, e.artist, e.render_path]),
          )
        : el("p", { class: "muted", text: "Nothing in this theme is currently displayable." }),
    ]),
    el("div", { class: "panel" }, [
      // Never omitted when empty: a section that appeared only on trouble would
      // train a reader to take its absence as "everything is fine".
      el("h3", { text: `Not showing (${manifest.exclusions.length})` }),
      manifest.exclusions.length
        ? table(
            "Every work this theme holds that is not on the wall, and exactly why.",
            ["Title", "Reason", "What is missing"],
            manifest.exclusions.map((x) => [x.title, x.reason, x.detail]),
          )
        : el("p", { class: "muted", text: "Every work in this theme reached the wall." }),
    ]),
    el("div", { class: "panel" }, [
      el("h3", { text: "How it rotates" }),
      facts([
        ["Interval", `${manifest.rotation_interval_seconds} seconds`],
        ["Order", manifest.shuffle ? "shuffled" : "as curated"],
        ["Directive sequence", manifest.directive_sequence],
        ["Pinned work", manifest.pinned_work_id],
      ]),
    ]),
  ];
  render(generation, ...panels);
}

/* The display plane's own report, whatever it chose to put in it.
 *
 * Rendered generically rather than as named rows, and that is the design rather
 * than laziness: `reported_at` is the only key the observability strategy makes
 * contract, and everything else is explicitly the writer's to shape. Naming TV
 * connectivity and panel state here would invent a second contract that plane
 * never agreed to — and a writer that spelled one differently would drop off the
 * panel in silence, which is the failure the one named key exists to prevent.
 *
 * So whatever arrives is shown. That is what gives the failure table's TV, panel
 * and last-error rows a reader at all. */
function reportedFacts(reported) {
  if (!reported) return null;
  const pairs = Object.entries(reported).map(([key, value]) => [
    key,
    // Objects and arrays would reach `facts` as "[object Object]", which is a
    // field displayed and unreadable — worse than one omitted, because it looks
    // like the panel is working.
    value !== null && typeof value === "object" ? JSON.stringify(value) : value,
  ]);
  return pairs.length ? facts(pairs) : null;
}

async function viewHealth(generation) {
  const health = await api("/api/health");
  const box = health.artwork_box;
  render(
    generation,
    el("h2", { text: "Health" }),
    el("div", { class: "panel" }, [
      el("h3", { text: "The display plane" }),
      // An observation with its age, never a verdict. A green dot computed from
      // a file that may simply be young is how a health surface starts lying.
      el("p", { text: health.heartbeat.description }),
      facts([
        ["Heartbeat file", health.heartbeat.path],
        ["Last reported", health.heartbeat.reported_at],
        // The exact figure beside the sentence's plain-language one. Not the
        // same fact twice in worse units: the sentence is what a curator reads,
        // and this is what an operator compares against the 60-second interval.
        ["Age", health.heartbeat.age_seconds === null ? null : `${health.heartbeat.age_seconds.toFixed(0)} seconds`],
        ["Problem", health.heartbeat.problem],
      ]),
      health.heartbeat.absent
        ? el("p", {
            class: "muted",
            // States what absent *means*, not why it is absent. "The display
            // plane has not been built yet" would have been true the day this
            // was written and wrong the day that plane ships, with nothing to
            // catch it — a page asserting a fact about the project rather than
            // reporting one about the file in front of it.
            text: "Nothing has ever written a heartbeat here. Where the display plane is not running, that is the correct reading rather than a fault.",
          })
        : null,
      health.heartbeat.reported ? el("h4", { text: "What it reported" }) : null,
      reportedFacts(health.heartbeat.reported),
    ]),
    el("div", { class: "panel" }, [
      el("h3", { text: "The backup" }),
      el("p", { text: health.backup.description }),
      facts([
        ["Backup record", health.backup.path],
        ["Last completed", health.backup.completed_at],
        ["Age", health.backup.age_seconds === null ? null : `${health.backup.age_seconds.toFixed(0)} seconds`],
        ["Problem", health.backup.problem],
      ]),
      health.backup.absent
        ? el("p", {
            class: "muted",
            // Says what the catalogue is worth and what an absent record means,
            // and deliberately stops there. "The backup job has not been built
            // yet" would be a claim about the project rather than about the file
            // in front of it, and would be wrong the day that job ships with
            // nothing to catch it — the same trap the heartbeat's note avoids.
            text: "No backup has recorded itself here. The catalogue is the irreplaceable asset — the images can all be fetched again — so this is the reading to watch.",
          })
        : null,
      health.backup.reported ? el("h4", { text: "What it recorded" }) : null,
      reportedFacts(health.backup.reported),
    ]),
    el("div", { class: "panel" }, [
      el("h3", { text: "This deployment's geometry" }),
      el("p", {
        class: "muted",
        text: "The space a work is rendered into on this television, after the mat. Every size shown in the grid is judged against it.",
      }),
      facts([
        ["Artwork box", `${box.width} × ${box.height} px`],
        ["Scale", `${box.pixels_per_inch.toFixed(1)} pixels per inch on the wall`],
        ["On the wall", `${(box.width / box.pixels_per_inch).toFixed(1)}″ × ${(box.height / box.pixels_per_inch).toFixed(1)}″`],
        ["Resolution floor", `${box.floor_inches}″ on the long edge`],
      ]),
    ]),
  );
}

/* -- discovery ------------------------------------------------------------- */

/* Which kind of nothing an unresolved work came back with, in words a curator
 * acts on. The enum values are diagnostic labels; only one of them ("not held")
 * suggests the work may not exist, and a screen showing the raw value leaves
 * that distinction to be guessed.
 *
 * Every member of UnresolvedReason must appear here — a test reads this map and
 * the enum and fails when they disagree, so a sixth reason arrives as a failure
 * rather than as a raw token on a card. */
const REASON_SENTENCES = {
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

function reasonBadge(work) {
  if (!work.unresolved_reason) return null;
  const value = work.unresolved_reason;
  return el("span", { class: "badge badge-unknown", title: REASON_SENTENCES[value] || "" }, [
    el("span", { class: "glyph", text: "▲", "aria-hidden": true }),
    el("span", { text: REASON_WORDS[value] || value }),
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

const RESOLUTION_GLYPHS = { resolved: "●", unresolved: "▲", pending: "◌" };
const RESOLUTION_WORDS = { resolved: "has an image", unresolved: "no image", pending: "not looked up" };

function resolutionBadge(work) {
  const status = work.resolution_status;
  return el("span", { class: `badge badge-${status}` }, [
    el("span", { class: "glyph", text: RESOLUTION_GLYPHS[status] || "●", "aria-hidden": true }),
    el("span", { text: RESOLUTION_WORDS[status] || status }),
  ]);
}

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
/* An if-chain rather than an object literal like the badge maps above, and the
 * asymmetry is a decision rather than an oversight: several of these branches
 * read the tally, the run kind and whether image resolution is wired, so a map
 * of bare strings could not hold them. The cost is that the checker which reads
 * those maps cannot parse this, so `test_every_run_status_is_named_in_the_client`
 * takes the weaker form of asserting each status value appears here at all —
 * enough to fail when a tenth state is added, which is the property wanted. */
function runSentence(view) {
  const run = view.run;
  const tally = view.tally;
  if (run.status === "resolving_works") {
    return "Working out which works match the intent.";
  }
  if (run.status === "awaiting_approval") {
    return `This run proposed ${tally.proposed} works, which is more than the threshold, so it stopped to ask. Nothing further is spent until you decide.`;
  }
  if (run.status === "resolving_images") {
    if (!view.image_resolution_available) {
      return `There are ${tally.proposed} works to find images for, but no image provider is configured in this deployment, so the run will stay here. Cancel it when you are done reading it.`;
    }
    if (run.kind === "resolve") {
      return `Looking again for images of the ${tally.total} works this re-search covers.`;
    }
    return `The work list of ${tally.proposed} works is settled, and the run is looking for an image of each.`;
  }
  if (run.status === "completed") {
    let sentence =
      run.kind === "resolve"
        ? `This re-search finished: ${tally.resolved} of the ${tally.total} works it covers have an image.`
        : `This run finished: ${tally.resolved_proposals} of ${tally.proposed} works it was asked for have an image.`;
    if (run.kind !== "resolve" && tally.offered) {
      sentence += ` Separately, the collection offered ${tally.offered} more works by artists this run named but could not confirm. They are labelled below and are not what was asked for.`;
    }
    if (tally.unresolved) {
      sentence += ` ${tally.unresolved} could not be matched to any image and are reported rather than dropped — each says which kind of nothing below.`;
    }
    if (tally.pending) {
      // Held apart from unresolved deliberately. "We looked and it is not
      // there" and "we could not look" lead to opposite actions, and merging
      // them tells a curator their painting does not exist because a museum was
      // briefly unreachable.
      sentence += ` ${tally.pending} could not be looked up at all — the image provider was unreachable for them, which says nothing about whether they exist.`;
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

async function viewDiscovery(generation) {
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

  const panels = [el("h2", { text: "Discovery" }), entry];

  if (!runs.runs.length) {
    panels.push(el("p", { class: "muted", text: "No searches yet. Ask for something above." }));
  } else {
    panels.push(
      el("div", { class: "panel" }, [
        el("h3", { text: `Searches (${runs.count})` }),
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

/* Slow enough not to hammer a Pi, fast enough that a curator watching a run does
 * not wonder whether the page is live. The server answers immediately rather
 * than holding the request open, so this interval is the whole of the latency. */
const RUN_POLL_MS = 2000;

async function viewRun(runId, generation) {
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
    // One blip must not end the watch. Without this the throw leaves the last
    // paint on screen looking current, `guard` writes a message naming a URL,
    // and no further poll is ever scheduled — so a curator watching a live run
    // through a single 502 is left with a stale page that never recovers and
    // never says it stopped. Re-arm first, then re-throw so the message is
    // still shown: the next tick repaints and clears it if the blip has passed.
    scheduleRunPoll(runId, pollGeneration);
    throw failure;
  }
  if (state.poll !== pollGeneration) return;
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
    el("p", {}, [
      el("button", { class: "action quiet", type: "button", text: "← All searches", onclick: () => go("discovery") }),
    ]),
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
            "Every work this run holds. Works the collection offered are labelled: they are by an artist the run named, not the works it asked for.",
            ["Title", "Artist", "Where it came from", "Image", "Why the run named it"],
            view.works.map((work) => [
              work.title,
              work.artist || "—",
              provenanceBadge(work),
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

/* -- review ---------------------------------------------------------------- */

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
 * meets it.
 *
 * **What is deliberately NOT changed here**: the badge beside this still reads
 * "has an image", because `resolution_status` records what the *run* found and
 * rejecting an image deliberately does not rewrite it. That is a true statement
 * about the run and a confusing one beside this sentence, and reconciling them
 * means deciding whether the badge describes the run or the card — a product
 * question, not a rendering one. Left as it is, knowingly. */
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
 * could read back off it afterwards. */
function candidateCard(card, notice, alternatesOpen = false) {
  const work = card.work;
  const node = el("li", { class: "card", "data-work": work.work_id });

  const repaint = async (message) => {
    const fresh = await api(`/api/candidates/${encodeURIComponent(work.work_id)}`);
    // The disclosure's state is carried over, because choosing between scans is
    // a sequence rather than one act: a curator turning one down is usually
    // about to turn down or choose another. Rebuilding the card closed would
    // collapse the list they are working in, on every click, and cost a second
    // fetch to get back to where they were.
    node.replaceWith(candidateCard(fresh, message, disclosure.open));
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

/* Every work a run holds, paged through to the end.
 *
 * No `limit` is sent, so the server's own default and cap govern and the client
 * holds no copy of either. Asking for the cap explicitly would put the number in
 * two places, and the day the service lowered it the grid would ask for more
 * than it allows and be refused outright. */
async function fetchAllCandidates(runId) {
  const works = [];
  let run = null;
  let total = 0;
  for (let page = 0; page < PAGE_CEILING; page += 1) {
    const body = await api(`/api/runs/${encodeURIComponent(runId)}/candidates?offset=${works.length}`);
    run = body.run;
    total = body.total;
    works.push(...body.works);
    // Same stopping condition as `fetchAllWorks`, and the same reason: a page
    // reporting more while carrying nothing makes no progress, so asking again
    // sends the identical request. The ceiling bounds it regardless; this is
    // what keeps a misbehaving page from costing fifty round trips.
    if (!body.truncated || body.works.length === 0) break;
  }
  return { run, works, total };
}

async function viewReview(runId, generation) {
  const page = await fetchAllCandidates(runId);
  const wanting = page.works.filter((card) => card.work.verdict === "awaiting_better_image");

  const grid = el("ul", { class: "grid" }, page.works.map((card) => candidateCard(card, null)));

  const panels = [
    el("p", {}, [
      el("button", { class: "action quiet", type: "button", text: "← The search", onclick: () => go("run", runId) }),
    ]),
    el("h2", { text: page.run.intent || "Re-search" }),
    // The catalogue grid's own helper: `fetchAllCandidates` returns the
    // `{works, total}` shape it takes, and a second copy of the sentence is how
    // one grid comes to word truncation differently from the other.
    shortfallNote(page),
    // Offered only when there is something to re-search. A button that spends
    // and would do nothing is worse than no button: it invites a curator to pay
    // for a run over an empty list.
    wanting.length
      ? el("div", { class: "panel" }, [
          el("h3", { text: "Scans you turned down" }),
          el("p", {
            class: "muted",
            // Says that nothing is looking, which is the fact a curator cannot
            // see. Rejecting a scan records a judgement; it does not start a
            // search, and a page that stayed silent would leave them waiting for
            // one that is never coming.
            text: `${wanting.length} ${wanting.length === 1 ? "work is" : "works are"} waiting for a better scan. Nothing is looking for one — a re-search is what looks, and it spends.`,
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
                    body: JSON.stringify({ work_ids: wanting.map((card) => card.work.work_id) }),
                  });
                  go("run", run.run_id);
                }),
            }),
          ]),
        ])
      : null,
    page.works.length ? grid : el("p", { class: "muted", text: "This run settled on no works, so there is nothing to review." }),
  ];
  render(generation, ...panels);
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

/* -- routing --------------------------------------------------------------- */

const VIEWS = { works: viewWorks, discovery: viewDiscovery, themes: viewThemes, manifest: viewManifest, health: viewHealth };

/* The views that address one thing and carry its id in the fragment. Held as a
 * map rather than as a chain of comparisons about which view is which: the
 * dispatch, the fragment and the tab highlight all read it, and three
 * hand-written conditions are three chances for them to disagree about the same
 * view. `tab` is which section stays lit while a detail view is open. */
const DETAIL_VIEWS = {
  work: { render: viewWork, tab: "works" },
  run: { render: viewRun, tab: "discovery" },
  // Keyed by the run whose works are being judged, not by a work: a curator
  // reviews a run's output as a set, and a per-work address would make the grid
  // unreachable by URL.
  review: { render: viewReview, tab: "discovery" },
};

async function guard(work) {
  try {
    await work();
    clearError();
  } catch (failure) {
    showError(failure.message);
  }
}

function go(view, detailId = null) {
  state.view = view;
  state.detailId = detailId;
  // Leaving a view invalidates any refresh it had scheduled, so a run page left
  // open does not keep repainting behind whatever replaced it — and discards
  // what was painted, since the DOM that record describes is about to go.
  //
  // The `nav` bump here is load-bearing only on the path that does NOT change
  // the hash — navigating to the view already displayed, which is what clicking
  // the current tab does. Every other path writes the fragment and re-enters
  // through `readHash`, which bumps it again. Written down because a mutation
  // sweep survives its removal: the cross-view case is covered, and this is the
  // narrow one that is not, so the next reader should not take the survivor for
  // proof that the line does nothing.
  state.nav += 1;
  state.poll += 1;
  state.painted = null;
  const hash = DETAIL_VIEWS[view] ? `#${view}/${detailId}` : `#${view}`;
  if (window.location.hash !== hash) {
    window.location.hash = hash;
    return; // hashchange re-enters here
  }
  refresh(true);
}

function refresh(moveFocus = false) {
  const detail = DETAIL_VIEWS[state.view];
  const lit = detail ? detail.tab : state.view;
  for (const tab of document.querySelectorAll("nav.tabs button")) {
    if (tab.dataset.view === lit) tab.setAttribute("aria-current", "page");
    else tab.removeAttribute("aria-current");
  }
  // Captured here, before the view starts, so it is the navigation that
  // commissioned this paint rather than whatever is current when it finishes.
  const generation = state.nav;
  const done = guard(detail ? () => detail.render(state.detailId, generation) : () => VIEWS[state.view](generation));
  if (moveFocus) {
    // Navigating replaces the whole view, which destroys the control that was
    // focused — leaving focus on <body>, so the next Tab starts from the top of
    // the page. Sending it to the new view is what makes the surface navigable
    // by keyboard at all. Not done on first paint: stealing focus from a
    // freshly loaded page is its own bug.
    done.then(() => document.getElementById("view").focus());
  }
  return done;
}

function readHash() {
  const hash = window.location.hash.replace(/^#/, "");
  const slash = hash.indexOf("/");
  const head = slash === -1 ? hash : hash.slice(0, slash);
  if (slash !== -1 && DETAIL_VIEWS[head]) {
    state.view = head;
    state.detailId = decodeURIComponent(hash.slice(slash + 1));
  } else {
    // The path is consulted when there is no fragment, so the typed and
    // bookmarked URLs `pages.py` serves actually open the view they name.
    // Without this every one of them fell through to the Works grid: the server
    // answered 200 for /discovery and the client then rendered something else,
    // which is a worse failure than a 404 because it looks like it worked.
    const typed = window.location.pathname.replace(/^\//, "");
    state.view = VIEWS[hash] ? hash : VIEWS[typed] ? typed : "works";
    state.detailId = null;
  }
  // A fragment change is a navigation like any other, and the view being left
  // may have had a refresh scheduled over a page it is about to lose.
  state.nav += 1;
  state.poll += 1;
  state.painted = null;
}

for (const tab of document.querySelectorAll("nav.tabs button")) {
  tab.addEventListener("click", () => go(tab.dataset.view));
}
window.addEventListener("hashchange", () => {
  readHash();
  refresh(true);
});

readHash();
refresh();
