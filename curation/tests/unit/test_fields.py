"""Constraint 10: a description carries only the markup the label renderer can take.

The label renderer hands description text to Pango. Pango accepts a small tag
vocabulary and refuses to parse markup that is unbalanced or that contains a bare
`&` — and it refuses at render time, on a panel in another room, where nobody is
watching. So the normalising happens once on the way in rather than in every
renderer that reads the text back out, which is what the 2024 code did and is why
each renderer had to remember to.
"""

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from curation.services.errors import ServiceError
from curation.services.fields import description_markup, relative_path


def test_the_two_tags_the_renderer_understands_survive():
    assert description_markup("A <i>very</i> <b>fine</b> diner.") == "A <i>very</i> <b>fine</b> diner."


def test_the_tags_sources_actually_send_are_folded_into_them():
    """Museums return HTML emphasis; Pango speaks the shorter pair."""
    assert description_markup("<em>Nighthawks</em> and <strong>Chop Suey</strong>") == "<i>Nighthawks</i> and <b>Chop Suey</b>"


def test_paragraphs_become_blank_lines_rather_than_vanishing():
    """Dropping the tag outright would run two paragraphs into one sentence."""
    assert description_markup("<p>First para.</p><p>Second para.</p>") == "First para.\n\nSecond para."


def test_a_line_break_separates_rather_than_disappearing():
    assert description_markup("Line one<br>Line two") == "Line one\n\nLine two"


def test_every_other_tag_is_dropped_and_its_text_kept():
    assert description_markup('An <a href="https://x.example">artist</a> and a <span>place</span>.') == "An artist and a place."


def test_the_contents_of_a_code_element_are_dropped_with_it():
    """Unknown tags are unwrapped and their text kept — which is wrong for these.

    A scraped page carrying a script or style block would otherwise put its
    source on the physical label as visible text, and nothing would report it.
    """
    assert description_markup("A diner.<script>alert(1)</script>") == "A diner."
    assert description_markup("<style>.x { color: red }</style>A diner.") == "A diner."


def test_an_unclosed_code_element_silences_the_rest_rather_than_leaking_it():
    assert description_markup("A diner.<script>alert(1)") == "A diner."


def test_an_ampersand_is_escaped_so_pango_does_not_read_it_as_an_entity():
    assert description_markup("Oil & graphite") == "Oil &amp; graphite"


def test_an_entity_the_source_already_escaped_survives_as_one():
    assert description_markup("Oil &amp; graphite") == "Oil &amp; graphite"


def test_a_stray_angle_bracket_is_escaped_rather_than_read_as_a_tag():
    assert description_markup("Width < height") == "Width &lt; height"


def test_an_unclosed_tag_is_closed_rather_than_passed_on():
    """Pango refuses unbalanced markup, and it refuses where nobody is watching."""
    assert description_markup("A <i>very fine diner.") == "A <i>very fine diner.</i>"


def test_a_closing_tag_with_no_opener_is_dropped():
    assert description_markup("A very fine</i> diner.") == "A very fine diner."


def test_crossed_tags_come_out_nested():
    """`<i>a<b>b</i>c</b>` is what a scraper produces and what Pango rejects."""
    assert description_markup("<i>a<b>b</i>c") == "<i>a<b>b</b></i>c"


def test_runs_of_blank_lines_are_collapsed():
    assert description_markup("<p><p>First.</p></p><p>Second.</p>") == "First.\n\nSecond."


def test_a_description_that_normalises_to_nothing_is_recorded_as_absent():
    """An empty string and "no description" would otherwise read differently for no reason."""
    assert description_markup("<p></p>") is None
    assert description_markup("   ") is None


def test_no_description_stays_no_description():
    assert description_markup(None) is None


# -- constraint 6, at the level the rule itself lives --------------------------


def test_a_relative_path_passes_through_normalised():
    assert relative_path("./originals//w1.tif", field="path") == "originals/w1.tif"


@pytest.mark.parametrize("value", ["/mnt/photos/w1.tif", "/w1.tif"])
def test_an_absolute_path_is_refused(value):
    with pytest.raises(ServiceError, match="must be relative to ART_ROOT"):
        relative_path(value, field="path")


@pytest.mark.parametrize("value", ["../w1.tif", "originals/../../w1.tif"])
def test_a_path_that_climbs_out_of_the_art_root_is_refused(value):
    """Leaving ART_ROOT by climbing breaks the same promise as starting outside it."""
    with pytest.raises(ServiceError, match="climbs out of it"):
        relative_path(value, field="path")


def test_an_empty_path_is_refused_by_the_name_of_the_field():
    with pytest.raises(ServiceError, match="preview_path cannot be empty"):
        relative_path("  ", field="preview_path")


# -- constraint 10 against the population that actually reaches it --------------


def _parses_as_xml(markup: str) -> None:
    """Pango parses description text as XML, so this is its bar, applied locally.

    The assertions above check individual rewrites; this checks the property that
    makes them worth having. A description that survives every rule and still
    fails to parse is a rendering failure on a panel nobody is watching, which is
    the outcome the constraint exists to prevent.
    """
    ET.fromstring(f"<root>{markup}</root>")


def _corpus_descriptions() -> list[str]:
    """Every description the seeded catalogue was built from.

    The 41 works in `all.json` are the real input to this function in this
    deployment — museum prose with paragraph markup, entities and the occasional
    stray tag — so they are a population worth asserting against rather than only
    the cases someone thought to write down.
    """
    payload = json.loads(Path(__file__).resolve().parents[3].joinpath("all.json").read_text())
    return [entry["metadata"]["description"] for entry in payload["art"] if entry.get("metadata", {}).get("description")]


def test_the_corpus_carries_markup_this_function_has_to_remove():
    """Guards the test below from passing because it found nothing to check."""
    raw = _corpus_descriptions()
    assert raw, "the corpus carries no descriptions"
    assert any("<p>" in text for text in raw)


def test_every_corpus_description_normalises_to_the_constraint():
    for text in _corpus_descriptions():
        normalised = description_markup(text)
        assert normalised is not None
        assert set(re.findall(r"</?([a-zA-Z][a-zA-Z0-9]*)", normalised)) <= {"i", "b"}
        _parses_as_xml(normalised)
