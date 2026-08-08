"""The two planes agree on where the heartbeat is and what its instant is called.

**This is the one agreement whose violation looks like the opposite of itself.**
Curation's reader treats a document without a `reported_at` key as an unreadable
heartbeat and says so on the health panel. A display plane that spelled the field
`timestamp` would therefore be reported as *down* while running perfectly — this
product's defining failure mode, manufactured by the mechanism built to detect it.
The filename has the same shape: write to the wrong name and the reader reports,
truthfully and uselessly, that the display plane has never reported at all.

Neither plane can import the other — the isolation norm forbids display reaching
into curation, and they are separate projects with separate interpreters — so the
constants are declared twice on purpose. That duplication is safe only if
something compares them, and nothing did until this file. It reads both sources
rather than importing either, which is the same technique `test_plane_isolation.py`
uses and works from the repository root with no environment of either plane's.

The guard is proven able to fail below, because a check nobody has watched go red
is a check nobody knows is wired up.
"""

import ast
import pathlib

import pytest

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
WRITER = REPOSITORY_ROOT / "display" / "src" / "display" / "heartbeat.py"
READER = REPOSITORY_ROOT / "curation" / "src" / "curation" / "manifest" / "heartbeat.py"

#: The names that have to match, as each side spells the constant holding them.
SHARED_CONSTANTS = ("HEARTBEAT_FILENAME", "REPORTED_AT_KEY")


def string_constants(source: pathlib.Path) -> dict[str, str]:
    """Every module-level `NAME: ... = "literal"` in a file, without importing it.

    Annotated assignments only, which is how both modules declare these — they are
    `Final[str]`. A plain assignment would be missed, so the emptiness of the
    result is asserted against rather than assumed.
    """
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    found: dict[str, str] = {}
    for node in tree.body:
        target = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target = node.target.id
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target = node.targets[0].id
        if target is not None and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            found[target] = node.value.value
    return found


def test_both_modules_exist_to_be_compared():
    """The vacuity check: this whole file passes trivially over two missing files."""
    assert WRITER.is_file(), f"no heartbeat writer at {WRITER}"
    assert READER.is_file(), f"no heartbeat reader at {READER}"


@pytest.mark.parametrize("constant", SHARED_CONSTANTS)
def test_the_planes_agree(constant: str):
    written = string_constants(WRITER)
    read = string_constants(READER)

    assert constant in written, f"the display plane's heartbeat writer declares no {constant}"
    assert constant in read, f"the curation plane's heartbeat reader declares no {constant}"
    assert written[constant] == read[constant], (
        f"the planes disagree about {constant}: "
        f"display writes {written[constant]!r}, curation reads {read[constant]!r}. "
        "A mismatch here reports a running display plane as down."
    )


def test_the_agreed_values_are_the_ones_the_artifacts_name():
    """Pinned literally, because both sides moving together is still a break.

    `observability-strategy.md` § The Health Surface states both names as the
    contract. A rename that updated both planes would pass the comparison above
    while silently orphaning every heartbeat already on disk and every artifact
    that documents it.
    """
    written = string_constants(WRITER)

    assert written["HEARTBEAT_FILENAME"] == "display-heartbeat.json"
    assert written["REPORTED_AT_KEY"] == "reported_at"


class TestTheGuardCanFail:
    def test_it_catches_a_disagreement(self, tmp_path: pathlib.Path):
        agreeing = tmp_path / "reader.py"
        agreeing.write_text('REPORTED_AT_KEY: Final[str] = "reported_at"\n')
        disagreeing = tmp_path / "writer.py"
        disagreeing.write_text('REPORTED_AT_KEY: Final[str] = "timestamp"\n')

        assert string_constants(agreeing)["REPORTED_AT_KEY"] != string_constants(disagreeing)["REPORTED_AT_KEY"]

    def test_it_reads_a_plain_assignment_too(self, tmp_path: pathlib.Path):
        """So a module dropping its `Final[str]` annotation does not go unread."""
        plain = tmp_path / "plain.py"
        plain.write_text('HEARTBEAT_FILENAME = "display-heartbeat.json"\n')

        assert string_constants(plain)["HEARTBEAT_FILENAME"] == "display-heartbeat.json"

    def test_it_does_not_invent_constants_that_are_not_there(self, tmp_path: pathlib.Path):
        empty = tmp_path / "empty.py"
        empty.write_text('"""No constants here."""\n\nINTERVAL = 60\n')

        assert string_constants(empty) == {}
