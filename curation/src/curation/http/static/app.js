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
const state = { view: "works", detailId: null, nav: 0, poll: 0, painted: null, watch: null };

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

/* Both the grid and the theme picker page through to the end rather than showing
 * the first page. The picker is the one that made this necessary: a truncated
 * grid is a visible short list, but a truncated picker means a curator simply
 * cannot put work 101 in a theme, and is told nothing about why.
 *
 * **THE JUSTIFICATION FOR THIS HAS BEEN RETIRED, AND THE BEHAVIOUR HAS NOT.**
 * This paragraph used to open "the design target is hundreds of works, so…".
 * `nonfunctional-requirements.md` moved that target to **thousands** on
 * 2026-08-10, and its own amendment calls fetching the whole catalogue
 * "indefensible at 4,000". So what is written below is a description of what this
 * file does, no longer an argument that it is right: the grid owes server-side
 * search, paging and virtualisation, which `information-architecture.md`
 * specifies and no chunk has built. The picker's reason above is unaffected and
 * still binds — whatever replaces this must still leave every work reachable.
 *
 * **No `limit` is sent**, which is the same rule `fetchAllCandidates` states
 * below and for the same reason. This asked for `limit=100` — a copy of the
 * service's `MAX_LIST_LIMIT` — until 2026-08-05, and that copy was a live break
 * waiting on an unrelated edit: `list_artworks` *refuses* a limit above its cap,
 * the refusal arrives as a 400, and `api()` throws. So the day anyone lowered
 * the catalogue's cap, the Works grid — the default landing view — and the theme
 * picker would have failed outright while the review grid, which asks for
 * nothing, kept paging.
 *
 * The cost is paid knowingly: the server's default page is smaller than its cap,
 * so this makes more round trips than asking for the maximum would. They are
 * against a loopback server on the same box. `PAGE_CEILING` no longer admits
 * "far more works than the design target" — at the amended target it is the
 * thing that will bite first, and `shortfallNote` is what keeps that visible
 * rather than silent until the paging work lands.
 *
 * `PAGE_CEILING` is a runaway guard, not a policy. If it is ever hit the caller
 * reports how many were left out, because a cap nobody mentions is the silent
 * omission this product exists to refuse. */
const PAGE_CEILING = 50;

