/* The browser client: boot, and the table of every screen it can show.
 *
 * No framework and no build step, deliberately: this is one operator's tool on
 * a private network, and a toolchain here would be a second thing to keep
 * running on a Pi for no gain a curator can see. ES modules are the browser's
 * own, so `type="module"` in `index.html` is the whole of the "build".
 *
 * **This file holds boot and the route table and nothing else.** Everything it
 * imports obeys one structural rule, recorded in `architecture.md` § Components
 * & Responsibilities: `core/` is shared and knows no screen; a module under
 * `screens/` may import from `core/` and must never import another screen. The
 * route table below is the one place they meet. That is what lets several
 * screens be built at once — a screen reaching sideways into another rebuilds
 * the single writer this split exists to end.
 *
 * TEXT IS SET WITH textContent, NEVER innerHTML — the rule is stated at
 * `core/render.js`, where the helper that enforces it lives, and it binds every
 * module here.
 */

import { install, go, refresh } from "./core/router.js";
import { installSearch, paintSearch } from "./core/search.js";
import { installStatus, paintStatus } from "./core/status.js";
import { state } from "./core/state.js";
import { viewCollection } from "./screens/collection.js";
import { viewConversation } from "./screens/conversation.js";
import { viewDiscover } from "./screens/discover.js";
import { viewHealth } from "./screens/health.js";
import { viewReview } from "./screens/review.js";
import { RUN_POLL_MAX_FAILURES, viewRun } from "./screens/run.js";
import { viewTheme } from "./screens/theme.js";
import { viewWalls } from "./screens/walls.js";
import { viewWork } from "./screens/work.js";

/* Every screen, and how it is reached.
 *
 * **Three destinations, and none of them names a pipeline stage.** That is the
 * acceptance criterion `information-architecture.md` § Direction was ratified to
 * bind, and this table is where it is checked by eye: the entries carrying
 * `destination` are the whole of the navigation. What they replaced — Works,
 * Discovery, Themes, On the wall, Health — were the pipeline's internal stages
 * in pipeline order, each correct as the chunk that produced it and wrong in
 * the sum.
 *
 * `opensFrom` is a *default* return, not a parent: a contextual screen returns
 * to the destination it was actually opened from, which travels in the address
 * as `?from=`. The default is what a bookmark or an agent's link gets, having no
 * opener to remember.
 *
 * Health is here, with a real address and no `destination` — reachable, and not
 * navigable-to. The masthead indicator is what expands to it, and
 * `core/status.js` records why that indicator is the thing that makes the
 * demotion safe.
 *
 * Insertion order is the navigation's order: the Walls first, because the thing
 * the product exists to produce should not be the fourth item behind three tabs
 * about producing it.
 */
const ROUTES = {
  walls: { render: viewWalls, destination: "The Walls" },
  collection: { render: viewCollection, destination: "Collection" },
  discover: { render: viewDiscover, destination: "Discover" },
  work: { render: viewWork, detail: true, opensFrom: "collection" },
  run: { render: viewRun, detail: true, opensFrom: "discover" },
  // Keyed by the conversation, and contextual rather than a fourth destination:
  // intent-forming is something a curator does *within* Discover, and a
  // destination for it would name a stage of the pipeline — which is the one
  // thing the navigation is not allowed to do.
  conversation: { render: viewConversation, detail: true, opensFrom: "discover" },
  // Keyed by the run whose works are being judged, not by a work: a curator
  // reviews a run's output as a set, and a per-work address would make the grid
  // unreachable by URL.
  review: { render: viewReview, detail: true, opensFrom: "discover" },
  theme: { render: viewTheme, opensFrom: "collection" },
  health: { render: viewHealth, opensFrom: "walls" },
};

installStatus();
installSearch();
install(ROUTES, {
  onNavigate: () => {
    paintSearch();
    paintStatus();
  },
});

/* The handful of internals the browser suite drives directly.
 *
 * A module's bindings are not globals, which is right — the client should not
 * be scattering names onto `window` — but `tests/browser` reaches four of them
 * through `page.evaluate` to express states a real server cannot be asked for on
 * purpose: a paint that loses its view, two refreshes racing, a watch's failure
 * count. Published explicitly, in one place, so what the tests may touch is a
 * decision recorded here rather than an accident of which functions happened to
 * be top-level.
 *
 * It is also the console surface for the operator this product is built for,
 * which is why it is not hidden behind a debug flag: a tool on a private network
 * whose author is its only user gains nothing from being harder to poke at. */
Object.assign(window, { go, refresh, state, viewRun, RUN_POLL_MAX_FAILURES });
