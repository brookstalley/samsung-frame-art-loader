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

#: Every tree whose absence from a fresh clone would matter. `curation/tests`
#: carries almost all of the curation plane's coverage, and a tree the guard does
#: not walk is exactly the tree this guard was built for: the suite stays green
#: locally while the clone and the Pi quietly lose it.
SOURCE_TREES = ("curation/src", "curation/tests", "display/src", "tests")


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

    assert candidates, "expected to find package directories; has the layout moved?"
    ignored = _ignored(candidates)
    assert not ignored, "these package directories would never be committed:\n" + "\n".join(ignored)


def test_the_tv_token_is_not_tracked():
    """It was committed to a public repo once. Keep it from happening twice."""
    tracked = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True).stdout.splitlines()
    offenders = [p for p in tracked if pathlib.Path(p).name in {"token_file", ".env"}]
    assert not offenders, f"credential files must never be tracked: {offenders}"


#: The loader unit, whose environment dependency is otherwise invisible.
LOADER_UNIT = pathlib.Path("deploy/samsung-frame-art-loader.service")


def _unit_directives() -> dict[str, list[str]]:
    """Map each directive in the loader unit to every value assigned to it."""
    directives: dict[str, list[str]] = {}
    for raw in LOADER_UNIT.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("["):
            continue
        key, _, value = line.partition("=")
        directives.setdefault(key.strip(), []).append(value.strip())
    return directives


def test_the_loader_unit_declares_its_environment_file():
    """`config.py` raises at import without five deployment values, and the unit is
    what has to supply them.

    Declared without a `-` prefix on purpose: systemd treats a missing
    `EnvironmentFile=` as fatal and names the path it wanted, which is a far better
    failure than the import-time crash that a silently absent file produces.
    Prefixing it with `-` would restore exactly the silence this guard exists to
    prevent, so the assertion covers the prefix and not merely the directive.
    """
    values = _unit_directives().get("EnvironmentFile", [])
    assert values, "the loader unit must declare EnvironmentFile= — config.py requires five variables at import"
    assert not any(v.startswith("-") for v in values), f"EnvironmentFile= must not be optional (`-` prefix): {values}"


def test_the_loader_unit_cannot_silently_stop_retrying():
    """systemd's stock rate limit gives up after 5 starts in 10s.

    With `Restart=always` and no override, an import-time failure burns that whole
    allowance in about half a second and parks the unit in `failed` — a dark
    television and a service that stopped trying, which is the opposite of the
    product's requirement that an unattended failure be visible without inspecting
    the wall. Retrying on a real interval, forever, keeps the fault legible in the
    journal and in `systemctl status`.
    """
    directives = _unit_directives()
    assert directives.get("Restart") == ["always"], "the loader is meant to come back from anything"
    assert directives.get("StartLimitIntervalSec") == [
        "0"
    ], "start rate limiting must be disabled, or a crash loop ends in a silent permanent `failed`"

    restart_sec = directives.get("RestartSec", [])
    assert restart_sec, "RestartSec= must be set; the 100ms default is what exhausts the burst allowance"
    assert int(restart_sec[0]) >= 5, f"RestartSec= must leave a real gap between attempts, got {restart_sec[0]}"
