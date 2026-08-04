"""Acquiring a catalogued work's master image, and what each outcome records.

The fetch modules are tested beside this one; what is asserted here is the policy
that sits above them — which source is used, when a refusal is data about a source
rather than a fault, and what the catalogue holds afterwards.
"""

import stat
from contextlib import contextmanager
from pathlib import Path

import pytest
from PIL import Image

from curation.acquisition.service import (
    AcquisitionOutcome,
    AcquisitionService,
    AcquisitionSettings,
)
from curation.acquisition.space import NotEnoughSpace
from curation.persistence.records import (
    AcquisitionMethod,
    FetchStatus,
    RightsStatus,
    SourceClass,
)
from curation.services.errors import ServiceError


def _jpeg_bytes(width: int = 120, height: int = 80) -> bytes:
    """A real JPEG: the service measures what it fetched, so a stand-in would make
    every success here depend on Pillow never being asked to open it."""
    from io import BytesIO

    buffer = BytesIO()
    Image.new("RGB", (width, height), (40, 40, 90)).save(buffer, format="JPEG")
    return buffer.getvalue()


def _serves(payload: bytes):
    @contextmanager
    def open_stream(_url: str):
        yield iter([payload])

    return open_stream


def _refuses(exc: Exception):
    @contextmanager
    def open_stream(_url: str):
        def gen():
            raise exc
            yield  # pragma: no cover - unreachable, keeps this a generator

        yield gen()

    return open_stream


@pytest.fixture
def acq_settings(tmp_path) -> AcquisitionSettings:
    return AcquisitionSettings(
        art_root=tmp_path,
        originals_path=tmp_path / "raw",
        tile_cache_path=tmp_path / "tile-cache",
        user_agent="samsung-frame-art-loader (test)",
        tile_binary="dezoomify-rs",
        tile_max_pixels=8192,
        tile_timeout_seconds=30,
        max_image_bytes=10_000_000,
        min_free_bytes=1,
    )


def _resolves_publicly(_host: str):
    """Stated rather than looked up, so a rule about sources is not a rule about DNS."""
    return ["93.184.216.34"]


def _acquisition(service, acq_settings, open_stream, *, resolve=_resolves_publicly) -> AcquisitionService:
    return AcquisitionService(service, acq_settings, open_stream=open_stream, resolve=resolve)


#: The stand-in binary's output path is its last argument, which is awkward to
#: build inside an f-string because the shell expansion uses the same braces.
_LAST_ARG = '"$(eval echo \\${$#})"'

_WRITES_ZERO_BYTES_THEN_FAILS = ": > " + _LAST_ARG + '\necho "[ERROR] Could not get any tile for the image." >&2\nexit 1\n'


def _copies_to_last_arg(seed) -> str:
    return 'cp "' + str(seed) + '" ' + _LAST_ARG + "\nexit 0\n"


def _work_with_source(service, *, method=AcquisitionMethod.DIRECT_HTTP, url="https://gallery.example.com/a.jpg", primary=True):
    work = service.add_artwork(title="Nighthawks")
    source = service.add_source(
        artwork_id=work.id,
        url=url,
        provider="gallery_site",
        source_class=SourceClass.CONTEMPORARY_WEB,
        acquisition_method=method,
        rights_status=RightsStatus.UNKNOWN,
        is_primary=primary,
    )
    return work, source


class TestASuccessfulDirectFetch:
    def test_the_work_holds_an_original_naming_real_bytes(self, service, acq_settings):
        work, _ = _work_with_source(service)
        acquisition = _acquisition(service, acq_settings, _serves(_jpeg_bytes()))

        result = acquisition.acquire(work.id)

        assert result.outcome is AcquisitionOutcome.ACQUIRED
        original = service.get_original(work.id)
        assert original is not None
        held = acq_settings.art_root / original.relative_path
        assert held.exists()
        assert held.stat().st_size == original.byte_size > 0

    def test_the_recorded_dimensions_are_the_images_own(self, service, acq_settings):
        work, _ = _work_with_source(service)
        acquisition = _acquisition(service, acq_settings, _serves(_jpeg_bytes(300, 200)))

        acquisition.acquire(work.id)

        original = service.get_original(work.id)
        assert (original.width, original.height) == (300, 200)

    def test_the_stored_path_is_relative_to_the_art_root(self, service, acq_settings):
        # Constraint 6: no absolute path ever reaches a record.
        work, _ = _work_with_source(service)
        acquisition = _acquisition(service, acq_settings, _serves(_jpeg_bytes()))

        acquisition.acquire(work.id)

        assert not Path(service.get_original(work.id).relative_path).is_absolute()

    def test_the_source_records_a_successful_fetch(self, service, acq_settings):
        work, source = _work_with_source(service)
        acquisition = _acquisition(service, acq_settings, _serves(_jpeg_bytes()))

        acquisition.acquire(work.id)

        refreshed = next(s for s in service.list_sources(work.id) if s.id == source.id)
        assert refreshed.last_fetch_status is FetchStatus.OK
        assert refreshed.last_fetched_at is not None

    def test_the_content_hash_matches_the_bytes_on_disk(self, service, acq_settings):
        import hashlib

        work, _ = _work_with_source(service)
        payload = _jpeg_bytes()
        acquisition = _acquisition(service, acq_settings, _serves(payload))

        acquisition.acquire(work.id)

        original = service.get_original(work.id)
        assert original.content_hash == hashlib.sha256(payload).hexdigest()


