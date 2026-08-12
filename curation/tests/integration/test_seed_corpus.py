"""Seeding the real 2024 index, and putting what it produced on a wall.

This runs against the tracked index itself rather than a fixture of it, because
the acceptance this chunk owes is about that corpus: the counts below were
measured from it, and a fixture would only prove the seeder survives a corpus
nobody has.

The image tree is synthesised. The deployed one lives on the Pi and holds
multi-megabyte museum scans; what the seeder does with a file is measure it, and
a stand-in of the right size at the right path exercises that identically.
"""

from pathlib import Path

import pytest

from curation.manifest.builder import ExclusionReason
from curation.seed.ingest import SeedNote, seed_catalogue
from curation.seed.legacy import read_index

#: The tracked index the 2024 wall is curated from, four levels up from here.
INDEX = Path(__file__).parents[3] / "all.json"

#: Measured from that file on 2026-08-01. Records and works differ because two
#: records describe one painting — same URL, same master, same title, differing
#: only in the mat colour someone chose for it.
RECORDS = 41
WORKS = 40

#: Works whose label will read short, by cause. Each is a count of *works* — not
#: of artists and not of records — because a label is set per work, and the three
#: units give different numbers for the same corpus.
#:
#: These are what remains *after* the source's own words are read. The index's
#: own parse of them leaves 14 works with no nationality; going back to the text
#: it parsed recovers nine of those, which is the whole reason that text is
#: treated as the authority.
WITHOUT_NATIONALITY = 5
WITHOUT_BIRTH_YEAR = 9
WITHOUT_MEDIUM = 2
WITHOUT_DIMENSIONS = 2


@pytest.fixture(scope="module")
def records():
    assert INDEX.exists(), f"the 2024 index should be tracked at {INDEX}"
    return read_index(INDEX)


@pytest.fixture
def art_root(records, tmp_path, jpeg):
    """A tree holding a master and a finished render for every record."""
    for record in records:
        jpeg(tmp_path / record.raw_path, width=6000, height=4000)
        jpeg(tmp_path / record.ready_path, width=3840, height=2160)
    return tmp_path


def counted(report, note):
    return [work for work in report.works if note in {entry.note for entry in work.notes}]


class TestTheIndexItself:
    def test_it_holds_the_records_this_chunk_was_measured_against(self, records):
        assert len(records) == RECORDS

    def test_two_of_them_describe_one_work(self, records):
        assert len({record.url for record in records}) == WORKS


class TestSeedingIt:
    def test_every_record_becomes_a_work_or_is_accounted_for(self, records, service, art_root):
        report = seed_catalogue(records, catalogue=service, art_root=art_root)

        assert len(report.works) == WORKS
        assert report.records_collapsed == RECORDS - WORKS
        assert len(report.works) + report.records_collapsed == report.records_read

    def test_the_catalogue_holds_exactly_those_works(self, records, service, art_root):
        seed_catalogue(records, catalogue=service, art_root=art_root)

        assert service.list_artworks(limit=1).total == WORKS

    def test_running_it_twice_does_not_double_the_catalogue(self, records, service, art_root):
        seed_catalogue(records, catalogue=service, art_root=art_root)
        second = seed_catalogue(records, catalogue=service, art_root=art_root)

        assert service.list_artworks(limit=1).total == WORKS
        assert second.created == []

    def test_no_work_carries_a_source_url_as_its_identity(self, records, service, art_root):
        report = seed_catalogue(records, catalogue=service, art_root=art_root)

        assert not [work for work in report.works if work.url in work.work_id]

    def test_the_collapsed_record_names_the_colour_it_dropped(self, records, service, art_root):
        report = seed_catalogue(records, catalogue=service, art_root=art_root)

        (collapsed,) = counted(report, SeedNote.DUPLICATE_RECORD_DISCARDED)
        (note,) = [entry for entry in collapsed.notes if entry.note is SeedNote.DUPLICATE_RECORD_DISCARDED]
        assert "#433735" in note.detail
        assert service.current_mat_color(collapsed.work_id).hex_rgb == "#1c1818"


