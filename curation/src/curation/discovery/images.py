"""The seam phase 2 reaches a provider through, and the types that cross it.

Phase 2 turns each work phase 1 named into image *instances* — where the picture
can actually be got, how big it is, and whether it is genuinely that work. Doing
that means calling a museum's API over the network. **None of that is in this
module.** What is here is the narrow interface those calls are reached through, so
everything above — driving a run, ranking instances, caching previews, deciding a
work is unresolved — is buildable and testable without a network.

The seam is the same shape as phase 1's for the same reason: the provider is
replaceable. `provider` is an open vocabulary in the data model precisely because
one museum is the first of many, and a second one is an implementation of this
protocol rather than a change to anything that consumes it.

**A provider reports what it found; it never decides whether it is right.** The
judgement — is this genuinely the work that was asked for — is made above the
seam, from the title and artist a provider reports, and deliberately not from
whatever relevance number the provider offers. That is not a stylistic
preference: the Art Institute's own score was measured non-comparable between
queries and non-zero for a collection it does not hold, so ranking by it attaches
a real painting by a real artist to a request for something else with no signal
that anything went wrong (`artic-api-findings.md`). One judgement, above the
seam, is also what stops two providers from disagreeing about what "confident"
means.

**Phase 2 over a museum API spends nothing**, which is why nothing here carries a
cost the way phase 1's seam does. The comparison that establishes confidence is
local and deterministic, and the APIs are open. A provider that did charge would
need spend to travel back across this seam, and that is a change to make when one
arrives rather than scaffolding for one that has not.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from curation.persistence.records import AcquisitionMethod, RightsStatus, SourceClass


@dataclass(frozen=True, slots=True)
class ImageQuery:
    """The work an instance is wanted for, as phase 1 named it.

    Carries the proposed title and artist rather than a `CandidateWork`, for the
    same reason `ProposedWork` is not a candidate row: a provider has no business
    with ids, run references or verdicts, and keeping the row on this side of the
    seam is what stops a provider implementation from being able to write one.
    """

    title: str
    artist: str | None = None


@dataclass(frozen=True, slots=True)
class FoundImage:
    """One image instance a provider found, in the provider's own terms.

    **`title` and `artist` are what the provider calls this thing**, and they are
    the evidence confidence is judged from — not decoration, and not the same
    strings as the query. A provider that returned only a URL would leave nothing
    to check the identity against, which is the failure mode the whole
    near-match problem lives in.

    Dimensions are the *master's*, not the preview's. They are what the rendered
    size on the wall is computed from, so a provider that reports a preview's
    dimensions here would put every instance below the floor.
    """

    url: str
    provider: str
    source_class: SourceClass
    acquisition_method: AcquisitionMethod
    title: str
    artist: str | None = None
    preview_url: str | None = None
    estimated_width: int | None = None
    estimated_height: int | None = None
    rights_status: RightsStatus | None = None


class ImageSearchFailure(Exception):
    """A provider could not be asked, or could not be understood.

    Distinct from "asked, and there was nothing there": finding no instance is an
    ordinary and reportable outcome that makes a work `unresolved`, while a
    provider being unreachable says nothing about whether the work exists. A run
    that recorded the second as the first would tell a curator their painting is
    not in the collection because a server was briefly down.
    """


@runtime_checkable
class ImageSearch(Protocol):
    """Phase 2's providers, as everything above them sees them.

    **No `unavailable_reason` here, deliberately — the asymmetry with phase 1's
    seam is the design.** Phase 1 needs one because it refuses at `start`, before
    a run exists, and has to say why. Phase 2 has a run in hand by the time it
    could refuse, and a deployment with no provider is represented by *having no
    provider* rather than by holding one that declines: the run stays at
    `resolving_images`, and the wording a caller reads comes from whether the
    wiring is there. A refusing stand-in here would be a second way to express
    the same absence, and the two would eventually disagree.
    """

    @property
    def provider(self) -> str:
        """The name instances from this search are recorded under.

        Here so that wiring which needs to key something by provider can ask the
        provider rather than repeat its name — a second copy of that string is a
        second thing to update when a provider is added, and the wiring is the
        copy nobody would think to check.
        """

    def find_images(self, query: ImageQuery) -> Sequence[FoundImage]:
        """Every instance this provider holds for the work, unjudged and unranked.

        Raises `ImageSearchFailure` when the provider could not be asked.
        """

    def fetch_preview(self, url: str) -> bytes | None:
        """The bytes behind a preview URL, or `None` if they could not be got.

        Returning `None` rather than raising, because a preview that will not
        download is a degraded review card and not a failed resolution: the
        instance is still real, still selectable, and still carries a source-side
        URL. Losing the whole work over a missing thumbnail would be the tail
        wagging the dog.
        """

    def tile_url(self, url: str) -> str:
        """Where the tiles of the object `url` names are actually served.

        On this seam because the provider is the only thing that can answer it:
        the URL a source records identifies the object, and for a provider serving
        tiles the image service lives somewhere the object's own address does not
        say. A provider whose recorded URLs the tile fetcher can already read
        returns its argument.

        Raises `ImageSearchFailure` when the provider could not be asked, or
        answered without an image.
        """
