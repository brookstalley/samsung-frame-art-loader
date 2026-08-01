"""Seeding the catalogue from parsed index records.

The seeder's whole job is to be safe to run twice and honest about what it could
not do, so most of what is asserted here is about the second run and about the
report rather than about the first run's happy path.
"""

import uuid
from string import Formatter

import pytest

from curation.persistence.records import AcquisitionMethod, ArtworkStatus, MatMethod, RenditionKind, SourceClass
from curation.seed.ingest import _DETAIL, MAT_REASON, SeedNote, seed_catalogue
from curation.seed.legacy import LegacyRecord, ParsedArtist


@pytest.fixture
def record():
    """One index record, defaulting everything a test does not name."""

    def _record(title="Nighthawks", *, url=None, artist=None, mat="#27285b", **fields):
        stem = title.replace(" ", "-")
        return LegacyRecord(
            url=url or f"https://www.artic.edu/artworks/{stem}",
            title=title,
            artist=artist or ParsedArtist(name="Edward Hopper", nationality="American", born=1882, died=1967),
            raw_path=f"raw/{stem}.jpg",
            ready_path=f"ready/{stem}_rscaled.jpg",
            mat_hex=mat,
            provider="artic",
            source_class=SourceClass.INSTITUTIONAL,
            acquisition_method=AcquisitionMethod.DEZOOMIFY,
            **{"date_created": "1942", "medium": "Oil on canvas", "dimensions": "84.1 × 152.4 cm", **fields},
        )

    return _record


@pytest.fixture
def tree(tmp_path, jpeg):
    """An art tree holding whichever of a record's two files a test asks for."""

    def _tree(*records, master=True, render=True):
        for entry in records:
            if master:
                jpeg(tmp_path / entry.raw_path, width=6000, height=4000)
            if render:
                jpeg(tmp_path / entry.ready_path, width=3840, height=2160)
        return tmp_path

    return _tree


def seed(records, service, art_root):
    return seed_catalogue(records, catalogue=service, art_root=art_root)


class TestTheReportsVocabulary:
    """The report's prose is behaviour: it is what a curator acts on."""

    #: Every value a note's sentence is allowed to ask for, and something to put
    #: there. A sentence naming anything else could not be filled at the site
    #: that raises it, and would reach a curator as a formatting error.
    CONTEXT = {"path": "raw/a.jpg", "count": 2, "discarded": "#433735"}

    def test_every_cause_has_a_sentence(self):
        """A cause added without one reaches a curator as a bare enum value."""
        assert [note for note in SeedNote if note not in _DETAIL] == []

    def test_no_sentence_is_blank(self):
        assert [note for note in SeedNote if not _DETAIL[note].strip()] == []

    def test_every_sentence_can_be_filled(self):
        """The failure this catches happens in front of a curator, not in a test."""
        unfillable = [note for note in SeedNote if not _DETAIL[note].format(**self.CONTEXT)]
        assert unfillable == []

    def test_no_sentence_asks_for_something_the_code_cannot_give_it(self):
        asked = {field for note in SeedNote for _, field, _, _ in Formatter().parse(_DETAIL[note]) if field}
        assert asked <= set(self.CONTEXT)


class TestSeedingOnce:
    def test_a_record_becomes_a_work_with_everything_the_index_carried(self, service, record, tree):
        entry = record()
        report = seed([entry], service, tree(entry))

        (seeded,) = report.works
        assert seeded.created
        detail = service.get_artwork(seeded.work_id)
        assert detail.artwork.title == "Nighthawks"
        assert detail.artwork.status is ArtworkStatus.ACCEPTED
        assert detail.artist is not None and detail.artist.name == "Edward Hopper"

    def test_identity_is_minted_and_is_never_the_source_url(self, service, record, tree):
        entry = record()
        report = seed([entry], service, tree(entry))

        (seeded,) = report.works
        assert uuid.UUID(seeded.work_id).version == 4
        assert entry.url not in seeded.work_id
        (source,) = service.list_sources(seeded.work_id)
        assert source.url == entry.url
        assert source.is_primary

    def test_the_master_is_measured_from_the_file_rather_than_taken_on_trust(self, service, record, tree):
        entry = record()
        report = seed([entry], service, tree(entry))

        original = service.get_original(report.works[0].work_id)
        assert original is not None
        assert (original.width, original.height) == (6000, 4000)
        assert original.content_hash.startswith("sha256:")
        assert original.byte_size > 0
        assert original.relative_path == "raw/Nighthawks.jpg"

    def test_the_render_is_recorded_at_the_size_the_file_actually_is(self, service, record, tree):
        entry = record()
        report = seed([entry], service, tree(entry))

        (view,) = service.list_renditions(report.works[0].work_id)
        assert view.rendition.kind is RenditionKind.TV_DISPLAY
        assert (view.rendition.target_width, view.rendition.target_height) == (3840, 2160)
        assert not view.stale

    def test_the_mat_is_carried_rather_than_derived(self, service, record, tree):
        entry = record(mat="#433735")
        report = seed([entry], service, tree(entry))

        mat = service.current_mat_color(report.works[0].work_id)
        assert mat is not None
        assert mat.hex_rgb == "#433735"
        assert mat.method is MatMethod.MANUAL
        assert mat.reason == MAT_REASON

    def test_a_clean_record_earns_no_notes(self, service, record, tree):
        entry = record()
        assert seed([entry], service, tree(entry)).noted == []

    def test_one_artist_row_serves_every_work_of_theirs(self, service, record, tree):
        artist = ParsedArtist(name="Mark Rothko", nationality="American", born=1903, died=1970)
        entries = [record("No. 1", artist=artist), record("No. 2", artist=artist)]
        report = seed(entries, service, tree(*entries))

        artist_ids = {service.get_artwork(work.work_id).artist.id for work in report.works}
        assert len(artist_ids) == 1


