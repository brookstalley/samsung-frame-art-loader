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
import logging
from itertools import permutations
from pathlib import Path

import pytest
from PIL import Image

from curation.acquisition.color import format_hex, hex_distance, parse_hex, rgb_to_lab, scale_lightness
from curation.acquisition.compose import compose

# `_DERIVED_LIGHTNESS_CEILING` is private to the engine and is imported anyway,
# deliberately: the whole point of the test below is that the clamp's number and
# the corpus's own lightest mat are not two figures free to drift apart. Reaching
# for a public copy would create the second home the check exists to prevent.
# `CORPUS_MAX_LIGHTNESS` is public and is imported for the opposite reason — the
# requirement's bar belongs to the product, and a copy declared here would be a bar
# this file guards and the operator's tool does not.
from curation.acquisition.mat import (
    _DERIVED_LIGHTNESS_CEILING,
    _FALLBACK_LIGHTNESS,
    CORPUS_MAX_LIGHTNESS,
    MatEngine,
    _most_covered_colour,
    _under_the_corpus_bar,
    dominant_color,
)
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

    def test_the_fallback_stays_within_the_corpus_bar_for_every_work(self, tmp_path):
        """**"Every", and the two pale entries are why the word changed.** This
        read "for most works" and fed six colours of which the lightest was mid
        grey, on the reasoning that darkening by a third cannot bring a white
        artwork under the bar. That was true of the arithmetic and false as a
        description of the requirement, and the gap is what let the producer put a
        mat over the bar on 7 of the operator's 40 real works while this stayed
        green. The clamp is what makes "every" sayable, so the palest cases — the
        ones darkening alone cannot rescue — are now the ones under test.

        **Asserted against the ceiling the engine enforces, not the requirement's
        round bar.** Those are 45.2 and 50, and the 4.8 between them is enough room
        for a clamp that overshoots to pass while looking correct — which is how
        the gamut overshoot survived its first test."""
        palettes = [
            (255, 255, 255),
            (240, 235, 220),
            (30, 60, 120),
            (200, 40, 40),
            (90, 70, 50),
            (128, 128, 128),
            (60, 90, 60),
            (10, 10, 10),
        ]
        over_the_bar = {}
        for index, colour in enumerate(palettes):
            source = tmp_path / f"work-{index}.jpg"
            Image.new("RGB", (400, 300), colour).save(source, format="JPEG", quality=95)
            choice = MatEngine(None, image_max_edge=256).choose(source)
            lightness = rgb_to_lab(parse_hex(choice.hex_rgb)).l
            if lightness > _DERIVED_LIGHTNESS_CEILING:
                over_the_bar[colour] = round(lightness, 1)

        assert over_the_bar == {}

    def test_the_clamp_is_the_corpus_ceiling_rather_than_a_number_of_its_own(self, corpus):
        """**The one place the corpus's ceiling is decided is the corpus.** The
        engine clamps derived lightness to a constant, and a constant typed into a
        module is free to drift from the file it claims to describe — silently,
        because both keep parsing. Deriving it here means a corpus that gains a
        lighter mat fails this test instead of leaving the engine enforcing a bar
        the corpus no longer sets."""
        lightest = max(rgb_to_lab(parse_hex(record.mat_hex)).l for record in corpus)

        assert round(lightest, 1) == _DERIVED_LIGHTNESS_CEILING

    def test_the_clamp_darkens_a_pale_work_without_turning_it_grey(self, tmp_path):
        """A ceiling on lightness only. Clamping in RGB, or falling back to a
        neutral, would answer a warm ochre work with a grey mat — and the corpus's
        own instruction is to prefer a low-chroma colour *drawn from the artwork*
        over a neutral. The chroma assertion is what tells the two apart; a
        lightness-only assertion passes for both."""
        source = tmp_path / "ochre.jpg"
        Image.new("RGB", (400, 300), (235, 200, 140)).save(source, format="JPEG", quality=95)

        chosen = rgb_to_lab(parse_hex(MatEngine(None, image_max_edge=256).choose(source).hex_rgb))

        assert chosen.l <= _DERIVED_LIGHTNESS_CEILING
        assert (chosen.a**2 + chosen.b**2) ** 0.5 > 5.0

    def test_a_saturated_work_gets_a_darker_mat_rather_than_a_grey_one(self, tmp_path):
        """**The case where asking for the ceiling does not get it.** sRGB cannot
        show a vivid yellow at L\\* 45.2, so the naive clamp — hold lightness, keep
        a\\* and b\\* — comes back *lighter* than it asked for, over the very bar it
        was enforcing. Two ways out, and the corpus picks between them: hold the
        lightness and desaturate, which answers a vivid work with a grey, or go
        darker and keep the colour, which is what "when in doubt, go darker" says.
        Asserting the chroma is what tells the two apart — a lightness-only
        assertion passes for the grey."""
        source = tmp_path / "vivid.jpg"
        Image.new("RGB", (400, 300), (0, 255, 0)).save(source, format="JPEG", quality=95)

        chosen = rgb_to_lab(parse_hex(MatEngine(None, image_max_edge=256).choose(source).hex_rgb))

        assert chosen.l <= _DERIVED_LIGHTNESS_CEILING
        assert (chosen.a**2 + chosen.b**2) ** 0.5 > 30.0

    def test_the_ceiling_holds_for_every_colour_a_display_can_show(self):
        """**The invariant, swept rather than asserted in prose.** Three records
        claim no derived colour exceeds the ceiling; a claim about every colour is
        only worth what reproduces it, and this project's own rule is that a
        premise be checkable at the moment something is built on it. The grid is
        coarse enough to run in a suite and fine enough to have caught the defect
        it exists for: the naive clamp overshoots most on saturated hues, which a
        lattice this size hits repeatedly."""
        over = {
            colour: round(rgb_to_lab(_under_the_corpus_bar(colour)).l, 2)
            for colour in (
                (red, green, blue) for red in range(0, 256, 15) for green in range(0, 256, 15) for blue in range(0, 256, 15)
            )
            if rgb_to_lab(_under_the_corpus_bar(colour)).l > _DERIVED_LIGHTNESS_CEILING
        }

        assert over == {}

    def test_a_clamped_mat_says_so_where_someone_can_read_it(self, tmp_path, caplog):
        """**The ceiling firing is otherwise unrecoverable after the fact.**
        `method` records that a colour was derived rather than chosen, but not that
        it was then held back, so "why is this mat not the colour of the picture?"
        has nowhere to look — and the operator has been asked to judge exactly the
        works this fires on. Both figures are asserted because a line naming the
        wrong one is worse than no line: it would send a reader looking for a bug
        in the derivation instead of at the ceiling."""
        source = tmp_path / "vivid.jpg"
        Image.new("RGB", (400, 300), (0, 255, 0)).save(source, format="JPEG", quality=95)

        with caplog.at_level(logging.INFO, logger="curation.acquisition.mat"):
            choice = MatEngine(None, image_max_edge=256).choose(source)

        assert "held at the corpus ceiling" in caplog.text
        assert f"capped to L* {rgb_to_lab(parse_hex(choice.hex_rgb)).l:.1f}" in caplog.text
        assert f"derived L* {rgb_to_lab(scale_lightness(dominant_color(source), _FALLBACK_LIGHTNESS)).l:.1f}" in caplog.text

    def test_a_mat_the_ceiling_did_not_touch_says_nothing(self, tmp_path, caplog):
        """The half that defends the guard rather than the line. Without it the
        block can be made unconditional and every assertion above still passes —
        and then every mechanically derived mat in the catalogue reports having
        been capped, which is a log that has stopped meaning anything."""
        source = tmp_path / "deep-blue.jpg"
        Image.new("RGB", (400, 300), (30, 60, 120)).save(source, format="JPEG", quality=95)

        with caplog.at_level(logging.INFO, logger="curation.acquisition.mat"):
            MatEngine(None, image_max_edge=256).choose(source)

        assert "held at the corpus ceiling" not in caplog.text

    def test_a_work_already_under_the_bar_is_left_exactly_where_it_was(self, tmp_path):
        """The clamp is a ceiling, not a second darkening pass applied to
        everything. A version that scaled every derived colour would move the
        mats that were never the problem — and it would pass every assertion above
        while quietly changing the answer for most of the catalogue."""
        source = tmp_path / "deep-blue.jpg"
        Image.new("RGB", (400, 300), (30, 60, 120)).save(source, format="JPEG", quality=95)

        derived = dominant_color(source)
        expected = rgb_to_lab(derived).l * _FALLBACK_LIGHTNESS

        chosen = rgb_to_lab(parse_hex(MatEngine(None, image_max_edge=256).choose(source).hex_rgb)).l

        assert chosen == pytest.approx(expected, abs=1.0)


