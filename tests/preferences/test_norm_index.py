"""The norm index must not name an enforcement artifact that does not exist.

`project-preferences.md`'s norm index assigns each norm a mechanism and the
artifact that carries it. Nothing checked that those artifacts were real, and
three sessions running, they were not: the broad-except row named ruff rules
selected in neither `pyproject.toml`; the manifest-channel row named
`tests/preferences/test_plane_isolation.py`, a file that has never existed; and
the `T20` row's carve-out list fell three hours behind the config it describes.
Every one was found by accident, by the first person with an unrelated reason to
read the row — which is the definition of a rule with no mechanism.

This is the narrow slice of that guard: **an artifact the index names as a test
must resolve.** The wider check — that a named ruff rule is actually selected in
the named `pyproject.toml` — needs to resolve rule codes and TOML keys across
every plane's config and is deliberately not attempted here. *(This said "across
two projects" until 2026-08-11, written when there were two; the display plane
made it three on 2026-08-06, which is the same staleness the plane derivation
below was added to repair, one paragraph away and unnoticed by the same edit.)*

Scoped to the **Enforcement artifact column**, never the Why column. The Why
column legitimately discusses artifacts that do not exist — the manifest-channel
row's correction names the phantom test precisely to record that it never
existed, and a guard that read prose would fail on the sentence explaining the
bug it exists to prevent.
"""

import ast
import pathlib
import re

import pytest

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
NORM_INDEX = REPOSITORY_ROOT / ".prawduct" / "artifacts" / "project-preferences.md"


#: Every directory in this repository that holds a test tree, as the prefix a
#: reference to one is written with — `""` for the root plane, `curation/`,
#: `display/`.
#:
#: **Derived rather than listed, and that is a repair.** This was written as a
#: literal `(?:curation/)?`, correct on the day it was typed and wrong from
#: 2026-08-06, when the display plane landed with its own suite. The regex is
#: unanchored, so `display/tests/test_epaper.py` did not fail to match — it
#: matched the *tail*, `tests/test_epaper.py`, and resolved against the root
#: plane where no such file exists. A row naming a real, passing display-plane
#: guard therefore failed this file, and the diagnostic pointed at the row rather
#: than at the scanner. That is the third time this index's own machinery has gone
#: stale by carrying a count or a list of planes (see the `black` and `T20` rows
#: in the artifact), which is why the plane set is now computed here instead: a
#: fourth plane is picked up by existing.
def _plane_prefixes() -> list[str]:
    """`""` for the root plane, then one `name/` per plane that has a test tree."""
    nested = sorted(path.parent.name + "/" for path in REPOSITORY_ROOT.glob("*/tests") if path.is_dir())
    return ["", *nested]


#: `tests/…` under any leading path, optionally with a `::test_name` node id, with
#: whatever precedes `tests/` captured as group 1.
#:
#: **The prefix is matched permissively and *checked* separately, rather than being
#: built from the derived plane set.** Deriving the alternation fixed the stale
#: list and left the failure class untouched: the pattern is unanchored, so any
#: prefix the alternation did not know still matched the *tail* and resolved
#: against the root plane. A typo reproduces it exactly — `dispaly/tests/x.py`
#: yields `tests/x.py` and fails with "no such file" naming a plane the row never
#: mentioned, which is the misdirected diagnostic the derivation was written to
#: stop. So does a row written for a plane before its `tests/` directory exists,
#: which this index has done before (the plane-isolation row, named in the module
#: docstring above).
#:
#: A left-boundary lookbehind alone would be the wrong repair on its own: it turns
#: the misdirected failure into a *silent non-match*, and a guard that quietly
#: scans nothing is the failure mode this whole file exists to refuse. So the
#: prefix is allowed to be any number of segments and is then asserted against the
#: derived planes by `test_every_named_enforcement_artifact_names_a_real_plane`,
#: which fails by name.
TEST_REFERENCE = re.compile(r"(?<![\w/.\-])((?:[\w.\-]+/)*)tests/[\w/.\-]+\.py(?:::\w+)?")

