"""The route from a failing scheduled probe to a human who will actually see it.

Before this existed, `api-drift.yml`'s own comments promised a notification that
was never designed — the only route was GitHub's default Actions email, which
goes to whoever last edited the cron file and is silently absent for anyone whose
Actions notifications are off. A weekly probe could sit red for months while the
product went on being built against a findings document nobody had re-verified.

The mechanism has exactly one hard requirement beyond "say something": **a weekly
failure must not open a new issue every Monday.** That is what most of this file
is about, because a de-duplication that quietly stops working looks identical to
one that works — nothing fails, issues just start piling up somewhere nobody is
looking that week.

`gh` is injected rather than run: every decision worth pinning is in which call
gets made and with what, and a test that shelled out would prove only that the
machine running it had a token.
"""

import importlib.util
import pathlib

import pytest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / ".github" / "scripts" / "report_drift_failure.py"

RUN_URL = "https://github.com/brookstalley/samsung-frame-art-loader/actions/runs/123"


def _load():
    """Import the script, which lives outside any package and has no importable name."""
    spec = importlib.util.spec_from_file_location("report_drift_failure", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeGh:
    """Records every `gh` call and answers the one read the script makes."""

    def __init__(self, open_issues: list[dict] | None = None):
        self.open_issues = open_issues or []
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, *args: str) -> str:
        self.calls.append(args)
        if args[:2] == ("issue", "list"):
            import json  # noqa: PLC0415

            return json.dumps(self.open_issues)
        return ""

    def call_named(self, *prefix: str) -> tuple[str, ...] | None:
        for call in self.calls:
            if call[: len(prefix)] == prefix:
                return call
        return None


def test_a_first_failure_opens_an_issue():
    script = _load()
    gh = FakeGh(open_issues=[])

    assert script.main("Museum APIs (free)", RUN_URL, gh=gh) == 0

    created = gh.call_named("issue", "create")
    assert created is not None, "a contract failing for the first time must produce something durable"
    assert "Museum APIs (free)" in created[created.index("--title") + 1]
    assert RUN_URL in created[created.index("--body") + 1]


def test_a_repeat_failure_comments_instead_of_opening_a_second_issue():
    """The de-duplication requirement, stated as the behaviour rather than the mechanism.

    Weekly probes mean fifty-two issues a year for one unfixed contract if this
    is wrong, and a backlog nobody can read is the same as no alert at all.
    """
    script = _load()
    gh = FakeGh(open_issues=[{"number": 77, "title": script.title_for("Museum APIs (free)")}])

    assert script.main("Museum APIs (free)", RUN_URL, gh=gh) == 0

    assert gh.call_named("issue", "create") is None, "a second issue was opened for a contract already reported"
    commented = gh.call_named("issue", "comment")
    assert commented is not None
    assert commented[2] == "77"
    assert RUN_URL in commented[commented.index("--body") + 1], "the comment must name the run, or it adds nothing"


def test_a_different_contract_failing_gets_its_own_issue():
    """One issue per contract, not one per workflow.

    The per-marker job split exists so a museum outage does not mask the binary
    result; collapsing both onto one issue would give that structure away at the
    last step.
    """
    script = _load()
    gh = FakeGh(open_issues=[{"number": 77, "title": script.title_for("Museum APIs (free)")}])

    script.main("dezoomify-rs (free)", RUN_URL, gh=gh)

    created = gh.call_named("issue", "create")
    assert created is not None
    assert "dezoomify-rs (free)" in created[created.index("--title") + 1]


def test_the_dedup_search_is_scoped_to_the_workflow_s_own_label():
    """Scoped by label, so the search is not a title match against the whole backlog."""
    script = _load()
    gh = FakeGh()

    script.main("Museum APIs (free)", RUN_URL, gh=gh)

    listed = gh.call_named("issue", "list")
    assert listed is not None
    assert "--label" in listed and listed[listed.index("--label") + 1] == script.LABEL
    assert listed[listed.index("--state") + 1] == "open", "a closed issue must not suppress a fresh report"
    created = gh.call_named("issue", "create")
    assert created[created.index("--label") + 1] == script.LABEL, "an issue it cannot find again is not deduplicated"


def test_a_closed_issue_for_the_same_contract_does_not_suppress_a_new_one():
    """The operator closes these by hand, having reconciled the findings document.

    So a closed issue means "that drift was dealt with" — and the contract moving
    again afterwards is new information that must not be swallowed. Only open
    issues are searched, and this is the case that proves the difference matters.
    """
    script = _load()
    gh = FakeGh(open_issues=[])

    script.main("Museum APIs (free)", RUN_URL, gh=gh)

    assert gh.call_named("issue", "create") is not None


@pytest.mark.parametrize(
    "near_miss",
    [
        "api-drift: Museum APIs (free) no longer matches what we recorded ",
        "API-drift: Museum APIs (free) no longer matches what we recorded",
        "Museum APIs (free) no longer matches what we recorded",
        "api-drift: museum apis (free) no longer matches what we recorded",
    ],
)
def test_a_title_that_is_not_exactly_ours_is_not_commented_on(near_miss):
    """Exact match, deliberately: commenting on somebody else's issue is the worse error.

    A human filing a related item by hand, or an older title format left over
    from a rename, must not absorb the workflow's report — the operator would
    then be reading drift notices threaded under an issue about something else.
    Opening one issue too many is recoverable; hijacking one is confusing in a
    way nobody traces back to a workflow.
    """
    script = _load()

    assert script.choose([{"number": 5, "title": near_miss}], "Museum APIs (free)") is None


def test_the_title_is_stable_for_a_given_contract():
    """The whole de-duplication rests on this, so it is asserted rather than assumed."""
    script = _load()

    assert script.title_for("Museum APIs (free)") == script.title_for("Museum APIs (free)")
    assert script.title_for("Museum APIs (free)") != script.title_for("dezoomify-rs (free)")


def test_the_body_sends_a_reader_to_both_faults_that_land_here():
    """Two different failures reach this issue and they have opposite remedies.

    A failed assertion means a recorded fact has moved. A failure from
    `assert_tests_ran.py` means the job verified nothing — an expired secret, a
    failed install — and the contract may be perfectly fine. A body that named
    only the first would send the operator to reconcile a document against an API
    that never changed.
    """
    script = _load()
    body = script.body_for("Museum APIs (free)", RUN_URL)

    assert "assert_tests_ran.py" in body
    assert "findings" in body
    assert RUN_URL in body


def test_the_contract_names_are_the_workflow_s_own_job_names():
    """The name in the issue title is what tells the operator which probe to look at.

    Passed as a literal from each job in `api-drift.yml`, so a job renamed
    without updating its reporting step would file issues under a contract name
    that appears nowhere — findable by neither search nor memory.
    """
    workflow = (SCRIPT.parents[2] / ".github" / "workflows" / "api-drift.yml").read_text(encoding="utf-8")

    reported = [
        line.strip().strip('"')
        for line in workflow.splitlines()
        if line.strip().startswith('"') and line.strip().endswith('"') and "(" in line
    ]
    assert reported, "no contract names found — this test is asserting nothing"

    for name in reported:
        assert f'name: "{name}"' in workflow, f"{name!r} is reported as a contract but names no job"