class TestTheDominanceVoteCountsAColourOnce:
    """What the quantiser partitions and what a viewer calls one colour differ.

    Median cut splits along the widest channel, so a colour spread over a gradient
    lands in two clusters and then loses the largest-cluster vote to a smaller
    rival that stayed whole. Measured on the operator's masters, a benign
    re-encode was enough to move a work's derived colour from a near-black navy to
    a near-white — the split moves, and the winner changes with it.

    **The bands are sized to fit under the engine's own examination edge**, so
    nothing is resampled on the way in. A resize blends adjacent bands into
    intermediate colours, and those blends are themselves clustered — which makes
    the fixture's arithmetic depend on the resampling filter rather than on the
    behaviour under test.
    """

    #: Two shades of one orange, far enough apart for median cut to separate them
    #: and close enough that no one would call them different colours.
    ORANGE = ((232, 120, 24), (214, 108, 20))
    #: The undivided rival: smaller than the orange in total, larger than either
    #: half of it. This is the whole of the failure, expressed as three numbers.
    TEAL = (26, 108, 116)

    def _banded(self, path, bands):
        """An image of flat horizontal bands, written pixel-exact."""
        width, height = 240, 200
        image = Image.new("RGB", (width, height))
        top = 0
        for fraction, colour in bands:
            for row in range(top, min(top + int(height * fraction), height)):
                for column in range(width):
                    image.putpixel((column, row), colour)
            top += int(height * fraction)
        image.save(path, format="PNG")
        return path

    def test_a_colour_split_across_clusters_still_wins_the_vote(self, tmp_path):
        """The orange covers 44% in two shades; the teal covers 30% in one. Taking
        the largest cluster answers teal, which is the bug — no viewer looking at
        this image would say its dominant colour is the teal."""
        source = self._banded(
            tmp_path / "split.png",
            [(0.22, self.ORANGE[0]), (0.22, self.ORANGE[1]), (0.30, self.TEAL), (0.13, (140, 140, 140)), (0.13, (24, 24, 28))],
        )

        assert dominant_color(source) in self.ORANGE

    def test_a_merged_group_answers_with_the_shade_that_covers_most(self, tmp_path):
        """**Which shade speaks for the group is a real choice, so it is asserted
        on a fixture where the shades differ.** The split above deliberately holds
        two equal halves, which cannot tell "the group's largest member" apart from
        "its smallest" — both are the same orange. Here one shade covers 30% and
        the other 14%, so answering with the minor shade is a visible wrong answer:
        the mat would be a colour the picture barely contains."""
        source = self._banded(
            tmp_path / "lopsided.png",
            [(0.30, self.ORANGE[0]), (0.14, self.ORANGE[1]), (0.28, self.TEAL), (0.14, (140, 140, 140)), (0.14, (24, 24, 28))],
        )

        assert dominant_color(source) == self.ORANGE[0]

    def test_a_gradient_of_three_shades_is_one_colour(self, tmp_path):
        """**Single-link grouping, which two shades cannot distinguish.** With a
        pair, "close to any member" and "close to every member" are the same
        sentence; with a chain they are not. A\\B and B\\C sit under the threshold
        while A\\C sits over it, so complete-link grouping splits this gradient back
        into two and hands the vote to the teal. A gradient across three of the five
        clusters is not exotic — it is what a painted sky is, and it is the case the
        merge exists for."""
        chain = [(248, 132, 30), (214, 108, 20), (180, 86, 12)]
        far = hex_distance(format_hex(chain[0]), format_hex(chain[2]))
        near = max(
            hex_distance(format_hex(chain[0]), format_hex(chain[1])), hex_distance(format_hex(chain[1]), format_hex(chain[2]))
        )
        assert near < 10.0 < far, "the fixture must chain, or it is testing the two-shade case again"

        source = self._banded(
            tmp_path / "gradient.png",
            [(0.17, chain[0]), (0.17, chain[1]), (0.17, chain[2]), (0.35, self.TEAL), (0.14, (24, 24, 28))],
        )

        assert dominant_color(source) in chain

    def test_the_answer_does_not_depend_on_the_order_the_clusters_arrive_in(self):
        """The tie the winner's key exists to break, put the only way it can be.

        Two groups of exactly equal area is reachable, and with nothing but the area
        in the key the winner is whichever the iteration reached first — stable for
        one file and decided by the quantiser's reporting order, which is not a
        property anybody chose. Asserting it through `dominant_color` cannot see
        this: one image yields one cluster order, so every call agrees no matter how
        the tie is resolved. Permuting the clusters is the whole test."""
        clusters = [(100, (232, 120, 24)), (100, (26, 108, 116)), (60, (24, 24, 28))]

        answers = {_most_covered_colour(list(permuted)) for permuted in permutations(clusters)}

        assert len(answers) == 1

    def test_genuinely_different_colours_still_compete(self, tmp_path):
        """The other half of the threshold, and the one that would go unnoticed:
        a merge wide enough to group everything would answer with whatever colour
        the chain happened to end on, and would pass the test above every time.
        Here the teal really is the largest single colour and must win."""
        source = self._banded(
            tmp_path / "teal-really-wins.png",
            [(0.50, self.TEAL), (0.20, self.ORANGE[0]), (0.16, (140, 140, 140)), (0.14, (24, 24, 28))],
        )

        assert dominant_color(source) == self.TEAL

    def test_the_derived_colour_survives_a_benign_re_encode(self, tmp_path):
        """**The property the operator's measurement found broken.** Nothing about
        a picture changes when it is saved again at a slightly different quality,
        so nothing about its dominant colour may either. Asserted on the pair that
        breaks it: the split orange, where the two shades' counts are close enough
        that a re-encode can reorder them."""
        source = self._banded(
            tmp_path / "before.png",
            [(0.22, self.ORANGE[0]), (0.22, self.ORANGE[1]), (0.30, self.TEAL), (0.13, (140, 140, 140)), (0.13, (24, 24, 28))],
        )
        re_encoded = tmp_path / "after.jpg"
        with Image.open(source) as image:
            image.convert("RGB").save(re_encoded, format="JPEG", quality=92)

        assert hex_distance(format_hex(dominant_color(source)), format_hex(dominant_color(re_encoded))) < 10.0


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
