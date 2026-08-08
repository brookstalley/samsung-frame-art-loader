"""What the default-suite CI leg may skip collecting, and what it may not.

The curation plane's CI invocation is not the documented local one. Locally
`uv run pytest` is right: the opt-in markers are deselected by `addopts` and
whichever optional groups happen to be installed import cleanly. In CI a default
`uv sync` installs none of them, so the modules that `importorskip` their group
land skips in the report — and `assert_tests_ran.py` reads any skip as a
provisioning failure and fails the job. A green suite, a red leg, and nothing
actually wrong: the alarm that cries wolf until nobody reads it.

So the leg names those directories with `--ignore`. **That list is the kind of
thing that goes stale silently in both directions, which is why it is derived
here rather than trusted.**

- *Too few* and CI goes red on a passing suite, and the failure points at a
  provisioning problem that does not exist.
- *Too many* and coverage shrinks with nothing to show for it. A directory
  ignored after its `importorskip` was removed stops running in CI entirely,
  reports nothing, and looks exactly like a directory that is passing.

The second is the one worth a mechanism. Nobody re-derives an ignore list to
check whether an entry is still earning its place.
"""

import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = REPO / ".github" / "workflows" / "suites.yml"
CURATION_TESTS = REPO / "curation" / "tests"


def _directories_that_import_or_skip(tests_root: pathlib.Path) -> set[str]:
    """Top-level directories under `tests_root` holding a module that may not import.

    `pytest.importorskip` at module scope is the exact construct that turns an
    absent optional group into a collection-time skip. Matched textually — the
    alternative is importing every test module to find out, which needs the very
    dependencies whose absence is the subject.

    **The call, not the word.** Matching the bare name found four files on the
    first run, two of them these tests and one the guard they are about, all of
    which only *discuss* the construct in prose. A guard that counts its own
    docstring is worse than none: it fails on a healthy tree and teaches whoever
    is on call to widen it until it stops meaning anything.
    """
    found = set()
    for path in tests_root.rglob("*.py"):
        if re.search(r"\bimportorskip\s*\(", path.read_text(encoding="utf-8")):
            found.add(path.relative_to(tests_root).parts[0])
    return found


#: A line opening a job: two spaces, a name, a colon, nothing else. The workflow's
#: only other two-space keys are inside a job's body, which are all deeper.
_JOB = re.compile(r"^  ([A-Za-z][\w-]*):\s*$")


def _pytest_invocations_by_job() -> dict[str, list[str]]:
    """Every `uv run … pytest …` command in the workflow, under the job that runs it.

    **Keyed by job rather than matched by shape**, which is the correction that
    let a second ignore-carrying leg exist. This helper used to assert there was
    exactly one such invocation in the whole file and identify the curation leg by
    that uniqueness — fine while it was true, and a test that fails on the next
    plane to grow an optional group rather than on anything being wrong. Naming
    the job says which claim is about which suite.

    Text rather than a YAML parse because the root project depends on no YAML
    library, and a guard that added one to read four lines would cost more than it
    protects.
    """
    invocations: dict[str, list[str]] = {}
    job = None
    for line in WORKFLOW.read_text(encoding="utf-8").splitlines():
        opening = _JOB.match(line)
        if opening:
            job = opening.group(1)
        elif job and not line.strip().startswith("#") and re.search(r"uv run .*\bpytest\b", line):
            invocations.setdefault(job, []).append(line.strip())
    return invocations


def _ignored_by(job: str) -> set[str]:
    """The directory names that job's pytest invocation excludes."""
    invocations = _pytest_invocations_by_job()
    assert job in invocations, (
        f"no `uv run … pytest` step under a job named {job!r} in suites.yml — either the job was "
        "renamed, or the suite it ran is no longer run in CI at all"
    )
    assert len(invocations[job]) == 1, (
        f"the {job!r} job runs pytest {len(invocations[job])} times: {invocations[job]}. This test "
        "reads one invocation per job; a job that grew a second needs its own claim rather than a "
        "union of both, or the two would cover for each other's gaps."
    )
    return {match.removeprefix("tests/") for match in re.findall(r"--ignore=(\S+)", invocations[job][0])}


def check_ignores(ignored: set[str], needed: set[str]) -> None:
    """Raise unless the two sets agree, naming which direction they disagree in.

    A function rather than a bare assertion in the test below, because the two
    directions are separate claims and only one of them has a real tree to prove
    it against: this repo's `--ignore` list happens to be correct, so the
    over-exclusion half could only be exercised by fabricating the inputs.

    That half was undefended when written. A mutation sweep changed the
    comparison from `==` to `needed <= ignored` — tolerating any number of
    unnecessary entries — and every test still passed, while the docstring above
    it claimed over-exclusion was "the one worth a mechanism".
    """
    missing = needed - ignored
    extra = ignored - needed
    assert not missing, (
        f"the curation CI leg does not ignore {sorted(missing)}, whose modules cannot import "
        "without their optional group. In CI they land collection skips, and assert_tests_ran.py "
        "fails the job reporting a provisioning fault against a suite that is fine."
    )
    assert not extra, (
        f"the curation CI leg ignores {sorted(extra)}, which import cleanly and need no exclusion. "
        "Those directories do not run in CI at all, and report nothing while not running — which "
        "is indistinguishable from passing."
    )