class TestFailuresAreRecordedNotRaised:
    def test_a_refused_url_records_a_failed_fetch(self, service, acq_settings):
        # A `file://` source is the case the fetch policy exists for, and it must
        # arrive as data about the source rather than as an exception.
        work, source = _work_with_source(service, url="file:///etc/passwd")
        acquisition = _acquisition(service, acq_settings, _serves(_jpeg_bytes()))

        result = acquisition.acquire(work.id)

        assert result.outcome is AcquisitionOutcome.FAILED
        assert "refused" in result.detail
        refreshed = next(s for s in service.list_sources(work.id) if s.id == source.id)
        assert refreshed.last_fetch_status is FetchStatus.FAILED

    def test_a_refused_url_is_never_fetched(self, service, acq_settings):
        reached = []

        @contextmanager
        def open_stream(url: str):
            reached.append(url)
            yield iter([_jpeg_bytes()])

        work, _ = _work_with_source(service, url="https://127.0.0.1/a.jpg")
        _acquisition(service, acq_settings, open_stream).acquire(work.id)

        assert reached == []

    def test_a_transport_failure_records_a_failed_fetch(self, service, acq_settings):
        work, _ = _work_with_source(service)
        acquisition = _acquisition(service, acq_settings, _refuses(RuntimeError("connection reset")))

        result = acquisition.acquire(work.id)

        assert result.outcome is AcquisitionOutcome.FAILED
        assert "connection reset" in result.detail

    def test_a_failed_fetch_leaves_a_previously_held_image_alone(self, service, acq_settings):
        # The promise the notice makes to a curator: retrying costs nothing it
        # already has.
        work, _ = _work_with_source(service)
        _acquisition(service, acq_settings, _serves(_jpeg_bytes(300, 200))).acquire(work.id)
        held = service.get_original(work.id)

        _acquisition(service, acq_settings, _refuses(RuntimeError("boom"))).acquire(work.id)

        after = service.get_original(work.id)
        assert (after.content_hash, after.width, after.height) == (held.content_hash, 300, 200)
        assert (acq_settings.art_root / after.relative_path).exists()

    def test_bytes_that_are_not_an_image_are_a_failure_not_an_original(self, service, acq_settings):
        # Size alone would pass this: it is a non-empty file that no renderer
        # could ever open.
        work, _ = _work_with_source(service)
        acquisition = _acquisition(service, acq_settings, _serves(b"this is not a JPEG" * 10))

        result = acquisition.acquire(work.id)

        assert result.outcome is AcquisitionOutcome.FAILED
        assert "not a readable image" in result.detail
        assert service.get_original(work.id) is None

    def test_undecodable_bytes_are_removed_rather_than_left_on_disk(self, service, acq_settings):
        work, _ = _work_with_source(service)
        _acquisition(service, acq_settings, _serves(b"not a JPEG" * 10)).acquire(work.id)

        assert list((acq_settings.originals_path).glob("*")) == []


class TestTheFreeSpaceGuard:
    def test_a_disk_below_the_floor_refuses_before_anything_is_fetched(self, service, acq_settings):
        from dataclasses import replace

        reached = []

        @contextmanager
        def open_stream(url: str):
            reached.append(url)
            yield iter([_jpeg_bytes()])

        work, _ = _work_with_source(service)
        # A floor no real filesystem clears, so the guard fires deterministically.
        greedy = replace(acq_settings, min_free_bytes=2**62)

        with pytest.raises(NotEnoughSpace, match="short"):
            _acquisition(service, greedy, open_stream).acquire(work.id)

        assert reached == [], "the guard has to run before the fetch, not after it"

    def test_the_refusal_names_the_shortfall(self, service, acq_settings):
        from dataclasses import replace

        work, _ = _work_with_source(service)
        with pytest.raises(NotEnoughSpace, match="GiB"):
            _acquisition(service, replace(acq_settings, min_free_bytes=2**62), _serves(b"")).acquire(work.id)

    def test_the_guard_does_not_require_the_tree_to_exist_yet(self, service, acq_settings):
        # First acquisition on a fresh deployment: `raw/` has not been created,
        # and "no space" would be a wrong answer to the question asked.
        work, _ = _work_with_source(service)
        assert not acq_settings.originals_path.exists()

        result = _acquisition(service, acq_settings, _serves(_jpeg_bytes())).acquire(work.id)

        assert result.outcome is AcquisitionOutcome.ACQUIRED


