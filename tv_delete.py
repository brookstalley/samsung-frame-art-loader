"""Removing artwork from the television, confirmed against the TV's own list.

`samsungtvws`'s async `delete_list` sends the request and returns `None` whether
the television removed anything or not — it never reads the reply. Deletion is
the library's only removal verb, so that is the most consequential silent
failure on the TV interface: a run can log "deleting 12 images", delete none,
and look identical either way.

Confirmation therefore cannot come from the call. It comes from re-reading the
television's content list and checking the ids are gone, which is also stronger
than trusting an acknowledgement would be: it reports the state the set is
actually in rather than what it said it would do.

Three outcomes are kept apart, because collapsing them is the whole defect:

* every requested id is gone — `DeleteResult.complete`
* the TV still lists some of them — `DeleteResult.surviving` names which, and a
  WARNING is logged by this module so the outcome cannot go unreported even if a
  caller ignores the return value
* nobody could establish which of those it is — `DeleteNotConfirmed`, where
  reporting either success or failure would be a guess

That third case covers the refused request and the unreadable list alike. They
are one finding, not two: the removal is sent and the reply discarded, so a
caller that separated them would be distinguishing states it cannot observe.

Two entry points, differing only in what an unknown outcome costs the caller.
`delete_list_confirmed` raises; `remove_from_tv` logs an ERROR and returns None,
for the caller with work left that is worth more than a tidy television.
"""

import logging

#: The category every image this project uploads lands in. Samsung exposes no
#: way to create another: 2 = my pictures, 4 = favourites, 8 = store, and the
#: upload verb takes no category argument.
UPLOADED_CATEGORY = "MY-C0002"


class DeleteNotConfirmed(Exception):
    """What the television holds could not be established after a removal request.

    Distinct from "the images are still listed", which is a known failure. This
    is the unknown one: the caller knows only that it asked. Raised whether the
    request itself was refused or the confirming read could not be made — the
    library discards the reply either way, so those are the same finding.
    """


class DeleteResult:
    """What the television actually holds after a removal was requested."""

    def __init__(self, requested: tuple[str, ...], surviving: tuple[str, ...]):
        self.requested = requested
        self.surviving = surviving

    @property
    def deleted(self) -> tuple[str, ...]:
        """The requested ids the television no longer lists."""
        still_there = set(self.surviving)
        return tuple(content_id for content_id in self.requested if content_id not in still_there)

    @property
    def complete(self) -> bool:
        """True when every requested id is gone from the television."""
        return not self.surviving

    def __repr__(self) -> str:
        return f"DeleteResult(requested={len(self.requested)}, deleted={len(self.deleted)}, surviving={self.surviving!r})"


async def delete_list_confirmed(tv_art, content_ids, category: str = UPLOADED_CATEGORY) -> DeleteResult:
    """Ask the television to remove `content_ids`, then verify against its list.

    `tv_art` is a `samsungtvws.async_art.SamsungTVAsyncArt`, taken as a
    parameter rather than imported so this module can be exercised without the
    library or a television.

    Any failure to establish what the set holds — whether the removal request
    itself was refused, or the confirming read could not be made — raises
    `DeleteNotConfirmed`, chained to the original. That is one outcome, not two:
    in both cases the caller knows only that it asked.
    """
    # Preserve order and drop repeats: the TV is asked once per id, and the
    # report back to the caller reads in the order they asked.
    requested = tuple(dict.fromkeys(content_ids))
    if not requested:
        return DeleteResult(requested=(), surviving=())

    try:
        await tv_art.delete_list(list(requested))
        remaining = await tv_art.available(category=category)
    except Exception as err:  # prawduct:allow prawduct/broad-except -- unowned library, unstable errors; re-raised
        # Caught by outcome rather than by type, deliberately. samsungtvws
        # reports a timed-out art request by returning None from
        # `wait_for_response` and then *asserting* on it, raises its own
        # ResponseError when the set replies with an error event, and lets
        # websockets and JSON errors through from underneath — a list that has
        # already changed once in this library's history and is not ours to
        # depend on. Every one of them means the same thing here, and naming a
        # subset is how the ones left out become an abort in the caller.
        raise DeleteNotConfirmed(
            f"asked the television to remove {len(requested)} image(s) and could not establish what it holds"
        ) from err

    still_listed = {entry["content_id"] for entry in remaining}
    surviving = tuple(content_id for content_id in requested if content_id in still_listed)
    if surviving:
        logging.warning(
            "The television still lists %d of %d image(s) after a removal request: %s",
            len(surviving),
            len(requested),
            ", ".join(surviving),
        )
    return DeleteResult(requested=requested, surviving=surviving)


async def remove_from_tv(tv_art, content_ids, category: str = UPLOADED_CATEGORY) -> DeleteResult | None:
    """Remove images and report what the set confirmed, or `None` if it could not say.

    The caller for whom an unconfirmable removal is not worth abandoning the
    rest of its work. Leftover images on the television are untidy; a caller
    that stopped here would skip everything it had left to do — for the
    housekeeping pass that means the catalogue save and every pending upload,
    which is the worse outcome. The ERROR keeps it from being a silent one.

    Use `delete_list_confirmed` directly where an unconfirmed removal genuinely
    should stop the caller.
    """
    try:
        return await delete_list_confirmed(tv_art, content_ids, category=category)
    except DeleteNotConfirmed as err:
        logging.error("Removal of %d image(s) could not be confirmed, continuing: %s", len(content_ids), err)
        return None


def describe_removal(result: DeleteResult | None, requested_count: int) -> str:
    """One sentence about a removal that never claims more than is known.

    The three outcomes read differently on purpose. "Confirmed 0 of 5" is a
    claim — the set was asked and kept them all — and it must not be the
    sentence printed when nobody could tell.
    """
    if result is None:
        return f"asked the TV to remove {requested_count} image(s); it could not confirm any of them"
    return f"the TV confirmed {len(result.deleted)} of {requested_count} image(s) removed"
