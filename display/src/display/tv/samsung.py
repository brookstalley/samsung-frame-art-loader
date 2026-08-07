"""The `samsungtvws` fork, corrected at the seam.

Every non-obvious line here answers something measured against this deployment's
own television rather than read from the library's source. The measurements live
in `platform-and-dependency-findings.md` § The television and are firmware-scoped;
what is encoded here is the *behaviour* they establish:

* **Constructing the client performs blocking network I/O** — 0.24 s with a
  cached token, 8.4 s while pairing, ~15 s against a set that is asleep, which is
  most of the time. It cannot happen on the event loop, so it happens on a thread.
* **`start_listening()` hangs rather than raising** when the set is not in art
  mode, and on another attempt raised after ~15 s. Not even consistent between
  runs, so it gets a ceiling of this plane's own.
* **`upload()` reports failure on uploads that succeeded.** The image is on the
  wall and the caller is told it is not, which is worse than a plain failure
  because it lies in the safe-looking direction: a caller that retries duplicates
  the image. So an upload is confirmed against the set's own content list.
* **`delete_list()` never reads its reply** — it sends and returns None whether
  the set removed anything or not. Removal is confirmed the same way.

The rule those last two share, and the one to apply to any verb added later:
**this library's return values are not trustworthy in either direction; confirm
against the television itself.**

**Nothing above this seam imports `samsungtvws`.** That is not tidiness — it is
what makes the standing risk survivable, since the fork is unowned, static, and
has no maintained alternative carrying an async art client.
"""

import asyncio
import json
import logging
from collections.abc import Awaitable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, Final, TypeVar

from samsungtvws.async_art import SamsungTVAsyncArt
from samsungtvws.exceptions import ConnectionFailure, HttpApiError, ResponseError
from websockets.exceptions import WebSocketException

from display.tv.client import (
    UPLOADED_CATEGORY,
    RemovalOutcome,
    TvClient,
    TvRemovalUnconfirmed,
    TvUnavailable,
    TvUploadFailed,
)

log = logging.getLogger(__name__)

#: What one library call returns. Named so `_call` can pass a result through
#: without flattening it to `Any` — every caller of `_call` knows the shape it
#: expects, and a wrapper that erased it would push the guesswork outwards.
T = TypeVar("T")

#: Everything this library throws when the television goes away, as one tuple.
#:
#: `AssertionError` is in here because that is how this library reports a
#: timed-out request — an `assert data` on a reply that never came, not a
#: programming error to let through. `OSError` covers three things at once: the
#: builtin `TimeoutError` a websocket open raises, the `ConnectionResetError` of
#: a dropped socket, and — non-obviously — **every `requests` exception**, since
#: `RequestException` subclasses `OSError`. That last one is why nothing here
#: imports `requests` to name its timeout: the constructor's blocking REST call
#: is already covered, and importing an HTTP client into this plane is exactly
#: what the isolation guard forbids.
#:
#: `JSONDecodeError` is a `ValueError` and is named rather than caught broadly:
#: `upload()` parses the set's `conn_info` reply, so a set answering something
#: unexpected surfaces there rather than at a socket.
_LIBRARY_FAILURES: Final[tuple[type[Exception], ...]] = (
    OSError,
    AssertionError,
    KeyError,
    json.JSONDecodeError,
    ResponseError,
    HttpApiError,
    ConnectionFailure,
    WebSocketException,
)

#: The set's own art application publishes no matte for images this product
#: sends: the mat is already composed into the render by the curation plane, and
#: letting the television draw a second one over it would frame the frame.
_NO_MATTE: Final[str] = "none"


