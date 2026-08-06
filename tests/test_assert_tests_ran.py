"""The CI guard that tells a suite which ran from one which skipped itself.

`.github/scripts/assert_tests_ran.py` is the only thing standing between "this
job verified the thing it exists to verify" and "this job was green because every
test skipped". **Every CI job that runs a suite depends on it** — the API-drift
probes and the browser suite — and each of those suites is *designed* to skip when
its dependency is absent, which is correct on a developer's machine and is
precisely the trap in CI. The invariant is stated rather than a count of today's
jobs, because the count is the part that goes stale: the last test in this file is
what actually holds it, by deriving the list from the workflow files.

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
#: pytest reports an expected failure as a `<skipped>` element and counts it in
#: the suite's `skipped` attribute, telling the two apart only by `type`.
XFAIL_CASE = (
    '<testcase classname="tests.unit.test_identity" name="test_a_reversed_name_is_accepted">'
    '<skipped type="pytest.xfail" message="artist identity is order-sensitive"/>'
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
    guard that fails the job without saying why leaves an operator reading every
    workflow in the repo to find which install broke.
    """
    guard = _load()
    report = _report(tmp_path, NESTED.format(tests=1, skipped=1, cases=SKIPPED_CASE))

    guard.main(report)

    printed = capsys.readouterr().out
    assert "tests.live.test_a::test_it_still_holds" in printed
    assert "dezoomify-rs is not installed" in printed


@SHAPES
def test_an_expected_failure_is_not_read_as_a_missing_dependency(tmp_path, shape, capsys):
    """An `xfail` ran and failed as recorded. It is the opposite of unprovisioned.

    pytest gives it a `<skipped>` element and counts it in the suite's `skipped`
    attribute, so a guard reading that attribute cannot tell a documented
    expected failure from an absent secret. This one is told apart by `type`.

    Found the day the default suites first got a CI leg: the curation suite
    carries one `xfail` for an order-sensitivity in artist identity, and the job
    went red naming a dependency that was never missing. Until then no CI job ran
    a suite that contained an `xfail`, so the defect had nowhere to show.
    """
    guard = _load()
    report = _report(tmp_path, shape.format(tests=2, skipped=1, cases=PASSING_CASE + XFAIL_CASE))

    assert guard.main(report) == 0
    printed = capsys.readouterr().out
    assert "xfailed 1" in printed, "an expected failure must be reported, not silently discounted"
    assert "::error::" not in printed


@SHAPES
def test_a_real_skip_beside_an_expected_failure_still_fails_the_job(tmp_path, shape, capsys):
    """The distinction must not become a hole: one xfail cannot cover for a skip.

    This is the mutation the fix invites — classify by type, then count the
    wrong bucket — and it would leave a job green whenever a documented xfail
    happened to sit in the same suite as an unprovisioned test.
    """
    guard = _load()
    report = _report(tmp_path, shape.format(tests=3, skipped=2, cases=PASSING_CASE + XFAIL_CASE + SKIPPED_CASE))

    assert guard.main(report) == 1
    printed = capsys.readouterr().out
    assert "dezoomify-rs is not installed" in printed
    assert "1 test(s) skipped" in printed, "the count must exclude the xfail, or it misstates what is wrong"


def test_suite_level_skips_with_no_case_detail_still_fail_the_job(tmp_path, capsys):
    """A report the classifier cannot read must not thereby win a pass.

    The `type` attribute is the only thing separating an xfail from a missing
    dependency, so a report that declares skips at suite level and carries no
    `<skipped>` case elements — another tool's output, a truncated file — is
    unclassifiable. It fails, because the safe direction for an unknown is to
    refuse rather than to wave through.
    """
    guard = _load()
    report = _report(tmp_path, NESTED.format(tests=4, skipped=2, cases=PASSING_CASE))

    assert guard.main(report) == 1
    assert "no testcase detail" in capsys.readouterr().out


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


def test_every_workflow_that_runs_a_suite_calls_the_guard():
    """The guard is worth nothing where it is not wired, and wiring is easy to omit.

    Derived from the workflow files rather than from a list written here: a new
    workflow that runs pytest and forgets the guard is exactly the regression
    this asserts, and a hardcoded list of today's workflows could not see it.

    **Both spellings of the extension**, because GitHub accepts either and a
    guard that walks only one has a hole exactly the width of someone typing
    `.yaml`.

    **What this does NOT catch, stated rather than left to be discovered:** it
    matches per *file*, so a second pytest job added to a workflow that already
    calls the guard elsewhere would pass unseen. Closing that needs a YAML parse,
    and pyyaml is not a dependency of this plane — adding one for a single test
    buys less than it costs. The Critic reviews new jobs; this holds the case
    where a whole workflow forgets.
    """
    directory = GUARD.parents[2] / ".github" / "workflows"
    workflows = sorted(set(directory.glob("*.yml")) | set(directory.glob("*.yaml")))
    assert workflows, "no workflows found — this test is asserting nothing"

    for workflow in workflows:
        text = workflow.read_text(encoding="utf-8")
        if "pytest" not in text:
            continue
        assert "assert_tests_ran.py" in text, f"{workflow.name} runs pytest but never checks that anything actually ran"


