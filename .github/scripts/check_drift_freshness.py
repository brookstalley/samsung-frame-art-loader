"""Fail when the API-drift probes have stopped running at all.

`assert_tests_ran.py` closes the green-but-verified-nothing hole for a run that
*happened*. A schedule that stops firing produces no artifact at all: no run, no
skip, nothing to assert on. It is silent, and silence looks exactly like health.

**Two routes take the schedule away, and neither announces itself.** GitHub fires
`schedule` only for workflows on the repository's default branch, so a drift
workflow living on an unmerged branch has never run and never will; and GitHub
disables scheduled workflows after a stretch of repository inactivity, which
nothing here would otherwise notice. Both leave the `*-api-findings.md` documents
quietly un-re-verified while the product goes on being built against them.

**The remedy shape is the one this product already uses elsewhere.** The preview
sweep logs `preview.swept` on every pass *including the ones that reclaim
nothing*, precisely so that absence over an interval is itself the fault. This is
that idea applied to a workflow: a successful run is the positive signal, and its
age is the thing measured.

**Per tier, because the two tiers run on different clocks.** The free probes are
weekly and the paid one monthly, so a single age threshold would either nag about
a paid tier that is behaving or sleep through three missed weeks of the free one.
The tiers are told apart by which *jobs* actually ran in each workflow run — a
weekly run skips the paid job and a monthly run skips the free ones, so a run's
mere existence says nothing about which tier it refreshed.

Reads a JSON document on stdin: a list of runs, newest first, each
``{"createdAt": "<ISO-8601>", "conclusion": "success", "jobs": [{"name": ..., "conclusion": ...}]}``.
The workflow builds it from `gh`; everything that decides anything is here, where
it can be tested without a network.

Usage: check_drift_freshness.py [--now <ISO-8601>] < runs.json
"""

import json
import sys
from datetime import UTC, datetime, timedelta

#: How long a tier may go unrefreshed before absence is the finding, and why each
#: number is the number it is.
#:
#: Free — the probes run weekly, on Mondays. One miss is unremarkable: GitHub's
#: scheduler is contended and delays runs, which is why the cron is deliberately
#: off the hour. Two could still be bad luck. Three weeks with nothing is a
#: pattern rather than noise, and it is still well inside the window in which a
#: museum contract change matters.
#:
#: Paid — monthly, on the 1st. Two missed months, with slack for the longest
#: month pair (62 days), a delayed run, and the fact that this check only fires on
#: a push to `main` rather than continuously. It is deliberately loose: this tier
#: spends real money, it moves slower than the free ones, and a late alarm about
#: it costs far less than a monthly false one.
STALE_AFTER = {"free": timedelta(days=21), "paid": timedelta(days=75)}

#: Which job in `api-drift.yml` stands for which tier. A run refreshed a tier only
#: if that tier's job actually *succeeded* in it — `skipped` is the normal state
#: for the other tier's job in any given run, and `failure` is a run that told us
#: something but re-verified nothing.
TIER_JOBS = {
    "free": ("Museum APIs (free)", "dezoomify-rs (free)"),
    "paid": ("OpenRouter (spends money)",),
}


def newest_success(runs: list[dict], job_names: tuple[str, ...]) -> datetime | None:
    """When any of `job_names` last succeeded, or None if it never has.

    Any one of the tier's jobs counts. The free tier has two — a museum outage
    and a broken binary install are separate faults with separate jobs, and
    either one succeeding proves the schedule itself is alive, which is the only
    thing this file is asking about. Whether a *probe* failed is
    `report_drift_failure.py`'s question, and it has a louder answer.
    """
    for run in runs:
        for job in run.get("jobs", []):
            if job.get("name") in job_names and job.get("conclusion") == "success":
                return datetime.fromisoformat(run["createdAt"].replace("Z", "+00:00"))
    return None


def main(runs: list[dict], now: datetime) -> int:
    worst = 0
    for tier, job_names in TIER_JOBS.items():
        last = newest_success(runs, job_names)
        limit = STALE_AFTER[tier]

        if last is None:
            print(
                f"::error::The {tier} API-drift probes have never completed successfully. "
                "GitHub fires `schedule` only for workflows on the default branch, so this is "
                "what a drift workflow that has not yet been merged — or one whose first run "
                "failed — looks like. Dispatch it by hand once (Actions -> API drift -> Run "
                "workflow) to prove the wiring, rather than waiting a week to find a typo."
            )
            worst = 1
            continue

        age = now - last
        if age > limit:
            print(
                f"::error::The {tier} API-drift probes last succeeded {age.days} days ago "
                f"({last.date().isoformat()}), past the {limit.days}-day mark. Either the "
                "schedule has stopped firing — GitHub disables scheduled workflows after a "
                "stretch of repository inactivity — or the workflow is no longer on the default "
                "branch. Until it runs, the *-api-findings.md measurements are not being "
                "re-verified and should not be treated as current."
            )
            worst = 1
        else:
            print(f"{tier}: last succeeded {age.days} days ago ({last.date().isoformat()}), within {limit.days} days")

    return worst


if __name__ == "__main__":
    argv = sys.argv[1:]
    now = datetime.now(UTC)
    if argv[:1] == ["--now"]:
        now = datetime.fromisoformat(argv[1].replace("Z", "+00:00"))
        argv = argv[2:]
    if argv:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(json.load(sys.stdin), now))
