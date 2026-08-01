"""Reading the 2024 index.

Every `artist_details` case below is a shape that actually occurs in the tracked
index, quoted verbatim. That is the point of the file: the parser exists to
survive one particular corpus, so a synthetic case would prove it survives a
corpus nobody has.
"""

import json

import pytest

from curation.persistence.records import AcquisitionMethod, SourceClass
from curation.seed.legacy import (
    LegacyIndexError,
    ParsedArtist,
    artist_name,
    parse_artist,
    read_index,
    ready_path_for,
)


def parse(artist, details=None, *, nationality=None, born=None, died=None):
    return parse_artist(artist=artist, details=details, nationality=nationality, born=born, died=died)


class TestArtistDetails:
    """The forms the index states an artist in."""

    def test_the_newline_form_yields_nationality_and_both_years(self):
        parsed = parse("Charles Demuth", "Charles Demuth\nAmerican, 1883–1935")
        assert parsed == ParsedArtist(name="Charles Demuth", nationality="American", born=1883, died=1935)

    def test_the_parenthetical_form_yields_the_same(self):
        """The index's own parse gave these records no nationality at all."""
        parsed = parse("Georgia O'Keeffe", "Georgia O'Keeffe (American, 1887–1986)", born=1887, died=1986)
        assert parsed.nationality == "American"
        assert (parsed.born, parsed.died) == (1887, 1986)

    def test_an_ascii_hyphen_reads_as_a_range(self):
        parsed = parse("Frank Lloyd Wright", "Frank Lloyd Wright\nAmerican, 1867-1959")
        assert (parsed.born, parsed.died) == (1867, 1959)

    def test_a_birthplace_clause_stays_with_the_nationality(self):
        """A museum label reads "American, born Russia (Latvia)" — that is the line."""
        parsed = parse("Mark Rothko", "Mark Rothko (Marcus Rothkowitz)\nAmerican, born Russia (Latvia), 1903–1970")
        assert parsed.nationality == "American, born Russia (Latvia)"
        assert (parsed.born, parsed.died) == (1903, 1970)

    def test_an_alternate_name_in_parentheses_is_not_a_details_clause(self):
        """Without the year test, "(Marcus Rothkowitz)" becomes the nationality."""
        parsed = parse("Mark Rothko", "Mark Rothko (Marcus Rothkowitz)\nAmerican, 1903–1970")
        assert parsed.nationality == "American"

    def test_a_born_only_artist_keeps_a_legible_lifespan(self):
        """Rendered from the years alone this reads "1930–", which looks like a fault."""
        parsed = parse("Jasper Johns", "Jasper Johns\nAmerican, born 1930")
        assert (parsed.born, parsed.died) == (1930, None)
        assert parsed.lifespan_text == "born 1930"

    def test_a_complete_lifespan_carries_no_text_form(self):
        """Two integers say it; a text form would only be a second place to disagree."""
        assert parse("Charles Demuth", "Charles Demuth\nAmerican, 1883–1935").lifespan_text is None

    def test_a_born_and_died_sentence_yields_both_years(self):
        parsed = parse(
            "Vasily Kandinsky",
            "Vasily Kandinsky\nBorn Moscow (formerly Russian Empire, now Russia), 1866; died Neuilly-sur-Seine, France, 1944",
        )
        assert (parsed.born, parsed.died) == (1866, 1944)
        assert parsed.nationality == "Born Moscow (formerly Russian Empire, now Russia)"

    def test_an_attribution_line_beats_the_production_credits_below_it(self):
        """Taking "the second line" here would read a printing house's founding year as a birth."""
        parsed = parse(
            "Raoul Dufy",
            "Designed by Raoul Dufy (French, 1877–1953)\n"
            "Produced by Bianchini Férier, founded 1888\n"
            "Printed by Manufacture de Tournon\nFrance, Tournon",
        )
        assert parsed.nationality == "French"
        assert (parsed.born, parsed.died) == (1877, 1953)

    def test_a_culture_with_no_dates_keeps_its_place(self):
        parsed = parse("Moche", "Moche\nNorth coast, Peru", nationality="North coast, Peru")
        assert parsed.nationality == "North coast, Peru"
        assert (parsed.born, parsed.died) == (None, None)

    def test_a_name_with_its_script_attached_still_parses(self):
        parsed = parse("Katsushika Hokusai", "Katsushika Hokusai 葛飾 北斎\nJapanese, 1760-1849")
        assert parsed.nationality == "Japanese"
        assert (parsed.born, parsed.died) == (1760, 1849)

    def test_the_sources_words_beat_the_indexs_own_parse(self):
        """Brancusi died in 1957; the index stored 1952 and its own details text says 1957."""
        parsed = parse("Constantin Brancusi", "Constantin Brancusi\nFrench, born Romania, 1876–1957", born=1876, died=1952)
        assert parsed.died == 1957

    def test_they_beat_it_on_the_nationality_too(self):
        """The two agree everywhere in the corpus today, so only a test states which wins."""
        parsed = parse("Someone", "Someone\nDutch, 1872–1944", nationality="Belgian")
        assert parsed.nationality == "Dutch"


