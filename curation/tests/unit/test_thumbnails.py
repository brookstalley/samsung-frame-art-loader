"""Small copies of held works — which image they come from, and when they go stale.

The risk this covers is not "does Pillow resize". It is that a thumbnail is a
*rendition*, so it inherits the catalogue's staleness rule, and a cache that
answers from a file made before the master changed puts a superseded acquisition
in front of the curator — the one thing the staleness rule exists to prevent.

**And that inheritance is not sufficient, which is the harder half.** A thumbnail
is the one rendition drawn from another rendition: once a work has a television
canvas the thumbnail is a copy of *that*, and neither composing a canvas nor
recomposing one in a new mat colour touches the original the inherited rule asks
about. So the inherited rule alone answers "current" for a picture that has since
been redrawn, and the two ways a curator meets it — a card badged "wall render"
over the bare master, and a mat colour that changes the wall but not the picture
in front of them — are what the tests below hold.
"""

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from PIL import Image

from curation.persistence.records import (
    AcquisitionMethod,
    FetchStatus,
    MatMethod,
    Rendition,
    RenditionKind,
    RightsStatus,
    SourceClass,
)
from curation.services.errors import ServiceError
from curation.services.thumbnails import (
    THUMBNAIL_MAX_EDGE_PX,
    ThumbnailSettings,
    ThumbnailSource,
    ThumbnailUnavailable,
    _drawn_from,
)


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
                fetch_status=FetchStatus.OK,
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
            fetch_status=FetchStatus.OK,
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


class TestTheSupersededSignal:
    """The one line that says a thumbnail was regenerated for the new reason.

    Its stated purpose is to make a *wrong* comparison legible: anything holding
    `_drawn_from` false re-encodes a 4K canvas per card per page load and reaches
    the operator as "the grid got slow", against a journal with nothing in it. A
    signal whose failure mode is silence is exactly the kind that can be deleted
    without a suite noticing, so both halves are asserted — that it fires here,
    and that it does not fire on the regenerations that were always ordinary. A
    line emitted on every regeneration would be noise rather than the diagnostic
    its comment argues for.
    """

    @staticmethod
    def _events(caplog):
        return [r for r in caplog.records if r.__dict__.get("event") == "thumbnail.superseded"]

    def test_a_regeneration_forced_by_the_new_rule_says_so(self, thumbnails, service, settings, decodable_jpeg, work, caplog):
        artwork = work(width=1600, height=1200)
        thumbnails.thumbnail(artwork.id)

        rendered = f"ready/{artwork.id}.jpg"
        decodable_jpeg(settings.art_root / rendered, width=3840, height=2160)
        service.record_rendition(
            artwork_id=artwork.id,
            kind=RenditionKind.TV_DISPLAY,
            target_width=3840,
            target_height=2160,
            path=rendered,
        )

        with caplog.at_level(logging.INFO, logger="curation.services.thumbnails"):
            thumbnails.thumbnail(artwork.id)

        records = self._events(caplog)
        assert len(records) == 1
        emitted = records[0].__dict__
        assert emitted["work_id"] == artwork.id
        assert emitted["source_kind"] == RenditionKind.TV_DISPLAY.value
        # Both stamps, because the comparison between them is the whole claim —
        # a line reporting only that it happened cannot tell an operator whether
        # the clock or the upsert is what went wrong.
        assert emitted["thumbnail_generated_at"] and emitted["source_generated_at"]

    def test_a_deleted_cache_file_regenerates_quietly(self, thumbnails, work, caplog):
        """Always-regenerated, long before this rule; a line here would be noise."""
        artwork = work()
        thumbnails.thumbnail(artwork.id).unlink()

        with caplog.at_level(logging.INFO, logger="curation.services.thumbnails"):
            thumbnails.thumbnail(artwork.id)

        assert self._events(caplog) == []

    def test_a_replaced_master_regenerates_quietly(self, thumbnails, service, settings, decodable_jpeg, work, caplog):
        """The inherited staleness rule's own case, and not what this signal is about."""
        artwork = work(content_hash="hash-1")
        thumbnails.thumbnail(artwork.id)

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
            fetch_status=FetchStatus.OK,
        )

        with caplog.at_level(logging.INFO, logger="curation.services.thumbnails"):
            thumbnails.thumbnail(artwork.id)

        assert self._events(caplog) == []