def _ci_pytest_invocations(directory: pathlib.Path) -> list[tuple[str, str]]:
    """Every line in a workflow directory that actually runs pytest.

    Shared by the two tests below so there is one scan rather than a scan and a
    copy of it — a test that re-implements the loop it names defends nothing,
    which is how the comment skip below came to be asserted and undefended at the
    same time.

    **Both spellings of the extension**, because GitHub accepts either and a walk
    over one has a hole exactly the width of someone typing `.yaml`.

    Comment lines are skipped: a workflow may legitimately document the unscoped
    *local* command in prose — `api-drift.yml` does — and nothing runs a comment.
    """
    workflows = sorted(set(directory.glob("*.yml")) | set(directory.glob("*.yaml")))
    assert workflows, f"no workflows found in {directory} — the caller is asserting nothing"
    found = []
    for workflow in workflows:
        for line in workflow.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or "uv run pytest" not in stripped:
                continue
            found.append((workflow.name, stripped))
    return found


def _is_scoped(line: str) -> bool:
    """Whether an invocation names a path before its flags.

    The path comes first by convention, and it is the token that is neither the
    command nor an option nor an option's value.
    """
    after = line.split("uv run pytest", 1)[1].split()
    return bool(after) and not after[0].startswith("-")


def test_every_ci_pytest_invocation_scopes_a_path():
    """An unscoped run collects the whole tree, and this guard fails on any skip.

    Five suites here are deselected by a marker expression in `addopts` — the
    browser one and the four live/eval ones — and their modules `importorskip`
    at collection when the opt-in group is absent, which it is in CI. So a job
    running `pytest -m live_museum` with no path still *collects* those modules,
    lands their skips in the report, and this guard fails the job while every
    probe passed. The alarm then cries wolf until nobody reads it, which is
    strictly worse than not having wired it.

    **Asserted rather than remembered because it has now been found and
    hand-fixed twice in one bundle** — `browser.yml` on 2026-08-05 and all three
    `api-drift.yml` jobs hours later, the second time by Critic review rather than
    by anyone noticing. A defect that recurs across files in one day is one a
    reviewer should not have to catch a third time.

    Matched textually rather than through a YAML parse, for the reason the test
    above gives: pyyaml is not a dependency of this plane.

    **Every line carrying the command counts, whatever precedes it**, and that
    breadth is the correction rather than the original design. The first version
    matched two prefixes — `run: uv run pytest` and `- uv run pytest` — and its
    docstring claimed an invocation it did not match "would simply not match the
    prefix and would be reported". It would not: an unmatched line never enters
    the list, so it is skipped in silence. That is a coverage hole, not a loss of
    precision, and it sat exactly where `CLAUDE.md` points — every command it
    documents is written `cd curation && uv run pytest …`, which the prefixes
    missed, as would any invocation inside a `run: |` block. A guard against a
    thrice-recurring defect, blind to the form the documentation teaches.

    Comment lines are skipped, because a workflow may legitimately document the
    unscoped *local* command in prose — `api-drift.yml` does — and nothing runs a
    comment.

    **What is still not checked, stated as the limitation it is.** The breadth
    above is about which lines are *collected*; the assertion below reads the
    first token after the command on that one line, so a shell continuation —
    `uv run pytest \\` with the arguments on the next line — collects and then
    passes, because the token it inspects is the backslash. No workflow here is
    written that way and the check would have to grow a line-joining pass to
    cover it.

    Written out because the previous version of this docstring overstated its
    reach in exactly this way, and that is the more dangerous half of the defect
    it describes: a guard whose stated limitation is not its real one cannot warn
    you, so the limit gets recorded rather than rounded off.
    """
    invocations = _ci_pytest_invocations(GUARD.parents[2] / ".github" / "workflows")
    assert invocations, "no pytest invocations found in any workflow — this test is asserting nothing"

    for name, line in invocations:
        assert _is_scoped(line), (
            f"{name}: `{line}` runs pytest with no path scope, so it collects the whole tree — "
            "the opt-in suites' import skips will land in the report and fail the guard"
        )


def test_a_documented_command_in_a_comment_does_not_fail_the_scope_check(tmp_path):
    """The comment skip is a branch, and a branch is not covered by running near it.

    Its failure mode is a false red on a workflow whose prose documents the
    *local* invocation — which is unscoped on purpose, because no guard reads a
    report at a terminal.

    **This drives the real scan**, which is the whole point and is what the first
    version of this test got wrong: it re-implemented the loop in its own body, so
    deleting the comment skip from the actual scanner turned nothing red and the
    branch stayed undefended while a docstring claimed otherwise. The Critic
    caught it by simulating exactly that mutation. Both tests call
    `_ci_pytest_invocations` now — that one over `.github/workflows`, this one
    over a fixture — so there is one loop and mutating it is visible from here.

    The fixture is a workflow whose comment carries the unscoped local form and
    whose step carries the scoped CI form: with the branch removed the comment
    yields `-m` as its first token and is reported.
    """
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "probe.yml").write_text(
        "jobs:\n"
        "  j:\n"
        "    steps:\n"
        "      # Locally this is right: `uv run pytest -m live_museum -n0`\n"
        "      - run: uv run pytest tests/live -m live_museum -n0 --junitxml=results.xml\n",
        encoding="utf-8",
    )

    collected = _ci_pytest_invocations(workflows)

    assert [line for _, line in collected] == [
        "- run: uv run pytest tests/live -m live_museum -n0 --junitxml=results.xml"
    ], f"the commented local command was read as a CI invocation: {collected}"
    assert all(_is_scoped(line) for _, line in collected)
