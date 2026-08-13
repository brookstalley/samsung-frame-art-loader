"""The display plane's corpus quotes the name splits curation actually seeds.

**The claim, not the duplication, is what needs guarding.** `display/src/display/
panel/corpus.py` holds real records so the label engine is measured against the
words the wall really carries, and its docstring says the name splits are "the
split the seed table actually stores". The duplication itself is deliberate and
required — the isolation norm forbids display importing curation, and they are
separate projects with separate interpreters — but a promise that two files agree
is worth exactly as much as the thing that checks it.

**Written because that promise has already been broken once, one level down.**
`label_preview.py` carried its own copy of the reference record, kept in step with
the corpus by hand, and the tool and the suite agreed only for as long as somebody
remembered. Moving the corpus into the package closed that gap and opened this
one: the copy is now display-against-curation rather than tool-against-tests, one
seam wider and no better defended.

The consequence is soft and slow, which is why nothing would notice it. The
preview is the only instrument the legibility ruling can be made with, and a
corpus quoting splits the seed table no longer holds is an instrument showing
records that are not on the wall — while every test over it still passes, because
they all read the same stale copy.

This reads both sources rather than importing either, the technique
`test_heartbeat_contract.py` and `test_plane_isolation.py` both use, so it runs
from the repository root with neither plane's environment.
"""

import ast
import pathlib

import pytest

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
CORPUS = REPOSITORY_ROOT / "display" / "src" / "display" / "panel" / "corpus.py"
SEED_TABLE = REPOSITORY_ROOT / "curation" / "src" / "curation" / "seed" / "names.py"

#: The name of curation's lookup, so a rename is a failure here rather than a
#: silently empty comparison.
SEEDED = "SEEDED_NAME_PARTS"


def seeded_name_parts(source: pathlib.Path) -> dict[str, tuple[str | None, str | None]]:
    """Curation's authored split table, read without importing the plane.

    Only the shape that table actually uses is understood — a dict literal of
    string keys to two-tuples of a string or `None`. A row in any other shape is
    left out rather than guessed at, and `test_the_table_was_actually_read`
    below is what stops that silence from passing for agreement.
    """
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    for node in tree.body:
        target = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target = node.target.id
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target = node.targets[0].id
        if target != SEEDED or not isinstance(node.value, ast.Dict):
            continue
        return {
            key.value: tuple(_literal(part) for part in value.elts)
            for key, value in zip(node.value.keys, node.value.values, strict=True)
            if isinstance(key, ast.Constant) and isinstance(key.value, str) and isinstance(value, ast.Tuple)
        }
    return {}


def corpus_records(source: pathlib.Path) -> dict[str, dict[str, str]]:
    """Every module-level record in the display plane's corpus, by its constant's name."""
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    found: dict[str, dict[str, str]] = {}
    for node in tree.body:
        target = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target = node.target.id
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target = node.targets[0].id
        if target is None or not isinstance(node.value, ast.Dict):
            continue
        fields = {
            key.value: value.value
            for key, value in zip(node.value.keys, node.value.values, strict=True)
            if isinstance(key, ast.Constant) and isinstance(key.value, str) and isinstance(value, ast.Constant)
        }
        if fields:
            found[target] = fields
    return found


def _literal(node: ast.expr) -> str | None:
    return node.value if isinstance(node, ast.Constant) else None


def test_both_sources_exist_to_be_compared():
    """The vacuity check: everything below passes trivially over missing files."""
    assert CORPUS.is_file(), f"nothing at {CORPUS} to read the corpus from"
    assert SEED_TABLE.is_file(), f"nothing at {SEED_TABLE} to read the splits from"


def test_the_table_was_actually_read():
    """**The failure this file is most likely to have is silence.**

    A reader that understood none of the rows returns an empty mapping, and every
    comparison below then holds over nothing at all — which is the same green as
    real agreement. Curation's table is authored data with dozens of rows, so any
    small number here means the parse stopped understanding it.
    """
    assert len(seeded_name_parts(SEED_TABLE)) >= 20, "the seed table parsed to almost nothing, so nothing was compared"
    assert corpus_records(CORPUS), "no records were read out of the corpus"