class TestChoosingTheSource:
    def test_the_primary_source_is_used_when_none_is_named(self, service, acq_settings):
        work, primary = _work_with_source(service)
        service.add_source(
            artwork_id=work.id,
            url="https://other.example.com/b.jpg",
            provider="http",
            source_class=SourceClass.CONTEMPORARY_WEB,
            acquisition_method=AcquisitionMethod.DIRECT_HTTP,
            rights_status=RightsStatus.UNKNOWN,
        )
        result = _acquisition(service, acq_settings, _serves(_jpeg_bytes())).acquire(work.id)

        assert result.source_id == primary.id

    def test_a_named_source_overrides_the_primary(self, service, acq_settings):
        work, _ = _work_with_source(service)
        other = service.add_source(
            artwork_id=work.id,
            url="https://other.example.com/b.jpg",
            provider="http",
            source_class=SourceClass.CONTEMPORARY_WEB,
            acquisition_method=AcquisitionMethod.DIRECT_HTTP,
            rights_status=RightsStatus.UNKNOWN,
        )
        result = _acquisition(service, acq_settings, _serves(_jpeg_bytes())).acquire(work.id, source_id=other.id)

        assert result.source_id == other.id

    def test_acquiring_from_a_second_source_moves_the_primary_flag(self, service, acq_settings):
        # `is_primary` means "produced the held original", so it has to follow
        # the image rather than stay where acceptance first put it.
        work, first = _work_with_source(service)
        other = service.add_source(
            artwork_id=work.id,
            url="https://other.example.com/b.jpg",
            provider="http",
            source_class=SourceClass.CONTEMPORARY_WEB,
            acquisition_method=AcquisitionMethod.DIRECT_HTTP,
            rights_status=RightsStatus.UNKNOWN,
        )
        _acquisition(service, acq_settings, _serves(_jpeg_bytes())).acquire(work.id, source_id=other.id)

        sources = {s.id: s for s in service.list_sources(work.id)}
        assert sources[other.id].is_primary
        assert not sources[first.id].is_primary

    def test_a_failed_fetch_does_not_move_the_primary_flag(self, service, acq_settings):
        work, first = _work_with_source(service)
        other = service.add_source(
            artwork_id=work.id,
            url="https://other.example.com/b.jpg",
            provider="http",
            source_class=SourceClass.CONTEMPORARY_WEB,
            acquisition_method=AcquisitionMethod.DIRECT_HTTP,
            rights_status=RightsStatus.UNKNOWN,
        )
        _acquisition(service, acq_settings, _refuses(RuntimeError("boom"))).acquire(work.id, source_id=other.id)

        sources = {s.id: s for s in service.list_sources(work.id)}
        assert sources[first.id].is_primary
        assert not sources[other.id].is_primary

    def test_a_work_with_no_source_is_refused_by_name(self, service, acq_settings):
        work = service.add_artwork(title="Nighthawks")
        with pytest.raises(ServiceError, match="no source"):
            _acquisition(service, acq_settings, _serves(b"")).acquire(work.id)

    def test_a_source_belonging_to_another_work_is_refused(self, service, acq_settings):
        work, _ = _work_with_source(service)
        other_work, other_source = _work_with_source(service, url="https://elsewhere.example.com/c.jpg")

        with pytest.raises(ServiceError, match="does not belong"):
            _acquisition(service, acq_settings, _serves(b"")).acquire(work.id, source_id=other_source.id)

    def test_several_sources_with_no_primary_refuse_rather_than_guess(self, service, acq_settings):
        # Which source is right is the judgement acceptance already made; making
        # it again here could silently disagree with it.
        work, _ = _work_with_source(service, primary=False)
        service.add_source(
            artwork_id=work.id,
            url="https://other.example.com/b.jpg",
            provider="http",
            source_class=SourceClass.CONTEMPORARY_WEB,
            acquisition_method=AcquisitionMethod.DIRECT_HTTP,
            rights_status=RightsStatus.UNKNOWN,
        )
        with pytest.raises(ServiceError, match="none is primary"):
            _acquisition(service, acq_settings, _serves(b"")).acquire(work.id)

    def test_a_single_source_with_no_primary_flag_is_used(self, service, acq_settings):
        # One source is the only source, so using it invents no judgement.
        work, only = _work_with_source(service, primary=False)
        result = _acquisition(service, acq_settings, _serves(_jpeg_bytes())).acquire(work.id)
        assert result.source_id == only.id


