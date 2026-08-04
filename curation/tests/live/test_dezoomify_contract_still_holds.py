"""The recorded dezoomify findings, as a test rather than as prose.

`dezoomify-cli-findings.md` is a snapshot of a live probe, and the wrapper is
written entirely against it: which flags exist, that exit codes classify nothing,
that the saved-file announcement goes to stderr, and that the output *extension*
decides the encoder. A document nobody re-runs quietly stops describing the tool.

**This suite exists because of a specific failure that no fake could catch.** The
stand-ins in `tests/unit/test_acquisition_dezoomify.py` are shell scripts that
write to their last argument whatever it is called, so they are blind to anything
the real binary decides from the filename. A staging path ending `.partial` passed
every one of them and fails outright against the real tool — every tiled fetch in
the deployment would have failed against a green suite. The lesson generalises:
where behaviour is the *binary's* rather than the wrapper's, only the binary can
be the witness.

**Deselected by default**, on its own marker beside `live_museum`, for the same
two reasons: it costs nothing — the Art Institute's API is open and these fetches
are small — but it needs the network *and* the binary, and a suite whose job is to
be green cannot depend on either.

    uv run pytest -m live_binary
"""

import shutil

import pytest

from curation.acquisition.dezoomify import TileOutcome, tile_fetch

pytestmark = pytest.mark.live_binary

#: A small work at the Art Institute, asked for at a low zoom level so the probe
#: costs a handful of tiles rather than a gigapixel walk.
INFO_JSON = "https://www.artic.edu/iiif/2/f70f3419-2911-ace8-469e-a997aa001b0a/info.json"
USER_AGENT = "samsung-frame-art-loader (contract test)"


@pytest.fixture(autouse=True)
def _needs_the_binary():
    if shutil.which("dezoomify-rs") is None:
        pytest.skip("dezoomify-rs is not installed")


def _fetch(tmp_path, name="work.jpg", **kwargs):
    return tile_fetch(
        INFO_JSON,
        destination=tmp_path / "raw" / name,
        tile_cache=tmp_path / "tiles",
        binary="dezoomify-rs",
        user_agent=USER_AGENT,
        max_width=900,
        max_height=900,
        timeout_seconds=180,
        **kwargs,
    )


def test_a_real_tiled_fetch_produces_a_readable_image(tmp_path):
    from curation.services.imaging import measure

    result = _fetch(tmp_path)

    assert result.outcome is TileOutcome.COMPLETE
    assert result.byte_size > 0
    # The property the whole staging arrangement turns on: whatever the wrapper
    # names the staged file, the bytes the binary writes must be an image this
    # process can open and measure. A path whose extension the binary cannot
    # classify fails here and nowhere else.
    width, height = measure(result.path)
    assert width > 0 and height > 0


def test_the_staged_name_keeps_an_extension_the_binary_can_encode_to(tmp_path):
    # Asserts the shape of the name the wrapper chose, against the real tool.
    # `<stem>.partial<suffix>` keeps `.jpg` last; `<name>.partial` does not, and
    # the binary refuses it with "was not recognized as an image format".
    result = _fetch(tmp_path)

    assert result.path is not None
    assert result.path.suffix == ".jpg"
    assert ".partial" in result.path.name
    assert result.path.exists()


def test_the_tile_cache_is_populated_when_the_directory_exists(tmp_path):
    # The recorded behaviour the wrapper's mkdir defends: given a directory the
    # binary caches into it, and given none it warns per tile and caches nothing.
    _fetch(tmp_path)

    assert any((tmp_path / "tiles").iterdir())