#: The dumbest scan that could find a test reference: no prefix, no node id, no
#: lookbehind. It exists only to be compared against `TEST_REFERENCE`, so that a
#: narrowing of that pattern fails as a difference instead of shrinking quietly
#: past the floor below — see `test_the_pattern_finds_every_reference_a_naive_scan_can_see`.
_NAIVE_REFERENCE = re.compile(r"tests/[\w/.\-]+\.py")

#: The index named this many test artifacts when the guard was written. The
#: assertion is `>=`, not `==`: adding a Test row must not fail this file, but a
#: refactor that empties the column must not leave it green either. A regex that
#: silently stops matching is exactly how this guard would rot into a test that
#: passes over nothing — the failure mode the norm index itself keeps hitting.
MINIMUM_KNOWN_REFERENCES = 3

#: The table is located by its header, not by counting cells. Shape-matching
#: ("any row with five cells") silently skips a row it does not recognise, and a
#: single inline pipe in any cell would drop that row from the scan while the
#: floor below stayed satisfied — a Test row going unchecked with the suite green.
#: Anchoring on the header means an unexpected row shape *fails* instead.
NORM_INDEX_HEADER = "| Preference / norm | Mechanism | Enforcement artifact | Audit home | Why |"

ENFORCEMENT_COLUMN = 2
EXPECTED_COLUMNS = 5

#: A floor on rows. It covers what the contiguity check structurally cannot:
#: **bottom-truncation** — rows deleted off the end leave the span unbroken, so
#: every line still starts with `|` and only the count falls. Do not delete this
#: constant on the reasoning that the exact check subsumes it; it does not.
#:
#: A floor does decay — at twenty rows a truncation of five still clears fifteen
#: — which is why it is not the primary guard. An earlier version of this comment
#: claimed it "does NOT carry the early-break check any more", written when the
#: contiguity check was believed to cover every break. It did not cover the
#: blank-line form, and for a while this constant was the only thing that did,
#: while its own comment disclaimed the job. That is the under-claiming failure
#: this repo has a learning about, committed in the comment announcing the fix.
MINIMUM_KNOWN_ROWS = 15


def _lines_after_the_header() -> tuple[list[str], int]:
    """Every line of the artifact, plus the index of the norm index's header row.

    Shared so the header's absence produces one diagnostic rather than a bare
    `ValueError` from whichever caller looked it up without checking.
    """
    lines = [line.rstrip() for line in NORM_INDEX.read_text(encoding="utf-8").splitlines()]
    if NORM_INDEX_HEADER not in lines:
        raise AssertionError(
            f"{NORM_INDEX.name} has no norm index header matching:\n  {NORM_INDEX_HEADER}\n"
            "The table moved or its columns were renamed, and this guard can no longer find it. "
            "Fix the anchor deliberately rather than letting the guard scan nothing."
        )
    return lines, lines.index(NORM_INDEX_HEADER)


def _norm_index_rows() -> list[list[str]]:
    """The norm index's data rows, located by its header and ended by the table."""
    lines, header = _lines_after_the_header()
    rows: list[list[str]] = []
    for line in lines[header + 1 :]:
        if not line.startswith("|"):
            break  # the table ended
        body = line.strip().strip("|")
        # `|` belongs in this set: `.strip("|")` removes only the outer pipes, so
        # the separator arrives as `---|---|---|---|---` and still carries the
        # inner ones. Omitting it made this branch dead code — the separator was
        # returned as a data row, harmless only because it happens to split into
        # five `---` cells, while every row number below counted from it.
        if set(body) <= set("-:| "):
            continue  # the header separator
        rows.append([cell.strip() for cell in body.split("|")])
    return rows


def _enforcement_artifacts() -> list[str]:
    """Every test path named in the norm index's Enforcement artifact column.

    `finditer` rather than `findall` because the pattern captures the plane
    prefix: `findall` would return the group and throw the reference away.
    """
    return [
        match.group(0)
        for row in _norm_index_rows()
        if len(row) > ENFORCEMENT_COLUMN
        for match in TEST_REFERENCE.finditer(row[ENFORCEMENT_COLUMN])
    ]


