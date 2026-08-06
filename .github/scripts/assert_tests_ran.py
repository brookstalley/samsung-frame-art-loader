"""Fail when an opt-in suite reported success without actually testing anything.

**Two kinds of suite depend on this, not one.** The live probes are the obvious
half; `browser.yml` is the other, and it needs exactly the same protection for a
different missing dependency — the browser suite skips itself when the `browser`
group or the downloaded Chromium is absent, which in CI is a provisioning failure
that would otherwise report a green client-coverage job having executed no line of
the client. Written out because an earlier version of this docstring described
only the live suites, so the guard read as narrower than the workflows that
actually call it.

**The whole opt-in-probe design depends on this.** Every test in those suites skips
itself cleanly when its dependency is absent — `skipif(not OPENROUTER_API_KEY)`,
`pytest.skip("dezoomify-rs is not installed")` — which is right for a developer's
machine and is a trap in CI. An expired secret, a rename, a failed binary install:
each gives a completely green pytest run that made no request and verified
nothing, and a scheduled job whose job is to notice change would go on reporting
success for as long as it stayed broken.

So a skip here is read as a provisioning failure rather than a legitimate
absence. In CI every dependency is meant to be present; if one is not, that is
the finding.

**An `xfail` is not one of those skips, and the distinction is load-bearing.**
pytest reports an expected failure in JUnit as a `<skipped>` element and counts
it in the suite's `skipped` attribute — indistinguishable from a missing
dependency if you read the attribute, which is what this file used to do. An
`xfail` is the opposite of an unprovisioned test: it ran, it failed exactly as
recorded, and the recording is a deliberate artefact of a decision someone wrote
down. Failing the job on one would mean a suite could never carry a documented
expected failure and a CI leg at the same time.

Found the day the default suites first got a CI leg: the curation suite carries
one `xfail`, and the job went red naming a "dependency not provisioned" that was
a documented order-sensitivity in artist identity. Nothing was broken; the guard
was reading the wrong number.

Usage: assert_tests_ran.py <junit-xml-path>
"""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def main(path: Path) -> int:
    if not path.is_file():
        # pytest writes the file even when every test fails, so its absence means
        # pytest never got far enough to run — a collection error, a bad marker
        # expression, or an install that did not complete.
        print(f"::error::{path} does not exist — pytest never produced a report.")
        return 1

    root = ET.parse(path).getroot()
    # `testsuite` is nested under `testsuites` in pytest's output, but has been
    # the root element in older versions. Handle both rather than assume.
    suites = root.findall(".//testsuite") or ([root] if root.tag == "testsuite" else [])
    if not suites:
        print(f"::error::{path} contains no testsuite element.")
        return 1

    tests = sum(int(s.get("tests", 0)) for s in suites)
    skipped = sum(int(s.get("skipped", 0)) for s in suites)
    failures = sum(int(s.get("failures", 0)) for s in suites)
    errors = sum(int(s.get("errors", 0)) for s in suites)
    ran = tests - skipped

    # The suite attribute counts expected failures alongside real skips, so the
    # cases are walked to tell them apart. An `xfail` carries type
    # "pytest.xfail"; a genuine skip carries "pytest.skip" or, in reports from
    # other tools, no type at all — which is read as a real skip, because the
    # safe direction for an unknown is to fail the job rather than pass it.
    blocking = []
    expected_failures = 0
    for suite in suites:
        for case in suite.iter("testcase"):
            skip = case.find("skipped")
            if skip is None:
                continue
            if skip.get("type") == "pytest.xfail":
                expected_failures += 1
                continue
            name = f"{case.get('classname', '')}::{case.get('name', '')}".lstrip(":")
            blocking.append((name, skip.get("message", "no reason given")))

    # A report whose suite attribute claims skips but carries no `<skipped>` case
    # elements is one this walk cannot classify. Trust the attribute there: a
    # tool that omits the detail must not thereby win a pass.
    if skipped and not blocking and not expected_failures:
        blocking = [("<unnamed>", f"{skipped} skip(s) reported at suite level with no testcase detail")]

    summary = f"collected {tests}, ran {ran}, skipped {len(blocking)}, failed {failures}, errored {errors}"
    if expected_failures:
        summary += f", xfailed {expected_failures}"
    print(summary)

    if tests == 0:
        print("::error::No tests were collected. The marker expression selected nothing.")
        return 1

    if blocking:
        # Named individually — "3 skipped" does not tell you which dependency is
        # missing, and that is the only thing worth knowing here.
        for name, message in blocking:
            print(f"::error::skipped in CI: {name} — {message}")
        print(
            f"::error::{len(blocking)} test(s) skipped. In CI a skip means a dependency was not provisioned "
            "— an absent or expired secret, or a failed install — not a legitimate absence. "
            "This job verified less than it appears to have."
        )
        return 1

    if ran == 0:
        print("::error::Nothing ran.")
        return 1

    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(Path(sys.argv[1])))
