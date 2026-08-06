"""Exercise the Samsung art API against the live television and report what it does.

Run by hand, on the Pi, with the set awake. Nothing else verifies this: the
library is a two-year-old fork of an unowned websocket protocol, its failure
modes differ across TV generations, and reading its source only establishes what
it intends to do. This establishes what this television does.

    python tv_api_check.py --image "$ART_ROOT/ready/<a 4K composite>.jpg"

Every check reports rather than asserts, because a "no" is a finding worth
recording and not a reason to stop. The exit status is non-zero if any check
failed, so it can gate a deploy.

It is safe to run against the wall in use: the only image it removes is the one
it uploaded itself, and it removes that one whether the run succeeds or not. It
does not change art mode, brightness, or the slideshow.
"""

import argparse
import asyncio
import logging
import os
import time

import requests
from samsungtvws.async_art import SamsungTVAsyncArt
from samsungtvws.exceptions import ConnectionFailure, HttpApiError, ResponseError
from websockets.exceptions import WebSocketException

import config
import panel_check
from tv_delete import UPLOADED_CATEGORY, DeleteNotConfirmed, delete_list_confirmed

logging.basicConfig(format="%(levelname)s:%(message)s", level=logging.INFO)

#: The events that mean "the image on the wall changed". The first two are the
#: same notion under two spellings — which one a set emits depends on its API
#: generation, and registering only one fails silently on the other, so both go
#: on. `image_selected` is different: it is the reply to `select_image`, so it
#: acknowledges the request this script made rather than reporting a rotation.
#: All three are registered because the point is to learn which ones this
#: television actually sends.
IMAGE_CHANGED_EVENTS = ("slideshow_image_changed", "auto_rotation_image_changed", "image_selected")

#: Ceiling for the calls the client's own `timeout=` reaches: the REST request
#: for the model year, and opening the websocket. Named because both default to
#: no limit, so a set that drops packets rather than refusing them would hang
#: construction forever and report no elapsed figure at all.
#:
#: It does NOT govern art requests once the connection is up — those carry their
#: own defaults inside the library (2s for a generic reply, 4s for the content
#: list, 10s for an upload acknowledgement), and none of them derives from this.
#: Worth keeping straight: a daemon watchdog built on this number as the
#: per-request bound would be wrong about every window that governs art traffic.
TV_TIMEOUT_SECONDS = 15


class Report:
    """Findings in the order they were made, and whether any of them failed."""

    def __init__(self):
        self.lines: list[tuple[str, str, str]] = []

    def record(self, outcome: str, check: str, detail: str) -> None:
        self.lines.append((outcome, check, detail))
        print(f"  [{outcome:4}] {check}: {detail}")

    def ok(self, check: str, detail: str) -> None:
        self.record("ok", check, detail)

    def fail(self, check: str, detail: str) -> None:
        self.record("FAIL", check, detail)

    def note(self, check: str, detail: str) -> None:
        self.record("note", check, detail)

    @property
    def failed(self) -> bool:
        return any(outcome == "FAIL" for outcome, _, _ in self.lines)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--image",
        help=(
            "A real image to upload and then remove. Use a 4K composite from ready/ — the point is to time the "
            "size this product actually sends. Without it, the upload and delete checks are skipped."
        ),
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Leave the uploaded test image on the television instead of removing it. Skips the delete check.",
    )
    return parser.parse_args()


def check_construction(report: Report) -> SamsungTVAsyncArt | None:
    """Time the constructor, which performs blocking network I/O before returning.

    Building the client makes a synchronous HTTP request for the set's model
    year, and on a 2024-or-later panel with no token yet it also opens and
    closes a remote-control websocket to mint one — that generation will not
    accept the art channel until the token exists. Both happen inside
    `__init__`, so construction blocks the calling thread and raises when the
    set is unreachable, rather than deferring the failure to first use.
    """
    started = time.monotonic()
    try:
        # An explicit timeout, because the default is None: a set that refuses
        # connections fails fast, but one that silently drops them would hang
        # here forever and report no number at all.
        tv_art = SamsungTVAsyncArt(
            host=config.tv_address,
            port=config.tv_port,
            name="tvpi-apicheck",
            token_file=config.tv_token_file,
            timeout=TV_TIMEOUT_SECONDS,
        )
    except (HttpApiError, requests.exceptions.Timeout) as err:
        # Both, because the library converts only `requests.ConnectionError`
        # into `HttpApiError` — and a set that completes the handshake then goes
        # quiet raises `ReadTimeout`, which is not one. Without the second name
        # the half-open case exits with a traceback and no elapsed figure, which
        # is the one number this check exists to produce.
        elapsed = time.monotonic() - started
        report.fail(
            "constructor",
            f"unreachable after {elapsed:.2f}s ({type(err).__name__}: {err}). "
            "The set is asleep, off, or answering nothing — wake it and run this again.",
        )
        return None
    elapsed = time.monotonic() - started
    report.ok(
        "constructor",
        f"returned in {elapsed:.2f}s of blocking I/O (ceiling {TV_TIMEOUT_SECONDS}s) — "
        "record this; a daemon cannot do it on its loop",
    )
    return tv_art


