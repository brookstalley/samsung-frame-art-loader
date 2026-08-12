"""Serving the browser client itself — the shell and its two assets.

The client is a static page and a script that reads `/api/*`. It is served from
this package rather than built, because the alternative is a Node toolchain on a
Raspberry Pi maintained for a single-operator tool on a private network, which
buys nothing a curator can see.

The shell answers on every UI path, not only `/`. In-page navigation writes a
fragment, so the server sees one path in practice — but a bookmarked or reloaded
deep link must not 404, and a catch-all that returned the shell for `/api/...`
too would turn a mistyped endpoint into a page of HTML that a client parses as
JSON. So the UI paths are listed rather than globbed.
"""

from pathlib import Path
from typing import Final

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter()

STATIC_DIR: Final[Path] = Path(__file__).parent / "static"

#: Every path the client renders a view for. Adding a view means adding it here;
#: a view reachable only by clicking is a view nobody can bookmark.
#:
#: The first four are the three destinations and the root. The rest are screens
#: reached from one of them — contextual in the navigation, and no less
#: addressable for it: `information-architecture.md` requires every screen and
#: every consequential state to have a URL, and Health in particular is
#: *reachable and not navigable-to*, which is a statement about the navigation
#: rather than about the address.
#:
#: `/works`, `/discovery`, `/themes` and `/manifest` are the spellings the
#: surface answered to before the three destinations existed. They are kept
#: because they have been real, bookmarkable paths since the client was built;
#: `core/route.js` maps each onto the screen that took over its job, and rewrites
#: the address bar to the new spelling on arrival. Nothing here generates one.
UI_PATHS: Final[tuple[str, ...]] = (
    "/",
    "/walls",
    "/collection",
    "/discover",
    "/theme",
    "/taste",
    "/health",
    "/works",
    "/discovery",
    "/themes",
    "/manifest",
)


def index() -> FileResponse:
    """The client shell."""
    return FileResponse(STATIC_DIR / "index.html", media_type="text/html")


# Registered in a loop rather than with a decorator per path, so `UI_PATHS` is
# the single list and a route cannot be added to one without the other. Module
# scope on purpose: exporting a `register(router)` helper would invite a second
# call that silently double-registers every path.
for _path in UI_PATHS:
    router.add_api_route(_path, index, methods=["GET"], include_in_schema=False)