class SamsungTv(TvClient):
    """One television, reached over the art websocket."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        token_file: Path,
        client_name: str,
        connect_timeout_seconds: float,
        upload_timeout_seconds: float,
    ) -> None:
        self._host = host
        self._port = port
        self._token_file = token_file
        self._client_name = client_name
        self._connect_timeout = connect_timeout_seconds
        self._upload_timeout = upload_timeout_seconds
        self._art: SamsungTVAsyncArt | None = None

    async def connect(self) -> None:
        """Build the client off the loop, then open the art channel under a ceiling."""
        if self._art is not None:
            return

        try:
            art = await asyncio.to_thread(self._construct)
        except _LIBRARY_FAILURES as exc:
            raise TvUnavailable(f"could not reach the television at {self._host}:{self._port} ({_named(exc)})") from exc

        try:
            await asyncio.wait_for(art.start_listening(), timeout=self._connect_timeout)
        except TimeoutError as exc:
            # The set accepted the websocket and then said nothing, which is what
            # it does when art mode is off. Distinguished in the message because
            # it is the one failure a person can fix by picking up the remote.
            await self._quietly_close(art)
            raise TvUnavailable(
                f"the television at {self._host} accepted a connection but never opened the art channel within "
                f"{self._connect_timeout:.0f}s; it is most likely not in art mode"
            ) from exc
        except _LIBRARY_FAILURES as exc:
            await self._quietly_close(art)
            raise TvUnavailable(f"the television at {self._host} refused the art channel ({_named(exc)})") from exc

        self._art = art

    def _construct(self) -> SamsungTVAsyncArt:
        """Blocking, and therefore called only from a worker thread.

        The blocking part is `get_token()`, which opens and closes the
        *remote-control* websocket — a different channel from the art one
        everything else here uses. An explicit `timeout` is passed because the
        library's default is None: a set that refuses connections fails fast, but
        one that silently drops them would hang this thread forever.
        """
        return SamsungTVAsyncArt(
            host=self._host,
            port=self._port,
            name=self._client_name,
            token_file=str(self._token_file),
            timeout=self._connect_timeout,
        )

    async def close(self) -> None:
        """Let the connection go, and never raise on the way out."""
        art, self._art = self._art, None
        if art is not None:
            await self._quietly_close(art)

    async def _quietly_close(self, art: SamsungTVAsyncArt) -> None:
        try:
            await art.close()
        except _LIBRARY_FAILURES as exc:
            # Closing is best-effort by definition: this runs while something has
            # already gone wrong, and a failure here must not replace the real
            # error with a tidier one. Said out loud rather than swallowed.
            log.debug("closing the television connection raised %s", _named(exc), extra={"event": "tv.close_failed"})

    async def disable_native_slideshow(self) -> None:
        """Tell the set to stop rotating on its own.

        Its slideshow can only be scoped to a whole category — there is no
        content-id list, no album and no playlist — so it cannot be made to show
        a theme. Rotation is driven from here instead, and the set's own timer
        would otherwise change the picture underneath it.
        """
        await self._call("set_slideshow_status", self._client().set_slideshow_status(duration=0))

    async def listed_content_ids(self) -> frozenset[str]:
        return frozenset(entry["content_id"] for entry in await self._available() if "content_id" in entry)

    async def _available(self) -> list[dict[str, Any]]:
        entries = await self._call("available", self._client().available(category=UPLOADED_CATEGORY))
        if not isinstance(entries, list):
            raise TvUnavailable(f"the television listed its uploads as a {type(entries).__name__}, not a list")
        return [entry for entry in entries if isinstance(entry, dict)]

    async def upload(self, path: Path) -> str:
        """Put an image on the television, and establish whether it landed.

        The library returns None when the acknowledgement does not arrive inside
        its window, whether or not the image is on the set — so a falsy return is
        a question, not an answer. The answer comes from reading the set's own
        list back.

        **Attribution uses two independent signals**, because either alone can be
        wrong. The `image_date` this request stamped identifies the upload, and
        the set echoes it in its listing; a snapshot taken before the attempt
        identifies what is new. A single new id is attributed even without a
        marker match, and several new ids without one are attributed to nobody —
        claiming an id this upload did not create would bind a work to somebody
        else's picture.

        The marker is only unique because uploads here are sequential: one
        reconciliation loop, one image at a time. A concurrent uploader would
        need a finer marker than the second-resolution timestamp the protocol
        carries.
        """
        marker = datetime.now().strftime("%Y:%m:%d %H:%M:%S")
        before = await self.listed_content_ids()

        reported: Exception | None = None
        content_id: str | None = None
        try:
            content_id = await self._client().upload(
                str(path),
                matte=_NO_MATTE,
                portrait_matte=_NO_MATTE,
                date=marker,
                timeout=self._upload_timeout,
            )
        except _LIBRARY_FAILURES as exc:
            reported = exc

        if content_id:
            return content_id

        landed = await self._attribute(marker, before)
        if landed is not None:
            log.warning(
                "the television reported no id for %s but is holding it as %s; trusting the set over the library",
                path.name,
                landed,
                extra={
                    "event": "tv.upload_misreported",
                    "tv_content_id": landed,
                    "reported": _named(reported) if reported else None,
                },
            )
            return landed

        raise TvUploadFailed(
            f"{path.name} is not on the television after an upload attempt"
            + (f" ({_named(reported)})" if reported is not None else " (the library reported no id)")
        )

    async def _attribute(self, marker: str, before: frozenset[str]) -> str | None:
        """Which newly listed id, if any, this upload can honestly claim."""
        try:
            entries = await self._available()
        except TvUnavailable:
            # The set went away between the upload and the read-back, so nothing
            # can be established. Reported as a failed upload rather than a
            # connection error, because the caller's next move is the same and
            # the work must not be recorded as `uploaded`.
            return None

        arrived = [entry for entry in entries if entry.get("content_id") not in before]
        marked = [entry["content_id"] for entry in arrived if entry.get("image_date") == marker and entry.get("content_id")]
        if len(marked) == 1:
            return marked[0]
        if len(arrived) == 1 and arrived[0].get("content_id"):
            return str(arrived[0]["content_id"])
        return None

    async def select_image(self, content_id: str) -> None:
        """Ask the set to put an image it already holds on the wall.

        **Asking is all this does, and the caller must confirm it.** This once
        returned with no check, on the reasoning that the wall would be checked by
        the next thing to look at it. Nothing looks: a television observed on
        2026-08-07 with its panel dark accepted this call, raised nothing, emitted
        none of the three art-mode events, and went on displaying the image it had
        — through repeated attempts over twelve seconds. The failure is therefore
        silent and permanent rather than transient, which is exactly the shape a
        return value cannot carry. `current_content_id` is the confirming read.
        """
        await self._call("select_image", self._client().select_image(content_id, show=True))

    async def current_content_id(self) -> str | None:
        """Ask the set what is on the wall, tolerating an answer it will not give.

        Shaped as "or None" rather than raising, because a set that declines to
        describe its own display is not the same event as one that has gone away
        — the caller's response is to leave the wall alone and say what it could
        not establish, not to reconnect. A malformed answer is treated as no
        answer for the same reason: the alternative is comparing a selection
        against a value whose meaning nobody knows.
        """
        answer = await self._call("get_current", self._client().get_current())
        if not isinstance(answer, dict):
            return None
        content_id = answer.get("content_id")
        return content_id if isinstance(content_id, str) and content_id else None

    async def reported_art_mode(self) -> str | None:
        """The set's own art-mode flag, for a log line and nothing else.

        Swallows every failure rather than propagating one: this runs only on a
        path that has already established something is wrong, and a diagnostic
        that can itself raise would replace the report of the real fault with a
        report of the failed attempt to describe it.
        """
        try:
            mode = await self._call("get_artmode", self._client().get_artmode())
        except TvUnavailable:
            return None
        return mode if isinstance(mode, str) else None

    async def remove(self, content_ids: Sequence[str]) -> RemovalOutcome:
        """Remove images, then read the set's own list to find out what happened.

        Confirmation cannot come from the call: the library sends the request and
        discards the reply, so "it worked" and "it was refused" are the same
        return value. Reading the list back is also stronger than an
        acknowledgement would be — it reports the state the set is actually in
        rather than what it said it would do.
        """
        requested = tuple(content_ids)
        if not requested:
            return RemovalOutcome(requested=(), surviving=())

        try:
            await self._client().delete_list(list(requested))
        except _LIBRARY_FAILURES as exc:
            raise TvRemovalUnconfirmed(f"the removal request was refused ({_named(exc)}); what the set holds is unknown") from exc

        try:
            still_listed = await self.listed_content_ids()
        except TvUnavailable as exc:
            raise TvRemovalUnconfirmed(f"the removal was sent but the set's list could not be read back ({exc})") from exc

        outcome = RemovalOutcome(requested=requested, surviving=tuple(cid for cid in requested if cid in still_listed))
        if not outcome.complete:
            # Logged here rather than only returned, so the outcome cannot go
            # unreported because a caller ignored the return value.
            log.warning(
                "the television still lists %d of %d images requested for removal",
                len(outcome.surviving),
                len(requested),
                extra={"event": "tv.removal_incomplete", "surviving": list(outcome.surviving)},
            )
        return outcome

    async def set_brightness(self, value: int) -> None:
        await self._call("set_brightness", self._client().set_brightness(value))

    def _client(self) -> SamsungTVAsyncArt:
        if self._art is None:
            raise TvUnavailable("not connected to the television")
        return self._art

    async def _call(self, verb: str, awaitable: Awaitable[T]) -> T:
        """Run one library call, and turn its many failures into this plane's one.

        The connection is dropped on failure rather than kept: the library holds a
        websocket whose state after an error is not knowable from out here, and a
        caller retrying on a half-dead connection is how a daemon spends a night
        failing at the same call. The next attempt reconnects.
        """
        try:
            return await awaitable
        except _LIBRARY_FAILURES as exc:
            # **Closed, not merely dropped.** Several of these arrive over a
            # perfectly healthy socket — `AssertionError` is this library's
            # request-timeout, and `ResponseError` is the set saying no — so
            # abandoning the reference leaves the websocket open and, worse,
            # leaves the reader task `start_listening` spawned holding it alive
            # against collection. On a daemon that runs for months, one leak per
            # transient error is the whole failure.
            art, self._art = self._art, None
            if art is not None:
                await self._quietly_close(art)
            raise TvUnavailable(f"{verb} failed against the television at {self._host} ({_named(exc)})") from exc


def _named(exc: Exception) -> str:
    """`TypeName: message`, because several of these carry an empty message."""
    return f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