class TestSeedingTwice:
    def test_the_second_run_creates_nothing(self, service, record, tree):
        entry = record()
        root = tree(entry)
        seed([entry], service, root)
        second = seed([entry], service, root)

        assert [work.created for work in second.works] == [False]
        assert service.list_artworks().total == 1

    def test_the_mat_history_does_not_grow_a_row_per_run(self, service, record, tree):
        entry = record()
        root = tree(entry)
        first = seed([entry], service, root)
        seed([entry], service, root)

        assert len(service.mat_color_history(first.works[0].work_id)) == 1

    def test_neither_does_anything_else(self, service, record, tree):
        entry = record()
        root = tree(entry)
        first = seed([entry], service, root)
        seed([entry], service, root)

        work_id = first.works[0].work_id
        assert len(service.list_sources(work_id)) == 1
        assert len(service.list_renditions(work_id)) == 1

    def test_a_changed_mat_supersedes_and_the_previous_choice_is_kept(self, service, record, tree):
        """Mat quality is the product's subjective bar: a worse choice has to be reversible."""
        first_entry = record(mat="#433735")
        root = tree(first_entry)
        first = seed([first_entry], service, root)
        seed([record(mat="#1c1818")], service, root)

        history = service.mat_color_history(first.works[0].work_id)
        assert [mat.hex_rgb for mat in history] == ["#1c1818", "#433735"]
        assert service.current_mat_color(first.works[0].work_id).hex_rgb == "#1c1818"

    def test_a_replaced_master_leaves_its_old_render_reading_stale(self, service, record, tree, jpeg):
        """Re-stamping here would declare a superseded acquisition current, and the
        rule that keeps it off the wall could then never fire for a seeded work."""
        entry = record()
        root = tree(entry)
        first = seed([entry], service, root)
        work_id = first.works[0].work_id

        jpeg(root / entry.raw_path, width=7000, height=5000)
        second = seed([entry], service, root)

        assert [view.stale for view in service.list_renditions(work_id)] == [True]
        assert SeedNote.RENDITION_STALE in {item.note for item in second.works[0].notes}

    def test_a_stale_render_keeps_the_moment_it_was_actually_made(self, service, record, tree, jpeg):
        """Re-recording would move `generated_at` to now and claim a regeneration that did not happen."""
        entry = record()
        root = tree(entry)
        first = seed([entry], service, root)
        made_at = service.list_renditions(first.works[0].work_id)[0].rendition.generated_at

        jpeg(root / entry.raw_path, width=7000, height=5000)
        seed([entry], service, root)

        assert service.list_renditions(first.works[0].work_id)[0].rendition.generated_at == made_at

    def test_a_render_that_arrives_later_is_picked_up(self, service, record, tree, jpeg):
        """The report names a missing render; putting the file there and re-running has to fix it."""
        entry = record()
        root = tree(entry, render=False)
        first = seed([entry], service, root)
        assert [note.note for note in first.works[0].notes] == [SeedNote.RENDITION_FILE_ABSENT]

        jpeg(root / entry.ready_path, width=3840, height=2160)
        second = seed([entry], service, root)

        assert second.works[0].notes == []
        assert len(service.list_renditions(first.works[0].work_id)) == 1


