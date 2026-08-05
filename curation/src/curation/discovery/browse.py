"""The seam a collection is *browsed* through, as opposed to searched.

Phase 2 asks a provider "do you hold this particular work". This asks a
different question — "what do you hold by this artist" — and the difference is
not a parameter on the first one. A search is given a work and judges whether
what came back is it; a browse is given a facet, and every record that matches
is, by construction, a work the collection holds under its own name. There is
nothing to judge, and one call serving both would invite a caller to run the
identity comparison over records that were never claimed to be anything else.

**What comes back is a supplement, never a resolution.** No image reached
through this seam may be attached to a work phase 1 named — that is the confident
near-match the data model forbids, and here it is forbidden structurally rather
than by rule: a browse is never told which work failed, so it has nothing to
attach an image to. What it produces becomes its own candidate, carrying the
collection's own title and attribution.

**Facets travel in as a batch, and that is a requirement rather than an
optimisation.** A run supplements from several artists at once, and the works
offered must be spread across them — one prolific artist otherwise fills the
whole allowance and the offer silently becomes about that artist instead of about
the intent. Spreading them means knowing what each facet matched *separately*, so
the seam returns a group per facet rather than one merged list a caller would
have to re-partition by guessing which record answered which query.

**`FoundImage` is reused rather than mirrored**, because a collection's record
*is* an image instance in every respect this product cares about: an address, a
title, an attribution, the master's dimensions and a rights statement. A parallel
type carrying the same eight fields would be a second thing to update whenever a
provider learns to report a ninth.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Protocol, runtime_checkable

from curation.discovery.images import FoundImage

#: Confidence recorded for an offered work's instance.
#:
#: **Not the outcome of a comparison, because there is nothing to compare.**
#: Phase 2 earns its confidence by checking that the title and artist a provider
#: returned are the ones that were asked for; here the record and the request are
#: the same object — the collection produced both the work and the picture of it
#: from one row of its own catalogue. Running a title against itself would report
#: certainty it had not established.
#:
#: Deliberately not 1.0, and for the same reason phase 2's confident match is
#: not: nothing here has inspected the image, so the top of the scale stays free
#: for a provider that can. It equals that constant today and is written
#: separately rather than imported from it, because the two answer different
#: questions and a change to either has no business moving the other.
OFFERED_CONFIDENCE: Final[float] = 0.95


@dataclass(frozen=True, slots=True)
class BrowseQuery:
    """The facet the collection is filtered by.

    One field today, and it is a class rather than a bare string so that a second
    facet does not change this seam's signature. Widening past artist adjacency
    is gated on a measurement per `product-brief.md` — style, classification and
    period were measured missing on ordinary spellings — so the room is left
    without the speculation.
    """

    artist: str


@dataclass(frozen=True, slots=True)
class OfferedGroup:
    """What one facet matched: some of the works, and how many there were in all.

    **`matched` is the collection's total, not `len(works)`**, and the difference
    is the point. A curator told "offered one work by this artist" reads it very
    differently depending on whether the collection holds one or four hundred, and
    `product-brief.md` requires an offered work to say which. `works` is capped by
    what the caller asked for; `matched` never is.
    """

    query: BrowseQuery
    matched: int
    works: Sequence[FoundImage]


class CollectionBrowseFailure(Exception):
    """A collection could not be browsed, or could not be understood.

    Distinct from "browsed, and it holds nothing for that facet", which is an
    ordinary answer and the honest one for an artist the collection does not
    carry. A run reporting the second as the first would tell a curator the
    collection has nothing when a server was briefly down.
    """


@runtime_checkable
class CollectionBrowse(Protocol):
    """A wired collection, as the run that supplements from it sees one."""

    @property
    def provider(self) -> str:
        """The name works offered from this collection are recorded under."""

    def browse(self, queries: Sequence[BrowseQuery], *, per_query: int) -> Sequence[OfferedGroup]:
        """Wall-appropriate works the collection holds, grouped by facet.

        `per_query` bounds how many works each group carries, never how many it
        reports matching. A facet the collection has nothing for yields a group
        with no works rather than being dropped, so a caller can tell "asked and
        the collection holds none" from "never asked".

        **A `per_query` of zero or less means "do not ask"**, and the groups come
        back empty without the collection being consulted. Stated because the
        empty group is otherwise the same shape as "asked and it holds none", and
        an implementation left to choose would make a caller unable to tell a
        switched-off supplement from an exhausted one.

        Ordered by nothing the caller should read. The Art Institute's relevance
        score survives a filter-only query — one Ellsworth Kelly painting comes
        back at 13,535 against its siblings' 6 to 8 — so an implementation that
        passed the provider's order through would hand the caller a ranking that
        looks meaningful and is not (`artic-api-findings.md`).

        Raises `CollectionBrowseFailure` when the collection could not be asked.
        """