class TestWhatTheReportSays:
    """The gap in the corpus is visible now rather than discovered at the wall."""

    @pytest.fixture
    def report(self, records, service, art_root):
        return seed_catalogue(records, catalogue=service, art_root=art_root)

    def test_it_names_every_work_whose_label_has_no_nationality(self, report):
        assert len(counted(report, SeedNote.NATIONALITY_ABSENT)) == WITHOUT_NATIONALITY

    def test_it_names_every_work_whose_artist_has_no_birth_year(self, report):
        assert len(counted(report, SeedNote.BIRTH_YEAR_ABSENT)) == WITHOUT_BIRTH_YEAR

    def test_it_names_every_work_with_no_medium(self, report):
        assert len(counted(report, SeedNote.MEDIUM_ABSENT)) == WITHOUT_MEDIUM

    def test_it_names_both_works_with_no_physical_dimensions(self, report):
        titles = {work.title for work in counted(report, SeedNote.DIMENSIONS_ABSENT)}
        assert titles == {"Homage to the Square, Sonorous", "Kaldor Public Art Project 10: Jeff Koons 1995"}

    def test_a_dimensionless_work_stores_nothing_rather_than_a_default_size(self, report, service):
        for work in counted(report, SeedNote.DIMENSIONS_ABSENT):
            assert service.get_artwork(work.work_id).artwork.dimensions is None

    def test_a_complete_tree_leaves_no_work_short_of_an_image(self, report):
        assert counted(report, SeedNote.ORIGINAL_FILE_ABSENT) == []
        assert counted(report, SeedNote.RENDITION_FILE_ABSENT) == []


class TestPuttingThemOnTheWall:
    """Seeding is proven by a manifest, which is the only channel to the display plane."""

    @pytest.fixture
    def built(self, records, service, display, art_root, wall_id):
        report = seed_catalogue(records, catalogue=service, art_root=art_root)
        theme = display.add_theme(name="Everything")
        for work in report.works:
            display.add_to_theme(theme_id=theme.id, artwork_id=work.work_id)
        return display.build_manifest(wall_id, theme.id)

    def test_entries_and_exclusions_together_account_for_every_work(self, built):
        assert built.considered == WORKS

    def test_a_seeded_work_with_all_four_requirements_reaches_the_wall(self, built):
        assert len(built.entries) == WORKS
        assert built.exclusions == []

    def test_a_work_with_no_physical_dimensions_still_reaches_it(self, built):
        """Readiness asks for an original, a mat and a current render — never a size in centimetres."""
        titles = {entry.label["title"] for entry in built.entries}
        assert "Homage to the Square, Sonorous" in titles

    def test_a_label_renders_legibly_when_the_artist_is_barely_described(self, built):
        """A partial label is a real outcome here; a label with no title is not."""
        assert all(entry.label["title"] for entry in built.entries)
        (albers,) = [entry for entry in built.entries if entry.label["title"] == "Homage to the Square, Sonorous"]
        assert albers.label["artist"] == "Josef Albers"
        assert albers.label["artist_nationality"] is None
        assert albers.label["artist_dates"] is None

    def test_a_living_artists_label_does_not_read_as_a_missing_death_date(self, built):
        """Rendered from the years alone this would say "1930–", which looks like a fault."""
        johns = [entry for entry in built.entries if entry.label["artist"] == "Jasper Johns"]
        assert johns and all(entry.label["artist_dates"] == "born 1930" for entry in johns)

    def test_the_index_own_parse_is_corrected_on_the_way_in(self, built):
        """The index stored Brancusi's death as 1952; its own details text says 1957."""
        (brancusi,) = [entry for entry in built.entries if entry.label["artist"] == "Constantin Brancusi"]
        assert brancusi.label["artist_dates"] == "1876–1957"

    def test_a_work_the_tree_had_no_render_for_is_excluded_by_name(self, records, service, display, tmp_path, jpeg, wall_id):
        """The report and the manifest have to agree about which work is not ready."""
        for record in records:
            jpeg(tmp_path / record.raw_path, width=6000, height=4000)
        for record in records[1:]:
            jpeg(tmp_path / record.ready_path, width=3840, height=2160)
        report = seed_catalogue(records, catalogue=service, art_root=tmp_path)
        assert [work.title for work in counted(report, SeedNote.RENDITION_FILE_ABSENT)] == [records[0].title]

        theme = display.add_theme(name="Everything")
        for work in report.works:
            display.add_to_theme(theme_id=theme.id, artwork_id=work.work_id)
        built = display.build_manifest(wall_id, theme.id)

        assert built.considered == WORKS
        assert [(exclusion.title, exclusion.reason) for exclusion in built.exclusions] == [
            (records[0].title, ExclusionReason.NO_RENDITION)
        ]
