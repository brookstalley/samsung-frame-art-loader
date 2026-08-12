"""The two planes agree on what the files between them are called.

**This is the one agreement whose violation looks like the opposite of itself.**
Curation's reader treats a document without a `reported_at` key as an unreadable
heartbeat and says so on the health panel. A display plane that spelled the field
`timestamp` would therefore be reported as *down* while running perfectly — this
product's defining failure mode, manufactured by the mechanism built to detect it.
The filename has the same shape: write to the wrong name and the reader reports,
truthfully and uselessly, that the display plane has never reported at all.

**The manifest's name is here for the same reason**, though its failure is the
mirror image: curation publishing to one name while display waits on another is a
wall that never changes and a journal that says, correctly, that no manifest has
arrived. Both names became *templates* carrying a wall id on 2026-08-12, which is
a second way for two literals to drift and the reason the manifest pair stopped
being an unguarded duplication.

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

#: The manifest's two ends. It runs the other way — curation writes, display
#: reads — so "writer" and "reader" are the heartbeat's roles, and these are
#: named for the plane instead.
MANIFEST_IN_DISPLAY = REPOSITORY_ROOT / "display" / "src" / "display" / "config.py"
MANIFEST_IN_CURATION = REPOSITORY_ROOT / "curation" / "src" / "curation" / "manifest" / "builder.py"

#: Every declaration both planes make separately and must spell identically, as
#: `(constant, display's copy, curation's copy)`.
SHARED_CONSTANTS = (
    ("HEARTBEAT_FILENAME_TEMPLATE", WRITER, READER),
    ("REPORTED_AT_KEY", WRITER, READER),
    ("MANIFEST_FILENAME_TEMPLATE", MANIFEST_IN_DISPLAY, MANIFEST_IN_CURATION),
)


def string_constants(source: pathlib.Path) -> dict[str, str]:
    """Every module-level `NAME: ... = "literal"` in a file, without importing it.

    Both spellings are read: an annotated assignment, which is how both modules
    declare these today (`Final[str]`), and a plain one, so a module that drops
    its annotation does not silently fall out of the comparison. Only single-name
    targets count — a tuple unpack holding one of these would be a shape neither
    module uses and guessing at it would be worse than missing it.
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
    """The vacuity check: this whole file passes trivially over missing files."""
    for constant, in_display, in_curation in SHARED_CONSTANTS:
        assert in_display.is_file(), f"nothing at {in_display} to read {constant} from"
        assert in_curation.is_file(), f"nothing at {in_curation} to read {constant} from"


@pytest.mark.parametrize(("constant", "in_display", "in_curation"), SHARED_CONSTANTS)
def test_the_planes_agree(constant: str, in_display: pathlib.Path, in_curation: pathlib.Path):
    display = string_constants(in_display)
    curation = string_constants(in_curation)

    assert constant in display, f"{_relative(in_display)} declares no {constant}"
    assert constant in curation, f"{_relative(in_curation)} declares no {constant}"
    assert display[constant] == curation[constant], (
        f"the planes disagree about {constant}: "
        f"{_relative(in_display)} says {display[constant]!r}, "
        f"{_relative(in_curation)} says {curation[constant]!r}. "
        "A mismatch here is a running plane reported as down, or a wall that never changes."
    )


def test_the_agreed_values_are_the_ones_the_artifacts_name():
    """Pinned literally, because both sides moving together is still a break.

    `observability-strategy.md` § The Health Surface states the heartbeat's two
    names as the contract, and `architecture.md` § One manifest per wall states
    the manifest's. A rename that updated both planes would pass the comparison
    above while silently orphaning every file already on disk and every artifact
    that documents it.

    **Both filenames are templates carrying a wall id**, since 2026-08-12: one
    manifest and one heartbeat per wall, so a display cannot open a wall it does
    not serve and health can name which wall is silent. The placeholder is part
    of the pin — a template that lost it would put every wall back in one file.
    """
    assert string_constants(WRITER)["HEARTBEAT_FILENAME_TEMPLATE"] == "display-heartbeat-{wall_id}.json"
    assert string_constants(WRITER)["REPORTED_AT_KEY"] == "reported_at"
    assert string_constants(MANIFEST_IN_DISPLAY)["MANIFEST_FILENAME_TEMPLATE"] == "theme-manifest-{wall_id}.json"


def _relative(path: pathlib.Path) -> str:
    return str(path.relative_to(REPOSITORY_ROOT))


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
        plain.write_text('HEARTBEAT_FILENAME_TEMPLATE = "display-heartbeat-{wall_id}.json"\n')

        assert string_constants(plain)["HEARTBEAT_FILENAME_TEMPLATE"] == "display-heartbeat-{wall_id}.json"

    def test_it_does_not_invent_constants_that_are_not_there(self, tmp_path: pathlib.Path):
        empty = tmp_path / "empty.py"
        empty.write_text('"""No constants here."""\n\nINTERVAL = 60\n')

        assert string_constants(empty) == {}
