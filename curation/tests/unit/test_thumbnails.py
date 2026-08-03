"""Small copies of held works — which image they come from, and when they go stale.

The risk this covers is not "does Pillow resize". It is that a thumbnail is a
*rendition*, so it inherits the catalogue's staleness rule, and a cache that
answers from a file made before the master changed puts a superseded acquisition
in front of the curator — the one thing the staleness rule exists to prevent.
"""

from pathlib import Path

import pytest
from PIL import Image

from curation.persistence.records import AcquisitionMethod, MatMethod, RenditionKind, RightsStatus, SourceClass
from curation.services.errors import ServiceError
from curation.services.thumbnails import THUMBNAIL_MAX_EDGE_PX, ThumbnailSettings, ThumbnailUnavailable


@pytest.fixture
def work(service, settings, decodable_jpeg):
    """A work whose master is a real file on disk, and a factory for its renditions."""

    def _make(*, master=True, width=1600, height=1200, content_hash="hash-1"):
        artwork = service.add_artwork(title="Nighthawks", date_created="1942")
        source = service.add_source(
            artwork_id=artwork.id,
            url="https://museum.example/nighthawks",
            provider="artic",
            source_class=SourceClass.INSTITUTIONAL,
            acquisition_method=AcquisitionMethod.DEZOOMIFY,
            rights_status=RightsStatus.PUBLIC_DOMAIN,
            is_primary=True,
        )
        if master:
            relative = f"raw/{artwork.id}.jpg"
            decodable_jpeg(settings.art_root / relative, width=width, height=height)
            service.record_original(
                artwork_id=artwork.id,
                source_id=source.id,
                path=relative,
                width=width,
                height=height,
                byte_size=(settings.art_root / relative).stat().st_size,
                content_hash=content_hash,
            )
        return artwork

    return _make


class TestWhichImageIsUsed:
    def test_the_master_stands_in_when_nothing_has_been_rendered(self, thumbnails, work):
        artwork = work()
        assert thumbnails.source_for(artwork.id).kind == "original"

    def test_a_current_wall_render_is_preferred_over_the_master(self, thumbnails, service, settings, decodable_jpeg, work):
        artwork = work()
        rendered = f"ready/{artwork.id}.jpg"
        decodable_jpeg(settings.art_root / rendered, width=3840, height=2160)
        service.record_rendition(
            artwork_id=artwork.id,
            kind=RenditionKind.TV_DISPLAY,
            target_width=3840,
            target_height=2160,
            path=rendered,
        )
        source = thumbnails.source_for(artwork.id)
        assert source.kind == RenditionKind.TV_DISPLAY.value
        assert source.path == settings.art_root / rendered

    def test_a_stale_wall_render_is_refused_and_the_master_used_instead(
        self, thumbnails, service, settings, decodable_jpeg, work
    ):
        """Serving it would put the previous acquisition on the wall's own preview."""
        artwork = work()
        rendered = f"ready/{artwork.id}.jpg"
        decodable_jpeg(settings.art_root / rendered, width=3840, height=2160)
        service.record_rendition(
            artwork_id=artwork.id,
            kind=RenditionKind.TV_DISPLAY,
            target_width=3840,
            target_height=2160,
            path=rendered,
        )
        # A new acquisition for the same work: the render now describes an image
        # this work no longer holds.
        source = service.list_sources(artwork.id)[0]
        service.record_original(
            artwork_id=artwork.id,
            source_id=source.id,
            path=f"raw/{artwork.id}.jpg",
            width=1600,
            height=1200,
            byte_size=100,
            content_hash="hash-2",
        )
        assert thumbnails.source_for(artwork.id).kind == "original"

    def test_a_render_recorded_but_absent_from_disk_falls_back_rather_than_failing(self, thumbnails, service, settings, work):
        artwork = work()
        service.record_rendition(
            artwork_id=artwork.id,
            kind=RenditionKind.TV_DISPLAY,
            target_width=3840,
            target_height=2160,
            path=f"ready/{artwork.id}.jpg",
        )
        assert thumbnails.source_for(artwork.id).kind == "original"

    def test_a_work_with_no_master_says_so_rather_than_failing_obscurely(self, thumbnails, work):
        artwork = work(master=False)
        with pytest.raises(ThumbnailUnavailable, match="No master image has been acquired"):
            thumbnails.source_for(artwork.id)

    def test_a_master_recorded_but_absent_names_the_path_it_expected(self, thumbnails, service, settings, work):
        artwork = work()
        (settings.art_root / f"raw/{artwork.id}.jpg").unlink()
        with pytest.raises(ThumbnailUnavailable, match=f"raw/{artwork.id}.jpg"):
            thumbnails.source_for(artwork.id)


