"""The check that notices the drift probes have stopped running at all.

`assert_tests_ran.py` covers the run that happened and verified nothing. This
covers the run that never happened, which produces no report to inspect and no
skip to count — it is pure absence, and absence is indistinguishable from health
unless something goes looking.

Driven through `main` with hand-built run lists rather than against the GitHub
API, because every decision worth pinning is in how those lists are read: which
job counts for which tier, what a skipped job means, and where the boundary
between fresh and stale falls.
"""

import importlib.util
import json
import pathlib
import subprocess
import sys
from datetime import UTC, datetime, timedelta

import pytest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / ".github" / "scripts" / "check_drift_freshness.py"

NOW = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)

MUSEUM = "Museum APIs (free)"
BINARY = "dezoomify-rs (free)"
PAID = "OpenRouter (spends money)"


def _load():
    """Import the script, which lives outside any package and has no importable name."""
    spec = importlib.util.spec_from_file_location("check_drift_freshness", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(days_ago: float, *jobs: tuple[str, str | None]) -> dict:
    """One workflow run, `days_ago` before NOW, carrying the given (job, conclusion) pairs."""
    when = NOW - timedelta(days=days_ago)
    return {
        "createdAt": when.isoformat().replace("+00:00", "Z"),
        "jobs": [{"name": name, "conclusion": conclusion} for name, conclusion in jobs],
    }


def test_both_tiers_running_on_time_passes():
    guard = _load()
    runs = [
        _run(2, (MUSEUM, "success"), (BINARY, "success")),
        _run(5, (PAID, "success")),
    ]

    assert guard.main(runs, NOW) == 0


def test_a_workflow_that_has_never_run_fails(capsys):
    """The current state of this repo, and the first fault the check exists for.

    GitHub fires `schedule` only for workflows on the default branch, so a drift
    workflow sitting on an unmerged branch has run zero times. Nothing about that
    is visible anywhere: no red check, no absent artifact, just a workflow nobody
    has thought about since writing it.
    """
    guard = _load()

    assert guard.main([], NOW) == 1

    printed = capsys.readouterr().out
    assert "never completed successfully" in printed
    assert "default branch" in printed, "the message must name the cause it is most likely to be"
    assert "Run workflow" in printed, "and the remedy, or it sends the reader nowhere"


def test_the_free_tier_going_quiet_is_caught_while_the_paid_one_is_fine(capsys):
    """The reason the tiers are measured apart rather than together.

    A single age threshold over "the newest run" would read the healthy monthly
    run as evidence the weekly probes are fine. They are not: three Mondays have
    passed with nothing.
    """
    guard = _load()
    runs = [_run(3, (PAID, "success")), _run(30, (MUSEUM, "success"))]

    assert guard.main(runs, NOW) == 1

    printed = capsys.readouterr().out
    assert "free API-drift probes last succeeded 30 days ago" in printed
    assert "paid: last succeeded 3 days ago" in printed, "the healthy tier must still report, not go silent"


def test_the_paid_tier_going_quiet_is_caught_while_the_free_one_is_fine(capsys):
    guard = _load()
    runs = [_run(1, (MUSEUM, "success")), _run(90, (PAID, "success"))]

    assert guard.main(runs, NOW) == 1

    printed = capsys.readouterr().out
    assert "paid API-drift probes last succeeded 90 days ago" in printed


def test_either_free_job_alone_proves_the_schedule_is_alive():
    """A museum outage must not read as a dead schedule.

    The free tier has two jobs against two unrelated dependencies. Whether a
    *probe* failed is a different question with a louder answer — an issue filed
    by `report_drift_failure.py`. This file only asks whether the cron still
    fires, and one succeeding job answers that.
    """
    guard = _load()
    runs = [_run(1, (MUSEUM, "failure"), (BINARY, "success")), _run(1, (PAID, "success"))]

    assert guard.main(runs, NOW) == 0


@pytest.mark.parametrize("conclusion", ["skipped", "failure", "cancelled", None])
def test_a_run_whose_tier_job_did_not_succeed_does_not_refresh_that_tier(conclusion):
    """`skipped` is the normal state of the other tier's job in any given run.

    A weekly run skips the paid job and a monthly run skips the free ones, so a
    run's mere existence says nothing about which tier it refreshed. Counting one
    would let a healthy weekly cadence vouch indefinitely for a paid probe that
    has not run since the workflow was written.
    """
    guard = _load()
    runs = [_run(1, (MUSEUM, "success")), _run(1, (PAID, conclusion))]

    assert guard.main(runs, NOW) == 1


def test_the_boundary_is_inclusive_of_the_stated_limit():
    """Exactly at the limit is fresh; past it is not.

    Pinned because the two sides are one `>` apart and the stated number is the
    contract: "21 days" must mean a probe 21 days old still passes, or the
    documented interval is off by one from the enforced one.
    """
    guard = _load()

    at_limit = [_run(21, (MUSEUM, "success")), _run(1, (PAID, "success"))]
    assert guard.main(at_limit, NOW) == 0

    past_limit = [_run(21.5, (MUSEUM, "success")), _run(1, (PAID, "success"))]
    assert guard.main(past_limit, NOW) == 1


def test_the_thresholds_match_the_cadences_they_are_derived_from():
    """The numbers are reasoned from the crons, so the crons are where they are checked.

    Each threshold is "N missed runs of that tier". If somebody changes a cron
    without revisiting the threshold, the tier either nags on a healthy cadence
    or sleeps through several misses — and both are silent. Read from the workflow
    rather than restated here, so the two cannot drift apart.
    """
    guard = _load()
    workflow = (SCRIPT.parents[2] / ".github" / "workflows" / "api-drift.yml").read_text(encoding="utf-8")

    assert 'cron: "17 6 * * 1"' in workflow, "the free tier is no longer weekly — revisit STALE_AFTER['free']"
    assert 'cron: "43 6 1 * *"' in workflow, "the paid tier is no longer monthly — revisit STALE_AFTER['paid']"

    assert guard.STALE_AFTER["free"] > timedelta(days=14), "a weekly probe must survive two ordinary misses"
    assert guard.STALE_AFTER["paid"] > timedelta(days=62), "a monthly probe must survive the longest two-month pair"


def test_every_job_named_in_the_tier_map_exists_in_the_workflow():
    """Job names are the join key, and they are matched as strings.

    Renaming a job in `api-drift.yml` would silently make its tier read as
    never-run — the check would go red for a reason that has nothing to do with
    the schedule, and the message would send the operator to dispatch a workflow
    that is running perfectly well.
    """
    guard = _load()
    workflow = (SCRIPT.parents[2] / ".github" / "workflows" / "api-drift.yml").read_text(encoding="utf-8")

    for tier, names in guard.TIER_JOBS.items():
        for name in names:
            assert f'name: "{name}"' in workflow, f"{tier} maps to a job named {name!r}, which no longer exists"


def test_the_entry_point_reads_stdin_and_exits_nonzero():
    """The workflow pipes `gh` output in and reads the exit code — so drive both.

    Every test above calls `main` directly, which leaves the argument parsing,
    the stdin read and the `SystemExit` untested; a script whose logic is perfect
    and whose entry point is broken fails the job for no reason anyone can see in
    the output. Run as a subprocess because that is what CI does.
    """
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--now", "2026-08-06T12:00:00Z"],
        input="[]",
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "never completed successfully" in result.stdout


def test_the_entry_point_exits_zero_on_a_healthy_pair():
    """The other half: a passing check must not fail the job."""
    runs = json.dumps([_run(2, (MUSEUM, "success")), _run(2, (PAID, "success"))])

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--now", "2026-08-06T12:00:00Z"],
        input=runs,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
