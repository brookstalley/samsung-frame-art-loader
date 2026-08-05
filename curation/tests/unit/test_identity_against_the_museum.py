"""The identity comparison, measured against records the museum really returned.

`phase_one_proposals.json` is model output only: it can measure phase 1 against
phase 1, and cannot reach this comparison at all. This corpus is the other side of
the seam — real pairs of what a model proposed and what the Art Institute answered
with, each labelled by reading it as a cataloguer would.

**Why a corpus rather than more unit cases.** The comparison's whole job is to
survive the near-misses a live collection actually produces, and those are
stranger than anything written from imagination: a title quoted and deliberately
misspelled by a different artist, a sitter photographed two centuries after the
painting, an artist's name filed family-name-first. Every pair here happened.

Deterministic and free: the museum records are recorded, so nothing is asked over
the network.
"""

import json
from pathlib import Path

import pytest

from curation.discovery.images import FoundImage, ImageQuery
from curation.discovery.phase_two import PhaseTwoEngine
from curation.persistence.records import AcquisitionMethod, RightsStatus, SourceClass
from curation.services.display_fit import ArtworkBox

CORPUS = Path(__file__).resolve().parents[1] / "fixtures" / "identity_pairs.json"

#: The same 42" geometry the live floor test pins, so a pair's verdict here and
#: its fate in a real run are the same judgement.
BOX = ArtworkBox(width=3316, height=1597, pixels_per_inch=104.9, floor_inches=12.0)


def pairs():
    return json.loads(CORPUS.read_text())["pairs"]


class OneRecord:
    """A provider holding exactly the record the museum really returned."""

    def __init__(self, title: str, artist: str) -> None:
        self._found = FoundImage(
            url="https://api.artic.edu/api/v1/artworks/1",
            provider="artic",
            source_class=SourceClass.INSTITUTIONAL,
            acquisition_method=AcquisitionMethod.DEZOOMIFY,
            title=title,
            artist=artist,
            preview_url="https://www.artic.edu/iiif/2/x/full/843,/0/default.jpg",
            # Comfortably above the floor: this corpus is about identity, and a
            # pair failing on size would report the wrong reason.
            estimated_width=6000,
            estimated_height=4500,
            rights_status=RightsStatus.PUBLIC_DOMAIN,
        )

    @property
    def provider(self) -> str:
        return "artic"

    def find_images(self, query: ImageQuery):
        return (self._found,)

    def fetch_preview(self, url: str):
        return b""

    def tile_url(self, url: str) -> str:
        return url


def resolves(pair) -> bool:
    """Whether the pipeline would accept this museum record as the work asked for."""
    engine = PhaseTwoEngine(OneRecord(pair["found_title"], pair["found_artist"]), box=BOX)
    resolution = engine.resolve(ImageQuery(title=pair["asked_title"], artist=pair["asked_artist"]))
    return bool(resolution.instances)


#: Pairs this comparison is known to get wrong, with the reason it is not fixed
#: here. `strict` on purpose: if a change ever makes one of these pass, this fails
#: and the defect is closed deliberately rather than drifting shut unnoticed.
KNOWN_WRONG = {
    "p005": (
        "The artist comparison is order-sensitive, so a name the museum files "
        "family-name-first is refused. The fix is to make artist identity "
        "order-insensitive, and that cannot be done here: the same function derives "
        "`work_dedup_key`, so sorting its tokens changes the stored suppression key "
        "for most multi-token names — 'vincent van gogh' becomes 'gogh van vincent' "
        "— and every work a curator has already rejected would become proposable "
        "again. That needs a migration and a ruling on whether two painters whose "
        "names are anagrams may merge. Tracked separately."
    )
}


@pytest.mark.parametrize("pair", [p for p in pairs() if p["same_work"]], ids=lambda p: p["id"])
def test_a_record_that_is_the_work_is_accepted(pair, request):
    """A true match must survive, or the pipeline resolves nothing at all.

    These are the pairs behind the measured resolution rate. Losing one here is
    losing a work off a real curator's review grid.
    """
    if pair["id"] in KNOWN_WRONG:
        request.applymarker(pytest.mark.xfail(strict=True, reason=KNOWN_WRONG[pair["id"]]))
    assert resolves(pair), f"refused a genuine match: {pair['note']}"


@pytest.mark.parametrize("pair", [p for p in pairs() if not p["same_work"]], ids=lambda p: p["id"])
def test_a_record_that_is_not_the_work_is_refused(pair):
    """Every one of these arrived at a comfortable relevance score.

    A pipeline that ranked by the museum's own number would attach each of them
    to the request and report success — the confident near-match the data model
    forbids, arriving through the most obvious implementation.
    """
    assert not resolves(pair), f"accepted a near-match as the work: {pair['note']}"


def test_the_corpus_holds_both_answers():
    """A corpus of one label cannot falsify the comparison in both directions.

    All-negative and it cannot notice a comparison that refuses everything;
    all-positive and it cannot notice one that accepts everything. Asserted
    rather than left to whoever next adds a pair.
    """
    labels = {pair["same_work"] for pair in pairs()}
    assert labels == {True, False}