class TestTheApiMethodHasNoProducer:
    def test_an_api_source_is_refused_in_words_rather_than_silently_mishandled(self, service, acq_settings):
        work, _ = _work_with_source(service, method=AcquisitionMethod.API)

        result = _acquisition(service, acq_settings, _serves(_jpeg_bytes())).acquire(work.id)

        assert result.outcome is AcquisitionOutcome.FAILED
        assert "no fetch path is built" in result.detail
        assert "api" in result.detail


class TestTiledAcquisition:
    """Driven through a stand-in binary, for the reasons its own tests give."""

    @staticmethod
    def _binary(tmp_path: Path, body: str) -> str:
        script = tmp_path / "fake-dezoomify"
        script.write_text("#!/bin/sh\n" + body)
        script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        return str(script)

    def _tiled_work(self, service):
        return _work_with_source(
            service,
            method=AcquisitionMethod.DEZOOMIFY,
            url="https://www.artic.edu/iiif/2/abc/info.json",
        )

    def test_a_complete_tiled_fetch_records_an_ok_status(self, service, acq_settings, tmp_path):
        from dataclasses import replace

        payload = _jpeg_bytes(200, 150)
        (tmp_path / "seed.jpg").write_bytes(payload)
        binary = self._binary(tmp_path, f'cp "{tmp_path / "seed.jpg"}" "$(eval echo \\${{$#}})"\nexit 0\n')
        work, source = self._tiled_work(service)

        result = _acquisition(service, replace(acq_settings, tile_binary=binary), _serves(b"")).acquire(work.id)

        assert result.outcome is AcquisitionOutcome.ACQUIRED
        refreshed = next(s for s in service.list_sources(work.id) if s.id == source.id)
        assert refreshed.last_fetch_status is FetchStatus.OK

    def test_a_partial_tiled_fetch_is_recorded_as_partial_and_still_held(self, service, acq_settings, tmp_path):
        # `partial_tiles` is a normal outcome: the work goes on the wall with
        # gaps rather than being treated as a failure.
        from dataclasses import replace

        (tmp_path / "seed.jpg").write_bytes(_jpeg_bytes(200, 150))
        binary = self._binary(
            tmp_path,
            f'cp "{tmp_path / "seed.jpg"}" "$(eval echo \\${{$#}})"\n'
            'echo "[WARN ] Only 120 tiles out of 238 could be downloaded." >&2\nexit 1\n',
        )
        work, source = self._tiled_work(service)

        result = _acquisition(service, replace(acq_settings, tile_binary=binary), _serves(b"")).acquire(work.id)

        assert result.outcome is AcquisitionOutcome.PARTIAL
        assert result.acquired
        assert service.get_original(work.id) is not None
        refreshed = next(s for s in service.list_sources(work.id) if s.id == source.id)
        assert refreshed.last_fetch_status is FetchStatus.PARTIAL_TILES

    def test_a_completed_fetch_reclaims_its_tile_cache(self, service, acq_settings, tmp_path):
        from dataclasses import replace

        (tmp_path / "seed.jpg").write_bytes(_jpeg_bytes())
        binary = self._binary(tmp_path, f'cp "{tmp_path / "seed.jpg"}" "$(eval echo \\${{$#}})"\nexit 0\n')
        work, source = self._tiled_work(service)

        _acquisition(service, replace(acq_settings, tile_binary=binary), _serves(b"")).acquire(work.id)

        assert not (acq_settings.tile_cache_path / source.id).exists()

    def test_a_partial_fetch_keeps_its_tile_cache_so_a_retry_is_cheap(self, service, acq_settings, tmp_path):
        from dataclasses import replace

        (tmp_path / "seed.jpg").write_bytes(_jpeg_bytes())
        binary = self._binary(
            tmp_path,
            f'cp "{tmp_path / "seed.jpg"}" "$(eval echo \\${{$#}})"\n'
            'echo "[WARN ] Only 3 tiles out of 9 could be downloaded." >&2\nexit 1\n',
        )
        work, source = self._tiled_work(service)

        _acquisition(service, replace(acq_settings, tile_binary=binary), _serves(b"")).acquire(work.id)

        assert (acq_settings.tile_cache_path / source.id).is_dir()

    def test_each_source_caches_tiles_under_its_own_id(self, service, acq_settings, tmp_path):
        # One shared cache could only be emptied wholesale, taking the tiles of a
        # fetch that is still worth resuming.
        from dataclasses import replace

        (tmp_path / "seed.jpg").write_bytes(_jpeg_bytes())
        binary = self._binary(
            tmp_path,
            f'cp "{tmp_path / "seed.jpg"}" "$(eval echo \\${{$#}})"\n'
            'echo "[WARN ] Only 3 tiles out of 9 could be downloaded." >&2\nexit 1\n',
        )
        first, first_source = self._tiled_work(service)
        second, second_source = self._tiled_work(service)
        acquisition = _acquisition(service, replace(acq_settings, tile_binary=binary), _serves(b""))

        acquisition.acquire(first.id)
        acquisition.acquire(second.id)

        assert (acq_settings.tile_cache_path / first_source.id).is_dir()
        assert (acq_settings.tile_cache_path / second_source.id).is_dir()

    def test_a_missing_binary_raises_rather_than_blaming_the_source(self, service, acq_settings):
        from dataclasses import replace

        from curation.acquisition.dezoomify import DezoomifyUnavailable

        work, source = self._tiled_work(service)
        absent = replace(acq_settings, tile_binary="/nonexistent/dezoomify-rs")

        with pytest.raises(DezoomifyUnavailable):
            _acquisition(service, absent, _serves(b"")).acquire(work.id)

        # Nothing recorded against the source: no URL is at fault, and a `failed`
        # row here would send a reader to a museum rather than to the deployment.
        refreshed = next(s for s in service.list_sources(work.id) if s.id == source.id)
        assert refreshed.last_fetch_status is None


