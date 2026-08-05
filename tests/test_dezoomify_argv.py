"""dezoomify is invoked with an argv list, so remote text cannot become a command.

`get_dezoomify_file` is handed a URL and a Referer built out of a museum API's
JSON response — `metadata["config"]["iiif_url"]` and `metadata["data"]["image_id"]`
— not out of anything the operator typed. Under `shell=True` a quote plus `;` or
`$(...)` anywhere in that document would run as a command on the loader host, and
because the response is cached to `api-cache/` and replayed, one hostile document
would persist across every later acquisition. The surrounding code already
sanitises the *filename* it derives from the same document, which is what made the
unsanitised URL easy to miss.

The assertion is on the argv actually passed, not on the absence of a crash: a
metacharacter-laden URL that never reaches a shell also never misbehaves, so
"nothing happened" is not evidence. Asserting the call receives a *list* whose
elements are the untouched strings is what distinguishes the fix from the defect —
under the old code the first argument was a single interpolated string, and every
substring check below would have passed against it.

The third-party imports are stubbed rather than installed. Reaching this function
otherwise means the OpenCV and scikit-image stack in the dev group, hundreds of
megabytes for a plane that retires at Chunk 20, and none of it participates in
building an argv list.
"""

import asyncio
import subprocess
import sys
from unittest.mock import MagicMock

import pytest

# `config` reads the environment at import and raises if it is unset, so it has to
# be resolved under a controlled environment before anything importing it. Reusing
# the neighbouring harness rather than restating its variables keeps one copy of
# that list: a second would drift the first time `config` grows a required value.
from test_config import load_config

#: Everything `image_utils` reaches on the way in, including through `ai` and
#: `source_utils`. These are the Pi's image-processing stack; none is installed in
#: the root dev group, which carries only pytest, ruff and black.
_STUBBED = (
    "cv2",
    "numpy",
    "requests",
    "colour",
    "PIL",
    "skimage",
    "skimage.transform",
    "openai",
    "bs4",
)

#: A URL shaped like the ARTIC `info.json` the real path builds, carrying the
#: metacharacters that matter: a quote to close the interpolation, `;` to start a
#: new command, and `$(...)` for the substitution form that needs no quote at all.
HOSTILE_URL = 'https://example.org/iiif/2/x"; touch /tmp/pwned; echo "$(id)/info.json'


@pytest.fixture
def image_utils(monkeypatch):
    """Import `image_utils` with its absent third-party stack stubbed out."""
    load_config(monkeypatch)
    for name in _STUBBED:
        monkeypatch.setitem(sys.modules, name, MagicMock())
    monkeypatch.delitem(sys.modules, "image_utils", raising=False)
    import image_utils as module

    return module


@pytest.fixture
def captured_argv(monkeypatch, image_utils):
    """Capture the arguments dezoomify would have been launched with."""
    seen = {}

    class FakePopen:
        def __init__(self, args, **kwargs):
            seen["args"] = args
            seen["kwargs"] = kwargs
            # Non-zero: the success branch parses a filename out of stdout, which
            # has nothing to do with what this file asserts.
            self.returncode = 1

        def wait(self):
            return self.returncode

        def communicate(self):
            return b"", b""

    monkeypatch.setattr(subprocess, "Popen", FakePopen)
    return seen


def _argv(captured_argv):
    """The captured arguments, having established they are argv at all.

    Every assertion below goes through here on purpose. A shell string contains
    the URL just as truly as a list element equals it, so `in` and `.count()`
    silently pass against the defect — this is the check that does not.
    """
    args = captured_argv["args"]
    assert isinstance(args, list), "a shell string, not an argv list — the injection is back"
    return args


def _run(image_utils, tmp_path, **kwargs):
    return asyncio.run(
        image_utils.get_dezoomify_file(
            url=HOSTILE_URL,
            destination_dir=str(tmp_path),
            destination_fullpath="",
            **kwargs,
        )
    )


def test_the_binary_is_launched_without_a_shell(image_utils, captured_argv, tmp_path):
    _run(image_utils, tmp_path)

    args = _argv(captured_argv)
    assert not captured_argv["kwargs"].get("shell"), "shell=True re-enables the injection"
    assert args[0] == image_utils.dezoomify_rs_path


