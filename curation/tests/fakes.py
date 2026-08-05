"""A discovery engine the suite drives, standing where a paid one will stand.

**Not scaffolding.** This is the provider every test of the run lifecycle runs
against, and it stays that way once a real engine exists: the lifecycle's
interesting cases are a run that breaks, a run the provider refuses to fund, and
a run that overruns its search allowance, and none of those can be provoked
reliably — or cheaply — against a live API.

It lives under `tests/` rather than in the package on purpose. A convincing
stand-in reachable from a deployment is one somebody eventually wires up, and the
result would be invented works written into a real catalogue with nothing to
distinguish them from found ones. What the package ships instead is an engine
that refuses.
"""

from __future__ import annotations

import threading
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal

from curation.discovery.browse import BrowseQuery, CollectionBrowseFailure, OfferedGroup
from curation.discovery.engine import (
    EngineFailure,
    EngineSpend,
    ProposedWork,
    WorkList,
    WorkListRequest,
)
from curation.discovery.images import FoundImage, ImageQuery, ImageSearchFailure
from curation.persistence.discovery_records import SpendCategory
from curation.persistence.records import AcquisitionMethod, RightsStatus, SourceClass

#: Titles that are actually distinct works by one artist, so a run built from
#: them exercises the dedup key doing nothing rather than the key collapsing a
#: list into one row and the test passing for the wrong reason.
_TITLES = (
    "The Persistence of Memory",
    "The Elephants",
    "Swans Reflecting Elephants",
    "The Temptation of St. Anthony",
    "Galatea of the Spheres",
)


def a_work(title: str, *, artist: str | None = "Salvador Dalí") -> ProposedWork:
    return ProposedWork(title=title, artist=artist, rationale=f"{title} is a central example of what was asked for.")


def works(count: int, *, artist: str | None = "Salvador Dalí") -> tuple[ProposedWork, ...]:
    """`count` distinct works, generated past the end of the named list.

    Numbered beyond the handful of real titles rather than repeating them: a
    twenty-six-work run testing the approval gate needs twenty-six *distinct*
    works, and recycling titles would have the dedup key silently reduce it to
    five.
    """
    named = [a_work(title, artist=artist) for title in _TITLES[:count]]
    extra = [a_work(f"Untitled Study No. {index}", artist=artist) for index in range(len(named), count)]
    return tuple(named + extra)


def spent(*, tokens_usd: str = "0.08", searches: int = 1, search_usd: str = "0.005") -> tuple[EngineSpend, ...]:
    """What a run of this size costs, in the two categories phase 1 can incur.

    Web search is its own category because it bills per call rather than per
    token, and its `units` is where the search count lives — the same record that
    prices the searches is the one the cap is read from, so the two cannot
    disagree.

    The token counts are the ones a **real run measured** — 3,453 in and 1,608
    out. They were 490,000 / 30,000, which was the shipped estimate basis before
    it was re-based against that measurement; a fake echoing a figure the code no
    longer holds reads as corroborating it.
    """
    return (
        EngineSpend(
            category=SpendCategory.DISCOVERY_TOKENS,
            cost_usd=Decimal(tokens_usd),
            model_id="fake/deterministic-v1",
            input_tokens=3_453,
            output_tokens=1_608,
        ),
        EngineSpend(category=SpendCategory.WEB_SEARCH, cost_usd=Decimal(search_usd) * searches, units=searches),
    )


def a_work_list(count: int = 3, *, searches: int = 1, artist: str | None = "Salvador Dalí") -> WorkList:
    return WorkList(works=works(count, artist=artist), spend=spent(searches=searches))