def test_every_norm_index_row_has_the_shape_the_parser_assumes():
    """An unreadable row must fail loudly, never drop silently out of the scan.

    A cell containing an inline `|` splits into an extra column and shifts every
    cell after it. The Enforcement artifact would then be read from the wrong
    column — or, under the shape-matching this parser replaced, the row would
    vanish from the scan entirely and take its Test claim with it, leaving the
    suite green over a row nobody checked.
    """
    malformed = [(index, row) for index, row in enumerate(_norm_index_rows(), start=1) if len(row) != EXPECTED_COLUMNS]
    assert not malformed, (
        f"norm index rows must have exactly {EXPECTED_COLUMNS} columns; these do not "
        f"(likely an unescaped `|` inside a cell): "
        + "; ".join(f"row {index} has {len(row)}: {row[0][:60]!r}" for index, row in malformed)
    )


def test_the_table_runs_unbroken_from_its_header():
    """Detect an early break exactly, rather than inferring it from a row count.

    `_norm_index_rows()` stops at the first line that does not start with `|`, so
    a stray line inside the table silently discards every row below it. A floor
    only notices while the table is small — at twenty rows, dropping five still
    clears fifteen. This reads the same span the parser walks and fails on every
    shape that can split the table — a blank, a stray line, or a sub-heading —
    while still allowing the blank that genuinely ends it, so the check
    does not weaken as the index grows.
    """
    lines, header = _lines_after_the_header()
    separated = False
    for offset, line in enumerate(lines[header + 1 :]):
        number = header + 2 + offset
        if not line:
            separated = True  # legitimate if the table is over; fatal if it is not
            continue
        # Only a blank line can end this table, so prose or a heading is a
        # terminator *after* one and a stray line *before* one. An earlier
        # version broke on any `#` unconditionally, which meant a sub-heading
        # dropped between two rows stopped this walk and the parser at the same
        # line — reintroducing, for headings, the exact silent discard the blank
        # handling above had just closed.
        if separated and not line.startswith("|"):
            break  # blank, then something that is not a row: the table is over
        assert line.startswith("|"), (
            f"line {number} sits inside the norm index but does not start with `|`, "
            f"so every row below it is dropped from the scan: {line[:70]!r}"
        )
        assert not separated, (
            f"line {number} is a table row cut off from the norm index by a blank line above it. "
            "The parser stops at that blank, so this row and everything below it go unchecked "
            f"while the suite stays green: {line[:70]!r}"
        )


def test_the_header_separator_is_not_returned_as_a_row():
    """The separator branch needs its own test; no data-row mutation can reach it.

    This existed as dead code once. `.strip("|")` removes only the outer pipes, so
    the separator still contains the inner ones and the character-set check that
    was meant to recognise it never matched — it was returned as a data row,
    invisible because it splits into exactly five `---` cells that name no
    artifact. Mutating a *data* row exercises the shape check and never this
    branch, so the guard has to name the separator directly.

    Note what each half of this test can and cannot catch. The dashes-only check
    is a strict subset of the parser's skip set, so it is vacuous over any real
    file — it is a regression guard on the predicate, and fails only if that is
    edited back. The second assertion is the one that observes parsed output: a
    norm row always names a norm, so every row must carry an alphanumeric.
    """
    rows = _norm_index_rows()
    dashes_only = [row for row in rows if all(set(cell) <= set("-: ") for cell in row)]
    assert not dashes_only, f"the header separator leaked into the parsed rows: {dashes_only}"

    unnamed = [row for row in rows if not any(character.isalnum() for character in row[0])]
    assert not unnamed, f"every norm row names a norm; these rows have no name: {unnamed}"