def test_a_hostile_url_arrives_as_one_inert_element(image_utils, captured_argv, tmp_path):
    _run(image_utils, tmp_path)

    args = _argv(captured_argv)
    assert args.count(HOSTILE_URL) == 1, "the URL was split, quoted or rewritten"
    # Nothing else in the call carries a fragment of it: had the metacharacters
    # been interpreted, the payload would appear as elements of its own.
    others = [a for a in args if a != HOSTILE_URL]
    assert not [a for a in others if "touch" in a or "$(" in a]


def test_a_hostile_referer_arrives_as_one_inert_element(image_utils, captured_argv, tmp_path):
    _run(image_utils, tmp_path, http_referer=HOSTILE_URL)

    args = _argv(captured_argv)
    # The real ARTIC call passes the same `info.json` URL as both URL and Referer,
    # so the header value is remote text on exactly the same footing.
    assert args.count(f"Referer: {HOSTILE_URL}") == 1
    assert args[args.index(f"Referer: {HOSTILE_URL}") - 1] == "--header"


def test_a_url_the_binary_would_read_as_a_flag_is_refused(image_utils, captured_argv, tmp_path):
    """Argument injection: a different bug class from the shell injection above.

    The ARTIC path builds its URL out of two remote fields —
    `f"{metadata['config']['iiif_url']}/{image_id}/info.json"` — so a document
    supplying an `iiif_url` of `--tile-cache=/somewhere` yields a whole URL that
    `dezoomify-rs` parses as an option rather than as the thing to fetch. That
    silently overrides one of the settings pinned in `dezoomify_params`, which is a
    remote document reconfiguring the fetch on the loader host.

    Asserting the process was never launched, not merely that the return was falsey:
    a refusal that still ran the binary would have refused nothing.
    """
    hostile = asyncio.run(
        image_utils.get_dezoomify_file(
            url="--tile-cache=/tmp/attacker",
            destination_dir=str(tmp_path),
            destination_fullpath="",
        )
    )

    assert hostile == (False, None)
    assert "args" not in captured_argv, "the binary was launched with a flag as its URL"


def test_a_non_http_url_never_reaches_the_binary(image_utils, captured_argv, tmp_path):
    # Every caller reaches this with a museum URL, but nothing on the way in checks
    # that. `file://` is the case that matters: the binary would be pointed at the
    # loader host's own disk by a remote document.
    assert asyncio.run(
        image_utils.get_dezoomify_file(
            url="file:///etc/passwd",
            destination_dir=str(tmp_path),
            destination_fullpath="",
        )
    ) == (False, None)
    assert "args" not in captured_argv


def test_the_url_is_fenced_off_from_the_options(image_utils, captured_argv, tmp_path):
    """The end-of-options separator is present, immediately before the positionals.

    Structural rather than behavioural on purpose, and the reason is worth stating:
    the scheme check tested above means no URL that survives to here can begin with
    `-`, so there is no input that makes this separator change the outcome. It is the
    guard that holds if that check is ever loosened, and a guard nothing asserts is
    one a later reader deletes as dead code. Deleting `argv.append("--")` fails this.
    """
    _run(image_utils, tmp_path, out_file="Artist - Title.jpg")

    args = _argv(captured_argv)
    assert "--" in args, "the end-of-options separator is gone"
    assert args[args.index(HOSTILE_URL) - 1] == "--", "the separator no longer fences the URL"
    # Everything after it is positional: the URL, then the output filename.
    assert args[args.index("--") + 1 :] == [HOSTILE_URL, str(tmp_path / "Artist - Title.jpg")]


def test_the_output_filename_is_its_own_element(image_utils, captured_argv, tmp_path):
    # `out_file` is derived from the same remote document as the URL. It is
    # sanitised upstream, but the argv form is what makes that belt-and-braces
    # rather than the only thing standing between a title and a shell.
    _run(image_utils, tmp_path, out_file="Artist - Title.jpg")

    args = _argv(captured_argv)
    assert args[-1] == str(tmp_path / "Artist - Title.jpg")
    assert args[-2] == HOSTILE_URL