async function fetchAllWorks() {
  const works = [];
  let total = 0;
  let truncated = false;
  for (let page = 0; page < PAGE_CEILING; page += 1) {
    const body = await api(`/api/works?offset=${works.length}`);
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
  // The walls come along because hanging is an act against a named wall: a
  // theme panel cannot offer "put this up" without saying where, and it cannot
  // say where without knowing what the walls are called.
  const [themes, walls, works] = await Promise.all([api("/api/themes"), api("/api/walls"), fetchAllWorks()]);

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

  if (!walls.walls.length) {
    panels.push(
      el("p", { class: "note", text: "There are no walls, so nothing can be hung. A wall is created when the plane first opens the catalogue." }),
    );
  }

  for (const placement of themes.themes) {
    panels.push(themePanel(placement, walls.walls, works.works));
  }
  render(generation, ...panels);
}

function themePanel(placement, walls, allWorks) {
  const theme = placement.theme;
  const hangingOn = placement.hanging_on;
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
      // Hanging carries a glyph and the words beside any colour — and the words
      // name the walls, because "on the wall" reads correctly today only while
      // there is one of them.
      hangingOn.length
        ? el("span", { class: "badge", style: "margin-left: 0.5rem" }, [
            el("span", { class: "glyph", text: "●", "aria-hidden": true }),
            el("span", { text: `on ${hangingOn.map((wall) => wall.name).join(", ")}` }),
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
      // One button per wall, named for that wall. There is no single-wall
      // shortcut to replace when a second display arrives, which is the whole
      // point: with one wall this reads "Hang on the living room" and with three
      // it reads as three choices, and neither is a different layout.
      ...walls
        .filter((wall) => !hangingOn.some((hung) => hung.wall_id === wall.wall_id))
        .map((wall) =>
          el("button", {
            class: "action",
            type: "button",
            text: `Hang on ${wall.name}`,
            onclick: () =>
              guard(async () => {
                await api(`/api/themes/${encodeURIComponent(theme.theme_id)}/activate`, {
                  method: "POST",
                  body: JSON.stringify({ wall_id: wall.wall_id }),
                });
                go("manifest");
              }),
          }),
        ),
      ...hangingOn.map((wall) =>
        el("button", {
          class: "action quiet",
          type: "button",
          text: `Take down from ${wall.name}`,
          onclick: () =>
            guard(async () => {
              await api(`/api/walls/${encodeURIComponent(wall.wall_id)}/theme`, { method: "DELETE" });
              await refresh();
            }),
        }),
      ),
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
  // One section per wall, with one wall the degenerate case rather than a
  // special one: there is no single-wall layout here for a second display to
  // replace. A wall with nothing hanging is asked nothing — the route would
  // refuse, and correctly, because there is no theme to evaluate.
  const walls = await api("/api/walls");
  const hung = walls.walls.filter((wall) => wall.theme);
  const builds = await Promise.all(
    hung.map(async (wall) => [wall, await api(`/api/manifest?wall_id=${encodeURIComponent(wall.wall_id)}`)]),
  );

  const panels = [el("h2", { text: "The walls" })];
  for (const wall of walls.walls.filter((candidate) => !candidate.theme)) {
    panels.push(el("p", { class: "muted", text: `Nothing is hanging on ${wall.name}. Hang a theme from Themes.` }));
    // The fact the MCP surface already states after an unhang, said here too.
    // Taking a theme down rewrites no manifest, so the set goes on showing the
    // picture — and a curator who read only the line above would take a
    // successful take-down for a failed one, which is the same inference
    // `activate_theme` cites when it argues hanging must publish immediately.
    panels.push(
      el("p", {
        class: "note",
        text: "Taking a theme down does not blank the wall: the display goes on showing what it last received until a theme is hung.",
      }),
    );
  }
  for (const [wall, manifest] of builds) {
    panels.push(...manifestPanels(wall, manifest));
  }
  render(generation, ...panels);
}

function manifestPanels(wall, manifest) {
  return [
    // `h3` for the wall and `h4` for its panels, so the nesting survives a
    // second wall: with two walls hung, sibling `h3`s would give a reader
    // navigating by heading four headings in a row and no signal for which
    // counts belong to which room. The single-wall view read correctly by
    // accident, having only one room's worth of headings to confuse.
    el("h3", { class: "wall-title", text: `${wall.name}: ${manifest.theme.name}` }),
    el("p", { class: "note", text: manifest.summary }),
    el("div", { class: "panel" }, [
      el("h4", { text: `Showing (${manifest.entries.length})` }),
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
      el("h4", { text: `Not showing (${manifest.exclusions.length})` }),
      manifest.exclusions.length
        ? table(
            "Every work this theme holds that is not on the wall, and exactly why.",
            ["Title", "Reason", "What is missing"],
            manifest.exclusions.map((x) => [x.title, x.reason, x.detail]),
          )
        : el("p", { class: "muted", text: "Every work in this theme reached the wall." }),
    ]),
    el("div", { class: "panel" }, [
      el("h4", { text: "How it rotates" }),
      facts([
        ["Interval", `${manifest.rotation_interval_seconds} seconds`],
        ["Order", manifest.shuffle ? "shuffled" : "as curated"],
        ["Directive sequence", manifest.directive_sequence],
        ["Pinned work", manifest.pinned_work_id],
      ]),
    ]),
  ];
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

/* What `resolution_status` says, in the tense it actually holds.
 *
 * **The column describes the RUN's outcome, not the card's current state**, and
 * these words now say so. That is the answer to "does this badge describe the run
 * or the card", and it is written here rather than only in a decision record
 * because the words are the whole of the fix.
 *
 * They used to read "has an image" — present tense, a claim about the work right
 * now — beside a card that could also read "You have turned down everything that
 * was found for it." Each true, together contradictory: only a resolution
 * *attempt* recomputes this column, so turning down the last surviving instance
 * leaves it reading `resolved` until the next re-search.
 *
 * The rejection model is deliberate and settled — `discovery.reject_image` does
 * not rewrite `resolution_status`, and `_accept` asks the images rather than this
 * column for exactly that reason. So the column was right and the wording was
 * wrong, and rewording is what makes the two parts of that card consistent.
 *
 * **Chosen over deriving the badge from surviving instances**, which was the
 * other real option. That would have made the badge mean *the card's* state on
 * the review grid while the run table — whose rows carry no instance data — went
 * on meaning the run's, so one badge would have said two things on two screens.
 * These words mean the same on the grid, in the run table, and beside the raw
 * `resolution_status` an agent reads over MCP. */
const RESOLUTION_WORDS = {
  resolved: "the run found an image",
  unresolved: "the run found none",
  pending: "not looked up",
};

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
      // "found no image for" rather than "could not confirm". The run did name
      // works for those artists — they are in the table directly below this
      // sentence, badged `not held` — so a word that reads as "named nothing for"
      // is denied by the screen it is printed on. That was issue #95 on the
      // review grid, and it lived here too: the same claim, one surface over, on
      // the page a curator lands on first.
      sentence += ` Separately, the collection offered ${tally.offered} more ${tally.offered === 1 ? "work" : "works"} by artists this run found no image for. They are labelled below and are not what was asked for.`;
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

/* Slow enough not to hammer a Pi, fast enough that a curator watching a run does
 * not wonder whether the page is live. The server answers immediately rather
 * than holding the request open, so this interval is the whole of the latency. */
const RUN_POLL_MS = 2000;

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
const RUN_POLL_MAX_FAILURES = 5;

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
 * meets it.
 *
 * **The badge beside this used to contradict it, and no longer does.** It read
 * "has an image" — a present-tense claim — while `resolution_status` records what
 * the *run* found, and rejecting an image deliberately does not rewrite it. The
 * product question that paragraph deferred is answered: the column describes the
 * run, and `RESOLUTION_WORDS` says so. Rewording it rather than deriving the
 * badge from surviving instances keeps one badge meaning one thing on the review
 * grid, in the run table and over MCP — see the comment on `RESOLUTION_WORDS`. */
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

async function viewReview(runId, generation) {
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