class TestRecordsDescribingOneWork:
    def test_two_records_for_one_url_become_one_work(self, service, record, tree):
        entries = [record(mat="#433735"), record(mat="#1c1818")]
        report = seed(entries, service, tree(*entries))

        assert len(report.works) == 1
        assert report.records_read == 2
        assert report.records_collapsed == 1

    def test_the_last_record_wins_and_the_dropped_colour_is_named(self, service, record, tree):
        entries = [record(mat="#433735"), record(mat="#1c1818")]
        report = seed(entries, service, tree(*entries))

        (work,) = report.works
        assert service.current_mat_color(work.work_id).hex_rgb == "#1c1818"
        (note,) = [entry for entry in work.notes if entry.note is SeedNote.DUPLICATE_RECORD_DISCARDED]
        assert "#433735" in note.detail

    def test_the_dropped_colour_is_not_in_the_catalogue_at_all(self, service, record, tree):
        entries = [record(mat="#433735"), record(mat="#1c1818")]
        report = seed(entries, service, tree(*entries))

        assert [mat.hex_rgb for mat in service.mat_color_history(report.works[0].work_id)] == ["#1c1818"]

    def test_every_record_read_is_accounted_for(self, service, record, tree):
        entries = [record("A"), record("B"), record("B")]
        report = seed(entries, service, tree(*entries))

        assert report.records_read == len(report.works) + report.records_collapsed


class TestWhatTheTreeDoesNotHold:
    def test_a_missing_master_is_named_with_its_path(self, service, record, tree):
        entry = record()
        report = seed([entry], service, tree(entry, master=False))

        (note,) = [item for item in report.works[0].notes if item.note is SeedNote.ORIGINAL_FILE_ABSENT]
        assert entry.raw_path in note.detail
        assert service.get_original(report.works[0].work_id) is None

    def test_a_missing_master_means_no_render_is_recorded_either(self, service, record, tree):
        """A rendition is stamped with the hash of the master it was made from."""
        entry = record()
        report = seed([entry], service, tree(entry, master=False))

        assert service.list_renditions(report.works[0].work_id) == []

    def test_a_missing_render_is_named_and_the_work_still_seeds(self, service, record, tree):
        entry = record()
        report = seed([entry], service, tree(entry, render=False))

        (note,) = [item for item in report.works[0].notes if item.note is SeedNote.RENDITION_FILE_ABSENT]
        assert entry.ready_path in note.detail
        assert service.get_original(report.works[0].work_id) is not None

    def test_a_zero_length_master_is_reported_rather_than_recorded(self, service, record, tmp_path):
        """A file that exists, holds nothing, and looks fine by name is the known download failure."""
        entry = record()
        (tmp_path / entry.raw_path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / entry.raw_path).write_bytes(b"")
        report = seed([entry], service, tmp_path)

        assert SeedNote.ORIGINAL_UNREADABLE in {item.note for item in report.works[0].notes}
        assert service.get_original(report.works[0].work_id) is None

    def test_a_file_that_is_not_an_image_is_reported_rather_than_guessed_at(self, service, record, tmp_path):
        entry = record()
        (tmp_path / entry.raw_path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / entry.raw_path).write_bytes(b"this is not a jpeg")
        report = seed([entry], service, tmp_path)

        assert SeedNote.ORIGINAL_UNREADABLE in {item.note for item in report.works[0].notes}


class TestWhatTheLabelWillBeMissing:
    def test_an_absent_nationality_is_reported(self, service, record, tree):
        entry = record(artist=ParsedArtist(name="Josef Albers"))
        report = seed([entry], service, tree(entry))

        assert SeedNote.NATIONALITY_ABSENT in {item.note for item in report.works[0].notes}

    def test_an_absent_birth_year_is_reported(self, service, record, tree):
        entry = record(artist=ParsedArtist(name="Josef Albers", nationality="American"))
        report = seed([entry], service, tree(entry))

        assert {item.note for item in report.works[0].notes} == {SeedNote.BIRTH_YEAR_ABSENT}

    def test_an_absent_death_year_is_not(self, service, record, tree):
        """Two of these artists are alive; reporting it would list works that are complete."""
        entry = record(artist=ParsedArtist(name="Jasper Johns", nationality="American", born=1930))
        report = seed([entry], service, tree(entry))

        assert report.works[0].notes == []

    def test_absent_dimensions_are_reported_and_stored_as_nothing(self, service, record, tree):
        entry = record(dimensions=None)
        report = seed([entry], service, tree(entry))

        assert SeedNote.DIMENSIONS_ABSENT in {item.note for item in report.works[0].notes}
        assert service.get_artwork(report.works[0].work_id).artwork.dimensions is None

    def test_an_absent_medium_is_reported(self, service, record, tree):
        entry = record(medium=None)
        report = seed([entry], service, tree(entry))

        assert SeedNote.MEDIUM_ABSENT in {item.note for item in report.works[0].notes}

    def test_an_artist_described_by_only_one_of_their_records_is_still_described(self, service, record, tree):
        """An artist row is written once, so the richer reading must not depend on record order."""
        bare = ParsedArtist(name="Franz Kline")
        full = ParsedArtist(name="Franz Kline", nationality="American", born=1910, died=1962)
        entries = [record("Painting", artist=bare), record("Vertical Rust", artist=full)]
        report = seed(entries, service, tree(*entries))

        assert service.get_artwork(report.works[0].work_id).artist.nationality == "American"
        assert report.works[0].notes == []
