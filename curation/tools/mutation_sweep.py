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

`mutations.json` is a list of objects with `label`, `file` (relative to the
curation project root), `find` and `replace`. `find` must appear in the file; a
mutation whose pattern has drifted is reported rather than silently skipped,
because a sweep that quietly tests nothing is worse than no sweep.

**Write mutations that change behaviour, and check that yours did.** A `replace`
that only edits a comment, adds a `# noqa`, or renames an unused local cannot
fail any test, so it always survives — and a survivor is exactly what a real
finding looks like. Nothing here can tell the two apart: from the outside, "no
test covers this branch" and "this mutation was never a defect" are the same
green run. Two of the first five mutations written against the review surface
were this, and both were investigated as findings before the mistake was
spotted. If a survivor surprises you, confirm the mutation actually breaks
something before you go writing a test for it.

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


def load(path: pathlib.Path) -> list[Mutation]:
    try:
        described = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise SweepError(f"could not read mutations from {path}: {exc}") from exc
    try:
        return [Mutation(**entry) for entry in described]
    except TypeError as exc:
        raise SweepError(f"a mutation in {path} is missing a field or has an extra one: {exc}") from exc


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
        completed = subprocess.run(
            ["uv", "run", "pytest", *targets, "-q", "-x", "--no-header", "-p", "no:cacheprovider"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            # See the module docstring: without this a same-second rewrite of
            # equal length runs against stale bytecode and reports a false
            # survivor.
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            check=False,
        )
    finally:
        shutil.move(backup, path)
    return completed.returncode != 0


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
    try:
        mutations = load(pathlib.Path(argv[0]))
        return sweep(mutations, argv[1:])
    except SweepError as exc:
        # Distinct from a survivor, and it must not be mistaken for one: this
        # means the sweep did not measure what it claimed to. Hence the separate
        # exit code as well as the separate stream.
        say(f"the sweep is misconfigured: {exc}", error=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