@dataclass
class FakeEngine:
    """Answers with whatever it was built to answer, and records what it was asked.

    `gate` is what makes a run observably in-flight: a test that needs to see a
    run *while* it is working — to cancel it, to watch a status call hold, to
    leave it for startup reconciliation to find — has to be able to stop phase 1
    in the middle, and an engine that always returns instantly cannot be caught
    there.
    """

    result: WorkList = field(default_factory=a_work_list)
    error: EngineFailure | None = None
    reason: str | None = None
    gate: threading.Event | None = None
    requests: list[WorkListRequest] = field(default_factory=list)

    @property
    def unavailable_reason(self) -> str | None:
        return self.reason

    def enumerate_works(self, request: WorkListRequest) -> WorkList:
        self.requests.append(request)
        if self.gate is not None:
            # Bounded so a test that forgets to release the gate fails as a test
            # rather than hanging the suite.
            assert self.gate.wait(timeout=20), "the fake engine was never released"
        if self.error is not None:
            raise self.error
        return self.result

    @property
    def searched(self) -> Sequence[int]:
        """The allowance every call was given, for asserting the cap travelled."""
        return [request.search_allowance for request in self.requests]


#: A museum's response to a work it holds, at a size that clears the floor on the
#: shipped 42" geometry. Dimensions are the master's, as the real API reports
#: them on `thumbnail` — see `.prawduct/artifacts/artic-api-findings.md`.
def an_image(
    title: str,
    *,
    artist: str | None = "Salvador Dalí",
    width: int = 6949,
    height: int = 8400,
    provider: str = "artic",
    rights: RightsStatus | None = RightsStatus.PUBLIC_DOMAIN,
    url: str | None = None,
) -> FoundImage:
    """One instance a provider offers. Its URL is derived unless a test names one.

    A test about *which* instance a work ended up with has to be able to say
    which URL it expects, and a derived one it cannot write down forces the
    assertion to go through some other field instead. The derivation stays the
    default because most tests do not care, and two calls with the same title
    and size standing for the same instance is what makes "the provider offered
    it again" expressible at all.
    """
    return FoundImage(
        url=url or f"https://api.artic.edu/api/v1/artworks/{abs(hash((title, width))) % 100000}",
        provider=provider,
        source_class=SourceClass.INSTITUTIONAL,
        acquisition_method=AcquisitionMethod.DEZOOMIFY,
        title=title,
        artist=artist,
        preview_url=f"https://www.artic.edu/iiif/2/{abs(hash(title)) % 100000}/full/843,/0/default.jpg",
        estimated_width=width,
        estimated_height=height,
        rights_status=rights,
    )


@dataclass
class FakeImageSearch:
    """A museum that holds whatever it was built to hold.

    Keyed by the title asked for rather than answering one fixed list, because
    the interesting phase-2 runs are the mixed ones — some works resolved, one
    below floor, one the collection does not hold — and a provider that answered
    identically for every work could not produce them.

    Anything not in `holdings` comes back as the real API does for a work it does
    not have: plausible results for *other* works, which is what the judgement
    above the seam has to reject.
    """

    holdings: dict[str, Sequence[FoundImage]] = field(default_factory=dict)
    unreachable: bool = False
    fails_for: set[str] = field(default_factory=set)
    asked: list[str] = field(default_factory=list)
    fetched: list[str] = field(default_factory=list)
    resolved: list[str] = field(default_factory=list)
    preview_bytes: bytes | None = b"\xff\xd8\xff\xe0 jpeg"

    @property
    def provider(self) -> str:
        return "artic"

    def tile_url(self, url: str) -> str:
        """The image service for an object, as the real client derives one.

        Mirrors the real shape rather than echoing the argument: the whole point
        of this seam is that the URL a source records and the URL the tiles come
        from are *different strings*, and a stand-in that returned its input
        would make a caller that skipped the resolution step pass.
        """
        self.resolved.append(url)
        if self.unreachable:
            raise ImageSearchFailure(f"could not reach the collection to resolve {url!r}")
        return f"https://www.artic.edu/iiif/2/{abs(hash(url)) % 100000}"

    def find_images(self, query: ImageQuery) -> Sequence[FoundImage]:
        self.asked.append(query.title)
        if self.unreachable or query.title in self.fails_for:
            raise ImageSearchFailure(f"could not reach the collection for {query.title!r}")
        if query.title in self.holdings:
            return self.holdings[query.title]
        # A near-match rather than an empty list, which is what the live API
        # really returns: the collection at a comfortable score, none of it the
        # work asked for.
        return (an_image("Ann-In Memory", artist="Joseph Cornell"),)

    def fetch_preview(self, url: str) -> bytes | None:
        self.fetched.append(url)
        return self.preview_bytes