def _configured_diagonal() -> float | None:
    """What this deployment says the panel measures, or None if it has not said.

    Read from the environment rather than from `config`, because the value
    belongs to the curation plane and this module is the 2024 one — importing it
    here would be the geometry crossing a plane boundary to be checked. `config`
    has already called `load_dotenv()`, so the same `.env` both planes read is in
    scope by the time this runs.

    An unparseable value is None, not an error: this is a diagnostic tool, and
    refusing to report on the television because a number is malformed would
    withhold every other check over the one that already looks wrong.
    """
    raw = os.environ.get("TV_PANEL_DIAGONAL_INCHES")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


async def check_identity(tv_art: SamsungTVAsyncArt, report: Report) -> None:
    """What this television is, and which half of the API split it speaks."""
    if not await tv_art.supported():
        report.fail("art mode", "this television reports no art mode support")
        return
    report.ok("art mode", "supported")

    version = await tv_art.get_api_version()
    report.ok("api version", f"{version} — {_api_generation(version)}")

    info = await tv_art.get_device_info()
    model = info.get("device", {}).get("modelName") if isinstance(info, dict) else None
    # The library branches on the model YEAR, not the name: from 2024 it mints a
    # pairing token before the art channel will accept one. Which side of that
    # line this panel falls on is worth having written down.
    report.note("model", f"{model or 'not reported'} — record it; the token handshake changes for 2024-or-later panels")

    # The set names its own size, so the configured diagonal is checkable rather
    # than merely documentable — and until now it was only ever documented. A
    # live deployment ran 42" against this 50" panel and every judgement about
    # whether a work was big enough for the wall was silently mis-sized.
    #
    # Warned, not failed: this tool reports what it finds, and a diagonal
    # disagreeing with the panel is a `.env` fix rather than a broken television.
    # Silent when the model line is one this codebase has not verified a parse
    # against, which is most of them.
    mismatch = panel_check.disagreement(model, _configured_diagonal())
    if mismatch is not None:
        report.fail("panel size", mismatch)
    else:
        report.ok("panel size", "the configured diagonal agrees with the set, or neither side stated one")


def _api_generation(version: str) -> str:
    """Which half of the verb split a reported API version falls on.

    The set is never asked this — the library exposes `auto_rotation_*` and
    `slideshow_*` side by side and leaves the choice to the caller, so the
    threshold lives in consumers rather than in the library. The convention
    those consumers use is to strip the dots and compare against 4000, which
    reads "4.3.4.0" as 4340 (new) and "2.03" as 203 (old) — but the same rule
    reads a three-component "4.3.1" as 431 and calls a 4.x set old. The major
    component is the durable form of the same test, so that is what is compared
    here, and the raw version is printed beside it: the version is the fact and
    the generation is an inference.
    """
    major = str(version).split(".")[0]
    if not major.isdigit():
        return f"generation unknown from {version!r} — record it and decide by hand"
    return "new API (slideshow_* verbs)" if int(major) >= 4 else "old API (auto_rotation_* verbs)"


async def check_callbacks(tv_art: SamsungTVAsyncArt, report: Report, content_id: str | None) -> None:
    """Register all three change events and see which ones this set emits."""
    fired: list[str] = []

    async def on_event(event, response):
        fired.append(event)

    for trigger in IMAGE_CHANGED_EVENTS:
        tv_art.set_callback(trigger, on_event)

    if content_id is None:
        report.note("callbacks", "registered, but nothing was selected to provoke one — pass --image to test properly")
        return

    await tv_art.select_image(content_id)
    # The set emits on its own schedule; a short wait is the whole test.
    await asyncio.sleep(5)

    for trigger in IMAGE_CHANGED_EVENTS:
        tv_art.set_callback(trigger, None)

    if fired:
        report.ok("callbacks", f"fired: {', '.join(sorted(set(fired)))}")
    else:
        report.fail("callbacks", f"none of {', '.join(IMAGE_CHANGED_EVENTS)} fired within 5s of select_image")