class TestWithoutArtistDetails:
    """Eight records carry no `artist_details` line at all."""

    def test_the_flat_artist_field_is_the_fallback(self):
        parsed = parse("Josef Albers")
        assert parsed == ParsedArtist(name="Josef Albers")

    def test_the_indexs_stored_nationality_fills_what_the_words_do_not_carry(self):
        assert parse("Robert Gober", nationality="American").nationality == "American"

    def test_a_clause_hiding_in_the_flat_field_is_read_from_there(self):
        """One record puts the whole clause in the artist's name and nowhere else."""
        parsed = parse("Juan Gris (Spanish, 1887–1927)")
        assert parsed.name == "Juan Gris"
        assert parsed.nationality == "Spanish"
        assert (parsed.born, parsed.died) == (1887, 1927)

    def test_years_stored_as_text_become_years(self):
        """The index wrote some of these as numbers and some as strings."""
        assert parse("Marilyn Minter", nationality="American", born="1948").born == 1948

    def test_a_year_that_is_not_a_year_is_not_read_as_one(self):
        assert parse("Nobody", nationality="American", born="unknown").born is None


class TestArtistName:
    def test_an_alternate_name_survives(self):
        assert artist_name("Mark Rothko (Marcus Rothkowitz)") == "Mark Rothko (Marcus Rothkowitz)"

    def test_a_details_clause_does_not(self):
        assert artist_name("Juan Gris (Spanish, 1887–1927)") == "Juan Gris"


class TestReadyPath:
    def test_the_render_is_named_from_the_master_and_the_resize(self):
        assert ready_path_for("Charles Demuth - Home of the Brave.jpg", "scaled") == (
            "ready/Charles Demuth - Home of the Brave_rscaled.jpg"
        )

    def test_the_name_carries_no_panel_geometry(self):
        """The 2024 label filenames encoded one, which is why they name a panel nobody owns."""
        assert "_w" not in ready_path_for("A work.jpg", "scaled")


