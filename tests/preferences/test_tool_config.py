"""The two planes are excluded from the root's tools by two settings that must agree.

The root project configures both black and ruff, and both must stop at the plane
boundary — each plane owns its own interpreter, its own lock, and its own tool
config. The boundary is therefore drawn twice, in two syntaxes: ruff takes a list
of paths, black takes a **regex** against the root-relative path.

Nothing made them agree. On 2026-08-02 they did not: ruff excluded both planes and
black excluded neither, so `black .` at the root walked 103 files instead of 18 and
formatted the curation plane under `py312` rather than the `py314` that plane
declares. It produced byte-identical output, because the two targets happen not to
differ for this code — which is exactly why a year could pass before anyone noticed
the split had stopped holding for formatting while it still held for lint.

That is this repo's stated trigger for a mechanical guard rather than vigilance
(`tests/test_repo_hygiene.py`, opening docstring). The `.gitignore` half of the same
sweep needed no test because an ignore rule enforces itself; two hand-mirrored lists
in two syntaxes do not.

**What this does not cover:** ruff's own matching semantics. That `extend-exclude =
["display"]` excludes the future `display/` package and *not* the legacy root module
`display.py` was verified by hand on 2026-08-02 (`ruff check --show-files` lists
`display.py`; `black --verbose` walks it) and is asserted here only on the black
side, where it costs no subprocess.
"""

import pathlib
import re
import tomllib

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
ROOT_PYPROJECT = REPOSITORY_ROOT / "pyproject.toml"


def _config() -> dict:
    return tomllib.loads(ROOT_PYPROJECT.read_text(encoding="utf-8"))


def _ruff_planes() -> list[str]:
    planes = _config()["tool"]["ruff"]["extend-exclude"]
    assert planes, "the root ruff config excludes no plane; has the boundary moved?"
    return planes


def _black_excludes() -> re.Pattern:
    pattern = _config()["tool"]["black"]["extend-exclude"]
    assert pattern, "the root black config excludes nothing, so it formats both planes"
    # Black normalises to a root-relative path with a leading slash and `search`es
    # the pattern against it. Mirrored here rather than reimplemented: a `match`
    # would pass on patterns black itself would not honour.
    return re.compile(pattern)


def _excluded_by_black(path: str) -> bool:
    return _black_excludes().search(path) is not None


def test_black_excludes_exactly_the_planes_ruff_excludes():
    """The two settings name the same set, tested by behaviour rather than by string.

    Comparing the regex source against the list would only ever check that someone
    edited both lines; asking the regex what it actually matches checks that the two
    mean the same thing.
    """
    planes = _ruff_planes()
    # Every real top-level directory is a candidate, so a plane added to one
    # setting and not the other shows up here rather than in six months.
    present = {p.name for p in REPOSITORY_ROOT.iterdir() if p.is_dir() and not p.name.startswith(".")}
    candidates = sorted(set(planes) | present)

    disagree = [name for name in candidates if _excluded_by_black(f"/{name}/anything.py") != (name in planes)]
    assert not disagree, (
        "black and ruff disagree about which directories are outside the root project: "
        f"{disagree}. ruff excludes {sorted(planes)}; black excludes "
        f"{sorted(n for n in candidates if _excluded_by_black(f'/{n}/anything.py'))}. "
        "Both settings must name the same planes — they are the same boundary."
    )


def test_a_root_module_sharing_a_plane_name_is_still_formatted():
    """`display.py` is a 2024 module; `display/` will be a plane. Only the plane goes.

    A pattern written without the trailing slash would exclude the module too, and
    silently drop a file that both tools are supposed to hold to the strict set —
    the kind of near-miss that leaves the suite green.
    """
    for plane in _ruff_planes():
        assert not _excluded_by_black(f"/{plane}.py"), (
            f"the black exclusion swallows the root module `{plane}.py` as well as the "
            f"`{plane}/` plane. It needs the trailing slash."
        )
    assert not _excluded_by_black("/config.py"), "root modules must stay under the root tool config"
