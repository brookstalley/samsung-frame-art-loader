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
the named `pyproject.toml` — needs to resolve rule codes and TOML keys across two
projects and is deliberately not attempted here.

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

#: `tests/…` or `curation/tests/…`, optionally with a `::test_name` node id.
TEST_REFERENCE = re.compile(r"(?:curation/)?tests/[\w/.\-]+\.py(?:::\w+)?")

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
    """Every test path named in the norm index's Enforcement artifact column."""
    return [
        reference
        for row in _norm_index_rows()
        if len(row) > ENFORCEMENT_COLUMN
        for reference in TEST_REFERENCE.findall(row[ENFORCEMENT_COLUMN])
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
