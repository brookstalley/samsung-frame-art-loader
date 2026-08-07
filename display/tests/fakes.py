"""A television that behaves like the real one without being one.

**Subclasses `TvClient` rather than duck-typing it**, which is the whole reason
the interface is an abstract base: a verb added to the boundary fails this class
at import instead of quietly leaving the fake behind while every test stays green.

It models the set's *observable* behaviour, not its protocol: images live in one
flat category under ids the set invents, selecting one that is not there is an
error, and each failure the real client can produce can be armed on demand. What
it deliberately does **not** model is the library's misreporting — an upload that
lands while returning None is corrected inside `SamsungTv`, below this seam, and a
fake that reproduced it here would be testing the correction twice and the
daemon's behaviour not at all.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Final

from display.tv import RemovalOutcome, TvClient, TvRemovalUnconfirmed, TvUnavailable, TvUploadFailed

#: A picture the set holds that this product did not put there — an art-store
#: image, in the category the daemon neither uploads to nor removes from. The set
#: is displaying one of these before the daemon has shown anything.
FOREIGN_IMAGE: Final[str] = "SAM-F0000"


class FakeTv(TvClient):
    """One television's worth of observable state, plus arming for each failure."""

    def __init__(self) -> None:
        #: content id -> the file that was uploaded under it.
        self.holding: dict[str, Path] = {}
        self.selected: list[str] = []
        self.brightness: list[int] = []
        self.removed: list[tuple[str, ...]] = []
        self.connects = 0
        self.slideshow_disabled = 0
        self._next_id = 0
        self._connected = False

        #: Armed failures. Each is the real client's behaviour, named for what a
        #: test is trying to reproduce rather than for the exception it raises.
        self.unavailable = False
        self.refuse_uploads = False
        self.removal_unconfirmable = False
        #: Ids the set will not part with, so "removal reported, image survived"
        #: is reachable without making the whole call fail.
        self.unremovable: set[str] = set()
        #: Ids the set lists and still refuses to select. A real one has been
        #: observed refusing calls it should accept, and the daemon has to tell
        #: that apart from an id the set has simply forgotten — the two arrive as
        #: the same exception and want opposite responses.
        self.refuse_selection_of: set[str] = set()

        #: The set takes every selection and displays none of them. **Observed on
        #: a real television on 2026-08-07**, with its panel dark: `select_image`
        #: returned, raised nothing and emitted no event, while what the set
        #: displayed did not change over twelve seconds and repeated attempts.
        #: Armed here because the failure is invisible from the call — a fake that
        #: could not reproduce it let the daemon report rotations that never
        #: happened, and every test passed.
        self.displays_nothing_selected = False
        #: What the set is displaying. It starts on a picture of the set's own
        #: rather than on nothing, because **a Frame is never displaying nothing**
        #: — the one observed refusing selections went on showing an art-store
        #: image throughout. That is what makes the failure detectable: the
        #: observable is that the wall did not *change*, not that it is blank.
        self.displaying: str | None = FOREIGN_IMAGE
        #: Ids the set announces as selected while reporting `is_shown: "No"`. A
        #: distinct arming from `displays_nothing_selected`, which is silence: the
        #: set answering "I took it and I am not showing it" is a different wire
        #: behaviour from it never answering, and both mean the wall did not move.
        self.admits_not_showing: set[str] = set()
        #: The set's own art-mode flag, as it would report it.
        self.art_mode: str | None = "on"

    async def connect(self) -> None:
        """Cheap once connected, exactly as the real client is.

        **This is load-bearing and was got wrong first.** `SamsungTv.connect`
        returns immediately when it already holds a client, so in production a set
        that goes away *after* a connection is established is discovered by the
        next real call — `select_image`, `upload` — and not by `connect`. A fake
        that re-checked reachability every pass made the outage arrive at the top
        of the tick instead, so the whole of the directive path was unreachable
        while the set was away: two tests asserting that a directive is not
        consumed during an outage passed because the code under test never ran. A
        mutation sweep found it by swapping two statements neither test executed.
        """
        if self._connected:
            return
        self._check_reachable()
        self.connects += 1
        self._connected = True

    async def close(self) -> None:
        return None

    async def disable_native_slideshow(self) -> None:
        self._check_reachable()
        self.slideshow_disabled += 1

    async def listed_content_ids(self) -> frozenset[str]:
        self._check_reachable()
        return frozenset(self.holding)

    async def upload(self, path: Path) -> str:
        self._check_reachable()
        if self.refuse_uploads:
            raise TvUploadFailed(f"{path.name} is not on the television after an upload attempt")
        self._next_id += 1
        content_id = f"MY-F{self._next_id:04d}"
        self.holding[content_id] = path
        return content_id

    async def show(self, content_id: str) -> bool:
        self._check_reachable()
        if content_id not in self.holding:
            # The real set answers an unknown id with an error rather than a
            # blank wall, and a fake that accepted anything would let a daemon
            # bug — selecting an orphaned binding — pass every test.
            raise TvUnavailable(f"the television does not hold {content_id}")
        if content_id in self.refuse_selection_of:
            raise TvUnavailable(f"the television refused {content_id}")
        self.selected.append(content_id)
        if self.displays_nothing_selected or content_id in self.admits_not_showing:
            # The wall is left where it was, which is the point: the request was
            # taken and the picture did not change.
            return False
        self.displaying = content_id
        return True

    async def reported_art_mode(self) -> str | None:
        return self.art_mode

    async def remove(self, content_ids: Sequence[str]) -> RemovalOutcome:
        self._check_reachable()
        if self.removal_unconfirmable:
            raise TvRemovalUnconfirmed("the removal request was refused; what the set holds is unknown")
        requested = tuple(content_ids)
        self.removed.append(requested)
        for content_id in requested:
            if content_id not in self.unremovable:
                self.holding.pop(content_id, None)
        return RemovalOutcome(requested=requested, surviving=tuple(c for c in requested if c in self.holding))

    async def set_brightness(self, value: int) -> None:
        self._check_reachable()
        self.brightness.append(value)

    def _check_reachable(self) -> None:
        if self.unavailable:
            # The real client drops its handle on any failed call, so the next
            # attempt reconnects rather than retrying on a websocket whose state
            # nobody can know. A fake that stayed "connected" through a failure
            # would let a daemon skip the reconnect and still pass.
            self._connected = False
            raise TvUnavailable("the television is asleep")

    # -- what a test asserts against ---------------------------------------

    @property
    def on_the_wall(self) -> Path | None:
        """The file the wall is *displaying*, or None if it is displaying none.

        Read from what the set displays rather than from the last id requested,
        so that a test asserting a picture reached the wall cannot be satisfied by
        a request the set ignored. Those were the same thing until a television
        was found accepting selections and displaying nothing.
        """
        return self.holding.get(self.displaying) if self.displaying else None