class TestTheRuleAtItsBoundary:
    """The one case the service's own tests cannot reach.

    Both writes stamp `datetime.now(UTC)` themselves and are separated by an
    image encode, so no test driving the service can produce two rows of the same
    instant — and there is no clock seam to fake, deliberately. The rule is a pure
    function of two timestamps, so its boundary is pinned where it can be: an
    exact tie means the thumbnail was recorded in the same instant as the canvas
    and therefore cannot have been made *from* it, which is why the comparison is
    strict. Relaxing it to `>=` serves a picture of the mat colour that was just
    replaced, and nothing else in this file can tell.
    """

    @staticmethod
    def _rendition(at):
        return Rendition(
            id="r1",
            artwork_id="a1",
            kind=RenditionKind.THUMBNAIL,
            target_width=THUMBNAIL_MAX_EDGE_PX,
            target_height=THUMBNAIL_MAX_EDGE_PX,
            relative_path="thumbs/a1.jpg",
            source_content_hash="hash-1",
            generated_at=at,
        )

    def test_a_thumbnail_of_the_same_instant_is_not_treated_as_drawn_from_the_canvas(self):
        instant = datetime(2026, 8, 10, 12, 0, 0, tzinfo=UTC)
        source = ThumbnailSource(kind=RenditionKind.TV_DISPLAY.value, path=Path("ready/a1.jpg"), generated_at=instant)
        assert _drawn_from(self._rendition(instant), source) is False

    def test_a_thumbnail_taken_after_the_canvas_is_kept(self):
        canvas = datetime(2026, 8, 10, 12, 0, 0, tzinfo=UTC)
        source = ThumbnailSource(kind=RenditionKind.TV_DISPLAY.value, path=Path("ready/a1.jpg"), generated_at=canvas)
        later = canvas + timedelta(microseconds=1)
        assert _drawn_from(self._rendition(later), source) is True

    def test_a_thumbnail_of_the_master_is_never_second_guessed_on_time(self):
        """The master's branch has no timestamp to compare, and must not invent one."""
        source = ThumbnailSource(kind="original", path=Path("raw/a1.jpg"), generated_at=None)
        ancient = datetime(1999, 1, 1, tzinfo=UTC)
        assert _drawn_from(self._rendition(ancient), source) is True


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
            fetch_status=FetchStatus.OK,
        )

        with Image.open(thumbnails.thumbnail(artwork.id)) as regenerated:
            assert regenerated.size[1] > regenerated.size[0], "the cache still holds the previous acquisition"

    def test_a_thumbnail_of_the_master_is_rebuilt_once_a_wall_render_exists(
        self, thumbnails, service, settings, decodable_jpeg, work
    ):
        """The master's hash cannot answer this, which is why it went unnoticed.

        A thumbnail is the one rendition made from *another rendition*, and the
        staleness rule compares a rendition against the **original**. Composing a
        canvas does not change the original, so a thumbnail built from the bare
        master before the work was ever prepared stayed "current" for good — and
        `source_for` reports `tv_display` over it, so the card badges "wall
        render" above the unmatted picture. Two things a curator can see: the
        aspect becomes the panel's, and the mat appears.
        """
        artwork = work(width=1600, height=1200)
        with Image.open(thumbnails.thumbnail(artwork.id)) as first:
            assert first.size[0] / first.size[1] == pytest.approx(1600 / 1200, abs=0.01), "the master's own shape"

        rendered = f"ready/{artwork.id}.jpg"
        decodable_jpeg(settings.art_root / rendered, width=3840, height=2160)
        service.record_rendition(
            artwork_id=artwork.id,
            kind=RenditionKind.TV_DISPLAY,
            target_width=3840,
            target_height=2160,
            path=rendered,
        )

        assert thumbnails.source_for(artwork.id).kind == RenditionKind.TV_DISPLAY.value
        with Image.open(thumbnails.thumbnail(artwork.id)) as regenerated:
            assert regenerated.size[0] / regenerated.size[1] == pytest.approx(
                3840 / 2160, abs=0.01
            ), "the cache still holds the bare master while the card says 'wall render'"

    def test_a_recomposed_canvas_regenerates_so_a_new_mat_is_actually_seen(
        self, thumbnails, service, settings, decodable_jpeg, work
    ):
        """The same defect on the path a curator drives deliberately.

        Setting a mat colour re-renders the canvas to the *same* path and upserts
        the same rendition row, so nothing about the original moves and no file
        appears or disappears. Without this the curator presses a colour, the
        catalogue records it, the wall shows it — and the picture in front of them
        does not change, which reads as the control being broken.
        """
        artwork = work()
        rendered = f"ready/{artwork.id}.jpg"

        def compose(colour):
            """What `prepare(force=True)` does: same path, same geometry, new paint."""
            decodable_jpeg(settings.art_root / rendered, width=3840, height=2160, color=colour)
            service.record_rendition(
                artwork_id=artwork.id,
                kind=RenditionKind.TV_DISPLAY,
                target_width=3840,
                target_height=2160,
                path=rendered,
            )

        compose((20, 20, 20))
        with Image.open(thumbnails.thumbnail(artwork.id)) as first:
            assert first.convert("RGB").getpixel((4, 4)) == pytest.approx((20, 20, 20), abs=6)

        # What pressing a mat preset amounts to.
        compose((200, 190, 170))

        with Image.open(thumbnails.thumbnail(artwork.id)) as regenerated:
            assert regenerated.convert("RGB").getpixel((4, 4)) == pytest.approx(
                (200, 190, 170), abs=6
            ), "the curator's picture still shows the mat colour they replaced"

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "Known and filed as #116: nothing records what a cached thumbnail was drawn from, so a "
            "canvas-derived one keeps being served under an 'original' badge once the canvas "
            "file goes. Closing it needs provenance on the row; strict, so this flips to a "
            "failure the moment it is fixed rather than sitting green and forgotten."
        ),
    )
    def test_a_canvas_derived_thumbnail_is_not_served_once_the_canvas_file_goes(
        self, thumbnails, service, settings, decodable_jpeg, work
    ):
        """This defect with its two sides swapped, and the reason it is not closed here.

        A `tv_display` row that is current by hash but whose file has gone is the
        state `preparation.py` documents as what a restored catalogue or a cleared
        `ready/` leaves — and `test_a_render_recorded_but_absent_from_disk...`
        above already treats it as real. `source_for` falls back to the master and
        reports `original`, while the cache still holds the matted 16:9 picture, so
        the curator is shown the composed render under a badge denying it.

        The timestamp cannot answer this: it says when the thumbnail was made, not
        what it was made *from*. Regenerating whenever an absent-file canvas row
        exists is the wrong closure — it spends a re-encode per page load forever
        on a thumbnail legitimately drawn from the master.
        """
        artwork = work(width=1600, height=1200)
        rendered = f"ready/{artwork.id}.jpg"
        decodable_jpeg(settings.art_root / rendered, width=3840, height=2160)
        service.record_rendition(
            artwork_id=artwork.id,
            kind=RenditionKind.TV_DISPLAY,
            target_width=3840,
            target_height=2160,
            path=rendered,
        )
        thumbnails.thumbnail(artwork.id)

        (settings.art_root / rendered).unlink()

        assert thumbnails.source_for(artwork.id).kind == "original"
        with Image.open(thumbnails.thumbnail(artwork.id)) as served:
            assert served.size[0] / served.size[1] == pytest.approx(
                1600 / 1200, abs=0.01
            ), "the canvas is gone and its picture is still being served under a 'master image' badge"

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
    def test_a_thumbnail_does_not_make_a_work_displayable(self, thumbnails, service, display, work, wall_id):
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
        build = display.build_manifest(wall_id, theme.id)
        assert [exclusion.reason for exclusion in build.exclusions] == ["no_rendition"]


def _leftovers(settings) -> list:
    """Anything sitting in the thumbnail cache, staging files included."""
    if not settings.thumbnails_path.exists():
        return []
    return sorted(settings.thumbnails_path.glob("*"))
