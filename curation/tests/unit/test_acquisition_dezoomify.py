"""The dezoomify wrapper, against the contract the real binary was observed to have.

The fakes here reproduce behaviours recorded from `dezoomify-rs 2.18.1`: a
zero-byte file left behind on total failure, a usable image left behind on a
partial one, both under exit code 1, and the saved-file announcement on stderr.
A fake that returned tidy exit codes would test a binary this product does not
have.
"""

import json
import stat
from pathlib import Path

import pytest

from curation.acquisition.dezoomify import (
    DezoomifyUnavailable,
    TileOutcome,
    reclaim_tile_cache,
    tile_fetch,
)

ARGV_DUMP = "argv.json"


def _fake_binary(tmp_path: Path, body: str) -> Path:
    """A stand-in on disk, because the wrapper resolves and executes a real file."""
    script = tmp_path / "fake-dezoomify"
    script.write_text(
        "#!/bin/sh\n"
        # Every invocation records exactly what it was handed, which is what the
        # security assertion below reads. Written as one JSON array element per
        # argument so an argument containing spaces or `;` cannot be confused
        # with two arguments.
        f'python3 -c "import json,sys;'
        f"open(r'{tmp_path / ARGV_DUMP}','w').write(json.dumps(sys.argv[1:]))\" \"$@\"\n" + body
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return script


def _passed_argv(tmp_path: Path) -> list[str]:
    return json.loads((tmp_path / ARGV_DUMP).read_text())


def _run(tmp_path: Path, script: Path, url: str = "https://museum.example.com/info.json", **kwargs):
    defaults = {
        "destination": tmp_path / "out" / "work.jpg",
        "tile_cache": tmp_path / "tiles",
        "binary": str(script),
        "user_agent": "samsung-frame-art-loader/1.0 (probe)",
        "max_width": 8192,
        "max_height": 8192,
        "timeout_seconds": 30,
    }
    return tile_fetch(url, **{**defaults, **kwargs})


# The last argv element is the destination and the one before it is the URL.
SAVES_IMAGE = 'printf "x%.0s" $(seq 1 100) > "$(eval echo \\${$#})"\nexit 0\n'
ZERO_BYTE_THEN_FAIL = ': > "$(eval echo \\${$#})"\necho "[ERROR] Could not get any tile for the image." >&2\nexit 1\n'
PARTIAL = (
    'printf "x%.0s" $(seq 1 500) > "$(eval echo \\${$#})"\n'
    "echo \"[WARN ] Only 120 tiles out of 238 could be downloaded. The resulting image was still created in 'x'.\" >&2\n"
    "exit 1\n"
)
WRITES_NOTHING = 'echo "[WARN ] Reached end of input. Exiting..." >&2\nexit 0\n'


class TestSecurityOfTheInvocation:
    """The plan's bar: assert on the argv passed, not on the absence of a crash."""

    def test_a_url_with_shell_metacharacters_arrives_as_one_inert_element(self, tmp_path):
        hostile = "https://museum.example.com/a;touch OWNED;$(whoami)/info.json"
        script = _fake_binary(tmp_path, SAVES_IMAGE)

        _run(tmp_path, script, url=hostile)

        argv = _passed_argv(tmp_path)
        # One element, byte-for-byte — not split on the space or the semicolon.
        assert hostile in argv
        assert argv.count(hostile) == 1
        assert not (tmp_path / "OWNED").exists()

    def test_the_url_is_never_concatenated_into_another_argument(self, tmp_path):
        url = "https://museum.example.com/info.json"
        script = _fake_binary(tmp_path, SAVES_IMAGE)

        _run(tmp_path, script, url=url)

        argv = _passed_argv(tmp_path)
        # A URL glued to a flag would still "contain" the URL, so the check is
        # that no *other* element carries it.
        assert [arg for arg in argv if url in arg] == [url]

    def test_the_child_is_given_no_stdin_to_prompt_on(self, tmp_path, monkeypatch):
        # White-box on purpose, and for the same reason the argv assertion above
        # is: the property that matters is what the child is handed. Under pytest
        # the parent's own stdin is already closed, so a fake that tries to read
        # returns immediately whether or not this is wired correctly — a test
        # shaped that way passes with `stdin=None` and proves nothing.
        import subprocess as sp

        seen = {}
        real = sp.run

        def capture(*args, **kwargs):
            seen.update(kwargs)
            return real(*args, **kwargs)

        monkeypatch.setattr(sp, "run", capture)
        _run(tmp_path, _fake_binary(tmp_path, SAVES_IMAGE))

        assert seen["stdin"] is sp.DEVNULL

    def test_an_image_index_is_always_supplied(self, tmp_path):
        # Omitting it is what sends the binary to an interactive prompt when a
        # source offers several images.
        script = _fake_binary(tmp_path, SAVES_IMAGE)
        _run(tmp_path, script)
        assert "--image-index" in _passed_argv(tmp_path)


class TestClassification:
    def test_a_saved_image_is_complete(self, tmp_path):
        script = _fake_binary(tmp_path, SAVES_IMAGE)
        result = _run(tmp_path, script)
        assert result.outcome is TileOutcome.COMPLETE
        assert result.usable
        assert result.byte_size == 100

    def test_exit_one_with_a_real_image_is_partial_not_failed(self, tmp_path):
        # The observed shape: most tiles arrived, the image is usable, exit is 1.
        script = _fake_binary(tmp_path, PARTIAL)
        result = _run(tmp_path, script)
        assert result.outcome is TileOutcome.PARTIAL
        assert result.usable
        assert (result.tiles_fetched, result.tiles_expected) == (120, 238)

    def test_a_partial_image_is_kept_on_disk(self, tmp_path):
        # The 2024 code deleted this file, which made `partial_tiles`
        # unrecordable in practice.
        script = _fake_binary(tmp_path, PARTIAL)
        result = _run(tmp_path, script)
        assert result.path is not None
        assert result.path.exists()
        assert result.path.stat().st_size == 500

    def test_exit_one_with_a_zero_byte_file_is_failed(self, tmp_path):
        script = _fake_binary(tmp_path, ZERO_BYTE_THEN_FAIL)
        result = _run(tmp_path, script)
        assert result.outcome is TileOutcome.FAILED
        assert not result.usable

    def test_the_zero_byte_file_is_removed_not_left_to_be_found(self, tmp_path):
        script = _fake_binary(tmp_path, ZERO_BYTE_THEN_FAIL)
        result = _run(tmp_path, script)
        assert result.path is None
        assert not (tmp_path / "out" / "work.jpg").exists()

    def test_exit_zero_with_no_file_is_failed(self, tmp_path):
        # The trap the probe found: reading no input and writing nothing exits 0.
        script = _fake_binary(tmp_path, WRITES_NOTHING)
        result = _run(tmp_path, script)
        assert result.outcome is TileOutcome.FAILED

    def test_a_failure_carries_the_binarys_own_reason(self, tmp_path):
        script = _fake_binary(tmp_path, ZERO_BYTE_THEN_FAIL)
        result = _run(tmp_path, script)
        assert "Could not get any tile" in result.detail

    def test_an_unrecognised_failure_message_is_called_partial_not_complete(self, tmp_path):
        # An image, a non-zero exit, and no tile counts to read — the shape a
        # reworded message in a later release produces. Complete is the claim
        # that would be silently wrong, recording a gappy image as `ok` and
        # reclaiming the tiles a retry would have used.
        rephrased = _fake_binary(
            tmp_path,
            'printf "x%.0s" $(seq 1 100) > "$(eval echo \\${$#})"\n'
            'echo "[WARN ] 120/238 tiles retrieved; output written with gaps." >&2\n'
            "exit 1\n",
        )
        result = _run(tmp_path, rephrased)

        assert result.outcome is TileOutcome.PARTIAL
        assert result.usable
        assert (result.tiles_fetched, result.tiles_expected) == (None, None)
        assert "does not recognise" in result.detail

    def test_a_timeout_is_a_failure_and_says_so(self, tmp_path):
        script = _fake_binary(tmp_path, "sleep 5\nexit 0\n")
        result = _run(tmp_path, script, timeout_seconds=1)
        assert result.outcome is TileOutcome.FAILED
        assert "did not finish" in result.detail


class TestTheTileCache:
    def test_the_cache_directory_is_created_before_invoking(self, tmp_path):
        # Observed: given a missing directory the binary warns per tile and
        # caches nothing, losing the retry this directory exists for.
        cache = tmp_path / "tiles" / "nested"
        script = _fake_binary(tmp_path, SAVES_IMAGE)
        _run(tmp_path, script, tile_cache=cache)
        assert cache.is_dir()

    def test_the_cache_path_is_passed_to_the_binary(self, tmp_path):
        cache = tmp_path / "tiles"
        script = _fake_binary(tmp_path, SAVES_IMAGE)
        _run(tmp_path, script, tile_cache=cache)
        argv = _passed_argv(tmp_path)
        assert argv[argv.index("--tile-cache") + 1] == str(cache)

    def test_reclaiming_removes_the_tree(self, tmp_path):
        cache = tmp_path / "tiles"
        cache.mkdir()
        (cache / "a-tile.png").write_bytes(b"x")
        reclaim_tile_cache(cache)
        assert not cache.exists()

    def test_reclaiming_a_cache_that_is_already_gone_is_not_an_error(self, tmp_path):
        reclaim_tile_cache(tmp_path / "never-existed")


class TestDestination:
    def test_the_destination_is_never_touched(self, tmp_path):
        # A held image stands at the destination. Nothing here may remove it or
        # write over it: a retry that fails must cost the work nothing, and
        # promotion is the caller's step.
        destination = tmp_path / "out" / "work.jpg"
        destination.parent.mkdir(parents=True)
        destination.write_bytes(b"the image the work is displaying")

        result = _run(tmp_path, _fake_binary(tmp_path, SAVES_IMAGE), destination=destination)

        assert result.outcome is TileOutcome.COMPLETE
        assert result.path != destination
        assert destination.read_bytes() == b"the image the work is displaying"

    def test_a_failed_retry_leaves_the_held_image_alone(self, tmp_path):
        destination = tmp_path / "out" / "work.jpg"
        destination.parent.mkdir(parents=True)
        destination.write_bytes(b"the image the work is displaying")

        result = _run(tmp_path, _fake_binary(tmp_path, ZERO_BYTE_THEN_FAIL), destination=destination)

        assert result.outcome is TileOutcome.FAILED
        assert destination.read_bytes() == b"the image the work is displaying"

    def test_a_stale_staged_file_is_cleared_so_a_retry_is_not_refused(self, tmp_path):
        # The stand-in refuses to overwrite, which is what the real binary does.
        # A fake that overwrote happily would pass with the clearing removed.
        destination = tmp_path / "out" / "work.jpg"
        destination.parent.mkdir(parents=True)
        (destination.parent / "work.jpg.partial").write_bytes(b"debris from an interrupted attempt")
        refuses_to_overwrite = _fake_binary(
            tmp_path,
            'if [ -e "$(eval echo \\${$#})" ]; then\n'
            '  echo "[ERROR] Destination file already exists" >&2\n'
            "  exit 1\n"
            "fi\n" + SAVES_IMAGE,
        )

        result = _run(tmp_path, refuses_to_overwrite, destination=destination)

        assert result.outcome is TileOutcome.COMPLETE
        assert result.byte_size == 100


class TestDeploymentFailures:
    def test_a_missing_binary_is_not_reported_as_a_fetch_failure(self, tmp_path):
        # No source is at fault, so recording a failed fetch against the URL
        # would blame a museum for a deployment problem.
        with pytest.raises(DezoomifyUnavailable, match="not on PATH"):
            _run(tmp_path, Path(tmp_path / "does-not-exist"))