def test_the_curation_leg_ignores_exactly_the_directories_that_cannot_import():
    """Derived on both sides, so neither over- nor under-exclusion can sit unnoticed.

    A new `tests/perf/` that `importorskip`s its group would otherwise turn CI
    red for a reason that reads as a provisioning fault. An old entry left behind
    after its `importorskip` went away would otherwise stop a whole directory
    running in CI, silently and indefinitely.
    """
    needed = _directories_that_import_or_skip(CURATION_TESTS)
    assert needed, "no module under curation/tests uses importorskip — the CI leg should carry no --ignore at all"

    check_ignores(_ignored_by("curation"), needed)


def test_a_missing_ignore_is_rejected():
    """Under-exclusion: the job goes red on a healthy suite, blaming a phantom install."""
    with pytest.raises(AssertionError, match="cannot import"):
        check_ignores(ignored={"browser"}, needed={"browser", "eval"})


def test_an_unnecessary_ignore_is_rejected():
    """Over-exclusion: a whole directory stops running in CI and nothing says so.

    The half a real tree cannot demonstrate, because this repo's list is correct
    — so it is fabricated here rather than left to a `==` nobody can see fail.
    """
    with pytest.raises(AssertionError, match="import cleanly and need no exclusion"):
        check_ignores(ignored={"browser", "eval", "integration"}, needed={"browser", "eval"})


def test_tests_live_is_collected_rather_than_ignored():
    """The one opt-in directory that stays in, and the reason it can.

    `tests/live` is deselected by the marker expression in `addopts`, not by an
    import guard: its modules import cleanly with nothing optional installed, so
    they contribute no skip. Ignoring it would look consistent with its siblings
    and would cost the collection of six modules for nothing.

    Asserted so that "it is not ignored" is a checked property rather than an
    accident of whoever last edited the line.
    """
    assert "live" not in _directories_that_import_or_skip(CURATION_TESTS), (
        "a module under curation/tests/live now uses importorskip, so it can no longer be collected "
        "in CI — add --ignore=tests/live to the curation leg in suites.yml"
    )
    assert "live" not in _ignored_by("curation")


def test_the_root_leg_needs_no_ignores():
    """Why the two test jobs are not written the same way.

    The root suite runs the 2024 modules and has no opt-in group to miss, so its
    invocation is the plain one. If that ever stops being true, this fails here
    rather than in CI — where it would present as a provisioning failure against
    a suite that is fine.
    """
    assert _directories_that_import_or_skip(REPO / "tests") == set(), (
        "a module under the root tests/ now uses importorskip, so the root CI leg needs the same "
        "--ignore treatment the curation leg has"
    )


def test_the_display_leg_ignores_exactly_the_directories_that_cannot_import():
    """The same claim about the third suite, derived the same way on both sides.

    This test used to assert the display leg needed *no* ignores, and predicted
    the moment that would stop being true: the e-paper panel arriving behind an
    optional install. It has arrived. The typesetter needs Pango through
    PyGObject, which a default `uv sync` does not install, so `tests/raster`
    `importorskip`s the group and the leg excludes it.

    **What excluding it must not mean is that the typesetter goes untested in
    CI**, which is what the job asserted below exists to prevent — a directory
    ignored by one leg and run by no other is coverage that has silently gone.
    """
    needed = _directories_that_import_or_skip(REPO / "display" / "tests")
    assert needed, "no module under display/tests uses importorskip — the display CI leg should carry no --ignore at all"

    check_ignores(_ignored_by("display"), needed)


def test_every_directory_the_display_leg_ignores_is_run_by_another_job():
    """The half that `check_ignores` cannot see, and the one that actually bites.

    Ignoring a directory keeps a green leg honest; it does not keep the code
    tested. A `--ignore` added because a group is optional, with no job installing
    that group, removes the tests from CI entirely — and a suite that does not run
    reports exactly what a suite that passes reports.

    So the ignored directories are checked against the paths other jobs name.
    Here that is `tests/raster`, run by the typesetting job with the group
    installed and `assert_tests_ran.py` behind it.
    """
    elsewhere = {
        path
        for job, invocations in _pytest_invocations_by_job().items()
        if job != "display"
        for invocation in invocations
        # The `--ignore=` arguments come out first: a directory another job also
        # excludes is not a directory another job runs, and counting it would let
        # two legs cover for each other while neither collected a line of it.
        for path in re.findall(r"(?<![=\w/])tests/\S+", re.sub(r"--ignore=\S+", "", invocation))
    }
    unrun = {f"tests/{name}" for name in _ignored_by("display")} - elsewhere
    assert not unrun, (
        f"the display leg ignores {sorted(unrun)} and no other job in suites.yml runs it, so those "
        "tests do not execute in CI at all — which is indistinguishable from their passing"
    )