class TestGenerating:
    def test_the_thumbnail_fits_inside_the_box_and_keeps_its_shape(self, thumbnails, work):
        artwork = work(width=1600, height=1200)
        with Image.open(thumbnails.thumbnail(artwork.id)) as produced:
            assert max(produced.size) == THUMBNAIL_MAX_EDGE_PX
            # 4:3 in, 4:3 out. Cropping an artwork to fill a tile is the one
            # thing this surface must not do.
            assert produced.size[0] / produced.size[1] == pytest.approx(1600 / 1200, abs=0.01)

    def test_an_image_smaller_than_the_box_is_not_enlarged(self, thumbnails, work):
        """Upscaling turns an honest "this image is small" into an apparent rendering fault."""
        artwork = work(width=200, height=150)
        with Image.open(thumbnails.thumbnail(artwork.id)) as produced:
            assert produced.size == (200, 150)

    def test_generating_records_a_rendition_so_the_file_is_not_an_orphan(self, thumbnails, service, work):
        artwork = work()
        thumbnails.thumbnail(artwork.id)
        kinds = [view.rendition.kind for view in service.list_renditions(artwork.id)]
        assert RenditionKind.THUMBNAIL in kinds

    def test_the_recorded_path_is_relative_to_the_art_root(self, thumbnails, service, work):
        """No stored path is absolute, so a catalogue survives being restored elsewhere."""
        artwork = work()
        thumbnails.thumbnail(artwork.id)
        row = next(v.rendition for v in service.list_renditions(artwork.id) if v.rendition.kind is RenditionKind.THUMBNAIL)
        assert row.relative_path == f"thumbs/{artwork.id}.jpg"

    def test_a_second_ask_reuses_the_file_rather_than_re_encoding_it(self, thumbnails, work):
        artwork = work()
        first = thumbnails.thumbnail(artwork.id)
        stamp = first.stat().st_mtime_ns
        assert thumbnails.thumbnail(artwork.id).stat().st_mtime_ns == stamp

    def test_a_replaced_master_regenerates_rather_than_serving_the_old_picture(
        self, thumbnails, service, settings, decodable_jpeg, work
    ):
        """The whole point of the staleness rule, applied to the cache.

        The inputs move and the number of calls does not: an idempotence test
        that holds the tree still tests the case nobody would re-run for.
        """
        artwork = work(width=1600, height=1200, content_hash="hash-1")
        first = thumbnails.thumbnail(artwork.id)
        with Image.open(first) as produced:
            assert produced.size[0] > produced.size[1], "the first master is landscape"

        source = service.list_sources(artwork.id)[0]
        replacement = f"raw/{artwork.id}-2.jpg"
        decodable_jpeg(settings.art_root / replacement, width=600, height=1500)
        service.record_original(
            artwork_id=artwork.id,
            source_id=source.id,
            path=replacement,
            width=600,
            height=1500,
            byte_size=(settings.art_root / replacement).stat().st_size,
            content_hash="hash-2",
        )

        with Image.open(thumbnails.thumbnail(artwork.id)) as regenerated:
            assert regenerated.size[1] > regenerated.size[0], "the cache still holds the previous acquisition"

    def test_a_deleted_cache_file_is_rebuilt_even_though_its_row_is_current(self, thumbnails, work):
        """A row is a promise about a file; the file is the answer."""
        artwork = work()
        first = thumbnails.thumbnail(artwork.id)
        first.unlink()
        assert thumbnails.thumbnail(artwork.id).is_file()

    def test_a_file_that_is_not_an_image_is_reported_rather_than_raised_as_a_fault(self, thumbnails, service, settings, work):
        artwork = work()
        (settings.art_root / f"raw/{artwork.id}.jpg").write_bytes(b"this is not a picture")
        with pytest.raises(ThumbnailUnavailable, match="could not be read"):
            thumbnails.thumbnail(artwork.id)

    def test_an_unreadable_source_writes_nothing_at_all(self, thumbnails, settings, work):
        """The cheap half: the decode fails before any byte is written."""
        artwork = work()
        (settings.art_root / f"raw/{artwork.id}.jpg").write_bytes(b"this is not a picture")
        with pytest.raises(ThumbnailUnavailable):
            thumbnails.thumbnail(artwork.id)
        assert _leftovers(settings) == []

    def test_a_write_that_fails_partway_leaves_no_partial_file_behind(self, thumbnails, settings, work, monkeypatch):
        """The half that actually needs the cleanup, and the one that is easy to miss.

        The unreadable-source case above cannot reach it: decoding raises before
        anything has been written, so that test passes with the cleanup deleted
        outright — verified by deleting it. A disk filling up mid-write is the
        real path, and it is the one that would otherwise leave a half-written
        `.tmp` in the cache for every failed attempt, each under a fresh uuid and
        so stranded for good.

        **The injection point moved when the decode was extracted**, and the
        contract did not. Encoding now happens in memory and only the finished
        bytes reach the disk, so a failure during *encode* can no longer strand
        anything — there is nothing on disk yet to strand. What remains is the
        disk write itself, which is what this now fails, and it is covered by the
        `finally` rather than by either named handler.
        """
        artwork = work()
        intact = Path.write_bytes

        def fail_partway(self, data):  # noqa: ANN001, ANN202
            intact(self, b"\xff\xd8half an image")
            raise OSError("no space left on device")

        monkeypatch.setattr(Path, "write_bytes", fail_partway)
        with pytest.raises(ThumbnailUnavailable, match="could not be read"):
            thumbnails.thumbnail(artwork.id)
        monkeypatch.setattr(Path, "write_bytes", intact)

        assert _leftovers(settings) == []

    def test_a_mode_pillow_refuses_to_convert_is_reported_not_raised(self, thumbnails, work, monkeypatch):
        """A `ValueError` out of `convert` is a missing thumbnail, not a 500.

        Injected rather than built from a file, because no format round-trips to
        the mode that provokes it (`La`) through `Image.open` — the sibling
        `inline_preview` records that measurement and this is its other half. The
        branch is boundary defence; what is asserted is the *contract*, which is
        real either way: this service answers "no thumbnail, here is why" and the
        route above it turns that into a reported absence beside the work rather
        than an error page over the whole grid.

        It was absent here while the sibling carried it, and that asymmetry is
        what the extracted decode exists to stop recurring.
        """
        artwork = work()

        def refuse(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
            raise ValueError("conversion from La to RGB not supported")

        monkeypatch.setattr(Image.Image, "convert", refuse)

        with pytest.raises(ThumbnailUnavailable, match="could not be read"):
            thumbnails.thumbnail(artwork.id)

    def test_a_greyscale_master_still_produces_a_jpeg_a_browser_renders(self, thumbnails, service, settings, work):
        """Museum scans arrive in modes a JPEG save would otherwise refuse."""
        artwork = work()
        Image.new("L", (900, 600), 128).save(settings.art_root / f"raw/{artwork.id}.jpg", format="JPEG")
        with Image.open(thumbnails.thumbnail(artwork.id)) as produced:
            assert produced.mode == "RGB"


class TestWhereTheCacheMayLive:
    def test_a_cache_outside_the_art_root_is_refused_at_wiring_time(self, tmp_path):
        """Caught here it names both directories; caught later it is a ValueError mid-request."""
        with pytest.raises(ServiceError, match="must sit inside ART_ROOT"):
            ThumbnailSettings(art_root=tmp_path / "art", directory=tmp_path / "elsewhere")


class TestReadinessIsUnaffected:
    def test_a_thumbnail_does_not_make_a_work_displayable(self, thumbnails, service, display, work):
        """A thumbnail is a curation convenience; the wall wants a television render.

        Recorded as a test because both are `Rendition` rows, and a readiness rule
        that counted any rendition would put works on the wall with nothing to
        show — passing every test that only ever recorded the right kind.
        """
        artwork = work()
        service.record_mat_color(artwork_id=artwork.id, hex_rgb="#27285b", method=MatMethod.VISION_MODEL)
        thumbnails.thumbnail(artwork.id)
        theme = display.add_theme(name="Evening")
        display.add_to_theme(theme_id=theme.id, artwork_id=artwork.id)
        build = display.build_manifest(theme.id)
        assert [exclusion.reason for exclusion in build.exclusions] == ["no_rendition"]


def _leftovers(settings) -> list:
    """Anything sitting in the thumbnail cache, staging files included."""
    if not settings.thumbnails_path.exists():
        return []
    return sorted(settings.thumbnails_path.glob("*"))