def test_the_index_still_has_all_its_rows():
    """A row floor, because the reference floor cannot see a row vanish."""
    rows = _norm_index_rows()
    assert len(rows) >= MINIMUM_KNOWN_ROWS, (
        f"expected at least {MINIMUM_KNOWN_ROWS} norm rows, parsed {len(rows)}. Rows are dropped "
        "silently when a line inside the table does not start with `|` — the scan stops there and "
        "everything below it goes unchecked."
    )


def test_the_index_still_names_test_artifacts_at_all():
    """Guards the guard: an extraction that matches nothing must not read as a pass."""
    found = _enforcement_artifacts()
    assert len(found) >= MINIMUM_KNOWN_REFERENCES, (
        f"expected at least {MINIMUM_KNOWN_REFERENCES} test artifacts in the norm index's "
        f"Enforcement column, found {len(found)}: {found}. Either the column was emptied "
        "or the table's shape moved out from under this parser."
    )


def test_the_pattern_finds_every_reference_a_naive_scan_can_see():
    """Guards the guard against scanning *less*, which the floor above cannot see.

    `MINIMUM_KNOWN_REFERENCES` catches an extraction that collapses to nothing. It
    cannot catch one that collapses partway: narrow `TEST_REFERENCE` so it stops
    matching prefixed references and the curation and display rows vanish while the
    root-plane ones still clear a floor of three — the suite green over exactly the
    rows the 2026-08-11 plane repair was written to protect. That is the
    `test_plane_isolation.py` incident (a row naming a file that never existed, live
    for months) arriving by a second route.

    So this compares the compiled pattern against the dumbest scan that could work.
    `_NAIVE_REFERENCE` has no prefix group, no node-id tail and no lookbehind, and
    every string it can find is one `TEST_REFERENCE` must also find — the compiled
    match starts earlier and ends later over the same `tests/….py`. A count that
    disagrees means the pattern was narrowed, and it fails by the difference rather
    than by a number somebody has to maintain. Raising the floor by hand each time a
    row is added is the maintained-count shape the plane derivation was written to
    retire; this is the same reasoning applied to the other axis.
    """
    cells = [row[ENFORCEMENT_COLUMN] for row in _norm_index_rows() if len(row) > ENFORCEMENT_COLUMN]
    naive = [match.group(0) for cell in cells for match in _NAIVE_REFERENCE.finditer(cell)]
    found = _enforcement_artifacts()

    missed = sorted(set(naive) - {reference[reference.index("tests/") :].split("::")[0] for reference in found})
    assert not missed, (
        f"a naive scan of the Enforcement column finds {len(naive)} test references and "
        f"TEST_REFERENCE finds {len(found)}; these are visible to the dumb scan and not to the "
        f"compiled one: {missed}. The pattern was narrowed and is now scanning less than the "
        "index names — the failure this file exists to refuse, arriving as a shrink rather than "
        "as a zero."
    )


@pytest.mark.parametrize("reference", _enforcement_artifacts())
def test_every_named_enforcement_artifact_names_a_real_plane(reference):
    """A reference under an unknown plane must fail by name, never by its tail.

    This is the half of the 2026-08-11 repair that the derived plane set did not
    buy on its own. `TEST_REFERENCE` matches the prefix permissively, so a typo
    (`dispaly/tests/test_epaper.py`) or a plane whose `tests/` directory does not
    exist yet arrives here intact instead of being silently truncated to
    `tests/test_epaper.py` and reported as missing from the root plane — a
    diagnostic that names a plane the row never mentioned and sends the reader to
    the wrong file. The sibling test below then answers the different question of
    whether the file is there.
    """
    prefix = reference[: reference.index("tests/")]
    planes = _plane_prefixes()
    assert prefix in planes, (
        f"the norm index names {reference}, whose plane prefix {prefix!r} is not a test tree in "
        f"this repository. Known planes: {planes}. Either the prefix is misspelled, or the plane "
        "exists without a `tests/` directory — in which case the row is naming a mechanism that "
        "cannot run yet."
    )


