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

const state = { view: "works", workId: null };

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
    // `truncated` alone would loop forever against an empty page, so the
    // stopping condition is what actually arrived.
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

function render(...nodes) {
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

/* A badge always carries a glyph and a word beside its colour, so the state
 * survives greyscale, colour blindness, and a dimmed room. */
function fitBadge(work) {
  if (!work.fit) {
    return el("span", { class: "badge badge-unknown", title: work.fit_note || "" }, [
      el("span", { class: "glyph", text: "—", "aria-hidden": true }),
      el("span", { text: "no size known" }),
    ]);
  }
  const verdict = work.fit.verdict;
  const inches = work.fit.rendered_long_edge_inches.toFixed(1);
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
  return el("span", { class: "badge badge-below_floor" }, [
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

async function viewWorks() {
  const page = await fetchAllWorks();
  const heading = el("h2", {
    text: page.works.length === page.total ? `${page.total} works` : `${page.works.length} of ${page.total} works`,
  });
  const note = shortfallNote(page);
  render(heading, note, el("ul", { class: "grid" }, page.works.map(workCard)));
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

async function viewWork(artworkId) {
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

  render(...panels);
}

async function viewThemes() {
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
  render(...panels);
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

async function viewManifest() {
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
  render(...panels);
}

async function viewHealth() {
  const health = await api("/api/health");
  const box = health.artwork_box;
  render(
    el("h2", { text: "Health" }),
    el("div", { class: "panel" }, [
      el("h3", { text: "The display plane" }),
      // An observation with its age, never a verdict. A green dot computed from
      // a file that may simply be young is how a health surface starts lying.
      el("p", { text: health.heartbeat.description }),
      facts([
        ["Heartbeat file", health.heartbeat.path],
        ["Last reported", health.heartbeat.reported_at],
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

/* -- routing --------------------------------------------------------------- */

const VIEWS = { works: viewWorks, themes: viewThemes, manifest: viewManifest, health: viewHealth };

async function guard(work) {
  try {
    await work();
    clearError();
  } catch (failure) {
    showError(failure.message);
  }
}

function go(view, workId = null) {
  state.view = view;
  state.workId = workId;
  const hash = view === "work" ? `#work/${workId}` : `#${view}`;
  if (window.location.hash !== hash) {
    window.location.hash = hash;
    return; // hashchange re-enters here
  }
  refresh(true);
}

function refresh(moveFocus = false) {
  for (const tab of document.querySelectorAll("nav.tabs button")) {
    const selected = tab.dataset.view === state.view || (state.view === "work" && tab.dataset.view === "works");
    if (selected) tab.setAttribute("aria-current", "page");
    else tab.removeAttribute("aria-current");
  }
  const done = guard(state.view === "work" ? () => viewWork(state.workId) : VIEWS[state.view]);
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
  if (hash.startsWith("work/")) {
    state.view = "work";
    state.workId = decodeURIComponent(hash.slice("work/".length));
  } else {
    state.view = VIEWS[hash] ? hash : "works";
    state.workId = null;
  }
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
