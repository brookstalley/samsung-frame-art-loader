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

    print(f"collected {tests}, ran {ran}, skipped {skipped}, failed {failures}, errored {errors}")

    if tests == 0:
        print("::error::No tests were collected. The marker expression selected nothing.")
        return 1

    if skipped:
        # Named individually — "3 skipped" does not tell you which dependency is
        # missing, and that is the only thing worth knowing here.
        for suite in suites:
            for case in suite.iter("testcase"):
                skip = case.find("skipped")
                if skip is not None:
                    name = f"{case.get('classname', '')}::{case.get('name', '')}".lstrip(":")
                    print(f"::error::skipped in CI: {name} — {skip.get('message', 'no reason given')}")
        print(
            f"::error::{skipped} test(s) skipped. In CI a skip means a dependency was not provisioned "
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