class TestReadIndex:
    def _write(self, tmp_path, document):
        path = tmp_path / "all.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def _record(self, **overrides):
        record = {
            "url": "https://www.artic.edu/artworks/1/a-work",
            "raw_file": "A work.jpg",
            "mat_hexrgb": "#27285B",
            "metadata": {"title": "A work", "artist": "Someone", "date_created": "1931"},
        }
        return record | overrides

    def test_a_record_becomes_paths_relative_to_the_art_root(self, tmp_path):
        (record,) = read_index(self._write(tmp_path, {"default_resize": "scaled", "art": [self._record()]}))
        assert record.raw_path == "raw/A work.jpg"
        assert record.ready_path == "ready/A work_rscaled.jpg"

    def test_order_is_preserved_because_it_is_the_only_recency_signal(self, tmp_path):
        urls = [self._record(url=f"https://www.artic.edu/artworks/{n}/w") for n in (3, 1, 2)]
        document = {"default_resize": "scaled", "art": urls}
        assert [record.url.split("/")[-2] for record in read_index(self._write(tmp_path, document))] == ["3", "1", "2"]

    def test_a_tile_served_host_is_institutional_and_dezoomified(self, tmp_path):
        (record,) = read_index(self._write(tmp_path, {"default_resize": "scaled", "art": [self._record()]}))
        assert record.provider == "artic"
        assert record.source_class is SourceClass.INSTITUTIONAL
        assert record.acquisition_method is AcquisitionMethod.DEZOOMIFY

    def test_the_other_known_host_is_named_too(self, tmp_path):
        document = {"default_resize": "scaled", "art": [self._record(url="https://artsandculture.google.com/asset/x")]}
        (record,) = read_index(self._write(tmp_path, document))
        assert record.provider == "google_arts_culture"
        assert record.acquisition_method is AcquisitionMethod.DEZOOMIFY

    def test_an_unknown_host_is_a_plain_web_page_rather_than_a_refusal(self, tmp_path):
        """Guessing that an unknown site serves tiles sends the fetcher somewhere that cannot work."""
        document = {"default_resize": "scaled", "art": [self._record(url="https://example.museum/piece")]}
        (record,) = read_index(self._write(tmp_path, document))
        assert record.provider == "example.museum"
        assert record.source_class is SourceClass.CONTEMPORARY_WEB
        assert record.acquisition_method is AcquisitionMethod.DIRECT_HTTP

    def test_per_device_state_has_nowhere_to_land(self, tmp_path):
        """`tv_content_id` is a fact about one television, and the catalogue holds none."""
        document = {"default_resize": "scaled", "art": [self._record(tv_content_id="MY_F1114", tv_content_thumb_md5="d931")]}
        (record,) = read_index(self._write(tmp_path, document))
        assert "MY_F1114" not in repr(record)
        assert not hasattr(record, "tv_content_id")

    def test_a_blank_field_reads_as_absent(self, tmp_path):
        blank = self._record(metadata={"title": "A work", "artist": "Someone", "medium": "  "})
        (record,) = read_index(self._write(tmp_path, {"default_resize": "scaled", "art": [blank]}))
        assert record.medium is None

    def test_the_files_default_resize_applies_where_a_record_states_none(self, tmp_path):
        (record,) = read_index(self._write(tmp_path, {"default_resize": "cropped", "art": [self._record()]}))
        assert record.ready_path.endswith("_rcropped.jpg")

    def test_a_record_stating_its_own_resize_wins(self, tmp_path):
        document = {"default_resize": "scaled", "art": [self._record(resize_option="cropped")]}
        (record,) = read_index(self._write(tmp_path, document))
        assert record.ready_path.endswith("_rcropped.jpg")

    @pytest.mark.parametrize(
        ("document", "expected"),
        [
            ({"art": "not a list"}, "no 'art' list"),
            (["not an object"], "should hold an object"),
        ],
    )
    def test_a_document_of_the_wrong_shape_is_refused_by_name(self, tmp_path, document, expected):
        with pytest.raises(LegacyIndexError, match=expected):
            read_index(self._write(tmp_path, document))

    def test_a_record_missing_a_required_field_names_the_field_and_its_position(self, tmp_path):
        document = {"default_resize": "scaled", "art": [self._record(raw_file=None)]}
        with pytest.raises(LegacyIndexError, match="record 0 has no raw_file"):
            read_index(self._write(tmp_path, document))

    def test_a_file_that_is_not_json_is_refused(self, tmp_path):
        path = tmp_path / "all.json"
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(LegacyIndexError, match="not valid JSON"):
            read_index(path)

    def test_a_record_with_no_resize_anywhere_is_refused(self, tmp_path):
        with pytest.raises(LegacyIndexError, match="no resize_option"):
            read_index(self._write(tmp_path, {"art": [self._record()]}))