class TestWiring:
    def test_a_tree_outside_the_art_root_is_refused_at_construction(self, tmp_path):
        with pytest.raises(ServiceError, match="must sit inside ART_ROOT"):
            AcquisitionSettings(
                art_root=tmp_path,
                originals_path=Path("/elsewhere/raw"),
                tile_cache_path=tmp_path / "tile-cache",
                user_agent="x",
                tile_binary="dezoomify-rs",
                tile_max_pixels=8192,
                tile_timeout_seconds=30,
                max_image_bytes=1,
                min_free_bytes=1,
            )

    def test_a_tile_cache_outside_the_art_root_is_refused_too(self, tmp_path):
        with pytest.raises(ServiceError, match="must sit inside ART_ROOT"):
            AcquisitionSettings(
                art_root=tmp_path,
                originals_path=tmp_path / "raw",
                tile_cache_path=Path("/elsewhere/tiles"),
                user_agent="x",
                tile_binary="dezoomify-rs",
                tile_max_pixels=8192,
                tile_timeout_seconds=30,
                max_image_bytes=1,
                min_free_bytes=1,
            )


class TestAFailedRetryCostsTheWorkNothing:
    """The promise `retry_acquisition`'s tip makes, asserted on both fetch paths.

    The surface tells a curator that "a failed attempt replaces nothing", and the
    partial-result notice actively invites the retry that would test it. Both
    routes are covered here because the guarantee held on one path only by
    accident of where staging happened to live.
    """

    @staticmethod
    def _binary(tmp_path: Path, body: str) -> str:
        script = tmp_path / "fake-dezoomify-retry"
        script.write_text("#!/bin/sh\n" + body)
        script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        return str(script)

    def test_a_failed_direct_retry_keeps_the_held_image_and_its_row(self, service, acq_settings):
        work, _ = _work_with_source(service)
        _acquisition(service, acq_settings, _serves(_jpeg_bytes(300, 200))).acquire(work.id)
        held = service.get_original(work.id)
        held_file = acq_settings.art_root / held.relative_path

        _acquisition(service, acq_settings, _refuses(RuntimeError("museum went away"))).acquire(work.id)

        assert held_file.exists(), "the row still names this file, so deleting it strands the record"
        assert service.get_original(work.id).content_hash == held.content_hash

    def test_a_failed_tiled_retry_keeps_the_held_image_and_its_row(self, service, acq_settings, tmp_path):
        from dataclasses import replace

        work, source = _work_with_source(
            service,
            method=AcquisitionMethod.DEZOOMIFY,
            url="https://www.artic.edu/iiif/2/abc/info.json",
        )
        (tmp_path / "seed.jpg").write_bytes(_jpeg_bytes(300, 200))
        succeeds = replace(
            acq_settings,
            tile_binary=self._binary(tmp_path, _copies_to_last_arg(tmp_path / "seed.jpg")),
        )
        _acquisition(service, succeeds, _serves(b"")).acquire(work.id)
        held = service.get_original(work.id)
        held_file = acq_settings.art_root / held.relative_path
        assert held_file.exists()

        fails = replace(
            acq_settings,
            tile_binary=self._binary(tmp_path, _WRITES_ZERO_BYTES_THEN_FAILS),
        )
        result = _acquisition(service, fails, _serves(b"")).acquire(work.id, source_id=source.id)

        assert result.outcome is AcquisitionOutcome.FAILED
        assert held_file.exists(), "the failing retry deleted the image the work was displaying"
        assert service.get_original(work.id).content_hash == held.content_hash

    def test_unreadable_new_bytes_leave_the_held_image_in_place(self, service, acq_settings):
        # The other route to the same divergence: the fetch succeeds, the bytes
        # turn out not to be an image, and the promotion must not have happened.
        work, _ = _work_with_source(service)
        _acquisition(service, acq_settings, _serves(_jpeg_bytes(300, 200))).acquire(work.id)
        held = service.get_original(work.id)
        held_file = acq_settings.art_root / held.relative_path

        result = _acquisition(service, acq_settings, _serves(b"a 200 response that is not an image" * 5)).acquire(work.id)

        assert result.outcome is AcquisitionOutcome.FAILED
        assert held_file.read_bytes(), "the held image was replaced by bytes that are not an image"
        assert service.get_original(work.id).content_hash == held.content_hash

    def test_a_decompression_bomb_is_recorded_rather_than_raised(self, service, acq_settings):
        # `DecompressionBombError` derives from `Exception`, not `OSError`, and the
        # bytes that trigger it are chosen by whoever controls the source — so a
        # narrower catch fails the call and strands the staged file.
        from PIL import Image

        work, _ = _work_with_source(service)
        original_limit = Image.MAX_IMAGE_PIXELS
        Image.MAX_IMAGE_PIXELS = 16
        try:
            result = _acquisition(service, acq_settings, _serves(_jpeg_bytes(400, 400))).acquire(work.id)
        finally:
            Image.MAX_IMAGE_PIXELS = original_limit

        assert result.outcome is AcquisitionOutcome.FAILED
        assert "not a readable image" in result.detail
        assert list(acq_settings.originals_path.glob("*")) == [], "the staged file was orphaned"

    def test_a_failing_promotion_keeps_the_tiles_a_retry_would_use(self, service, acq_settings, tmp_path):
        from dataclasses import replace

        work, source = _work_with_source(
            service,
            method=AcquisitionMethod.DEZOOMIFY,
            url="https://www.artic.edu/iiif/2/abc/info.json",
        )
        (tmp_path / "junk").write_bytes(b"not an image at all" * 5)
        settings = replace(
            acq_settings,
            tile_binary=self._binary(tmp_path, _copies_to_last_arg(tmp_path / "junk")),
        )

        result = _acquisition(service, settings, _serves(b"")).acquire(work.id)

        assert result.outcome is AcquisitionOutcome.FAILED
        assert (acq_settings.tile_cache_path / source.id).is_dir(), "the retry lost its head start"


