"""Break each branch on purpose, and report the ones no test noticed.

A green suite says nothing about a branch no test reaches. This applies one
deliberate defect at a time, runs a chosen slice of the suite, and reports every
mutation that survived — each survivor being a line you could delete without a
test objecting.

**Run it on the branches a chunk adds, before believing they are covered.** It
has found something on every chunk it has been run on: a listing whose rows all
claimed the same picture, an action with no test over the wire at all, guards
whose only defence was that nothing had tried.

Usage:

    uv run python tools/mutation_sweep.py mutations.json tests/unit/test_thing.py

    # An opt-in suite needs its marker, or pytest collects nothing:
    uv run python tools/mutation_sweep.py m.json tests/browser/test_x.py -- -m browser

`mutations.json` is a list of objects with `label`, `file` (relative to the
curation project root), `find` and `replace`. `find` must appear in the file; a
mutation whose pattern has drifted is reported rather than silently skipped,
because a sweep that quietly tests nothing is worse than no sweep.

Everything after a `--` is handed to pytest verbatim.

**The chosen tests are run once, unmutated, before anything is swept, and the
sweep refuses to start unless they run and pass.** That guard is the reason this
paragraph exists: every opt-in suite here — browser, the three live markers, the
evaluation one — is deselected by a marker expression in `pyproject.toml`'s
`addopts`, and naming such a test on the command line does *not* select it.
pytest then collects nothing and exits 5, which the old verdict (`returncode !=
0`) read as the mutation having been caught. A twenty-one mutation sweep of the
review grid reported every one caught by runs that executed no test at all —
indistinguishable from a real pass, and strictly worse than never sweeping.
Anything other than a pass or a failure now stops the sweep and says so.

**Write mutations that change behaviour, and check that yours did.** A `replace`
that only edits a comment, adds a `# noqa`, or renames an unused local cannot
fail any test, so it always survives — and a survivor is exactly what a real
finding looks like. Nothing here can tell the two apart: from the outside, "no
test covers this branch" and "this mutation was never a defect" are the same
green run. Two of the first five mutations written against the review surface
were this, and both were investigated as findings before the mistake was
spotted. If a survivor surprises you, confirm the mutation actually breaks
something before you go writing a test for it.

**A killed sweep leaves the source mutated, and git will happily commit it.**
The restore runs in a `finally`, which handles an exception and a Ctrl-C and does
*not* handle SIGKILL — so a sweep cut short by an outer timeout leaves the target
file carrying its mutation and a `.sweepbak` sitting beside it. The next run then
reports `pattern is not in <file> any more`, which reads like mutation drift and
is actually the tool telling you the tree is dirty. **If a sweep is killed, restore
from the `.sweepbak` before doing anything else** — `git status` shows the stray
backup, and `git diff` shows a change you did not write. Give a sweep a timeout it
can finish inside: one mutation costs a full run of the target tests, so budget
`(mutations + 1) x suite time`.

**Bytecode caching is disabled for the child runs, and that is not a detail.**
This rewrites a source file, runs pytest, and restores it, often several times a
second. CPython decides a `.pyc` is current by comparing the source's
`(mtime, size)`, both at one-second resolution — so a mutation that changes a
line's length not at all (`30` to `40`) inside the same second is invisible, the
stale bytecode is loaded, and the mutation never runs. That reports as SURVIVED,
which is indistinguishable from a real finding and sends you writing a test for
a branch that was already covered. Setting `PYTHONDONTWRITEBYTECODE` in the child
environment removes the cache from the question entirely.
"""

import json
import os
import pathlib
import shutil
import subprocess
import sys
from dataclasses import dataclass

#: The curation project root — this file lives in `tools/` directly beneath it.
ROOT = pathlib.Path(__file__).resolve().parent.parent


@dataclass(frozen=True, slots=True)
class Mutation:
    """One deliberate defect, and where to introduce it."""

    label: str
    file: str
    find: str
    replace: str


class SweepError(RuntimeError):
    """The sweep itself is wrong — a missing file, a pattern that no longer matches."""


