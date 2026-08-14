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

#: Curation's other authored lookup, for the same reason: a rename should fail
#: here rather than quietly compare nothing.
SHORTENED = "SEEDED_DISPLAY_NATIONALITIES"


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
            key.value: (_literal(value.elts[0]), _literal(value.elts[1]))
            for key, value in zip(node.value.keys, node.value.values, strict=True)
            if isinstance(key, ast.Constant) and isinstance(key.value, str) and isinstance(value, ast.Tuple)
            # **The arity is part of the shape this reader models.** Callers
            # unpack two names, so a row of any other length has to be left out
            # here rather than raising there — a reader that half-understands a
            # row reports a broken test instead of a table it does not model.
            and len(value.elts) == 2
        }
    return {}


def seeded_display_nationalities(source: pathlib.Path) -> dict[str, str]:
    """Curation's authored short-nationality table, read without importing the plane.

    A flat dict of string to string, so the reader is simpler than the split one
    above and fails the same way: a row it does not understand is left out, and
    the vacuity check is what stops that reading as agreement.
    """
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    for node in tree.body:
        target = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target = node.target.id
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target = node.targets[0].id
        if target != SHORTENED or not isinstance(node.value, ast.Dict):
            continue
        return {
            key.value: value.value
            for key, value in zip(node.value.keys, node.value.values, strict=True)
            if isinstance(key, ast.Constant)
            and isinstance(key.value, str)
            and isinstance(value, ast.Constant)
            and isinstance(value.value, str)
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
    assert seeded_display_nationalities(SEED_TABLE), "the short-nationality table parsed to nothing"


def test_every_corpus_record_quotes_the_nationality_the_manifest_would_carry():
    """**The same claim as the split, one field over, and it drifts the same way.**

    Curation resolves the short form when it builds the manifest, so what reaches
    this plane for an artist the table covers is the short string and never the
    recorded one. A corpus record still quoting the institution's prose would be
    measuring the label against a line the wall stopped carrying — and every test
    over that corpus would stay green, because they all read the same copy.

    Records the table says nothing about are the fallback case and are skipped:
    their nationality is whatever the catalogue holds, which this file has no way
    to know and no business asserting.
    """
    shortened = seeded_display_nationalities(SEED_TABLE)

    compared = 0
    for name, record in corpus_records(CORPUS).items():
        artist = record.get("artist")
        if artist is None or artist not in shortened:
            continue
        compared += 1
        assert record.get("artist_nationality") == shortened[artist], (
            f"{name} sets {artist}'s nationality as {record.get('artist_nationality')!r}, "
            f"and the manifest would carry {shortened[artist]!r}"
        )
    assert compared, "no corpus record covers an artist the short-nationality table carries"


def test_every_corpus_record_that_names_an_artist_quotes_the_seeded_split():
    """The claim itself, over every record that makes it.

    A corpus record is free to hold an artist the seed table says nothing about —
    that is the fallback case, and the test below covers it. What no record may
    do is state a split that disagrees with the authored one, because the
    engine's hardest decisions are all decided by which part of a name leads.

    **`MOCHE` is compared here like any other record, not exempted.** The table
    carries it as `(None, None)` — a culture has no family name, which is an
    authored answer rather than a silence — so the corpus stating no parts for
    it is the agreement being checked, and inventing one would fail here.
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
    """The other half: an artist absent from the table gets no parts invented.

    **A forward guard rather than a live one, and saying so is the point.**
    Every artist the corpus names is currently in the seed table — `Moche` among
    them, carried as `(None, None)`, which is the table stating that a culture
    has no family name rather than the table being silent. That row is compared
    by the test above like any other. What this covers is the case where a
    corpus record names somebody the table has never heard of: the label falls
    back to the whole name unstyled, and a record that invented parts would be
    exercising the engine against a manifest curation cannot produce.

    An empty loop body here is therefore the expected state, not a gap.
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

    def test_a_row_of_the_wrong_arity_is_left_out_rather_than_raising(self, tmp_path: pathlib.Path):
        """The reader skips what it does not model, rather than handing a row it
        half-understands to a caller that unpacks two names from it."""
        table = tmp_path / "names.py"
        table.write_text('SEEDED_NAME_PARTS = {"Three Parts": ("A", "B", "C"), "Two Parts": ("D", "E")}\n')

        assert seeded_name_parts(table) == {"Two Parts": ("D", "E")}


def corpus_keys(source: pathlib.Path) -> set[str]:
    """The names `--record` takes, out of the `CORPUS` tuple's own first elements.

    **The key, not the constant, is what the documents quote.** A record is
    declared as `HOKUSAI` and selected as `--record hokusai`, and the two are
    written down in different places — so a pin over the constants alone would
    hold while every command an operator has been given stopped working.
    """
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    for node in tree.body:
        target = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target = node.target.id
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target = node.targets[0].id
        if target != "CORPUS" or not isinstance(node.value, ast.Tuple):
            continue
        return {
            pair.elts[0].value
            for pair in node.value.elts
            if isinstance(pair, ast.Tuple) and pair.elts and isinstance(pair.elts[0], ast.Constant)
        }
    return set()


#: The records the documents send a human to by hand, as `(constant, --record
#: key)`. Both halves are pinned because they are written down separately:
#: `accessibility-spec.md` quotes measurements taken against the constants, while
#: `deploy/README.md` and `operator-verification.md` give the operator commands
#: naming the keys. A rename that updated the corpus and this suite together
#: would pass every comparison above and orphan whichever half it missed.
#:
#: **Every key the queue entries name, not a sample of them.** A pin that covered
#: most of them would fail in exactly the way it exists to prevent, and the three
#: sparse records are the ones a tidying pass is likeliest to rename — they are
#: also the ones whose questions nothing else can ask.
#:
#: **`kandinsky` was the one it missed, which is the shape of failure this comment
#: was already describing.** The list said "every key the queue entries name" and
#: covered seven of eight; the sitting queued on 2026-08-13 sends the operator to
#: draw `kandinsky` by name, and it is the record that motivated
#: `display_nationality` at all. A claim of completeness is only worth the
#: enumeration under it, so `test_every_corpus_key_is_pinned` below now derives
#: the completeness rather than leaving it to this comment.
QUOTED_BY_THE_ARTIFACTS = (
    ("HOKUSAI", "hokusai"),
    ("OKEEFFE", "okeeffe"),
    ("WRIGHT", "wright"),
    ("MOCHE", "moche"),
    ("KANDINSKY", "kandinsky"),
    ("UNATTRIBUTED", "unattributed"),
    ("NATIONALITY_ONLY", "nationality-only"),
    ("ANONYMOUS", "anonymous"),
)


@pytest.mark.parametrize(("constant", "key"), QUOTED_BY_THE_ARTIFACTS)
def test_the_records_the_artifacts_quote_are_still_in_the_corpus(constant: str, key: str):
    assert constant in corpus_records(CORPUS), f"{constant} is quoted by the artifacts and is no longer declared"
    assert key in corpus_keys(CORPUS), f"--record {key} is a documented command and the corpus no longer offers it"


def test_every_corpus_key_is_pinned():
    """**The completeness the comment above claims, derived rather than asserted
    in prose.**

    That comment said "every key the queue entries name" while the list held seven
    of eight — `kandinsky` was missing, and it is the record a queued sitting names
    and the one that motivated a catalogue field. A sentence cannot notice a new
    record; this can.

    Pinning *every* key rather than only the documented ones is the deliberate
    stronger rule: this corpus exists so a human can look at its records, so a
    record nothing sends anybody to is either about to be documented or should not
    be here. Either way a rename should stop and be looked at.
    """
    pinned = {key for _, key in QUOTED_BY_THE_ARTIFACTS}

    assert corpus_keys(CORPUS) - pinned == set(), "a corpus record is not pinned, so a rename of it would go unnoticed"


def test_the_corpus_keys_were_actually_read():
    """The vacuity guard for the pin above: an unparsed `CORPUS` yields nothing,
    and `x in set()` would then fail loudly rather than silently — but a *typo*
    in this reader would make every key look missing, which reads as a rename."""
    assert len(corpus_keys(CORPUS)) >= 8, "the CORPUS tuple parsed to almost nothing, so the keys were never checked"
