"""The shipped browser client, driven by a real browser against a real server.

Every other suite here stops at the HTTP boundary: it asserts what `/api/*`
answers and takes on trust that the page does something sensible with it. That
trust has been wrong three times. `replaceChildren` coerced a null and put the
string "null" on the page; every image tile silently took the shape of its own
picture; and the run view repainted on every poll, so a keyboard user standing on
"Approve the list" lost the focus every two seconds. None of the three is visible
to a test that reads JSON, and two of them reached a running product.

So this level runs the real `app.js`, served by the real server, in a real
Chromium. **The client is what is under test and `/api` is its boundary** — which
is why several tests here stub a route rather than seed a catalogue. Some of the
control flow worth pinning describes states a real server reaches only slowly,
expensively, or cannot be asked for deterministically at all: a poll that changes
nothing, a page that keeps insisting there is more, an unresolved work carrying
each kind of nothing in turn. A harness that could not reach them would cover the
client's rendering and none of its control flow, which is the half that has
actually broken.

**Where a real server can produce the state, it does.** Paging runs against a
real catalogue and the real `truncated` flag; the image tests write a real file
and take it away; the focus move runs against the real routes. Stubs are for what
a server cannot be asked to do on purpose.

Payload builders live in `payloads.py` beside this file, and the rule they follow
— build from the API's own response models, never a hand-written dict — is
stated there.
"""

import io
import json
import pathlib

import pytest
from PIL import Image

from curation.persistence.records import (
    AcquisitionMethod,
    FetchStatus,
    RightsStatus,
    SourceClass,
)

BROWSER_DIR = pathlib.Path(__file__).parent


def pytest_collection_modifyitems(items):
    """Mark everything in this directory `browser`, rather than trusting each file to.

    The marker is what keeps a suite needing a 200MB browser out of the default
    run, so a file that forgot it would not fail here — it would fail for every
    contributor who had not installed one, in a suite they never asked to run.
    Applying it from the directory means a new test file cannot be added without
    it. Scoped by path because this hook is handed every collected item, not only
    the ones beneath this conftest.
    """
    for item in items:
        if BROWSER_DIR in item.path.parents:
            item.add_marker(pytest.mark.browser)


@pytest.fixture
def work_with_an_image(service, settings, decodable_jpeg):
    """A work whose master is really on disk, so its thumbnail really renders.

    `ready_work` records an original without writing one, which is right for the
    readiness rules it serves and wrong here: the browser has to actually decode
    what the thumbnail endpoint returns, and a work whose file is missing would
    exercise the absent-image path in a test asking about the present-image one.
    """

    def _work(title="Nighthawks", *, width=1600, height=1200):
        artwork = service.add_artwork(title=title, date_created="1942", medium="Oil on canvas")
        source = service.add_source(
            artwork_id=artwork.id,
            url=f"https://museum.example/{artwork.id}",
            provider="artic",
            source_class=SourceClass.INSTITUTIONAL,
            acquisition_method=AcquisitionMethod.DEZOOMIFY,
            rights_status=RightsStatus.PUBLIC_DOMAIN,
            is_primary=True,
        )
        relative = f"raw/{artwork.id}.jpg"
        decodable_jpeg(settings.art_root / relative, width=width, height=height)
        service.record_original(
            artwork_id=artwork.id,
            source_id=source.id,
            path=relative,
            width=width,
            height=height,
            byte_size=(settings.art_root / relative).stat().st_size,
            content_hash=f"hash-{artwork.id}",
            fetch_status=FetchStatus.OK,
        )
        return artwork

    return _work


class Ui:
    """The page under test, with the few things every test here needs.

    Thin on purpose: the point of this level is that Playwright's own waiting is
    doing the work, so wrapping locators in helpers would only hide which
    assertion is actually waiting for what.
    """

    def __init__(self, page, base_url: str):
        self.page = page
        self.base_url = base_url
        self.requests: list[str] = []
        page.on("request", lambda request: self.requests.append(request.url))

    def open(self, fragment: str = "") -> None:
        """Load the shell and wait for the client's first paint to land."""
        self.page.goto(f"{self.base_url}/{fragment}")
        # The view starts empty and every route fills it, so waiting on content
        # is what distinguishes "painted" from "the script has not run yet".
        self.page.wait_for_selector("#view *")

    def serve(self, pattern: str, payloads) -> None:
        """Answer `pattern` with each payload in turn; the last one repeats.

        A list rather than one body, because several behaviours here are about
        what happens *across* successive answers — a poll that changes nothing
        and then one that does — which a route with a single answer could not
        express.

        An entry may be a plain dict, answered 200, or a `(status, body)` pair.
        The pair is what lets a sequence express a *failing* answer, which the
        client's own failure model needs: "one blip then fine" and "broken from
        the first request and staying broken" are different behaviours, and
        neither can be written with successes alone.
        """
        entries = [payloads] if isinstance(payloads, (dict, tuple)) else list(payloads)
        served = {"count": 0}

        def handler(route):
            index = min(served["count"], len(entries) - 1)
            served["count"] += 1
            entry = entries[index]
            status, body = entry if isinstance(entry, tuple) else (200, entry)
            route.fulfill(
                status=status,
                content_type="application/json",
                body=json.dumps(body),
            )

        self.page.route(pattern, handler)

    def serve_image(self, pattern: str, *, colour=(84, 66, 132)) -> None:
        """Answer `pattern` with a real JPEG the browser can actually decode.

        Real bytes rather than a stub, because the assertion this supports is
        that a picture *renders* — a card whose `<img>` fails silently paints a
        blank box, which is the exact failure the review grid must not have, and
        an undecodable stub would make every such test look like that failure.
        """
        buffer = io.BytesIO()
        Image.new("RGB", (240, 180), colour).save(buffer, format="JPEG")
        body = buffer.getvalue()
        self.page.route(
            pattern,
            lambda route: route.fulfill(status=200, content_type="image/jpeg", body=body),
        )

    def text(self) -> str:
        return self.page.inner_text("#view")

    def focused(self) -> str:
        """What the keyboard is standing on, named so a test can assert it."""
        return self.page.evaluate(
            "() => { const a = document.activeElement;" " return a ? (a.id || a.textContent || a.tagName) : 'none'; }"
        )

    def requests_matching(self, needle: str) -> list[str]:
        return [url for url in self.requests if needle in url]


@pytest.fixture
def ui(page, server_url):
    return Ui(page, server_url)
