"""The `samsungtvws` fork, corrected at the seam.

Every non-obvious line here answers something measured against this deployment's
own television rather than read from the library's source. The measurements live
in `platform-and-dependency-findings.md` § The television and are firmware-scoped;
what is encoded here is the *behaviour* they establish:

* **Constructing the client performs blocking network I/O** — 0.24 s with a
  cached token, 8.4 s while pairing, ~15 s against a set that is asleep, which is
  most of the time. It cannot happen on the event loop, so it happens on a thread.
* **`start_listening()` can hang rather than raise**, and on another attempt
  raised after ~15 s — not even consistent between runs, so it gets a ceiling of
  this plane's own. **Not a symptom of art mode being off**, which is what it was
  first taken for: with a cached token the channel opens against a dark panel and
  against a set showing a programme. It has been seen failing *in* art mode after
  heavy connect-and-close churn, which points at a cap on concurrent clients.
* **`upload()` reports failure on uploads that succeeded.** The image is on the
  wall and the caller is told it is not, which is worse than a plain failure
  because it lies in the safe-looking direction: a caller that retries duplicates
  the image. So an upload is confirmed against the set's own content list.
* **`delete_list()` never reads its reply** — it sends and returns None whether
  the set removed anything or not. Removal is confirmed the same way.
* **`select_image()` neither reports nor can be asked what it did.** It sends and
  returns; the set announces the result by *emitting* `image_selected`, carrying
  the id and an `is_shown` flag. Selection is confirmed by listening for that
  event from before the request goes out.

The rule those three share, and the one to apply to any verb added later:
**this library's return values are not trustworthy in either direction; confirm
against the television itself.**

**`get_current_artwork` is not that confirmation, and believing it was cost this
plane two days.** It reports the *art-store* slot — its replies carry
`"content_type": "artstore"` — and it is unaffected by selecting a user upload.
Measured on 2026-08-07 against a set in art mode: the wall visibly changed to the
requested image, `image_selected` fired at +1.0 s with `is_shown: "Yes"`, and
`get_current_artwork` went on naming the same art-store id it had named for days,
through 37 seconds of polling. It was adopted as the confirming read a day
earlier because it *agreed* in the dark state — where it is right by coincidence,
having simply never changed. There is no reader on this firmware that answers
"what is on the wall"; `get_slideshow_status.current_content_id` is empty while
the slideshow is off, which is the state this plane requires.

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
    SelectionAnnouncement,
    SelectionObserver,
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

#: The set's announcement that a selection took effect. It carries the id and an
#: `is_shown` flag, and it is the only signal on this firmware that distinguishes
#: a selection the wall acted on from one it accepted and ignored.
_IMAGE_SELECTED: Final[str] = "image_selected"

#: `is_shown` when the set means it. A string rather than a boolean on the wire.
_IS_SHOWN_YES: Final[str] = "Yes"

#: Everything the set says when its art mode may have changed. All four are
#: treated identically — as "ask again" — so none of their payloads is parsed and
#: the list can grow without anything downstream having to learn a new shape.
#: `wakeup` and `go_to_standby` are here because the transition this plane waits
#: for is somebody picking up a remote, which is what they report.
_ART_MODE_ANNOUNCEMENTS: Final[tuple[str, ...]] = (
    "art_mode_changed",
    "artmode_status",
    "go_to_standby",
    "wakeup",
)


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
        select_confirm_seconds: float,
    ) -> None:
        self._host = host
        self._port = port
        self._token_file = token_file
        self._client_name = client_name
        self._connect_timeout = connect_timeout_seconds
        self._upload_timeout = upload_timeout_seconds
        self._select_confirm = select_confirm_seconds
        self._art: SamsungTVAsyncArt | None = None

        #: The selection currently awaiting the set's announcement, as the id that
        #: was asked for and the future its answer resolves. One slot rather than a
        #: map because selection here is strictly sequential — one reconciliation
        #: loop, one image at a time, the same property `upload`'s marker relies on.
        self._awaiting: tuple[str, asyncio.Future[bool]] | None = None

        #: Everyone else who wants to hear what the set says about the wall.
        #: **Held here rather than registered with the library**, which keeps one
        #: handler per event and would let the second subscriber silently unseat
        #: the confirmation above. Survives reconnection because it belongs to this
        #: object, while the library callback is re-registered per connection.
        #:
        #: **What bounds it**: subscribers register at composition and are one per
        #: distinct caller — today exactly one, the daemon — so this is bounded by
        #: the program's structure rather than by anything that happens at runtime.
        #: That is why it needs no cap and no removal verb, and why re-subscribing
        #: is idempotent rather than additive: reconnection is the one event that
        #: would otherwise grow it with time.
        self._selection_observers: list[SelectionObserver] = []

        #: Whether the set has said something about art mode that nobody has
        #: collected yet. An edge, not a state: it says "ask again", and the
        #: answer always comes from a fresh read.
        self._art_mode_announced = False

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
            # The set accepted the websocket and then said nothing. **The cause is
            # not known from here**, and the message says so rather than naming
            # art mode: with a cached token this channel opens perfectly well
            # against a dark panel and against a programme, and this failure has
            # been observed *in* art mode after many connections in quick
            # succession. Waiting is the move that has actually worked.
            await self._quietly_close(art)
            raise TvUnavailable(
                f"the television at {self._host} accepted a connection but never opened the art channel within "
                f"{self._connect_timeout:.0f}s; it has been seen doing this after many connections in quick "
                "succession, and clearing after a couple of minutes' quiet"
            ) from exc
        except _LIBRARY_FAILURES as exc:
            await self._quietly_close(art)
            raise TvUnavailable(f"the television at {self._host} refused the art channel ({_named(exc)})") from exc

        # Registered per connection, not once per process: `_call` abandons the
        # client on any failure, so the next attempt is a *new* object and a
        # subscription made against the old one would leave selections
        # unconfirmable for the rest of the daemon's life.
        #
        # **The library keeps one handler per event, not a list** — its
        # `set_callback` is a plain dict assignment — so a second subscriber to
        # `image_selected` does not join this one, it *replaces* it. The failure
        # is silent and total: every selection then falls to its timeout and is
        # reported as a wall that did not change, while the newcomer works
        # perfectly. Anything else here that wants this event must be fanned out
        # from this handler rather than registered alongside it. A second
        # *distinct* event is safe, and is another line here plus a handler.
        art.set_callback(_IMAGE_SELECTED, self._on_image_selected)
        for announcement in _ART_MODE_ANNOUNCEMENTS:
            art.set_callback(announcement, self._on_art_mode_changed)

        # A reconnection is itself news: the set may have entered art mode while
        # this plane could not hear it, and without this the wall would sit out
        # whatever wait was in force when the connection dropped.
        self._art_mode_announced = True
        self._art = art

    def observe_selections(self, observer: SelectionObserver) -> None:
        """Also hear what the set says about the picture on the wall.

        **The reason this method exists rather than a second `set_callback`.** The
        library keeps one handler per event, so registering directly would replace
        the confirmation handler rather than join it, and every rotation would then
        fall to its timeout and report a wall that would not move — silently, while
        the newcomer worked perfectly. Subscribing here fans out instead, which is
        the only safe way to add a listener.

        Observers are called on the library's reader task, so an observer must be
        cheap and must not block: a slow one delays every message on this socket,
        including the confirmations the rotation is waiting for. Anything
        expensive — drawing a panel, writing a file — belongs on the caller's own
        task, driven by what it learns here.

        **Registering the same observer twice registers it once.** This list is
        per client object and lives as long as the process, while the library
        callbacks below are re-registered on every reconnection — so a caller that
        reasonably re-subscribed after a drop would otherwise be told twice per
        announcement for the rest of the daemon's life, and the drawing that
        follows would redraw a panel it had just drawn. **There is deliberately no
        way to unsubscribe**: nothing needs one, the list is bounded by the number
        of distinct callers rather than by time, and an unused removal path is one
        more thing to keep correct.
        """
        if observer not in self._selection_observers:
            self._selection_observers.append(observer)

    def _on_image_selected(self, _event: str, response: dict[str, Any]) -> None:
        """Resolve the selection this announcement is about, then tell everyone.

        Deliberately synchronous and total: it runs on the library's reader task,
        where an exception is not delivered to anybody who could act on it and
        would take the socket's reader down with it. Anything unrecognised is left
        alone, and the waiting selection falls to its timeout — which reports the
        wall as unchanged, the safe direction, since claiming a picture is up when
        it is not is the defect this whole path exists to prevent.

        **The announcement is parsed before the pending selection is consulted,
        and that order is the point.** The set echoes selections nobody here made
        — somebody using the remote — and those arrive with no pending selection
        at all. Reading `_awaiting` first, as this did while confirmation was its
        only job, discarded exactly the announcements an observer wants most: the
        ones where the wall changed and this plane did not do it.
        """
        announcement = _announced(response)
        if announcement is None:
            return
        self._resolve_pending(announcement)
        self._tell_observers(announcement)

    def _resolve_pending(self, announcement: "SelectionAnnouncement") -> None:
        """Settle the selection now in flight, if this announcement is about it.

        An announcement for a *different* id is ignored rather than treated as a
        refusal: letting one of the set's echoes resolve this future would report
        the wrong work as shown.
        """
        pending = self._awaiting
        if pending is None:
            return
        content_id, waiter = pending
        if waiter.done() or announcement.content_id != content_id:
            return
        waiter.set_result(announcement.is_shown)

    def _tell_observers(self, announcement: "SelectionAnnouncement") -> None:
        """Hand the announcement to every observer, and let none of them break another.

        **Each is isolated, because they are strangers to each other.** An observer
        that raises must not cost a later one its notification, and — since this
        runs on the reader task — must not take the socket down. The failure is
        logged rather than swallowed: an observer raising on every announcement is
        a real fault, and the journal is where this plane says so.
        """
        for observer in self._selection_observers:
            try:
                observer(announcement)
            except Exception:  # prawduct:allow prawduct/broad-except -- reader task; observers are strangers
                log.exception(
                    "an observer of the television's selections raised; the others still ran",
                    extra={"event": "tv.selection_observer_failed", "tv_content_id": announcement.content_id},
                )

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

    async def show(self, content_id: str) -> bool:
        """Select an image and wait for the set to announce that it is displayed.

        **The waiter is armed before the request goes out**, which is the whole
        reason this is one method rather than two. The announcement has been
        measured arriving 0.49 s after the request, well inside the window a
        caller would need to register a listener afterwards, so a select-then-
        listen shape drops the answer it is waiting for and reports a working wall
        as stuck.

        A set that never announces gets `False` rather than an exception: with its
        panel dark this television accepts the request, raises nothing, emits no
        event, and goes on displaying what it had — indefinitely, while uploads,
        removals and brightness all succeed. That is a stated outcome, not a
        connection failure, and the caller distinguishes them.

        **A redundant selection is announced too** — asking for the image already
        displayed emits the event with `is_shown: "Yes"` (measured 2026-08-07), so
        the restart path that re-shows the current picture confirms normally
        rather than reporting every restart as a wall that would not move.
        """
        waiter: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        self._awaiting = (content_id, waiter)
        try:
            await self._call("select_image", self._client().select_image(content_id, show=True))
            try:
                return await asyncio.wait_for(waiter, timeout=self._select_confirm)
            except TimeoutError:
                return False
        finally:
            # Cleared on every route out, including the failure that drops the
            # connection: a stale slot would let the *next* connection's first
            # announcement resolve a future nobody is waiting on any more.
            self._awaiting = None

    async def showing_art(self) -> bool:
        """Whether the set is showing art, read fresh every time it is asked.

        **Never answered from the announcements below**, deliberately. A cached
        view of the set's state is wrong in the one direction that matters: a
        missed announcement would license a selection into somebody's programme,
        and that is silent, daily and rude. A read costs one round trip on a
        rotation that happens every few minutes.

        Anything other than the set plainly saying `on` is a no, including a reply
        this seam cannot read — a wall that waits is late, a wall that does not is
        an interruption.
        """
        mode = await self._call("get_artmode", self._client().get_artmode())
        return mode == "on"

    def art_mode_announcement_pending(self) -> bool:
        announced, self._art_mode_announced = self._art_mode_announced, False
        return announced

    def _on_art_mode_changed(self, _event: str, _response: dict[str, Any]) -> None:
        """Note that the set said something about art mode, and nothing more.

        The payload is deliberately not parsed. This is a nudge to go and ask
        again, not a source of truth, so the only thing worth knowing is that
        *something changed* — which makes it correct for `art_mode_changed`,
        `artmode_status` and the wake and standby notices alike, without this
        seam having to model each one's spelling. Getting the payload wrong would
        then be impossible rather than merely unlikely.
        """
        self._art_mode_announced = True

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


def _announced(response: dict[str, Any]) -> "SelectionAnnouncement | None":
    """Read the set's selection announcement, or None if it is not one we can read.

    A `content_id` that is absent or is not a string is unreadable rather than
    empty: this feeds both a confirmation and every observer, and a blank id would
    match nothing while looking like an answer.
    """
    try:
        announced = json.loads(response["data"])
    except (KeyError, TypeError, json.JSONDecodeError):
        return None
    if not isinstance(announced, dict):
        return None
    content_id = announced.get("content_id")
    if not isinstance(content_id, str) or not content_id:
        return None
    return SelectionAnnouncement(content_id=content_id, is_shown=announced.get("is_shown") == _IS_SHOWN_YES)
