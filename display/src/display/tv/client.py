"""The television, as the rest of this plane is allowed to see it.

**The interface exists because the client behind it is a liability.** The
`samsungtvws` fork this product depends on is unowned, four months static, and
carries a known defect in the verb that matters most; there is no maintained
alternative offering the async art client this plane is built on. The mitigation
was never "switch upstreams" — it is keeping the television boundary small and
behind a seam, so replacing the client is a swap rather than a rewrite.

So this module is a contract and holds no protocol knowledge. Everything the
library does badly is corrected on the other side of it, and what comes through
here is the corrected form:

* An **upload** returns a content id or raises. It never returns "no id, and no
  statement about whether the image landed", which is what the library does and
  what the 2024 loader turned into a duplicate on the wall.
* A **removal** reports what the television actually holds afterwards, and keeps
  *unconfirmable* apart from *failed*, because collapsing those two was the
  original defect.
* Everything that can go wrong with the connection arrives as `TvUnavailable`,
  regardless of which of the library's seven exception types produced it. An
  asleep television is an expected operating condition here, not an incident.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

#: The category every image this product uploads lands in. Samsung exposes no way
#: to create another — 2 is my-pictures, 4 favourites, 8 the store — and the
#: upload verb takes no category argument at all. Rotation is therefore a pointer
#: into one flat list, which is why bindings and orphan removal exist.
UPLOADED_CATEGORY: Final[str] = "MY-C0002"


class TvUnavailable(Exception):
    """The television could not be reached, or stopped answering mid-conversation.

    One type for every underlying cause on purpose. The caller's response is the
    same to all of them — hold the wall where it is, back off, try again — and a
    daemon that branched on which library exception arrived would be encoding the
    library's internals into the loop that exists to be independent of them.
    """


class TvUploadFailed(Exception):
    """An image was not put on the television, confirmed rather than assumed."""


class TvRemovalUnconfirmed(Exception):
    """What the television holds after a removal could not be established.

    Distinct from "the images are still listed", which is a known failure. This
    is the unknown one: the caller knows only that it asked. The library discards
    the reply to a removal, so a caller that reported either outcome would be
    guessing.
    """


@dataclass(frozen=True)
class RemovalOutcome:
    """What the television held after a removal was requested, read back from it."""

    requested: tuple[str, ...]
    surviving: tuple[str, ...]

    @property
    def removed(self) -> tuple[str, ...]:
        """The requested ids the television no longer lists."""
        still_there = set(self.surviving)
        return tuple(content_id for content_id in self.requested if content_id not in still_there)

    @property
    def complete(self) -> bool:
        return not self.surviving


@dataclass(frozen=True)
class SelectionAnnouncement:
    """The set's own word about what is on the wall now.

    **The only honest account of the wall this product has.** The set reports the
    picture it is displaying by emitting this; the read that looks like it should
    answer the same question — `get_current_artwork` — reports the art-store slot
    instead, and named one unchanging id across every observation ever made here
    while the picture visibly changed (`samsung-tv-state-findings.md`).

    Announcements arrive for selections nobody here made, because somebody using
    the remote produces one too. A consumer must therefore treat the id as news
    about the wall rather than as an echo of its own request.
    """

    content_id: str
    #: The set's `is_shown` flag, already read off the wire, where it is the
    #: string "Yes" rather than a boolean.
    is_shown: bool


#: What a selection observer is handed. Called on the television's reader task,
#: so it must be cheap, must not block, and must not assume anything about which
#: task it runs on.
SelectionObserver = Callable[[SelectionAnnouncement], None]


class TvClient(ABC):
    """What the daemon may ask of a television.

    An abstract base rather than a structural protocol, deliberately: the test
    double subclasses it, so a method added here fails the fake loudly at import
    instead of passing every test while the real client grew a capability nothing
    exercised.
    """

    @abstractmethod
    async def connect(self) -> None:
        """Reach the set and open the art channel, or raise `TvUnavailable`."""

    @abstractmethod
    async def close(self) -> None:
        """Let the connection go. Never raises — this runs on the way out."""

    @abstractmethod
    async def disable_native_slideshow(self) -> None:
        """Stop the set's own slideshow, so it cannot fight host-driven selection."""

    @abstractmethod
    async def listed_content_ids(self) -> frozenset[str]:
        """Every id the television currently lists in the uploaded category."""

    @abstractmethod
    async def upload(self, path: Path) -> str:
        """Put an image on the television and return the id it was given.

        Raises `TvUploadFailed` only when the image is confirmed *not* to be
        there — never merely because the library said so.
        """

    @abstractmethod
    async def show(self, content_id: str) -> bool:
        """Put an image the set already holds on the wall, and say whether it appeared.

        **Asking and confirming are one call because they cannot safely be two.**
        The television reports a selection by *emitting* an event, not by
        answering a later question, so the only sound confirmation listens from
        before the request is sent. Split across two calls, every caller races
        the set — and the shape invites the confirming *read* that this seam
        previously carried, which was measured answering about something else
        entirely (see `samsung.py`).

        Returns False for the failure the return value of a bare selection cannot
        express: a set that accepts the request, raises nothing, and goes on
        displaying what it had. Raises `TvUnavailable` if the set could not be
        asked at all — which is a different event, and the caller treats it so.
        """

    @abstractmethod
    async def showing_art(self) -> bool:
        """Whether the set is showing art, and may therefore be asked to change it.

        **This is a permission question, not a diagnostic.** Selecting an image on
        a set that is showing a television programme does not fail politely — it
        switches the set into art mode and takes the screen off the person
        watching (measured; `samsung-tv-state-findings.md`). So nothing may be put
        on the wall without asking this first.

        **False on anything short of a clear yes**, including a reply this seam
        cannot read. The two errors are not symmetric: a wall that waits is late,
        and a wall that does not wait interrupts somebody's evening. Raises
        `TvUnavailable` when the set could not be asked at all, which is the
        existing outage path and a different event again.
        """

    @abstractmethod
    def art_mode_announcement_pending(self) -> bool:
        """Whether the set has announced an art-mode change since this was last asked.

        **A hint that it is worth asking again, never an answer in itself.** The
        set announces its own transitions, so a wall that backed off because
        nobody was in art mode can resume the moment somebody is, instead of
        sitting out the remainder of a wait. What it must not become is a cached
        view of the set's state: a missed announcement would then freeze the wall
        for ever or, worse, license a selection into somebody's programme. Missing
        one here costs only promptness, because the decision is still a fresh
        read.

        Synchronous and consuming — it reports an edge, and clears it.
        """

    @abstractmethod
    async def reported_art_mode(self) -> str | None:
        """The set's own art-mode flag, or None if it would not answer.

        Diagnosis, never control flow — nothing decides what to do from this.
        It is asked only when a selection has already been shown not to have
        landed, so that the one line an operator reads says *why* the wall is not
        changing rather than merely that it is not. The flag is the set's own word
        and is not a capability test: this television serves uploads, removals and
        brightness perfectly well while reporting art mode off.
        """

    @abstractmethod
    async def remove(self, content_ids: Sequence[str]) -> RemovalOutcome:
        """Remove images, and report what the television holds afterwards."""

    @abstractmethod
    async def set_brightness(self, value: int) -> None:
        """Set the panel's brightness on the set's own scale."""

    @abstractmethod
    def observe_selections(self, observer: SelectionObserver) -> None:
        """Be told, from now on, whatever the set says about the picture on the wall.

        **A method rather than a callback anyone may register, because the library
        underneath keeps one handler per event.** A second subscriber registered
        directly does not join the selection confirmation, it *replaces* it — after
        which every rotation falls to its timeout and reports a wall that will not
        move, silently, while the new subscriber works perfectly. This fans out
        instead, so adding a listener cannot break the one that was already there.

        Observers run on the client's own reader task and must be cheap. Anything
        expensive belongs on the observer's own task, driven by what it learns.
        """
