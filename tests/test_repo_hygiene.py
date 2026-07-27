"""No source file is silently excluded from version control.

This exists because of a real near-miss: the stock Python `.gitignore` carries an
unanchored `MANIFEST` rule for the setuptools artifact, and on a case-insensitive
filesystem (macOS) that also matched `curation/src/curation/manifest/` — the
theme-manifest builder, which is the only channel between the two planes. The
package existed on disk, imports succeeded, and tests passed; it was simply never
committed. A fresh clone, or the Pi, would have had a missing module.

The failure mode is invisible by construction, so it gets a mechanical guard
rather than vigilance.
"""

import pathlib
import subprocess

SOURCE_TREES = ("curation/src", "display/src", "tests")


def _ignored(paths: list[pathlib.Path]) -> list[str]:
    """Return the subset of `paths` that git would exclude."""
    if not paths:
        return []
    # `--no-index` is load-bearing. Without it git skips paths already in the
    # index, because ignore rules genuinely do not apply to tracked files — so
    # the check would pass for anything already committed and could never fail
    # on a bad rule once the damage was undone. We want the stronger invariant:
    # no ignore rule matches a source path, whatever the index currently holds.
    result = subprocess.run(
        ["git", "check-ignore", "--stdin", "--no-index"],
        input="\n".join(str(p) for p in paths),
        capture_output=True,
        text=True,
        check=False,
    )
    # Exit 0 = some paths ignored, 1 = none ignored. Anything else is a real error.
    assert result.returncode in (0, 1), f"git check-ignore failed: {result.stderr}"
    return [line for line in result.stdout.splitlines() if line]


def test_no_python_source_is_gitignored():
    candidates: list[pathlib.Path] = []
    for tree in SOURCE_TREES:
        root = pathlib.Path(tree)
        if root.exists():
            candidates.extend(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)

    assert candidates, "expected to find source files; has the layout moved?"
    ignored = _ignored(candidates)
    assert not ignored, "these source files would never be committed:\n" + "\n".join(ignored)


def test_no_package_directory_is_gitignored():
    """Directories matter separately: an ignored dir hides files that look fine alone."""
    candidates: list[pathlib.Path] = []
    for tree in SOURCE_TREES:
        root = pathlib.Path(tree)
        if root.exists():
            candidates.extend(p for p in root.rglob("*") if p.is_dir() and p.name != "__pycache__")

    ignored = _ignored(candidates)
    assert not ignored, "these package directories would never be committed:\n" + "\n".join(ignored)


def test_the_tv_token_is_not_tracked():
    """It was committed to a public repo once. Keep it from happening twice."""
    tracked = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True).stdout.splitlines()
    offenders = [p for p in tracked if pathlib.Path(p).name in {"token_file", ".env"}]
    assert not offenders, f"credential files must never be tracked: {offenders}"