def test_every_corpus_record_that_names_an_artist_quotes_the_seeded_split():
    """The claim itself, over every record that makes it.

    A corpus record is free to hold an artist the seed table says nothing about —
    that is the fallback case, and `MOCHE` is deliberately one of them. What it
    may not do is state a split that disagrees with the authored one, because the
    engine's hardest decisions are all decided by which part of a name leads.
    """
    splits = seeded_name_parts(SEED_TABLE)

    compared = 0
    for name, record in corpus_records(CORPUS).items():
        artist = record.get("artist")
        if artist is None or artist not in splits:
            continue
        family, given = splits[artist]
        compared += 1
        assert record.get("artist_family_name") == family, (
            f"{name} says {artist}'s family name is {record.get('artist_family_name')!r}, " f"and the seed table says {family!r}"
        )
        assert record.get("artist_given_name") == given, (
            f"{name} says {artist}'s given name is {record.get('artist_given_name')!r}, " f"and the seed table says {given!r}"
        )
    assert compared >= 4, f"only {compared} record(s) were checked against the table, so this asserts almost nothing"


def test_a_record_the_table_says_nothing_about_carries_no_split():
    """The other half, and the behaviour a heuristic could not have.

    `MOCHE` is a culture rather than a person and the seed table deliberately
    omits it, so the label falls back to the whole name unstyled. A corpus record
    that invented parts for such a name would be exercising the engine against a
    manifest curation cannot produce.
    """
    splits = seeded_name_parts(SEED_TABLE)

    for name, record in corpus_records(CORPUS).items():
        artist = record.get("artist")
        if artist is None or artist in splits:
            continue
        assert "artist_family_name" not in record and "artist_given_name" not in record, (
            f"{name} splits {artist!r}, which the seed table says nothing about — "
            "so the wall's own manifest would carry no parts for it"
        )


class TestTheGuardCanFail:
    """A check nobody has watched go red is a check nobody knows is wired up."""

    def test_it_catches_a_split_that_drifted(self, tmp_path: pathlib.Path):
        table = tmp_path / "names.py"
        table.write_text('SEEDED_NAME_PARTS: Final[dict] = {"Katsushika Hokusai": ("Hokusai", "Katsushika")}\n')

        assert seeded_name_parts(table)["Katsushika Hokusai"] == ("Hokusai", "Katsushika")

    def test_it_reads_a_row_with_no_parts(self, tmp_path: pathlib.Path):
        """`None` means the record has no such part, and is not a parse failure."""
        table = tmp_path / "names.py"
        table.write_text('SEEDED_NAME_PARTS = {"Moche": (None, None)}\n')

        assert seeded_name_parts(table)["Moche"] == (None, None)

    def test_it_does_not_invent_a_table_that_is_not_there(self, tmp_path: pathlib.Path):
        empty = tmp_path / "empty.py"
        empty.write_text('"""Nothing here."""\n\nOTHER = {"a": ("b", "c")}\n')

        assert seeded_name_parts(empty) == {}

    def test_it_does_not_invent_records_that_are_not_there(self, tmp_path: pathlib.Path):
        empty = tmp_path / "corpus.py"
        empty.write_text('"""Nothing here."""\n\nCOUNT = 3\n')

        assert corpus_records(empty) == {}


@pytest.mark.parametrize("record", ["HOKUSAI", "OKEEFFE", "WRIGHT"])
def test_the_records_the_artifacts_quote_are_still_in_the_corpus(record: str):
    """Pinned by name, because both sides moving together is still a break.

    `accessibility-spec.md` quotes measurements taken against these, and
    `operator-verification.md` sends the operator to `--record` them by hand. A
    rename that updated the corpus and the tests would pass every comparison
    above while orphaning both documents.
    """
    assert record in corpus_records(CORPUS)
