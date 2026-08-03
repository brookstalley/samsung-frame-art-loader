"""Cached previews: where they land, when they are not re-fetched, and failure.

The cache exists so review works when a museum does not, so the cases that
matter are the unhappy ones — a fetch that returns nothing, a second run over the
same instance, and a write interrupted partway.
"""

import pytest

from curation.services.errors import ServiceError
from curation.services.previews import PreviewCache, PreviewSettings

URL = "https://www.artic.edu/iiif/2/b272df73-a965-ac37-4172-be4e99483637/full/843,/0/default.jpg"
JPEG = b"\xff\xd8\xff\xe0 jpeg bytes"


@pytest.fixture
def cache_dir(tmp_path):
    return tmp_path / "previews"


def a_cache(tmp_path, cache_dir, fetch) -> PreviewCache:
    return PreviewCache(PreviewSettings(art_root=tmp_path, directory=cache_dir), fetch)


def test_a_fetched_preview_lands_inside_art_root_at_a_relative_path(tmp_path, cache_dir):
    """Every catalogue path is relative to ART_ROOT, so a preview has to be too."""
    path = a_cache(tmp_path, cache_dir, lambda url: JPEG).store(URL)

    assert path is not None
    assert not path.startswith("/")
    assert (tmp_path / path).read_bytes() == JPEG


def test_the_same_url_is_fetched_once_however_often_it_is_asked_for(tmp_path, cache_dir):
    """A work re-searched later finds its preview on disk rather than asking again.

    The two calls differ in nothing but the cache being warm, which is the point:
    an idempotence test that changed the inputs would be testing something else.
    """
    calls: list[str] = []

    def fetch(url: str) -> bytes:
        calls.append(url)
        return JPEG

    cache = a_cache(tmp_path, cache_dir, fetch)
    first = cache.store(URL)
    second = cache.store(URL)

    assert first == second
    assert calls == [URL], "the museum was asked exactly once"


def test_two_different_urls_do_not_collide(tmp_path, cache_dir):
    cache = a_cache(tmp_path, cache_dir, lambda url: url.encode())
    one = cache.store(URL)
    two = cache.store(URL.replace("b272df73", "ce38cdf4"))

    assert one != two
    assert (tmp_path / one).read_bytes() != (tmp_path / two).read_bytes()


def test_a_fetch_that_returns_nothing_reports_absence_rather_than_writing_an_empty_file(tmp_path, cache_dir):
    """An empty file would be indistinguishable from a cached preview on the next run."""
    path = a_cache(tmp_path, cache_dir, lambda url: None).store(URL)

    assert path is None
    assert not cache_dir.exists() or not any(cache_dir.iterdir())


def test_a_zero_byte_file_left_by_an_earlier_run_is_re_fetched(tmp_path, cache_dir):
    """A half-written file must not be treated as a valid cache hit forever."""
    calls: list[str] = []

    def fetch(url: str) -> bytes:
        calls.append(url)
        return JPEG

    cache = a_cache(tmp_path, cache_dir, fetch)
    # Cache it, then truncate it where it landed — which finds the real path
    # without reaching into how the name is derived.
    path = cache.store(URL)
    (tmp_path / path).write_bytes(b"")

    again = cache.store(URL)

    assert again == path
    assert (tmp_path / again).read_bytes() == JPEG
    assert len(calls) == 2, "the empty file was not mistaken for a cache hit"


def test_nothing_partial_is_left_behind_after_a_successful_write(tmp_path, cache_dir):
    """The staging file is renamed into place, not left beside the real one."""
    a_cache(tmp_path, cache_dir, lambda url: JPEG).store(URL)

    assert [path.name for path in cache_dir.iterdir() if path.name.endswith(".partial")] == []


def test_a_url_without_a_recognised_extension_still_gets_an_image_suffix(tmp_path, cache_dir):
    """The filename is ours; a suffix copied unchecked from a URL is a path component."""
    path = a_cache(tmp_path, cache_dir, lambda url: JPEG).store("https://example.org/image?id=7")

    assert path is not None
    assert path.endswith(".jpg")


def test_a_cache_outside_the_art_tree_is_refused_at_wiring_time(tmp_path):
    """Caught at startup naming both directories, not mid-run as a `relative_to` error."""
    with pytest.raises(ServiceError, match="must sit inside ART_ROOT"):
        PreviewSettings(art_root=tmp_path / "art", directory=tmp_path / "elsewhere")


def test_previews_are_kept_apart_from_thumbnails(settings):
    """Different lifecycles: a preview is disposable, a thumbnail belongs to a held work.

    A sweep that could not tell the two directories apart would delete the
    catalogue's own derived images along with the candidates'.
    """
    assert settings.previews_path != settings.thumbnails_path
    assert settings.previews_path.is_relative_to(settings.art_root)
