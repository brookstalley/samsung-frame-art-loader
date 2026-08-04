"""The single-request fetch path, and the ceilings it enforces on the way in."""

import hashlib
from contextlib import contextmanager

import pytest

from curation.acquisition.direct import direct_fetch


def _serves(*chunks: bytes, raises: Exception | None = None):
    @contextmanager
    def open_stream(_url: str):
        def gen():
            yield from chunks
            if raises is not None:
                raise raises

        yield gen()

    return open_stream


def _run(tmp_path, open_stream, *, max_bytes=10_000_000, name="work.jpg"):
    return direct_fetch(
        "https://gallery.example.com/image.jpg",
        destination=tmp_path / "raw" / name,
        open_stream=open_stream,
        max_bytes=max_bytes,
    )


class TestTheHappyPath:
    def test_bytes_land_at_the_destination(self, tmp_path):
        result = _run(tmp_path, _serves(b"abc", b"def"))
        assert result.usable
        assert result.path.read_bytes() == b"abcdef"

    def test_the_size_and_hash_describe_what_arrived(self, tmp_path):
        result = _run(tmp_path, _serves(b"abc", b"def"))
        assert result.byte_size == 6
        assert result.content_hash == hashlib.sha256(b"abcdef").hexdigest()

    def test_the_parent_directory_is_created(self, tmp_path):
        result = _run(tmp_path, _serves(b"x"))
        assert result.path.parent.is_dir()

    def test_no_staging_file_survives_a_success(self, tmp_path):
        _run(tmp_path, _serves(b"x"))
        assert list((tmp_path / "raw").glob("*.partial")) == []


class TestTheZeroByteGuard:
    def test_an_empty_body_is_not_usable(self, tmp_path):
        result = _run(tmp_path, _serves())
        assert not result.usable
        assert "no bytes" in result.detail

    def test_an_empty_body_leaves_no_file_behind(self, tmp_path):
        # A zero-byte file is indistinguishable from a good one by name, which is
        # the failure the catalogue refuses to record.
        _run(tmp_path, _serves())
        assert not (tmp_path / "raw" / "work.jpg").exists()
        assert list((tmp_path / "raw").glob("*.partial")) == []

    def test_a_body_of_only_empty_chunks_is_empty(self, tmp_path):
        result = _run(tmp_path, _serves(b"", b"", b""))
        assert not result.usable


class TestTheSizeCeiling:
    def test_a_body_over_the_ceiling_is_refused(self, tmp_path):
        result = _run(tmp_path, _serves(b"x" * 100), max_bytes=50)
        assert not result.usable
        assert "ceiling" in result.detail

    def test_an_oversized_body_leaves_nothing_on_disk(self, tmp_path):
        # Truncating would record a half-image nothing downstream could detect.
        _run(tmp_path, _serves(b"x" * 100), max_bytes=50)
        assert not (tmp_path / "raw" / "work.jpg").exists()
        assert list((tmp_path / "raw").glob("*.partial")) == []

    def test_a_body_exactly_at_the_ceiling_is_kept(self, tmp_path):
        result = _run(tmp_path, _serves(b"x" * 50), max_bytes=50)
        assert result.usable
        assert result.byte_size == 50

    def test_the_ceiling_is_enforced_across_chunks_not_per_chunk(self, tmp_path):
        # Ten small chunks over the limit must refuse just as one large one does.
        result = _run(tmp_path, _serves(*[b"x" * 10] * 10), max_bytes=50)
        assert not result.usable


class TestFailures:
    def test_a_transport_raising_mid_stream_is_a_recorded_failure(self, tmp_path):
        result = _run(tmp_path, _serves(b"abc", raises=RuntimeError("connection reset")))
        assert not result.usable
        assert "connection reset" in result.detail

    def test_a_partial_stream_leaves_no_file_at_the_destination(self, tmp_path):
        _run(tmp_path, _serves(b"abc", raises=RuntimeError("boom")))
        assert not (tmp_path / "raw" / "work.jpg").exists()

    def test_an_os_error_is_reported_rather_than_raised(self, tmp_path):
        result = _run(tmp_path, _serves(b"abc", raises=OSError("disk full")))
        assert not result.usable
        assert "disk full" in result.detail

    def test_a_failure_never_returns_a_hash(self, tmp_path):
        # A hash beside a failed fetch would be a hash of nothing in particular.
        result = _run(tmp_path, _serves(b"abc", raises=RuntimeError("boom")))
        assert result.content_hash is None
        assert result.byte_size == 0


class TestOverwriting:
    def test_a_refetch_replaces_the_previous_file(self, tmp_path):
        _run(tmp_path, _serves(b"old"))
        result = _run(tmp_path, _serves(b"newer bytes"))
        assert result.path.read_bytes() == b"newer bytes"

    def test_a_failed_refetch_leaves_the_previous_file_alone(self, tmp_path):
        # Staging is what buys this: the destination is only replaced once every
        # byte is present, so a failed retry does not cost the image already held.
        first = _run(tmp_path, _serves(b"good bytes"))
        _run(tmp_path, _serves(b"partial", raises=RuntimeError("boom")))
        assert first.path.read_bytes() == b"good bytes"


@pytest.mark.parametrize("chunks", [(b"a",), (b"a", b"b"), (b"a" * 1000,)])
def test_the_hash_always_matches_the_file_on_disk(tmp_path, chunks):
    # The hash is computed while streaming rather than by re-reading, so this is
    # the assertion that the two cannot drift.
    result = direct_fetch(
        "https://gallery.example.com/image.jpg",
        destination=tmp_path / "work.jpg",
        open_stream=_serves(*chunks),
        max_bytes=10_000,
    )
    assert result.content_hash == hashlib.sha256(result.path.read_bytes()).hexdigest()