def a_decodable_jpeg(width: int = 1200, height: int = 900) -> bytes:
    """Preview bytes a museum could really have served, and that Pillow can open.

    `FakeImageSearch.preview_bytes` defaults to a stub that is *not* decodable,
    which is right for tests about caching bytes and wrong for every test about
    showing them: a preview that will not decode produces no image block, so a
    review surface would look broken for a reason that is the fixture's.
    """
    from io import BytesIO

    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (width, height), (84, 66, 132)).save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


def a_museum_holding(
    *titles: str,
    sizes: dict[str, tuple[int, int]] | None = None,
    held_as: dict[str, str] | None = None,
) -> FakeImageSearch:
    """A provider holding one instance of each named work, with showable previews.

    Sizes default to a gallery-grade scan, because most tests want a work that
    clears the resolution floor and only a few care about the one that does not.
    Pass `sizes` to make a particular work small.

    **`held_as` separates the title asked for from the title the collection files
    the work under**, which the query-keyed shape alone cannot express. Real
    collections do this constantly — a work catalogued under its full descriptive
    title, or in another language — and the identity comparison above the seam
    exists precisely to judge the difference. Without this, every fixture agreed
    with its query by construction and no test could reach the disagreement.
    """
    measured = sizes or {}
    spelled = held_as or {}
    holdings = {}
    for title in titles:
        width, height = measured.get(title, (6000, 4500))
        slug = title.lower().replace(" ", "-")
        holdings[title] = (an_image(spelled.get(title, title), url=f"https://artic.edu/{slug}", width=width, height=height),)
    found = FakeImageSearch(holdings=holdings)
    found.preview_bytes = a_decodable_jpeg()
    return found


@dataclass
class FakeCollectionBrowse:
    """A collection that holds whatever it was built to hold, keyed by artist.

    Keyed by the artist asked about, because the interesting supplement cases are
    the uneven ones — one artist with fifty works, one with two, one the
    collection has never heard of — and a browse that answered identically for
    every facet could not produce the spread the round-robin exists to make.

    `matched` is tracked apart from the works returned so a test can express "the
    collection holds four hundred and you are seeing three", which is the figure
    every offered work's rationale has to quote.
    """

    holdings: dict[str, Sequence[FoundImage]] = field(default_factory=dict)
    matched: dict[str, int] = field(default_factory=dict)
    unreachable: bool = False
    asked: list[list[str]] = field(default_factory=list)

    @property
    def provider(self) -> str:
        return "artic"

    def browse(self, queries: Sequence[BrowseQuery], *, per_query: int) -> Sequence[OfferedGroup]:
        self.asked.append([query.artist for query in queries])
        if self.unreachable:
            raise CollectionBrowseFailure("could not reach the collection to browse it")
        groups = []
        for query in queries:
            works = tuple(self.holdings.get(query.artist, ()))[:per_query]
            groups.append(
                OfferedGroup(
                    query=query,
                    matched=self.matched.get(query.artist, len(self.holdings.get(query.artist, ()))),
                    works=works,
                )
            )
        return tuple(groups)


def a_collection_holding(**by_artist: Sequence[str]) -> FakeCollectionBrowse:
    """A collection holding the named works for each artist, ready to be offered.

    Sized to clear the display floor, because a supplement's whole job is to put
    something showable in front of a curator and a fixture that quietly fell
    below the floor would test the exclusion rather than the offer.
    """
    holdings = {
        artist: tuple(
            an_image(title, artist=artist, url=f"https://artic.edu/{title.lower().replace(' ', '-')}", width=6000, height=4500)
            for title in titles
        )
        for artist, titles in by_artist.items()
    }
    return FakeCollectionBrowse(holdings=holdings)