class TestARetryNeverLowersTheQualityOfWhatIsHeld:
    """Constraint 16, and the half of the retry promise staging does not keep.

    Staging covers the fetch that *fails*. A fetch that succeeds *partially* is
    not a failure — it arrives with usable bytes and a real image — so it reached
    promotion on the same path a complete one does and overwrote whatever the work
    was displaying. That is the data-loss shape: the curator is told retrying is
    safe, retries a work holding a complete master, and is handed back a gappy one
    with nothing recording that it used to be whole.

    The seeds below differ in *dimensions* rather than only in bytes, so an
    assertion can tell which image survived rather than only that some image did.
    """

    @staticmethod
    def _binary(tmp_path: Path, body: str) -> str:
        script = tmp_path / "fake-dezoomify-quality"
        script.write_text("#!/bin/sh\n" + body)
        script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        return str(script)

    def _tiled_work(self, service):
        return _work_with_source(
            service,
            method=AcquisitionMethod.DEZOOMIFY,
            url="https://www.artic.edu/iiif/2/abc/info.json",
        )

    def _settings(self, acq_settings, tmp_path, seed_name: str, *, width: int, height: int, complete: bool):
        from dataclasses import replace

        seed = tmp_path / seed_name
        seed.write_bytes(_jpeg_bytes(width, height))
        body = _copies_to_last_arg(seed)
        if not complete:
            body = body.replace(
                "exit 0\n",
                'echo "[WARN ] Only 120 tiles out of 238 could be downloaded." >&2\nexit 1\n',
            )
        return replace(acq_settings, tile_binary=self._binary(tmp_path, body))

    def test_a_partial_refetch_does_not_replace_a_complete_master(self, service, acq_settings, tmp_path):
        work, source = self._tiled_work(service)
        complete = self._settings(acq_settings, tmp_path, "whole.jpg", width=400, height=300, complete=True)
        _acquisition(service, complete, _serves(b"")).acquire(work.id)
        held = service.get_original(work.id)
        held_file = acq_settings.art_root / held.relative_path

        gappy = self._settings(acq_settings, tmp_path, "gappy.jpg", width=120, height=90, complete=False)
        result = _acquisition(service, gappy, _serves(b"")).acquire(work.id, source_id=source.id)

        assert result.outcome is AcquisitionOutcome.KEPT_HELD
        assert not result.acquired
        # The image itself, not merely a row pointing at one: dimensions identify
        # which of the two seeds is on disk.
        with Image.open(held_file) as image:
            assert image.size == (400, 300), "the gappy re-fetch overwrote the complete master"
        reread = service.get_original(work.id)
        assert (reread.content_hash, reread.width) == (held.content_hash, 400)
        assert reread.fetch_status is FetchStatus.OK

    def test_the_refused_attempt_is_recorded_on_the_source_and_not_on_the_original(self, service, acq_settings, tmp_path):
        """The two columns say different things, which is why splitting them fixed this.

        `Source.last_fetch_status` is the source's *most recent* attempt, so a
        refused partial belongs on it — otherwise `sources` shows a fetch date
        older than the retry a curator was just told to make, and this outcome's
        notice sends them to exactly that read. `Original.fetch_status` is a fact
        about the held bytes, which this attempt did not change, so it must not
        move. Before the split these were one field and the guard read the wrong one.
        """
        work, source = self._tiled_work(service)
        complete = self._settings(acq_settings, tmp_path, "whole.jpg", width=400, height=300, complete=True)
        _acquisition(service, complete, _serves(b"")).acquire(work.id)

        gappy = self._settings(acq_settings, tmp_path, "gappy.jpg", width=120, height=90, complete=False)
        _acquisition(service, gappy, _serves(b"")).acquire(work.id, source_id=source.id)

        refreshed = next(s for s in service.list_sources(work.id) if s.id == source.id)
        assert refreshed.last_fetch_status is FetchStatus.PARTIAL_TILES
        assert refreshed.last_fetched_at is not None
        # And the held image's own provenance is untouched, which is what the
        # guard reads on the next attempt.
        assert service.get_original(work.id).fetch_status is FetchStatus.OK

    def test_the_refused_bytes_are_discarded_rather_than_left_beside_the_original(self, service, acq_settings, tmp_path):
        work, source = self._tiled_work(service)
        complete = self._settings(acq_settings, tmp_path, "whole.jpg", width=400, height=300, complete=True)
        _acquisition(service, complete, _serves(b"")).acquire(work.id)
        held = service.get_original(work.id)

        gappy = self._settings(acq_settings, tmp_path, "gappy.jpg", width=120, height=90, complete=False)
        _acquisition(service, gappy, _serves(b"")).acquire(work.id, source_id=source.id)

        remaining = sorted(p.name for p in acq_settings.originals_path.glob("*"))
        assert remaining == [Path(held.relative_path).name], "the refused fetch was orphaned on disk"

    def test_the_refused_attempt_keeps_the_tiles_so_asking_again_is_still_cheap(self, service, acq_settings, tmp_path):
        work, source = self._tiled_work(service)
        complete = self._settings(acq_settings, tmp_path, "whole.jpg", width=400, height=300, complete=True)
        _acquisition(service, complete, _serves(b"")).acquire(work.id)

        gappy = self._settings(acq_settings, tmp_path, "gappy.jpg", width=120, height=90, complete=False)
        _acquisition(service, gappy, _serves(b"")).acquire(work.id, source_id=source.id)

        assert (acq_settings.tile_cache_path / source.id).is_dir()

    def test_a_complete_refetch_does_replace_a_held_partial(self, service, acq_settings, tmp_path):
        """The guard must not freeze a work at the first gappy image it got."""
        work, source = self._tiled_work(service)
        gappy = self._settings(acq_settings, tmp_path, "gappy.jpg", width=120, height=90, complete=False)
        first = _acquisition(service, gappy, _serves(b"")).acquire(work.id)
        assert first.outcome is AcquisitionOutcome.PARTIAL
        assert service.get_original(work.id).fetch_status is FetchStatus.PARTIAL_TILES

        complete = self._settings(acq_settings, tmp_path, "whole.jpg", width=400, height=300, complete=True)
        result = _acquisition(service, complete, _serves(b"")).acquire(work.id, source_id=source.id)

        assert result.outcome is AcquisitionOutcome.ACQUIRED
        reread = service.get_original(work.id)
        assert (reread.width, reread.fetch_status) == (400, FetchStatus.OK)

    def test_a_partial_replaces_a_held_partial(self, service, acq_settings, tmp_path):
        """Neither is authoritative and the second may hold more tiles; refusing
        would freeze the work at its first partial with no way forward."""
        work, source = self._tiled_work(service)
        first = self._settings(acq_settings, tmp_path, "gappy-one.jpg", width=120, height=90, complete=False)
        _acquisition(service, first, _serves(b"")).acquire(work.id)

        second = self._settings(acq_settings, tmp_path, "gappy-two.jpg", width=360, height=240, complete=False)
        result = _acquisition(service, second, _serves(b"")).acquire(work.id, source_id=source.id)

        assert result.outcome is AcquisitionOutcome.PARTIAL
        reread = service.get_original(work.id)
        assert (reread.width, reread.fetch_status) == (360, FetchStatus.PARTIAL_TILES)

    def test_a_first_partial_acquisition_is_still_held(self, service, acq_settings, tmp_path):
        """There is nothing to lower. A gappy image beats no image, which is why
        `partial_tiles` is a recorded outcome rather than a refusal."""
        work, _ = self._tiled_work(service)
        gappy = self._settings(acq_settings, tmp_path, "gappy.jpg", width=120, height=90, complete=False)

        result = _acquisition(service, gappy, _serves(b"")).acquire(work.id)

        assert result.outcome is AcquisitionOutcome.PARTIAL
        assert service.get_original(work.id) is not None

    def test_a_partial_does_not_replace_an_original_of_unrecorded_completeness(self, service, acq_settings, tmp_path):
        """Rows written before `fetch_status` existed — the seeded 2024 corpus —
        cannot be told from complete ones, so they get the protective reading."""
        work, source = self._tiled_work(service)
        complete = self._settings(acq_settings, tmp_path, "whole.jpg", width=400, height=300, complete=True)
        _acquisition(service, complete, _serves(b"")).acquire(work.id)
        held = service.get_original(work.id)
        # Exactly what the seed writes, and what a pre-column row reads back as.
        service.record_original(
            artwork_id=work.id,
            source_id=source.id,
            path=held.relative_path,
            width=held.width,
            height=held.height,
            byte_size=held.byte_size,
            content_hash=held.content_hash,
            fetch_status=None,
        )
        assert service.get_original(work.id).fetch_status is None

        gappy = self._settings(acq_settings, tmp_path, "gappy.jpg", width=120, height=90, complete=False)
        result = _acquisition(service, gappy, _serves(b"")).acquire(work.id, source_id=source.id)

        assert result.outcome is AcquisitionOutcome.KEPT_HELD
        assert "unrecorded completeness" in result.detail
        assert service.get_original(work.id).width == 400

    def test_a_partial_is_promoted_when_the_held_row_names_a_file_that_is_gone(self, service, acq_settings, tmp_path):
        """A row outliving its file is the one case where refusing protects nothing.

        The guard's premise is that the work already holds a better image. When the
        bytes are gone — a botched sync, a restore that missed one — the premise is
        false, and refusing would leave the work with a dangling row instead of a
        gappy picture. Preparation already treats a missing master as a failure
        wanting exactly this re-acquisition.
        """
        work, source = self._tiled_work(service)
        complete = self._settings(acq_settings, tmp_path, "whole.jpg", width=400, height=300, complete=True)
        _acquisition(service, complete, _serves(b"")).acquire(work.id)
        held = service.get_original(work.id)
        (acq_settings.art_root / held.relative_path).unlink()

        gappy = self._settings(acq_settings, tmp_path, "gappy.jpg", width=120, height=90, complete=False)
        result = _acquisition(service, gappy, _serves(b"")).acquire(work.id, source_id=source.id)

        assert result.outcome is AcquisitionOutcome.PARTIAL
        reread = service.get_original(work.id)
        assert (reread.width, reread.fetch_status) == (120, FetchStatus.PARTIAL_TILES)
        assert (acq_settings.art_root / reread.relative_path).is_file()

    def test_a_complete_refetch_from_a_smaller_scan_is_allowed(self, service, acq_settings, tmp_path):
        """Pixel count is deliberately not compared. Moving a work to another
        institution's complete file is a choice acceptance already made, and a
        guard that second-guessed it would refuse a legitimate re-acquisition."""
        work, source = self._tiled_work(service)
        large = self._settings(acq_settings, tmp_path, "large.jpg", width=400, height=300, complete=True)
        _acquisition(service, large, _serves(b"")).acquire(work.id)

        smaller = self._settings(acq_settings, tmp_path, "smaller.jpg", width=160, height=120, complete=True)
        result = _acquisition(service, smaller, _serves(b"")).acquire(work.id, source_id=source.id)

        assert result.outcome is AcquisitionOutcome.ACQUIRED
        assert service.get_original(work.id).width == 160

    def test_a_direct_refetch_is_unaffected_because_it_cannot_come_back_partial(self, service, acq_settings):
        """The direct path records `ok` or nothing at all, so the guard never
        fires on it — asserted so a later change that makes direct fetches partial
        cannot quietly skip the comparison."""
        work, _ = _work_with_source(service)
        _acquisition(service, acq_settings, _serves(_jpeg_bytes(400, 300))).acquire(work.id)

        result = _acquisition(service, acq_settings, _serves(_jpeg_bytes(160, 120))).acquire(work.id)

        assert result.outcome is AcquisitionOutcome.ACQUIRED
        assert service.get_original(work.id).fetch_status is FetchStatus.OK