@pytest.mark.parametrize("reference", _enforcement_artifacts())
def test_every_named_enforcement_artifact_resolves(reference):
    """A named file must exist, and a named `::test` must be defined in it."""
    path_text, _, test_name = reference.partition("::")
    path = REPOSITORY_ROOT / path_text

    assert path.is_file(), (
        f"the norm index names {reference} as an enforcement artifact and no such file exists. "
        "Either the artifact moved and the row did not, or the row claims a mechanism it "
        "never had — which this index has done before."
    )
    if not test_name:
        return

    defined = {
        node.name
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert test_name in defined, (
        f"the norm index names {reference}, but {path_text} defines no {test_name}. "
        f"It defines: {sorted(name for name in defined if name.startswith('test_'))}"
    )


# -- the guards the index deliberately does NOT name ----------------------------


#: The header of the "Deliberately uncovered" table, which records guards ruled
#: *not* to be norm enforcement. Anchored on its own header for the same reason
#: the norm index is: a table this guard cannot find is a table it scans nothing
#: of, and that reads identically to passing.
UNCOVERED_HEADER = "| Guard | Ruling (owner, 2026-08-06) | Reasoning |"


def _deliberately_uncovered_artifacts() -> list[str]:
    """Every test reference named in the deliberately-uncovered table's Guard column.

    A separate parser rather than a widened one, because the two tables answer
    opposite questions and must not be able to absorb each other's rows: the norm
    index says "this guard enforces a stated norm", and this table says "this
    guard exists and is deliberately not that".
    """
    lines = [line.rstrip() for line in NORM_INDEX.read_text(encoding="utf-8").splitlines()]
    assert UNCOVERED_HEADER in lines, (
        f"{NORM_INDEX.name} has no deliberately-uncovered table matching:\n  {UNCOVERED_HEADER}\n"
        "It moved or its columns were renamed. Fix the anchor deliberately rather than letting "
        "this guard scan nothing."
    )
    found: list[str] = []
    for line in lines[lines.index(UNCOVERED_HEADER) + 1 :]:
        if not line.startswith("|"):
            break
        body = line.strip().strip("|")
        if set(body) <= set("-:| "):
            continue
        # `finditer` and `group(0)` for the same reason as the sibling parser: the
        # pattern captures the plane prefix, so `findall` returns that group and
        # discards the reference it was found in.
        found.extend(match.group(0) for match in TEST_REFERENCE.finditer(body.split("|")[0]))
    return found


@pytest.mark.parametrize("reference", _deliberately_uncovered_artifacts())
def test_every_deliberately_uncovered_guard_still_exists(reference):
    """A ruling about a guard is worth nothing once the guard is gone.

    The "Deliberately uncovered" table records the owner's decision that four
    mechanical guards are *not* stated norms. That section says plainly that a
    guard listed there is still a guard — so a rename or a deletion leaves a
    ruling about nothing, and the next Norm Health sweep re-asks a question whose
    subject no longer exists.

    The sibling check above walks the norm index only: its parser stops at the
    blank line ending that table, so it never saw these three. That is the same
    rename-with-nothing-noticing exposure this file exists to close, reappearing
    one heading further down the same document.
    """
    path_text, _, test_name = reference.partition("::")
    path = REPOSITORY_ROOT / path_text

    assert path.is_file(), (
        f"the deliberately-uncovered table names {reference} and no such file exists. "
        "Either the guard moved and the ruling did not, or the guard was deleted — and a "
        "recorded decision not to cover something that no longer exists is worse than silence."
    )
    if not test_name:
        return

    defined = {
        node.name
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert test_name in defined, f"the deliberately-uncovered table names {reference}, but {path_text} defines no {test_name}."


def test_the_deliberately_uncovered_table_is_not_empty():
    """A parametrised guard over an empty list passes by running nothing at all."""
    assert _deliberately_uncovered_artifacts(), (
        "no test references found in the deliberately-uncovered table — either its Guard column "
        "stopped naming files, or the parser above no longer finds the table it names"
    )
