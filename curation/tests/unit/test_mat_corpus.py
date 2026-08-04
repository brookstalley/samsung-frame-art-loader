"""The 41 hand-accepted mats, and what they establish as the bar.

**The corpus is `all.json` itself, and there is no extracted fixture beside it.**
Chunk 06 deferred copying these colours into `tests/fixtures/mat_corpus.json`;
this is the decision not to. `all.json` is tracked, is already the canonical
record `nonfunctional-requirements.md` names, and is read here through the
product's own `read_index` rather than a second parser. A copy would be a second
place the 41 colours live, free to drift from the one the seed actually loads —
and the drift would be silent, because both files would keep parsing.

What this file can and cannot do is worth stating plainly. It **cannot** judge
whether a new mat is as good as the old one: that is subjective, it is the
operator's look, and `tools/mat_corpus.py` produces the sheet they look at. What
it **can** do is hold the one property the corpus states unambiguously — every
one of these mats is dark — and check that the engine's own mechanical producer
respects it. That property is not decorative: probing candidate models turned up
two that proposed a near-white mat over a Rothko and a Mondrian, which is the
single failure that glares on an emissive panel.
"""

import json
from pathlib import Path

import pytest
from PIL import Image

from curation.acquisition.color import hex_distance, parse_hex, rgb_to_lab
from curation.acquisition.compose import compose
from curation.acquisition.mat import MatEngine, dominant_color
from curation.persistence.records import MatMethod
from curation.seed.legacy import read_index
from curation.services.display_fit import ArtworkBox

#: The 2024 index, two levels up from this file: `curation/tests/unit` → the
#: repository root. Located by walking rather than by a fixed number of parents,
#: so moving this file does not silently start reading nothing.
CORPUS_PATH = next(
    (parent / "all.json" for parent in Path(__file__).resolve().parents if (parent / "all.json").is_file()),
    None,
)

#: The lightness no mat in the corpus exceeds. Measured, not chosen: the 41 run
#: from L* 6.7 to 45.2 with a median of 20.7, so 50 — mid-grey — sits above every
#: one of them with room to spare, and is the round number that says "darker than
#: the middle of the range a display can show".
CORPUS_MAX_LIGHTNESS = 50.0


@pytest.fixture(scope="module")
def corpus():
    """The 41 records, read through the loader the seed itself uses."""
    if CORPUS_PATH is None:
        pytest.fail(
            "all.json is not in this checkout. It is the mat regression corpus and the only place the 41 "
            "hand-accepted colours exist, so it is tracked deliberately — see nonfunctional-requirements.md "
            "§ Output Quality, which forbids repo-hygiene work from deleting it."
        )
    return read_index(CORPUS_PATH)


def test_the_corpus_is_the_forty_one_works_the_requirement_names(corpus):
    """A count, because the requirement names one: 'the 41 existing artworks with
    their hand-tuned mats are the regression corpus'. A corpus that quietly
    shrank would still pass every property below."""
    assert len(corpus) == 41


def test_every_corpus_colour_is_one_the_engine_can_read(corpus):
    """The colour module against the real data it will meet, rather than against
    examples chosen to suit it."""
    for record in corpus:
        assert parse_hex(record.mat_hex)


def test_every_corpus_mat_is_darker_than_mid_grey(corpus):
    """**The bar, stated as the corpus states it.** 'Avoid having the mat seem
    brighter than the artwork since this will be on an LCD display. If in doubt,
    go darker' produced 41 colours of which the lightest is L* 45.2. A new engine
    proposing a pale mat is not exercising taste, it is failing the one rule the
    whole corpus agrees on."""
    too_light = {
        record.mat_hex: round(rgb_to_lab(parse_hex(record.mat_hex)).l, 1)
        for record in corpus
        if rgb_to_lab(parse_hex(record.mat_hex)).l > CORPUS_MAX_LIGHTNESS
    }
    assert too_light == {}


def test_the_corpus_is_low_chroma_but_not_uniformly_grey(corpus):
    """Both halves matter, and a single-sided assertion would miss one of them.
    An engine that answered grey every time would satisfy 'low chroma' and lose
    what the prompt asks for — a colour drawn from the work. An engine answering
    saturated colours would fail the other way."""
    chromas = [
        (rgb_to_lab(parse_hex(record.mat_hex)).a ** 2 + rgb_to_lab(parse_hex(record.mat_hex)).b ** 2) ** 0.5 for record in corpus
    ]
    greys = [chroma for chroma in chromas if chroma < 1.0]

    assert max(chromas) < 40
    assert 5 <= len(greys) <= len(chromas) - 5