async def check_upload(tv_art: SamsungTVAsyncArt, report: Report, path: str) -> str | None:
    """Upload by path — the streaming route — at the timeout production uses.

    Deliberately does NOT pass a generous `timeout=`. That argument governs the
    wait for the set's `image_added` reply after the bytes are written, and on
    expiry `upload()` returns None rather than raising — which is the silent
    failure this whole exercise exists to close. Checking at a window six times
    wider than the loader's would clear a pass the loader would not.
    """
    size_mb = os.path.getsize(path) / (1024 * 1024)
    started = time.monotonic()
    try:
        content_id = await tv_art.upload(path, matte="none", portrait_matte="none")
    except (OSError, AssertionError, KeyError, ResponseError) as err:
        report.fail("upload", f"{type(err).__name__}: {err}")
        return None
    elapsed = time.monotonic() - started

    if not content_id:
        report.fail(
            "upload",
            f"returned no content id after {elapsed:.1f}s — the set did not acknowledge the image inside the "
            "library's default reply window, which is the silent-None path the loader would also have taken",
        )
        return None
    # One number, and it covers both the transfer and the wait for the reply —
    # the library does them inside one call, so they cannot be separated from
    # out here. Read it against the library's default reply window: a total
    # anywhere near it means the margin is thin even though this run passed.
    report.ok("upload", f"{size_mb:.1f} MB, {elapsed:.1f}s from first byte to acknowledgement, as {content_id}")

    listed = {entry["content_id"] for entry in await tv_art.available(category=UPLOADED_CATEGORY)}
    if content_id in listed:
        report.ok("upload listed", f"{content_id} appears in {UPLOADED_CATEGORY}")
    else:
        report.fail("upload listed", f"{content_id} was returned but the set does not list it")
    return content_id


async def check_confirmed_delete(tv_art: SamsungTVAsyncArt, report: Report, content_id: str) -> None:
    """The verb whose result the library discards. Only the test image is touched."""
    try:
        result = await delete_list_confirmed(tv_art, [content_id])
    except DeleteNotConfirmed as err:
        report.fail("confirmed delete", f"sent, unconfirmable: {err}")
        return

    if result.complete:
        report.ok("confirmed delete", f"{content_id} is gone from the set's own list")
    else:
        report.fail("confirmed delete", f"the set still lists {', '.join(result.surviving)} after removal")


async def guarded(report: Report, name: str, coroutine):
    """Run one check so that its failure costs only that check.

    Access to the television is the scarce resource here — it has to be awake,
    and someone has to be standing next to it. A first check that raises would
    otherwise take the callback and confirmed-delete findings with it and cost a
    second trip, so an unexpected exception is recorded as a finding and the run
    continues. `AssertionError` is in the list on purpose: it is how this library
    reports a timed-out request. `OSError` is what covers the builtin
    `TimeoutError` a websocket open raises against its `open_timeout`, and
    `WebSocketException` the handshake failures that are not `OSError` at all.

    Not a complete set, and cannot be: a television that accepts the websocket
    and then goes silent hangs in the startup `recv()`, which carries no timeout
    of its own. That one is a stopwatch and a Ctrl-C, and it is a finding.
    """
    try:
        return await coroutine
    except (
        OSError,
        AssertionError,
        KeyError,
        ResponseError,
        HttpApiError,
        ConnectionFailure,
        WebSocketException,
        DeleteNotConfirmed,
    ) as err:
        report.fail(name, f"raised {type(err).__name__}: {err}")
        return None


async def run(args) -> int:
    report = Report()
    print(f"Checking the art API on {config.tv_address}:{config.tv_port}\n")

    tv_art = check_construction(report)
    if tv_art is None:
        # Nothing downstream can say anything without a client, and reporting
        # each remaining check as failed would blame them for the set being off.
        print(f"\n{len(report.lines)} checks, 1 failed")
        return 1

    # Guarded like everything else. A set that completes the TCP handshake and
    # then goes quiet gets past construction and stalls here instead, on the art
    # websocket — and an unguarded traceback at this line would cost the summary,
    # the exit path, and the connection close, for the same fault one call later.
    await guarded(report, "listening", tv_art.start_listening())
    if report.failed:
        # Only the listening guard can have failed by here — construction's
        # failure returned above, and nothing else has run.
        await tv_art.close()
        print(f"\n{len(report.lines)} checks, 1 failed")
        return 1

    content_id = None
    try:
        await guarded(report, "identity", check_identity(tv_art, report))
        if args.image:
            content_id = await guarded(report, "upload", check_upload(tv_art, report, args.image))
        await guarded(report, "callbacks", check_callbacks(tv_art, report, content_id))
        if content_id and not args.keep:
            await guarded(report, "confirmed delete", check_confirmed_delete(tv_art, report, content_id))
            # The check IS the removal, so there is nothing left for the cleanup
            # below to do — and if it raised, the assignment is skipped and the
            # cleanup gets its turn.
            content_id = None
        elif content_id:
            report.note("confirmed delete", f"skipped; {content_id} left on the set by --keep")
    finally:
        if content_id and not args.keep:
            # Whatever went wrong above, do not leave the test image on the wall.
            # Cleanup must not raise over the top of the failure that caused it.
            await guarded(report, "cleanup", delete_list_confirmed(tv_art, [content_id]))
        await tv_art.close()

    failures = [line for line in report.lines if line[0] == "FAIL"]
    print(f"\n{len(report.lines)} checks, {len(failures)} failed")
    return 1 if report.failed else 0


def main() -> int:
    args = parse_args()
    if args.image and not os.path.exists(args.image):
        print(f"No such image: {args.image}")
        return 2
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
