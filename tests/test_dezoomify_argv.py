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


def test_the_output_filename_is_its_own_element(image_utils, captured_argv, tmp_path):
    # `out_file` is derived from the same remote document as the URL. It is
    # sanitised upstream, but the argv form is what makes that belt-and-braces
    # rather than the only thing standing between a title and a shell.
    _run(image_utils, tmp_path, out_file="Artist - Title.jpg")

    args = _argv(captured_argv)
    assert args[-1] == str(tmp_path / "Artist - Title.jpg")
    assert args[-2] == HOSTILE_URL