#: pytest's own exit codes, for the two this tool can interpret and the one that
#: silently ruined a whole sweep. 0 is a passing run — the mutation survived — and
#: 1 is a failing one, which is a mutation caught. **5 is "no tests were
#: collected", and it is not a caught mutation**: it is the sweep testing nothing
#: at all and reporting success for every line of it.
PASSED, FAILED, NO_TESTS = 0, 1, 5


def load(path: pathlib.Path) -> list[Mutation]:
    try:
        described = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise SweepError(f"could not read mutations from {path}: {exc}") from exc
    try:
        return [Mutation(**entry) for entry in described]
    except TypeError as exc:
        raise SweepError(f"a mutation in {path} is missing a field or has an extra one: {exc}") from exc


def run_tests(targets: list[str]) -> subprocess.CompletedProcess[str]:
    """Run the chosen slice of the suite. One place, so the sweep and its baseline agree.

    They must be the identical invocation: a baseline that ran a different command
    from the mutated runs would vouch for a suite the sweep never executes.
    """
    return subprocess.run(
        # `-n0` FIRST, so a caller's own `-n` in the passthrough still wins.
        #
        # It is not an optimisation, it is what makes the verdict readable. With
        # `-x` under xdist a failing test ends the session as INTERRUPTED and
        # pytest exits **2**, not 1 — so every *caught* mutation looked like the
        # unclassifiable exit this tool refuses to guess at, and a sweep aborted
        # on its first real catch saying it was misconfigured. `-n auto` is in
        # this project's `addopts`, so that was the default path.
        #
        # Serial costs nothing worth having here: a sweep runs the same narrow
        # slice `(mutations + 1)` times, where per-run worker startup is most of
        # the bill — measured at 67s serial against 65s parallel for ten
        # mutations over two files.
        ["uv", "run", "pytest", "-n0", *targets, "-q", "-x", "--no-header", "-p", "no:cacheprovider"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        # See the module docstring: without this a same-second rewrite of equal
        # length runs against stale bytecode and reports a false survivor.
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        check=False,
    )


def check_baseline(targets: list[str]) -> None:
    """Refuse to sweep unless the chosen tests actually run, and pass, unmutated.

    **This is the guard that was missing, and its absence made a whole sweep read
    green while executing nothing.** Every opt-in suite in this project — browser,
    the three live markers, the evaluation one — is deselected by a marker
    expression in `pyproject.toml`'s `addopts`. Naming such a test on the command
    line does not select it: pytest collects nothing, exits 5, and the old
    `returncode != 0` read that as the mutation having been caught. Twenty-one
    mutations reported caught by a run that never executed a line of the file
    they were applied to, which is indistinguishable from a real pass and is
    strictly worse than no sweep at all.

    An already-failing target set is refused for the same reason one step along:
    every mutation would be "caught" by the failure that was there before it.
    """
    completed = run_tests(targets)
    if completed.returncode == NO_TESTS:
        raise SweepError(
            f"pytest collected no tests from {' '.join(targets)}, so a sweep over them would report "
            "every mutation as caught while executing nothing.\n"
            "If these carry an opt-in marker — the browser and the three live suites all do — pass it "
            "through after a `--`:\n"
            "    uv run python tools/mutation_sweep.py mutations.json tests/browser/test_x.py -- -m browser"
        )
    if completed.returncode != PASSED:
        raise SweepError(
            f"the chosen tests do not pass before anything is mutated (pytest exit {completed.returncode}), "
            "so every mutation would be reported as caught by a failure that was already there. Fix the "
            f"suite first.\n{completed.stdout[-2000:]}"
        )


def apply_and_run(mutation: Mutation, targets: list[str]) -> bool:
    """Introduce the defect, run the tests, put the file back. True if a test caught it.

    The file is restored in a `finally`, so an interrupted sweep does not leave a
    deliberate defect in the working tree — which would otherwise be discovered
    later as a mysterious failing test, or worse, committed.
    """
    path = ROOT / mutation.file
    if not path.is_file():
        raise SweepError(f"{mutation.label}: {path} does not exist")
    original = path.read_text()
    found = original.count(mutation.find)
    if found == 0:
        raise SweepError(
            f"{mutation.label}: its pattern is not in {mutation.file} any more. "
            "Update the mutation — a sweep that skips is a sweep that passes."
        )
    if found > 1:
        # Ambiguity is refused rather than resolved by taking the first match.
        # Two functions in one module can easily share a guard — `if not
        # listing.truncated: return None` appeared in both a catalogue listing
        # and an image listing — and mutating the wrong one tests a branch you
        # were not asking about, against a target set chosen for the one you
        # were. The result is a survivor that is nobody's real coverage gap, and
        # it reads exactly like one.
        raise SweepError(
            f"{mutation.label}: its pattern appears {found} times in {mutation.file}, so which one "
            "would be mutated is not decidable. Extend `find` until it is unique — a mutation that "
            "lands somewhere other than where you meant reports on a branch you did not choose."
        )

    backup = path.with_suffix(path.suffix + ".sweepbak")
    shutil.copy(path, backup)
    try:
        path.write_text(original.replace(mutation.find, mutation.replace, 1))
        completed = run_tests(targets)
    finally:
        shutil.move(backup, path)
    if completed.returncode not in (PASSED, FAILED):
        # Every other exit code means the run did not answer the question. 5 is
        # the one that made this necessary — everything deselected — but a usage
        # error or an internal error would equally have read as a caught mutation
        # under a bare `returncode != 0`, which is a verdict reached from a run
        # that never tested anything.
        raise SweepError(
            f"{mutation.label}: pytest exited {completed.returncode}, which is neither a pass nor a "
            f"failure, so whether this mutation was caught is unknown.\n{completed.stdout[-2000:]}"
        )
    return completed.returncode == FAILED


def say(message: str = "", *, error: bool = False) -> None:
    """Everything this tool tells its operator, through one waived call.

    The `logging` only / `print()` norm reserves printing for deliberate CLI
    output and requires the waiver per line rather than per file, so that the
    reason sits beside the call instead of in a table a reader has to remember.
    Funnelling every message through here means the project carries exactly one
    such waiver for this tool, and nothing else in it can print by accident.

    Flushed on every call because a sweep runs for minutes and its per-mutation
    lines are progress, not a summary — buffered, they would all arrive at the
    end and the operator would have no way to tell a slow run from a hung one.
    """
    print(message, file=sys.stderr if error else sys.stdout, flush=True)  # noqa: T201 -- this tool's report IS its output


def sweep(mutations: list[Mutation], targets: list[str]) -> int:
    check_baseline(targets)
    survivors = []
    for mutation in mutations:
        caught = apply_and_run(mutation, targets)
        say(f"{'caught   ' if caught else 'SURVIVED '} {mutation.label}")
        if not caught:
            survivors.append(mutation.label)

    say()
    if not survivors:
        say(f"every one of {len(mutations)} mutations was caught")
        return 0
    say(f"{len(survivors)} of {len(mutations)} mutations survived — these branches are undefended:")
    for label in survivors:
        say(f"  - {label}")
    return 1


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        say(__doc__ or "")
        return 2
    # Everything after a `--` goes to pytest verbatim, which is how an opt-in
    # suite is reached: `-m browser` and friends cannot be inferred from a path,
    # and inferring them would be this tool deciding which tests the operator
    # meant. Without a `--` the whole tail is target paths, as before.
    targets, passthrough = argv[1:], []
    if "--" in targets:
        cut = targets.index("--")
        targets, passthrough = targets[:cut], targets[cut + 1 :]
    try:
        mutations = load(pathlib.Path(argv[0]))
        return sweep(mutations, [*targets, *passthrough])
    except SweepError as exc:
        # Distinct from a survivor, and it must not be mistaken for one: this
        # means the sweep did not measure what it claimed to. Hence the separate
        # exit code as well as the separate stream.
        say(f"the sweep is misconfigured: {exc}", error=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
