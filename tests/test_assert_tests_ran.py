"""The CI guard that tells a suite which ran from one which skipped itself.

`.github/scripts/assert_tests_ran.py` is the only thing standing between "this
job verified the thing it exists to verify" and "this job was green because every
test skipped". Five CI jobs depend on it — the four in `api-drift.yml` and the
browser suite — and each of those suites is *designed* to skip when its
dependency is absent, which is correct on a developer's machine and is precisely
the trap in CI.

So the guard is load-bearing, and until this file it had no test: a guard that
stopped working would itself be invisible, reporting the same silent green it
exists to refuse. That is the failure shape it was written against, one level up.

It is exercised by calling `main` with real JUnit XML rather than by running CI,
because the two root element shapes pytest emits are handled here by hand and
nothing else pins which one is being read.
"""

import importlib.util
import pathlib

import pytest

GUARD = pathlib.Path(__file__).resolve().parents[1] / ".github" / "scripts" / "assert_tests_ran.py"


def _load():
    """Import the guard, which lives outside any package and has no importable name."""
    spec = importlib.util.spec_from_file_location("assert_tests_ran", GUARD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _report(tmp_path, body: str) -> pathlib.Path:
    path = tmp_path / "results.xml"
    path.write_text(body, encoding="utf-8")
    return path


#: pytest has emitted both of these as the root element across versions, and the
#: guard handles the pair by hand. Parametrising over both is what stops a
#: refactor quietly supporting only the one this repo happens to produce today.
_SUITE = '<testsuite name="pytest" tests="{tests}" skipped="{skipped}" failures="0" errors="0">{cases}</testsuite>'
NESTED = f"<testsuites>{_SUITE}</testsuites>"
BARE = _SUITE
SHAPES = pytest.mark.parametrize("shape", [NESTED, BARE], ids=["testsuites-root", "testsuite-root"])

PASSING_CASE = '<testcase classname="tests.live.test_a" name="test_it_still_holds"/>'
SKIPPED_CASE = (
    '<testcase classname="tests.live.test_a" name="test_it_still_holds">'
    '<skipped message="dezoomify-rs is not installed"/>'
    "</testcase>"
)


@SHAPES
def test_a_suite_that_really_ran_is_allowed_through(tmp_path, shape):
    guard = _load()
    report = _report(tmp_path, shape.format(tests=1, skipped=0, cases=PASSING_CASE))

    assert guard.main(report) == 0


@SHAPES
def test_a_suite_that_skipped_itself_fails_the_job(tmp_path, shape):
    """The whole point: a green run that made no request must not read as success."""
    guard = _load()
    report = _report(tmp_path, shape.format(tests=1, skipped=1, cases=SKIPPED_CASE))

    assert guard.main(report) == 1


def test_the_failure_names_which_dependency_was_missing(tmp_path, capsys):
    """ "1 test(s) skipped" sends nobody anywhere; the reason is the whole value.

    Asserted on the emitted line rather than only on the exit code, because a
    guard that fails the job without saying why leaves an operator reading five
    workflow files to find which install broke.
    """
    guard = _load()
    report = _report(tmp_path, NESTED.format(tests=1, skipped=1, cases=SKIPPED_CASE))

    guard.main(report)

    printed = capsys.readouterr().out
    assert "tests.live.test_a::test_it_still_holds" in printed
    assert "dezoomify-rs is not installed" in printed


def test_a_marker_that_selected_nothing_fails_the_job(tmp_path, capsys):
    """Zero collected is the other silent green — a typo'd `-m` verifies nothing.

    The message is asserted, not only the exit code, and that is not fussiness:
    two branches refuse this report — "no tests collected" and "nothing ran" —
    so an exit code alone cannot tell which fired, and the two send an operator
    to opposite places. One means the marker expression matched nothing, the
    other that everything it matched was skipped.
    """
    guard = _load()
    report = _report(tmp_path, NESTED.format(tests=0, skipped=0, cases=""))

    assert guard.main(report) == 1
    assert "marker expression selected nothing" in capsys.readouterr().out


def test_a_report_that_was_never_written_fails_the_job(tmp_path):
    """pytest writes the file even when everything fails, so absence means it never ran."""
    guard = _load()

    assert guard.main(tmp_path / "nothing-here.xml") == 1


def test_a_report_with_no_testsuite_fails_the_job(tmp_path):
    """Well-formed XML that is not a pytest report must not be read as a pass."""
    guard = _load()
    report = _report(tmp_path, "<hello/>")

    assert guard.main(report) == 1


def test_every_workflow_that_runs_a_suite_calls_the_guard(tmp_path):
    """The guard is worth nothing where it is not wired, and wiring is easy to omit.

    Derived from the workflow files rather than from a list written here: a new
    workflow that runs pytest and forgets the guard is exactly the regression
    this asserts, and a hardcoded list of today's workflows could not see it.
    """
    workflows = sorted((GUARD.parents[2] / ".github" / "workflows").glob("*.yml"))
    assert workflows, "no workflows found — this test is asserting nothing"

    for workflow in workflows:
        text = workflow.read_text(encoding="utf-8")
        if "pytest" not in text:
            continue
        assert "assert_tests_ran.py" in text, f"{workflow.name} runs pytest but never checks that anything actually ran"
