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


# -- the "never raises" contract, enforced rather than asserted in a docstring ---
#
# Every branch below returns `None` instead of propagating. That is the whole
# point of the module: a preview is a review-card nicety, and a run that found
# its images must not die because one thumbnail could not be written. Each test
# names the exception a real deployment would produce.


def test_a_provider_that_raises_something_other_than_a_transport_error_is_absorbed(tmp_path, cache_dir):
    """`httpx.InvalidURL` is not an `HTTPError`, so the seam's `None` is not enough.

    A provider that raises past its own contract would otherwise reach the
    run-level handler and fail a whole run over a thumbnail.
    """

    def fetch(url: str) -> bytes:
        raise ValueError("not a valid URL")

    assert a_cache(tmp_path, cache_dir, fetch).store(URL) is None


def test_a_provider_raising_an_oserror_is_reported_as_the_provider_not_the_cache(tmp_path, cache_dir, caplog):
    """The two `OSError` sources are different diagnoses and must read differently.

    One handler over both would send whoever reads the log looking at their disk
    when the fault was the network.
    """

    def fetch(url: str) -> bytes:
        raise OSError("connection reset by peer")

    with caplog.at_level("INFO"):
        assert a_cache(tmp_path, cache_dir, fetch).store(URL) is None

    reasons = [record.reason for record in caplog.records if hasattr(record, "reason")]
    assert any("the provider raised" in reason for reason in reasons)
    assert not any("the cache could not be read" in reason for reason in reasons)


def test_an_unreadable_cache_directory_degrades_the_card_rather_than_failing_the_run(tmp_path, cache_dir, monkeypatch):
    """A stat that raises is this machine's problem, and it is reported as one."""

    def explode(self):
        raise OSError("permission denied")

    monkeypatch.setattr("pathlib.Path.exists", explode)

    assert a_cache(tmp_path, cache_dir, lambda url: JPEG).store(URL) is None


def test_bytes_that_cannot_be_written_degrade_the_card_rather_than_failing_the_run(tmp_path, cache_dir, monkeypatch):
    """A full or read-only disk is a real operational condition, not a run-ender.

    The run has already done the expensive part — it found the images — so
    losing it here would throw away everything for the sake of a thumbnail.
    """

    def explode(self, _data):
        raise OSError("no space left on device")

    monkeypatch.setattr("pathlib.Path.write_bytes", explode)

    assert a_cache(tmp_path, cache_dir, lambda url: JPEG).store(URL) is None


def test_a_publish_that_fails_after_writing_leaves_no_partial_behind(tmp_path, cache_dir, monkeypatch):
    """The staging file is reclaimed, because nothing else ever will.

    Its name is derived from the destination, so it is never read — nothing
    looks for `.partial` — and no sweep collects it. The failure this handles is
    a full disk, which is the condition under which stranded bytes cost the most,
    and the device is the one the operational spec names as the top risk.

    Distinct from the write failing outright: there the staging file was never
    created, so the leak needs a publish that gets the bytes down and then
    cannot rename them.
    """

    def explode(self, _target):
        raise OSError("no space left on device")

    monkeypatch.setattr("pathlib.Path.replace", explode)
    cache = a_cache(tmp_path, cache_dir, lambda url: JPEG)

    assert cache.store(URL) is None
    assert list((tmp_path / cache_dir).glob("*.partial")) == []


def test_a_run_completes_when_no_preview_can_be_written(services, settings, engine, monkeypatch):
    """The consequence, through the runner that actually joins the two.

    `store` returning `None` is only worth anything if the caller carries on, and
    the caller is `DiscoveryRunner._record_instance` — so this drives a whole run
    rather than calling the engine and the cache side by side, which would prove
    each half works and nothing about the seam between them.
    """
    from fakes import FakeImageSearch, a_work, an_image

    from curation.discovery.engine import WorkList
    from curation.discovery.phase_two import PhaseTwoEngine
    from curation.persistence.discovery_records import InitiatedBy, ResolutionStatus, RunStatus
    from curation.services.runner import DiscoveryRunner

    def explode(self, _data):
        raise OSError("no space left on device")

    monkeypatch.setattr("pathlib.Path.write_bytes", explode)
    museum = FakeImageSearch(holdings={"The Elephants": (an_image("The Elephants"),)})
    engine.result = WorkList(works=(a_work("The Elephants"),))
    runner = DiscoveryRunner(
        services.discovery,
        engine,
        settings.discovery_settings,
        images=PhaseTwoEngine(museum, box=settings.tv_artwork_box),
        previews=PreviewCache(
            PreviewSettings(art_root=settings.art_root, directory=settings.previews_path),
            museum.fetch_preview,
        ),
        spawn=lambda work: work(),
    )

    run_id = runner.start(intent_text="elephants", initiated_by=InitiatedBy.MCP_CLIENT).id

    assert services.discovery.get_run(run_id).status is RunStatus.COMPLETED
    work = services.discovery.list_candidate_works(run_id)[0]
    assert work.resolution_status is ResolutionStatus.RESOLVED
    image = services.discovery.list_candidate_images(work.id)[0]
    assert image.is_selected is True
    assert image.preview_path is None, "nothing was written, and the row says so"
    # Asserted on the stored row rather than on the fake's input, so this checks
    # what a review card would actually read back.
    assert image.preview_url, "the card falls back to the source URL"


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