def test_the_corpus_holds_genuinely_distinct_choices(corpus):
    """Guards against the corpus degenerating into a handful of repeated values,
    which would make any comparison against it meaningless while every other
    assertion here still held."""
    assert len({record.mat_hex for record in corpus}) >= 30


def test_every_corpus_colour_composes_onto_a_canvas(tmp_path, corpus):
    """The compositor against all 41 rather than one invented colour: these are
    what a seeded deployment actually renders with on its first pass."""
    source = tmp_path / "work.jpg"
    Image.new("RGB", (600, 400), (200, 180, 160)).save(source, format="JPEG")
    box = ArtworkBox(width=3316, height=1597, pixels_per_inch=104.87, floor_inches=12.0)

    for index, record in enumerate(corpus):
        result = compose(
            source,
            destination=tmp_path / f"ready/{index}.jpg",
            mat_hex=record.mat_hex,
            panel_width=3840,
            panel_height=2160,
            box=box,
        )
        assert result.path.is_file()


class TestTheMechanicalProducerAgainstTheBar:
    """The half of the engine that can be checked without a model or a network.

    The vision half is checked against the same bar in `tests/live`, where a real
    call can be made, and looked at by the operator through
    `tools/mat_corpus.py`. Neither substitutes for this: the fallback runs on
    every keyless deployment and on every model failure, so it is the producer
    most likely to be the one actually painting a wall.
    """

    @pytest.mark.parametrize(
        ("colour", "label"),
        [
            ((240, 235, 220), "a pale wash, the case that most tempts a bright mat"),
            ((255, 255, 255), "pure white"),
            ((30, 60, 120), "a deep blue"),
            ((200, 40, 40), "a saturated red"),
            ((128, 128, 128), "mid grey"),
            ((10, 10, 10), "near black"),
        ],
    )
    def test_the_fallback_never_proposes_a_mat_lighter_than_the_work(self, tmp_path, colour, label):
        """**Including from a white artwork**, which is the case that decides it:
        two thirds of white is still bright, and an engine that returned it would
        put a glaring mat around the palest works in a collection."""
        source = tmp_path / "work.jpg"
        Image.new("RGB", (400, 300), colour).save(source, format="JPEG", quality=95)

        choice = MatEngine(None, image_max_edge=256).choose(source)

        assert choice.method is MatMethod.DOMINANT_COLOR_FALLBACK
        assert rgb_to_lab(parse_hex(choice.hex_rgb)).l < rgb_to_lab(dominant_color(source)).l

    def test_the_fallback_stays_within_the_corpus_bar_for_most_works(self, tmp_path):
        """Stated as "most" rather than "every", honestly: darkening by a third
        cannot bring a white artwork under the bar, and the corpus contains no
        work that pale. What it can show is that the producer lands in the
        corpus's own region for ordinary art rather than beside it."""
        under_the_bar = 0
        palettes = [(30, 60, 120), (200, 40, 40), (90, 70, 50), (128, 128, 128), (60, 90, 60), (10, 10, 10)]
        for index, colour in enumerate(palettes):
            source = tmp_path / f"work-{index}.jpg"
            Image.new("RGB", (400, 300), colour).save(source, format="JPEG", quality=95)
            choice = MatEngine(None, image_max_edge=256).choose(source)
            if rgb_to_lab(parse_hex(choice.hex_rgb)).l <= CORPUS_MAX_LIGHTNESS:
                under_the_bar += 1

        assert under_the_bar == len(palettes)


def test_the_distance_metric_discriminates_across_the_real_corpus(corpus):
    """A metric that reported everything as near-identical would make the
    operator's ΔE column useless while passing every unit test written against
    invented pairs. The corpus's own spread is the check."""
    hexes = [record.mat_hex for record in corpus]
    distances = [hex_distance(one, two) for one, two in zip(hexes, hexes[1:], strict=False)]

    assert max(distances) > 15
    assert min(distances) >= 0


def test_the_corpus_file_is_the_one_the_seed_reads(corpus):
    """Ties this file's premise to the code rather than to a comment. If the seed
    stopped reading `all.json`, or read a differently-shaped one, this corpus
    would be describing a file nothing loads."""
    document = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))

    assert {record.mat_hex for record in corpus} == {entry["mat_hexrgb"].lower() for entry in document["art"]}
