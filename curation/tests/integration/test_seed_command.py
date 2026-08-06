"""The seeding command as it is actually invoked.

Everything below the entry point has its own tests, and that is exactly why this
file exists: the first version of `main` handed the seeder a *store* where a
*service* belongs, and every test one layer down stayed green because each of
them wired the service itself. What a command does with the objects it builds is
only ever proven by running the command.
"""

import json

import pytest

from curation.persistence.file import open_catalogue_file
from curation.persistence.sqlite import SqliteCatalogue
from curation.seed.__main__ import main, render
from curation.seed.ingest import SeededWork, SeedNote, SeedNoteEntry, SeedReport
from curation.services.catalogue import CatalogueService


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch, tmp_path):
    """Resolve from this process's environment and nothing else.

    `Settings.from_env` calls `load_dotenv()`, which searches from the config
    module's own directory upward — so the developer's real `.env`, created by
    the documented setup step, is always on the search path.

    Since the 2026-08-05 precedence fix the `ART_ROOT` set here already wins,
    and this stub is the second lock rather than the only one. It is kept
    because of what it guards: this test *seeds a catalogue*, so a precedence
    regression would write into the developer's real art tree, and it would do
    it while passing.
    """
    monkeypatch.setattr("curation.config.load_dotenv", lambda **_: False)
    monkeypatch.setenv("ART_ROOT", str(tmp_path / "art"))


@pytest.fixture
def index(tmp_path, jpeg):
    """A one-record index, with the tree the record points at."""
    document = {
        "default_resize": "scaled",
        "art": [
            {
                "url": "https://www.artic.edu/artworks/1/nighthawks",
                "raw_file": "Nighthawks.jpg",
                "mat_hexrgb": "#27285b",
                "metadata": {
                    "title": "Nighthawks",
                    "artist": "Edward Hopper",
                    "artist_details": "Edward Hopper\nAmerican, 1882–1967",
                    "date_created": "1942",
                    "medium": "Oil on canvas",
                    "dimensions": "84.1 × 152.4 cm",
                },
            }
        ],
    }
    path = tmp_path / "all.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    jpeg(tmp_path / "art" / "raw" / "Nighthawks.jpg", width=6000, height=4000)
    jpeg(tmp_path / "art" / "ready" / "Nighthawks_rscaled.jpg", width=3840, height=2160)
    return path


@pytest.fixture
def seeded_catalogue(tmp_path):
    """Open the catalogue the command wrote, the way any other reader would."""
    opened = []

    def _open():
        handle = open_catalogue_file(tmp_path / "art" / "catalogue.sqlite")
        opened.append(handle)
        return CatalogueService(SqliteCatalogue(handle))

    yield _open
    for handle in opened:
        handle.close()


class TestRunningIt:
    def test_it_seeds_the_catalogue_it_resolves_from_the_environment(self, index, seeded_catalogue, capsys):
        assert main([str(index)]) == 0
        capsys.readouterr()

        listing = seeded_catalogue().list_artworks()
        assert listing.total == 1
        assert listing.entries[0].artwork.title == "Nighthawks"
        assert listing.entries[0].artist.name == "Edward Hopper"

    def test_the_work_it_seeds_is_ready_for_a_wall(self, index, seeded_catalogue, capsys):
        """A work reaches the wall on a master, a mat and a current render — all three from files."""
        main([str(index)])
        capsys.readouterr()

        service = seeded_catalogue()
        (work,) = service.list_artworks().entries
        assert service.get_original(work.artwork.id) is not None
        assert service.current_mat_color(work.artwork.id) is not None
        assert [view.stale for view in service.list_renditions(work.artwork.id)] == [False]

    def test_it_reports_what_it_did(self, index, capsys):
        main([str(index)])

        printed = capsys.readouterr().out
        assert "1 work(s) created" in printed
        assert "Every work seeded cleanly." in printed

    def test_a_missing_index_is_named_rather_than_raised(self, tmp_path, capsys):
        assert main([str(tmp_path / "absent.json")]) == 2
        assert "Could not read" in capsys.readouterr().err

    def test_an_unreadable_index_is_named_rather_than_raised(self, tmp_path, capsys):
        broken = tmp_path / "all.json"
        broken.write_text("{not json", encoding="utf-8")

        assert main([str(broken)]) == 2
        assert "not valid JSON" in capsys.readouterr().err


class TestWhatItPrints:
    """The report is what a curator acts on, so its shape is behaviour."""

    def _report(self, *notes):
        work = SeededWork(url="https://example.museum/x", title="A work", work_id="w-1", created=True, notes=list(notes))
        return SeedReport(records_read=1, works=[work])

    def test_a_clean_run_says_so_rather_than_saying_nothing(self, tmp_path):
        lines = render(self._report(), art_root=tmp_path)
        assert any("Every work seeded cleanly." in line for line in lines)

    def test_a_work_needing_attention_is_named_with_its_reason(self, tmp_path):
        note = SeedNoteEntry(note=SeedNote.DIMENSIONS_ABSENT, detail="No physical dimensions are recorded.")
        lines = render(self._report(note), art_root=tmp_path)

        assert any("1 work(s) need attention" in line for line in lines)
        assert any(line.strip() == "A work" for line in lines)
        assert any("No physical dimensions are recorded." in line for line in lines)

    def test_the_counts_it_leads_with_add_up_to_what_it_read(self, tmp_path):
        lines = render(SeedReport(records_read=41, works=[]), art_root=tmp_path)
        assert "Read 41 record(s)" in lines[0]
        assert "41 record(s) collapsed" in lines[1]
