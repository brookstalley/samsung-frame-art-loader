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
